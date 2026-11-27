#!/usr/bin/env python3
"""Host differential test of the strike reader (one strike's damage) against the game's own ARM code.

    python src/readable/strike/tests/strike_diff.py                 300 cases
    python src/readable/strike/tests/strike_diff.py -n 1500 --seed 7    the long run
    python src/readable/strike/tests/strike_diff.py --plant         also plant bugs: each must be caught

The method of src/readable/battle2/tests/battle2_diff.py (whose made-up fight sides this test borrows,
read only) and src/readable/item/tests/item_diff.py (the fifth argument word): strike_power, the whole
of map::BattleInfo::Side::GetSimplePower (0x005253A8), runs through its real override entry in a
generated driver; the ORIGINAL ARM code from the owner's extracted/text.bin runs in arm_mini.py on the
same memory. Compared: r0, the number of bytes read from unmapped memory AND the list of guest calls,
in order, with their argument registers (docs/DECISIONS.md F-018); Unit::GetStrImpl and GetPowImpl are
listed with their fifth argument, the word at sp (guest_call5), and the dead stack below sp holds junk,
so a fifth word stored in the wrong slot shows. The states are random test values, never game data,
and on purpose often outside the ranges the game uses (unmapped sides, units, records and terrain,
negative and huge numbers, skill numbers shared by two caches, negative skill numbers).

Guest functions answered by one table on both sides (listed and compared): unit::Item::ToData,
Item::IsMagic, Unit::GetAttack, Unit::GetStrImpl and Unit::GetPowImpl. On the ARM side each of them
raises "cold guard" while one of ITS OWN one-time caches is cold (the game's code would reach the
guard routine inside the call, and the readable override of that callee would give up inside this
one): so the readable code must give up before the call. A readable give-up before anything was read
is also allowed when a cache the readable code asks first is cold, or a callee's cache is cold for
the skill step that calls it (early_ok); any other early give-up is a mismatch.

--plant copies src/readable/strike/ to build/readable/strike/plant/, makes one small wrong change at a
time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch.

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
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "battle2", "tests"))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "sheet", "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import arm_mini as A  # noqa: E402
import battle2_diff as B  # noqa: E402  (the made-up fight sides; read only)
import sheet_diff as S  # noqa: E402  (the driver body)

TEXT = os.path.join(ROOT, "extracted", "text.bin")
OUT = os.path.join(ROOT, "build", "readable", "strike")
SRC_ST = os.path.join(ROOT, "src", "readable", "strike")
SP = B.SP
ADDRESS = 0x005253A8

TO_DATA, IS_MAGIC, GET_ATTACK, STR_IMPL, POW_IMPL = B.TO_DATA, B.IS_MAGIC, B.GET_ATTACK, B.STR_IMPL, B.POW_IMPL
LEAF_STUBS = dict(B.LEAF_STUBS)            # answered by r0..r3 on both sides
ARITY = dict(LEAF_STUBS)
ARITY[STR_IMPL] = ARITY[POW_IMPL] = 5      # listed with the fifth word (the rally kind at sp)

MAGIC_GUARD = 0x006D38D4                   # Item::IsMagic's own cache (item.h S_ItemMagicGuard)
STR_GUARDS, MAG_GUARDS = B.STAT_GUARDS[:4], B.STAT_GUARDS[4:]
EXP_GUARDS, SP_GUARDS, SP_SKILLS = B.EXP_GUARDS, B.SP_GUARDS, B.SP_SKILLS
STEPS = ("luna", "fang", "ignis", "rend", "venge", "astra")
s32, sx, word = B.s32, B.sx, B.word


def cold(st, guards) -> bool:
    return any(word(st, g) & 1 == 0 for g in guards)


def skill_numbers(st) -> dict:
    return {k: s32(sx(word(st, a, 2), 16)) for k, a in SP_SKILLS.items()}


# ------------------------------------------------------------------ the made-up cases
def gen(rng):
    st = B.base_state(rng)
    st.fill(SP - 0x400, 0x800)             # junk below sp (a fifth word in the wrong slot shows) and above it
                                           # (a fifth word never stored reads the caller's junk at sp)
    B.guard(st, MAGIC_GUARD)
    B.cool(st, SP_GUARDS + B.STAT_GUARDS + EXP_GUARDS + (MAGIC_GUARD,), 0.01)
    B.make_sides(st)
    a, b = rng.sample(range(4), 2)
    side = B.SIDE(a)
    other = B.SIDE(b) if rng.random() > 0.05 else rng.choice(B.UNMAPPED)
    names = list(STEPS) * 2
    skill = 0 if rng.random() < 0.25 else sx(word(st, SP_SKILLS[rng.choice(names)], 2), 16)
    if rng.random() < 0.05:
        skill = rng.choice([-1, 0x7FFFFFFF, 1000])
    item = s32(side + 0x10)
    st.oracle[(TO_DATA, item)] = B.ITEMDATA(rng.randrange(B.NITEMS)) if rng.random() > 0.05 else rng.choice(B.UNMAPPED)
    if rng.random() < 0.4:                 # the "pierces Dragonskin" flag on a weapon now and then
        k = rng.randrange(B.NITEMS)
        st.put(B.ITEMDATA(k), 8, word(st, B.ITEMDATA(k), 8) | word(st, B.SP_PIERCE, 8))
    if rng.random() < 0.6:
        zeroed, shared = focus(st, side, other, item)
        skill = rng.choice([0] + list(STEPS) * 2)
        skill = 0 if skill == 0 or zeroed else sx(word(st, SP_SKILLS[skill], 2), 16)
        if shared is not None and rng.random() < 0.7:
            skill = shared
        if rng.random() < 0.2:             # a getter's cache cold for the step that calls it
            step = rng.choice(["ignis", "rend", "fang"])
            skill = sx(word(st, SP_SKILLS[step], 2), 16)
            st.put(rng.choice((MAGIC_GUARD,) * 2 + B.STAT_GUARDS + (EXP_GUARDS if step == "fang" else ())), 4, 0)
    if rng.random() < 0.08:                # exactly one cache cold: each guard must be asked (or met) on its own
        st.put(rng.choice(SP_GUARDS + B.STAT_GUARDS + EXP_GUARDS + (MAGIC_GUARD,) * 4), 4, 0)
    answers(st, side, other, item)
    return st, [side, other, skill, B.odd_int(rng)]


def focus(st, side: int, other: int, item: int) -> None:
    """Most cases (returns whether a damage skill's cache was set to 0, and the number two caches share or None): every cache warm, distinct skill numbers (now and then two caches share one), a weapon
    that hits, small defenses so the damage is often above 0, the other side's Dragonskin and
    halve-damage bits set often in the row the striking side reads, so that every skill step meets each
    of them, with and without the piercing flag, a magic and a physical weapon."""
    rng = st.rng
    for g in SP_GUARDS + B.STAT_GUARDS + EXP_GUARDS + (MAGIC_GUARD,):
        if rng.random() > 0.02:
            st.put(g, 4, rng.choice([1, 0x101]))
    for a, v in zip(SP_SKILLS.values(), rng.sample(range(1, 40), len(SP_SKILLS))):
        st.put(a, 2, v)
    shared = None
    if rng.random() < 0.12:                # two damage skills share a number: both steps run
        x, y = rng.choice([("ignis", "rend"), ("fang", "ignis"), ("rend", "venge"), tuple(rng.sample(list(STEPS), 2))])
        st.put(SP_SKILLS[y], 2, word(st, SP_SKILLS[x], 2))
        shared = sx(word(st, SP_SKILLS[x], 2), 16)
    zeroed = rng.random() < 0.12           # a damage skill's cache holds 0: the forecast (skill 0) takes that step
    if zeroed:                             # (Astra more often: its step changes the most results)
        st.put(SP_SKILLS[rng.choice(STEPS + ("astra", "astra"))], 2, 0)
    st.put(side + 0x10, 2, rng.randrange(1, 1 << 16))
    st.put(side + 0x28, 4, word(st, side + 0x28) & ~0x40)
    if other not in B.UNMAPPED:
        row = B.detail_row(st, side)
        st.put(side + 0x48, 4, rng.randrange(20, 130))
        d = other + 0x48 + row * 0x24
        for f in (4, 8, 0xC, 0x10):
            st.put(d + f, 4, s32(rng.randrange(-3, 25)))
        bits = other + 0xE6 + row * 0x94
        for name, p in (("scale", 0.5), ("aegis", 0.25)):
            bit = sx(word(st, SP_SKILLS[name], 2), 16)
            addr = bits + (bit >> 3)
            on = rng.random() < p
            st.mem[addr] = (st.mem.get(addr, 0) | (1 << (bit & 7))) if on else (st.mem.get(addr, 0) & ~(1 << (bit & 7)))
        if rng.random() < 0.7:
            st.put(other + 0x20, 4, 0)
        if rng.random() < 0.15:            # the foe without a unit now and then
            st.put(other + 4, 4, 0)
    if rng.random() < 0.6:
        st.put(side + 0x28, 4, word(st, side + 0x28) & ~0x2)
    if rng.random() < 0.5:
        data = st.oracle.get((TO_DATA, item), B.ITEMDATA(0))
        if data not in B.UNMAPPED:
            st.put(data, 8, word(st, data, 8) | word(st, B.SP_PIERCE, 8))
    return zeroed, shared


def answers(st, side: int, other: int, item: int) -> None:
    """What the table-answered calls give in this case (both sides read the same table)."""
    rng = st.rng
    u = word(st, side + 4)
    for flag in (0, 1):
        st.oracle[(GET_ATTACK, u, item, flag)] = s32(B.odd_int(rng))
    data = st.oracle[(TO_DATA, item)]
    st.oracle[(IS_MAGIC, data)] = rng.choice([0, 1, 1, 2, 0x80000000]) if rng.random() < 0.9 else 0
    small = [0, 1, 3, 7, 12, 20, 31, 40]
    for getter in (STR_IMPL, POW_IMPL):
        st.oracle[(getter, u, item, 1, 1)] = s32(B.pick(rng, small, [-1, -9, 0x7FFFFFFF, -0x80000000], 0.1))
        if other not in B.UNMAPPED:
            fu = word(st, other + 4)
            st.oracle[(getter, fu, s32(other + 0x10), 1, 1)] = s32(B.pick(rng, small, [-1, -9, 0x7FFFFFFF], 0.1))
    for a in B.UNMAPPED:                   # a foe unit read from an unmapped side is 0
        for getter in (STR_IMPL, POW_IMPL):
            st.oracle.setdefault((getter, 0, s32(a + 0x10), 1, 1), s32(rng.choice(small)))


def early_ok(st, args: list[int]) -> bool:
    """Whether the readable code may give up before reading anything while the original runs on:
    a cache it asks first is cold (its own nine), or a callee's cache for the skill step that calls it
    (Ignis and Rend Heaven: IsMagic's and both stats'; Dragon Fang: those and the weapon-exp limit's)."""
    if cold(st, SP_GUARDS):
        return True
    skill, sk = s32(args[2]), skill_numbers(st)
    stats = (MAGIC_GUARD,) + B.STAT_GUARDS
    if skill in (sk["ignis"], sk["rend"]) and cold(st, stats):
        return True
    return skill == sk["fang"] and cold(st, stats + EXP_GUARDS)


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY with its arguments (past r3: the
    words at sp, as the callee sees them)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            n = ARITY[target]
            regs = list(self.r[:min(n, 4)]) + [self.mem.read(self.r[13] + 4 * k, 4) for k in range(n - 4)]
            self.listed.append(S.call_text(target, regs))
        return super().call(target, ret)


def arm_run(text: bytes, st, args: list[int]) -> list:
    """Expected outputs, in the order the C driver prints them: [gave_up, r0, faults, calls]."""
    mem = A.Memory(text)
    for a, d in st.regions():
        mem.map(a, d)
    callee_guards = {IS_MAGIC: lambda a: (MAGIC_GUARD,),
                     STR_IMPL: lambda a: STR_GUARDS, POW_IMPL: lambda a: MAG_GUARDS,
                     GET_ATTACK: lambda a: (MAGIC_GUARD,) + B.STAT_GUARDS + (EXP_GUARDS if a[2] else ())}

    def answer(f, n):
        def stub(cpu, a):
            g = callee_guards.get(f)
            if g is not None and cold(st, g(a)):
                raise A.ColdGuard()        # the callee would reach the guard routine (its override gives up)
            return st.oracle.get((f,) + tuple(x & 0xFFFFFFFF for x in a[:n]), 0)
        return stub
    cpu = ListingCpu(mem, {f: answer(f, n) for f, n in LEAF_STUBS.items()}, guard=B.GUARD)
    cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
    for i in range(4):
        cpu.r[i] = args[i] & 0xFFFFFFFF
    try:
        cpu.run(ADDRESS)
    except A.ColdGuard:
        return [1]
    stray = [w for w in mem.writes if not SP - 0x400 <= w[0] < SP]
    if stray:
        raise A.Unsupported(f"the original wrote guest memory outside its stack: {stray[:3]}")
    return [0, cpu.r[0], mem.faults, S.calls_field(cpu.listed)]


# ------------------------------------------------------------------ the C side
STACK_DRIVER_OLD = (
    "static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; writes++; uint8_t *p = at(a, 0); if (p) *p = v; }",
    "    for (uint32_t i = 0; i < n; i++) k += snprintf(buf + k, sizeof buf - (size_t)k, \":%x\", r[i]);",
    "            c.r[13] = a[4];",
    "    char buf[96];",
)
STACK_DRIVER_NEW = (
    # a store into the dead stack (the 0x400 bytes below the case's sp) is the fifth argument word of a
    # guest_call5, not a write of guest data: counted apart, never as WROTE-GUEST
    "static uint32_t stack_top; static int stack_writes;\n"
    "static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; if (a < stack_top && a >= stack_top - 0x400u) "
    "stack_writes++; else writes++; uint8_t *p = at(a, 0); if (p) *p = v; }",
    "    for (uint32_t i = 0; i < n; i++) k += snprintf(buf + k, sizeof buf - (size_t)k, \":%x\", "
    "i < 4 ? r[i] : r32(NULL, r[13] + 4u * (i - 4u)));",
    "            c.r[13] = a[4]; stack_top = a[4]; stack_writes = 0;",
    "    char buf[128];",
)


def driver_text() -> str:
    text = S.DRIVER.replace('#include "sheet.h"', '#include "strike.h"')
    text = text.replace("src/readable/sheet/tests/sheet_diff.py", "src/readable/strike/tests/strike_diff.py")
    for old, new in zip(STACK_DRIVER_OLD, STACK_DRIVER_NEW):
        if text.count(old) != 1:
            raise SystemExit(f"strike_diff: sheet_diff's driver changed, cannot patch: {old[:60]!r}")
        text = text.replace(old, new)
    decls = f"void override_0x{ADDRESS:08X}(Context *);\n"
    table = ("static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n"
             f"    {{0x{ADDRESS:08X}u, override_0x{ADDRESS:08X}}},\n}};\n")
    return text.replace("@OVERRIDE_DECLS@", decls + table)


_SHARED_OBJS: dict[str, str] = {}


def _compile(cc: str, src: str, obj: str, flags: list[str], env: dict) -> str | None:
    r = subprocess.run([cc] + flags + ["-c", src, "-o", obj], capture_output=True, text=True, env=env)
    return f"{src}:\n{r.stdout}{r.stderr}" if r.returncode else None


def build_driver(cc: str, out: str, st_dir: str, strict: bool = True) -> str:
    """The driver with every source of src/readable/, the strike folder's taken from st_dir (a planted
    bug may leave a parameter unused: not strict then). The other areas' objects are compiled once per
    run and reused for every planted bug."""
    from concurrent.futures import ThreadPoolExecutor
    os.makedirs(out, exist_ok=True)
    src = os.path.join(out, "strike_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_ST)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(st_dir, f) for f in sorted(os.listdir(st_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "strike_driver.exe" if os.name == "nt" else "strike_driver")
    inc = ["-I", st_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
           "-I", os.path.join(ROOT, "include", "readable"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    strict_warn = ["-Wall", "-Wextra", "-Werror"]
    base = ["-std=c11", "-O1", "-fwrapv"]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    shared_dir, own_dir = os.path.join(OUT, "obj_shared"), os.path.join(out, "obj")
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
    with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) // 2)) as pool:
        errs = list(pool.map(lambda j: _compile(cc, j[0], j[1], j[2], env), jobs))
    bad = [e for e in errs if e]
    if bad:
        raise SystemExit("strike_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"strike_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[tuple[str, bool], list[int]] = {}  # (skill step, Dragonskin) -> [cases, damage > 0]


def path_of(st, args: list[int], r0: int) -> None:
    side, other, skill = args[0], args[1], s32(args[2])
    sk = skill_numbers(st)
    names = [k for k in STEPS if sk[k] == skill]
    step = "+".join(names) if names and skill != 0 else "none"
    row = B.detail_row(st, side)
    bit = sx(word(st, SP_SKILLS["scale"], 2), 16)
    skin = bool(st.mem.get(other + 0xE6 + row * 0x94 + (bit >> 3), 0) >> (bit & 7) & 1)
    c = PATHS.setdefault((step, skin), [0, 0])
    c[0] += 1
    c[1] += int(r0 != 0)


def make_cases(text: bytes, n: int, seed: int, record: bool = True):
    rng = random.Random(seed)
    lines = [f"arity {f:x} {k}" for f, k in ARITY.items()]
    expected: dict[int, tuple] = {}
    unsupported = 0
    for cid in range(n):
        st, args = gen(rng)
        try:
            exp = arm_run(text, st, args)
        except A.Unsupported as e:
            unsupported += 1
            if unsupported == 1:
                print(f"  ARM interpreter: {e}")
            continue
        expected[cid] = (exp, args, early_ok(st, args))
        if record and exp[0] == 0:
            path_of(st, args, exp[1])
        lines.append(f"case {cid} ov:0x{ADDRESS:08X} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
        lines += [f"stub {f:x} {k}" for f, k in LEAF_STUBS.items()]
        for addr, data in st.regions():
            for off in range(0, len(data), 4096):
                lines.append(f"mem {addr + off:x} {data[off:off + 4096].hex()}")
        for key, val in st.oracle.items():
            if key[0] not in LEAF_STUBS:
                continue
            k = list(key) + [0] * (5 - len(key))
            lines.append("oracle " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in k[:5]) + f" {val & 0xFFFFFFFF:x}")
        lines.append("run")
    return lines, expected, unsupported


def parse(tok: str):
    try:
        return int(tok)
    except ValueError:
        return tok


COVERAGE = {"values": set(), "nonzero": 0, "faulty": 0, "calls": 0, "five": 0}


def compare(exe: str, cc: str, lines: list[str], expected: dict, show: int, quiet: bool = False) -> list[int]:
    env = dict(os.environ, FE_READABLE_LOG=os.path.join(os.path.dirname(exe), "fe_readable.log"),
               PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"strike_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
    got: dict[int, list] = {}
    flagged: dict[int, str] = {}
    for ln in r.stdout.split("\n"):
        parts = ln.split()
        if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE", "NESTED-GIVEUP"):
            flagged[int(parts[0])] = parts[1]
        elif parts:
            got[int(parts[0])] = [parse(x) for x in parts[1:4]] + parts[4:]
    res = [0, 0, 0, 0]  # cases, mismatches, gave-up cases, early give-ups
    for c, (exp, args, early) in expected.items():
        res[0] += 1
        g = got.get(c)
        if exp[0] == 0 and not quiet:
            COVERAGE["values"].add(exp[1])
            COVERAGE["nonzero"] += int(exp[1] != 0)
            COVERAGE["faulty"] += int(exp[2] != 0)
            COVERAGE["calls"] += 0 if exp[3] == "-" else exp[3].count(",") + 1
            COVERAGE["five"] += sum(exp[3].count(f"{f:x}:") for f in (STR_IMPL, POW_IMPL))
        if exp[0] == 1:
            res[2] += 1
            exp = [1, 0]
        elif g is not None and g == [1, 0] and c not in flagged and early:
            res[3] += 1
            continue
        if g is None or g != exp or c in flagged:
            res[1] += 1
            if res[1] <= show and not quiet:
                why = f" ({flagged[c]})" if c in flagged else ""
                print(f"  MISMATCH strike_power case {c}: original {exp}, readable {g}{why}; "
                      + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in args))
    return res


# planted bugs: (exact text in strike.c, replacement); each text occurs once
PLANTS = [
    # the caches: one own guard not asked; a callee's cache not asked (Ignis/Rend, Dragon Fang); over-eager
    ("           fe_static_ready(ctx, S_StScaleGuard) && fe_static_ready(ctx, S_StAegisGuard) &&\n",
     "           fe_static_ready(ctx, S_StScaleGuard) &&\n"),
    ("    if ((skill == ignis || skill == rend) && !stat_caches_ready(ctx))",
     "    if ((skill == ignis) && !stat_caches_ready(ctx))"),
    ("    return fe_static_ready(ctx, S_StMagicGuard) && unit_stat_caches_ready(ctx, ST_STAT_STR) &&",
     "    return unit_stat_caches_ready(ctx, ST_STAT_STR) &&"),
    ("           unit_stat_caches_ready(ctx, ST_STAT_MAG);\n}", "           1;\n}"),
    ("    return stat_caches_ready(ctx) && fe_static_ready(ctx, S_StExpLimitGuardA) &&",
     "    return fe_static_ready(ctx, S_StMagicGuard) && fe_static_ready(ctx, S_StExpLimitGuardA) &&"),
    ("    if (skill == fang && !attack_caches_ready(ctx))", "    if (skill == astra && !attack_caches_ready(ctx))"),
    # the two early returns
    ("    if (READ_FIELD(ctx, BattleSide, side, item) == 0)\n        return 0;", "    if (0)\n        return 0;"),
    ("    if (flags & ST_SIDE_FLAG_NO_DAMAGE)", "    if (flags & 0x10u)"),
    # the row and the base
    ("    return (type == 2 || type == 3) ? 1u : 0u;", "    return (type == 2) ? 1u : 0u;"),
    ("    gaddr guard = (flags & ST_SIDE_FLAG_MAGIC) ? FIELD_ADDR(BattleDetail, detail, resistance)",
     "    gaddr guard = (flags & ST_SIDE_FLAG_NO_DAMAGE) ? FIELD_ADDR(BattleDetail, detail, resistance)"),
    ("    int32_t attack = READ_FIELD(ctx, BattleSide, side, detail[0].attack);",
     "    int32_t attack = guest_s32(ctx, FIELD_ADDR(BattleSide, side, detail) + row * (gaddr)sizeof(BattleDetail));"),
    ("    damage = fe_add32(damage, -guest_s32(ctx, guard + 4u)); /* the bonus word after the stat */",
     "    damage = fe_add32(damage, -guest_s32(ctx, guard + 8u)); /* the bonus word after the stat */"),
    # Luna
    ("        damage = fe_add32(damage, fe_asr(defense, has_skin(ctx, bits) ? 2 : 1));",
     "        damage = fe_add32(damage, fe_asr(defense, 1));"),
    # Dragon Fang
    ("                                           triangle < 0 ? 0u : 1u);",
     "                                           triangle <= 0 ? 0u : 1u);"),
    ("        damage = fe_add32(damage, fe_asr(att, has_skin(ctx, bits) ? 2 : 1));",
     "        damage = fe_add32(damage, fe_asr(att, has_skin(ctx, bits) ? 1 : 2));"),
    # Ignis
    ("        int32_t stat = stat_of(ctx, magic ? ST_UnitGetStrImpl : ST_UnitGetPowImpl, unit,",
     "        int32_t stat = stat_of(ctx, magic ? ST_UnitGetPowImpl : ST_UnitGetStrImpl, unit,"),
    ("        damage = fe_add32(damage, fe_asr(stat, has_skin(ctx, bits) ? 2 : 1));",
     "        damage = fe_add32(damage, fe_asr(stat, 1));"),
    # Rend Heaven: the striking unit instead of the foe; the foe's item replaced by the own; skin ignored
    ("        gaddr foe = READ_FIELD(ctx, BattleSide, other, unit);",
     "        gaddr foe = READ_FIELD(ctx, BattleSide, side, unit);"),
    ("                               FIELD_ADDR(BattleSide, other, item));",
     "                               FIELD_ADDR(BattleSide, side, item));"),
    ("        damage = fe_add32(damage, fe_asr(stat, skin ? 2 : 1));",
     "        damage = fe_add32(damage, fe_asr(stat, skin ? 1 : 1));"),
    # the fifth word (rally kind) and the bools of the stat getters
    ("    return (int32_t)guest_call5(ctx, getter, unit, item, 1u, 1u, 0u);",
     "    return (int32_t)guest_call5(ctx, getter, unit, item, 1u, 1u, 1u);"),
    ("    return (int32_t)guest_call5(ctx, getter, unit, item, 1u, 1u, 0u);",
     "    return (int32_t)guest_call(ctx, getter, unit, item, 1u, 1u);"),
    ("    return (int32_t)guest_call5(ctx, getter, unit, item, 1u, 1u, 0u);",
     "    return (int32_t)guest_call5(ctx, getter, unit, item, 1u, 0u, 0u);"),
    # IsMagic's answer read as "equals 1"
    ("    return guest_call1(ctx, ST_ItemIsMagic, data) != 0;", "    return guest_call1(ctx, ST_ItemIsMagic, data) == 1;"),
    # Vengeance and Astra
    ("        damage = fe_add32(damage, has_skin(ctx, bits) ? fe_asr(vengeance, 1) : vengeance);",
     "        damage = fe_add32(damage, has_skin(ctx, bits) ? vengeance : fe_asr(vengeance, 1));"),
    ("            damage = fe_mul32(damage, ST_ASTRA_SKIN_PERCENT) / 100; /* toward zero, as the multiply-high does */",
     "            damage = fe_asr(fe_mul32(damage, ST_ASTRA_SKIN_PERCENT), 7);"),
    ("    if (skill == astra) {", "    if (skill == astra && skill != 0) {"),
    # the steps are separate ifs: an else-if chain would drop a shared number's second step
    ("    if (skill == rend) {", "    else if (skill == rend) {"),
    # Dragonskin, the pierce flag, the halve-damage bit, terrain
    ("            damage = fe_asr(fe_mul32(damage, 3), 2);", "            damage = fe_asr(damage, 1);"),
    ("        if (READ_FIELD(ctx, ItemData, data, flags) & guest_u64(ctx, S_StPierceMask))",
     "        if ((uint32_t)READ_FIELD(ctx, ItemData, data, flags) & (uint32_t)guest_u64(ctx, S_StPierceMask))"),
    ("    if (has_bit(ctx, bits, guest_s16(ctx, S_StAegis)))\n        damage = fe_asr(damage, 1);",
     "    if (has_bit(ctx, bits, guest_s16(ctx, S_StAegis)))\n        damage = fe_asr(damage, 2);"),
    ("    gaddr terrain = guest_ptr(ctx, other + ST_SIDE_TERRAIN); /* read once; its attributes twice */",
     "    gaddr terrain = guest_ptr(ctx, side + ST_SIDE_TERRAIN); /* read once; its attributes twice */"),
    ("        if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & ST_TERRAIN_ATTR_QUARTER)",
     "        if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & 0x800000u)"),
    # a negative skill number's bit (arithmetic shift) read as unsigned
    ("    return (guest_u8(ctx, bytes + (gaddr)fe_asr(bit, 3)) & (1u << (bit & 7))) != 0;",
     "    return (guest_u8(ctx, bytes + ((uint32_t)bit >> 3)) & (1u << (bit & 7))) != 0;"),
    # the last step skipped (no follower half, no floor)
    ("    return stance_follow_up_damage(ctx, side, damage);", "    return damage;"),
]


def plant(text: bytes, cc: str, n: int, seed: int) -> int:
    lines, expected, _ = make_cases(text, n, seed, record=False)
    missed = 0
    for i, (old, new) in enumerate(PLANTS, 1):
        d = os.path.join(OUT, "plant", "src")
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(SRC_ST, d, ignore=shutil.ignore_patterns("tests"))
        path = os.path.join(d, "strike.c")
        body = open(path, encoding="utf-8").read()
        if body.count(old) != 1:
            print(f"  planted bug {i}: its text occurs {body.count(old)} times in strike.c (the list is stale)")
            missed += 1
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body.replace(old, new))
        exe = build_driver(cc, os.path.join(OUT, "plant"), d, strict=False)
        res = compare(exe, cc, lines, expected, 0, quiet=True)
        print(f"  planted bug {i:2d} ({old.strip()[:56]!r}): " + (f"caught, {res[1]} mismatches" if res[1] else "NOT CAUGHT"))
        missed += 0 if res[1] else 1
    return missed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=300, help="cases (default 300)")
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument("--show", type=int, default=5, help="mismatches to print")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, help="cases for each planted bug (default: -n)")
    a = ap.parse_args(argv)
    if not os.path.isfile(TEXT):
        print("strike_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = S.find_cc()
    if not cc:
        print("strike_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_ST)
    lines, expected, unsupported = make_cases(text, a.n, a.seed)
    n, bad, cold_n, early = compare(exe, cc, lines, expected, a.show)
    bad += unsupported
    print(f"strike_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
    notes = ([f"{cold_n} cold: both reached / gave up at a cache"] if cold_n else []) + \
            ([f"{early} early give-ups"] if early else [])
    print(f"  {'strike_power':28s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({'; '.join(notes)})" if notes else ""))
    if unsupported:
        print(f"  {unsupported} cases the ARM interpreter could not run (counted as failures)")
    print(f"strike_diff: what the cases exercised: {len(COVERAGE['values'])} distinct results, "
          f"{COVERAGE['nonzero']} not 0, {COVERAGE['faulty']} with unmapped reads, {COVERAGE['calls']} guest calls "
          f"listed ({COVERAGE['five']} with a fifth word)")
    print("strike_diff: steps met (skill step / other side's Dragonskin: cases, damage > 0)")
    print("  " + ", ".join(f"{k[0]}/{'skin' if k[1] else 'no skin'} {v[0]}:{v[1]}" for k, v in sorted(PATHS.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"strike_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not bad and not missed
    print(f"strike_diff: {'OK' if ok else 'FAILED'} ({n} cases, {bad} mismatches"
          + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "") + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
