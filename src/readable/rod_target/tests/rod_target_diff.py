#!/usr/bin/env python3
"""Host differential test of the rod_target batch against the game's own ARM code.

    python src/readable/rod_target/tests/rod_target_diff.py            300 cases
    python src/readable/rod_target/tests/rod_target_diff.py -n 1500 --seed 7   the long run
    python src/readable/rod_target/tests/rod_target_diff.py --plant    also plant bugs: each must be caught

The method of src/readable/who_holds/tests/who_holds_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): the
test makes up guest states (the function's thirteen one-time caches and their guard words, the map's
Situation record, a user and a target unit with their person and class flag words, the item records
unit::Item::ToData answers, and the answers of the six other callees; all random test values, never game
data, and on purpose often outside the ranges the game uses: staff numbers that repeat or do not fit in
a byte, skill numbers with bit 15 set, flag bits above 31, HP and debuff bytes above 0x7F, negative
weapon experience, item slots past 4 and negative, unmapped records, persons, classes and Situation),
runs the ORIGINAL ARM code of map::ItemHelper::Rod::(anonymous)::CanUseTarget from the owner's
extracted/text.bin in arm_mini.py and the readable C function (built with the host gcc against
tools/readable/stub/) on the same memory, and compares r0, the number of bytes read from unmapped memory
AND the list of guest calls, in order, with their argument registers (docs/DECISIONS.md F-018).

Every callee is answered by one table on both sides and listed. While one of the thirteen guards is
cold the original reaches the guard routine (arm_mini raises "cold guard") before any other read or
call, and the readable code must give up at entry: no early give-up is allowed.

--plant copies src/readable/rod_target/ to build/readable/rod_target/plant/, makes one small wrong
change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one
mismatch. Changes that cannot change any answer are listed in docs/ROD_TARGET.md and not planted.

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
OUT = os.path.join(ROOT, "build", "readable", "rod_target")
SRC_DIR = os.path.join(ROOT, "src", "readable", "rod_target")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
TO_DATA, IS_ALLIED, MAX_HP, HAS_SKILL = 0x003D0EA4, 0x0053C3E0, 0x0052A364, 0x0052DD04
WEAPON_EXP, IS_MAGIC, CAN_EQUIP = 0x0052DC54, 0x005290B8, 0x0052C634
CAN_USE = 0x0034AC30
LEAF_STUBS = {TO_DATA: 1, IS_ALLIED: 2, MAX_HP: 4, HAS_SKILL: 2, WEAPON_EXP: 2, IS_MAGIC: 1, CAN_EQUIP: 4}
ARITY = dict(LEAF_STUBS)

OVERRIDES = {"rod_can_use_target": CAN_USE}
ADDR = dict(OVERRIDES)

# src/readable/rod_target/rod_target.h: guards in the game's order
GUARDS = (0x006D74C0, 0x006D74BC, 0x006D74B8, 0x006D74B4, 0x006D74B0, 0x006D74AC, 0x006D74A8,
          0x006D74A4, 0x006D74A0, 0x006D749C, 0x006D7498, 0x006D7494, 0x006D7490)
MASK_NOMOVE, MASK_NOWARP = 0x006D7550, 0x006D7558
USE_NAMES = ("heal", "heal all", "rescue", "draw", "weakness", "freeze", "silence", "curse")
USES = {n: 0x006D7450 + 2 * i for i, n in enumerate(USE_NAMES)}
SK_RESIST, SK_IMMUNE, SK_CHAIN = 0x006D7460, 0x006D7462, 0x006D7464
G_SITUATION = 0x006D7ED0
ALLIED_STAFFS = ("heal", "heal all", "rescue")

# guest layout of the made-up state
USER, TARGET = 0x08010000, 0x08012000
SIT = 0x08060000
PERSON, JOB = 0x08030000, 0x08031000
REC = lambda k: 0x08040000 + k * 0x80  # noqa: E731
NREC = 10
UNMAPPED = [0, 2, 0x40, 0x7FF0, 0x0FFF0000]


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sx(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def ostub(st, func: int, *args: int, value: int) -> None:
    st.oracle[(func,) + tuple(s32(a) for a in args[:LEAF_STUBS[func]])] = s32(value)


# ------------------------------------------------------------------ the made-up state
_CASE = [0]  # every sixth case has exactly one cold guard, the guards taken in turn


def gen_rod(rng):
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    st.zero(0x006D7440, 0x130)
    for g in GUARDS:
        st.put(g, 4, rng.choice([1, 0x101, 0xFFFFFFFF]))
    _CASE[0] += 1
    if _CASE[0] % 6 == 0:  # exactly one cold: each guard must be asked
        st.put(GUARDS[(_CASE[0] // 6) % len(GUARDS)], 4, rng.choice([0, 0x100, 0xFFFFFFFE]))
    elif rng.random() < 0.03:  # several cold
        for g in GUARDS:
            if rng.random() < 0.3:
                st.put(g, 4, rng.choice([0, 0x100, 0xFFFFFFFE]))
    # the eight staff numbers: mostly different, sometimes a repeat, above 0x7F or above 0xFF
    nums = rng.sample(range(1, 60), 8)
    for i in range(8):
        r = rng.random()
        if r < 0.08:
            nums[i] = nums[rng.randrange(8)]
        elif r < 0.14:
            nums[i] = rng.choice([0x80, 0x9C, 0xFF])
        elif r < 0.20:
            nums[i] = rng.choice([0x105, 0x1FF, 0x8003, 0xFFFF])
    for n, v in zip(USE_NAMES, nums):
        st.put(USES[n], 2, v)
    skills = [pick(rng, list(range(1, 200)), [0x8001, 0xFFFF, 0x80FF], 0.15) for _ in range(3)]
    for a, v in zip((SK_RESIST, SK_IMMUNE, SK_CHAIN), skills):
        st.put(a, 2, v)
    masks = []
    for a in (MASK_NOMOVE, MASK_NOWARP):
        v = pick(rng, [1 << rng.randrange(64), 1 << rng.randrange(32, 64)], [0, (1 << rng.randrange(64)) | (1 << rng.randrange(64))], 0.1)
        st.put(a, 8, v)
        masks.append(v)
    # the Situation record (Situation.flags bit 27: no rescue or draw)
    st.fill(SIT, 0x20)
    flags = rng.getrandbits(32) & ~0x08000000
    if rng.random() < 0.15:
        flags |= 0x08000000
    st.put(SIT + 4, 4, flags)
    st.put(G_SITUATION, 4, SIT if rng.random() > 0.04 else rng.choice(UNMAPPED))
    # which staff the case aims at, and whether the target is allied
    aim = rng.choice(USE_NAMES + ("heal", "heal all", "rescue", "draw", "draw", "weakness", "weakness", "weakness",
                                  "weakness", "weakness", "silence", "silence", "curse", "freeze", "other"))
    allied = (aim in ALLIED_STAFFS) != (rng.random() < 0.15)
    # the units, person and class
    st.fill(USER, 0x140)
    st.fill(TARGET, 0x140)
    st.fill(PERSON, 0x10)
    st.fill(JOB, 0x10)
    target = pick(rng, [TARGET], [0, USER], 0.12)
    if target:
        both = masks[0] | masks[1]
        words = [rng.getrandbits(64) & ~both for _ in range(3)]
        for w in range(3):
            if rng.random() < 0.2:
                words[w] |= masks[rng.randrange(2)]
        if aim in ("rescue", "draw") and rng.random() < 0.5:  # the "no move" or "no warp" bit alone, in one word
            words[rng.randrange(3)] |= masks[rng.randrange(2)]
        st.put(target + 0x0, 8, words[0])
        st.put(PERSON, 8, words[1])
        st.put(JOB, 8, words[2])
        st.put(target + 0x9C, 4, PERSON if rng.random() > 0.05 else rng.choice(UNMAPPED))
        st.put(target + 0xA0, 4, JOB if rng.random() > 0.05 else rng.choice(UNMAPPED))
        st.put(target + 0xF3, 1, pick(rng, list(range(1, 60)), [0x80, 0xFF, 0x9C, 0], 0.3))
        for k in range(8):
            st.put(target + 0x37 + k, 1, pick(rng, [0, 0, 0, 0, 1, 1, 2, 3], [0x80, 0xFF, 0xFE, 0x7F], 0.1))
    # the item slot and the record ToData answers for it
    slot = pick(rng, [0, 1, 2, 3, 4], [5, -1, 0x40000000, -0x3FFFFFC2], 0.08)
    item = s32(USER + 0x108 + slot * 4)
    for j in range(NREC):
        st.fill(REC(j), 0x68)
    k = rng.randrange(NREC)
    rec = REC(k) if rng.random() > 0.04 else rng.choice(UNMAPPED)
    ostub(st, TO_DATA, item, value=rec)
    st.put(REC(k) + 0x1B, 1, nums[USE_NAMES.index(aim)] & 0xFF if aim != "other" else rng.randrange(256))
    # the staff's eight amounts (extra_data): mostly 0, one to three stats set, so the answer turns on them
    for s in range(8):
        st.put(REC(k) + 0x40 + s, 1, 0)
    for s in ([0] if rng.random() < 0.3 else rng.sample(range(8), rng.choice([1, 1, 2, 3]))):
        st.put(REC(k) + 0x40 + s, 1, pick(rng, [1, 2, 3, 4, 5, 0xFF, 0xFE], [0x80, 0x7F, 0x81], 0.1))
    # the callees' answers
    if target:
        sit = word(st, G_SITUATION)
        ostub(st, IS_ALLIED, word(st, target + 0xA4), st.mem.get(sit + 8, 0),
              value=pick(rng, [1], [0x100, 0xFFFFFFFF], 0.2) if allied else 0)
        if aim in ("heal", "heal all") and rng.random() < 0.4:
            st.put(target + 0xF3, 1, rng.choice([0x80, 0x9C, 0xFF]))
        hp = sx(st.mem[target + 0xF3], 8)
        ostub(st, MAX_HP, target, 1, 0, 0, value=pick(rng, [hp + 1, hp, hp + 5, hp - 1, hp + 20],
                                                     [-5, 0x7FFFFFFF, -0x80000000, 0x100], 0.1))
        # the three skills (immunity and resistance on the target, the chain on the user). For a weakness
        # case one of seven set-ups is taken (chain twice); each then often builds the case its rule turns on
        mode = rng.choice(("none", "immune", "immune", "resist", "chain", "chain", "resist")) if aim == "weakness" else None
        hp_only = mode == "chain" and rng.random() < 0.75  # see below: no immunity then, it would clear the hp amount too
        for skn, unit, p, m in ((1, target, 0.25, "immune"), (0, target, 0.4, "resist"), (2, USER, 0.35, "chain")):
            if hp_only and m == "immune":
                continue
            if (rng.random() < p) if mode is None else (mode == m or (mode == "chain" and rng.random() < 0.4)):
                ostub(st, HAS_SKILL, unit, sx(skills[skn], 16), value=pick(rng, [1], [0x100, 0xFFFFFFFF], 0.1))
        none_case = rng.random() if mode == "none" else 1.0
        if none_case < 0.6:  # only the hp amount, above the hp debuff (never compared)
            for j in range(8):
                st.put(REC(k) + 0x40 + j, 1, 0)
            st.put(REC(k) + 0x40, 1, rng.choice([1, 3, 5]))
            st.put(target + 0x37, 1, 0)
        elif none_case < 0.85:  # one amount 1..3 against a debuff byte above 0x7F (signed: below 0, so it counts)
            stat = rng.randrange(1, 8)
            for j in range(8):
                st.put(REC(k) + 0x40 + j, 1, 0)
            st.put(REC(k) + 0x40 + stat, 1, rng.randrange(1, 4))
            st.put(target + 0x37 + stat, 1, rng.choice([0x80, 0xFE, 0xFF]))
        if hp_only:  # only the hp amount above 0: never counts under the chain
            for j in range(1, 8):                    # (ARM 0x34B288 starts at [sp,#1]); the others 0 or below
                st.put(REC(k) + 0x40 + j, 1, rng.choice([0, 0, 0, 0xFF, 0x80, 0xFE]))
            st.put(REC(k) + 0x40, 1, rng.randrange(1, 8))
        if mode == "immune" and rng.random() < 0.6:  # an amount that would count without the immunity
            st.put(REC(k) + 0x40 + rng.randrange(1, 8), 1, 3)
            for j in range(1, 8):
                st.put(target + 0x37 + j, 1, 0)
        if mode == "resist" and rng.random() < 0.6:  # one amount 2 or 3 against a debuff 0 or 1
            stat = rng.randrange(1, 8)
            for j in range(8):
                st.put(REC(k) + 0x40 + j, 1, 0)
            st.put(REC(k) + 0x40 + stat, 1, rng.choice([2, 3]))
            st.put(target + 0x37 + stat, 1, 0)
        elif mode == "resist" and rng.random() < 0.5:  # one amount 0x80..0xFF (below 0) against a debuff 0: halved
            stat = rng.randrange(1, 8)                 # with the sign kept it stays below 0 and never counts;
            for j in range(8):                         # halved unsigned (0xFF -> 0x7F) it would
                st.put(REC(k) + 0x40 + j, 1, 0)
            st.put(REC(k) + 0x40 + stat, 1, rng.choice([0x80, 0xC1, 0xFE, 0xFF]))
            st.put(target + 0x37 + stat, 1, 0)
        quiet = rng.random() < 0.8  # silence: often no tome or staff experience, so the items are asked
        for kind in (5, 6):
            ostub(st, WEAPON_EXP, target, kind,
                  value=pick(rng, [0, 0, -1] if quiet else [0, 1, 30, -1], [-0x80000000, 0x7FFFFFFF, 0x100], 0.1))
        magic_slot = rng.choice([0, 1, 2, 3, 4, 4, 4, 5])  # 5: none; 4 (the last slot) often
        for s in range(5):
            titem = s32(target + 0x108 + 4 * s)
            r = REC(rng.randrange(NREC)) if titem != item else rec
            ostub(st, TO_DATA, titem, value=r)
            if s == magic_slot or rng.random() < 0.15:
                ostub(st, IS_MAGIC, r, value=pick(rng, [1], [0x100, 0xFFFFFFFF], 0.1))
            if s == magic_slot or rng.random() < 0.3:
                ostub(st, CAN_EQUIP, target, titem, 1, 1, value=pick(rng, [1], [0x100, 0x80000000], 0.1))
    return st, f"ov:0x{CAN_USE:08X}", [USER, slot, target, 0], ("call", CAN_USE, aim)


FUNCS = {"rod_can_use_target": gen_rod}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY with its argument registers."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.listed.append(call_text(target, self.r[:ARITY[target]]))
        return super().call(target, ret)


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
    stray = [w for w in mem.writes if not SP - 0x400 <= w[0] < SP]
    if stray:
        raise A.Unsupported(f"the original wrote guest memory outside its stack: {stray[:3]}")
    return [0, cpu.r[0], mem.faults, calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER_HEAD = r'''
/* Generated by src/readable/rod_target/tests/rod_target_diff.py: runs the
   rod_target batch on memory images read from stdin and prints its results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rod_target.h"
'''


def driver_text() -> str:
    import sheet_diff as S  # the same driver body: page memory, call list, oracle, nested give-ups
    body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in sorted(OVERRIDES.values()))
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in sorted(OVERRIDES.values())) + "};\n"
    return DRIVER_HEAD + body.replace("@OVERRIDE_DECLS@", decls + table)


def find_cc() -> str | None:
    import check  # tools/readable/check.py: the same compiler search
    return check.find_cc()


_SHARED_OBJS: dict[str, str] = {}  # the other areas' objects, compiled once per run (plants reuse them)


def _compile(cc: str, src: str, obj: str, flags: list[str], env: dict) -> str | None:
    r = subprocess.run([cc] + flags + ["-c", src, "-o", obj], capture_output=True, text=True, env=env)
    return f"{src}:\n{r.stdout}{r.stderr}" if r.returncode else None


def build_driver(cc: str, out: str, my_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, this folder's taken from my_dir (a planted
    bug may leave a variable unused: not strict then). Each source is compiled on its own, in
    parallel; the other areas' objects once per run, reused for every planted bug."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "rod_target_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_DIR)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(my_dir, f) for f in sorted(os.listdir(my_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "rod_target_driver.exe" if os.name == "nt" else "rod_target_driver")
    inc = ["-I", my_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
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
        raise SystemExit("rod_target_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"rod_target_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list, aim: str) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up (cold)"
    elif args[2] == 0:
        key = "no target"
    else:
        allied = "allied" if "53c3e0" in exp[3] and st.oracle.get(
            (IS_ALLIED, word(st, args[2] + 0xA4), st.mem.get(word(st, G_SITUATION) + 8, 0)), 0) else "enemy"
        key = f"{allied} {aim} -> {exp[1]}"
        if exp[2]:
            key += " (unmapped reads)"
    p[key] = p.get(key, 0) + 1


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    _CASE[0] = 0
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
            note_path(name, st, args, exp, how[2])
            expected[cid] = (name, exp, (kind, args), False)  # no early give-up is allowed
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
        raise SystemExit(f"rod_target_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file.
# Every one can change an answer (r0, unmapped reads or the call list) before capture (F-027).
F = "rod_target.c"
H = "rod_target.h"
PLANTS = [
    # the caches not asked first: the readable code would read a cold cache
    (F, "    if (!caches_ready(ctx))\n        return (int32_t)fe_use_original(ctx);\n", ""),
    # one guard not asked (the last; one in the middle)
    (F, "        S_RtGuardResist, S_RtGuardImmune, S_RtGuardChain,\n", "        S_RtGuardResist, S_RtGuardImmune,\n"),
    (F, "        S_RtGuardDraw,   S_RtGuardWeakness,", "        S_RtGuardWeakness,"),
    # no target: not answered 0 first
    (F, "    if (target == 0)\n        return 0;\n", ""),
    # the army asked from the wrong Situation byte
    (F, "READ_FIELD(ctx, Situation, situation, force_index);", "READ_FIELD(ctx, Situation, situation, view_force);"),
    # the item slot's address: 2 bytes a slot
    (F, "((gaddr)slot << 2);", "((gaddr)slot << 1);"),
    # heal: >= instead of >, the HP byte unsigned, the max-HP arguments
    (F, "    return max_hp > guest_s8(ctx, target + RT_UNIT_HP);", "    return max_hp >= guest_s8(ctx, target + RT_UNIT_HP);"),
    (F, "    return max_hp > guest_s8(ctx, target + RT_UNIT_HP);", "    return max_hp > guest_u8(ctx, target + RT_UNIT_HP);"),
    (F, "guest_call(ctx, RT_UnitMaxHp, target, 1u, 0u, 0u);", "guest_call(ctx, RT_UnitMaxHp, target, 0u, 0u, 0u);"),
    # heal all dropped (answers no)
    (F, "        if (staff_is(ctx, item, S_RtUseHealAll))\n            return is_hurt(ctx, target);\n", ""),
    # the staff tests in another order (rescue before heal)
    (F, "        if (staff_is(ctx, item, S_RtUseHeal))\n            return is_hurt(ctx, target);\n"
        "        if (staff_is(ctx, item, S_RtUseHealAll))\n            return is_hurt(ctx, target);\n"
        "        if (staff_is(ctx, item, S_RtUseRescue))\n            return may_be_moved(ctx, target);\n",
     "        if (staff_is(ctx, item, S_RtUseRescue))\n            return may_be_moved(ctx, target);\n"
     "        if (staff_is(ctx, item, S_RtUseHeal))\n            return is_hurt(ctx, target);\n"
     "        if (staff_is(ctx, item, S_RtUseHealAll))\n            return is_hurt(ctx, target);\n"),
    # the staff number: only its low byte compared, or the record's byte read signed
    (F, "== guest_u16(ctx, use);", "== guest_u8(ctx, use);"),
    (F, "    return READ_FIELD(ctx, ItemData, data, item_subkind) ==",
     "    return guest_s8(ctx, FIELD_ADDR(ItemData, data, item_subkind)) =="),
    # rescue and draw: the map bit wrong, a flag word left out, the 64-bit bits cut to 32, no-warp dropped
    (H, "#define RT_SITUATION_NO_WARP 0x08000000u", "#define RT_SITUATION_NO_WARP 0x00080000u"),
    (F, "    flags |= READ_FIELD(ctx, PersonData, person, flags);\n", "    (void)person;\n"),
    (F, "    flags |= READ_FIELD(ctx, JobData, job, flags);\n", "    (void)job;\n"),
    (F, "    if (flags & guest_u64(ctx, S_RtMaskNoMove))", "    if ((uint32_t)flags & guest_u64(ctx, S_RtMaskNoMove))"),
    (F, "    return (flags & guest_u64(ctx, S_RtMaskNoWarp)) == 0;", "    return 1;"),
    # weakness: immunity does not clear, resistance not halved or halved twice, the skills asked in the wrong order
    (F, "        for (int stat = 0; stat < 8; stat++)\n            amount[stat] = 0;\n", "        amount[0] = 0;\n"),
    (F, "            amount[stat] = (int8_t)fe_asr(amount[stat], 1);", "            amount[stat] = (int8_t)fe_asr(amount[stat], 2);"),
    # resistance halving without the sign (0xFF halves to 0x7F, not -1; review 2026-11-17, round 22 integrate)
    (F, "            amount[stat] = (int8_t)fe_asr(amount[stat], 1);",
     "            amount[stat] = (int8_t)((uint8_t)amount[stat] >> 1);"),
    (F, "    if (has_skill(ctx, target, S_RtSkillImmune)) {", "    if (has_skill(ctx, target, S_RtSkillResist)) {"),
    # the chain skill asked on the target, or > 0 as >= 0
    (F, "    if (has_skill(ctx, user, S_RtSkillChain)) {", "    if (has_skill(ctx, target, S_RtSkillChain)) {"),
    (F, "            if (amount[stat] > 0)", "            if (amount[stat] >= 0)"),
    # the chain loop from hp (the hp amount counted under the chain)
    (F, "        for (int stat = 1; stat < 8; stat++)\n            if (amount[stat] > 0)",
     "        for (int stat = 0; stat < 8; stat++)\n            if (amount[stat] > 0)"),
    # the compare loop: from hp, >=, debuff unsigned, from the item's stat_bonus
    (F, "    for (int stat = 1; stat < 8; stat++)\n        if (amount[stat] > READ_FIELD",
     "    for (int stat = 0; stat < 8; stat++)\n        if (amount[stat] > READ_FIELD"),
    (F, "        if (amount[stat] > READ_FIELD(ctx, Unit, target, debuff[stat]))",
     "        if (amount[stat] >= READ_FIELD(ctx, Unit, target, debuff[stat]))"),
    (F, "READ_FIELD(ctx, Unit, target, debuff[stat])", "guest_u8(ctx, FIELD_ADDR(Unit, target, debuff[stat]))"),
    (F, "READ_FIELD(ctx, ItemData, data, extra_data[stat]);", "READ_FIELD(ctx, ItemData, data, stat_bonus[stat]);"),
    # the skill number zero-extended
    (F, "(uint32_t)(int32_t)guest_s16(ctx, number)", "(uint32_t)guest_u16(ctx, number)"),
    # draw dropped (answers no); the non-allied order (draw before weakness)
    (F, "    if (staff_is(ctx, item, S_RtUseDraw))\n        return may_be_moved(ctx, target);\n", ""),
    # freeze, silence, curse bits
    (H, "#define RT_COND_FROZEN 0x02u", "#define RT_COND_FROZEN 0x01u"),
    (H, "#define RT_COND_SILENCED 0x08u", "#define RT_COND_SILENCED 0x10u"),
    (H, "#define RT_COND_CURSED 0x20u", "#define RT_COND_CURSED 0x40u"),
    # silence: the tome kind, the experience test unsigned, four slots, IsMagic not asked, CanItemEquip's bools
    (H, "#define RT_KIND_TOME 5", "#define RT_KIND_TOME 4"),
    (F, "    if ((int32_t)guest_call2(ctx, RT_UnitWeaponExp, target, RT_KIND_STAFF) > 0)",
     "    if (guest_call2(ctx, RT_UnitWeaponExp, target, RT_KIND_STAFF) > 0)"),
    (H, "#define RT_ITEM_SLOTS 5", "#define RT_ITEM_SLOTS 4"),
    (F, "guest_call1(ctx, RT_ItemIsMagic, data) != 0 &&", "data != 0xFFFFFFFFu &&"),
    (F, "guest_call(ctx, RT_UnitCanEquipItem, target, item, 1u, 1u)", "guest_call(ctx, RT_UnitCanEquipItem, target, item, 1u, 0u)"),
    # silence without the magic test
    (F, "        return casts_magic(ctx, target) && (READ_FIELD", "        return (READ_FIELD"),
    # any other staff answers yes (enemy side)
    (F, "        return (READ_FIELD(ctx, Unit, target, conditions[0]) & RT_COND_CURSED) == 0;\n    return 0;",
     "        return (READ_FIELD(ctx, Unit, target, conditions[0]) & RT_COND_CURSED) == 0;\n    return 1;"),
    # a callee's answer read as a byte (Force::IsAllied)
    (F, "READ_FIELD(ctx, Unit, target, force), army) != 0)", "READ_FIELD(ctx, Unit, target, force), army) & 0xFFu)"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_DIR, d, ignore=shutil.ignore_patterns("tests"))
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
        print(f"  planted bug {i:2d} ({fname}: {old.strip()[:56]!r}): "
              + (f"caught, {bad} mismatches" if bad else "NOT CAUGHT"))
        missed += 0 if bad else 1
    return missed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=300, help="cases (default 300)")
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, help="cases for each planted bug (default: -n)")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("rod_target_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("rod_target_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_DIR)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"rod_target_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, _early) in per.items():
        total_bad += bad
        note = f"  ({cold_n} cold: both gave up at entry)" if cold_n else ""
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches{note}")
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("rod_target_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("rod_target_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"rod_target_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"rod_target_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
