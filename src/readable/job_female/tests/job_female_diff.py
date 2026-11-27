#!/usr/bin/env python3
"""Host differential test of the job_female batch against the game's own ARM code.

    python src/readable/job_female/tests/job_female_diff.py            300 cases
    python src/readable/job_female/tests/job_female_diff.py -n 1500 --seed 7   the long run
    python src/readable/job_female/tests/job_female_diff.py --plant    also plant bugs: each must be caught

The method of src/readable/female/tests/female_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): the
test makes up guest states (a class record with its PersonFlag word; Job::IsFemale's one-time cache and
its guard word, with the caches of Unit::IsFemale and Person::IsFemale beside it, each often holding a
different bit, so reading the wrong one is seen; all random test values, never game data, and on
purpose often outside the ranges the game uses: unmapped class pointers, a record whose high flag word
is on an unmapped page, cached bits in either half of the 64-bit word, 0, two bits or every bit, guard
words cold or hot with other bits set), runs the ORIGINAL ARM code of Job::IsFemale from the owner's
extracted/text.bin in arm_mini.py and the readable C function (built with the host gcc against
tools/readable/stub/) on the same memory, and compares r0, the number of bytes read from unmapped
memory AND the list of guest calls (none is expected; docs/DECISIONS.md F-018).

The body calls nothing once its cache is filled. While the guard is cold the original reaches the guard
routine (arm_mini raises "cold guard") before any other read, and the readable code must give up at
entry: no early give-up is allowed.

--plant copies src/readable/job_female/ to build/readable/job_female/plant/, makes one small wrong
change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one
mismatch. Changes that cannot change any answer are listed in docs/JOB_FEMALE.md and not planted.

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
OUT = os.path.join(ROOT, "build", "readable", "job_female")
SRC_DIR = os.path.join(ROOT, "src", "readable", "job_female")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
JOB_IS_FEMALE = 0x00524AF4
LEAF_STUBS: dict[int, int] = {}  # no callee once the cache is filled
ARITY = dict(LEAF_STUBS)

OVERRIDES = {"job_female_is_female": JOB_IS_FEMALE}
ADDR = dict(OVERRIDES)

# src/readable/job_female/job_female.h
JOB_GUARD, JOB_MASK = 0x006D39AC, 0x006D3A08
# the two other female caches (src/readable/female/female.h): decoys, never read by Job::IsFemale
OTHER_MASKS = (0x006D9AF0, 0x006D3B70)

# guest layout of the made-up state (8-aligned records, as the game's: the original reads them with ldrd)
JOB = lambda k: 0x08060000 + k * 0x100  # noqa: E731
NREC = 4
TORN_JOB = 0x080E1000 - 4      # a record whose flags' high word is on an unmapped page
UNMAPPED = [0, 0x40, 0x7FF0, 0x0FFF0000]
COLD = [0, 0x100, 0xFFFFFFFE]
HOT = [1, 0x101, 0xFFFFFFFF]


def u64(st, addr: int) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(8)), "little")


# ------------------------------------------------------------------ the made-up state
def cache(st, rng) -> int:
    """Job::IsFemale's guard and cached bit, the words around them filled with junk (a wrong offset
    reads something else), and the two other female caches holding (often) other bits. Returns the
    cached mask."""
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    st.fill(0x006D3980, 0x100)
    st.fill(0x006D3B00, 0x100)
    st.zero(0x006D9780, 0x400)
    st.put(JOB_GUARD, 4, COLD[rng.randrange(3)] if rng.random() < 0.1 else HOT[rng.randrange(3)])
    st.put(0x006D3B2C, 4, HOT[rng.randrange(3)])  # Person::IsFemale's guard: hot, so a swap is seen
    b = rng.randrange(64)
    v = pick(rng, [1 << b], [0, (1 << b) | (1 << rng.randrange(64)), (1 << 64) - 1, 1 << (b ^ 32)], 0.12)
    st.put(JOB_MASK, 8, v)
    for m in OTHER_MASKS:
        st.put(m, 8, v if rng.random() < 0.2 else 1 << rng.randrange(64))
    return v


def flag_word(rng, mask: int, p_has: float) -> int:
    """A sparse random PersonFlag word that sometimes holds (one of) the cached bit(s)."""
    w = rng.getrandbits(64) & rng.getrandbits(64) & rng.getrandbits(64) & ~mask
    if mask and rng.random() < p_has:
        bits = [i for i in range(64) if mask >> i & 1]
        w |= (1 << rng.choice(bits)) if rng.random() < 0.5 else mask
    return w


def put_record(st, addr: int, flags: int, size: int = 0x100) -> None:
    if addr == TORN_JOB:
        st.fill(addr - 0x3C, 0x40)
        st.put(addr, 4, flags)  # only the low word is mapped
    else:
        st.fill(addr, size)
        st.put(addr, 8, flags)


def gen_job(rng):
    st = State(rng)
    jmask = cache(st, rng)
    for k in range(NREC):
        put_record(st, JOB(k), flag_word(rng, jmask, 0.45))
    r = rng.random()
    if r < 0.88:
        job = JOB(rng.randrange(NREC))
    elif r < 0.94:
        job = TORN_JOB
        put_record(st, job, flag_word(rng, jmask, 0.5))
    else:
        job = rng.choice(UNMAPPED)
    return st, f"ov:0x{JOB_IS_FEMALE:08X}", [job, rng.getrandbits(32), 0, 0], ("call", JOB_IS_FEMALE, None)


FUNCS = {"job_female_is_female": gen_job}


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
/* Generated by src/readable/job_female/tests/job_female_diff.py: runs the
   job_female batch on memory images read from stdin and prints its results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "job_female.h"
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
    src = os.path.join(out, "job_female_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_DIR)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(my_dir, f) for f in sorted(os.listdir(my_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "job_female_driver.exe" if os.name == "nt" else "job_female_driver")
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
        raise SystemExit("job_female_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"job_female_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up (cold)"
    else:
        key = f"-> {exp[1]}" + (", unmapped reads" if exp[2] else "")
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
        raise SystemExit(f"job_female_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
F = "job_female.c"
H = "job_female.h"
RET = "    return (READ_FIELD(ctx, JobData, job, flags) & female) != 0;"
LOAD = "    uint64_t female = guest_u64(ctx, S_FemJobMask);"
PLANTS = [
    # the cache not asked first: the readable code would read a cold cache
    (F, "    if (!fe_static_ready(ctx, S_FemJobGuard))\n        return (int32_t)fe_use_original(ctx);\n", ""),
    # the wrong guard word: Person::IsFemale's, or the word after Job::IsFemale's
    (H, "#define S_FemJobGuard 0x006D39ACu", "#define S_FemJobGuard 0x006D3B2Cu"),
    (H, "#define S_FemJobGuard 0x006D39ACu", "#define S_FemJobGuard 0x006D39B0u"),
    # another function's cache (Unit::IsFemale's or Person::IsFemale's), the wrong offset, or only its low word
    (F, LOAD, "    uint64_t female = guest_u64(ctx, 0x006D9AF0u);"),
    (F, LOAD, "    uint64_t female = guest_u64(ctx, 0x006D3B70u);"),
    (H, "#define S_FemJobMask 0x006D3A08u", "#define S_FemJobMask 0x006D3A00u"),
    (F, LOAD, "    uint64_t female = guest_u32(ctx, S_FemJobMask);"),
    # the class word read as 32 bits, from the wrong offset, or through a pointer at +0
    (F, "READ_FIELD(ctx, JobData, job, flags) & female", "guest_u32(ctx, job) & female"),
    (F, "READ_FIELD(ctx, JobData, job, flags) & female", "guest_u64(ctx, job + 8u) & female"),
    (F, "READ_FIELD(ctx, JobData, job, flags) & female", "guest_u64(ctx, guest_u32(ctx, job)) & female"),
    # every cached bit required, the raw bits answered, the answer inverted
    (F, RET, "    return (READ_FIELD(ctx, JobData, job, flags) & female) == female;"),
    (F, RET, "    return (int32_t)(READ_FIELD(ctx, JobData, job, flags) & female);"),
    (F, RET, "    return (READ_FIELD(ctx, JobData, job, flags) & female) == 0;"),
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
        print("job_female_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("job_female_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_DIR)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"job_female_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, _early) in per.items():
        total_bad += bad
        note = f"  ({cold_n} cold: both gave up at entry)" if cold_n else ""
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches{note}")
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("job_female_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("job_female_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"job_female_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"job_female_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
