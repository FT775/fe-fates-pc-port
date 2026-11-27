#!/usr/bin/env python3
"""Host differential test of the weapon-rank batch against the game's own ARM code.

    python src/readable/weapon_rank/tests/weapon_rank_diff.py             all functions, 300 cases each
    python src/readable/weapon_rank/tests/weapon_rank_diff.py -n 1500 --seed 7    the long run
    python src/readable/weapon_rank/tests/weapon_rank_diff.py --only unit_first_weapon_exp
    python src/readable/weapon_rank/tests/weapon_rank_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/battle2/tests/battle2_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): for
every readable function of src/readable/weapon_rank/ the test makes up guest states (units with their
Person, class and force, the PersonFlag words, the weapon-rank thresholds, the save's difficulty, the
one-time caches; all random test values, never game data, and on purpose often outside the ranges
the game uses: unmapped units, Persons and records, pool numbers 0, 251 and negative, weapon kinds
past 7 and negative, bools that are not 0/1, limits that are 0, negative or huge), runs the ORIGINAL
ARM code from the owner's extracted/text.bin in arm_mini.py and the readable C function (built with
the host gcc against tools/readable/stub/) on the same memory, and compares r0, the number of bytes
read from unmapped memory AND the list of guest calls, in order, with their argument registers
(docs/DECISIONS.md F-018).

Every callee is answered by one table on both sides and listed: UnitPool::Get, GameUserData::Get,
WeaponLevel::Get, WeaponLevel::GetLevel, Unit::GetWeaponExp and Unit::GetWeaponExpLimit. The last
two are overrides of the triangle batch whose readable code gives up while GetWeaponExpLimit's three
caches are cold: on the ARM side their table answer raises "cold guard" then (the game's own code
would reach the guard routine inside the call), so the readable code must give up before reading
anything (it asks those guards first; otherwise the override would give up nested, which the
project counts as a mismatch). UnitGetWeaponLevel ends with a tail branch (B) into
WeaponLevel::GetLevel; the tier-1 library enters that override there (its generated code is
`CALL(override_0x005090A4)`, no copy of GetLevel inside the caller; docs/MOVE.md 9), so the tail
branch is listed as a call here and the readable code makes it as a guest call.

unit_first_weapon_exp is a helper (CaclulateFirstWeaponExp stores; docs/WEAPON_RANK.md): it runs
through a test-only entry of the generated driver (never a marker in src/readable/); the ARM function
runs whole and the eight bytes it STORES through its pointer are the expected result, folded into
one number (FNV-1a) on both sides.

An early give-up (the readable code gives up before reading anything while the original runs to the
end) is accepted only where it must happen: script_unit_weapon_rank with its bool set and a limit
cache cold (it asks before the pool-number and force tests that may end the original first). Any
other early give-up is a mismatch.

--plant copies src/readable/weapon_rank/ to build/readable/weapon_rank/plant/, makes one small wrong
change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one
mismatch.

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
from stance_diff import State, pick  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "weapon_rank")
SRC_WR = os.path.join(ROOT, "src", "readable", "weapon_rank")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
POOL_GET, USER_GET, LEVEL_GET, GET_LEVEL, GET_EXP, GET_LIMIT = (
    0x004F6174, 0x001B3AFC, 0x001A80D4, 0x005090A4, 0x0052DC54, 0x0052F824)
LEAF_STUBS = {POOL_GET: 1, USER_GET: 0, LEVEL_GET: 0, GET_LEVEL: 2, GET_EXP: 2, GET_LIMIT: 2}
ARITY = dict(LEAF_STUBS)

OVERRIDES = {"script_unit_weapon_rank": 0x003AC430, "unit_weapon_exp_for_job_intro": 0x00532060}
TEST_ENTRIES = {"unit_first_weapon_exp": 0x00531C5C}
ADDR = dict(OVERRIDES, **TEST_ENTRIES)

# caches (src/readable/weapon_rank/weapon_rank.h)
LIMIT_GUARDS = (0x006D97B4, 0x006D97B0, 0x006D97AC)
INTRO_GUARD, INTRO_MASK = 0x006D97BC, 0x006D9AA0

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x140  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
FORCE = lambda k: 0x08030000 + k * 12  # noqa: E731
LEVEL = 0x08040000      # WeaponLevel record (six u8 thresholds, then two pad bytes)
GUD = 0x08050000        # GameUserData
BUF = 0x08060000        # CaclulateFirstWeaponExp's output buffer (ARM side only)
SCRIPT = 0x08070000     # the cmvm context (never read)
TORN = 0x080F1000 - 0xE8 - 4  # a unit whose weapon_exp bytes 4..7 are on an unmapped page
NUNITS, NPERS, NJOBS, NFORCES = 5, 5, 4, 6
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sx(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def cold(st, guards) -> bool:
    return any(not st.mem.get(g, 0) & 1 for g in guards)


def fnv(data: bytes) -> int:
    h = 0x811C9DC5
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def ostub(st, func: int, *args: int, value: int) -> None:
    st.oracle[(func,) + tuple(s32(a) for a in args[:LEAF_STUBS[func]])] = s32(value)


# ------------------------------------------------------------------ the made-up state
def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    st.zero(0x006D9600, 0x600)
    for g in LIMIT_GUARDS + (INTRO_GUARD,):
        st.put(g, 4, rng.choice([1, 0x101, 0xFFFFFFFF]))
    st.put(INTRO_MASK, 8, 1 << rng.randrange(64) if rng.random() > 0.05 else rng.randrange(1 << 64))
    mask = word(st, INTRO_MASK, 8)
    for k in range(NPERS):
        p = PERSON(k)
        st.fill(p, 0x100)
        st.put(p, 8, flags_word(rng, mask))
        st.put(p + 0x34, 1, pick(rng, [0, 1, 2, 3, 0, 2], [4, 0x81, 0xFF], 0.1))
        for j in range(8):
            st.put(p + 0x60 + j, 1, pick(rng, [0, 0, 1, 5, 21, 51, 96, 161, 251], [0x7F, 0x80, 0xFF, 2], 0.2))
    for k in range(NJOBS):
        st.fill(JOB(k), 0x100)
        st.put(JOB(k), 8, flags_word(rng, mask))
    for k in range(NFORCES):
        st.fill(FORCE(k), 12)
        st.put(FORCE(k) + 8, 1, pick(rng, [0, 1, 2, 3, 9, 9], [4, 8, 10, 0x89], 0.15))
    for k in range(NUNITS):
        make_unit(st, UNIT(k), mask)
    st.fill(LEVEL, 8)
    th = sorted(rng.sample(range(1, 256), 6), reverse=True)
    if rng.random() < 0.2:  # thresholds out of order or 0 / 255
        th = [rng.choice([0, 1, 0x7F, 0x80, 0xFF, rng.randrange(256)]) for _ in range(6)]
    for i, t in enumerate(th):
        st.put(LEVEL + i, 1, t)
    st.fill(GUD, 0x40)
    st.put(GUD + 0x2D, 1, pick(rng, [0, 1, 2, 1, 2], [3, 0xFF, 0x81], 0.1))
    ostub(st, USER_GET, value=GUD if rng.random() > 0.03 else rng.choice(UNMAPPED))
    ostub(st, LEVEL_GET, value=LEVEL if rng.random() > 0.03 else rng.choice(UNMAPPED))
    return st


def flags_word(rng, mask: int) -> int:
    v = rng.randrange(1 << 64)
    return v | mask if rng.random() < 0.15 else v & ~mask & ((1 << 64) - 1)


def make_unit(st, u: int, mask: int) -> None:
    rng = st.rng
    st.fill(u, 0x140)
    st.put(u, 8, flags_word(rng, mask))
    st.put(u + 0x9C, 4, PERSON(rng.randrange(NPERS)) if rng.random() > 0.05 else rng.choice(UNMAPPED + [0]))
    st.put(u + 0xA0, 4, JOB(rng.randrange(NJOBS)) if rng.random() > 0.05 else rng.choice(UNMAPPED + [0]))
    st.put(u + 0xA4, 4, FORCE(rng.randrange(NFORCES)) if rng.random() > 0.05 else rng.choice(UNMAPPED + [0]))
    for j in range(8):
        st.put(u + 0xE8 + j, 1, pick(rng, [0, 1, 5, 21, 51, 96, 161, 251, rng.randrange(256)], [0x80, 0xFF], 0.2))


def torn_unit(st) -> int:
    """A unit that ends right inside its weapon_exp bytes (the rest is on an unmapped page)."""
    src = UNIT(st.rng.randrange(NUNITS))
    for i in range(0xE8 + 4):
        st.mem[TORN + i] = st.mem[src + i]
    return TORN


def unit_arg(st) -> int:
    r = st.rng.random()
    if r < 0.82:
        return UNIT(st.rng.randrange(NUNITS))
    if r < 0.9:
        return torn_unit(st)
    return st.rng.choice(UNMAPPED + [0])


def answer_limits(st, u: int) -> None:
    for k in range(8):
        ostub(st, GET_LIMIT, u, k, value=pick(st.rng, [0, 1, 5, 21, 51, 96, 161, 251, 251, 251],
                                               [-1, -0x80000000, 0x7FFFFFFF, 300, 0x100], 0.12))


def answer_levels(st) -> None:
    """WeaponLevel::GetLevel answered by its rule (the first threshold the exp reaches, signed) for the
    record and every exp a case can pass; other records get a random rank."""
    rng = st.rng
    th = [st.mem.get(LEVEL + i, 0) for i in range(6)]
    exps = set(range(256)) | {s32(v) for (f, *_), v in st.oracle.items() if f == GET_EXP}
    for e in exps:
        se = sx(e, 32)
        rank = next((i for i, t in enumerate(th) if t <= se), 6)
        ostub(st, GET_LEVEL, LEVEL, e, value=rank)
    for e in list(exps)[:16]:
        for bad in UNMAPPED:
            ostub(st, GET_LEVEL, bad, e, value=rng.randrange(7))


def cool(st, guards, p: float) -> None:
    for g in guards:
        if st.rng.random() < p:
            st.put(g, 4, st.rng.choice([0, 0x100]))


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def entry(name, args, store=None):
    a = ADDR[name]
    return f"ov:0x{a:08X}", args + [0] * (4 - len(args)), ("call", a, store)


def gen_script(rng):
    st = base_state(rng)
    cool(st, LIMIT_GUARDS, 0.06)
    index = pick(rng, list(range(1, NUNITS + 1)) + [250], [0, -1, 251, 0x80000000, 0xFFFF, 1000], 0.15)
    u = unit_arg(st)
    pool = u if rng.random() > 0.05 else rng.choice(UNMAPPED + [0])
    ostub(st, POOL_GET, index, value=pool)
    if rng.random() < 0.4 and UNIT(0) <= pool < UNIT(NUNITS):  # mostly a force the script accepts
        st.put(pool + 0xA4, 4, FORCE(0))
        st.put(FORCE(0) + 8, 1, rng.choice([0, 1, 2]))
    kind = pick(rng, list(range(8)), [8, 0x7F, 0x80, 0xFF, 0x105, 0xFFFFFFFF, 0x80000003, 0x2000], 0.2)
    capped = pick(rng, [0, 1, 0, 1], [2, 0x100, 0xFFFFFFFF], 0.1)
    for v in {pool, u}:
        ostub(st, GET_EXP, v, sx(kind & 0xFF, 8),
              value=pick(rng, [0, 1, 5, 21, 51, 96, 161, 251, rng.randrange(256)], [-1, 0x7FFFFFFF, 300], 0.1))
    answer_levels(st)
    return (st,) + entry("script_unit_weapon_rank", [SCRIPT, index, kind, capped])


def gen_intro(rng):
    st = base_state(rng)
    cool(st, (INTRO_GUARD,), 0.05)
    u = unit_arg(st)
    kind = pick(rng, [7, 7, 7, 0, 1, 2, 3, 4, 5, 6], [8, 0x107, 0xFFFFFFFF, 0x80000007, 0x7F, 0x80], 0.12)
    if rng.random() < 0.3 and UNIT(0) <= u < UNIT(NUNITS):  # the stone flag on exactly one of the three
        mask = word(st, INTRO_MASK, 8)
        for a in (u, word(st, u + 0x9C), word(st, u + 0xA0)):
            if a in UNMAPPED or a == 0:
                continue
            st.put(a, 8, word(st, a, 8) & ~mask & ((1 << 64) - 1))
        target = rng.choice([u, word(st, u + 0x9C), word(st, u + 0xA0)])
        if target not in UNMAPPED and target != 0:
            st.put(target, 8, word(st, target, 8) | mask)
    return (st,) + entry("unit_weapon_exp_for_job_intro", [u, kind])


def gen_first(rng):
    st = base_state(rng)
    cool(st, LIMIT_GUARDS, 0.05)
    u = unit_arg(st)
    st.zero(BUF, 8)
    st.fill(BUF, 8)
    answer_limits(st, u)
    return (st,) + entry("unit_first_weapon_exp", [u, BUF],
                         store=lambda mem: fnv(bytes(mem.read8(BUF + i) for i in range(8))))


def early_ok(name: str, st, args: list[int]) -> bool:
    """Whether the readable code may give up before reading anything while the original runs to the
    end: script_unit_weapon_rank with its bool set and a GetWeaponExpLimit cache cold."""
    if name == "script_unit_weapon_rank":
        return s32(args[3]) != 0 and cold(st, LIMIT_GUARDS)
    return False


FUNCS = {
    "script_unit_weapon_rank": gen_script,
    "unit_weapon_exp_for_job_intro": gen_intro,
    "unit_first_weapon_exp": gen_first,
}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX and every tail branch (B) to a callee of ARITY with its
    argument registers. Every callee here is answered by the table (the tail branch into GetLevel is
    entered as a call by the library, docs/MOVE.md 9)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.listed.append(call_text(target, self.r[:ARITY[target]]))
        return super().call(target, ret)

    def step(self, ins: int, pc: int) -> None:
        c = ins >> 28
        if c != 0xF and self.cond(c) and (ins >> 24) & 0xF == 0xA:  # B (no link)
            target = (pc + 8 + (A.sx(ins & 0xFFFFFF, 24) << 2)) & A.MASK
            stub = self.stubs.get(target)
            if target in ARITY and stub is not None:  # a tail call: listed, returns to the caller's caller
                self.listed.append(call_text(target, self.r[:ARITY[target]]))
                self.r[0] = stub(self, tuple(self.r[:4])) & A.MASK
                self.r[15] = self.r[14]
                return
        super().step(ins, pc)


def call_text(target: int, regs) -> str:
    return f"{target:x}" + "".join(f":{r & 0xFFFFFFFF:x}" for r in regs)


def calls_field(listed: list[str]) -> str:
    return ",".join(listed) if listed else "-"


def arm_run(text: bytes, st, kind: str, args: list[int], how: tuple) -> list:
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]. For the
    helper, r0 is what the original stored (how[2] folds it from the memory afterwards)."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def answer(f, n):
        return lambda cpu, a: st.oracle.get((f,) + tuple(x & 0xFFFFFFFF for x in a[:n]), 0)
    stubs = {f: answer(f, n) for f, n in LEAF_STUBS.items()}

    def limited(f, n):  # GetWeaponExp / GetWeaponExpLimit: the game's code reaches the guard while cold
        inner = answer(f, n)

        def stub(cpu, a):
            if any(not cpu.mem.read(g, 4) & 1 for g in LIMIT_GUARDS):
                raise A.ColdGuard()
            return inner(cpu, a)
        return stub
    stubs[GET_EXP] = limited(GET_EXP, 2)
    stubs[GET_LIMIT] = limited(GET_LIMIT, 2)
    cpu = ListingCpu(mem, stubs, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    try:
        cpu.run(how[1])
    except A.ColdGuard:
        return [1]
    allowed = (lambda a: SP - 0x400 <= a < SP or BUF <= a < BUF + 8) if how[2] else (lambda a: SP - 0x400 <= a < SP)
    stray = [w for w in mem.writes if not allowed(w[0])]
    if stray:
        raise A.Unsupported(f"the original wrote guest memory outside its stack: {stray[:3]}")
    r0 = cpu.r[0] if how[2] is None else how[2](mem)
    return [0, r0, mem.faults, calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER_HEAD = r'''
/* Generated by src/readable/weapon_rank/tests/weapon_rank_diff.py: runs the weapon-rank batch on
   memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "weapon_rank.h"
'''

TEST_ENTRY_CODE = r'''
/* test-only entry (never in src/readable/: this address has a helper row, no override) */
static uint32_t t_first(Context *ctx, gaddr unit) {
    uint8_t out[WR_KINDS];
    memset(out, 0, sizeof out);
    unit_first_weapon_exp(ctx, unit, out);
    uint32_t h = 0x811C9DC5u;
    for (int i = 0; i < WR_KINDS; i++) h = (h ^ out[i]) * 0x01000193u;
    return h;
}
void test_0x00531C5C(Context *ctx) { FE_ENTRY(0x00531C5C, t_first, FE_ARG(0)); }
'''


def driver_text() -> str:
    import sheet_diff as S  # the same driver body: page memory, call list, oracle, nested give-ups
    body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in sorted(OVERRIDES.values()))
    entries = [(a, f"override_0x{a:08X}") for a in sorted(OVERRIDES.values())] + \
        [(a, f"test_0x{a:08X}") for a in sorted(TEST_ENTRIES.values())]
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, {f}}},\n" for a, f in entries) + "};\n"
    tdecls = "".join(f"void test_0x{a:08X}(Context *);\n" for a in sorted(TEST_ENTRIES.values()))
    return DRIVER_HEAD + body.replace("@OVERRIDE_DECLS@", decls + tdecls + table) + TEST_ENTRY_CODE


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


_SHARED_OBJS: dict[str, str] = {}  # the other areas' objects, compiled once per run (plants reuse them)


def _compile(cc: str, src: str, obj: str, flags: list[str], env: dict) -> str | None:
    r = subprocess.run([cc] + flags + ["-c", src, "-o", obj], capture_output=True, text=True, env=env)
    return f"{src}:\n{r.stdout}{r.stderr}" if r.returncode else None


def build_driver(cc: str, out: str, wr_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, this folder's taken from wr_dir (a planted
    bug may leave a parameter unused: not strict then). Each source is compiled on its own, in
    parallel; the other areas' objects once per run, reused for every planted bug."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "weapon_rank_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_WR)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(wr_dir, f) for f in sorted(os.listdir(wr_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "weapon_rank_driver.exe" if os.name == "nt" else "weapon_rank_driver")
    inc = ["-I", wr_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    strict_warn = ["-Wall", "-Wextra", "-Werror"]
    base = ["-std=c11", "-O1", "-fwrapv"]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    shared_dir = os.path.join(OUT, "obj_shared")
    own_dir = os.path.join(out, "obj")
    os.makedirs(shared_dir, exist_ok=True)
    os.makedirs(own_dir, exist_ok=True)
    jobs = []
    for s in sorted(others):
        if s not in _SHARED_OBJS:
            rel = os.path.relpath(s, os.path.join(ROOT, "src", "readable")).replace(os.sep, "_")
            jobs.append((s, os.path.join(shared_dir, rel[:-2] + ".o"), base + strict_warn + inc, True))
    for s in mine:
        jobs.append((s, os.path.join(own_dir, os.path.basename(s)[:-2] + ".o"),
                     base + (strict_warn if strict else ["-w"]) + inc, False))
    with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
        errs = list(pool.map(lambda j: _compile(cc, j[0], j[1], j[2], env), jobs))
    bad = [e for e in errs if e]
    if bad:
        raise SystemExit("weapon_rank_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"weapon_rank_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up (cold)"
    elif name == "script_unit_weapon_rank":
        idx = sx(args[1], 32)
        pool = st.oracle.get((POOL_GET, s32(args[1])), 0)
        if not 1 <= idx <= 250:
            key = "pool number refused"
        elif st.mem.get(word(st, pool + 0xA4) + 8) == 9:
            key = "force 9"
        else:
            key = "rank, capped" if s32(args[3]) else "rank, stored byte"
    elif name == "unit_weapon_exp_for_job_intro":
        key = "stone" if s32(args[1]) == 7 else "other kind"
        if s32(args[1]) == 7 and exp[1] == 0:
            key = "stone, 0"
    else:
        u = args[0]
        pers = word(st, u + 0x9C) if u not in UNMAPPED and u != 0 else 0
        diff = st.mem.get(GUD + 0x2D, 0) if st.oracle.get((USER_GET,), 0) == GUD else None
        kind = st.mem.get(pers + 0x34)
        key = f"difficulty {diff}, unit_kind {'1/3' if kind in (1, 3) else 'other'}"
    p[key] = p.get(key, 0) + 1


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines = [f"arity {f:x} {k}" for f, k in ARITY.items()]
    expected: dict[int, tuple[str, list, tuple, bool]] = {}
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
            note_path(name, st, args, exp)
            expected[cid] = (name, exp, (kind, args), early_ok(name, st, args))
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
        raise SystemExit(f"weapon_rank_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list] = {}
    flagged: dict[int, str] = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE", "NESTED-GIVEUP"):
            flagged[int(parts[0])] = parts[1]
        elif parts:
            got[int(parts[0])] = [parse(x) for x in parts[1:4]] + parts[4:]  # the call list stays text
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs, early) in expected.items():
        res = per.setdefault(name, [0, 0, 0, 0])  # cases, mismatches, gave-up cases, early give-ups
        res[0] += 1
        g = got.get(c)
        if exp[0] == 0:
            cov = COVERAGE.setdefault(name, {"values": set(), "nonzero": 0, "faulty": 0, "calls": 0})
            cov["values"].add(exp[1])
            cov["nonzero"] += int(exp[1] != 0)
            cov["faulty"] += int(exp[2] != 0)
            cov["calls"] += 0 if exp[3] == "-" else exp[3].count(",") + 1
        if exp[0] == 1:
            res[2] += 1
            exp = [1, 0]  # a give-up must come before any unmapped read
        elif g is not None and g[:1] == [1] and g[1:] == [0] and c not in flagged and early:
            res[3] += 1  # an early give-up early_ok allows (a cache asked first is cold): always safe
            continue
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
F = "weapon_rank.c"
PLANTS = [
    # script_unit_weapon_rank
    (F, "    if (unit_index <= 0 || unit_index > WR_SCRIPT_UNIT_MAX)\n",
     "    if (unit_index <= 0 || unit_index >= WR_SCRIPT_UNIT_MAX)\n"),
    (F, "    if (unit_index <= 0 || unit_index > WR_SCRIPT_UNIT_MAX)\n",
     "    if (unit_index < 0 || unit_index > WR_SCRIPT_UNIT_MAX)\n"),
    (F, "    if (READ_FIELD(ctx, Force, force, type) == WR_FORCE_TYPE_ABSENT)\n        return 0;\n", ""),
    # the pool asked once and kept: one call less
    (F, "    unit = guest_call1(ctx, WR_UnitPoolGet, (uint32_t)unit_index);\n", ""),
    # the kind passed whole instead of its low byte sign-extended
    (F, "(uint32_t)(int32_t)(int8_t)(uint8_t)kind", "kind"),
    (F, "    if (capped == 0)\n        exp = guest_u8", "    if (capped != 0)\n        exp = guest_u8"),
    # GetWeaponExp's caches not asked first: its override would give up nested
    (F, "    if (capped != 0 && !exp_limit_ready(ctx))\n        return (int32_t)fe_use_original(ctx);\n", ""),
    # asked whatever the bool: an early give-up early_ok does not allow
    (F, "    if (capped != 0 && !exp_limit_ready(ctx))\n", "    if (!exp_limit_ready(ctx))\n"),
    # WeaponLevel::Get read directly instead of called: one call less
    (F, "    gaddr level = guest_call(ctx, WR_WeaponLevelGet, 0u, 0u, 0u, 0u);\n",
     "    gaddr level = guest_u32(ctx, 0x006D3D20u);\n"),
    # unit_weapon_exp_for_job_intro
    (F, "    if (!fe_static_ready(ctx, S_JobIntroGuard))\n        return (int32_t)fe_use_original(ctx);\n", ""),
    (F, "    if (kind == WR_KIND_STONE && (guest_u64", "    if (kind == 6u && (guest_u64"),
    (F, "           READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), flags) |\n", ""),
    (F, "    return guest_u8(ctx, FIELD_ADDR(Unit, unit, weapon_exp) + kind);\n}",
     "    return guest_s8(ctx, FIELD_ADDR(Unit, unit, weapon_exp) + kind);\n}"),
    # unit_first_weapon_exp
    (F, "    if (!exp_limit_ready(ctx)) {\n        fe_use_original(ctx);\n        return;\n    }\n", ""),
    (F, "        if (limit < 1)\n            limit = 1;\n", ""),
    (F, " && unit_kind != WR_PERSON_KIND_NO_FLOOR_B &&", " &&"),
    # the limit not asked again: one call less (and a limit of 0 or below gets the floor)
    (F, "            (int32_t)guest_call2(ctx, WR_UnitGetWeaponExpLimit, unit, (uint32_t)kind) > 0) {",
     "            limit > 0) {"),
    (F, "threshold) + WR_FLOOR_RANK_HARD);", "threshold) + WR_FLOOR_RANK_LUNATIC);"),
    (F, "            else if (difficulty == WR_DIFFICULTY_LUNATIC)", "            else if (difficulty >= WR_DIFFICULTY_LUNATIC)"),
    (F, "            if (least > limit)\n                least = limit;\n", ""),
    (F, "(own > limit ? limit : own)", "own"),
    (F, "        int32_t start = least > own ?", "        int32_t start = least >= own + 1 && own != 0 ?"),
    (F, "    uint32_t difficulty = READ_FIELD(ctx, GameUserData, user, difficulty);",
     "    uint32_t difficulty = READ_FIELD(ctx, GameUserData, guest_u32(ctx, 0x006DA248u), difficulty);"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_WR, d, ignore=shutil.ignore_patterns("tests"))
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
              + (f"caught, {bad} mismatches in {', '.join(hit[:4])}" if bad else "NOT CAUGHT"))
        missed += 0 if bad else 1
    return missed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=300, help="cases per function (default 300)")
    ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, help="cases per function for each planted bug (default: -n)")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("weapon_rank_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("weapon_rank_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_WR)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"weapon_rank_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, early) in per.items():
        total_bad += bad
        notes = ([f"{cold_n} cold: both reached / gave up at the cache"] if cold_n else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("weapon_rank_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("weapon_rank_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"weapon_rank_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"weapon_rank_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
