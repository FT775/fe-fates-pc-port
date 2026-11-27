#!/usr/bin/env python3
"""Host differential test of the movement and terrain readable code against the game's own ARM code.

    python src/readable/move/tests/move_diff.py             all functions, 300 cases each
    python src/readable/move/tests/move_diff.py -n 1500 --seed 7    the long run
    python src/readable/move/tests/move_diff.py --only route_cost
    python src/readable/move/tests/move_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/sheet/tests/sheet_diff.py (and the ARM interpreter
src/readable/battle/tests/arm_mini.py): for every readable function of src/readable/move/ the test
makes up guest states (a map image with its unit, tile-kind and cost-column grids, a terrain tile
table, a TerrainCost table, units with their Person, class and force, routes, a deploy and its move
image, the one-time caches; all random test values, never game data, and on purpose often outside
the ranges the game uses: coordinates off the map and far off it, tile kinds past the table, cost
columns past the row, route bytes with bit 7 and other bits set, negative terrain numbers, unmapped
units and records), runs the ORIGINAL ARM code from the owner's extracted/text.bin in arm_mini.py
and the readable C function (built with the host gcc against tools/readable/stub/) on the same
memory, and compares r0, the number of bytes read from unmapped memory AND the list of guest calls,
in order, with their argument registers (docs/DECISIONS.md F-018). On the ARM side every BL/BLX
and every tail branch (B) to a stubbed callee is listed (also inside callees that run as ARM code);
a tail branch to an override runs on as ARM code, unlisted (3dsrecomp inlines it; round 10 integrate);
on the C side every guest call is listed (one that reaches another override of this batch runs
that override, as in the capture library). A one-time cache that is not filled must make the
original reach the guard routine and the readable code give up before reading anything; a nested
give-up (a guest call of another readable function giving up inside while the outer one goes on)
is a mismatch.

Guest functions answered by one table on both sides: unit::Item::ToData, Unit::IsEquipSkill,
Unit::IsItemEnhanceHave, Force::IsAllied and UnitPool::Get (answered with the unit the game's
code would give, so the callers read real unit records). Unit::GetCategory runs as ARM code on the
ARM side and as its readable override (sheet batch) on the C side; Terrain::Get, Map::Get,
map::Image::Unit::GetUnit, TerrainCost::GetCostFromUnit and Unit::IsCostFree run as ARM code and as
this batch's overrides. Force::Get (a NOP falling into UnitPool::GetForce) runs as ARM code and is
done inline by the C side (not listed).

--plant copies src/readable/move/ to build/readable/move/plant/, makes one small wrong change at a
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
OUT = os.path.join(ROOT, "build", "readable", "move")
SRC_MOVE = os.path.join(ROOT, "src", "readable", "move")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
TO_DATA, IS_EQUIP, ENHANCE_HAVE, IS_ALLIED, POOL_GET = 0x003D0EA4, 0x0052DD04, 0x0052FB98, 0x0053C3E0, 0x004F6174
LEAF_STUBS = {TO_DATA: 1, IS_EQUIP: 2, ENHANCE_HAVE: 3, IS_ALLIED: 2, POOL_GET: 1}

OVERRIDES = {  # name -> address
    "terrain_record": 0x004E0AFC, "terrain_is_castle_unit_dispos": 0x00545324, "cursor_terrain": 0x0039B7E4,
    "map_get": 0x00342574, "script_terrain_height": 0x003A7BAC, "script_terrain_width": 0x003A7BD0,
    "script_terrain_out_of_play_area": 0x003AE294, "script_terrain_has_flag": 0x003AE12C,
    "camera_play_area_w": 0x005270FC, "camera_play_area_h": 0x005270DC, "ai_terrain_score": 0x004CB124,
    "terrain_cost_row": 0x001A67EC, "terrain_cost_for_unit": 0x001A6708, "unit_is_cost_free": 0x0052AB90,
    "route_cost": 0x00394BC0, "route_goal_x": 0x00395B50, "route_goal_y": 0x00395B88, "route_cross": 0x0052650C,
    "job_is_flyer": 0x00524980, "job_is_rider": 0x00524A7C,
    "image_unit_at": 0x00526424, "script_unit_at": 0x003ABE80, "move_image_get": 0x005278A0,
    "deploy_is_fill": 0x00527734,
}
GET_CATEGORY = 0x0052B728
TERRAIN_GET, MAP_GET, IMAGE_GET_UNIT = 0x004E0AFC, 0x00342574, 0x00526424
COST_FROM_UNIT, IS_COST_FREE = 0x001A6708, 0x0052AB90
# the callees listed on both sides, with the argument registers compared
ARITY = dict(LEAF_STUBS)
ARITY.update({GET_CATEGORY: 1, TERRAIN_GET: 1, MAP_GET: 0, IMAGE_GET_UNIT: 3,
              COST_FROM_UNIT: 2, IS_COST_FREE: 1})

# globals and caches (src/readable/move/move.h, src/readable/sheet/sheet.h)
G_MAPIMAGE, G_MAP, G_TERRAIN_HEADER, G_TERRAIN_COST, G_UNITPOOL = 0x006D73E8, 0x006D72F4, 0x006D3C9C, 0x006D3CA0, 0x006D9F40
COST_GUARD, COST_OWN_MASK = 0x006D3CAC, 0x006D3CE0
CASTLE_GUARD, CASTLE_ROW = 0x006D3CA4, 0x006D3CA8
FREE_ITEM_GUARD, FREE_ITEM_MASK = 0x006D99C8, 0x006D9CD0
FREE_SKILL_GUARD, FREE_SKILL = 0x006D99C4, 0x006D96E0
FREE_SHOOTER_GUARD, FREE_SHOOTER_MASK = 0x006D99A8, 0x006D96D8
CAT_GUARDS = (0x006D97D0, 0x006D97CC, 0x006D97C8, 0x006D97C4, 0x006D97C0)
CAT_DRAGON, CAT_BEAST = 0x006D9668, 0x006D966A
CAT_FLAGS = (0x006D9AA8, 0x006D9AB0, 0x006D9AB8)
FILL_GUARD, FILL_MASK = 0x006D7380, 0x006D73E0
FLYER_GUARD, FLYER_MASK, RIDER_GUARD, RIDER_MASK = 0x006D39A8, 0x006D3992, 0x006D39A4, 0x006D3990
SCORE_FLYER_GUARD, SCORE_FLYER_MASK, SCORE_SKILL_GUARD, SCORE_SKILL = 0x006D108C, 0x006D1064, 0x006D1088, 0x006D1066
ALL_GUARDS = (COST_GUARD, CASTLE_GUARD, FREE_ITEM_GUARD, FREE_SKILL_GUARD, FREE_SHOOTER_GUARD, FILL_GUARD,
              FLYER_GUARD, RIDER_GUARD, SCORE_FLYER_GUARD, SCORE_SKILL_GUARD) + CAT_GUARDS
U16_MASKS = (FREE_SHOOTER_MASK, CAT_DRAGON, CAT_BEAST, FLYER_MASK, RIDER_MASK, SCORE_FLYER_MASK)
U64_MASKS = (COST_OWN_MASK, FREE_ITEM_MASK, FILL_MASK) + CAT_FLAGS
SKILLS = (FREE_SKILL, SCORE_SKILL)

# guest layout of the made-up state
UNITS = 0x08000000                       # UnitPool.units: unit number n at UNITS + (n - 1) * 0x140
UNIT = lambda k: UNITS + k * 0x140  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
FORCES = 0x08030000                      # UnitPool.forces: 10 records of 12 bytes
ITEMDATA = lambda k: 0x08040000 + k * 0x80  # noqa: E731
MAPIMG = 0x08100000                      # 0x1008 bytes: header, unit grid +8, tile kinds +0x408, cost columns +0xC08
TILES = 0x08200000                       # TerrainTile records, 0x28 each
TERRHDR = 0x08210000
COSTHDR = 0x08300000
ROUTE = 0x08400000
ROUTEOBJ = 0x08410000
DEPLOY = 0x08500000
MOVEIMG = 0x08600000
NUNITS, NJOBS, NTILES, NITEMS, NCLASSES = 6, 6, 12, 8, 6
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
COORDS = list(range(0, 32))
ODD_COORDS = [-1, -2, -33, 32, 33, 40, 255, 1000, 0x7FFFFFFF, -0x80000000]
SKILL_IDS = list(range(1, 30))


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sxs16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def guard(st, addr: int, cold_p: float = 0.01) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def coord(rng, p_odd: float = 0.12) -> int:
    return s32(pick(rng, COORDS, ODD_COORDS, p_odd))


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    for g in ALL_GUARDS:
        guard(st, g)
    for a in U16_MASKS:
        st.put(a, 2, 1 << rng.randrange(16) if rng.random() > 0.05 else rng.randrange(1 << 16))
    for a in U64_MASKS:
        st.put(a, 8, 1 << rng.randrange(64) if rng.random() > 0.05 else rng.randrange(1 << 64))
    for a in SKILLS:
        st.put(a, 2, pick(rng, SKILL_IDS, [0, -1, 0x7FFF, -0x8000], 0.08) & 0xFFFF)
    # the map: present most of the time
    st.put(G_MAP, 4, 0 if rng.random() < 0.1 else 0x08700000)
    st.put(G_MAPIMAGE, 4, MAPIMG if rng.random() > 0.03 else rng.choice(UNMAPPED))
    map_image(st)
    terrain_tables(st)
    units(st)
    return st


def map_image(st) -> None:
    rng = st.rng
    st.put(MAPIMG, 1, pick(rng, [15, 20, 24, 28, 32], [0, 1, 255]))
    st.put(MAPIMG + 1, 1, pick(rng, [15, 20, 24, 28, 32], [0, 1, 255]))
    for off in range(4):  # play area: min usually 1, end usually size - 1; sometimes anything
        lo = off < 2
        st.put(MAPIMG + 2 + off, 1, pick(rng, [1] if lo else [14, 19, 23, 27, 31], [0, 2, 5, 31, 32, 200, 255], 0.2))
    for i in range(1024):  # the unit grid: mostly empty
        r = rng.random()
        st.mem[MAPIMG + 8 + i] = 0 if r < 0.7 else rng.randrange(1, NUNITS + 1) if r < 0.97 else rng.randrange(256)
        st.mem[MAPIMG + 0x408 + i] = rng.randrange(NTILES) if rng.random() > 0.02 else rng.randrange(256)
        st.mem[MAPIMG + 0xC08 + i] = rng.randrange(24) if rng.random() > 0.02 else rng.randrange(256)


def terrain_tables(st) -> None:
    rng = st.rng
    st.put(G_TERRAIN_HEADER, 4, TERRHDR if rng.random() > 0.03 else rng.choice(UNMAPPED))
    st.fill(TERRHDR, 0x10)
    st.put(TERRHDR, 4, TILES if rng.random() > 0.03 else rng.choice(UNMAPPED))
    for k in range(NTILES):
        t = TILES + k * 0x28
        st.fill(t, 0x28)
        st.put(t + 0x10, 1, pick(rng, [0, 1, 2, 3, 5, 8, 12, 20], [255, 30]))
        for f in (0x11, 0x12, 0x13):
            st.put(t + f, 1, pick(rng, [0, 0, 5, 10, 20, 30, -5, -10, -20], [127, -128, 100, -100], 0.15) & 0xFF)
        attr = rng.randrange(1 << 32) if rng.random() < 0.3 else 0
        for bit, p in ((8, 0.3), (0x100, 0.4), (1, 0.2), (0x20, 0.2)):
            attr = (attr | bit) if rng.random() < p else (attr & ~bit)
        st.put(t + 0x18, 4, attr)
    # the TerrainCost table
    st.put(G_TERRAIN_COST, 4, COSTHDR if rng.random() > 0.03 else rng.choice(UNMAPPED))
    cols = pick(rng, [1, 4, 7, 13, 16, 20, 23], [0, 2, 0xFFFFFFFD, 0x101], 0.1)
    st.put(COSTHDR, 4, cols)
    stride = ((cols + 3) & ~3) & 0xFFFFFFFF
    if stride <= 0x200:
        for i in range(stride * NCLASSES + 32):
            st.mem[COSTHDR + 4 + i] = pick(rng, [1, 1, 1, 2, 2, 3, 5, -1 & 0xFF, -1 & 0xFF], [0, 0x80, 0x7F, 0xFE])
    st.put(CASTLE_ROW, 4, COSTHDR + 4 + stride * rng.randrange(NCLASSES) if rng.random() > 0.05 else rng.choice(UNMAPPED))


def units(st) -> None:
    rng = st.rng
    st.put(G_UNITPOOL, 4, UNITS if rng.random() > 0.03 else rng.choice(UNMAPPED))
    st.put(G_UNITPOOL + 4, 4, FORCES if rng.random() > 0.03 else rng.choice(UNMAPPED))
    for n in range(256):  # UnitPool::Get, answered by the table: what its code gives
        st.oracle[(POOL_GET, n)] = 0 if n == 0 else s32(word(st, G_UNITPOOL) + (n - 1) * 0x140)
    for f in range(10):
        st.fill(FORCES + f * 12, 12)
        st.put(FORCES + f * 12 + 8, 1, pick(rng, [f, f, 0, 1, 2], [9, 31, 255]))
    for k in range(NJOBS):
        j = JOB(k)
        st.fill(j, 0x80)
        st.put(j + 0x5C, 1, pick(rng, list(range(NCLASSES)), [200, 255], 0.05))
        st.put(j + 0x1A, 2, rng.randrange(1 << 16))
    for k in range(NITEMS):
        st.fill(ITEMDATA(k), 0x10)
    for k in range(NUNITS):
        u, p = UNIT(k), PERSON(k)
        st.fill(u, 0x140)
        st.fill(p, 0x10)
        st.put(u + 0x9C, 4, p if rng.random() > 0.03 else rng.choice(UNMAPPED))
        st.put(u + 0xA0, 4, JOB(rng.randrange(NJOBS)) if rng.random() > 0.03 else rng.choice(UNMAPPED))
        st.put(u + 0xA4, 4, FORCES + 12 * rng.randrange(10) if rng.random() > 0.03 else rng.choice(UNMAPPED))
        st.put(u + 0x54, 4, rng.randrange(1 << 32) if rng.random() < 0.5 else 0)
        for base in (u, p):  # flag words: mostly without the masks' bits
            if rng.random() < 0.7:
                v = word(st, base, 8)
                for m in U64_MASKS:
                    v &= ~word(st, m, 8)
                st.put(base, 8, v)
    for k in range(NJOBS):
        if rng.random() < 0.7:
            v = word(st, JOB(k), 8)
            for m in U64_MASKS:
                v &= ~word(st, m, 8)
            st.put(JOB(k), 8, v)


def answer_unit(st, u: int) -> None:
    """what the table-answered guest calls give for this unit (also for an unmapped one)"""
    rng = st.rng
    for a in SKILLS:
        st.oracle[(IS_EQUIP, s32(u), s32(sxs16(word(st, a, 2))))] = int(rng.random() < 0.4)
    for slot in range(5):
        item = s32(u + 0x108 + 4 * slot)
        st.oracle[(TO_DATA, item)] = ITEMDATA(rng.randrange(NITEMS)) if rng.random() > 0.05 else rng.choice(UNMAPPED)
        st.oracle[(ENHANCE_HAVE, s32(u), item, 1)] = int(rng.random() < 0.5)
    for f in range(12):
        for t in list(range(10)) + [31, 255]:
            st.oracle[(IS_ALLIED, s32(FORCES + 12 * f), t)] = int(rng.random() < 0.5)


def unit_arg(st, unmapped_p: float = 0.06) -> int:
    u = st.rng.choice(UNMAPPED) if st.rng.random() < unmapped_p else UNIT(st.rng.randrange(NUNITS))
    answer_unit(st, u)
    return u


def item_flags_focus(st, u: int) -> None:
    """sometimes give an item record the cost-free item flag"""
    if UNITS <= u < UNIT(NUNITS) and st.rng.random() < 0.5:
        k = st.rng.randrange(NITEMS)
        st.put(ITEMDATA(k), 8, word(st, ITEMDATA(k), 8) | word(st, FREE_ITEM_MASK, 8))


def route_bytes(st, addr: int, n: int | None = None) -> list[int]:
    rng = st.rng
    n = rng.choice([0, 1, 2, 3, 5, 8, 12]) if n is None else n
    steps = []
    for _ in range(n):
        b = rng.choice([1, 2, 4, 8]) if rng.random() < 0.75 else rng.randrange(0x80)
        if rng.random() < 0.05:
            b = rng.choice([0x81, 0x82, 0x84, 0x88, 0xFF, 0xC0])  # bit 7 with others: not the end mark everywhere
        steps.append(b)
    for i, b in enumerate(steps + [0x80]):
        st.mem[addr + i] = b
    return steps


def cool(st, guards, p: float = 0.03) -> None:
    for g in guards:
        if st.rng.random() < p:
            st.put(g, 4, 0)


def ov(name, args):
    a = OVERRIDES[name]
    return f"ov:0x{a:08X}", [s32(x) for x in args] + [0] * (4 - len(args)), ("call", a)


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def gen_terrain_record(rng):
    st = base_state(rng)
    t = pick(rng, list(range(NTILES)), [-1, NTILES, 255, 1000, 0x7FFFFFFF, -0x80000000])
    return (st,) + ov("terrain_record", [t])


def gen_castle(rng):
    st = base_state(rng)
    cool(st, (CASTLE_GUARD,))
    t = TILES + 0x28 * rng.randrange(NTILES) if rng.random() > 0.06 else rng.choice(UNMAPPED)
    return (st,) + ov("terrain_is_castle_unit_dispos", [t])


def gen_xy(name, with_this=True):
    def gen(rng):
        st = base_state(rng)
        args = ([rng.randrange(1 << 32)] if with_this else []) + [coord(rng), coord(rng)]
        return (st,) + ov(name, args)
    return gen


def gen_script(name):
    def gen(rng):
        st = base_state(rng)
        return (st,) + ov(name, [rng.randrange(1 << 32)])
    return gen


def gen_has_flag(rng):
    st = base_state(rng)
    flag = pick(rng, [8, 0x100, 1, 0x20, 0x108], [0, 0xFFFFFFFF, 0x80000000])
    return (st,) + ov("script_terrain_has_flag", [rng.randrange(1 << 32), coord(rng), coord(rng), flag])


def gen_map_get(rng):
    st = base_state(rng)
    if rng.random() < 0.1:
        del st.mem[G_MAP]  # unmapped on purpose (the page stays: it reads 0 on both sides)
    return (st,) + ov("map_get", [])


def gen_score(rng):
    st = base_state(rng)
    cool(st, (SCORE_FLYER_GUARD, SCORE_SKILL_GUARD) + CAT_GUARDS, 0.02)
    u = unit_arg(st)
    if rng.random() < 0.5:  # focused: not a flyer, so the terrain is read
        st.put(SCORE_FLYER_MASK, 2, 0)
    x, y = coord(rng), coord(rng)
    if rng.random() < 0.5 and 0 <= x < 32 and 0 <= y < 32:
        # focused (ai_perm batch, 2026-11-15): odd negative defence and heal on the tile itself, where a
        # division toward zero and a shift or a floor give different answers (-1 / 5 = 0, -7 / 5 = -1,
        # -11 / 10 = -1), with and without the "lockpick" pairing that lifts them to 0
        kind = st.mem[MAPIMG + 0x408 + (x | y << 5)]
        if kind < NTILES:
            t = TILES + kind * 0x28
            odd = [-1, -2, -3, -4, -6, -7, -9, -11, -13, -19, -21, -49, -99, -127, -128]
            st.put(t + 0x11, 1, rng.choice(odd) & 0xFF)  # defense
            st.put(t + 0x13, 1, rng.choice(odd + [-5, -10, 9, 11]) & 0xFF)  # heal
            if rng.random() < 0.5:
                st.put(t + 0x12, 1, rng.choice([-1, -3, 0, 4, 7, 30]) & 0xFF)  # avoid
            if rng.random() < 0.5:
                st.put(t + 0x18, 4, word(st, t + 0x18) | 0x100)  # the attribute "lockpick" lifts
    return (st,) + ov("ai_terrain_score", [u, x, y])


def gen_cost_row(rng):
    st = base_state(rng)
    r = pick(rng, list(range(NCLASSES)), [-1, 200, 0x7FFFFFFF, -0x80000000])
    return (st,) + ov("terrain_cost_row", [r])


def gen_cost_for_unit(rng):
    st = base_state(rng)
    cool(st, (COST_GUARD,))
    u = unit_arg(st)
    if rng.random() < 0.3 and UNITS <= u < UNIT(NUNITS):  # focused: the "own terrain cost" flag
        st.put(u, 8, word(st, u, 8) | word(st, COST_OWN_MASK, 8))
    col = pick(rng, list(range(24)), [-1, -4, 255, 1000, 0x7FFFFFFF])
    return (st,) + ov("terrain_cost_for_unit", [u, col])


def gen_cost_free(rng):
    st = base_state(rng)
    cool(st, (FREE_ITEM_GUARD, FREE_SKILL_GUARD, FREE_SHOOTER_GUARD) + CAT_GUARDS, 0.015)
    u = unit_arg(st)
    item_flags_focus(st, u)
    return (st,) + ov("unit_is_cost_free", [u])


def gen_route_cost(rng):
    st = base_state(rng)
    cool(st, (COST_GUARD, FREE_ITEM_GUARD, FREE_SKILL_GUARD, FREE_SHOOTER_GUARD) + CAT_GUARDS, 0.01)
    u = unit_arg(st)
    item_flags_focus(st, u)
    route_bytes(st, ROUTE)
    return (st,) + ov("route_cost", [u, coord(rng), coord(rng), ROUTE])


def gen_goal(name):
    def gen(rng):
        st = base_state(rng)
        route_bytes(st, ROUTE)
        return (st,) + ov(name, [coord(rng, 0.2), ROUTE])
    return gen


def gen_cross(rng):
    st = base_state(rng)
    st.fill(ROUTEOBJ, 0x100)
    steps = route_bytes(st, ROUTEOBJ, rng.choice([0, 1, 3, 6, 10, 20]))
    count = pick(rng, [len(steps), len(steps), max(len(steps) - 1, 0)], [0, 200, 255])
    sx = rng.randrange(32) if rng.random() > 0.1 else rng.choice([-1, -5, -128, 127])
    sy = rng.randrange(32) if rng.random() > 0.1 else rng.choice([-1, -5, -128, 127])
    st.put(ROUTEOBJ + 0x80, 1, count)
    st.put(ROUTEOBJ + 0x81, 1, sx & 0xFF)  # signed bytes: a start off the map's top or left edge too
    st.put(ROUTEOBJ + 0x82, 1, sy & 0xFF)
    # focused: a tile on the route (often), the start, the last tile
    x, y = sx, sy
    path = [(x, y)]
    for b in steps:
        x += -1 if b & 1 else 1 if b & 2 else 0
        y += -1 if b & 8 else 1 if b & 4 else 0
        path.append((x, y))
    if rng.random() < 0.6:
        x, y = rng.choice(path)
    else:
        x, y = coord(rng), coord(rng)
    obj = ROUTEOBJ if rng.random() > 0.04 else rng.choice(UNMAPPED)
    return (st,) + ov("route_cross", [obj, x, y])


def gen_job(name, guard_addr):
    def gen(rng):
        st = base_state(rng)
        cool(st, (guard_addr,))
        j = JOB(rng.randrange(NJOBS)) if rng.random() > 0.06 else rng.choice(UNMAPPED)
        return (st,) + ov(name, [j])
    return gen


def gen_image_unit(rng):
    st = base_state(rng)
    img = MAPIMG + 8 if rng.random() > 0.06 else rng.choice(UNMAPPED)
    return (st,) + ov("image_unit_at", [img, coord(rng), coord(rng)])


def move_image(st) -> None:
    rng = st.rng
    for i in range(1024):
        st.mem[MOVEIMG + i] = pick(rng, [0xFF, 0xFF, 0, 1, 2, 3, 5], [0x80, 0x7F])


def gen_move_image(rng):
    st = base_state(rng)
    move_image(st)
    img = MOVEIMG if rng.random() > 0.05 else rng.choice(UNMAPPED)
    return (st,) + ov("move_image_get", [img, coord(rng), coord(rng)])


def gen_fill(rng):
    st = base_state(rng)
    cool(st, (FILL_GUARD,))
    move_image(st)
    for k in range(NUNITS):
        answer_unit(st, UNIT(k))
    answer_unit(st, 0)
    d = DEPLOY
    st.put(d + 0x80C, 4, MOVEIMG if rng.random() > 0.04 else rng.choice(UNMAPPED))
    st.put(d + 0x818, 4, MAPIMG + 8 if rng.random() > 0.04 else rng.choice(UNMAPPED))
    mode = rng.randrange(1 << 32) if rng.random() < 0.2 else 0
    for bit, p in ((4, 0.25), (0x10, 0.5), (0x4000, 0.5)):
        mode = (mode | bit) if rng.random() < p else (mode & ~bit)
    st.put(d + 0x1624, 4, mode)
    st.put(d + 0x1628, 1, pick(rng, list(range(10)), [11, 255]))
    x, y = coord(rng), coord(rng)
    if rng.random() < 0.6 and 0 <= x < 32 and 0 <= y < 32:  # focused: a unit there, a reached tile
        t = x | y << 5
        st.mem[MAPIMG + 8 + t] = rng.randrange(1, NUNITS + 1)
        st.mem[MOVEIMG + t] = rng.choice([1, 2, 3])
        tk = st.mem[MAPIMG + 0x408 + t]
        if tk < NTILES and rng.random() < 0.7:
            a = TILES + tk * 0x28 + 0x18
            st.put(a, 4, word(st, a) & ~8)
        if rng.random() < 0.3:
            u = UNIT(st.mem[MAPIMG + 8 + t] - 1)
            st.put(u, 8, word(st, u, 8) | word(st, FILL_MASK, 8))
    dep = d if rng.random() > 0.03 else rng.choice(UNMAPPED)
    return (st,) + ov("deploy_is_fill", [dep, x, y])


FUNCS = {
    "terrain_record": gen_terrain_record,
    "terrain_is_castle_unit_dispos": gen_castle,
    "cursor_terrain": gen_xy("cursor_terrain"),
    "map_get": gen_map_get,
    "script_terrain_height": gen_script("script_terrain_height"),
    "script_terrain_width": gen_script("script_terrain_width"),
    "script_terrain_out_of_play_area": gen_xy("script_terrain_out_of_play_area"),
    "script_terrain_has_flag": gen_has_flag,
    "camera_play_area_w": gen_script("camera_play_area_w"),
    "camera_play_area_h": gen_script("camera_play_area_h"),
    "ai_terrain_score": gen_score,
    "terrain_cost_row": gen_cost_row,
    "terrain_cost_for_unit": gen_cost_for_unit,
    "unit_is_cost_free": gen_cost_free,
    "route_cost": gen_route_cost,
    "route_goal_x": gen_goal("route_goal_x"),
    "route_goal_y": gen_goal("route_goal_y"),
    "route_cross": gen_cross,
    "job_is_flyer": gen_job("job_is_flyer", FLYER_GUARD),
    "job_is_rider": gen_job("job_is_rider", RIDER_GUARD),
    "image_unit_at": gen_image_unit,
    "script_unit_at": gen_xy("script_unit_at"),
    "move_image_get": gen_move_image,
    "deploy_is_fill": gen_fill,
}


# ------------------------------------------------------------------ sharper cases (round 13, F-025)
# Each SHARP generator aims at one planted bug the cases above never told apart (docs/harness/H6_SURVIVORS.md).
# They draw from their own random stream (n // 3 cases each), so the cases of FUNCS stay exactly as they were.

def _toward_zero(a: int, b: int) -> int:
    q = abs(a) // b
    return q if a >= 0 else -q


def gen_score_cap(rng):
    """ai_terrain_score's clamp at its top: a unit that is not a flyer on a tile whose score adds up to exactly
    61 .. 66 (mostly 63 and 64), with the "lockpick" attribute bit clear or set. Catches the clamp's test
    `score > 63` made `score > 64` (only a score of exactly 64 tells them apart; no terrain of the game has the
    avoid that takes)."""
    st = base_state(rng)
    st.put(SCORE_FLYER_GUARD, 4, 1)
    st.put(SCORE_SKILL_GUARD, 4, 1)
    for g in CAT_GUARDS:
        st.put(g, 4, 1)
    st.put(SCORE_FLYER_MASK, 2, 0)
    st.put(G_MAPIMAGE, 4, MAPIMG)
    st.put(G_TERRAIN_HEADER, 4, TERRHDR)
    st.put(TERRHDR, 4, TILES)
    u = unit_arg(st, 0.0)
    x, y = rng.randrange(32), rng.randrange(32)
    kind = rng.randrange(NTILES)
    st.mem[MAPIMG + 0x408 + (x | y << 5)] = kind
    t = TILES + kind * 0x28
    target = rng.choice([63, 64, 64, 64, 63, 65, 62, 61, 66])
    defense = rng.choice([0, 0, 5, 10, 14, 25, -1, -6])
    heal = rng.choice([0, 0, 10, 19, 20, -1, -11])
    avoid = target - 5 - _toward_zero(defense, 5) - _toward_zero(heal, 10)
    if not -128 <= avoid <= 127:
        defense, heal, avoid = 0, 0, target - 5
    st.put(t + 0x11, 1, defense & 0xFF)
    st.put(t + 0x12, 1, avoid & 0xFF)
    st.put(t + 0x13, 1, heal & 0xFF)
    if defense >= 0 and heal >= 0 and rng.random() < 0.5:  # lockpick lifts only negatives: same score
        st.put(t + 0x18, 4, word(st, t + 0x18) | 0x100)
    return (st,) + ov("ai_terrain_score", [u, x, y])


SHARP = [
    ("ai_terrain_score", gen_score_cap),
]


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX and every tail branch (B) to a callee of ARITY (stubbed
    or run as ARM code) with its argument registers; with USAT, which arm_mini does not model."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.listed.append(call_text(target, self.r[:ARITY[target]]))
        return super().call(target, ret)

    def step(self, ins: int, pc: int) -> None:
        c = ins >> 28
        if c != 0xF and self.cond(c):
            if (ins >> 24) & 0xF == 0xA:  # B (no link): a tail call when it reaches a listed callee
                target = (pc + 8 + (A.sx(ins & 0xFFFFFF, 24) << 2)) & A.MASK
                stub = self.stubs.get(target)
                if target in ARITY and stub is not None:
                    # a stubbed tail call (a guest function, the readable code makes a guest call): listed,
                    # and it returns straight to the caller's caller
                    self.listed.append(call_text(target, self.r[:ARITY[target]]))
                    self.r[0] = stub(self, tuple(self.r[:4])) & A.MASK
                    self.r[15] = self.r[14]
                    return
                # a tail branch to an override runs on as ARM code, unlisted (round 10 integrate): 3dsrecomp
                # keeps the target's code inside the caller's generated function, so in the library the
                # original never enters that override from there (cursor_terrain -> Terrain::Get: the live
                # compare showed the extra call; docs/MOVE.md 9, docs/SUPPORT.md)
            if (ins & 0x0FE00030) == 0x06E00010:  # USAT Rd, #sat, Rn{, shift}
                sat = (ins >> 16) & 0x1F
                rn, rd = ins & 0xF, (ins >> 12) & 0xF
                kind = 2 if ins & 0x40 else 0
                v, _ = self.shift(self.r[rn], kind, (ins >> 7) & 0x1F, self.c, False)
                v = A.sx(v, 32)
                self.r[rd] = max(0, min(v, (1 << sat) - 1))
                return
        super().step(ins, pc)


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
DRIVER_HEAD = r'''
/* Generated by src/readable/move/tests/move_diff.py: runs readable movement and terrain functions
   on memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "move.h"
'''


def driver_text() -> str:
    sys.path.insert(0, os.path.join(ROOT, "src", "readable", "sheet", "tests"))
    import sheet_diff as S  # the same driver body: page memory, call list, oracle, nested give-ups
    body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
    addrs = sorted(set(OVERRIDES.values()) | {GET_CATEGORY})
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in addrs)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in addrs) + "};\n"
    return DRIVER_HEAD + body.replace("@OVERRIDE_DECLS@", decls + table)


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


def build_driver(cc: str, out: str, move_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, the move folder's taken from move_dir
    (a planted bug may leave a parameter unused: not strict then, warnings are not errors)."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "move_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_MOVE)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(move_dir, f) for f in os.listdir(move_dir) if f.endswith(".c")]
    exe = os.path.join(out, "move_driver.exe" if os.name == "nt" else "move_driver")
    inc = ["-I", move_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    warn = ["-Wall", "-Wextra", "-Werror"] if strict else ["-w"]
    cmd = [cc, "-std=c11"] + warn + ["-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"move_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines = [f"arity {f:x} {k}" for f, k in ARITY.items()]
    expected: dict[int, tuple[str, list, tuple]] = {}
    unsupported: dict[str, int] = {}
    cid = 0
    # round 13 (F-025): SHARP's cases come from their own random stream, so the cases of FUNCS stay as they were
    sharp_rng = random.Random(seed ^ 0x5EED13)
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
        raise SystemExit(f"move_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
    # move_terrain.c
    ("move_terrain.c", "    return table + (gaddr)tile * TERRAIN_RECORD_SIZE;", "    return table + (gaddr)tile * 0x24u;"),
    ("move_terrain.c", "    return guest_s8(ctx, guest_ptr(ctx, S_CastleRow) + column) > 0 ? 1u : 0u;",
     "    return guest_s8(ctx, guest_ptr(ctx, S_CastleRow) + column) >= 0 ? 1u : 0u;"),
    ("move_terrain.c", "    if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & TERRAIN_ATTR_BLOCKED)\n        return 0;\n    column",
     "    if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & 0x10u)\n        return 0;\n    column"),
    ("move_terrain.c", "    return terrain_record(ctx, (int32_t)tile_kind(ctx, x, y));",
     "    return terrain_record(ctx, (int32_t)tile_kind(ctx, y, x));"),
    ("move_terrain.c", "    return guest_ptr(ctx, G_Map);", "    return guest_ptr(ctx, G_MapImage);"),
    ("move_terrain.c", "    return guest_u8(ctx, guest_ptr(ctx, G_MapImage) + MAPIMAGE_HEIGHT);",
     "    return guest_s8(ctx, guest_ptr(ctx, G_MapImage) + MAPIMAGE_HEIGHT);"),
    ("move_terrain.c", "    return guest_u8(ctx, guest_ptr(ctx, G_MapImage) + MAPIMAGE_WIDTH);",
     "    return guest_u8(ctx, guest_ptr(ctx, G_MapImage) + MAPIMAGE_HEIGHT);"),
    # the bounds read all at once: same answers, other unmapped-read counts
    ("move_terrain.c", "    if ((int32_t)READ_FIELD(ctx, MapImage, image, play_x_min) > x)\n        return 0;",
     "    int32_t ye = READ_FIELD(ctx, MapImage, image, play_y_end);\n    if ((int32_t)READ_FIELD(ctx, MapImage, image, play_x_min) > x || ye < -1000)\n        return 0;"),
    ("move_terrain.c", "    if (x >= (int32_t)READ_FIELD(ctx, MapImage, image, play_x_end))",
     "    if (x > (int32_t)READ_FIELD(ctx, MapImage, image, play_x_end))"),
    ("move_terrain.c", "        return 1;\n    return in_play_area(ctx, guest_ptr(ctx, G_MapImage), x, y) ? 0u : 1u;",
     "        return 0;\n    return in_play_area(ctx, guest_ptr(ctx, G_MapImage), x, y) ? 0u : 1u;"),
    ("move_terrain.c", "    return (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & flag) != 0 ? 1u : 0u;",
     "    return (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & flag) == flag ? 1u : 0u;"),
    ("move_terrain.c", "    return (end - READ_FIELD(ctx, MapImage, image, play_x_min)) & 0xFFu;",
     "    return end - READ_FIELD(ctx, MapImage, image, play_x_min);"),
    ("move_terrain.c", "    uint32_t end = READ_FIELD(ctx, MapImage, image, play_y_end);",
     "    uint32_t end = READ_FIELD(ctx, MapImage, image, play_x_end);"),
    ("move_terrain.c", "    int32_t score = defense / 5 + 5 + avoid + heal / 10;", "    int32_t score = defense / 5 + 5 + avoid + fe_asr(heal, 3);"),
    # a floor division of a negative defence (the odd negative cases of the ai_perm batch catch it)
    ("move_terrain.c", "    int32_t score = defense / 5 + 5 + avoid + heal / 10;",
     "    int32_t score = (defense < 0 ? (defense - 4) / 5 : defense / 5) + 5 + avoid + heal / 10;"),
    ("move_terrain.c", "    return score < 0 ? 0 : score > 63 ? 63 : score;", "    return score < 0 ? 0 : score > 64 ? 64 : score;"),
    ("move_terrain.c", "        heal = heal < 0 ? 0 : heal;\n", ""),
    # the cached skill not asked: the flyer cache only
    ("move_terrain.c", "    if (!fe_static_ready(ctx, S_ScoreFlyerGuard) || !fe_static_ready(ctx, S_ScoreSkillGuard) ||",
     "    if (!fe_static_ready(ctx, S_ScoreFlyerGuard) ||"),
    # GetCategory's caches not asked by a caller: its override gives up nested
    ("move_terrain.c", "        !fe_static_ready(ctx, S_CatGuardA) || !fe_static_ready(ctx, S_CatGuardB) ||\n        !fe_static_ready(ctx, S_CatGuardC) || !fe_static_ready(ctx, S_CatGuardD) ||\n        !fe_static_ready(ctx, S_CatGuardE))",
     "        !fe_static_ready(ctx, S_CatGuardE))"),
    # move_cost.c
    ("move_cost.c", "    *stride = (READ_FIELD(ctx, TerrainCostHeaderData, header, columns) + 3u) & ~3u;",
     "    *stride = READ_FIELD(ctx, TerrainCostHeaderData, header, columns);"),
    ("move_cost.c", "    return rows + stride * (gaddr)row;", "    return rows + stride * (gaddr)row + 1u;"),
    ("move_cost.c", "    if (cost >= 0)\n        return cost;", "    if (cost > 0)\n        return cost;"),
    ("move_cost.c", "        cost = guest_s8(ctx, rows + (gaddr)column);", "        cost = guest_s8(ctx, rows + stride + (gaddr)column);"),
    ("move_cost.c", "                     READ_FIELD(ctx, JobData, job, flags);\n    if (flags & mask)",
     "                     0;\n    if (flags & mask)"),
    ("move_cost.c", "    uint32_t shooter = guest_u16(ctx, S_FreeShooterMask);", "    uint32_t shooter = guest_u16(ctx, S_FreeSkill);"),
    ("move_cost.c", "            guest_call3(ctx, MOVE_UnitIsItemEnhanceHave, unit, item, 1u) != 0)",
     "            guest_call3(ctx, MOVE_UnitIsItemEnhanceHave, unit, item, 0u) != 0)"),
    ("move_cost.c", "    for (uint32_t slot = 0; slot < 5u; slot++) {", "    for (uint32_t slot = 0; slot < 4u; slot++) {"),
    ("move_cost.c", "    return (step & 1u) ? -1 : (step & 2u) ? 1 : 0;", "    return (step & 2u) ? 1 : (step & 1u) ? -1 : 0;"),
    ("move_cost.c", "    return (step & 8u) ? -1 : (step & 4u) ? 1 : 0;", "    return (step & 8u) ? -1 : (step & 4u) ? 2 : 0;"),
    ("move_cost.c", "        if (cost > 1) {", "        if (cost >= 1) {"),
    ("move_cost.c", "        } else if (cost < 0) {\n            cost = 0;\n        }", "        }"),
    ("move_cost.c", "        uint32_t column = guest_u8(ctx, image + MAPIMAGE_COST_COLUMN + move_tile(x, y));",
     "        uint32_t column = guest_u8(ctx, image + 0x408u + move_tile(x, y));"),
    ("move_cost.c", "    if (!fe_static_ready(ctx, S_CostGuard) || !cost_free_ready(ctx))",
     "    if (!fe_static_ready(ctx, S_CostGuard))"),
    ("move_cost.c", "    } while (!(next & ROUTE_END));\n    return x;", "    } while (next != ROUTE_END);\n    return x;"),
    ("move_cost.c", "        y = fe_add32(y, step_dy(guest_u8(ctx, route)));\n        route++;",
     "        y = fe_add32(y, step_dx(guest_u8(ctx, route)));\n        route++;"),
    ("move_cost.c", "        if (x == cx && y == cy)\n            return i;", "        if (x == cx || y == cy)\n            return i;"),
    ("move_cost.c", "    int32_t cy = guest_s8(ctx, route + ROUTE_START_Y);", "    int32_t cy = guest_u8(ctx, route + ROUTE_START_Y);"),
    ("move_cost.c", "    return (READ_FIELD(ctx, JobData, job, category) & guest_u16(ctx, S_FlyerMask)) != 0 ? 1u : 0u;",
     "    return (READ_FIELD(ctx, JobData, job, category) & guest_u16(ctx, S_RiderMask)) != 0 ? 1u : 0u;"),
    ("move_cost.c", "    if (!fe_static_ready(ctx, S_RiderGuard))", "    if (!fe_static_ready(ctx, S_FlyerGuard))"),
    # move_occupy.c
    ("move_occupy.c", "    return guest_call1(ctx, MOVE_UnitPoolGet, guest_u8(ctx, image + move_tile(x, y)));",
     "    return guest_call1(ctx, MOVE_UnitPoolGet, guest_s8(ctx, image + move_tile(x, y)));"),
    ("move_occupy.c", "    return guest_u8(ctx, unit + UNIT_NUMBER);", "    return guest_u8(ctx, unit + UNIT_NUMBER + 1u);"),
    ("move_occupy.c", "    gaddr unit = guest_call3(ctx, MOVE_ImageUnitGetUnit, units, (uint32_t)x, (uint32_t)y);",
     "    gaddr unit = guest_call3(ctx, MOVE_ImageUnitGetUnit, units - 8u, (uint32_t)x, (uint32_t)y);"),
    ("move_occupy.c", "        return -1;\n    return guest_s8(ctx, image + move_tile(x, y));", "        return -1;\n    return guest_u8(ctx, image + move_tile(x, y));"),
    ("move_occupy.c", "    if (reached == 0)\n        return 1;", "    if (reached == 0)\n        return 0;"),
    ("move_occupy.c", "    if (mode & DEPLOY_FILL_STOP)\n        return 0;", "    if (mode & 0x08u)\n        return 0;"),
    ("move_occupy.c", "        if (guest_u32(ctx, unit + UNIT_IMMOBILE_WORD) & 0x100u)", "        if (guest_u32(ctx, unit + UNIT_IMMOBILE_WORD) & 0x200u)"),
    ("move_occupy.c", "    return guest_call2(ctx, MOVE_ForceIsAllied, force, type) != 0 ? 1u : 0u;",
     "    return guest_call2(ctx, MOVE_ForceIsAllied, type, force) != 0 ? 1u : 0u;"),
    ("move_occupy.c", "    if (!(mode & DEPLOY_FILL_ALLY_TEST))\n        return 1;", "    if (!(mode & DEPLOY_FILL_ALLY_TEST))\n        return 0;"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_MOVE, d, ignore=shutil.ignore_patterns("tests"))
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
        print("move_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("move_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_MOVE)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"move_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:32s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:32s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("move_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:32s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"move_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"move_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
