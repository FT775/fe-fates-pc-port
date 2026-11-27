#!/usr/bin/env python3
"""Check the readable layer (docs/READABLE.md, "Checks"). Standard library only.

    python tools/readable/check.py                  lint + generated headers + compile + host test
    python tools/readable/check.py --selftest       also: broken inputs must be rejected
    python tools/readable/check.py --no-compile     lint only (no C compiler needed)
    python tools/readable/check.py --verify-logs DIR
                                                    classify the outputs tools/readable/verify.py
                                                    wrote (one readable + one shadow run per
                                                    override, VERIFY_ONLY=<address>)

Lint (no compiler, no ROM):
  - config/readable/functions.csv: address 0x + 8 uppercase hex digits, a function start
    in config/functions.csv, even (ARM); kind override|helper|writer; status unverified |
    verified-unit | blocked | shadow-clean | verified (verified-unit and blocked only on
    overrides, blocked with 'blocked: <reason>' in evidence); source exists and defines
    the named function
  - every override marker in src/readable/ is in the registry with that source, appears
    once, and its body's FE_ENTRY names the same address literal and function
  - a writer (kind writer: a function that stores into the game only through the writer gate,
    docs/WRITERS.md) NEVER has an override marker: it runs only when a hook calls it and the gate
    lets it (armed in writer.c, listed in FE_WRITERS, readable mode); its evidence says WRITER and
    its source goes through the gate (fe_writer_*); a row whose evidence says WRITER is kind writer
  - no header in include/readable/ holds an override marker outside comments (staging
    pastes headers into each override file, where 3dsrecomp's scanner would see it)
  - no ARM disassembly in src/readable/ or include/readable/ (readable code is written,
    not copied from asm/)
  - a source with a function below shadow-clean says UNVERIFIED in its comments
  - src/readable/core/runtime.c exists and its FE_TRACKED (C suffixes allowed) is at
    least the number of override rows
  - include/readable/generated/ is up to date (tools/readable/gen_structs.py)
Compile (host gcc or clang; FE_HOST_CC overrides; SKIP when none is found):
  - each source, -std=c11 -Wall -Wextra -Wpedantic -Werror, against tools/readable/stub/
  - each staged file (tools/readable/stage.py) with only the stub on the include path
  - tools/readable/tests/host_test.c linked with every source, then run
  - tools/readable/tests/capture_test.c linked with src/readable/core/{capture,runtime}.c,
    then run in an emptied build/readable/hosttest/capture/ (capture mode, docs/HARNESS.md
    3.1: page copy before the first write, nesting, escapes, restore on every way out,
    live runs A and B, record writer, store-mode cleanup)
  - tools/readable/tests/undo_test.c linked with src/readable/core/{undo,capture,runtime}.c,
    then run (the undo log, H8 groundwork, not used by any mode yet: planted stores come
    back after a give-up at every depth, budget/unwind/svc/overflow exits, nested merge)

Prints `readable: OK` when everything ran and passed, `readable: N problem(s)` otherwise,
and `readable: OK (compile SKIPPED: ...)` when only the compiler was missing.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

SRC = os.path.join(ROOT, "src", "readable")
INC = os.path.join(ROOT, "include", "readable")
GEN = os.path.join(INC, "generated")
STUB = os.path.join(HERE, "stub")
REGISTRY = os.path.join(ROOT, "config", "readable", "functions.csv")
FUNCTIONS = os.path.join(ROOT, "config", "functions.csv")
BUILD = os.path.join(ROOT, "build", "readable")

ADDR_RX = re.compile(r"0x[0-9A-F]{8}")
IDENT = re.compile(r"[A-Za-z_]\w*")
# tier order (READABLE.md rule 8); "blocked" = tier 2 cannot test it, reason in evidence
STATUSES = ("unverified", "verified-unit", "blocked", "shadow-clean", "verified")
KINDS = ("override", "helper", "writer")  # writer: stores only through the writer gate, never an override marker
GATE_RX = re.compile(r"\bfe_writer_(begin|store|call)\s*\(")
# below shadow-clean the source must still say UNVERIFIED (a unit smoke test is not proof)
NOT_PROVEN = ("unverified", "verified-unit", "blocked")
# ARM mnemonics followed by a register or register list: copied disassembly
DISASM_RX = re.compile(
    r"\b(?:ldr|ldrb|ldrh|ldrsb|ldrsh|ldrd|ldm\w*|str|strb|strh|strd|stm\w*|mov|movs|mvn|add|adds|sub|subs|rsb|"
    r"mul|mla|smlal|umull|and|orr|orrs|eor|bic|cmp|cmn|tst|teq|lsl|lsr|asr|uxtb|uxth|uxtab|sxtb|push|pop|bl|blx|bx)"
    r"(?:eq|ne|cs|cc|mi|pl|hi|ls|ge|lt|gt|le)?\s+(?:r\d{1,2}|sp|lr|pc|\{)\s*[,}]?", re.I)
WORD_RX = re.compile(r"^\s*\.(?:word|byte|hword)\s", re.M)
CC_CANDIDATES = [r"C:\msys64\ucrt64\bin\gcc.exe", "gcc", "clang", "cc"]
CFLAGS = ["-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Werror"]


def rel(p: str, root: str = ROOT) -> str:
    try:
        return os.path.relpath(p, root).replace(os.sep, "/")
    except ValueError:  # another drive (self-test copies live in the temp folder)
        return p.replace(os.sep, "/")


# ------------------------------------------------------------------ parsing
def strip_code(text: str) -> str:
    """Comments blanked (newlines kept), string and char contents blanked: the same
    view 3dsrecomp's override scanner has (re-implemented here, not copied)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join(ch if ch == "\n" else " " for ch in text[i:j]))
            i = j
        elif c in "\"'":
            out.append(c)
            i += 1
            while i < n and text[i] != c:
                if text[i] == "\\":
                    out.append("  ")
                    i += 2
                    continue
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i < n:
                out.append(c)
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def markers(code: str) -> list[tuple[str, int, int]]:
    """(literal, offset after the closing parenthesis, line) of each override marker."""
    found = []
    for m in re.finditer(r"RECOMP_OVERRIDE(_IN)?\s*\(([^)]*)\)", code):
        if m.start() > 0 and (code[m.start() - 1].isalnum() or code[m.start() - 1] == "_"):
            continue
        found.append((m.group(2).strip() if not m.group(1) else "IN:" + m.group(2).strip(), m.end(),
                      code.count("\n", 0, m.start()) + 1))
    return found


def registry(path: str = REGISTRY) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("address", "").strip()]


def function_starts() -> set[int]:
    """Function starts of config/functions.csv. Before that file exists for a new port, the
    code analysis cache (build/cache/analysis.json, tools/gen_asm.py) and the game's symbol
    map stand in (a note says so); with neither, nothing is a start."""
    if os.path.isfile(FUNCTIONS):
        with open(FUNCTIONS, newline="", encoding="utf-8") as fh:
            return {int(r["addr"], 16) for r in csv.DictReader(fh)}
    starts: set[int] = set()
    cache = os.path.join(ROOT, "build", "cache", "analysis.json")
    if os.path.isfile(cache):
        import json
        with open(cache, encoding="utf-8") as fh:
            starts |= set(json.load(fh)["funcs"])
    try:
        import symmap  # noqa: E402  (same folder)
        if symmap.available():
            starts |= set(symmap.by_addr())
    except (ImportError, OSError, KeyError):
        pass
    if not getattr(function_starts, "_noted", False):
        print(f"note: {rel(FUNCTIONS)} missing: function starts from the analysis cache and the symbol map "
              f"({len(starts)})")
        function_starts._noted = True
    return starts


def files_under(base: str, exts: tuple[str, ...]) -> list[str]:
    out = []
    for dp, _dn, fn in os.walk(base):
        out += [os.path.join(dp, f) for f in fn if f.endswith(exts)]
    return sorted(out)


# ------------------------------------------------------------------ lint
def lint(src: str = SRC, inc: str = INC, reg_path: str = REGISTRY, root: str = ROOT,
         starts: set[int] | None = None) -> list[str]:
    errs: list[str] = []
    starts = function_starts() if starts is None else starts
    rows = registry(reg_path)
    by_addr: dict[str, dict] = {}
    names: set[str] = set()
    for r in rows:
        a, name, kind, status = r["address"].strip(), r["name"].strip(), r["kind"].strip(), r["status"].strip()
        where = f"{rel(reg_path, root)}: {a}"
        if not ADDR_RX.fullmatch(a):
            errs.append(f"{where}: address must be 0x + 8 uppercase hex digits")
            continue
        if a in by_addr:
            errs.append(f"{where}: listed twice")
        by_addr[a] = r
        if int(a, 16) not in starts:
            errs.append(f"{where}: not a function start in config/functions.csv")
        if int(a, 16) & 1:
            errs.append(f"{where}: odd (Thumb) address; readable overrides are written for ARM functions")
        if not IDENT.fullmatch(name) or name in names:
            errs.append(f"{where}: name {name!r} is not a fresh C identifier")
        names.add(name)
        if kind not in KINDS:
            errs.append(f"{where}: kind must be override, helper or writer")
        if kind == "writer" and not r.get("evidence", "").lstrip().startswith("WRITER"):
            errs.append(f"{where}: a writer row's evidence starts with 'WRITER' (docs/WRITERS.md)")
        if kind != "writer" and r.get("evidence", "").lstrip().startswith("WRITER"):
            errs.append(f"{where}: evidence says WRITER but the kind is {kind}: a writer is kind writer")
        if status not in STATUSES:
            errs.append(f"{where}: status must be one of {', '.join(STATUSES)}")
        if status == "blocked" and "blocked:" not in r.get("evidence", ""):
            errs.append(f"{where}: status blocked needs 'blocked: <reason>' in evidence")
        if status in ("verified-unit", "blocked") and kind != "override":
            errs.append(f"{where}: only overrides are run by verify (status {status} on a {kind})")
        s = os.path.join(root, r["source"].strip())
        if not os.path.isfile(s):
            errs.append(f"{where}: source {r['source']} does not exist")
            continue
        code = strip_code(open(s, encoding="utf-8").read())
        if not re.search(rf"^[A-Za-z_][\w \t\*]*\b{re.escape(name)}\s*\(\s*Context\s*\*\s*ctx\b", code, re.M):
            errs.append(f"{where}: {r['source']} does not define {name}(Context *ctx, ...)")
        if kind == "writer" and not GATE_RX.search(code):
            errs.append(f"{where}: a writer's source {r['source']} must store through the writer gate (fe_writer_*)")

    seen: dict[str, str] = {}
    for path in files_under(src, (".c",)):
        text = open(path, encoding="utf-8").read()
        code = strip_code(text)
        rp = rel(path, root)
        for lit, end, line in markers(code):
            where = f"{rp}:{line}"
            if lit.startswith("IN:"):
                errs.append(f"{where}: module overrides are not used by this game")
                continue
            if not ADDR_RX.fullmatch(lit):
                errs.append(f"{where}: marker address {lit!r} must be 0x + 8 uppercase hex digits")
                continue
            if lit in seen:
                errs.append(f"{where}: {lit} is overridden twice (also in {seen[lit]})")
            seen[lit] = rp
            r = by_addr.get(lit)
            if r is not None and r["kind"].strip() == "writer":
                errs.append(f"{where}: {lit} {r['name']} is a writer: a writer never has an override marker (it runs "
                            f"only through the writer gate, docs/WRITERS.md)")
                continue
            if r is None or r["kind"].strip() != "override":
                errs.append(f"{where}: {lit} is not an override in config/readable/functions.csv")
                continue
            if r["source"].strip() != rp:
                errs.append(f"{where}: registry says {lit} lives in {r['source']}")
            body = code[end:]
            stop = re.search(r"RECOMP_OVERRIDE", body)
            body = body[:stop.start()] if stop else body
            # FE_ENTRY0 is FE_ENTRY for a function whose only parameter is ctx (fe_guest.h)
            m = re.search(r"\bFE_ENTRY0?\s*\(\s*([^,\s]+)\s*,\s*([A-Za-z_]\w*)", body)
            if not m:
                errs.append(f"{where}: the override body has no FE_ENTRY(address, function, ...)")
            elif m.group(1) != lit:
                errs.append(f"{where}: FE_ENTRY names {m.group(1)}, the marker {lit}")
            elif m.group(2) != r["name"].strip():
                errs.append(f"{where}: FE_ENTRY calls {m.group(2)}, the registry says {r['name']}")
        # classify_verify accepts a first memory difference in the dead stack; verify reports
        # only the FIRST differing byte, so a later one above sp would be hidden. That is only
        # sound while readable code writes no guest memory (READABLE.md 1.3 point 4, rule 5).
        for wm in GUEST_WRITE_RX.finditer(code):
            errs.append(f"{rp}:{code.count(chr(10), 0, wm.start()) + 1}: writes guest memory "
                        f"({wm.group(1)}); the verify classifier assumes readable code never does "
                        f"(READABLE.md 1.3 point 4)")
        if "UNVERIFIED" not in text and any(
                x["source"].strip() == rp and x["status"].strip() in NOT_PROVEN for x in rows):
            errs.append(f"{rp}: has functions below shadow-clean but does not say UNVERIFIED")
    # runtime.c counts events per function in a table of FE_TRACKED slots; with more
    # overrides than slots the extra functions share slot 0 and their counts mix
    rt = os.path.join(src, "core", "runtime.c")
    overrides = sum(1 for r in rows if r["kind"].strip() == "override")
    if not os.path.isfile(rt):
        errs.append(f"{rel(rt, root)}: missing; the FE_TRACKED check needs it (moved? update check.py)")
    else:
        m = TRACKED_RX.search(open(rt, encoding="utf-8").read())
        tracked = None
        if m:
            try:
                tracked = int(m.group(1).rstrip("uUlL"), 0)   # C suffixes: 1024u, 1024UL
            except ValueError:
                pass
        if tracked is None:
            errs.append(f"{rel(rt, root)}: no '#define FE_TRACKED <number>'"
                        + (f" (cannot read {m.group(1)!r})" if m else ""))
        elif tracked < overrides:
            errs.append(f"{rel(rt, root)}: FE_TRACKED is {tracked}, below the {overrides} override "
                        f"rows in {rel(reg_path, root)}; grow it")
    for a, r in by_addr.items():
        if r["kind"].strip() == "override" and a not in seen:
            errs.append(f"{rel(reg_path, root)}: {a} {r['name']} is an override without a marker in {r['source']}")
        if r["kind"].strip() == "helper" and a in seen:
            errs.append(f"{rel(reg_path, root)}: {a} is a helper but has a marker")

    for path in files_under(inc, (".h",)):
        for lit, _end, line in markers(strip_code(open(path, encoding="utf-8").read())):
            errs.append(f"{rel(path, root)}:{line}: override marker in a header (staging would paste it into every file)")
    for path in files_under(src, (".c", ".h")) + files_under(inc, (".h",)):
        text = open(path, encoding="utf-8").read()
        for i, line in enumerate(text.split("\n"), 1):
            if DISASM_RX.search(line) or WORD_RX.match(line):
                errs.append(f"{rel(path, root)}:{i}: looks like ARM disassembly; write readable C instead")
    return errs


def lint_generated() -> list[str]:
    import gen_structs  # noqa: E402  (same folder)
    errs = []
    for path, text in gen_structs.outputs().items():
        old = open(path, encoding="utf-8", newline="").read() if os.path.exists(path) else None
        if old != text:
            errs.append(f"{rel(path)} is out of date (python tools/readable/gen_structs.py gen)")
    return errs


# ------------------------------------------------------------------ compile
def find_cc() -> str | None:
    env = os.environ.get("FE_HOST_CC")
    for c in ([env] if env else []) + CC_CANDIDATES:
        p = c if os.path.isfile(c) else shutil.which(c)
        if p:
            return p
    return None


def run(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    cc_dir = os.path.dirname(cmd[0])
    if os.path.isdir(cc_dir):  # MSYS2 gcc needs its own DLLs on PATH
        env["PATH"] = cc_dir + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    return r.returncode, (r.stdout + r.stderr).strip()


def compile_checks(cc: str) -> tuple[list[str], list[str]]:
    errs, notes = [], []
    inc = ["-I", STUB, "-I", INC, "-I", GEN]
    srcs = files_under(SRC, (".c",))
    for s in srcs:
        rc, out = run([cc] + CFLAGS + ["-fsyntax-only"] + inc + [s])
        if rc or out:
            errs.append(f"compile {rel(s)}:\n{out}")
    notes.append(f"syntax: {len(srcs)} source(s) against the stub, -Wpedantic -Werror")

    import stage  # noqa: E402  (same folder)
    staged_dir = os.path.join(BUILD, "check_stage")
    staged = stage.stage("shadow", staged_dir)
    want = [lit for s in srcs for lit, _e, _l in markers(strip_code(open(s, encoding="utf-8").read()))]
    got = [lit for s in staged for lit, _e, _l in markers(strip_code(open(s, encoding="utf-8").read()))]
    if sorted(want) != sorted(got):
        errs.append(f"staged files carry markers {sorted(got)}, the sources {sorted(want)}")
    for s in staged:
        rc, out = run([cc] + ["-std=c11", "-Wall", "-Wextra", "-Werror", "-fsyntax-only", "-I", STUB, s])
        if rc or out:
            errs.append(f"compile staged {rel(s)}:\n{out}")
    notes.append(f"staged: {len(staged)} self-contained file(s) compile with only the stub")

    exe_dir = os.path.join(BUILD, "hosttest")
    os.makedirs(exe_dir, exist_ok=True)
    exe = os.path.join(exe_dir, "host_test.exe" if os.name == "nt" else "host_test")
    test = os.path.join(HERE, "tests", "host_test.c")
    rc, out = run([cc] + CFLAGS + ["-O1", "-fwrapv"] + inc + [test] + srcs + ["-o", exe])
    if rc:
        errs.append(f"build host test:\n{out}")
        return errs, notes
    log = os.path.join(exe_dir, "fe_readable.log")
    if os.path.exists(log):
        os.remove(log)
    os.environ["FE_READABLE_LOG"] = log  # the runtime's log lines go to a file, not the report
    try:
        rc, out = run([exe])
    finally:
        del os.environ["FE_READABLE_LOG"]
    summary = re.findall(r"^host test: (\d+)/(\d+) checks passed", out, re.M)
    if rc or not summary or summary[-1][0] != summary[-1][1]:
        errs.append(f"host test failed:\n{out}")
    notes.append(next((ln for ln in out.splitlines() if ln.startswith("host test:")), "host test: no summary"))
    e, n = capture_test(cc, inc, exe_dir)
    e2, n2 = undo_test(cc, inc, exe_dir)
    return errs + e + e2, notes + n + n2


def undo_test(cc: str, inc: list[str], exe_dir: str, undo_src: str | None = None) -> tuple[list[str], list[str]]:
    """The undo log (src/readable/core/undo.c, include/readable/fe_undo.h) against its own fake
    guest. Writes nothing but the exe. undo_src replaces undo.c (planted-bug runs)."""
    core = [undo_src or os.path.join(SRC, "core", "undo.c")]
    core += [os.path.join(SRC, "core", f) for f in ("capture.c", "runtime.c")]
    missing = [rel(c) for c in core if not os.path.isfile(c)]
    if missing:
        return [f"undo test: missing {', '.join(missing)}"], []
    exe = os.path.join(exe_dir, "undo_test.exe" if os.name == "nt" else "undo_test")
    test = os.path.join(HERE, "tests", "undo_test.c")
    rc, out = run([cc] + CFLAGS + ["-O1", "-fwrapv"] + inc + [test] + core + ["-o", exe])
    if rc:
        return [f"build undo test:\n{out}"], []
    rc, out = run([exe], cwd=exe_dir)
    summary = re.findall(r"^undo test: (\d+)/(\d+) checks passed", out, re.M)
    errs = []
    if rc or not summary or summary[-1][0] != summary[-1][1]:
        errs.append(f"undo test failed:\n{out}")
    note = next((ln for ln in out.splitlines() if ln.startswith("undo test:")), "undo test: no summary")
    return errs, [note]


def capture_test(cc: str, inc: list[str], exe_dir: str) -> tuple[list[str], list[str]]:
    """Capture mode (src/readable/core/capture.c) against its own fake host. It runs with an
    emptied scratch folder below build/ as argument and working folder, because it writes
    records there (invented values only)."""
    core = [os.path.join(SRC, "core", f) for f in ("capture.c", "runtime.c")]
    missing = [rel(c) for c in core if not os.path.isfile(c)]
    if missing:
        return [f"capture test: missing {', '.join(missing)}"], []
    exe = os.path.join(exe_dir, "capture_test.exe" if os.name == "nt" else "capture_test")
    test = os.path.join(HERE, "tests", "capture_test.c")
    rc, out = run([cc] + CFLAGS + ["-O1", "-fwrapv"] + inc + [test] + core + ["-o", exe])
    if rc:
        return [f"build capture test:\n{out}"], []
    scratch = os.path.join(exe_dir, "capture")
    if os.path.isdir(scratch):
        shutil.rmtree(scratch)
    os.makedirs(scratch)
    os.environ["FE_READABLE_LOG"] = os.path.join(scratch, "fe_readable.log")
    try:
        rc, out = run([exe, os.path.abspath(scratch)], cwd=scratch)
    finally:
        del os.environ["FE_READABLE_LOG"]
    summary = re.findall(r"^capture test: (\d+)/(\d+) checks passed", out, re.M)
    errs = []
    if rc or not summary or summary[-1][0] != summary[-1][1]:
        errs.append(f"capture test failed:\n{out}")
    note = next((ln for ln in out.splitlines() if ln.startswith("capture test:")), "capture test: no summary")
    return errs, [note]


# ------------------------------------------------------------------ verify logs
# Read from 3dsrecomp df82e6e src/verify.rs (not copied): the stack is 0x0FFC0000..0x10000000,
# every function starts with sp = 0x0FFFF000, so bytes below that are pushes (dead stack).
# Writable regions are compared in the order .data/.bss, heap, stack, TLS and only the FIRST
# differing byte is reported: a first difference in the dead stack means .data/.bss and the
# heap are equal, but the stack above sp and TLS were not looked at (READABLE.md 1.3).
DEAD_STACK = (0x0FFC0000, 0x0FFFF000)
SCRATCH = {"r1", "r2", "r3", "r12", "r14", "n", "z", "c", "v", "q"}
# verdicts that count as a pass of tier 2 (GAVE-UP passes but proves nothing: blocked)
VERIFY_PASS = ("CLEAN", "ABI-ONLY")
VERIFY_OK = VERIFY_PASS + ("GAVE-UP",)
# UNSAMPLED: verify cannot pick the address at all (see classify_function); no evidence either way
UNSAMPLED = "UNSAMPLED"
NOT_TESTED = "no executable function was tested (VERIFY_ONLY address not found?)"
STUCK = "stuck: one side ran past the instruction limit, nothing was compared"
# verify's own line for a single function (3dsrecomp src/verify.rs:596): how each side stopped
STOPPED_RX = re.compile(r"^\s+executable ([0-9A-F]{8}), interpreter stopped with (\w+), recompiled with (\w+)", re.M)
GAVE_UP_RX = re.compile(r"^\[fe-readable\] 0x([0-9A-F]{8}) \w+: gave up, the original ran", re.M)
SHADOW_MISMATCH_RX = re.compile(r"^\[fe-readable\] MISMATCH 0x([0-9A-F]{8}) .*$", re.M)
SHADOW_SKIPPED_RX = re.compile(r"^\[fe-readable\] 0x([0-9A-F]{8}) \w+: shadow skipped", re.M)
# guest memory writes in readable sources (see lint)
TRACKED_RX = re.compile(r"^\s*#\s*define\s+FE_TRACKED\s+(\w+)", re.M)
GUEST_WRITE_RX = re.compile(r"\b(WRITE_FIELD|guest_set_\w+|mem_write\w*)\s*\(")
SHADOW_MATCH_RX = re.compile(r"^\[fe-readable\] 0x([0-9A-F]{8}) \w+: shadow match", re.M)


def classify_verify(text: str, address: str | None = None) -> tuple[str, list[str]]:
    """One `3dsrecomp verify` output (VERIFY_ONLY=one address) -> (verdict, details).
    verdicts: CLEAN (no difference), ABI-ONLY (differences only where AAPCS lets a
    function leave anything: r1-r3, r12, lr, flags, dead stack), MISMATCH, NOT-RUN
    (nothing compared: address not found, more than one function run, or stuck).
    address: the 8 hex digits the run was for; a report about another address or a
    run of several functions (VERIFY_ONLY ignored) is NOT-RUN."""
    summary = re.search(r"^executable\s+(\d+) functions, (\d+) returned, (\d+) reached an svc, "
                        r"(\d+) stuck, (\d+) stopped otherwise, (\d+) mismatched", text, re.M)
    if not summary or summary.group(1) == "0":
        return "NOT-RUN", [NOT_TESTED]
    tested, returned, svc, stuck, other, mismatched = (int(x) for x in summary.groups())
    if tested != 1:
        return "NOT-RUN", [f"{tested} functions were tested, not one (VERIFY_ONLY not honoured?)"]
    if stuck:
        return "NOT-RUN", [STUCK]
    lines = re.findall(r"^\s+executable ([0-9A-F]{8})\s{2}(.+)$", text, re.M)
    if address is not None and any(a != address.upper() for a, _ in lines):
        return "NOT-RUN", [f"the report names {lines[0][0]}, the run was for {address.upper()}"]
    if not lines:
        if mismatched:
            return "MISMATCH", ["counted as mismatched but no detail line"]
        how = "returned" if returned else "stopped at an svc" if svc else "stopped otherwise" if other else "?"
        return "CLEAN", [] if returned else [how]
    bad, abi = split_differences(lines[0][1])
    return ("MISMATCH", bad + abi) if bad else ("ABI-ONLY", abi)


def split_differences(line: str) -> tuple[list[str], list[str]]:
    """One verify detail line -> (differences AAPCS does not allow, ones it does)."""
    bad, abi = [], []
    for item in (x.strip() for x in line.split(", ")):
        m = re.match(r"(\w+) \S+ against \S+$", item)
        mm = re.match(r"memory at ([0-9A-F]{8})$", item)
        if m and m.group(1) in SCRATCH:
            abi.append(item)
        elif mm and DEAD_STACK[0] <= int(mm.group(1), 16) < DEAD_STACK[1]:
            abi.append(item + " (dead stack)")
        else:
            bad.append(item)
    return bad, abi


# Shadow mode and verify's fault counter (3dsrecomp df82e6e, read, not copied):
#  - Memory.faults is a host-side counter of BYTE accesses to unmapped pages; a faulting read
#    returns 0 and changes nothing else (src/verify.rs:39, 125-130; read16/read32 are built
#    from read8, 135-141). It is reset per function (verify.rs:74) and compared as
#    "<interpreter> faults against <recompiled>" (verify.rs:426-427). Nothing in the guest
#    Context can save or restore it.
#  - FE_READABLE=shadow runs the original and then the readable function on the same memory
#    (include/readable/fe_guest.h FE_ENTRY, shadow branch), so the recompiled side's count is
#    F(original, generated) + F(readable); the interpreter's is F(original) = A.
#  - The readable pass (FE_READABLE=readable) runs the readable function alone on the same
#    made-up state; when it passes, its count equals A, so F(readable) = A.
# Hence a shadow pass whose ONLY non-AAPCS difference is "A faults against 2A", with the
# readable pass passing without a give-up and a "shadow match" line logged (the readable code ran to the end,
# no give-up, same r0), proves F(original, generated) = A: the doubling is the readable
# code's own reads counted a second time, not guest state. Any other count stays a MISMATCH,
# with one exception that claims nothing (the shadow surplus after a give-up, below).
#
# Shadow surplus after a give-up (batch 2, 2026-11-09). When the readable pass GAVE UP (a
# cold one-time cache: the original ran, the function is GAVE-UP/blocked whatever the shadow
# pass shows), the shadow pass's recompiled side also counts reads of readable code that runs
# in shadow mode AFTER the original: this override on the caches the original has just filled
# (shadow mode writes nothing back, fe_guest.h FE_ENTRY), and every readable override the
# original calls (each runs its own original and then its readable code). Those reads are all
# counted by the same host counter (verify.rs:39, 125-130), change no guest state (a faulting
# read returns 0, verify.rs:125-130) and the count is their only trace (verify.rs:426-427), so
# the recompiled side counts MORE: B > A. The surplus says nothing about our code either way,
# so it is accepted only when the verdict stays GAVE-UP (no status gain), the readable pass
# itself compared clean apart from AAPCS (no fault difference there), the shadow pass differs
# in nothing else beyond AAPCS, and the shadow log has no MISMATCH line for ANY address (a
# nested readable override that disagreed is still a MISMATCH). B <= A stays a MISMATCH:
# extra readable code can only add reads.
#
# Shadow surplus from nested readable overrides, without a give-up (batch 3, 2026-11-09).
# The same host counter (verify.rs:39, 125-130, 426-427) also counts the readable code of
# every override the ORIGINAL calls: in shadow mode each of them runs its own original and
# then its readable code, and logs its own "shadow match" line. For an override whose
# original calls other overrides the recompiled side is therefore
#   B = F(original, generated) + sum of F(readable callee, per call) [+ F(readable) = A when
#       this override's own readable code ran: its "shadow match" line],
# e.g. units_are_family: 8 against 24 = 8 + 8 (unit_parent_child_pair, logged) + 8. A callee's
# reads are a part of the original's, so the sum is at most A when the callees read what
# their originals read. Accepted, with the readable pass's own verdict, only when ALL hold:
# the readable pass passed without giving up (so the readable code alone was compared with
# the interpreter, and that is the evidence); the fault count is the shadow pass's only
# non-AAPCS difference; the shadow log has a "shadow match" line for at least one OTHER
# address (a nested override did run) and no MISMATCH line for any address; and
# 2A < B <= 4A with this override's own match line, A < B <= 2A without one (its original
# stopped in a short slice, so its readable code never ran). The bound is 4A, not 3A, since
# round 8 (sheet batch, unit_equipped_item 10 against 40): when ALL of the readable code's
# reads are made by its own guest call to a nested override, that call too runs the callee's
# original and then its readable code in shadow mode, so this override's readable part counts
# 2A: A (original) + A (the callee's readable code from the original's call) + 2A = 4A. Nested
# deeper (round 10, support batch, unit_can_romance 90 against 488: IsRomance -> IsFamily ->
# GetFamilyChildImpl / IsFamilyBrotherSister, all overrides): every nesting level runs its callees'
# original AND readable code once more, so each level can double the count: B <= 2^(d+1) A for
# nesting depth d. Each level is a distinct override with its own logged match line, so d is at
# most k, the number of OTHER overrides with a logged match. Round 11 (Grok REVIEW_2026-11-16 finding 1:
# 2^(k+1) let a function with many FLAT nested overrides pass with up to 64A): d is now the real
# nesting depth, the longest chain of calls from this override through other logged overrides in the
# game's own code (a BL / BLX / B from inside one function's range to the start of the next, read
# from extracted/text.bin with config/functions.csv's ranges; nested_depth). The bound is 2^(d+1) A
# (d at least 1: 4A, as before; capped at 5). Without text.bin or a function row, d = 1 (the old 4A:
# fails closed). unit_can_romance: IsRomance -> IsFamily -> GetFamilyChildImpl, d = 2, 8A >= 488/90.
# What is lost: with a nested
# override the count no longer shows F(original, generated) = A exactly (the exact-doubling
# rule above does); the detail line says so. Anything outside the bounds stays a MISMATCH.
#
# The original itself runs past verify's limit (batch 3). verify runs the game's own code
# under its interpreter for at most LIMIT = 200000 instructions (verify.rs:21, 304-315) and
# compares nothing when either side stopped with Limit (verify.rs:613-616: counted as
# "stuck"). When the INTERPRETER is the side that hit the limit, in both passes, and the
# generated original hit it too in the shadow pass, the made-up state sends the game's own
# code into a loop longer than verify allows (weapon_triangle_row: a table scan from a null
# table pointer): that says nothing about our code, and verify cannot sample the function.
# That is UNSAMPLED (nothing compared, no status change). A run where only the recompiled
# side hit the limit stays NOT-RUN: there our code may be the one that loops.
#
# A callee's one-time cache filled by the original first (round 8, sheet batch,
# unit_is_special_battle 25 against 34). The readable code calls a game function through the
# guest (Job::IsGiant) that fills a one-time cache the first time it runs, reading many unmapped
# bytes in verify's made-up memory. In the readable pass that cache is cold, so those reads are
# in A (and the pass compared equal to the interpreter's A). In the shadow pass the original
# ran first and filled it, so the readable code's run reads less: B = A + F with 0 < F < A.
# Accepted, with the readable pass's own verdict, only when ALL hold: the readable pass passed
# without giving up; the fault count is the shadow pass's only non-AAPCS difference; this
# override's own "shadow match" line is logged; NO other override logged a match (else the
# nested rule above applies) and no MISMATCH line for any address; and A < B < 2A. What is lost:
# the shadow pass no longer shows F(readable) = A; the readable pass alone is the evidence.
#
# Both at once: a nested override AND a callee's one-time cache filled by the original first
# (round 11, battle2 batch, unit_item_stat_bonus 0x0033A790, 310 against 440). GetEnhanceHave calls
# Unit::IsItemEnhanceHave (not an override; it calls __cxa_guard_acquire, so it has one-time caches)
# five times, and that calls unit::Item::ToData (an override, item_to_data, logged). Rebuilt exactly
# from verify.rs's made-up state (regions() and the per-function registers) in arm_mini.py
# (docs/BATTLE2.md 8): A = 254 (first IsItemEnhanceHave call, cold caches, 6 of them in ToData)
# + 4 x 14 (warm) = 310. Shadow: the original 310 + 5 x 6 (the nested ToData's readable code) = 340,
# then the readable code on the warm caches 5 x 14 + 5 x 6 = 100: B = 440 exactly. The nested
# surplus pushes B up and the warm cache pulls it down, so B lands below 2A, where neither rule
# above accepts it. Accepted, with the readable pass's own verdict, only when ALL hold: the readable
# pass passed without giving up; the fault count is the shadow pass's only non-AAPCS difference;
# this override's own "shadow match" line and at least one OTHER override's are logged; no
# MISMATCH line for any address; A < B < 2A; and the game's code of this override calls (BL/BLX/B,
# static_calls) a function that is NOT an override with a logged match and that itself calls the
# one-time guard routine (config/readable/addresses.json "guard"; callee_cache_filler). Without
# text.bin, a function row or the guard address the rule does not apply (fails closed). What is
# lost: as for the two rules it combines; the readable pass alone is the evidence.
FAULTS_RX = re.compile(r"(\d+) faults against (\d+)$")
# one line of the build's generated entry table (lib/entries.c): {0x0027CA28u, f_0027CA00},
ENTRY_RX = re.compile(r"\{0x([0-9A-Fa-f]{8})u, (\w+)\}")


def function_ends() -> dict[int, int]:
    """config/functions.csv: start -> end of every guest function."""
    with open(FUNCTIONS, newline="", encoding="utf-8") as fh:
        return {int(r["addr"], 16): int(r["end"], 16) for r in csv.DictReader(fh)}


def entry_holder(entries_text: str | None, address: str, end: int | None) -> str | None:
    """The generated function that holds the code of the guest function at address, from
    the build's entry table: every entry strictly inside (address, end) names the same
    f_<H> with H != address, and there is at least one. That is what a fall-through
    (0x0027CA00 -> 0x0027CA08) or a tail-call target (0x002EDEF4 -> 0x002B3180) looks like:
    the build seeds the override address as a function start, yet the code after the entry
    is generated as part of the holder. None for anything else (no table, no entry inside,
    entries of the function itself, mixed holders): then nothing says why verify did not
    pick the address."""
    if not entries_text or end is None:
        return None
    a = int(address, 16)
    inside = {name for k, name in ENTRY_RX.findall(entries_text) if a < (int(k, 16) & ~1) < end}
    if len(inside) != 1:
        return None
    holder = inside.pop()
    m = re.fullmatch(r"f_([0-9A-F]{8})", holder)
    return holder if m and int(m.group(1), 16) != a else None


def shadow_fault_doubling(shadow_out: str, address: str) -> tuple[int, int] | None:
    """(A, B) when the shadow pass's only non-AAPCS difference is 'A faults against B'."""
    lines = re.findall(r"^\s+executable ([0-9A-F]{8})\s{2}(.+)$", shadow_out, re.M)
    if len(lines) != 1 or lines[0][0] != address:
        return None
    bad, _abi = split_differences(lines[0][1])
    m = FAULTS_RX.match(bad[0]) if len(bad) == 1 else None
    return (int(m.group(1)), int(m.group(2))) if m else None


def stopped_with(out: str | None, address: str) -> tuple[str, str] | None:
    """(interpreter stop, recompiled stop) from verify's single-function line, or None."""
    found = STOPPED_RX.findall(out or "")
    return (found[0][1], found[0][2]) if len(found) == 1 and found[0][0] == address else None


TEXT_BIN = os.path.join(ROOT, "extracted", "text.bin")
TEXT_BASE = 0x00100000
CALLS_OVERRIDE = None  # the self-test's made-up call graph: {address: {callee, ...}} (8 upper hex digits)
_calls_cache: dict = {}


def static_calls(address: str) -> set[str] | None:
    """The function starts the game's code at `address` reaches with an ARM BL / BLX / B (immediate) from
    inside its own range (config/functions.csv), read from extracted/text.bin; None without either."""
    if CALLS_OVERRIDE is not None:  # an address missing from it: no function row (None)
        got = CALLS_OVERRIDE.get(address.upper())
        return None if got is None else set(got)
    a = int(address, 16)
    if a in _calls_cache:
        return _calls_cache[a]
    out = None
    try:
        ends = _calls_cache.setdefault("ends", function_ends())
        end = ends.get(a)
        if end is not None and os.path.isfile(TEXT_BIN):
            with open(TEXT_BIN, "rb") as fh:
                fh.seek(a - TEXT_BASE)
                code = fh.read(end - a)
            out = set()
            for off in range(0, len(code) - 3, 4):
                w = int.from_bytes(code[off:off + 4], "little")
                if (w >> 25) & 7 != 5:
                    continue
                imm = w & 0xFFFFFF
                imm -= (imm & 0x800000) << 1
                target = a + off + 8 + imm * 4 + ((w >> 23) & 2 if w >> 28 == 0xF else 0)
                if target in ends and not a <= target < end:
                    out.add(f"{target:08X}")
    except (OSError, ValueError, KeyError):
        out = None
    _calls_cache[a] = out
    return out


def nested_depth(address: str, logged: set[str]) -> int | None:
    """The longest chain address -> x1 -> x2 ... of calls in the game's code (static_calls) where every
    x is another override with a logged shadow match; None when a call list cannot be read."""
    memo: dict[str, int | None] = {}

    def depth(x: str, seen: frozenset) -> int | None:
        if x in memo:
            return memo[x]
        calls = static_calls(x)
        if calls is None:
            return None
        best = 0
        for c in sorted(calls & logged):
            if c in seen:
                continue
            d = depth(c, seen | {c})
            if d is None:
                return None
            best = max(best, d + 1)
        memo[x] = best
        return best
    a = address.upper()
    return depth(a, frozenset({a}))


def nested_bound(shadow_log: str, address: str) -> int:
    """2^(d+1), d = the nesting depth of other overrides with a logged shadow match in the game's own
    call graph (nested_depth; at least 1, at most 5; 1 when the graph cannot be read): the surplus bound
    of "Shadow surplus from nested readable overrides" (comment above FAULTS_RX)."""
    logged = {m.group(1) for m in SHADOW_MATCH_RX.finditer(shadow_log)} - {address.upper()}
    d = nested_depth(address, logged) if logged else None
    return 2 ** (min(max(d or 1, 1), 5) + 1)


def one_time_guard() -> str | None:
    """The one-time guard routine (__cxa_guard_acquire) as 8 upper hex digits, from
    config/readable/addresses.json via gameaddr.py; None when it cannot be read."""
    try:
        import gameaddr
        return f"{gameaddr.addr('guard') & ~1:08X}"
    except Exception:  # noqa: BLE001 - any failure: the rule that needs it does not apply
        return None


def callee_cache_filler(address: str, logged: set[str]) -> str | None:
    """A function the game's code at `address` calls (static_calls) that is not an override with a
    logged shadow match and itself calls the one-time guard routine: a one-time cache that the
    original fills before the readable code runs in shadow mode. None when there is none or a call
    list or the guard address cannot be read (see "Both at once" above FAULTS_RX)."""
    guard = one_time_guard()
    calls = static_calls(address)
    if guard is None or calls is None:
        return None
    for c in sorted(calls - logged - {address.upper()}):
        sub = static_calls(c)
        if sub is not None and guard in sub:
            return c
    return None


def classify_function(address: str, readable_out: str | None, readable_log: str = "",
                      shadow_out: str | None = None, shadow_log: str = "",
                      holder: str | None = None) -> tuple[str, list[str]]:
    """The tier-2 verdict of one override from its two verify runs:
    readable pass (FE_READABLE=readable: the readable result is what verify compares) and
    the optional shadow pass (FE_READABLE=shadow: the original drives, the readable result
    is compared with it on the same state and a difference is logged).
      MISMATCH  the readable pass differs in r0/r4-r11/sp/pc/memory/stop, or the shadow
                log has a MISMATCH line, or the shadow pass differs beyond AAPCS (shadow
                mode must be invisible); the one exception is a fault count of exactly
                twice the original's with a logged shadow match and a readable pass
                that passed without giving up (verify's host counter, see
                shadow_fault_doubling), or a bounded surplus with a logged match of
                a nested override (see the comment above FAULTS_RX)
      NOT-RUN   no readable output, or nothing was compared
      UNSAMPLED both passes tested 0 functions and the build's entry table shows the
                code held inside another function (holder, see entry_holder); 0
                functions without a holder stays NOT-RUN. Or: the game's own code
                under the interpreter ran past verify's instruction limit in both
                passes (and the generated original in the shadow pass): verify
                compares nothing then
      GAVE-UP   it matched, but only because the readable code gave up and the original
                ran (cold one-time cache, guest call without code): proves nothing
      CLEAN / ABI-ONLY  a pass"""
    a = address.upper()
    if readable_out is None:
        return "NOT-RUN", ["no readable-pass output"]
    verdict, details = classify_verify(readable_out, a)
    # Not in verify's sample: with VERIFY_ONLY, 3dsrecomp verify filters the functions of
    # its OWN fresh discovery pass (not the build's, which seeds every override address)
    # that codegen::recompiles (src/main.rs:263-275, src/codegen/mod.rs:141-143). An entry
    # that the recompiler keeps inside a bigger function (a fall-through like 0x0027CA00 ->
    # 0x0027CA08, a tail-call target like 0x002EDEF4 -> 0x002B3180) is then never picked:
    # both passes test 0 functions. Nothing was compared, so this is no evidence; it is not a
    # failure of the run either (verify.py counts it as a problem only for a row whose status
    # already rests on tier 2). Zero functions can have other causes (an address that is not
    # code, a wrong Thumb bit), so UNSAMPLED also needs the holder from the build's
    # lib/entries.c (entry_holder); without one it stays NOT-RUN.
    if (shadow_out is not None and details == [NOT_TESTED]
            and classify_verify(shadow_out, a) == ("NOT-RUN", [NOT_TESTED])
            and not GAVE_UP_RX.search(readable_log) and not SHADOW_MISMATCH_RX.search(shadow_log)):
        if holder is None:
            return "NOT-RUN", [NOT_TESTED, "0 functions in both passes and the build's entry table shows no "
                                           "holder for this address: nothing explains it"]
        return UNSAMPLED, [f"verify cannot pick this address: its code is held inside {holder} (the build's "
                           f"lib/entries.c), not a function of its own in 3dsrecomp's discovery; nothing compared"]
    # the game's own code runs past verify's limit (see the comment above FAULTS_RX)
    if (shadow_out is not None and details == [STUCK]
            and classify_verify(shadow_out, a) == ("NOT-RUN", [STUCK])
            and (stopped_with(readable_out, a) or ("", ""))[0] == "Limit"
            and stopped_with(shadow_out, a) == ("Limit", "Limit")
            and not SHADOW_MISMATCH_RX.search(shadow_log)):
        return UNSAMPLED, ["verify cannot compare this function: in its made-up state the game's own code "
                           "runs past the instruction limit under verify's interpreter (both passes; the "
                           "generated original too), so nothing was compared"]
    details = list(details)
    for m in SHADOW_MISMATCH_RX.finditer(shadow_log):
        if m.group(1) == a:
            return "MISMATCH", [f"shadow: {m.group(0)[len('[fe-readable] '):]}"] + details
    if shadow_out is not None:
        sv, sd = classify_verify(shadow_out, a)
        if sv == "MISMATCH":
            doubled = shadow_fault_doubling(shadow_out, a)
            matched = any(m.group(1) == a for m in SHADOW_MATCH_RX.finditer(shadow_log))
            # F(readable) = A is proven only by a readable pass that passed WITHOUT giving up:
            # after a give-up the original ran too and its reads are in that count. (The
            # VERIFY_PASS test alone changes no final verdict: a failing readable pass is
            # returned as it is below. It is kept so the rule reads as derived.)
            readable_alone = verdict in VERIFY_PASS and not any(
                m.group(1) == a for m in GAVE_UP_RX.finditer(readable_log))
            gave_up = verdict in VERIFY_PASS and not readable_alone
            if doubled and doubled[1] == 2 * doubled[0] and matched and readable_alone:
                # see shadow_fault_doubling's comment: the readable code's reads counted twice
                details.append(f"shadow pass: {doubled[0]} faults against {doubled[1]} = the original's "
                               f"unmapped reads plus the readable code's same reads (verify's host counter, "
                               f"not guest state)")
            elif doubled and doubled[1] > doubled[0] and gave_up and not SHADOW_MISMATCH_RX.search(shadow_log):
                # see "Shadow surplus after a give-up" above: the verdict stays GAVE-UP
                details.append(f"shadow pass: {doubled[0]} faults against {doubled[1]}: the surplus is "
                               f"readable code run in shadow mode after the original (this override on the "
                               f"caches it filled, readable callees), verify's host counter, not guest state")
            elif (doubled and readable_alone and not SHADOW_MISMATCH_RX.search(shadow_log)
                  and {m.group(1) for m in SHADOW_MATCH_RX.finditer(shadow_log)} - {a}
                  and (2 * doubled[0] < doubled[1] <= nested_bound(shadow_log, a) * doubled[0] if matched
                       else doubled[0] < doubled[1] <= 2 * doubled[0])):
                # see "Shadow surplus from nested readable overrides" above
                nested = sorted({m.group(1) for m in SHADOW_MATCH_RX.finditer(shadow_log)} - {a})
                details.append(f"shadow pass: {doubled[0]} faults against {doubled[1]}: the surplus is the "
                               f"readable code of overrides the original calls "
                               f"({', '.join('0x' + n for n in nested)}: shadow match logged)"
                               + (" plus this override's own readable reads" if matched else "")
                               + "; verify's host counter, not guest state; the original's own count "
                                 "is not shown by this pass")
            elif (doubled and readable_alone and matched and not SHADOW_MISMATCH_RX.search(shadow_log)
                  and {m.group(1) for m in SHADOW_MATCH_RX.finditer(shadow_log)} - {a}
                  and doubled[0] < doubled[1] < 2 * doubled[0]
                  and callee_cache_filler(a, {m.group(1) for m in SHADOW_MATCH_RX.finditer(shadow_log)} - {a})):
                # see "Both at once" above FAULTS_RX
                nested = sorted({m.group(1) for m in SHADOW_MATCH_RX.finditer(shadow_log)} - {a})
                filler = callee_cache_filler(a, set(nested))
                details.append(f"shadow pass: {doubled[0]} faults against {doubled[1]}: the readable code of "
                               f"overrides the original calls ({', '.join('0x' + n for n in nested)}: shadow "
                               f"match logged) adds reads, and the readable code ran after the original had "
                               f"filled the one-time cache of 0x{filler} (it calls the guard routine), so it "
                               f"read less; verify's host counter, not guest state; the readable pass alone "
                               f"is the evidence")
            elif (doubled and readable_alone and matched and not SHADOW_MISMATCH_RX.search(shadow_log)
                  and not ({m.group(1) for m in SHADOW_MATCH_RX.finditer(shadow_log)} - {a})
                  and doubled[0] < doubled[1] < 2 * doubled[0]):
                # see "A callee's one-time cache filled by the original first" above
                details.append(f"shadow pass: {doubled[0]} faults against {doubled[1]}: the readable code ran "
                               f"after the original had filled a callee's one-time cache, so it read less than "
                               f"in the readable pass (verify's host counter, not guest state); the readable "
                               f"pass alone is the evidence")
            else:
                return "MISMATCH", [f"shadow pass not invisible: {'; '.join(sd)}"] + details
            sd = [x for x in sd if not FAULTS_RX.match(x)]
            sv = "ABI-ONLY" if sd else "CLEAN"
        if sv == "ABI-ONLY":
            # the original's own registers come back unchanged in shadow mode, so this is the
            # generated code against the interpreter, not ours: noted, not held against us
            details.append(f"shadow pass ABI-ONLY ({'; '.join(sd)}): the generated original itself")
        if sv == "NOT-RUN":
            details.append(f"shadow pass not run ({'; '.join(sd)})")
        elif any(m.group(1) == a for m in SHADOW_MATCH_RX.finditer(shadow_log)):
            details.append("shadow: readable r0 = game r0")
        elif any(m.group(1) == a for m in SHADOW_SKIPPED_RX.finditer(shadow_log)):
            details.append("shadow: readable gave up")
        else:
            details.append("shadow: no comparison logged (the original stopped in a short slice?)")
    if verdict in VERIFY_PASS and any(m.group(1) == a for m in GAVE_UP_RX.finditer(readable_log)):
        return "GAVE-UP", ["readable code gave up, the original ran: only the fallback was tested"] + details
    return verdict, details


def read_opt(path: str) -> str | None:
    return open(path, encoding="utf-8", errors="replace").read() if os.path.exists(path) else None


def verify_results(d: str, reg_path: str = REGISTRY) -> list[tuple[dict, str, list[str]]]:
    """(registry row, verdict, details) per override, from the files tools/readable/verify.py
    writes in d: <ADDR>.txt + <ADDR>.readable.log (readable pass), <ADDR>.shadow.txt +
    <ADDR>.shadow.log (shadow pass, optional), and the build's entry table lib/entries.c
    when it is there (the holder of an address verify cannot pick; without it such an
    address is NOT-RUN)."""
    out = []
    entries = read_opt(os.path.join(d, "lib", "entries.c"))
    ends = function_ends() if entries else {}
    for r in sorted((r for r in registry(reg_path) if r["kind"].strip() == "override"),
                    key=lambda r: r["address"]):
        a = r["address"].strip()[2:]
        f = lambda suffix: os.path.join(d, a + suffix)  # noqa: E731
        holder = entry_holder(entries, a, ends.get(int(a, 16) & ~1))
        verdict, details = classify_function(a, read_opt(f(".txt")), read_opt(f(".readable.log")) or "",
                                             read_opt(f(".shadow.txt")), read_opt(f(".shadow.log")) or "",
                                             holder)
        out.append((r, verdict, details))
    return out


def verify_logs(d: str) -> int:
    counts: dict[str, int] = {}
    for r, verdict, details in verify_results(d):
        counts[verdict] = counts.get(verdict, 0) + 1
        print(f"  {verdict:<8} {r['address']} {r['name']}" + (f": {'; '.join(details)}" if details else ""))
    print("verify-logs: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    print("note: verify runs ONE made-up state per function and pristine (cold) one-time caches, so")
    print("      functions that give up on a cold cache only test the give-up path here (GAVE-UP)")
    return 1 if (counts.get("MISMATCH") or counts.get("NOT-RUN")) else 0


# ------------------------------------------------------------------ self-test
def selftest() -> list[str]:
    """Each broken input must produce at least one lint error; a clean copy none."""
    errs = []
    starts = function_starts()
    with tempfile.TemporaryDirectory() as td:
        def tree():
            root = os.path.join(td, "t")
            if os.path.isdir(root):
                shutil.rmtree(root)
            shutil.copytree(SRC, os.path.join(root, "src", "readable"))
            shutil.copytree(INC, os.path.join(root, "include", "readable"))
            os.makedirs(os.path.join(root, "config", "readable"))
            shutil.copy(REGISTRY, os.path.join(root, "config", "readable", "functions.csv"))
            return root

        def check(root):
            return lint(os.path.join(root, "src", "readable"), os.path.join(root, "include", "readable"),
                        os.path.join(root, "config", "readable", "functions.csv"), root, starts)

        def edit(path, old, new, count=1):
            t = open(path, encoding="utf-8").read()
            if old not in t:
                raise SystemExit(f"selftest: {old!r} not in {path}")
            open(path, "w", encoding="utf-8").write(t.replace(old, new, count))

        clean = check(tree())
        if clean:
            errs.append("selftest: the clean copy fails lint: " + "; ".join(clean[:3]))
        # the flag_manager_get row as it stands (its status moves with verify.py --update-status);
        # the cases edit the Fates pilot (unit/forces.c, event/flags.c), so they follow its text
        flag_status = next(r["status"].strip() for r in registry() if r["address"].strip() == "0x00508584")
        flag_row = f",{flag_status},yes,\"symbol map FlagManager::Get"
        forces, flags = "src/readable/unit/forces.c", "src/readable/event/flags.c"
        cases = [
            ("marker address not in the registry", forces, "RECOMP_OVERRIDE(0x0053C3E0)", "RECOMP_OVERRIDE(0x0053C3E4)"),
            ("FE_ENTRY literal differs from the marker", forces, "FE_ENTRY(0x0053C3E0", "FE_ENTRY(0x53C3E0"),
            ("FE_ENTRY calls another function", forces, "force_is_allied, FE_ARG", "unit_next, FE_ARG"),
            ("lower-case hex in a marker", flags, "RECOMP_OVERRIDE(0x00508584)", "RECOMP_OVERRIDE(0x00508584)".lower()),
            ("override marker in a header", "include/readable/fe.h", "#endif /* FE_H */", "#define X RECOMP_OVERRIDE(0x0053C3E0)\n#endif"),
            ("disassembly pasted into a source", forces, "#include \"fe.h\"", "#include \"fe.h\"\n/* ldrsb r0, [r1, r0] */"),
            ("UNVERIFIED note removed", flags, "UNVERIFIED", "checked"),
            ("bad status", "config/readable/functions.csv", flag_row, flag_row.replace(f",{flag_status},", ",done,")),
            ("registry address not a function start", "config/readable/functions.csv", "0x0053C3E0,force_is_allied", "0x0053C3E4,force_is_allied"),
            ("override listed but no marker", flags, "RECOMP_OVERRIDE(0x00508584) {", "static void unused(Context *ctx) {"),
            ("blocked without a reason", "config/readable/functions.csv", flag_row, flag_row.replace(f",{flag_status},", ",blocked,")),
            ("guest memory write in a source", forces, "#include \"fe.h\"", "#include \"fe.h\"\nstatic void poke(Context *ctx) { WRITE_FIELD(ctx, Unit, 0u, map_x, 0); }"),
            ("guest_set_ call in a source", flags, "#include \"fe.h\"", "#include \"fe.h\"\nstatic void poke(Context *ctx) { guest_set_u8(ctx, 0u, 1u); }"),
            ("verified-unit on a helper", "config/readable/functions.csv", "unit_pool_force,helper,src/readable/unit/forces.c,unverified", "unit_pool_force,helper,src/readable/unit/forces.c,verified-unit"),
            ("Thumb (odd) registry address", "config/readable/functions.csv", "0x0053C3E0,force_is_allied", "0x0053C3E1,force_is_allied"),
            ("unknown kind", "config/readable/functions.csv", "0x0053C3E0,force_is_allied,override", "0x0053C3E0,force_is_allied,hook"),
            ("a writer row hidden as a helper", "config/readable/functions.csv", ",config_set_battle,writer,", ",config_set_battle,helper,"),
            ("a writer row without WRITER in its evidence", "config/readable/functions.csv", '"WRITER, OFF (docs/WRITERS.md): anonymous_namespace::Battle', '"OFF (docs/WRITERS.md): anonymous_namespace::Battle'),
            ("a writer whose source bypasses the gate", "src/readable/menu/menu_config_writer.c", "fe_writer_", "fe_xwriter_", 99),
        ]
        rejected = 0
        for title, f, old, new, *n in cases:
            root = tree()
            edit(os.path.join(root, f), old, new, n[0] if n else 1)
            if check(root):
                rejected += 1
            else:
                errs.append(f"selftest: not rejected: {title}")
        # FE_TRACKED: matched by TRACKED_RX so growing it does not break the selftest
        overrides = sum(1 for r in registry() if r["kind"].strip() == "override")
        rt_rel = os.path.join("src", "readable", "core", "runtime.c")

        def set_tracked(root, line):
            p = os.path.join(root, rt_rel)
            t = open(p, encoding="utf-8").read()
            if not TRACKED_RX.search(t):
                raise SystemExit(f"selftest: no FE_TRACKED define in {p}")
            open(p, "w", encoding="utf-8").write(TRACKED_RX.sub(line, t, count=1))

        tracked_bad = [
            ("FE_TRACKED below the override count", f"#define FE_TRACKED {max(1, overrides // 2)}"),
            ("FE_TRACKED one below the override count", f"#define FE_TRACKED {overrides - 1}"),
            ("FE_TRACKED define missing", "/* FE_TRACKED removed */"),
            ("FE_TRACKED not a number", "#define FE_TRACKED (1024)"),
            ("FE_TRACKED unparsable", "#define FE_TRACKED 1024zz"),
        ]
        for title, line in tracked_bad:
            root = tree()
            set_tracked(root, line)
            if check(root):
                rejected += 1
            else:
                errs.append(f"selftest: not rejected: {title}")
        root = tree()
        os.remove(os.path.join(root, rt_rel))
        if check(root):
            rejected += 1
        else:
            errs.append("selftest: not rejected: runtime.c missing")
        # must be accepted: an exact fit (linear probing fills every slot) and C suffixes
        for line in (f"#define FE_TRACKED {overrides}", "#define FE_TRACKED 1024u", "#define FE_TRACKED 0x400UL"):
            root = tree()
            set_tracked(root, line)
            bad = check(root)
            if bad:
                errs.append(f"selftest: wrongly rejected {line!r}: " + "; ".join(bad[:2]))
        # duplicate marker
        root = tree()
        p = os.path.join(root, "src", "readable", "unit", "forces.c")
        t = open(p, encoding="utf-8").read()
        open(p, "w", encoding="utf-8").write(t + "\nRECOMP_OVERRIDE(0x0053C3E0) {\n    FE_ENTRY(0x0053C3E0, force_is_allied, FE_ARG(0), FE_ARG(1));\n}\n")
        if check(root):
            rejected += 1
        else:
            errs.append("selftest: not rejected: duplicate marker")
        # planted: an override marker on a writer (config_set_battle, Battle::SetValue). It must be refused by the
        # writer rule itself, not only because the address is "not an override"
        root = tree()
        p = os.path.join(root, "src", "readable", "menu", "menu_config_writer.c")
        t = open(p, encoding="utf-8").read()
        open(p, "w", encoding="utf-8").write(t + "\nRECOMP_OVERRIDE(0x003BC36C) {\n    FE_ENTRY(0x003BC36C, config_set_battle, FE_ARG(0));\n}\n")
        bad = check(root)
        if any("a writer never has an override marker" in e for e in bad):
            rejected += 1
        else:
            errs.append(f"selftest: not rejected: an override marker on a writer ({bad[:2]})")
        total = len(cases) + len(tracked_bad) + 3
    # verify-log classifier
    a = "002C4D88"
    summ = "executable  {} functions, {} returned, 0 reached an svc, {} stuck, 0 stopped otherwise, {} mismatched, 0 svcs gone through\n"
    head = f"  executable {a}, interpreter stopped with Returned, recompiled with Returned\n"
    one_ok, one_bad = summ.format(1, 1, 0, 0), summ.format(1, 0, 0, 1)
    samples = [
        (head + one_ok, "CLEAN"),
        (head + f"  executable {a}  r1 00000005 against DEAD0001, r14 002C4DE0 against FFFFFFF0, memory at 0FFFEFF0\n" + one_bad, "ABI-ONLY"),
        (head + f"  executable {a}  r0 00000005 against 00000006\n" + one_bad, "MISMATCH"),
        (head + f"  executable {a}  r1 0 against 1, memory at 004D0C88\n" + one_bad, "MISMATCH"),
        (head + f"  executable {a}  memory at 0FFFF004\n" + one_bad, "MISMATCH"),     # above sp: the caller's frame
        (head + f"  executable {a}  r13 0FFFEFF8 against 0FFFF000\n" + one_bad, "MISMATCH"),
        (head + f"  executable {a}  stopped with Returned against Svc(1)\n" + one_bad, "MISMATCH"),
        (head + f"  executable {a}  2 faults against 3\n" + one_bad, "MISMATCH"),
        (head + f"  executable {a}  vfp state\n" + one_bad, "MISMATCH"),
        (head + one_bad, "MISMATCH"),                                                  # counted, no detail line
        (summ.format(0, 0, 0, 0), "NOT-RUN"),
        (head + summ.format(1, 0, 1, 0), "NOT-RUN"),                                   # stuck
        (summ.format(500, 499, 0, 1) + f"  executable 00100000  r0 1 against 2\n", "NOT-RUN"),   # VERIFY_ONLY ignored
        ("  executable 00100000  r0 1 against 2\n" + one_bad, "NOT-RUN"),              # another address
        ("could not open lib.dll, not found\n", "NOT-RUN"),
    ]
    for text, want in samples:
        got = classify_verify(text, a)[0]
        if got != want:
            errs.append(f"selftest: verify log classified {got}, want {want}: {text.strip()[-70:]!r}")
    abi = head + f"  executable {a}  r12 1 against 2, memory at 0FFFEFF0\n" + one_bad
    gave = f"[fe-readable] mode readable (set FE_READABLE=original|readable|shadow)\n[fe-readable] 0x{a} unit_crit: gave up, the original ran (1)\n"
    smis = f"[fe-readable] MISMATCH 0x{a} unit_crit(r0=1 r1=2 r2=3 r3=4): game 00000005 (5), readable 00000006 (6) [1 mismatches, 0 matches]\n"
    smatch = f"[fe-readable] 0x{a} unit_crit: shadow match (1 so far, 0 mismatches)\n"
    snest = "[fe-readable] 0x002EBA08 unit_has_skill: shadow match (1 so far, 0 mismatches)\n"
    snest2, snest3, snest4, snest5, snest6, snest7, snest8 = (
        f"[fe-readable] 0x{x} nested_{x}: shadow match (1 so far, 0 mismatches)\n"
        for x in ("00531428", "0053386C", "004F0FDC", "00600000", "00600100", "00700000", "00700100"))
    lim = lambda i, r: (f"  executable {a}, interpreter stopped with {i}, recompiled with {r}\n"  # noqa: E731
                        + summ.format(1, 0, 1, 0))
    combos = [
        ((abi, "", head + one_ok, smatch), "ABI-ONLY"),
        ((head + one_ok, gave, None, ""), "GAVE-UP"),
        ((abi, "", head + one_ok, smis), "MISMATCH"),                                  # shadow log disagrees
        ((abi, "", head + f"  executable {a}  r0 1 against 2\n" + one_bad, smatch), "MISMATCH"),   # shadow visible
        ((None, "", head + one_ok, smatch), "NOT-RUN"),
        ((head + f"  executable {a}  r0 1 against 2\n" + one_bad, gave, None, ""), "MISMATCH"),     # gave up yet differs
        ((abi, "", head + f"  executable {a}  r1 1 against 2\n" + one_bad, smatch), "ABI-ONLY"),   # generated code's own
        # shadow fault doubling (shadow_fault_doubling): exactly 2x, match logged, readable pass passes
        ((abi, "", head + f"  executable {a}  2 faults against 4\n" + one_bad, smatch), "ABI-ONLY"),
        ((head + one_ok, "", head + f"  executable {a}  1 faults against 2\n" + one_bad, smatch), "CLEAN"),
        ((abi, "", head + f"  executable {a}  4 faults against 2\n" + one_bad, smatch), "MISMATCH"),     # fewer: not doubling
        ((abi, "", head + f"  executable {a}  r1 1 against 2, 5 faults against 10\n" + one_bad, smatch), "ABI-ONLY"),
        ((abi, "", head + f"  executable {a}  2 faults against 5\n" + one_bad, smatch), "MISMATCH"),     # not 2x
        ((abi, "", head + f"  executable {a}  2 faults against 4\n" + one_bad, ""), "MISMATCH"),         # nothing logged
        ((abi, "", head + f"  executable {a}  2 faults against 4\n" + one_bad,
          smatch.replace("shadow match (1 so far, 0 mismatches)", "shadow skipped")), "MISMATCH"),     # readable gave up
        ((abi, "", head + f"  executable {a}  r0 1 against 2, 2 faults against 4\n" + one_bad, smatch), "MISMATCH"),
        ((abi, "", head + f"  executable {a}  2 faults against 4, memory at 004D0C88\n" + one_bad, smatch), "MISMATCH"),
        ((head + f"  executable {a}  2 faults against 3\n" + one_bad, "", head + f"  executable {a}  2 faults against 4\n" + one_bad, smatch), "MISMATCH"),  # readable pass faults differ
        # the readable pass gave up: its count includes the original's reads, F(readable) = A
        # is not proven, so the doubling is not accepted as a pass; a surplus is accepted
        # only as GAVE-UP (shadow surplus after a give-up: no evidence, no failure)
        ((head + one_ok, gave, head + f"  executable {a}  2 faults against 4\n" + one_bad, smatch), "GAVE-UP"),
        ((abi, gave, head + f"  executable {a}  1 faults against 2\n" + one_bad, smatch), "GAVE-UP"),
        ((head + one_ok, gave, head + f"  executable {a}  149 faults against 157, memory at 0FFFEF90\n" + one_bad, ""), "GAVE-UP"),
        ((head + one_ok, gave, head + f"  executable {a}  5 faults against 4\n" + one_bad, ""), "MISMATCH"),       # fewer
        ((head + one_ok, gave, head + f"  executable {a}  r0 1 against 2, 5 faults against 9\n" + one_bad, ""), "MISMATCH"),
        ((head + one_ok, gave, head + f"  executable {a}  4 faults against 9, memory at 004D0C88\n" + one_bad, ""), "MISMATCH"),
        ((head + one_ok, gave, head + f"  executable {a}  4 faults against 9\n" + one_bad,
          smis.replace(f"0x{a} unit_crit", "0x002C48F8 unit_stat_cap")), "MISMATCH"),                         # a callee disagreed
        ((head + f"  executable {a}  2 faults against 3\n" + one_bad, gave,
          head + f"  executable {a}  4 faults against 9\n" + one_bad, ""), "MISMATCH"),                       # readable pass faults differ
        ((abi, "", head + f"  executable {a}  4 faults against 9\n" + one_bad, smatch), "MISMATCH"),           # no give-up: exact 2x only
        # shadow surplus from nested readable overrides (batch 3): bounded, a nested match logged
        ((abi, "", head + f"  executable {a}  8 faults against 24\n" + one_bad, snest + smatch), "ABI-ONLY"),
        ((abi, "", head + f"  executable {a}  228 faults against 468\n" + one_bad, snest + smatch), "ABI-ONLY"),
        ((head + one_ok, "", head + f"  executable {a}  224 faults against 228\n" + one_bad, snest), "CLEAN"),   # own code not run (short slice)
        ((abi, "", head + f"  executable {a}  10 faults against 40\n" + one_bad, snest + smatch), "ABI-ONLY"),   # 4A: readable reads via a nested override (round 8)
        ((abi, "", head + f"  executable {a}  8 faults against 33\n" + one_bad, snest + smatch), "MISMATCH"),    # above 4A
        # nested deeper (round 10; round 11: by the real nesting depth d in the made-up call graph
        # CALLS below: a -> 002EBA08 -> 00531428 -> 0053386C (a chain), a -> 004F0FDC (flat)): 2^(d+1) A
        ((abi, "", head + f"  executable {a}  90 faults against 488\n" + one_bad, snest + snest2 + snest3 + snest4 + smatch), "ABI-ONLY"),  # d = 3: 16A
        ((abi, "", head + f"  executable {a}  90 faults against 488\n" + one_bad, snest + snest2 + smatch), "ABI-ONLY"),  # d = 2: 8A
        ((abi, "", head + f"  executable {a}  90 faults against 488\n" + one_bad, snest + smatch), "MISMATCH"),  # d = 1: 4A
        ((abi, "", head + f"  executable {a}  8 faults against 65\n" + one_bad, snest + snest2 + smatch), "MISMATCH"),  # above 8A
        ((abi, "", head + f"  executable {a}  8 faults against 65\n" + one_bad, snest + snest + snest2 + smatch), "MISMATCH"),  # a repeated line counts once
        ((abi, gave, head + f"  executable {a}  90 faults against 488\n" + one_bad, snest + snest2 + snest3 + smatch), "GAVE-UP"),  # after a give-up: never a pass
        # round 11: a non-benign extra read is still caught. Four overrides logged, but only one level deep
        # in the call graph (snest, snest4 called by a; snest2, snest3 by nobody here): d = 1, 4A. Under the
        # round-10 rule (k = 4: 32A) 90 against 488 passed; it must not
        ((abi, "", head + f"  executable {a}  90 faults against 488\n" + one_bad, snest + snest4 + snest5 + snest6 + smatch), "MISMATCH"),
        ((abi, "", head + f"  executable {a}  90 faults against 360\n" + one_bad, snest + snest4 + snest5 + snest6 + smatch), "ABI-ONLY"),  # 4A exactly
        # the chain d = 3 (16A) does not stretch to 2^(k+1) = 32A either: 90 against 1500 (16.7A) fails
        ((abi, "", head + f"  executable {a}  90 faults against 1500\n" + one_bad, snest + snest2 + snest3 + snest4 + smatch), "MISMATCH"),
        # a nested override's call list unreadable (no function row): d = 1, fails closed
        ((abi, "", head + f"  executable {a}  90 faults against 488\n" + one_bad, snest7 + snest8 + smatch), "MISMATCH"),
        # a callee's one-time cache filled by the original first (round 8): A < B < 2A, own match, no nested
        ((abi, "", head + f"  executable {a}  25 faults against 34, memory at 0FFFEFF0\n" + one_bad, smatch), "ABI-ONLY"),
        ((abi, "", head + f"  executable {a}  25 faults against 34\n" + one_bad, ""), "MISMATCH"),              # no own match
        ((abi, "", head + f"  executable {a}  25 faults against 25\n" + one_bad, smatch), "MISMATCH"),         # no surplus
        ((abi, gave, head + f"  executable {a}  25 faults against 34\n" + one_bad, smatch), "GAVE-UP"),         # after a give-up: never a pass
        ((abi, "", head + f"  executable {a}  r0 1 against 2, 25 faults against 34\n" + one_bad, smatch), "MISMATCH"),
        ((abi, "", head + f"  executable {a}  8 faults against 12\n" + one_bad, snest + smatch), "MISMATCH"),    # own match, below 2A
        ((abi, "", head + f"  executable {a}  8 faults against 17\n" + one_bad, snest), "MISMATCH"),             # no own match, above 2A
        ((abi, "", head + f"  executable {a}  8 faults against 24\n" + one_bad, smatch), "MISMATCH"),            # no nested override logged
        ((abi, "", head + f"  executable {a}  8 faults against 8\n" + one_bad, snest), "MISMATCH"),              # no surplus at all
        ((abi, "", head + f"  executable {a}  r0 1 against 2, 8 faults against 24\n" + one_bad, snest + smatch), "MISMATCH"),
        ((abi, "", head + f"  executable {a}  8 faults against 24, memory at 004D0C88\n" + one_bad, snest + smatch), "MISMATCH"),
        ((abi, "", head + f"  executable {a}  8 faults against 24\n" + one_bad,
          snest + smatch + smis.replace(f"0x{a} unit_crit", "0x002C48F8 unit_stat_cap")), "MISMATCH"),            # a callee disagreed
        ((head + f"  executable {a}  8 faults against 9\n" + one_bad, "",
          head + f"  executable {a}  8 faults against 24\n" + one_bad, snest + smatch), "MISMATCH"),               # readable pass faults differ
        ((abi, gave, head + f"  executable {a}  8 faults against 24\n" + one_bad, snest + smatch), "GAVE-UP"),     # after a give-up: never a pass
        # the game's own code runs past verify's limit: interpreter Limit in both passes
        ((lim("Limit", "Returned"), "", lim("Limit", "Limit"), ""), "UNSAMPLED"),
        ((lim("Limit", "Limit"), gave, lim("Limit", "Limit"), ""), "UNSAMPLED"),
        ((lim("Returned", "Limit"), "", lim("Limit", "Limit"), ""), "NOT-RUN"),                            # our side looped
        ((lim("Limit", "Returned"), "", lim("Limit", "Returned"), ""), "NOT-RUN"),                         # the generated original returned
        ((lim("Limit", "Returned"), "", lim("Returned", "Limit"), ""), "NOT-RUN"),
        ((lim("Limit", "Returned"), "", None, ""), "NOT-RUN"),                                                  # no shadow pass
        ((lim("Limit", "Returned"), "", lim("Limit", "Limit"), smis), "MISMATCH"),                           # the shadow log disagrees
        ((lim("Limit", "Returned"), "", lim("Limit", "Limit"),
          smis.replace(f"0x{a} unit_crit", "0x002C48F8 unit_stat_cap")), "NOT-RUN"),                              # a callee disagreed
        ((head + summ.format(1, 0, 1, 0), "", head + summ.format(1, 0, 1, 0), ""), "NOT-RUN"),                    # stuck, no Limit line
        # not in verify's sample: 0 functions in both passes AND a holder in the entry table
        ((summ.format(0, 0, 0, 0), "", summ.format(0, 0, 0, 0), "", "f_002C4D00"), "UNSAMPLED"),
        ((summ.format(0, 0, 0, 0), "", summ.format(0, 0, 0, 0), ""), "NOT-RUN"),                                # no holder
        ((summ.format(0, 0, 0, 0), "", head + one_ok, smatch, "f_002C4D00"), "NOT-RUN"),                        # the shadow pass ran
        ((summ.format(0, 0, 0, 0), "", None, "", "f_002C4D00"), "NOT-RUN"),                                      # no shadow pass
    ]
    global CALLS_OVERRIDE
    CALLS_OVERRIDE = {a: {"002EBA08", "004F0FDC", "00700000"}, "002EBA08": {"00531428"}, "00531428": {"0053386C"},
                      "0053386C": set(), "004F0FDC": set(), "00600000": set(), "00600100": set()}
    try:
        for combo, want in combos:
            got = classify_function(a, *combo)[0]
            if got != want:
                errs.append(f"selftest: function verdict {got}, want {want} ({str(combo[2])[-40:]!r})")
        # both at once (round 11, battle2): a nested override AND a callee with a one-time cache.
        # Made-up graphs: a -> 002EBA08 (logged override) and a -> 0052FB98, which calls the guard
        # routine (and 002EBA08); variants without the guard call, with the filler itself logged, none.
        g = one_time_guard() or "00302C6C"
        sb = lambda x, y, more="": head + f"  executable {a}  {more}{x} faults against {y}\n" + one_bad  # noqa: E731
        with_guard = {a: {"002EBA08", "0052FB98"}, "002EBA08": set(), "0052FB98": {g, "002EBA08"}}
        no_guard = {a: {"002EBA08", "0052FB98"}, "002EBA08": set(), "0052FB98": {"002EBA08"}}
        filler_logged = {a: {"002EBA08"}, "002EBA08": {g}}
        snest_filler = "[fe-readable] 0x0052FB98 filler: shadow match (1 so far, 0 mismatches)\n"
        both = [
            (with_guard, (abi, "", sb(310, 440, "memory at 0FFFEFD4, "), snest + smatch), "ABI-ONLY"),  # the real case
            (with_guard, (head + one_ok, "", sb(310, 440), snest + smatch), "CLEAN"),
            (no_guard, (abi, "", sb(310, 440), snest + smatch), "MISMATCH"),          # no one-time cache: no reason
            (filler_logged, (abi, "", sb(310, 440), snest + smatch), "MISMATCH"),     # only cache is in a logged override
            (with_guard, (abi, "", sb(310, 440), snest + snest_filler + smatch), "MISMATCH"),  # the filler logged
            (None, (abi, "", sb(310, 440), snest + smatch), "MISMATCH"),              # no call graph: fails closed
            (with_guard, (abi, "", sb(310, 310), snest + smatch), "MISMATCH"),        # no surplus
            (with_guard, (abi, "", sb(310, 440), smatch), "ABI-ONLY"),                # no nested: the round-8 rule
            (with_guard, (abi, "", sb(310, 440, "r0 1 against 2, "), snest + smatch), "MISMATCH"),
            (with_guard, (abi, "", sb(310, 440, "memory at 004D0C88, "), snest + smatch), "MISMATCH"),
            (with_guard, (abi, "", sb(310, 440), snest + smatch + smis.replace(f"0x{a} unit_crit", "0x002EBA08 unit_has_skill")), "MISMATCH"),
            (with_guard, (abi, gave, sb(310, 440), snest + smatch), "GAVE-UP"),        # after a give-up: never a pass
            (with_guard, (head + f"  executable {a}  310 faults against 311\n" + one_bad, "", sb(310, 440), snest + smatch), "MISMATCH"),
        ]
        for graph, combo, want in both:
            CALLS_OVERRIDE = {} if graph is None else graph
            _calls_cache.clear()
            got = classify_function(a, *combo)[0]
            if got != want:
                errs.append(f"selftest: function verdict {got}, want {want} (both at once: {str(combo[2])[-40:]!r}, "
                            f"{str(combo[3])[-40:]!r})")
    finally:
        CALLS_OVERRIDE = None
        _calls_cache.clear()
    # entry_holder on a made-up entry table (function 0x00200000..0x00200040)
    tab = lambda *rows: "".join(f"    {{0x{k:08X}u, {n}}},\n" for k, n in rows)  # noqa: E731
    holder_cases = [
        (tab((0x00200000, "override_0x00200000"), (0x00200010, "f_001FFFF8"), (0x00200020, "f_001FFFF8")), "f_001FFFF8"),
        (tab((0x00200000, "override_0x00200000"), (0x00200010, "f_00300000")), "f_00300000"),   # tail-call target
        (tab((0x00200000, "override_0x00200000"), (0x00200010, "f_00200000")), None),           # its own code
        (tab((0x00200000, "override_0x00200000"), (0x00200040, "f_00200040")), None),           # nothing inside
        (tab((0x00200000, "override_0x00200000"), (0x00200010, "f_001FFFF8"), (0x00200020, "f_00200000")), None),
        (tab((0x00200010, "override_0x00200010")), None),
        (None, None),
    ]
    for text, want in holder_cases:
        got = entry_holder(text, "00200000", 0x00200040)
        if got != want:
            errs.append(f"selftest: entry_holder {got}, want {want}")
    try:
        import verify  # noqa: E402  (same folder)
        verrs, vsum = verify.selftest()
        errs += verrs
    except SystemExit as e:   # a broken pipeline self-test must fail, never pass
        errs.append(f"selftest: verify pipeline self-test stopped: {e}")
        vsum = "verify pipeline self-test: stopped"
    print(f"self-test: {rejected}/{total} broken inputs rejected, {len(samples)} verify-log samples, "
          f"{len(combos) + len(both)} verdict combinations, {len(holder_cases)} entry-table cases")
    print(vsum)
    return errs


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--verify-logs", metavar="DIR")
    a = ap.parse_args(argv)
    if a.verify_logs:
        return verify_logs(a.verify_logs)
    errs = lint() + lint_generated()
    print(f"lint: {len(registry())} registry row(s), {len(errs)} problem(s)")
    skipped = None
    if not a.no_compile:
        cc = find_cc()
        if cc is None:
            skipped = "no host C compiler (set FE_HOST_CC)"
        else:
            e, notes = compile_checks(cc)
            errs += e
            for n in notes:
                print(n)
    else:
        skipped = "--no-compile"
    if a.selftest:
        errs += selftest()
    for e in errs:
        print(e)
    if errs:
        print(f"readable: {len(errs)} problem(s)")
        return 1
    print("readable: OK" + (f" (compile SKIPPED: {skipped})" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
