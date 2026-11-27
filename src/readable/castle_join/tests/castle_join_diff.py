#!/usr/bin/env python3
"""Host differential test of the castle-join batch against the game's own ARM code.

    python src/readable/castle_join/tests/castle_join_diff.py             300 cases
    python src/readable/castle_join/tests/castle_join_diff.py -n 1500 --seed 7    the long run
    python src/readable/castle_join/tests/castle_join_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/weapon_rank/tests/weapon_rank_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py).
The batch has one helper and no override: castle_join_offer, the read-only part of
castle::JoinSequence::GetJoinPersonList (docs/CASTLE_JOIN.md). It runs through a test-only entry of
the generated driver (never a marker in src/readable/).

The ARM side runs the WHOLE original function on a made-up state: a list (castle::JoinPersonList_t,
filled with junk), a loaded castle join file with its body and join table (records with Person
labels, three chapter labels and three building words each; all random test values, never game
data, and on purpose often outside what the game uses: a file of 0, a body word of 0, unmapped
files and bodies, a table that runs onto an unmapped page, sometimes a mapped page 0 with a table at
0x20 (so a table taken at body + 0x20 for a body of 0 is caught), counts that are 0, negative or
past six records, building words that are -1, 0x80, 0x1FF or negative, chapter labels of 0). The file load
is answered on the ARM side only: ArchiveFile::ArchiveFile puts the case's file pointer into the
object on the stack and FileBase::Free does nothing; these two calls are not listed, because the
helper starts from the loaded file (its second argument here) and never loads or frees. The
expected result is what the original STORES into the list (its count and that many Persons) and its
return value, folded into one number (FNV-1a) on both sides; the original may write nothing else
outside its stack.

Every other callee is answered by one table on both sides and listed with its argument registers, in
order (docs/DECISIONS.md F-018): UnitPool::GetFromPerson, castle::cut::IsCleared, Castle::Get,
Castle::GetData, castle::BuildingDispos::IsBuilt and Person::Get. UnitPool::GetFromPerson can reach
Person::IsDownload, whose readable override gives up while its cache is cold: on the ARM side its
table answer raises "cold guard" then, so the readable code must give up first (it asks that guard
before anything else). Also compared: the number of bytes read from unmapped memory.

An early give-up (the readable code gives up before reading anything while the original runs to the
end) is accepted only with the download cache cold (then the original met no GetFromPerson call).
Any other early give-up is a mismatch.

--plant copies src/readable/castle_join/ to build/readable/castle_join/plant/, makes one small wrong
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
OUT = os.path.join(ROOT, "build", "readable", "castle_join")
SRC_CJ = os.path.join(ROOT, "src", "readable", "castle_join")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
FROM_PERSON, IS_CLEARED, CASTLE_GET, GET_DATA, IS_BUILT, PERSON_GET = (
    0x004F5E74, 0x00469D34, 0x0044544C, 0x0044545C, 0x00455610, 0x0044A6DC)
LEAF_STUBS = {FROM_PERSON: 2, IS_CLEARED: 1, CASTLE_GET: 0, GET_DATA: 1, IS_BUILT: 4, PERSON_GET: 1}
ARITY = dict(LEAF_STUBS)
ARCHIVE_CTOR, FILE_FREE = 0x00193408, 0x0011CF84  # ARM side only, not listed
JOIN_FILE_NAME = 0x00451F74  # the file name GetJoinPersonList passes (in the code segment; not read here)

OVERRIDES: dict[str, int] = {}
TEST_ENTRIES = {"castle_join_offer": 0x00451DF4}
ADDR = dict(OVERRIDES, **TEST_ENTRIES)

DOWNLOAD_GUARD = 0x006D3B3C  # castle_join.h S_CjDownloadGuard

# guest layout of the made-up state
LIST = 0x08060000             # the caller's JoinPersonList_t (ARM side only): six words, then the count
FILE = 0x08100000             # the loaded file (the word at +0x70 is its body)
BODY = 0x08110000             # its body; the table at +0x20
TORN_BODY = 0x08121000 - 0x24 - 2 * 32  # a body whose table holds two mapped records, then a page gap
CASTLE = 0x08130000           # Castle::Get's answer
DATA = 0x08140000             # Castle::GetData's answer (the dispos word at +4)
DISPOS = (0x08150000, 0x08150100)
LABEL = lambda k: 0x08200000 + k * 0x10  # noqa: E731  Person labels (never read: answered by the table)
CHAPTER = lambda k: 0x08210000 + k * 0x10  # noqa: E731
PERSON = lambda k: 0x08220000 + k * 0x100  # noqa: E731
UNIT = lambda k: 0x08230000 + k * 0x140  # noqa: E731
NLABELS, NCHAPTERS, NRECORDS = 8, 6, 12
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
FORCES = 0x59
RANK = 3
BUILDING_WORDS = [0, 1, 2, 5, 9, 0x10, 0x2E, 0xFFFFFFFF, 0xFFFFFFFF]
BUILDING_RARE = [0x80, 0x1FF, 0xFFFFFF85, 0x7FFFFFFF, 0x80000000, 0x100]


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sx(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def fnv(data: bytes) -> int:
    h = 0x811C9DC5
    for b in data:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def fold(found: int, persons: list[int]) -> int:
    """The result both sides print: FNV-1a of the return value, the count and the listed Persons."""
    return fnv(b"".join(s32(v).to_bytes(4, "little") for v in [found, len(persons)] + persons))


def ostub(st, func: int, *args: int, value: int) -> None:
    st.oracle[(func,) + tuple(s32(a) for a in args[:LEAF_STUBS[func]])] = s32(value)


# ------------------------------------------------------------------ the made-up state
def make_record(st, rec: int) -> None:
    rng = st.rng
    st.fill(rec, 32)
    st.put(rec + 4, 4, LABEL(rng.randrange(NLABELS)) if rng.random() > 0.06 else rng.choice([0] + UNMAPPED))
    if rng.random() < 0.4:  # no chapter condition
        for j in range(3):
            st.put(rec + 8 + 4 * j, 4, 0)
    else:
        for j in range(3):
            st.put(rec + 8 + 4 * j, 4, CHAPTER(rng.randrange(NCHAPTERS)) if rng.random() < 0.6 else
                   pick(rng, [0], UNMAPPED, 0.2))
    if rng.random() < 0.4:  # no building condition
        for j in range(3):
            st.put(rec + 20 + 4 * j, 4, 0xFFFFFFFF)
    else:
        for j in range(3):
            st.put(rec + 20 + 4 * j, 4, pick(rng, BUILDING_WORDS, BUILDING_RARE, 0.2))


def gen_offer(rng):
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    st.zero(0x006D3800, 0x400)
    st.put(DOWNLOAD_GUARD, 4, rng.choice([1, 0x101, 0xFFFFFFFF]) if rng.random() > 0.06 else rng.choice([0, 0x100]))
    st.fill(LIST, 28)
    # the file, its body and the join table
    st.fill(FILE, 0x80)
    r = rng.random()
    body = BODY if r < 0.75 else TORN_BODY if r < 0.85 else rng.choice([0] + UNMAPPED)
    st.put(FILE + 0x70, 4, body)
    if body in (BODY, TORN_BODY):
        st.fill(body, 0x20)
        if body == TORN_BODY:
            count, mapped = rng.choice([2, 3, 4]), 2
        else:
            count = pick(rng, [0, 1, 2, 3, 4, 5, 6, 7, 8, 10], [0xFFFFFFFF, 0x80000000, NRECORDS], 0.1)
            mapped = NRECORDS
        st.put(body + 0x20, 4, count)
        for i in range(mapped):
            make_record(st, body + 0x24 + 32 * i)
    file = FILE if rng.random() > 0.12 else rng.choice([0, 0, 0] + UNMAPPED)
    if (body == 0 or file == 0) and rng.random() < 0.5:
        # page 0 mapped (never in the game): the original reads the count at address 0 (0 here), so a
        # table taken at 0x20 instead would run the records below it
        st.zero(0, 0x24)
        st.put(0x20, 4, rng.choice([1, 2, 3]))
        for i in range(3):
            make_record(st, 0x24 + 32 * i)
    # the table answers
    st.zero(DATA, 8)
    st.put(DATA + 4, 4, rng.choice(DISPOS) if rng.random() > 0.05 else rng.choice([0] + UNMAPPED))
    ostub(st, CASTLE_GET, value=CASTLE)
    ostub(st, GET_DATA, CASTLE, value=DATA if rng.random() > 0.05 else rng.choice(UNMAPPED))
    p_army = rng.choice([0.0, 0.2, 0.5])
    for lab in [0] + UNMAPPED + [LABEL(k) for k in range(NLABELS)]:
        ostub(st, FROM_PERSON, lab, FORCES, value=UNIT(rng.randrange(4)) if rng.random() < p_army else 0)
        ostub(st, PERSON_GET, lab, value=PERSON(rng.randrange(8)) if rng.random() > 0.1 else 0)
    p_clear = rng.choice([0.2, 0.5, 0.8])
    for ch in UNMAPPED + [CHAPTER(k) for k in range(NCHAPTERS)]:
        ostub(st, IS_CLEARED, ch, value=1 if rng.random() < p_clear else 0)
    p_built = rng.choice([0.2, 0.5, 0.8])
    for d in set(DISPOS) | {0} | set(UNMAPPED):
        for w in set(BUILDING_WORDS + BUILDING_RARE):
            ostub(st, IS_BUILT, d, sx(w & 0xFF, 8), RANK, 0, value=1 if rng.random() < p_built else 0)
    a = TEST_ENTRIES["castle_join_offer"]
    return st, f"ov:0x{a:08X}", [LIST, file, 0, 0], ("call", a, file)


def early_ok(name: str, st, args: list[int]) -> bool:
    """Whether the readable code may give up before reading anything while the original runs to the end:
    only with the download cache cold (then the original met no GetFromPerson call)."""
    return not st.mem.get(DOWNLOAD_GUARD, 0) & 1


FUNCS = {"castle_join_offer": gen_offer}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY with its argument registers (this
    function has no tail branch)."""

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
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]; r0 is
    the fold of what the original returned and stored into the list."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)

    def answer(f, n):
        return lambda cpu, a: st.oracle.get((f,) + tuple(x & 0xFFFFFFFF for x in a[:n]), 0)
    stubs = {f: answer(f, n) for f, n in LEAF_STUBS.items()}

    def from_person(cpu, a):  # the game's code may reach IsDownload's guard inside
        if not cpu.mem.read(DOWNLOAD_GUARD, 4) & 1:
            raise A.ColdGuard()
        return answer(FROM_PERSON, 2)(cpu, a)
    stubs[FROM_PERSON] = from_person
    opened: list[int] = []

    def ctor(cpu, a):  # ArchiveFile::ArchiveFile(const char*): the object on the stack gets the case's file
        if a[1] != JOIN_FILE_NAME:
            raise A.Unsupported(f"ArchiveFile opened with {a[1]:#x}")
        cpu.mem.write(a[0] + 4, 4, how[2])
        opened.append(a[0])
        return a[0]

    def free(cpu, a):
        if [a[0]] != opened:
            raise A.Unsupported("FileBase::Free on another object")
        return 0
    stubs[ARCHIVE_CTOR] = ctor
    stubs[FILE_FREE] = free
    cpu = ListingCpu(mem, stubs, guard=GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    try:
        cpu.run(how[1])
    except A.ColdGuard:
        return [1]
    if not opened:
        raise A.Unsupported("the file was never opened")
    stray = [w for w in mem.writes if not (SP - 0x400 <= w[0] < SP or LIST <= w[0] < LIST + 28)]
    if stray:
        raise A.Unsupported(f"the original wrote guest memory outside its stack and list: {stray[:3]}")
    count = mem.read(LIST + 24, 4)
    if count > 6:
        raise A.Unsupported(f"list count {count}")
    persons = [mem.read(LIST + 4 * i, 4) for i in range(count)]
    return [0, fold(cpu.r[0], persons), mem.faults, calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER_HEAD = r'''
/* Generated by src/readable/castle_join/tests/castle_join_diff.py: runs the castle-join batch on
   memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "castle_join.h"
'''

TEST_ENTRY_CODE = r'''
/* test-only entry (never in src/readable/: this address has a helper row, no override). The list
   pointer (argument 0) is the original's; the helper takes the loaded file (argument 1). */
static uint32_t t_offer(Context *ctx, gaddr file) {
    CastleJoinOffer out;
    memset(&out, 0xA5, sizeof out);
    uint32_t found = (uint32_t)castle_join_offer(ctx, file, &out);
    uint32_t words[2 + CJ_LIST_MAX];
    int n = 0;
    words[n++] = found;
    words[n++] = (uint32_t)out.count;
    for (int i = 0; i < out.count && i < CJ_LIST_MAX; i++) words[n++] = out.person[i];
    uint32_t h = 0x811C9DC5u;
    for (int i = 0; i < n; i++)
        for (int b = 0; b < 4; b++) h = (h ^ ((words[i] >> (8 * b)) & 0xFFu)) * 0x01000193u;
    return h;
}
void test_0x00451DF4(Context *ctx) { FE_ENTRY(0x00451DF4, t_offer, FE_ARG(1)); }
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


def build_driver(cc: str, out: str, cj_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, this folder's taken from cj_dir (a planted
    bug may leave a parameter unused: not strict then). Each source is compiled on its own, in
    parallel; the other areas' objects once per run, reused for every planted bug."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "castle_join_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_CJ)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(cj_dir, f) for f in sorted(os.listdir(cj_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "castle_join_driver.exe" if os.name == "nt" else "castle_join_driver")
    inc = ["-I", cj_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
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
        raise SystemExit("castle_join_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"castle_join_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    keys = []
    if exp[0] == 1:
        keys.append("gave up (cold)")
    else:
        file = s32(args[1])
        body = word(st, file + 0x70) if file == FILE else None
        if body == TORN_BODY:
            keys.append("table onto an unmapped page")
        elif body != BODY:
            keys.append("no table (file or body 0 or unmapped)")
        calls = exp[3].split(",") if exp[3] != "-" else []
        taken = sum(c.startswith(f"{PERSON_GET:x}:") for c in calls)
        keys.append("0 taken" if taken == 0 else "1-6 taken" if taken <= 6 else "more than 6 taken (list full)")
        if any(c.startswith(f"{IS_CLEARED:x}:") for c in calls):
            keys.append("chapter asked")
        if any(c.startswith(f"{IS_BUILT:x}:") for c in calls):
            keys.append("building asked")
        if exp[2]:
            keys.append("unmapped reads")
        if st.mem.get(0x20) is not None:
            keys.append("page 0 mapped")
    for key in keys:
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
        raise SystemExit(f"castle_join_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
# planted bugs: (file, exact text, replacement); each text occurs once in its file
F = "castle_join.c"
PLANTS = [
    # the download cache not asked first: GetFromPerson's IsDownload would give up nested
    (F, "    if (!fe_static_ready(ctx, S_CjDownloadGuard))\n        return (int32_t)fe_use_original(ctx);\n", ""),
    # a file of 0 read through anyway (an unmapped read more)
    (F, "    if (file != 0) {\n", "    {\n"),
    (F, "        if (body != 0)\n            table = body + CJ_BODY_TABLE;\n",
     "        table = body + CJ_BODY_TABLE;\n"),
    # the count compared unsigned (negative counts run)
    (F, "    for (int32_t i = 0; i < guest_s32(ctx, table); i++) {",
     "    for (uint32_t i = 0; i < guest_u32(ctx, table) && i < 64u; i++) {"),
    # the count read once (fewer unmapped reads on a torn table: same count, so this one is subtle)
    (F, "        gaddr record = table + CJ_TABLE_RECORDS + (gaddr)i * CJ_RECORD_SIZE;",
     "        gaddr record = table + (gaddr)i * CJ_RECORD_SIZE;"),
    # units already in the army not skipped
    (F, "            continue; /* already in the army */\n", "            (void)0; /* already in the army */\n"),
    # the force mask
    (F, "guest_u32(ctx, record + CJ_REC_PERSON), CJ_JOIN_FORCES) != 0)",
     "guest_u32(ctx, record + CJ_REC_PERSON), 0xFFu) != 0)"),
    # the conditions in the other order (call order differs)
    (F, "        if (!join_chapter_met(ctx, record) || !join_building_met(ctx, record))",
     "        if (!join_building_met(ctx, record) || !join_chapter_met(ctx, record))"),
    # both conditions needed in full instead of "any of three"
    (F, "        if (guest_call1(ctx, CJ_CutIsCleared, guest_u32(ctx, chapter + 4u * (gaddr)i)) != 0)\n            return 1;\n    return 0;",
     "        if (guest_call1(ctx, CJ_CutIsCleared, guest_u32(ctx, chapter + 4u * (gaddr)i)) == 0)\n            return 0;\n    return 1;"),
    # zero chapter labels skipped (IsCleared(0) not asked: one call less)
    (F, "        if (guest_call1(ctx, CJ_CutIsCleared, guest_u32(ctx, chapter + 4u * (gaddr)i)) != 0)",
     "        if (guest_u32(ctx, chapter + 4u * (gaddr)i) != 0 &&\n            guest_call1(ctx, CJ_CutIsCleared, guest_u32(ctx, chapter + 4u * (gaddr)i)) != 0)"),
    # only the first chapter label tested for "none"
    (F, "    if (guest_u32(ctx, chapter) == 0 && guest_u32(ctx, chapter + 4u) == 0 && guest_u32(ctx, chapter + 8u) == 0)",
     "    if (guest_u32(ctx, chapter) == 0)"),
    # only the first building word tested for "none"
    (F, "    if (guest_s32(ctx, building) == CJ_NO_BUILDING && guest_s32(ctx, building + 4u) == CJ_NO_BUILDING &&\n        guest_s32(ctx, building + 8u) == CJ_NO_BUILDING)",
     "    if (guest_s32(ctx, building) == CJ_NO_BUILDING)"),
    # Castle::Get / GetData asked once for the three types
    (F, "        gaddr castle = guest_call(ctx, CJ_CastleGet, 0u, 0u, 0u, 0u);\n        gaddr data = guest_call1(ctx, CJ_CastleGetData, castle);\n",
     "        gaddr castle = i ? 0x08130000u : guest_call(ctx, CJ_CastleGet, 0u, 0u, 0u, 0u);\n        gaddr data = i ? 0x08140000u : guest_call1(ctx, CJ_CastleGetData, castle);\n"),
    # the building type passed whole, not its low byte sign-extended
    (F, "(uint32_t)(int32_t)(int8_t)(uint8_t)guest_u32(ctx, building + 4u * (gaddr)i)",
     "guest_u32(ctx, building + 4u * (gaddr)i)"),
    # zero-extended instead of sign-extended
    (F, "(uint32_t)(int32_t)(int8_t)(uint8_t)guest_u32(ctx, building + 4u * (gaddr)i)",
     "(uint32_t)(uint8_t)guest_u32(ctx, building + 4u * (gaddr)i)"),
    # the rank
    (F, "dispos, type, (uint32_t)CJ_BUILDING_RANK, 0u)", "dispos, type, 2u, 0u)"),
    # the dispos word at the wrong offset
    (F, "        gaddr dispos = guest_ptr(ctx, data + CJ_DATA_DISPOS);", "        gaddr dispos = guest_ptr(ctx, data);"),
    # the Person read directly from the label instead of Person::Get
    (F, "        gaddr person = guest_call1(ctx, CJ_PersonGet, guest_u32(ctx, record + CJ_REC_PERSON));",
     "        gaddr person = guest_u32(ctx, record + CJ_REC_PERSON);"),
    # the list cap
    (F, "        if (out->count != CJ_LIST_MAX)\n", "        if (out->count != CJ_LIST_MAX - 1)\n"),
    # the count returned instead of 1 ("found only while the list has room" would be an equivalent
    # mutant: the list is full only after six Persons were taken, so found is already 1)
    (F, "        found = 1;\n", "        found = out->count;\n"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_CJ, d, ignore=shutil.ignore_patterns("tests"))
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
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, help="cases per function for each planted bug (default: -n)")
    a = ap.parse_args(argv)
    if a.only and a.only not in FUNCS:
        print(f"unknown function {a.only}; one of: {', '.join(FUNCS)}")
        return 2
    if not os.path.isfile(TEXT):
        print("castle_join_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("castle_join_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_CJ)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"castle_join_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, early) in per.items():
        total_bad += bad
        notes = ([f"{cold_n} cold: both reached / gave up at the cache"] if cold_n else []) + \
                ([f"{early} early give-ups"] if early else [])
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("castle_join_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("castle_join_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"castle_join_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"castle_join_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
