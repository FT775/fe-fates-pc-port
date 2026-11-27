#!/usr/bin/env python3
"""Host differential test of the weapon_level_view batch against the game's own ARM code.

    python src/readable/weapon_level_view/tests/weapon_level_view_diff.py            300 cases
    python src/readable/weapon_level_view/tests/weapon_level_view_diff.py -n 1500 --seed 7   the long run
    python src/readable/weapon_level_view/tests/weapon_level_view_diff.py --plant    also plant bugs: each must be caught

The method of src/readable/weapon_rank/tests/weapon_rank_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): the
test makes up guest states (a unit and its class pointer, the weapon exp GetWeaponExp answers for each
kind, 21 ItemSubKind records, Job::CanEquipFromSubKind's answers, GetWeaponExpLimit's three one-time
caches; all random test values, never game data, and on purpose often outside the ranges the game
uses: unmapped units, records and class pointers, negative and huge exp, record kinds past 7 and
negative, duplicate and missing sub-kinds, line numbers negative, huge and past the last line), runs
the ORIGINAL ARM code of GameInfoViewer::GetWeaponLevelKind from the owner's extracted/text.bin in
arm_mini.py and the readable C function (built with the host gcc against tools/readable/stub/) on the
same memory, and compares r0, the number of bytes read from unmapped memory AND the list of guest
calls, in order, with their argument registers (docs/DECISIONS.md F-018).

Every callee is answered by one table on both sides and listed: Unit::GetWeaponExp, ItemSubKind::Get,
Job::CanEquipFromSubKind. GetWeaponExp is an override of the triangle batch whose readable code gives
up while GetWeaponExpLimit's three caches are cold: on the ARM side its table answer raises "cold
guard" then (the game's code would reach the guard routine inside the call). GetWeaponExp is the
game's first call, before any read, so the readable code asks those guards at entry and gives up
exactly where the original would: no early give-up is allowed.

--plant copies src/readable/weapon_level_view/ to build/readable/weapon_level_view/plant/, makes one
small wrong change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least
one mismatch. Changes that cannot change any answer (a sign extension of a number 0 .. 20, a signed
instead of unsigned read of a byte compared with 0 .. 7) are listed in docs/WEAPON_LEVEL_VIEW.md and
not planted.

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
OUT = os.path.join(ROOT, "build", "readable", "weapon_level_view")
SRC_DIR = os.path.join(ROOT, "src", "readable", "weapon_level_view")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
GET_EXP, SUBKIND_GET, CAN_EQUIP = 0x0052DC54, 0x0019B97C, 0x00524420
LEAF_STUBS = {GET_EXP: 2, SUBKIND_GET: 1, CAN_EQUIP: 2}
ARITY = dict(LEAF_STUBS)

OVERRIDES = {"weapon_level_view_kind": 0x001D13A4}
ADDR = dict(OVERRIDES)

LIMIT_GUARDS = (0x006D97B4, 0x006D97B0, 0x006D97AC)  # src/readable/weapon_level_view/weapon_level_view.h

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x140  # noqa: E731
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
SUBREC = lambda k: 0x08040000 + k * 0x10  # noqa: E731
NUNITS, NJOBS, NSUB = 4, 3, 24
# a unit whose class pointer (+0xA0) is on an unmapped page. The unit stays 4-aligned, as every Unit in
# the game: a word that straddles a page edge would be an unaligned load, which arm_mini.py models as the
# older rotated read while the C reads the bytes in place (not a case the game can meet).
TORN = 0x080F1000 - 0xA0
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
TORN_REC = 0x080E1000 - 1      # a sub-kind record whose kind byte is unmapped


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sx(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def cold(st, guards) -> bool:
    return any(not st.mem.get(g, 0) & 1 for g in guards)


def ostub(st, func: int, *args: int, value: int) -> None:
    st.oracle[(func,) + tuple(s32(a) for a in args[:LEAF_STUBS[func]])] = s32(value)


# ------------------------------------------------------------------ the made-up state
EXP_COMMON = [0, 0, 1, 5, 21, 51, 96, 161, 251]
EXP_RARE = [-1, -0x80000000, 0x7FFFFFFF, 0x100, 0x80, 0xFFFF]


def gen_view(rng):
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    st.zero(0x006D9600, 0x600)
    for g in LIMIT_GUARDS:
        st.put(g, 4, rng.choice([1, 0x101, 0xFFFFFFFF]))
    if rng.random() < 0.06:
        for g in LIMIT_GUARDS:
            if rng.random() < 0.5:
                st.put(g, 4, rng.choice([0, 0x100]))
    for k in range(NJOBS):
        st.fill(JOB(k), 0x100)
    for k in range(NUNITS):
        u = UNIT(k)
        st.fill(u, 0x140)
        st.put(u + 0xA0, 4, JOB(rng.randrange(NJOBS)) if rng.random() > 0.06 else rng.choice(UNMAPPED + [0]))
    # the unit
    r = rng.random()
    if r < 0.86:
        u = UNIT(rng.randrange(NUNITS))
    elif r < 0.93:
        for i in range(0xA0):
            st.mem[TORN + i] = rng.randrange(256)
        u = TORN
    else:
        u = rng.choice(UNMAPPED + [0])
    # the weapon exp per kind: mostly a few kinds above 0
    p_have = rng.choice([0.2, 0.4, 0.6, 0.9])
    for k in range(8):
        v = pick(rng, [rng.choice(EXP_COMMON[2:])] if rng.random() < p_have else [0], EXP_RARE, 0.12)
        ostub(st, GET_EXP, u, k, value=v)
    # the sub-kind records: kinds mostly 0 .. 7, some kinds missing, stones often twice
    for k in range(NSUB):
        st.fill(SUBREC(k), 0x10)
        st.put(SUBREC(k) + 1, 1, pick(rng, list(range(8)) + [7, 7, 7], [8, 0x7F, 0x80, 0x87, 0xFF, 0xF9], 0.12))
    for k in range(8):  # sometimes a kind has no record at all
        if rng.random() < 0.08:
            for j in range(NSUB):
                if st.mem[SUBREC(j) + 1] == k:
                    st.put(SUBREC(j) + 1, 1, rng.choice([8, 0xFF]))
    order = list(range(NSUB))
    rng.shuffle(order)
    for i in range(21):
        rec = SUBREC(order[i]) if rng.random() > 0.04 else rng.choice(UNMAPPED + [TORN_REC, 0])
        ostub(st, SUBKIND_GET, i, value=rec)
    # Job::CanEquipFromSubKind: for every class pointer the case can pass, every sub-kind
    jobs = {JOB(k) for k in range(NJOBS)} | {word(st, u + 0xA0)} | set(UNMAPPED) | {0}
    for j in jobs:
        for i in range(21):
            ostub(st, CAN_EQUIP, j, i, value=pick(rng, [0, 1, 1], [2, 0x100, 0xFFFFFFFF, 0x80000000], 0.1))
    n_lines = sum(1 for k in range(8) if sx(st.oracle[(GET_EXP, s32(u), k)], 32) > 0)
    line = pick(rng, list(range(max(1, n_lines))) + [n_lines],
                [-1, -0x80000000, 0x7FFFFFFF, 8, 9, 0x100, 0x80000001], 0.12)
    return st, f"ov:0x{ADDR['weapon_level_view_kind']:08X}", [u, line, 0, 0], ("call", ADDR["weapon_level_view_kind"], None)


FUNCS = {"weapon_level_view_kind": gen_view}


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
    inner = stubs[GET_EXP]

    def limited(cpu, a):  # GetWeaponExp: the game's code reaches GetWeaponExpLimit's guard while cold
        if any(not cpu.mem.read(g, 4) & 1 for g in LIMIT_GUARDS):
            raise A.ColdGuard()
        return inner(cpu, a)
    stubs[GET_EXP] = limited
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
/* Generated by src/readable/weapon_level_view/tests/weapon_level_view_diff.py: runs the
   weapon_level_view batch on memory images read from stdin and prints its results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "weapon_level_view.h"
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
    src = os.path.join(out, "weapon_level_view_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_DIR)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(my_dir, f) for f in sorted(os.listdir(my_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "weapon_level_view_driver.exe" if os.name == "nt" else "weapon_level_view_driver")
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
        raise SystemExit("weapon_level_view_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"weapon_level_view_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up (cold)"
    else:
        r0 = sx(exp[1], 32)
        calls = exp[3]
        stone_asked = f"{CAN_EQUIP:x}:" in calls
        if r0 >= 0:
            key = "stone sub-kind" if stone_asked else "sub-kind found"
            if stone_asked and calls.count(f"{CAN_EQUIP:x}:") > 1:
                key = "stone, refused then found"
        else:
            if f"{SUBKIND_GET:x}:" in calls:
                key = "-1, line reached but no sub-kind fits" + (" (stone asked)" if stone_asked else "")
            else:
                key = "-1, no such line"
        if exp[2]:
            key += ", unmapped reads"
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
        raise SystemExit(f"weapon_level_view_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
F = "weapon_level_view.c"
H = "weapon_level_view.h"
PLANTS = [
    # GetWeaponExp's caches not asked first: its override would give up nested
    (F, "    if (!exp_limit_ready(ctx))\n        return (int32_t)fe_use_original(ctx);\n", ""),
    # only two of the three caches asked
    (F, " && fe_static_ready(ctx, S_WlvExpLimitGuardB) &&", " &&"),
    # a kind with exp 0 or below counted as a line
    (F, "        if (exp <= 0)\n            continue;\n", ""),
    (F, "        if (exp <= 0)\n", "        if (exp < 0)\n"),
    # exp compared unsigned: a negative exp would count
    (F, "        if (exp <= 0)\n", "        if ((uint32_t)exp == 0u)\n"),
    (F, "        if (seen == line) {\n", "        if (seen >= line) {\n"),
    # a kind whose sub-kind is not found ends the search at once: the later GetWeaponExp calls missing
    (F, "                    return (int32_t)(int8_t)sub;\n            }\n        }\n",
     "                    return (int32_t)(int8_t)sub;\n            }\n            return WLV_NONE;\n        }\n"),
    (F, "        seen++;\n", "        if (exp > 1)\n            seen++;\n"),
    (H, "#define WLV_KINDS 8 ", "#define WLV_KINDS 7 "),
    (H, "#define WLV_SUBKINDS 21 ", "#define WLV_SUBKINDS 20 "),
    (F, "            for (int32_t sub = 0; sub < WLV_SUBKINDS; sub++) {", "            for (int32_t sub = 1; sub < WLV_SUBKINDS; sub++) {"),
    # ItemSubKind::Get read directly (its table word) instead of called: calls missing
    (F, "                gaddr record = guest_call1(ctx, WLV_ItemSubKindGet, (uint32_t)sub);\n",
     "                gaddr record = guest_u32(ctx, 0x006D3954u) + (gaddr)sub * 0x10u;\n"),
    # the record's kind read from the wrong byte
    (F, "FIELD_ADDR(ItemSubKindData, record, kind)", "FIELD_ADDR(ItemSubKindData, record, origin)"),
    (H, "#define WLV_KIND_STONE 7 ", "#define WLV_KIND_STONE 6 "),
    # the class test skipped for stones
    (F, "                if (kind != WLV_KIND_STONE ||\n", "                if (1 ||\n"),
    # the class test on every kind
    (F, "                if (kind != WLV_KIND_STONE ||\n", "                if (0 ||\n"),
    # the unit passed instead of its class
    (F, "READ_FIELD(ctx, Unit, unit, job),", "unit,"),
    # the class test's answer read as a byte
    (F, "                                (uint32_t)(int32_t)(int8_t)sub) != 0)",
     "                                (uint32_t)(int32_t)(int8_t)sub) % 256u != 0)"),
    (F, "                    return (int32_t)(int8_t)sub;\n", "                    return kind;\n"),
    (H, "#define WLV_NONE (-1) ", "#define WLV_NONE 0 "),
    # the record's kind compared with the line number instead of the weapon kind
    (F, "record, kind)) != kind)", "record, kind)) != seen)"),
    # a kind with exp exactly 1 not counted as a line
    (F, "        if (exp <= 0)\n", "        if (exp <= 1)\n"),
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
        print("weapon_level_view_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("weapon_level_view_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_DIR)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"weapon_level_view_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, _early) in per.items():
        total_bad += bad
        note = f"  ({cold_n} cold: both gave up at entry)" if cold_n else ""
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches{note}")
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("weapon_level_view_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("weapon_level_view_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"weapon_level_view_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"weapon_level_view_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
