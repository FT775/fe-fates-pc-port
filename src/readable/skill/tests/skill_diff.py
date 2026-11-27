#!/usr/bin/env python3
"""Host differential test of the skill readable code against the game's own ARM code.

    python src/readable/skill/tests/skill_diff.py             all functions, 300 cases each
    python src/readable/skill/tests/skill_diff.py -n 2000     more cases
    python src/readable/skill/tests/skill_diff.py --seed 7    another random sequence
    python src/readable/skill/tests/skill_diff.py --only unit_has_skill
    python src/readable/skill/tests/skill_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/unit/tests/growth_diff.py (and the ARM interpreter
src/readable/battle/tests/arm_mini.py): for every readable function of src/readable/skill/
the test makes up guest states (units with personal and equipped skills, their Person and Job,
a Skill table, the one-time caches, a BattleInfo with four sides, the battle Random, the
SkillIndexProvider words; all random test values, never game data, and on purpose often outside
the ranges the game uses: skill numbers that do not fit a short, difficulties past 2, levels and
pool indexes that are negative or huge, side numbers past 3, bools that are not 0/1, unmapped
unit pointers), runs the ORIGINAL ARM code from the owner's extracted/text.bin in arm_mini.py and
the readable C function (built with the host gcc against tools/readable/stub/) on the same
memory, and compares:

  - overrides (15): r0, the number of bytes read from unmapped memory (tier 2 compares that
    count) AND the list of guest calls, in order, with their argument registers (F-018). On the
    ARM side every BL/BLX to a listed callee is listed (also inside callees that run as ARM
    code); on the C side every guest call is listed (one that reaches another readable override
    of this batch runs that override, as in the capture library).
  - give-ups: a one-time cache that is not filled must make the original reach the guard routine
    and the readable code give up before reading anything; and a readable override must never
    let a NESTED override give up (a guest call of another readable function that gives up
    inside, while the outer one goes on): in the capture library that runs the inner original
    and shows as a fault-count surplus in tier 2 (the unit_dual_exp_damage finding of the
    growth batch). The driver counts give-ups by nesting depth; a nested one is a mismatch.
  - helpers: unit_skill_chance against the whole of Unit::GetEquipSkillProbability (its
    GetCapabilityImpl is answered by a table that also checks the stack words) and
    battle_attack_skill_pick against the whole of map::BattleCalculator::CalculateAttack with
    CreateNewScene and CalculateAttackSingle stubbed: the scene it stores (skill, side, kind),
    the number of GetValue(100) draws, the battle Random's four words afterwards, the strike
    calls, the unmapped reads and the list of guest calls (without the Random, scene and strike
    calls, which the helper does not make).

Guest functions answered by one table on both sides: UnitPool::Get, EquipSkill::Get(const char*),
IdentHash::GetIdent, Unit::HasCheerSkillCapability, unit::Item::ToData, Unit::GetCapabilityImpl
(and, for CalculateAttack, CreateNewScene and CalculateAttackSingle). Everything else runs as ARM
code: GameUserData::Get, Unit::IsEquipSkill, EquipSkill::Get(short) / GetCommonNum,
HasBattleSkill, GetEquipSkillProbability, Random::GetValue and the RVCT division.

--plant copies src/readable/skill/ to build/readable/skill/plant/, makes one small wrong change
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
OUT = os.path.join(ROOT, "build", "readable", "skill")
SRC_SKILL = os.path.join(ROOT, "src", "readable", "skill")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
POOL_GET, BY_NAME, GET_IDENT, RALLY_CAP, TO_DATA, GET_CAP = (
    0x004F6174, 0x001758C4, 0x00127330, 0x00532124, 0x003D0EA4, 0x0052F7A0)
NEW_SCENE, ATTACK_SINGLE = 0x00361ED8, 0x003628BC
RANDOM_BELOW = 0x0044ADF8
PROBABILITY, CALC_ATTACK = 0x005324B8, 0x00361F70
LEAF_STUBS = {POOL_GET: 1, BY_NAME: 1, GET_IDENT: 2, RALLY_CAP: 1, TO_DATA: 1}  # GET_CAP: a checking stub

OVERRIDES = {  # name -> address
    "unit_has_skill": 0x0052DD04, "unit_personal_skill": 0x00530814, "unit_equipped_skill_count": 0x00530B90,
    "skill_record": 0x001758E4, "skill_total": 0x001758F8, "skill_common_total": 0x001758B4,
    "job_class_skill": 0x00524224, "skill_pool_test": 0x0053AA74, "skill_is_unknown": 0x00506034,
    "script_unit_has_skill": 0x003AB148, "unit_has_rally_move_skill": 0x0052F9F8,
    "unit_has_rally_skill": 0x0052E6E4, "battle_side_has_skill": 0x003A34B4,
    "unit_lethality_immune": 0x003A3360, "skill_effect_name": 0x00211BC4,
}
IS_EQUIP, SKILL_GET, COMMON_NUM, HAS_BATTLE = 0x0052DD04, 0x001758E4, 0x001758B4, 0x003A34B4
# the callees listed on both sides, with the argument registers compared
ARITY = {IS_EQUIP: 2, SKILL_GET: 1, COMMON_NUM: 0, HAS_BATTLE: 3, POOL_GET: 1, BY_NAME: 1, GET_IDENT: 2,
         RALLY_CAP: 1, TO_DATA: 1, GET_CAP: 2, 0x00530814: 1, 0x00530B90: 1, 0x001758F8: 0,
         0x00524224: 2, 0x0053AA74: 2, 0x00506034: 1, 0x003AB148: 3, 0x0052F9F8: 1, 0x0052E6E4: 1,
         0x003A3360: 1, 0x00211BC4: 1}

# globals and caches (config/readable/globals.csv, src/readable/skill/skills.h)
G_GAMEUSER, G_EQUIPSKILL, G_PROVIDER, G_RANDOM, G_IDENT = 0x006DA248, 0x006D3C5C, 0x006BC0AC, 0x00752B8C, 0x006DCB44
JOB_GUARD, JOB_MASK = 0x006D39B0, 0x006D3A10
RALLY_GUARD, RALLY_SKILL = 0x006D9978, 0x006D96C0
NOHR_GUARD, NOHR_SKILL = 0x006D6848, 0x006D676A
KILL_GUARDS = (0x006D6854, 0x006D6850, 0x006D684C)
KILL_MASK, KILL_SKIN, KILL_SHIELD = 0x006D6910, 0x006D676C, 0x006D676E
CHANCE_GUARDS = (0x006D97FC, 0x006D97F8, 0x006D97F4, 0x006D97F0)
CHANCE_HOSHIDO, CHANCE_CHARM, CHANCE_FORBID, CHANCE_FORCE = 0x006D966C, 0x006D966E, 0x006D9AF8, 0x006D9B00
ATTACK_GUARDS = tuple(0x006D67A4 - 4 * i for i in range(10)) + (0x006D677C,)
ATTACK_SKILLS = tuple(0x006D6724 + 2 * i for i in range(10))
ATTACK_ITEM_MASK = 0x006D6890

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x400  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
FORCE = lambda k: 0x08030000 + k * 0x10  # noqa: E731
ITEMDATA = lambda k: 0x08040000 + k * 0x80  # noqa: E731
GUD = 0x08050000
POOL = 0x08060000
IDENT_TABLE = 0x08070000
ENTRY = lambda k: 0x08071000 + k * 0x20  # noqa: E731
INFO = 0x08080000                          # BattleInfo: four sides of 0x200
CALC = 0x08090000
SCENE = 0x080A0000
SKILLTAB = 0x09000000                      # NSKILLS records of 0x20; nothing else near it
NSKILLS = 64
NNEG = 8                                   # records of the skill numbers -1 .. -8 (below the table): a
                                           # negative attack-skill number can activate (review 5)
NUNITS = 6
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
STATS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 255]


def s8(rng, common, rare=(), p=0.1) -> int:
    return pick(rng, common, rare, p) & 0xFF


def guard(st, addr: int, cold_p: float = 0.02) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def flag64(st, addr: int, mask_addr: int, p: float) -> None:
    mask = int.from_bytes(bytes(st.mem.get(mask_addr + i, 0) for i in range(8)), "little")
    v = int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(8)), "little")
    st.put(addr, 8, (v | mask) if st.rng.random() < p else (v & ~mask))


def word16(st, addr: int) -> int:
    return st.mem.get(addr, 0) | st.mem.get(addr + 1, 0) << 8


def skill_number(rng) -> int:
    """a skill number as a register: mostly small, sometimes 0, negative or not a short (0x10000: its
    low half is 0, so a truncating reader would stop early)"""
    return pick(rng, list(range(1, 24)) + [0], [-1, 0xFFFF, 0x10003, 0x8000, -0x8000, 63, 64, 200, 0x7FFF,
                                               0x10000, 0x10005, -0xFFFB, 0x7FFF0002], 0.25) \
        & 0xFFFFFFFF


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.put(G_GAMEUSER, 4, GUD)
    st.fill(GUD, 0x40)
    st.put(GUD + 0x2D, 1, pick(rng, [0, 1, 2, 0, 1, 2], [3, 255, 7], 0.12))
    # the Skill table
    st.put(G_EQUIPSKILL, 4, SKILLTAB)
    st.put(G_EQUIPSKILL + 4, 4, pick(rng, [20, 40, 60, 64], [0, 1, 0x7FFFFFFF, 0xFFFFFFFF, 300]))
    st.put(G_EQUIPSKILL + 8, 4, pick(rng, [64, 229], [0, 0xFFFFFFFF]))
    st.fill(SKILLTAB - NNEG * 0x20, (NNEG + NSKILLS) * 0x20)
    for n in range(-NNEG, NSKILLS):
        r = SKILLTAB + n * 0x20
        st.put(r + 0x10, 2, n)
        st.put(r + 0x16, 1, pick(rng, [0, 0, 3, 5, 3, 5, 1, 2, 4], [6, 7, 8, 255]))
        st.put(r + 0x17, 1, pick(rng, [1, 1, 2, 3, 1], [0, 255, 50]))
        st.put(r + 0x18, 1, pick(rng, [1, 1, 2, 4, 1], [3, 255, 7]))  # never 0: the game's division traps
        st.put(r + 0x19, 1, pick(rng, [0, 1, 3, 4, 5], [2, 255]))
    # caches: mostly warm, with skill numbers the units often have
    for g in (JOB_GUARD, RALLY_GUARD, NOHR_GUARD) + KILL_GUARDS:
        guard(st, g)
    for g in CHANCE_GUARDS + ATTACK_GUARDS:  # sixteen caches in the attack choice: colder less often
        guard(st, g, 0.005)
    st.put(JOB_MASK, 8, 1 << rng.randrange(64))
    for a in (RALLY_SKILL, NOHR_SKILL, KILL_SKIN, KILL_SHIELD, CHANCE_HOSHIDO, CHANCE_CHARM):
        st.put(a, 2, pick(rng, list(range(1, 24)), [0, -1, 0x7FFF, 63], 0.08))
    for m in (KILL_MASK, CHANCE_FORBID, CHANCE_FORCE, ATTACK_ITEM_MASK):
        st.put(m, 8, 1 << rng.randrange(64))
    numbers = rng.sample(range(1, 30), 10)
    for a, n in zip(ATTACK_SKILLS, numbers):
        r = rng.random()  # a negative number (its record below the table) often: it can activate, and
        # the s16 the game reads into the scene must stay negative (review 5)
        st.put(a, 2, n if r > 0.2 else -rng.randrange(1, NNEG + 1) if r > 0.04 else rng.choice([0, -1, 63]))
    # the SkillIndexProvider words, the battle Random, the ident hash
    for off in range(0, 0x90, 4):
        st.put(G_PROVIDER + off, 4, pick(rng, list(range(1, 40)), [0, -1, 0x10005, 0x7FFFFFFF]) & 0xFFFFFFFF)
    for i in range(4):
        st.put(G_RANDOM + 4 * i, 4, rng.randrange(1, 1 << 32))
    st.put(G_IDENT, 4, IDENT_TABLE)
    st.fill(IDENT_TABLE, 0x10)
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
    st.put(FORCE(k) + 8, 1, pick(rng, [0, 1, 2, 3, 9], [255, 8]))
    attack = [word16(st, a) for a in ATTACK_SKILLS]
    special = [word16(st, a) for a in (RALLY_SKILL, NOHR_SKILL, KILL_SKIN, KILL_SHIELD, CHANCE_HOSHIDO, CHANCE_CHARM)]
    for i in range(5):
        r = rng.random()
        v = (rng.choice(attack) if r < 0.35 else rng.choice(special) if r < 0.6 else 0 if r < 0.8
             else pick(rng, list(range(1, 24)), [-1, 0x7FFF, 0x8000, 63]))
        st.put(u + 0xFE + 2 * i, 2, v)
    for d in range(3):
        st.put(p + 0x74 + 2 * d, 2, rng.choice(attack + special + [0, 0, 5, -1]))
    st.put(j + 0x54, 8, int.from_bytes(bytes(rng.randrange(256) for _ in range(8)), "little"))
    for base in (u, p, j):
        for m in (JOB_MASK, KILL_MASK, CHANCE_FORBID, CHANCE_FORCE):
            flag64(st, base, m, 0.08)
    return u


def all_units(st, n: int = NUNITS) -> list[int]:
    return [make_unit(st, k) for k in range(n)]


def answer_caps(st) -> None:
    """GetCapabilityImpl answers for every unit and stat the code can ask about."""
    rng = st.rng
    for k in range(NUNITS):
        for s in STATS:
            st.oracle[(GET_CAP, UNIT(k), s)] = pick(rng, [0, 5, 10, 20, 30, 40, 50], [-5, 99, 200, -100]) & 0xFFFFFFFF
    for u in UNMAPPED:
        for s in STATS:
            st.oracle[(GET_CAP, u, s)] = rng.randrange(60)


TORN_END = 0x080F1000  # a page nothing else uses: a torn unit ends right before it


def torn_unit(st, source: int) -> int:
    """a copy of a unit whose record stops (unmapped from there on) at one of the offsets the
    skill readers read in order: shows a read the game does not make (or skips) as a fault count"""
    if getattr(st, "torn", None) is not None:  # one torn unit per state (copies would overlap)
        return st.torn
    cut = st.rng.choice([0x9C, 0xA0, 0xA4, 0xFC, 0x100, 0x104, 0x108])  # 4-aligned: units are
    base = TORN_END - cut
    for i in range(cut):
        st.mem[base + i] = st.mem.get(source + i, 0)
    st.torn = base
    return base


def unit_arg(st, units: list[int], unmapped_p: float = 0.12, torn_p: float = 0.1) -> int:
    r = st.rng.random()
    if r < unmapped_p:
        return st.rng.choice(UNMAPPED)
    if r < unmapped_p + torn_p:
        return torn_unit(st, st.rng.choice(units))
    return st.rng.choice(units)


def skill_of(st, unit: int) -> int:
    """a skill to ask about: often one the unit has"""
    rng = st.rng
    if unit < 0x08000000 or rng.random() < 0.4 or (TORN_END - 0x140 <= unit < TORN_END):
        return skill_number(rng)
    if rng.random() < 0.75:
        a = unit + 0xFE + 2 * rng.randrange(5)  # an equipped skill
    else:
        person = word16(st, unit + 0x9C) | word16(st, unit + 0x9E) << 16
        a = person + 0x74 + 2 * rng.randrange(3)  # a personal skill (of some difficulty)
    v = word16(st, a)
    v = v - 0x10000 if v & 0x8000 else v
    if rng.random() < 0.3:  # not a short, but its low half is a skill the unit has: the game compares the
        # whole register, so it never matches (a planted (int16_t) cast must show; review 5)
        v += rng.choice([0x10000, -0x10000, 0x20000, 0x7FFF0000, -0x80000000])
    return v & 0xFFFFFFFF


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def ov(name, args):
    a = OVERRIDES[name]
    return f"ov:0x{a:08X}", args + [0] * (4 - len(args)), ("call", a)


def gen_has(rng):
    st = base_state(rng)
    units = all_units(st, 2)
    u = unit_arg(st, units)
    return (st,) + ov("unit_has_skill", [u, skill_of(st, u)])


COLD_MORE = {"unit_has_rally_move_skill": (RALLY_GUARD,), "unit_has_rally_skill": (RALLY_GUARD,),
             "unit_lethality_immune": KILL_GUARDS, "job_class_skill": (JOB_GUARD,),
             "battle_side_has_skill": (NOHR_GUARD,), "battle_attack_skill_pick": (NOHR_GUARD,) + CHANCE_GUARDS}


def colder(st, name: str, p: float = 0.08) -> None:
    for g in COLD_MORE.get(name, ()):
        if st.rng.random() < p:
            st.put(g, 4, 0)


def gen_unit_only(name, n=2):
    def gen(rng):
        st = base_state(rng)
        units = all_units(st, n)
        colder(st, name)
        u = unit_arg(st, units)
        st.oracle.update({(RALLY_CAP, x): int(rng.random() < 0.3) for x in units + UNMAPPED})
        return (st,) + ov(name, [u])
    return gen


def gen_record(rng):
    st = base_state(rng)
    return (st,) + ov("skill_record", [skill_number(rng)])


def gen_noarg(name):
    def gen(rng):
        return (base_state(rng),) + ov(name, [])
    return gen


def gen_job(rng):
    st = base_state(rng)
    make_unit(st, 0)
    colder(st, "job_class_skill")
    flag64(st, JOB(0), JOB_MASK, 0.5)  # a promoted class half the time
    j = JOB(0) if rng.random() > 0.08 else rng.choice(UNMAPPED)
    level = pick(rng, [1, 5, 10, 15, 25, 35, 2, 20, 40], [0, -1, 0x100000005 & 0xFFFFFFFF, 0x7FFFFFFF, 0xFFFFFFF6])
    return (st,) + ov("job_class_skill", [j, level & 0xFFFFFFFF])


def gen_pool(rng):
    st = base_state(rng)
    st.fill(POOL - 0x20, 0x60)
    n = pick(rng, list(range(0, 70)), [-1, -8, -9, -200, 300, 0x7FFFFFFF, -0x80000000])
    if rng.random() < 0.15:  # exactly the common count: the edge of "at or past"
        n = int.from_bytes(bytes(st.mem[G_EQUIPSKILL + 4 + i] for i in range(4)), "little")
    p = POOL if rng.random() > 0.06 else rng.choice(UNMAPPED)
    return (st,) + ov("skill_pool_test", [p, n & 0xFFFFFFFF])


def gen_unknown(rng):
    st = base_state(rng)
    n = rng.randrange(NSKILLS)
    rec = SKILLTAB + n * 0x20
    if rng.random() < 0.5:
        st.put(rec + 0x19, 1, 5)
    name = st.mem[rec + 4] | st.mem[rec + 5] << 8 | st.mem[rec + 6] << 16 | st.mem[rec + 7] << 24
    e = rng.randrange(4)
    st.fill(ENTRY(e), 0x20)
    if rng.random() < 0.4:
        st.put(ENTRY(e) + 0xC, 4, 0)
    st.oracle[(GET_IDENT, IDENT_TABLE, name)] = 0 if rng.random() < 0.25 else (
        ENTRY(e) if rng.random() < 0.9 else rng.choice(UNMAPPED))
    if rng.random() < 0.06:
        rec = rng.choice(UNMAPPED)
    return (st,) + ov("skill_is_unknown", [rec])


def gen_script(rng):
    st = base_state(rng)
    units = all_units(st, 3)
    idx = pick(rng, [1, 2, 3, 5, 100, 250], [0, -1, 251, 0x7FFFFFFF, -0x80000000])
    st.oracle[(POOL_GET, idx & 0xFFFFFFFF)] = rng.choice(units) if rng.random() > 0.1 else rng.choice(UNMAPPED + [0])
    seid = rng.choice([0x0062EF14, 0x00640DB8, 0x12345678])
    target = st.oracle[(POOL_GET, idx & 0xFFFFFFFF)]
    n = rng.randrange(NSKILLS + 4)
    if target in units and rng.random() < 0.6:  # a skill that unit has (when it fits the table)
        v = word16(st, target + 0xFE + 2 * rng.randrange(5))
        n = v if v < NSKILLS else n
    st.oracle[(BY_NAME, seid)] = SKILLTAB + n * 0x20 if rng.random() > 0.05 else rng.choice(UNMAPPED)
    return (st,) + ov("script_unit_has_skill", [0x0BAD0000, idx & 0xFFFFFFFF, seid])


def make_info(st, units: list[int]) -> None:
    rng = st.rng
    st.fill(INFO, 0x810)
    for s in range(4):
        side = INFO + s * 0x200
        st.put(side + 4, 4, 0 if (s >= 2 and rng.random() < 0.4) else unit_arg(st, units, 0.06))
        st.put(side + 0x10, 2, 0 if rng.random() < 0.15 else rng.randrange(1, 5))
        st.put(side + 0x28, 4, rng.choice([0x100, 0x100, 0x4000, 0x10, 0x4100]) if rng.random() < 0.3 else 0)
        st.put(side + 0x2C, 4, pick(rng, [0, 1, 5, 12, 20], [-3, 0x7FFFFFFF]) & 0xFFFFFFFF)
        for b in range(64):
            st.put(side + 0xE6 + b, 1, rng.randrange(256) if rng.random() < 0.05 else 0)
        q = word16(st, ATTACK_SKILLS[9])
        q = q - 0x10000 if q & 0x8000 else q
        if rng.random() < 0.45 and 0 <= q < 512:  # Quixotic active on this side (often: one side only)
            st.mem[side + 0xE6 + (q >> 3)] |= 1 << (q & 7)


def gen_battle_has(rng):
    st = base_state(rng)
    units = all_units(st, 4)
    make_info(st, units)
    colder(st, "battle_side_has_skill")
    for k in range(4):  # Nohrian Trust on a third of the units
        if rng.random() < 0.33:
            st.put(UNIT(k) + 0xFE + 2 * rng.randrange(5), 2, word16(st, NOHR_SKILL))
    side = pick(rng, [0, 1, 2, 3], [4, 5, 6, 7, 0x100, 0xFFFFFFFF, 0x80000000], 0.3)
    info = INFO if rng.random() > 0.05 else rng.choice(UNMAPPED)
    skill = skill_of(st, UNIT(rng.randrange(4))) if rng.random() < 0.7 else skill_number(rng)
    return (st,) + ov("battle_side_has_skill", [info, side & 0xFFFFFFFF, skill])


def gen_effect(rng):
    st = base_state(rng)
    if rng.random() < 0.7:
        off = rng.randrange(0x30, 0x90, 4)
        v = st.mem[G_PROVIDER + off] | st.mem[G_PROVIDER + off + 1] << 8 | st.mem[G_PROVIDER + off + 2] << 16 | \
            st.mem[G_PROVIDER + off + 3] << 24
    else:
        v = skill_number(rng)
    return (st,) + ov("skill_effect_name", [v])


def gen_chance(rng):
    st = base_state(rng)
    units = all_units(st)
    answer_caps(st)
    u = unit_arg(st, units)
    skill = skill_of(st, u)
    q = pick(rng, [0, 1], [2, 0x100, 0xFFFFFFFF])
    return st, "chance", [u, skill, q, 0], ("call", PROBABILITY)


def gen_pick(rng):
    st = base_state(rng)
    units = all_units(st)
    answer_caps(st)
    make_info(st, units)
    st.fill(CALC, 0x40)
    st.put(CALC, 4, INFO if rng.random() > 0.04 else rng.choice(UNMAPPED))
    st.zero(SCENE, 0x20)
    for k in range(5):
        st.fill(ITEMDATA(k), 0x80)
        flag64(st, ITEMDATA(k), ATTACK_ITEM_MASK, 0.15)
    for s in range(4):
        st.oracle[(TO_DATA, INFO + s * 0x200 + 0x10)] = ITEMDATA(s)
    st.oracle[(TO_DATA, 0)] = ITEMDATA(4)
    colder(st, "battle_attack_skill_pick", 0.025)
    side = pick(rng, [0, 1, 0, 1, 2, 3], [4, 0x100, 0xFFFFFFFF])
    # the attacking unit carries many of the nine skills (personal and equipped), with low stats
    # most of the time: many draws per attack, so chance == roll happens (the > against >= edge)
    if rng.random() < 0.7:
        attacker = st.mem.get(INFO + (side & 3) * 0x200 + 4, 0) | st.mem.get(INFO + (side & 3) * 0x200 + 5, 0) << 8 \
            | st.mem.get(INFO + (side & 3) * 0x200 + 6, 0) << 16 | st.mem.get(INFO + (side & 3) * 0x200 + 7, 0) << 24
        if UNIT(0) <= attacker < UNIT(NUNITS):
            # no "no roll" side flag and a weapon that allows skills most of the time: many draws, so
            # chance == roll (the > against >= edge) shows in several cases (review 5)
            if rng.random() < 0.8:
                st.put(INFO + (side & 3) * 0x200 + 0x28, 4, 0)
                for k in range(5):
                    flag64(st, ITEMDATA(k), ATTACK_ITEM_MASK, 0.0)
            attack = [word16(st, a) for a in ATTACK_SKILLS[:9]]
            for i in range(5):
                st.put(attacker + 0xFE + 2 * i, 2, rng.choice(attack))
            low = rng.random() < 0.5  # low stats half the time: most skills fail, up to nine draws per attack
            for s_ in STATS:
                st.oracle[(GET_CAP, attacker, s_)] = rng.choice(
                    [0, 1, 2, 3, 4] if low else [0, 1, 2, 3, 5, 8, 10, 15, 20, 40, 25, 30, 35, 50])
            for mask in (CHANCE_FORBID, CHANCE_FORCE):  # no forced / forbidden flags here
                for base in (attacker, word16(st, attacker + 0x9C) | word16(st, attacker + 0x9E) << 16,
                             word16(st, attacker + 0xA0) | word16(st, attacker + 0xA2) << 16):
                    m = int.from_bytes(bytes(st.mem.get(mask + i, 0) for i in range(8)), "little")
                    v = int.from_bytes(bytes(st.mem.get(base + i, 0) for i in range(8)), "little")
                    if base + 7 in st.mem:
                        st.put(base, 8, v & ~m)
            if rng.random() < 0.25:
                # the first die's value made the chance of every skill (factor 1, divisor 1, the
                # stat = that value, no +10 / +15 / +20 bonus): chance == roll on the first draw,
                # where the game's "chance > roll" does not activate and ">=" would (review 5)
                s = [int.from_bytes(bytes(st.mem[G_RANDOM + 4 * i + j] for j in range(4)), "little")
                     for i in range(4)]
                t = (s[0] ^ (s[0] << 11)) & 0xFFFFFFFF
                first = ((t ^ (t >> 8)) ^ (s[3] ^ (s[3] >> 19))) & 0x7FFFFFFF
                roll = first % 100
                for n in range(-NNEG, NSKILLS):
                    r = SKILLTAB + n * 0x20
                    st.put(r + 0x16, 1, rng.randrange(1, 6))
                    st.put(r + 0x17, 1, 1)
                    st.put(r + 0x18, 1, 1)
                st.put(CHANCE_HOSHIDO, 2, 0)
                st.put(CHANCE_CHARM, 2, 0)
                for s_ in STATS:
                    st.oracle[(GET_CAP, attacker, s_)] = roll
                for k in range(4):
                    st.zero(INFO + k * 0x200 + 0xE6, 64)
    calc = CALC if rng.random() > 0.15 else rng.choice(UNMAPPED)  # an unmapped calculator: every re-read faults
    return st, "pick", [calc, side & 0xFFFFFFFF, 0, 0], ("pick", CALC_ATTACK)


FUNCS = {
    "unit_has_skill": gen_has,
    "unit_personal_skill": gen_unit_only("unit_personal_skill"),
    "unit_equipped_skill_count": gen_unit_only("unit_equipped_skill_count"),
    "skill_record": gen_record,
    "skill_total": gen_noarg("skill_total"),
    "skill_common_total": gen_noarg("skill_common_total"),
    "job_class_skill": gen_job,
    "skill_pool_test": gen_pool,
    "skill_is_unknown": gen_unknown,
    "script_unit_has_skill": gen_script,
    "unit_has_rally_move_skill": gen_unit_only("unit_has_rally_move_skill"),
    "unit_has_rally_skill": gen_unit_only("unit_has_rally_skill"),
    "battle_side_has_skill": gen_battle_has,
    "unit_lethality_immune": gen_unit_only("unit_lethality_immune"),
    "skill_effect_name": gen_effect,
    "unit_skill_chance": gen_chance,
    "battle_attack_skill_pick": gen_pick,
}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY (stubbed or run as ARM code)
    with its argument registers, and counting the Random draws and the strikes."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []
        self.draws = 0
        self.strikes: list[int] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY and target != PROBABILITY:
            self.listed.append(call_text(target, self.r[:ARITY[target]]))
        if target == RANDOM_BELOW:
            self.draws += 1
        if target == ATTACK_SINGLE:
            self.strikes.append(self.r[2])
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

    def cap(cpu, a):
        sp = cpu.r[13]
        if a[2] != 0 or a[3] != 1 or cpu.mem.read(sp, 4) != 1 or cpu.mem.read(sp + 4, 4) != 0:
            return 0xBAD0BAD  # the game passes (stat, no item, true, true, 0): would show as a mismatch
        return st.oracle.get((GET_CAP, a[0], a[1]), 0)
    stubs[GET_CAP] = cap
    if how[0] == "pick":
        stubs[NEW_SCENE] = lambda cpu, a: SCENE
        stubs[ATTACK_SINGLE] = lambda cpu, a: 0
    cpu = ListingCpu(mem, stubs, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    try:
        cpu.run(how[1])
    except A.ColdGuard:
        return [1]
    if how[0] == "call":
        return [0, cpu.r[0], mem.faults, calls_field(cpu.listed)]
    skill = mem.read(SCENE + 8, 4)
    scene = [skill, mem.read(SCENE + 4, 1), mem.read(SCENE + 5, 1)]
    strikes = cpu.strikes + [0xFFFFFFFF] * 2
    return ([0] + scene + [cpu.draws] + [mem.read(G_RANDOM + 4 * i, 4) for i in range(4)]
            + [strikes[0] & 0xFFFFFFFF, strikes[1] & 0xFFFFFFFF, len(cpu.strikes), mem.faults,
               calls_field(cpu.listed)])


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/skill/tests/skill_diff.py: runs readable skill functions on memory
   images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "skills.h"

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

/* GetCapabilityImpl(stat, no item, true, true, 0), answered by the table */
static int32_t stat_of(Context *ctx, void *env, gaddr unit, uint32_t stat) {
    (void)ctx; (void)env;
    uint32_t r[4] = {unit, stat, 0, 0};
    list_call(0x0052F7A0u, r);
    return (int32_t)oracle_get(0x0052F7A0u, 2, r);
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
            } else if (!strcmp(kind, "chance")) {
                int32_t chance = 0;
                int ok = unit_skill_chance(&c, a[0], a[1], a[2], stat_of, NULL, &chance);
                cl = ncalls ? calls : "-";
                if (!ok || originals) printf("%u 1 %d\n", id, faults);
                else printf("%u 0 %u %d %s\n", id, (uint32_t)chance, faults, cl);
            } else if (!strcmp(kind, "pick")) {
                SkillAttackPick p;
                int ok = battle_attack_skill_pick(&c, a[0], a[1], stat_of, NULL, &p);
                cl = ncalls ? calls : "-";
                if (!ok || originals) printf("%u 1 %d\n", id, faults);
                else {
                    int32_t astra = (int16_t)r16(&c, 0x006D6728u), aether = (int16_t)r16(&c, 0x006D6726u);
                    int n = p.skill == astra ? 5 : p.skill == aether ? 2 : 1;
                    printf("%u 0 %u %u %u %d", id, (uint32_t)p.skill, p.skill ? p.side & 0xFFu : 0u,
                           p.skill ? 4u : 0u, p.draws);
                    for (int i = 0; i < 4; i++) printf(" %u", p.random.s[i]);
                    printf(" %u %u %d %d %s\n", (uint32_t)p.strikes[0], (uint32_t)(n > 1 ? p.strikes[1] : -1), n,
                           faults, cl);
                }
            }
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


def build_driver(cc: str, out: str, skill_dir: str) -> str:
    """Builds the driver with every source of src/readable/, the skill folder's taken from skill_dir."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "skill_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_SKILL)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(skill_dir, f) for f in os.listdir(skill_dir) if f.endswith(".c")]
    exe = os.path.join(out, "skill_driver.exe" if os.name == "nt" else "skill_driver")
    inc = ["-I", skill_dir, "-I", os.path.join(ROOT, "src", "readable", "unit"),
           "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"skill_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
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
            stubs = dict(LEAF_STUBS)
            stubs[GET_CAP] = 2
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


COVERAGE: dict[str, dict] = {}


def compare(exe: str, cc: str, lines: list[str], expected: dict, show: int, quiet: bool = False):
    log = os.path.join(os.path.dirname(exe), "fe_readable.log")
    env = dict(os.environ, FE_READABLE_LOG=log, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"skill_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
        if exp[0] == 0:  # what the cases exercise (printed as evidence): results seen, draws
            cov = COVERAGE.setdefault(name, {"values": set(), "draws": 0, "chosen": 0, "nonzero": 0})
            cov["values"].add(exp[1])
            cov["nonzero"] += int(exp[1] != 0)
            if inputs[0] == "pick":
                cov["draws"] += exp[4]
                cov["chosen"] += int(exp[1] != 0)
        if exp[0] == 1:
            res[2] += 1
            exp = [1, 0]  # a give-up must come before any unmapped read
        elif g is not None and g[:1] == [1] and g[1:] == [0] and c not in flagged:
            # an early give-up: a needed cache is cold, the readable code asks before reading
            # anything (the original would reach that cache later or not at all); always safe
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
    # unit_has_skill
    ("skill_has.c", "    if (skill == 0)\n        return 0;\n    gaddr person = READ_FIELD(ctx, Unit, unit, person);\n    gaddr personal",
     "    gaddr person = READ_FIELD(ctx, Unit, unit, person);\n    gaddr personal"),
    ("skill_has.c", "personal_skill) + 2u * (uint32_t)difficulty(ctx);\n    gaddr slots",
     "personal_skill);\n    gaddr slots"),
    ("skill_has.c", "    if (skill_word(ctx, slots + 6u) == skill || skill_word(ctx, slots + 8u) == skill)",
     "    if (skill_word(ctx, slots + 6u) == skill)"),
    ("skill_has.c", "static uint32_t skill_word(Context *ctx, gaddr addr) {\n    return (uint32_t)(int32_t)guest_s16(ctx, addr);",
     "static uint32_t skill_word(Context *ctx, gaddr addr) {\n    return (uint32_t)guest_u16(ctx, addr);"),
    # reads slot 1 even when the personal skill matched: same answers, more unmapped reads with a
    # torn unit (tier 2 counts them)
    ("skill_has.c", "    if (skill_word(ctx, personal) == skill || skill_word(ctx, slots) == skill)\n        return 1;",
     "    uint32_t p0 = skill_word(ctx, personal), s0 = skill_word(ctx, slots);\n    if (p0 == skill || s0 == skill)\n        return 1;"),
    ("skill_has.c", "        if (guest_u16(ctx, FIELD_ADDR(Unit, unit, equip_skills) + 2u * i) != 0)",
     "        if (guest_s16(ctx, FIELD_ADDR(Unit, unit, equip_skills) + 2u * i) > 0)"),
    ("skill_has.c", "    if (level == 25)", "    if (level == 20)"),
    ("skill_has.c", "        if (level == 15)\n            return guest_u16(ctx, skills + 2u);",
     "        if (level == 15)\n            return (uint32_t)guest_s16(ctx, skills + 2u);"),
    ("skill_has.c", "    if (common <= number)", "    if (common < number)"),
    ("skill_has.c", "    return guest_u8(ctx, pool + (gaddr)fe_asr(number, 3)) & (1u << ((uint32_t)number & 7u));",
     "    return guest_u8(ctx, pool + ((uint32_t)number >> 3)) & (1u << ((uint32_t)number & 7u));"),
    # GetCommonNum read in C instead of through the guest: same numbers, a missing callee call
    ("skill_has.c", "    int32_t common = (int32_t)guest_call(ctx, SKILL_EquipSkillGetCommonNum, 0u, 0u, 0u, 0u);",
     "    int32_t common = (int32_t)skill_common_total(ctx);"),
    ("skill_has.c", "    return guest_u32(ctx, entry + 0xCu) != 0 ? 0 : 1;", "    return guest_u32(ctx, entry + 0x8u) != 0 ? 0 : 1;"),
    ("skill_has.c", "    if (unit_index <= 0 || unit_index > 250)", "    if (unit_index <= 0 || unit_index >= 250)"),
    # the second UnitPool::Get left out: same unit, one callee call less
    ("skill_has.c", "    unit = guest_call1(ctx, SKILL_UnitPoolGet, (uint32_t)unit_index);\n    gaddr record",
     "    gaddr record"),
    # unit_has_rally_skill without the ask-first: the cache read later, a give-up after a guest call
    ("skill_has.c", "uint32_t unit_has_rally_skill(Context *ctx, gaddr unit) {\n    if (!fe_static_ready(ctx, S_RallyMoveGuard))\n        return fe_use_original(ctx);\n",
     "uint32_t unit_has_rally_skill(Context *ctx, gaddr unit) {\n"),
    # skill_battle.c
    ("skill_battle.c", "    uint32_t pair = (side < 2u ? side + 2u : side - 2u) & 0xFFu;", "    uint32_t pair = side ^ 2u;"),
    # IsEquipSkill done in C instead of through the guest: same answers, missing callee calls
    ("skill_battle.c", "    if (guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill) != 0)\n        return 1;\n    if (guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill_word(ctx, S_NohrSkillId)) == 0)",
     "    if (unit_has_skill(ctx, unit, skill) != 0)\n        return 1;\n    if (guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill_word(ctx, S_NohrSkillId)) == 0)"),
    ("skill_battle.c", "    if (guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill_word(ctx, S_KillSkinSkill)) != 0)\n        return 1;\n",
     ""),
    ("skill_battle.c", "{0x7C, 0x00211E3Cu}", "{0x7C, 0x00211E30u}"),
    ("skill_battle.c", "        v = fe_add32(v, 15);", "        v = fe_add32(v, 10);"),
    ("skill_battle.c", "    if (kind == 5 && guest_call2", "    if (kind == 3 && guest_call2"),
    ("skill_battle.c", "    if (flags & guest_u64(ctx, S_ChanceForceMask))\n        v = 100;\n    if (flags & guest_u64(ctx, S_ChanceForbidMask))\n        v = 0;",
     "    if (flags & guest_u64(ctx, S_ChanceForbidMask))\n        v = 0;\n    if (flags & guest_u64(ctx, S_ChanceForceMask))\n        v = 100;"),
    ("skill_battle.c", "    v = v < 0 ? 0 : v > 100 ? 100 : v;", "    v = v < 0 ? 0 : v > 99 ? 99 : v;"),
    ("skill_battle.c", "    v /= divisor;", "    v = fe_asr(v, divisor > 1 ? 1 : 0);"),
    ("skill_battle.c", "                if (chance > roll)", "                if (chance >= roll)"),
    # the roll drawn only when the chance is above 0: same skills mostly, fewer draws
    ("skill_battle.c", "                int32_t roll = growth_random_below(ctx, &out->random, 100);  /* drawn before the chance */\n                out->draws++;\n                int32_t chance;\n                if (!unit_skill_chance(ctx, unit, skill_word(ctx, number_at), quixotic, stat, env, &chance))\n                    return 0;\n",
     "                int32_t chance;\n                if (!unit_skill_chance(ctx, unit, skill_word(ctx, number_at), quixotic, stat, env, &chance))\n                    return 0;\n                int32_t roll = 0;\n                if (chance > 0) {\n                    roll = growth_random_below(ctx, &out->random, 100);\n                    out->draws++;\n                }\n"),
    ("skill_battle.c", "                if (i == 0 && READ_FIELD(ctx, BattleSide, mine, power) <= 0)",
     "                if (i == 0 && READ_FIELD(ctx, BattleSide, mine, power) < 0)"),
    ("skill_battle.c", "            uint32_t quixotic = bit_set(ctx, FIELD_ADDR(BattleSide, mine, skill_bits), q) ||\n                                bit_set(ctx, FIELD_ADDR(BattleSide, other, skill_bits), q);",
     "            uint32_t quixotic = bit_set(ctx, FIELD_ADDR(BattleSide, other, skill_bits), q);"),
    ("skill_battle.c", "                  (READ_FIELD(ctx, BattleSide, mine, flags) & 0x4100u) == 0;",
     "                  (READ_FIELD(ctx, BattleSide, mine, flags) & 0x4000u) == 0;"),
    # the BattleInfo pointer read once: same choice, fewer unmapped reads with an unmapped calculator
    ("skill_battle.c", "                gaddr again = READ_FIELD(ctx, BattleCalculator, calculator, info);\n",
     "                gaddr again = info;\n"),
    # the pick without asking HasBattleSkill's cache first: its guest call gives up inside (nested)
    ("skill_battle.c", "    if (!fe_static_ready(ctx, S_AttackGuardItem) || !fe_static_ready(ctx, S_NohrSkillGuard) ||",
     "    if (!fe_static_ready(ctx, S_AttackGuardItem) ||"),
    ("skill_battle.c", "        out->strikes[0] = guest_s16(ctx, S_AttackSkill0 + 2u * SKILL_ATTACK_SOL);",
     "        out->strikes[0] = guest_s16(ctx, S_AttackSkill0 + 2u * SKILL_ATTACK_LUNA);"),
    # review 5: the skill number truncated to a short (the game compares the whole register, so
    # 0x10003 never matches skill 3; 0x10000 is not "skill 0")
    ("skill_has.c", "uint32_t unit_has_skill(Context *ctx, gaddr unit, uint32_t skill) {\n    if (skill == 0)",
     "uint32_t unit_has_skill(Context *ctx, gaddr unit, uint32_t skill) {\n"
     "    skill = (uint32_t)(int32_t)(int16_t)skill;\n    if (skill == 0)"),
    # review 5: the activated skill number read unsigned (a negative number that activates would be
    # stored as 0xFFxx instead of the game's sign-extended word)
    ("skill_battle.c", "                    chosen = guest_s16(ctx, number_at);",
     "                    chosen = guest_u16(ctx, number_at);"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_SKILL, d, ignore=shutil.ignore_patterns("tests"))
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
    ap.add_argument("--seed", type=int, default=20261113)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, default=200, help="cases per function for each planted bug")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("skill_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("skill_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_SKILL)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"skill_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:32s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:32s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("skill_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        extra = f", {cov['chosen']} with a skill activated, {cov['draws']} draws" if name == "battle_attack_skill_pick" else ""
        print(f"  {name:32s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0{extra}")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"skill_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"skill_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
