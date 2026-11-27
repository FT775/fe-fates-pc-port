#!/usr/bin/env python3
"""Host differential test of the stance readable code against the game's own ARM code.

    python src/readable/battle/tests/stance_diff.py            all functions, 400 cases each
    python src/readable/battle/tests/stance_diff.py -n 2000    more cases
    python src/readable/battle/tests/stance_diff.py --seed 7   another random sequence
    python src/readable/battle/tests/stance_diff.py --only unit_can_pair_with

For every readable function of src/readable/battle/ the test generates made-up guest states
(units, Person and class records, bonus blocks, Personality records, the battle sides and
counters; all random test values, never game data), then

  - runs the ORIGINAL ARM code from the owner's extracted/text.bin in arm_mini.py (a small
    ARM interpreter in this folder; Unicorn is not installed and the project had none), and
  - runs the readable C function on the same memory, built with the host gcc against
    tools/readable/stub/ (the program is written to build/readable/stances/ and linked with
    every source of src/readable/, as tools/readable/tests/host_test.c is),

and compares the results: r0 for overrides (called through their override entry in
readable mode), the values the game writes for helpers. Guest functions the readable code
still calls through guest_call() are answered by the same random table on both sides
(stubs); everything else the original calls (Personality::Get, GameUserData::Get,
PersonEnhance*::*, map::Situation::CanDual) runs as ARM code. A one-time cache that is not
filled must make the original reach the guard routine and the readable code give up.

Exit 0 only when every case of every function matches. Needs extracted/text.bin and a
host C compiler (FE_HOST_CC, or the ones tools/readable/check.py looks for); SKIPs
(exit 0, says so) without them.
"""
from __future__ import annotations

import argparse
import os
import random
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "stances")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json

# guest functions answered by a table (readable code calls them through guest_call)
STUBS = {0x0044A6F8: 1, 0x0053B88C: 3, 0x0053BB20: 3, 0x0052F518: 2, 0x0052DD04: 2}
PERSON_GET, FAM_DUAL, FAM_DOUBLE, RELIANCE, IS_SKILL = STUBS

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x400  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
BLOCK = lambda k: 0x08030000 + k * 0x100  # noqa: E731
PERSONALITY = 0x08040000
EDIT = lambda k: 0x08050000 + k * 0x40  # noqa: E731
FAMILY = lambda k: 0x08060000 + k * 0x40  # noqa: E731
FORCE = lambda k: 0x08070000 + k * 0xC  # noqa: E731
SITUATION, GUD = 0x08080000, 0x08080100
INFO, CALC = 0x08090000, 0x080A0000
SP = 0x0FFFF000
G_GameUserData, G_PersonalityTable, G_Situation = 0x006DA248, 0x006D3B98, 0x006D7ED0


class State:
    """Guest memory of one case (sparse byte map) plus the stub table."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.mem: dict[int, int] = {}
        self.oracle: dict[tuple, int] = {}

    def fill(self, addr: int, n: int) -> None:
        for i in range(n):
            self.mem[addr + i] = self.rng.randrange(256)

    def zero(self, addr: int, n: int) -> None:
        for i in range(n):
            self.mem[addr + i] = 0

    def put(self, addr: int, size: int, value: int) -> None:
        for i in range(size):
            self.mem[addr + i] = (value >> (8 * i)) & 0xFF

    def regions(self) -> list[tuple[int, bytes]]:
        out, keys = [], sorted(self.mem)
        start = prev = None
        buf = bytearray()
        for a in keys:
            if start is None or a != prev + 1:
                if start is not None:
                    out.append((start, bytes(buf)))
                start, buf = a, bytearray()
            buf.append(self.mem[a])
            prev = a
        if start is not None:
            out.append((start, bytes(buf)))
        return out

    def stub(self, func: int, *args: int, value: int) -> None:
        self.oracle[(func,) + tuple(a & 0xFFFFFFFF for a in args[:STUBS[func]])] = value & 0xFFFFFFFF


# ------------------------------------------------------------------ random values
def pick(rng, common, rare=(), p_rare=0.1):
    return rng.choice(rare) if rare and rng.random() < p_rare else rng.choice(common)


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)  # stack
    st.put(G_PersonalityTable, 4, PERSONALITY)
    st.put(G_GameUserData, 4, GUD)
    st.fill(GUD, 0x40)
    for k in range(8):
        st.fill(PERSONALITY + k * 0x40, 0x40)
        st.put(PERSONALITY + k * 0x40 + 0x3C, 1, pick(rng, [-1, 0, 1, 2, 3], [-5, 4, 7]))
        for j in range(3):
            st.put(PERSONALITY + k * 0x40 + 0x3D + j, 1, pick(rng, [0, 1, 2, 3, 4, 5, 6, 7], [8, 200]))
    for k in range(4):
        st.fill(BLOCK(k), 0x100)
    return st


def make_unit(st: State, k: int, *, partner=None, force_type=None) -> int:
    rng = st.rng
    u = UNIT(k)
    st.fill(u, 0x140)
    st.fill(PERSON(k), 0x98)
    st.fill(JOB(k), 0x80)
    st.put(u + 0x9C, 4, PERSON(k))
    st.put(u + 0xA0, 4, JOB(k))
    st.put(PERSON(k) + 0x1C, 4, BLOCK(rng.randrange(4)))
    st.put(PERSON(k) + 0x20, 4, BLOCK(rng.randrange(4)))
    st.put(PERSON(k) + 0x2A, 2, pick(rng, [0, 0, 0x10 + k, 0x20 + k], [0xFFFF]))
    st.put(u + 0xA8, 4, partner if partner is not None else 0)
    st.put(u + 0xB0, 4, EDIT(k) if rng.random() < 0.5 else 0)
    st.fill(EDIT(k), 0x20)
    st.put(EDIT(k) + 0x1A, 1, rng.randrange(8))
    st.put(EDIT(k) + 0x1B, 1, rng.randrange(8))
    fam = FAMILY(k) if rng.random() < 0.6 else 0
    st.put(u + 0xB4, 4, fam)
    st.zero(FAMILY(k), 0x20)
    st.put(FAMILY(k), 4, rng.choice([0, 1, 0x12345678]))
    st.put(FAMILY(k) + 0x14, 4, rng.choice([0, 1, 0x80000000]))
    st.zero(FORCE(k), 0xC)
    st.put(FORCE(k) + 8, 1, force_type if force_type is not None else rng.choice([0, 1, 2, 3, 0xFF]))
    st.put(u + 0xA4, 4, FORCE(k))
    st.put(u + 0x135, 1, pick(rng, [0, 1, 2, 3, 4, 5], [9, 10, 200, 255]))
    return u


def person_get_stubs(st: State, k: int) -> None:
    fid = st.mem[PERSON(k) + 0x2A] | st.mem[PERSON(k) + 0x2B] << 8
    if fid:
        target = PERSON(4 + k) if st.rng.random() < 0.7 else 0
        if target:
            st.fill(target, 0x98)
            st.put(target + 0x1C, 4, BLOCK(st.rng.randrange(4)))
            st.put(target + 0x20, 4, BLOCK(st.rng.randrange(4)))
        st.stub(PERSON_GET, fid, value=target)


def type_arg(rng) -> int:
    return s32(pick(rng, [0, 1, 2, 3], [-1, 4, 7, 0x100, 0x7FFFFFFF, -4]))


def rank_arg(rng) -> int:
    return s32(pick(rng, [0, 1, 2, 3, 4, 5], [-1, -2, 6, 7]))


def guard(st: State, guard_addr: int, cold_p: float = 0.08) -> None:
    st.put(guard_addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).
# kind: "ov:<address>" (override entry, readable mode, result r0) or a helper name.

def gen_attack_total(rng):
    st = base_state(rng)
    return st, "ov:0x0050CBE8", [BLOCK(rng.randrange(4)), type_arg(rng), rank_arg(rng), 0], ("call", 0x0050CBE8)


def gen_guard_total(rng):
    st = base_state(rng)
    return st, "ov:0x0050D968", [BLOCK(rng.randrange(4)), type_arg(rng), rank_arg(rng), 0], ("call", 0x0050D968)


def gen_attack_edit(rng):
    st = base_state(rng)
    st.put(SP, 4, rng.choice([rng.randrange(8), rng.randrange(8), 0x100]))  # bane on the stack
    boon = rng.choice([rng.randrange(8), rng.randrange(8), 0xFF])
    return st, "ov:0x0050CADC", [BLOCK(rng.randrange(4)), type_arg(rng), rank_arg(rng), boon], ("call", 0x0050CADC)


def gen_guard_edit(rng):
    st = base_state(rng)
    st.put(SP, 4, rng.choice([rng.randrange(8), rng.randrange(8), 0x100]))
    boon = rng.choice([rng.randrange(8), rng.randrange(8), 0xFF])
    stat = s32(pick(rng, [0, 1, 2, 3, 4, 5, 6, 7], [0x101, -1]))
    return st, "ov:0x0050D844", [BLOCK(rng.randrange(4)), stat, rank_arg(rng), boon], ("call", 0x0050D844)


def gen_unit_attack(rng):
    st = base_state(rng)
    u = make_unit(st, 0)
    person_get_stubs(st, 0)
    t, r = type_arg(rng), rank_arg(rng)
    st.stub(FAM_DUAL, FAMILY(0), t, r, value=rng.randrange(-20, 20))
    return st, "ov:0x0052E974", [u, t, r, 0], ("call", 0x0052E974)


def gen_unit_guard(rng):
    st = base_state(rng)
    u = make_unit(st, 0)
    p = make_unit(st, 1) if rng.random() < 0.9 else 0
    person_get_stubs(st, 0)
    guard(st, 0x006D9798)
    skill = pick(rng, [5, 17, 0x7FFF], [0x8001, 0xFFFF])
    st.put(0x006D965E, 2, skill)
    rank = rng.choice([-1, 0, 1, 2, 3, 4, 5])
    st.stub(RELIANCE, u, p, value=rank)
    stat = s32(pick(rng, [0, 1, 2, 3, 4, 5, 6, 7], [0x101, -1, 8]))
    st.stub(FAM_DOUBLE, FAMILY(0), stat & 0xFF, rank, value=rng.randrange(-20, 20))
    sk = skill - 0x10000 if skill & 0x8000 else skill
    st.stub(IS_SKILL, p, sk, value=rng.choice([0, 1, 2]))
    return st, "ov:0x00530A34", [u, stat, p, 0], ("call", 0x00530A34)


def gen_unit_move(rng):
    st = base_state(rng)
    u = make_unit(st, 0)
    return st, "ov:0x00530680", [u, rng.choice([0, UNIT(1)]), 0, 0], ("call", 0x00530680)


def gen_can_pair(rng):
    st = base_state(rng)
    same = rng.random() < 0.6
    ft = rng.choice([0, 1, 2])
    u = make_unit(st, 0, partner=rng.choice([0, 0, 0, UNIT(2)]), force_type=ft)
    o = make_unit(st, 1, partner=rng.choice([0, 0, 0, UNIT(3)]), force_type=ft if same else (ft + 1) % 3)
    guard(st, 0x006D99B8)
    mask = 1 << rng.randrange(64)
    st.put(0x006D9CB8, 8, mask)
    for base in (u, PERSON(0), JOB(0), o, PERSON(1), JOB(1)):  # mostly clear of the bit
        v = int.from_bytes(bytes(st.mem[base + i] for i in range(8)), "little")
        if rng.random() < 0.85:
            v &= ~mask
        st.put(base, 8, v)
    return st, "ov:0x0052B60C", [u, o, 0, 0], ("call", 0x0052B60C)


def gen_can_dual(rng):
    st = base_state(rng)
    st.fill(SITUATION, 0x10)
    st.put(SITUATION + 4, 4, rng.choice([0, 0x80000, 0x7FFFF, 0xFFFFFFFF, rng.randrange(1 << 32)]))
    st.put(GUD + 0x28, 4, rng.choice([0, 8, 0xFFFFFFF7, rng.randrange(1 << 32)]))
    for t in range(4):
        st.put(SITUATION + t, 1, rng.choice([0, 1, 1, 2, 0xFF]))
    t = rng.choice([0, 1, 2, 3, 3, 9, 0xFFFFFFFF])
    return st, "ov:0x005281B8", [SITUATION, t, 0, 0], ("call", 0x005281B8)


def battle_state(rng) -> State:
    """Four sides, two leads with an ally or a partner behind them, the counters."""
    st = base_state(rng)
    st.fill(INFO, 0x810)
    st.fill(CALC, 0x40)
    st.put(CALC, 4, INFO)
    st.put(G_Situation, 4, SITUATION if rng.random() < 0.9 else 0)
    st.fill(SITUATION, 0x10)
    st.put(SITUATION + 4, 4, rng.choice([0, 0x80000]))
    st.put(GUD + 0x28, 4, rng.choice([0, 8]))
    for t in range(4):
        st.put(SITUATION + t, 1, rng.choice([0, 1]))
    for k in range(2):
        paired = rng.random() < 0.55
        lead = make_unit(st, k, partner=UNIT(k + 2) if paired else 0, force_type=rng.choice([0, 1, 2]))
        behind = make_unit(st, k + 2, partner=lead if paired else 0, force_type=0)
        side = INFO + k * 0x200
        st.put(side + 4, 4, lead)
        st.put(side + 0x28, 4, rng.choice([0, 0x100, 0x4000, 0x40, 0x2, rng.randrange(1 << 32)]))
        st.put(side + 0x3C, 4, s32(rng.choice([-1, 0, 1, 2])))
        st.put(side + 0x40, 1, rng.choice([0, 0, 0, 1]))
        st.put(side + 0x90, 4, rng.choice([0, behind, behind, UNIT(k + 2) + 0x400 * 0]) if rng.random() < 0.9 else 0)
        st.put(side + 0x400 + 4, 4, behind)
        st.put(side + 0x43C, 4, 0x7777)  # follow-up side's attack count: cleared or not
    st.put(INFO + 0x804, 4, rng.choice([0, 0, 0x10, 0x2, 0x4]))
    for i in range(4):
        st.put(CALC + 0x14 + 4 * i, 4, s32(pick(rng, [0, 1, 2, 3, 4, 5], [9, 10, 11, -1])))
    return st


def gen_dual_plan(rng):
    st = battle_state(rng)
    guard(st, 0x006D69C8)
    skill = pick(rng, [3, 44], [0x8000])
    st.put(0x006D6932, 2, skill)
    sk = skill - 0x10000 if skill & 0x8000 else skill
    for k in range(2):
        st.stub(IS_SKILL, UNIT(k), sk, value=rng.choice([0, 1]))
    return st, "dual_plan", [INFO, rng.randrange(2), 0, 0], ("dual_plan",)


def gen_guard_blocks(rng):
    st = battle_state(rng)
    attacker = rng.randrange(4)
    return st, "guard_blocks", [CALC, attacker, 0, 0], ("guard_blocks", attacker)


def gen_after_strike(rng):
    st = battle_state(rng)
    attacker = rng.randrange(4)
    skill = pick(rng, [7, 99], [0x8002])
    st.put(0x006D6760, 2, skill)
    sk = skill - 0x10000 if skill & 0x8000 else skill
    for k in range(4):
        st.stub(IS_SKILL, UNIT(k), sk, value=rng.choice([0, 1]))
    blocked = rng.random() < 0.3
    return st, "after_strike", [CALC, attacker, int(blocked), 0], ("after_strike", attacker, blocked)


def gen_turn_begin(rng):
    st = base_state(rng)
    u = make_unit(st, 0)
    st.put(u + 8, 4, rng.choice([0, 0x800000, 0xFFFFFFFF, 0xFF7FFFFF, rng.randrange(1 << 32)]))
    return st, "turn_begin", [u, 0, 0, 0], ("turn_begin",)


def gen_follow_up(rng):
    st = base_state(rng)
    st.fill(INFO, 0x200)
    st.put(INFO + 0x28, 4, rng.choice([0, 2, 3, 1, 0xFFFFFFFD, rng.randrange(1 << 32)]))
    dmg = s32(pick(rng, [0, 1, 2, 3, 7, 15, 30, -1, -2, -3], [0x7FFFFFFF, -0x80000000]))
    return st, "follow_up", [INFO, dmg, 0, 0], ("follow_up", dmg)


FUNCS = {
    "stance_attack_bonus_total": gen_attack_total,
    "stance_guard_bonus_total": gen_guard_total,
    "stance_attack_bonus_edit": gen_attack_edit,
    "stance_guard_bonus_edit": gen_guard_edit,
    "unit_attack_stance_bonus": gen_unit_attack,
    "unit_guard_stance_bonus": gen_unit_guard,
    "unit_guard_stance_move": gen_unit_move,
    "unit_can_pair_with": gen_can_pair,
    "situation_can_dual": gen_can_dual,
    "battle_dual_plan": gen_dual_plan,
    "stance_dual_guard_blocks": gen_guard_blocks,
    "stance_gauge_after_strike": gen_after_strike,
    "stance_gauge_at_turn_begin": gen_turn_begin,
    "stance_follow_up_damage": gen_follow_up,
}


# ------------------------------------------------------------------ the ARM side
def arm_run(text: bytes, st: State, args: list[int], how: tuple) -> list[int]:
    """Expected outputs, in the order the C driver prints them: [gave_up, values...]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def stub_fn(func):
        n = STUBS[func]
        return lambda cpu, a: st.oracle.get((func,) + tuple(a[:n]), 0)

    cpu = A.Cpu(mem, {f: stub_fn(f) for f in STUBS}, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    rd = lambda a, n: mem.read(a, n)  # noqa: E731
    kind = how[0]
    try:
        if kind == "call":
            cpu.run(how[1])
            return [0, cpu.r[0]]
        if kind == "dual_plan":
            info, side = args[0], args[1]
            cpu.r[0] = info
            cpu.run(0x00347350)
            if not [w for w in mem.writes if not SP - 0x1000 <= w[0] < SP]:  # pushes do not count
                return [0, 0, 0, 0, 0]
            s = info + side * 0x200
            return [0, 1, rd(s + 0x94, 1), rd(s + 0x98, 4), int(rd(s + 0x43C, 4) == 0)]
        if kind == "guard_blocks":
            attacker = how[1]
            d = 1 if attacker in (0, 2) else 0
            cpu.r[4], cpu.r[5], cpu.r[7] = attacker, CALC, INFO + attacker * 0x200
            mem.map(SP + 120, struct.pack("<I", 0))  # GetSimplePower is not asked for
            cpu.run(0x003633D0, stop={0x00363448})
            cpu.r[6] = INFO + d * 0x200
            pc = cpu.run(0x00363760, stop={0x003637BC, 0x0036382C})
            return [0, int(pc == 0x003637BC)]
        if kind == "after_strike":
            attacker, blocked = how[1], how[2]
            d = 1 if attacker in (0, 2) else 0
            special = int(attacker >= 2 and rd(INFO + d * 0x200 + 0x40, 1) != 0)
            mem.map(SP + 48, struct.pack("<I", special))
            cpu.r[4], cpu.r[5], cpu.r[6] = attacker, CALC, INFO + d * 0x200
            cpu.r[10] = (4 if blocked else 0) | (st.rng.randrange(1 << 32) & ~4)
            cpu.run(0x00364530, stop={0x00364848})
            return [0] + [rd(CALC + 0x14 + 4 * i, 4) for i in range(4)]
        if kind == "turn_begin":
            cpu.r[4], cpu.r[5] = args[0], 0
            cpu.run(0x003A557C, stop={0x003A55B0})
            return [0, rd(args[0] + 8, 4), rd(args[0] + 0x135, 1)]
        if kind == "follow_up":
            cpu.r[6], cpu.r[4] = args[0], args[1] & 0xFFFFFFFF
            cpu.run(0x005259B0, stop={0x005259CC})
            return [0, cpu.r[0]]
    except A.ColdGuard:
        return [1]
    raise ValueError(kind)


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/battle/tests/stance_diff.py: runs readable stance functions on
   memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "stances.h"

static uint8_t **pages, **nopages;
static uint32_t used[4096]; static int nused;
static unsigned faults;
static uint8_t *at(uint32_t a, int make) {
    uint8_t *p = pages[a >> 12];
    if (!p && make && nused < 4096) { p = pages[a >> 12] = calloc(4096, 1); used[nused++] = a >> 12; }
    return p ? p + (a & 0xFFF) : NULL;
}
static uint8_t r8(Context *c, uint32_t a) { (void)c; uint8_t *p = at(a, 0); if (!p) { faults++; return 0; } return *p; }
static uint16_t r16(Context *c, uint32_t a) { return (uint16_t)(r8(c, a) | r8(c, a + 1) << 8); }
static uint32_t r32(Context *c, uint32_t a) { return (uint32_t)r16(c, a) | (uint32_t)r16(c, a + 2) << 16; }
static int writes;
static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; writes++; uint8_t *p = at(a, 0); if (p) *p = v; }
static void w16(Context *c, uint32_t a, uint16_t v) { w8(c, a, (uint8_t)v); w8(c, a + 1, (uint8_t)(v >> 8)); }
static void w32(Context *c, uint32_t a, uint32_t v) { w16(c, a, (uint16_t)v); w16(c, a + 2, (uint16_t)(v >> 16)); }
static void interp(Context *c, uint32_t a, uint32_t o) { (void)c; (void)a; (void)o; }
static void svc(Context *c, uint32_t n) { (void)c; (void)n; }

/* the stub table: (function, args...) -> value; other args -> 0 */
#define MAXO 256
static uint32_t stub_n[8], stub_f[8]; static int nstubs;
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
static Code lookup(Context *c, uint32_t a) {
    (void)c;
    for (int i = 0; i < nstubs; i++) if (stub_f[i] == a) return oracle;
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

void override_0x0050CBE8(Context *); void override_0x0050D968(Context *);
void override_0x0050CADC(Context *); void override_0x0050D844(Context *);
void override_0x0052E974(Context *); void override_0x00530A34(Context *);
void override_0x00530680(Context *); void override_0x0052B60C(Context *);
void override_0x005281B8(Context *);
static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {
    {0x0050CBE8u, override_0x0050CBE8}, {0x0050D968u, override_0x0050D968}, {0x0050CADCu, override_0x0050CADC},
    {0x0050D844u, override_0x0050D844}, {0x0052E974u, override_0x0052E974}, {0x00530A34u, override_0x00530A34},
    {0x00530680u, override_0x00530680}, {0x0052B60Cu, override_0x0052B60C}, {0x005281B8u, override_0x005281B8},
};

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
            noracle = 0; originals = 0; writes = 0;
        } else if (!strncmp(line, "mem ", 4)) {
            uint32_t addr; int off = 0;
            sscanf(line + 4, "%x %n", &addr, &off);
            const char *h = line + 4 + off;
            for (uint32_t i = 0; h[2 * i] && h[2 * i] != '\n' && h[2 * i] != '\r'; i++)
                *at(addr + i, 1) = (uint8_t)(hexval(h[2 * i]) << 4 | hexval(h[2 * i + 1]));
        } else if (!strncmp(line, "oracle ", 7)) {
            uint32_t *k = o_key[noracle];
            sscanf(line + 7, "%x %x %x %x %x %x", &k[0], &k[1], &k[2], &k[3], &k[4], &o_val[noracle]);
            noracle++;
        } else if (!strncmp(line, "run", 3)) {
            Context c = fresh();
            c.r[13] = a[4];
            if (!strncmp(kind, "ov:", 3)) {
                uint32_t addr = (uint32_t)strtoul(kind + 3, NULL, 16);
                for (int i = 0; i < 4; i++) c.r[i] = a[i];
                for (unsigned i = 0; i < sizeof ovs / sizeof ovs[0]; i++) if (ovs[i].a == addr) ovs[i].f(&c);
                if (originals) printf("%u 1\n", id); else printf("%u 0 %u\n", id, c.r[0]);
            } else if (!strcmp(kind, "dual_plan")) {
                BattleDualPlan p; memset(&p, 0, sizeof p);
                int r = battle_dual_plan(&c, a[0], a[1], &p);
                if (fe_gave_up(&c)) printf("%u 1\n", id);
                else if (!r) printf("%u 0 0 0 0 0\n", id);
                else printf("%u 0 1 %u %u %d\n", id, p.dual_attack, (uint32_t)p.gauge_total, p.clear_follow_up);
            } else if (!strcmp(kind, "guard_blocks")) {
                int r = stance_dual_guard_blocks(&c, a[0], a[1]);
                printf("%u %d %d\n", id, fe_gave_up(&c), r);
            } else if (!strcmp(kind, "after_strike")) {
                StanceGauges g; stance_gauge_after_strike(&c, a[0], a[1], (int)a[2], &g);
                printf("%u %d %u %u %u %u\n", id, fe_gave_up(&c), (uint32_t)g.gauge[0], (uint32_t)g.gauge[1],
                       (uint32_t)g.gauge[2], (uint32_t)g.gauge[3]);
            } else if (!strcmp(kind, "turn_begin")) {
                StanceTurnBegin t; stance_gauge_at_turn_begin(&c, a[0], &t);
                printf("%u %d %u %u\n", id, fe_gave_up(&c), t.flags, t.guard_gauge);
            } else if (!strcmp(kind, "follow_up")) {
                int32_t r = stance_follow_up_damage(&c, a[0], (int32_t)a[1]);
                printf("%u %d %u\n", id, fe_gave_up(&c), (uint32_t)r);
            }
            if (writes) printf("%u WROTE-GUEST %d\n", id, writes);
        }
    }
    (void)faults;
    return 0;
}
'''


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


def build_driver(cc: str) -> str:
    os.makedirs(OUT, exist_ok=True)
    src = os.path.join(OUT, "stance_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(DRIVER)
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    exe = os.path.join(OUT, "stance_driver.exe" if os.name == "nt" else "stance_driver")
    inc = ["-I", os.path.join(ROOT, "tools", "readable", "stub"), "-I", os.path.join(ROOT, "include", "readable"),
           "-I", os.path.join(ROOT, "include", "readable", "generated"),
           "-I", os.path.join(ROOT, "src", "readable", "battle")]
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"stance_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=400, help="cases per function (default 400)")
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("stance_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("stance_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc)
    rng = random.Random(a.seed)
    lines = [f"stub {f:x} {n}" for f, n in STUBS.items()]
    expected: dict[int, tuple[str, list[int], tuple]] = {}
    cid = 0
    for name, gen in FUNCS.items():
        if a.only and name != a.only:
            continue
        for _ in range(a.n):
            st, kind, args, how = gen(rng)
            exp = arm_run(text, st, args, how)
            expected[cid] = (name, exp, (kind, args))
            lines.append(f"case {cid} {kind} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
            for addr, data in st.regions():
                for off in range(0, len(data), 4096):
                    lines.append(f"mem {addr + off:x} {data[off:off + 4096].hex()}")
            for key, val in st.oracle.items():
                k = list(key) + [0] * (5 - len(key))
                lines.append("oracle " + " ".join(f"{x:x}" for x in k) + f" {val:x}")
            lines.append("run")
            cid += 1
    log = os.path.join(OUT, "fe_readable.log")
    env = dict(os.environ, FE_READABLE_LOG=log, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        print(f"stance_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
        return 1
    got: dict[int, list[int]] = {}
    wrote: set[int] = set()
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] == "WROTE-GUEST":
            wrote.add(int(parts[0]))
        elif parts:
            got[int(parts[0])] = [int(x) for x in parts[1:]]
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs) in expected.items():
        res = per.setdefault(name, [0, 0, 0])  # cases, mismatches, gave-up cases
        res[0] += 1
        g = got.get(c)
        if exp[0] == 1:
            res[2] += 1
        if g is None or g != exp or c in wrote:
            res[1] += 1
            if res[1] <= a.show:
                why = " (wrote guest memory)" if c in wrote else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    total_bad = 0
    print(f"stance_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold) in per.items():
        total_bad += bad
        print(f"  {name:28s} {n:5d} cases  {bad:3d} mismatches  ({cold} with a cold cache: original reached "
              f"the guard, readable gave up)" if cold else f"  {name:28s} {n:5d} cases  {bad:3d} mismatches")
    print(f"stance_diff: {'OK' if not total_bad else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches)")
    return 1 if total_bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
