#!/usr/bin/env python3
"""Host differential test of the battle formula readable code against the game's own ARM code.

    python src/readable/battle/tests/formula_diff.py             all functions, 300 cases each
    python src/readable/battle/tests/formula_diff.py -n 2000     more cases
    python src/readable/battle/tests/formula_diff.py --seed 7    another random sequence
    python src/readable/battle/tests/formula_diff.py --only unit_hit
    python src/readable/battle/tests/formula_diff.py --plant     also plant bugs: each must be caught

The method of stance_diff.py and triangle_diff.py (same folder): for every readable function
of src/readable/battle/formula_*.c the test makes up guest states (units, their Person and
class records, carried items, Item records, the weapon-rank tables, fight sides, the
one-time caches; all random test values, never game data, and on purpose often outside the
ranges the game uses: negative stats, huge limits, slots past 4, bools that are not 0/1,
random rally kinds and distances), runs the ORIGINAL ARM code from the owner's
extracted/text.bin in arm_mini.py and the readable C function (built with the host gcc
against tools/readable/stub/) on the same memory, and compares:

  - overrides (21): r0, the number of bytes read from unmapped memory (tier 2's
    verify compares that count too) AND the number of calls to ItemSubKind::Get 0x0019B97C
    (the live shadow compare counts callee calls, docs/DECISIONS.md F-018; on the C side a
    guest call to it reaches its readable override item_subkind_record, as in the capture
    library), through their override entry in readable mode (the
    stat getters with their fifth argument on the guest stack); about 1 case in 8 uses an
    unmapped unit pointer, as tier 2's made-up state does (r0 = 2);
  - helpers: forecast_detail against what the whole of Side::CalculateDetail 0x00348754
    stores into the BattleDetail row (its four Calculate* callees are no-op stubs: they are
    not part of the helper), forecast_crit against the region 0x00347CEC..0x00347DDC of
    BattleInfo::CalculateSimple.

Every guest function the readable code still calls is answered by one table on both sides
(unit::Item::ToData / GetHit / GetCritical / GetPower, Item::IsMagic, Unit::GetLimit,
unit::Edit::GetCapability, Unit::GetDoubleCapability, Unit::IsEquipSkill, GetEnhanceHave,
Unit::GetRangeI / GetRangeO). Everything else runs as ARM code: the five stat getters inside
GetHit and the others, GetItemIndexEquipped, the weapon-rank code of the triangle batch,
GetCritical / GetSecure / GetContinuous inside CalculateDetail. A one-time cache that is not
filled must make the original reach the guard routine and the readable code give up.

--plant copies the battle sources to build/readable/formula/plant/, makes one small wrong
change at a time (the list PLANTS below), rebuilds and reruns: every planted bug must give
at least one mismatch.

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
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
from stance_diff import pick, s32  # noqa: E402
import triangle_diff as T  # noqa: E402  (tables, units, items, the rank caches)

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "formula")
SRC_BATTLE = os.path.join(ROOT, "src", "readable", "battle")
GUARD = T.GUARD
SP = T.SP

# guest functions answered by the table: address -> number of arguments in the key
TO_DATA = T.TO_DATA
ITEM_HIT, ITEM_CRIT, ITEM_POWER, IS_MAGIC = 0x0053B2A4, 0x0053AD54, 0x0053B4B4, 0x005290B8
GET_LIMIT, EDIT_CAP, DOUBLE_CAP, IS_EQUIP, ENHANCE = 0x005337F0, 0x0053ABEC, 0x00530A34, 0x0052DD04, 0x0033A790
RANGE_I, RANGE_O = 0x00534474, 0x00534510
STUBS = {TO_DATA: 1, ITEM_HIT: 1, ITEM_CRIT: 1, ITEM_POWER: 1, IS_MAGIC: 1, GET_LIMIT: 2, EDIT_CAP: 2,
         DOUBLE_CAP: 3, IS_EQUIP: 2, ENHANCE: 2, RANGE_I: 2, RANGE_O: 2}
DETAIL_CALLEES = (0x00349880, 0x00349CF0, 0x00348FF0, 0x003491F8)  # no-op stubs inside Side::CalculateDetail

# caches (src/readable/battle/formulas.h)
STAT_CACHES = {  # stat -> (guards, skill-id addresses)
    1: ((0x006D9740, 0x006D973C, 0x006D9738, 0x006D9734), (0x006D962C, 0x006D962E, 0x006D9630, 0x006D9632)),
    2: ((0x006D974C, 0x006D9748, 0x006D9744), (0x006D9634, 0x006D9636, 0x006D9638)),
    3: ((0x006D9758, 0x006D9754, 0x006D9750), (0x006D963A, 0x006D963C, 0x006D963E)),
    4: ((0x006D976C, 0x006D9768, 0x006D9764, 0x006D9760, 0x006D975C),
        (0x006D9640, 0x006D9642, 0x006D9644, 0x006D9646, 0x006D9648)),
    5: ((0x006D9778, 0x006D9774, 0x006D9770), (0x006D964A, 0x006D964C, 0x006D964E)),
}
UNIT_GUARDS = (0x006D9924, 0x006D9920, 0x006D991C, 0x006D9938, 0x006D9934, 0x006D9930, 0x006D992C, 0x006D9928)
UNIT_MASKS = (0x006D9C48, 0x006D9C50, 0x006D9C58, 0x006D9C68, 0x006D9C70, 0x006D9C78, 0x006D9C80, 0x006D9C60)
FC_GUARDS = (0x006D6A08, 0x006D6A04, 0x006D6A00, 0x006D69FC, 0x006D69F8, 0x006D6A14, 0x006D6A10, 0x006D6A0C, 0x006D9898)  # last: Unit::GetRangeI's cache, asked by forecast_strikes (round 8)
FC_MASKS = (0x006D6AE8, 0x006D6AF0, 0x006D6AF8, 0x006D6B08, 0x006D6B00)
FC_IDS = (0x006D6946, 0x006D6948, 0x006D694A)
RULE_PTR, RULE = 0x006D7ED0, 0x08060000
BASE_6918 = 0x006D6918

FORCE = lambda k: 0x08030000 + k * 0x10  # noqa: E731
EDIT = lambda k: 0x08040000 + k * 0x40  # noqa: E731
PARTNER = lambda k: 0x08050000 + k * 0x400  # noqa: E731
INFO = T.INFO
INFO_FLAGS = INFO + 0x804
SKILL_IDS = [1, 2, 3, 5, 8, 13, 21, 34, 40, 63, 100, 255]
RALLY_KINDS = [9, 10, 11, 12, 13, 16, 17, 18, 19, 20, 23, 24, 25, 26, 27, 31, 32, 33]


# ------------------------------------------------------------------ the made-up state
def guard(st, addr, cold_p=0.01):
    T.guard(st, addr, cold_p)


def all_caches(st) -> None:
    """Every cache of the formula code (and the triangle code under it), mostly warm."""
    rng = st.rng
    T.caches(st, 0.01)
    for guards, ids in STAT_CACHES.values():
        for g in guards:
            guard(st, g)
        for i in ids:
            st.put(i, 2, rng.choice(SKILL_IDS) if rng.random() < 0.9 else rng.choice([0, -1, 0x7FFF]) & 0xFFFF)
    for g in UNIT_GUARDS + FC_GUARDS:
        guard(st, g)
    for m in UNIT_MASKS + FC_MASKS:
        st.put(m, 8, 1 << rng.randrange(64))
    for i in FC_IDS:
        st.put(i, 2, rng.choice(SKILL_IDS + [-3, 600]) & 0xFFFF)
    st.put(RULE_PTR, 4, RULE)
    st.put(RULE + 4, 4, rng.randrange(1 << 32) & ~(0 if rng.random() < 0.3 else 0x40000))


def skill_ids(st) -> list[int]:
    ids = set()
    for _g, addrs in STAT_CACHES.values():
        for a in addrs:
            v = st.mem.get(a, 0) | st.mem.get(a + 1, 0) << 8
            ids.add(v - 0x10000 if v & 0x8000 else v)
    for a in FC_IDS:
        v = st.mem.get(a, 0) | st.mem.get(a + 1, 0) << 8
        ids.add(v - 0x10000 if v & 0x8000 else v)
    return sorted(ids)


def stat_value(rng) -> int:
    return s32(pick(rng, [0, 1, 5, 10, 20, 30, 40, 60, 99], [-1, -50, 120, 200, 0x7FFFFFFF, -0x80000000], 0.15))


def full_unit(st, k: int) -> int:
    """A unit with everything the stat getters and the battle numbers read."""
    rng = st.rng
    u = T.make_unit(st, k)
    st.fill(T.PERSON(k), 0x48)
    for base in (u, T.PERSON(k), T.JOB(k)):
        for m in UNIT_MASKS[:7]:
            T.maybe_flag(st, base, m, 0.2)
    p, j = T.PERSON(k), T.JOB(k)
    for s in range(8):  # bases: usually small, sometimes anything (the random fill)
        if rng.random() < 0.7:
            st.put(p + 0x38 + s, 1, pick(rng, [0, 1, 2, 3, 5, 8], [-3, 60]) & 0xFF)
            st.put(j + 0x1C + s, 1, pick(rng, [0, 3, 5, 8, 12, 20], [-10, 127]) & 0xFF)
            st.put(u + 0xC8 + s, 1, pick(rng, [0, 0, 1, 4, 10], [-5, 100]) & 0xFF)
    for off in (0x4C, 0x4E, 0x50, 0x52):  # class hit / crit / avoid / dodge
        st.put(j + off, 2, s32(pick(rng, [0, 5, 10, 15, 20, 30], [-10, -0x8000, 0x7FFF, 1000])) & 0xFFFF)
    # state flags: the pair bits, bit 21, bit 30, bit 5
    state = rng.randrange(1 << 32)
    for bit, pr in ((2, 0.4), (4, 0.4), (0x200000, 0.3), (0x40000000, 0.3), (0x20, 0.5)):
        state = (state | bit) if rng.random() < pr else (state & ~bit)
    st.put(u + 8, 4, state)
    for i in range(6):  # condition bytes: mostly clear
        st.put(u + 0x28 + i, 1, rng.randrange(256) if rng.random() < 0.35 else 0)
    st.put(u + 0xA4, 4, FORCE(k))
    st.fill(FORCE(k), 0x10)
    st.put(FORCE(k) + 8, 1, pick(rng, [0, 1, 1, 2], [3, 0xFF]))
    st.put(u + 0xA8, 4, PARTNER(k) if rng.random() < 0.6 else 0)
    st.put(u + 0xB0, 4, EDIT(k) if rng.random() < 0.4 else 0)
    # carried items: number + flags (0x4000 = equipped), each answered by ToData
    eq = rng.choice([None, 0, 1, 2, 3, 4, 0, 0])
    for slot in range(5):
        a = u + 0x108 + 4 * slot
        flags = rng.randrange(1 << 16) & ~0x4000
        if eq is not None and (slot == eq or (slot > eq and rng.random() < 0.2)):
            flags |= 0x4000
        st.put(a, 2, rng.randrange(1, 400))
        st.put(a + 2, 2, flags)
        item_record(st, a, rng.randrange(8))
    # what the guest calls answer for this unit
    for s in range(8):
        st.oracle[(GET_LIMIT, u, s)] = stat_value(rng)
        st.oracle[(EDIT_CAP, EDIT(k), s)] = s32(pick(rng, [0, 1, -1, 2, -2, 3], [100, -100]))
        st.oracle[(DOUBLE_CAP, PARTNER(k), s, u)] = s32(pick(rng, [0, 1, 2, 3, 4], [-7, 90]))
        st.oracle[(ENHANCE, u, s)] = s32(pick(rng, [0, 0, 1, 2, 4], [-3, 0x7FFFFFFF]))
    for i in skill_ids(st):
        st.oracle[(IS_EQUIP, u, s32(i))] = int(rng.random() < 0.4)
    return u


def item_record(st, addr: int, k: int) -> None:
    """The unit::Item at addr is answered by Item record k (and its item-level numbers)."""
    rng = st.rng
    data = T.ITEMDATA(k)
    st.oracle[(TO_DATA, addr & 0xFFFFFFFF)] = data
    st.oracle[(ITEM_HIT, addr & 0xFFFFFFFF)] = s32(pick(rng, [50, 70, 80, 90, 100], [0, -20, 0x7FFFFFF0]))
    st.oracle[(ITEM_CRIT, addr & 0xFFFFFFFF)] = s32(pick(rng, [0, 5, 10, 20], [-5, 255]))
    st.oracle[(ITEM_POWER, addr & 0xFFFFFFFF)] = s32(pick(rng, [3, 5, 8, 11, 16], [0, -4, 200]))
    if (IS_MAGIC, data) not in st.oracle:
        st.oracle[(IS_MAGIC, data)] = int(rng.random() < 0.3)
        for off in (0x24, 0x26):
            st.put(data + off, 2, s32(pick(rng, [0, 5, 10, 20], [-15, -0x8000, 0x7FFF])) & 0xFFFF)
        for off in (0x2A, 0x2B):
            st.put(data + off, 1, pick(rng, [0, 0, -1, -3, 2, 5], [-128, 127]) & 0xFF)
        for s in range(8):
            st.put(data + 0x38 + s, 1, pick(rng, [0, 0, 0, 1, 2, -2, 4], [-128, 127]) & 0xFF)
        for m in (UNIT_MASKS[7], FC_MASKS[2], FC_MASKS[3], FC_MASKS[4]):
            T.maybe_flag(st, data, m, 0.2)


def unit_state(rng):
    st = T.base_state(rng)
    all_caches(st)
    u = full_unit(st, 0)
    if rng.random() < 0.12:  # an unmapped unit, as in tier 2's made-up state (r0 = 2): every field reads 0
        u = rng.choice([2, 0x40, 0x7FF0, 0x0FFF0000])
    return st, u


def item_arg(st, u) -> int:
    rng = st.rng
    r = rng.random()
    if r < 0.12:
        return 0
    if r < 0.75:
        return u + 0x108 + 4 * rng.randrange(5)
    a = T.ITEM(rng.randrange(4))
    st.put(a, 4, rng.randrange(1 << 32))
    item_record(st, a, rng.randrange(8))
    return a


def bool_arg(rng) -> int:
    return pick(rng, [0, 1, 1], [2, 0x100, 0xFFFFFFFF], 0.15)


def slot_arg(rng) -> int:
    return s32(pick(rng, [-1, -1, 0, 1, 2, 3, 4], [-2, 5, 7, -0x80000000, 0x7FFFFFFF], 0.15))


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def gen_equipped(rng):
    st, u = unit_state(rng)
    return st, "ov:0x005310C0", [u, 0, 0, 0], ("call", 0x005310C0)


def gen_stat(addr):
    def gen(rng):
        st, u = unit_state(rng)
        st.put(SP, 4, s32(pick(rng, [0, 0, 0] + RALLY_KINDS, [rng.randrange(1 << 32), -1], 0.1)))
        return st, f"ov:0x{addr:08X}", [u, item_arg(st, u), bool_arg(rng), bool_arg(rng)], ("call", addr)
    return gen


def gen_item_form(addr, with_bool):
    def gen(rng):
        st, u = unit_state(rng)
        return st, f"ov:0x{addr:08X}", [u, item_arg(st, u), bool_arg(rng) if with_bool else 0, 0], ("call", addr)
    return gen


def gen_slot_form(addr, with_bool):
    def gen(rng):
        st, u = unit_state(rng)
        return st, f"ov:0x{addr:08X}", [u, slot_arg(rng), bool_arg(rng) if with_bool else 0, 0], ("call", addr)
    return gen


def battle_state(rng, full_units: bool):
    """Four fight sides: types, units, weapons, flags, the two detail rows, skill bits, bonuses."""
    st = T.base_state(rng)
    all_caches(st)
    st.fill(INFO, 0x808)
    st.put(INFO_FLAGS, 4, rng.randrange(1 << 32) & ~(0 if rng.random() < 0.3 else 0x21))
    for k in range(4):
        side = INFO + k * 0x200
        st.put(side, 1, k if rng.random() < 0.8 else rng.choice([0, 1, 2, 3, 4, 0xFF]))
        if rng.random() < 0.92:
            u = full_unit(st, k) if full_units else T.make_unit(st, k)
            if not full_units:
                st.fill(T.PERSON(k), 0x10)
                for base in (u, T.PERSON(k), T.JOB(k)):
                    for m in FC_MASKS[:2]:
                        T.maybe_flag(st, base, m, 0.3)
                st.put(u + 0x28, 1, rng.randrange(256) if rng.random() < 0.4 else 0)
                for i in skill_ids(st):
                    st.oracle[(IS_EQUIP, u, s32(i))] = int(rng.random() < 0.3)
        else:
            u = 0
        st.put(side + 4, 4, u)
        st.put(side + 0x10, 2, 0 if rng.random() < 0.1 else rng.randrange(1, 0x10000))
        item_record(st, side + 0x10, rng.randrange(8))
        flags = rng.randrange(1 << 32)
        for bit, p in ((0x1, 0.4), (0x2, 0.3), (0x40, 0.2), (0x80, 0.2), (0x100, 0.15), (0x4000, 0.15)):
            flags = (flags | bit) if rng.random() < p else (flags & ~bit)
        st.put(side + 0x28, 4, flags)
        for row in range(2):  # detail rows: hit/crit/avoid/crit avoid and the speeds
            d = side + 0x48 + 0x24 * row
            for off in (0x14, 0x16, 0x18, 0x1A):
                st.put(d + off, 2, s32(pick(rng, [0, 10, 40, 70, 100, 150], [-30, -0x8000, 0x7FFF])) & 0xFFFF)
            for off in (0x1C, 0x20):
                st.put(d + off, 4, s32(pick(rng, [0, 5, 10, 15, 20, 25], [-3, 0x7FFFFFFF, -0x80000000])))
        for off in (0xAE, 0xB2, 0x13A, 0x13E, 0x13E + 0x94, 0x1EE, 0x1F2):
            st.put(side + off, 2, s32(pick(rng, [0, 0, 5, 10, 15], [-20, 0x7FFF, 0x8000, 0xFFFF])) & 0xFFFF)
        for off in (0x140, 0x144):
            st.put(side + off, 4, s32(pick(rng, [0, 0, 1, 2, 5], [-4, 0x7FFFFFFF])))
        for i in skill_ids(st):  # the skill bit sets of both rows
            for row in range(2):
                b = side + 0xE6 + 0x94 * row + (i >> 3)
                if INFO <= b < INFO + 0x800 and rng.random() < 0.3:
                    st.put(b, 1, st.mem.get(b, 0) | 1 << (i & 7))
        st.oracle[(RANGE_I, u, side + 0x10)] = s32(pick(rng, [1, 1, 2, 3], [0, -1, 9]))
        st.oracle[(RANGE_O, u, side + 0x10)] = s32(pick(rng, [1, 2, 2, 3], [0, 5, -1]))
    return st


def side_pair(rng) -> tuple[int, int]:
    i = rng.randrange(4)
    j = rng.choice([x for x in range(4) if x != i]) if rng.random() < 0.9 else i
    return INFO + i * 0x200, INFO + j * 0x200


def set_bits(st, addr: int, on: int = 0, off: int = 0) -> None:
    v = int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(4)), "little")
    st.put(addr, 4, (v | on) & ~off)


def clear_flag(st, addr: int, mask_addr: int) -> None:
    T.maybe_flag(st, addr, mask_addr, 0.0)


def gen_fhit(rng):
    st = battle_state(rng, False)
    s, o = side_pair(rng)
    if rng.random() < 0.5:  # focused: a hindering staff against a target with only some of the defences
        set_bits(st, s + 0x28, on=0x80, off=0x40 if rng.random() < 0.7 else 0)
        target = st.mem.get(o + 4, 0) | st.mem.get(o + 5, 0) << 8 | st.mem.get(o + 6, 0) << 16 | st.mem.get(o + 7, 0) << 24
        if target:
            k = (target - 0x08000000) // 0x400
            for m in FC_MASKS[:2]:
                if rng.random() < 0.6:
                    for base in (target, T.PERSON(k), T.JOB(k)):
                        clear_flag(st, base, m)
            for i in skill_ids(st):
                if rng.random() < 0.7:
                    st.oracle[(IS_EQUIP, target, s32(i))] = 0
        if rng.random() < 0.7:
            set_bits(st, RULE + 4, off=0x40000)
    return st, "ov:0x00525090", [s, o, 0, 0], ("call", 0x00525090)


def gen_fstrikes(rng):
    st = battle_state(rng, False)
    s, o = side_pair(rng)
    d = s32(pick(rng, [1, 1, 2, 3], [0, -1, 7, 0x7FFFFFFF]))
    if rng.random() < 0.6:  # focused: reach the speed comparison and the skill bits
        set_bits(st, INFO_FLAGS, on=1 if rng.random() < 0.6 else 0, off=0x20)
        set_bits(st, s + 0x28, on=1 if rng.random() < 0.5 else 0, off=0x142 if rng.random() < 0.8 else 0x140)
        set_bits(st, o + 0x28, off=0x140)
        u = st.mem.get(s + 4, 0) | st.mem.get(s + 5, 0) << 8 | st.mem.get(s + 6, 0) << 16 | st.mem.get(s + 7, 0) << 24
        if u:
            st.put(u + 0x28, 1, st.mem.get(u + 0x28, 0) & ~0x08)
        for side in (s, o):  # the no-double skill bit: sometimes only in one row
            for row in range(2):
                for i in skill_ids(st):
                    b = side + 0xE6 + 0x94 * row + (i >> 3)
                    if INFO <= b < INFO + 0x800 and rng.random() < 0.6:
                        st.put(b, 1, st.mem.get(b, 0) & ~(1 << (i & 7)))
        row = 1 if st.mem.get(s, 0) in (2, 3) else 0
        theirs = rng.choice([0, 5, 10, 15])
        st.put(o + 0x48 + 0x24 * row + 0x20, 4, theirs)
        st.put(s + 0x48 + 0x1C, 4, theirs + rng.choice([4, 5, 5, 6]))
    return st, "ov:0x005259D4", [s, o, d, INFO_FLAGS], ("call", 0x005259D4)


def gen_fdetail(rng):
    st = battle_state(rng, True)
    s, o = side_pair(rng)
    return st, "detail", [s, o, 0, 0], ("detail",)


def gen_fcrit(rng):
    st = battle_state(rng, False)
    s, o = side_pair(rng)
    return st, "fcrit", [s, o, 0, 0], ("fcrit",)


FUNCS = {
    "unit_equipped_index": gen_equipped,
    "unit_strength": gen_stat(0x0052A80C),
    "unit_magic": gen_stat(0x0052A500),
    "unit_skill": gen_stat(0x0052C30C),
    "unit_speed": gen_stat(0x0052D860),
    "unit_luck": gen_stat(0x0052BC5C),
    "unit_hit": gen_item_form(0x00532DC4, True),
    "unit_hit_of_slot": gen_slot_form(0x00532D90, True),
    "unit_avoid": gen_item_form(0x00533524, False),
    "unit_avoid_of_slot": gen_slot_form(0x005334F0, False),
    "unit_crit": gen_item_form(0x0052B9BC, False),
    "unit_crit_of_slot": gen_slot_form(0x0052B988, False),
    "unit_crit_avoid": gen_item_form(0x005345E0, False),
    "unit_attack": gen_item_form(0x00534188, True),
    "unit_attack_of_slot": gen_slot_form(0x005342B8, True),
    "unit_attack_for_terrain": gen_item_form(0x00534180, False),
    "unit_attack_for_terrain_of_slot": gen_slot_form(0x005309A0, False),
    "unit_attack_speed": gen_item_form(0x0052E134, False),
    "unit_defense_speed": gen_item_form(0x00530834, False),
    "forecast_hit": gen_fhit,
    "forecast_strikes": gen_fstrikes,
    "forecast_detail": gen_fdetail,
    "forecast_crit": gen_fcrit,
}
# Planted bugs (H6 survivors, docs/harness/H6_SURVIVORS.md, round 12) that no case above told apart. make_cases runs
# SHARP from its own random stream (n // 3 cases each), so the cases of FUNCS stay exactly as they were.

def gen_fhit_clamp(rng):
    """forecast_hit's clamp at its edges: a plain weapon (no staff), hit - avoid exactly 101, 100, 99, 1, 0, -1 ...
    (catches the upper clamp's test `v > 100` made `v > 101`: only v = 101 tells them apart)."""
    st = battle_state(rng, False)
    i = rng.randrange(4)
    j = rng.choice([x for x in range(4) if x != i])
    s, o = INFO + i * 0x200, INFO + j * 0x200
    st.put(s + 0x10, 2, rng.randrange(1, 0x10000))
    set_bits(st, s + 0x28, off=0xC0)  # no staff, no hindering staff
    row = 1 if st.mem.get(s, 0) in (2, 3) else 0
    hit = rng.choice([0, 40, 100, 101, 150, 201])
    diff = rng.choice([101, 101, 101, 100, 102, 99, 1, 0, -1])
    st.put(s + 0x48 + 0x14, 2, s32(hit) & 0xFFFF)
    st.put(o + 0x48 + 0x24 * row + 0x18, 2, s32(hit - diff) & 0xFFFF)
    return st, "ov:0x00525090", [s, o, 0, 0], ("call", 0x00525090)


def gen_hit_none_cold(rng):
    """unit_hit with no weapon while one of its three caches is cold: the game asks the three guards before it
    tests the weapon, so it reaches the cold one and gives up; the readable code must give up too (catches the
    guard test `!G10 || !G20 || !G30` made `!G10 || (!G20 && !G30)`: only one of G20 / G30 cold tells them apart)."""
    st, u = unit_state(rng)
    for g in (0x006D9924, 0x006D9920, 0x006D991C):  # S_HitGuard10, 20, 30 (formulas.h): warm
        st.put(g, 4, 1)
    st.put(rng.choice([0x006D9920, 0x006D991C, 0x006D9924]), 4, 0)  # then one cold
    return st, "ov:0x00532DC4", [u, 0, bool_arg(rng), 0], ("call", 0x00532DC4)


SHARP = [
    ("forecast_hit", gen_fhit_clamp),
    ("unit_hit", gen_hit_none_cold),
]
OVERRIDES = sorted({int(k.split(":")[1], 16) for k in
                    ("ov:0x005310C0 ov:0x0052A80C ov:0x0052A500 ov:0x0052C30C ov:0x0052D860 ov:0x0052BC5C "
                     "ov:0x00532DC4 ov:0x00532D90 ov:0x00533524 ov:0x005334F0 ov:0x0052B9BC ov:0x0052B988 "
                     "ov:0x005345E0 ov:0x00534188 ov:0x005342B8 ov:0x00534180 ov:0x005309A0 ov:0x0052E134 "
                     "ov:0x00530834 ov:0x00525090 ov:0x005259D4").split()})


# ------------------------------------------------------------------ the ARM side
SUBKIND_GET = 0x0019B97C  # ItemSubKind::Get(int): runs as ARM code (C side: its readable override); calls counted


class CountingCpu(A.Cpu):
    """arm_mini's Cpu, counting the BL/BLX calls to ItemSubKind::Get (the callee still runs)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.subkind_calls = 0

    def call(self, target: int, ret: int) -> bool:
        if target == SUBKIND_GET:
            self.subkind_calls += 1
        return super().call(target, ret)


def arm_run(text: bytes, st, args: list[int], how: tuple) -> list[int]:
    """Expected outputs, in the order the C driver prints them: [gave_up, values...]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def answer(f, n):
        return lambda cpu, a: st.oracle.get((f,) + tuple(a[:n]), 0)
    stubs = {f: answer(f, n) for f, n in STUBS.items()}
    if how[0] == "detail":
        for f in DETAIL_CALLEES:
            stubs[f] = lambda cpu, a: cpu.r[0]
    cpu = CountingCpu(mem, stubs, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    try:
        if how[0] == "call":
            cpu.run(how[1])
            # the unmapped bytes read (verify compares this count too) and the ItemSubKind::Get calls
            # (the live shadow compare counts the callee calls, docs/DECISIONS.md F-018)
            return [0, cpu.r[0], mem.faults, cpu.subkind_calls]
        if how[0] == "detail":
            side, other = args[0], args[1]
            cpu.run(0x00348754)
            t = mem.read(other, 1)
            row = 1 if t in (2, 3) else 0
            d = side + 0x48 + 0x24 * row
            return [0, row, A.sx(mem.read(d + 0x16, 2), 16) & 0xFFFFFFFF, A.sx(mem.read(d + 0x1A, 2), 16) & 0xFFFFFFFF,
                    mem.read(d + 0x1C, 4), mem.read(d + 0x20, 4)]
        if how[0] == "fcrit":
            cpu.r[4], cpu.r[8], cpu.r[10], cpu.r[11] = args[0], args[1], BASE_6918, 0
            cpu.run(0x00347CEC, stop={0x00347DDC})
            return [0, cpu.r[7]]
    except A.ColdGuard:
        return [1]
    raise ValueError(how)


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/battle/tests/formula_diff.py: runs readable battle formula
   functions on memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "formulas.h"

static uint8_t **pages, **nopages;
static uint32_t used[8192]; static int nused;
static uint8_t *at(uint32_t a, int make) {
    uint8_t *p = pages[a >> 12];
    if (!p && make && nused < 8192) { p = pages[a >> 12] = calloc(4096, 1); used[nused++] = a >> 12; }
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

#define MAXO 2048
static uint32_t stub_n[16], stub_f[16]; static int nstubs;
static uint32_t o_key[MAXO][5], o_val[MAXO]; static int noracle;
static void oracle(Context *ctx) {
    uint32_t f = ctx->r[15], n = 0;
    for (int i = 0; i < nstubs; i++) if (stub_f[i] == f) n = stub_n[i];
    uint32_t v = 0;
    for (int i = 0; i < noracle; i++) {
        if (o_key[i][0] != f) continue;
        int ok = 1;
        for (uint32_t k = 0; k < n; k++) if (o_key[i][1 + k] != ctx->r[k]) ok = 0;
        if (ok) { v = o_val[i]; break; }
    }
    ctx->r[0] = v;
    ctx->r[15] = ctx->r[14];
}
/* ItemSubKind::Get: a guest call reaches its readable override, as in the capture library;
   the calls are counted (compared with the ARM side's) */
void override_0x0019B97C(Context *);
static int subkind_calls;
static void subkind_get(Context *ctx) { subkind_calls++; override_0x0019B97C(ctx); }
static Code lookup(Context *c, uint32_t a) {
    (void)c;
    for (int i = 0; i < nstubs; i++) if (stub_f[i] == a) return oracle;
    if (a == 0x0019B97Cu) return subkind_get;
    return NULL;
}
static int originals;
void fe_stub_original(Context *ctx) { originals++; ctx->r[0] = 0xDEADBEEFu; ctx->r[15] = ctx->r[14] & ~3u; }

static const Host host = {r8, r16, r32, w8, w16, w32, interp, lookup, svc};
static uint32_t vfp[32], fpscr;
static Context fresh(void) {
    Context c; memset(&c, 0, sizeof c);
    c.read_pages = nopages; c.write_pages = nopages; c.vfp = vfp; c.fpscr = &fpscr; c.host = &host;
    c.r[14] = 0x00123450u; c.budget = 1000;
    return c;
}

@OVERRIDE_DECLS@

static int hexval(int ch) { return ch <= '9' ? ch - '0' : (ch | 32) - 'a' + 10; }

int main(void) {
    pages = calloc(1u << 20, sizeof *pages);
    nopages = calloc(1u << 20, sizeof *nopages);
    fe_force_mode(FE_MODE_READABLE);
    static char line[1 << 16];
    char kind[64]; unsigned id = 0; uint32_t a[5] = {0};
    while (fgets(line, sizeof line, stdin)) {
        if (!strncmp(line, "stub ", 5)) {
            sscanf(line + 5, "%x %u", &stub_f[nstubs], &stub_n[nstubs]); nstubs++;
        } else if (!strncmp(line, "case ", 5)) {
            sscanf(line + 5, "%u %63s %x %x %x %x %x", &id, kind, &a[0], &a[1], &a[2], &a[3], &a[4]);
            for (int i = 0; i < nused; i++) { free(pages[used[i]]); pages[used[i]] = NULL; } nused = 0;
            noracle = 0; originals = 0; writes = 0; faults = 0; subkind_calls = 0;
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
            if (!strncmp(kind, "ov:", 3)) {
                uint32_t addr = (uint32_t)strtoul(kind + 3, NULL, 16);
                for (int i = 0; i < 4; i++) c.r[i] = a[i];
                int found = 0;
                for (unsigned i = 0; i < sizeof ovs / sizeof ovs[0]; i++) if (ovs[i].a == addr) { ovs[i].f(&c); found = 1; }
                if (!found) printf("%u NO-OVERRIDE\n", id);
                else if (originals) printf("%u 1 %d\n", id, faults); else printf("%u 0 %u %d %d\n", id, c.r[0], faults, subkind_calls);
            } else if (!strcmp(kind, "detail")) {
                ForecastDetail d; memset(&d, 0, sizeof d);
                forecast_detail(&c, a[0], a[1], &d);
                if (fe_gave_up(&c)) printf("%u 1\n", id);
                else printf("%u 0 %u %u %u %u %u\n", id, d.detail, (uint32_t)(int32_t)d.crit,
                            (uint32_t)(int32_t)d.crit_avoid, (uint32_t)d.attack_speed, (uint32_t)d.defense_speed);
            } else if (!strcmp(kind, "fcrit")) {
                int32_t r = forecast_crit(&c, a[0], a[1]);
                if (fe_gave_up(&c)) printf("%u 1\n", id); else printf("%u 0 %u\n", id, (uint32_t)r);
            }
            if (writes) printf("%u WROTE-GUEST %d\n", id, writes);
        }
    }
    return 0;
}
'''


def driver_text() -> str:
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in OVERRIDES)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in OVERRIDES) + "};\n"
    return DRIVER.replace("@OVERRIDE_DECLS@", decls + table)


def build_driver(cc: str, out: str, battle_dir: str) -> str:
    """Builds the driver with every source of src/readable/, the battle folder's taken from battle_dir."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "formula_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_BATTLE)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(battle_dir, f) for f in os.listdir(battle_dir) if f.endswith(".c")]
    exe = os.path.join(out, "formula_driver.exe" if os.name == "nt" else "formula_driver")
    inc = ["-I", battle_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"formula_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines = [f"stub {f:x} {k}" for f, k in STUBS.items()]
    expected: dict[int, tuple[str, list[int], tuple]] = {}
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
                exp = arm_run(text, st, args, how)
            except A.Unsupported as e:
                unsupported[name] = unsupported.get(name, 0) + 1
                if unsupported[name] == 1:
                    print(f"  ARM interpreter: {name}: {e}")
                continue
            expected[cid] = (name, exp, (kind, args))
            lines.append(f"case {cid} {kind} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
            for addr, data in st.regions():
                for off in range(0, len(data), 4096):
                    lines.append(f"mem {addr + off:x} {data[off:off + 4096].hex()}")
            for key, val in st.oracle.items():
                k = list(key) + [0] * (5 - len(key))
                lines.append("oracle " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in k) + f" {val & 0xFFFFFFFF:x}")
            lines.append("run")
            cid += 1
    return lines, expected, unsupported


def compare(exe: str, cc: str, lines: list[str], expected: dict, show: int, quiet: bool = False):
    log = os.path.join(os.path.dirname(exe), "fe_readable.log")
    env = dict(os.environ, FE_READABLE_LOG=log, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"formula_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list[int]] = {}
    wrote: set[int] = set()
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE"):
            wrote.add(int(parts[0]))
        elif parts:
            got[int(parts[0])] = [int(x) for x in parts[1:]]
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs) in expected.items():
        res = per.setdefault(name, [0, 0, 0, 0])  # cases, mismatches, gave-up cases, early give-ups
        res[0] += 1
        g = got.get(c)
        ov = inputs[0].startswith("ov:")
        if exp[0] == 1:
            res[2] += 1
            exp = [1, 0] if ov else exp  # a give-up must come before any unmapped read
        elif g is not None and g[:1] == [1] and g[1:] in ([0], []) and c not in wrote:
            # an early give-up: a needed cache is cold, the readable code asks before reading
            # anything (the original would reach that cache later or not at all); always safe
            res[3] += 1
            continue
        if g is None or g != exp or c in wrote:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = " (wrote guest memory or no override)" if c in wrote else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
PLANTS = [
    ("formula_stats.c", "value -= value / 2;", "value /= 2;"),
    ("formula_stats.c", "(state & UNIT_STATE_PAIR_SWAP) ? 4u : 2u;", "(state & UNIT_STATE_PAIR_SWAP) ? 2u : 4u;"),
    ("formula_stats.c", "    if (value < 0)\n        value = 0;\n    else if", "    if (value < 0)\n        value = 1;\n    else if"),
    ("formula_stats.c", "{S_SpdSkillMinus1, -1, 0}", "{S_SpdSkillMinus1, 1, 0}"),
    ("formula_stats.c", "{27, 3, 0x08, 8, 0}", "{27, 3, 0x08, 4, 0}"),
    ("formula_stats.c", "value = fe_add32(value, -1);", "value = fe_add32(value, -2);"),
    ("formula_stats.c", "return value > STAT_CAP ? STAT_CAP : value;", "return value > 100 ? 100 : value;"),
    ("formula_stats.c", "FIELD_ADDR(Unit, unit, debuff) + s", "FIELD_ADDR(Unit, unit, absorbed) + s"),
    ("formula_stats.c", "slot < UNIT_ITEM_SLOTS;", "slot < UNIT_ITEM_SLOTS - 1;"),
    ("formula_stats.c", "if (kind != r->kind &&", "if (kind == r->kind &&"),
    ("formula_unit.c", "fe_mul32(skl, 3)", "fe_mul32(skl, 2)"),
    ("formula_unit.c", "avoid = fe_add32(avoid, -20);\n    if (has_flag(ctx, words, S_AvoidMaskM10))",
     "avoid = fe_add32(avoid, -10);\n    if (has_flag(ctx, words, S_AvoidMaskM10))"),
    ("formula_unit.c", "enemy ? fe_asr(job_crit, 1) : job_crit", "enemy ? job_crit : fe_asr(job_crit, 1)"),
    ("formula_unit.c", "stat_of(ctx, STAT_SKL, unit, item), -4)", "stat_of(ctx, STAT_SKL, unit, item), -3)"),
    ("formula_unit.c", "fe_asr(lck, 1)", "fe_asr(lck, 2)"),
    ("formula_unit.c", "magic ? STAT_MAG : STAT_STR", "magic ? STAT_STR : STAT_MAG"),
    ("formula_unit.c", "        if (slot == -1)\n            return 0;", "        if (slot == -1)\n            return 1;"),
    ("formula_unit.c", "return slot >= 0 ? slot_item(unit, slot) : 0;", "return slot > 0 ? slot_item(unit, slot) : 0;"),
    ("formula_unit.c", "guest_call1(ctx, GUEST_ItemToData, item), speed_mod_player)",
     "guest_call1(ctx, GUEST_ItemToData, item), speed_mod_enemy)"),
    ("formula_unit.c", "hit = fe_add32(hit, 30);", "hit = fe_add32(hit, 20);"),
    # the rank bonus's weapon-kind lookup done in C again: same numbers, fewer ItemSubKind::Get
    # calls (the live mismatch_calls of 2026-11-12, docs/DECISIONS.md F-018)
    ("formula_unit.c", "guest_call1(ctx, GUEST_ItemSubKindGet, (int32_t)READ_FIELD(ctx, ItemData, data, weapon_kind))",
     "item_subkind_record(ctx, READ_FIELD(ctx, ItemData, data, weapon_kind))"),
    ("formula_unit.c", "if (has_flag(ctx, words, S_HitMask20))", "if (has_flag(ctx, words, S_HitMask10))"),
    ("formula_forecast.c", "S_FhStaffImmuneMask))\n            hit = 0;", "S_FhStaffImmuneMask))\n            hit = 1;"),
    ("formula_forecast.c", "v > 100 ? 100 : v", "v > 99 ? 99 : v"),
    ("formula_forecast.c", "mine >= fe_add32(theirs, 5)", "mine > fe_add32(theirs, 5)"),
    ("formula_forecast.c", "side_has_skill_bit(ctx, other, row, no_double)", "side_has_skill_bit(ctx, other, 0, no_double)"),
    ("formula_forecast.c", "return (flags & SIDE_FOLLOW_UP) ? 0 : 1;", "return (flags & SIDE_FOLLOW_UP) ? 1 : 0;"),
    ("formula_forecast.c", "bonus_crit_avoid) + row * BATTLE_BONUS_STRIDE);", "bonus_crit_avoid));"),
    ("formula_forecast.c", "        row == 0) {", "        row <= 1) {"),
    ("formula_forecast.c", "if (READ_FIELD(ctx, BattleSide, side, flags) & SIDE_NO_CRIT)",
     "if (READ_FIELD(ctx, BattleSide, side, flags) & SIDE_HINDER)"),
    ("formula_forecast.c", "detail_row(other, is_follower(ctx, side)), avoid)", "detail_row(other, 0), avoid)"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_BATTLE, d, ignore=shutil.ignore_patterns("tests"))
        path = os.path.join(d, fname)
        body = open(path, encoding="utf-8").read()
        if body.count(old) != 1:
            print(f"  planted bug {i}: its text occurs {body.count(old)} times in {fname} (the list is stale)")
            missed += 1
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body.replace(old, new))
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
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, default=100, help="cases per function for each planted bug")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("formula_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = T.find_cc()
    if not cc:
        print("formula_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_BATTLE)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"formula_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) +                 ([f"{early} early give-ups"] if early else [])
        print(f"  {name:32s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:32s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"formula_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"formula_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
