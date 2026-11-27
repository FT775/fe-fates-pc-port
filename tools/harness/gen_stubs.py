#!/usr/bin/env python3
"""Probe targets and probe stubs of the tier-4 harness (docs/HARNESS.md 3.2). Standard library only.

    python tools/harness/gen_stubs.py --check      config/harness/targets.csv agrees with the registry
                                                   (every readable override and every writer listed once,
                                                   no extra override or writer rows, probes are neither,
                                                   guard tags match extracted/code.bin when present)
    python tools/harness/gen_stubs.py --refresh    rewrite the override and writer rows of targets.csv from
                                                   config/readable/functions.csv (+ guard tags decoded
                                                   from extracted/code.bin), keeping every probe row
    python tools/harness/gen_stubs.py [--out DIR]  write the probe stubs (kind=probe rows) as
                                                   self-contained 3dsrecomp override files
                                                   harness__probes_NN.c into DIR (default
                                                   build/harness/overrides/); prints how many
    python tools/harness/gen_stubs.py --selftest   stubs for invented probe rows compile against the
                                                   stand-in header; broken target lists are refused

targets.csv (tracked) holds addresses, our own names, a kind and a reason: no game data.
  kind override  a readable override in src/readable (the registry is the truth; these rows
                 exist so harness.py can read reasons such as "guard user" in one place)
  kind probe     an address that gets an FE_PROBE stub in the capture library (from H7 on, per
                 writer batch; the first capture library has none, Grok consult point 3)
  kind writer    a readable writer (registry kind writer, docs/WRITERS.md): a game function our code
                 reproduces by storing ONLY through the writer gate, compiled in and OFF. It gets no
                 stub and no override marker, ever: the row exists so the harness knows the writer
                 slots (H6 on writers, harness.py --mutate --writer-callees) and so a probe can never
                 be put on a writer's address. The registry is the truth, as for overrides.
  reason         free text without commas or quotes; the exact tag "guard user (calls 0x<guard>)"
                 (GUARD_TAG; the guard is config/readable/addresses.json "guard") marks a direct caller of the one-time guard routine (harness.py: such a
                 function needs a cold record too, HARNESS.md 4.5). The word "guard" alone does not.
A probe address must be a function start in config/functions.csv (a stub replaces a whole function).

The stubs are written only under build/ (gitignored). Each one is

    <override marker>(0xADDRESS) { FE_PROBE(0xADDRESS); }

behind our own headers, pasted in by tools/readable/stage.py's flatten, like a staged source.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import glob
import json
import os
import re
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))

import check as rcheck  # noqa: E402  (registry, compiler search, markers)
import stage  # noqa: E402  (flatten: paste our headers)

TARGETS = os.path.join(ROOT, "config", "harness", "targets.csv")
OUT = os.path.join(ROOT, "build", "harness", "overrides")
GEN_SRC = os.path.join(ROOT, "build", "harness", "probe_src")
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
import gameaddr  # noqa: E402  (config/readable/addresses.json)

GUARD = gameaddr.addr("guard")                 # Fates: __cxa_guard_acquire 0x00302C6C (Thumb)
GUARD_TAG = f"guard user (calls 0x{GUARD:08X})"
# 3dsrecomp marks a Thumb function's override with an odd literal (address | 1). A probe on a
# Thumb routine (Fates' guard, __cxa_guard_acquire, is Thumb) must use that literal; odd
# addresses are accepted only for the Thumb routines named in config/readable/addresses.json.
THUMB_ENTRIES = {int(e["address"], 16) | 1 for e in gameaddr.table().values()
                 if e.get("isa") == "thumb" and e.get("address")}
GUARD_PROBE = GUARD | 1 if (GUARD | 1) in THUMB_ENTRIES else GUARD   # the probe / FE_CAPTURE_GUARD literal
CODE_BIN = os.path.join(ROOT, "extracted", "code.bin")
LAYOUT = os.path.join(ROOT, "extracted", "layout.json")
PER_FILE = 200
FIELDS = ["address", "name", "kind", "reason"]
ADDR_RX = re.compile(r"^0x[0-9A-F]{8}$")
NAME_RX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def rel(p: str) -> str:
    return rcheck.rel(p)


def read_targets(path: str = TARGETS) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        if rd.fieldnames != FIELDS:
            raise SystemExit(f"{rel(path)}: header {rd.fieldnames}, want {FIELDS}")
        return [dict(r) for r in rd]


def write_targets(rows: list[dict], path: str = TARGETS) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, FIELDS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in FIELDS})


def is_guard_user(reason: str) -> bool:
    """The guard tag, exactly; a source path or probe reason that merely says "guard" is not one."""
    return GUARD_TAG in (reason or "")


def function_starts(funcs_csv: str = rcheck.FUNCTIONS) -> set[str]:
    """Function starts of config/functions.csv as 0x + 8 uppercase hex (tracked; addresses only)."""
    with open(funcs_csv, newline="", encoding="utf-8") as fh:
        return {f"0x{int(r['addr'], 16):08X}" for r in csv.DictReader(fh)}


def call_target(w: int, a: int) -> int | None:
    """Target of an ARM BL<cond> or BLX imm at a (BLX switches to Thumb: the H bit adds 2)."""
    if (w >> 25) & 7 != 5:
        return None
    off = w & 0xFFFFFF
    if off & 0x800000:
        off -= 0x1000000
    if (w >> 28) == 0xF:                                  # BLX imm
        return (a + 8 + off * 4 + (((w >> 24) & 1) << 1)) & 0xFFFFFFFF
    if (w >> 24) & 1:                                     # BL (not B)
        return (a + 8 + off * 4) & 0xFFFFFFFF
    return None


def guard_callers(funcs_csv: str = rcheck.FUNCTIONS, code: bytes | None = None,
                  text_base: int | None = None, guard: int | None = None) -> set[int] | None:
    """Function starts whose body has a direct ARM bl/blx to the guard routine; None without
    extracted/code.bin or config/functions.csv. Decoded from code.bin (not asm/): in Fates the
    guard is Thumb, and gen_asm.py writes ARM->Thumb BLX calls as raw .inst words. Thumb
    callers are not scanned (Fates has only a handful of Thumb functions, all RVCT runtime).
    Only addresses come out of it; nothing is written."""
    guard = GUARD if guard is None else guard
    if code is None:
        if not (os.path.isfile(CODE_BIN) and os.path.isfile(LAYOUT)):
            return None
        with open(LAYOUT, encoding="utf-8") as fh:
            lay = json.load(fh)
        with open(CODE_BIN, "rb") as fh:
            code = fh.read()[: lay["text"]["size"]]
        text_base = lay["text"]["addr"]
    if not os.path.isfile(funcs_csv):
        return None
    with open(funcs_csv, newline="", encoding="utf-8") as fh:
        spans = sorted((int(r["addr"], 16), int(r["end"], 16)) for r in csv.DictReader(fh))
    starts = [s for s, _e in spans]
    out: set[int] = set()
    n = len(code) // 4
    for i, w in enumerate(struct.unpack(f"<{n}I", code[: n * 4])):
        at = text_base + 4 * i
        if call_target(w, at) != guard:
            continue
        j = bisect.bisect_right(starts, at) - 1
        if j >= 0 and at < spans[j][1]:
            out.add(spans[j][0])
    return out


WRITER_REASON = "WRITER OFF: stores only through the writer gate ({source}); no marker and no probe ever"


def writer_rows(reg_path: str = rcheck.REGISTRY) -> list[dict]:
    """One kind=writer row per registry writer (docs/WRITERS.md), in registry order."""
    return [{"address": r["address"], "name": r["name"], "kind": "writer",
             "reason": WRITER_REASON.format(source=r["source"].strip())}
            for r in rcheck.registry(reg_path) if r["kind"].strip() == "writer"]


def override_rows(reg_path: str = rcheck.REGISTRY, guards: set[int] | None = None) -> list[dict]:
    rows = []
    for r in rcheck.registry(reg_path):
        if r["kind"].strip() != "override":
            continue
        reason = f"readable override ({r['source']})"
        if guards is not None and (int(r["address"], 16) & ~1) in guards:
            reason += "; " + GUARD_TAG
        rows.append({"address": r["address"], "name": r["name"], "kind": "override", "reason": reason})
    return rows


def problems(rows: list[dict], reg_path: str = rcheck.REGISTRY, guards: set[int] | None = None,
             starts: set[str] | None = None) -> list[str]:
    errs: list[str] = []
    if starts is None:
        starts = function_starts()
    seen: set[str] = set()
    for i, r in enumerate(rows, 2):
        a = r.get("address") or ""
        if not ADDR_RX.match(a):
            errs.append(f"line {i}: address {a!r} must be 0x + 8 uppercase hex digits")
        elif int(a, 16) & 1 and not (r.get("kind") == "probe" and int(a, 16) in THUMB_ENTRIES):
            errs.append(f"line {i}: {a} is odd (ARM function starts are even; Thumb probes only for "
                        "the Thumb routines of config/readable/addresses.json)")
        if a in seen:
            errs.append(f"line {i}: {a} listed twice")
        seen.add(a)
        if not NAME_RX.match(r.get("name") or ""):
            errs.append(f"line {i}: name {r.get('name')!r} is not a C identifier")
        if r.get("kind") not in ("override", "probe", "writer"):
            errs.append(f"line {i}: kind {r.get('kind')!r} must be override, probe or writer")
        reason = r.get("reason") or ""
        if not reason.strip():
            errs.append(f"line {i}: {a} has no reason")
        if "," in reason or '"' in reason or "*/" in reason:
            errs.append(f"line {i}: reason holds a comma, a quote or */")
    reg = {r["address"]: r for r in rcheck.registry(reg_path) if r["kind"].strip() == "override"}
    listed = {r["address"]: r for r in rows if r.get("kind") == "override"}
    for a, r in reg.items():
        if a not in listed:
            errs.append(f"{a} {r['name']} is a readable override but not in targets.csv (gen_stubs.py --refresh)")
        elif listed[a]["name"] != r["name"]:
            errs.append(f"{a}: targets.csv names it {listed[a]['name']}, the registry {r['name']}")
    for a in listed:
        if a not in reg:
            errs.append(f"{a} is an override row but not a readable override in the registry")
    wreg = {r["address"]: r for r in rcheck.registry(reg_path) if r["kind"].strip() == "writer"}
    wlisted = {r["address"]: r for r in rows if r.get("kind") == "writer"}
    for a, r in wreg.items():
        if a not in wlisted:
            errs.append(f"{a} {r['name']} is a readable writer but not a writer row of targets.csv (gen_stubs.py --refresh)")
        elif wlisted[a]["name"] != r["name"]:
            errs.append(f"{a}: targets.csv names the writer {wlisted[a]['name']}, the registry {r['name']}")
    for a in wlisted:
        if a not in wreg:
            errs.append(f"{a} is a writer row but not a writer in the registry (config/readable/functions.csv kind writer)")
    for r in rows:
        a = r.get("address") or ""
        if r.get("kind") in ("probe", "override") and ADDR_RX.match(a) and f"0x{int(a, 16) & ~1:08X}" in wreg:
            errs.append(f"{a} is a writer's address: a writer never gets a probe or an override marker (docs/WRITERS.md)")
    for r in rows:
        if r.get("kind") == "probe" and r.get("address") in reg:
            errs.append(f"{r['address']} is a probe but already a readable override (one override per address)")
        elif r.get("kind") == "probe" and ADDR_RX.match(r.get("address") or "") and                 f"0x{int(r['address'], 16) & ~1:08X}" not in starts:
            errs.append(f"{r['address']} is a probe but not a function start in config/functions.csv")
    if guards is not None:
        for r in rows:
            if r.get("kind") != "override" or not ADDR_RX.match(r.get("address") or ""):
                continue
            want = int(r["address"], 16) in guards
            if want != is_guard_user(r.get("reason", "")):
                errs.append(f"{r['address']} {r['name']}: guard tag {'missing' if want else 'wrong'} "
                            f"(code.bin {'has' if want else 'has no'} a call to 0x{GUARD:08X})")
    return errs


def stub_text(chunk: list[dict], idx: int) -> str:
    lines = [f"/* GENERATED by tools/harness/gen_stubs.py from config/harness/targets.csv (file {idx}) --",
             "   do not edit. Harness probes (docs/HARNESS.md 3.2): each one forwards to the original;",
             "   in capture mode it records when sampled, otherwise it tells a replay tool's sink.",
             "   Addresses and our own names only; nothing here is game code. */",
             '#include "fe.h"', ""]
    for r in chunk:
        lines.append(f"/* {r['name']}: {r['reason']} */")
        lines.append(f"RECOMP_OVERRIDE({r['address']}) {{ FE_PROBE({r['address']}); }}")
    return "\n".join(lines) + "\n"


def generate(rows: list[dict], out_dir: str = OUT, src_dir: str = GEN_SRC) -> list[str]:
    """Write harness__probes_NN.c (self-contained) for the probe rows; returns the paths.
    Removes stale harness__probes_*.c from out_dir first; never touches other files there."""
    probes = [r for r in rows if r["kind"] == "probe"]
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(src_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "harness__probes_*.c")) + glob.glob(os.path.join(src_dir, "*.c")):
        os.remove(old)
    written = []
    for idx in range(0, len(probes), PER_FILE):
        n = idx // PER_FILE
        name = f"harness__probes_{n:02d}.c"
        src = os.path.join(src_dir, name)
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(stub_text(probes[idx:idx + PER_FILE], n))
        body: list[str] = []
        stage.flatten(src, set(), body)
        dst = os.path.join(out_dir, name)
        with open(dst, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(body) + "\n")
        written.append(dst)
    return written


# ------------------------------------------------------------------ self-test
def selftest() -> tuple[list[str], str]:
    errs: list[str] = []
    n = 0

    def expect(cond: bool, what: str):
        nonlocal n
        n += 1
        if not cond:
            errs.append(f"gen_stubs self-test: {what}")

    base = override_rows() + writer_rows()
    expect(not problems(base), f"fresh override and writer rows fail: {problems(base)[:2]}")
    reg = {r["address"] for r in base}
    wr = [r for r in base if r["kind"] == "writer"]
    expect(len(wr) >= 1, "no writer row from the registry (config_set_* and config_write_options are kind writer)")
    # probe addresses: the first three function starts of config/functions.csv that are not overrides
    fake = sorted(a for a in function_starts() if a not in reg)[:3]
    probes = [{"address": a, "name": f"probe_{a[2:]}", "kind": "probe", "reason": "self-test"} for a in fake]
    expect(not problems(base + probes), "probe rows refused")
    broken = [
        ("missing override", base[1:]),
        ("extra override", base + [{"address": "0x00100010", "name": "x", "kind": "override", "reason": "r"}]),
        ("renamed override", [dict(base[0], name=base[0]["name"] + "_x")] + base[1:]),
        ("probe on an override", base + [dict(base[0], kind="probe")]),
        ("duplicate", base + [probes[0], probes[0]]),
        ("lower-case hex", base + [dict(probes[0], address="0x0010000c")]),
        ("odd address", base + [dict(probes[0], address="0x00100005")]),
        ("bad kind", base + [dict(probes[0], kind="hook")]),
        ("no reason", base + [dict(probes[0], reason=" ")]),
        ("comment end in reason", base + [dict(probes[0], reason="a */ b")]),
        ("comma in reason", base + [dict(probes[0], reason="a, b")]),
        ("quote in reason", base + [dict(probes[0], reason='a "b"')]),
        ("probe inside a function", base + [dict(probes[0], address=f"0x{int(probes[0]['address'], 16) + 4:08X}")]),
        ("bad name", base + [dict(probes[0], name="1x")]),
        ("missing writer row", [r for r in base if r is not wr[0]]),
        ("extra writer row", base + [dict(probes[0], kind="writer")]),
        ("renamed writer row", [dict(r, name=r["name"] + "_x") if r is wr[0] else r for r in base]),
        ("probe on a writer's address", [r for r in base if r is not wr[0]] + [dict(wr[0], kind="probe")]),
        ("override row on a writer's address", [r for r in base if r is not wr[0]] + [dict(wr[0], kind="override")]),
        ("probe on a writer's address, writer row kept", base + [dict(wr[0], kind="probe", name="p_w")]),
    ]
    for what, rows in broken:
        expect(bool(problems(rows)), f"{what} accepted")
    g = int(base[0]["address"], 16)
    expect(bool(problems(base, guards={g})), "missing guard tag accepted")
    expect(not problems(override_rows(guards={g}) + writer_rows(), guards={g}), "right guard tag refused")
    expect(bool(problems(override_rows(guards={g}) + writer_rows(), guards=set())), "wrong guard tag accepted")
    looks = [dict(r, reason=r["reason"] + "; from src/readable/guard/x.c") if i == 0 else r for i, r in enumerate(base)]
    expect(not is_guard_user(looks[0]["reason"]) and not problems(looks, guards=set()),
           "the word guard in a reason taken for the guard tag")
    cc = rcheck.find_cc()
    scratch = os.path.join(ROOT, "build", "harness", "selftest")
    os.makedirs(scratch, exist_ok=True)  # on the repo's drive: stage.rel needs one
    with tempfile.TemporaryDirectory(dir=scratch, prefix="gen_stubs_") as td:
        # guard_callers on invented code + functions.csv: calls are mapped to the function holding
        # them; a call in a gap between functions, after a function's end, a plain B, or a call to
        # another routine is not. G is the guard; BLX imm (to Thumb) counts like BL.
        fcsv = os.path.join(td, "functions.csv")
        nl = chr(10)
        with open(fcsv, "w", encoding="utf-8", newline=nl) as fh:
            fh.write(nl.join(["addr,end,name,library,class,kind,name_source,confidence",
                              "0x00200000,0x00200010,a,,,,,", "0x00200020,0x00200040,b,,,,,",
                              "0x00200040,0x00200050,c,,,,,", "0x00200060,0x00200070,d,,,,,"]) + nl)
        base_va, G = 0x00200000, 0x00300002            # a Thumb guard (2-aligned), like Fates'

        def enc_bl(at, tgt, blx=False):
            d = tgt - (at + 8)
            if blx:
                return 0xFA000000 | (((d >> 1) & 1) << 24) | ((d >> 2) & 0xFFFFFF)
            return 0xEB000000 | ((d >> 2) & 0xFFFFFF)
        words = [0xE1A00000] * 0x30
        put = lambda at, w: words.__setitem__((at - base_va) // 4, w)  # noqa: E731
        put(0x0020000C, enc_bl(0x0020000C, G, blx=True))   # in a
        put(0x00200010, enc_bl(0x00200010, G, blx=True))   # a's end (exclusive): gap
        put(0x00200018, enc_bl(0x00200018, G, blx=True))   # gap before b
        put(0x00200024, enc_bl(0x00200024, G + 0xC, blx=True))  # b calls another routine
        put(0x00200028, enc_bl(0x00200028, G - 2) & 0xFEFFFFFF)  # a plain B (not a call) in b
        put(0x00200040, enc_bl(0x00200040, G, blx=True))   # first word of c
        put(0x00200080, enc_bl(0x00200080, G, blx=True))   # after the last function
        code = struct.pack(f"<{len(words)}I", *words)
        got = guard_callers(fcsv, code, base_va, G)
        expect(got == {0x00200000, 0x00200040}, f"guard_callers {sorted(map(hex, got or ()))}")
        expect(call_target(enc_bl(0x00200000, 0x00300000), 0x00200000) == 0x00300000, "BL target")
        expect(call_target(enc_bl(0x00200000, 0x00300002, blx=True), 0x00200000) == 0x00300002,
               "BLX imm target keeps the H bit")
        expect(guard_callers(os.path.join(td, "none.csv"), code, base_va, G) is None,
               "guard_callers without functions.csv")
        o, s = os.path.join(td, "out"), os.path.join(td, "src")
        os.makedirs(o)
        keep = os.path.join(o, "core__runtime.c")
        open(keep, "w").close()
        out = generate(base + probes, o, s)
        expect(len(out) == 1, f"{len(out)} stub file(s) for {len(probes)} probes")
        stubbed = [lit for p_ in out for lit, _e, _l in rcheck.markers(rcheck.strip_code(open(p_, encoding="utf-8").read()))]
        expect(not set(stubbed) & {r["address"] for r in wr}, "a writer row got a stub (a marker on a writer)")
        expect(generate(base, o, s) == [] and not glob.glob(os.path.join(o, "harness__*.c")),
               "stale stub files kept")
        expect(os.path.isfile(keep), "a staged readable file was removed")
        many = [{"address": f"0x{0x00800000 + 4 * i:08X}", "name": f"p{i}", "kind": "probe", "reason": "r"}
                for i in range(PER_FILE + 1)]
        expect(len(generate(many, o, s)) == 2, "not split per file")
        out = generate(probes, o, s)
        text = open(out[0], encoding="utf-8").read()
        got = [lit for lit, _e, _l in rcheck.markers(rcheck.strip_code(text))]
        expect(got == fake, f"markers {got}, want {fake}")
        expect('#include "fe.h"' not in text and "FE_PROBE(" in text, "headers not pasted")
        if cc:
            rc, msg = rcheck.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsyntax-only",
                                  "-I", rcheck.STUB, out[0]])
            expect(rc == 0 and not msg, f"stub does not compile with only the stand-in header:\n{msg}")
    return errs, f"gen_stubs self-test: {n - len(errs)}/{n} checks passed" + ("" if cc else " (compile SKIPPED)")


def check_targets(guards: set[int] | None, say=print) -> tuple[int, list[dict]]:
    if not os.path.isfile(TARGETS):
        say(f"targets: no {rel(TARGETS)} (gen_stubs.py --refresh)")
        return 3, []
    rows = read_targets()
    errs = problems(rows, guards=guards)
    for e in errs:
        say(f"targets: {e}")
    if errs:
        say(f"targets: {len(errs)} problem(s)")
        return 1, rows
    np = sum(r["kind"] == "probe" for r in rows)
    nw = sum(r["kind"] == "writer" for r in rows)
    ng = sum(is_guard_user(r["reason"]) for r in rows if r["kind"] == "override")
    say(f"targets: OK ({len(rows) - np - nw} override(s), {ng} of them guard users, {np} probe(s), {nw} writer(s), "
        f"never stubbed"
        f"{'' if guards is not None else '; guard tags not checked, no code.bin or config/functions.csv'})")
    return 0, rows


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    if a.selftest:
        errs, line = selftest()
        for e in errs:
            print(e)
        print(line)
        return 1 if errs else 0
    guards = guard_callers()
    if a.refresh:
        keep = [r for r in read_targets() if r["kind"] == "probe"] if os.path.isfile(TARGETS) else []
        write_targets(override_rows(guards=guards) + writer_rows() + keep)
    rc, rows = check_targets(guards)
    if rc or a.check or a.refresh:
        return rc
    out_dir = os.path.abspath(a.out)
    if not rel(out_dir).startswith("build/") or ".." in rel(out_dir).split("/"):
        print(f"gen_stubs: --out must be under build/ (got {a.out})")
        return 2
    out = generate(rows, out_dir)
    np = sum(r["kind"] == "probe" for r in rows)
    print(f"gen_stubs: {np} probe(s) in {len(out)} file(s) under {rel(out_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
