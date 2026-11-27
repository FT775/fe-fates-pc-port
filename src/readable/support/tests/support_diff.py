#!/usr/bin/env python3
"""Host differential test of the support / family / pair-up readable code against the game's own ARM code.

    python src/readable/support/tests/support_diff.py             all functions, 300 cases each
    python src/readable/support/tests/support_diff.py -n 1500 --seed 7    the long run
    python src/readable/support/tests/support_diff.py --only unit_support_level
    python src/readable/support/tests/support_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/sheet/tests/sheet_diff.py (and the ARM interpreter
src/readable/battle/tests/arm_mini.py): for every readable function of src/readable/support/ the
test makes up guest states (units with their Person, class, force, pair partner, family record and
support-points bytes; the support table with its 128 chains, records and entries; the map
Situation; the one-time cache; all random test values, never game data, and on purpose often
outside the ranges the game uses: thresholds of 0, 99, 100 and 255, negative and huge points,
support ids that share a chain, negative support ids, records of another id in the chain, empty
records, odd and even entry counts, force numbers of 3 and more, family records with one parent,
unmapped pointers anywhere in the chain and "torn" units and Persons whose record stops at an
offset the readers read), runs the ORIGINAL ARM code from the owner's extracted/text.bin in
arm_mini.py and the readable C function (built with the host gcc against tools/readable/stub/) on
the same memory, and compares r0, the number of bytes read from unmapped memory AND the list of
guest calls, in order, with their argument registers (docs/DECISIONS.md F-018). On the ARM side
every BL/BLX to a listed callee is listed, and so is a tail branch (B) to a guest function answered
by the table (Person::Get, the two GetMaxLevel: the readable code makes a guest call); a tail branch
to an override (Unit::GetRelianceLevel's to Reliance::GetLevel, ParentSingle::GetLevel and
BrotherSingle::GetLevel) is not listed and runs on as ARM code, because 3dsrecomp keeps the target's
code inside the caller's generated function (the original never enters that override; the readable
code runs the C); on the C side every guest call is listed (one that reaches another override of this
batch runs that override, as in the capture library). A one-time cache that is not filled must
make the original reach the guard routine and the readable code give up before reading anything;
a nested give-up is a mismatch.

Guest functions answered by one table on both sides: Person::IsDownload, Person::Get,
Force::GetMaskSameForce, UnitPool::GetFromPerson, ParentSingle::GetMaxLevel,
BrotherSingle::GetMaxLevel. Every other callee is an override of this batch: it runs as ARM code on
the ARM side and as its readable override on the C side.

--plant copies src/readable/support/ to build/readable/support/plant/, makes one small wrong change
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
OUT = os.path.join(ROOT, "build", "readable", "support")
SRC_SUPPORT = os.path.join(ROOT, "src", "readable", "support")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000
MASK = 0xFFFFFFFF

# ------------------------------------------------------------------ addresses
IS_DOWNLOAD, PERSON_GET, MASK_SAME_FORCE, POOL_FROM_PERSON, PARENT_MAX, BROTHER_MAX = (
    0x0053DFEC, 0x0044A6F8, 0x0041C6C4, 0x004F5EEC, 0x0053B690, 0x0053B828)
LEAF_STUBS = {IS_DOWNLOAD: 1, PERSON_GET: 1, MASK_SAME_FORCE: 1, POOL_FROM_PERSON: 2, PARENT_MAX: 1, BROTHER_MAX: 1}

OVERRIDES = {  # name -> (address, number of argument registers)
    "reliance_max_level": (0x005467F0, 1), "reliance_level": (0x00546878, 2), "reliance_person": (0x005468BC, 1),
    "reliance_is_romance": (0x005468C4, 1), "reliance_count": (0x004F1284, 1), "reliance_entry": (0x004F10EC, 2),
    "reliance_find": (0x004F0FDC, 2), "family_parent_record": (0x0053BECC, 2), "family_parent_level": (0x0053B800, 2),
    "family_sibling_level": (0x0053B864, 2), "family_grandfather": (0x0053BAC8, 1),
    "family_grandmother": (0x0053BAF4, 1), "situation_can_gain_support": (0x00527EC8, 2),
    "unit_support_points": (0x0052C260, 2), "unit_support_level": (0x0052F518, 2),
    "unit_support_max_level": (0x00530D2C, 2), "unit_can_support": (0x0052AD24, 2),
    "unit_family_child": (0x005306C4, 2), "unit_is_parent_child": (0x00530E84, 2), "unit_is_sibling": (0x00531428, 2),
    "unit_is_uncle_aunt": (0x0052FA58, 2), "unit_is_family": (0x0053386C, 2), "unit_can_romance": (0x005346F0, 2),
    "unit_spouse_pid": (0x0052E634, 1), "unit_can_trade_partner": (0x0052E818, 2),
}
# the callees listed on both sides, with the argument registers compared
ARITY = dict(LEAF_STUBS)
ARITY.update({a: n for a, n in OVERRIDES.values()})

G_RELIANCE = 0x006D3BD0
TRADE_GUARD, TRADE_MASK = 0x006D99BC, 0x006D9CC0
CACHE_BASE, CACHE_END = 0x006D9600, 0x006D9D00

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x400  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
FORCE = lambda k: 0x08030000 + k * 0x10  # noqa: E731
FAMILY = lambda k: 0x08040000 + k * 0x40  # noqa: E731
POINTS = lambda k: 0x08048000 + k * 0x80  # noqa: E731
BUCKETS = 0x08050000
NODE = lambda k: 0x08051000 + k * 0x10  # noqa: E731
RECORD = lambda k: 0x08052000 + k * 0x100  # noqa: E731
SITUATION = 0x08060000
NUNITS = 6
NPERSONS = 8  # persons 6 and 7 have no unit (partners only)
UNMAPPED = [4, 0x40, 0x7FF0, 0x0FFF0000]
TORN_END = 0x080F1000  # a page nothing else uses: a torn record ends right before it
TORN_UNIT_CUTS = (0x04, 0x08, 0x0C, 0x9C, 0xA0, 0xA4, 0xA8, 0xAC, 0xB4, 0xB8, 0x11C, 0x120)
TORN_PERSON_CUTS = (0x04, 0x08, 0x0C, 0x24, 0x26, 0x30, 0x32)
PIDS = [0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17]  # person numbers (u16) of persons 0..7
THRESHOLDS = [1, 2, 3, 5, 8, 10, 15, 20, 25, 30, 99, 99]
THRESHOLDS_RARE = [0, 98, 100, 200, 255]


def s32(v: int) -> int:
    return v & MASK


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def ptr_or(st, good: int, p_zero: float, p_bad: float = 0.03) -> int:
    r = st.rng.random()
    if r < p_zero:
        return 0
    if r < p_zero + p_bad:
        return st.rng.choice(UNMAPPED)
    return good


# ------------------------------------------------------------------ the support table
def make_table(st) -> list[int]:
    """the 128 chains and some records; returns the addresses of every entry made"""
    rng = st.rng
    st.zero(BUCKETS, 128 * 4)
    st.put(G_RELIANCE, 4, BUCKETS if rng.random() > 0.02 else rng.choice(UNMAPPED))
    ids = sorted({word(st, PERSON(k) + 0x30, 2) for k in range(NPERSONS)} | {rng.randrange(0x8000)})
    entries = []
    node_k = rec_k = 0
    for sid in ids:
        if sid & 0x8000:
            continue
        b = sid & 0x7F
        if word(st, BUCKETS + 4 * b) != 0 or rng.random() < 0.08:
            continue  # a chain made for another id with the same bucket, or none
        n_nodes = pick(rng, [1, 1, 1, 2, 2, 3])
        prev = BUCKETS + 4 * b
        for _ in range(n_nodes):
            if node_k >= 200 or rec_k >= 60:
                break
            node = NODE(node_k)
            node_k += 1
            st.put(prev, 4, node)
            rec = RECORD(rec_k)
            rec_k += 1
            st.put(node, 4, ptr_or(st, rec, 0.0, 0.02))
            st.put(node + 4, 4, 0)
            prev = node + 4
            # mostly this id; sometimes another id of the same chain
            rid = sid if rng.random() < 0.8 else ((sid + 0x80 * rng.randrange(1, 4)) & 0x7FFF)
            count = pick(rng, [0, 1, 2, 3, 4, 5, 6, 7], [12, 15], 0.05)
            st.fill(rec, 4 + 12 * count + 8)
            st.put(rec, 2, rid)
            st.put(rec + 2, 2, count)
            for i in range(count):
                e = rec + 4 + 12 * i
                make_entry(st, e)
                entries.append(e)
        if rng.random() < 0.03:  # an unmapped next pointer at the end of a chain
            st.put(prev, 4, rng.choice(UNMAPPED))
    return entries


def make_entry(st, e: int) -> None:
    rng = st.rng
    st.put(e, 2, pick(rng, PIDS, [0, 0xFFFF, 0x99], 0.05))
    st.put(e + 2, 2, pick(rng, list(range(0, 40)), [0x7F, 0x200, 0xFFFF], 0.04))
    # thresholds for C, B, A, S: mostly increasing, some levels missing (99)
    t = sorted(pick(rng, THRESHOLDS, THRESHOLDS_RARE, 0.1) for _ in range(4))
    if rng.random() < 0.05:  # no level at all
        t = [rng.choice([99, 99, 100, 255]) for _ in range(4)]
    if rng.random() < 0.2:
        rng.shuffle(t)
    for i, v in enumerate(t):
        st.put(e + 4 + i, 1, v)
    st.put(e + 8, 1, pick(rng, [0, 0, 1], [2, 0x80, 0xFF], 0.1))


# ------------------------------------------------------------------ units and persons
def make_person(st, k: int) -> int:
    rng = st.rng
    p = PERSON(k)
    st.fill(p, 0x98)
    st.put(p + 0x24, 2, PIDS[k])
    sid = pick(rng, [k, k, 0x80 + k, 0x100 + (k % 3), 3], [0xFFFF, 0x8000, 0x7FFF, 0x7F], 0.06)
    st.put(p + 0x30, 2, sid)
    for f in range(2):
        if rng.random() < 0.7:
            st.put(p + f * 4, 4, word(st, p + f * 4) & ~word(st, TRADE_MASK + f * 4))
    st.oracle[(IS_DOWNLOAD, p)] = int(rng.random() < 0.25) * rng.choice([1, 1, 2, 0x100])
    return p


def make_unit(st, k: int) -> int:
    rng = st.rng
    u, j = UNIT(k), JOB(k)
    st.fill(u, 0x140)
    st.fill(j, 0x80)
    st.put(u + 0x9C, 4, PERSON(k))
    st.put(u + 0xA0, 4, j)
    st.put(u + 0xA4, 4, FORCE(k))
    st.fill(FORCE(k), 0x10)
    st.put(FORCE(k) + 8, 1, pick(rng, [0, 0, 1, 2, 3, 4], [5, 7, 255]))
    state = rng.randrange(1 << 32)
    for bit, pr in ((0x40000, 0.12), (0x10000000, 0.35)):
        state = (state | bit) if rng.random() < pr else (state & ~bit)
    st.put(u + 8, 4, state)
    for f in range(2):
        for base in (u, j):
            if rng.random() < 0.8:
                st.put(base + f * 4, 4, word(st, base + f * 4) & ~word(st, TRADE_MASK + f * 4))
    partner = UNIT(rng.randrange(NUNITS))
    st.put(u + 0xA8, 4, ptr_or(st, partner, 0.5, 0.02))
    st.put(u + 0xB4, 4, ptr_or(st, FAMILY(k), 0.4, 0.03))
    make_family(st, k)
    st.put(u + 0x11C, 4, ptr_or(st, POINTS(k), 0.1, 0.03))
    st.zero(POINTS(k), 0x80)
    for i in range(0x80):
        st.put(POINTS(k) + i, 1, pick(rng, [0, 0, 1, 2, 4, 5, 8, 10, 15, 20, 30, 40], [99, 100, 255], 0.05))
    return u


def a_person(st, p_none: float = 0.25) -> int:
    rng = st.rng
    r = rng.random()
    if r < p_none:
        return 0
    if r < p_none + 0.03:
        return rng.choice(UNMAPPED)
    return PERSON(rng.randrange(NPERSONS))


def make_family(st, k: int) -> None:
    rng = st.rng
    f = FAMILY(k)
    st.fill(f, 0x40)
    for side in (0, 0x14):
        st.put(f + side, 4, a_person(st, 0.15))
        st.put(f + side + 8, 4, a_person(st, 0.4))
        st.put(f + side + 0xC, 4, a_person(st, 0.4))
        st.put(f + side + 0x10, 1, pick(rng, [0, 1, 3, 5, 7, 10, 12], [-1 & 0xFF, 0x80, 99]))
    st.put(f + 0x28, 1, pick(rng, [0, 1, 3, 5, 7, 10, 12], [0xFF, 0x80, 99]))


def relate(st, units: list[int]) -> None:
    """focused: make some real families (parent and child, siblings, an uncle or aunt)"""
    rng = st.rng
    if rng.random() < 0.6:  # unit c is a child of unit p's person
        c, p = rng.sample(range(NUNITS), 2)
        if word(st, UNIT(c) + 0xB4) == FAMILY(c):
            st.put(FAMILY(c) + rng.choice([0, 0x14]), 4, PERSON(p))
    if rng.random() < 0.5:  # siblings: same first or second parent
        a, b = rng.sample(range(NUNITS), 2)
        side = rng.choice([0, 0x14])
        st.put(FAMILY(b) + side, 4, word(st, FAMILY(a) + side))
    if rng.random() < 0.5:  # uncle / aunt: a's grandparent is b's parent
        a, b = rng.sample(range(NUNITS), 2)
        g = PERSON(rng.randrange(NPERSONS))
        st.put(FAMILY(a) + rng.choice([8, 0xC, 0x1C, 0x20]), 4, g)
        st.put(FAMILY(b) + rng.choice([0, 0x14]), 4, g)
    if rng.random() < 0.4:  # a support entry for a pair of units
        a, b = rng.sample(range(NUNITS), 2)
        give_entry(st, PERSON(a), PERSON(b))


def give_entry(st, person: int, other: int) -> None:
    """put an entry for other into person's first matching record (if there is one)"""
    sid = word(st, person + 0x30, 2)
    if sid & 0x8000 or word(st, G_RELIANCE) != BUCKETS:
        return
    node = word(st, BUCKETS + 4 * (sid & 0x7F))
    while NODE(0) <= node < NODE(200):
        rec = word(st, node)
        if RECORD(0) <= rec < RECORD(60) and word(st, rec, 2) == sid and word(st, rec + 2, 2) > 0:
            i = st.rng.randrange(word(st, rec + 2, 2))
            st.put(rec + 4 + 12 * i, 2, word(st, other + 0x24, 2))
            if st.rng.random() < 0.5:  # an S level
                st.put(rec + 4 + 12 * i + 7, 1, st.rng.choice([10, 20, 30, 40]))
            return
        node = word(st, node + 4)


def answer_world(st) -> None:
    """what the table-answered guest functions give"""
    rng = st.rng
    for pid in PIDS + [0, 0xFFFF, 0x99]:
        st.oracle[(PERSON_GET, pid)] = PERSON(PIDS.index(pid)) if pid in PIDS and rng.random() > 0.05 \
            else rng.choice([0, PERSON(rng.randrange(NPERSONS))] + UNMAPPED[:1])
    for t in list(range(8)) + [255]:
        st.oracle[(MASK_SAME_FORCE, t)] = rng.choice([0, 2, 4, 25, 0x1F, 0xFFFFFFFF])
    masks = set(st.oracle[(MASK_SAME_FORCE, t)] for t in list(range(8)) + [255])
    for pid in PIDS + [0, 0xFFFF, 0x99]:
        for m in masks:
            r = rng.random()
            st.oracle[(POOL_FROM_PERSON, pid, m)] = (UNIT(rng.randrange(NUNITS)) if r < 0.7 else
                                                     0 if r < 0.95 else rng.choice(UNMAPPED))


def answer_max(st, addrs) -> None:
    for a in addrs:
        st.oracle[(PARENT_MAX, s32(a))] = pick(st.rng, [3], [0, 4, 0xFFFFFFFF], 0.1)
        st.oracle[(BROTHER_MAX, s32(a))] = pick(st.rng, [3], [0, 2, 7], 0.1)


def base_state(rng):
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.zero(CACHE_BASE, CACHE_END - CACHE_BASE)
    st.put(TRADE_GUARD, 4, 0 if rng.random() < 0.03 else rng.choice([1, 0x101, 0xFFFFFFFF]))
    st.put(TRADE_MASK, 8, 1 << rng.randrange(64))
    for k in range(NPERSONS):
        make_person(st, k)
    units = [make_unit(st, k) for k in range(NUNITS)]
    st.entries = make_table(st)
    relate(st, units)
    answer_world(st)
    fams = [FAMILY(k) + d for k in range(NUNITS) for d in (0, 0x14, 0x28)]
    answer_max(st, fams + [0, 0x28] + [x + d for x in UNMAPPED for d in (0, 0x14, 0x28)])
    st.torn = None
    return st, units


def torn_copy(st, source: int, cuts) -> int:
    """a copy of a record that stops (unmapped from there on) at one of the offsets the readers read"""
    cut = st.rng.choice(cuts)
    base = TORN_END - cut
    for i in range(cut):
        st.mem[base + i] = st.mem.get(source + i, 0)
    return base


def unit_arg(st, units, p_unmapped: float = 0.06, p_torn: float = 0.08) -> int:
    r = st.rng.random()
    if r < p_unmapped:
        u = st.rng.choice(UNMAPPED)
    elif r < p_unmapped + p_torn and st.torn is None:
        u = st.torn = torn_copy(st, st.rng.choice(units), TORN_UNIT_CUTS)
    else:
        return st.rng.choice(units)
    st.oracle.setdefault((IS_DOWNLOAD, word(st, u + 0x9C)), int(st.rng.random() < 0.5))
    return u


def person_arg(st, p_unmapped: float = 0.05, p_torn: float = 0.08) -> int:
    r = st.rng.random()
    if r < p_unmapped:
        return st.rng.choice(UNMAPPED)
    if r < p_unmapped + p_torn and st.torn is None:
        st.torn = torn_copy(st, PERSON(st.rng.randrange(NPERSONS)), TORN_PERSON_CUTS)
        return st.torn
    return PERSON(st.rng.randrange(NPERSONS))


def entry_arg(st) -> int:
    rng = st.rng
    r = rng.random()
    if st.entries and r < 0.85:
        return rng.choice(st.entries)
    if r < 0.92:
        return rng.choice(UNMAPPED)
    e = RECORD(59) + 0x10  # a loose made-up entry
    st.fill(e, 12)
    make_entry(st, e)
    return e


def points_arg(rng) -> int:
    return s32(pick(rng, [0, 1, 2, 3, 4, 5, 8, 9, 10, 11, 15, 20, 25, 30, 40, 99],
                    [-1, -100, 100, 255, 256, 0x7FFFFFFF, -0x80000000], 0.12))


def family_arg(st) -> int:
    rng = st.rng
    r = rng.random()
    if r < 0.85:
        return FAMILY(rng.randrange(NUNITS))
    if r < 0.93:
        return rng.choice(UNMAPPED)
    return torn_copy(st, FAMILY(rng.randrange(NUNITS)), (0x04, 0x08, 0x0C, 0x14, 0x18, 0x1C, 0x20))


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def ov(name, args):
    a = OVERRIDES[name][0]
    return f"ov:0x{a:08X}", [s32(x) for x in args] + [0] * (4 - len(args)), ("call", a)


def gen_entry_only(name):
    def gen(rng):
        st, _units = base_state(rng)
        return (st,) + ov(name, [entry_arg(st)])
    return gen


def gen_entry_points(name):
    def gen(rng):
        st, _units = base_state(rng)
        return (st,) + ov(name, [entry_arg(st), points_arg(rng)])
    return gen


def gen_person(name):
    def gen(rng):
        st, _units = base_state(rng)
        return (st,) + ov(name, [person_arg(st)])
    return gen


def gen_entry_index(rng):
    st, _units = base_state(rng)
    i = pick(rng, [0, 0, 1, 2, 3, 4, 5, 6, 8, 10, 12], [-1, -5, 100, 0x7FFFFFFF, -0x80000000], 0.08)
    person = person_arg(st)
    if rng.random() < 0.1 and word(st, G_RELIANCE) == BUCKETS:
        # focused: an unmapped chain node in the bucket of support id 0 and a negative index: the game
        # reads the node's record word a second time before it returns (unmapped: counted)
        person = PERSON(0)
        st.put(person + 0x30, 2, 0)
        st.put(BUCKETS, 4, rng.choice(UNMAPPED))
        i = rng.choice([-1, -2, -7])
    return (st,) + ov("reliance_entry", [person, i])


def gen_find(rng):
    st, _units = base_state(rng)
    p = person_arg(st)
    o = person_arg(st, 0.04, 0.06) if st.torn is None else PERSON(rng.randrange(NPERSONS))
    if rng.random() < 0.4 and PERSON(0) <= p < PERSON(NPERSONS) and PERSON(0) <= o < PERSON(NPERSONS):
        give_entry(st, p, o)
    return (st,) + ov("reliance_find", [p, o])


def gen_family_unit(rng):
    st, units = base_state(rng)
    return (st,) + ov("family_parent_record", [family_arg(st), unit_arg(st, units)])


def gen_family_points(name):
    def gen(rng):
        st, _units = base_state(rng)
        return (st,) + ov(name, [family_arg(st), points_arg(rng)])
    return gen


def gen_family(name):
    def gen(rng):
        st, _units = base_state(rng)
        return (st,) + ov(name, [family_arg(st)])
    return gen


def gen_situation(rng):
    st, _units = base_state(rng)
    st.fill(SITUATION, 0x20)
    for f in range(4):
        st.put(SITUATION + f, 1, pick(rng, [0, 1, 1, 1], [2, 0xFF]))
    flags = word(st, SITUATION + 4)
    st.put(SITUATION + 4, 4, flags & ~0x200000 if rng.random() < 0.7 else flags | 0x200000)
    s = SITUATION if rng.random() > 0.05 else rng.choice(UNMAPPED)
    force = pick(rng, [0, 1, 2, 0, 1, 2, 3], [4, 0xFF, 0xFFFFFFFF, 0x80000000])
    return (st,) + ov("situation_can_gain_support", [s, force])


def gen_unit_entry(rng):
    st, units = base_state(rng)
    return (st,) + ov("unit_support_points", [unit_arg(st, units), entry_arg(st)])


def focus_pair(st, u: int, o: int, kinds=None, tiny: bool = False) -> None:
    """focused: the two units unique (mostly) and related one way or another. kinds / tiny (round 11, SHARP
    only): the relation drawn from kinds, and the shared Person pointer made the small value 1"""
    rng = st.rng
    ku, ko = (u - UNIT(0)) // 0x400, (o - UNIT(0)) // 0x400
    for x in (u, o):
        if rng.random() < 0.85:
            st.put(x + 8, 4, word(st, x + 8) & ~0x40000)
    # round 11 review: uncle1 / nephew1 three times as often (the review's plant on the other way's grandfather
    # test, mine's second parent not asked, was caught by 1 case of 150)
    kind = rng.choice(kinds or ["child", "child", "parent", "sibling", "sibling", "uncle", "uncle", "nephew", "entry",
                                "entry", "uncle1", "nephew1", "uncle1", "nephew1", "uncle1", "nephew1"])
    fu, fo = FAMILY(ku), FAMILY(ko)
    if kind in ("child", "sibling", "uncle", "uncle1"):
        st.put(u + 0xB4, 4, fu)
    if kind in ("parent", "sibling", "nephew", "nephew1"):
        st.put(o + 0xB4, 4, fo)
    if kind == "child":
        st.put(fu + rng.choice([0, 0x14]), 4, PERSON(ko))
    elif kind == "parent":
        st.put(fo + rng.choice([0, 0x14]), 4, PERSON(ku))
    elif kind == "sibling":
        side = rng.choice([0, 0x14])
        st.put(fo + side, 4, word(st, fu + side))
        if tiny:
            st.put(fu + side, 4, 1)
            st.put(fo + side, 4, 1)
    elif kind in ("uncle", "nephew", "uncle1", "nephew1"):
        a, b, fa = (fu, o, u) if kind.startswith("uncle") else (fo, u, o)
        st.put(b + 0xB4, 4, FAMILY((b - UNIT(0)) // 0x400))
        fb = FAMILY((b - UNIT(0)) // 0x400)
        g = PERSON(rng.randrange(NPERSONS))
        if tiny:
            g = 1
        for side in (0, 0x14):  # both parents set (the game needs them)
            if word(st, a + side) == 0 and rng.random() < 0.9:
                st.put(a + side, 4, PERSON(rng.randrange(NPERSONS)))
            if word(st, fb + side) == 0 and rng.random() < 0.9:
                st.put(fb + side, 4, PERSON(rng.randrange(NPERSONS)))
        which = rng.choice([(8, 0), (0x1C, 0), (0xC, 0x14), (0x20, 0x14)])
        if which[0] in (0x1C, 0x20):
            st.put(a + which[0] - 0x14, 4, 0)  # the first parent's grandparent missing: the second one counts
        st.put(a + which[0], 4, g)
        st.put(fb + which[1], 4, g)
        if kind.endswith("1"):
            # round 11: the same relation with ONE parent missing, on either record (the grandparent's side or
            # the other unit's, the matching parent or the other one): the game's both-parents tests answer 0
            # there, or (other way round) may still find the relation
            rec, side = rng.choice([(a, 0), (a, 0x14), (fb, 0), (fb, 0x14), (fb, which[1]), (fb, which[1] ^ 0x14)])
            st.put(rec + side, 4, 0)
        del fa
    else:
        give_entry(st, PERSON(ku), PERSON(ko))
        if rng.random() < 0.5:
            give_entry(st, PERSON(ko), PERSON(ku))


def gen_two_units(name, p_same: float = 0.05):
    def gen(rng):
        st, units = base_state(rng)
        u = unit_arg(st, units)
        o = u if rng.random() < p_same else unit_arg(st, units, 0.04, 0.06)
        if rng.random() < 0.6 and u != o and UNIT(0) <= u < UNIT(NUNITS) and UNIT(0) <= o < UNIT(NUNITS):
            focus_pair(st, u, o)
        return (st,) + ov(name, [u, o])
    return gen


def gen_unit(name):
    def gen(rng):
        st, units = base_state(rng)
        u = unit_arg(st, units)
        if rng.random() < 0.5 and UNIT(0) <= u < UNIT(NUNITS):  # focused: a unique unit with an S partner
            st.put(u + 8, 4, word(st, u + 8) & ~0x40000)
            k = (u - UNIT(0)) // 0x400
            give_entry(st, PERSON(k), PERSON(rng.randrange(NPERSONS)))
        return (st,) + ov(name, [u])
    return gen


def gen_trade(rng):
    st, units = base_state(rng)
    u = unit_arg(st, units)
    o = unit_arg(st, units, 0.04, 0.06)
    if rng.random() < 0.4:  # focused: same force types around
        t = rng.choice([0, 1, 2])
        for k in range(NUNITS):
            if rng.random() < 0.85:
                st.put(FORCE(k) + 8, 1, t)
    return (st,) + ov("unit_can_trade_partner", [u, o])


FUNCS = {
    "reliance_max_level": gen_entry_only("reliance_max_level"),
    "reliance_level": gen_entry_points("reliance_level"),
    "reliance_person": gen_entry_only("reliance_person"),
    "reliance_is_romance": gen_entry_only("reliance_is_romance"),
    "reliance_count": gen_person("reliance_count"),
    "reliance_entry": gen_entry_index,
    "reliance_find": gen_find,
    "family_parent_record": gen_family_unit,
    "family_parent_level": gen_family_points("family_parent_level"),
    "family_sibling_level": gen_family_points("family_sibling_level"),
    "family_grandfather": gen_family("family_grandfather"),
    "family_grandmother": gen_family("family_grandmother"),
    "situation_can_gain_support": gen_situation,
    "unit_support_points": gen_unit_entry,
    "unit_support_level": gen_two_units("unit_support_level"),
    "unit_support_max_level": gen_two_units("unit_support_max_level"),
    "unit_can_support": gen_two_units("unit_can_support"),
    "unit_family_child": gen_two_units("unit_family_child"),
    "unit_is_parent_child": gen_two_units("unit_is_parent_child"),
    "unit_is_sibling": gen_two_units("unit_is_sibling"),
    "unit_is_uncle_aunt": gen_two_units("unit_is_uncle_aunt"),
    "unit_is_family": gen_two_units("unit_is_family"),
    "unit_can_romance": gen_two_units("unit_can_romance"),
    "unit_spouse_pid": gen_unit("unit_spouse_pid"),
    "unit_can_trade_partner": gen_trade,
}


# ------------------------------------------------------------------ sharper cases (round 11, F-025)
# Planted bugs (H6 survivors) that no case above reached; docs/harness/H6_SURVIVORS.md. make_cases runs SHARP
# from its own random stream (n // 3 cases each), so the cases of FUNCS stay exactly as they were.

def gen_tiny(name, kinds):
    """siblings, or an uncle / aunt either way, whose shared Person pointer is the small value 1 (never a real
    address; these readers only compare it): a "not 0" test written as "not 1" shows"""
    def gen(rng):
        st, units = base_state(rng)
        u, o = rng.sample(units, 2)
        focus_pair(st, u, o, kinds=kinds, tiny=True)
        return (st,) + ov(name, [u, o])
    return gen


SHARP = [
    ("unit_is_sibling", gen_tiny("unit_is_sibling", ["sibling"])),
    ("unit_is_uncle_aunt", gen_tiny("unit_is_uncle_aunt", ["uncle", "nephew", "uncle", "nephew"])),
]


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY (stubbed or run as ARM code) and every
    tail branch (B) to a stubbed callee, with its argument registers."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.listed.append(call_text(target, self.r[:ARITY[target]]))
        return super().call(target, ret)

    def step(self, ins: int, pc: int) -> None:
        c = ins >> 28
        if c != 0xF and (ins >> 25) & 7 == 5 and not ins & (1 << 24) and self.cond(c):
            target = (pc + 8 + (A.sx(ins & 0xFFFFFF, 24) << 2)) & MASK
            if target in LEAF_STUBS:  # a tail call to a stubbed guest function: listed like a call
                self.listed.append(call_text(target, self.r[:ARITY[target]]))
                self.r[0] = self.stubs[target](self, tuple(self.r[:4])) & MASK
                self.r[15] = self.r[14]
                return
            # a tail branch to an override runs on as ARM code, unlisted: 3dsrecomp keeps the target's code
            # inside the caller's generated function, so the original never enters that override
        super().step(ins, pc)


def call_text(target: int, regs) -> str:
    return f"{target:x}" + "".join(f":{r & MASK:x}" for r in regs)


def calls_field(listed: list[str]) -> str:
    return ",".join(listed) if listed else "-"


def arm_run(text: bytes, st, kind: str, args: list[int], how: tuple) -> list:
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def answer(f, n):
        return lambda cpu, a: st.oracle.get((f,) + tuple(x & MASK for x in a[:n]), 0)
    stubs = {f: answer(f, n) for f, n in LEAF_STUBS.items()}
    cpu = ListingCpu(mem, stubs, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & MASK
    try:
        cpu.run(how[1])
    except A.ColdGuard:
        return [1]
    return [0, cpu.r[0], mem.faults, calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/support/tests/support_diff.py: runs readable support functions on
   memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "support.h"

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

DRIVER_OVERRIDES = sorted({a for a, _n in OVERRIDES.values()})


def driver_text() -> str:
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in DRIVER_OVERRIDES)
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in DRIVER_OVERRIDES) + "};\n"
    return DRIVER.replace("@OVERRIDE_DECLS@", decls + table)


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


def build_driver(cc: str, out: str, src_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, the support folder's taken from src_dir
    (a planted bug may leave a parameter unused: not strict then, warnings are not errors)."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "support_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_SUPPORT)):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(src_dir, f) for f in os.listdir(src_dir) if f.endswith(".c")]
    exe = os.path.join(out, "support_driver.exe" if os.name == "nt" else "support_driver")
    inc = ["-I", src_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    warn = ["-Wall", "-Wextra", "-Werror"] if strict else ["-w"]
    cmd = [cc, "-std=c11"] + warn + ["-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"support_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
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
        raise SystemExit(f"support_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
    # support_records.c: the record readers
    ("support_records.c", "    for (int32_t level = 4; level > 1; level--)\n        if (points_needed(ctx, reliance, level) < RELIANCE_POINTS_NEVER)",
     "    for (int32_t level = 4; level > 1; level--)\n        if (points_needed(ctx, reliance, level) <= RELIANCE_POINTS_NEVER)"),
    ("support_records.c", "    return points_needed(ctx, reliance, 1) < RELIANCE_POINTS_NEVER ? 1 : 0;",
     "    return 1;"),
    ("support_records.c", "        if ((int32_t)points_needed(ctx, reliance, level) <= points)",
     "        if ((int32_t)points_needed(ctx, reliance, level) < points)"),
    # the level compared unsigned against a negative number of points
    ("support_records.c", "    return (int32_t)points_needed(ctx, reliance, 1) <= points ? 1 : 0;",
     "    return points_needed(ctx, reliance, 1) <= (uint32_t)points ? 1 : 0;"),
    ("support_records.c", "    return guest_call1(ctx, SUP_PersonGet, guest_u16(ctx, reliance + RELIANCE_PARTNER));",
     "    return guest_call1(ctx, SUP_PersonGet, guest_u16(ctx, reliance + RELIANCE_SLOT));"),
    ("support_records.c", "    return points_needed(ctx, reliance, 4) < RELIANCE_POINTS_NEVER ? 1u : 0u;",
     "    return points_needed(ctx, reliance, 3) < RELIANCE_POINTS_NEVER ? 1u : 0u;"),
    # the table: the bucket mask, the id compare, the count, the walk
    ("support_records.c", "    return guest_ptr(ctx, buckets + ((uint32_t)*id & RELIANCE_BUCKETS_MASK) * 4u);",
     "    return guest_ptr(ctx, buckets + ((uint32_t)*id & 0x3Fu) * 4u);"),
    ("support_records.c", "        if (guest_u16(ctx, record + RELIANCE_REC_ID) == (uint32_t)id)\n            count = fe_add32",
     "        if (1)\n            count = fe_add32"),
    # the count stops at the first matching record
    ("support_records.c", "            count = fe_add32(count, guest_u16(ctx, record + RELIANCE_REC_COUNT));\n    }",
     "            return fe_add32(count, guest_u16(ctx, record + RELIANCE_REC_COUNT));\n    }"),
    ("support_records.c", "        if (count <= index) {", "        if (count < index) {"),
    # the record pointer not read again: the same address, one read less per hit (an unmapped node shows it)
    ("support_records.c", "        return entry_at(node_record(ctx, node), index);", "        return entry_at(record, index);"),
    ("support_records.c", "    return record + RELIANCE_REC_ENTRIES + (gaddr)i * RELIANCE_ENTRY_SIZE;",
     "    return record + RELIANCE_REC_ENTRIES + (gaddr)i * 8u;"),
    # other's number read once for both parts: same answers, fewer unmapped reads with a torn Person
    ("support_records.c", "        if (i < count) {\n            uint32_t wanted = READ_FIELD(ctx, PersonData, other, pid_number);",
     "        uint32_t wanted = READ_FIELD(ctx, PersonData, other, pid_number);\n        if (i < count) {"),
    # the search stops at the first record of the id
    ("support_records.c", "                    return entry_at(record, i);\n        }\n    }\n    return 0;",
     "                    return entry_at(record, i);\n        }\n        return 0;\n    }\n    return 0;"),
    # a negative support id taken as a list
    ("support_records.c", "    *id = READ_FIELD(ctx, PersonData, person, support_id);\n    if (*id < 0)",
     "    *id = READ_FIELD(ctx, PersonData, person, support_id) & 0x7FFF;\n    if (*id < 0)"),
    # family
    ("support_records.c", "    if (guest_ptr(ctx, family + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) == person)\n        return family + FAMILY_PARENT_B;",
     "    if (guest_ptr(ctx, family + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) == person)\n        return family;"),
    ("support_records.c", "    if (points >= 10)\n        return 3;", "    if (points > 10)\n        return 3;"),
    ("support_records.c", "    return points >= 1 ? 1 : 0;", "    return points >= 0 ? 1 : 0;"),
    ("support_records.c", "    (void)sibling;\n    return family_level(points);",
     "    (void)sibling;\n    return family_level(points) > 2 ? 2 : family_level(points);"),
    ("support_records.c", "    return g != 0 ? g : guest_ptr(ctx, family + FAMILY_PARENT_B + which);",
     "    return g;"),
    ("support_records.c", "    return grandparent(ctx, family, FAMILY_PARENT_GRANDMOTHER);",
     "    return grandparent(ctx, family, FAMILY_PARENT_GRANDFATHER);"),
    # the "both parents" test of the grandparents halved
    ("support_records.c", "    if (guest_ptr(ctx, family + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) == 0 ||\n        guest_ptr(ctx, family + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) == 0)",
     "    if (guest_ptr(ctx, family + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) == 0)"),
    ("support_records.c", "    if (force >= 3)\n        return 0;", "    if (force > 3)\n        return 0;"),
    ("support_records.c", "    return guest_u8(ctx, situation + force) == 1 ? 1u : 0u;",
     "    return guest_u8(ctx, situation + force) != 0 ? 1u : 0u;"),
    ("support_records.c", "    if (READ_FIELD(ctx, Situation, situation, flags) & SITUATION_NO_SUPPORT_GAIN)\n        return 0;\n", ""),
    # support_unit.c
    ("support_unit.c", "    if (!(READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_MAYBE_CLONE_BIT))\n        return 1;",
     "    if (!(READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_MAYBE_CLONE_BIT))\n        return 0;"),
    # the state word read once: same answers, fewer unmapped reads
    ("support_unit.c", "    if (READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_NOT_UNIQUE_BIT)\n        return 0;\n    if (!(READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_MAYBE_CLONE_BIT))",
     "    uint32_t state = READ_FIELD(ctx, Unit, unit, state_flags);\n    if (state & UNIT_STATE_NOT_UNIQUE_BIT)\n        return 0;\n    if (!(state & UNIT_STATE_MAYBE_CLONE_BIT))"),
    ("support_unit.c", "    if (guest_u8(ctx, reliance + RELIANCE_OWNS_POINTS) == 0) {",
     "    if (guest_u8(ctx, reliance + RELIANCE_OWNS_POINTS) != 0) {"),
    ("support_unit.c", "    return guest_u8(ctx, points + guest_u16(ctx, reliance + RELIANCE_SLOT));",
     "    return guest_s8(ctx, points + guest_u16(ctx, reliance + RELIANCE_SLOT));"),
    ("support_unit.c", "        gaddr parent_unit = child == unit ? other : unit;\n        gaddr parent = guest_call2(ctx, SUP_FamilyGetParent, READ_FIELD(ctx, Unit, child, family), parent_unit);\n        if (parent == 0)\n            return 0;\n        return family_parent_level",
     "        gaddr parent_unit = child == unit ? unit : other;\n        gaddr parent = guest_call2(ctx, SUP_FamilyGetParent, READ_FIELD(ctx, Unit, child, family), parent_unit);\n        if (parent == 0)\n            return 0;\n        return family_parent_level"),
    ("support_unit.c", "        return family_sibling_level(ctx, sibling, guest_u8(ctx, sibling + FAMILY_SIBLING_POINTS));",
     "        return family_sibling_level(ctx, sibling, guest_u8(ctx, sibling + 1u));"),
    # Reliance::GetLevel called through the guest: same answers, one call the generated original does not make
    ("support_unit.c", "    return reliance_level(ctx, entry, points);",
     "    return (int32_t)guest_call2(ctx, SUP_RelianceGetLevel, entry, (uint32_t)points);"),
    ("support_unit.c", "    if (level == 4 && (guest_call1(ctx, SUP_PersonIsDownload, READ_FIELD(ctx, Unit, unit, person)) != 0 ||",
     "    if (level >= 3 && (guest_call1(ctx, SUP_PersonIsDownload, READ_FIELD(ctx, Unit, unit, person)) != 0 ||"),
    # the game's GetMaxLevel call left out: the same 3 when the stub says 3, one guest call less
    ("support_unit.c", "        return (int32_t)guest_call1(ctx, SUP_ParentGetMaxLevel, parent);",
     "        return 3;"),
    ("support_unit.c", "    if (guest_call2(ctx, SUP_UnitIsFamily, unit, other) != 0)\n        return 1;",
     "    if (guest_call2(ctx, SUP_UnitIsFamily, unit, other) != 0)\n        return 0;"),
    # the romance test before the uncle test (the game asks the uncle test first)
    ("support_unit.c", "    if (guest_call2(ctx, SUP_UnitIsFamilyUncleAunt, unit, other) != 0 &&\n        guest_call2(ctx, SUP_UnitIsRomance, unit, other) != 0)",
     "    if (guest_call2(ctx, SUP_UnitIsRomance, unit, other) != 0 &&\n        guest_call2(ctx, SUP_UnitIsFamilyUncleAunt, unit, other) != 0)"),
    ("support_unit.c", "            return other;\n    }\n    return 0;", "            return unit;\n    }\n    return 0;"),
    ("support_unit.c", "    return guest_call2(ctx, SUP_UnitGetFamilyChildImpl, unit, other) != 0 ? 1u : 0u;",
     "    return guest_call2(ctx, SUP_UnitGetFamilyChildImpl, other, unit) != 0 ? 1u : 0u;"),
    ("support_unit.c", "        gaddr b = guest_ptr(ctx, theirs + FAMILY_PARENT_A + FAMILY_PARENT_PERSON);\n        if (b != 0 && a == b)\n            return 1;",
     "        gaddr b = guest_ptr(ctx, theirs + FAMILY_PARENT_B + FAMILY_PARENT_PERSON);\n        if (b != 0 && a == b)\n            return 1;"),
    # uncle / aunt: the grandmother compared with the first parent; the second direction left out;
    # the family word not read again (same answers, fewer reads)
    ("support_unit.c", "                gaddr b = guest_ptr(ctx, theirs + FAMILY_PARENT_B + FAMILY_PARENT_PERSON);\n                if (b != 0 && b == grandmother)",
     "                gaddr b = guest_ptr(ctx, theirs + FAMILY_PARENT_A + FAMILY_PARENT_PERSON);\n                if (b != 0 && b == grandmother)"),
    ("support_unit.c", "    if (READ_FIELD(ctx, Unit, other, family) == 0)\n        return 0;\nother_way:;",
     "    return 0;\nother_way:;"),
    ("support_unit.c", "            if (a != 0 && guest_ptr(ctx, mine + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) != 0 && a == grandfather)",
     "            if (a != 0 && guest_ptr(ctx, mine + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) != grandfather)"),
    ("support_unit.c", "    return guest_call2(ctx, SUP_UnitIsFamilyBrotherSister, unit, other) != 0 ? 1u : 0u;\n}",
     "    return 0;\n}"),
    ("support_unit.c", "    if (guest_call2(ctx, SUP_UnitIsFamily, unit, other) != 0)\n        return 0;\n    gaddr entry",
     "    gaddr entry"),
    ("support_unit.c", "        if ((int32_t)guest_call2(ctx, SUP_RelianceGetLevel, entry, points) >= 4) {",
     "        if ((int32_t)guest_call2(ctx, SUP_RelianceGetLevel, entry, points) >= 3) {"),
    ("support_unit.c", "            return guest_ptr(ctx, person + PERSON_PID_STRING);",
     "            return person;"),
    ("support_unit.c", "    if (all_flags(ctx, other) & forbidden)\n        return 0;\n", ""),
    ("support_unit.c", "    if (theirs == 0)\n        return 1;", "    if (theirs == 0)\n        return 0;"),
    ("support_unit.c", "    if (mine == 0 && READ_FIELD(ctx, Unit, other, pair_partner) == 0)\n        return 0;\n", ""),
    # round 11, one-parent uncle / aunt cases: each both-parents test left out in turn
    ("support_unit.c", "    return guest_ptr(ctx, family + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) != 0 &&\n"
     "           guest_ptr(ctx, family + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) != 0;",
     "    return guest_ptr(ctx, family + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) != 0 ||\n"
     "           guest_ptr(ctx, family + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) != 0;"),
    ("support_unit.c", "                if (a != 0 && guest_ptr(ctx, theirs + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) != 0 && a == grandfather)",
     "                if (a != 0 && a == grandfather)"),
    ("support_unit.c", "            if (guest_ptr(ctx, theirs + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) != 0) {",
     "            if (guest_ptr(ctx, theirs + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) != 0 || 1) {"),
    ("support_unit.c", "    if (mine == 0 || guest_ptr(ctx, mine + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) == 0)\n        return 0;\n    gaddr b",
     "    if (mine == 0)\n        return 0;\n    gaddr b"),
    # the cache not asked: the original reaches the guard, the readable code reads on
    ("support_unit.c", "    if (!fe_static_ready(ctx, S_TradeGuard))\n        return fe_use_original(ctx);\n", ""),
    # round 11 review's plants: the other way's grandfather test without mine's second parent; the first way's
    # both-parents test of mine halved to the first parent
    ("support_unit.c", "            if (a != 0 && guest_ptr(ctx, mine + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) != 0 && a == grandfather)",
     "            if (a != 0 && a == grandfather)"),
    ("support_unit.c", "    if (mine != 0 && has_both_parents(ctx, mine)) {",
     "    if (mine != 0 && guest_ptr(ctx, mine + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) != 0) {"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_SUPPORT, d, ignore=shutil.ignore_patterns("tests"))
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
        print("support_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("support_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_SUPPORT)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"support_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad, cold, early) in per.items():
        total_bad += bad
        notes = ([f"{cold} cold: both reached / gave up at the cache"] if cold else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:28s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:28s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("support_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:28s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"support_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"support_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
