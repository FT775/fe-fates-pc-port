#!/usr/bin/env python3
"""Planted bugs in readable functions, replayed offline (docs/HARNESS.md 5 "Mutation", milestone H6).
Standard library only. Run through harness.py:

    python tools/harness/harness.py --mutate --fake
            fakelib proof: invented records (synth, several seeds) and the right rows of
            fake_readable.c; no game, no library from the game
    python tools/harness/harness.py --mutate --run NAME --functions a,b,...
            game records of build/harness/runs/NAME (a store-mode headless run, FE_CAPTURE_STORE=keep)
            and the named readable functions (names or addresses from config/readable/functions.csv)
    python tools/harness/harness.py --mutate --writer-callees
            print the readable callees of the HOOK_LIST writer slots that have an address (asm/ needed)

How one mutant is made and judged:

1. A scratch copy of the function's source file gets ONE change inside the function's body (or the
   body of a static helper of the same file that the function calls directly). Operators:
     rel       a comparison flipped (< <=, > >=, == !=)
     arith     + -, & |, && ||, << >>, += -=, |= &= swapped
     const     an integer literal plus 1
     named     a named constant (ALL_CAPS macro used as a value) plus 1
     drop      a guest store (guest_set_*, WRITE_FIELD) removed
     swap      the first two value arguments of a call swapped (memory primitives and commutative
               helpers left out)
     field     READ_FIELD / WRITE_FIELD / FIELD_ADDR moved to the next field (+ the field's size)
     giveup    the condition of a give-up (fe_use_original, fe_gave_up, fe_static_ready) inverted
2. Only that file is recompiled (warnings allowed: a dropped store can leave a variable unused);
   every other object comes from a cache built once with the normal -Werror flags, then linked.
   A mutant that does not compile is STILLBORN and not counted.
3. replay.exe of the mutant replays the kept records of the chosen addresses, side readable. The
   mutant is CAUGHT when a record is MISMATCH (r0, regs, mem, calls) or B-ESCAPED (also replay.exe's
   RUNAWAY stop: run B left the record and kept reading made-up bytes, exit 4), or replay.exe crashes
   or hangs (wall-clock timeout: a last resort, reported apart); it SURVIVED otherwise. Before any mutant the unchanged build must replay with
   0 bad records (baseline), or nothing is judged.
4. A survivor is tagged with gcov line counts of the baseline, read from the section of the target
   .c file only (gcov -t also prints every header with inline code, whose line numbers overlap):
   `not reached` (the changed line never ran in any record: a test gap) or `reached` (it ran and
   nothing differed). The `why` column is filled in AUTOMATICALLY from that tag (test gap / value
   gap / harmless); a `reached` survivor is a value gap or an equivalent mutant, and only the
   entries of mutants_equivalent.csv (reviewed by hand, each with its reason) turn one into
   `equivalent`. Nothing else in the column is a hand verdict.

Output (small, under build/harness/mutate/LABEL/, gitignored): mutants.csv (one row per mutant) and
mutate.json (per-function counts). The scratch sources, objects and mutant executables are deleted
as each mutant finishes; the object cache stays (regenerated in a minute)."""
from __future__ import annotations

import concurrent.futures
import csv
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))

import check as rcheck  # noqa: E402

MUT_DIR = os.path.join(ROOT, "build", "harness", "mutate")
RUNAWAY_RC = 4  # replay.c RP_EXIT_RUNAWAY
CAUGHT_VERDICTS = ("mismatch_r0", "mismatch_regs", "mismatch_mem", "mismatch_calls", "b_escaped")
BAD_BASELINE = CAUGHT_VERDICTS + ("unfaithful", "damaged")

KEYWORDS = {"return", "case", "sizeof", "if", "else", "while", "for", "do", "switch", "goto", "break",
            "continue", "default", "static", "const", "unsigned", "signed", "int", "char", "void"}
# calls whose arguments are not swapped: memory primitives (address/value: an escape, not a bug model),
# give-up helpers, and commutative helpers (a swap would be an equivalent mutant by construction)
NO_SWAP = {"READ_FIELD", "WRITE_FIELD", "FIELD_ADDR", "fe_use_original", "fe_static_ready", "fe_gave_up",
           "fe_add32", "fe_mul32", "fe_asr", "guest_ptr", "FE_MEMBER", "offsetof", "sizeof"}
NO_SWAP_RX = re.compile(r"^(guest_(set_)?[su](8|16|32|64)|guest_set_ptr)$")
NO_NAMED = {"NULL", "EXIT_NONE", "EXIT_UNWIND", "FE_MODE_READABLE", "FE_MODE_CAPTURE", "FE_MODE_ORIGINAL"}
GIVEUP_RX = re.compile(r"\b(fe_use_original|fe_gave_up|fe_static_ready)\b")
STORE_RX = re.compile(r"\b(guest_set_\w+|WRITE_FIELD)\s*\(")
FIELD_RX = re.compile(r"\b(READ_FIELD|WRITE_FIELD|FIELD_ADDR)\s*\(")
TOKEN_RX = re.compile(r"<<=|>>=|<<|>>|->|<=|>=|==|!=|&&|\|\||\+\+|--|\+=|-=|&=|\|=|\^=|\*=|/=|%=|"
                      r"0[xX][0-9A-Fa-f]+[uUlL]*|\d+[uUlL]*|[A-Za-z_]\w*|\S")
INT_RX = re.compile(r"^(0[xX][0-9A-Fa-f]+|\d+)([uUlL]*)$")
REL_FLIP = {"<": "<=", "<=": "<", ">": ">=", ">=": ">", "==": "!=", "!=": "=="}
ARITH_FLIP = {"+": "-", "-": "+", "&": "|", "|": "&", "&&": "||", "||": "&&", "<<": ">>", ">>": "<<"}
COMPOUND_FLIP = {"+=": "-=", "-=": "+=", "|=": "&=", "&=": "|="}


@dataclass
class Mutant:
    mid: str
    function: str      # the readable function whose body (or helper's body) changed
    where: str         # the function or helper actually edited
    op: str
    line: int
    old: str
    new: str
    text: str = field(repr=False)
    src_line: str = ""  # the original line, whitespace squeezed (the key of mutants_equivalent.csv)
    col: int = 0        # column of the change in that line (two equal changes on one line differ)


# ------------------------------------------------------------------ finding functions in a source
def match_paren(code: str, i: int, open_c: str = "(", close_c: str = ")") -> int:
    """Index of the bracket closing the one at code[i] (code already stripped of comments/strings)."""
    depth = 0
    for j in range(i, len(code)):
        if code[j] == open_c:
            depth += 1
        elif code[j] == close_c:
            depth -= 1
            if depth == 0:
                return j
    return -1


def find_function(code: str, name: str) -> tuple[int, int, bool] | None:
    """(index of '{', index of '}', is static) of the definition of name, in stripped code."""
    for m in re.finditer(r"^([A-Za-z_][\w \t\*]*?)\b" + re.escape(name) + r"\s*\(", code, re.M):
        close = match_paren(code, m.end() - 1)
        if close < 0:
            continue
        k = close + 1
        while k < len(code) and code[k] in " \t\r\n":
            k += 1
        if k < len(code) and code[k] == "{":
            end = match_paren(code, k, "{", "}")
            if end > 0:
                return k, end, "static" in m.group(1).split()
    return None


def static_helpers(code: str, start: int, end: int, own: str) -> list[str]:
    """Static functions of the same file called directly in code[start:end] (one level)."""
    out = []
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", code[start:end]):
        n = m.group(1)
        if n in out or n == own or n in KEYWORDS:
            continue
        f = find_function(code, n)
        if f and f[2]:
            out.append(n)
    return out


def split_args(code: str, open_i: int, close_i: int) -> list[tuple[int, int]]:
    """(start, end) spans of the top-level arguments between the parentheses."""
    spans, depth, s = [], 0, open_i + 1
    for j in range(open_i + 1, close_i):
        c = code[j]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            spans.append((s, j))
            s = j + 1
    spans.append((s, close_i))
    return spans


def stripped_arg(code: str, span: tuple[int, int]) -> tuple[int, int]:
    a, b = span
    while a < b and code[a].isspace():
        a += 1
    while b > a and code[b - 1].isspace():
        b -= 1
    return a, b


# ------------------------------------------------------------------ operators
def mutants_in(text: str, code: str, start: int, end: int, function: str, where: str) -> list[tuple]:
    """(op, pos, length, replacement, old) edits inside code[start:end]."""
    edits = []
    toks = [(m.group(0), m.start()) for m in TOKEN_RX.finditer(code, start, end)]
    for i, (tok, pos) in enumerate(toks):
        prev = toks[i - 1][0] if i else ""
        nxt = toks[i + 1][0] if i + 1 < len(toks) else ""
        binary = bool(prev) and (re.match(r"^[A-Za-z_0-9]", prev) is not None and prev not in KEYWORDS
                                 or prev in (")", "]"))
        if tok in REL_FLIP:
            edits.append(("rel", pos, len(tok), REL_FLIP[tok], tok))
        elif tok in ARITH_FLIP and (binary or tok in ("&&", "||")):
            edits.append(("arith", pos, len(tok), ARITH_FLIP[tok], tok))
        elif tok in COMPOUND_FLIP:
            edits.append(("arith", pos, len(tok), COMPOUND_FLIP[tok], tok))
        elif INT_RX.match(tok) and not re.match(r"^[A-Za-z_]", tok):
            m = INT_RX.match(tok)
            digits, suffix = m.group(1), m.group(2)
            v = int(digits, 16) if digits.lower().startswith("0x") else int(digits)
            new = (f"0x{v + 1:X}" if digits.lower().startswith("0x") else str(v + 1)) + suffix
            edits.append(("const", pos, len(tok), new, tok))
        elif (re.match(r"^[A-Z][A-Z0-9_]*[A-Z][A-Z0-9_]*$", tok) and len(tok) >= 2 and nxt != "(" and
              tok not in NO_NAMED and prev not in (".", "->", "#")):
            edits.append(("named", pos, len(tok), f"({tok} + 1)", tok))
    # dropped stores: a guest store that is a whole statement
    for m in STORE_RX.finditer(code, start, end):
        close = match_paren(code, m.end() - 1)
        k = close + 1
        while k < end and code[k] in " \t":
            k += 1
        if close > 0 and k < end and code[k] == ";":
            old = text[m.start():k + 1]
            edits.append(("drop", m.start(), k + 1 - m.start(), "(void)0;" + "\n" * old.count("\n"), old))
    # field offsets: the next field (base + the field's size)
    for m in FIELD_RX.finditer(code, start, end):
        close = match_paren(code, m.end() - 1)
        args = split_args(code, m.end() - 1, close)
        first = 1 if m.group(1) != "FIELD_ADDR" else 0
        if len(args) < first + 3:
            continue
        t_a, t_b = stripped_arg(code, args[first])
        b_a, b_b = stripped_arg(code, args[first + 1])
        f_a, f_b = stripped_arg(code, args[first + 2])
        tname, base, member = text[t_a:t_b], text[b_a:b_b], text[f_a:f_b]
        edits.append(("field", b_a, b_b - b_a, f"({base}) + (gaddr)sizeof(FE_MEMBER({tname}, {member}))",
                      f"{m.group(1)} {member}"))
    # swapped arguments
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", code[start:end]):
        name = m.group(1)
        if name in KEYWORDS or name in NO_SWAP or NO_SWAP_RX.match(name) or STORE_RX.match(name + "("):
            continue
        open_i = start + m.end() - 1
        close = match_paren(code, open_i)
        if close < 0 or close > end:
            continue
        args = [stripped_arg(code, s) for s in split_args(code, open_i, close)]
        if not args or text[args[0][0]:args[0][1]] != "ctx":
            continue
        first = 2 if re.match(r"^guest_call\d?$", name) else 1
        if len(args) < first + 2:
            continue
        (a1, b1), (a2, b2) = args[first], args[first + 1]
        x, y = text[a1:b1], text[a2:b2]
        if x == y:
            continue
        edits.append(("swap", a1, b2 - a1, y + text[b1:a2] + x, f"{name}({x}, {y})"))
    # inverted give-ups
    for m in re.finditer(r"\bif\s*\(", code[start:end]):
        open_i = start + m.end() - 1
        close = match_paren(code, open_i)
        if close < 0:
            continue
        semi = code.find(";", close)
        body = code[close + 1:semi + 1] if semi > 0 else ""
        cond = code[open_i + 1:close]
        if GIVEUP_RX.search(cond) or "fe_use_original" in body:
            old = text[open_i + 1:close]
            edits.append(("giveup", open_i + 1, close - open_i - 1, f"!({old})", f"if ({old.strip()})"))
    return edits


MUTANT_CAP = 120  # per function; a cut is reported, never silent


def make_mutants(path: str, function: str, helpers: bool = True, cap: int = MUTANT_CAP,
                 say=None) -> list[Mutant]:
    text = open(path, encoding="utf-8").read()
    code = rcheck.strip_code(text)
    f = find_function(code, function)
    if f is None:
        return []
    targets = [(function, f)]
    if helpers:
        for h in static_helpers(code, f[0], f[1], function):
            hf = find_function(code, h)
            if hf:
                targets.append((h, hf))
    out, seen = [], set()
    for where, (s, e, _st) in targets:
        for op, pos, ln, new, old in mutants_in(text, code, s, e, function, where):
            mtext = text[:pos] + new + text[pos + ln:]
            if mtext in seen or mtext == text:
                continue
            seen.add(mtext)
            line = text.count("\n", 0, pos) + 1
            src_line = " ".join(text.splitlines()[line - 1].split())
            col = pos - (text.rfind(chr(10), 0, pos) + 1)
            out.append(Mutant("", function, where, op, line, " ".join(old.split())[:60],
                              " ".join(new.split())[:80], mtext, src_line, col))
    if len(out) > cap:
        (say or print)(f"mutate: WARNING: {function}: {len(out)} mutants, only the first {cap} kept "
                       f"({len(out) - cap} left out of the score)")
        out = out[:cap]
    for k, m in enumerate(out):
        m.mid = f"{function}-{k:03d}"
    return out


# ------------------------------------------------------------------ building
# At most this many child processes (compiler, linker, replay.exe, gcov) at once over every mutate() of this
# process, when set (h56.py h6 runs several source files side by side and sets it to its job share). None: no
# limit beyond each mutate()'s own thread pool (the old behaviour).
_SLOTS: threading.BoundedSemaphore | None = None


def set_process_limit(n: int | None) -> None:
    global _SLOTS
    _SLOTS = threading.BoundedSemaphore(n) if n else None


def run(cmd: list[str], env_extra: dict | None = None, timeout: float = 600, cwd: str | None = None):
    env = dict(os.environ)
    cc = rcheck.find_cc()
    if cc and os.path.isabs(cc):
        env["PATH"] = os.path.dirname(cc) + os.pathsep + env.get("PATH", "")
    env.update(env_extra or {})
    try:
        with _SLOTS or nullcontext():  # the timeout counts from the start of the child, not the wait for a slot
            r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout, cwd=cwd)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return -9, "timeout"
    except OSError as e:  # no such program
        return 127, str(e)


def norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def obj_name(src: str) -> str:
    rel = os.path.relpath(src, ROOT).replace("\\", "/")
    return re.sub(r"[^A-Za-z0-9_.]", "_", rel)[:-2] + ".o"


class Builder:
    """An object cache of every source of one replay.exe; a mutant recompiles one file and relinks."""

    def __init__(self, cc: str, cflags: list[str], incs: list[str], sources: list[str], work: str):
        self.cc, self.cflags, self.incs, self.sources, self.work = cc, cflags, incs, sources, work
        self.obj_dir = os.path.join(work, "obj")
        os.makedirs(self.obj_dir, exist_ok=True)
        self.objs = {norm(s): os.path.join(self.obj_dir, obj_name(s)) for s in sources}

    def compile_all(self, jobs: int) -> str:
        def one(s):
            o = self.objs[norm(s)]
            if os.path.isfile(o) and os.path.getmtime(o) > os.path.getmtime(s):
                return ""
            rc, out = run([self.cc] + self.cflags + self.incs + ["-c", s, "-o", o], timeout=900)
            return "" if rc == 0 else f"{rcheck.rel(s)}:\n{out}"
        # headers changed? then rebuild everything (cheap enough, and never stale)
        with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
            errs = [e for e in ex.map(one, self.sources) if e]
        return "\n".join(errs)

    def link(self, exe: str, replace: dict[str, str], extra: list[str] | None = None) -> str:
        replace = {norm(k): v for k, v in replace.items()}
        unknown = set(replace) - set(self.objs)
        if unknown:  # a mutant must replace a real object, never be linked next to the original
            return f"not a source of this build: {sorted(unknown)}"
        objs = [replace.get(norm(s), self.objs[norm(s)]) for s in self.sources]
        rc, out = run([self.cc] + objs + (extra or []) + ["-o", exe], timeout=600)
        return "" if rc == 0 else out

    def compile_one(self, src_copy: str, orig: str, obj: str, flags: list[str] | None = None,
                    strict: bool = False) -> str:
        fl = [f for f in self.cflags if strict or f != "-Werror"] + ([] if strict else ["-w"])
        rc, out = run([self.cc] + fl + (flags or []) + ["-I", os.path.dirname(orig)] + self.incs +
                      ["-c", src_copy, "-o", obj], timeout=600)
        return "" if rc == 0 else out


def header_stamp(incs: list[str]) -> float:
    newest = 0.0
    for i in range(1, len(incs), 2):
        for p in glob.glob(os.path.join(incs[i], "*.h")):
            newest = max(newest, os.path.getmtime(p))
    return newest


# ------------------------------------------------------------------ replaying
def replay_rows(exe: str, lib: str, run_dir: str, out: str, only: str, probes: str | None,
                timeout: float = 300) -> tuple[int, str, list[dict]]:
    cmd = [exe, "run", "--lib", lib, "--dir", os.path.abspath(run_dir), "--side", "readable",
           "--out", os.path.abspath(out), "--only", only]
    if probes:
        cmd += ["--probes", probes]
    rc, text = run(cmd, {"FE_READABLE": "original", "FE_READABLE_LOG": out + ".log"}, timeout=timeout)
    rows = []
    if os.path.isfile(out):
        with open(out, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                try:
                    rows.append(json.loads(ln))
                except ValueError:
                    break
    return rc, text, rows


def judge(results: list[tuple[int, str, list[dict]]], baseline_rows: int, baseline_matches: int = 0) -> tuple[str, str]:
    """(caught | survived, by what) over every run's replay of one mutant. A survivor that matched
    fewer records than the baseline gives up more: the original then runs, so the game stays right,
    but the harness loses evidence (`by` says how many)."""
    got = matches = 0
    for rc, text, rows in results:
        bad = [r for r in rows if r["verdict"] in CAUGHT_VERDICTS]
        if bad:
            r = bad[0]
            return "caught", f"{r['verdict']}@{r['address']}"
        if rc == RUNAWAY_RC:
            m = re.search(r"RUNAWAY: run B of ([0-9A-Fa-f]{8})", text or "")
            return "caught", "b_escaped@" + (f"0x{m.group(1).upper()}" if m else "?") + " (runaway: read outside the record without end)"
        if rc == -9:
            return "caught", "hang (replay.exe timed out)"
        if rc != 0:
            return "caught", f"crash (replay.exe exit {rc})"
        got += len(rows)
        matches += sum(1 for r in rows if r["verdict"] == "match")
    if got < baseline_rows:
        return "caught", f"crash ({got} of {baseline_rows} records replayed)"
    if matches < baseline_matches:
        return "survived", f"gives up more ({baseline_matches - matches} fewer matches)"
    return "survived", ""


def gcov_lines(builder: Builder, files: list[str], exe_dir: str, runs: list[str], lib: str, only: str,
               probes: str | None) -> dict[str, dict[int, int]]:
    """Line execution counts of files over the baseline replay (a coverage build of those files)."""
    cov_dir = os.path.join(exe_dir, "cov")
    if os.path.isdir(cov_dir):
        shutil.rmtree(cov_dir)
    os.makedirs(cov_dir)
    replace = {}
    for f in files:
        o = os.path.join(cov_dir, obj_name(f))
        err = builder.compile_one(f, f, o, ["--coverage", "-O0"], strict=False)
        if err:
            return {}
        replace[f] = o
    exe = os.path.join(cov_dir, "replay_cov.exe")
    if builder.link(exe, replace, ["--coverage"]):
        return {}
    for k, rd in enumerate(runs):
        replay_rows(exe, lib, rd, os.path.join(cov_dir, f"cov_{k}.jsonl"), only, probes)
    gcov = shutil.which("gcov") or os.path.join(os.path.dirname(builder.cc), "gcov.exe")
    out: dict[str, dict[int, int]] = {}
    for f in files:
        o = replace[f]
        rc, text = run([gcov, "-t", "-o", cov_dir, o], cwd=cov_dir)
        out[norm(f)] = parse_gcov(text, f)
    return out


GCOV_LINE_RX = re.compile(r"^\s*([0-9#=*-]+[*]?):\s*(\d+):(.*)$")


def parse_gcov(text: str, target: str) -> dict[int, int]:
    """{line: count} of the target source in `gcov -t` text. gcov prints one section per source
    file the object has code from (the .c file and every header with inline functions), each
    opened by a `-: 0:Source:PATH` line; only the target's section is read, else a header's
    line 105 would overwrite the .c file's line 105. {} when the target has no section."""
    want, want_base = norm(target), os.path.basename(target).lower()
    sections: dict[str, dict[int, int]] = {}
    cur: dict[int, int] | None = None
    for ln in text.splitlines():
        m = GCOV_LINE_RX.match(ln)
        if not m:
            continue
        c, n, rest = m.group(1).rstrip("*"), int(m.group(2)), m.group(3)
        if n == 0:
            if rest.startswith("Source:"):
                cur = sections.setdefault(rest[len("Source:"):].strip(), {})
            continue
        if c == "-" or cur is None:
            continue
        cur[n] = 0 if c.startswith("#") or c.startswith("=") else int(c)
    for path, counts in sections.items():
        if norm(path) == want:
            return counts
    same = [c for p, c in sections.items() if os.path.basename(p.replace("\\", "/")).lower() == want_base]
    return same[0] if len(same) == 1 else {}


# ------------------------------------------------------------------ the driver
@dataclass
class Target:
    function: str
    address: str      # "0x00201600"
    source: str       # absolute path


def mutate(label: str, targets: list[Target], runs: list[str], lib: str, cc: str, cflags: list[str],
           incs: list[str], sources: list[str], probes: str | None, jobs: int = 8,
           say=print, par_baseline: bool = False, deadline: float | None = None) -> tuple[int, dict]:
    """par_baseline: the baseline replays of the record folders run side by side (jobs at once) instead of one
    after another; the same rows, in the same order (h56.py h6 speed, round 8).
    deadline (time.time() value, h56.py h6 --budget-min): a mutant not started by then is not built or replayed;
    its row says result `unjudged`, by `time budget`, and it is not counted (judged = caught + survived). With a
    deadline the mutants are started in a fixed scrambled order (sha256 of the id), so a cut run's judged mutants are
    spread over every function of the file instead of being its first functions; the rows keep the usual order."""
    work = os.path.join(MUT_DIR, label)
    os.makedirs(work, exist_ok=True)
    started = time.time()
    builder = Builder(cc, cflags, incs, sources, os.path.join(MUT_DIR, "cache-" + label.split("-")[0]))
    stamp = header_stamp(incs)
    for o in builder.objs.values():  # a header newer than an object: rebuild it
        if os.path.isfile(o) and os.path.getmtime(o) < stamp:
            os.remove(o)
    err = builder.compile_all(jobs)
    if err:
        say(f"mutate: object cache does not build:\n{err[:2000]}")
        return 3, {}
    only = ",".join(sorted({t.address for t in targets}))
    base_exe = os.path.join(work, "replay_base.exe")
    err = builder.link(base_exe, {})
    if err:
        say(f"mutate: baseline link failed:\n{err[:2000]}")
        return 3, {}
    base_rows = 0
    per_addr: dict[str, int] = {}
    t0 = time.time()
    took: list[float] = []

    def base_one(k_rd):
        k, rd = k_rd
        t = time.time()
        res = replay_rows(base_exe, lib, rd, os.path.join(work, f"base_{k}.jsonl"), only, probes)
        took.append(time.time() - t)
        return res
    if par_baseline and len(runs) > 1:
        with concurrent.futures.ThreadPoolExecutor(max(1, jobs)) as ex:
            base_res = list(ex.map(base_one, enumerate(runs)))
    else:
        base_res = None
    for k, rd in enumerate(runs):
        rc, text, rows = base_res[k] if base_res is not None else base_one((k, rd))
        bad = [r for r in rows if r["verdict"] in BAD_BASELINE]
        if rc or bad:
            say(f"mutate: baseline is not clean on {rcheck.rel(rd)} (rc {rc}, {len(bad)} bad record(s): "
                f"{[(r['address'], r['verdict']) for r in bad][:3]}); nothing judged")
            return 1, {}
        base_rows += len(rows)
        for r in rows:
            if r["verdict"] == "match":
                per_addr[r["address"]] = per_addr.get(r["address"], 0) + 1
    # a mutant slower than this hangs: 20 x the mean baseline replay (each replay timed on its own, so replays run
    # side by side do not shorten it)
    hang = max(30.0, 20 * (sum(took) if took else time.time() - t0) / max(1, len(runs)))
    say(f"mutate: baseline clean: {base_rows} record(s) over {len(runs)} run(s); matches per address "
        f"{dict(sorted(per_addr.items()))}")
    cov = gcov_lines(builder, sorted({t.source for t in targets}), work, runs, lib, only, probes)

    mutants: list[tuple[Target, Mutant]] = []
    for t in targets:
        ms = make_mutants(t.source, t.function, say=say)
        if not ms:
            found = find_function(rcheck.strip_code(open(t.source, encoding="utf-8").read()), t.function)
            say(f"mutate: {t.function}: no mutants (" + ("its body has nothing to change: a call to another "
                "file's function" if found else f"function not found in {rcheck.rel(t.source)}") + ")")
        mutants += [(t, m) for m in ms]
    say(f"mutate: {len(mutants)} mutant(s) of {len(targets)} function(s)")

    def one(item: tuple[Target, Mutant]) -> dict:
        t, m = item
        row = {"id": m.mid, "function": m.function, "address": t.address, "edited": m.where,
               "file": rcheck.rel(t.source), "line": m.line, "operator": m.op, "old": m.old, "new": m.new,
               "source_line": m.src_line, "col": m.col}
        if deadline is not None and time.time() > deadline:
            row.update(result="unjudged", by="time budget")
            return row
        d = os.path.join(work, "m", m.mid)
        os.makedirs(d, exist_ok=True)
        src = os.path.join(d, os.path.basename(t.source))
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(m.text)
        obj = os.path.join(d, "m.o")
        if builder.compile_one(src, t.source, obj):
            row.update(result="stillborn", by="does not compile")
        else:
            exe = os.path.join(d, "replay.exe")
            err = builder.link(exe, {t.source: obj})
            if err:
                row.update(result="stillborn", by="does not link")
            else:
                res = [replay_rows(exe, lib, rd, os.path.join(d, f"r{k}.jsonl"), only, probes, hang)
                       for k, rd in enumerate(runs)]
                result, by = judge(res, base_rows, sum(per_addr.values()))
                row.update(result=result, by=by)
        if row["result"] == "survived":
            c = cov.get(os.path.normcase(os.path.abspath(t.source)), {})
            n = c.get(m.line)
            row["reached"] = "unknown" if not c else ("not reached" if not n else f"reached x{n}")
        shutil.rmtree(d, ignore_errors=True)
        return row

    rows = []
    order = list(range(len(mutants)))
    if deadline is not None:
        order.sort(key=lambda i: hashlib.sha256(mutants[i][1].mid.encode()).hexdigest())
    got: dict[int, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
        for k, (i, row) in enumerate(zip(order, ex.map(one, [mutants[i] for i in order]))):
            got[i] = row
            if (k + 1) % 25 == 0:
                say(f"  ... {k + 1}/{len(mutants)}")
    rows = [got[i] for i in range(len(mutants))]
    unjudged = sum(1 for r in rows if r["result"] == "unjudged")
    if unjudged:
        say(f"mutate: TIME BUDGET: {unjudged} of {len(mutants)} mutant(s) not judged (not counted)")
    shutil.rmtree(os.path.join(work, "m"), ignore_errors=True)
    for f in glob.glob(os.path.join(work, "base_*.jsonl*")) + [base_exe]:
        os.remove(f) if os.path.isfile(f) else None
    shutil.rmtree(os.path.join(work, "cov"), ignore_errors=True)

    stale = apply_equivalents(rows, say)
    for r in rows:  # a first reading of each survivor; mutants_equivalent.csv overrides it after a look
        if r["result"] != "survived" or r.get("why"):
            continue
        if r.get("by", "").startswith("gives up more"):
            r["why"] = "harmless: the readable side gives up more often and the original runs (fewer matches)"
        elif r.get("reached") == "not reached":
            r["why"] = "test gap: the changed line never ran in any record"
        else:
            r["why"] = "value gap: the line ran, but no record held a value that tells the two apart"
    fields = ["id", "function", "address", "edited", "file", "line", "operator", "old", "new", "result", "by",
              "reached", "why", "col", "source_line"]
    with open(os.path.join(work, "mutants.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    summary = summarize(rows)
    summary["_meta"] = {"stale_equivalents": stale, "label": label, "runs": [rcheck.rel(r) for r in runs], "baseline_records": base_rows,
                        "matches_per_address": per_addr, "seconds": round(time.time() - started, 1)}
    with open(os.path.join(work, "mutate.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    for fn, s in summary.items():
        if fn.startswith("_"):
            continue
        say(f"  {fn:34s} {s['caught']:3d}/{s['judged']:3d} caught ({s['rate']:5.1f}%; {s['caught_via_caller']} via a "
            f"caller's record, {s['caught_no_record']} by crash/timeout), {s['equivalent']} equivalent, "
            f"{s['stillborn']} stillborn, survivors: {s['survivors']}")
    tot = summary["_total"]
    say(f"mutate: {tot['caught']}/{tot['judged']} caught ({tot['rate']:.1f}%; equivalent mutants left out: "
        f"{tot['equivalent']}, stillborn: {tot['stillborn']}); {rcheck.rel(os.path.join(work, 'mutants.csv'))}")
    if tot["judged"] >= 10 and tot["caught"] == 0:
        say("mutate: WARNING: no mutant caught at all: the mutants may not be linked in (harness fault?)")
    if stale:
        say(f"mutate: {len(stale)} entry(ies) of {rcheck.rel(EQUIV)} matched no mutant of this run (other "
            f"functions, or the code changed)")
    return 0, summary


EQUIV = os.path.join(HERE, "mutants_equivalent.csv")
EQUIV_FIELDS = ["function", "operator", "old", "new", "col", "source_line", "why"]


def read_equivalents(path: str = EQUIV) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("function") and not r["function"].startswith("#")]


# An entry's `why` may end in "[id <mutant id> line <n>]": then it names that one mutant only (the key columns alone
# cannot tell apart two `return 0;` lines of one function). Round 42: the owner's 27 (F-037) are pinned this way;
# if the code moves, the entry matches nothing and is reported stale (never a wrong mark).
PIN_RX = re.compile(r"\[id ([A-Za-z_]\w*-\d+) line (\d+)\]\s*$")


def _pin_ok(r: dict, e: dict) -> bool:
    m = PIN_RX.search(e.get("why") or "")
    return m is None or (str(r.get("id", "")) == m.group(1) and str(r.get("line", "")) == m.group(2))


def apply_equivalents(rows: list[dict], say=print, path: str = EQUIV) -> list[str]:
    """Survivors listed in mutants_equivalent.csv (reviewed by hand, each with a reason) become
    `equivalent` and leave the score. A listed mutant that was CAUGHT proves its entry wrong: it is
    reported and stays caught. Entries that match nothing are returned (another run's functions, or
    the code changed). An entry pinned with "[id X line N]" (PIN_RX) matches only that mutant."""
    eq = read_equivalents(path)
    used = set()
    for r in rows:
        for k, e in enumerate(eq):
            if all(str(r.get(f, "")) == e[f] for f in ("function", "operator", "old", "new", "col", "source_line")) \
                    and _pin_ok(r, e):
                used.add(k)
                if r["result"] == "survived":
                    r["result"], r["why"] = "equivalent", e["why"]
                elif r["result"] == "caught":
                    say(f"mutate: WRONG equivalence entry (the mutant was caught): {r['id']} {e['why']}")
    return [f"{e['function']}: {e['operator']} {e['old']} -> {e['new']} in '{e['source_line']}'"
            for k, e in enumerate(eq) if k not in used]


def summarize(rows: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for r in rows + [dict(x, function="_total") for x in rows]:
        s = out.setdefault(r["function"], {"caught": 0, "survived": 0, "stillborn": 0, "equivalent": 0,
                                           "unjudged": 0, "caught_via_caller": 0, "caught_no_record": 0,
                                           "survivors": []})
        s[r["result"]] += 1
        if r["result"] == "caught":
            at = re.search(r"@(0x[0-9A-Fa-f]{8})", r.get("by", ""))
            if at and at.group(1).upper() != str(r.get("address", "")).upper():
                s["caught_via_caller"] += 1  # the record that told was another function's (a caller)
            elif not at:
                s["caught_no_record"] += 1   # a crash or timeout, no record named
        if r["result"] == "survived":
            s["survivors"].append(r["id"])
    for s in out.values():
        s["judged"] = s["caught"] + s["survived"]
        s["rate"] = 100.0 * s["caught"] / s["judged"] if s["judged"] else 0.0
        if len(s["survivors"]) > 12:
            s["survivors"] = s["survivors"][:12] + ["..."]
    return out


# ------------------------------------------------------------------ writer callees (HOOK_LIST)
# Fates: docs/harness/HOOK_LIST.md (round 8); the Awakening layout docs/tracks/HOOK_LIST.md is read the same way
HOOK_LISTS = (os.path.join(ROOT, "docs", "harness", "HOOK_LIST.md"), os.path.join(ROOT, "docs", "tracks", "HOOK_LIST.md"))
HOOK_LIST = next((p for p in HOOK_LISTS if os.path.isfile(p)), HOOK_LISTS[0])
SLOT_ID_RX = re.compile(r"^[A-Z]+\d+$")
NAME_TICK_RX = re.compile(r"`([A-Za-z_]\w*)`")


def hook_rows(path: str = HOOK_LIST) -> list[dict]:
    """Every writer slot row of a HOOK_LIST: {"id", "entry": int | None, "named": [identifiers in backticks of the
    table's 'readable callees' column, when the table has one]}. Parked rows and 'Not hooks' have no id: never read.
    'entry X' wins over the first address of the address cell (column 3); 'blank' gives no entry."""
    out, callee_col = [], None
    for ln in open(path, encoding="utf-8"):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if not ln.lstrip().startswith("|"):  # any line outside a table ends it
            callee_col = None
            continue
        if cells and cells[0].lower() == "id":  # a table header: where the callee column is, if any
            low = [c.lower() for c in cells]
            callee_col = low.index("readable callees") if "readable callees" in low else None
            continue
        if len(cells) < 4 or not SLOT_ID_RX.match(cells[0]):
            continue
        cell = cells[2]
        entry = None
        if not cell.lower().startswith("blank"):
            m = re.search(r"entry `(?:func_|0x)([0-9A-Fa-f]{8})`", cell) or re.search(r"`0x([0-9A-Fa-f]{8})`", cell)
            entry = int(m.group(1), 16) if m else None
        named = NAME_TICK_RX.findall(cells[callee_col]) if callee_col is not None and callee_col < len(cells) else []
        out.append({"id": cells[0], "entry": entry, "named": named})
    return out


def writer_slots(path: str = HOOK_LIST) -> list[tuple[str, int]]:
    """(slot id, entry address) of every writer row with an address."""
    return [(r["id"], r["entry"]) for r in hook_rows(path) if r["entry"] is not None]


def code_calls(entries: set[int], funcs_csv: str, code_bin: str, layout: str) -> dict[int, set[int]] | None:
    """{entry: direct bl/blx targets inside that function} decoded from code.bin; None without the files."""
    import bisect
    import gen_stubs  # noqa: E402  (same folder)
    if not (os.path.isfile(funcs_csv) and os.path.isfile(code_bin) and os.path.isfile(layout)):
        return None
    with open(layout, encoding="utf-8") as fh:
        lay = json.load(fh)
    with open(code_bin, "rb") as fh:
        code = fh.read()[: lay["text"]["size"]]
    base = lay["text"]["addr"]
    with open(funcs_csv, newline="", encoding="utf-8") as fh:
        spans = sorted((int(r["addr"], 16), int(r["end"], 16)) for r in csv.DictReader(fh))
    starts = [s_ for s_, _e in spans]
    calls: dict[int, set[int]] = {}
    for i in range(len(code) // 4):
        at = base + 4 * i
        t = gen_stubs.call_target(int.from_bytes(code[4 * i: 4 * i + 4], "little"), at)
        if t is None:
            continue
        j = bisect.bisect_right(starts, at) - 1
        if j >= 0 and at < spans[j][1] and spans[j][0] in entries:
            calls.setdefault(spans[j][0], set()).add(t & ~1)
    return calls


def writer_callees(funcs_csv: str = rcheck.FUNCTIONS, hook_list: str = HOOK_LIST, overrides: dict[int, str] | None = None,
                   code_bin: str | None = None, layout: str | None = None
                   ) -> tuple[list[tuple[str, int]], dict[int, list[str]]] | None:
    """Readable overrides a writer slot depends on: {override address: [slot ids]}. Two sources, joined:
    (1) the overrides the slot's game function calls directly (ARM bl/blx decoded from extracted/code.bin with
    config/functions.csv spans; skipped when those files are missing), (2) the overrides named in the slot's
    'readable callees' cell (our writer calls them, e.g. the GetValue compare). overrides: {address: name}
    (default: every registry override). None only without a HOOK_LIST."""
    import gen_stubs  # noqa: E402  (same folder)
    if not os.path.isfile(hook_list):
        return None
    if overrides is None:
        overrides = {int(r["address"], 16) & ~1: r["name"] for r in rcheck.registry() if r["kind"].strip() == "override"}
    by_name = {n: a for a, n in overrides.items()}
    rows = hook_rows(hook_list)
    slots = [(r["id"], r["entry"]) for r in rows if r["entry"] is not None]
    calls = code_calls({a for _s, a in slots}, funcs_csv, code_bin or gen_stubs.CODE_BIN, layout or gen_stubs.LAYOUT) or {}
    out: dict[int, list[str]] = {}
    for r in rows:
        got = {c for c in calls.get(r["entry"], ()) if c in overrides} if r["entry"] is not None else set()
        got |= {by_name[n] for n in r["named"] if n in by_name}
        for c in sorted(got):
            if r["id"] not in out.setdefault(c, []):
                out[c].append(r["id"])
    return slots, out


# ------------------------------------------------------------------ self-test of the operators
def selftest() -> tuple[list[str], str]:
    """Operators on an invented snippet (no compiler, no records): every kind appears where expected
    and nowhere else."""
    errs = []
    src = ("static uint32_t helper(Context *ctx, uint32_t a, uint32_t b) {\n    return a - b;\n}\n"
           "static uint32_t outside(Context *ctx) { return 1 + 2; }\n"
           "uint32_t fn(Context *ctx, gaddr p, uint32_t n) {\n"
           "    if (!fe_static_ready(ctx, 0x100u))\n        return fe_use_original(ctx);\n"
           "    /* comment < 5 */ uint32_t v = READ_FIELD(ctx, Foo, p, bar);\n"
           "    gaddr q = FIELD_ADDR(Foo, p + n, baz);\n"
           "    if (v >= LIMIT_X && n != 0)\n        v = helper(ctx, v, n);\n"
           "    guest_set_u8(ctx, p + 4, (uint8_t)v);\n    return v << 1;\n}\n")
    ms = make_mutants_text(src, "fn")
    ops = {}
    for m in ms:
        ops.setdefault(m.op, []).append((m.where, m.old, m.new))
    want = {"rel": 2, "arith": 5, "giveup": 1, "drop": 1, "field": 2, "swap": 1, "named": 1}
    for op, n in want.items():
        if len(ops.get(op, [])) != n:
            errs.append(f"mutate selftest: {op}: {len(ops.get(op, []))} mutant(s), want {n}: {ops.get(op)}")
    if any(w == "outside" for m in ms for w in [m.where]):
        errs.append("mutate selftest: a function the target never calls was mutated")
    if not any(m.where == "helper" and m.op == "arith" for m in ms):
        errs.append("mutate selftest: the static helper the target calls was not mutated")
    if any("comment" in m.old or m.line == 7 and m.op == "const" and m.old == "5" for m in ms):
        errs.append("mutate selftest: a comment was mutated")
    consts = sorted(m.new for m in ms if m.op == "const")
    if consts != ["0x101u", "1", "2", "5"]:
        errs.append(f"mutate selftest: constants {consts}")
    # the field operator moves the BASE argument by the size of the named member (READ_FIELD: arguments
    # ctx, type, base, member; FIELD_ADDR: type, base, member), nothing else
    fields = sorted((m.new, m.old) for m in ms if m.op == "field")
    if fields != [("(p + n) + (gaddr)sizeof(FE_MEMBER(Foo, baz))", "FIELD_ADDR baz"),
                  ("(p) + (gaddr)sizeof(FE_MEMBER(Foo, bar))", "READ_FIELD bar")] or not any(
            "READ_FIELD(ctx, Foo, (p) + (gaddr)sizeof(FE_MEMBER(Foo, bar)), bar)" in m.text for m in ms):
        errs.append(f"mutate selftest: field operator moved the wrong argument: {fields}")
    drop = [m for m in ms if m.op == "drop"]
    if drop and drop[0].text.count("\n") != src.count("\n"):
        errs.append("mutate selftest: a dropped store changed the line count")
    import tempfile
    hl_text = ("| id | slot | address | writes | readable callees | risk |\n|---|---|---|---|---|---|\n"
               "| O1 | a | entry `0x00200100` (x) | b | `fake_heal`, `not_an_override` | `fake_touch` in risk |\n"
               "| O2 | c | blank | d | `fake_caller` | x |\n"
               "| parked | `0x00200400` | no id |\n\n"
               "| id | slot | address | writes |\n|---|---|---|---|\n| P1 | e | `0x00200500` | `fake_count` |\n")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(hl_text)
        hl_path = fh.name
    fake_ov = {0x00200000: "fake_heal", 0x00200500: "fake_caller", 0x00201400: "fake_touch", 0x00201700: "fake_count"}
    rows_ = hook_rows(hl_path)
    got_wc = writer_callees(os.path.join(tempfile.gettempdir(), "no_functions.csv"), hl_path, fake_ov,
                            os.path.join(tempfile.gettempdir(), "no_code.bin"), os.path.join(tempfile.gettempdir(), "no.json"))
    os.remove(hl_path)
    if [(r["id"], r["entry"], r["named"]) for r in rows_] != [("O1", 0x00200100, ["fake_heal", "not_an_override"]),
                                                               ("O2", None, ["fake_caller"]), ("P1", 0x00200500, [])]:
        errs.append(f"mutate selftest: hook rows read wrongly: {rows_}")
    if got_wc is None or got_wc[1] != {0x00200000: ["O1"], 0x00200500: ["O2"]}:
        errs.append(f"mutate selftest: writer callees from the readable-callees column wrong: {got_wc}")
    if writer_slots_text("| C2 | job | `0x002F2484` stores at `0x002F24A8` | x |\n"
                         "| UI1 | anim | entry `0x001D9A08`, store at `0x001D9A10`. | x |\n"
                         "| L1 | roll | blank | x |\n| C1 | cc | stores at `0x002D1024`. Candidate entry "
                         "`func_002D0FB8` | x |\n") != [("C2", 0x002F2484), ("UI1", 0x001D9A08), ("C1", 0x002D0FB8)]:
        errs.append("mutate selftest: writer slot addresses read wrongly")
    # the equivalence list: a survivor it names leaves the score, a caught one proves the entry wrong
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EQUIV_FIELDS)
        w.writeheader()
        for fn in ("f", "g", "h"):
            w.writerow({"function": fn, "operator": "rel", "old": "<", "new": "<=", "col": "4", "source_line": "x",
                        "why": "invented"})
        eq_path = fh.name
    rows = [{"id": "f-0", "function": "f", "operator": "rel", "old": "<", "new": "<=", "col": 4, "source_line": "x",
             "result": "survived"},
            {"id": "g-0", "function": "g", "operator": "rel", "old": "<", "new": "<=", "col": 4, "source_line": "x",
             "result": "caught"},
            {"id": "f-1", "function": "f", "operator": "rel", "old": "<", "new": "<=", "col": 5, "source_line": "x",
             "result": "survived"}]
    said = []
    stale = apply_equivalents(rows, said.append, eq_path)
    os.remove(eq_path)
    s = summarize(rows)["_total"]
    if not (rows[0]["result"] == "equivalent" and rows[1]["result"] == "caught" and rows[2]["result"] == "survived"
            and len(stale) == 1 and stale[0].startswith("h:") and any("WRONG" in x for x in said)
            and s["judged"] == 2 and s["equivalent"] == 1):
        errs.append(f"mutate selftest: equivalence list applied wrongly: {rows} {stale} {said} {s}")
    # a pinned entry ("[id X line N]") marks only that mutant, not another with the same key columns
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EQUIV_FIELDS)
        w.writeheader()
        w.writerow({"function": "p", "operator": "const", "old": "0", "new": "1", "col": "15",
                    "source_line": "return 0;", "why": "invented [id p-7 line 20]"})
        eq_path = fh.name
    prow = lambda i, ln, res: {"id": i, "function": "p", "operator": "const", "old": "0", "new": "1",  # noqa: E731
                               "col": 15, "source_line": "return 0;", "line": ln, "result": res}
    rows = [prow("p-7", 20, "survived"), prow("p-2", 9, "survived"), prow("p-3", 12, "caught"),
            prow("p-7", 21, "survived")]
    said = []
    stale = apply_equivalents(rows, said.append, eq_path)
    os.remove(eq_path)
    if [r["result"] for r in rows] != ["equivalent", "survived", "caught", "survived"] or stale or said:
        errs.append(f"mutate selftest: a pinned equivalence entry applied wrongly: {rows} {stale} {said}")
    if judge([(0, "", [{"verdict": "match"}, {"verdict": "gave_up"}])], 2, 2) != ("survived", "gives up more (1 fewer matches)")             or judge([(0, "", [{"verdict": "mismatch_mem", "address": "0x1"}])], 1)[0] != "caught"             or judge([(5, "", [])], 1)[0] != "caught" or judge([(0, "", [{"verdict": "match"}])], 2)[0] != "caught":
        errs.append("mutate selftest: judge() verdicts wrong")
    # every caught verdict, the runaway stop, the timeout, a crash: caught; gave_up / match: not
    for v in ("mismatch_r0", "mismatch_regs", "mismatch_mem", "mismatch_calls", "b_escaped"):  # spelled out
        if judge([(0, "", [{"verdict": v, "address": "0x00000002"}])], 1)[0] != "caught":
            errs.append(f"mutate selftest: verdict {v} not caught")
    for v in ("match", "gave_up", "faithful"):
        if judge([(0, "", [{"verdict": v, "address": "0x00000002"}])], 1)[0] != "survived":
            errs.append(f"mutate selftest: verdict {v} counted as caught")
    rw = judge([(RUNAWAY_RC, "replay: RUNAWAY: run B of 002EFB34 kept reading", [])], 1)
    if rw[0] != "caught" or not rw[1].startswith("b_escaped@0x002EFB34"):
        errs.append(f"mutate selftest: runaway stop judged {rw}")
    if judge([(-9, "timeout", [])], 1) != ("caught", "hang (replay.exe timed out)"):
        errs.append("mutate selftest: a timeout is not a caught hang")
    sm = summarize([{"id": "a", "function": "f", "address": "0x00000010", "result": "caught", "by": "mismatch_r0@0x00000010"},
                    {"id": "b", "function": "f", "address": "0x00000010", "result": "caught", "by": "b_escaped@0x00000020"},
                    {"id": "c", "function": "f", "address": "0x00000010", "result": "caught", "by": "hang (replay.exe timed out)"}])["f"]
    if (sm["caught_via_caller"], sm["caught_no_record"]) != (1, 1):
        errs.append(f"mutate selftest: catches via a caller / without a record counted wrongly: {sm}")
    # linking: a replacement that is not a source of the build is refused before any compiler runs
    b = Builder("no-such-cc", [], [], [os.path.join(ROOT, "src", "x", "a.c")], tempfile.mkdtemp())
    if "not a source of this build" not in b.link("x.exe", {os.path.join(ROOT, "src", "x", "b.c"): "m.o"}):
        errs.append("mutate selftest: link() accepted a replacement that is not a source of the build")
    if b.link("x.exe", {os.path.join(ROOT, "src", "x", "a.c").replace(os.sep, "/"): "m.o"}).startswith("not a source"):
        errs.append("mutate selftest: link() refused a source written with other slashes")
    shutil.rmtree(b.work, ignore_errors=True)
    # gcov: only the target file's section counts (a header with inline code overlaps its lines)
    gc = ("        -:    0:Source:C:/r/src/readable/m.c\n        -:    0:Graph:m.gcno\n"
          "        5:    3:  if (a)\n    #####:    4:    return 1;\n        -:    5:}\n"
          "        -:    0:Source:C:/r/include/readable/fe_guest.h\n        9:    4:static inline int g(void)\n"
          "       12:    6:  x;\n        -:    0:Source:C:/r/include/other/m.c\n        7:    3:y\n")
    got_m = parse_gcov(gc, "C:/r/src/readable/m.c")
    if got_m != {3: 5, 4: 0}:
        errs.append(f"mutate selftest: gcov section of the target read wrongly: {got_m}")
    if parse_gcov(gc, "C:/r/src/readable/zz.c") != {} or parse_gcov(gc, "D:/elsewhere/m.c") != {}:
        errs.append("mutate selftest: gcov counts of another file taken for the target")
    # the per-function cap reports a cut
    said2 = []
    big = "uint32_t big(Context *ctx, uint32_t a) {\n" + "".join(f"    a = a + {k};\n" for k in range(70)) + "    return a;\n}\n"
    with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(big)
    capped = make_mutants(fh.name, "big", say=said2.append)
    os.remove(fh.name)
    if len(capped) != MUTANT_CAP or not any("left out of the score" in x for x in said2):
        errs.append(f"mutate selftest: the mutant cap cut silently ({len(capped)} kept, said {said2})")
    return errs, f"mutate operators: {len(ms)} mutants of an invented snippet, every operator where expected; equivalence list and verdicts"


def make_mutants_text(text: str, function: str) -> list[Mutant]:
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        p = fh.name
    try:
        return make_mutants(p, function)
    finally:
        os.remove(p)


def writer_slots_text(text: str) -> list[tuple[str, int]]:
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        p = fh.name
    try:
        return writer_slots(p)
    finally:
        os.remove(p)
