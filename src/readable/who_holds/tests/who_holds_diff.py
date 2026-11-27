#!/usr/bin/env python3
"""Host differential test of the who_holds batch against the game's own ARM code.

    python src/readable/who_holds/tests/who_holds_diff.py            300 cases
    python src/readable/who_holds/tests/who_holds_diff.py -n 1500 --seed 7   the long run
    python src/readable/who_holds/tests/who_holds_diff.py --plant    also plant bugs: each must be caught

The method of src/readable/weapon_level_view/tests/weapon_level_view_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): the
test makes up guest states (a class record: its category bits, weapon-exp caps and origin byte; the
sub-kind record ItemSubKind::Get answers; the function's five one-time caches and their guard words;
all random test values, never game data, and on purpose often outside the ranges the game uses:
unmapped class pointers and records, a class whose caps and origin are on an unmapped page, record
kinds past 7 and negative, sub-kinds negative, huge and with a stone number in the low byte only,
cache bits that are 0, several bits or the same bit twice), runs the ORIGINAL ARM code of
Job::CanEquipFromSubKind from the owner's extracted/text.bin in arm_mini.py and the readable C
function (built with the host gcc against tools/readable/stub/) on the same memory, and compares r0,
the number of bytes read from unmapped memory AND the list of guest calls, in order, with their
argument registers (docs/DECISIONS.md F-018).

The one callee, ItemSubKind::Get, is answered by one table on both sides and listed. While one of the
five guards is cold the original reaches the guard routine (arm_mini raises "cold guard") before any
other read or call, and the readable code must give up at entry: no early give-up is allowed.

--plant copies src/readable/who_holds/ to build/readable/who_holds/plant/, makes one small wrong
change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one
mismatch. Changes that cannot change any answer (the order of the cache read and the class read: the
caches are always mapped) are listed in docs/WHO_HOLDS.md and not planted.

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
OUT = os.path.join(ROOT, "build", "readable", "who_holds")
SRC_DIR = os.path.join(ROOT, "src", "readable", "who_holds")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
SUBKIND_GET, CAN_EQUIP = 0x0019B97C, 0x00524420
LEAF_STUBS = {SUBKIND_GET: 1}
ARITY = dict(LEAF_STUBS)

OVERRIDES = {"who_holds_can_equip_subkind": CAN_EQUIP}
ADDR = dict(OVERRIDES)

# src/readable/who_holds/who_holds.h: guards in the game's order, and the u16 behind each
GUARDS = (0x006D39D0, 0x006D39CC, 0x006D39C8, 0x006D39C4, 0x006D39C0)
MASKS = (0x006D3994, 0x006D3996, 0x006D3998, 0x006D399A, 0x006D399C)

# guest layout of the made-up state
JOB = lambda k: 0x08020000 + k * 0x100  # noqa: E731
SUBREC = lambda k: 0x08040000 + k * 0x10  # noqa: E731
NJOBS, NSUB = 4, 8
# a class whose caps (+0x44) and origin (+0x74) are on an unmapped page; its category (+0x1A) is
# mapped. 4-aligned, as every class record in the game (no read straddles the page edge).
TORN = 0x080F1000 - 0x40
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
TORN_REC = 0x080E1000 - 1      # a sub-kind record whose kind byte is unmapped


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
SUB_RARE = [-1, 13, 20, 21, 0x7FFFFFFF, -0x80000000, 0x10E, 0x111, 0x113, -242, 0x8000000F]


def gen_holds(rng):
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    st.zero(0x006D3980, 0x80)
    for g in GUARDS:
        st.put(g, 4, rng.choice([1, 0x101, 0xFFFFFFFF]))
    r = rng.random()
    if r < 0.05:  # several cold
        for g in GUARDS:
            if rng.random() < 0.4:
                st.put(g, 4, rng.choice([0, 0x100, 0xFFFFFFFE]))
    elif r < 0.15:  # exactly one cold: each guard must be asked
        st.put(rng.choice(GUARDS), 4, rng.choice([0, 0x100, 0xFFFFFFFE]))
    # the cached category bits: mostly five different single bits, sometimes 0, two bits or a repeat
    bits = rng.sample(range(16), 5)
    masks = []
    for i, m in enumerate(MASKS):
        v = pick(rng, [1 << bits[i]], [0, (1 << bits[i]) | (1 << rng.randrange(16)), 1 << bits[0], 0xFFFF], 0.1)
        st.put(m, 2, v)
        masks.append(v)
    for k in range(NJOBS):
        j = JOB(k)
        st.fill(j, 0x100)
        cat = 0
        for v in masks:
            if rng.random() < 0.5:
                cat |= v
        if rng.random() < 0.3:
            cat |= 1 << rng.randrange(16)
        st.put(j + 0x1A, 2, pick(rng, [cat], [0, 0xFFFF], 0.08))
        for w in range(8):
            st.put(j + 0x44 + w, 1, pick(rng, [0, 0, 1, 51, 251], [0x80, 0xFF], 0.1))
        st.put(j + 0x74, 1, pick(rng, [0, 1, 2, 1, 2, 1, 2, 3], [0x81, 0xFF, 0x41], 0.1))
    r = rng.random()
    if r < 0.86:
        job = JOB(rng.randrange(NJOBS))
    elif r < 0.94:
        st.fill(TORN, 0x40)
        st.put(TORN + 0x1A, 2, word(st, JOB(0) + 0x1A, 2))
        job = TORN
    else:
        job = rng.choice(UNMAPPED + [0])
    # the sub-kind: often a stone one
    sub = pick(rng, list(range(21)) + list(range(14, 20)) * 10, SUB_RARE, 0.1)
    # the record ItemSubKind::Get answers (only the one asked)
    for k in range(NSUB):
        st.fill(SUBREC(k), 0x10)
    k = rng.randrange(NSUB)
    stone_sub = (sub & 0xFF) in range(14, 20)
    kind = pick(rng, [7] * 20 + list(range(7)) if stone_sub else list(range(8)) + [7],
                [8, 0x7F, 0x80, 0x87, 0xFF, 0xF9, 0xBC], 0.12)
    st.put(SUBREC(k) + 1, 1, kind)
    rec = SUBREC(k) if rng.random() > 0.05 else rng.choice(UNMAPPED + [TORN_REC, 0])
    ostub(st, SUBKIND_GET, sub, value=rec)
    return st, f"ov:0x{CAN_EQUIP:08X}", [job, sub, 0, 0], ("call", CAN_EQUIP, None)


FUNCS = {"who_holds_can_equip_subkind": gen_holds}


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
/* Generated by src/readable/who_holds/tests/who_holds_diff.py: runs the
   who_holds batch on memory images read from stdin and prints its results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "who_holds.h"
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
    src = os.path.join(out, "who_holds_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_DIR)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(my_dir, f) for f in sorted(os.listdir(my_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "who_holds_driver.exe" if os.name == "nt" else "who_holds_driver")
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
        raise SystemExit("who_holds_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"who_holds_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up (cold)"
    else:
        rec = st.oracle.get((SUBKIND_GET, s32(args[1])), 0)
        kb = st.mem.get(rec + 1)
        sub = sx(args[1], 32)
        if kb is None:
            key = "record unmapped"
        elif kb != 7:
            key = "weapon cap" + (" (kind past 0..7)" if kb > 7 else "")
        elif 14 <= sub <= 19:
            key = f"stone {sub}"
        else:
            key = "stone, other sub-kind"
        key += f" -> {exp[1]}"
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
        raise SystemExit(f"who_holds_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
F = "who_holds.c"
H = "who_holds.h"
PLANTS = [
    # the caches not asked first: the readable code would read a cold cache
    (F, "    if (!caches_ready(ctx))\n        return (int32_t)fe_use_original(ctx);\n", ""),
    # one guard not asked
    (F, " &&\n           fe_static_ready(ctx, S_WhGuardTransform);", ";"),
    (F, "fe_static_ready(ctx, S_WhGuardBeast) &&", "1 &&"),
    # ItemSubKind::Get read directly (its table word) instead of called: the call missing
    (F, "    gaddr record = guest_call1(ctx, WH_ItemSubKindGet, (uint32_t)sub);\n",
     "    gaddr record = guest_u32(ctx, 0x006D3954u) + (gaddr)sub * 0x10u;\n"),
    # the sub-kind passed as its low byte
    (F, "guest_call1(ctx, WH_ItemSubKindGet, (uint32_t)sub);",
     "guest_call1(ctx, WH_ItemSubKindGet, (uint32_t)(int8_t)sub);"),
    # the record's kind read unsigned, or from the wrong byte
    (F, "    int32_t kind = guest_s8(ctx,", "    int32_t kind = guest_u8(ctx,"),
    (F, "FIELD_ADDR(ItemSubKindData, record, kind)", "FIELD_ADDR(ItemSubKindData, record, origin)"),
    # the stone test wrong
    (H, "#define WH_KIND_STONE 7 ", "#define WH_KIND_STONE 6 "),
    (F, "    if (kind != WH_KIND_STONE)\n", "    if (kind < WH_KIND_STONE)\n"),
    # the cap byte: the kind not added, or the cap compared with 1
    (F, "max_weapon_exp) + (gaddr)kind) != 0;", "max_weapon_exp)) != 0;"),
    (F, "max_weapon_exp) + (gaddr)kind) != 0;", "max_weapon_exp) + (gaddr)kind) > 1;"),
    # a kind past 7 clamped (the game does not range-check)
    (F, "max_weapon_exp) + (gaddr)kind)", "max_weapon_exp) + (gaddr)(kind & 7))"),
    # the stone rules
    (H, "#define WH_STONE_FIRST 14 ", "#define WH_STONE_FIRST 13 "),
    (F, "S_WhMaskDragon, job, &category) && !also_has(ctx, S_WhMaskTransform, category);",
     "S_WhMaskDragon, job, &category) && also_has(ctx, S_WhMaskTransform, category);"),
    (F, "        return first_has(ctx, S_WhMaskBeast, job, &category);",
     "        return first_has(ctx, S_WhMaskDragon, job, &category);"),
    (F, "S_WhMaskDragon, job, &category) && also_has(ctx, S_WhMaskTransform, category);",
     "S_WhMaskDragon, job, &category);"),
    (F, "S_WhMaskMonster, job, &category) && !also_has(ctx, S_WhMaskHumanoid, category);",
     "S_WhMaskMonster, job, &category) && !also_has(ctx, S_WhMaskTransform, category);"),
    (H, "#define WH_ORIGIN_NOHR 2", "#define WH_ORIGIN_NOHR 3"),
    (F, "READ_FIELD(ctx, JobData, job, origin) == WH_ORIGIN_HOSHIDO;",
     "READ_FIELD(ctx, JobData, job, origin) >= WH_ORIGIN_HOSHIDO;"),
    # the human-shaped test dropped on 19
    (F, "        return first_has(ctx, S_WhMaskHumanoid, job, &category) &&\n"
        "               READ_FIELD(ctx, JobData, job, origin) == WH_ORIGIN_HOSHIDO;",
     "        return READ_FIELD(ctx, JobData, job, origin) == WH_ORIGIN_HOSHIDO;"),
    (F, "    default:\n        return 0;", "    default:\n        return 1;"),
    # the class's category read as a byte
    (F, "    *category = READ_FIELD(ctx, JobData, job, category);",
     "    *category = guest_u8(ctx, FIELD_ADDR(JobData, job, category));"),
    # a cache read from the wrong word
    (H, "#define S_WhMaskMonster 0x006D3998u", "#define S_WhMaskMonster 0x006D399Au"),
    # the second test keeps only the low byte of the class's word
    (F, "    return (guest_u16(ctx, mask) & category) != 0;",
     "    return (guest_u16(ctx, mask) & category & 0xFFu) != 0;"),
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
        print("who_holds_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("who_holds_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_DIR)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"who_holds_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, _early) in per.items():
        total_bad += bad
        note = f"  ({cold_n} cold: both gave up at entry)" if cold_n else ""
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches{note}")
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("who_holds_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("who_holds_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"who_holds_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"who_holds_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
