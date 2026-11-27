#!/usr/bin/env python3
"""Host differential test of the shop-price batch against the game's own ARM code.

    python src/readable/shop_price/tests/shop_price_diff.py             all functions, 300 cases each
    python src/readable/shop_price/tests/shop_price_diff.py -n 1500 --seed 7    the long run
    python src/readable/shop_price/tests/shop_price_diff.py --only convoy_stack_value
    python src/readable/shop_price/tests/shop_price_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/weapon_rank/tests/weapon_rank_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): for
every readable function of src/readable/shop_price/ the test makes up guest states (buy-list menu
items with their class table, unit::Items, Item records; all random test values, never game data, and
on purpose often outside the ranges the game uses: unmapped menu items, items and records, class
tables whose GetUnitItem slot holds another function, buy prices of 0, negative or huge, full uses of
0, uses and counts of 0, negative or huge, forge ranks past 63), runs the ORIGINAL ARM code from the
owner's extracted/text.bin in arm_mini.py and the readable C function (built with the host gcc against
tools/readable/stub/) on the same memory, and compares r0, the number of bytes read from unmapped
memory AND the list of guest calls, in order, with their argument registers (docs/DECISIONS.md F-018).

Every callee is answered by one table on both sides and listed: unit::Item::ToData,
unit::Item::GetRefineRank, ItemBuyMenuItem::GetUnitItem (the virtual call at slot +0x6C) and two
made-up functions a class table may hold there instead. None of them gives up. The unsigned division
the convoy value makes (the game's text_udiv) runs inside arm_mini (it is not a call of interest).

convoy_stack_value is a helper (Transporter::GetPrice returns 64 bits; an override gives back r0 only;
docs/SHOP_PRICE.md): it runs through a test-only entry of the generated driver (never a marker in
src/readable/); the ARM function runs whole and its r0:r1 are the expected result, folded into one
number (FNV-1a over the eight bytes) on both sides.

No early give-up is allowed anywhere (no function here reads a one-time cache).

--plant copies src/readable/shop_price/ to build/readable/shop_price/plant/, makes one small wrong
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
OUT = os.path.join(ROOT, "build", "readable", "shop_price")
SRC_SP = os.path.join(ROOT, "src", "readable", "shop_price")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
TO_DATA, REFINE_RANK, GET_UNIT_ITEM = 0x003D0EA4, 0x0053B278, 0x0052834C
FAKE_SLOTS = (0x0BAD2000, 0x0BAD2004)  # made-up functions a class table may hold at +0x6C
LEAF_STUBS = {TO_DATA: 1, REFINE_RANK: 1, GET_UNIT_ITEM: 1, FAKE_SLOTS[0]: 1, FAKE_SLOTS[1]: 1}
ARITY = dict(LEAF_STUBS)

OVERRIDES = {"shop_buy_price": 0x00528454}
TEST_ENTRIES = {"convoy_stack_value": 0x001A6F4C}
ADDR = dict(OVERRIDES, **TEST_ENTRIES)

# guest layout of the made-up state
ITEM = lambda k: 0x08000000 + k * 8  # noqa: E731   unit::Items (u16 number, u16 bits)
REC = lambda k: 0x08010000 + k * 0x68  # noqa: E731  Item records (ItemData, 0x68 bytes)
MENU = lambda k: 0x08020000 + k * 0x60  # noqa: E731  buy-list menu items
TABLE = lambda k: 0x08030000 + k * 0x100  # noqa: E731  their class tables
NITEMS, NRECS, NMENUS, NTABLES = 6, 5, 3, 3
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
SLOT = 0x6C


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


def ostub(st, func: int, *args: int, value: int) -> None:
    st.oracle[(func,) + tuple(s32(a) for a in args[:LEAF_STUBS[func]])] = s32(value)


# ------------------------------------------------------------------ the made-up state
PRICES = [0, 0, 100, 300, 500, 1000, 1500, 3000, 8000, 30000]
PRICES_ODD = [-1, -500, -0x80000000, 0x7FFFFFFF, 0x10000000, 0x01000000, 0xFFFF]


def make_record(st, r: int) -> None:
    rng = st.rng
    st.fill(r, 0x68)
    st.put(r + 0x14, 2, pick(rng, [1, 2, 10, 50, 120, 200, 300], [0, 0xFFFF, 0x8000, 0xFFFE], 0.15))
    st.put(r + 0x1E, 1, pick(rng, [0, 0, 1, 3, 5, 10, 20, 30, 40, 45, 60], [0xFF, 0x80, 0x7F], 0.15))
    st.put(r + 0x2C, 4, s32(pick(rng, PRICES, PRICES_ODD, 0.15)))
    for i in range(2):  # pool ranks 0 and 1: below 0 often enough that both are
        st.put(r + 0x58 + i, 1, rng.choice([0xFF, 0xFF, 0x80, 0xFE, 0, 1, 3, 0x7F]))


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    for k in range(NRECS):
        make_record(st, REC(k))
    for k in range(NITEMS):
        st.fill(ITEM(k), 8)
        st.put(ITEM(k) + 2, 2, pick(rng, [0, 0, 1, 2, 3, 0x80, 0x81, 0x0500, 0x1402, 0x0101, rng.randrange(0x10000)],
                                    [0x7F, 0x80, 0xFFFF, 0x3F00], 0.1))
    return st


def answer_items(st, items) -> None:
    """ToData and GetRefineRank for every item a case can reach (one answer per item on both sides)."""
    rng = st.rng
    for it in items:
        ostub(st, TO_DATA, it, value=REC(rng.randrange(NRECS)) if rng.random() > 0.06 else rng.choice(UNMAPPED))
        ostub(st, REFINE_RANK, it, value=pick(rng, [0, 0, 0, 1, 2, 3, 5, 7], [0x3F, 0x10, 0xFFFFFFFF, 0x80000000], 0.1))


# ------------------------------------------------------------------ the functions
# Each generator returns (state, kind, args, how the ARM side runs).

def entry(name, args, result=None):
    a = ADDR[name]
    return f"ov:0x{a:08X}", args + [0] * (4 - len(args)), ("call", a, result)


def gen_buy(rng):
    st = base_state(rng)
    for k in range(NTABLES):
        st.fill(TABLE(k), 0x100)
        st.put(TABLE(k) + SLOT, 4, GET_UNIT_ITEM if rng.random() > 0.15 else rng.choice(FAKE_SLOTS))
    for k in range(NMENUS):
        m = MENU(k)
        st.fill(m, 0x60)
        st.put(m, 4, TABLE(rng.randrange(NTABLES)))
    m = MENU(rng.randrange(NMENUS))
    # the menu item's own unit::Item (+0x3A), as GetUnitItem returns it, or something else
    target = word(st, word(st, m) + SLOT)
    own = m + 0x3A
    got = own if rng.random() > 0.15 else rng.choice([ITEM(rng.randrange(NITEMS))] + UNMAPPED)
    for f in (GET_UNIT_ITEM,) + FAKE_SLOTS:
        ostub(st, f, m, value=got if f == target else rng.choice([own, ITEM(0)] + UNMAPPED))
    answer_items(st, {got, own, ITEM(0)})
    return (st,) + entry("shop_buy_price", [m])


def gen_convoy(rng):
    st = base_state(rng)
    r = rng.random()
    it = ITEM(rng.randrange(NITEMS)) if r < 0.92 else rng.choice(UNMAPPED + [0])
    answer_items(st, {it})
    uses = pick(rng, [0, 0, 1, 3, 10, 20, 40, 45, 60], [-1, -0x80000000, 0x7FFFFFFF, 0x10000, 255], 0.15)
    count = pick(rng, [0, 1, 1, 2, 5, 20, 99, 250], [-1, -3, -0x80000000, 0x7FFFFFFF, 0x10000, 0xFFFF], 0.15)

    def result(cpu, _mem):
        return fnv(cpu.r[0].to_bytes(4, "little") + cpu.r[1].to_bytes(4, "little"))
    return (st,) + entry("convoy_stack_value", [it, s32(uses), s32(count)], result=result)


FUNCS = {
    "shop_buy_price": gen_buy,
    "convoy_stack_value": gen_convoy,
}


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
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]. For the
    helper, r0 is how[2] folded from r0:r1."""
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
    r0 = cpu.r[0] if how[2] is None else how[2](cpu, mem)
    return [0, r0, mem.faults, calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
DRIVER_HEAD = r'''
/* Generated by src/readable/shop_price/tests/shop_price_diff.py: runs the shop-price batch on
   memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "shop_price.h"
'''

TEST_ENTRY_CODE = r'''
/* test-only entry (never in src/readable/: this address has a helper row, no override) */
static uint32_t t_convoy(Context *ctx, gaddr item, int32_t uses, int32_t count) {
    uint64_t v = convoy_stack_value(ctx, item, uses, count);
    uint32_t h = 0x811C9DC5u;
    for (int i = 0; i < 8; i++) h = (h ^ (uint8_t)(v >> (8 * i))) * 0x01000193u;
    return h;
}
void test_0x001A6F4C(Context *ctx) { FE_ENTRY(0x001A6F4C, t_convoy, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2)); }
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


def build_driver(cc: str, out: str, sp_dir: str, strict: bool = True) -> str:
    """Builds the driver with every source of src/readable/, this folder's taken from sp_dir (a planted
    bug may leave a parameter unused: not strict then). Each source is compiled on its own, in
    parallel; the other areas' objects once per run, reused for every planted bug."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "shop_price_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_SP)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(sp_dir, f) for f in sorted(os.listdir(sp_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "shop_price_driver.exe" if os.name == "nt" else "shop_price_driver")
    inc = ["-I", sp_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
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
        raise SystemExit("shop_price_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"shop_price_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up"
    elif name == "shop_buy_price":
        target = word(st, word(st, args[0]) + SLOT)
        got = st.oracle.get((target, s32(args[0])), 0)
        rec = st.oracle.get((TO_DATA, got), 0)
        key = ("GetUnitItem" if target == GET_UNIT_ITEM else "other slot function") + \
            (", unmapped record" if rec in UNMAPPED else "") + (", price 0" if exp[1] == 0 else "")
    else:
        it = args[0]
        rec = st.oracle.get((TO_DATA, s32(it)), 0)
        rank = st.oracle.get((REFINE_RANK, s32(it)), 0)
        bits = word(st, it + 2, 2) if it not in UNMAPPED and it != 0 else 0
        forged = rank != 0 or (bits & 0x7F) >= 2
        parts = ["forged" if forged else "plain"]
        if rec not in UNMAPPED:
            if st.mem.get(rec + 0x58, 0) >= 0x80 and st.mem.get(rec + 0x59, 0) >= 0x80:
                parts.append("unpooled")
            if word(st, rec + 0x2C) == 0:
                parts.append("price 0")
            elif sx(args[1], 32) > 0 and st.mem.get(rec + 0x1E, 0):
                parts.append("scaled by uses")
        else:
            parts.append("unmapped record")
        key = ", ".join(parts)
    p[key] = p.get(key, 0) + 1


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    lines = [f"arity {f:x} {k}" for f, k in ARITY.items()]
    expected: dict[int, tuple[str, list, tuple]] = {}
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
            expected[cid] = (name, exp, (kind, args))
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
        raise SystemExit(f"shop_price_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
        res = per.setdefault(name, [0, 0, 0])  # cases, mismatches, gave-up cases
        res[0] += 1
        g = got.get(c)
        if exp[0] == 0:
            cov = COVERAGE.setdefault(name, {"values": set(), "nonzero": 0, "faulty": 0, "calls": 0})
            cov["values"].add(exp[1])
            cov["nonzero"] += int(exp[1] != 0)
            cov["faulty"] += int(exp[2] != 0)
            cov["calls"] += 0 if exp[3] == "-" else exp[3].count(",") + 1
        else:
            res[2] += 1
            exp = [1, 0]
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file
F = "shop_price.c"
PLANTS = [
    # shop_buy_price
    (F, "guest_ptr(ctx, table + SP_MENU_GET_UNIT_ITEM_SLOT)", "guest_ptr(ctx, table + 0x68u)"),
    (F, "table + SP_MENU_GET_UNIT_ITEM_SLOT), menu_item);", "table + SP_MENU_GET_UNIT_ITEM_SLOT), table);"),
    # GetUnitItem assumed (+0x3A) instead of the virtual call: one call less
    (F, "    gaddr item = guest_call1(ctx, guest_ptr(ctx, table + SP_MENU_GET_UNIT_ITEM_SLOT), menu_item);\n",
     "    gaddr item = menu_item + 0x3Au + (table & 0u);\n"),
    # ToData's work done directly (Item::Get of the number): another call
    (F, "    gaddr record = guest_call1(ctx, SP_ItemToData, item);\n    return READ_FIELD(ctx, ItemData, record, buy_price);",
     "    gaddr record = guest_call1(ctx, 0x003D0EACu, guest_u16(ctx, item));\n"
     "    return READ_FIELD(ctx, ItemData, record, buy_price);"),
    (F, "    return READ_FIELD(ctx, ItemData, record, buy_price);\n}",
     "    return READ_FIELD(ctx, ItemData, record, sell_price);\n}"),
    # convoy_stack_value
    (F, "& SP_ITEM_BITS_NAME) >= SP_NAMED_FORGE_SLOT;", "& SP_ITEM_BITS_NAME) >= 1u;"),
    (F, "& SP_ITEM_BITS_NAME) >= SP_NAMED_FORGE_SLOT;", "& 0xFFu) >= SP_NAMED_FORGE_SLOT;"),
    # the rank kept from the first call: one call less
    (F, "        high = guest_call1(ctx, SP_ItemGetRefineRank, item) << SP_RANK_SHIFT;",
     "        high = 1u << SP_RANK_SHIFT;"),
    (F, "item) << SP_RANK_SHIFT;", "item) << 27u;"),
    (F, "pool_rank) + (gaddr)i) >= 0;", "pool_rank) + (gaddr)i) > 0;"),
    (F, "    for (int i = 0; i < SP_POOL_RANKS_ASKED && !pooled; i++) {",
     "    for (int i = 0; i < 1 && !pooled; i++) {"),
    # every pool rank asked even after one is found: one call more
    (F, "    for (int i = 0; i < SP_POOL_RANKS_ASKED && !pooled; i++) {",
     "    for (int i = 0; i < SP_POOL_RANKS_ASKED; i++) {"),
    (F, "    if (!pooled)\n", "    if (pooled)\n"),
    (F, "item), buy_price) == 0) {", "item), buy_price) <= 0) {"),
    (F, "        high += (uint32_t)count << SP_COUNT_SHIFT;\n", ""),
    (F, "        high += SP_NUMBER_FLIP - READ_FIELD", "        high += 0xFFFEu - READ_FIELD"),
    (F, "    if (uses <= 0)\n", "    if (uses < 0)\n"),
    (F, "    if (full == 0)\n", "    if (full <= 1)\n"),
    # signed division instead of the game's unsigned one
    (F, "    return ((uint32_t)READ_FIELD(ctx, ItemData, record, buy_price) * (uint32_t)uses) / full;",
     "    return (uint32_t)((int32_t)((uint32_t)READ_FIELD(ctx, ItemData, record, buy_price) * (uint32_t)uses) /"
     " (int32_t)full);"),
    (F, "(int64_t)(int32_t)worth", "(int64_t)worth"),
    (F, "* (int64_t)count;", "* (int64_t)(uint32_t)count;"),
    # the low word not carried into the high word
    (F, "    return ((uint64_t)high << 32) + (uint64_t)total;",
     "    return ((uint64_t)high << 32) | (uint32_t)total;"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_SP, d, ignore=shutil.ignore_patterns("tests"))
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
        print("shop_price_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("shop_price_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_SP)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"shop_price_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, gave) in per.items():
        total_bad += bad
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({gave} gave up)" if gave else ""))
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("shop_price_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("shop_price_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"shop_price_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"shop_price_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
