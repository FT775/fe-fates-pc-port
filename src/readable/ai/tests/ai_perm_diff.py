#!/usr/bin/env python3
"""Host differential test of the AI permission readers (docs/AI.md) against the game's own ARM code.

    python src/readable/ai/tests/ai_perm_diff.py             all functions, 300 cases each
    python src/readable/ai/tests/ai_perm_diff.py --seed 7    the second seed
    python src/readable/ai/tests/ai_perm_diff.py -n 1500 --seed 7    the long run
    python src/readable/ai/tests/ai_perm_diff.py --only ai_sigh_of_death_score
    python src/readable/ai/tests/ai_perm_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/move/tests/move_diff.py (and the ARM interpreter
src/readable/battle/tests/arm_mini.py): for every readable function of src/readable/ai/ai_permission.c,
ai_area.c and ai_items.c the test makes up guest states, runs the ORIGINAL ARM code from the owner's
extracted/text.bin in arm_mini.py and the readable C function (built with the host gcc against
tools/readable/stub/) on the same memory, and compares r0, the number of bytes read from unmapped
memory AND the list of guest calls, in order, with their argument registers (docs/DECISIONS.md F-018).
All values are random test values, never game data, and on purpose often outside the ranges the game
uses: coordinates off the map and far off it, unmapped units, AIThink objects, map images and command
lists, condition bytes and AI values that name nothing, command codes past the switch, bools that are
not 0/1, negative HP, a maximum HP of 0 (the game's division then gives 0).

Two kinds of made-up state are used. The status-sheet test's (src/readable/sheet/tests/sheet_diff.py:
units with Person, class, force, partner, carried items, Item and sub-kind records) for the permission,
item and stat readers, so that Unit::IsDontAttack, Unit::GetMHPImpl, Unit::GetMovePower and
Unit::GetCategory run as ARM code on one side and as their readable overrides on the other. The
movement test's (move_diff.py: map image with its unit and cost-column grids, terrain and TerrainCost
tables, the unit pool) for the map readers, so that map::Image::Unit::GetUnit and
TerrainCost::GetCostFromUnit run as ARM code and as their overrides. AIValue::IsArgument / GetArgument /
IsSkip and this batch's own IsActiveCommand and IsAttackPermissionOnlyCommand run as ARM code and as
overrides too.

Guest functions answered by one table on both sides: those of the two tests (unit::Item::ToData,
ItemSubKind::Get, Unit::CanItemEquip, Force::IsAllied, UnitPool::Get, ...) and GameUserData::Get,
Unit::CanKeyDoor, AIThink::GetTrickFromAccess, AIValue::GetPerson, AIValue::GetJob, Unit::CanItemUse,
Item::IsMagic and Unit::GetRangeO. The last three and GetTrickFromAccess are readable overrides of older
batches, tested there; the readable code here asks their one-time caches before anything else, so
they never give up inside it. Round 18: a call to Item::IsMagic or Unit::GetRangeO while its own cache
is cold is answered with a give-up counted as nested (COLD_STUBS), as their overrides would in the game,
and a give-up of ai_has_heal_rod while every cache it asks is warm is printed as gave_up 2, a mismatch
(GIVEUP_GUARDS). Any other early give-up at a cold cache is always safe.

Tail branches: on the ARM side every BL/BLX and every tail branch (B) to a stubbed callee is listed; a
tail branch to an override runs on as ARM code, unlisted (3dsrecomp keeps the target inside the caller;
round 10 integrate, docs/MOVE.md 9). AIThink::GetMovePowerSlow ends with such a branch into
Unit::GetMovePower on difficulty 2: the readable code runs unit_move directly there, and this test
models it that way. A nested give-up (a guest call of another readable function giving up inside while
the outer one goes on) is a mismatch.

--plant copies the three sources and ai_perm.h to build/readable/ai_perm/plant/, makes one small wrong
change at a time (PLANTS below, at least one per function), rebuilds and reruns: every planted bug must
give at least one mismatch.

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
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "move", "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
import move_diff as M  # noqa: E402
import sheet_diff as S  # noqa: E402
from stance_diff import pick  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "ai_perm")
SRC_AI = os.path.join(ROOT, "src", "readable", "ai")
MINE = ("ai_permission.c", "ai_area.c", "ai_items.c", "ai_perm.h")
GUARD = 0x00302C6C
SP = 0x0FFFF000
s32 = M.s32
word = M.word

# ------------------------------------------------------------------ addresses
GUD_GET, CAN_KEY_DOOR, TRICK, GET_PERSON, GET_JOB, CAN_USE, IS_MAGIC, RANGE_O = (
    0x001B3AFC, 0x00529E20, 0x004CF5B4, 0x0044A6F0, 0x00543E3C, 0x0052920C, 0x005290B8, 0x00534510)
OWN_STUBS = {GUD_GET: 0, CAN_KEY_DOOR: 1, TRICK: 3, GET_PERSON: 1, GET_JOB: 1, CAN_USE: 2, IS_MAGIC: 1, RANGE_O: 2}
LEAF_STUBS = dict(M.LEAF_STUBS)
LEAF_STUBS.update(S.LEAF_STUBS)
LEAF_STUBS.update(OWN_STUBS)
TO_DATA, SUBKIND_GET, CAN_EQUIP, IS_ALLIED, POOL_GET = S.TO_DATA, S.SUBKIND_GET, S.CAN_EQUIP, M.IS_ALLIED, M.POOL_GET

OVERRIDES = {  # this batch: name -> address
    "ai_attack_permission": 0x004CF624, "ai_attack_permission_self": 0x004CF658,
    "ai_heal_rod_permission": 0x004D0ADC, "ai_is_clever": 0x004D61E4, "ai_allow_idle_mutation": 0x004D0AC0,
    "ai_command_is_active": 0x004CB280, "ai_deploy_free_move_flag": 0x004D24D4, "ai_move_power_slow": 0x004CC818,
    "ai_heal_condition_for_entrust": 0x004D4054, "ai_attack_permission_for_command": 0x004D4770,
    "ai_has_active_command": 0x004CC870, "ai_has_crossfire_command": 0x004D48BC,
    "ai_is_escape_position": 0x004CC978, "ai_sigh_of_death_score": 0x004D0820,
    "ai_is_dual_support_unit": 0x004CDF40,
    "ai_item_index_heal": 0x004CC684, "ai_item_index_doping": 0x004CF360, "ai_has_heal_rod": 0x004C829C,
}
DONT_ATTACK, MHP, MOVE_POWER, CATEGORY = 0x0052DC90, 0x0052A364, 0x0052D5E4, 0x0052B728
IMAGE_GET_UNIT, COST_FROM_UNIT = M.IMAGE_GET_UNIT, M.COST_FROM_UNIT
IS_ARGUMENT, GET_ARGUMENT, IS_SKIP = 0x00543DF4, 0x00543E0C, 0x00543E44
IS_ACTIVE, ONLY_CMD = 0x004CB280, 0x004D4770
# overrides of older batches that run as ARM code on one side and as readable code on the other
CALLEES = {DONT_ATTACK, MHP, MOVE_POWER, CATEGORY, IMAGE_GET_UNIT, COST_FROM_UNIT, IS_ARGUMENT, GET_ARGUMENT,
           IS_SKIP}
ARITY = dict(M.ARITY)
ARITY.update(S.ARITY)
ARITY.update(LEAF_STUBS)
ARITY.update({DONT_ATTACK: 3, MHP: 4, MOVE_POWER: 3, CATEGORY: 1, IMAGE_GET_UNIT: 3, COST_FROM_UNIT: 2,
              IS_ARGUMENT: 1, GET_ARGUMENT: 3, IS_SKIP: 1, IS_ACTIVE: 2, ONLY_CMD: 4})
DRIVER_OVERRIDES = sorted(set(OVERRIDES.values()) | CALLEES | set(M.OVERRIDES.values()) | set(S.OVERRIDES.values()))

# globals and caches (src/readable/ai/ai_perm.h)
G_SITUATION, G_AI_HOLDER, G_COMMANDS = 0x006D7ED0, 0x006D0EBC, 0x0070560C
AI_CACHE = 0x006D1000                       # the block the AI caches live in (zeroed, then set)
HEAL_GUARDS, HEAL_USES = (0x006D1070, 0x006D106C), (0x006D1058, 0x006D105A)
DOPE_GUARDS, DOPE_USES = (0x006D1080, 0x006D107C, 0x006D1078, 0x006D1074), (0x006D105C, 0x006D105E, 0x006D1060,
                                                                               0x006D1062)
ROD_GUARD, ROD_MASK = 0x006D1084, 0x006D10D0
ONLY_GUARD, ONLY_MASK = 0x006D12B0, 0x006D1310
MAGIC_GUARD, RANGE_GUARD = 0x006D38D4, 0x006D989C
AI_GUARDS = HEAL_GUARDS + DOPE_GUARDS + (ROD_GUARD, ONLY_GUARD, MAGIC_GUARD, RANGE_GUARD)
USE_KINDS = [1, 2, 3, 4, 5, 6, 7, 9, 12, 17]

# objects of the made-up state (outside both tests' layouts)
THINK = 0x08800000           # AIThink: +0 the unit
SITUATION = 0x08801000
GUD = 0x08802000
HOLDER_ROOT, HOLDER_STATE = 0x08803000, 0x08804000
COMMAND = 0x08805000         # a single AICommand (IsActiveCommand)
VALUES = 0x08806000          # AIValue s16s (IsAttackPermissionOnlyCommand)
SEQ_ARRAYS = 0x08810000      # 3 arrays of sequence pointers
SEQS = 0x08820000            # sequences, 0x100 apart
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
COMMAND_CODES = [1, 2, 3, 5, 9, 11, 12, 13, 40, 41, 0x51, 20]


def guard(st, addr: int, cold_p: float = 0.01) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def cool(st, guards, p: float = 0.04) -> None:
    for g in guards:
        if st.rng.random() < p:
            st.put(g, 4, 0)


def ai_caches(st) -> None:
    rng = st.rng
    st.zero(AI_CACHE, 0x400)
    for g in AI_GUARDS:
        guard(st, g)
    for a in HEAL_USES + DOPE_USES:
        st.put(a, 2, pick(rng, USE_KINDS, [0, 0x100, 0xFFFF, 0x1FF], 0.08))
    for a in (ROD_MASK, ONLY_MASK):
        st.put(a, 8, 1 << rng.randrange(64) if rng.random() > 0.05 else rng.randrange(1 << 64))


def situation(st) -> None:
    rng = st.rng
    st.fill(SITUATION, 0x20)
    st.put(SITUATION + 8, 1, pick(rng, [0, 1, 1, 2, 3], [9, 31, 255]))
    st.put(G_SITUATION, 4, SITUATION if rng.random() > 0.03 else rng.choice(UNMAPPED))


def think_of(st, unit: int, p_none: float = 0.05, p_unmapped: float = 0.04) -> int:
    rng = st.rng
    st.fill(THINK, 0x40)
    st.put(THINK, 4, 0 if rng.random() < p_none else unit)
    return THINK if rng.random() > p_unmapped else rng.choice(UNMAPPED)


# --- the two base states
def sheet_state(rng):
    st = S.base_state(rng)
    units = S.all_units(st)
    ai_caches(st)
    situation(st)
    for u in units:  # the AI bytes: mostly small
        st.put(u + 0x54, 4, rng.randrange(1 << 32) if rng.random() < 0.4 else 0)
        st.put(u + 0x5A, 1, pick(rng, [0, 1, 2, 3, 7], [255, 0x80]))
        st.put(u + 0x5B, 1, pick(rng, [0, 0, 1, 2, 3], [255, 0x7F, 0x80]))
        st.put(u + 0x5D, 1, pick(rng, [0, 25, 50, 75, 100], [255, 1, 99]))
        st.put(u + 0xF3, 1, pick(rng, [0, 1, 2, 5, 10, 20, 30, 45], [-1, -5, -128, 127]) & 0xFF)
    return st, units


def move_state(rng):
    st = M.base_state(rng)
    ai_caches(st)
    situation(st)
    for k in range(M.NUNITS):
        u = M.UNIT(k)
        st.put(u + 0xF3, 1, pick(rng, [0, 1, 1, 2, 5, 20], [-1, -128, 127]) & 0xFF)
        st.put(u + 0xA8, 4, 0 if rng.random() < 0.85 else M.UNIT(rng.randrange(M.NUNITS)))
        M.answer_unit(st, u)
    M.answer_unit(st, 0)
    return st


def ov(name, args):
    a = OVERRIDES[name]
    return f"ov:0x{a:08X}", [s32(x) for x in args] + [0] * (4 - len(args)), ("call", a)


def bool_arg(rng) -> int:
    return pick(rng, [0, 1, 1], [2, 0x100, 0xFFFFFFFF], 0.15)


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def gen_attack(rng):
    st, units = sheet_state(rng)
    a = 0 if rng.random() < 0.15 else S.unit_arg(st, units)
    b = S.unit_arg(st, units)
    return (st,) + ov("ai_attack_permission", [a, b, bool_arg(rng)])


def gen_attack_self(rng):
    st, units = sheet_state(rng)
    t = think_of(st, S.unit_arg(st, units), p_none=0.15)
    return (st,) + ov("ai_attack_permission_self", [t, S.unit_arg(st, units), bool_arg(rng)])


def gen_rod_permission(rng):
    st, units = sheet_state(rng)
    u = S.unit_arg(st, units)
    if units[0] <= u < S.UNIT(S.NUNITS) and rng.random() < 0.5:
        st.put(u + 0x54, 4, rng.choice([0x100000, 0x200000, 0x300000, 0x400000, 0x80000]))
    return (st,) + ov("ai_heal_rod_permission", [rng.randrange(1 << 32), u])


def gen_clever(rng):
    st, _ = sheet_state(rng)
    return (st,) + ov("ai_is_clever", [])


def gen_idle(rng):
    st, _ = sheet_state(rng)
    st.fill(HOLDER_ROOT, 0x20)
    st.fill(HOLDER_STATE, 0x200)
    st.put(HOLDER_ROOT + 0x10, 4, HOLDER_STATE if rng.random() > 0.04 else rng.choice(UNMAPPED))
    st.put(HOLDER_STATE + 0x150, 1, pick(rng, [0, 1, 2], [0x80, 0xFF, 0x7F], 0.3))
    st.put(G_AI_HOLDER, 4, HOLDER_ROOT if rng.random() > 0.04 else rng.choice(UNMAPPED))
    return (st,) + ov("ai_allow_idle_mutation", [])


def gen_active(rng):
    st, units = sheet_state(rng)
    u = S.unit_arg(st, units)
    st.fill(COMMAND, 0x10)
    band = st.mem.get(u + 0x5B, 0) if u in units else 0
    st.put(COMMAND + 2, 1, pick(rng, [-2, -1, 0, band, band, 1, 3], [127, -128, -3], 0.15) & 0xFF)
    cmd = COMMAND if rng.random() > 0.04 else rng.choice(UNMAPPED)
    return (st,) + ov("ai_command_is_active", [u, cmd])


def gen_free_move(rng):
    st, units = sheet_state(rng)
    u = S.unit_arg(st, units)
    if units[0] <= u < S.UNIT(S.NUNITS):
        v = 0
        for bit in (0x2000, 0x8000, 0x10000):
            v |= bit if rng.random() < 0.5 else 0
        st.put(u + 0x54, 4, v | (rng.randrange(1 << 32) & ~0x1A000 if rng.random() < 0.3 else 0))
    st.oracle[(CAN_KEY_DOOR, s32(u))] = pick(rng, [0, 1], [2, 0x80000000])
    return (st,) + ov("ai_deploy_free_move_flag", [u])


def gud_state(st) -> None:
    rng = st.rng
    st.fill(GUD, 0x40)
    st.put(GUD + 0x2D, 1, pick(rng, [0, 1, 2], [3, 255, 0x80], 0.15))
    st.oracle[(GUD_GET,)] = GUD if rng.random() > 0.04 else rng.choice(UNMAPPED)


def gen_move_slow(rng):
    st, units = sheet_state(rng)
    cool(st, S.MOVE_GUARDS + S.CAT_GUARDS, 0.015)
    gud_state(st)
    u = S.unit_arg(st, units)
    return (st,) + ov("ai_move_power_slow", [think_of(st, u, p_none=0.03)])


def gen_entrust(rng):
    st, units = sheet_state(rng)
    cool(st, S.HP_GUARDS)
    u = S.unit_arg(st, units)
    if units[0] <= u < S.UNIT(S.NUNITS):
        r = rng.random()
        if r < 0.4:  # focused: a maximum HP near the HP, 0, negative
            st.oracle[(S.GET_LIMIT, u, 0)] = s32(rng.choice([0, 0, 1, 7, 20, 40, -1, -3]))
            st.put(u + 0xF3, 1, pick(rng, [0, 1, 3, 7, 10, 15, 19, 30], [-1, -7, -128, 127]) & 0xFF)
        elif r < 0.8:  # focused: HP exactly 3/4 of a capped maximum (the 75 % line), a player unit often
            cap = rng.choice([4, 8, 20, 40, 60])
            st.oracle[(S.GET_LIMIT, u, 0)] = cap
            for i in range(8):  # bases well above the cap, so the cap decides
                st.put(word(st, u + 0x9C) + 0x38 + i, 1, 60)
            st.put(u + 0x28, 7, 0)  # no condition bytes (no halving, no tonic)
            st.put(u + 0xF3, 1, cap * 3 // 4 + rng.choice([0, 0, -1, 1]))
            if rng.random() < 0.6:
                st.put(word(st, u + 0xA4) + 8, 1, 0)
        else:
            st.put(u + 0xF3, 1, pick(rng, [0, 1, 3, 7, 10, 15, 19, 30], [-1, -7, -128, 127]) & 0xFF)
    return (st,) + ov("ai_heal_condition_for_entrust", [u])


def value_answers(st, values: list[int], units: list[int]) -> None:
    """what AIValue::GetPerson / GetJob answer for these value addresses: a unit's Person or class
    often, anything sometimes"""
    rng = st.rng
    for v in values:
        u = rng.choice(units)
        st.oracle[(GET_PERSON, s32(v))] = word(st, u + 0x9C) if rng.random() < 0.6 else rng.choice([0, S.PERSON(0), 0x1234])
        st.oracle[(GET_JOB, s32(v))] = word(st, u + 0xA0) if rng.random() < 0.6 else rng.choice([0, S.JOB(1), 0x4321])


def flag_focus(st, u: int, mask_addr: int) -> None:
    """sometimes give the unit, its Person or its class the cached flag bit"""
    rng = st.rng
    if rng.random() < 0.5 and S.UNIT(0) <= u < S.UNIT(S.NUNITS):
        m = word(st, mask_addr, 8)
        base = rng.choice([u, word(st, u + 0x9C), word(st, u + 0xA0)])
        st.put(base, 8, word(st, base, 8) | m)


def gen_only(rng):
    st, units = sheet_state(rng)
    cool(st, (ONLY_GUARD,))
    u = S.unit_arg(st, units)
    flag_focus(st, u, ONLY_MASK)
    st.fill(VALUES, 0x10)
    if u in units and rng.random() < 0.3:  # focused: a key byte of 128 or more (signed and unsigned differ)
        st.put(u + 0x5A, 1, rng.choice([0x80, 0x9C, 0xFF]))
    force_type = st.mem.get(word(st, u + 0xA4) + 8, 0) if u in units else 0
    key = st.mem.get(u + 0x5A, 0) if u in units else 0
    st.put(VALUES, 2, pick(rng, [force_type, key, 0, 1, 3], [-1, -3, 0x7FFF, 0xFF], 0.15) & 0xFFFF)
    value_answers(st, [VALUES, VALUES + 4], units)
    v1 = VALUES if rng.random() > 0.04 else rng.choice(UNMAPPED)
    code = pick(rng, [3, 4, 5, 6, 7, 8, 9], [0, 1, 2, 10, 12, -1, 0x7FFFFFFF, -0x80000000, 0x103], 0.15)
    return (st,) + ov("ai_attack_permission_for_command", [code, v1, VALUES + 4, u])


def command_lists(st, units: list[int]) -> list[int]:
    """the AI sequence table: 3 order types, 4 sequences each, 1..6 commands ending with kind 0;
    returns every value address a command can name (for the GetPerson / GetJob tables)"""
    rng = st.rng
    st.zero(G_COMMANDS - 0x10, 0x40)
    for t in range(3):
        st.put(G_COMMANDS + 4 * t, 4, SEQ_ARRAYS + 0x40 * t if rng.random() > 0.03 else rng.choice(UNMAPPED))
    values = []
    for t in range(3):
        for i in range(4):
            seq = SEQS + 0x100 * (4 * t + i)
            st.put(SEQ_ARRAYS + 0x40 * t + 4 * i, 4, seq if rng.random() > 0.03 else rng.choice(UNMAPPED))
            st.fill(seq, 8)
            n = rng.choice([0, 1, 2, 3, 4, 6])
            for c in range(n):
                cmd = seq + 8 + 12 * c
                st.fill(cmd, 12)
                st.put(cmd, 1, pick(rng, [3, 3, 3, 1, 2], [4, 255]))
                st.put(cmd + 1, 1, pick(rng, COMMAND_CODES, [0, 255, 0x50, 0x52]))
                st.put(cmd + 2, 1, pick(rng, [-1, -1, -2, 0, 1, 2], [127, -128, 3]) & 0xFF)
                for off in (4, 8):
                    st.put(cmd + off, 2, pick(rng, [-1, -1, 0, 1, 3, 7, -4, -5, -6, -7, -3],
                                              [-2, -8, 0x7FFF, -0x8000]) & 0xFFFF)
                    values.append(cmd + off)
            st.zero(seq + 8 + 12 * n, 12)
    for u in units:
        for t in range(3):
            st.put(u + 0x65 + t, 1, pick(rng, [0, 1, 2, 3], [4, 63, 255]))
        for i in range(16):
            st.put(u + 0x6A + 2 * i, 2, pick(rng, [-1, 0, 1, 2, -3, 5], [-4, 0x7FFF]) & 0xFFFF)
            values.append(u + 0x6A + 2 * i)
        if rng.random() < 0.5:
            st.put(u + 0x54, 4, word(st, u + 0x54) | 0x200000)
    return values


def gen_has_active(rng):
    st, units = sheet_state(rng)
    command_lists(st, units)
    u = S.unit_arg(st, units, torn_p=0.04)
    order = pick(rng, [0, 1, 2], [3, 255, 0x40000000], 0.06)
    return (st,) + ov("ai_has_active_command", [order, u])


def gen_crossfire(rng):
    st, units = sheet_state(rng)
    cool(st, (ONLY_GUARD,))
    values = command_lists(st, units)
    value_answers(st, values, units)
    u = S.unit_arg(st, units, torn_p=0.04)
    t = S.unit_arg(st, units)
    flag_focus(st, t, ONLY_MASK)
    return (st,) + ov("ai_has_crossfire_command", [u, t])


def edge_coords(st):
    """focused: a tile on an edge of the playable area, or anywhere"""
    rng = st.rng
    img = M.MAPIMG
    x, y = M.coord(rng), M.coord(rng)
    if rng.random() < 0.6:
        side = rng.randrange(4)
        if side == 0:
            x = st.mem.get(img + 2, 0)
        elif side == 1:
            y = st.mem.get(img + 3, 0)
        elif side == 2:
            x = st.mem.get(img + 4, 0) - 1
        else:
            y = st.mem.get(img + 5, 0) - 1
    return s32(x), s32(y)


def gen_escape(rng):
    st = move_state(rng)
    cool(st, (M.COST_GUARD,))
    u = M.unit_arg(st)
    x, y = edge_coords(st)
    st.oracle[(TRICK, x, y, 6)] = 0 if rng.random() < 0.6 else rng.choice([M.TILES, 1, 0xFFFFFFFF])
    return (st,) + ov("ai_is_escape_position", [think_of(st, u, p_none=0.03), x, y])


def near_unit_coords(st):
    """focused: a tile next to or near units on the unit grid, or anywhere"""
    rng = st.rng
    if rng.random() < 0.7:
        cells = [i for i in range(1024) if 0 < st.mem[M.MAPIMG + 8 + i] <= M.NUNITS]
        if cells:
            c = rng.choice(cells)
            return s32((c & 31) + rng.randint(-2, 2)), s32((c >> 5) + rng.randint(-2, 2))
    return s32(M.coord(rng)), s32(M.coord(rng))


def gen_sigh(rng):
    st = move_state(rng)
    x, y = near_unit_coords(st)
    return (st,) + ov("ai_sigh_of_death_score", [x, y])


def gen_dual(rng):
    st = move_state(rng)
    u = M.unit_arg(st)
    if M.UNITS <= u < M.UNIT(M.NUNITS) and rng.random() < 0.85:
        st.put(u + 0xA8, 4, 0)
    x, y = near_unit_coords(st)
    return (st,) + ov("ai_is_dual_support_unit", [u, x, y])


def item_focus(st, uses) -> None:
    """item records: the ItemUse kind often one of the cached ones; heal sub-kinds"""
    rng = st.rng
    for k in range(S.NITEMS):
        if rng.random() < 0.6:
            st.put(S.ITEMDATA(k) + 0x1B, 1, word(st, rng.choice(uses), 2) & 0xFF)
        for s in range(8):
            st.put(S.ITEMDATA(k) + 0x40 + s, 1, 0 if rng.random() < 0.7 else rng.randrange(1, 256))
    for k in range(6):
        if rng.random() < 0.5:
            st.put(S.SUBKIND(k) + 1, 1, 8)


def can_use_answers(st, users: list[int], units: list[int]) -> None:
    rng = st.rng
    for user in users:
        for h in units + [0]:
            for slot in range(5):
                st.oracle[(CAN_USE, s32(user), s32(h + 0x108 + 4 * slot))] = int(rng.random() < 0.6)


def gen_heal_index(rng):
    st, units = sheet_state(rng)
    cool(st, HEAL_GUARDS)
    item_focus(st, HEAL_USES)
    u = S.unit_arg(st, units)
    user = rng.choice(units)
    can_use_answers(st, [user], units + [u])
    return (st,) + ov("ai_item_index_heal", [think_of(st, user), u, bool_arg(rng), bool_arg(rng)])


def gen_doping(rng):
    st, units = sheet_state(rng)
    cool(st, DOPE_GUARDS)
    item_focus(st, DOPE_USES)
    u = S.unit_arg(st, units)
    if S.UNIT(0) <= u < S.UNIT(S.NUNITS):
        for slot in range(5):  # the "AI never uses it" bit: mostly clear
            a = u + 0x108 + 4 * slot + 2
            st.put(a, 2, word(st, a, 2) & 0x7FFF if rng.random() < 0.8 else word(st, a, 2) | 0x8000)
        st.put(u + 0x29, 1, rng.randrange(256) if rng.random() < 0.6 else 0)
    user = rng.choice(units)
    can_use_answers(st, [user], units + [u])
    return (st,) + ov("ai_item_index_doping", [think_of(st, user), u])


def gen_heal_rod(rng):
    st, units = sheet_state(rng)
    cool(st, (ROD_GUARD,))
    cool(st, (MAGIC_GUARD, RANGE_GUARD), 0.1)  # round 18: more often, for COLD_STUBS / GIVEUP_GUARDS
    u = S.unit_arg(st, units)
    m = word(st, ROD_MASK, 8)
    for k in range(S.NITEMS):
        d = S.ITEMDATA(k)
        if rng.random() < 0.5:
            st.put(d, 8, word(st, d, 8) | m)
        st.put(d + 0x29, 1, pick(rng, [1, 2, 3, 10], [0, 255]))
        st.oracle[(IS_MAGIC, d)] = int(rng.random() < 0.3)
    for h in units + [u]:
        st.put(h + 0x28, 1, st.mem.get(h + 0x28, 0) | 8 if rng.random() < 0.4 else st.mem.get(h + 0x28, 0) & ~8)
        st.put(h + 0x54, 4, word(st, h + 0x54) | 0x80 if rng.random() < 0.5 else word(st, h + 0x54) & ~0x80)
        for slot in range(5):
            st.oracle[(RANGE_O, s32(h), s32(h + 0x108 + 4 * slot))] = pick(rng, [1, 2, 10, 255], [0xFE, 0])
    return (st,) + ov("ai_has_heal_rod", [u, bool_arg(rng)])


FUNCS = {
    "ai_attack_permission": gen_attack,
    "ai_attack_permission_self": gen_attack_self,
    "ai_heal_rod_permission": gen_rod_permission,
    "ai_is_clever": gen_clever,
    "ai_allow_idle_mutation": gen_idle,
    "ai_command_is_active": gen_active,
    "ai_deploy_free_move_flag": gen_free_move,
    "ai_move_power_slow": gen_move_slow,
    "ai_heal_condition_for_entrust": gen_entrust,
    "ai_attack_permission_for_command": gen_only,
    "ai_has_active_command": gen_has_active,
    "ai_has_crossfire_command": gen_crossfire,
    "ai_is_escape_position": gen_escape,
    "ai_sigh_of_death_score": gen_sigh,
    "ai_is_dual_support_unit": gen_dual,
    "ai_item_index_heal": gen_heal_index,
    "ai_item_index_doping": gen_doping,
    "ai_has_heal_rod": gen_heal_rod,
}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(M.ListingCpu):
    """move_diff's listing CPU (BL/BLX and stubbed tail calls listed, tail branches to an override run
    on unlisted, USAT) with this test's callee table."""

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.listed.append(M.call_text(target, self.r[:ARITY[target]]))
        return A.Cpu.call(self, target, ret)

    def step(self, ins: int, pc: int) -> None:
        c = ins >> 28
        if c != 0xF and self.cond(c) and (ins >> 24) & 0xF == 0xA:
            target = (pc + 8 + (A.sx(ins & 0xFFFFFF, 24) << 2)) & A.MASK
            stub = self.stubs.get(target)
            if target in ARITY and stub is not None:  # a stubbed tail call: listed, returns to the caller's caller
                self.listed.append(M.call_text(target, self.r[:ARITY[target]]))
                self.r[0] = stub(self, tuple(self.r[:4])) & A.MASK
                self.r[15] = self.r[14]
                return
        if c != 0xF and self.cond(c) and (ins & 0x0FE00030) == 0x06E00010:  # USAT
            M.ListingCpu.step(self, ins, pc)
            return
        A.Cpu.step(self, ins, pc)


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
    return [0, cpu.r[0], mem.faults, M.calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER_HEAD = r'''
/* Generated by src/readable/ai/tests/ai_perm_diff.py: runs the readable AI permission readers on
   memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ai_perm.h"
'''


# Round 18: the cold caches of the table-answered readable overrides. Item::IsMagic and Unit::GetRangeO are
# answered by the table, but in the game each is a readable override that gives up when its one-time cache is
# cold; called from inside ai_has_heal_rod, that is a nested give-up. So the driver answers a call to one of them
# with a give-up (counted as nested, a mismatch) when its guard is cold. Before this, planted bugs that weaken
# ai_has_heal_rod's guard check (h6host r17-host ai_has_heal_rod-001/-002/-003) passed the test.
COLD_STUBS = {IS_MAGIC: MAGIC_GUARD, RANGE_O: RANGE_GUARD}
# Round 18: the caches a function asks before it may give up. A give-up while every one of them is warm is
# needless: the driver prints it as gave_up 2, a mismatch (ai_has_heal_rod-004, a give-up-only planted bug).
GIVEUP_GUARDS = {"ai_has_heal_rod": (ROD_GUARD, MAGIC_GUARD, RANGE_GUARD)}


def driver_text() -> str:
    body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in DRIVER_OVERRIDES)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in DRIVER_OVERRIDES) + "};\n"
    cold = ("void fe_stub_original(Context *ctx);\n"
            "static const uint32_t cold_stub[][2] = {" + ", ".join(
                f"{{0x{f:08X}u, 0x{g:08X}u}}" for f, g in COLD_STUBS.items()) + "};\n"
            "static const uint32_t giveup_guards[][4] = {" + ", ".join(
                f"{{0x{OVERRIDES[n]:08X}u, " + ", ".join(f"0x{g:08X}u" for g in gs) + "}"
                for n, gs in GIVEUP_GUARDS.items()) + "};\n"
            "static int cold_override(Context *ctx, uint32_t f) {\n"
            "    for (unsigned i = 0; i < sizeof cold_stub / sizeof cold_stub[0]; i++)\n"
            "        if (cold_stub[i][0] == f) return !fe_static_ready(ctx, cold_stub[i][1]);\n"
            "    return 0;\n}\n"
            "static int needless_giveup(Context *ctx, uint32_t addr) {\n"
            "    for (unsigned i = 0; i < sizeof giveup_guards / sizeof giveup_guards[0]; i++) {\n"
            "        if (giveup_guards[i][0] != addr) continue;\n"
            "        for (int j = 1; j < 4; j++) if (!fe_static_ready(ctx, giveup_guards[i][j])) return 0;\n"
            "        return 1;\n    }\n    return 0;\n}\n")
    stub_line = "    for (int i = 0; i < nstubs; i++) if (stub_f[i] == f) { oracle(ctx); return; }\n"
    out_line = '            else if (originals) printf("%u 1 %d\\n", id, faults);\n'
    if body.count(stub_line) != 1 or body.count(out_line) != 1:
        raise SystemExit("ai_perm_diff: sheet_diff's driver changed; update driver_text")
    body = body.replace(stub_line, "    if (cold_override(ctx, f)) { depth++; fe_stub_original(ctx); depth--; return; }\n"
                        + stub_line)
    body = body.replace(out_line, '            else if (originals && !nested && needless_giveup(&c, addr)) '
                        'printf("%u 2 %d\\n", id, faults);\n' + out_line)
    return DRIVER_HEAD + body.replace("@OVERRIDE_DECLS@", decls + table + cold)


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


def readable_sources() -> list[str]:
    """The other sources of src/readable/ the driver links: the ones git tracks (other rewrite batches may
    be writing new files next to these at the same time; an unfinished one must not break this test),
    or, outside a git checkout, every .c file. This batch's own files are taken from the folder given."""
    mine = {f"src/readable/ai/{f}" for f in MINE}
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
        r = subprocess.run(["git", "ls-files", "src/readable"], cwd=ROOT, capture_output=True, text=True, check=True)
        files = [p for p in r.stdout.split() if p.endswith(".c")]
        if os.path.normcase(os.path.abspath(top)) != os.path.normcase(ROOT):
            files = []  # a copy inside another repository: not this checkout's list
    except (OSError, subprocess.CalledProcessError):
        files = []
    if not files:  # no checkout of its own (a copy, or no git): every .c file
        for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
            files += [os.path.relpath(os.path.join(dp, f), ROOT).replace(os.sep, "/") for f in fn if f.endswith(".c")]
    return sorted(p for p in files if p not in mine and os.path.isfile(os.path.join(ROOT, p)))


def build_driver(cc: str, out: str, ai_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, this batch's three taken from ai_dir (a
    planted bug may leave a parameter unused: not strict then, warnings are not errors)."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "ai_perm_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = [os.path.join(ROOT, p) for p in readable_sources()]
    sources += [os.path.join(ai_dir, f) for f in MINE if f.endswith(".c")]
    exe = os.path.join(out, "ai_perm_driver.exe" if os.name == "nt" else "ai_perm_driver")
    # ai_dir first (its ai_perm.h), then src/readable/ai (where ai_perm.h's "../sheet/sheet.h" resolves)
    inc = ["-I", ai_dir, "-I", SRC_AI, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    warn = ["-Wall", "-Wextra", "-Werror"] if strict else ["-w"]
    cmd = [cc, "-std=c11"] + warn + ["-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"ai_perm_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
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


def compare(exe, cc, lines, expected, show, quiet=False):
    return M.compare(exe, cc, lines, expected, show, quiet)


# planted bugs: (file, exact text, replacement); each text occurs once in its file; at least one per function
PLANTS = [
    # ai_permission.c
    ("ai_permission.c", "    if (unit == 0)\n        return 1;\n    return guest_call3(ctx, AI_UnitIsDontAttack, unit, target, ignore_state) != 0 ? 0u : 1u;\n}\n\n/* The same",
     "    if (unit == 0)\n        return 0;\n    return guest_call3(ctx, AI_UnitIsDontAttack, unit, target, ignore_state) != 0 ? 0u : 1u;\n}\n\n/* The same"),
    ("ai_permission.c", "    uint32_t state = READ_FIELD(ctx, Unit, target, state_flags);\n    gaddr unit = guest_ptr(ctx, think + AITHINK_UNIT);\n    if (state & UNIT_STATE_GONE)\n        return 0;",
     "    uint32_t state = READ_FIELD(ctx, Unit, target, state_flags);\n    if (state & UNIT_STATE_GONE)\n        return 0;\n    gaddr unit = guest_ptr(ctx, think + AITHINK_UNIT);"),
    ("ai_permission.c", "    return (guest_u32(ctx, target + UNIT_AI_FLAGS) & UNIT_AI_ROD_BITS) != 0 ? 1u : 0u;",
     "    return (guest_u32(ctx, target + UNIT_AI_FLAGS) & 0x100000u) != 0 ? 1u : 0u;"),
    ("ai_permission.c", "force_index) != 1 ? 1u : 0u;", "force_index) != 0 ? 1u : 0u;"),
    ("ai_permission.c", "    return guest_s8(ctx, state + AISTATE_IDLE_MUTATION);", "    return guest_u8(ctx, state + AISTATE_IDLE_MUTATION);"),
    ("ai_permission.c", "        return band != 0 ? 1u : 0u;", "        return band == 0 ? 1u : 0u;"),
    ("ai_permission.c", "    if (condition == -1)\n        return 1;", "    if (condition == -1)\n        return 0;"),
    ("ai_permission.c", "        flags |= 0x1000000u;", "        flags |= 0x100000u;"),
    ("ai_permission.c", "    if ((guest_u32(ctx, unit + UNIT_AI_FLAGS) & UNIT_AI_DOORS) && guest_call1(ctx, AI_UnitCanKeyDoor, unit) != 0)",
     "    if (guest_call1(ctx, AI_UnitCanKeyDoor, unit) != 0 && (guest_u32(ctx, unit + UNIT_AI_FLAGS) & UNIT_AI_DOORS))"),
    ("ai_permission.c", "        return unit_move(ctx, unit, 1u, 0);", "        return (int32_t)guest_call3(ctx, AI_UnitGetMovePower, unit, 1u, 0u);"),
    ("ai_permission.c", "    return fe_add32((int32_t)guest_call3(ctx, AI_UnitGetMovePower, unit, 1u, 0u), -2);",
     "    return fe_add32((int32_t)guest_call3(ctx, AI_UnitGetMovePower, unit, 1u, 0u), -1);"),
    ("ai_permission.c", "        limit = AI_HEAL_PERCENT_PLAYER;", "        limit = 76;"),
    ("ai_permission.c", "    if (hp >= max_hp)\n        return 0;", "    if (hp > max_hp)\n        return 0;"),
    ("ai_permission.c", "    case 5:\n        return guest_call1(ctx, AI_ValueGetPerson, value1) == READ_FIELD(ctx, Unit, unit, person) ? 0u : 1u;",
     "    case 5:\n        return guest_call1(ctx, AI_ValueGetPerson, value1) == READ_FIELD(ctx, Unit, unit, person) ? 1u : 0u;"),
    ("ai_permission.c", "    case 7:\n    case 8:", "    case 7:"),
    ("ai_permission.c", "    default:\n        return 1;", "    default:\n        return 0;"),
    ("ai_permission.c", "        return (int32_t)guest_u8(ctx, unit + UNIT_AI_KEY) == guest_s16(ctx, value1) ? 0u : 1u;",
     "        return (int32_t)guest_s8(ctx, unit + UNIT_AI_KEY) == guest_s16(ctx, value1) ? 0u : 1u;"),
    ("ai_permission.c", "        if (code == 0x51)\n            continue;", "        if (code == 0x50)\n            continue;"),
    ("ai_permission.c", "        v1 = guest_call3(ctx, AI_ValueGetArgument, v1, AI_ORDER_ATTACK, unit);",
     "        v1 = guest_call3(ctx, AI_ValueGetArgument, v1, 1u, unit);"),
    ("ai_permission.c", "    uint32_t index = guest_u8(ctx, unit + order + UNIT_AI_SEQUENCE);",
     "    uint32_t index = guest_u8(ctx, unit + UNIT_AI_SEQUENCE);"),
    ("ai_permission.c", "        if (guest_u8(ctx, command + AICMD_CODE) >= 12)", "        if (guest_u8(ctx, command + AICMD_CODE) > 12)"),
    ("ai_permission.c", "    if (!fe_static_ready(ctx, S_AiOnlyGuard)) /* the cache of the override it calls */\n        return fe_use_original(ctx);\n",
     ""),
    ("ai_permission.c", "        if ((code == 40 || code == 41) && !(guest_u32(ctx, unit + UNIT_AI_FLAGS) & UNIT_AI_CROSSFIRE_BIT))",
     "        if ((code == 40) && !(guest_u32(ctx, unit + UNIT_AI_FLAGS) & UNIT_AI_CROSSFIRE_BIT))"),
    # ai_area.c
    ("ai_area.c", "    if ((int32_t)READ_FIELD(ctx, MapImage, image, play_x_end) - 1 == x) {",
     "    if ((int32_t)READ_FIELD(ctx, MapImage, image, play_x_end) == x) {"),
    ("ai_area.c", "        uint32_t column = guest_u8(ctx, image + MAPIMAGE_COST_COLUMN + move_tile(x, y - 1));",
     "        uint32_t column = guest_u8(ctx, image + MAPIMAGE_COST_COLUMN + move_tile(x, y + 1));"),
    ("ai_area.c", "    return guest_call3(ctx, AI_GetTrickFromAccess, (uint32_t)x, (uint32_t)y, 6u) != 0 ? 1u : 0u;",
     "    return guest_call3(ctx, AI_GetTrickFromAccess, (uint32_t)x, (uint32_t)y, 5u) != 0 ? 1u : 0u;"),
    ("ai_area.c", "    lim = (int32_t)READ_FIELD(ctx, MapImage, map_image(ctx), play_y_end) - 1;",
     "    lim = (int32_t)READ_FIELD(ctx, MapImage, map_image(ctx), play_y_end);"),
    ("ai_area.c", "            if ((uint32_t)distance(x, y, tx, ty) - 1u >= 2u)", "            if ((uint32_t)distance(x, y, tx, ty) - 1u >= 3u)"),
    ("ai_area.c", "            if (guest_s8(ctx, unit + UNIT_HP) > 1)", "            if (guest_s8(ctx, unit + UNIT_HP) > 0)"),
    ("ai_area.c", "            uint32_t turn = READ_FIELD(ctx, Situation, guest_ptr(ctx, G_Situation), force_index);",
     "            uint32_t turn = READ_FIELD(ctx, Situation, guest_ptr(ctx, G_Situation), view_force);"),
    ("ai_area.c", "    if (READ_FIELD(ctx, Unit, unit, pair_partner) != 0)\n        return 1;",
     "    if (READ_FIELD(ctx, Unit, unit, pair_partner) != 0)\n        return 0;"),
    ("ai_area.c", "            if (distance(x, y, tx, ty) != 1)", "            if (distance(x, y, tx, ty) > 1)"),
    ("ai_area.c", "            if (READ_FIELD(ctx, Force, force, type) == READ_FIELD(ctx, Force, own, type))",
     "            if (force == own)"),
    # ai_items.c
    ("ai_items.c", "            if (holder == 0 || with_partner == 0)\n                return -1;",
     "            if (holder == 0)\n                return -1;"),
    ("ai_items.c", "            if (check_kind != 0 || pass == 1) {", "            if (check_kind != 0) {"),
    ("ai_items.c", "                return (int32_t)(pass * 5u + slot);", "                return (int32_t)(pass * 4u + slot);"),
    ("ai_items.c", "            if (use_kind(ctx, item) != guest_u16(ctx, S_AiHealUse0) && use_kind(ctx, item) != guest_u16(ctx, S_AiHealUse1))",
     "            if (use_kind(ctx, item) != guest_u16(ctx, S_AiHealUse0))"),
    ("ai_items.c", "        if (guest_u16(ctx, item + 2u) & ITEM_SLOT_LOCKED)", "        if (guest_u16(ctx, item + 2u) & 0x4000u)"),
    ("ai_items.c", "        if (use_kind(ctx, item) == guest_u16(ctx, S_AiDopeUse3))\n            return (int32_t)slot;",
     "        if (use_kind(ctx, item) == guest_u16(ctx, S_AiDopeUse2))\n            return (int32_t)slot;"),
    ("ai_items.c", "            if (!(guest_u8(ctx, unit + UNIT_SECRET_BITS + (bit >> 3)) & (1u << (bit & 7u))))",
     "            if (!(guest_u8(ctx, unit + UNIT_SECRET_BITS) & (1u << (bit & 7u))))"),
    ("ai_items.c", "            if ((guest_u8(ctx, holder + UNIT_SECRET_BITS) & 0x08u) &&",
     "            if ((guest_u8(ctx, holder + UNIT_SECRET_BITS) & 0x10u) &&"),
    ("ai_items.c", "            if (guest_call(ctx, AI_UnitCanItemEquip, holder, item, 1u, 1u) == 0)",
     "            if (guest_call(ctx, AI_UnitCanItemEquip, unit, item, 1u, 1u) == 0)"),
    ("ai_items.c", "            if (needs_range != 0 && guest_call2(ctx, AI_UnitGetRangeO, holder, item) == 255)",
     "            if (needs_range != 0 && guest_call2(ctx, AI_UnitGetRangeO, holder, item) >= 254)"),
    ("ai_items.c", "            if (!(guest_u32(ctx, unit + UNIT_AI_FLAGS) & UNIT_AI_PAIR_ROD))\n                return 0;",
     "            if (!(guest_u32(ctx, unit + UNIT_AI_FLAGS) & 0x40u))\n                return 0;"),
    # round 18: the four guard-check bugs h6host r17-host left open (ai_has_heal_rod-001 .. -004); caught only
    # with COLD_STUBS (nested give-ups of IsMagic / GetRangeO) and GIVEUP_GUARDS (a needless give-up)
    ("ai_items.c", "!fe_static_ready(ctx, S_AiMagicGuard) ||\n", "!fe_static_ready(ctx, S_AiMagicGuard) &&\n"),
    ("ai_items.c", "        (needs_range != 0 && !fe_static_ready(ctx, S_AiRangeOGuard)))",
     "        (needs_range == 0 && !fe_static_ready(ctx, S_AiRangeOGuard)))"),
    ("ai_items.c", "        (needs_range != 0 && !fe_static_ready(ctx, S_AiRangeOGuard)))",
     "        (needs_range != 1 && !fe_static_ready(ctx, S_AiRangeOGuard)))"),
    ("ai_items.c", "        (needs_range != 0 && !fe_static_ready(ctx, S_AiRangeOGuard)))",
     "        (needs_range != 0 || !fe_static_ready(ctx, S_AiRangeOGuard)))"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        for f in MINE:
            shutil.copy(os.path.join(SRC_AI, f), os.path.join(d, f))
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
    ap.add_argument("--plant-n", type=int, default=150, help="cases per function for each planted bug")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("ai_perm_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("ai_perm_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_AI)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"ai_perm_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:34s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:34s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("ai_perm_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in M.COVERAGE.items():
        print(f"  {name:34s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"ai_perm_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"ai_perm_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
