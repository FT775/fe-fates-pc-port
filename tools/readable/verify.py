#!/usr/bin/env python3
"""Tier 2 of the readable checks: 3dsrecomp `verify` on every readable override
(docs/READABLE.md 1.3 and 6). Standard library only.

    python tools/readable/verify.py                  stage, build, verify each override, classify
    python tools/readable/verify.py --skip-build     reuse the library already in build/readable/verify/lib
    python tools/readable/verify.py --only 0x002C4D88,0x002ECB44
    python tools/readable/verify.py --update-status  also write the results into config/readable/functions.csv
    python tools/readable/verify.py --check-setup    only say what was found (3dsrecomp, ROM, C compiler)
    python tools/readable/verify.py --selftest       the whole pipeline against a fake 3dsrecomp (no Rust, no ROM)

Needs:
  - 3dsrecomp built WITH the verify feature: `python tools/engine/engine.py build 3dsrecomp-verify`
    puts it at engine/target/3dsrecomp-verify/release/3dsrecomp.exe (or --recomp PATH, FE_3DSRECOMP).
    3dsrecomp has no licence: it is run as built, nothing of it is copied here.
  - the ROM: --rom, FE_ROM, or "rom" in play/config.json (the PLAY launcher's settings).
  - a C compiler for the generated code: CC if set, else MSYS2's gcc (C:\\msys64\\ucrt64\\bin is
    put first on PATH), else whatever 3dsrecomp finds (on Windows: gcc, clang, cc).

Everything is written under build/readable/verify/ (gitignored); nothing under %APPDATA%:
  overrides/                 tools/readable/stage.py --mode readable
  lib/                       3dsrecomp build <rom> lib --overrides overrides  (ALWAYS with a folder:
                             without one 3dsrecomp installs the library to %APPDATA%\\3dsrecomp,
                             where Zakuro would run it for the owner's game)
  <ADDR>.txt, .readable.log  VERIFY_ONLY=<ADDR> FE_READABLE=readable: verify compares the readable
                             result with the interpreter running the game's code
  <ADDR>.shadow.txt, .log    VERIFY_ONLY=<ADDR> FE_READABLE=shadow: the original drives, the readable
                             result is compared with it on the same state (logged), and shadow mode
                             must be invisible to verify
  build.log, summary.json

Verdicts per override (tools/readable/check.py classify_function): CLEAN, ABI-ONLY (differences
only in r1-r3, r12, lr, flags, stack below sp: allowed), GAVE-UP (matched only because the readable
code gave up, e.g. a one-time cache that is still cold in verify's pristine memory: its guard
words are 0 in the .data image; proves nothing), MISMATCH, NOT-RUN, UNSAMPLED (verify cannot
pick the address: both passes tested 0 functions and lib/entries.c shows its code held inside
another function; 0 functions without such a holder is NOT-RUN; nothing compared. Also when
the game's own code runs past verify's instruction limit under the interpreter in both passes).
--update-status: CLEAN/ABI-ONLY -> verified-unit; GAVE-UP -> blocked (reason in evidence);
MISMATCH on a verified-unit/blocked row -> unverified; UNSAMPLED only adds a note;
shadow-clean/verified are never touched.

Exit 0 when every override is CLEAN, ABI-ONLY, GAVE-UP or UNSAMPLED (UNSAMPLED counts as a
problem on a row whose status already rests on tier 2: that would be lost coverage); 1 on a
MISMATCH, a NOT-RUN or a failed step; 3 when a needed input is missing. The last line is `readable-verify: OK (...)`,
`readable-verify: N problem(s) (...)` or `readable-verify: SETUP MISSING: ...`.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import check  # noqa: E402  (same folder)
import stage  # noqa: E402

EXE = ".exe" if os.name == "nt" else ""
OUT = os.path.join(ROOT, "build", "readable", "verify")
RECOMP_DEFAULT = os.path.join(ROOT, "engine", "target", "3dsrecomp-verify", "release", "3dsrecomp" + EXE)
PLAY_CONFIG = os.path.join(ROOT, "play", "config.json")
MSYS2_BIN = r"C:\msys64\ucrt64\bin"
LIBRARY = stage.TITLE_ID + (".dll" if os.name == "nt" else ".so")
BUILD_TIMEOUT = 4 * 3600
VERIFY_TIMEOUT = 900
TIER2_TAG = "tier 2:"


class Setup(Exception):
    """A needed input is missing (exit 3)."""


# ------------------------------------------------------------------ finding things
def find_recomp(given: str | None) -> str:
    p = given or os.environ.get("FE_3DSRECOMP") or RECOMP_DEFAULT
    if not os.path.isfile(p):
        raise Setup(f"no 3dsrecomp at {check.rel(p)} (python tools/engine/engine.py build 3dsrecomp-verify)")
    return p


def find_rom(given: str | None) -> str:
    """--rom, else FE_ROM, else "rom" in play/config.json when that file is there, else the .cci in roms/
    (then the old repo-root place for one release): tools/paths.py (F-048)."""
    sys.path.append(os.path.join(ROOT, "tools"))
    import paths  # noqa: E402
    try:
        p = str(paths.resolve_rom(given, repo=ROOT))
    except paths.PathError as e:
        raise Setup(f"no ROM ({e}; --rom, FE_ROM, \"rom\" in play/config.json, or the .cci in roms/)") from None
    if not os.path.isfile(p):
        raise Setup(f"no ROM ({p}; --rom, FE_ROM, \"rom\" in play/config.json, or the .cci in roms/)")
    return p


def tool_env() -> tuple[dict, str]:
    """(environment for 3dsrecomp, which C compiler it will use)."""
    env = dict(os.environ)
    if env.get("CC", "").strip():
        return env, f"CC={env['CC']}"
    gcc = os.path.join(MSYS2_BIN, "gcc.exe")
    if os.name == "nt" and os.path.isfile(gcc):
        env["PATH"] = MSYS2_BIN + os.pathsep + env.get("PATH", "")
        return env, gcc
    return env, "3dsrecomp's own pick (gcc, clang, cc on PATH)"


def recomp_argv(recomp: str, *args: str) -> list[str]:
    # a .py "3dsrecomp" is the self-test's fake
    return ([sys.executable, recomp] if recomp.endswith(".py") else [recomp]) + list(args)


def has_verify(recomp: str, env: dict) -> bool:
    """A build without the feature answers `verify` with 'this build has no verify'."""
    try:
        r = subprocess.run(recomp_argv(recomp, "verify"), capture_output=True, text=True, env=env,
                           timeout=120, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Setup(f"could not run {check.rel(recomp)}: {e}")
    return "has no verify" not in (r.stdout + r.stderr)


def under(path: str, base: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(base)]) == os.path.abspath(base)
    except ValueError:
        return False


# ------------------------------------------------------------------ the run
def run_logged(argv: list[str], env: dict, log, timeout: float, out_path: str | None = None) -> tuple[int | None, float]:
    log.write("$ " + subprocess.list2cmdline(argv) + "\n")
    log.flush()
    t0 = time.time()
    try:
        if out_path:
            with open(out_path, "w", encoding="utf-8", errors="replace") as fh:
                r = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT, env=env, timeout=timeout,
                                   stdin=subprocess.DEVNULL)
        else:
            r = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=timeout,
                               stdin=subprocess.DEVNULL)
        rc = r.returncode
    except subprocess.TimeoutExpired:
        rc = None
        log.write(f"[verify.py] timed out after {timeout:.0f}s\n")
    took = time.time() - t0
    log.write(f"[verify.py] exit {rc} after {took:.1f}s\n")
    log.flush()
    return rc, took


def pipeline(rom: str, recomp: str, out_dir: str, reg_path: str = check.REGISTRY, only: list[str] | None = None,
             skip_build: bool = False, shadow: bool = True, env: dict | None = None,
             say=print) -> tuple[int, dict]:
    """Stage, build, verify, classify. Returns (exit code, summary)."""
    env = dict(env if env is not None else tool_env()[0])
    os.makedirs(out_dir, exist_ok=True)
    lib_dir = os.path.join(out_dir, "lib")
    library = os.path.join(lib_dir, LIBRARY)
    overrides_dir = os.path.join(out_dir, "overrides")
    rows = [r for r in check.registry(reg_path) if r["kind"].strip() == "override"]
    if only:
        want = {"0x" + a.strip().upper().removeprefix("0X").rjust(8, "0") for a in only}
        unknown = want - {r["address"] for r in rows}
        if unknown:
            raise Setup(f"--only names {sorted(unknown)}, which are not overrides in the registry")
        rows = [r for r in rows if r["address"] in want]
    summary: dict = {"tool": "tools/readable/verify.py", "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                     "rom": rom, "recomp": recomp, "library": library, "steps": {}, "functions": []}
    with open(os.path.join(out_dir, "build.log"), "a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n==== {summary['date']} verify.py\n")
        if not skip_build:
            staged = stage.stage("readable", overrides_dir)
            say(f"staged {len(staged)} file(s) into {check.rel(overrides_dir)} (default mode readable)")
            # always WITH a folder: without one 3dsrecomp installs into %APPDATA%\3dsrecomp
            assert under(lib_dir, out_dir)
            say(f"building the library into {check.rel(lib_dir)} (the whole game; this takes a while) ...")
            rc, took = run_logged(recomp_argv(recomp, "build", rom, lib_dir, "--overrides", overrides_dir),
                                  env, log, BUILD_TIMEOUT)
            summary["steps"]["build"] = {"exit": rc, "seconds": round(took, 1)}
            say(f"build: exit {rc} after {took:.0f}s (log: {check.rel(os.path.join(out_dir, 'build.log'))})")
            if rc != 0 or not os.path.isfile(library):
                say(f"readable-verify: 1 problem(s) (the build failed or wrote no {LIBRARY})")
                write_summary(out_dir, summary)
                return 1, summary
        elif not os.path.isfile(library):
            raise Setup(f"--skip-build but no library at {check.rel(library)}")
        passes = [("readable", ".txt", ".readable.log")] + ([("shadow", ".shadow.txt", ".shadow.log")] if shadow else [])
        for r in rows:
            a = r["address"][2:]
            for mode, out_suffix, log_suffix in passes:
                for suffix in (out_suffix, log_suffix):
                    p = os.path.join(out_dir, a + suffix)
                    if os.path.exists(p):
                        os.remove(p)
                e = dict(env, VERIFY_ONLY=a, FE_READABLE=mode, FE_READABLE_LOG=os.path.join(out_dir, a + log_suffix))
                rc, took = run_logged(recomp_argv(recomp, "verify", rom, library), e, log, VERIFY_TIMEOUT,
                                      os.path.join(out_dir, a + out_suffix))
                summary["steps"][f"{a}.{mode}"] = {"exit": rc, "seconds": round(took, 1)}
    results = [x for x in check.verify_results(out_dir, reg_path) if x[0]["address"] in {r["address"] for r in rows}]
    counts: dict[str, int] = {}
    for r, verdict, details in results:
        counts[verdict] = counts.get(verdict, 0) + 1
        summary["functions"].append({"address": r["address"], "name": r["name"], "verdict": verdict,
                                     "details": details, "status": r["status"]})
        say(f"  {verdict:<8} {r['address']} {r['name']}" + (f": {'; '.join(details)}" if details else ""))
    summary["counts"] = counts
    write_summary(out_dir, summary)
    text = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    say(f"verify-logs: {text}")
    bad = counts.get("MISMATCH", 0) + counts.get("NOT-RUN", 0)
    # an address verify used to sample and now cannot: coverage was lost, say so
    lost = [r["address"] for r, verdict, _ in results
            if verdict == check.UNSAMPLED and r["status"].strip() not in ("unverified", "")]
    for a in lost:
        say(f"  {a}: UNSAMPLED, but its status rests on tier 2")
    bad += len(lost)
    if not results:
        say("readable-verify: 1 problem(s) (no override was verified)")
        return 1, summary
    if bad:
        say(f"readable-verify: {bad} problem(s) ({text})")
        return 1, summary
    say(f"readable-verify: OK ({text})")
    return 0, summary


def write_summary(out_dir: str, summary: dict) -> None:
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
        fh.write("\n")


# ------------------------------------------------------------------ registry update
def new_status(old: str, verdict: str) -> str:
    if old in ("shadow-clean", "verified"):
        return old                       # higher tiers are only moved by their own evidence
    if verdict in check.VERIFY_PASS:
        return "verified-unit"
    if verdict == "GAVE-UP":
        return "blocked"
    if verdict == "MISMATCH":
        return "unverified"
    return old                           # NOT-RUN, UNSAMPLED: no evidence either way


def tier2_note(verdict: str, details: list[str], date: str) -> str:
    if verdict == "GAVE-UP":
        return (f"{TIER2_TAG} {date} blocked: verify only reached the give-up path (its pristine memory leaves "
                f"a one-time cache cold or a table the game builds at start-up missing); needs shadow mode in the game or the tier-4 harness")
    if verdict == check.UNSAMPLED and any("instruction limit" in d for d in details):
        return (f"{TIER2_TAG} {date} not sampled: in verify's made-up state the game's own code runs past "
                f"verify's instruction limit, nothing was compared; needs shadow mode in the game or the "
                f"tier-4 harness")
    if verdict == check.UNSAMPLED:
        held = next((d.split("held inside ")[1].split(" ")[0] for d in details if "held inside " in d), "another function")
        return (f"{TIER2_TAG} {date} not sampled: verify cannot pick this address (its code is held inside {held} "
                f"in the build's entry table); needs shadow mode in the game or the tier-4 harness")
    first = details[0] if details else ""
    return f"{TIER2_TAG} {date} {verdict}" + (f" ({first})" if first and verdict != "CLEAN" else "")


def update_registry(reg_path: str, summary: dict, say=print) -> int:
    """Write statuses and a 'tier 2:' note into the registry; returns rows changed."""
    with open(reg_path, encoding="utf-8", newline="") as fh:
        raw = fh.read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    header = lines[0].split(",")
    if header[-1] != "evidence" or "status" not in header:
        raise SystemExit(f"{reg_path}: unexpected header {lines[0]!r}")
    si = header.index("status")
    by_addr = {f["address"]: f for f in summary["functions"]}
    date = summary["date"][:10]
    changed = 0
    import csv as _csv
    for i, line in enumerate(lines[1:], 1):
        if not line.strip():
            continue
        fields = next(_csv.reader([line]))
        f = by_addr.get(fields[0])
        if f is None or f["verdict"] == "NOT-RUN":
            continue
        old = fields[si]
        status = new_status(old, f["verdict"])
        evidence = fields[-1].split(f" | {TIER2_TAG}")[0]
        if status not in ("shadow-clean", "verified"):
            evidence += f" | {tier2_note(f['verdict'], f['details'], date)}"
        if status != old:
            say(f"  {fields[0]} {fields[1]}: {old} -> {status}")
        fields[si] = status
        for x in fields[:-1]:
            if "," in x or '"' in x:
                raise SystemExit(f"{reg_path}:{i + 1}: a comma or quote outside evidence")
        new = ",".join(fields[:-1]) + ',"' + evidence.replace('"', '""') + '"'
        if new != line:
            lines[i] = new
            changed += 1
    with open(reg_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(nl.join(lines))
    return changed


# ------------------------------------------------------------------ self-test
FAKE = r'''
import json, os, sys
args = sys.argv[1:]
rec = os.environ.get("FAKE_RECORD")
if rec:
    with open(rec, "a") as fh:
        fh.write(json.dumps({"argv": args, "VERIFY_ONLY": os.environ.get("VERIFY_ONLY"),
                             "FE_READABLE": os.environ.get("FE_READABLE")}) + "\n")
if args == ["verify"]:
    print("this build has no verify, build it with --features verify" if os.environ.get("FAKE_NO_VERIFY") else "usage, ...")
    sys.exit(2)
if args[0] == "build":
    if len(args) != 5 or args[3] != "--overrides":
        print("no folder given: this would install into %APPDATA%"); sys.exit(9)
    files = [f for f in os.listdir(args[4]) if f.endswith(".c")]
    if not files or any("FE_MODE_READABLE" not in open(os.path.join(args[4], f), encoding="utf-8", errors="replace").read() for f in files):
        print("overrides not staged in readable mode"); sys.exit(8)
    os.makedirs(args[2], exist_ok=True)
    # the entry table: an address "notfound" is held inside another function (a fall-through
    # entry 4 bytes in, as for 0x0027CA08), "notfound_free" has no holder
    with open(os.path.join(args[2], "entries.c"), "w") as fh:
        for a, kind in json.loads(os.environ.get("FAKE_SCENARIOS", "{}")).items():
            print("    {0x%su, override_0x%s}," % (a, a), file=fh)
            if kind == "notfound":
                print("    {0x%08Xu, f_00100000}," % (int(a, 16) + 4), file=fh)
    if not os.environ.get("FAKE_NO_LIBRARY"):
        open(os.path.join(args[2], "LIBNAME"), "w").close()
    print(f"wrote 9 files, 1 MiB of C, {len(files)} overrides"); sys.exit(0)
if args[0] == "verify":
    a, mode = os.environ["VERIFY_ONLY"], os.environ["FE_READABLE"]
    kind = json.loads(os.environ["FAKE_SCENARIOS"]).get(a, "abi")
    log = open(os.environ["FE_READABLE_LOG"], "a")
    log.write(f"[fe-readable] mode {mode} (set FE_READABLE=original|readable|shadow)\n")
    s = "executable  {} functions, {} returned, 0 reached an svc, 0 stuck, 0 stopped otherwise, {} mismatched, 0 svcs gone through"
    if kind in ("notfound", "notfound_free"):
        print(s.format(0, 0, 0)); sys.exit(0)
    print(f"  executable {a}, interpreter stopped with Returned, recompiled with Returned")
    diff = None
    if mode == "readable":
        if kind in ("abi", "shadowmis"):
            diff = "r1 00000001 against 00000002, r12 0 against 1, memory at 0FFFEFF0"
        elif kind == "mismatch":
            diff = "r0 00000005 against 00000006"
        elif kind == "gaveup":
            log.write(f"[fe-readable] 0x{a} f: gave up, the original ran (1)\n")
    else:
        if kind == "shadowmis":
            log.write(f"[fe-readable] MISMATCH 0x{a} f(r0=1 r1=2 r2=3 r3=4): game 00000005 (5), readable 00000006 (6) [1 mismatches, 0 matches]\n")
        elif kind == "gaveup":
            log.write(f"[fe-readable] 0x{a} f: shadow skipped (readable gave up) (1)\n")
        else:
            log.write(f"[fe-readable] 0x{a} f: shadow match (1 so far, 0 mismatches)\n")
    if diff:
        print(f"  executable {a}  {diff}")
    print(s.format(1, 0 if diff else 1, 1 if diff else 0))
    sys.exit(0)
sys.exit(2)
'''.replace("LIBNAME", LIBRARY)


def selftest() -> tuple[list[str], str]:
    """The pipeline end to end against a fake 3dsrecomp, in a temporary folder. Returns
    (problems, summary line)."""
    errs: list[str] = []
    n = 0
    quiet = lambda *_a, **_k: None  # noqa: E731
    overrides = [r for r in check.registry() if r["kind"] == "override"]
    addrs = [r["address"][2:] for r in overrides]
    with tempfile.TemporaryDirectory() as td:
        fake = os.path.join(td, "fake_3dsrecomp.py")
        open(fake, "w", encoding="utf-8").write(FAKE)
        rom = os.path.join(td, "game.cci")
        open(rom, "wb").close()
        record = os.path.join(td, "record.jsonl")
        reg = os.path.join(td, "functions.csv")
        shutil.copy(check.REGISTRY, reg)

        def go(scen: dict, name: str, **kw):
            out = os.path.join(td, name)
            if os.path.exists(record):
                os.remove(record)
            env = dict(os.environ, FAKE_SCENARIOS=json.dumps(scen), FAKE_RECORD=record)
            env.update(kw.pop("extra_env", {}))
            return pipeline(rom, fake, out, reg, env=env, say=quiet, **kw)

        def expect(cond: bool, what: str):
            nonlocal n
            n += 1
            if not cond:
                errs.append(f"verify self-test: {what}")

        # 1. mixed results: every verdict reached, exit 1, the build had a folder, modes right
        scen = {addrs[0]: "abi", addrs[1]: "mismatch", addrs[2]: "gaveup", addrs[3]: "notfound",
                addrs[4]: "shadowmis", addrs[5]: "notfound_free"}
        rc, s = go(scen, "mixed")
        got = {f["address"][2:]: f["verdict"] for f in s["functions"]}
        expect(rc == 1, f"mixed results exit {rc}, want 1")
        expect(got.get(addrs[0]) == "ABI-ONLY", f"abi scenario -> {got.get(addrs[0])}")
        expect(got.get(addrs[1]) == "MISMATCH", f"r0 difference -> {got.get(addrs[1])}")
        expect(got.get(addrs[2]) == "GAVE-UP", f"give-up -> {got.get(addrs[2])}")
        expect(got.get(addrs[3]) == "UNSAMPLED", f"address not found -> {got.get(addrs[3])}")
        expect(got.get(addrs[4]) == "MISMATCH", f"shadow log mismatch -> {got.get(addrs[4])}")
        expect(got.get(addrs[5]) == "NOT-RUN", f"address not found, no holder -> {got.get(addrs[5])}")
        calls = [json.loads(x) for x in open(record, encoding="utf-8")]
        builds = [c for c in calls if c["argv"][0] == "build"]
        expect(len(builds) == 1 and len(builds[0]["argv"]) == 5, f"build calls {builds}")
        modes = sorted((c["VERIFY_ONLY"], c["FE_READABLE"]) for c in calls if c["argv"][0] == "verify")
        expect(modes == sorted((a, m) for a in addrs for m in ("readable", "shadow")),
               "one readable and one shadow verify run per override, with VERIFY_ONLY")
        expect(os.path.isfile(os.path.join(td, "mixed", "summary.json")), "summary.json written")

        # 2. all pass (one gives up): exit 0; the registry update moves statuses, lint accepts it
        rc, s = go({addrs[2]: "gaveup"}, "pass")
        expect(rc == 0, f"all-pass exit {rc}, want 0")
        update_registry(reg, s, say=quiet)
        st = {r["address"][2:]: r for r in check.registry(reg)}
        expect(st[addrs[0]]["status"] == "verified-unit", f"pass -> {st[addrs[0]]['status']}")
        expect(st[addrs[2]]["status"] == "blocked" and "blocked:" in st[addrs[2]]["evidence"],
               f"gave up -> {st[addrs[2]]['status']}")
        expect(all(r["status"] == "unverified" for r in check.registry(reg) if r["kind"] == "helper"),
               "helpers untouched")
        lint = check.lint(reg_path=reg)
        expect(not lint, f"updated registry fails lint: {lint[:2]}")
        update_registry(reg, s, say=quiet)
        expect(open(reg, encoding="utf-8").read().count(TIER2_TAG) == len(addrs),
               "a second update replaces the tier-2 note instead of adding one")

        # 3. a later mismatch takes verified-unit back; shadow-clean is never touched
        rc, s = go({addrs[0]: "mismatch"}, "regress", only=["0x" + addrs[0]])
        update_registry(reg, s, say=quiet)
        expect(check.registry(reg)[[r["address"][2:] for r in check.registry(reg)].index(addrs[0])]["status"]
               == "unverified", "mismatch after verified-unit -> unverified")
        expect(new_status("shadow-clean", "MISMATCH") == "shadow-clean", "shadow-clean untouched")
        expect(new_status("verified-unit", "NOT-RUN") == "verified-unit", "NOT-RUN changes nothing")
        expect(new_status("unverified", check.UNSAMPLED) == "unverified", "UNSAMPLED changes nothing")

        # 3b. not in verify's sample: no problem on an unverified row, a problem on a row
        # whose status rests on tier 2 (lost coverage)
        unver = [r["address"][2:] for r in check.registry(reg)
                 if r["kind"] == "override" and r["status"] == "unverified"]
        tier2 = [r["address"][2:] for r in check.registry(reg)
                 if r["kind"] == "override" and r["status"] in ("verified-unit", "blocked")]
        if unver and tier2:
            rc, s = go({unver[0]: "notfound"}, "unsampled", only=["0x" + unver[0]])
            expect(rc == 0 and s["functions"][0]["verdict"] == check.UNSAMPLED,
                   f"unsampled unverified row -> exit {rc}")
            update_registry(reg, s, say=quiet)
            row = next(r for r in check.registry(reg) if r["address"][2:] == unver[0])
            expect(row["status"] == "unverified" and "not sampled" in row["evidence"],
                   "UNSAMPLED keeps the status and notes it")
            rc, s = go({tier2[0]: "notfound"}, "unsampled2", only=["0x" + tier2[0]])
            expect(rc == 1, f"unsampled row with a tier-2 status -> exit {rc}, want 1")
            rc, s = go({unver[0]: "notfound_free"}, "unsampled3", only=["0x" + unver[0]])
            expect(rc == 1 and s["functions"][0]["verdict"] == "NOT-RUN",
                   f"0 functions without a holder on an unverified row -> exit {rc}, want 1 (NOT-RUN)")
        else:
            expect(False, "self-test registry has no unverified or no tier-2 override")

        # 4. broken setups and steps
        try:
            if has_verify(fake, dict(os.environ, FAKE_NO_VERIFY="1")):
                expect(False, "a build without the verify feature was not noticed")
            else:
                expect(True, "")
        except Setup as e:
            expect(False, f"probe failed: {e}")
        rc, s = go({}, "nolib", extra_env={"FAKE_NO_LIBRARY": "1"})
        expect(rc == 1 and not s["functions"], f"a build that wrote no library -> exit {rc}")
        try:
            go({}, "badonly", only=["0x00100000"])
            expect(False, "--only with a non-override address accepted")
        except Setup:
            expect(True, "")
        expect(not under(os.path.join(td, "x", "..", ".."), os.path.join(td, "x")), "path guard")
    return errs, f"verify pipeline self-test: {n - len(errs)}/{n} checks passed (fake 3dsrecomp)"


# ------------------------------------------------------------------ main
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom")
    ap.add_argument("--recomp", help="3dsrecomp built with --features verify")
    ap.add_argument("--out", default=OUT, help="output folder (must be under build/)")
    ap.add_argument("--only", default="", help="comma-separated override addresses")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--no-shadow", action="store_true", help="only the readable pass")
    ap.add_argument("--update-status", action="store_true")
    ap.add_argument("--check-setup", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        errs, line = selftest()
        for e in errs:
            print(e)
        print(line)
        return 1 if errs else 0
    if not under(a.out, os.path.join(ROOT, "build")):
        print(f"readable-verify: --out must be under build/ (got {a.out})")
        return 2
    try:
        recomp = find_recomp(a.recomp)
        rom = find_rom(a.rom)
        env, cc = tool_env()
        if not has_verify(recomp, env):
            raise Setup(f"{check.rel(recomp)} was built without the verify feature "
                        "(python tools/engine/engine.py build 3dsrecomp-verify)")
        print(f"3dsrecomp: {check.rel(recomp)}\nROM: {rom}\nC compiler: {cc}")
        if a.check_setup:
            print("readable-verify: setup OK")
            return 0
        only = [x.strip() for x in a.only.split(",") if x.strip()]
        rc, summary = pipeline(rom, recomp, os.path.abspath(a.out), only=only, skip_build=a.skip_build,
                               shadow=not a.no_shadow, env=env)
    except Setup as e:
        print(f"readable-verify: SETUP MISSING: {e}")
        return 3
    if a.update_status and summary.get("functions"):
        n = update_registry(check.REGISTRY, summary)
        print(f"registry: {n} row(s) updated in config/readable/functions.csv")
    print("note: one made-up state per function and cold one-time caches: a smoke test, not a proof")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
