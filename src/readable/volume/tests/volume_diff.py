#!/usr/bin/env python3
"""Host differential test of the volume batch against the game's own ARM code.

    python src/readable/volume/tests/volume_diff.py            300 cases per function
    python src/readable/volume/tests/volume_diff.py -n 1500 --seed 7   the long run
    python src/readable/volume/tests/volume_diff.py --plant    also plant bugs: each must be caught

The method of src/readable/female/tests/female_diff.py and shop_grey_diff.py (the C driver body of
src/readable/sheet/tests/sheet_diff.py, the ARM interpreter src/readable/battle/tests/arm_mini.py): the
test makes up guest states (an option line with its class table, the options block GameConfigData behind
G_GameConfig 0x006DA0F8 and its four volume bytes; all random test values, never game data, and on
purpose often outside the ranges the game uses: the byte 0xFE, 0xFF and every other value, a class table
whose GetMax slot holds a made-up function, GetMax answers of 0, 1, 255, 256, 257, negative ones and the
most negative int besides the game's 32, an options pointer of 0, unmapped, or missing), runs the
ORIGINAL ARM code of the four Volume*::GetValue from the owner's extracted/text.bin in arm_mini.py and the
readable C functions (built with the host gcc against tools/readable/stub/) on the same memory, and
compares r0, the number of bytes read from unmapped memory AND the list of guest calls, in order, with
their arguments (docs/DECISIONS.md F-018).

The only callee is the line's virtual GetMax (class table +0x94): VolumeItemBase::GetMax 0x003BB3F8 in
every table of the game, or one of two made-up functions; one table answers both sides and lists the
call. When the byte is 0xFF the original reaches GetMax by a tail call (bx r1); arm_mini does not stub
a plain branch, so ListingCpu below answers and lists a branch to a stubbed address as a call. The
signed division the bodies make (RVCT's 0x002FFA0C, and its division-by-zero handler 0x0013F8B4) runs
inside arm_mini: it is not a call of interest.

No early give-up is allowed anywhere (no function here reads a one-time cache).

--plant copies src/readable/volume/ to build/readable/volume/plant/, makes one small wrong change at a
time (PLANTS below), rebuilds and reruns: every planted bug must give at least one mismatch. Changes
that cannot change any answer are listed in docs/VOLUME.md and not planted.

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
OUT = os.path.join(ROOT, "build", "readable", "volume")
SRC_DIR = os.path.join(ROOT, "src", "readable", "volume")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000

# ------------------------------------------------------------------ addresses
BGM, SE, SYS_SE, VOICE = 0x003BCA4C, 0x003BC7C4, 0x003BB078, 0x003BB168
GET_MAX = 0x003BB3F8                      # VolumeItemBase::GetMax (returns 32 in the game)
FAKES = (0x0BAD3000, 0x0BAD3004, 0x0BAD3008, 0x0BAD300C)  # made-up functions a class table may hold
LEAF_STUBS = {GET_MAX: 1, **{f: 1 for f in FAKES}}
ARITY = dict(LEAF_STUBS)

OVERRIDES = {"volume_bgm_value": BGM, "volume_se_value": SE,
             "volume_sys_se_value": SYS_SE, "volume_voice_value": VOICE}
ADDR = dict(OVERRIDES)
FIELD = {"volume_bgm_value": 0x10, "volume_se_value": 0x11, "volume_sys_se_value": 0x12,
         "volume_voice_value": 0x13}

G_CONFIG = 0x006DA0F8
SLOT = 0x94                                # src/readable/volume/volume.h VOL_SLOT_GET_MAX

# guest layout of the made-up state
ITEM = lambda k: 0x08020000 + k * 0x40  # noqa: E731  option lines
TABLE = lambda k: 0x08030000 + k * 0x100  # noqa: E731  their class tables
CFG = 0x08040000                         # GameConfigData
NITEMS, NTABLES = 3, 3
UNMAPPED = [0, 0x40, 0x7FF0, 0x0FFF0000]
INT_MIN, INT_MAX = -0x80000000, 0x7FFFFFFF
MAXES_ODD = [0, 1, 2, 3, 7, 8, 16, 31, 33, 64, 100, 128, 255, 256, 257, 1000, -1, -2, -8, -32, -255,
             -256, -257, INT_MIN, INT_MAX]
BYTES = [0, 0, 1, 7, 8, 9, 15, 16, 100, 127, 128, 200, 247, 248, 253, 254, 254, 255, 255, 255, 255]


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def u32(st, addr: int) -> int:
    return int.from_bytes(bytes(st.mem.get(addr + i, 0) for i in range(4)), "little")


def ostub(st, func: int, *args: int, value: int) -> None:
    st.oracle[(func,) + tuple(s32(a) for a in args[:LEAF_STUBS[func]])] = s32(value)


# ------------------------------------------------------------------ the made-up state
def gen_for(name: str):
    def gen(rng):
        st = State(rng)
        st.zero(SP - 0x400, 0x800)
        st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
        for k in range(NTABLES):
            t = TABLE(k)
            st.fill(t, 0x100)
            # the neighbouring slots hold other made-up functions: a wrong slot is seen
            st.put(t + SLOT - 4, 4, FAKES[2])
            st.put(t + SLOT + 4, 4, FAKES[3])
            st.put(t + SLOT, 4, GET_MAX if rng.random() > 0.2 else rng.choice(FAKES[:2]))
        for k in range(NITEMS):
            st.fill(ITEM(k), 0x40)
            st.put(ITEM(k), 4, TABLE(rng.randrange(NTABLES)))  # a junk table would call into junk
        st.fill(CFG, 0x40)
        for off in range(0x10, 0x14):  # the other lines' bytes differ: a wrong field is seen
            st.put(CFG + off, 1, rng.choice(BYTES) if rng.random() < 0.7 else rng.randrange(256))
        r = rng.random()
        if r < 0.85:
            st.put(G_CONFIG, 4, CFG)
        elif r < 0.95:
            st.put(G_CONFIG, 4, rng.choice(UNMAPPED))
        # else the word itself is missing (its page unmapped)
        item = ITEM(rng.randrange(NITEMS))
        game = rng.random() < 0.6  # the game's own answer, 32, for every function
        for f in LEAF_STUBS:
            ostub(st, f, item, value=32 if game and f == GET_MAX else pick(rng, [32], MAXES_ODD, 0.75))
        return st, f"ov:0x{ADDR[name]:08X}", [item, rng.getrandbits(32), 0, 0], ("call", ADDR[name], None)
    return gen


FUNCS = {name: gen_for(name) for name in OVERRIDES}


# ------------------------------------------------------------------ the ARM side
class ListingCpu(A.Cpu):
    """arm_mini's Cpu, listing every BL/BLX to a callee of ARITY with its argument registers, and
    answering a plain branch (the tail call bx r1) to a stubbed address as a call that returns to lr."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.listed: list[str] = []

    def call(self, target: int, ret: int) -> bool:
        if target in ARITY:
            self.listed.append(call_text(target, self.r[:ARITY[target]]))
        return super().call(target, ret)

    def run(self, pc: int, stop: set[int] | None = None, limit: int = 200000) -> int:
        self.r[15] = pc
        stop = stop or set()
        while True:
            pc = self.r[15]
            if pc == A.RETURN_SENTINEL or pc in stop:
                return pc
            if pc in self.stubs:  # reached by a branch, not a call: a tail call
                self.call(pc, self.r[14])
                continue
            self.steps += 1
            if self.steps > limit:
                raise A.Unsupported("step limit")
            ins = self.mem.read(pc, 4)
            self.r[15] = (pc + 4) & A.MASK
            self.step(ins, pc)

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
/* Generated by src/readable/volume/tests/volume_diff.py: runs the
   volume batch on memory images read from stdin and prints its results. Test values only. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "volume.h"
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
    src = os.path.join(out, "volume_driver.c")
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(driver_text())
    others = []
    for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
        if os.path.normcase(os.path.abspath(dp)).startswith(os.path.normcase(SRC_DIR)):
            continue
        others += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    mine = [os.path.join(my_dir, f) for f in sorted(os.listdir(my_dir)) if f.endswith(".c")] + [src]
    exe = os.path.join(out, "volume_driver.exe" if os.name == "nt" else "volume_driver")
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
        raise SystemExit("volume_diff: building the C driver failed:\n" + "\n".join(bad))
    for s, obj, _f, shared in jobs:
        if shared:
            _SHARED_OBJS[s] = obj
    objs = [_SHARED_OBJS[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
    r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"volume_diff: linking the C driver failed:\n{r.stdout}{r.stderr}")
    return exe


PATHS: dict[str, dict] = {}  # what the cases met (printed as evidence)


def note_path(name: str, st, args: list[int], exp: list) -> None:
    p = PATHS.setdefault(name, {})
    if exp[0] == 1:
        key = "gave up"
    else:
        cfg = u32(st, G_CONFIG) if G_CONFIG in st.mem else None
        if cfg is None:
            where = "options word missing"
        elif cfg != CFG:
            where = "options pointer unmapped"
        else:
            byte = st.mem[CFG + FIELD[name]]
            where = "byte 0xFF (tail call)" if byte == 0xFF else "byte 0xFE" if byte == 0xFE else "byte < 0xFE"
        target = u32(st, u32(st, args[0]) + SLOT)
        mx = st.oracle.get((target, s32(args[0])), 0)
        mx = mx - (1 << 32) if mx >> 31 else mx
        kind = "max 32" if mx == 32 else "max 0" if mx == 0 else "max < 0" if mx < 0 else \
            "max > 256" if mx > 256 else "other max"
        key = f"{where}/{kind}"
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
        raise SystemExit(f"volume_diff: the C driver failed ({r.returncode}):\n{r.stderr}")
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
F = "volume.c"
H = "volume.h"
PLANTS = [
    # ---- the class table: the neighbouring slot (each holds another made-up function)
    (H, "#define VOL_SLOT_GET_MAX 0x94u", "#define VOL_SLOT_GET_MAX 0x90u"),
    (H, "#define VOL_SLOT_GET_MAX 0x94u", "#define VOL_SLOT_GET_MAX 0x98u"),
    # GetMax's argument: not the line
    (F, "        return (int32_t)guest_call1(ctx, get_max, item);", "        return (int32_t)guest_call1(ctx, get_max, 0u);"),
    (F, "    int32_t max = (int32_t)guest_call1(ctx, get_max, item);", "    int32_t max = (int32_t)guest_call1(ctx, get_max, 0u);"),
    # ---- the "full" byte: 0xFE also full, 0xFF not full, the game's 32 answered without the call
    (H, "#define VOL_FULL 0xFFu", "#define VOL_FULL 0xFEu"),
    (F, "    if (stored >= VOL_FULL)", "    if (stored > VOL_FULL)"),
    (F, "        return (int32_t)guest_call1(ctx, get_max, item);", "        return 32;"),
    # ---- the division: the range, the order, the steps (max instead of 256 / max), unsigned
    (H, "#define VOL_BYTE_RANGE 0x100", "#define VOL_BYTE_RANGE 0xFF"),
    (F, "    return rvct_div((int32_t)stored, step);", "    return rvct_div(step, (int32_t)stored);"),
    (F, "    int32_t step = rvct_div(VOL_BYTE_RANGE, max);", "    int32_t step = max;"),
    (F, "    return a / b;", "    return (int32_t)((uint32_t)a / (uint32_t)b);"),
    (F, "    if (b == 0)\n        return 0;", "    if (b == 0)\n        return a;"),
    # the byte read signed
    (F, "    stored = guest_u8(ctx, guest_ptr(ctx, G_GameConfig) + (gaddr)field);",
     "    stored = (uint32_t)(int32_t)guest_s8(ctx, guest_ptr(ctx, G_GameConfig) + (gaddr)field);"),
    # the byte not read again after the call (the unmapped reads differ)
    (F, "    stored = guest_u8(ctx, guest_ptr(ctx, G_GameConfig) + (gaddr)field);\n", ""),
    # the options block read at its pointer's address (no pointer load)
    (F, "    uint32_t stored = guest_u8(ctx, guest_ptr(ctx, G_GameConfig) + (gaddr)field);",
     "    uint32_t stored = guest_u8(ctx, G_GameConfig + (gaddr)field);"),
    # ---- each line's own byte
    (F, "    return volume_value(ctx, item, offsetof(GameConfigData, volume_bgm));",
     "    return volume_value(ctx, item, offsetof(GameConfigData, volume_se));"),
    (F, "    return volume_value(ctx, item, offsetof(GameConfigData, volume_se));",
     "    return volume_value(ctx, item, offsetof(GameConfigData, volume_sys_se));"),
    (F, "    return volume_value(ctx, item, offsetof(GameConfigData, volume_sys_se));",
     "    return volume_value(ctx, item, offsetof(GameConfigData, volume_voice));"),
    (F, "    return volume_value(ctx, item, offsetof(GameConfigData, volume_voice));",
     "    return volume_value(ctx, item, offsetof(GameConfigData, volume_bgm));"),
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
        print("volume_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
        return 0
    cc = find_cc()
    if not cc:
        print("volume_diff: SKIPPED (no host C compiler; set FE_HOST_CC)")
        return 0
    text = open(TEXT, "rb").read()
    exe = build_driver(cc, OUT, SRC_DIR)
    lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
    per = compare(exe, cc, lines, expected, a.show)
    total_bad = sum(unsupported.values())
    print(f"volume_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, "
          f"seed {a.seed}")
    for name, (n, bad, cold_n, _early) in per.items():
        total_bad += bad
        note = f"  ({cold_n} cold: both gave up at entry)" if cold_n else ""
        print(f"  {name:30s} {n:5d} cases  {bad:3d} mismatches{note}")
    for name, k in unsupported.items():
        print(f"  {name:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
    print("volume_diff: what the cases exercised (original's results, cases that did not give up)")
    for name, cov in COVERAGE.items():
        print(f"  {name:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
              f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
    print("volume_diff: paths met")
    for name, p in PATHS.items():  # the byte's path and the GetMax answer, counted apart
        for part in (0, 1):
            tally: dict[str, int] = {}
            for k, v in p.items():
                tally[k.split("/")[part]] = tally.get(k.split("/")[part], 0) + v
            print(f"  {name if part == 0 else '':30s} " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())))
    missed = 0
    if a.plant:
        missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
        print(f"volume_diff: planted bugs: {len(PLANTS) - missed}/{len(PLANTS)} caught")
    ok = not total_bad and not missed
    print(f"volume_diff: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, "
          f"{total_bad} mismatches" + (f", {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught" if a.plant else "")
          + ")")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
