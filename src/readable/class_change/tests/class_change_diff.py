#!/usr/bin/env python3
"""Host differential test of the class-change and seal batch against the game's own ARM code.

    python src/readable/class_change/tests/class_change_diff.py             all functions, 300 cases each
    python src/readable/class_change/tests/class_change_diff.py -n 1500 --seed 7    the long run
    python src/readable/class_change/tests/class_change_diff.py --only battle_seal_effect
    python src/readable/class_change/tests/class_change_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/battle2/tests/battle2_diff.py (and the ARM interpreter
src/readable/battle/tests/arm_mini.py): for every readable function of src/readable/class_change/
the test makes up guest states (units with their state bits and Person, Person records with their
two class numbers, items with a kind byte, the map fight's sequence object with its strike and
fight records, skill records, a seal block; all random test values, never game data, and on
purpose often outside the ranges the game uses: unmapped units, records and skill lookups, kind
bytes and amounts that are negative or huge, side numbers other than 0 and 1), runs the ORIGINAL
ARM code from the owner's extracted/text.bin in arm_mini.py and the readable C function (built with
the host gcc against tools/readable/stub/) on the same memory, and compares r0, the number of bytes
read from unmapped memory AND the list of guest calls, in order, with their argument registers
(docs/DECISIONS.md F-018). On the ARM side every BL and every tail branch (B) to a listed callee is
listed (GetSealEffect ends in two tail branches to EquipSkill::Get). No function of this batch reads
a one-time cache, so any give-up of the readable code is a mismatch.

Guest functions answered by one table on both sides (listed and compared): Job::Get(unsigned short),
Job::IsHigh, Person::IsDownload, EquipSkill::Get(const char*) and Unit::IsEquipSkill.

seal_merged_value is not an override (the pure part of the writer MergeSeal) and runs through a
test-only entry of the generated driver (never a marker in src/readable/): the ARM function runs
whole and the byte it STORES is the expected result; the seal block is always mapped there, since
the game writes into it.

--plant copies src/readable/class_change/ to build/readable/class_change/plant/, makes one small
wrong change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one
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
BATTLE_TESTS = os.path.join(ROOT, "src", "readable", "battle", "tests")
sys.path.insert(0, BATTLE_TESTS)
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
from stance_diff import State, pick  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "class_change")
SRC_CC = os.path.join(ROOT, "src", "readable", "class_change")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
JOB_GET, JOB_IS_HIGH, IS_DOWNLOAD, SKILL_GET, IS_EQUIP = 0x00341AA4, 0x00524804, 0x0053DFEC, 0x001758C4, 0x0052DD04
LEAF_STUBS = {JOB_GET: 1, JOB_IS_HIGH: 1, IS_DOWNLOAD: 1, SKILL_GET: 1, IS_EQUIP: 2}
ARITY = dict(LEAF_STUBS)

OVERRIDES = {  # name -> address (the registered overrides)
    "class_change_type": 0x001951B0, "unit_reliance_blocks_class_change": 0x00532D60,
    "person_base_job_index": 0x0053E198, "battle_seal_effect": 0x00357120,
}
TEST_ENTRIES = {"seal_merged_value": 0x00354D2C}  # the helper of the writer MergeSeal
ADDR = dict(OVERRIDES, **TEST_ENTRIES)

# skill ID labels (class_change.h CC_SEID_*): addresses in the code segment, passed by address
FIRST_LABELS = (0x0035739C, 0x003573A8, 0x003573B4, 0x003573C4, 0x003573D4, 0x003573E4)
DIRTY, CLUMSY, NINJA, ICE, CHAIN = 0x003573F4, 0x0035740C, 0x00357424, 0x00357434, 0x00354D98
SEAL_LABELS = FIRST_LABELS + (DIRTY, CLUMSY, NINJA, ICE)

# guest layout of the made-up state
UNIT = lambda k: 0x08000000 + k * 0x140  # noqa: E731
PERSON = lambda k: 0x08010000 + k * 0x100  # noqa: E731
JOBREC = lambda k: 0x08020000 + k * 0x100  # noqa: E731
ITEM = lambda k: 0x08040000 + k * 0x80  # noqa: E731
SEQ = 0x08100000
STRIKE = 0x08110000
FIGHT = 0x08120000
SKILLREC = lambda k: 0x08130000 + k * 0x20  # noqa: E731
CAP = 0x08140040  # seal block: 0x100 bytes mapped around it
NUNITS, NPERS, NJOBS, NITEMS, NSKILLS = 6, 6, 6, 8, 12
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sx(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get((addr + i) & 0xFFFFFFFF, 0) for i in range(n)), "little")


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    for k in range(NUNITS):
        u = UNIT(k)
        st.fill(u, 0x140)
        flags = rng.randrange(1 << 32)
        flags = (flags | 0x10000000) if rng.random() < 0.6 else (flags & ~0x10000000)
        st.put(u + 8, 4, flags)
        st.put(u + 0x9C, 4, PERSON(rng.randrange(NPERS)) if rng.random() > 0.06 else rng.choice(UNMAPPED))
    for k in range(NPERS):
        st.fill(PERSON(k), 0x40)
        for off in (0x2C, 0x2E):
            st.put(PERSON(k) + off, 2, pick(rng, list(range(1, 40)), [0, 0xFFFF, 0x8000, 0x7FFF], 0.1))
    for k in range(NJOBS):
        st.fill(JOBREC(k), 0x80)
    for k in range(NSKILLS):
        st.fill(SKILLREC(k), 0x20)
        st.put(SKILLREC(k) + 0x10, 2, pick(rng, list(range(1, 200)), [0, 0xFFFF, 0x8000, 0x7FFF], 0.1))
    return st


def ref(st, make, n: int, p_zero: float = 0.04, p_unmapped: float = 0.05) -> int:
    r = st.rng.random()
    if r < p_zero:
        return 0
    if r < p_zero + p_unmapped:
        return st.rng.choice(UNMAPPED)
    return make(st.rng.randrange(n))


def ov(name, args, post=None):
    a = ADDR[name]
    return f"ov:0x{a:08X}", [s32(x) for x in args] + [0] * (4 - len(args)), ("call", a, post)


def answer_skill(st, unit: int, label: int, p_has: float) -> None:
    """EquipSkill::Get(label) and Unit::IsEquipSkill(unit, the record's number) for one label"""
    rng = st.rng
    rec = ref(st, SKILLREC, NSKILLS, 0.06, 0.05)
    st.oracle[(SKILL_GET, label)] = rec
    number = s32(sx(word(st, rec + 0x10, 2), 16))
    st.oracle[(IS_EQUIP, s32(unit), number)] = rng.choice([1, 1, 1, 2, 0xFFFFFFFF]) if rng.random() < p_has else 0


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def gen_type(rng):
    st = base_state(rng)
    for k in range(NITEMS):
        st.fill(ITEM(k), 0x48)
        st.put(ITEM(k) + 0x40, 1, pick(rng, [0, 0, 1, 2, 3, 4, 4, 5, 6, 6, 7], [-1, -4, -6, 127, -128, 0x44], 0.15) & 0xFF)
    item = ITEM(rng.randrange(NITEMS)) if rng.random() > 0.06 else rng.choice(UNMAPPED)
    return (st,) + ov("class_change_type", [item])


def gen_reliance(rng):
    st = base_state(rng)
    unit = ref(st, UNIT, NUNITS, 0.0, 0.06)
    st.oracle[(IS_DOWNLOAD, s32(word(st, unit + 0x9C)))] = rng.choice([0, 0, 1, 2, 0xFFFFFFFF, 0x100])
    return (st,) + ov("unit_reliance_blocks_class_change", [unit])


def gen_low_job(rng):
    st = base_state(rng)
    person = ref(st, PERSON, NPERS, 0.0, 0.06)
    number = word(st, person + 0x2C, 2)
    job = ref(st, JOBREC, NJOBS, 0.05, 0.05)
    st.oracle[(JOB_GET, number)] = job
    st.oracle[(JOB_IS_HIGH, s32(job))] = rng.choice([0, 0, 1, 1, 2, 0xFFFFFFFF])
    return (st,) + ov("person_base_job_index", [person])


def gen_seal_effect(rng):
    st = base_state(rng)
    st.fill(SEQ, 0x300)
    st.fill(STRIKE, 0x40)
    st.fill(FIGHT, 0x240)
    st.put(SEQ + 0x25C, 4, 0 if rng.random() < 0.9 else rng.choice([1, 0x80000000, 0xFFFFFFFF]))
    mode = rng.randrange(1 << 32) if rng.random() < 0.5 else 0
    for bit in (4, 0x2000):
        mode = (mode | bit) if rng.random() < 0.05 else (mode & ~bit)
    st.put(SEQ + 0x280, 4, mode)
    st.put(SEQ + 0x274, 4, 0 if rng.random() < 0.06 else rng.choice([1, 2, 0x8000, 0xFFFFFFFF]))
    st.put(SEQ + 0x250, 4, STRIKE if rng.random() > 0.04 else rng.choice(UNMAPPED))
    st.put(SEQ + 0x24C, 4, FIGHT if rng.random() > 0.04 else rng.choice(UNMAPPED))
    for side in range(2):
        f = rng.randrange(1 << 32) if rng.random() < 0.3 else 0
        for bit, p in ((0x400, 0.05), (0x80, 0.5), (0x8000, 0.3), (0x10000, 0.3)):
            f = (f | bit) if rng.random() < p else (f & ~bit)
        st.put(STRIKE + 0x24 + 4 * side, 4, f)
    st.put(FIGHT + 0x23C, 4, s32(pick(rng, [0, 0, -1, 1, 2, -5], [0x7FFFFFFF, -0x80000000], 0.1)))
    side = pick(rng, [0, 0, 1, 1], [2, 3, 0xFFFFFFFF, 0x40], 0.12)
    units = []
    for s in range(2):
        u = ref(st, UNIT, NUNITS, 0.04, 0.04)
        st.put(SEQ + 0x270 + 4 * s, 4, u)
        units.append(u)
    unit = s32(word(st, s32(SEQ + 0x270 + 4 * side)))
    p_has = rng.choice([0.0, 0.08, 0.15, 0.3])
    focus = rng.random() < 0.35  # side 0's two extra steps ("dirty fight", "clumsy") met often
    if focus and side < 2:
        side = 0
        unit = s32(word(st, SEQ + 0x270))
    for label in SEAL_LABELS:
        answer_skill(st, unit, label, (0.03 if label in FIRST_LABELS else 0.5) if focus else p_has)
    return (st,) + ov("battle_seal_effect", [SEQ if rng.random() > 0.03 else 0x7FF0, side])


def gen_merge(rng):
    st = base_state(rng)
    st.fill(CAP - 0x40, 0x100)
    unit = ref(st, UNIT, NUNITS, 0.04, 0.04)
    answer_skill(st, unit, CHAIN, rng.choice([0.2, 0.5, 0.8]))
    stat = pick(rng, list(range(8)), [-8, -1, 8, 15, 0x30], 0.1)
    for i in range(8):
        if rng.random() < 0.5:
            st.put(CAP + i, 1, pick(rng, [0, 0, 1, 2, 3, 4, 5, 6], [0x7F, 0x80, 0xFF, 0xFE, 0xFB], 0.3))
    value = s32(pick(rng, [0, 1, 2, 3, 4, 5, 6, 8], [-1, -6, 127, 128, 255, 256, 0x7FFFFFFF, -0x80000000, 0x1FF], 0.15))
    at = s32(CAP + stat)
    return (st,) + ov("seal_merged_value", [CAP, unit, s32(stat), value], post=lambda mem: mem.read8(at))


FUNCS = {
    "class_change_type": gen_type,
    "unit_reliance_blocks_class_change": gen_reliance,
    "person_base_job_index": gen_low_job,
    "battle_seal_effect": gen_seal_effect,
    "seal_merged_value": gen_merge,
}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX and every tail branch (B) to a callee of ARITY with its
    argument registers (stubbed calls)."""

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
            if target in ARITY and stub is not None:
                self.listed.append(call_text(target, self.r[:ARITY[target]]))
                self.r[0] = stub(self, tuple(self.r[:4])) & A.MASK
                self.r[15] = self.r[14]
                return
        super().step(ins, pc)


def call_text(target: int, regs) -> str:
    return f"{target:x}" + "".join(f":{r & 0xFFFFFFFF:x}" for r in regs)


def arm_run(text: bytes, st, kind: str, args: list[int], how: tuple) -> list:
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]. For the
    helper, r0 is what the original stored (how[2] reads it from the memory afterwards)."""
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
    # stores outside the stack: none for an override (a reader), exactly the one byte for MergeSeal
    stores = [w for w in mem.writes if not (SP - 0x800 <= w[0] < SP + 0x400)]
    want = 0 if how[2] is None else 1
    if len(stores) != want or any(w[1] != 1 for w in stores):
        raise A.Unsupported(f"the original stored {stores[:4]} outside the stack ({want} byte(s) expected)")
    r0 = cpu.r[0] if how[2] is None else how[2](mem)
    return [0, r0, mem.faults, ",".join(cpu.listed) if cpu.listed else "-"]


# ------------------------------------------------------------------ the C side
DRIVER_HEAD = r'''
/* Generated by src/readable/class_change/tests/class_change_diff.py: runs the class-change and seal
   batch on memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "class_change.h"
'''

TEST_ENTRY_CODE = r'''
/* test-only entry (never in src/readable/: MergeSeal is a writer and has no override row) */
void test_0x00354D2C(Context *ctx) { FE_ENTRY(0x00354D2C, seal_merged_value, FE_ARG(0), FE_ARG(1), FE_ARG_S(2), FE_ARG_S(3)); }
'''


def driver_text() -> str:
    sys.path.insert(0, os.path.join(ROOT, "src", "readable", "sheet", "tests"))
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


def build_driver(cc: str, out: str, cc_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, this folder's taken from cc_dir (a
    planted bug may leave a parameter unused: not strict then). The other areas' objects are
    compiled once per run and reused for every planted bug."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "class_change_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_CC)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(cc_dir, f) for f in sorted(os.listdir(cc_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "class_change_driver.exe" if os.name == "nt" else "class_change_driver")
    inc = ["-I", cc_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
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
        raise SystemExit("class_change_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"class_change_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, int] = {}  # battle_seal_effect: which answer the original gave (printed as evidence)


def seal_path(st, args: list[int], r0: int) -> None:
    if r0 == 0:
        key = "none"
    else:
        hits = [i for i, lab in enumerate(SEAL_LABELS) if st.oracle.get((SKILL_GET, lab)) == r0]
        names = ["curse", "str", "mag", "spd", "def", "res", "dirty", "clumsy", "ninja", "ice"]
        key = names[hits[0]] if hits else "other"
    PATHS[key] = PATHS.get(key, 0) + 1


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines = [f"arity {f:x} {k}" for f, k in ARITY.items()]
    expected: dict[int, tuple] = {}
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
            if name == "battle_seal_effect" and exp[0] == 0:
                seal_path(st, args, exp[1])
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
        raise SystemExit(f"class_change_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list] = {}
    flagged: dict[int, str] = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE", "NESTED-GIVEUP"):
            flagged[int(parts[0])] = parts[1]
        elif parts:
            got[int(parts[0])] = [parse(x) for x in parts[1:4]] + parts[4:]  # the call list stays text
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs) in expected.items():
        res = per.setdefault(name, [0, 0])  # cases, mismatches
        res[0] += 1
        g = got.get(c)
        if exp[0] == 0:
            cov = COVERAGE.setdefault(name, {"values": set(), "nonzero": 0, "faulty": 0, "calls": 0})
            cov["values"].add(exp[1])
            cov["nonzero"] += int(exp[1] != 0)
            cov["faulty"] += int(exp[2] != 0)
            cov["calls"] += 0 if exp[3] == "-" else exp[3].count(",") + 1
        else:
            exp = [1, 0]  # no cache in this batch: the original never reaches the guard; kept for safety
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
F = "class_change.c"
PLANTS = [
    # class_change_type
    (F, "    int8_t kind = guest_s8(ctx, item + CC_ITEM_KIND_BYTE);", "    uint8_t kind = guest_u8(ctx, item + CC_ITEM_KIND_BYTE);\n    if (kind > 0x7F)\n        return 0;"),
    (F, "    if (kind == 4)\n        return 2;", "    if (kind == 5)\n        return 2;"),
    (F, "    if (kind == 6)\n        return 3;", "    if (kind >= 6)\n        return 3;"),
    (F, "    int8_t kind = guest_s8(ctx, item + CC_ITEM_KIND_BYTE);", "    int8_t kind = guest_s8(ctx, item + 0x41u);"),
    # unit_reliance_blocks_class_change
    (F, "    if ((READ_FIELD(ctx, Unit, unit, state_flags) & CC_UNIT_DOWNLOAD_ONLY) == 0)\n        return 0;",
     "    if ((READ_FIELD(ctx, Unit, unit, state_flags) & 0x08000000u) == 0)\n        return 0;"),
    (F, "    return download == 0 ? 1u : 0u;", "    return download == 1 ? 0u : 1u;"),
    (F, "    uint32_t download = guest_call1(ctx, CC_PersonIsDownload, READ_FIELD(ctx, Unit, unit, person));",
     "    uint32_t download = guest_call1(ctx, CC_PersonIsDownload, unit);"),
    # person_base_job_index
    (F, "        return READ_FIELD(ctx, PersonData, person, job_low);\n    return READ_FIELD(ctx, PersonData, person, job);",
     "        return READ_FIELD(ctx, PersonData, person, job_low);\n    return guest_u16(ctx, person + 0x2Cu) & 0xFFu;"),
    (F, "    if (guest_call1(ctx, CC_JobIsHigh, job) != 0)", "    if (guest_call1(ctx, CC_JobIsHigh, job) == 1)"),
    # the class number read once instead of twice (one unmapped read fewer)
    (F, "    gaddr job = guest_call1(ctx, CC_JobGet, READ_FIELD(ctx, PersonData, person, job));\n    if (guest_call1(ctx, CC_JobIsHigh, job) != 0)\n        return READ_FIELD(ctx, PersonData, person, job_low);\n    return READ_FIELD(ctx, PersonData, person, job);",
     "    uint16_t number = READ_FIELD(ctx, PersonData, person, job);\n    gaddr job = guest_call1(ctx, CC_JobGet, number);\n    if (guest_call1(ctx, CC_JobIsHigh, job) != 0)\n        return READ_FIELD(ctx, PersonData, person, job_low);\n    return number;"),
    # battle_seal_effect
    (F, "    if (guest_u32(ctx, sequence + CC_SEQ_MODE) & CC_SEQ_MODE_NO_SEAL)", "    if (guest_u32(ctx, sequence + CC_SEQ_MODE) & 0x4u)"),
    (F, "    if (guest_u32(ctx, strike + CC_STRIKE_FLAGS + 4u) & CC_STRIKE_NO_SEAL)\n        return 0;\n", ""),
    (F, "    if (active == 0)\n        return 0;", "    if (active == 0)\n        return 1;"),
    (F, "    static const gaddr first[] = {CC_SEID_DragonCurse, CC_SEID_SealStr, CC_SEID_SealMag,\n                                  CC_SEID_SealSpd, CC_SEID_SealDef, CC_SEID_SealRes};",
     "    static const gaddr first[] = {CC_SEID_DragonCurse, CC_SEID_SealMag, CC_SEID_SealStr,\n                                  CC_SEID_SealSpd, CC_SEID_SealDef, CC_SEID_SealRes};"),
    (F, "    for (size_t i = 0; i < sizeof first / sizeof first[0]; i++) {", "    for (size_t i = 0; i + 1 < sizeof first / sizeof first[0]; i++) {"),
    (F, "    if (side == 0) {", "    if (side != 1) {"),
    (F, "        if (guest_s32(ctx, fight + CC_FIGHT_DIRTY_OFF) <= 0) {", "        if (guest_s32(ctx, fight + CC_FIGHT_DIRTY_OFF) < 0) {"),
    (F, "        if (guest_u32(ctx, strike + CC_STRIKE_FLAGS) & CC_STRIKE_CLUMSY) {", "        if (guest_u32(ctx, strike + CC_STRIKE_FLAGS + 4u) & CC_STRIKE_CLUMSY) {"),
    # the last step reads the side's word from the fight record instead of the strike record. (Not
    # reading the strike pointer again cannot be seen by any test: nothing stores, so the pointer
    # cannot change, and the sequence word it comes from was already read, mapped.)
    (F, "    strike = guest_ptr(ctx, sequence + CC_SEQ_STRIKE);\n    uint32_t own",
     "    strike = guest_ptr(ctx, sequence + CC_SEQ_FIGHT);\n    uint32_t own"),
    (F, "    uint32_t own = guest_u32(ctx, strike + side * 4u + CC_STRIKE_FLAGS);", "    uint32_t own = guest_u32(ctx, strike + CC_STRIKE_FLAGS);"),
    (F, "    if (own & CC_STRIKE_NINJA)\n        return guest_call1(ctx, CC_EquipSkillGet, CC_SEID_NinjaReturn);\n    if (own & CC_STRIKE_ICE)\n        return guest_call1(ctx, CC_EquipSkillGet, CC_SEID_IceBlood);",
     "    if (own & CC_STRIKE_ICE)\n        return guest_call1(ctx, CC_EquipSkillGet, CC_SEID_IceBlood);\n    if (own & CC_STRIKE_NINJA)\n        return guest_call1(ctx, CC_EquipSkillGet, CC_SEID_NinjaReturn);"),
    # the second lookup left out (the record of the first is returned: one guest call fewer)
    (F, "    if (guest_call2(ctx, CC_UnitIsEquipSkill, unit, (uint32_t)(int32_t)number) == 0)\n        return 0;\n    return guest_call1(ctx, CC_EquipSkillGet, label);",
     "    if (guest_call2(ctx, CC_UnitIsEquipSkill, unit, (uint32_t)(int32_t)number) == 0)\n        return 0;\n    return skill;"),
    (F, "    int16_t number = guest_s16(ctx, skill + CC_SKILL_INDEX);\n    if (guest_call2", "    uint16_t number = guest_u16(ctx, skill + CC_SKILL_INDEX);\n    if (guest_call2"),
    # seal_merged_value
    (F, "        return (uint8_t)((uint32_t)value + guest_u8(ctx, at));", "        return (uint8_t)((uint32_t)value + (uint32_t)guest_s8(ctx, at)) & 0x7Fu;"),
    (F, "    return (uint8_t)(old < value ? value : old);", "    return (uint8_t)(old <= value ? old : value);"),
    (F, "    int32_t old = guest_s8(ctx, at);", "    int32_t old = guest_u8(ctx, at);"),
    (F, "    gaddr skill = guest_call1(ctx, CC_EquipSkillGet, CC_SEID_SealChain);", "    gaddr skill = guest_call1(ctx, CC_EquipSkillGet, CC_SEID_SealStr);"),
    (F, "    if (guest_call2(ctx, CC_UnitIsEquipSkill, unit, (uint32_t)(int32_t)number) != 0)\n        return",
     "    if (guest_call2(ctx, CC_UnitIsEquipSkill, capability, (uint32_t)(int32_t)number) != 0)\n        return"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_CC, d, ignore=shutil.ignore_patterns("tests"))
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
        print(f"  planted bug {i:2d} ({old.strip()[:56]!r}): "
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
        print("class_change_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("class_change_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_CC)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"class_change_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    for name, (n, bad) in per.items():
        total_bad += bad
        print(f"  {name:34s} {n:5d} cases  {bad:3d} mismatches")
    for name, k in unsupported.items():
        print(f"  {name:34s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("class_change_diff: what the cases exercised (original's results)")
    for name, cov in COVERAGE.items():
        print(f"  {name:34s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    if PATHS:
        print("class_change_diff: battle_seal_effect answers met: "
              + ", ".join(f"{k} {v}" for k, v in sorted(PATHS.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"class_change_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"class_change_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
