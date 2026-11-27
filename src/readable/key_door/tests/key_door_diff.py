#!/usr/bin/env python3
"""Host differential test of the key_door batch against the game's own ARM code.

    python src/readable/key_door/tests/key_door_diff.py            300 cases
    python src/readable/key_door/tests/key_door_diff.py -n 1500 --seed 7   the long run
    python src/readable/key_door/tests/key_door_diff.py --plant    also plant bugs: each must be caught

The method of src/readable/job_female/tests/job_female_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): the
test makes up guest states (Unit::CanKeyDoor's one-time cache, an s16 skill number, and its guard
word, the words around both filled with junk so a wrong offset is seen; the answers of the two guest
callees, Unit::IsEquipSkill and Unit::GetItemIndexKeyDoor, chosen per case; all random test values,
never game data, and on purpose often outside the ranges the game uses: negative and large skill
numbers, skill answers other than 0 and 1, item answers -1, -2, 0 .. 4, 0xFFFF and 0x80000000, unit
pointers that are 0 or unmapped, guard words cold or hot with other bits set), runs the ORIGINAL ARM
code of Unit::CanKeyDoor from the owner's extracted/text.bin in arm_mini.py and the readable C
function (built with the host gcc against tools/readable/stub/) on the same memory, and compares r0,
the number of bytes read from unmapped memory AND the ordered list of guest calls with their argument
registers (docs/DECISIONS.md F-018): the skill is asked first, the item only when the skill says no.

While the guard is cold the original reaches the guard routine (arm_mini raises "cold guard") before
any other read or call, and the readable code must give up at entry: no early give-up is allowed.

--plant copies src/readable/key_door/ to build/readable/key_door/plant/, makes one small wrong change at
a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch. Changes
that cannot change any answer are listed in docs/KEY_DOOR.md and not planted.

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
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
from stance_diff import State, pick  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "key_door")
SRC_DIR = os.path.join(ROOT, "src", "readable", "key_door")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
CAN_KEY_DOOR = 0x00529E20
HAS_SKILL = 0x0052DD04   # Unit::IsEquipSkill(short) const
KEY_ITEM = 0x00530BDC    # Unit::GetItemIndexKeyDoor(void) const
LEAF_STUBS: dict[int, int] = {HAS_SKILL: 2, KEY_ITEM: 1}
ARITY = dict(LEAF_STUBS)

OVERRIDES = {"key_door_unit_can_open": CAN_KEY_DOOR}
ADDR = dict(OVERRIDES)

# src/readable/key_door/key_door.h
KD_GUARD, KD_SKILL = 0x006D98F8, 0x006D96A0

UNITS = [0x08100000, 0x08100400, 0x08123450, 0]
COLD = [0, 0x100, 0xFFFFFFFE]
HOT = [1, 0x101, 0xFFFFFFFF]


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def ostub(st, func: int, *args: int, value: int) -> None:
    st.oracle[(func,) + tuple(s32(a) for a in args[:LEAF_STUBS[func]])] = s32(value)


# ------------------------------------------------------------------ the made-up state
def gen_key(rng):
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    st.fill(0x006D9600, 0x100)  # the cache and its neighbours: junk
    st.fill(0x006D9880, 0x100)  # the guard and its neighbours: junk (bit 0 random)
    st.put(KD_GUARD, 4, COLD[rng.randrange(3)] if rng.random() < 0.1 else HOT[rng.randrange(3)])
    skill = pick(rng, [rng.randrange(1, 0x200)], [0, -1, -rng.randrange(2, 0x8000), 0x7FFF,
                                                   0x100 | rng.randrange(0x100), rng.randrange(0x80, 0x100)], 0.3)
    st.put(KD_SKILL, 2, skill & 0xFFFF)
    unit = rng.choice(UNITS) if rng.random() < 0.85 else rng.getrandbits(32)
    has = pick(rng, [0, 1], [2, 0x100, 0xFFFFFFFF, 0x80000000], 0.12)
    ostub(st, HAS_SKILL, unit, skill, value=has)
    if rng.random() < 0.3:  # a decoy answer for a wrong argument: 1 (a wrong call must not pass unseen)
        ostub(st, HAS_SKILL, unit, skill & 0xFFFF, value=1 - (has != 0))
        ostub(st, HAS_SKILL, unit + 4, skill, value=1 - (has != 0))
    item = pick(rng, [-1, rng.randrange(5)], [-2, 0xFFFF, 0x80000000, 0x7FFFFFFF, 5], 0.15)
    ostub(st, KEY_ITEM, unit, value=item)
    return st, f"ov:0x{CAN_KEY_DOOR:08X}", [unit, rng.getrandbits(32), rng.getrandbits(32), 0], \
        ("call", CAN_KEY_DOOR, None)


FUNCS = {"key_door_unit_can_open": gen_key}


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
/* Generated by src/readable/key_door/tests/key_door_diff.py: runs the
   key_door batch on memory images read from stdin and prints its results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "key_door.h"
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
    src = os.path.join(out, "key_door_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_DIR)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(my_dir, f) for f in sorted(os.listdir(my_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "key_door_driver.exe" if os.name == "nt" else "key_door_driver")
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
        raise SystemExit("key_door_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"key_door_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up (cold)"
    else:
        how = "skill" if exp[3].count(",") == 0 else "item asked"
        key = f"{how} -> {exp[1]}" + (", unmapped reads" if exp[2] else "")
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
        raise SystemExit(f"key_door_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
F = "key_door.c"
H = "key_door.h"
GUARDED = "    if (!fe_static_ready(ctx, S_KeyDoorGuard))\n        return (int32_t)fe_use_original(ctx);\n"
LOAD = "    int32_t skill = guest_s16(ctx, S_KeyDoorSkill);"
ASK = "    if (guest_call2(ctx, KD_UnitIsEquipSkill, unit, (uint32_t)skill) != 0)\n        return 1;\n"
RET = "    return (int32_t)guest_call1(ctx, KD_UnitKeyItemIndex, unit) != KD_NO_ITEM;"
PLANTS = [
    # the cache not asked first: the readable code would read a cold cache and call
    (F, GUARDED, ""),
    # the wrong guard word (the next one, or one word before)
    (H, "#define S_KeyDoorGuard 0x006D98F8u", "#define S_KeyDoorGuard 0x006D98FCu"),
    (H, "#define S_KeyDoorGuard 0x006D98F8u", "#define S_KeyDoorGuard 0x006D98F4u"),
    # the wrong cache half-word, read unsigned, or cut to 8 bits
    (H, "#define S_KeyDoorSkill 0x006D96A0u", "#define S_KeyDoorSkill 0x006D96A2u"),
    (H, "#define S_KeyDoorSkill 0x006D96A0u", "#define S_KeyDoorSkill 0x006D96ACu"),
    (F, LOAD, "    int32_t skill = guest_u16(ctx, S_KeyDoorSkill);"),
    (F, LOAD, "    int32_t skill = (int8_t)guest_s16(ctx, S_KeyDoorSkill);"),
    # the skill not asked at all, asked of the wrong unit, or only an answer of exactly 1 taken
    (F, ASK, ""),
    (F, "KD_UnitIsEquipSkill, unit,", "KD_UnitIsEquipSkill, unit + 4u,"),
    (F, "(uint32_t)skill) != 0)", "(uint32_t)skill) == 1)"),
    # the item asked even when the skill said yes, or asked first
    (F, "        return 1;\n", "        (void)0;\n"),
    (F, ASK + RET, "    if ((int32_t)guest_call1(ctx, KD_UnitKeyItemIndex, unit) != KD_NO_ITEM)\n        return 1;\n"
                   "    return guest_call2(ctx, KD_UnitIsEquipSkill, unit, (uint32_t)skill) != 0;"),
    # the item's answer: only slots 0 and up taken, 0 taken as none, the raw slot answered, the answer inverted
    (F, RET, "    return (int32_t)guest_call1(ctx, KD_UnitKeyItemIndex, unit) >= 0;"),
    (F, RET, "    return (int32_t)guest_call1(ctx, KD_UnitKeyItemIndex, unit) > 0;"),
    (F, RET, "    return (int32_t)guest_call1(ctx, KD_UnitKeyItemIndex, unit) + 1;"),
    (F, RET, "    return (int32_t)guest_call1(ctx, KD_UnitKeyItemIndex, unit) == KD_NO_ITEM;"),
    (F, "        return 1;\n", "        return 2;\n"),
    # the item check reading only the low half-word (0xFFFF taken as none)
    (F, RET, "    return (int16_t)guest_call1(ctx, KD_UnitKeyItemIndex, unit) != KD_NO_ITEM;"),
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
        print("key_door_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("key_door_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_DIR)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"key_door_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, _early) in per.items():
        total_bad += bad
        note = f"  ({cold_n} cold: both gave up at entry)" if cold_n else ""
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches{note}")
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("key_door_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("key_door_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"key_door_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"key_door_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
