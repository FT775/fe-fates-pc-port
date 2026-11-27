#!/usr/bin/env python3
"""Shared machinery of the small host differential tests (round 17: the files that had no host test).

Not run on its own. A test script (src/readable/ai/tests/ai_value_diff.py, src/readable/event/tests/flags_diff.py,
src/readable/unit/tests/forces_diff.py) defines its functions, generators and planted bugs and calls install():
this module then gives it the same entry points every batch diff script has (TEXT, find_cc, build_driver,
make_cases, compare, plant), so tools/harness/h6host.py can run its planted copies too.

The method is the one of src/readable/shop_price/tests/shop_price_diff.py: made-up guest states (test values
only, never game data, often outside the ranges the game uses), the ORIGINAL ARM code from the owner's
extracted/text.bin run in arm_mini.py, the readable C function built with the host gcc against
tools/readable/stub/ (the C driver body of src/readable/sheet/tests/sheet_diff.py), on the same memory; r0,
the number of bytes read from unmapped memory and the list of guest calls (none expected: these functions
call nothing) are compared. No early give-up is allowed (none of these functions reads a one-time cache), and
neither side may write guest memory outside the ARM stack.
"""
from __future__ import annotations

import os
import random
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
for _p in (HERE, os.path.join(ROOT, "src", "readable", "sheet", "tests"), os.path.join(ROOT, "tools", "readable")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import arm_mini as A  # noqa: E402
from stance_diff import State, pick  # noqa: E402,F401  (re-exported for the scripts)

TEXT = os.path.join(ROOT, "extracted", "text.bin")
GUARD = 0x00302C6C  # __cxa_guard_acquire (Thumb), config/readable/addresses.json
SP = 0x0FFFF000
UNMAPPED = [2, 0x40, 0x7FF0, 0x0FFF0000]  # never inside text.bin (0x00100000 ..), never mapped by a case


def s32(v: int) -> int:
    return v & 0xFFFFFFFF


def sx(v: int, bits: int) -> int:
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


def base_state(rng) -> State:
    st = State(rng)
    st.zero(SP - 0x400, 0x800)
    st.fill(SP - 0x400, 0x400)  # the dead stack below sp holds junk
    return st


def install(g: dict) -> None:
    """Fills a test script's globals. The script defines NAME (e.g. "flags_diff"), SRC_DIR (its batch folder),
    FILES (the .c files of that folder under test), HEADER (the #include line of its driver), OVERRIDES
    (function name -> guest address), FUNCS (function name -> generator: rng -> (state, [args])), optionally NOT_LISTED (callees that 3dsrecomp keeps inside
    the calling function, so the readable C makes no guest call for them: arm_mini runs them, unlisted), PLANTS
    ((file, exact text, replacement), each text once in its file) and OUT (its build folder)."""
    name, src_dir, files = g["NAME"], g["SRC_DIR"], tuple(g["FILES"])
    not_listed = set(g.get("NOT_LISTED", ()))  # callees that run inside the function in the recompiled game
    overrides, funcs, out_dir = g["OVERRIDES"], g["FUNCS"], g["OUT"]
    shared_objs: dict[str, str] = {}
    paths: dict[str, dict] = {}
    coverage: dict[str, dict] = {}
    g["TEXT"], g["SP"], g["PATHS"], g["COVERAGE"] = TEXT, SP, paths, coverage
    g.setdefault("CACHE_OBJECTS", False)  # set by the script's own main (not by h6host, which caches itself)

    def arm_run(text: bytes, st, args: list[int], addr: int) -> list:
        mem = A.Memory(text)
        for a, d in st.regions():
            mem.map(a, d)
        calls: list[str] = []

        class Cpu(A.Cpu):
            def call(self, target: int, ret: int) -> bool:  # any guest call is listed (none expected)
                if target not in not_listed:
                    calls.append(f"{target:x}" + "".join(f":{r & 0xFFFFFFFF:x}" for r in self.r[:4]))
                return super().call(target, ret)
        cpu = Cpu(mem, {}, guard=GUARD)
        cpu.r[13], cpu.r[14] = SP, A.RETURN_SENTINEL
        for i in range(4):
            cpu.r[i] = args[i] & 0xFFFFFFFF
        try:
            cpu.run(addr)
        except A.ColdGuard:
            return [1]
        stray = [w for w in mem.writes if not SP - 0x400 <= w[0] < SP]
        if stray:
            raise A.Unsupported(f"the original wrote guest memory outside its stack: {stray[:3]}")
        return [0, cpu.r[0], mem.faults, ",".join(calls) if calls else "-"]

    def driver_text() -> str:
        import sheet_diff as S  # the same driver body: page memory, call list, oracle, nested give-ups
        body = S.DRIVER.split('#include "sheet.h"\n', 1)[1]
        addrs = sorted(set(overrides.values()))
        decls = "".join(f"void override_0x{a:08X}(Context *);\n" for a in addrs)
        table = "static const struct { uint32_t a; void (*f)(Context *); } ovs[] = {\n" + "".join(
            f"    {{0x{a:08X}u, override_0x{a:08X}}},\n" for a in addrs) + "};\n"
        head = (f"\n/* Generated by src/readable/{os.path.relpath(g['__file__'], os.path.join(ROOT, 'src', 'readable'))}"
                .replace("\\", "/") + ": runs readable functions on memory images read from stdin and prints\n"
                "   their results. Test values only. */\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n"
                + g["HEADER"] + "\n")
        return head + body.replace("@OVERRIDE_DECLS@", decls + table)

    def find_cc() -> str | None:
        import check  # tools/readable/check.py: the same compiler search
        return check.find_cc()

    def build_driver(cc: str, out: str, batch_dir: str, strict: bool = True) -> str:
        """The driver with every source of src/readable/, this batch folder's taken from batch_dir (a copy,
        perhaps with one planted bug; not strict then). One compiler command (the form h6host.py caches), or,
        in the script's own --plant run, the other areas compiled once and reused."""
        os.makedirs(out, exist_ok=True)
        src = os.path.join(out, f"{name}_driver.c")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(driver_text())
        # the files under test from batch_dir; every other source (this folder's others too: their includes
        # may climb out of the folder, e.g. "../sheet/sheet.h") from src/readable itself
        mine = [os.path.join(batch_dir, f) for f in files]
        skip = {os.path.normcase(os.path.join(src_dir, f)) for f in files}
        others = []
        for dp, _dn, fn in os.walk(os.path.join(ROOT, "src", "readable")):
            if os.path.basename(dp) == "tests":
                continue
            others += [os.path.join(dp, f) for f in fn
                       if f.endswith(".c") and os.path.normcase(os.path.join(dp, f)) not in skip]
        exe = os.path.join(out, f"{name}_driver.exe" if os.name == "nt" else f"{name}_driver")
        inc = ["-I", batch_dir, "-I", src_dir, "-I", os.path.join(ROOT, "tools", "readable", "stub"),
               "-I", os.path.join(ROOT, "include", "readable"),
               "-I", os.path.join(ROOT, "include", "readable", "generated")]
        warn = ["-Wall", "-Wextra", "-Werror"] if strict else ["-w"]
        base = ["-std=c11", "-O1", "-fwrapv"]
        env = dict(os.environ)
        env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
        if not g["CACHE_OBJECTS"]:
            cmd = [cc] + base[:1] + warn + base[1:] + inc + [src] + sorted(others) + mine + ["-o", exe]
            r = subprocess.run(cmd, capture_output=True, text=True, env=env)
            if r.returncode:
                raise SystemExit(f"{name}: building the C driver failed:\n{r.stdout}{r.stderr}")
            return exe
        from concurrent.futures import ThreadPoolExecutor
        shared_dir = os.path.join(out_dir, "obj_shared")
        own_dir = os.path.join(out, "obj")
        os.makedirs(shared_dir, exist_ok=True)
        os.makedirs(own_dir, exist_ok=True)
        jobs = []
        for s in sorted(others):
            if s not in shared_objs:
                rel = os.path.relpath(s, os.path.join(ROOT, "src", "readable")).replace(os.sep, "_")
                jobs.append((s, os.path.join(shared_dir, rel[:-2] + ".o"), base + ["-Wall", "-Wextra", "-Werror"] + inc,
                             True))
        for s in mine + [src]:
            jobs.append((s, os.path.join(own_dir, os.path.basename(s)[:-2] + ".o"), base + warn + inc, False))

        def comp(j):
            r = subprocess.run([cc] + j[2] + ["-c", j[0], "-o", j[1]], capture_output=True, text=True, env=env)
            return f"{j[0]}:\n{r.stdout}{r.stderr}" if r.returncode else None
        with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1)) as pool:
            errs = [e for e in pool.map(comp, jobs) if e]
        if errs:
            raise SystemExit(f"{name}: building the C driver failed:\n" + "\n".join(errs))
        for s, obj, _f, shared in jobs:
            if shared:
                shared_objs[s] = obj
        objs = [shared_objs[s] for s in sorted(others)] + [j[1] for j in jobs if not j[3]]
        r = subprocess.run([cc] + objs + ["-o", exe], capture_output=True, text=True, env=env)
        if r.returncode:
            raise SystemExit(f"{name}: linking the C driver failed:\n{r.stdout}{r.stderr}")
        return exe

    def make_cases(text: bytes, n: int, seed: int, only: str | None):
        rng = random.Random(seed)
        lines: list[str] = []
        expected: dict[int, tuple[str, list, tuple]] = {}
        unsupported: dict[str, int] = {}
        cid = 0
        for fname, gen in funcs.items():
            if only and fname != only:
                continue
            for _ in range(n):
                st, args = gen(rng)
                args = list(args) + [0] * (4 - len(args))
                addr = overrides[fname]
                kind = f"ov:0x{addr:08X}"
                try:
                    exp = arm_run(text, st, args, addr)
                except A.Unsupported as e:
                    unsupported[fname] = unsupported.get(fname, 0) + 1
                    if unsupported[fname] == 1:
                        print(f"  ARM interpreter: {fname}: {e}")
                    continue
                if "note_path" in g:
                    key = g["note_path"](fname, st, args, exp)
                    p = paths.setdefault(fname, {})
                    p[key] = p.get(key, 0) + 1
                expected[cid] = (fname, exp, (kind, args))
                lines.append(f"case {cid} {kind} " + " ".join(f"{x & 0xFFFFFFFF:x}" for x in args) + f" {SP:x}")
                for a, data in st.regions():
                    for off in range(0, len(data), 4096):
                        lines.append(f"mem {a + off:x} {data[off:off + 4096].hex()}")
                lines.append("run")
                cid += 1
        return lines, expected, unsupported

    def parse(tok: str):
        try:
            return int(tok)
        except ValueError:
            return tok

    def compare(exe: str, cc: str, lines: list[str], expected: dict, show: int, quiet: bool = False):
        log = os.path.join(os.path.dirname(exe), "fe_readable.log")
        env = dict(os.environ, FE_READABLE_LOG=log,
                   PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
        r = subprocess.run([exe], input="\n".join(lines) + "\n", capture_output=True, text=True, env=env)
        if r.returncode:
            raise SystemExit(f"{name}: the C driver failed ({r.returncode}):\n{r.stderr}")
        got: dict[int, list] = {}
        flagged: dict[int, str] = {}
        for ln in r.stdout.split("\n"):
            parts = ln.split()
            if len(parts) >= 2 and parts[1] in ("WROTE-GUEST", "NO-OVERRIDE", "NESTED-GIVEUP"):
                flagged[int(parts[0])] = parts[1]
            elif parts:
                got[int(parts[0])] = [parse(x) for x in parts[1:4]] + parts[4:]
        per: dict[str, list[int]] = {}
        for c, (fname, exp, inputs) in expected.items():
            res = per.setdefault(fname, [0, 0, 0])  # cases, mismatches, gave-up cases
            res[0] += 1
            gv = got.get(c)
            if exp[0] == 0:
                cov = coverage.setdefault(fname, {"values": set(), "nonzero": 0, "faulty": 0, "calls": 0})
                cov["values"].add(exp[1])
                cov["nonzero"] += int(exp[1] != 0)
                cov["faulty"] += int(exp[2] != 0)
                cov["calls"] += 0 if exp[3] == "-" else exp[3].count(",") + 1
            else:
                res[2] += 1
                exp = [1, 0]
            if gv is None or gv != exp or c in flagged:
                res[1] += 1
                if res[1] <= show and not quiet:
                    why = f" ({flagged[c]})" if c in flagged else ""
                    print(f"  MISMATCH {fname} case {c}: original {exp}, readable {gv}{why}; {inputs[0]} "
                          + " ".join(f"{x & 0xFFFFFFFF:#x}" for x in inputs[1]))
        return per

    def plant(text: bytes, cc: str, n: int, seed: int) -> int:
        """Each planted bug must give a mismatch; returns the number not caught."""
        lines, expected, _ = make_cases(text, n, seed, None)
        missed = 0
        for i, (fname, old, new) in enumerate(g["PLANTS"], 1):
            d = os.path.join(out_dir, "plant", "src")
            shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(src_dir, d, ignore=shutil.ignore_patterns("tests"))
            path = os.path.join(d, fname)
            body = open(path, encoding="utf-8").read()
            if body.count(old) != 1:
                print(f"  planted bug {i}: its text occurs {body.count(old)} times in {fname} (the list is stale)")
                missed += 1
                continue
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body.replace(old, new))
            try:
                exe = build_driver(cc, os.path.join(out_dir, "plant"), d, strict=False)
                per = compare(exe, cc, lines, expected, 0, quiet=True)
            except SystemExit as e:  # a planted bug that does not build proves nothing: the list is stale
                print(f"  planted bug {i:2d} ({fname}: {old.strip()[:48]!r}): NOT CAUGHT (did not build: "
                      f"{str(e).splitlines()[-1][:80]})")
                missed += 1
                continue
            bad = sum(v[1] for v in per.values())
            hit = [k for k, v in per.items() if v[1]]
            print(f"  planted bug {i:2d} ({fname}: {old.strip()[:48]!r}): "
                  + (f"caught, {bad} mismatches in {', '.join(hit[:4])}" if bad else "NOT CAUGHT"))
            missed += 0 if bad else 1
        return missed

    def run(a) -> int:
        """The script's main, after its argparse (kept in the script: h6host.py reads its -n / --seed defaults)."""
        if a.only and a.only not in funcs:
            print(f"unknown function {a.only}; one of: {', '.join(funcs)}")
            return 2
        if not os.path.isfile(TEXT):
            print(f"{name}: SKIPPED (extracted/text.bin is missing; extract the ROM first)")
            return 0
        cc = find_cc()
        if not cc:
            print(f"{name}: SKIPPED (no host C compiler; set FE_HOST_CC)")
            return 0
        g["CACHE_OBJECTS"] = True
        text = open(TEXT, "rb").read()
        exe = build_driver(cc, out_dir, src_dir)
        lines, expected, unsupported = make_cases(text, a.n, a.seed, a.only)
        per = compare(exe, cc, lines, expected, a.show)
        total_bad = sum(unsupported.values())
        print(f"{name}: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed {a.seed}")
        for fname, (n, bad, gave) in per.items():
            total_bad += bad + gave  # no function here may give up
            print(f"  {fname:30s} {n:5d} cases  {bad:3d} mismatches" + (f"  ({gave} gave up)" if gave else ""))
        for fname, k in unsupported.items():
            print(f"  {fname:30s} {k:5d} cases the ARM interpreter could not run (counted as failures)")
        print(f"{name}: what the cases exercised (original's results)")
        for fname, cov in coverage.items():
            print(f"  {fname:30s} {len(cov['values']):5d} distinct results, {cov['nonzero']} not 0, "
                  f"{cov['faulty']} with unmapped reads, {cov['calls']} guest calls listed")
        if paths:
            print(f"{name}: paths met")
            for fname, p in paths.items():
                print(f"  {fname:30s} " + ", ".join(f"{k} {v}" for k, v in sorted(p.items())))
        missed = 0
        nplants = len(g["PLANTS"])
        if a.plant:
            missed = plant(text, cc, a.plant_n or a.n, a.seed + 1)
            print(f"{name}: planted bugs: {nplants - missed}/{nplants} caught")
        ok = not total_bad and not missed
        print(f"{name}: {'OK' if ok else 'FAILED'} ({sum(v[0] for v in per.values())} cases, {total_bad} mismatches"
              + (f", {nplants - missed}/{nplants} planted bugs caught" if a.plant else "") + ")")
        return 0 if ok else 1

    g.update(arm_run=arm_run, driver_text=driver_text, find_cc=find_cc, build_driver=build_driver,
             make_cases=make_cases, compare=compare, plant=plant, run=run)
