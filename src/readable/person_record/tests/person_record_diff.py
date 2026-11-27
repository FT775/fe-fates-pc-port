#!/usr/bin/env python3
"""Host differential test of the person_record batch against the game's own ARM code.

    python src/readable/person_record/tests/person_record_diff.py            300 cases of each function
    python src/readable/person_record/tests/person_record_diff.py -n 1500 --seed 7   the long run (3,000 cases)
    python src/readable/person_record/tests/person_record_diff.py --plant    also plant bugs: each must be caught

Two functions, two kinds of made-up guest state (all random test values, never game data):

- person_record_by_name, the override of Person::Get(const char*) (0x0044A6DC): the state and checks of
  src/readable/skill_record/tests/skill_record_diff.py (the same IdentHash::GetSurely lookup): the ID
  label hash table that G_IdentHash 0x006DCB44 points at, filled from made-up labels hashed the game's
  way, and on purpose often outside what the game uses (null, unmapped, empty and unterminated labels,
  bytes of 0x80 and above, decoy keys, duplicate keys, junk and unmapped bucket words, a null or
  unmapped table, 0 buckets, bucket counts up to 0xFFFFFFFF). The original runs with its tail branch
  into IdentHash::GetSurely and the runtime's division 0x0012A0E4 (and its division-by-zero path).
- person_record_get, the helper of Person::Get(unsigned short) (0x0044A6F8, called directly by the
  driver: it has no override marker, docs/PERSON_RECORD.md section 2): the state and checks of
  src/readable/job_record/tests/job_record_diff.py with the person block's offsets (the list of loaded
  person blocks at G_PersonBlocks 0x006D3B28; header +0x4 count, +0x34 first number, records at +0x10,
  0x98 bytes each): empty lists, unmapped nodes and blocks, overlapping and empty blocks, a block placed
  so the record address wraps to 0, numbers negative or wider than 16 bits.

The ORIGINAL ARM code runs from the owner's extracted/text.bin in arm_mini.py and the readable C (built
with the host gcc against tools/readable/stub/) on the same memory; compared are r0, the number of bytes
read from unmapped memory AND the list of guest calls (none is expected; docs/DECISIONS.md F-018).
Neither body has a cache or calls a guest function, so neither may give up.

A made-up pointer can land a data read inside the game's code (arm_mini maps extracted/text.bin, the C
driver's memory does not): that is a test artifact, not a difference of the function, so such a case is
drawn again, and the count is printed ("drawn again"). A read within 4 KB of the instruction making it
(a literal pool) is not counted.

--plant copies src/readable/person_record/ to build/readable/person_record/plant/, makes one small wrong
change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one
mismatch. Changes that cannot change any answer are listed in docs/PERSON_RECORD.md and not planted.

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
OUT = os.path.join(ROOT, "build", "readable", "person_record")
SRC_DIR = os.path.join(ROOT, "src", "readable", "person_record")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json (never reached here)
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
PERSON_BY_NAME = 0x0044A6DC
LEAF_STUBS: dict[int, int] = {}  # the body calls no guest function (the division runs in arm_mini)
ARITY = dict(LEAF_STUBS)

PERSON_GET = 0x0044A6F8  # a helper: called directly by the driver (driver_text)
OVERRIDES = {"person_record_by_name": PERSON_BY_NAME}
HELPERS = {"person_record_get": PERSON_GET}
ADDR = dict(OVERRIDES, **HELPERS)

# include/readable/generated/fe_globals.h
G_IDENT_HASH = 0x006DCB44
PERSON_LIST = 0x006D3B28  # G_PersonBlocks

# guest layout of the made-up state
HASH = 0x08010000
BUCKETS = 0x08100000
ENTRY = lambda k: 0x08200000 + k * 0x20  # noqa: E731
LABEL = lambda k: 0x08300000 + k * 0x80  # noqa: E731
PAGE_END_LABEL = 0x08401000            # a label written up to the end of the page before this one
UNMAPPED = [0x40, 0x7FF0, 0x0FFF0000]
MAPPED_BUCKETS = 0x400                 # bucket words mapped at most (a larger count reads past them)
NODE = lambda k: 0x08020000 + k * 0x40  # noqa: E731
BLOCK = lambda k: 0x08040000 + k * 0x1000  # noqa: E731
NBLK = 5
LOW_NODE = 0x080F0FF0           # a node at the end of a page (the next page is unmapped)
LOW_BLOCK = 0x0000C000          # a block low in memory
WRAP_BLOCK = 0xFFFFFF58         # block + 0x10 + 1 * 0x98 = 0 (mod 2^32)
WRAP_FIRST = 0x10


def hashes(label: bytes) -> tuple[int, int]:
    """IdentHash's two hashes of a label (signed bytes, 32-bit wrap): (bucket hash, key hash)."""
    h = k = 0
    for b in label:
        c = b - 256 if b >= 0x80 else b
        h = (h * 37 + c) & 0xFFFFFFFF
        k = (k * 31 + c) & 0xFFFFFFFF
    return h, k


def u16(st, addr: int) -> int:
    return int.from_bytes(bytes(st.mem.get((addr + i) & 0xFFFFFFFF, 0) for i in range(2)), "little")


def u32(st, addr: int) -> int:
    return int.from_bytes(bytes(st.mem.get((addr + i) & 0xFFFFFFFF, 0) for i in range(4)), "little")


ALPHA = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"


def make_label(rng) -> bytes:
    r = rng.random()
    if r < 0.06:
        return b""
    if r < 0.12:
        return bytes([rng.choice(ALPHA)])
    body = bytes(rng.choice(ALPHA) for _ in range(rng.randrange(2, 24)))
    if rng.random() < 0.25:  # bytes of 0x80 and above (a UTF-8 label): signed in the hash
        body += bytes(rng.randrange(0x80, 0x100) for _ in range(rng.randrange(1, 7)))
    return (b"PID_" if rng.random() < 0.7 else b"") + body


def put_label(st, addr: int, label: bytes) -> None:
    st.fill(addr, 0x80)  # junk after the end byte: reading past it is seen
    for i, b in enumerate(label):
        st.mem[addr + i] = b
    st.mem[addr + len(label)] = 0


# ------------------------------------------------------------------ the made-up state
def gen_by_name(rng):
    """Person::Get(const char*): the ID label hash table (the EquipSkill::Get(const char*) test's shape)."""
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    st.fill(0x006DCB00, 0x80)   # the statics around the table word hold junk
    count = pick(rng, [rng.randrange(1, 9), rng.randrange(1, 64), rng.randrange(1, 300)],
                 [0, 1, 0xFFFFFFFF, 0x80000000, 0x10000, rng.getrandbits(32)], 0.12)
    st.fill(HASH, 0x20)
    st.put(HASH + 4, 4, count)
    st.put(HASH + 0x10, 4, BUCKETS)
    nb = min(count, MAPPED_BUCKETS)
    words = [0] * nb
    for i in range(nb):  # empty buckets: 0, sometimes a junk or unmapped word
        r = rng.random()
        words[i] = 0 if r < 0.9 else (rng.choice(UNMAPPED) if r < 0.95 else rng.getrandbits(32) | 3)
    labels = [make_label(rng) for _ in range(rng.randrange(1, 12))]
    held = [i for i in range(len(labels)) if rng.random() < 0.85]
    chains: dict[int, list[tuple[int, int]]] = {}
    for i in held:
        h, k = hashes(labels[i])
        # 0 buckets: the runtime's division-by-zero path hands back the dividend as the remainder
        chain = chains.setdefault(h % count if count else h, [])
        chain.append((k, rng.getrandbits(32)))
        if rng.random() < 0.25:  # a decoy in front: the same bucket, the key differs only in its upper half
            chain.insert(rng.randrange(len(chain)), (k ^ (rng.randrange(1, 0x10000) << 16), rng.getrandbits(32)))
        if rng.random() < 0.15:  # a decoy in front differing only in its lower half
            chain.insert(0, (k ^ rng.randrange(1, 0x10000), rng.getrandbits(32)))
        if rng.random() < 0.1:   # a second entry with the same key behind it: the first one answers
            chain.append((k, rng.getrandbits(32)))
    e = 0
    for b, chain in chains.items():
        nxt = rng.choice(UNMAPPED) if rng.random() < 0.04 else 0  # sometimes an unmapped last link
        for key, val in reversed(chain):
            st.fill(ENTRY(e), 0x20)
            st.put(ENTRY(e), 4, nxt)
            st.put(ENTRY(e) + 4, 4, key)
            st.put(ENTRY(e) + 0xC, 4, val)
            nxt = ENTRY(e)
            e += 1
        if b < nb:
            words[b] = nxt
        else:  # a bucket past the mapped words: map that one word
            st.put((BUCKETS + 4 * b) & 0xFFFFFFFF, 4, nxt)
    for i, w in enumerate(words):
        st.put(BUCKETS + 4 * i, 4, w)
    for i, lab in enumerate(labels):
        put_label(st, LABEL(i), lab)
    tail = bytes(rng.choice(ALPHA) for _ in range(rng.randrange(1, 9)))  # a label with no end byte
    for i, b in enumerate(tail):
        st.mem[PAGE_END_LABEL - len(tail) + i] = b
    # the table pointer: mostly the table, sometimes null or unmapped
    r = rng.random()
    st.put(G_IDENT_HASH, 4, HASH if r < 0.93 else (0 if r < 0.96 else rng.choice(UNMAPPED)))
    # the label asked
    r = rng.random()
    if r < 0.62 and held:
        name = LABEL(rng.choice(held))
    elif r < 0.75:
        name = LABEL(rng.randrange(len(labels)))  # held or not
    elif r < 0.81:
        name = 0
    elif r < 0.86:
        name = rng.choice(UNMAPPED)
    elif r < 0.92:
        name = PAGE_END_LABEL - len(tail)
    else:
        name = LABEL(rng.randrange(len(labels))) + rng.randrange(1, 4)  # inside a label (or its junk)
    return st, f"ov:0x{PERSON_BY_NAME:08X}", [name, rng.getrandbits(32), rng.getrandbits(32), rng.getrandbits(32)], \
        ("call", PERSON_BY_NAME, None)


def put_block(st, addr: int, first: int, count: int) -> None:
    st.fill(addr, min(0x40, 0x100000000 - addr))  # the wrap block ends at the top of the address space
    st.put(addr + 0x04, 2, count)
    st.put(addr + 0x34, 2, first)


def gen_get(rng):
    """Person::Get(unsigned short): the list of loaded person blocks (the Job::Get test's shape)."""
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    st.fill(0x006D3B00, 0x60)   # Person's other statics around the list word hold junk
    ranges = []
    # the blocks: the main one usually starts at 0, added ones after it (sometimes overlapping,
    # empty, or at the u16 limits)
    first = 0
    for k in range(NBLK):
        f = first if rng.random() < 0.7 else pick(rng, [0, rng.randrange(400)], [0xFFFF, 0xFF00, 0x8000], 0.15)
        c = pick(rng, [rng.randrange(1, 160)], [0, 1, 0xFFFF, rng.randrange(0x10000)], 0.12)
        put_block(st, BLOCK(k), f, c)
        ranges.append((f, c))
        first = (f + c) & 0xFFFF
    put_block(st, LOW_BLOCK, pick(rng, [0, 5]), pick(rng, [10, 200]))
    put_block(st, WRAP_BLOCK, WRAP_FIRST, 4)
    # the nodes, linked in order (no cycle: the game would not end either)
    nb = pick(rng, [1, 2, 3], [4, 5], 0.2)
    order = rng.sample(range(NBLK), nb)
    nodes = [NODE(k) for k in range(nb)]
    for i, k in enumerate(order):
        st.fill(nodes[i], 0x10)
        blk = BLOCK(k)
        r = rng.random()
        if r < 0.04:
            blk = rng.choice(UNMAPPED)
        elif r < 0.09:
            blk = WRAP_BLOCK
        st.put(nodes[i], 4, blk)
        nxt = nodes[i + 1] if i + 1 < nb else 0
        if nxt == 0 and rng.random() < 0.05:
            nxt = rng.choice(UNMAPPED[1:])  # an unmapped last link
        st.put(nodes[i] + 8, 4, nxt)
    r = rng.random()
    if r < 0.05:
        head = 0
    elif r < 0.08:
        head = rng.choice(UNMAPPED[1:])
    elif r < 0.11:
        head = LOW_NODE  # a node whose block sits low in memory, linked to the others
        st.fill(LOW_NODE, 0x10)
        st.put(LOW_NODE, 4, LOW_BLOCK)
        st.put(LOW_NODE + 8, 4, nodes[0])
    else:
        head = nodes[0]
    wrap = rng.random() < 0.06
    if wrap:  # a listed block placed so that the record of person WRAP_FIRST + 1 is at address 0
        st.put(nodes[rng.randrange(nb)], 4, WRAP_BLOCK)
    st.put(PERSON_LIST, 4, head)
    # the person number: mostly inside some block, sometimes just outside, sometimes wide
    r = rng.random()
    if wrap and r < 0.7:
        n = WRAP_FIRST + 1
    elif r < 0.55:
        f, c = rng.choice(ranges)
        n = f + rng.randrange(max(c, 1))
    elif r < 0.75:
        f, c = rng.choice(ranges)
        n = rng.choice([f - 1, f + c, f + c - 1, f])
    elif r < 0.83:
        n = rng.randrange(0x10000)
    elif r < 0.88:
        n = rng.randrange(0, 210)  # the low block's range
    elif r < 0.94:
        n = WRAP_FIRST + 1 if rng.random() < 0.6 else rng.choice([WRAP_FIRST, WRAP_FIRST + 3, WRAP_FIRST + 4])
    else:
        n = rng.choice([-1, -0x8000, 0x10000, 0x7FFFFFFF, 0x80000000, rng.getrandbits(32)])
    n &= 0xFFFFFFFF
    if rng.random() < 0.04:
        n |= rng.getrandbits(16) << 16  # junk above the 16 bits in the register
    return st, f"ov:0x{PERSON_GET:08X}", [n, rng.getrandbits(32), rng.getrandbits(32), rng.getrandbits(32)], \
        ("call", PERSON_GET, None)


FUNCS = {"person_record_by_name": gen_by_name, "person_record_get": gen_get}


# ------------------------------------------------------------------ the ARM side
class CodeAsData(Exception):
    """The made-up state sent a data read into the game's code (extracted/text.bin, mapped in arm_mini
    but not in the C driver's memory): a test artifact, not a difference of the function. The case is
    drawn again (counted and printed)."""


class TextWatchMemory(A.Memory):
    """arm_mini's Memory, noting data reads that land in the code more than 4 KB away from the
    instruction making them (a literal pool is always within 4 KB of its load)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.pc: int | None = None   # the instruction being executed (None while fetching)
        self.code_reads = 0

    def read8(self, a: int) -> int:
        a &= 0xFFFFFFFF
        if self.pc is not None and (a >> 12) not in self.pages and 0 <= a - self.text_base < len(self.text)                 and abs(a - self.pc) > 0x1000:
            self.code_reads += 1
        return super().read8(a)


class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY with its argument registers."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def step(self, ins: int, pc: int) -> None:
        self.mem.pc = pc
        try:
            super().step(ins, pc)
        finally:
            self.mem.pc = None

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
    mem = TextWatchMemory(text)
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
    if mem.code_reads:
        raise CodeAsData(f"{mem.code_reads} data bytes read from the game's code")
    return [0, cpu.r[0], mem.faults, calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER_HEAD = r'''
/* Generated by src/readable/person_record/tests/person_record_diff.py: runs the
   person_record batch on memory images read from stdin and prints its results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "person_record.h"
'''


def driver_text() -> str:
    import sheet_diff as S  # the same driver body: page memory, call list, oracle, nested give-ups
    body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
    decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in sorted(OVERRIDES.values()))
    # person_record_get is a helper (no override marker, docs/PERSON_RECORD.md section 2): the driver calls
    # it directly, with the game's argument register, and puts its answer in r0
    decls += "static void call_person_record_get(Context *ctx) { ctx->r[0] = person_record_get(ctx, ctx->r[0]); }\n"
    rows = sorted([(a, f"override_0x{a:08X}") for a in OVERRIDES.values()]
                  + [(a, f"call_{n}") for n, a in HELPERS.items()])
    table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
        f"    {{0x{a:08X}u, {fn}}},\n" for a, fn in rows) + "};\n"
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
    src = os.path.join(out, "person_record_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_DIR)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(my_dir, f) for f in sorted(os.listdir(my_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "person_record_driver.exe" if os.name == "nt" else "person_record_driver")
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
        raise SystemExit("person_record_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"person_record_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


REDRAWN: dict[str, int] = {}  # cases drawn again: the made-up state read the game's code as data
PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    """Which way the original answered. By name: a null label, an entry found or no entry found, and
    whether the table had 0 buckets (the remainder is the bucket hash itself). By number: a record of
    the k-th node's block, the fallback, or the wrap-to-0 fallback (worked out as the game walks)."""
    p = PATHS.setdefault(name, {})
    if name == "person_record_get":
        n = args[0] - (1 << 32) if args[0] >> 31 else args[0]
        head = u32(st, PERSON_LIST)
        key = "empty list -> fallback" if head == 0 else "no block holds it -> fallback"
        node, k = head, 0
        while head and node and k < 16:
            blk = u32(st, node)
            f = u16(st, blk + 0x34)
            if f <= n < f + u16(st, blk + 4):
                rec = (blk + 0x10 + (n - f) * 0x98) & 0xFFFFFFFF
                key = f"record of node {k}" if rec else "record wraps to 0 -> fallback"
                break
            node, k = u32(st, node + 8), k + 1
        if exp[2]:
            key += ", unmapped reads"
    elif exp[0] == 1:
        key = "gave up"
    elif args[0] == 0:
        key = "null label -> 0"
    else:
        key = ("entry found" if exp[1] else "no entry -> 0") + (", unmapped reads" if exp[2] else "")
        if u32(st, G_IDENT_HASH) == HASH and u32(st, HASH + 4) == 0:
            key += " (0 buckets)"
        elif u32(st, G_IDENT_HASH) != HASH:
            key += " (null or unmapped table: 0 buckets)"
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
            while True:
                st, kind, args, how = gen(rng)
                try:
                    exp = arm_run(text, st, kind, args, how)
                except CodeAsData as e:
                    REDRAWN[name] = REDRAWN.get(name, 0) + 1
                    if REDRAWN[name] == 1:
                        print(f"  {name}: a made-up state read the game's code as data ({e}); drawn again")
                    continue
                except A.Unsupported as e:
                    exp = None
                    unsupported[name] = unsupported.get(name, 0) + 1
                    if unsupported[name] == 1:
                        print(f"  ARM interpreter: {name}: {e}")
                break
            if exp is None:
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
        raise SystemExit(f"person_record_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
            exp = [1, 0]  # never expected here: the original has no cache and calls no guest function
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file.
# Every one can change an answer (r0, unmapped reads or the call list) before capture (F-027).
F = "person_record.c"
H = "person_record.h"
G = F
FOUND = "            return guest_u32(ctx, entry + PR_ENTRY_VALUE);"
PLANTS = [
    # the wrong table word
    (F, "guest_u32(ctx, G_IdentHash), name)", "guest_u32(ctx, G_IdentHash + 4u), name)"),
    # the wrong offsets: count, bucket array, next link, key, value
    (H, "#define PR_HASH_COUNT 0x04u", "#define PR_HASH_COUNT 0x08u"),
    (H, "#define PR_HASH_BUCKETS 0x10u", "#define PR_HASH_BUCKETS 0x0Cu"),
    (H, "#define PR_ENTRY_NEXT 0x0u", "#define PR_ENTRY_NEXT 0x8u"),
    (H, "#define PR_ENTRY_KEY 0x4u", "#define PR_ENTRY_KEY 0x8u"),
    (H, "#define PR_ENTRY_VALUE 0xCu", "#define PR_ENTRY_VALUE 0x8u"),
    # the hash multipliers swapped one at a time
    (H, "#define PR_BUCKET_MUL 37u", "#define PR_BUCKET_MUL 31u"),
    (H, "#define PR_KEY_MUL 31u", "#define PR_KEY_MUL 37u"),
    # the label's bytes taken as unsigned (the game sign-extends each byte)
    (F, "uint32_t c = (uint32_t)(int32_t)guest_s8(ctx, p);", "uint32_t c = guest_u8(ctx, p);"),
    # the null label not asked first (the game answers 0 before reading anything else)
    (F, "    if (name == 0)\n        return 0;\n", ""),
    # the empty label not asked first: the end byte hashed and the byte after it read
    (F, "    if (first != 0) {", "    if (1) {"),
    # the bucket picked with the key hash, or with a signed division
    (F, "bucket_hash % count :", "key % count :"),
    (F, "bucket_hash % count :", "(uint32_t)((int32_t)bucket_hash % (int32_t)count) :"),
    # the wrong bucket word size
    (F, "+ (bucket << 2));", "+ (bucket << 3));"),
    # only the first entry of a chain asked
    (F, "        entry = guest_u32(ctx, entry + PR_ENTRY_NEXT);", "        entry = 0;"),
    # the key compared on 16 bits only
    (F, "if (guest_u32(ctx, entry + PR_ENTRY_KEY) == key)",
     "if (guest_u16(ctx, entry + PR_ENTRY_KEY) == (key & 0xFFFFu))"),
    # the last matching entry answered instead of the first
    (F, "    while (entry != 0) {\n        if (guest_u32(ctx, entry + PR_ENTRY_KEY) == key)\n" + FOUND
     + "\n        entry = guest_u32(ctx, entry + PR_ENTRY_NEXT);\n    }\n    return 0;",
     "    gaddr found = 0;\n    while (entry != 0) {\n        if (guest_u32(ctx, entry + PR_ENTRY_KEY) == key)\n"
     "            found = guest_u32(ctx, entry + PR_ENTRY_VALUE);\n"
     "        entry = guest_u32(ctx, entry + PR_ENTRY_NEXT);\n    }\n    return found;"),
    # the entry's address answered instead of its value
    (F, FOUND, "            return entry + PR_ENTRY_VALUE;"),
    # 0 buckets: the remainder taken as 0, or the lookup answering 0 (the runtime's division-by-zero
    # path hands back the dividend)
    (F, "count != 0 ? bucket_hash % count : bucket_hash;", "count != 0 ? bucket_hash % count : 0u;"),
    (F, "    uint32_t bucket = count != 0 ? bucket_hash % count : bucket_hash;\n",
     "    if (count == 0)\n        return 0;\n    uint32_t bucket = bucket_hash % count;\n"),
    # ---- Person::Get(unsigned short), the helper (the Job::Get test's plants)
    # the wrong list word
    (G, "guest_u32(ctx, G_PersonBlocks);", "guest_u32(ctx, G_PersonBlocks + 4u);"),
    # the empty list not asked first: the walk would read from address 0
    (F, "    if (head != 0) {", "    if (1) {"),
    # the range tests: off by one at either end, or the lower one unsigned (the upper one is reached
    # only with 0 <= first <= n, so unsigned there cannot change an answer: docs/JOB_RECORD.md)
    (F, "            if (n >= first) {", "            if (n > first) {"),
    (F, "                if (end > n) {", "                if (end >= n) {"),
    (F, "            if (n >= first) {", "            if ((uint32_t)n >= (uint32_t)first) {"),
    # the count ignored (only the first number asked)
    (F, "int32_t end = first + guest_u16(ctx, block + PR_BLOCK_COUNT);", "int32_t end = first + 0x10000;"),
    # the person number taken as 16 bits (the game compares the whole register)
    (F, "    int32_t n = (int32_t)number;", "    int32_t n = (int32_t)(uint16_t)number;"),
    # the wrong offsets: count, first number, next link, records, record size
    (H, "#define PR_BLOCK_COUNT 0x04u", "#define PR_BLOCK_COUNT 0x06u"),
    (H, "#define PR_BLOCK_FIRST 0x34u", "#define PR_BLOCK_FIRST 0x24u"),
    (H, "#define PR_NODE_NEXT 0x8u", "#define PR_NODE_NEXT 0x4u"),
    (H, "#define PR_BLOCK_RECORDS 0x10u", "#define PR_BLOCK_RECORDS 0x08u"),
    (H, "#define PR_RECORD_SIZE 0x98u", "#define PR_RECORD_SIZE 0x90u"),
    # the index not taken from the first number
    (F, "((uint32_t)n - (uint32_t)first) * PR_RECORD_SIZE;", "(uint32_t)n * PR_RECORD_SIZE;"),
    # a record address of 0 answered instead of the fallback
    (F, "                    if (record != 0)\n                        return record;\n                    break;\n",
     "                    return record;\n"),
    # the fallback: 0, the head pointer itself, or the last node's block instead of the first's
    (F, "    return guest_u32(ctx, head + PR_NODE_BLOCK) + PR_BLOCK_RECORDS;", "    return 0;"),
    (F, "    return guest_u32(ctx, head + PR_NODE_BLOCK) + PR_BLOCK_RECORDS;", "    return head + PR_BLOCK_RECORDS;"),
    (F, "            node = guest_u32(ctx, node + PR_NODE_NEXT);\n        } while (node != 0);",
     "            gaddr next = guest_u32(ctx, node + PR_NODE_NEXT);\n            if (next == 0)\n"
     "                head = node;\n            node = next;\n        } while (node != 0);"),
    # only the first block asked
    (F, "        } while (node != 0);", "        } while (0);"),
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
        print("person_record_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("person_record_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_DIR)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"person_record_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, _early) in per.items():
        total_bad += bad
        note = f"  ({cold_n} gave up)" if cold_n else ""
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches{note}")
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("person_record_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    for name, k in REDRAWN.items():
        print(f"  {name:30s} {k:5d} made-up states drawn again (a data read landed in the game's code)")
    print("person_record_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"person_record_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"person_record_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
