#!/usr/bin/env python3
"""Host differential test of the skill_record batch against the game's own ARM code.

    python src/readable/skill_record/tests/skill_record_diff.py            300 cases
    python src/readable/skill_record/tests/skill_record_diff.py -n 1500 --seed 7   the long run
    python src/readable/skill_record/tests/skill_record_diff.py --plant    also plant bugs: each must be caught

The method of src/readable/skill_record/tests/skill_record_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): the
test makes up guest states (the ID label hash table that G_IdentHash 0x006DCB44 points at: a bucket
count, a bucket array and chains of entries with a key hash and a value, filled from made-up labels
hashed the game's way; all random test values, never game data, and on purpose often outside what the
game uses: a null label, an unmapped label, an empty label, a label that runs to the end of a mapped
page without its end byte, labels with bytes of 0x80 and above (signed in the hash), labels no entry
holds, decoy entries whose key differs only in its upper or lower half, two entries with the same key
in one chain, unmapped or junk bucket words, an unmapped or null table, a table with 0 buckets, bucket
counts up to 0xFFFFFFFF with only part of the bucket array mapped), runs the ORIGINAL ARM code of
EquipSkill::Get(const char*) (its tail branch into IdentHash::GetSurely and the runtime's division
0x0012A0E4 included) from the owner's extracted/text.bin in arm_mini.py and the readable C override
(built with the host gcc against tools/readable/stub/) on the same memory, and compares r0, the number
of bytes read from unmapped memory AND the list of guest calls (none is expected; docs/DECISIONS.md
F-018).

The body has no one-time cache and calls no guest function, so it never gives up. A table with 0
buckets runs the runtime's division-by-zero path in arm_mini (0x002FFC28, the no-op __rt_div0 at
0x0013F8B4): the remainder is the dividend, and the readable code must answer the same.

--plant copies src/readable/skill_record/ to build/readable/skill_record/plant/, makes one small wrong
change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one
mismatch. Changes that cannot change any answer are listed in docs/SKILL_RECORD.md and not planted.

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
OUT = os.path.join(ROOT, "build", "readable", "skill_record")
SRC_DIR = os.path.join(ROOT, "src", "readable", "skill_record")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json (never reached here)
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
SKILL_BY_NAME = 0x001758C4
LEAF_STUBS: dict[int, int] = {}  # the body calls no guest function (the division runs in arm_mini)
ARITY = dict(LEAF_STUBS)

OVERRIDES = {"skill_record_by_name": SKILL_BY_NAME}
ADDR = dict(OVERRIDES)

# include/readable/generated/fe_globals.h
G_IDENT_HASH = 0x006DCB44

# guest layout of the made-up state
HASH = 0x08010000
BUCKETS = 0x08100000
ENTRY = lambda k: 0x08200000 + k * 0x20  # noqa: E731
LABEL = lambda k: 0x08300000 + k * 0x80  # noqa: E731
PAGE_END_LABEL = 0x08401000            # a label written up to the end of the page before this one
UNMAPPED = [0x40, 0x7FF0, 0x0FFF0000]
MAPPED_BUCKETS = 0x400                 # bucket words mapped at most (a larger count reads past them)


def hashes(label: bytes) -> tuple[int, int]:
    """IdentHash's two hashes of a label (signed bytes, 32-bit wrap): (bucket hash, key hash)."""
    h = k = 0
    for b in label:
        c = b - 256 if b >= 0x80 else b
        h = (h * 37 + c) & 0xFFFFFFFF
        k = (k * 31 + c) & 0xFFFFFFFF
    return h, k


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
    return (b"SEID_" if rng.random() < 0.7 else b"") + body


def put_label(st, addr: int, label: bytes) -> None:
    st.fill(addr, 0x80)  # junk after the end byte: reading past it is seen
    for i, b in enumerate(label):
        st.mem[addr + i] = b
    st.mem[addr + len(label)] = 0


# ------------------------------------------------------------------ the made-up state
def gen_get(rng):
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
    return st, f"ov:0x{SKILL_BY_NAME:08X}", [name, rng.getrandbits(32), rng.getrandbits(32), rng.getrandbits(32)], \
        ("call", SKILL_BY_NAME, None)


FUNCS = {"skill_record_by_name": gen_get}


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
/* Generated by src/readable/skill_record/tests/skill_record_diff.py: runs the
   skill_record batch on memory images read from stdin and prints its results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "skill_record.h"
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
    src = os.path.join(out, "skill_record_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_DIR)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(my_dir, f) for f in sorted(os.listdir(my_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "skill_record_driver.exe" if os.name == "nt" else "skill_record_driver")
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
        raise SystemExit("skill_record_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"skill_record_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    """Which way the original answered: a null label, an entry found or no entry found, and whether
    the table had 0 buckets (the remainder is the bucket hash itself)."""
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
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
        raise SystemExit(f"skill_record_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
F = "skill_record.c"
H = "skill_record.h"
FOUND = "            return guest_u32(ctx, entry + SR_ENTRY_VALUE);"
PLANTS = [
    # the wrong table word
    (F, "guest_u32(ctx, G_IdentHash), name)", "guest_u32(ctx, G_IdentHash + 4u), name)"),
    # the wrong offsets: count, bucket array, next link, key, value
    (H, "#define SR_HASH_COUNT 0x04u", "#define SR_HASH_COUNT 0x08u"),
    (H, "#define SR_HASH_BUCKETS 0x10u", "#define SR_HASH_BUCKETS 0x0Cu"),
    (H, "#define SR_ENTRY_NEXT 0x0u", "#define SR_ENTRY_NEXT 0x8u"),
    (H, "#define SR_ENTRY_KEY 0x4u", "#define SR_ENTRY_KEY 0x8u"),
    (H, "#define SR_ENTRY_VALUE 0xCu", "#define SR_ENTRY_VALUE 0x8u"),
    # the hash multipliers swapped one at a time
    (H, "#define SR_BUCKET_MUL 37u", "#define SR_BUCKET_MUL 31u"),
    (H, "#define SR_KEY_MUL 31u", "#define SR_KEY_MUL 37u"),
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
    (F, "        entry = guest_u32(ctx, entry + SR_ENTRY_NEXT);", "        entry = 0;"),
    # the key compared on 16 bits only
    (F, "if (guest_u32(ctx, entry + SR_ENTRY_KEY) == key)",
     "if (guest_u16(ctx, entry + SR_ENTRY_KEY) == (key & 0xFFFFu))"),
    # the last matching entry answered instead of the first
    (F, "    while (entry != 0) {\n        if (guest_u32(ctx, entry + SR_ENTRY_KEY) == key)\n" + FOUND
     + "\n        entry = guest_u32(ctx, entry + SR_ENTRY_NEXT);\n    }\n    return 0;",
     "    gaddr found = 0;\n    while (entry != 0) {\n        if (guest_u32(ctx, entry + SR_ENTRY_KEY) == key)\n"
     "            found = guest_u32(ctx, entry + SR_ENTRY_VALUE);\n"
     "        entry = guest_u32(ctx, entry + SR_ENTRY_NEXT);\n    }\n    return found;"),
    # the entry's address answered instead of its value
    (F, FOUND, "            return entry + SR_ENTRY_VALUE;"),
    # 0 buckets: the remainder taken as 0, or the lookup answering 0 (the runtime's division-by-zero
    # path hands back the dividend)
    (F, "count != 0 ? bucket_hash % count : bucket_hash;", "count != 0 ? bucket_hash % count : 0u;"),
    (F, "    uint32_t bucket = count != 0 ? bucket_hash % count : bucket_hash;\n",
     "    if (count == 0)\n        return 0;\n    uint32_t bucket = bucket_hash % count;\n"),
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
        print("skill_record_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("skill_record_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_DIR)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"skill_record_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, _early) in per.items():
        total_bad += bad
        note = f"  ({cold_n} gave up)" if cold_n else ""
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches{note}")
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("skill_record_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("skill_record_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"skill_record_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"skill_record_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
