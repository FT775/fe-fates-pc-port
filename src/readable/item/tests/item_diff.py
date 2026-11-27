#!/usr/bin/env python3
"""Host differential test of the item readable code against the game's own ARM code.

    python src/readable/item/tests/item_diff.py             all functions, 300 cases each
    python src/readable/item/tests/item_diff.py -n 1500 --seed 7    the long run
    python src/readable/item/tests/item_diff.py --only item_might
    python src/readable/item/tests/item_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/sheet/tests/sheet_diff.py (its C driver and its compare are reused;
the ARM interpreter is src/readable/battle/tests/arm_mini.py): for every readable function of
src/readable/item/ the test makes up guest states (a list of loaded Item blocks with their
records, carried unit::Items, units with five item slots, the forge and item-kind tables, the
one-time caches; all random test values, never game data, and on purpose often outside the
ranges the game uses: item numbers past every block, negative and 32-bit numbers, empty and
unmapped blocks, an empty block list, forge tables past the mapped table, bools that are not
0/1, unmapped items and "torn" items whose second halfword is unmapped), runs the ORIGINAL ARM
code from the owner's extracted/text.bin in arm_mini.py and the readable C function (built with
the host gcc against tools/readable/stub/) on the same memory, and compares r0, the number of
bytes read from unmapped memory AND the list of guest calls, in order, with their argument
registers (docs/DECISIONS.md F-018). On the ARM side every BL/BLX to a listed callee is listed
(also inside callees that run as ARM code); on the C side every guest call is listed (one that
reaches another override of this batch runs that override). A one-time cache that is not filled
must make the original reach the guard routine and the readable code give up before reading
anything; a nested give-up (a guest call of another readable function giving up inside while the
outer one goes on) is a mismatch.

Guest functions answered by one table on both sides: ItemSubKind::Get, Unit::GetPowImpl,
Unit::IsEquipSkill, Unit::CanItemEquip. Item::Get, unit::Item::ToData, ItemRefine::Get,
Item::IsWeapon, Item::IsMagic and unit::Item::IsShopRefine run as ARM code on the ARM side and as
their readable overrides on the C side (other functions of this batch call them).

--plant copies src/readable/item/ to build/readable/item/plant/, makes one small wrong change at a
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
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "battle", "tests"))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "sheet", "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
import sheet_diff as S  # noqa: E402  (the C driver text and the compare)
from stance_diff import State, pick  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "item")
SRC_ITEM = os.path.join(ROOT, "src", "readable", "item")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
SUBKIND_GET, POW_IMPL, IS_EQUIP, CAN_EQUIP = 0x0019B97C, 0x0052A500, 0x0052DD04, 0x0052C634
LEAF_STUBS = {SUBKIND_GET: 1, POW_IMPL: 4, IS_EQUIP: 2, CAN_EQUIP: 4}
# this batch's overrides that others of it call: ARM code on the ARM side, the override on the C side
ITEM_GET, TO_DATA, REFINE_GET, IS_WEAPON, IS_MAGIC, IS_SHOP_REFINE = (
    0x003D0EAC, 0x003D0EA4, 0x0017CFA8, 0x00529164, 0x005290B8, 0x0053B0F8)
ARITY = dict(LEAF_STUBS)
ARITY[POW_IMPL] = 5  # listed with its fifth argument, the word at sp (round 11: guest_call5); answered by r0..r3
ARITY.update({ITEM_GET: 1, TO_DATA: 1, REFINE_GET: 2, IS_WEAPON: 1, IS_MAGIC: 1, IS_SHOP_REFINE: 1})

OVERRIDES = {  # name -> address
    "item_record": 0x003D0EAC, "item_to_data": 0x003D0EA4, "item_try_record": 0x003D10A0,
    "item_kind_record": 0x004EC1CC, "item_refine_record": 0x0017CFA8, "item_is_weapon": 0x00529164,
    "item_is_magic": 0x005290B8, "item_can_use": 0x00528F3C, "item_is_download": 0x00528E68,
    "item_is_hidden_effect": 0x00528E90, "item_might": 0x0053B4B4, "item_hit": 0x0053B2A4,
    "item_crit": 0x0053AD54, "item_uses_left": 0x0053AE48, "item_forge_rank": 0x0053B278,
    "item_same_kind": 0x0053AE18, "item_equals": 0x0053B470, "item_is_consumable": 0x0053B578,
    "item_can_forge": 0x0053B0F8, "item_can_forge_with": 0x0053B070, "item_sell_price": 0x0053AE8C,
    "unit_range_max": 0x00534510, "unit_item_heal_amount": 0x0052F288, "unit_can_cannon_item": 0x0052DF90,
    "unit_has_cannon_item": 0x0052F1AC,
}

# tables and caches (src/readable/item/item.h)
G_LIST, G_KIND, G_REFINE = 0x006D38D0, 0x006D3950, 0x006D3958
MAGIC_GUARD, HIDDEN_GUARD, USABLE_GUARD = 0x006D38D4, 0x006D38D8, 0x006D38DC
MAGIC_MASK, HIDDEN_MASK, USABLE_MASK = 0x006D3920, 0x006D3928, 0x006D3930
EXPEND_GUARD, SELL_GUARDS, FORGE_GUARDS = 0x006D9EC8, (0x006D9ED0, 0x006D9ECC), (0x006D9EDC, 0x006D9ED8, 0x006D9ED4)
EXPEND_MASK, SELL_MASKS, FORGE_MASKS = 0x006D9F10, (0x006D9F18, 0x006D9F20), (0x006D9F28, 0x006D9F30, 0x006D9F38)
RANGE_GUARD, RANGE_SKILL = 0x006D989C, 0x006D967A
HEAL_GUARDS, HEAL_SKILL, HEAL_MASK = (0x006D9910, 0x006D990C, 0x006D9908, 0x006D9904, 0x006D9900), 0x006D96AA, 0x006D9C38
ALL_GUARDS = (MAGIC_GUARD, HIDDEN_GUARD, USABLE_GUARD, EXPEND_GUARD) + SELL_GUARDS + FORGE_GUARDS + \
    (RANGE_GUARD,) + HEAL_GUARDS
ALL_MASKS = (MAGIC_MASK, HIDDEN_MASK, USABLE_MASK, EXPEND_MASK) + SELL_MASKS + FORGE_MASKS + (HEAL_MASK,)
SKILL_CACHES = (RANGE_SKILL, HEAL_SKILL)

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x400  # noqa: E731
NODE = lambda k: 0x08070000 + k * 0x10  # noqa: E731
BLOCK = lambda k: 0x08080000 + k * 0x1000  # noqa: E731
SUBKIND = lambda k: 0x08048000 + k * 0x10  # noqa: E731
REFINE, KIND = 0x08090000, 0x08098000
LOOSE = lambda k: 0x080A0000 + k * 4  # noqa: E731
TORN = 0x080F0FFE  # a unit::Item whose second halfword is on an unmapped page
NUNITS, NLOOSE, NSUB = 3, 8, 8
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
RECORD = 0x68


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sx8(v: int) -> int:
    v &= 0xFF
    return v - 0x100 if v & 0x80 else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def guard(st, addr: int, cold_p: float = 0.01) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def cool(st, guards, p: float = 0.04) -> None:
    for g in guards:
        if st.rng.random() < p:
            st.put(g, 4, 0)


# ------------------------------------------------------------------ the made-up state
def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    # round 11 review: the dead stack below sp holds junk, not zeros, so a fifth argument word stored in the
    # wrong slot (guest_call5) is read back as junk and shows in the call list (with zeros it matched the 0)
    st.fill(SP - 0x400, 0x400)
    st.zero(0x006D3800, 0x200)
    st.zero(0x006D9600, 0xA00)
    for g in ALL_GUARDS:
        guard(st, g)
    for m in ALL_MASKS:
        st.put(m, 8, 1 << rng.randrange(64) if rng.random() > 0.05 else rng.randrange(1 << 64))
    for a in SKILL_CACHES:
        st.put(a, 2, pick(rng, list(range(1, 30)), [0, 0xFFFF, 0x8000], 0.08))
    st.fill(REFINE, 0x400)
    st.fill(KIND, 0x100)
    st.put(G_REFINE, 4, REFINE if rng.random() > 0.03 else rng.choice(UNMAPPED))
    st.put(G_KIND, 4, KIND if rng.random() > 0.03 else rng.choice(UNMAPPED))
    st.numbers = []  # item numbers some block holds
    st.records = []  # every record address
    make_blocks(st)
    make_subkinds(st)
    for k in range(NLOOSE):
        make_item(st, LOOSE(k))
    make_item(st, TORN)
    st.mem.pop(TORN + 2, None)
    st.mem.pop(TORN + 3, None)
    return st


def make_blocks(st) -> None:
    rng = st.rng
    nblocks = pick(rng, [1, 2, 2, 3, 3], [0], 0.03)
    st.put(G_LIST, 4, NODE(0) if nblocks else 0)
    first = rng.choice([0, 0, 1, 5])
    for k in range(nblocks):
        st.fill(NODE(k), 0x10)
        st.put(NODE(k) + 8, 4, NODE(k + 1) if k + 1 < nblocks else 0)
        if rng.random() < 0.03:  # a node whose block is unmapped
            st.put(NODE(k), 4, rng.choice(UNMAPPED))
            continue
        b = BLOCK(k)
        st.put(NODE(k), 4, b)
        count = pick(rng, [2, 3, 4, 6, 8], [0, 1], 0.06)
        st.fill(b, 8)
        st.put(b + 6, 2, count)
        if k == 2 and rng.random() < 0.7:  # download items: far away
            first = rng.choice([0x200, 0x1F0, 0xFFF0])
        for i in range(max(count, 1)):  # record 0 holds the block's first number even when count is 0
            rec = b + 8 + i * RECORD
            make_record(st, rec, (first + i) & 0xFFFF)
            st.records.append(rec)
            if i < count:
                st.numbers.append((first + i) & 0xFFFF)
        if rng.random() < 0.1:  # overlapping numbers: the first block that holds a number wins
            first = max(0, first - 1)
        else:
            first += count + rng.choice([0, 0, 0, 2])


def make_record(st, rec: int, number: int) -> None:
    rng = st.rng
    st.fill(rec, RECORD)
    flags = word(st, rec, 8)
    for m in ALL_MASKS:
        mask = word(st, m, 8)
        flags = (flags | mask) if rng.random() < 0.25 else (flags & ~mask)
    st.put(rec, 8, flags)
    st.put(rec + 0x14, 2, number)
    st.put(rec + 0x1A, 1, pick(rng, [0, 1, 2, 3, 4, 5, 6, 7, 19], [0x80, 0x7F, 20], 0.05) & 0xFF)
    st.put(rec + 0x1E, 1, pick(rng, [0, 1, 3, 10, 20, 40], [255], 0.1))
    st.put(rec + 0x1F, 1, pick(rng, [0, 3, 7, 11, 15, 20], [255], 0.1))
    st.put(rec + 0x20, 2, s32(pick(rng, [0, 50, 70, 85, 100], [-1, -0x8000, 0x7FFF], 0.1)) & 0xFFFF)
    st.put(rec + 0x22, 2, s32(pick(rng, [0, 0, 5, 10, 30], [-5, -0x8000, 0x7FFF], 0.1)) & 0xFFFF)
    st.put(rec + 0x29, 1, pick(rng, [0, 1, 1, 2, 2, 3, 5, 7, 9, 10, 12], [0xFE, 0xFF, 0xFD], 0.06))
    st.put(rec + 0x30, 4, s32(pick(rng, [0, 100, 350, 1000, 4000], [-1, 0x7FFFFFFF, 0x80000000, 0x40000001], 0.1)))
    st.put(rec + 0x40, 1, pick(rng, [0, 10, 15, 20, 50, -3, -1], [-128, 127, 99], 0.15) & 0xFF)
    st.put(rec + 0x48, 1, pick(rng, [0, 1, 2, 3, 5, 9], [200, 255, 25], 0.06))
    st.put(rec + 0x49, 1, pick(rng, [0, 1, 4, 9], [200, 255], 0.06))


def make_subkinds(st) -> None:
    """ItemSubKind::Get for every sub-kind byte a record holds (and 0, read from unmapped records)"""
    rng = st.rng
    for k in range(NSUB):
        st.fill(SUBKIND(k), 0x10)
        st.put(SUBKIND(k) + 1, 1, pick(rng, [0, 1, 2, 3, 4, 5, 6, 8], [7, 9, 0x85, 0x86, 255], 0.08))
        st.put(SUBKIND(k) + 3, 1, pick(rng, [0, 1, 2, 3, -1], [-128, 127], 0.1) & 0xFF)
    values = {0} | {sx8(st.mem.get(r + 0x1A, 0)) for r in st.records}
    for v in sorted(values):
        st.oracle[(SUBKIND_GET, s32(v))] = SUBKIND(rng.randrange(NSUB)) if rng.random() > 0.03 else rng.choice(UNMAPPED)


def item_number(st) -> int:
    rng = st.rng
    if st.numbers and rng.random() < 0.85:
        return rng.choice(st.numbers)
    return pick(rng, [0, 1, rng.randrange(0x400)], [0xFFFF, rng.randrange(1 << 16)], 0.3)


def make_item(st, a: int) -> None:
    rng = st.rng
    bits = pick(rng, [0, 0, 0, 1, 2, 3, 5], [0x7F, 0x40], 0.1)
    if rng.random() < 0.2:
        bits |= 0x80
    bits |= pick(rng, [0, 0, 1, 2, 3, 5, 7, 10], [63, rng.randrange(64)], 0.15) << 8
    bits |= (0x4000 if rng.random() < 0.3 else 0) | (0x8000 if rng.random() < 0.1 else 0)
    st.put(a, 2, item_number(st))
    st.put(a + 2, 2, bits)


def item_arg(st) -> int:
    r = st.rng.random()
    if r < 0.06:
        return st.rng.choice(UNMAPPED)
    if r < 0.14:
        return TORN
    return LOOSE(st.rng.randrange(NLOOSE))


def record_arg(st) -> int:
    r = st.rng.random()
    if r < 0.05 or not st.records:
        return st.rng.choice(UNMAPPED)
    return st.rng.choice(st.records)


def make_unit(st, k: int) -> int:
    rng = st.rng
    u = UNIT(k)
    st.fill(u, 0x140)
    st.put(u + 0x28, 1, (st.mem[u + 0x28] | 8) if rng.random() < 0.6 else (st.mem[u + 0x28] & ~8))
    for slot in range(5):
        make_item(st, u + 0x108 + 4 * slot)
    answer_unit(st, u)
    return u


def answer_unit(st, u: int) -> None:
    rng = st.rng
    for a in SKILL_CACHES:
        st.oracle[(IS_EQUIP, s32(u), s32((word(st, a, 2) ^ 0x8000) - 0x8000))] = int(rng.random() < 0.5)
    for it in [u + 0x108 + 4 * s for s in range(5)] + [LOOSE(k) for k in range(NLOOSE)] + [TORN] + UNMAPPED:
        st.oracle[(CAN_EQUIP, s32(u), s32(it), 0, 1)] = int(rng.random() < 0.4)
    # round 11: magic 0 and 1 (half 0: the floor of 1), odd and negative values (an arithmetic halving)
    st.oracle[(POW_IMPL, s32(u), 0, 1, 1)] = s32(pick(rng, [0, 1, 2, 3, 5, 10, 21], [-3, -1, -2, 99, -0x7FFFFFFF], 0.3))


def unit_arg(st) -> int:
    units = [make_unit(st, k) for k in range(NUNITS)]
    if st.rng.random() < 0.06:
        u = st.rng.choice(UNMAPPED)
        answer_unit(st, u)
        return u
    return st.rng.choice(units)


def bool_arg(rng) -> int:
    return pick(rng, [0, 1, 1], [2, 0x100, 0xFFFFFFFF], 0.15)


# ------------------------------------------------------------------ the functions
def ov(name, args):
    a = OVERRIDES[name]
    return f"ov:0x{a:08X}", args + [0] * (4 - len(args)), ("call", a)


def gen_number(name):
    def gen(rng):
        st = base_state(rng)
        r = rng.random()
        if r < 0.6:
            n = item_number(st)
        elif r < 0.8 and st.numbers:  # just outside a run of numbers
            n = (rng.choice(st.numbers) + rng.choice([-1, 1, 2])) & 0xFFFF
        else:
            n = s32(pick(rng, [0x10000, -1, -0x8000, 0x7FFFFFFF, rng.randrange(1 << 32)]))
        if rng.random() < 0.12 and word(st, G_LIST) == NODE(0) and word(st, NODE(0)) == BLOCK(0):
            # focused: a second block placed so that its record 0 sits at address 0 (the address
            # wraps): Item::Get counts that as missing and falls back, TryGet returns 0 as found
            wrap = 0xFFFFFFF8
            st.put(NODE(0) + 8, 4, NODE(5))
            st.fill(NODE(5), 0x10)
            st.put(NODE(5), 4, wrap)
            st.put(NODE(5) + 8, 4, 0)
            st.put(wrap, 8, 0)
            st.put(wrap + 6, 2, 2)
            st.zero(0, 0x80)
            st.put(0x14, 2, 0x3000)  # block +0x1C wraps to 0x14: its first number
            n = 0x3000
        return (st,) + ov(name, [n])
    return gen


def gen_to_data(rng):
    st = base_state(rng)
    return (st,) + ov("item_to_data", [item_arg(st)])


def gen_kind(rng):
    st = base_state(rng)
    return (st,) + ov("item_kind_record", [s32(pick(rng, list(range(20)), [-1, 0x7FFFFFFF, rng.randrange(1 << 32)]))])


def gen_refine(rng):
    st = base_state(rng)
    t = s32(pick(rng, list(range(12)), [-1, 255, rng.randrange(1 << 32)]))
    r = s32(pick(rng, list(range(12)) + [63], [-1, 0x40000000]))
    return (st,) + ov("item_refine_record", [t, r])


def gen_record(name, guards=()):
    def gen(rng):
        st = base_state(rng)
        cool(st, guards, 0.05)
        return (st,) + ov(name, [record_arg(st)])
    return gen


def gen_item(name, guards=(), p=0.04):
    def gen(rng):
        st = base_state(rng)
        cool(st, guards, p)
        return (st,) + ov(name, [item_arg(st)])
    return gen


def gen_two_items(name, guards=()):
    def gen(rng):
        st = base_state(rng)
        cool(st, guards, 0.03)
        a = item_arg(st)
        b = item_arg(st)
        if rng.random() < 0.15:  # focused: the same unmapped item twice (every extra read shows)
            a = b = rng.choice(UNMAPPED)
        if rng.random() < 0.5 and a in [LOOSE(k) for k in range(NLOOSE)] and b != a and \
                b in [LOOSE(k) for k in range(NLOOSE)]:  # focused: same number, maybe same fields
            st.put(b, 2, word(st, a, 2))
            if rng.random() < 0.5:
                st.put(b + 2, 2, word(st, a + 2, 2) ^ rng.choice([0, 0, 0x80, 0x4000, 0x100, 1]))
        return (st,) + ov(name, [a, b])
    return gen


def gen_sell(rng):
    st = base_state(rng)
    cool(st, SELL_GUARDS, 0.03)
    if rng.random() < 0.5:  # focused: fewer barred records, so the price rules are reached
        for m in SELL_MASKS:
            st.put(m, 8, 1 << 63)
        for rec in st.records:
            st.put(rec + 4, 4, word(st, rec + 4) & 0x7FFFFFFF)
            if rng.random() < 0.4:  # prices whose product with the uses passes 2^31 (the division is unsigned)
                st.put(rec + 0x30, 4, rng.choice([0x80000000, 0x40000001, 0xFFFFFFFF, 0x7FFFFFFF]))
    return (st,) + ov("item_sell_price", [item_arg(st)])


def gen_unit_item(name, guards=(), p=0.04):
    def gen(rng):
        st = base_state(rng)
        cool(st, guards, p)
        r = None
        if name == "unit_range_max" and rng.random() < 0.3:
            # round 11, focused: the 0xFE range (half the unit's magic, guest_call5), or 9 and 10 (just below and
            # at the endless-staff range), on every record
            r = rng.choice([0xFE, 0xFE, 9, 10])
            for rec in st.records:
                st.put(rec + 0x29, 1, r)
        u = unit_arg(st)
        if r in (9, 10) and rng.random() < 0.8:
            # ... and mostly a staff (every sub-kind of kind 6) held by a unit with the "endless staff" skill
            # (every IsEquipSkill answer 1), so the staff rule meets those ranges
            for k in range(NSUB):
                st.put(SUBKIND(k) + 1, 1, 6)
            for key in [k for k in st.oracle if k[0] == IS_EQUIP]:
                st.oracle[key] = 1
        it = u + 0x108 + 4 * rng.randrange(5) if (UNIT(0) <= u < UNIT(NUNITS) and rng.random() < 0.5) \
            else item_arg(st)
        return (st,) + ov(name, [u, it])
    return gen


def gen_cannon(rng):
    st = base_state(rng)
    cool(st, (MAGIC_GUARD,), 0.03)
    u = unit_arg(st)
    it = u + 0x108 + 4 * rng.randrange(5) if (UNIT(0) <= u < UNIT(NUNITS) and rng.random() < 0.5) else item_arg(st)
    return (st,) + ov("unit_can_cannon_item", [u, it, bool_arg(rng)])


def gen_has_cannon(rng):
    st = base_state(rng)
    cool(st, (MAGIC_GUARD,), 0.03)
    if rng.random() < 0.2:
        # round 11 review, focused: the IsMagic guard cold with check_magic on, so the slot loop reaches IsMagic
        # (the planted bug "guard not asked first" was caught by 2 cases, then by none once the stack held junk)
        st.put(MAGIC_GUARD, 4, 0)
        return (st,) + ov("unit_has_cannon_item", [unit_arg(st), 1])
    return (st,) + ov("unit_has_cannon_item", [unit_arg(st), bool_arg(rng)])


FUNCS = {
    "item_record": gen_number("item_record"),
    "item_to_data": gen_to_data,
    "item_try_record": gen_number("item_try_record"),
    "item_kind_record": gen_kind,
    "item_refine_record": gen_refine,
    "item_is_weapon": gen_record("item_is_weapon"),
    "item_is_magic": gen_record("item_is_magic", (MAGIC_GUARD,)),
    "item_can_use": gen_record("item_can_use", (USABLE_GUARD,)),
    "item_is_download": gen_record("item_is_download"),
    "item_is_hidden_effect": gen_record("item_is_hidden_effect", (HIDDEN_GUARD,)),
    "item_might": gen_item("item_might"),
    "item_hit": gen_item("item_hit"),
    "item_crit": gen_item("item_crit"),
    "item_uses_left": gen_item("item_uses_left"),
    "item_forge_rank": gen_item("item_forge_rank"),
    "item_same_kind": gen_two_items("item_same_kind"),
    "item_equals": gen_two_items("item_equals"),
    "item_is_consumable": gen_item("item_is_consumable", (EXPEND_GUARD,)),
    "item_can_forge": gen_item("item_can_forge", FORGE_GUARDS, 0.02),
    "item_can_forge_with": gen_two_items("item_can_forge_with", FORGE_GUARDS),
    "item_sell_price": gen_sell,
    "unit_range_max": gen_unit_item("unit_range_max", (RANGE_GUARD,)),
    "unit_item_heal_amount": gen_unit_item("unit_item_heal_amount", HEAL_GUARDS, 0.01),
    "unit_can_cannon_item": gen_cannon,
    "unit_has_cannon_item": gen_has_cannon,
}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY (stubbed or run as ARM code) with its
    argument registers."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            n = ARITY[target]
            regs = list(self.r[:min(n, 4)]) + [self.mem.read(self.r[13] + 4 * k, 4) for k in range(n - 4)]
            self.listed.append(S.call_text(target, regs))
        return super().call(target, ret)


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
    stray = [w for w in mem.writes if not SP - 0x400 <= w[0] < SP]  # its own stack frame is fine
    if stray:
        raise A.Unsupported(f"the original wrote guest memory outside its stack: {stray[:3]}")
    return [0, cpu.r[0], mem.faults, S.calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER_OVERRIDES = sorted(set(OVERRIDES.values()))


STACK_DRIVER_OLD = (
    "static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; writes++; uint8_t *p = at(a, 0); if (p) *p = v; }",
    "    for (uint32_t i = 0; i < n; i++) k += snprintf(buf + k, sizeof buf - (size_t)k, \":%x\", r[i]);",
    "            c.r[13] = a[4];",
    "    char buf[96];",
)
STACK_DRIVER_NEW = (
    # round 11 (guest_call5): a store into the dead stack (the 0x400 bytes below the case's sp) is the fifth
    # argument word of a call, not a write of guest data: counted apart, never as WROTE-GUEST
    "static uint32_t stack_top; static int stack_writes;\n"
    "static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; if (a < stack_top && a >= stack_top - 0x400u) "
    "stack_writes++; else writes++; uint8_t *p = at(a, 0); if (p) *p = v; }",
    # an argument past r3 is the word at sp + 4 * (n - 4), as the callee sees it
    "    for (uint32_t i = 0; i < n; i++) k += snprintf(buf + k, sizeof buf - (size_t)k, \":%x\", "
    "i < 4 ? r[i] : r32(NULL, r[13] + 4u * (i - 4u)));",
    "            c.r[13] = a[4]; stack_top = a[4]; stack_writes = 0;",
    "    char buf[128];",
)


def driver_text() -> str:
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in DRIVER_OVERRIDES)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in DRIVER_OVERRIDES) + "};\n"
    text = S.DRIVER.replace('#include "sheet.h"', '#include "item.h"')
    text = text.replace("src/readable/sheet/tests/sheet_diff.py", "src/readable/item/tests/item_diff.py")
    text = text.replace("readable status-sheet functions", "readable item functions")
    for old, new in zip(STACK_DRIVER_OLD, STACK_DRIVER_NEW):
        if text.count(old) != 1:
            raise SystemExit(f"item_diff: sheet_diff's driver changed, cannot patch: {old[:60]!r}")
        text = text.replace(old, new)
    return text.replace("@OVERRIDE_DECLS@", decls + table)


def build_driver(cc: str, out: str, item_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, the item folder's taken from item_dir
    (a planted bug may leave a parameter unused: not strict then, warnings are not errors)."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "item_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_ITEM)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(item_dir, f) for f in os.listdir(item_dir) if f.endswith(".c")]
    exe = os.path.join(out, "item_driver.exe" if os.name == "nt" else "item_driver")
    inc = ["-I", item_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    warn = ["-Wall", "-Wextra", "-Werror"] if strict else ["-w"]
    cmd = [cc, "-std=c11"] + warn + ["-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"item_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


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


def compare(exe: str, cc: str, lines: list[str], expected: dict, show: int, quiet: bool = False):
    """sheet_diff.compare. Until round 11 a give-up where the original calls Unit::GetPowImpl (the 0xFE range;
    five arguments, the fifth on the stack) was accepted as benign; the readable code now passes the fifth word
    with guest_call5, so that case is compared like any other (r0, unmapped reads, the call list with the fifth
    argument read from the stack on both sides)."""
    per = S.compare(exe, cc, lines, expected, show, quiet)
    # round 11: sheet_diff counts a give-up with no unmapped read where the original did not give up as an
    # "early give-up" (a cold cache asked before the game would ask it), always safe. Only the functions below
    # ask a cache before the game does (section 5 of docs/ITEM.md); anywhere else such a give-up is a give-up
    # in the middle of the function (after reads and guest calls, as unit_range_max's old one at the 0xFE
    # range) and is counted as a mismatch.
    for name, v in per.items():
        if name not in EARLY_GIVEUP_OK and v[3]:
            if not quiet:
                print(f"  MISMATCH {name}: {v[3]} give-ups where the original did not give up (no early cache here)")
            v[1] += v[3]
            v[3] = 0
    return per


EARLY_GIVEUP_OK = {"item_is_magic", "item_is_hidden_effect", "unit_can_cannon_item", "unit_has_cannon_item",
                   "item_can_forge_with"}




# planted bugs: (file, exact text, replacement); each text occurs once in its file
PLANTS = [
    # item_record.c
    ("item_record.c", "        if ((int32_t)number < first)\n", "        if (number < (uint32_t)first)\n"),
    ("item_record.c", "        if (end <= (int32_t)number)\n", "        if (end < (int32_t)number)\n"),
    ("item_record.c", "        if (zero_is_missing && record == 0)\n            return 0;\n", ""),
    ("item_record.c", "    return guest_u32(ctx, head + ITEM_NODE_BLOCK) + ITEM_BLOCK_RECORDS;\n}",
     "    return head == 0 ? 0 : guest_u32(ctx, head + ITEM_NODE_BLOCK) + ITEM_BLOCK_RECORDS;\n}"),
    # ToData asked Item::Get through the guest: one call too many in the callers' lists
    ("item_record.c", "    return item_record(ctx, guest_u16(ctx, item));",
     "    return guest_call1(ctx, ITEM_ItemGet, guest_u16(ctx, item));"),
    ("item_record.c", "    return find_record(ctx, guest_u32(ctx, G_ItemArchiveList), number, 0, &found);",
     "    gaddr r = find_record(ctx, guest_u32(ctx, G_ItemArchiveList), number, 0, &found);\n    return found ? r : 1;"),
    ("item_record.c", "    return guest_u32(ctx, G_ItemKindTable) + kind * ITEM_KIND_RECORD_SIZE;",
     "    return guest_u32(ctx, G_ItemKindTable) + kind * 0x10u;"),
    ("item_record.c", "(table * ITEM_REFINE_ROW + rank) * ITEM_REFINE_RECORD_SIZE", "(rank * ITEM_REFINE_ROW + table) * ITEM_REFINE_RECORD_SIZE"),
    ("item_record.c", "    return (kind == 6 || kind == 8) ? 0u : 1u;", "    return (kind == 6 || kind == 7) ? 0u : 1u;"),
    ("item_record.c", "    if (kind == 5 || kind == 6)\n        return 1;\n", "    if (kind == 5)\n        return 1;\n"),
    # the guard not asked at all: a cold cache read as filled
    ("item_record.c", "uint32_t item_is_hidden_effect(Context *ctx, gaddr record) {\n    if (!fe_static_ready(ctx, S_ItemHiddenGuard))\n"
     "        return fe_use_original(ctx);\n", "uint32_t item_is_hidden_effect(Context *ctx, gaddr record) {\n"),
    ("item_record.c", "& guest_u64(ctx, S_ItemUsableMask)) != 0 ? 1u : 0u;", "& guest_u64(ctx, S_ItemMagicMask)) != 0 ? 1u : 0u;"),
    ("item_record.c", "    return number >= guest_u16(ctx, block + ITEM_BLOCK_COUNT) ? 1u : 0u;",
     "    return number > guest_u16(ctx, block + ITEM_BLOCK_COUNT) ? 1u : 0u;"),
    ("item_record.c", "    if (guest_u8(ctx, FIELD_ADDR(ItemData, record, weapon_kind)) == 19)\n        return 1;\n", ""),
    # item_value.c
    ("item_value.c", "    return with_forge_bonus(ctx, item, might, 1);", "    return with_forge_bonus(ctx, item, might, 2);"),
    ("item_value.c", "    return with_forge_bonus(ctx, item, hit, 2);", "    return with_forge_bonus(ctx, item, hit, 1);"),
    ("item_value.c", "    int32_t crit = READ_FIELD(ctx, ItemData, record_of(ctx, item), crit);",
     "    int32_t crit = READ_FIELD(ctx, ItemData, record_of(ctx, item), avoid);"),
    ("item_value.c", "        forged = (item_bits(ctx, item) & ITEM_BITS_NAME) >= 2;", "        forged = (item_bits(ctx, item) & ITEM_BITS_NAME) >= 1;"),
    ("item_value.c", "    if (bits & ITEM_BITS_NO_FORGE)\n        return value;\n", ""),
    ("item_value.c", "(bits & ITEM_BITS_NAME) == 1 ? guest_u8(ctx, record_of(ctx, item) + ITEM_REFINE_TABLE_2)",
     "(bits & ITEM_BITS_NAME) == 2 ? guest_u8(ctx, record_of(ctx, item) + ITEM_REFINE_TABLE_2)"),
    # IsWeapon asked once and kept for the rank: one call less
    ("item_value.c", "    int32_t rank = weapon_rank(ctx, item, record_of(ctx, item));\n    gaddr row",
     "    int32_t rank = count_field(item_bits(ctx, item));\n    gaddr row"),
    # the count read only once: same answers, fewer reads of a torn item
    ("item_value.c", "    if (is_weapon(ctx, record_of(ctx, item)) && count_field(item_bits(ctx, item)) != 0)\n        forged = 1;\n    else\n        forged = (item_bits(ctx, item) & ITEM_BITS_NAME) >= 2;",
     "    uint32_t first_bits = item_bits(ctx, item);\n    if (is_weapon(ctx, record_of(ctx, item)) && count_field(first_bits) != 0)\n        forged = 1;\n    else\n        forged = (first_bits & ITEM_BITS_NAME) >= 2;"),
    ("item_value.c", "    if (is_weapon(ctx, record_of(ctx, item)))\n        return 0;\n    return count_field",
     "    if (!is_weapon(ctx, record_of(ctx, item)))\n        return 0;\n    return count_field"),
    ("item_value.c", "    return (int32_t)((bits >> ITEM_BITS_COUNT_SHIFT) & ITEM_BITS_COUNT_MASK);",
     "    return (int32_t)((bits >> ITEM_BITS_COUNT_SHIFT) & 0x1Fu);"),
    ("item_value.c", "    return (item_bits(ctx, item) & ITEM_BITS_NAME) == (item_bits(ctx, other) & ITEM_BITS_NAME) ? 1u : 0u;",
     "    return (item_bits(ctx, item) & 0xFFu) == (item_bits(ctx, other) & 0xFFu) ? 1u : 0u;"),
    ("item_value.c", "    return count_field(a) == count_field(b) ? 1u : 0u;", "    return 1u;"),
    ("item_value.c", "& guest_u64(ctx, S_ExpendMask)) == 0 ? 1u : 0u;", "& guest_u64(ctx, S_ExpendMask)) != 0 ? 1u : 0u;"),
    ("item_value.c", "    if (flags & guest_u64(ctx, S_ForgeMaskValuable))\n        return 0;\n", ""),
    ("item_value.c", "    return READ_FIELD(ctx, ItemSubKindData, sub, refine_group) >= 0 ? 1u : 0u;",
     "    return READ_FIELD(ctx, ItemSubKindData, sub, refine_group) > 0 ? 1u : 0u;"),
    # IsShopRefine run in C, not through the guest: a call missing from the list
    ("item_value.c", "    if (guest_call1(ctx, ITEM_ItemIsShopRefine, item) == 0)", "    if (item_can_forge(ctx, item) == 0)"),
    # its guards not asked first: its override gives up nested
    ("item_value.c", "    /* the guards of IsShopRefine(void), asked before its guest call (no give-up inside it) */\n"
     "    if (!fe_static_ready(ctx, S_ForgeGuard0) || !fe_static_ready(ctx, S_ForgeGuard1) ||\n"
     "        !fe_static_ready(ctx, S_ForgeGuard2))\n        return fe_use_original(ctx);\n", ""),
    ("item_value.c", "    int32_t rank = weapon_rank(ctx, item, guest_call1(ctx, ITEM_ItemGet, number));",
     "    int32_t rank = weapon_rank(ctx, item, record_of(ctx, item));"),
    ("item_value.c", "    if (READ_FIELD(ctx, ItemData, record, flags) & barred)\n        return -1;",
     "    if (READ_FIELD(ctx, ItemData, record, flags) & barred)\n        return 0;"),
    ("item_value.c", "        } while (weapon_rank(ctx, item, record_of(ctx, item)) > doubled);",
     "        } while (weapon_rank(ctx, item, record_of(ctx, item)) >= doubled);"),
    ("item_value.c", "    return (int32_t)(((uint32_t)uses * price) / full);", "    return (int32_t)uses * (int32_t)price / (int32_t)full;"),
    ("item_value.c", "    if (full == 0)\n        return READ_FIELD(ctx, ItemData, record, sell_price);\n", "    if (full == 0)\n        return 0;\n"),
    ("item_value.c", "    uint64_t barred = guest_u64(ctx, S_SellMaskLocked) | guest_u64(ctx, S_SellMaskValuable);",
     "    uint64_t barred = guest_u64(ctx, S_SellMaskLocked);"),
    # item_unit.c
    ("item_unit.c", "        range < ITEM_STAFF_RANGE)", "        range < 9)"),
    # round 11, the 0xFE range through guest_call5: a wrong fifth (stack) word, a wrong register argument,
    # no floor of 1, a logical instead of an arithmetic halving, and the old give-up back
    ("item_unit.c", "ITEM_UnitGetPowImpl, unit, 0u, 1u, 1u, 0u)", "ITEM_UnitGetPowImpl, unit, 0u, 1u, 1u, 1u)"),
    ("item_unit.c", "ITEM_UnitGetPowImpl, unit, 0u, 1u, 1u, 0u)", "ITEM_UnitGetPowImpl, unit, 0u, 1u, 0u, 0u)"),
    ("item_unit.c", "        range = half < 1 ? 1 : half;", "        range = half;"),
    ("item_unit.c", "fe_asr((int32_t)guest_call5(ctx, ITEM_UnitGetPowImpl, unit, 0u, 1u, 1u, 0u), 1)",
     "(int32_t)(guest_call5(ctx, ITEM_UnitGetPowImpl, unit, 0u, 1u, 1u, 0u) >> 1)"),
    ("item_unit.c", "        int32_t half = fe_asr((int32_t)guest_call5(ctx, ITEM_UnitGetPowImpl, unit, 0u, 1u, 1u, 0u), 1);\n"
     "        range = half < 1 ? 1 : half;\n",
     "        return (int32_t)fe_use_original(ctx);\n"),
    # round 11 review: guest_call5 itself (include/readable/fe_guest.h, copied with fe.h into the plant folder):
    # the fifth word stored 4 bytes too high, caught only because the dead stack holds junk now. A guest_call5 that
    # does not put sp back cannot be caught here: FE_ENTRY puts every register back (fe_load) after the readable
    # function, so tools/readable/tests/guest_call5_test.py checks that one, calling guest_call5 directly.
    ("fe_guest.h", "    guest_set_u32(ctx, low, a4);\n", "    guest_set_u32(ctx, low + 4u, a4);\n"),
    ("item_unit.c", "    if (READ_FIELD(ctx, ItemSubKindData, sub, kind) == ITEM_KIND_STAFF && has_skill(ctx, unit, S_RangeOSkill) != 0 &&",
     "    if (has_skill(ctx, unit, S_RangeOSkill) != 0 && READ_FIELD(ctx, ItemSubKindData, sub, kind) == ITEM_KIND_STAFF &&"),
    ("item_unit.c", "    gaddr record = to_data(ctx, item);\n    gaddr sub", "    gaddr record = item_to_data(ctx, item);\n    gaddr sub"),
    ("item_unit.c", "        heal += heal / 2;", "        heal += heal >> 1;"),
    ("item_unit.c", "    int32_t heal = guest_s8(ctx, record + ITEM_HEAL);", "    int32_t heal = guest_u8(ctx, record + ITEM_HEAL);"),
    ("item_unit.c", "    if (guest_call(ctx, ITEM_UnitCanItemEquip, unit, item, 0u, 1u) == 0)",
     "    if (guest_call(ctx, ITEM_UnitCanItemEquip, unit, item, 1u, 0u) == 0)"),
    ("item_unit.c", "    if (check_magic == 0 || (guest_u8(ctx, unit + UNIT_CONDITION_0) & 0x08u) == 0)",
     "    if (check_magic == 0 || (guest_u8(ctx, unit + UNIT_CONDITION_0) & 0x04u) == 0)"),
    ("item_unit.c", "    for (uint32_t slot = 0; slot < 5u; slot++)", "    for (uint32_t slot = 0; slot < 4u; slot++)"),
    # the IsMagic guard not asked by the slot loop: its override gives up nested
    ("item_unit.c", "uint32_t unit_has_cannon_item(Context *ctx, gaddr unit, uint32_t check_magic) {\n    if (!fe_static_ready(ctx, S_ItemMagicGuard))\n        return fe_use_original(ctx);\n",
     "uint32_t unit_has_cannon_item(Context *ctx, gaddr unit, uint32_t check_magic) {\n"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_ITEM, d, ignore=shutil.ignore_patterns("tests"))
        path = os.path.join(d, fname)
        if fname == "fe_guest.h":  # a shared header: fe.h comes along so item.h's "fe.h" pulls this copy in
            for h in ("fe.h", fname):
                shutil.copy(os.path.join(ROOT, "include", "readable", h), os.path.join(d, h))
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
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, default=150, help="cases per function for each planted bug")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("item_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = S.find_cc()
    if not cc:
        print("item_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_ITEM)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    S.COVERAGE.clear()
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"item_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:28s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:28s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("item_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in S.COVERAGE.items():
        print(f"  {name:28s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"item_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"item_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
