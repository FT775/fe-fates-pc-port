#!/usr/bin/env python3
"""Host differential test of the item_enhance batch (Unit::IsItemEnhanceHave) against the game's own ARM code.

    python src/readable/item_enhance/tests/item_enhance_diff.py            300 cases
    python src/readable/item_enhance/tests/item_enhance_diff.py -n 1500 --seed 7   the long run
    python src/readable/item_enhance/tests/item_enhance_diff.py --plant    also plant bugs: each must be caught

The method of src/readable/rod_target/tests/rod_target_diff.py and src/readable/equip_use/tests/
equip_use_diff.py (the C driver body of src/readable/sheet/tests/sheet_diff.py, the ARM interpreter
src/readable/battle/tests/arm_mini.py). The made-up guest states start from equip_use_diff.py's
base_state (units with their Person and class records, Item records, ItemSubKind records, the 21
one-time caches of Unit::CanItemEquip and the 9 of the overrides it calls, torn records and a torn unit)
and add this function's sixteen caches, item flag words that turn on them, owners' PersonFlag bits in
the units, Persons and classes, and ItemSubKind kind 8. All random test values, never game data, and on
purpose often outside the ranges the game uses: bools that are not 0/1, a combined "only for" cache
that does not match its six parts, unmapped and torn records and units.

The ORIGINAL ARM code of Unit::IsItemEnhanceHave from the owner's extracted/text.bin runs in arm_mini.py,
INCLUDING its tail branch into Unit::CanItemEquip's ARM code (3dsrecomp copies that code into the
caller, so the live library never enters the CanItemEquip override from here; docs/ITEM_ENHANCE.md 2).
The readable C function runs on the same memory and calls unit_can_equip_item's C directly. Compared:
r0, the number of bytes read from unmapped memory AND the list of guest calls, in order, with their
argument registers (docs/DECISIONS.md F-018); the callees of both functions (ToData, ItemSubKind::Get,
Person::IsDownload, and CanItemEquip's GetWeaponExpLimit, Job::CanEquipFromSubKind, GetCategory,
IsEquipSkill, IsFemale) are answered by one table on both sides and listed. A tail branch is not a
call: CanItemEquip itself is never listed, on either side.

One-time caches: the readable code must give up, before reading anything else, exactly when one of the
46 guards it asks (its 16 own, and the 30 unit_can_equip_item asks) is cold, and must not give up
otherwise. A cold own guard makes the original reach the guard routine at entry; a cold CanItemEquip
guard does so only if the original reaches the tail branch; when it does not, the case is counted apart
as an "early give-up" (safe: the original runs; docs/ITEM.md section 5). Every case with all guards
warm must match exactly, so a give-up there is a mismatch. Every fourth case has exactly one guard cold,
own and CanItemEquip ones taken in turn; the first time round the CanItemEquip guards, that case
has no bonus bit (the original answers 0 before the tail branch), so each of the 30 is seen to be
asked by the readable code itself.

--plant copies src/readable/item_enhance/ to build/readable/item_enhance/plant/, makes one small wrong
change at a time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch.
Changes that cannot change any answer are listed in docs/ITEM_ENHANCE.md and not planted.

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
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "equip_use", "tests"))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "battle", "tests"))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "sheet", "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
import equip_use_diff as EU  # noqa: E402  (base_state, answers, CanItemEquip's caches)
from stance_diff import pick  # noqa: E402

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "item_enhance")
SRC_DIR = os.path.join(ROOT, "src", "readable", "item_enhance")
GUARD = EU.GUARD
SP = EU.SP

# ------------------------------------------------------------------ addresses
TO_DATA, SUBKIND, IS_DOWNLOAD = EU.TO_DATA, EU.SUBKIND, EU.IS_DOWNLOAD
CAN_EQUIP = 0x0052C634  # reached by the tail branch: never a stub, never listed
ENHANCE = 0x0052FB98
LEAF_STUBS = dict(EU.LEAF_STUBS)
ARITY = dict(LEAF_STUBS)
NAMES = dict(EU.NAMES)
assert CAN_EQUIP not in LEAF_STUBS

OVERRIDES = {"unit_item_enhance_have": ENHANCE}

# item_enhance.h: sixteen guards, one word apart, asked going down
OWN_GUARDS = tuple(range(0x006D9894, 0x006D9854, -4))
assert len(OWN_GUARDS) == 16 and OWN_GUARDS[-1] == 0x006D9858
PERSON_BITS = tuple(0x006D9B98 + 8 * i for i in range(6))  # avatar, Takumi, Ryoma, Leo, Xander, Ophelia
CARRY, FUJIN, BRYN = 0x006D9BC8, 0x006D9BD0, 0x006D9BD8
ONLY_BITS = tuple(0x006D9BE0 + 8 * i for i in range(6))     # the same six owners
ANY_ONLY = 0x006D9C10
EQUIP_GUARDS = EU.ALL_GUARDS
ALL_GUARDS = OWN_GUARDS + EQUIP_GUARDS
UNITS = [EU.UNIT(k) for k in range(EU.NUNITS)]
RECS = [EU.REC(k) for k in range(EU.NRECS)]


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def word(st, addr: int, n: int = 4) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(n)), "little")


def any_cold(st) -> bool:
    return any((word(st, g) & 1) == 0 for g in ALL_GUARDS)


def bit64(rng) -> int:
    return 1 << rng.randrange(64) if rng.random() > 0.05 else rng.choice([0, rng.randrange(1 << 64)])


# ------------------------------------------------------------------ the made-up state
_CASE = [0, 0, 0]  # cases made, own guards made cold, CanItemEquip guards made cold (reset per case set)
COLD_SEEN: dict[int, int] = {}


def own_caches(st) -> None:
    rng = st.rng
    st.zero(0x006D9850, 0x50)    # this function's guard words
    st.zero(0x006D9B90, 0x90)    # CanItemEquip's combined mask (set again below) and this function's values
    for g in ALL_GUARDS:
        st.put(g, 4, rng.choice([1, 0x101, 0xFFFFFFFF]))
    # CanItemEquip's own values, as equip_use_diff's caches() made them (the zero above cleared ANY_ONLY)
    any_eq = 0
    for a in EU.ITEM_MASKS:
        any_eq |= word(st, a, 8)
    st.put(EU.ANY_ONLY, 8, any_eq if rng.random() < 0.9 else rng.randrange(1 << 64))
    for a in PERSON_BITS + (CARRY, FUJIN, BRYN) + ONLY_BITS:
        st.put(a, 8, bit64(rng))
    if rng.random() < 0.3:  # the owners' PersonFlag bits the same as CanItemEquip's (as in the game, where
        for a, b in zip(PERSON_BITS, EU.PERSON_MASKS[:6]):  # both come from the same six labels)
            st.put(a, 8, word(st, b, 8))
    if rng.random() < 0.3:  # the "only for" item bits the same as CanItemEquip's avatar and royal ones
        for a, b in zip(ONLY_BITS, (EU.ITEM_MASKS[0],) + EU.ITEM_MASKS[4:9]):
            st.put(a, 8, word(st, b, 8))
    any_only = 0
    for a in ONLY_BITS:
        any_only |= word(st, a, 8)
    r = rng.random()
    st.put(ANY_ONLY, 8, any_only if r < 0.85 else (0 if r < 0.9 else rng.randrange(1 << 64)))
    _CASE[0] += 1
    st.early = False
    if _CASE[0] % 4 == 0:  # exactly one cold guard: own and CanItemEquip's in turn
        if (_CASE[0] // 4) % 2:
            g = OWN_GUARDS[_CASE[1] % len(OWN_GUARDS)]
            _CASE[1] += 1
        else:
            g = EQUIP_GUARDS[_CASE[2] % len(EQUIP_GUARDS)]
            # the first time round, the case answers before the tail branch (no bonus bit), so the
            # readable code's own test of that guard is what must make it give up
            st.early = _CASE[2] < len(EQUIP_GUARDS)
            _CASE[2] += 1
        st.put(g, 4, rng.choice([0, 0x100, 0xFFFFFFFE]))
        COLD_SEEN[g] = COLD_SEEN.get(g, 0) + 1
    elif rng.random() < 0.02:  # several cold
        for g in ALL_GUARDS:
            if rng.random() < 0.2:
                st.put(g, 4, 0)


def gen_enhance(rng):
    st = EU.base_state(rng)
    own_caches(st)
    r = rng.random()
    unit = rng.choice(UNITS) if r < 0.9 else (EU.TORN_UNIT if r < 0.96 else rng.choice(EU.UNMAPPED))
    item = EU.ITEM(rng.randrange(EU.NITEMS)) if rng.random() > 0.05 else rng.choice(EU.UNMAPPED + [0])
    r = rng.random()
    rec = rng.choice(RECS) if r < 0.86 else rng.choice([EU.TORN_REC, EU.TORN_REC2] * 3 + EU.UNMAPPED)
    named = EU.bool_arg(rng)
    torn_owner = rng.random() < 0.1
    if torn_owner:
        # the torn record (only the low word of its flags mapped; every read of the flag word gives 4
        # unmapped bytes): the bonus bit and the "only for" bits all in the low word, the owners tried
        # past the first, so a flag word read once instead of once per owner shows
        rec = EU.TORN_REC
        for a in (CARRY,) + ONLY_BITS:
            st.put(a, 8, 1 << rng.randrange(32))
        any_only = 0
        for a in ONLY_BITS:
            any_only |= word(st, a, 8)
        st.put(ANY_ONLY, 8, any_only)
    # the item record's flag word: which of the three bonus bits, and which "only for" bits
    flags = rng.randrange(1 << 64) & rng.randrange(1 << 64)
    for a in (CARRY, FUJIN, BRYN) + ONLY_BITS:
        flags &= ~word(st, a, 8)
    aim = "carry" if torn_owner else rng.choice(("carry", "carry", "carry", "fujin", "bryn", "none"))
    if st.early:
        aim = "none"
    if aim == "carry":
        flags |= word(st, CARRY, 8)
    elif aim in ("fujin", "bryn"):
        flags |= word(st, FUJIN if aim == "fujin" else BRYN, 8)
        named = named if rng.random() < 0.3 else pick(rng, [1], [0x100, 0x80000000, 2], 0.3)
        if rng.random() < 0.2:
            named = 0
    owner = rng.randrange(1, 6) if torn_owner else (rng.randrange(6) if rng.random() < 0.55 else None)
    if owner is not None:
        flags |= word(st, ONLY_BITS[owner], 8)
        if rng.random() < 0.15:
            flags |= word(st, ONLY_BITS[rng.randrange(6)], 8)
    if rec in RECS:
        st.put(rec, 8, flags)
    elif rec == EU.TORN_REC:
        st.put(rec, 4, flags & 0xFFFFFFFF)
    elif rec == EU.TORN_REC2:
        st.put(rec, 8, flags)
    # the unit (own, Person, class flag words) often carries the owner's PersonFlag bit; state bit 28
    if owner is not None and unit in UNITS and rng.random() < 0.75:
        where = rng.choice([unit, word(st, unit + 0x9C), word(st, unit + 0xA0)])
        if where in [EU.PERSON(k) for k in range(EU.NUNITS)] + [EU.JOB(k) for k in range(EU.NUNITS)] + UNITS:
            st.put(where, 8, word(st, where, 8) | word(st, PERSON_BITS[owner], 8))
    elif owner is not None and unit == EU.TORN_UNIT and rng.random() < 0.6:
        st.put(unit, 8, word(st, unit, 8) | word(st, PERSON_BITS[owner], 8))
    # the sub-kind: kind 8 often, so the bonus counts without the equip test
    if rec in RECS and rng.random() < 0.3:
        idx = rng.choice(EU.SUB_INDICES)
        st.put(EU.SUB(idx) + 1, 1, 8)
        st.put(rec + 0x1A, 1, s32(idx) & 0xFF)
    EU.answers(st, unit, item, rec)
    if unit in UNITS and owner is not None and rng.random() < 0.6:
        # the owner's case with state bit 28 set, so Person::IsDownload decides; its answer often a
        # word whose low byte is 0 (0x100, 0x80000000), which still means yes
        st.put(unit + 8, 4, word(st, unit + 8) | 0x10000000)
        ostub(st, IS_DOWNLOAD, word(st, unit + 0x9C), value=rng.choice([0, 1, 0x100, 0x80000000, 2]))
    elif unit in UNITS and rng.random() < 0.4:  # IsDownload of the unit's Person: yes often
        ostub(st, IS_DOWNLOAD, word(st, unit + 0x9C), value=pick(rng, [1], [2, 0x100, 0x80000000], 0.3))
    return st, f"ov:0x{ENHANCE:08X}", [unit, item, named, 0], ("call", ENHANCE, aim)


def ostub(st, func: int, *args: int, value: int) -> None:
    st.oracle[(func,) + tuple(s32(a) for a in args[:LEAF_STUBS[func]])] = s32(value)


FUNCS = {"unit_item_enhance_have": gen_enhance}


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
/* Generated by src/readable/item_enhance/tests/item_enhance_diff.py: runs the
   item_enhance batch on memory images read from stdin and prints its results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "item_enhance.h"
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
    parallel; the other areas' objects once per run, reused for every planted bug. A planted copy
    lives two folders below build/readable/item_enhance/, so its "../equip_use/equip_use.h" is found
    through the extra -I of src/readable/item_enhance's parent's sibling (see inc)."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "item_enhance_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_DIR)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(my_dir, f) for f in sorted(os.listdir(my_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "item_enhance_driver.exe" if os.name == "nt" else "item_enhance_driver")
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
        raise SystemExit("item_enhance_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"item_enhance_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, exp: list, aim: str) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up (cold)"
    else:
        calls = [] if exp[3] == "-" else [int(c.split(":")[0], 16) for c in exp[3].split(",")]
        if SUBKIND not in calls:
            key = "owner's item" if exp[1] else "no bonus bit"
        elif len(calls) > calls.index(SUBKIND) + 1:
            key = "equip test"
        else:
            key = "kind 8"
        key += f" ({aim}) -> {'yes' if exp[1] else 'no'}"
        if IS_DOWNLOAD in calls[:calls.index(SUBKIND) + 1 if SUBKIND in calls else len(calls)]:
            key += " after IsDownload"
        if exp[2]:
            key += " (unmapped reads)"
    p[key] = p.get(key, 0) + 1


def make_cases(text: bytes, n: int, seed: int, only: str | None):
    rng = random.Random(seed)
    _CASE[0] = _CASE[1] = _CASE[2] = 0
    EU.COLD_TURN[0] = EU.COLD_TURN[1] = 0
    COLD_SEEN.clear()
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
            note_path(name, exp, how[2])
            expected[cid] = (name, exp, (kind, args), any_cold(st))
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
        raise SystemExit(f"item_enhance_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list] = {}
    flagged: dict[int, str] = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE", "NESTED-GIVEUP"):
            flagged[int(parts[0])] = parts[1]
        elif parts:
            got[int(parts[0])] = [parse(x) for x in parts[1:4]] + parts[4:]  # the call list stays text
    per: dict[str, list[int]] = {}
    for c, (name, exp, inputs, cold) in expected.items():
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
        elif cold:
            # a CanItemEquip guard is cold and the original did not reach the tail branch: the readable
            # code must give up before reading anything; the original goes on. Safe.
            exp = [1, 0]
            if g == exp and c not in flagged:
                res[3] += 1
                continue
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                print(f"  MISMATCH {name} case {c}: original {exp}, readable {g}{why}; {inputs[0]} "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
    return per


# planted bugs: (file, exact text, replacement); each text occurs once in its file.
# Every one can change an answer (r0, unmapped reads or the call list) before capture (F-027).
F = "item_enhance.c"
H = "item_enhance.h"
PLANTS = [
    # the caches not asked first
    (F, "    if (!caches_ready(ctx))\n        return fe_use_original(ctx);\n", ""),
    # an own guard not asked: the first, the last
    (F, "    for (gaddr g = S_IeGuardFirst; g >= S_IeGuardLast;", "    for (gaddr g = S_IeGuardFirst - 4u; g >= S_IeGuardLast;"),
    (F, "    for (gaddr g = S_IeGuardFirst; g >= S_IeGuardLast;", "    for (gaddr g = S_IeGuardFirst; g > S_IeGuardLast;"),
    # CanItemEquip's own caches, or one of its callees' (the download guard), not asked
    (F, "    for (gaddr g = S_EuGuardFirst; g <= S_EuGuardLast; g += S_EuGuardStep)\n        if (!fe_static_ready(ctx, g))\n            return 0;\n", ""),
    (F, "fe_static_ready(ctx, S_EuDownloadGuard) &&", ""),
    # the bonus bits: "bonus while carried" missing; the named weapons never, or always, added;
    # the bool tested on its low byte; the Brynhildr's bit left out
    (F, "    uint64_t wanted = guest_u64(ctx, S_IeCarryBonus);", "    uint64_t wanted = 0;"),
    (F, "    if (named_weapons != 0)\n        wanted |=", "    if (0)\n        wanted |="),
    (F, "    if (named_weapons != 0)\n        wanted |=", "    if (1)\n        wanted |="),
    (F, "    if (named_weapons != 0)\n        wanted |=", "    if ((named_weapons & 0xFFu) != 0)\n        wanted |="),
    (F, " | guest_u64(ctx, S_IeBrynhildr);", ";"),
    # no bonus bit answered yes
    (F, "    if ((flags & wanted) == 0)\n        return 0;", "    if ((flags & wanted) == 0)\n        return 1;"),
    # the combined "only for" test dropped (the owners always tried)
    (F, "    if ((flags & guest_u64(ctx, S_IeAnyOnly)) != 0) {", "    if (1) {"),
    # the flag word not read again for each owner
    (F, "            if (k > 0)\n                flags = READ_FIELD(ctx, ItemData, data, flags);\n", ""),
    # the owners' pairs crossed (Takumi's item bit with Ryoma's PersonFlag bit); the last owner dropped
    (F, "{S_IeTakumiOnly, S_IeTakumiFlag}, {S_IeRyomaOnly, S_IeRyomaFlag}",
     "{S_IeTakumiOnly, S_IeRyomaFlag}, {S_IeRyomaOnly, S_IeTakumiFlag}"),
    (H, "#define IE_OWNERS 6", "#define IE_OWNERS 5"),
    # an owner's item not held by its owner answered no (the game goes on to the sub-kind test)
    (F, "            if ((flags & guest_u64(ctx, owners[k].item_bit)) != 0 && held_by_owner(ctx, unit, owners[k].person_bit))\n                return 1;",
     "            if ((flags & guest_u64(ctx, owners[k].item_bit)) != 0)\n                return (uint32_t)held_by_owner(ctx, unit, owners[k].person_bit);"),
    # the unit's flags: the Person's or the class's word left out, cut to 32 bits
    (F, "    flags |= READ_FIELD(ctx, PersonData, person, flags);\n", ""),
    (F, "    flags |= READ_FIELD(ctx, JobData, job, flags);\n", "    (void)job;\n"),
    (F, "    if ((flags & guest_u64(ctx, person_bit)) == 0)", "    if (((uint32_t)flags & guest_u64(ctx, person_bit)) == 0)"),
    # state bit 28: wrong bit, test turned round; IsDownload not asked, or its answer read as a byte
    (H, "#define IE_UNIT_DOWNLOAD_ONLY 0x10000000u", "#define IE_UNIT_DOWNLOAD_ONLY 0x08000000u"),
    (F, "& IE_UNIT_DOWNLOAD_ONLY) == 0)\n        return 1;", "& IE_UNIT_DOWNLOAD_ONLY) != 0)\n        return 1;"),
    (F, "    return guest_call1(ctx, IE_PersonIsDownload, person) != 0;", "    return 0;"),
    (F, "    return guest_call1(ctx, IE_PersonIsDownload, person) != 0;",
     "    return (guest_call1(ctx, IE_PersonIsDownload, person) & 0xFFu) != 0;"),
    # the sub-kind: weapon_kind read unsigned, kind 7 instead of 8, the kind test dropped
    (F, "(uint32_t)(int32_t)READ_FIELD(ctx, ItemData, data, weapon_kind)", "(uint32_t)guest_u8(ctx, data + 0x1Au)"),
    (H, "#define IE_KIND_ALWAYS 8 ", "#define IE_KIND_ALWAYS 7 "),
    (F, "    if (READ_FIELD(ctx, ItemSubKindData, subkind, kind) == IE_KIND_ALWAYS)\n        return 1;\n",
     "    (void)subkind;\n"),
    # the equip test: its bools, and made a guest call (docs/MOVE.md 9: the live library inlines it)
    (F, "    return unit_can_equip_item(ctx, unit, item, 1u, 1u);", "    return unit_can_equip_item(ctx, unit, item, 1u, 0u);"),
    (F, "    return unit_can_equip_item(ctx, unit, item, 1u, 1u);", "    return unit_can_equip_item(ctx, unit, item, 0u, 1u);"),
    (F, "    return unit_can_equip_item(ctx, unit, item, 1u, 1u);",
     "    return guest_call(ctx, 0x0052C634u, unit, item, 1u, 1u);"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    """Each planted bug must give a mismatch; returns the number not caught."""
    lines, expected, _ = make_cases(text, n, seed, None)
    missed = 0
    for i, (fname, old, new) in enumerate(PLANTS, 1):
        # the copy keeps the folder layout (plant/src/item_enhance next to plant/src/equip_use) so
        # "../equip_use/equip_use.h" is found
        top = os.path.join(OUT, "plant", "src")
        d = os.path.join(top, "item_enhance")
        shutil.rmtree(top, ignore_errors=True)
        shutil.copytree(SRC_DIR, d, ignore=shutil.ignore_patterns("tests"))
        shutil.copytree(os.path.join(ROOT, "src", "readable", "equip_use"), os.path.join(top, "equip_use"),
                        ignore=shutil.ignore_patterns("tests", "*.c"))
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
        print("item_enhance_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("item_enhance_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_DIR)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"item_enhance_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, early) in per.items():
        total_bad += bad
        note = []
        if cold_n:
            note.append(f"{cold_n} cold: both gave up")
        if early:
            note.append(f"{early} early give-ups (a CanItemEquip cache cold, tail not reached; safe)")
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(note)})" if note else ""))
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    own = sum(1 for g in OWN_GUARDS if COLD_SEEN.get(g))
    eq = sum(1 for g in EQUIP_GUARDS if COLD_SEEN.get(g))
    print(f"item_enhance_diff: guards made cold alone: {own}/{len(OWN_GUARDS)} own, {eq}/{len(EQUIP_GUARDS)} CanItemEquip's")
    print("item_enhance_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("item_enhance_diff: paths met")
    for name, p in PATHS.items():
        for k, v in sorted(p.items()):
            print(f"  {k}: {v}")
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"item_enhance_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"item_enhance_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
