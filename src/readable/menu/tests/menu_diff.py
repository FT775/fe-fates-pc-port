#!/usr/bin/env python3
"""Host differential test of the menu / panel readable code against the game's own ARM code.

    python src/readable/menu/tests/menu_diff.py             all functions, 300 cases each
    python src/readable/menu/tests/menu_diff.py -n 2000     more cases
    python src/readable/menu/tests/menu_diff.py --seed 7    another random sequence
    python src/readable/menu/tests/menu_diff.py --only config_is_detail_battle
    python src/readable/menu/tests/menu_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/skill/tests/skill_diff.py (and the ARM interpreter
src/readable/battle/tests/arm_mini.py): for every readable function of src/readable/menu/ the
test makes up guest states (a GameConfigData object, the Pad, the map Situation, units with their
Person, Job and force, the one-time caches, option items, a danger image with Deploy's two tile
sets, a map image with its tile grid, a battle sequence, a map actor; all random test values,
never game data, and on purpose often outside the ranges the game uses: option bytes past their
last value, army types past 3, bools that are not 0/1, tile coordinates past 31 or negative,
unmapped and "torn" units, a missing map Situation), runs the ORIGINAL ARM code from the owner's
extracted/text.bin in arm_mini.py and the readable C function (built with the host gcc against
tools/readable/stub/) on the same memory, and compares:

  - overrides (16): r0, the number of bytes read from unmapped memory (tier 2 compares that
    count) AND the list of guest calls, in order, with their argument registers (F-018). On the
    ARM side every BL/BLX to a listed callee is listed (also inside callees that run as ARM
    code); on the C side every guest call is listed (one that reaches a readable override of
    this batch, or Force::IsAllied's, runs that override, as in the capture library).
  - give-ups: a one-time cache that is not filled must make the original reach the guard routine
    and the readable code give up before reading anything; a NESTED give-up (a guest call of
    another readable function that gives up inside while the outer one goes on) is a mismatch.
  - helpers, each against the game's own code:
      config_saved_record     the whole of GameConfigData::Serialize, Stream::WriteByte /
                              WriteLong stubbed: the ordered list of values written
      battle_picture_choice   the ProcSequence constructor from 0x0035D8A0 to 0x0035D96C: the
                              flags word it leaves, unmapped reads, the guest calls
      actor_hp_bar_shown      map::Actor::Tick from 0x0038D408 to 0x0038D44C: the bit it computes
      danger_update_targets   the whole of map::Image::Danger::Update, Danger::Add and the
                              clearing / cannon-enumerator calls stubbed: the units passed to Add
                              in order, the flag word after, unmapped reads, the guest calls
      danger_add_preview      Danger::Add from 0x0038F30C to 0x0038F330 (the move-search flags)
                              and from 0x0038F6F8 to its end (the OR into the four sets): the
                              flags, the sets it touched, the flag word, unmapped reads
      danger_tile_kind        map::Panel::Danger::SetVertex from 0x00390F9C (the option test)
                              and from 0x00391008 to the three places a tile goes (first colour,
                              second colour, not drawn)

Guest functions answered by one table on both sides: VertexBuffer::GetSize, Force::Get,
Terrain::Get, an option item's virtual GetMask. Everything else runs as ARM code: the guard
routine's callers, Force::IsAllied, Unit::IsDetailBattleMust / NotAllow, GameConfigData::
IsDetailBattle / IsDetailSupport (called by the battle-picture decision).

--plant copies src/readable/menu/ to build/readable/menu/plant/, makes one small wrong change at a
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
OUT = os.path.join(ROOT, "build", "readable", "menu")
SRC_MENU = os.path.join(ROOT, "src", "readable", "menu")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
GET_SIZE, FORCE_GET, TERRAIN_GET = 0x0013082C, 0x004F630C, 0x004E0AFC
FAKE_MASKS = (0x0BAD1000, 0x0BAD1004)  # the option item's virtual GetMask (made-up class tables)
IS_ALLIED, MUST, NOT_ALLOW, DETAIL_BATTLE, DETAIL_SUPPORT = 0x0053C3E0, 0x00530884, 0x00531BA8, 0x0050AAA0, 0x0050AC04
WRITE_BYTE, WRITE_LONG = 0x0044C3DC, 0x0044C41C
SERIALIZE = 0x0050AEA0
UPDATE, ADD, MEMSET = 0x0038F834, 0x0038F304, 0x00301148
ENUM_CTOR, ENUM_RUN, ENUM_DTOR = 0x00399C70, 0x00399AB0, 0x00399CA4
LEAF_STUBS = {GET_SIZE: 1, FORCE_GET: 1, TERRAIN_GET: 1, FAKE_MASKS[0]: 1, FAKE_MASKS[1]: 1}

OVERRIDES = {  # name -> address
    "config_danger_value": 0x003BAEEC, "config_hp_gauge_value": 0x003BC508, "config_battle_value": 0x003BC358,
    "config_game_speed_value": 0x003BC954, "config_ai_skip_value": 0x003BC130, "config_distance_value": 0x003BC628,
    "config_encounter_bgm_value": 0x003BAD1C, "config_item_value": 0x003BA88C,
    "config_is_speed_fast": 0x0050AA68, "config_is_skip_input": 0x0050AA4C, "config_info_capability": 0x0050AE40,
    "config_is_detail_battle": DETAIL_BATTLE, "config_is_detail_support": DETAIL_SUPPORT,
    "unit_is_detail_battle_must": MUST, "unit_is_detail_battle_not_allow": NOT_ALLOW,
    "danger_panel_is_hide": 0x005264C4,
}
# the callees listed on both sides, with the argument registers compared
ARITY = {GET_SIZE: 1, FORCE_GET: 1, TERRAIN_GET: 1, FAKE_MASKS[0]: 1, FAKE_MASKS[1]: 1, IS_ALLIED: 2, MUST: 1,
         NOT_ALLOW: 1, DETAIL_BATTLE: 4, DETAIL_SUPPORT: 4}

# globals and caches (config/readable/globals.csv, src/readable/menu/menus.h)
G_CONFIG, G_PAD, G_SITUATION, G_MAPIMAGE, G_DEPLOY = 0x006DA0F8, 0x006BD96C, 0x006D7ED0, 0x006D73E8, 0x006D7364
SUPPORT_GUARD, SUPPORT_MASK = 0x006DA0FC, 0x006DA130
MUST_GUARDS, MUST_MASKS = (0x006D97E0, 0x006D97DC), (0x006D9AD0, 0x006D9AD8)
NOT_GUARD, NOT_MASK = 0x006D97E4, 0x006D9AE0
GUARDS = (SUPPORT_GUARD,) + MUST_GUARDS + (NOT_GUARD,)
MASKS = (SUPPORT_MASK,) + MUST_MASKS + (NOT_MASK,)

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x400  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
FORCE = lambda k: 0x08030000 + k * 0x10  # noqa: E731 (a unit's own force record)
ARMY = lambda t: 0x08040000 + t * 0x10  # noqa: E731 (what Force::Get answers for army t)
CFG, CFG2 = 0x08100000, 0x08100100
PAD = 0x08110000
SIT = 0x08120000
ITEM, VTABLE, BGMLIST = 0x08130000, 0x08131000, 0x08132000
PANEL, VBUF = 0x08140000, 0x08141000
SEQ = 0x08150000
ACTOR = 0x08160000
IMG = 0x08170000                            # a danger image (DangerImage, 0x204 bytes)
DEPLOY, ZONE_A, ZONE_B = 0x08180000, 0x08181000, 0x08182000
MAP = 0x08200000                            # a map image: draw_terrain +0x408, danger +0x1008
TERRAIN = lambda k: 0x08300000 + k * 0x28  # noqa: E731
STREAM = 0x0BAD2000
NUNITS = 10
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]


def s8(rng, common, rare=(), p=0.1) -> int:
    return pick(rng, common, rare, p) & 0xFF


def guard(st, addr: int, cold_p: float = 0.04) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def flag64(st, addr: int, mask_addr: int, p: float) -> None:
    mask = int.from_bytes(bytes(st.mem.get(mask_addr + i, 0) for i in range(8)), "little")
    v = int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(8)), "little")
    st.put(addr, 8, (v | mask) if st.rng.random() < p else (v & ~mask))


def word(st, addr: int) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(4)), "little")


def make_config(st, base: int) -> None:
    rng = st.rng
    st.fill(base, 0x40)
    bits = rng.randrange(1 << 32)
    for b in (1, 29, 30):  # the bits the readers test, each on half the time
        bits = bits | (1 << b) if rng.random() < 0.5 else bits & ~(1 << b)
    st.put(base + 4, 4, bits)
    st.put(base + 0x8, 1, s8(rng, [0, 1, 2, 3, 4], [5, 6, 255, 128], 0.12))
    st.put(base + 0xC, 1, s8(rng, [0, 1, 2], [3, 255], 0.12))
    st.put(base + 0xE, 1, s8(rng, [0, 1, 2], [3, 255, 4], 0.12))
    st.put(base + 0x16, 1, s8(rng, [0, 1], [2, 255], 0.12))


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.put(G_CONFIG, 4, CFG)
    make_config(st, CFG)
    make_config(st, CFG2)
    st.put(G_PAD, 4, PAD if rng.random() > 0.06 else rng.choice(UNMAPPED))
    st.fill(PAD, 0x20)
    for off in (0xC, 0x14):  # held, pressed: the bits the readers test, each on half the time
        v = rng.randrange(1 << 32)
        for b in (0, 1, 3, 9, 10):
            v = v | (1 << b) if rng.random() < 0.5 else v & ~(1 << b)
        st.put(PAD + off, 4, v)
    st.put(G_SITUATION, 4, SIT if rng.random() > 0.08 else 0)
    st.fill(SIT, 0x40)
    for t in range(32):
        st.put(SIT + t, 1, s8(rng, [0, 1, 1], [2, 255]) if t != 4 and t not in (5, 6, 7) else st.mem[SIT + t])
    st.put(SIT + 4, 4, (word(st, SIT + 4) | 1) if rng.random() < 0.3 else (word(st, SIT + 4) & ~1))
    st.put(SIT + 8, 1, s8(rng, [0, 1, 2, 3], [4, 9, 31, 200], 0.15))
    st.put(SIT + 9, 1, s8(rng, [0, 1, 2, 3], [4, 255], 0.1))
    for g in GUARDS:
        guard(st, g)
    for m in MASKS:
        st.put(m, 8, 1 << rng.randrange(64))
    return st


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
    st.put(FORCE(k) + 8, 1, s8(rng, [0, 1, 2, 3], [9, 255, 4], 0.1))
    state = rng.randrange(1 << 32)
    for b, pr in ((2, 0.2), (14, 0.1), (16, 0.4), (17, 0.1), (31, 0.5)):
        state = state | (1 << b) if rng.random() < pr else state & ~(1 << b)
    st.put(u + 8, 4, state)
    st.put(u + 0x14, 4, 0)
    for base in (u, p, j):
        for m in MASKS:
            flag64(st, base, m, 0.1)
    return u


def all_units(st, n: int = NUNITS) -> list[int]:
    return [make_unit(st, k) for k in range(n)]


TORN_END = 0x080F1000  # a page nothing else uses: a torn unit ends right before it


def torn_unit(st, source: int) -> int:
    """a copy of a unit whose record stops (unmapped from there on) at an offset the readers
    read: shows a read the game does not make (or skips) as a fault count"""
    if getattr(st, "torn", None) is not None:
        return st.torn
    cut = st.rng.choice([0x8, 0x9C, 0xA0, 0xA4])
    base = TORN_END - cut
    for i in range(cut):
        st.mem[base + i] = st.mem.get(source + i, 0)
    st.torn = base
    return base


def unit_arg(st, units: list[int], null_p: float = 0.1, unmapped_p: float = 0.08, torn_p: float = 0.08) -> int:
    r = st.rng.random()
    if r < null_p:
        return 0
    if r < null_p + unmapped_p:
        return st.rng.choice(UNMAPPED)
    if r < null_p + unmapped_p + torn_p:
        return torn_unit(st, st.rng.choice(units))
    return st.rng.choice(units)


def flip_arg(rng) -> int:
    return pick(rng, [0, 1], [2, 0x100, 0xFFFFFFFF], 0.12)


def colder(st, guards, p: float = 0.1) -> None:
    for g in guards:
        if st.rng.random() < p:
            st.put(g, 4, 0)


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def ov(name, args):
    a = OVERRIDES[name]
    return f"ov:0x{a:08X}", args + [0] * (4 - len(args)), ("call", a)


def gen_value(name):
    def gen(rng):
        st = base_state(rng)
        if rng.random() < 0.06:
            st.put(G_CONFIG, 4, rng.choice(UNMAPPED))
        return (st,) + ov(name, [rng.choice([ITEM, 0, 0x12345678])])
    return gen


def gen_bgm(rng):
    st = base_state(rng)
    st.fill(ITEM, 0x60)
    n = pick(rng, [0, 1, 2, 3, 5, 8, 16], [-1, -5, -0x80000000, 20], 0.15)
    st.put(ITEM + 0x4C, 4, n & 0xFFFFFFFF)
    st.put(ITEM + 0x50, 4, BGMLIST if rng.random() > 0.05 else rng.choice(UNMAPPED))
    values = [pick(rng, list(range(12)), [255, 0x100, 0xFFFFFFFF]) & 0xFFFFFFFF for _ in range(16)]
    for i, v in enumerate(values):
        st.put(BGMLIST + 4 * i, 4, v)
    if rng.random() < 0.6 and 0 < n <= 16:
        st.put(CFG + 0x14, 1, values[rng.randrange(n)] & 0xFF)
    return (st,) + ov("config_encounter_bgm_value", [ITEM])


def gen_item(rng):
    st = base_state(rng)
    st.fill(ITEM, 0x20)
    st.put(ITEM, 4, VTABLE)
    st.fill(VTABLE, 0x100)
    fake = rng.choice(FAKE_MASKS)
    st.put(VTABLE + 0x80, 4, fake)
    st.oracle[(fake, ITEM)] = pick(rng, [1, 2, 0x10, 0x20, 0x40, 0x10000, 0x20000000], [0, 0xFFFFFFFF, 0x80000000])
    if rng.random() < 0.06:
        st.put(G_CONFIG, 4, rng.choice(UNMAPPED))
    return (st,) + ov("config_item_value", [ITEM])


def gen_config_reader(name):
    def gen(rng):
        st = base_state(rng)
        cfg = rng.choice([CFG, CFG2]) if rng.random() > 0.06 else rng.choice(UNMAPPED)
        return (st,) + ov(name, [cfg])
    return gen


def gen_detail(name):
    def gen(rng):
        st = base_state(rng)
        units = all_units(st, 4)
        colder(st, GUARDS, 0.04)
        a, b = unit_arg(st, units), unit_arg(st, units)
        cfg = rng.choice([CFG, CFG2]) if rng.random() > 0.05 else rng.choice(UNMAPPED)
        r = rng.random()
        if r < 0.35 and cfg in (CFG, CFG2):  # option 4 (state bit 31) with the two units differing:
            st.put(cfg + 0x8, 1, 4)          # one says "picture", the other "map"
            for u, bit in ((a, rng.randrange(2)), (b, None)):
                if UNIT(0) <= u < UNIT(NUNITS):
                    v = word(st, u + 8)
                    bit = bit if bit is not None else 1 - (word(st, a + 8) >> 31 if UNIT(0) <= a < UNIT(NUNITS) else 0)
                    st.put(u + 8, 4, (v | 0x80000000) if bit else (v & 0x7FFFFFFF))
        elif r < 0.5 and cfg in (CFG, CFG2):  # option values past 4 (5 most often): "map"
            st.put(cfg + 0x8, 1, rng.choice([5, 5, 5, 6, 255]))
        return (st,) + ov(name, [cfg, a, b, flip_arg(rng)])
    return gen


def gen_unit_flag(name, guards):
    def gen(rng):
        st = base_state(rng)
        units = all_units(st, 3)
        colder(st, guards)
        return (st,) + ov(name, [unit_arg(st, units, null_p=0.04)])
    return gen


def gen_hide(rng):
    st = base_state(rng)
    st.fill(PANEL, 0x20)
    st.put(PANEL, 4, VBUF if rng.random() > 0.1 else rng.choice([0, VBUF + 0x40]))
    for v in (VBUF, VBUF + 0x40, 0):
        st.oracle[(GET_SIZE, v)] = pick(rng, [0, 0, 1, 6, 96], [0xFFFFFFFF, 0x80000000])
    panel = PANEL if rng.random() > 0.06 else rng.choice(UNMAPPED)
    return (st,) + ov("danger_panel_is_hide", [panel])


def gen_saved(rng):
    st = base_state(rng)
    cfg = rng.choice([CFG, CFG2]) if rng.random() > 0.06 else rng.choice(UNMAPPED)
    return st, "saved", [cfg, STREAM, 0, 0], ("saved", SERIALIZE)


def gen_picture(rng):
    st = base_state(rng)
    units = all_units(st, 4)
    colder(st, GUARDS, 0.02)
    st.fill(SEQ, 0x290)
    st.put(SEQ + 0x25C, 4, 0 if rng.random() < 0.85 else rng.choice([1, 0x100, 0xFFFFFFFF]))
    f = rng.randrange(1 << 32)
    f = f | 2 if rng.random() < 0.15 else f & ~2
    f = f | 4 if rng.random() < 0.4 else f & ~4
    st.put(SEQ + 0x280, 4, f)
    st.put(SEQ + 0x270, 4, unit_arg(st, units))
    st.put(SEQ + 0x274, 4, unit_arg(st, units))
    return st, "picture", [SEQ, 0, 0, 0], ("picture", 0x0035D8A0)


def gen_hpbar(rng):
    st = base_state(rng)
    units = all_units(st, 3)
    st.fill(ACTOR, 0x40)
    st.put(ACTOR + 0x34, 4, unit_arg(st, units, null_p=0.03))
    actor = ACTOR if rng.random() > 0.05 else rng.choice(UNMAPPED)
    return st, "hpbar", [actor, 0, 0, 0], ("hpbar", 0x0038D408)


def gen_update(rng):
    st = base_state(rng)
    units = all_units(st)
    order = units[:]
    rng.shuffle(order)
    lists, i = [], 0
    for t in range(3):  # three armies, 0 .. 5 units each, one list per army
        n = rng.randrange(0, 6)
        lists.append(order[i:i + n])
        i += n
    for t, members in enumerate(lists):
        st.fill(ARMY(t), 0x10)
        st.put(ARMY(t), 4, members[0] if members else 0)
        for k, u in enumerate(members):
            st.put(u + 0x14, 4, members[k + 1] if k + 1 < len(members) else 0)
        st.oracle[(FORCE_GET, t)] = ARMY(t) if rng.random() > 0.04 else rng.choice(UNMAPPED)
    st.fill(IMG, 0x204)
    fl = rng.randrange(1 << 32)
    st.put(IMG + 0x200, 4, fl | 1 if rng.random() < 0.4 else fl & ~1)
    return st, "dupdate", [IMG, 0, 0, 0], ("dupdate", UPDATE)


def gen_add(rng):
    st = base_state(rng)
    units = all_units(st, 3)
    st.fill(IMG, 0x204)
    st.put(G_DEPLOY, 4, DEPLOY)
    st.fill(DEPLOY, 0x820)
    st.put(DEPLOY + 0x810, 4, ZONE_A if rng.random() > 0.06 else rng.choice(UNMAPPED))
    st.put(DEPLOY + 0x814, 4, ZONE_B if rng.random() > 0.06 else rng.choice(UNMAPPED))
    for z in (ZONE_A, ZONE_B):
        for i in range(128):
            st.put(z + i, 1, rng.randrange(256) if rng.random() < 0.3 else 0)
    unit = unit_arg(st, units, null_p=0.0, unmapped_p=0.05, torn_p=0.0)
    return st, "dadd", [IMG, unit, 0, 0], ("dadd", ADD)


def gen_tile(rng):
    st = base_state(rng)
    st.put(G_MAPIMAGE, 4, MAP)
    for i in range(0x400):
        st.put(MAP + 0x408 + i, 1, rng.randrange(12))
    dense = rng.random() < 0.5  # half the cases: most tiles in both drawn sets (which colour wins)
    for i in range(0x204):
        st.put(MAP + 0x1008 + i, 1, rng.randrange(256) | (0xF0 if dense else 0) if dense or rng.random() < 0.4 else 0)
    if rng.random() < 0.7:  # the option says "drawn" most of the time
        st.put(CFG + 0xE, 1, rng.choice([0, 2]))
    for k in range(12):
        t = TERRAIN(k)
        st.fill(t, 0x28)
        st.put(t + 0x10, 1, 0 if rng.random() < 0.2 else rng.randrange(1, 256))
        v = word(st, t + 0x18)
        st.put(t + 0x18, 4, v | 8 if rng.random() < 0.2 else v & ~8)
        st.oracle[(TERRAIN_GET, k)] = t if rng.random() > 0.05 else rng.choice(UNMAPPED)
    x = pick(rng, list(range(32)), [32, 33, 40, 47, 63, 255, -1], 0.3)  # past 31: x | y << 5 is not x + y * 32
    y = pick(rng, list(range(32)), [32, 40, 255, -1], 0.1)
    return st, "dtile", [x & 0xFFFFFFFF, y & 0xFFFFFFFF, 0, 0], ("dtile", 0x00390F9C)


FUNCS = {
    "config_danger_value": gen_value("config_danger_value"),
    "config_hp_gauge_value": gen_value("config_hp_gauge_value"),
    "config_battle_value": gen_value("config_battle_value"),
    "config_game_speed_value": gen_value("config_game_speed_value"),
    "config_ai_skip_value": gen_value("config_ai_skip_value"),
    "config_distance_value": gen_value("config_distance_value"),
    "config_encounter_bgm_value": gen_bgm,
    "config_item_value": gen_item,
    "config_is_speed_fast": gen_config_reader("config_is_speed_fast"),
    "config_is_skip_input": gen_config_reader("config_is_skip_input"),
    "config_info_capability": gen_config_reader("config_info_capability"),
    "config_is_detail_battle": gen_detail("config_is_detail_battle"),
    "config_is_detail_support": gen_detail("config_is_detail_support"),
    "unit_is_detail_battle_must": gen_unit_flag("unit_is_detail_battle_must", MUST_GUARDS),
    "unit_is_detail_battle_not_allow": gen_unit_flag("unit_is_detail_battle_not_allow", (NOT_GUARD,)),
    "danger_panel_is_hide": gen_hide,
    "config_saved_record": gen_saved,
    "battle_picture_choice": gen_picture,
    "actor_hp_bar_shown": gen_hpbar,
    "danger_update_targets": gen_update,
    "danger_add_preview": gen_add,
    "danger_tile_kind": gen_tile,
}


# ------------------------------------------------------------------ sharper cases (round 11, F-025)
# Planted bugs (H6 survivors) that no case above reached; docs/harness/H6_SURVIVORS.md. make_cases runs SHARP
# from its own random stream (n // 3 cases each), so the cases of FUNCS stay exactly as they were.

def gen_detail_plain(name):
    """battle_mode 2 or 3 with the map's byte 1 and no "always" / "never" PersonFlag anywhere (the four masks
    0): the option's own answer is what comes back, so an answer of 2 for 1 shows"""
    def gen(rng):
        st = base_state(rng)
        units = all_units(st, 4)
        for m in MASKS:
            st.put(m, 8, 0)
        cfg = rng.choice([CFG, CFG2])
        st.put(cfg + 0x8, 1, rng.choice([2, 3]))
        st.put(cfg + 4, 4, word(st, cfg + 4) | 2 if rng.random() < 0.8 else word(st, cfg + 4) & ~2)
        st.put(G_SITUATION, 4, SIT)
        for t in list(range(4)) + list(range(9, 32)):
            st.put(SIT + t, 1, 1 if rng.random() < 0.85 else 0)
        st.put(SIT + 8, 1, rng.choice([0, 1, 2, 3]))
        a, b = rng.choice(units), rng.choice(units + [0])
        if rng.random() < 0.3:
            a, b = b, a
        return (st,) + ov(name, [cfg, a, b, flip_arg(rng)])
    return gen


def gen_bgm_sharp(rng):
    """the battle-music reader with no list (count 0 or below) and the config pointer unmapped: a reader that
    goes on to the config without a list shows as an unmapped read"""
    st = base_state(rng)
    st.fill(ITEM, 0x60)
    st.put(ITEM + 0x4C, 4, rng.choice([0, 0, 0, -1, -0x80000000, 1, 3]) & 0xFFFFFFFF)
    st.put(ITEM + 0x50, 4, BGMLIST if rng.random() < 0.7 else rng.choice(UNMAPPED))
    for i in range(16):
        st.put(BGMLIST + 4 * i, 4, rng.randrange(12))
    st.put(G_CONFIG, 4, rng.choice(UNMAPPED) if rng.random() < 0.8 else CFG)
    return (st,) + ov("config_encounter_bgm_value", [ITEM])


def gen_detail_tiny(name):
    """unit arguments of 0 and 1 only, the caches often cold: "no unit" must be a test against 0 (the
    original asks the caches as soon as one unit is not 0, and gives up when one is cold)"""
    def gen(rng):
        st = base_state(rng)
        all_units(st, 2)
        colder(st, GUARDS, 0.5)
        a, b = rng.choice([(1, 0), (0, 1), (1, 1), (0, 0), (1, 0), (0, 1)])
        return (st,) + ov(name, [rng.choice([CFG, CFG2]), a, b, flip_arg(rng)])
    return gen


SHARP = [
    ("config_is_detail_battle", gen_detail_plain("config_is_detail_battle")),
    ("config_is_detail_support", gen_detail_plain("config_is_detail_support")),
    ("config_encounter_bgm_value", gen_bgm_sharp),
    ("config_is_detail_battle", gen_detail_tiny("config_is_detail_battle")),
    ("config_is_detail_support", gen_detail_tiny("config_is_detail_support")),
]


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY (stubbed or run as ARM code)
    with its argument registers; VFP loads (vldr, no effect on the integer registers) are
    skipped, for the SetVertex region."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.listed.append(call_text(target, self.r[:ARITY[target]]))
        return super().call(target, ret)

    def step(self, ins: int, pc: int) -> None:
        if (ins >> 28) != 0xF and (ins & 0x0F300E00) == 0x0D100A00:  # VLDR
            return
        return super().step(ins, pc)


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
    written: list[tuple[int, int]] = []
    added: list[int] = []
    if how[0] == "saved":
        stubs[WRITE_BYTE] = lambda cpu, a: written.append((1, a[1] & 0xFF)) or 0
        stubs[WRITE_LONG] = lambda cpu, a: written.append((4, a[1])) or 0
    if how[0] == "dupdate":
        stubs[MEMSET] = lambda cpu, a: 0
        stubs[ENUM_CTOR] = lambda cpu, a: a[0]
        stubs[ENUM_RUN] = lambda cpu, a: 0
        stubs[ENUM_DTOR] = lambda cpu, a: 0
        stubs[ADD] = lambda cpu, a: added.append(a[1]) or 0
    cpu = ListingCpu(mem, stubs, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    try:
        if how[0] == "call":
            cpu.run(how[1])
            return [0, cpu.r[0], mem.faults, calls_field(cpu.listed)]
        if how[0] == "saved":
            if cpu.run(how[1], stop={WRITE_BYTE}) == WRITE_BYTE:  # the last byte: a tail branch, not a BL
                written.append((1, cpu.r[1] & 0xFF))
            return [0] + [f"{k}:{v:x}" for k, v in written] + [mem.faults]
        if how[0] == "picture":
            cpu.r[4] = args[0]
            cpu.run(how[1], stop={0x0035D96C})
            flags = word(st, args[0] + 0x280)
            for a, n, v in mem.writes:
                if a == args[0] + 0x280 and n == 4:
                    flags = v
            return [0, flags, mem.faults, calls_field(cpu.listed)]
        if how[0] == "hpbar":
            cpu.r[1], cpu.r[5] = G_CONFIG, args[0]
            cpu.run(how[1], stop={0x0038D44C})
            return [0, cpu.r[1], mem.faults]
        if how[0] == "dupdate":
            cpu.run(how[1])
            return [0, len(added)] + added + [mem.read(args[0] + 0x200, 4), mem.faults, calls_field(cpu.listed)]
        if how[0] == "dadd":
            image, unit = args[0], args[1]
            cpu.run(0x0038F30C, stop={0x0038F330})
            search = cpu.r[0]
            cpu.r[13] = SP - 0x100
            mem.write(cpu.r[13] + 0x40, 4, image)
            mem.write(cpu.r[13] + 0x44, 4, unit)
            faults = mem.faults
            cpu.run(0x0038F6F8, stop={0x0038F81C})
            faults = mem.faults
            marked = (word(st, unit + 8) & 0x10000) != 0 if unit + 11 in st.mem else False
            sets = [bytes(mem.read8(image + 0x80 * k + i) for i in range(128)).hex() for k in range(4)]
            shown = [sets[0] if marked else "-", sets[1], sets[2] if marked else "-", sets[3]]
            return [0, search] + shown + [mem.read(image + 0x200, 4), faults]
        if how[0] == "dtile":
            cfg = word(st, G_CONFIG)
            cpu.r[4] = cfg
            pc = cpu.run(0x00390F9C, stop={0x00390FB0, 0x00391704})
            kind_ = 0
            if pc == 0x00390FB0:
                m = word(st, G_MAPIMAGE)
                cpu.r[4], cpu.r[8] = args[0], args[1]
                cpu.r[6], cpu.r[7] = (m + 0x1008) & 0xFFFFFFFF, (m + 0x408) & 0xFFFFFFFF
                pc = cpu.run(0x00391008, stop={0x0039104C, 0x003912AC, 0x003916D4})
                kind_ = {0x0039104C: 1, 0x003912AC: 2, 0x003916D4: 0}[pc]
            return [0, kind_, mem.faults, calls_field(cpu.listed)]
    except A.ColdGuard:
        return [1]
    raise SystemExit(f"menu_diff: unknown kind {how[0]}")


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/menu/tests/menu_diff.py: runs readable menu functions on memory
   images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "menus.h"

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

static int depth, nested;
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
static void hex128(const uint8_t *b) { printf(" "); for (int i = 0; i < 128; i++) printf("%02x", b[i]); }

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
            const char *cl;
            if (!strncmp(kind, "ov:", 3)) {
                uint32_t addr = (uint32_t)strtoul(kind + 3, NULL, 16);
                for (int i = 0; i < 4; i++) c.r[i] = a[i];
                int found = 0;
                for (unsigned i = 0; i < sizeof ovs / sizeof ovs[0]; i++) if (ovs[i].a == addr) { ovs[i].f(&c); found = 1; }
                cl = ncalls ? calls : "-";
                if (!found) printf("%u NO-OVERRIDE\n", id);
                else if (originals) printf("%u 1 %d\n", id, faults);
                else printf("%u 0 %u %d %s\n", id, c.r[0], faults, cl);
            } else if (!strcmp(kind, "saved")) {
                MenuSavedEntry e[MN_SAVED_ENTRIES];
                int ok = config_saved_record(&c, a[0], e);
                if (!ok || originals) printf("%u 1 %d\n", id, faults);
                else {
                    printf("%u 0", id);
                    for (int i = 0; i < MN_SAVED_ENTRIES; i++) printf(" %u:%x", e[i].kind, e[i].value);
                    printf(" %d\n", faults);
                }
            } else if (!strcmp(kind, "picture")) {
                uint32_t f = 0;
                int ok = battle_picture_choice(&c, a[0], &f);
                cl = ncalls ? calls : "-";
                if (!ok || originals) printf("%u 1 %d\n", id, faults);
                else printf("%u 0 %u %d %s\n", id, f, faults, cl);
            } else if (!strcmp(kind, "hpbar")) {
                uint32_t s = 0;
                int ok = actor_hp_bar_shown(&c, a[0], &s);
                if (!ok || originals) printf("%u 1 %d\n", id, faults);
                else printf("%u 0 %u %d\n", id, s, faults);
            } else if (!strcmp(kind, "dupdate")) {
                static DangerTargets t;
                int ok = danger_update_targets(&c, a[0], &t);
                cl = ncalls ? calls : "-";
                if (!ok || originals) printf("%u 1 %d\n", id, faults);
                else {
                    printf("%u 0 %d", id, t.count);
                    for (int i = 0; i < t.count; i++) printf(" %u", t.units[i]);
                    printf(" %u %d %s\n", t.flags_after, faults, cl);
                }
            } else if (!strcmp(kind, "dadd")) {
                static DangerAddPreview p;
                int ok = danger_add_preview(&c, a[0], a[1], &p);
                uint32_t state = 0;  /* the test's own look at the unit: not counted as a read */
                for (uint32_t i = 0; i < 4; i++) {
                    uint8_t *q = at(a[1] + 8u + i, 0);
                    state |= (uint32_t)(q ? *q : 0) << (8 * i);
                }
                int marked = (state & MN_STATE_DANGER_MARK) != 0;
                if (!ok || originals) printf("%u 1 %d\n", id, faults);
                else {
                    printf("%u 0 %u", id, p.search_flags);
                    for (int k = 0; k < 4; k++) {
                        if ((k == 0 || k == 2) && !marked) printf(" -");
                        else hex128(p.sets[k]);
                    }
                    printf(" %u %d\n", p.flags_after, faults);
                }
            } else if (!strcmp(kind, "dtile")) {
                uint32_t k = 0;
                int ok = danger_tile_kind(&c, (int32_t)a[0], (int32_t)a[1], &k);
                cl = ncalls ? calls : "-";
                if (!ok || originals) printf("%u 1 %d\n", id, faults);
                else printf("%u 0 %u %d %s\n", id, k, faults, cl);
            }
            if (writes) printf("%u WROTE-GUEST %d\n", id, writes);
            if (nested) printf("%u NESTED-GIVEUP %d\n", id, nested);
        }
    }
    return 0;
}
'''

# the C driver can reach these by a guest call: this batch's overrides and Force::IsAllied's
DRIVER_OVERRIDES = sorted(set(OVERRIDES.values()) | {IS_ALLIED})


def driver_text() -> str:
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in DRIVER_OVERRIDES)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in DRIVER_OVERRIDES) + "};\n"
    return DRIVER.replace("@OVERRIDE_DECLS@", decls + table)


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


def build_driver(cc: str, out: str, menu_dir: str) -> str:
    """Builds the driver with every source of src/readable/, the menu folder's taken from menu_dir."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "menu_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_MENU)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(menu_dir, f) for f in os.listdir(menu_dir) if f.endswith(".c")]
    exe = os.path.join(out, "menu_driver.exe" if os.name == "nt" else "menu_driver")
    inc = ["-I", menu_dir, "-I", os.path.join(ROOT, "src", "readable", "unit"),
           "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"menu_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
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
        raise SystemExit(f"menu_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
        if exp[0] == 0:
            cov = COVERAGE.setdefault(name, {"values": set(), "nonzero": 0})
            v = exp[1] if len(exp) > 1 else None
            cov["values"].add(v)
            cov["nonzero"] += int(v not in (0, "1:1"))
        if exp[0] == 1:
            res[2] += 1
            exp = [1, 0]  # a give-up must come before any unmapped read
        elif g is not None and g[:1] == [1] and g[1:] == [0] and c not in flagged:
            res[3] += 1  # an early give-up: a needed cache is cold, asked before anything is read
            continue
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                ge = [x if not isinstance(x, str) or len(x) < 40 else x[:40] + "..." for x in (g or [])]
                ee = [x if not isinstance(x, str) or len(x) < 40 else x[:40] + "..." for x in exp]
                print(f"  MISMATCH {name} case {c}: original {ee}, readable {ge}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
PLANTS = [
    # menu_config.c: the option items
    ("menu_config.c", "config_object(ctx), danger);", "config_object(ctx), byte_0f);"),
    ("menu_config.c", "config_object(ctx), hp_gauge);", "config_object(ctx), byte_15);"),
    ("menu_config.c", "    for (int32_t i = 0; i < count; i++)", "    for (int32_t i = 1; i < count; i++)"),
    ("menu_config.c", "    if (count <= 0)\n        return 0;\n", "    if (count <= 0)\n        return 1;\n"),
    ("menu_config.c", "option_bits)) != 0 ? 1u : 0u;\n}\n\n/* ---- GameConfigData", "option_bits));\n}\n\n/* ---- GameConfigData"),
    # the item's mask taken as a constant instead of its virtual GetMask: a missing guest call
    ("menu_config.c", "    uint32_t mask = guest_call1(ctx, guest_ptr(ctx, table + MN_ITEM_GETMASK_SLOT), item);",
     "    uint32_t mask = table != 0 ? 0x10u : 0u;"),
    # IsSpeedFast
    ("menu_config.c", "    if ((READ_FIELD(ctx, Pad, pad, held) & 1u) && speed == 2)",
     "    if ((READ_FIELD(ctx, Pad, pad, held) & 1u) && speed >= 2)"),
    # the pad read before the "always fast" test: same answers, more unmapped reads
    ("menu_config.c", "    uint32_t speed = READ_FIELD(ctx, GameConfigData, config, game_speed);\n    if (speed == 1)\n        return 1;\n    gaddr pad = guest_ptr(ctx, G_Pad);",
     "    uint32_t speed = READ_FIELD(ctx, GameConfigData, config, game_speed);\n    gaddr pad = guest_ptr(ctx, G_Pad);\n    uint32_t held = READ_FIELD(ctx, Pad, pad, held);\n    (void)held;\n    if (speed == 1)\n        return 1;"),
    ("menu_config.c", "pressed) & 0xAu)", "pressed) & 0x2u)"),
    ("menu_config.c", "    if (bits & 0x20000000u)\n        return 2;\n    return (bits & 0x40000000u) != 0 ? 1u : 0u;",
     "    if (bits & 0x40000000u)\n        return 1;\n    return (bits & 0x20000000u) != 0 ? 2u : 0u;"),
    # the battle-animation rule
    ("menu_config.c", "Situation, situation, force_index)) == 1", "Situation, situation, view_force)) == 1"),
    ("menu_config.c", "        return READ_FIELD(ctx, Unit, unit, state_flags) >> 31;",
     "        return (READ_FIELD(ctx, Unit, unit, state_flags) >> 30) & 1u;"),
    ("menu_config.c", "    case 1:\n        return 1;\n    case 2:", "    case 1:\n    case 5:\n        return 1;\n    case 2:"),
    # IsDetailBattle: the flip only for a bool of exactly 1 (the game tests the whole register)
    ("menu_config.c", "    if (flip != 0)\n        picture ^= 1u;\n    if (unit_a != 0 && guest_call1(ctx, MN_UnitDetailMust, unit_a) != 0)",
     "    if (flip == 1)\n        picture ^= 1u;\n    if (unit_a != 0 && guest_call1(ctx, MN_UnitDetailMust, unit_a) != 0)"),
    # IsDetailBattle: the unit checks in another order (a, a, b, b): same answers, another call list
    ("menu_config.c", "    if (unit_b != 0 && guest_call1(ctx, MN_UnitDetailMust, unit_b) != 0)\n        picture = 1;\n    if (unit_a != 0 && guest_call1(ctx, MN_UnitDetailNotAllow, unit_a) != 0)\n        picture = 0;",
     "    if (unit_a != 0 && guest_call1(ctx, MN_UnitDetailNotAllow, unit_a) != 0)\n        picture = 0;\n    if (unit_b != 0 && guest_call1(ctx, MN_UnitDetailMust, unit_b) != 0)\n        picture = 1;"),
    ("menu_config.c", "    if (unit_b != 0 && situation != 0 && option_says_picture(ctx, config, situation, unit_b))\n        picture = 1;",
     "    if (unit_b != 0 && situation != 0)\n        picture = option_says_picture(ctx, config, situation, unit_b);"),
    # IsDetailBattle without asking the two unit checks' caches first: a nested give-up
    ("menu_config.c", "        (!fe_static_ready(ctx, MN_MustGuardA) || !fe_static_ready(ctx, MN_MustGuardB) ||\n         !fe_static_ready(ctx, MN_NotAllowGuard)))",
     "        !fe_static_ready(ctx, MN_NotAllowGuard))"),
    # IsDetailSupport
    ("menu_config.c", "        uint32_t says = situation != 0 ? option_says_picture(ctx, config, situation, unit_a) : 0u;\n        if ((READ_FIELD(ctx, GameConfigData, config, option_bits) & 2u) && says)",
     "        uint32_t says = situation != 0 ? option_says_picture(ctx, config, situation, unit_a) : 0u;\n        if ((READ_FIELD(ctx, GameConfigData, config, option_bits) & 1u) && says)"),
    ("menu_config.c", "uint32_t config_is_detail_support(Context *ctx, gaddr config, gaddr unit_a, gaddr unit_b, uint32_t flip) {\n    if (!fe_static_ready(ctx, MN_SupportGuard))\n        return fe_use_original(ctx);\n",
     "uint32_t config_is_detail_support(Context *ctx, gaddr config, gaddr unit_a, gaddr unit_b, uint32_t flip) {\n"),
    # the unit flag readers
    ("menu_config.c", "    uint64_t always = guest_u64(ctx, MN_MustMaskA) | guest_u64(ctx, MN_MustMaskB);",
     "    uint64_t always = guest_u64(ctx, MN_MustMaskA);"),
    ("menu_config.c", "uint32_t unit_is_detail_battle_not_allow(Context *ctx, gaddr unit) {\n    if (!fe_static_ready(ctx, MN_NotAllowGuard))\n        return fe_use_original(ctx);\n",
     "uint32_t unit_is_detail_battle_not_allow(Context *ctx, gaddr unit) {\n"),
    ("menu_config.c", "    return f | READ_FIELD(ctx, JobData, job, flags);", "    (void)job;\n    return f;"),
    ("menu_config.c", "    for (uint32_t i = 0; i < 15; i++) {", "    for (uint32_t i = 0; i < 14; i++) {"),
    # menu_show.c
    ("menu_show.c", "held) & 0x200u)", "held) & 0x100u)"),
    ("menu_show.c", "(flags & 4u) ? MN_ConfigDetailSupport", "(flags & 8u) ? MN_ConfigDetailSupport"),
    # the battle-picture decision without asking IsDetailBattle's caches first: a nested give-up
    ("menu_show.c", "    if (!fe_static_ready(ctx, MN_SupportGuard) || !fe_static_ready(ctx, MN_MustGuardA) ||\n        !fe_static_ready(ctx, MN_MustGuardB) || !fe_static_ready(ctx, MN_NotAllowGuard))",
     "    if (!fe_static_ready(ctx, MN_SupportGuard))"),
    # the flags word not read again before bit 0 is set
    ("menu_show.c", "        flags = READ_FIELD(ctx, BattleSequence, sequence, flags) | 1u;  /* the game reads the word again */",
     "        flags |= 1u;"),
    ("menu_show.c", "        (READ_FIELD(ctx, Situation, guest_ptr(ctx, G_Situation), flags) & 1u) == 0 &&\n", ""),
    ("menu_show.c", "state_flags) & MN_STATE_PARTNER) == 0)", "state_flags) & 0x2u) == 0)"),
    # menu_danger.c
    ("menus.h", "#define MN_STATE_DANGER_SKIP 0x24004u", "#define MN_STATE_DANGER_SKIP 0x4004u"),
    ("menu_danger.c", "    for (uint32_t army = 0; army < 3; army++) {", "    for (uint32_t army = 0; army < 2; army++) {"),
    ("menu_danger.c", "            if ((READ_FIELD(ctx, DangerImage, image, flags) & MN_DANGER_WHOLE) == 0 &&\n                (READ_FIELD(ctx, Unit, unit, state_flags) & MN_STATE_DANGER_MARK) == 0)",
     "            if ((READ_FIELD(ctx, Unit, unit, state_flags) & MN_STATE_DANGER_MARK) == 0)"),
    # the allied test against a wrong army number (only the low bit of the viewing army)
    ("menu_danger.c", "READ_FIELD(ctx, Unit, unit, force), view) != 0)", "READ_FIELD(ctx, Unit, unit, force), view & 1u) != 0)"),
    ("menu_danger.c", "option == 0 ? 0x50000u : option == 2 ? 0x30000u : 0x10000u;",
     "option == 0 ? 0x50000u : option == 1 ? 0x30000u : 0x10000u;"),
    ("menu_danger.c", "        or_set(ctx, image, 2, READ_FIELD(ctx, MapDeploy, deploy, zone_b), out->sets[2]);",
     "        or_set(ctx, image, 2, READ_FIELD(ctx, MapDeploy, deploy, zone_a), out->sets[2]);"),
    ("menu_danger.c", "    out->flags_after = READ_FIELD(ctx, DangerImage, image, flags) | MN_DANGER_REDRAW;\n    return !fe_gave_up(ctx);\n}\n\n/* Helper for the tile test",
     "    out->flags_after = READ_FIELD(ctx, DangerImage, image, flags);\n    return !fe_gave_up(ctx);\n}\n\n/* Helper for the tile test"),
    ("menu_danger.c", "(int32_t)((uint32_t)x | ((uint32_t)y << 5));", "(int32_t)((uint32_t)x + ((uint32_t)y << 5));"),
    ("menu_danger.c", "    if (option != 2 && option != 0)", "    if (option > 2)"),
    ("menu_danger.c", "    if (guest_u8(ctx, FIELD_ADDR(DangerImage, image, marked_b) + (gaddr)fe_asr(tile, 3)) & bit)\n        *kind = 1;\n    else if (guest_u8(ctx, FIELD_ADDR(DangerImage, image, all_b) + (gaddr)fe_asr(tile, 3)) & bit)\n        *kind = 2;",
     "    if (guest_u8(ctx, FIELD_ADDR(DangerImage, image, all_b) + (gaddr)fe_asr(tile, 3)) & bit)\n        *kind = 2;\n    else if (guest_u8(ctx, FIELD_ADDR(DangerImage, image, marked_b) + (gaddr)fe_asr(tile, 3)) & bit)\n        *kind = 1;"),
    ("menu_danger.c", "MN_TERRAIN_FLAGS) & 8u))", "MN_TERRAIN_FLAGS) & 4u))"),
    ("menu_danger.c", "guest_ptr(ctx, panel)) == 0 ? 1u : 0u;", "guest_ptr(ctx, panel)) == 1 ? 1u : 0u;"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_MENU, d, ignore=shutil.ignore_patterns("tests"))
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
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, default=200, help="cases per function for each planted bug")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("menu_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("menu_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_MENU)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"menu_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:32s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:32s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("menu_diff: what the cases exercised (original's first result, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:32s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"menu_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"menu_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
