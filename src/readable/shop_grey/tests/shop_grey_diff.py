#!/usr/bin/env python3
"""Host differential test of the shop-grey batch against the game's own ARM code.

    python src/readable/shop_grey/tests/shop_grey_diff.py             all functions, 300 cases each
    python src/readable/shop_grey/tests/shop_grey_diff.py -n 1500 --seed 7    the long run
    python src/readable/shop_grey/tests/shop_grey_diff.py --only shop_buy_max
    python src/readable/shop_grey/tests/shop_grey_diff.py --plant     also plant bugs: each must be caught

The method of src/readable/shop_price/tests/shop_price_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): for
every readable function of src/readable/shop_grey/ the test makes up guest states (buy-list menu items
with their class table, discount byte and stock record, Item records, the save's GameUserData with its
gold, the shop's own data behind the word at 0x006D8A68; all random test values, never game data, and on
purpose often outside the ranges the game uses: unmapped menu items (GetStock only), records, stock records,
GameUserData and shop data, the 0x006D8A68 word missing, class tables whose slots hold other functions,
prices of 0, -1, negative or huge enough that the 19/20 cut wraps, gold of 0, negative or huge, gold
right at the price and the cut price, stock counts of 0 and past 127, discount and owner bytes of any
value), runs the ORIGINAL ARM code from the owner's extracted/text.bin in arm_mini.py and the readable C
function (built with the host gcc against tools/readable/stub/) on the same memory, and compares r0,
the number of bytes read from unmapped memory AND the list of guest calls, in order, with their argument
registers (docs/DECISIONS.md F-018).

Every callee is answered by one table on both sides and listed: unit::Item::ToData, GameUserData::Get,
ItemBuyMenuItem::GetUnitItem (the virtual call at slot +0x6C), ItemBuyMenuItem::GetPrice (the virtual
call at slot +0x74) and two made-up functions a class table may hold in either slot instead. None of them
gives up. The signed division GetBuySellMax makes (RVCT's 0x002FFA0C, and its division-by-zero handler
0x0013F8B4) runs inside arm_mini: it is not a call of interest.

No early give-up is allowed anywhere (no function here reads a one-time cache).

--plant copies src/readable/shop_grey/ to build/readable/shop_grey/plant/, makes one small wrong change
at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch. The
list holds every small change found that can change an answer (F-027); a change that cannot (for
example "more than the stock" written as "at least the stock") is not a bug and is not planted.

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
OUT = os.path.join(ROOT, "build", "readable", "shop_grey")
SRC_SG = os.path.join(ROOT, "src", "readable", "shop_grey")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
TO_DATA, GUD_GET, GET_UNIT_ITEM, GET_PRICE = 0x003D0EA4, 0x001B3AFC, 0x0052834C, 0x00528454
FAKE_SLOTS = (0x0BAD2000, 0x0BAD2004)  # made-up functions a class table may hold at +0x6C or +0x74
LEAF_STUBS = {TO_DATA: 1, GUD_GET: 0, GET_UNIT_ITEM: 1, GET_PRICE: 1, FAKE_SLOTS[0]: 1, FAKE_SLOTS[1]: 1}
ARITY = dict(LEAF_STUBS)

OVERRIDES = {"shop_stock": 0x00528470, "shop_price_disabled": 0x005283F0, "shop_buy_max": 0x00528354}
TEST_ENTRIES: dict[str, int] = {}
ADDR = dict(OVERRIDES)

# guest layout of the made-up state
REC = lambda k: 0x08010000 + k * 0x68  # noqa: E731  Item records (ItemData, 0x68 bytes)
MENU = lambda k: 0x08020000 + k * 0x60  # noqa: E731  buy-list menu items
TABLE = lambda k: 0x08030000 + k * 0x100  # noqa: E731  their class tables
STOCK = lambda k: 0x08040000 + k * 0x10  # noqa: E731  stock records
GUD = 0x08050000      # GameUserData
SHOP = 0x08060000     # the shop's own data
SHOP_WORD = 0x006D8A68
NRECS, NMENUS, NTABLES, NSTOCKS = 4, 3, 3, 3
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]
SLOT_ITEM, SLOT_PRICE = 0x6C, 0x74
INT_MIN, INT_MAX = -0x80000000, 0x7FFFFFFF


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sx(v: int, bits: int = 32) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def mapped(st, addr: int) -> bool:
    return addr in st.mem


def ostub(st, func: int, *args: int, value: int) -> None:
    st.oracle[(func,) + tuple(s32(a) for a in args[:LEAF_STUBS[func]])] = s32(value)


def cut(price: int) -> int:
    """price * 19 / 20: the product wraps to 32 bits, the division goes toward zero."""
    p = sx(price * 19)
    q = abs(p) // 20
    return q if p >= 0 else -q


# ------------------------------------------------------------------ the made-up state
PRICES = [0, 0, 1, 19, 20, 21, 100, 300, 500, 1000, 1500, 3000, 8000, 30000]
PRICES_ODD = [-1, -2, -20, -500, INT_MIN, INT_MAX, 0x10000000, 0x0AAAAAAB, 0x06BCA1B0, 0xFFFF]
GOLDS = [0, 0, 1, 50, 100, 999, 1000, 5000, 20000, 99999, 500000, 999999]
GOLDS_ODD = [-1, -100, INT_MIN, INT_MAX, 0x40000000]


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    for k in range(NRECS):
        st.fill(REC(k), 0x68)
        st.put(REC(k) + 0x2C, 4, s32(pick(rng, PRICES, PRICES_ODD, 0.2)))
    for k in range(NSTOCKS):
        st.fill(STOCK(k), 0x10)
        st.put(STOCK(k) + 2, 1, pick(rng, [0, 0, 1, 2, 3, 5, 10, 50, 99, 100], [0x7F, 0x80, 0xFF, 0xC8], 0.2))
    for k in range(NTABLES):
        st.fill(TABLE(k), 0x100)
        st.put(TABLE(k) + SLOT_ITEM, 4, GET_UNIT_ITEM if rng.random() > 0.15 else rng.choice(FAKE_SLOTS))
        st.put(TABLE(k) + SLOT_PRICE, 4, GET_PRICE if rng.random() > 0.15 else rng.choice(FAKE_SLOTS))
    for k in range(NMENUS):
        m = MENU(k)
        st.fill(m, 0x60)
        st.put(m, 4, TABLE(rng.randrange(NTABLES)))  # a junk table would send the virtual call into junk
        st.put(m + 0x38, 1, pick(rng, [0, 0, 0, 1], [0x80, 0xFF, 2], 0.15))
        r = rng.random()
        st.put(m + 0x40, 4, 0 if r < 0.4 else STOCK(rng.randrange(NSTOCKS)) if r < 0.93 else rng.choice(UNMAPPED))
    st.fill(GUD, 0x60)
    st.put(GUD + 0x38, 4, s32(pick(rng, GOLDS, GOLDS_ODD, 0.15)))
    st.fill(SHOP, 0x40)
    st.put(SHOP + 0x31, 1, pick(rng, [0, 0, 0, 1], [2, 0x80, 0xFF], 0.2))
    r = rng.random()
    if r < 0.93:  # else the word is missing (unmapped)
        st.put(SHOP_WORD, 4, SHOP if r < 0.88 else rng.choice(UNMAPPED + [0]))
    return st


def pick_menu(st, rng) -> int:
    return MENU(rng.randrange(NMENUS)) if rng.random() > 0.06 else rng.choice(UNMAPPED)


def answer_gud(st, rng) -> int:
    gud = GUD if rng.random() > 0.05 else rng.choice(UNMAPPED)
    ostub(st, GUD_GET, value=gud)
    return gud


def set_gold_near(st, rng, gud: int, target: int, spread: list[int]) -> None:
    """Puts the gold right around a value the answer turns on (the price, the cut price, a cap)."""
    if gud == GUD:
        st.put(GUD + 0x38, 4, s32(target + rng.choice(spread)))


# ------------------------------------------------------------------ the functions
def entry(name, args):
    a = ADDR[name]
    return f"ov:0x{a:08X}", args + [0] * (4 - len(args)), ("call", a, None)


def gen_stock(rng):
    st = base_state(rng)
    return (st,) + entry("shop_stock", [pick_menu(st, rng)])


def gen_disabled(rng):
    st = base_state(rng)
    m = MENU(rng.randrange(NMENUS))  # mapped: the virtual call needs a table
    target = word(st, word(st, m) + SLOT_ITEM)
    own = m + 0x3A
    got = own if rng.random() > 0.12 else rng.choice([0x08000000] + UNMAPPED)
    for f in (GET_UNIT_ITEM,) + FAKE_SLOTS:
        ostub(st, f, m, value=got if f == target else rng.choice([own, 0x08000000] + UNMAPPED))
    rec = REC(rng.randrange(NRECS)) if rng.random() > 0.06 else rng.choice(UNMAPPED)
    for it in {got, own, 0x08000000}:
        ostub(st, TO_DATA, it, value=rec if it == got else REC(rng.randrange(NRECS)))
    gud = answer_gud(st, rng)
    if rng.random() < 0.5 and mapped(st, rec + 0x2C):
        price = sx(word(st, rec + 0x2C))
        discounted = mapped(st, m + 0x38) and st.mem[m + 0x38] != 0
        # around the price the line uses, or around the other one (catches a cut used or skipped wrongly)
        aim = cut(price) if discounted != (rng.random() < 0.25) else price
        set_gold_near(st, rng, gud, aim, [-1, 0, 0, 1])
    return (st,) + entry("shop_price_disabled", [m])


def gen_max(rng):
    st = base_state(rng)
    m = MENU(rng.randrange(NMENUS))  # mapped: the virtual call needs a table
    target = word(st, word(st, m) + SLOT_PRICE)
    # -1 more often: the division's "over -1" path (a cut -1 is 0, so only without the discount)
    price = pick(rng, PRICES, PRICES_ODD + [-1, -1, -1], 0.25)
    for f in (GET_PRICE,) + FAKE_SLOTS:
        ostub(st, f, m, value=price if f == target else pick(rng, PRICES, PRICES_ODD, 0.2))
    gud = answer_gud(st, rng)
    if rng.random() < 0.6:
        discounted = mapped(st, m + 0x38) and st.mem[m + 0x38] != 0
        eff = cut(price) if discounted != (rng.random() < 0.2) else price
        n = rng.choice([0, 1, 2, 3, 5, 10, 50, 98, 99, 100, 101, 127, 128, 200, 255, 256, 1000])
        stock = word(st, m + 0x40) if mapped(st, m + 0x40) else 0
        if stock and mapped(st, stock + 2) and rng.random() < 0.4:
            n = st.mem[stock + 2] + rng.choice([-1, 0, 1])
        set_gold_near(st, rng, gud, n * eff, [0, 0, 1, -1, max(eff - 1, 0)])
    return (st,) + entry("shop_buy_max", [m])


FUNCS = {
    "shop_stock": gen_stock,
    "shop_price_disabled": gen_disabled,
    "shop_buy_max": gen_max,
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
    the shop-grey batch has no helper, so how[2] is always None and r0 is the result."""
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
/* Generated by src/readable/shop_grey/tests/shop_grey_diff.py: runs the shop-grey batch on
   memory images read from stdin and prints their results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "shop_grey.h"
'''

TEST_ENTRY_CODE = ''  # no helper here: every function is an override


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
    src = os.path.join(out, "shop_grey_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_SG)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(sp_dir, f) for f in sorted(os.listdir(sp_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "shop_grey_driver.exe" if os.name == "nt" else "shop_grey_driver")
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
        raise SystemExit("shop_grey_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"shop_grey_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    m = args[0]
    if exp[0] == 1:
        key = "gave up"
    elif name == "shop_stock":
        stock = word(st, m + 0x40) if mapped(st, m + 0x40) else 0
        key = "no stock record" if stock == 0 else "unmapped stock record" if not mapped(st, stock + 2) \
            else "count past 127" if st.mem[stock + 2] >= 0x80 else "stock record"
        key += ", unmapped menu item" if not mapped(st, m) else ""
    else:
        parts = []
        parts.append("discount" if st.mem.get(m + 0x38, 0) else "no discount")
        slot = SLOT_ITEM if name == "shop_price_disabled" else SLOT_PRICE
        target = word(st, word(st, m) + slot)
        if target in FAKE_SLOTS:
            parts.append("other slot function")
        if st.oracle.get((GUD_GET,), 0) != GUD:
            parts.append("unmapped GameUserData")
        if name == "shop_price_disabled":
            parts.append("greyed" if exp[1] else "not greyed")
        else:
            price = st.oracle.get((target, s32(m)), 0)
            if price == 0:
                parts.append("price 0")
            v = sx(exp[1])
            parts.append("1 (owner)" if v == 1 and st.mem.get(word(st, SHOP_WORD) + 0x31, 0) else
                         "99" if v == 99 else "negative" if v < 0 else "0" if v == 0 else "other")
            stock = word(st, m + 0x40)
            if stock:
                parts.append("stock")
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
        raise SystemExit(f"shop_grey_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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


# planted bugs: (file, exact text, replacement); each text occurs once in its file. Every small change
# found that can change an answer (F-027), per function.
F = "shop_grey.c"
_MAX_HEAD = ("    gaddr table = guest_ptr(ctx, menu_item);\n"
             "    int32_t price = (int32_t)guest_call1(ctx, guest_ptr(ctx, table + SG_SLOT_GET_PRICE), menu_item);\n"
             "    if (guest_u8(ctx, menu_item + SG_MENU_DISCOUNT) != 0)\n"
             "        price = cut_price(price);\n"
             "    int32_t most = rvct_div(save_gold(ctx), price);\n")
PLANTS = [
    # shop_stock
    (F, "    gaddr stock = guest_ptr(ctx, menu_item + SG_MENU_STOCK);\n    if (stock == 0)",
     "    gaddr stock = guest_ptr(ctx, menu_item + 0x3Cu);\n    if (stock == 0)"),
    (F, "        return SG_NO_STOCK;", "        return 0;"),
    (F, "    return guest_u8(ctx, stock + SG_STOCK_COUNT);", "    return guest_u8(ctx, stock + 3u);"),
    (F, "    return guest_u8(ctx, stock + SG_STOCK_COUNT);", "    return guest_s8(ctx, stock + SG_STOCK_COUNT);"),
    # shop_price_disabled
    (F, "table + SG_SLOT_GET_UNIT_ITEM), menu_item);", "table + SG_SLOT_GET_UNIT_ITEM), table);"),
    (F, "guest_ptr(ctx, table + SG_SLOT_GET_UNIT_ITEM)", "guest_ptr(ctx, table + 0x68u)"),
    # GetUnitItem assumed (+0x3A) instead of the virtual call: one call less
    (F, "    gaddr item = guest_call1(ctx, guest_ptr(ctx, table + SG_SLOT_GET_UNIT_ITEM), menu_item);\n",
     "    gaddr item = menu_item + 0x3Au + (table & 0u);\n"),
    (F, "guest_call1(ctx, SG_ItemToData, item);", "guest_call1(ctx, SG_ItemToData, menu_item);"),
    # the item taken as its own record: one call less
    (F, "    gaddr record = guest_call1(ctx, SG_ItemToData, item);\n", "    gaddr record = item;\n"),
    (F, "record, buy_price);", "record, sell_price);"),
    (F, "    if (guest_u8(ctx, menu_item + SG_MENU_DISCOUNT) != 0)\n        price = cut_price(price);\n    return save_gold",
     "    if (guest_u8(ctx, menu_item + SG_MENU_DISCOUNT) == 0)\n        price = cut_price(price);\n    return save_gold"),
    (F, "    if (guest_u8(ctx, menu_item + SG_MENU_DISCOUNT) != 0)\n        price = cut_price(price);\n    return save_gold",
     "    if (guest_u8(ctx, menu_item + 0x39u) != 0)\n        price = cut_price(price);\n    return save_gold"),
    (F, "    if (guest_u8(ctx, menu_item + SG_MENU_DISCOUNT) != 0)\n        price = cut_price(price);\n    return save_gold",
     "    return save_gold"),
    (F, "    return save_gold(ctx) < price ? 1u : 0u;", "    return save_gold(ctx) <= price ? 1u : 0u;"),
    (F, "    return save_gold(ctx) < price ? 1u : 0u;", "    return (uint32_t)save_gold(ctx) < (uint32_t)price ? 1u : 0u;"),
    # the price cut
    (F, "(uint32_t)price * (uint32_t)SG_DISCOUNT_MUL)", "(uint32_t)price * 18u)"),
    (F, "(uint32_t)SG_DISCOUNT_MUL) / SG_DISCOUNT_DIV;", "(uint32_t)SG_DISCOUNT_MUL) / 19;"),
    (F, "    return (int32_t)((uint32_t)price * (uint32_t)SG_DISCOUNT_MUL) / SG_DISCOUNT_DIV;",
     "    return (int32_t)(((int64_t)price * SG_DISCOUNT_MUL) / SG_DISCOUNT_DIV);"),
    (F, "    return (int32_t)((uint32_t)price * (uint32_t)SG_DISCOUNT_MUL) / SG_DISCOUNT_DIV;",
     "    return (int32_t)(((uint32_t)price * (uint32_t)SG_DISCOUNT_MUL) / (uint32_t)SG_DISCOUNT_DIV);"),
    # the save's gold
    (F, "user + SG_USER_GOLD", "user + 0x3Cu"),
    # GameUserData read directly: one call less
    (F, "    gaddr user = guest_call(ctx, SG_GameUserDataGet, 0u, 0u, 0u, 0u);",
     "    gaddr user = guest_ptr(ctx, 0x006DA248u);"),
    # shop_buy_max
    (F, "table + SG_SLOT_GET_PRICE)", "table + SG_SLOT_GET_UNIT_ITEM)"),
    (F, "table + SG_SLOT_GET_PRICE), menu_item);", "table + SG_SLOT_GET_PRICE), table);"),
    # the gold asked before the price: the call order changes
    (F, _MAX_HEAD, "    int32_t gold_first = save_gold(ctx);\n" + _MAX_HEAD.replace("rvct_div(save_gold(ctx), price)",
                                                                                 "rvct_div(gold_first, price)")),
    (F, _MAX_HEAD, _MAX_HEAD.replace("    if (guest_u8(ctx, menu_item + SG_MENU_DISCOUNT) != 0)\n"
                                     "        price = cut_price(price);\n", "")),
    (F, "    if (b == 0)\n        return 0;", "    if (b == 0)\n        return a;"),
    (F, "        return (int32_t)(0u - (uint32_t)a);", "        return a;"),
    (F, "    return a / b;\n}", "    return (a % b != 0 && ((a < 0) != (b < 0))) ? a / b - 1 : a / b;\n}"),
    (F, "    gaddr stock = guest_ptr(ctx, menu_item + SG_MENU_STOCK);\n    if (stock != 0) {",
     "    gaddr stock = guest_ptr(ctx, menu_item + 0x3Cu);\n    if (stock != 0) {"),
    (F, "        if (most > left)\n            most = left;", "        most += left & 0;"),
    (F, "        int32_t left = guest_u8(ctx, stock + SG_STOCK_COUNT);",
     "        int32_t left = guest_s8(ctx, stock + SG_STOCK_COUNT);"),
    (F, "guest_ptr(ctx, SG_ShopSequenceData)", "guest_ptr(ctx, SG_ShopSequenceData + 4u)"),
    (F, "shop + SG_SHOP_OWNER) != 0) {", "shop + 0x30u) != 0) {"),
    (F, "shop + SG_SHOP_OWNER) != 0) {", "shop + SG_SHOP_OWNER) == 0) {"),
    (F, "        if (most > SG_MAX_OTHER_OWNER)\n            most = SG_MAX_OTHER_OWNER;",
     "        if (most > 2)\n            most = 2;"),
    (F, "    } else if (most > SG_MAX_OWN) {\n        most = SG_MAX_OWN;",
     "    } else if (most > 100) {\n        most = 100;"),
    # a floor at 0 the game does not have
    (F, "    return most;\n}", "    return most < 0 ? 0 : most;\n}"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_SG, d, ignore=shutil.ignore_patterns("tests"))
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
        print("shop_grey_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("shop_grey_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_SG)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"shop_grey_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, gave) in per.items():
        total_bad += bad
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({gave} gave up)" if gave else ""))
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("shop_grey_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("shop_grey_diff: paths met")
    for name, p in PATHS.items():
        print(f"  {name:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"shop_grey_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"shop_grey_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
