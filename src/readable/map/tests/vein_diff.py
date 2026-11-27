#!/usr/bin/env python3
"""Host differential test of the dragon vein readable code against the game's own ARM code.

    python src/readable/map/tests/vein_diff.py             all functions, 400 cases each
    python src/readable/map/tests/vein_diff.py -n 2000     more cases
    python src/readable/map/tests/vein_diff.py --seed 7    another random sequence
    python src/readable/map/tests/vein_diff.py --only trick_is_access
    python src/readable/map/tests/vein_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/battle/tests/stance_diff.py and triangle_diff.py (same ARM
interpreter, arm_mini.py): for every readable function of src/readable/map/vein_*.c the test
makes up guest states (gimmick lists, units, Person blocks, the map image, terrain records,
the one-time caches; all random test values, never game data), runs the ORIGINAL ARM code from
the owner's extracted/text.bin and the readable C function (built with the host gcc against
tools/readable/stub/) on the same memory, and compares:

  - overrides: r0, through their override entry in readable mode;
  - the helper trick_preview_marks: the whole of map::trick::Data::SetDeploy 0x00526D98 runs as
    ARM code; its return value and every byte it leaves in a 3 KiB window around the preview
    bitmap (MapDeploy +0x151C) are compared with what the helper returns.

The ARM side runs every game function the originals call (map::Trick::Get, trick::Enumerator,
trick::Data::IsAccess, GetAccessForCannon, Terrain::Get, UnitPool::Get, map::Mind::*,
Person::IsDownload, PositionEnumerator) except a few library routines answered in Python with
the same meaning: operator new[] / delete[] (a bump allocator), the memory copy and clear
routines, sut::strcmp, and map::Deploy::Cannon (a cannon preview, not rewritten: the helper
only says "cannon"). The readable side calls no guest function at all. A one-time cache that
is not filled must make the original reach the guard routine and the readable code give up.

Inputs deliberately reach outside the usual ranges (the triangle review found a test that
only drew in-range values): coordinates of -1, -128, 127, 255, 1000 and the 32-bit extremes;
widths and heights of 0, negative and 127; every gimmick type 0..31 and a few above; unit
numbers 0, 251 and the extremes; text with no digits, empty numbers, numbers over 255 and
over 32 bits, odd counts, more than 16 positions (the game's spill array) and more than 16
matches of one search.

--plant copies the sources to build/readable/veins/plant/, makes one small wrong change at a
time (a list below), rebuilds and reruns: every planted bug must give at least one mismatch.

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
from stance_diff import State, pick, s32  # noqa: E402  (memory image, random helpers)

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "veins")
SRC_MAP = os.path.join(ROOT, "src", "readable", "map")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json

# library routines answered in Python on the ARM side
NEW_ARRAY, DELETE_ARRAY = 0x00113B54, 0x002FE014
MEMCPY, MEMCLR, STRCMP = 0x003002DC, 0x0011F440, 0x003028E4
DEPLOY_CANNON = 0x0039D270

# globals and caches (config/readable/globals.csv, src/readable/map/veins.h)
G_TRICK, G_IMAGE, G_DEPLOY, G_MIND = 0x006D7FEC, 0x006D73E8, 0x006D7364, 0x006D7568
G_THDR, G_PBLOCKS, G_UNITPOOL = 0x006D3C9C, 0x006D3B28, 0x006D9F40
VEIN_GUARD, VEIN_MASK = 0x006D99C0, 0x006D9CC8
DL_GUARD, DL_MASK = 0x006D3B3C, 0x006D3B90
ENUM_VTABLE, ENUM_IS_EXCLUSION = 0x0069C96C, 0x00399AA8  # trick::Enumerator's table, slot 2

# guest layout of the made-up state
TRICK = 0x08200000
DATA = lambda k: 0x08210000 + k * 0x40  # noqa: E731
TEXTS = lambda k: 0x08230000 + k * 0x100  # noqa: E731
UNITS = 0x08000000
UNIT = lambda n: UNITS + (n - 1) * 0x140  # noqa: E731  (pool number n >= 1)
PERSON = lambda k: 0x08100000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08110000 + k * 0x100  # noqa: E731
FORCE = lambda k: 0x08120000 + k * 0x10  # noqa: E731
IMAGE, THDR, TILES = 0x08300000, 0x08310000, 0x08320000
TILE_COUNT = 40
MIND = 0x08330000
NODE = lambda k: 0x08340000 + k * 0x10  # noqa: E731
BLOCK = lambda k: 0x08350000 + k * 0x40  # noqa: E731
DEPLOY = 0x08600000
MARKS = DEPLOY + 0x151C
WINDOW_BEFORE, WINDOW = 1024, 3072  # VEIN_MARKS_BEFORE / VEIN_MARKS_BYTES
HEAP = 0x08700000
SP = 0x0FFFF000

COORD_RARE = [-1, -2, -128, 127, 128, 255, 1000, -0x80000000, 0x7FFFFFFF]


# ------------------------------------------------------------------ random values
def coord(rng, near: int, p_rare: float = 0.06) -> int:
    r = rng.random()
    if r < p_rare:
        return s32(rng.choice(COORD_RARE))
    if r < 0.75:
        return s32(near)
    return s32(rng.choice([near - 1, near + 1, rng.randrange(-3, 36)]))


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x800, 0xC00)
    st.put(G_TRICK, 4, TRICK)
    st.put(G_IMAGE, 4, IMAGE)
    st.put(G_DEPLOY, 4, DEPLOY)
    st.put(G_MIND, 4, MIND)
    st.put(G_THDR, 4, THDR)
    st.put(G_UNITPOOL, 4, UNITS)
    st.put(ENUM_VTABLE + 8, 4, ENUM_IS_EXCLUSION)
    st.zero(HEAP, 0x400)
    return st


def guard(st: State, addr: int, cold_p: float = 0.06) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def terrain(st: State) -> None:
    """The map image (play area, current tile grid) and a terrain record table."""
    rng = st.rng
    st.fill(IMAGE, 0x10)
    if rng.random() < 0.8:
        area = [1, 1, rng.randrange(8, 32), rng.randrange(8, 32)]
    else:
        area = [rng.randrange(256) for _ in range(4)]
    for i, v in enumerate(area):
        st.put(IMAGE + 2 + i, 1, v)
    for i in range(0x400):
        st.put(IMAGE + 0x808 + i, 1, rng.randrange(TILE_COUNT) if rng.random() < 0.97 else rng.randrange(256))
    st.put(THDR, 4, TILES)
    st.put(THDR + 4, 4, TILE_COUNT)
    for t in range(TILE_COUNT):
        r = TILES + t * 0x28
        st.fill(r, 0x28)
        st.put(r + 0xD, 1, pick(rng, [0, 0, 1, 7], [0xFF]))
        attr = rng.randrange(1 << 32)
        for bit, p in ((0x400, 0.4), (0x800, 0.4), (0x1000, 0.4), (0x2000, 0.08), (0x4000, 0.08)):
            attr = (attr | bit) if rng.random() < p else (attr & ~bit)
        st.put(r + 0x18, 4, attr)


def trick_type(rng, favour: list[int]) -> int:
    r = rng.random()
    if r < 0.6:
        return rng.choice(favour)
    return rng.randrange(32) if r < 0.95 else rng.choice([32, 40, 200, 255])


def make_trick(st: State, k: int, ttype: int, x: int | None = None, y: int | None = None) -> int:
    rng = st.rng
    d = DATA(k)
    st.fill(d, 0x20)
    st.put(d, 4, 0)
    st.put(d + 8, 1, (x if x is not None else pick(rng, list(range(0, 32)), [-1, -128, 127, 100], 0.05)) & 0xFF)
    st.put(d + 9, 1, (y if y is not None else pick(rng, list(range(0, 32)), [-1, -128, 127, 100], 0.05)) & 0xFF)
    st.put(d + 10, 1, pick(rng, [1, 1, 1, 2, 3, 4], [0, -1, -5, 12, 127], 0.06) & 0xFF)
    st.put(d + 11, 1, pick(rng, [1, 1, 1, 2, 3, 4], [0, -1, -5, 12, 127], 0.06) & 0xFF)
    st.put(d + 12, 1, ttype & 0xFF)
    st.put(d + 0x15, 1, pick(rng, [1, 2, 4, 8], [0, 3, 16, 255]))
    st.put(d + 0x16, 1, pick(rng, [1, 1, 2, 4, 0, 3], [5, 6, 7, 0x80, 0xFF], 0.15))
    st.put(d + 0x18, 4, TEXTS(k))
    st.put(TEXTS(k), 1, 0)
    return d


def trick_list(st: State, n: int, favour: list[int]) -> list[int]:
    """n gimmicks linked from Trick.first, in list order."""
    datas = [make_trick(st, k, trick_type(st.rng, favour)) for k in range(n)]
    for a, b in zip(datas, datas[1:]):
        st.put(a, 4, b)
    st.put(TRICK, 4, datas[0] if datas else 0)
    st.put(TRICK + 4, 4, n)
    return datas


def rd(st: State, addr: int, n: int) -> int:
    return sum(st.mem.get(addr + i, 0) << (8 * i) for i in range(n))


def sx8(v: int) -> int:
    return v - 256 if v & 0x80 else v


def maybe_flag(st: State, addr: int, mask: int, p: float) -> None:
    v = rd(st, addr, 8)
    st.put(addr, 8, (v | mask) if st.rng.random() < p else (v & ~mask))


def person_blocks(st: State, person: int) -> None:
    """A Person record's flags and number, and a list of loaded Person blocks around that number."""
    rng = st.rng
    st.fill(person, 0x30)
    number = pick(rng, [0, 5, 100, 254, 0x7A00, 0x7A10], [0xFFFF, 0x8000])
    st.put(person + 0x24, 2, number)
    maybe_flag(st, person, rd(st, DL_MASK, 8), 0.2)
    n = pick(rng, [0, 1, 2, 3, 4], [6])
    for k in range(n):
        first = max(0, min(0xFFFF, number + pick(rng, [0, -3, -10, 1, 5, -200], [-0x8000, 0x100])))
        st.fill(BLOCK(k), 0x40)
        st.put(BLOCK(k) + 0x34, 2, first)
        st.put(BLOCK(k) + 4, 2, pick(rng, [0, 1, 4, 11, 20, 255], [0xFFFF]))
        st.put(BLOCK(k) + 7, 1, pick(rng, [0, 1], [0x80, 0xFF]))
        st.put(NODE(k), 4, BLOCK(k))
        st.put(NODE(k) + 4, 4, rng.randrange(1 << 32))
        st.put(NODE(k) + 8, 4, NODE(k + 1) if k + 1 < n else 0)
    st.put(G_PBLOCKS, 4, NODE(0) if n else 0)


def make_unit(st: State, number: int, k: int, p_flag: float = 0.25) -> int:
    """Unit with pool number `number`: flags, state bit 28, Person (+ blocks), class, force."""
    rng = st.rng
    u = UNIT(number)
    st.fill(u, 0x140)
    st.put(u + 0x9C, 4, PERSON(k))
    st.put(u + 0xA0, 4, JOB(k))
    st.put(u + 0xA4, 4, FORCE(k) if rng.random() < 0.95 else 0)
    st.fill(FORCE(k), 0x10)
    st.put(FORCE(k) + 8, 1, pick(rng, [0, 1, 2, 9, 9, 3], [10, 0xFF]))
    st.fill(JOB(k), 0x10)
    flags = rd(st, u + 8, 4)
    st.put(u + 8, 4, (flags | 0x10000000) if rng.random() < 0.5 else (flags & ~0x10000000))
    person_blocks(st, PERSON(k))
    vm = rd(st, VEIN_MASK, 8)
    for base in (u, PERSON(k), JOB(k)):
        maybe_flag(st, base, vm, p_flag)
    return u


def caches(st: State) -> None:
    rng = st.rng
    guard(st, VEIN_GUARD)
    guard(st, DL_GUARD)
    st.put(VEIN_MASK, 8, 1 << rng.randrange(64))
    st.put(DL_MASK, 8, 1 << rng.randrange(64))


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def gen_is_access(rng):
    st = base_state(rng)
    terrain(st)
    d = make_trick(st, 0, trick_type(rng, [11, 11, 9, 10, 9, 10, 25, 26, 27, 29, 29, 12, 28]))
    x0, y0 = sx8(st.mem[d + 8]), sx8(st.mem[d + 9])
    w, h = sx8(st.mem[d + 10]), sx8(st.mem[d + 11])
    inside = rng.random() < 0.5
    x = coord(rng, x0 + (rng.randrange(max(w, 1)) if inside else rng.randrange(-1, max(w, 0) + 2)))
    y = coord(rng, y0 + (rng.randrange(max(h, 1)) if inside else rng.randrange(-1, max(h, 0) + 2)))
    ttype = st.mem[d + 12]
    if 25 <= ttype <= 27 and rng.random() < 0.6:  # the cannon's access tile, worked out here
        side, mx, my = st.mem[d + 0x15], x0 + ((w - 1) >> 1), y0 + ((h - 1) >> 1)
        ax, ay = {1: (x0 - 1, my), 2: (x0 + w, my), 4: (mx, y0 + h), 8: (mx, y0 - 1)}.get(side, (mx, my))
        x, y = coord(rng, ax), coord(rng, ay)
    elif ttype in (9, 10) and rng.random() < 0.7:  # the grown ring's edges and corners
        x = coord(rng, rng.choice([x0 - 1, x0 + w, x0 - 1, x0 + w, x0 - 2, x0 + w + 1, x0]))
        y = coord(rng, rng.choice([y0 - 1, y0 + h, y0 - 1, y0 + h, y0 - 2, y0 + h + 1, y0]))
    return st, "ov:0x00526BA0", [d, x, y, 0], ("call", 0x00526BA0)


def gen_at_access(rng):
    st = base_state(rng)
    terrain(st)
    n = pick(rng, [0, 1, 2, 3, 5, 8, 12], [18, 24])
    datas = trick_list(st, n, [11, 11, 11, 11, 11, 12, 29, 9, 25])
    ttype = pick(rng, [11, 11, 11, 0, 12, 29, 9, 25], [0x10B, 0xFFFFFF0B, 255, 31])
    same = [d for d in datas if st.mem[d + 12] == ttype & 0xFF] or datas
    if datas and rng.random() < 0.85:
        t = rng.choice(same)
        if rng.random() < 0.6:
            st.put(t + 0x16, 1, st.mem[t + 0x16] | 1)
        x = coord(rng, sx8(st.mem[t + 8]) + rng.randrange(max(sx8(st.mem[t + 10]), 1)))
        y = coord(rng, sx8(st.mem[t + 9]) + rng.randrange(max(sx8(st.mem[t + 11]), 1)))
    else:
        x, y = pick(rng, [(-1, -1), (-1, 3), (3, -1), (5, 5)], [(-128, -128), (1000, 3)])
        x, y = s32(x), s32(y)
    return st, "ov:0x004CF5B4", [x, y, ttype, 0], ("call", 0x004CF5B4)


def gen_trick_test(rng):
    st = base_state(rng)
    terrain(st)
    n = pick(rng, [0, 1, 2, 4, 8], [20])
    datas = trick_list(st, n, [11, 11, 12, 12])
    ttype = pick(rng, [11, 12, 0, 11, 12], [0x10C, 0xFFFFFF0B, 200])
    same = [d for d in datas if st.mem[d + 12] == ttype & 0xFF or ttype == 0] or datas
    if datas and rng.random() < 0.85:
        t = rng.choice(same)
        x, y = sx8(st.mem[t + 8]), sx8(st.mem[t + 9])
        x = pick(rng, [x, x, x, -1, x + 1, 0], [-128])
        y = pick(rng, [y, y, y, -1, y - 1, 0], [127])
    else:
        x, y = pick(rng, [(-1, -1), (0, 0), (31, 31), (0, -1), (-1, 0)], [(1000, -0x80000000)])
    mask = pick(rng, [2, 2, 1, 4, 0], [0xFF, 0x100, 0x80000002, 6])
    st.put(SP, 4, mask)
    return st, "ov:0x003B0A44", [rng.randrange(1 << 32), s32(x), s32(y), ttype], ("call", 0x003B0A44)


def gen_download(rng):
    st = base_state(rng)
    caches(st)
    person_blocks(st, PERSON(0))
    return st, "ov:0x0053DFEC", [PERSON(0), 0, 0, 0], ("call", 0x0053DFEC)


def gen_can_vein(rng):
    st = base_state(rng)
    caches(st)
    u = make_unit(st, 1, 0)
    return st, "ov:0x0052DFE8", [u, 0, 0, 0], ("call", 0x0052DFE8)


def gen_script_can(rng):
    st = base_state(rng)
    caches(st)
    for n in (1, 2, 3, 250):
        make_unit(st, n, n % 8)
    number = pick(rng, [1, 2, 3, 250, 1, 2], [0, -1, 4, 249, 251, 255, 0x7FFFFFFF, -0x80000000, 0x10001], 0.2)
    return st, "ov:0x003ABD8C", [rng.randrange(1 << 32), s32(number), 0, 0], ("call", 0x003ABD8C)


def gen_command(rng):
    st = base_state(rng)
    caches(st)
    terrain(st)
    n = pick(rng, [0, 1, 2, 4, 8], [17, 20])
    datas = trick_list(st, n, [11, 11, 11, 12, 29])
    st.fill(MIND, 8)
    index = pick(rng, [1, 2, 3], [0, 200])
    st.put(MIND, 1, index)
    for num in (1, 2, 3):
        u = make_unit(st, num, num, 0.5)
        veins = [d for d in datas if st.mem[d + 12] == 11] or datas
        if datas and rng.random() < 0.8:
            t = rng.choice(veins)
            if rng.random() < 0.6:
                st.put(t + 0x16, 1, st.mem[t + 0x16] | 1)
            st.put(u + 0xF4, 1, (sx8(st.mem[t + 8]) + rng.randrange(-1, max(sx8(st.mem[t + 10]), 1) + 1)) & 0xFF)
            st.put(u + 0xF5, 1, (sx8(st.mem[t + 9]) + rng.randrange(-1, max(sx8(st.mem[t + 11]), 1) + 1)) & 0xFF)
        elif rng.random() < 0.3:
            st.put(u + 0xF4, 1, 0xFF)
            st.put(u + 0xF5, 1, 0xFF)
    return st, "ov:0x0037B138", [rng.randrange(1 << 32), 0, 0, 0], ("call", 0x0037B138)


def positions_text(rng, regions: list[tuple[int, int]]) -> bytes:
    r = rng.random()
    if r < 0.18:
        return rng.choice([b"None", b"All", b"EnableAll", b"DoneAll", b"RuinAll"])
    if r < 0.24:
        return rng.choice([b"", b"Alll", b"none", b",", b",,", b"x", b"-1,-1", b"3", b"300,2", b"99999999999,5",
                           b"4294967301,1", b"2147483648,0", b"1, 2", b"\x81\x82,3,4", b"All "])
    count = pick(rng, [1, 1, 2, 3, 4], [0, 17, 20, 25])
    nums = []
    for _ in range(count):
        if regions and rng.random() < 0.8:
            nums += list(rng.choice(regions))
        else:
            nums += [rng.randrange(-2, 34), rng.randrange(-2, 34)]
    if rng.random() < 0.1:
        nums.append(rng.randrange(32))  # odd count
    parts = [str(v) if v >= 0 or rng.random() < 0.5 else "" for v in nums]
    return ",".join(parts).encode()


def gen_marks(rng):
    st = base_state(rng)
    terrain(st)
    st.zero(MARKS - WINDOW_BEFORE, WINDOW)
    n = pick(rng, [1, 2, 4, 6, 8], [17, 20])
    datas = trick_list(st, n, [12, 12, 12, 12, 11])
    regions = [(sx8(st.mem[d + 8]), sx8(st.mem[d + 9])) for d in datas if st.mem[d + 12] == 12]
    for k, d in enumerate(datas):
        if st.mem[d + 12] == 12 and rng.random() < 0.85:  # keep regions small: the ARM side is slow
            st.put(d + 10, 1, rng.randrange(1, 5))
            st.put(d + 11, 1, rng.randrange(1, 5))
        text = positions_text(rng, regions)
        for i, b in enumerate(text + b"\0"):
            st.put(TEXTS(k) + i, 1, b)
    d = DATA(0)
    st.put(d + 12, 1, pick(rng, [11, 11, 11, 11, 28, 28, 25, 26, 27], [0, 12, 29, 31, 255], 0.15))
    return st, "marks", [d, 0, 0, 0], ("marks", 0x00526D98)


FUNCS = {
    "trick_is_access": gen_is_access,
    "trick_at_access": gen_at_access,
    "script_trick_test": gen_trick_test,
    "person_is_download": gen_download,
    "unit_can_dragon_vein": gen_can_vein,
    "script_unit_can_dragon_vein": gen_script_can,
    "vein_command_attribute": gen_command,
    "trick_preview_marks": gen_marks,
}


# ------------------------------------------------------------------ sharper cases (round 13, F-025)
# Each SHARP generator aims at planted bugs the cases above never told apart (docs/harness/H6_SURVIVORS.md).
# They draw from their own random stream (n // 3 cases each), so the cases of FUNCS stay exactly as they were.

def gen_is_access_types(rng):
    """trick_is_access on the types the cases above seldom build, each on the tile that tells a planted bug
    apart: a type 1..8, 13, 14, 23 or 24 gimmick asked about a tile inside its area (catches `case 24` made
    `case 25`: type 24 then answers "none"), and a type 28 or 29 gimmick (or a cannon, 25..27) asked about the
    tile a cannon of that size and side would be used from (catches the cannon test `type - 25 <= 2` made
    `<= 3`: type 28 then answers by the cannon rule)."""
    st = base_state(rng)
    terrain(st)
    ttype = rng.choice([24, 24, 23, 13, 14, 28, 28, 28, 29, 25, 26, 27, 1, 5, 8])
    x0, y0 = rng.randrange(1, 28), rng.randrange(1, 28)
    d = make_trick(st, 0, ttype, x0, y0)
    w, h = rng.randrange(1, 5), rng.randrange(1, 5)
    st.put(d + 10, 1, w)
    st.put(d + 11, 1, h)
    if ttype >= 25:
        side = rng.choice([1, 2, 4, 8, 0, 3])
        st.put(d + 0x15, 1, side)
        mx, my = x0 + ((w - 1) >> 1), y0 + ((h - 1) >> 1)
        x, y = {1: (x0 - 1, my), 2: (x0 + w, my), 4: (mx, y0 + h), 8: (mx, y0 - 1)}.get(side, (mx, my))
    else:
        x, y = x0 + rng.randrange(w), y0 + rng.randrange(h)
    return st, "ov:0x00526BA0", [d, s32(x), s32(y), 0], ("call", 0x00526BA0)


SHARP = [
    ("trick_is_access", gen_is_access_types),
]


# ------------------------------------------------------------------ the ARM side
def c_string(mem: A.Memory, a: int) -> bytes:
    out = bytearray()
    while len(out) < 0x10000:
        b = mem.read8(a + len(out))
        if b == 0:
            break
        out.append(b)
    return bytes(out)


def arm_run(text: bytes, st: State, args: list[int], how: tuple) -> list[int]:
    """Expected outputs, in the order the C driver prints them: [gave_up, values...]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)
    heap = [HEAP + 0x400]

    def new_array(cpu, a):
        p = heap[0]
        heap[0] += (a[0] + 7) & ~7
        mem.map(p, bytes(a[0]))
        return p

    def memcpy(cpu, a):
        for i in range(a[2]):
            mem.write(a[0] + i, 1, mem.read8(a[1] + i))
        return a[0]

    def memclr(cpu, a):
        for i in range(a[1]):
            mem.write(a[0] + i, 1, 0)
        return a[0]

    def strcmp(cpu, a):
        x, y = c_string(mem, a[0]), c_string(mem, a[1])
        return 0 if x == y else (1 if x > y else s32(-1))

    stubs = {NEW_ARRAY: new_array, DELETE_ARRAY: lambda cpu, a: 0, MEMCPY: memcpy, MEMCLR: memclr,
             STRCMP: strcmp, DEPLOY_CANNON: lambda cpu, a: 0x5A}
    cpu = A.Cpu(mem, stubs, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    try:
        if how[0] == "call":
            cpu.run(how[1], limit=2_000_000)
            return [0, cpu.r[0]]
        if how[0] == "marks":
            cpu.run(how[1], limit=5_000_000)
            cannon = int(any(c[0] == DEPLOY_CANNON for c in cpu.calls))
            out = [0, cannon, 0 if cannon else cpu.r[0]]
            for i in range(WINDOW):
                b = mem.read8(MARKS - WINDOW_BEFORE + i)
                if b:
                    out += [i, b]
            return out
    except A.ColdGuard:
        return [1]
    raise ValueError(how[0])


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/map/tests/vein_diff.py: runs readable dragon vein functions on
   memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "veins.h"

static uint8_t **pages, **nopages;
static uint32_t used[8192]; static int nused;
static uint8_t *at(uint32_t a, int make) {
    uint8_t *p = pages[a >> 12];
    if (!p && make && nused < 8192) { p = pages[a >> 12] = calloc(4096, 1); used[nused++] = a >> 12; }
    return p ? p + (a & 0xFFF) : NULL;
}
static uint8_t r8(Context *c, uint32_t a) { (void)c; uint8_t *p = at(a, 0); return p ? *p : 0; }
static uint16_t r16(Context *c, uint32_t a) { return (uint16_t)(r8(c, a) | r8(c, a + 1) << 8); }
static uint32_t r32(Context *c, uint32_t a) { return (uint32_t)r16(c, a) | (uint32_t)r16(c, a + 2) << 16; }
static int writes;
static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; writes++; uint8_t *p = at(a, 0); if (p) *p = v; }
static void w16(Context *c, uint32_t a, uint16_t v) { w8(c, a, (uint8_t)v); w8(c, a + 1, (uint8_t)(v >> 8)); }
static void w32(Context *c, uint32_t a, uint32_t v) { w16(c, a, (uint16_t)v); w16(c, a + 2, (uint16_t)(v >> 16)); }
static void interp(Context *c, uint32_t a, uint32_t o) { (void)c; (void)a; (void)o; }
static void svc(Context *c, uint32_t n) { (void)c; (void)n; }
static int guest_calls;
static void refuse(Context *ctx) { guest_calls++; ctx->r[0] = 0; ctx->r[15] = ctx->r[14]; }
static Code lookup(Context *c, uint32_t a) { (void)c; (void)a; return refuse; }
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

void override_0x00526BA0(Context *); void override_0x004CF5B4(Context *); void override_0x003B0A44(Context *);
void override_0x0053DFEC(Context *); void override_0x0052DFE8(Context *); void override_0x003ABD8C(Context *);
void override_0x0037B138(Context *);
static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {
    {0x00526BA0u, override_0x00526BA0}, {0x004CF5B4u, override_0x004CF5B4}, {0x003B0A44u, override_0x003B0A44},
    {0x0053DFECu, override_0x0053DFEC}, {0x0052DFE8u, override_0x0052DFE8}, {0x003ABD8Cu, override_0x003ABD8C},
    {0x0037B138u, override_0x0037B138},
};

static int hexval(int ch) { return ch <= '9' ? ch - '0' : (ch | 32) - 'a' + 10; }
static VeinMarks marks;

int main(void) {
    pages = calloc(1u << 20, sizeof *pages);
    nopages = calloc(1u << 20, sizeof *nopages);
    fe_force_mode(FE_MODE_READABLE);
    static char line[1 << 16];
    char kind[64]; unsigned id = 0; uint32_t a[5] = {0};
    while (fgets(line, sizeof line, stdin)) {
        if (!strncmp(line, "case ", 5)) {
            sscanf(line + 5, "%u %63s %x %x %x %x %x", &id, kind, &a[0], &a[1], &a[2], &a[3], &a[4]);
            for (int i = 0; i < nused; i++) { free(pages[used[i]]); pages[used[i]] = NULL; } nused = 0;
            originals = 0; writes = 0; guest_calls = 0;
        } else if (!strncmp(line, "mem ", 4)) {
            uint32_t addr; int off = 0;
            sscanf(line + 4, "%x %n", &addr, &off);
            const char *h = line + 4 + off;
            for (uint32_t i = 0; h[2 * i] && h[2 * i] != '\n' && h[2 * i] != '\r'; i++)
                *at(addr + i, 1) = (uint8_t)(hexval(h[2 * i]) << 4 | hexval(h[2 * i + 1]));
        } else if (!strncmp(line, "run", 3)) {
            Context c = fresh();
            c.r[13] = a[4];
            if (!strncmp(kind, "ov:", 3)) {
                uint32_t addr = (uint32_t)strtoul(kind + 3, NULL, 16);
                for (int i = 0; i < 4; i++) c.r[i] = a[i];
                for (unsigned i = 0; i < sizeof ovs / sizeof ovs[0]; i++) if (ovs[i].a == addr) ovs[i].f(&c);
                if (originals) printf("%u 1\n", id); else printf("%u 0 %u\n", id, c.r[0]);
            } else if (!strcmp(kind, "marks")) {
                trick_preview_marks(&c, a[0], &marks);
                if (fe_gave_up(&c)) printf("%u 1\n", id);
                else {
                    int cannon = marks.kind == VEIN_MARKS_CANNON;
                    printf("%u 0 %d %u", id, cannon, cannon ? 0u : marks.result);
                    for (int i = 0; i < VEIN_MARKS_BYTES; i++) if (marks.bytes[i]) printf(" %d %u", i, marks.bytes[i]);
                    printf("\n");
                }
            }
            if (writes) printf("%u WROTE-GUEST %d\n", id, writes);
            if (guest_calls) printf("%u GUEST-CALL %d\n", id, guest_calls);
        }
    }
    return 0;
}
'''


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


def build_driver(cc: str, out: str, map_dir: str) -> str:
    """Builds the driver with every source of src/readable/, the map folder's taken from map_dir."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "vein_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(DRIVER)
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)) == os.path.normcase(SRC_MAP):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(map_dir, f) for f in os.listdir(map_dir) if f.endswith(".c")]
    exe = os.path.join(out, "vein_driver.exe" if os.name == "nt" else "vein_driver")
    inc = ["-I", map_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"vein_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines: list[str] = []
    expected: dict[int, tuple[str, list[int], tuple]] = {}
    cid = 0
    # round 13 (F-025): SHARP's cases come from their own random stream, so the cases of FUNCS stay as they were
    sharp_rng = random.Random(seed ^ 0x5EED13)
    jobs = [(name, gen, n, rng) for name, gen in FUNCS.items()] +         [(name, gen, max(1, n // 3), sharp_rng) for name, gen in SHARP]
    for name, gen, count, gen_rng in jobs:
        if only and name != only:
            continue
        for _ in range(count):
            st, kind, args, how = gen(gen_rng)
            exp = arm_run(text, st, args, how)
            expected[cid] = (name, exp, (kind, args))
            lines.append(f"case {cid} {kind} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
            for addr, data in st.regions():
                for off in range(0, len(data), 4096):
                    lines.append(f"mem {addr + off:x} {data[off:off + 4096].hex()}")
            lines.append("run")
            cid += 1
    return lines, expected


def compare(exe: str, cc: str, lines: list[str], expected: dict, show: int, quiet: bool = False):
    log = os.path.join(os.path.dirname(exe), "fe_readable.log")
    env = dict(os.environ, FE_READABLE_LOG=log, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"vein_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list[int]] = {}
    bad_side: dict[int, str] = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "GUEST-CALL"):
            bad_side[int(parts[0])] = parts[1].lower()
        elif parts:
            got[int(parts[0])] = [int(x) for x in parts[1:]]
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs) in expected.items():
        res = per.setdefault(name, [0, 0, 0])  # cases, mismatches, gave-up cases
        res[0] += 1
        g = got.get(c)
        if exp[0] == 1:
            res[2] += 1
        if g is None or g != exp or c in bad_side:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({bad_side[c]})" if c in bad_side else ""
                print(f"  MISMATCH {name} case {c}: original {exp[:24]}, readable {None if g is None else g[:24]}{why}; "
                      f"{inputs[0]} " + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
PLANTS = [
    ("vein_tricks.c", "        return x - 1;", "        return x;"),
    ("vein_tricks.c", "*ay = READ_FIELD(ctx, TrickData, data, y) - 1;", "*ay = READ_FIELD(ctx, TrickData, data, y) + 1;"),
    ("vein_tricks.c", "return x0 <= x && x <= x0 + w - 1", "return x0 <= x && x <= x0 + w"),
    ("vein_tricks.c", "    case 9: case 10:\n        if", "    case 9:\n        if"),
    ("vein_tricks.c", "return y != y0 - 1 && y != y0 + h;", "return 1;"),
    ("vein_tricks.c", "change_to[0]) != 0;", "change_to[1]) != 0;"),
    ("vein_tricks.c", "(uint32_t)x | (uint32_t)y << 5), change_to", "(uint32_t)y | (uint32_t)x << 5), change_to"),
    ("vein_tricks.c", "if (type - 25u <= 2u) {", "if (type - 25u <= 1u) {"),
    ("vein_tricks.c", "} else if (!(x < 0 && y < 0) &&", "} else if (!(x < 0 || y < 0) &&"),
    ("vein_tricks.c", "if (mask != 0 && (READ_FIELD(ctx, TrickData, d, state) & mask) == 0)",
     "if ((READ_FIELD(ctx, TrickData, d, state) & mask) == 0)"),
    ("vein_tricks.c", "    type &= 0xFFu;\n", ""),
    ("vein_tricks.c", "if (y >= 0 && READ_FIELD(ctx, TrickData, d, y) != y)", "if (y > 0 && READ_FIELD(ctx, TrickData, d, y) != y)"),
    ("vein_tricks.c", "return trick_find(ctx, TRICK_SEARCH_ACCESS, x, y, type, TRICK_USABLE);",
     "return trick_find(ctx, TRICK_SEARCH_ACCESS, x, y, type, TRICK_DONE);"),
    ("vein_tricks.c", "& mask) != 0;\n}", "& mask) == mask;\n}"),
    ("vein_units.c", "if (!fe_static_ready(ctx, S_DownloadGuard))", "if (0)"),
    ("vein_units.c", "return first <= number && number < first +", "return first <= number && number <= first +"),
    ("vein_units.c", "        return node != head;", "        return 1;"),
    ("vein_units.c", "        if (READ_FIELD(ctx, PersonBlock, block, flag_07) == 0)\n            return 0;\n", ""),
    ("vein_units.c", "& UNIT_STATE_VEIN_DOWNLOAD_ONLY) == 0)", "& 0x08000000u) == 0)"),
    ("vein_units.c", "READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), flags);",
     "0;"),
    ("vein_units.c", "if (number <= 0 || number > 250)", "if (number <= 0 || number >= 250)"),
    ("vein_units.c", "units + (number - 1u) * (gaddr)sizeof(Unit);", "units + number * (gaddr)sizeof(Unit);"),
    ("vein_units.c", "type) == FORCE_TYPE_NO_VEIN)", "type) == 8u)"),
    ("vein_units.c", "return vein != 0 ? MENU_ATTR_SHOWN : MENU_ATTR_HIDDEN;", "return vein != 0 ? MENU_ATTR_SHOWN : 2u;"),
    ("vein_units.c", "READ_FIELD(ctx, Unit, unit, map_x), READ_FIELD(ctx, Unit, unit, map_y),",
     "READ_FIELD(ctx, Unit, unit, map_y), READ_FIELD(ctx, Unit, unit, map_x),"),
    ("vein_effect.c", "if (text_is(ctx, text, \"DoneAll\"))\n        return TRICK_DONE;",
     "if (text_is(ctx, text, \"DoneAll\"))\n        return TRICK_RUINED;"),
    ("vein_effect.c", "            if (number < 0)\n                number = 0;\n", ""),
    ("vein_effect.c", "            values++;\n            number = -1;", "            values++;\n            number = 0;"),
    ("vein_effect.c", "((attributes & TERRAIN_CHANGES_WHEN_DONE) && (state & TRICK_DONE))",
     "((attributes & TERRAIN_CHANGES_WHEN_DONE) && (state & TRICK_USABLE))"),
    ("vein_effect.c", "y2 < READ_FIELD(ctx, MapImage, image, play_y_end); y2++)", "y2 <= READ_FIELD(ctx, MapImage, image, play_y_end); y2++)"),
    ("vein_effect.c", "mark(ctx, out, (uint32_t)x2 | (uint32_t)ty << 5);", "mark(ctx, out, (uint32_t)x2 | (uint32_t)(ty + 1) << 5);"),
    ("vein_effect.c", "int32_t tx = pos.x[i] + col, ty = pos.y[i] + row;",
     "int32_t tx = READ_FIELD(ctx, TrickData, region, x) + col, ty = READ_FIELD(ctx, TrickData, region, y) + row;"),
    ("vein_effect.c", "int32_t at = fe_asr((int32_t)tile, 3) + VEIN_MARKS_BEFORE;", "int32_t at = (int32_t)(tile >> 3) + VEIN_MARKS_BEFORE;"),
    ("vein_effect.c", "if (!fe_gave_up(ctx) && pos.count >= 1) {", "if (!fe_gave_up(ctx) && pos.count >= 2) {"),
    ("vein_effect.c", "trick_find(ctx, TRICK_SEARCH_AT, pos.x[i], pos.y[i], TRICK_TYPE_VEIN_REGION, 0);",
     "trick_find(ctx, TRICK_SEARCH_AT, pos.x[i], pos.y[i], TRICK_TYPE_VEIN_REGION, TRICK_USABLE);"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_MAP, d, ignore=shutil.ignore_patterns("tests"))
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
              + (f"caught, {bad} mismatches in {', '.join(hit)}" if bad else "NOT CAUGHT"))
        missed += 0 if bad else 1
    return missed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=400, help="cases per function (default 400)")
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, default=150, help="cases per function for each planted bug")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("vein_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("vein_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_MAP)
    lines, expected = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = 0
    print(f"vein_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold) in per.items():
        total_bad += bad
        print(f"  {name:28s} {n:5d} cases  {bad:3d} mismatches  ({cold} with a cold cache: original reached "
              f"the guard, readable gave up)" if cold else f"  {name:28s} {n:5d} cases  {bad:3d} mismatches")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"vein_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"vein_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
