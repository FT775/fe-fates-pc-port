#!/usr/bin/env python3
"""Host differential test of the AI attack-score readable code against the game's own ARM code.

    python src/readable/ai_score/tests/ai_score_diff.py             all functions, 300 cases each
    python src/readable/ai_score/tests/ai_score_diff.py -n 1500 --seed 7    the long run
    python src/readable/ai_score/tests/ai_score_diff.py --only rod_can_use_from
    python src/readable/ai_score/tests/ai_score_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/move/tests/move_diff.py (the sheet test's C driver and the ARM interpreter
src/readable/battle/tests/arm_mini.py): for every readable function of src/readable/ai_score/ the test
makes up guest states (an AIBattleSimulator with its four battle sides, units with their items, forces
and pair partners, item records, sub-kind records, a map image with its playable area and unit grid, a
breakable object, the versus configuration, the one-time caches; all random test values, never game
data, and on purpose often outside the ranges the game uses: negative and huge skill numbers, null and
unmapped items, units and records, item numbers 0, debuff bytes of both signs, coordinates and ranges
off the map and far off it, item slots past the five, a playable area that ends before it starts),
runs the ORIGINAL ARM code from the owner's extracted/text.bin in arm_mini.py and the readable C
function (built with the host gcc against tools/readable/stub/) on the same memory, and compares r0,
the number of bytes read from unmapped memory AND the list of guest calls, in order, with their
argument registers (docs/DECISIONS.md F-018). On the ARM side every BL/BLX and every tail branch (B)
to a stubbed callee is listed (also inside callees that run as ARM code); a tail branch to an override
would run on as ARM code, unlisted, as 3dsrecomp inlines it (move_diff.py, round 10 integrate). The
two tail branches met here go to guest functions that are not rewritten (Rod::CanUseDisvalueRange's
into Rod::CanUseTarget, map::Image::Unit::GetUnit's into UnitPool::Get) and are listed as calls on
both sides, as image_unit_at's branch matched live (docs/MOVE.md 9). On the C side every guest call is
listed (one that reaches another override runs that override, as in the capture library). A one-time
cache that is not filled must make the original reach the guard routine and the readable code give up
before reading anything; a nested give-up (a guest call of another readable function giving up inside
while the outer one goes on) is a mismatch.

Guest functions answered by one table on both sides: unit::Item::ToData, Unit::IsEquipSkill,
ItemSubKind::Get, Unit::CanItemEquip, Unit::GetRangeI, Unit::GetRangeO, Force::Get, UnitPool::Get,
Rod::CanUseTarget, WeaponBonus::Get, WeaponLevel::Get, WeaponLevel::GetLevel and Unit::GetPowImpl (the
last listed with its fifth argument, the word at sp, as item_diff.py does since guest_call5, round 11;
the C driver counts the readable code's one store of that word into the dead stack apart, never as a
write of guest data). Item::IsHiddenEffect, map::Image::Unit::GetUnit and Unit::GetWeaponExpLimit run
as ARM code on the ARM side and as their readable overrides (item, move and triangle batches) on the C
side; versus::Config::Get and map::Situation::IsVersus likewise (this batch).

The ARM side models the three VFP instructions IsPower0Attack uses (VLDR of a single, VCMPE.F32,
VMRS APSR_nzcv) in the test's own CPU subclass; the readable code gives up on that path (the float
test), so those cases count as early give-ups.

--plant copies src/readable/ai_score/ to build/readable/ai_score/plant/, makes one small wrong change at
a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch.

PARKED (docs/DECISIONS.md F-025): the sources are src/readable/ai_score/*.c.parked, so no build,
stage or check sees them; this test copies them to build/readable/ai_score/parked_src/ as *.c and
builds only that copy.

Exit 0 only when every case matches (and, with --plant, every planted bug is caught). Needs
extracted/text.bin and a host C compiler (FE_HOST_CC, or the ones tools/readable/check.py looks for);
SKIPs (exit 0, says so) without them.
"""
from __future__ import annotations

import argparse
import os
import random
import shutil
import struct
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
OUT = os.path.join(ROOT, "build", "readable", "ai_score")
SRC_AREA = os.path.join(ROOT, "src", "readable", "ai_score")
PARKED = ".c.parked"  # parked batch (docs/DECISIONS.md F-025, docs/AI_SCORE.md): no stage/build/check walker sees these


def unpark(dst: str) -> str:
    """Copies the parked batch (src/readable/ai_score/, tests left out) to dst with each *.c.parked
    named *.c again, so only this test builds it; nothing else (stage.py, build.py, check.py, the
    other batches' drivers) picks up *.c.parked. Returns dst."""
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(SRC_AREA, dst, ignore=shutil.ignore_patterns("tests"))
    for f in os.listdir(dst):
        if f.endswith(PARKED):
            os.replace(os.path.join(dst, f), os.path.join(dst, f[:-len(PARKED)] + ".c"))
    return dst
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
TO_DATA, IS_EQUIP, SUBKIND_GET = 0x003D0EA4, 0x0052DD04, 0x0019B97C
CAN_EQUIP, RANGE_I, RANGE_O, FORCE_GET = 0x0052C634, 0x00534474, 0x00534510, 0x004F630C
POOL_GET, CAN_USE_TARGET = 0x004F6174, 0x0034AC30
BONUS_GET, LEVEL_GET, GET_LEVEL, POW_IMPL = 0x001A8090, 0x001A80D4, 0x005090A4, 0x0052A500
LEAF_STUBS = {TO_DATA: 1, IS_EQUIP: 2, SUBKIND_GET: 1, CAN_EQUIP: 4, RANGE_I: 2, RANGE_O: 2, FORCE_GET: 1,
              POOL_GET: 1, CAN_USE_TARGET: 3, BONUS_GET: 1, LEVEL_GET: 0, GET_LEVEL: 2, POW_IMPL: 4}

OVERRIDES = {  # name -> address (this batch)
    "ai_sim_is_power0_attack": 0x0050C10C,
    "trick_is_destroy_target_castle_offense": 0x00526B10,
    "versus_config_get": 0x004C5344,
    "situation_is_versus": 0x00528238,
    "rod_can_use_from": 0x0034A8CC,
    "unit_rod_heal_power": 0x0052F008,
}
HIDDEN, GET_UNIT, CONFIG_GET, IS_VERSUS, EXP_LIMIT = 0x00528E90, 0x00526424, 0x004C5344, 0x00528238, 0x0052F824
RANGES = {  # name -> the original's code (functions.csv), for the instruction coverage printed as evidence
    "ai_sim_is_power0_attack": (0x0050C10C, 0x0050C648),
    "trick_is_destroy_target_castle_offense": (0x00526B10, 0x00526B28),
    "versus_config_get": (0x004C5344, 0x004C5354),
    "situation_is_versus": (0x00528238, 0x0052824C),
    "rod_can_use_from": (0x0034A8CC, 0x0034AC30),
    "unit_rod_heal_power": (0x0052F008, 0x0052F1AC),
}
REACHED: dict[str, set] = {}
OTHER_OVERRIDES = (HIDDEN, GET_UNIT, EXP_LIMIT)  # older batches' overrides this batch calls, run on both sides
ARITY = dict(LEAF_STUBS)
# stubbed overrides that fill one-time caches: on the ARM side a cold guard makes the call reach the guard
# routine (the original gives up there, as it would), on the C side it counts as a nested give-up (the
# override would give up inside the caller); so a caller that forgets to ask those guards first is caught
GUARDED_STUBS = {POW_IMPL: (0x006D974C, 0x006D9748, 0x006D9744), RANGE_I: (0x006D9898,), RANGE_O: (0x006D989C,)}
ARITY[POW_IMPL] = 5  # listed with its fifth argument, the word at sp (guest_call5); answered by r0..r3
ARITY.update({HIDDEN: 1, GET_UNIT: 3, CONFIG_GET: 0, IS_VERSUS: 1, EXP_LIMIT: 2})

# globals and caches (src/readable/ai_score/ai_score.h, item.h, sheet.h)
P0_SKILLS = 0x006D0EF8
P0_GUARDS = tuple(0x006D0F40 - 4 * i for i in range(8))
HIDDEN_GUARD, HIDDEN_MASK = 0x006D38D8, 0x006D3928
ROD_AREA_GUARD, ROD_AREA_USE, ROD_REVIVE_GUARD, ROD_REVIVE_USE = 0x006D74C8, 0x006D7466, 0x006D74C4, 0x006D7468
RANGE_GUARDS = (0x006D9898, 0x006D989C)
ROD_SKILL_GUARD, ROD_SKILL, ROD_MAGIC_GUARD, ROD_MAGIC_MASK = 0x006D9918, 0x006D96AC, 0x006D9914, 0x006D9C40
LIMIT_GUARDS = (0x006D97B4, 0x006D97B0, 0x006D97AC)
MAG_GUARDS = (0x006D974C, 0x006D9748, 0x006D9744)  # Unit::GetPowImpl's (formulas.h S_MagGuard0..2)
STONE_MASK, STAFF_MASK, STAFF_FLOOR = 0x006D9A90, 0x006D9A98, 0x006D97B8
G_VERSUS, G_SITUATION, G_MAPIMAGE = 0x006DA318, 0x006D7ED0, 0x006D73E8
ALL_GUARDS = (P0_GUARDS + (HIDDEN_GUARD, ROD_AREA_GUARD, ROD_REVIVE_GUARD, ROD_SKILL_GUARD, ROD_MAGIC_GUARD)
              + RANGE_GUARDS + LIMIT_GUARDS + MAG_GUARDS)
U64_MASKS = (HIDDEN_MASK, ROD_MAGIC_MASK, STONE_MASK, STAFF_MASK)

# guest layout of the made-up state
UNITS = 0x08000000
UNIT = lambda k: UNITS + k * 0x140  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
ITEMDATA = lambda k: 0x08040000 + k * 0x80  # noqa: E731
SUBKINDS = 0x08050000                    # 0x10-byte sub-kind records; ItemSubKind::Get(i) = SUBKINDS + i * 0x10
FORCES = 0x08060000                      # Force records, 12 bytes each
SIM = 0x08100000                         # AIBattleSimulator: 0x900 bytes
TRICK = 0x08200000
VCONF = 0x08300000
MAPIMG = 0x08400000                      # map image: play area bytes 2..5, unit grid +8 (32 x 32)
BONUS = 0x08500000                       # the WeaponBonus row the table answers
LEVELS = 0x08501000                      # the WeaponLevel record the table answers
NUNITS, NITEMS = 6, 8
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
SKILL_IDS = list(range(1, 64))


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sxs16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def guard(st, addr: int, cold_p: float = 0.01) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def cool(st, guards, p: float = 0.03) -> None:
    for g in guards:
        if st.rng.random() < p:
            st.put(g, 4, 0)


def small_s8(rng) -> int:
    return pick(rng, [0, 0, 0, 1, 2, 3, 4, 5, 6, 7, -1, -2, -4], [127, -128, 100, -100, 50], 0.1) & 0xFF


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    for g in ALL_GUARDS:
        guard(st, g)
    for a in U64_MASKS:
        st.put(a, 8, 1 << rng.randrange(64) if rng.random() > 0.05 else rng.randrange(1 << 64))
    for i in range(8):
        st.put(P0_SKILLS + 2 * i, 2, pick(rng, SKILL_IDS, [0, -1, -9, 0x7FFF, -0x8000, 200], 0.08) & 0xFFFF)
    st.put(ROD_AREA_USE, 2, pick(rng, [5, 6], [0, 0x105, 0x8006], 0.3))
    st.put(ROD_REVIVE_USE, 2, pick(rng, [7, 8], [0, 0x107, 0x8008], 0.3))
    st.put(G_VERSUS, 4, 0 if rng.random() < 0.6 else VCONF)
    st.put(G_SITUATION, 4, rng.randrange(1 << 32))
    st.put(ROD_SKILL, 2, pick(rng, SKILL_IDS, [0, -1, 0x7FFF], 0.08) & 0xFFFF)
    st.put(STAFF_FLOOR, 4, pick(rng, [0, 21, 51, 91, 141], [255, 0x7FFFFFFF, 0xFFFFFFFF], 0.05))
    units(st)
    items(st)
    return st


def flags_without_masks(st, base: int) -> None:
    v = word(st, base, 8)
    for m in U64_MASKS:
        v &= ~word(st, m, 8)
    st.put(base, 8, v)


def units(st) -> None:
    rng = st.rng
    for k in range(NUNITS):
        j = JOB(k)
        st.fill(j, 0x80)
        if rng.random() < 0.7:  # flag words: mostly without the masks' bits
            flags_without_masks(st, j)
    for k in range(NUNITS):
        u, p = UNIT(k), PERSON(k)
        st.fill(u, 0x140)
        st.fill(p, 0x80)
        st.put(u + 0x9C, 4, p if rng.random() > 0.03 else rng.choice(UNMAPPED))
        st.put(u + 0xA0, 4, JOB(rng.randrange(NUNITS)) if rng.random() > 0.03 else rng.choice(UNMAPPED))
        for base in (u, p):
            if rng.random() < 0.7:
                flags_without_masks(st, base)
        st.put(u + 0x3D, 1, small_s8(rng))
        st.put(u + 0x3E, 1, small_s8(rng))
        st.put(u + 0xA4, 4, FORCES + 12 * rng.randrange(6) if rng.random() > 0.03 else rng.choice(UNMAPPED))
        st.put(u + 0xA8, 4, 0 if rng.random() < 0.6 else UNIT(rng.randrange(NUNITS)) if rng.random() < 0.9
               else rng.choice(UNMAPPED))


def items(st) -> None:
    rng = st.rng
    st.fill(SUBKINDS - 0x800, 0x1000)
    for i in range(-128, 128):  # ItemSubKind::Get, answered by the table: what its code gives
        st.oracle[(SUBKIND_GET, s32(i))] = s32(SUBKINDS + i * 0x10)
        st.put(SUBKINDS + i * 0x10 + 1, 1, pick(rng, [0, 1, 2, 3, 4, 5, 6, 7], [3, 255], 0.2))
    for k in range(NITEMS):
        r = ITEMDATA(k)
        st.fill(r, 0x80)
        st.put(r + 0x1A, 1, pick(rng, list(range(20)), [19, 0x80, 0xFF], 0.15))
        st.put(r + 0x1B, 1, pick(rng, [5, 6, 7, 8, 1, 2], [0, 255], 0.05))
        st.put(r + 0x1F, 1, pick(rng, [0, 10, 15, 20, 30], [255, 1], 0.1))
        st.put(r + 0x46, 1, small_s8(rng))
        st.put(r + 0x47, 1, small_s8(rng))
        v = word(st, r, 8)
        for m in U64_MASKS:
            if rng.random() < 0.7:
                v &= ~word(st, m, 8)
        st.put(r, 8, v)


def item_answer(st) -> int:
    rng = st.rng
    return ITEMDATA(rng.randrange(NITEMS)) if rng.random() > 0.05 else rng.choice(UNMAPPED)


def answer_skills(st, u: int, skills, p: float) -> None:
    for sk in skills:
        st.oracle[(IS_EQUIP, s32(u), s32(sxs16(word(st, sk, 2))))] = int(st.rng.random() < p)


def unit_ptr(st, p_unmapped: float = 0.05) -> int:
    return st.rng.choice(UNMAPPED) if st.rng.random() < p_unmapped else UNIT(st.rng.randrange(NUNITS))


def ov(name, args):
    a = OVERRIDES[name]
    return f"ov:0x{a:08X}", [s32(x) for x in args] + [0] * (4 - len(args)), ("call", a)


# ------------------------------------------------------------------ the functions
def gen_power0(rng):
    st = base_state(rng)
    cool(st, P0_GUARDS + (HIDDEN_GUARD,), 0.01)
    s = SIM
    st.fill(s, 0x900)
    st.put(s + 0x814, 4, 0 if rng.random() < 0.8 else pick(rng, [1, 2, 3], [0x7FFFFFFF, 0xFFFFFFFF, 0x80000000]))
    st.put(s + 0x820, 4, struct.unpack("<I", struct.pack("<f", pick(rng, [0.0, 0.25, 0.5, 1.0, -0.5],
                                                                     [float("nan"), -0.0])))[0])
    st.put(s + 0x244, 4, 0 if rng.random() < 0.75 else pick(rng, [1, 2], [0x7FFFFFFF, 0xFFFFFFFF, 0x80000000]))
    st.put(s + 0x444, 4, 0 if rng.random() < 0.5 else pick(rng, [1, 2], [0xFFFFFFFF, 0x80000000]))
    for item in (s + 0x18, s + 0x418):
        st.put(item, 2, 0 if rng.random() < 0.15 else rng.randrange(1, 1 << 16))
        st.oracle[(TO_DATA, s32(item))] = item_answer(st)
    st.oracle[(TO_DATA, 0)] = item_answer(st)
    for k in range(NITEMS):  # focused: concealed weapons (weapon kind byte 19) often, debuffs of both signs
        if rng.random() < 0.5:
            st.put(ITEMDATA(k) + 0x1A, 1, 19)
    for i in range(0x2EE - 0x20, 0x2EE + 0x20):  # side 1's skill bits: mostly clear
        st.mem[s + i] = 0 if rng.random() < 0.6 else rng.randrange(256)
    attacker = unit_ptr(st)
    target = 0 if rng.random() < 0.1 else unit_ptr(st)
    st.put(s, 4, attacker)
    st.put(s + 4, 4, target)
    answer_skills(st, attacker, [P0_SKILLS + 2 * i for i in range(8)], rng.choice([0.0, 0.12, 0.3]))
    if rng.random() < 0.5:
        power0_deep(st, attacker)
    obj = s if rng.random() > 0.03 else rng.choice(UNMAPPED)
    return (st,) + ov("ai_sim_is_power0_attack", [obj])


def power0_deep(st, attacker: int) -> None:
    """Half the IsPower0Attack cases go past every early exit to the debuff path: caches warm, no float
    test, side 1's +0x3C not above 0, none of the three "always hits" skills; then concealed weapons on
    both sides with debuffs of both signs, the seal / status / chain skills often, and the target's own
    lowered Defence / Resistance near the numbers the code compares with (so an off-by-one shows)."""
    rng, s = st.rng, SIM
    for g in P0_GUARDS + (HIDDEN_GUARD,):
        st.put(g, 4, 1)
    st.put(s + 0x814, 4, pick(rng, [0], [0xFFFFFFFF, 0x80000000], 0.1))
    st.put(s + 0x244, 4, pick(rng, [0], [0xFFFFFFFF, 0x80000000], 0.1))
    st.put(s + 0x444, 4, 0 if rng.random() < 0.4 else pick(rng, [1, 2], [0x7FFFFFFF], 0.1))
    debuffs = [-3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 12]
    for item in (s + 0x18, s + 0x418):
        st.put(item, 2, 0 if rng.random() < 0.05 else rng.randrange(1, 1 << 16))
        k = rng.randrange(NITEMS)
        st.oracle[(TO_DATA, s32(item))] = ITEMDATA(k)
        if rng.random() < 0.85:
            st.put(ITEMDATA(k) + 0x1A, 1, 19)
        st.put(ITEMDATA(k) + 0x46, 1, rng.choice(debuffs) & 0xFF)
        st.put(ITEMDATA(k) + 0x47, 1, rng.choice(debuffs) & 0xFF)
    k = rng.randrange(NITEMS)
    st.oracle[(TO_DATA, 0)] = ITEMDATA(k)
    skill = [sxs16(word(st, P0_SKILLS + 2 * i, 2)) for i in range(8)]
    p_yes = [0.4, 0.4, 0.0, 0.0, 0.03, 0.03, 0.03, 0.3]  # seal Def / Res, (status: bits), venom, fangs, breath, chain
    for i in range(8):
        st.oracle[(IS_EQUIP, s32(attacker), s32(skill[i]))] = int(rng.random() < p_yes[i])
    for i in range(0x2EE - 0x20, 0x2EE + 0x20):  # side 1's skill bits: clear, then the two status skills
        st.mem[s + i] = 0
    for i, p in ((2, 0.4), (3, 0.15)):
        if rng.random() < p:
            a = s + 0x2EE + (skill[i] >> 3)
            st.mem[a] = st.mem.get(a, 0) | (1 << (skill[i] & 7))
    target = UNIT(rng.randrange(NUNITS)) if rng.random() > 0.05 else 0
    st.put(s + 4, 4, target)
    if target:
        st.put(target + 0x3D, 1, rng.randrange(-4, 9) & 0xFF)
        st.put(target + 0x3E, 1, rng.randrange(-4, 9) & 0xFF)


def gen_castle_offense(rng):
    st = base_state(rng)
    st.fill(TRICK, 0x40)
    st.put(TRICK + 0xC, 1, pick(rng, list(range(10, 28)), [0, 255, 128, 14, 15, 22, 23], 0.2))
    t = TRICK if rng.random() > 0.05 else rng.choice(UNMAPPED)
    return (st,) + ov("trick_is_destroy_target_castle_offense", [t])


def gen_config(rng):
    st = base_state(rng)
    if rng.random() < 0.1:
        del st.mem[G_VERSUS]  # one byte unmapped on purpose (the page stays)
    return (st,) + ov("versus_config_get", [])


def gen_is_versus(rng):
    st = base_state(rng)
    if rng.random() < 0.05:
        st.put(G_VERSUS, 4, rng.randrange(1 << 32))
    return (st,) + ov("situation_is_versus", [rng.randrange(1 << 32)])


def map_image(st) -> None:
    rng = st.rng
    st.put(G_MAPIMAGE, 4, MAPIMG if rng.random() > 0.03 else rng.choice(UNMAPPED))
    st.fill(MAPIMG, 8)
    lo, hi = [1, 0, 2], [15, 20, 24, 31, 32]
    for off, pool in ((2, lo), (3, lo), (4, hi), (5, hi)):  # play area: sometimes odd (an end before the start)
        st.put(MAPIMG + off, 1, pick(rng, pool, [0, 1, 5, 33, 40], 0.1))
    for i in range(1024):  # the unit grid: mostly empty
        r = rng.random()
        st.mem[MAPIMG + 8 + i] = 0 if r < 0.75 else rng.randrange(1, NUNITS + 1) if r < 0.98 else rng.randrange(256)
    for n in range(256):  # UnitPool::Get, answered by the table: what its code gives
        st.oracle[(POOL_GET, n)] = 0 if n == 0 else s32(UNITS + (n - 1) * 0x140)
    for f in range(6):
        st.fill(FORCES + 12 * f, 12)
        st.put(FORCES + 12 * f + 8, 1, pick(rng, [0, 0, 1, 2, 3, 4], [255], 0.05))


def gen_rod(rng):
    st = base_state(rng)
    cool(st, (ROD_AREA_GUARD, ROD_REVIVE_GUARD) + RANGE_GUARDS, 0.015)
    map_image(st)
    unit = unit_ptr(st, 0.04)
    slot = pick(rng, [0, 1, 2, 3, 4], [5, 7, -1, 100], 0.05)
    item = s32(unit + 0x108 + 4 * slot)
    rec = item_answer(st)
    st.oracle[(TO_DATA, item)] = rec
    if ITEMDATA(0) <= rec < ITEMDATA(NITEMS) and rng.random() < 0.8:  # focused: a staff of one of the uses
        k = (rec - ITEMDATA(0)) // 0x80
        st.put(SUBKINDS + 0x10 * k + 1, 1, 6)
        st.put(rec + 0x1A, 1, k)
        st.put(rec + 0x1B, 1, rng.choice([word(st, ROD_AREA_USE, 2) & 0xFF, word(st, ROD_AREA_USE, 2) & 0xFF,
                                          word(st, ROD_REVIVE_USE, 2) & 0xFF, 1]))
    if UNITS <= unit < UNIT(NUNITS) and rng.random() < 0.8:
        st.put(unit + 0x28, 1, word(st, unit + 0x28, 1) & ~8)
    st.oracle[(CAN_EQUIP, s32(unit), item, 1, 1)] = int(rng.random() < 0.85)
    st.oracle[(RANGE_I, s32(unit), item)] = pick(rng, [0, 1, 1, 2], [3, -1, 50, 0x7FFFFFFF], 0.08) & 0xFFFFFFFF
    st.oracle[(RANGE_O, s32(unit), item)] = pick(rng, [1, 2, 3, 5, 7, 10],
                                                 [0, -1, 40, 0x7FFFFFFF, -0x80000000], 0.08) & 0xFFFFFFFF
    st.oracle[(FORCE_GET, 4)] = FORCES + 12 * 4 if rng.random() > 0.05 else rng.choice(UNMAPPED)
    st.put(FORCES + 12 * 4 + 4, 4, 0 if rng.random() < 0.3 else UNIT(rng.randrange(NUNITS)))
    p_yes = rng.choice([0.0, 0.02, 0.1, 0.5])
    for t in [UNIT(k) for k in range(NUNITS)] + [0] + UNMAPPED + [word(st, UNIT(k) + 0xA8) for k in range(NUNITS)]:
        st.oracle[(CAN_USE_TARGET, s32(unit), s32(slot), s32(t))] = int(rng.random() < p_yes)
    odd = [-1, -5, 32, 40, 255, 1000, 0x7FFFFFFF, -0x80000000, 0x7FFFFFFD, 65540, 0x7FFF0, -65536]
    x = s32(pick(rng, list(range(32)), odd, 0.2))
    y = s32(pick(rng, list(range(32)), odd, 0.2))
    if rng.random() < 0.08:  # focused: a tile near the 32-bit top with a very low reach, so x - reach leaves
        # 16 bits and the distance wraps below 0 (only the game's SXTH bounds then scan near tile 0)
        x = s32(rng.choice([0x7FFFFFFD, 0x7FFFFFFA, 0x7FFFFFF0]))
        y = s32(rng.randrange(2, 20))
        st.oracle[(RANGE_I, s32(unit), item)] = s32(-0x80000000)
        st.oracle[(RANGE_O, s32(unit), item)] = rng.choice([3, 5, 7, 10, 20])
        if ITEMDATA(0) <= rec < ITEMDATA(NITEMS):
            k = (rec - ITEMDATA(0)) // 0x80
            st.put(SUBKINDS + 0x10 * k + 1, 1, 6)
            st.put(rec + 0x1A, 1, k)
            st.put(rec + 0x1B, 1, word(st, ROD_AREA_USE, 2) & 0xFF)
            if UNITS <= unit < UNIT(NUNITS):
                st.put(unit + 0x28, 1, word(st, unit + 0x28, 1) & ~8)
            st.oracle[(CAN_EQUIP, s32(unit), item, 1, 1)] = 1
    return (st,) + ov("rod_can_use_from", [unit, slot, x, y])


def gen_heal(rng):
    st = base_state(rng)
    cool(st, (ROD_SKILL_GUARD, ROD_MAGIC_GUARD) + LIMIT_GUARDS + MAG_GUARDS, 0.015)
    unit = unit_ptr(st, 0.04)
    item = s32(unit + 0x108 + 4 * rng.randrange(5)) if rng.random() > 0.05 else rng.choice([0] + UNMAPPED)
    st.oracle[(TO_DATA, item)] = item_answer(st)
    rec = st.oracle[(TO_DATA, item)]
    if ITEMDATA(0) <= rec < ITEMDATA(NITEMS) and rng.random() < 0.3:  # focused: the "+ magic / 3" flag
        st.put(rec, 8, word(st, rec, 8) | word(st, ROD_MAGIC_MASK, 8))
    if UNITS <= unit < UNIT(NUNITS):
        st.put(unit + 0xEE, 1, pick(rng, [0, 1, 20, 21, 50, 51, 90, 91, 140, 141, 200], [255], 0.05))
    st.oracle[(BONUS_GET, 6)] = BONUS if rng.random() > 0.04 else rng.choice(UNMAPPED)
    st.fill(BONUS, 0x40)
    st.oracle[(LEVEL_GET,)] = LEVELS
    for m in range(-1, 256):  # WeaponLevel::GetLevel(levels, exp): a rank 0..5 (rarely odd)
        st.oracle[(GET_LEVEL, LEVELS, s32(m))] = pick(rng, [0, 1, 2, 3, 4, 5], [-1, 6, 0x40], 0.03) & 0xFFFFFFFF
    st.oracle[(POW_IMPL, s32(unit), 0, 1, 1)] = pick(rng, [0, 5, 12, 30, 31, 32], [-3, -4, 0x7FFFFFFF, -0x80000000]) & 0xFFFFFFFF
    target = 0 if rng.random() < 0.3 else unit_ptr(st)
    answer_skills(st, target, [ROD_SKILL], 0.4)
    return (st,) + ov("unit_rod_heal_power", [unit, item, target])


FUNCS = {
    "ai_sim_is_power0_attack": gen_power0,
    "trick_is_destroy_target_castle_offense": gen_castle_offense,
    "versus_config_get": gen_config,
    "situation_is_versus": gen_is_versus,
    "rod_can_use_from": gen_rod,
    "unit_rod_heal_power": gen_heal,
}

# ------------------------------------------------------------------ the ARM side
def f32(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits & 0xFFFFFFFF))[0]


class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX and every tail branch (B) to a callee of ARITY (stubbed
    or run as ARM code) with its argument registers; with the three VFP instructions of
    IsPower0Attack, which arm_mini does not model."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []
        self.s = [0] * 32
        self.fp_nzcv = (0, 0, 0, 0)
        self.reach = None  # (start, end, set of pcs reached) of the function under test

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            n = ARITY[target]
            regs = list(self.r[:min(n, 4)]) + [self.mem.read(self.r[13] + 4 * k, 4) for k in range(n - 4)]
            self.listed.append(call_text(target, regs))
        return super().call(target, ret)

    def step(self, ins: int, pc: int) -> None:
        if self.reach is not None and self.reach[0] <= pc < self.reach[1]:
            self.reach[2].add(pc)
        c = ins >> 28
        if c != 0xF and self.cond(c):
            if (ins >> 24) & 0xF == 0xA:  # B (no link): a tail call when it reaches a listed callee
                target = (pc + 8 + (A.sx(ins & 0xFFFFFF, 24) << 2)) & A.MASK
                stub = self.stubs.get(target)
                if target in ARITY and stub is not None:
                    self.listed.append(call_text(target, self.r[:ARITY[target]]))
                    self.r[0] = stub(self, tuple(self.r[:4])) & A.MASK
                    self.r[15] = self.r[14]
                    return
                # a tail branch to an override runs on as ARM code, unlisted (move_diff.py, round 10)
            if (ins & 0x0F300F00) == 0x0D100A00:  # VLDR Sd, [Rn, #+/-imm*4]
                d = ((ins >> 12) & 0xF) << 1 | ((ins >> 22) & 1)
                rn = (ins >> 16) & 0xF
                base = ((pc + 8) & ~3) if rn == 15 else self.r[rn]
                off = (ins & 0xFF) * 4
                addr = (base + off if ins & (1 << 23) else base - off) & A.MASK
                self.s[d] = self.mem.read(addr, 4)
                return
            if (ins & 0x0FBF0F50) == 0x0EB40A40:  # VCMP(E).F32 Sd, Sm
                d = ((ins >> 12) & 0xF) << 1 | ((ins >> 22) & 1)
                m = (ins & 0xF) << 1 | ((ins >> 5) & 1)
                a, b = f32(self.s[d]), f32(self.s[m])
                if a != a or b != b:
                    self.fp_nzcv = (0, 0, 1, 1)
                elif a == b:
                    self.fp_nzcv = (0, 1, 1, 0)
                elif a < b:
                    self.fp_nzcv = (1, 0, 0, 0)
                else:
                    self.fp_nzcv = (0, 0, 1, 0)
                return
            if (ins & 0x0FFFFFFF) == 0x0EF1FA10:  # VMRS APSR_nzcv, FPSCR
                self.n, self.z, self.c, self.v = self.fp_nzcv
                return
        super().step(ins, pc)


def call_text(target: int, regs) -> str:
    return f"{target:x}" + "".join(f":{r & 0xFFFFFFFF:x}" for r in regs)


def calls_field(listed: list[str]) -> str:
    return ",".join(listed) if listed else "-"


def arm_run(text: bytes, st, kind: str, args: list[int], how: tuple, name: str | None = None) -> list:
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def answer(f, n):
        return lambda cpu, a: st.oracle.get((f,) + tuple(x & 0xFFFFFFFF for x in a[:n]), 0)
    stubs = {f: answer(f, n) for f, n in LEAF_STUBS.items()}

    def guarded(f, inner):
        def stub(cpu, a):
            if any(not (cpu.mem.read(g, 4) & 1) for g in GUARDED_STUBS[f]):
                raise A.ColdGuard()
            return inner(cpu, a)
        return stub
    for f in GUARDED_STUBS:
        stubs[f] = guarded(f, stubs[f])
    cpu = ListingCpu(mem, stubs, guard=GUARD)
    if name in RANGES:
        cpu.reach = RANGES[name] + (REACHED.setdefault(name, set()),)
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
/* Generated by src/readable/ai_score/tests/ai_score_diff.py: runs readable AI attack-score functions
   on memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ai_score.h"
'''

# the stub list the C driver is told per case (GetPowImpl is listed in LEAF_STUBS too: unit_rod_heal_power
# reaches it through guest_call5; GUARDED_STUBS adds its cache guards)
C_STUBS = {f: n for f, n in LEAF_STUBS.items()}


STACK_DRIVER_OLD = (
    "static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; writes++; uint8_t *p = at(a, 0); if (p) *p = v; }",
    "    for (uint32_t i = 0; i < n; i++) k += snprintf(buf + k, sizeof buf - (size_t)k, \":%x\", r[i]);",
    "            c.r[13] = a[4];",
    "    char buf[96];",
    "static void oracle(Context *ctx) {\n    uint32_t f = ctx->r[15], n = 0;",
    "        } else if (!strncmp(line, \"stub \", 5)) {",
    "noracle = 0; nstubs = 0;",
)
STACK_DRIVER_NEW = (
    # guest_call5 (round 11): a store into the dead stack (the 0x400 bytes below the case's sp) is the fifth
    # argument word of a call, not a write of guest data: counted apart, never as WROTE-GUEST
    "static uint32_t stack_top; static int stack_writes;\n"
    "static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; if (a < stack_top && a >= stack_top - 0x400u) "
    "stack_writes++; else writes++; uint8_t *p = at(a, 0); if (p) *p = v; }",
    # an argument past r3 is the word at sp + 4 * (n - 4), as the callee sees it
    "    for (uint32_t i = 0; i < n; i++) k += snprintf(buf + k, sizeof buf - (size_t)k, \":%x\", "
    "i < 4 ? r[i] : r32(NULL, r[13] + 4u * (i - 4u)));",
    "            c.r[13] = a[4]; stack_top = a[4]; stack_writes = 0;",
    "    char buf[128];",
    # a guarded stub (GUARDED_STUBS) with a cold guard: the override would give up inside the caller
    "static int nested; static uint32_t sg_f[16], sg_a[16]; static int nsg;\n"
    "static void oracle(Context *ctx) {\n    uint32_t f = ctx->r[15], n = 0;\n"
    "    for (int i = 0; i < nsg; i++) if (sg_f[i] == f && !(r32(ctx, sg_a[i]) & 1u)) nested++;",
    "        } else if (!strncmp(line, \"sguard \", 7)) {\n"
    "            if (nsg < 16) { sscanf(line + 7, \"%x %x\", &sg_f[nsg], &sg_a[nsg]); nsg++; }\n"
    "        } else if (!strncmp(line, \"stub \", 5)) {",
    "noracle = 0; nstubs = 0; nsg = 0;",
)


def driver_text() -> str:
    sys.path.insert(0, os.path.join(ROOT, "src", "readable", "sheet", "tests"))
    import sheet_diff as S  # the same driver body: page memory, call list, oracle, nested give-ups
    body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
    for old, new in zip(STACK_DRIVER_OLD, STACK_DRIVER_NEW):
        if body.count(old) != 1:
            raise SystemExit(f"ai_score_diff: sheet_diff's driver changed, cannot patch: {old[:60]!r}")
        body = body.replace(old, new)
    addrs = sorted(set(OVERRIDES.values()) | set(OTHER_OVERRIDES))
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in addrs)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in addrs) + "};\n"
    return DRIVER_HEAD + body.replace("@OVERRIDE_DECLS@", decls + table)


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


_OTHER_OBJS: dict = {}


def build_driver(cc: str, out: str, area_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, this folder's taken from area_dir
    (a planted bug may leave a parameter unused: not strict then, warnings are not errors)."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "ai_score_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_AREA)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(area_dir, f) for f in os.listdir(area_dir) if f.endswith(".c")]
    exe = os.path.join(out, "ai_score_driver.exe" if os.name == "nt" else "ai_score_driver")
    inc = ["-I", area_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    # Strict warnings for this folder and the driver only: other folders are compiled apart with
    # warnings off, so a batch being written at the same time (its warnings are its own check.py's
    # business) does not stop this test. Errors anywhere still stop it.
    warn = ["-Wall", "-Wextra", "-Werror"] if strict else ["-w"]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    mine = [src] + [s for s in sources if os.path.normcase(os.path.dirname(s)) == os.path.normcase(area_dir)]
    others = sorted(s for s in sources if s not in mine)

    def compile_all(group, flags, objdir, may_skip=False):
        shutil.rmtree(objdir, ignore_errors=True)
        os.makedirs(objdir)
        objs = []
        for k, s in enumerate(group):
            obj = os.path.join(objdir, f"{k}_{os.path.splitext(os.path.basename(s))[0]}.o")
            r = subprocess.run([cc, "-std=c11"] + flags + ["-O1", "-fwrapv"] + inc + ["-c", s, "-o", obj],
                               capture_output=True, text=True, env=env)
            if r.returncode and may_skip:
                # another batch's file that does not compile right now (being written at the same time):
                # left out and named; if this test needed it, the link below fails and says so
                print(f"  note: left out {os.path.relpath(s, ROOT)} (does not compile now; not this batch's file)")
                continue
            if r.returncode:
                raise SystemExit(f"ai_score_diff: building the C driver failed ({s}):\n{r.stdout}{r.stderr}")
            objs.append(obj)
        return objs
    if _OTHER_OBJS.get("key") != (cc, tuple(others)):  # the other folders: once per run of this script
        _OTHER_OBJS["objs"] = compile_all(others, ["-w"], os.path.join(OUT, "obj_others"), may_skip=True)
        _OTHER_OBJS["key"] = (cc, tuple(others))
    objs = _OTHER_OBJS["objs"] + compile_all(mine, warn, os.path.join(out, "obj_mine"))
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"ai_score_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
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
                exp = arm_run(text, st, kind, args, how, name)
            except A.Unsupported as e:
                unsupported[name] = unsupported.get(name, 0) + 1
                if unsupported[name] == 1:
                    print(f"  ARM interpreter: {name}: {e}")
                continue
            expected[cid] = (name, exp, (kind, args))
            lines.append(f"case {cid} {kind} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
            lines += [f"stub {f:x} {k}" for f, k in C_STUBS.items()]
            lines += [f"sguard {f:x} {g:x}" for f, gs in GUARDED_STUBS.items() for g in gs]
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
        raise SystemExit(f"ai_score_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
            # an early give-up: a needed cache is cold, or the path needs what readable C does not do
            # (VFP, a stack argument); the readable code stops before any unmapped read; always safe
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
    # ai_score_sim.c: IsPower0Attack
    ("ai_score_sim.c", "    for (int i = 0; i < P0_SKILLS; i++)", "    for (int i = 0; i < P0_SKILLS - 1; i++)"),
    ("ai_score_sim.c", "    if (!fe_static_ready(ctx, S_P0HiddenGuard))\n        return fe_use_original(ctx);\n", ""),
    ("ai_score_sim.c", "    if (guest_s32(ctx, sim + SIM_SIDE1_COUNT) > 0)", "    if (guest_s32(ctx, sim + SIM_SIDE1_COUNT) >= 0)"),
    ("ai_score_sim.c", "        attacker_has(ctx, sim, P0_DEATH_BREATH))", "        attacker_has(ctx, sim, P0_NEGATIVE_CHAIN))"),
    ("ai_score_sim.c", "    gaddr arg = guest_u16(ctx, item) != 0 ? item : 0u;", "    gaddr arg = item;"),
    ("ai_score_sim.c", "    if (v > *def)\n        *def = v;", "    *def = v;"),
    ("ai_score_sim.c", "    v = guest_s8(ctx, record + ITEM_DEBUFF_RES);", "    v = guest_s8(ctx, record + ITEM_DEBUFF_DEF);"),
    ("ai_score_sim.c", "    if (guest_s32(ctx, sim + SIM_SIDE2_COUNT) > 0)\n", "    if (guest_s32(ctx, sim + SIM_SIDE2_COUNT) > -1000)\n"),
    ("ai_score_sim.c", "#include \"ai_score.h\"\n", "#include \"ai_score.h\"\n#undef P0_SEAL_AMOUNT\n#define P0_SEAL_AMOUNT 5\n"),
    ("ai_score_sim.c", "    if (side1_has(ctx, sim, (int32_t)p0_skill(ctx, P0_STATUS_IMMUNE))) {",
     "    if (side1_has(ctx, sim, (int32_t)p0_skill(ctx, P0_STATUS_RESIST))) {"),
    ("ai_score_sim.c", "    return (byte & (1u << ((uint32_t)skill & 7u))) != 0;", "    return (byte & (0x80u >> ((uint32_t)skill & 7u))) != 0;"),
    ("ai_score_sim.c", "        def = fe_asr(def, 1);", "        def = fe_asr(def, 2);"),
    ("ai_score_sim.c", "        return (def - 1 > 0 || res - 1 > 0) ? 0u : 1u;", "        return (def > 0 || res - 1 > 0) ? 0u : 1u;"),
    ("ai_score_sim.c", "    if (guest_s8(ctx, target + UNIT_DEBUFF_DEF) < def - 1)", "    if (guest_s8(ctx, target + UNIT_DEBUFF_DEF) <= def - 1)"),
    ("ai_score_sim.c", "    if (guest_s8(ctx, target + UNIT_DEBUFF_RES) < res - 1)", "    if (guest_u8(ctx, target + UNIT_DEBUFF_RES) < res - 1)"),
    ("ai_score_sim.c", "    if (guest_ptr(ctx, sim + SIM_TARGET) == 0)\n        return 1;", "    if (guest_ptr(ctx, sim + SIM_TARGET) == 0)\n        return 0;"),
    ("ai_score_sim.c", "        return fe_use_original(ctx); /* the float test */", "        return 0; /* the float test */"),
    # the other three
    ("ai_score_sim.c", "    return type - TRICK_CASTLE_OFFENSE_FIRST <= TRICK_CASTLE_OFFENSE_SPAN ? 1u : 0u;",
     "    return type - TRICK_CASTLE_OFFENSE_FIRST < TRICK_CASTLE_OFFENSE_SPAN ? 1u : 0u;"),
    ("ai_score_sim.c", "    return guest_ptr(ctx, G_VersusConfig);", "    return guest_ptr(ctx, G_VersusConfig + 4u);"),
    ("ai_score_sim.c", "    return guest_call(ctx, AS_VersusConfigGet, 0u, 0u, 0u, 0u) != 0 ? 1u : 0u;",
     "    return guest_ptr(ctx, G_VersusConfig) != 0 ? 1u : 0u;"),
    # ai_score_heal.c
    ("ai_score_heal.c", "        !fe_static_ready(ctx, S_RodLimitGuardC) || !unit_stat_caches_ready(ctx, AS_STAT_MAG))",
     "        !fe_static_ready(ctx, S_RodLimitGuardC))"),
    ("ai_score_heal.c", "    int32_t heal = guest_u8(ctx, record + ITEM_HEAL);", "    int32_t heal = guest_s8(ctx, record + ITEM_HEAL);"),
    ("ai_score_heal.c", "        heal = fe_add32(heal, magic / 3);", "        heal = fe_add32(heal, fe_asr(magic, 1) - fe_asr(magic, 3));"),
    ("ai_score_heal.c", "guest_call5(ctx, AS_UnitGetPowImpl, unit, 0u, 1u, 1u, 0u)", "guest_call5(ctx, AS_UnitGetPowImpl, unit, 0u, 1u, 1u, 1u)"),
    ("ai_score_heal.c", "    int32_t capped = limit < exp ? limit : exp;", "    int32_t capped = limit > exp ? limit : exp;"),
    ("ai_score_heal.c", "    heal = fe_add32(heal, guest_s8(ctx, bonus + ((gaddr)rank << 1)));",
     "    heal = fe_add32(heal, guest_s8(ctx, bonus + (gaddr)rank));"),
    ("ai_score_heal.c", "        heal = fe_add32(heal, fe_asr(heal, 1));", "        heal = fe_add32(heal, fe_asr(heal, 2));"),
    ("ai_score_heal.c", "    if (target != 0 &&\n", "    if (\n"),
    ("ai_score_heal.c", "    gaddr bonus = guest_call1(ctx, AS_WeaponBonusGet, STAFF_KIND);\n    int32_t exp = guest_u8(ctx, unit + UNIT_STAFF_EXP);\n    int32_t limit = (int32_t)guest_call2(ctx, AS_UnitGetWeaponExpLimit, unit, STAFF_KIND);",
     "    int32_t exp = guest_u8(ctx, unit + UNIT_STAFF_EXP);\n    int32_t limit = (int32_t)guest_call2(ctx, AS_UnitGetWeaponExpLimit, unit, STAFF_KIND);\n    gaddr bonus = guest_call1(ctx, AS_WeaponBonusGet, STAFF_KIND);"),
    # ai_score_rod.c
    ("ai_score_rod.c", "        !fe_static_ready(ctx, S_RodRangeIGuard) || !fe_static_ready(ctx, S_RodRangeOGuard))",
     "        !fe_static_ready(ctx, S_RodRangeIGuard))"),
    ("ai_score_rod.c", "    gaddr item = unit + (gaddr)slot * 4u + UNIT_ITEMS;", "    gaddr item = unit + (gaddr)slot * 2u + UNIT_ITEMS;"),
    ("ai_score_rod.c", "    if (READ_FIELD(ctx, ItemSubKindData, sub, kind) != STAFF_KIND)",
     "    if (READ_FIELD(ctx, ItemSubKindData, sub, kind) != 5u)"),
    ("ai_score_rod.c", "    if (guest_u8(ctx, unit + UNIT_CONDITION_BYTE) & UNIT_CONDITION_NO_STAFF)",
     "    if (guest_u8(ctx, unit + UNIT_CONDITION_BYTE) & 0x10u)"),
    ("ai_score_rod.c", "    if (guest_call(ctx, AS_UnitCanItemEquip, unit, item, 1u, 1u) == 0)",
     "    if (guest_call(ctx, AS_UnitCanItemEquip, unit, item, 1u, 0u) == 0)"),
    # the second ToData not asked again (the game asks it twice): one call fewer
    ("ai_score_rod.c", "    use = guest_u8(ctx, guest_call1(ctx, AS_ItemToData, item) + ITEM_USE);\n", ""),
    # the cached ItemUse numbers read as one byte instead of 16 bits (a high byte not 0 then matches)
    ("ai_score_rod.c", "    if (use == guest_u16(ctx, S_RodReviveUse)) {", "    if (use == guest_u8(ctx, S_RodReviveUse)) {"),
    ("ai_score_rod.c", "    if (use == guest_u16(ctx, S_RodAreaUse))", "    if (use == guest_u8(ctx, S_RodAreaUse))"),
    ("ai_score_rod.c", "    return (int16_t)(a >= b ? a : b);", "    return a >= b ? a : b;"),
    ("ai_score_rod.c", "    return (int16_t)(a <= b ? a : b);", "    return (int16_t)(a < b ? b : a);"),
    ("ai_score_rod.c", "                               (int32_t)guest_u8(ctx, guest_ptr(ctx, G_MapImage) + MAPIMAGE_PLAY_X_END) - 1);",
     "                               (int32_t)guest_u8(ctx, guest_ptr(ctx, G_MapImage) + MAPIMAGE_PLAY_X_END));"),
    ("ai_score_rod.c", "    int32_t y_lo = bound_max16(sub32(y, rmax), guest_u8(ctx, guest_ptr(ctx, G_MapImage) + MAPIMAGE_PLAY_Y_MIN));",
     "    int32_t y_lo = bound_max16(sub32(y, rmin), guest_u8(ctx, guest_ptr(ctx, G_MapImage) + MAPIMAGE_PLAY_Y_MIN));"),
    ("ai_score_rod.c", "            if (d < rmin || rmax < d)", "            if (d <= rmin || rmax < d)"),
    ("ai_score_rod.c", "            int32_t d = fe_add32(abs32(sub32(x, tx)), abs32(sub32(y, ty)));",
     "            int32_t d = fe_add32(sub32(x, tx), abs32(sub32(y, ty)));"),
    ("ai_score_rod.c", "            if (partner != 0 && guest_call3(ctx, AS_RodCanUseTarget, unit, (uint32_t)slot, partner) != 0)",
     "            if (partner != 0 && guest_call3(ctx, AS_RodCanUseTarget, unit, (uint32_t)slot, there) != 0)"),
    ("ai_score_rod.c", "    gaddr grid = guest_ptr(ctx, G_MapImage) + MAPIMAGE_UNITS;", "    gaddr grid = guest_ptr(ctx, G_MapImage);"),
    ("ai_score_rod.c", "        if (guest_call1(ctx, AS_SituationIsVersus, guest_ptr(ctx, G_Situation)) != 0)",
     "        if (guest_call1(ctx, AS_SituationIsVersus, G_Situation) != 0)"),
    ("ai_score_rod.c", "        if (guest_u8(ctx, guest_ptr(ctx, unit + UNIT_FORCE) + FORCE_TYPE) != 0)",
     "        if (guest_u8(ctx, guest_ptr(ctx, unit + UNIT_FORCE) + FORCE_TYPE) > 1)"),
    ("ai_score_rod.c", "        return (guest_u32(ctx, first + UNIT_STATE_FLAGS) & 0x80u) != 0 ? 1u : 0u;",
     "        return (guest_u32(ctx, first + UNIT_STATE_FLAGS) & 0x40u) != 0 ? 1u : 0u;"),
    ("ai_score_rod.c", "    return guest_call3(ctx, AS_RodCanUseTarget, unit, (uint32_t)slot, there);",
     "    return guest_call3(ctx, AS_RodCanUseTarget, unit, (uint32_t)x, there);"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = unpark(os.path.join(OUT, "plant", "src"))
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
    ap.add_argument("--unreached", action="store_true", help="list the original's words no case reached")
    ap.add_argument("--plant-n", type=int, default=150, help="cases per function for each planted bug")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("ai_score_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("ai_score_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, unpark(os.path.join(OUT, "parked_src")))
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"ai_score_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:40s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:40s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("ai_score_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:40s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("ai_score_diff: instructions of the original reached (all cases; literal pools are never run)")
    for name, pcs in REACHED.items():
        lo, hi = RANGES[name]
        print(f"  {name:40s} {len(pcs):5d} of {(hi - lo) // 4} words")
        if a.unreached:
            gone = [pc for pc in range(lo, hi, 4) if pc not in pcs]
            runs, start = [], None
            for pc in gone + [None]:
                if start is not None and (pc is None or pc != prev + 4):
                    runs.append(f"{start:08X}-{prev:08X}" if prev != start else f"{start:08X}")
                    start = None
                if pc is not None and start is None:
                    start = pc
                prev = pc
            print(f"    not reached: {', '.join(runs) or 'none'}")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"ai_score_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"ai_score_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
