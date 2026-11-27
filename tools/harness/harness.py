#!/usr/bin/env python3
"""Driver of the tier-4 record-and-replay harness (docs/HARNESS.md 3.5). Standard library only.

    python tools/harness/harness.py --selftest      fakelib: the whole pipeline with invented code and
                                                    memory (no ROM, no game library; fast, in check_all)
    python tools/harness/harness.py abi             ABI gate: stand-in header vs the library's recomp.h
    python tools/harness/harness.py build [--coverage]
                                                    abi gate, then compile build/harness/replay/replay.exe
                                                    (src/readable natively + tools/harness/replay.c)
    python tools/harness/harness.py synth --run NAME [--image build/code.bin] [--addrs all|a,b]
                                     [--calls N] [--seed S] [--live ab|a]
                                                    made-up states through the real capture runtime:
                                                    records, live runs A and B, summary.tsv
    python tools/harness/harness.py replay --run NAME [--side readable|original|both] [--only a,b]
                                                    offline replay of a run's records (JSON lines)
    python tools/harness/harness.py classify --run NAME
                                                    per-function verdicts from the offline replay
    python tools/harness/harness.py report [--runs a,b]
                                                    merge the runs' summary.tsv files (counts add,
                                                    path signatures unite) -> build/harness/report.json
    python tools/harness/harness.py coverage --run NAME
                                                    gcov branch coverage of the readable side (needs
                                                    `build --coverage` and a replay)
    python tools/harness/harness.py shots FILE.ppm... --run NAME
                                                    PPM screenshots (boot.exe's dumps) -> PNG under
                                                    build/harness/shots/NAME/ (for H4a)
    python tools/harness/harness.py smoke [--calls N] [--seeds 1,2,3] [--keep]
                                                    abi + build + synth on the real library and the
                                                    code image + replay both sides + report; the
                                                    records are dropped after a clean replay
    python tools/harness/harness.py headless --run NAME [--route prologue] [--mode original|capture]
                                     [--live ab|a] [--no-late] [--save ZIP] [--keep-state]
                                     [--only a,b [--store | --store-keep]]
                                                    one windowless boot.exe run of the capture library
                                                    from a scratch copy of the newest PLAY save backup
                                                    (tools/harness/headless.py, config/harness/routes.json)
    python tools/harness/harness.py h4a [--route prologue] [--run h4a]
                                                    milestone H4a: determinism (original twice), then
                                                    capture with run A only, then runs A+B, each
                                                    savestate compared with original's; offline replay
                                                    of the kept records; report of the game run
    python tools/harness/harness.py --mutate --fake [--jobs N]
                                                    H6: planted bugs in the right rows of fakelib's
                                                    readable side, replayed on invented records
    python tools/harness/harness.py --mutate --run NAME --functions a,b [--jobs N]
                                                    H6: planted bugs in readable functions, replayed on
                                                    the kept game records of a store-mode run
                                                    (tools/harness/mutate.py; mutants.csv under
                                                    build/harness/mutate/)
    python tools/harness/harness.py --mutate --writer-callees
                                                    the readable callees of the HOOK_LIST writer slots
                                                    (docs/harness/HOOK_LIST.md); with --run NAME: H6 on
                                                    exactly those callees with that run's kept records
                                                    (a writer H6); with --fake: the same plumbing on the
                                                    fakelib (a made-up hook list, no game)

Library: --lib, else build/harness/lib/<title id>.dll (the capture library, H3), else the
tier-2 library build/readable/verify/lib/<title id>.dll. Its recomp.h is read in place for the
ABI gate and never copied. Everything is written under build/harness/ (gitignored): runs/<NAME>/
(records.fecap, pages/, summary.tsv, replay_*.jsonl, logs), replay/ (replay.exe, objects, gcov data),
selftest/, shots/, report.*. Nothing is written under %APPDATA%; no window is ever opened.

Storage policy (owner, 2026-11-10; HARNESS.md status line): runs compare live and keep only bad
records plus a small summary. `synth` keeps every record of its (made-up) states on purpose: that is
the working set the offline replay and the self-test need, regenerated in seconds.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))

import check as rcheck  # noqa: E402  (tools/readable/check.py: compiler search, source markers)

SRC = os.path.join(ROOT, "src", "readable")
INC = os.path.join(ROOT, "include", "readable")
STUB = os.path.join(ROOT, "tools", "readable", "stub")
BUILD = os.path.join(ROOT, "build", "harness")
RUNS = os.path.join(BUILD, "runs")
REPLAY_DIR = os.path.join(BUILD, "replay")
SELFTEST_DIR = os.path.join(BUILD, "selftest")
TARGETS = os.path.join(ROOT, "config", "harness", "targets.csv")
sys.path.append(os.path.join(ROOT, "tools"))  # gamecfg (appended: tools/build.py must not shadow tools/harness/build.py)
from gamecfg import GAME  # noqa: E402

LIB_NAME = f"{GAME.title_id}.dll"   # 3dsrecomp names the library after the title id
LIB_CANDIDATES = [os.path.join(BUILD, "lib", LIB_NAME),
                  os.path.join(ROOT, "build", "readable", "verify", "lib", LIB_NAME)]
EXE = ".exe" if os.name == "nt" else ""
INCS = ["-I", STUB, "-I", INC, "-I", os.path.join(INC, "generated"), "-I", HERE]
CFLAGS = ["-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-O1", "-fwrapv"]

VNAMES = ["none", "match", "mismatch_r0", "mismatch_mem", "mismatch_calls", "gave_up", "b_escaped",
          "faithful", "unfaithful", "incomplete", "escaped", "hostmem", "truncated"]
MISMATCH = ("mismatch_r0", "mismatch_regs", "mismatch_mem", "mismatch_calls")
BAD = MISMATCH + ("unfaithful", "b_escaped", "damaged")
ENTRY_RX = re.compile(r"FE_ENTRY0?\s*\(\s*(0x[0-9A-F]{8})\s*,\s*(\w+)")

# FeCapHeader (include/readable/fe_capture.h): magic, 16 words, entry and exit FeCapRegs (60 words)
HEADER = struct.Struct("<8s16I")
REGS_BYTES = 60 * 4
HEADER_BYTES = HEADER.size + 2 * REGS_BYTES
PAGE_BYTES = 24 + 4096 // 4
EVENT_BYTES = 16


def rel(p: str) -> str:
    return rcheck.rel(p)


def run(cmd: list[str], env_extra: dict | None = None, cwd: str | None = None,
        timeout: float = 600) -> tuple[int, str]:
    env = dict(os.environ)
    cc_dir = os.path.dirname(cmd[0]) if os.path.isabs(cmd[0]) else ""
    cc = rcheck.find_cc()
    for d in (cc_dir, os.path.dirname(cc) if cc else ""):
        if d and os.path.isdir(d):  # MSYS2 tools need their own DLLs on PATH
            env["PATH"] = d + os.pathsep + env.get("PATH", "")
    env.update(env_extra or {})
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def find_lib(arg: str | None) -> str | None:
    if arg:
        return os.path.abspath(arg) if os.path.isfile(arg) else None
    return next((p for p in LIB_CANDIDATES if os.path.isfile(p)), None)


def below_build(p: str) -> bool:
    p = os.path.abspath(p)
    return p.startswith(os.path.abspath(os.path.join(ROOT, "build")) + os.sep) and ".." not in p.split(os.sep)


# ------------------------------------------------------------------ ABI gate
def abi_lines(cc: str, defines: list[str], incs: list[str], out_dir: str, tag: str) -> tuple[list[str] | None, str]:
    os.makedirs(out_dir, exist_ok=True)
    exe = os.path.join(out_dir, f"abi_{tag}{EXE}")
    rc, out = run([cc, "-std=c11", "-Wall", "-Wextra", "-Wno-unused-function"] + defines + incs +
                  [os.path.join(HERE, "abi_check.c"), "-o", exe])
    if rc:
        return None, f"build abi_check ({tag}):\n{out}"
    rc, out = run([exe])
    if rc:
        return None, f"abi_check ({tag}) failed:\n{out}"
    return out.splitlines(), ""


def abi_compare(a: list[str], b: list[str]) -> list[str]:
    """Lines that differ (empty = same layout). Missing lines count."""
    diffs = [f"stub: {x} | generated: {y}" for x, y in zip(a, b) if x != y]
    if len(a) != len(b):
        diffs.append(f"line count {len(a)} vs {len(b)}")
    return diffs


def abi_gate(cc: str, lib_dir: str, out_dir: str) -> tuple[bool, str]:
    if not os.path.isfile(os.path.join(lib_dir, "recomp.h")):
        return False, f"no recomp.h next to the library in {rel(lib_dir)}"
    a, err = abi_lines(cc, ["-DFE_ABI_STUB"], ["-I", STUB, "-I", HERE], out_dir, "stub")
    if a is None:
        return False, err
    b, err = abi_lines(cc, ["-DFE_ABI_GENERATED"], ["-I", lib_dir], out_dir, "generated")
    if b is None:
        return False, err
    diffs = abi_compare(a, b)
    if diffs:
        return False, "ABI differs (replay refused):\n  " + "\n  ".join(diffs)
    return True, f"abi: {len(a)} facts identical (stand-in vs {rel(os.path.join(lib_dir, 'recomp.h'))})"


# ------------------------------------------------------------------ building replay.exe
def native_overrides() -> list[tuple[str, str]]:
    """(address literal, readable function) of every override in src/readable."""
    out = []
    for s in rcheck.files_under(SRC, (".c",)):
        code = rcheck.strip_code(open(s, encoding="utf-8").read())
        for lit, end, _line in rcheck.markers(code):
            if lit.startswith("IN:"):
                continue
            m = ENTRY_RX.search(code, end)
            out.append((lit, m.group(2) if m and m.group(1) == lit else "?"))
    return sorted(set(out))


def write_table(path: str) -> int:
    rows = native_overrides()
    lines = ["/* GENERATED by tools/harness/harness.py from the override markers in src/readable: the",
             "   readable overrides compiled into replay.exe. Addresses and names only. */",
             '#include "overrides.h"', '#include "replay_abi.h"', ""]
    lines += [f"void override_{lit}(Context *ctx);" for lit, _ in rows]
    lines += ["", "const FeReplayOverride fe_replay_overrides[] = {"]
    lines += [f'    {{{lit}u, override_{lit}, "{name}"}},' for lit, name in rows]
    lines += ["};", "const unsigned fe_replay_override_count = sizeof fe_replay_overrides / "
              "sizeof fe_replay_overrides[0];", ""]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return len(rows)


def build_replay(cc: str, out_dir: str, readable: list[str], coverage: bool = False) -> tuple[str | None, str]:
    """Compiles replay.c + the readable sources (+ core/) into out_dir/replay.exe. With coverage the
    readable sources are compiled one by one with --coverage into out_dir/obj (gcov data there)."""
    os.makedirs(out_dir, exist_ok=True)
    exe = os.path.join(out_dir, "replay" + EXE)
    core = [os.path.join(SRC, "core", f) for f in ("capture.c", "runtime.c")]
    sources = [os.path.join(HERE, "replay.c")] + readable + [c for c in core if c not in readable]
    if not coverage:
        rc, out = run([cc] + CFLAGS + INCS + sources + ["-o", exe], timeout=900)
        return (exe, "") if rc == 0 else (None, f"build replay.exe:\n{out}")
    obj_dir = os.path.join(out_dir, "obj")
    if os.path.isdir(obj_dir):
        shutil.rmtree(obj_dir)
    os.makedirs(obj_dir)
    objs = []
    for s in sources:
        o = os.path.join(obj_dir, os.path.splitext(os.path.basename(s))[0] + "_" +
                         format(abs(hash(s)) % 0xFFFF, "04x") + ".o")
        flags = CFLAGS + (["--coverage"] if s in readable else [])
        rc, out = run([cc] + flags + INCS + ["-c", s, "-o", o], timeout=600)
        if rc:
            return None, f"compile {rel(s)}:\n{out}"
        objs.append(o)
    rc, out = run([cc, "--coverage"] + objs + ["-o", exe], timeout=600)
    return (exe, "") if rc == 0 else (None, f"link replay.exe:\n{out}")


def readable_sources() -> list[str]:
    return [s for s in rcheck.files_under(SRC, (".c",))]


def replay_inputs() -> list[str]:
    """Every file replay.exe is compiled from (readable code, its headers, replay.c and its header)."""
    return (readable_sources() + rcheck.files_under(INC, (".h",)) + rcheck.files_under(STUB, (".h",)) +
            [os.path.join(HERE, "replay.c"), os.path.join(HERE, "replay_abi.h")])


def replay_stale(exe: str, inputs: list[str] | None = None) -> list[str]:
    """Inputs newer than replay.exe (empty = fresh). A stale replay.exe runs old readable code, so its
    offline verdicts can disagree with live ones (SOLVED.md, H5 route 3): refuse it."""
    if not os.path.isfile(exe):
        return ["(no replay.exe)"]
    built = os.path.getmtime(exe)
    return [p for p in (replay_inputs() if inputs is None else inputs)
            if os.path.isfile(p) and os.path.getmtime(p) > built]


# ------------------------------------------------------------------ running replay.exe
def replay_env(run_dir: str) -> dict:
    return {"FE_READABLE": "original", "FE_READABLE_LOG": os.path.join(run_dir, "fe_readable.log")}


def synth(exe: str, lib: str, run_dir: str, image: str | None = None, addrs: str | None = None,
          calls: int = 12, seed: int = 1, probes: str | None = None, guard: str | None = None,
          live: str = "ab", fresh: bool = True) -> tuple[int, str]:
    if not below_build(run_dir):
        return 2, f"{run_dir}: not below build/"
    if fresh and os.path.isdir(run_dir):
        shutil.rmtree(run_dir)
    os.makedirs(run_dir, exist_ok=True)
    cmd = [exe, "synth", "--lib", lib, "--dir", os.path.abspath(run_dir), "--calls", str(calls),
           "--seed", str(seed), "--live", live]
    if image:
        cmd += ["--image", image]
    if addrs:
        cmd += ["--addrs", addrs]
    if probes:
        cmd += ["--probes", probes]
    if guard:
        cmd += ["--guard", guard]
    rc, out = run(cmd, replay_env(run_dir), timeout=3600)
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump({"source": "synth", "seed": seed, "calls": calls, "live": live, "image": bool(image),
                   "library": os.path.basename(lib), "library_bytes": os.path.getsize(lib)}, fh)
    return rc, out


def replay(exe: str, lib: str, run_dir: str, side: str, probes: str | None = None,
           only: str | None = None, wide: list[str] | None = None,
           env_extra: dict | None = None) -> tuple[int, str, list[dict]]:
    """env_extra: more environment for replay.exe (h56.py h5's lanes: GCOV_PREFIX, so each lane's gcov counters go
    to its own folder)."""
    out = os.path.join(run_dir, f"replay_{side}.jsonl")
    cmd = [exe, "run", "--lib", lib, "--dir", os.path.abspath(run_dir), "--side", side, "--out",
           os.path.abspath(out)]
    if probes:
        cmd += ["--probes", probes]
    if only:
        cmd += ["--only", only]
    wide = wide_results() if wide is None else wide
    if wide:
        cmd += ["--wide", ",".join(wide)]
    rc, text = run(cmd, dict(replay_env(run_dir), **(env_extra or {})), timeout=3600)
    rows = []
    if os.path.isfile(out):
        with open(out, encoding="utf-8") as fh:
            rows = [json.loads(ln) for ln in fh if ln.strip()]
    return rc, text, rows


def wide_results() -> list[str]:
    """Overrides whose result is 64-bit (r0 and r1 compared, HARNESS.md 5 rule 3): the `returns`
    column of config/readable/functions.csv once it exists (H7); none until then."""
    try:
        return [r["address"] for r in rcheck.registry() if r.get("returns", "").strip() == "r0r1"]
    except (OSError, KeyError):
        return []


# ------------------------------------------------------------------ verdicts
def guard_users() -> set[int]:
    """Known users of the one-time guard routine (targets.csv reason column, H3); empty until then."""
    if not os.path.isfile(TARGETS):
        return set()
    sys.path.insert(0, HERE)
    import gen_stubs  # noqa: E402  (same folder; GUARD_TAG names this game's guard address)
    with open(TARGETS, newline="", encoding="utf-8") as fh:
        return {int(r["address"], 16) for r in csv.DictReader(fh)
                if gen_stubs.GUARD_TAG in r.get("reason", "")}


def sig_parts(sig: int) -> tuple[int, int, int]:
    """(r0 bucket, written-bytes bucket, read-bytes bucket) of a path signature (capture.c)."""
    return sig & 0xF, (sig >> 4) & 0x3F, (sig >> 10) & 0x3F


def fn_verdict(v: dict, signatures: int, deep: int, cold: int, warm: int, guard_user: bool = False,
               kind: str = "override") -> str:
    """HARNESS.md 5 'Per function'; mirrors capture.c fe_cap_fn_verdict, plus harness.py's half of
    the cold/warm rule: a known guard user needs a cold record too (4.5)."""
    if any(v.get(k, 0) for k in MISMATCH):
        return "MISMATCH"
    if v.get("match", 0):
        if signatures < 2:
            return "SHALLOW"
        if (v["match"] >= 8 and deep >= 1 and (cold == 0 or warm >= 1) and (not guard_user or cold >= 1)):
            return "REPLAY-CLEAN"
        return "PARTIAL"
    if v.get("unfaithful", 0):
        return "UNFAITHFUL"
    if v.get("faithful", 0):
        return "A-CLEAN"
    return "NO-DATA"


def classify(rows: list[dict], guards: set[int] | None = None) -> dict[str, dict]:
    """Per function from offline replay rows (one per record)."""
    guards = guards or set()
    fns: dict[str, dict] = {}
    for r in rows:
        f = fns.setdefault(r["address"], {"kind": r["kind"], "records": 0, "verdicts": {}, "sigs": {},
                                         "cold": 0, "warm": 0, "deep": 0, "first_rb": None, "inlined": 0,
                                         "details": []})
        f["records"] += 1
        v = r["verdict"]
        f["verdicts"][v] = f["verdicts"].get(v, 0) + 1
        f["inlined"] += r.get("inlined", 0)
        if v in BAD and len(f["details"]) < 3:
            f["details"].append(f"call {r['call']}: {v}: {r['detail']}")
        if v in ("match", "faithful"):
            sig = int(r["signature"], 16)
            f["sigs"][sig] = f["sigs"].get(sig, 0) + 1
            r0b, wb, rb = sig_parts(sig)
            deep = wb > 0 or r0b >= 3
            if f["first_rb"] is None:
                f["first_rb"] = rb
            elif rb > f["first_rb"]:
                deep = True
            f["deep"] += int(deep)
            f["cold" if r.get("cold") else "warm"] += 1
    for a, f in fns.items():
        f["verdict"] = fn_verdict(f["verdicts"], len(f["sigs"]), f["deep"], f["cold"], f["warm"],
                                  int(a, 16) in guards, f["kind"])
    return fns


def read_summary(path: str) -> dict[str, dict]:
    out = {}
    with open(path, encoding="utf-8") as fh:
        lines = [ln.rstrip("\n") for ln in fh if not ln.startswith("#")]
    if not lines:
        return out
    head = lines[0].split("\t")
    for ln in lines[1:]:
        if not ln:
            continue
        cells = dict(zip(head, ln.split("\t")))
        sigs = {}
        for part in filter(None, cells.get("signatures", "").split(";")):
            s, _, n = part.partition(":")
            sigs[int(s, 16)] = int(n)
        out[cells["address"]] = {
            "kind": cells["kind"], "verdict": cells["verdict"], "calls": int(cells["calls"]),
            "records": int(cells["records"]), "verdicts": {v: int(cells.get(v, 0)) for v in VNAMES[1:]},
            "cold": int(cells["cold"]), "warm": int(cells["warm"]), "deep": int(cells["deep"]),
            "kept": int(cells["kept"]), "sigs": sigs}
    return out


LIVE_BAD = BAD + ("escaped",)  # the record kinds that fail a capture run (same set as parallel.py CAPTURE_BAD)


def live_bad_records(run_dir: str) -> tuple[dict, dict]:
    """Every summary.tsv below a capture run's folder, merged: (functions, {address: bad record count}) for the
    LIVE_BAD kinds. h4a fails on any (round 6); mismatch_regs and damaged are offline verdicts (report/replay) that
    capture.c never writes, kept in the set so a summary that ever carries them still fails."""
    found = sorted(glob.glob(os.path.join(run_dir, "**", "summary.tsv"), recursive=True))
    rows = merge_summaries(found) if found else {}
    bad = {k: sum(v["verdicts"].get(b, 0) for b in LIVE_BAD) for k, v in rows.items()}
    return rows, {k: n for k, n in bad.items() if n}


def merge_summaries(paths: list[str], guards: set[int] | None = None) -> dict[str, dict]:
    """Counts add, signatures unite (hits add); the verdict is computed again on the sum."""
    guards = guards or set()
    merged: dict[str, dict] = {}
    for p in paths:
        for a, f in read_summary(p).items():
            m = merged.setdefault(a, {"kind": f["kind"], "calls": 0, "records": 0, "verdicts": {},
                                      "cold": 0, "warm": 0, "deep": 0, "kept": 0, "sigs": {}, "runs": 0})
            m["runs"] += 1
            for k in ("calls", "records", "cold", "warm", "deep", "kept"):
                m[k] += f[k]
            for v, n in f["verdicts"].items():
                m["verdicts"][v] = m["verdicts"].get(v, 0) + n
            for s, n in f["sigs"].items():
                m["sigs"][s] = m["sigs"].get(s, 0) + n
    for a, m in merged.items():
        m["verdict"] = fn_verdict(m["verdicts"], len(m["sigs"]), m["deep"], m["cold"], m["warm"],
                                  int(a, 16) in guards, m["kind"])
    return merged


SYNTH_TAG = "SYNTH-"  # verdicts from made-up states carry it, so a label copied alone is not taken as status evidence


def synth_label(verdict: str, synthetic: bool) -> str:
    return SYNTH_TAG + verdict if synthetic and not verdict.startswith(SYNTH_TAG) else verdict


def verdict_table(fns: dict[str, dict], synthetic: bool = False) -> str:
    counts: dict[str, int] = {}
    for f in fns.values():
        v = synth_label(f["verdict"], synthetic)
        counts[v] = counts.get(v, 0) + 1
    return ", ".join(f"{k} {counts[k]}" for k in sorted(counts))


# ------------------------------------------------------------------ PNG screenshots (H4a)
def read_ppm(path: str) -> tuple[int, int, bytes]:
    data = open(path, "rb").read()
    tokens, i = [], 0
    while len(tokens) < 4:
        while data[i:i + 1].isspace():
            i += 1
        if data[i:i + 1] == b"#":
            while data[i:i + 1] not in (b"\n", b""):
                i += 1
            continue
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        tokens.append(data[i:j])
        i = j
    if tokens[0] != b"P6" or int(tokens[3]) != 255:
        raise ValueError(f"{path}: not a binary 8-bit PPM (P6)")
    w, h = int(tokens[1]), int(tokens[2])
    pixels = data[i + 1:i + 1 + w * h * 3]
    if len(pixels) != w * h * 3:
        raise ValueError(f"{path}: cut short")
    return w, h, pixels


def png_bytes(w: int, h: int, rgb: bytes) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ppm_to_png(src: str, dst_dir: str, remove: bool = True) -> str:
    w, h, rgb = read_ppm(src)
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.splitext(os.path.basename(src))[0] + ".png")
    with open(dst, "wb") as fh:
        fh.write(png_bytes(w, h, rgb))
    if remove:
        os.remove(src)
    return dst


# ------------------------------------------------------------------ gcov
def gcov_report(obj_dir: str, sources: list[str]) -> tuple[list[str], int, int]:
    gcov = shutil.which("gcov") or os.path.join(os.path.dirname(rcheck.find_cc() or ""), "gcov" + EXE)
    lines, taken_total, branches_total = [], 0, 0
    if not os.path.isfile(gcov):
        return ["coverage: gcov not found"], 0, 0
    for o in sorted(f for f in os.listdir(obj_dir) if f.endswith(".gcda")):
        rc, out = run([gcov, "-b", "-n", "-o", obj_dir, os.path.join(obj_dir, o)], cwd=obj_dir)
        src = None
        for ln in out.splitlines():
            m = re.match(r"File '(.+)'", ln)
            if m:
                src = m.group(1)
            m = re.match(r"Taken at least once:\s*([\d.]+)% of (\d+)", ln)
            if m and src and os.path.normcase(os.path.abspath(src)) in {os.path.normcase(s) for s in sources}:
                n = int(m.group(2))
                taken = round(float(m.group(1)) * n / 100)
                taken_total += taken
                branches_total += n
                lines.append(f"  {rel(src)}: branches taken {taken}/{n}")
                src = None
    return lines, taken_total, branches_total


# ------------------------------------------------------------------ self-test (fakelib)
FAKE_PROBES = "200600,200A00,201100"
# fakelib rows whose planted bug is a register FE_ENTRY always restores: live run B (r0 only) matches,
# replay.exe (rule 3) must not
FAKE_REG_BUGS = {"0x00200D00": "r7:", "0x00200E00": "s20:", "0x00200F00": "fpscr control:"}
FAKE_GUARD = "200A00"


def records_of(data: bytes):
    """(offset, header words after the magic) of every record in a records.fecap image."""
    off = 0
    while off + HEADER_BYTES <= len(data):
        words = HEADER.unpack_from(data, off)[1:]
        yield off, words
        off += words[2]


def corrupt(records: str, what: str, address: int | None = None) -> int | None:
    """Damages one valid record of a records.fecap (self-test): 'exit' flips exit r0, 'lookup' the
    first lookup's address, 'note' the first probe note's r0, 'move' moves a page the record only
    wrote (never read) elsewhere; 'forge' makes an escaped record of `address` look valid with exit
    registers = entry registers, so that only run A's way out (it stops at the svc) tells. Returns
    the record's address, or None when none fits."""
    data = bytearray(open(records, "rb").read())
    for off, w in records_of(bytes(data)):
        addr, flags, pages, events, lookups, notes = w[3], w[8], w[12], w[13], w[14], w[15]
        if what == "forge" and addr == address:  # an escaped record made to look valid, exit = entry
            struct.pack_into("<I", data, off + 8 + 8 * 4, 1)  # flags = VALID only
            data[off + HEADER.size + REGS_BYTES:off + HEADER.size + 2 * REGS_BYTES] =                 data[off + HEADER.size:off + HEADER.size + REGS_BYTES]
            open(records, "wb").write(bytes(data))
            return addr
        if not flags & 1 or (address is not None and addr != address):
            continue
        tail = off + HEADER_BYTES + pages * PAGE_BYTES + events * EVENT_BYTES
        if what == "exit":
            p = off + HEADER.size + REGS_BYTES  # exit.r[0]
        elif what == "lookup" and lookups:
            p = tail
        elif what == "note" and notes:
            p = tail + lookups * 8 + 8  # FeCapNote: callee, kind, r[0]
        elif what == "move":
            p = None
            for i in range(pages):
                pg = off + HEADER_BYTES + i * PAGE_BYTES
                read_bits, write_bits = data[pg + 24:pg + 24 + 512], data[pg + 24 + 512:pg + PAGE_BYTES]
                if not any(read_bits) and any(write_bits):
                    struct.pack_into("<I", data, pg, 0x0FE00000)
                    p = -1
                    break
            if p is None:
                continue
        else:
            continue
        if p >= 0:
            struct.pack_into("<I", data, p, struct.unpack_from("<I", data, p)[0] ^ 0x40)
        open(records, "wb").write(bytes(data))
        return addr
    return None


def corrupt_event(records: str) -> int | None:
    """Flips new_value of the first logged write of the first valid record that has one; returns
    its address (None when no such record)."""
    data = bytearray(open(records, "rb").read())
    off = 0
    while off + HEADER_BYTES <= len(data):
        f = HEADER.unpack_from(data, off)
        words = f[1:]
        record_bytes, address, flags = words[2], words[3], words[8]
        pages, events = words[12], words[13]
        if flags & 1 and events:
            ev = off + HEADER_BYTES + pages * PAGE_BYTES
            for e in range(events):
                kind = struct.unpack_from("<I", data, ev + e * EVENT_BYTES)[0]
                if kind & 0xFF == 1 and not kind & 0x10000:
                    p = ev + e * EVENT_BYTES + 12
                    struct.pack_into("<I", data, p, struct.unpack_from("<I", data, p)[0] ^ 0x5A)
                    open(records, "wb").write(bytes(data))
                    return address
        off += record_bytes
    return None


def selftest() -> int:
    passed, total = 0, 0

    def check(cond: bool, what: str) -> None:
        nonlocal passed, total
        total += 1
        if cond:
            passed += 1
        else:
            print(f"  FAIL  {what}")

    cc = rcheck.find_cc()
    if cc is None:
        print("harness selftest: SKIPPED (no host C compiler)")
        return 0
    d = SELFTEST_DIR
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)

    # 1. ABI gate: the same header passes, a changed one is refused
    a, err = abi_lines(cc, ["-DFE_ABI_STUB"], ["-I", STUB, "-I", HERE], os.path.join(d, "abi"), "stub")
    check(a is not None and len(a) > 30, f"abi_check builds and prints facts {err}")
    bad_stub = os.path.join(d, "abi_bad")
    os.makedirs(bad_stub)
    text = open(os.path.join(STUB, "overrides.h"), encoding="utf-8").read()
    for name, old, new in (("swap", "    uint32_t svc;\n    uint32_t depth;", "    uint32_t depth;\n    uint32_t svc;"),
                           ("add", "    void *user;\n};", "    void *user;\n    uint32_t extra;\n};")):
        if old not in text:
            check(False, f"abi mutation '{name}' no longer applies to the stub")
            continue
        sub = os.path.join(bad_stub, name)
        os.makedirs(sub)
        with open(os.path.join(sub, "overrides.h"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace(old, new))
        b, err = abi_lines(cc, ["-DFE_ABI_STUB"], ["-I", sub, "-I", HERE], os.path.join(d, "abi"), "bad_" + name)
        check(a is not None and b is not None and abi_compare(a, b) != [], f"abi gate refuses a changed layout ({name})")
    check(a is not None and abi_compare(a, list(a)) == [], "abi gate accepts the same layout")

    # 2. build fakelib.dll and the self-test replay.exe (fake readable side)
    lib = os.path.join(d, "fakelib" + (".dll" if os.name == "nt" else ".so"))
    rc, out = run([cc] + CFLAGS + ["-shared"] + INCS + [os.path.join(HERE, "fakelib", "fakelib.c"), "-o", lib])
    check(rc == 0, f"build fakelib: {out}")
    exe, err = build_replay(cc, os.path.join(d, "bin"), [os.path.join(HERE, "fakelib", "fake_readable.c")])
    check(exe is not None, f"build replay.exe (fakelib): {err}")
    if rc or exe is None:
        print(f"harness selftest: {passed}/{total} checks passed")
        return 1

    # 3. synth: records through the real capture runtime, live runs A and B
    run1 = os.path.join(d, "runs", "seed1")
    rc, out = synth(exe, lib, run1, calls=20, seed=1, probes=FAKE_PROBES, guard=FAKE_GUARD)
    check(rc == 0 and out.startswith("synth:"), f"synth runs: {out[-300:]}")
    summ = read_summary(os.path.join(run1, "summary.tsv")) if os.path.isfile(os.path.join(run1, "summary.tsv")) else {}
    want = {"0x00200000": "REPLAY-CLEAN", "0x00200300": "MISMATCH", "0x00200700": "MISMATCH",
            "0x00200900": "MISMATCH", "0x00200400": "NO-DATA", "0x00201000": "MISMATCH", "0x00201200": "MISMATCH",
            "0x00201300": "MISMATCH"}
    for a_, v in want.items():
        check(summ.get(a_, {}).get("verdict") == v, f"live verdict of {a_} is {v} (got {summ.get(a_, {}).get('verdict')})")
    # h4a's live gate (round 6): the MISMATCH functions of this run are bad, the clean one is not; a summary in a
    # stage folder (a staged run) counts too
    _rows, bad = live_bad_records(run1)
    check(all(bad.get(a_, 0) > 0 for a_, v in want.items() if v == "MISMATCH") and "0x00200000" not in bad,
          f"h4a's live gate finds every MISMATCH function and not the clean one ({sorted(bad)})")
    staged = os.path.join(d, "runs", "staged")
    os.makedirs(os.path.join(staged, "stage0"))
    shutil.copy2(os.path.join(run1, "summary.tsv"), os.path.join(staged, "stage0", "summary.tsv"))
    check(live_bad_records(staged)[1] == bad, "h4a's live gate reads a summary.tsv in a stage folder")
    check(live_bad_records(os.path.join(d, "runs", "nothing"))[1] == {}, "no summary.tsv: no bad record")
    s = summ.get("0x00200800", {}).get("verdicts", {})
    check(s.get("b_escaped", 0) > 0 and s.get("match", 0) == 0, "planted extra read (peek) is b_escaped live")
    s = summ.get("0x00200100", {}).get("verdicts", {})
    check(s.get("gave_up", 0) >= 1 and s.get("match", 0) >= 1, "cached: gave up while cold, matched when warm")
    s = summ.get("0x00200400", {}).get("verdicts", {})
    check(s.get("escaped", 0) == summ.get("0x00200400", {}).get("records", -1), "an svc inside makes every record escaped")
    check(all(fn_verdict(f["verdicts"], len(f["sigs"]), f["deep"], f["cold"], f["warm"]) == f["verdict"]
              for f in summ.values()) and len(summ) >= 8, "harness.py's verdict rule = capture.c's on every row")

    # 3b. states are regenerated, not stored: the same seed gives the same records and summary
    again = os.path.join(d, "runs", "seed1_again")
    rc, out = synth(exe, lib, again, calls=20, seed=1, probes=FAKE_PROBES, guard=FAKE_GUARD)
    same = rc == 0 and all(open(os.path.join(run1, f), "rb").read() == open(os.path.join(again, f), "rb").read()
                           for f in ("records.fecap", "summary.tsv"))
    check(same, "synth is deterministic: the same seed gives byte-identical records and summary")
    drop_records(again)
    check(not os.path.exists(os.path.join(again, "records.fecap")) and not os.path.exists(os.path.join(again, "pages"))
          and os.path.isfile(os.path.join(again, "summary.tsv")), "dropping a run's records keeps its summary")

    # 3c. plain `report` leaves out capture replays of synthetic sessions (they repeat a route run)
    rr_dir = os.path.join(d, "report_runs")
    for name, meta in (("route-ab", {"source": "headless", "route": "bt-ch2"}),
                       ("syn-cap", {"source": "replay", "session_kind": "synthetic"}),
                       ("own-cap", {"source": "replay", "session_kind": "owner"}), ("bare", None),
                       ("broken", "{not json"), ("list", "[1, 2]"),
                       ("cheat-flag", {"source": "headless", "route": "bt-ch8", "cheat": True}),
                       ("cheat-name", {"source": "headless", "route": "cheat-family"}),
                       ("cheat-start", {"source": "headless", "route": "bt-ch9", "start_save_cheat": "cheat-x"})):
        os.makedirs(os.path.join(rr_dir, name))
        if meta is not None:
            with open(os.path.join(rr_dir, name, "run.json"), "w", encoding="utf-8") as fh:
                fh.write(meta if isinstance(meta, str) else json.dumps(meta))
    why: dict = {}
    got = default_report_runs(rr_dir, why)
    check(got == (["own-cap", "route-ab"], ["bare", "broken", "cheat-flag", "cheat-name", "cheat-start", "list",
                                           "syn-cap"]),
          f"report keeps owner replays and real-play route runs only; skips synthetic replays, cheat runs (flag, "
          f"cheat start save, a cheat-* route without the flag) and runs without a readable run.json (got {got})")
    check(why.get("bare", "").startswith("suspect") and why.get("broken", "").startswith("suspect")
          and why.get("cheat-name", "").startswith("cheat"), f"skip reasons ({why})")

    # 4. original vs original: 0 mismatches, every valid record faithful
    rc, out, rows = replay(exe, lib, run1, "original", FAKE_PROBES)
    valid = [r for r in rows if r["verdict"] not in ("hostmem", "escaped", "incomplete", "truncated")]
    check(rc == 0 and rows and all(r["verdict"] == "match" for r in valid) and len(valid) >= 50,
          f"original vs original: {len(valid)} valid record(s), all match ({out[-200:]})")
    check(not any(r["verdict"] in BAD for r in rows), "original vs original: no mismatch, unfaithful or escape")

    # 5. readable side offline = the live verdicts; planted bugs caught; inline calls counted
    rc, out, rows = replay(exe, lib, run1, "readable", FAKE_PROBES)
    disagree = [r for r in rows if r["live"] != r["verdict"] and r["address"] not in FAKE_REG_BUGS]
    check(rc == 0 and rows and not disagree,
          f"offline verdict = live verdict on every record ({len(disagree)} differ: {disagree[:2]})")
    fns = classify(rows)
    for a_, v in want.items():
        check(fns.get(a_, {}).get("verdict") == v, f"offline verdict of {a_} is {v} (got {fns.get(a_, {}).get('verdict')})")

    # 5a. rule 3 beyond r0: callee-saved r4-r11, s16-s31 and the FPSCR control bits are compared offline
    # (live run B compares r0 only, so live these match); AAPCS scratch is not compared
    for a_, prefix in FAKE_REG_BUGS.items():
        rr = [r for r in rows if r["address"] == a_ and r["verdict"] != "hostmem"]
        check(rr and all(r["verdict"] == "mismatch_regs" and r["detail"].startswith(prefix) and r["live"] == "match"
                         for r in rr),
              f"rule 3: {a_} ({prefix.rstrip(':')}) is mismatch_regs offline, match live "
              f"({[(r['verdict'], r['live'], r['detail']) for r in rr][:2]})")
    rr = [r for r in rows if r["address"] == "0x00201500" and r["verdict"] != "hostmem"]
    check(rr and all(r["verdict"] == "match" for r in rr),
          f"rule 3: changed scratch registers (r2, r3, r12, s0-s15, FPSCR flags) still match "
          f"({[(r['verdict'], r['detail']) for r in rr if r['verdict'] != 'match'][:2]})")
    # rule 4: B may make no extra call, also after A's last call and to a callee A also called
    for a_, what in (("0x00201000", "a repeated callee"), ("0x00201200", "an extra call at the end")):
        rr = [r for r in rows if r["address"] == a_ and r["verdict"] not in ("hostmem",)]
        check(rr and all(r["verdict"] == "mismatch_calls" and r["detail"].startswith("probe calls: 1 vs 2")
                         for r in rr), f"rule 4: {what} is mismatch_calls ({[(r['verdict'], r['detail']) for r in rr][:2]})")
    # rule 1: the caller's frame at entry sp is compared (only below sp is dead stack)
    rr = [r for r in rows if r["address"] == "0x00201300" and r["verdict"] not in ("hostmem",)]
    check(rr and all(r["verdict"] == "mismatch_mem" and r["first_diffs"] and
                     all(int(x, 16) >= 0x0FFF8000 for x in r["first_diffs"]) for r in rr),
          f"rule 1: an out-parameter at entry sp is a memory mismatch ({[(r['verdict'], r['detail']) for r in rr][:2]})")
    # rule 2: a same-value store run A never made is counted, still a match
    rr = [r for r in rows if r["address"] == "0x00201400" and r["verdict"] not in ("hostmem",)]
    check(rr and all(r["verdict"] == "match" and r["same_value"] >= 1 for r in rr) and
          any(r["same_value"] == 4 for r in rr) and
          all(r["same_value"] == 0 for r in rows if r["address"] == "0x00200000" and r["verdict"] == "match"),
          f"rule 2: same-value writes counted ({[(r['verdict'], r['same_value']) for r in rr][:3]})")
    caller = [r for r in rows if r["address"] == "0x00200500" and r["verdict"] == "match"]
    check(caller and all(r["inlined"] == 1 for r in caller), "caller: double() done inline is counted, still match")
    calls2 = [r for r in rows if r["address"] == "0x00200700" and r["verdict"] == "mismatch_calls"]
    check(calls2 and "r0=" in calls2[0]["detail"], "caller2: wrong probe argument named in the detail")
    mem = [r for r in rows if r["verdict"] == "mismatch_mem"]
    check(mem and all(r["address"] in ("0x00200900", "0x00200C00", "0x00201300") and r["mem_diffs"] >= 1 and r["first_diffs"]
                      for r in mem),
          "store2: every differing byte counted and listed")
    peek = [r for r in rows if r["address"] == "0x00200800" and r["verdict"] == "b_escaped"]
    check(peek and all(r["extra_reads"] >= 4 for r in peek), "peek: extra reads of run B reported")
    ver = [r for r in rows if r["address"] == "0x00200B00"]
    check(ver and all(r["verdict"] == "b_escaped" and "device 00100010" in r["detail"] for r in ver),
          "version: a write to a page the game cannot write is b_escaped (DEVICE)")
    mark = [r for r in rows if r["address"] == "0x00200C00" and r["verdict"] not in ("hostmem",)]
    check(mark and all(r["verdict"] == "mismatch_mem" and r["first_diffs"] for r in mark),
          "mark: a byte only run B wrote is a memory mismatch")
    heal = [r for r in rows if r["address"] == "0x00200000" and r["verdict"] == "match"]
    check(heal and all(r["a_writes"] >= 2 for r in heal), "heal: writes compared (dead-stack scratch excluded)")

    # 5b. a 64-bit result (returns = r0r1) also compares r1: heal's original leaves junk there, which
    # readable mode does not reproduce (it restores r1-r3)
    rc, out, rows = replay(exe, lib, run1, "readable", FAKE_PROBES, only="200000", wide=["0x00200000"])
    hw = [r for r in rows if r["verdict"] not in ("hostmem",)]
    check(hw and all(r["verdict"] == "mismatch_regs" and r["detail"].startswith("r1:") for r in hw),
          "a 64-bit result compares r1 (rule 3)")

    # 6. a damaged record is never a pass: a flipped logged write -> unfaithful, a flipped page -> damaged
    bad = os.path.join(d, "runs", "damaged")
    shutil.copytree(run1, bad)
    hit = corrupt_event(os.path.join(bad, "records.fecap"))
    check(hit is not None, "found a valid record with a logged write to damage")
    pages = sorted(os.listdir(os.path.join(bad, "pages")))
    with open(os.path.join(bad, "pages", pages[0]), "r+b") as fh:
        b0 = fh.read(1)
        fh.seek(0)
        fh.write(bytes([b0[0] ^ 0xFF]))
    rc, out, rows = replay(exe, lib, bad, "original", FAKE_PROBES)
    check(any(r["verdict"] == "unfaithful" and r["address"] == f"0x{hit:08X}" for r in rows),
          "a changed write log makes run A unfaithful")
    check(any(r["verdict"] == "damaged" and "hash" in r["detail"] for r in rows), "a changed page file is found (hash)")

    for what, addr in (("exit", None), ("lookup", 0x00200500), ("note", 0x00200500), ("move", 0x00200000),
                       ("forge", 0x00200400)):
        dmg = os.path.join(d, "runs", "damaged_" + what)
        shutil.copytree(run1, dmg)
        hit = corrupt(os.path.join(dmg, "records.fecap"), what, addr)
        rc, out, rows = replay(exe, lib, dmg, "original", FAKE_PROBES)
        bad_rows = [r for r in rows if r["verdict"] == "unfaithful"]
        check(hit is not None and len(bad_rows) == 1 and bad_rows[0]["address"] == f"0x{hit:08X}",
              f"a damaged record ({what}) is unfaithful, the rest still match: "
              f"{[(r['address'], r['detail']) for r in bad_rows][:2]}")
        if what == "move":
            check(bad_rows and "outside the record" in bad_rows[0]["detail"], "run A writing outside the record is named")
        if what == "forge":
            check(bad_rows and "run A stopped" in bad_rows[0]["detail"], "run A stopping inside is unfaithful")

    # 6b. a library with another recomp_abi is refused
    lib4 = os.path.join(d, "fakelib_abi4" + (".dll" if os.name == "nt" else ".so"))
    rc, out = run([cc] + CFLAGS + ["-shared", "-DFL_ABI=4"] + INCS + [os.path.join(HERE, "fakelib", "fakelib.c"),
                                                                      "-o", lib4])
    rc, out = run([exe, "run", "--lib", lib4, "--dir", run1], replay_env(d))
    check(rc == 3 and "recomp_abi 4" in out, f"replay refuses recomp_abi 4: {out}")

    # 7. run A only (FE_CAPTURE_LIVE=a): faithful, never matched
    runa = os.path.join(d, "runs", "live_a")
    rc, out = synth(exe, lib, runa, calls=4, seed=3, probes=FAKE_PROBES, guard=FAKE_GUARD, live="a")
    sa = read_summary(os.path.join(runa, "summary.tsv")) if rc == 0 else {}
    check(sa and all(f["verdicts"]["match"] == 0 for f in sa.values()) and
          any(f["verdict"] == "A-CLEAN" for f in sa.values()), "live=a gives run A only (A-CLEAN)")

    # 8. report: two runs merge (counts add, signatures unite)
    run2 = os.path.join(d, "runs", "seed2")
    rc, out = synth(exe, lib, run2, calls=20, seed=2, probes=FAKE_PROBES, guard=FAKE_GUARD)
    s2 = read_summary(os.path.join(run2, "summary.tsv")) if rc == 0 else {}
    merged = merge_summaries([os.path.join(run1, "summary.tsv"), os.path.join(run2, "summary.tsv")])
    h = "0x00200000"
    check(h in merged and merged[h]["records"] == summ[h]["records"] + s2[h]["records"] and
          len(merged[h]["sigs"]) >= max(len(summ[h]["sigs"]), len(s2[h]["sigs"])) and
          merged[h]["verdict"] == "REPLAY-CLEAN" and merged["0x00200300"]["verdict"] == "MISMATCH",
          "report merges two runs")
    check(verdict_table(merged, True).startswith(SYNTH_TAG) and SYNTH_TAG not in verdict_table(merged) and
          synth_label(synth_label("REPLAY-CLEAN", True), True) == SYNTH_TAG + "REPLAY-CLEAN",
          "labels from made-up states are tagged SYNTH- (once)")
    check(fn_verdict({"match": 9}, 3, 1, 0, 9, guard_user=True) == "PARTIAL" and
          fn_verdict({"match": 9}, 3, 1, 1, 8, guard_user=True) == "REPLAY-CLEAN" and
          fn_verdict({"match": 9}, 3, 1, 2, 0) == "PARTIAL", "guard users need a cold record, cold needs warm")

    # 9. folders outside build/ are refused, nothing written
    outside = os.path.join(ROOT, "docs", "harness_selftest_refused")
    rc, out = run([exe, "run", "--lib", lib, "--dir", outside], replay_env(d))
    check(rc == 2 and not os.path.exists(outside), "replay refuses a folder outside build/")
    fake_build = os.path.join(ROOT, "docs", "build", "harness_selftest_refused")
    rc, out = run([exe, "run", "--lib", lib, "--dir", fake_build], replay_env(d))
    check(rc == 2 and not os.path.exists(os.path.join(ROOT, "docs", "build")),
          "replay refuses a 'build' folder that is not this repository's build/")
    rc, out = run([exe, "run", "--lib", lib, "--dir", os.path.join(d, "runs", "seed1", "..", "..")], replay_env(d))
    check(rc == 2, "replay refuses '..'")
    rc, out = run([exe, "run", "--lib", os.path.join(d, "no_such.dll"), "--dir", run1], replay_env(d))
    check(rc == 3, "replay refuses a library it cannot load")

    # 10. coverage build: gcov sees the readable side's branches
    cexe, err = build_replay(cc, os.path.join(d, "cov"), [os.path.join(HERE, "fakelib", "fake_readable.c")],
                             coverage=True)
    if cexe:
        rc, out, rows = replay(cexe, lib, run1, "readable", FAKE_PROBES)
        lines, taken, branches = gcov_report(os.path.join(d, "cov", "obj"),
                                             [os.path.join(HERE, "fakelib", "fake_readable.c")])
        check(rc == 0 and branches > 0 and 0 < taken <= branches, f"gcov branch coverage: {lines}")
    else:
        check(False, f"coverage build: {err}")

    # 11. screenshots: PPM -> PNG round trip (invented 3x2 image)
    ppm = os.path.join(d, "shot.ppm")
    rgb = bytes(range(18))
    with open(ppm, "wb") as fh:
        fh.write(b"P6\n# invented\n3 2\n255\n" + rgb)
    png = ppm_to_png(ppm, os.path.join(d, "shots"))
    data = open(png, "rb").read()
    idat = data.index(b"IDAT")
    ln = struct.unpack(">I", data[idat - 4:idat])[0]
    raw = zlib.decompress(data[idat + 4:idat + 4 + ln])
    check(data.startswith(b"\x89PNG\r\n\x1a\n") and not os.path.exists(ppm) and
          raw == b"\x00" + rgb[:9] + b"\x00" + rgb[9:], "PPM screenshot becomes a PNG, the PPM is removed")

    # 12. H3: targets.csv agrees with the registry; gen_stubs.py and build.py self-tests
    import gen_stubs  # noqa: E402  (same folder)
    import build as hbuild  # noqa: E402
    rc_t, _rows = gen_stubs.check_targets(gen_stubs.guard_callers(), say=lambda *_a, **_k: None)
    check(rc_t == 0, "config/harness/targets.csv agrees with the registry (gen_stubs.py --check)")
    import headless  # noqa: E402  (same folder)
    import mutate  # noqa: E402  (same folder)
    for sub in (gen_stubs.selftest, hbuild.selftest, headless.selftest, mutate.selftest):
        sub_errs, line = sub()
        for e in sub_errs:
            print(f"  FAIL  {e}")
        check(not sub_errs, line)

    # 13. a replay.exe older than its inputs is refused (H5 route 3: a stale one ran old readable code)
    st_dir = os.path.join(SELFTEST_DIR, "stale")
    os.makedirs(st_dir, exist_ok=True)
    fake_exe, fake_src = os.path.join(st_dir, "replay" + EXE), os.path.join(st_dir, "input.c")
    for p in (fake_exe, fake_src):
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("x\n")
    os.utime(fake_exe, (1_000_000, 1_000_000))
    os.utime(fake_src, (2_000_000, 2_000_000))
    newer = replay_stale(fake_exe, [fake_src])
    os.utime(fake_src, (500_000, 500_000))
    check(newer == [fake_src] and replay_stale(fake_exe, [fake_src]) == [] and
          replay_stale(os.path.join(st_dir, "none" + EXE), []) != [] and
          all(os.path.isfile(p) for p in replay_inputs()) and os.path.join(HERE, "replay.c") in replay_inputs(),
          "replay.exe older than a readable source is stale; a newer one is fresh; inputs include replay.c")
    shutil.rmtree(st_dir, ignore_errors=True)

    print(f"harness selftest: {passed}/{total} checks passed")
    return 0 if passed == total else 1


# ------------------------------------------------------------------ commands
def drop_records(run_dir: str) -> None:
    """Removes a run's records.fecap and pages/ (keeps summary.tsv, the replay results and logs)."""
    for p in (os.path.join(run_dir, "records.fecap"), os.path.join(run_dir, "pages")):
        if os.path.isdir(p):
            shutil.rmtree(p)
        elif os.path.isfile(p):
            os.remove(p)


def cmd_report(run_names: list[str]) -> int:
    paths = [os.path.join(RUNS, n, "summary.tsv") for n in run_names]
    paths = [p for p in paths if os.path.isfile(p)]
    if not paths:
        print("report: no summary.tsv found")
        return 3
    merged = merge_summaries(paths, guard_users())
    synthetic = [p for p in paths if run_source(os.path.dirname(p)) == "synth"]
    # one made-up run in the mix taints every merged label (counts add across runs): tag them all
    tag = bool(synthetic)
    os.makedirs(BUILD, exist_ok=True)
    out = {a: {k: (synth_label(v, tag) if k == "verdict" else v if k != "sigs" else
                   {f"{s:08X}": n for s, n in v.items()}) for k, v in f.items()}
           for a, f in sorted(merged.items())}
    with open(os.path.join(BUILD, "report.json"), "w", encoding="utf-8") as fh:
        json.dump({"runs": [{"summary": rel(p), "source": run_source(os.path.dirname(p))} for p in paths],
                   "status_evidence": not tag, "functions": out}, fh, indent=1)
    for a, f in sorted(merged.items()):
        if f["verdict"] in ("MISMATCH", "UNFAITHFUL"):
            print(f"  {a} {f['kind']} {synth_label(f['verdict'], tag)}: {f['verdicts']}")
    if synthetic:
        print(f"report: {len(synthetic)} of {len(paths)} run(s) use made-up states (synth): their verdicts test the "
              f"harness and the code paths, they are never evidence for a function's status (labels tagged "
              f"{SYNTH_TAG})")
    print(f"report: {len(merged)} function(s) from {len(paths)} run(s): {verdict_table(merged, tag)}")
    return 0


def callbacks_totals(run_dir: str) -> str:
    try:
        with open(os.path.join(run_dir, "callbacks.tsv"), encoding="utf-8") as fh:
            first = fh.readline().strip()
    except OSError:
        return "no callbacks.tsv"
    return first.split("totals:", 1)[-1].strip()


def cmd_h4a(route: str, save: str | None, prefix: str) -> int:
    """Milestone H4a (docs/HARNESS.md 4.1, 8): Grok's order, determinism first, fidelity only, then A+B."""
    sys.path.insert(0, HERE)
    import build as hbuild  # noqa: E402
    import headless  # noqa: E402
    try:
        if headless.load_routes().get(route, {}).get("cheat"):  # docs/CHEATS.md: staged runs, scored apart
            print(f"h4a: {route} is a cheat route (boot.exe in stages, one summary.tsv per stage): score it with "
                  f"parallel.py runs --mode capture, which reads every stage and keeps cheat runs in their own table")
            return 2
    except headless.Stop as e:
        print(f"h4a: {e}")
        return 3
    fresh, why = hbuild.freshness(BUILD, say=lambda *_a, **_k: None)
    print(f"library: {'fresh' if fresh else 'STALE'}: {why}")
    if not fresh:
        print("h4a: the capture library must be fresh first: python tools/harness/build.py")
        return 3
    out: dict = {"route": route, "library": why, "steps": {}}
    ok = True
    kept: list[str] = []  # runs whose stripped metadata (meta.bin.z) waits for compare_meta

    def compare(x: dict, y: dict) -> tuple[bool, str]:
        return headless.compare_digests(x["state"], y["state"], headless.load_meta(x["run"]),
                                        headless.load_meta(y["run"]))

    def same_count(x: dict) -> tuple[bool, str]:
        """Capture must not change the guest's work either: the instruction count of the original."""
        eq = x["instructions"] == o1["instructions"]
        return eq, f"instructions {x['instructions']} ({'same as' if eq else 'DIFFERENT from'} the original)"

    def step(name: str, **kw) -> dict:
        r = headless.run(f"{prefix}-{name}", route, save=save, keep_meta=True, **kw)
        kept.append(r["run"])
        out["steps"][name] = {k: r.get(k) for k in ("run", "mode", "live", "exit_code", "seconds", "frames",
                                                    "instructions", "state", "shots")}
        if r["exit_code"] != 0 or "state" not in r:
            raise headless.Stop(f"run {r['run']} failed (exit {r['exit_code']}, see runs/{r['run']}/boot.log)")
        return r

    try:
        o1 = step("orig1", mode="original")
        o2 = step("orig2", mode="original")
        same, line = compare(o1, o2)
        same = same and o1["instructions"] == o2["instructions"]
        print(f"h4a 1/3 determinism (original twice, frame {o1['state_frame']}): {line}; instructions "
              f"{o1['instructions']} vs {o2['instructions']}: {'DETERMINISTIC' if same else 'DIVERGED'}")
        out["deterministic"] = same
        if not same:
            print("h4a: runs diverge: keep small checkpoints instead of regenerating (HARNESS.md 4); stopping")
            ok = False
            raise headless.Stop("not deterministic")
        ca = step("cap-a", mode="capture", live="a")
        same_a, line = compare(o1, ca)
        count_a, count_line = same_count(ca)
        line += "; " + count_line
        same_a = same_a and count_a
        summary_a = os.path.join(RUNS, ca["run"], "summary.tsv")
        if not os.path.isfile(summary_a):  # capture.c starts on the first readable call: none on this route
            print(f"h4a 2/3 fidelity only (capture, run A): {line}; no readable function was called on this route "
                  f"(no summary.tsv): nothing to compare live, run B not started")
            out["fidelity"] = {"state_same": same_a, "functions": 0}
            ok = ok and same_a
            raise headless.Stop("no readable function met")
        rows_a = read_summary(summary_a)
        unfaithful = sorted(k for k, v in rows_a.items() if v["verdicts"].get("unfaithful"))
        faithful = sum(v["verdicts"].get("faithful", 0) for v in rows_a.values())
        print(f"h4a 2/3 fidelity only (capture, run A): {line}; {len(rows_a)} function(s) met, {faithful} "
              f"record(s) faithful, unfaithful in {len(unfaithful)} function(s) {unfaithful[:8]}")
        print(f"         callbacks: {callbacks_totals(os.path.join(RUNS, ca['run']))}")
        out["fidelity"] = {"state_same": same_a, "functions": len(rows_a), "faithful_records": faithful,
                           "unfaithful_functions": unfaithful}
        if not same_a or unfaithful:
            print("h4a: capture disturbs the game or run A is unfaithful: run B not started")
            ok = False
            raise headless.Stop("fidelity gate")
        cb = step("cap-ab", mode="capture", live="ab")
        same_b, line = compare(o1, cb)
        count_b, count_line = same_count(cb)
        line += "; " + count_line
        same_b = same_b and count_b
        # the live verdicts (round 6, same rule as parallel.py): any bad record in any summary.tsv of run A+B
        # fails h4a; the boot.log is not read for this (its [fe-capture] lines are capped)
        rows_b, bad_b = live_bad_records(os.path.join(RUNS, cb["run"]))
        print(f"h4a 3/3 live compare (capture, runs A+B): {line}; {len(rows_b)} function(s) met, "
              f"{sum(bad_b.values())} bad record(s) ({', '.join(LIVE_BAD)}) in {len(bad_b)} function(s) "
              f"{sorted(bad_b)[:8]}")
        print(f"         callbacks: {callbacks_totals(os.path.join(RUNS, cb['run']))}")
        out["live"] = {"state_same": same_b, "functions": len(rows_b), "bad_records": sum(bad_b.values()),
                       "bad_functions": sorted(bad_b)}
        ok = ok and same_b and not bad_b
    except headless.Stop as e:
        print(f"h4a: {e}")
        ok = False
    finally:
        for name in kept:  # storage policy: about 0.25 MB each, only needed for the comparisons above
            try:
                os.remove(headless.meta_path(name))
            except OSError:
                pass
    # one result file per route, so a later route never overwrites another's evidence
    result = "h4a.json" if route == "prologue" else f"h4a-{route}.json"
    with open(os.path.join(BUILD, result), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    if "live" not in out:
        return 1
    run_ab = os.path.join(RUNS, f"{prefix}-cap-ab")
    if os.path.isfile(os.path.join(run_ab, "records.fecap")):
        cc, lib = rcheck.find_cc(), find_lib(None)
        exe = os.path.join(REPLAY_DIR, "replay" + EXE)
        stale = replay_stale(exe) if os.path.isfile(exe) else []
        if stale:
            print(f"h4a: {rel(exe)} is STALE ({len(stale)} newer input(s), first {rel(stale[0])}): kept records "
                  "not replayed offline (run `harness.py build`)")
        elif cc and lib and os.path.isfile(exe):
            for side in ("original", "readable"):
                rc, text, rows = replay(exe, lib, run_ab, side)
                print(f"h4a replay of the kept records, {side}: " + (text.splitlines()[-1] if text else f"rc {rc}"))
                if side == "original" and (rc or any(r["verdict"] in BAD for r in rows)):
                    print("h4a: original vs original is not clean on game records: a harness bug")
                    ok = False
                if side == "readable":
                    differ = [r for r in rows if r["live"] != r["verdict"]]
                    print(f"h4a offline vs live verdicts: {len(rows) - len(differ)}/{len(rows)} agree")
        else:
            print("h4a: replay.exe not built (harness.py build): kept records not replayed offline")
    else:
        print("h4a: no record kept (every record matched or gave up): nothing to replay offline")
    rc = cmd_report([f"{prefix}-cap-ab"])
    # the exit code covers the game (memory, metadata, instruction counts), run A's fidelity, the live
    # verdicts of run A+B (round 6: a mismatch record FAILS h4a, it is still a finding to read in the report),
    # the offline replay of kept records and the report
    print(f"h4a: {'PASS' if ok and rc == 0 else 'FAIL'} (exit code covers state, metadata, instruction counts, "
          f"fidelity, live mismatch records, offline replay and report)")
    return 0 if ok and rc == 0 else 1


def default_report_runs(runs_dir: str, why: dict | None = None) -> tuple[list[str], list[str]]:
    """The runs plain `harness.py report` merges as real play. Skipped (never merged as real play):
    - the capture replays of a synthetic session (recapture.py run on a session made by `recapture.py synth`):
      they replay a route run that is already in runs/, so counting them would add the same calls twice;
    - cheat runs (run.json "cheat" or "start_save_cheat", F-019), and any run whose route is named cheat-*
      even when run.json forgot the flag: real-play totals stay honest-play only;
    - suspect runs: no run.json, or one that cannot be read as a JSON object (Grok review 5 #1): without it
      nothing says the run was real play.
    Replays of an owner session are kept: they are the main source of records (HARNESS.md 4.3).
    why, if given, gets {run: reason} for each skipped run."""
    names, skipped = [], []
    for name in sorted(os.listdir(runs_dir)) if os.path.isdir(runs_dir) else []:
        reason = None
        try:
            with open(os.path.join(runs_dir, name, "run.json"), encoding="utf-8") as fh:
                meta = json.load(fh)
            if not isinstance(meta, dict):
                raise ValueError("not an object")
        except (OSError, ValueError):
            meta, reason = {}, "suspect: no readable run.json"
        route = str(meta.get("route") or "")
        if reason:
            pass
        elif meta.get("source") == "replay" and meta.get("session_kind") == "synthetic":
            reason = "replay of a synthetic session"
        elif meta.get("cheat") or meta.get("start_save_cheat") or route.startswith("cheat-"):
            reason = "cheat track (F-019)"  # cheat-track records never count as real play
        elif meta.get("options_run") or meta.get("start_save_options"):
            reason = "options track (OPTIONS_WIRING section 7)"  # writers armed: never counted as real play
        if reason:
            skipped.append(name)
            if why is not None:
                why[name] = reason
        else:
            names.append(name)
    return names, skipped


def run_source(run_dir: str) -> str:
    try:
        with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
            return json.load(fh).get("source", "?")
    except (OSError, ValueError):
        return "?"


FAKE_MUTATE = {"0x00200000": "fake_heal", "0x00200100": "fake_cached", "0x00200500": "fake_caller",
               "0x00201400": "fake_touch", "0x00201600": "fake_clampst", "0x00201700": "fake_count",
               "0x00201800": "fake_diff", "0x00201900": "fake_gated"}  # the right rows (fake_readable.c)
FAKE_MUTATE_SEEDS = (1, 2, 3, 4)


FAKE_HOOK_LIST = ("| id | slot | address | writes | readable callees | risk |\n|---|---|---|---|---|---|\n"
                  "| FW1 | a made-up writer that heals | blank | nothing (fakelib) | `fake_heal`, `fake_clampst` | none |\n"
                  "| FW2 | a made-up writer that counts | blank | nothing | `fake_count` | none |\n")


def fake_writer_targets(targets: list) -> tuple[list, str]:
    """The fakelib's targets a made-up hook list names (mutate.writer_callees on FAKE_HOOK_LIST): the same code path
    as the game's writer H6, with the fakelib's names standing in for the registry."""
    import mutate  # noqa: E402
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8", newline="\n") as fh:
        fh.write(FAKE_HOOK_LIST)
        path = fh.name
    try:
        got = mutate.writer_callees(os.path.join(BUILD, "no_functions.csv"), path,
                                    {int(t.address, 16): t.function for t in targets},
                                    os.path.join(BUILD, "no_code.bin"), os.path.join(BUILD, "no_layout.json"))
    finally:
        os.remove(path)
    keep = {f"0x{c:08X}" for c in (got[1] if got else {})}
    out = [t for t in targets if t.address.upper().replace("0X", "0x") in keep]
    return out, (f"mutate: writer H6 (fake): {len(out)} callee(s) of the made-up writer slots: "
                 + ", ".join(t.function for t in out))


def writer_callee_names(run_dir: str) -> tuple[list[str], str]:
    """The readable overrides the HOOK_LIST writer slots depend on (mutate.writer_callees) that run_dir kept records
    of (its summary.tsv). Empty when there is no hook list or no such record."""
    import mutate  # noqa: E402
    got = mutate.writer_callees()
    if got is None:
        return [], "mutate: no hook list (docs/harness/HOOK_LIST.md): writer callees unknown"
    names = {int(r["address"], 16) & ~1: r["name"] for r in rcheck.registry() if r["kind"].strip() == "override"}
    have = set()
    p = os.path.join(run_dir, "summary.tsv")
    if os.path.isfile(p):
        for a_, f in read_summary(p).items():
            if f["records"]:
                have.add(int(a_, 16) & ~1)
    keep = sorted(names[c] for c in got[1] if c in have)
    left = sorted(names[c] for c in got[1] if c not in have)
    return keep, (f"mutate: writer H6: {len(got[1])} readable callee(s) of {len(got[0])} writer slot(s); records for "
                  f"{len(keep)}: {', '.join(keep) or 'none'}" + (f"; no records for {', '.join(left)}" if left else ""))


def cmd_mutate(a) -> int:
    """H6 (HARNESS.md 5 "Mutation"): see tools/harness/mutate.py."""
    import mutate  # noqa: E402  (same folder)
    if a.writer_callees and not a.fake and a.run == "synth":  # list only
        got = mutate.writer_callees()
        if got is None:
            print(f"mutate: no hook list ({' or '.join(rel(p) for p in mutate.HOOK_LISTS)}): writer callees unknown")
            return 3
        slots, callees = got
        names = {int(r["address"], 16) & ~1: r for r in rcheck.registry()}
        print(f"writer slots with an address ({len(slots)}): " + ", ".join(f"{s_} 0x{x:08X}" for s_, x in slots))
        print(f"readable callees ({len(callees)}):")
        for c, sids in sorted(callees.items()):
            r = names.get(c, {})
            print(f"  0x{c:08X} {r.get('name', '?'):34s} {r.get('source', '?'):45s} called by {', '.join(sids)}")
        return 0
    cc = rcheck.find_cc()
    if cc is None:
        print("mutate: SETUP MISSING: no host C compiler")
        return 3
    jobs = a.jobs or max(1, min(12, (os.cpu_count() or 4) // 2))
    if a.fake:
        d = os.path.join(BUILD, "mutate", "fake-records")
        lib = os.path.join(d, "fakelib" + (".dll" if os.name == "nt" else ".so"))
        os.makedirs(d, exist_ok=True)
        rc, out = run([cc] + CFLAGS + ["-shared"] + INCS + [os.path.join(HERE, "fakelib", "fakelib.c"), "-o", lib])
        if rc:
            print(f"mutate: build fakelib: {out}")
            return 1
        fake = os.path.join(HERE, "fakelib", "fake_readable.c")
        sources = [os.path.join(HERE, "replay.c"), fake] + [os.path.join(SRC, "core", f) for f in ("capture.c", "runtime.c")]
        exe, err = build_replay(cc, os.path.join(d, "bin"), [fake])
        if exe is None:
            print(err)
            return 1
        runs = []
        for seed in FAKE_MUTATE_SEEDS:  # invented states, regenerated in seconds (storage policy)
            rd = os.path.join(d, f"seed{seed}")
            rc, out = synth(exe, lib, rd, calls=16, seed=seed, probes=FAKE_PROBES, guard=FAKE_GUARD)
            if rc:
                print(f"mutate: synth seed {seed}: {out[-300:]}")
                return 1
            runs.append(rd)
        targets = [mutate.Target(n, addr, fake) for addr, n in FAKE_MUTATE.items()]
        label = "fake"
        if a.writer_callees:  # a writer H6 on the fakelib: only the callees a made-up hook list names
            targets, why = fake_writer_targets(targets)
            print(why)
            if not targets:
                return 1
            label = "fake-writer"
        rc, summary = mutate.mutate(label, targets, runs, lib, cc, CFLAGS, INCS, sources, FAKE_PROBES, jobs)
        for rd in runs:
            drop_records(rd)
        if rc:
            return rc
        return 0 if summary["_total"]["rate"] >= 90.0 else 1
    if a.run == "synth" or not (a.functions or a.writer_callees):
        print("mutate: give --fake, or --run NAME --functions a,b | --writer-callees (a store-mode run's kept records)")
        return 2
    run_dir = os.path.join(RUNS, a.run)
    if not os.path.isfile(os.path.join(run_dir, "records.fecap")):
        print(f"mutate: no records in {rel(run_dir)} (a headless run with --only ... --store-keep)")
        return 3
    lib = find_lib(a.lib)
    if lib is None:
        print("mutate: SETUP MISSING: no library")
        return 3
    ok, msg = abi_gate(cc, os.path.dirname(lib), os.path.join(BUILD, "abi"))
    print(msg)
    if not ok:
        return 1
    reg = {r["name"]: r for r in rcheck.registry() if r["kind"].strip() == "override"}
    by_addr = {r["address"].upper().replace("0X", "0x"): r for r in reg.values()}
    targets = []
    if a.writer_callees:  # a writer H6: the HOOK_LIST slots' readable callees that this run kept records of
        names, why = writer_callee_names(run_dir)
        print(why)
        if not names:
            return 3
        a.functions = ",".join(names)
    for f in a.functions.split(","):
        r = reg.get(f) or by_addr.get(f.upper().replace("0X", "0x"))
        if r is None:
            print(f"mutate: {f}: not a readable override in config/readable/functions.csv")
            return 2
        targets.append(mutate.Target(r["name"], r["address"], os.path.join(ROOT, r["source"])))
    table = os.path.join(BUILD, "mutate", "overrides_table.c")
    write_table(table)
    sources = [os.path.join(HERE, "replay.c")] + readable_sources() + [table]
    label = "game-" + a.run
    rc, summary = mutate.mutate(label, targets, [run_dir], lib, cc, CFLAGS, INCS, sources, a.probes, jobs)
    return rc


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", choices=["abi", "build", "synth", "replay", "classify", "report",
                                                   "coverage", "shots", "smoke", "headless", "h4a"])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutate", action="store_true", help="H6 planted bugs (tools/harness/mutate.py)")
    ap.add_argument("--fake", action="store_true", help="--mutate: the fakelib proof")
    ap.add_argument("--functions", help="--mutate: readable functions (names or addresses)")
    ap.add_argument("--writer-callees", action="store_true",
                    help="--mutate: list the writer slots' readable callees (docs/harness/HOOK_LIST.md); with --run NAME "
                         "H6 on exactly those callees; with --fake the same on the fakelib")
    ap.add_argument("--jobs", type=int, help="--mutate: mutants built and replayed at once")
    ap.add_argument("--lib")
    ap.add_argument("--run", default="synth")
    ap.add_argument("--runs")
    ap.add_argument("--side", default="readable", choices=["readable", "original", "both"])
    ap.add_argument("--only")
    ap.add_argument("--image")
    ap.add_argument("--addrs")
    ap.add_argument("--probes")
    ap.add_argument("--calls", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seeds", help="smoke: comma list of seeds, one run each")
    ap.add_argument("--keep", action="store_true", help="smoke: keep the records (default: drop when clean)")
    ap.add_argument("--live", default="ab", choices=["ab", "a"])
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--route", default="title", help="headless/h4a: a route of config/harness/routes.json")
    ap.add_argument("--mode", default="capture", choices=["original", "capture"], help="headless")
    ap.add_argument("--no-late", action="store_true", help="headless: FE_CAPTURE_LATE=0")
    ap.add_argument("--save", help="headless/h4a: a PLAY backup zip (default: the newest in play/backups)")
    ap.add_argument("--keep-state", action="store_true", help="headless: keep the savestate in runs/NAME/")
    ap.add_argument("--store", action="store_true", help="headless: FE_CAPTURE_STORE=1 (needs --only)")
    ap.add_argument("--markers", action="store_true",
                    help="headless: memory-read screen markers at each shot frame (config/harness/markers.json)")
    ap.add_argument("--dump", help="headless: one guest range 0xADDR,LEN dumped at the end into runs/RUN/ (discovery)")
    ap.add_argument("--store-keep", action="store_true",
                    help="headless: FE_CAPTURE_STORE=keep (needs --only; records stay even when all pass)")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mutate:
        return cmd_mutate(a)
    if a.command is None:
        ap.print_help()
        return 2
    run_dir = os.path.join(RUNS, a.run)
    if a.command == "shots":
        for f in a.files:
            print(rel(ppm_to_png(f, os.path.join(BUILD, "shots", a.run))))
        return 0
    if a.command == "report":
        if a.runs:
            names = a.runs.split(",")
        else:
            why: dict = {}
            names, skipped = default_report_runs(RUNS, why)
            if skipped:
                print(f"report: {len(skipped)} run(s) left out of the real-play merge (name them with --runs to "
                      f"include): " + ", ".join(f"{n} ({why[n]})" for n in skipped))
        return cmd_report(names)
    if a.command in ("headless", "h4a"):
        sys.path.insert(0, HERE)
        import headless  # noqa: E402  (same folder)
        try:
            if a.command == "h4a":
                return cmd_h4a(a.route, a.save, a.run if a.run != "synth" else "h4a")
            if a.run == "synth":
                print("headless: give --run NAME")
                return 2
            r = headless.run(a.run, a.route, a.mode, live=a.live, late=not a.no_late, save=a.save,
                             keep_state=a.keep_state, only=a.only,
                             store="keep" if a.store_keep else a.store, markers=a.markers, extra_dump=a.dump)
            return 0 if r["exit_code"] == 0 and "state" in r else 1
        except headless.Stop as e:
            print(f"headless: SETUP: {e}")
            return 3
    if a.command == "classify":
        path = os.path.join(run_dir, "replay_readable.jsonl")
        if not os.path.isfile(path):
            print(f"classify: no {rel(path)} (run replay first)")
            return 3
        rows = [json.loads(ln) for ln in open(path, encoding="utf-8") if ln.strip()]
        fns = classify(rows, guard_users())
        with open(os.path.join(run_dir, "classify.json"), "w", encoding="utf-8") as fh:
            json.dump({k: {x: (y if x != "sigs" else len(y)) for x, y in v.items()} for k, v in fns.items()}, fh,
                      indent=1)
        for addr, f in sorted(fns.items()):
            if f["verdict"] == "MISMATCH":
                print(f"  {addr} MISMATCH: " + " | ".join(f["details"]))
        print(f"classify: {len(fns)} function(s): {verdict_table(fns, run_source(run_dir) == 'synth')}")
        return 0
    cc = rcheck.find_cc()
    if cc is None:
        print("harness: SETUP MISSING: no host C compiler (FE_HOST_CC, MSYS2 gcc, gcc, clang)")
        return 3
    lib = find_lib(a.lib)
    if lib is None:
        print("harness: SETUP MISSING: no library (--lib, build/harness/lib, build/readable/verify/lib)")
        return 3
    if os.path.dirname(lib) == os.path.abspath(os.path.join(BUILD, "lib")):
        # the capture library: built from today's sources? (build.py manifest; H4a gates on it)
        sys.path.insert(0, HERE)
        import build as hbuild  # noqa: E402  (same folder; imported only here, it stages files)
        fresh, why = hbuild.freshness(BUILD, say=lambda *_a, **_k: None)
        print(f"library: {'fresh' if fresh else 'STALE'}: {why}")
    ok, msg = abi_gate(cc, os.path.dirname(lib), os.path.join(BUILD, "abi"))
    print(msg)
    if not ok:
        return 1
    if a.command == "abi":
        return 0
    exe = os.path.join(REPLAY_DIR, "replay" + EXE)
    if a.command in ("build", "smoke"):
        n = write_table(os.path.join(REPLAY_DIR, "overrides_table.c"))
        exe_built, err = build_replay(cc, REPLAY_DIR, readable_sources() + [os.path.join(REPLAY_DIR, "overrides_table.c")],
                                      coverage=a.coverage)
        if exe_built is None:
            print(err)
            return 1
        print(f"build: {rel(exe_built)} with {n} readable override(s){' (gcov)' if a.coverage else ''}")
        if a.command == "build":
            return 0
    if not os.path.isfile(exe):
        print(f"harness: no {rel(exe)}: run `harness.py build` first")
        return 3
    if a.command == "replay":
        stale = replay_stale(exe)
        if stale:  # old readable code would give offline verdicts that differ from live ones
            print(f"harness: {rel(exe)} is STALE ({len(stale)} newer input(s), first {rel(stale[0])}): "
                  "run `harness.py build` first")
            return 3
    if a.command == "smoke":
        image = a.image or os.path.join(ROOT, "build", "code.bin")
        image = image if os.path.isfile(image) else None
        names, worst = [], 0
        for seed in [int(x) for x in (a.seeds or str(a.seed)).split(",")]:
            name = f"{a.run}-s{seed}"
            rdir = os.path.join(RUNS, name)
            rc, out = synth(exe, lib, rdir, image, a.addrs, a.calls, seed, a.probes, live=a.live)
            print(f"[{name}] " + (out.splitlines()[-1] if out else f"synth rc {rc}"))
            if rc:
                return 1
            names.append(name)
            clean = True
            for side in ("original", "readable"):
                rc, out, rows = replay(exe, lib, rdir, side, a.probes)
                print(f"[{name}] " + (out.splitlines()[-1] if out else f"replay rc {rc}"))
                if side == "original" and (rc or any(r["verdict"] in BAD for r in rows)):
                    print(f"[{name}] original vs original is not clean: a harness bug")
                    clean, worst = False, 1
                if side == "readable":
                    differ = [r for r in rows if r["live"] != r["verdict"]]
                    print(f"[{name}] offline vs live verdicts: {len(rows) - len(differ)}/{len(rows)} agree")
                    if differ:
                        clean, worst = False, 1
            if clean and not a.keep:  # storage policy: the states regenerate from the seed in seconds
                drop_records(rdir)
        rc = cmd_report(names)
        return max(rc, worst)
    if a.command == "synth":
        rc, out = synth(exe, lib, run_dir, a.image, a.addrs, a.calls, a.seed, a.probes, live=a.live)
        print(out)
        return rc
    if a.command == "replay":
        sides = ["original", "readable"] if a.side == "both" else [a.side]
        worst = 0
        for side in sides:
            rc, out, rows = replay(exe, lib, run_dir, side, a.probes, a.only)
            print(out.splitlines()[-1] if out else f"replay rc {rc}")
            worst = max(worst, rc)
            if side == "original" and any(r["verdict"] in BAD for r in rows):
                print("replay: original vs original is not clean: a harness bug (HARNESS.md 5, self-tests)")
                worst = max(worst, 1)
        return worst
    if a.command == "coverage":
        lines, taken, branches = gcov_report(os.path.join(REPLAY_DIR, "obj"), readable_sources())
        print("\n".join(lines))
        print(f"coverage: branches taken {taken}/{branches}" + (f" ({100 * taken / branches:.1f}%)" if branches else ""))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
