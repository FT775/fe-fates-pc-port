#!/usr/bin/env python3
"""Host differential test of the weapon triangle readable code against the game's own ARM code.

    python src/readable/battle/tests/triangle_diff.py             all functions, 400 cases each
    python src/readable/battle/tests/triangle_diff.py -n 2000     more cases
    python src/readable/battle/tests/triangle_diff.py --seed 7    another random sequence
    python src/readable/battle/tests/triangle_diff.py --only weapon_rank_of_exp
    python src/readable/battle/tests/triangle_diff.py --plant     also plant bugs: each must be caught

The same method as stance_diff.py (same folder): for every readable function of
src/readable/battle/triangle_*.c the test makes up guest states (units, classes, Item records,
the sub-kind / rank / bonus / triangle tables, the four battle sides, the one-time caches; all
random test values, never game data), runs the ORIGINAL ARM code from the owner's
extracted/text.bin in arm_mini.py and the readable C function (built with the host gcc against
tools/readable/stub/) on the same memory, and compares:

  - overrides: r0, through their override entry in readable mode;
  - helpers: what the game's code region stores, against what the helper returns. The regions:
      Unit::GetAttack 0x005341FC..0x005342A4 and Unit::GetHit 0x00532F2C..0x00532FD8 (rank bonus),
      BattleInfo::CalculateDetail 0x003479B4..0x00347AEC (lookup) and 0x00347B08..0x00347B6C
      (reversal), Side::CalculateDetailHit 0x00349048..0x00349144 and Side::CalculateDetailAttack
      0x00349970..0x00349A7C (the triangle bonus and the bool passed to GetHit / GetAttack).

unit::Item::ToData, the one guest function the readable code still calls, is answered by the
same table on both sides. Unit::GetHit / GetAttack, called by the two Side regions, are stubs
on the ARM side (they are not part of the triangle helper); their argument and their stored
result are subtracted out. Everything else (ItemSubKind::Get, WeaponLevel::*, WeaponInteract::Get,
WeaponBonus::Get, Unit::GetWeaponExp / GetWeaponExpLimit) runs as ARM code. A one-time cache
that is not filled must make the original reach the guard routine and the readable code give up.

--plant copies the triangle sources to build/readable/triangle/plant/, makes one small wrong
change at a time (a list below: a comparison, an index, a sign, a column...), rebuilds and
reruns: every planted bug must give at least one mismatch.

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
from stance_diff import State, pick, s32  # noqa: E402  (same folder: memory image, random helpers)

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "triangle")
SRC_BATTLE = os.path.join(ROOT, "src", "readable", "battle")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json

TO_DATA = 0x003D0EA4                      # unit::Item::ToData: answered by a table on both sides
STUBS = {TO_DATA: 1}
GET_HIT, GET_ATTACK = 0x00532DC4, 0x00534188  # ARM-side stubs inside the Side::CalculateDetail* regions

# globals and caches (config/readable/globals.csv, src/readable/battle/triangle.h)
G_SUBKIND, G_LEVEL, G_BONUS, G_INTERACT = 0x006D3954, 0x006D3D20, 0x006D3D24, 0x006D3D28
REV_GUARD, REV_MASK = 0x006D6978, 0x006D6A88
LIM_GUARDS = (0x006D97B4, 0x006D97B0, 0x006D97AC)
STONE_MASK, STAFF_MASK, STAFF_FLOOR = 0x006D9A90, 0x006D9A98, 0x006D97B8
DETAIL_CACHE = 0x006D6918  # base register of the CalculateDetail* caches (r8 / r9 in the regions)

# guest layout of the made-up state
SUBKIND, BONUS, LEVEL, INTERACT = 0x08100000, 0x08110000, 0x08120000, 0x08130000
ITEMDATA = lambda k: 0x08140000 + k * 0x80  # noqa: E731
UNIT = lambda k: 0x08000000 + k * 0x400  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x400 + 0x200  # noqa: E731
ITEM = lambda k: 0x08150000 + k * 0x10  # noqa: E731  (a unit::Item outside a battle side)
INFO = 0x08090000
SP = 0x0FFFF000


# ------------------------------------------------------------------ random values
def kind_byte(rng) -> int:
    return pick(rng, [0, 1, 2, 3, 4, 5, 6, 7], [8, 9, 0xFF, 0x80, 0x7F], 0.12) & 0xFF


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.put(G_SUBKIND, 4, SUBKIND)
    st.put(G_LEVEL, 4, LEVEL)
    st.put(G_BONUS, 4, BONUS)
    st.put(G_INTERACT, 4, INTERACT)
    # sub-kind table: indexes -128..127 reachable (Item.weapon_kind is signed)
    st.fill(SUBKIND - 0x800, 0x1000)
    for i in range(-128, 128):
        st.put(SUBKIND + 16 * i + 1, 1, kind_byte(rng))
    # rank thresholds (S first): usually descending, sometimes anything
    if rng.random() < 0.75:
        th = sorted((rng.randrange(256) for _ in range(6)), reverse=True)
    else:
        th = [rng.randrange(256) for _ in range(6)]
    for i, t in enumerate(th):
        st.put(LEVEL + i, 1, t)
    st.put(LEVEL + 6, 2, 0)
    # rank bonus rows: kinds -128..7 reachable
    st.fill(BONUS - 0x700, 0x800)
    for i in range(8 * 12):
        st.put(BONUS + i, 1, pick(rng, [0, 0, 1, 2, 3, 5, 10, -1, -5]) & 0xFF)
    # triangle: rank rows, then the matrix; kinds -128..127 reachable
    st.fill(INTERACT - 0x500, 0xA00)
    for i in range(12):
        st.put(INTERACT + i, 1, pick(rng, [0, 1, 2, 5, 10, 15, 20], [-3, 127, -128]) & 0xFF)
    for i in range(64):
        st.put(INTERACT + 12 + i, 1, pick(rng, [0, 0, 1, -1], [2, -2, 100]) & 0xFF)
    for k in range(8):
        st.fill(ITEMDATA(k), 0x68)
        st.put(ITEMDATA(k) + 0x1A, 1, pick(rng, list(range(21)), [-1, -128, 127, 40]) & 0xFF)
    return st


def guard(st: State, addr: int, cold_p: float = 0.05) -> None:
    st.put(addr, 4, 0 if st.rng.random() < cold_p else st.rng.choice([1, 0x101, 0xFFFFFFFF]))


def caches(st: State, cold_p: float = 0.05) -> None:
    rng = st.rng
    for g in LIM_GUARDS:
        guard(st, g, cold_p)
    guard(st, REV_GUARD, cold_p)
    st.put(STONE_MASK, 8, 1 << rng.randrange(64))
    st.put(STAFF_MASK, 8, 1 << rng.randrange(64))
    st.put(REV_MASK, 8, 1 << rng.randrange(64))
    st.put(STAFF_FLOOR, 4, s32(pick(rng, [0, 20, 50, 100, 150, 255], [-1, 300, -0x80000000])))


def maybe_flag(st: State, addr: int, mask_addr: int, p: float = 0.5) -> None:
    """Keeps or clears the cached mask bit in a 64-bit flag word at addr."""
    mask = int.from_bytes(bytes(st.mem[mask_addr + i] for i in range(8)), "little")
    v = int.from_bytes(bytes(st.mem[addr + i] for i in range(8)), "little")
    v = (v | mask) if st.rng.random() < p else (v & ~mask)
    st.put(addr, 8, v)


def make_unit(st: State, k: int) -> int:
    rng = st.rng
    u = UNIT(k)
    st.fill(u, 0x200)
    st.fill(PERSON(k), 0x10)
    st.fill(JOB(k) - 0x100, 0x200)
    st.put(u + 0x9C, 4, PERSON(k))
    st.put(u + 0xA0, 4, JOB(k))
    for i in range(8):
        st.put(u + 0xE8 + i, 1, pick(rng, [0, 1, 20, 50, 100, 150, 200, 251, 255]))
        st.put(JOB(k) + 0x44 + i, 1, pick(rng, [0, 1, 100, 200, 251, 255]))
    for base in (u, PERSON(k), JOB(k)):  # the two limit bits: mostly clear
        maybe_flag(st, base, STONE_MASK, 0.15)
        maybe_flag(st, base, STAFF_MASK, 0.15)
    return u


def item_at(st: State, addr: int, k: int, rng) -> None:
    """A unit::Item at addr (its u16 item number) that ToData answers with Item record k."""
    st.put(addr, 2, pick(rng, [1, 7, 0x123, 0xFFFF], [0], 0.15))
    st.oracle[(TO_DATA, addr & 0xFFFFFFFF)] = ITEMDATA(k)
    maybe_flag(st, ITEMDATA(k), REV_MASK, 0.3)


def kind_arg(rng) -> int:
    return s32(pick(rng, [0, 1, 2, 3, 4, 5, 6, 6, 7, 7], [8, -1, -128, 0x100]))


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def gen_subkind(rng):
    st = base_state(rng)
    i = s32(pick(rng, list(range(21)), [-1, -128, 127, 0x10000, -0x10000]))
    return st, "ov:0x0019B97C", [i, 0, 0, 0], ("call", 0x0019B97C)


def gen_bonus(rng):
    st = base_state(rng)
    return st, "ov:0x001A8090", [kind_arg(rng), 0, 0, 0], ("call", 0x001A8090)


def gen_level(rng):
    st = base_state(rng)
    return st, "ov:0x001A80D4", [rng.randrange(1 << 32), 0, 0, 0], ("call", 0x001A80D4)


def gen_interact(rng):
    st = base_state(rng)
    return st, "ov:0x001D77B8", [rng.randrange(1 << 32), 0, 0, 0], ("call", 0x001D77B8)


def gen_rank(rng):
    st = base_state(rng)
    th = [st.mem[LEVEL + i] for i in range(6)]
    exp = s32(pick(rng, [rng.randrange(256), rng.choice(th), rng.choice(th) - 1, rng.choice(th) + 1],
                   [-1, -0x80000000, 0x7FFFFFFF, 256], 0.1))
    return st, "ov:0x005090A4", [LEVEL, exp, 0, 0], ("call", 0x005090A4)


def gen_limit(rng):
    st = base_state(rng)
    caches(st)
    u = make_unit(st, 0)
    return st, "ov:0x0052F824", [u, kind_arg(rng), 0, 0], ("call", 0x0052F824)


def gen_exp(rng):
    st = base_state(rng)
    caches(st)
    u = make_unit(st, 0)
    return st, "ov:0x0052DC54", [u, kind_arg(rng), 0, 0], ("call", 0x0052DC54)


def gen_rank_attack(rng):
    st = base_state(rng)
    caches(st)
    u = make_unit(st, 0)
    item_at(st, ITEM(0), rng.randrange(8), rng)
    return st, "rank_attack", [u, ITEM(0), 0, 0], ("rank", 0x005341FC, 0x005342A4)


def gen_rank_hit(rng):
    st = base_state(rng)
    caches(st)
    u = make_unit(st, 0)
    item_at(st, ITEM(0), rng.randrange(8), rng)
    return st, "rank_hit", [u, ITEM(0), 0, 0], ("rank", 0x00532F2C, 0x00532FD8)


def battle_state(rng) -> State:
    """Four sides with units, weapons, triangle cells and flags."""
    st = base_state(rng)
    caches(st)
    st.fill(INFO, 0x800)
    for k in range(4):
        side = INFO + k * 0x200
        st.put(side, 1, k if rng.random() < 0.8 else rng.choice([0, 1, 2, 3, 4, 0xFF]))
        st.put(side + 4, 4, make_unit(st, k) if rng.random() < 0.9 else 0)
        item_at(st, side + 0x10, rng.randrange(8), rng)
        st.put(side + 0x14, 4, s32(pick(rng, [0, 1, -1, 2, -2], [7, -0x80000000, 0x7FFFFFFF])))
        flags = rng.randrange(1 << 32)
        for bit, p in ((0x2000, 0.35), (0x40, 0.2)):
            flags = (flags | bit) if rng.random() < p else (flags & ~bit)
        st.put(side + 0x28, 4, flags)
    st.stub_value = {GET_HIT: rng.randrange(1 << 32), GET_ATTACK: rng.randrange(1 << 32)}
    return st


def gen_lookup(rng):
    st = battle_state(rng)
    side = rng.randrange(4)
    return st, "lookup", [INFO, side, 0, 0], ("lookup", side)


def gen_reverse(rng):
    st = battle_state(rng)
    side = rng.randrange(4)
    return st, "reverse", [INFO, side, 0, 0], ("reverse", side)


def side_pair(rng) -> tuple[int, int]:
    i = rng.randrange(4)
    j = rng.choice([x for x in range(4) if x != i]) if rng.random() < 0.9 else i
    return INFO + i * 0x200, INFO + j * 0x200


def gen_hit_bonus(rng):
    st = battle_state(rng)
    s, o = side_pair(rng)
    return st, "hit_bonus", [s, o, 0, 0], ("detail", 0x00349048, {0x00349144}, {0x003491D4}, GET_HIT, 2)


def gen_attack_bonus(rng):
    st = battle_state(rng)
    s, o = side_pair(rng)
    return st, "attack_bonus", [s, o, 0, 0], ("detail", 0x00349970, {0x00349A7C}, {0x003499C0}, GET_ATTACK, 4)


FUNCS = {
    "item_subkind_record": gen_subkind,
    "weapon_bonus_record": gen_bonus,
    "weapon_level_record": gen_level,
    "weapon_interact_record": gen_interact,
    "weapon_rank_of_exp": gen_rank,
    "unit_weapon_exp_limit": gen_limit,
    "unit_weapon_exp": gen_exp,
    "unit_weapon_rank_attack": gen_rank_attack,
    "unit_weapon_rank_hit": gen_rank_hit,
    "triangle_side_lookup": gen_lookup,
    "triangle_after_reverse": gen_reverse,
    "triangle_hit_bonus": gen_hit_bonus,
    "triangle_attack_bonus": gen_attack_bonus,
}


# ------------------------------------------------------------------ the ARM side
def arm_run(text: bytes, st: State, args: list[int], how: tuple) -> list[int]:
    """Expected outputs, in the order the C driver prints them: [gave_up, values...]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)
    values = getattr(st, "stub_value", {})
    stubs = {TO_DATA: lambda cpu, a: st.oracle.get((TO_DATA, a[0]), 0),
             GET_HIT: lambda cpu, a: values.get(GET_HIT, 0),
             GET_ATTACK: lambda cpu, a: values.get(GET_ATTACK, 0)}
    cpu = A.Cpu(mem, stubs, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    rd = lambda a, n: mem.read(a, n)  # noqa: E731
    kind = how[0]
    try:
        if kind == "call":
            cpu.run(how[1])
            return [0, cpu.r[0]]
        if kind == "rank":
            unit, item = args[0], args[1]
            start, stop = how[1], how[2]
            if start == 0x005341FC:  # GetAttack: r5 item, r6 unit, r4 sum, r8 bonus
                cpu.r[4], cpu.r[5], cpu.r[6], cpu.r[8] = 0, item, unit, 0
            else:                    # GetHit: r6 item, r5 unit, r4 sum, r9 bonus
                cpu.r[4], cpu.r[5], cpu.r[6], cpu.r[9] = 0, unit, item, 0
            cpu.run(start, stop={stop})
            return [0, cpu.r[4]]
        if kind == "lookup":
            side = how[1]
            s = INFO + side * 0x200
            cpu.r[4], cpu.r[5], cpu.r[9] = INFO, side, DETAIL_CACHE
            cpu.run(0x003479B4, stop={0x00347AEC})
            looked = int(any(w[0] == s + 0x14 for w in mem.writes))
            return [0, looked, rd(s + 0x14, 4) if looked else 0, rd(s + 0x28, 4)]
        if kind == "reverse":
            side = how[1]
            cpu.r[4], cpu.r[2] = INFO, side
            cpu.run(0x00347B08, stop={0x00347B6C})
            return [0, rd(INFO + side * 0x200 + 0x14, 4)]
        if kind == "detail":
            start, done, skipped, callee, size = how[1:]
            cpu.r[4], cpu.r[6], cpu.r[8], cpu.r[9] = args[0], args[1], DETAIL_CACHE, DETAIL_CACHE
            pc = cpu.run(start, stop=done | skipped)
            if pc in skipped:
                return [0, 0, 0, 0]
            calls = [c for c in cpu.calls if c[0] == callee]
            if len(calls) != 1:
                raise A.Unsupported(f"expected one call to {callee:08X}, got {len(calls)}")
            keep = calls[0][1][2]
            bits = 8 * size
            stored = rd(cpu.r[5] + (20 if size == 2 else 0), size)
            bonus = (stored - values[callee]) & ((1 << bits) - 1)
            return [0, 1, keep, bonus]
    except A.ColdGuard:
        return [1]
    raise ValueError(kind)


# ------------------------------------------------------------------ the C side
DRIVER = r'''
/* Generated by src/readable/battle/tests/triangle_diff.py: runs readable weapon triangle
   functions on memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "triangle.h"

static uint8_t **pages, **nopages;
static uint32_t used[4096]; static int nused;
static uint8_t *at(uint32_t a, int make) {
    uint8_t *p = pages[a >> 12];
    if (!p && make && nused < 4096) { p = pages[a >> 12] = calloc(4096, 1); used[nused++] = a >> 12; }
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

#define MAXO 64
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

void override_0x0019B97C(Context *); void override_0x001A8090(Context *); void override_0x001A80D4(Context *);
void override_0x001D77B8(Context *); void override_0x005090A4(Context *); void override_0x0052F824(Context *);
void override_0x0052DC54(Context *);
static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {
    {0x0019B97Cu, override_0x0019B97C}, {0x001A8090u, override_0x001A8090}, {0x001A80D4u, override_0x001A80D4},
    {0x001D77B8u, override_0x001D77B8}, {0x005090A4u, override_0x005090A4}, {0x0052F824u, override_0x0052F824},
    {0x0052DC54u, override_0x0052DC54},
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
            if (noracle < MAXO - 1) noracle++;
        } else if (!strncmp(line, "run", 3)) {
            Context c = fresh();
            c.r[13] = a[4];
            if (!strncmp(kind, "ov:", 3)) {
                uint32_t addr = (uint32_t)strtoul(kind + 3, NULL, 16);
                for (int i = 0; i < 4; i++) c.r[i] = a[i];
                for (unsigned i = 0; i < sizeof ovs / sizeof ovs[0]; i++) if (ovs[i].a == addr) ovs[i].f(&c);
                if (originals) printf("%u 1\n", id); else printf("%u 0 %u\n", id, c.r[0]);
            } else if (!strcmp(kind, "rank_attack") || !strcmp(kind, "rank_hit")) {
                int32_t r = kind[5] == 'a' ? unit_weapon_rank_attack(&c, a[0], a[1]) : unit_weapon_rank_hit(&c, a[0], a[1]);
                if (fe_gave_up(&c)) printf("%u 1\n", id); else printf("%u 0 %u\n", id, (uint32_t)r);
            } else if (!strcmp(kind, "lookup")) {
                TriangleLookup t; memset(&t, 0, sizeof t);
                triangle_side_lookup(&c, a[0], a[1], &t);
                if (fe_gave_up(&c)) printf("%u 1\n", id);
                else printf("%u 0 %d %u %u\n", id, t.looked_up, (uint32_t)t.triangle, t.flags);
            } else if (!strcmp(kind, "reverse")) {
                int32_t r = triangle_after_reverse(&c, a[0], a[1]);
                if (fe_gave_up(&c)) printf("%u 1\n", id); else printf("%u 0 %u\n", id, (uint32_t)r);
            } else if (!strcmp(kind, "hit_bonus") || !strcmp(kind, "attack_bonus")) {
                TriangleRankBonus b; memset(&b, 0, sizeof b);
                int hit = kind[0] == 'h';
                if (hit) triangle_hit_bonus(&c, a[0], a[1], &b); else triangle_attack_bonus(&c, a[0], a[1], &b);
                uint32_t mask = hit ? 0xFFFFu : 0xFFFFFFFFu;
                if (fe_gave_up(&c)) printf("%u 1\n", id);
                else if (!b.applies) printf("%u 0 0 0 0\n", id);
                else printf("%u 0 1 %d %u\n", id, b.keep_rank_bonus, (uint32_t)b.bonus & mask);
            }
            if (writes) printf("%u WROTE-GUEST %d\n", id, writes);
        }
    }
    return 0;
}
'''


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


def build_driver(cc: str, out: str, battle_dir: str) -> str:
    """Builds the driver with every source of src/readable/, the battle folder's taken from battle_dir."""
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "triangle_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(DRIVER)
    sources = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)) == os.path.normcase(SRC_BATTLE):
            continue
        sources += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    sources += [os.path.join(battle_dir, f) for f in os.listdir(battle_dir) if f.endswith(".c")]
    exe = os.path.join(out, "triangle_driver.exe" if os.name == "nt" else "triangle_driver")
    inc = ["-I", battle_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-fwrapv"] + inc + [src] + sorted(sources) + ["-o", exe]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"triangle_diff: building the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines = [f"stub {f:x} {k}" for f, k in STUBS.items()]
    expected: dict[int, tuple[str, list[int], tuple]] = {}
    cid = 0
    for name, gen in FUNCS.items():
        if only and name != only:
            continue
        for _ in range(n):
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
    return lines, expected


def compare(exe: str, cc: str, lines: list[str], expected: dict, show: int, quiet: bool = False):
    log = os.path.join(os.path.dirname(exe), "fe_readable.log")
    env = dict(os.environ, FE_READABLE_LOG=log, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"triangle_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
            if res[1] <= show and not quiet:
                why = " (wrote guest memory)" if c in wrote else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
PLANTS = [
    ("triangle_tables.c", "if (threshold <= exp)", "if (threshold < exp)"),
    ("triangle_tables.c", "    return WEAPON_RANK_NONE;\n}", "    return WEAPON_RANK_NONE - 1;\n}"),
    ("triangle_tables.c", "return limit < exp ? limit : exp;", "return limit < exp ? exp : limit;"),
    ("triangle_tables.c", "if (limit < floor)", "if (limit > floor)"),
    ("triangle_tables.c", "if (kind == TRIANGLE_KIND_STONE &&", "if (kind == TRIANGLE_KIND_STAFF &&"),
    ("triangle_tables.c", "if (kind >= TRIANGLE_KINDS)", "if (kind >= TRIANGLE_KINDS - 1)"),
    ("triangle_tables.c", "(gaddr)index * (gaddr)sizeof(ItemSubKindData)", "(gaddr)index * 8u"),
    ("triangle_tables.c", "kind * (gaddr)sizeof(WeaponBonusData)", "kind * 10u"),
    ("triangle_tables.c", "!fe_static_ready(ctx, S_ExpLimitGuardC)", "0"),
    ("triangle_battle.c", "        factor *= 2;", "        factor *= 1;"),
    ("triangle_battle.c", "gaddr o = battle_side(info, opposing_lead(side));\n    int32_t factor",
     "gaddr o = battle_side(info, side ^ 2u);\n    int32_t factor"),
    ("triangle_battle.c", "(gaddr)own_kind * 8u + (gaddr)other_kind", "(gaddr)other_kind * 8u + (gaddr)own_kind"),
    ("triangle_battle.c", "triangle > 0 ? side : opposing", "side"),
    ("triangle_battle.c", "out->keep_rank_bonus = triangle >= 0;", "out->keep_rank_bonus = triangle > 0;"),
    ("triangle_battle.c", "& 0x40u))", "& 0x80u))"),
    ("triangle_battle.c", "type == 2 || type == 3", "type == 2"),
    ("triangle_battle.c", "(gaddr)rank * 2u + (gaddr)column);", "(gaddr)rank * 2u + 1u);"),
    ("triangle_battle.c", "& guest_u64(ctx, S_ReverseMask)) != 0", "& guest_u64(ctx, S_ReverseMask)) == 0"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected = make_cases(text, n, seed, None)
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
        print("triangle_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("triangle_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_BATTLE)
    lines, expected = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = 0
    print(f"triangle_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold) in per.items():
        total_bad += bad
        print(f"  {name:28s} {n:5d} cases  {bad:3d} mismatches  ({cold} with a cold cache: original reached "
              f"the guard, readable gave up)" if cold else f"  {name:28s} {n:5d} cases  {bad:3d} mismatches")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n, a.seed + 1)
        print(f"triangle_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"triangle_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
