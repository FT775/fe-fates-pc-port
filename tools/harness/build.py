#!/usr/bin/env python3
"""Build the tier-4 capture library (docs/HARNESS.md 3.3). Standard library only.

    python tools/harness/build.py                 check targets.csv, stage src/readable (capture.c
                                                  included) + the probe stubs into
                                                  build/harness/overrides/, then
                                                  3dsrecomp build <rom> build/harness/lib --overrides ...
    python tools/harness/build.py --stage-only    everything but the 3dsrecomp run
    python tools/harness/build.py --check-setup   say what was found (3dsrecomp, ROM, C compiler)
    python tools/harness/build.py --check-fresh   is build/harness/lib's library built from today's
                                                  sources? (stages again into build/harness/fresh_check
                                                  and compares with lib/harness_build.json; exit 0
                                                  fresh, 1 stale or no manifest). An in-game capture
                                                  run must pass it first (HARNESS.md 3.3).
    python tools/harness/build.py --selftest      the pipeline against a fake 3dsrecomp (no ROM); stages only
                                                  git-tracked src/readable files (another area's untracked
                                                  work in progress, with or without registry rows, is left out)
    python tools/harness/build.py --swap          build into build/harness/next, then swap the DLL and manifest
                                                  into --out's lib/ (the old DLL renamed aside: works while a
                                                  look-ahead's boot.exe holds it open; round 8 lost 357 s)
    python tools/harness/build.py --boot          Zakuro's windowless runner for headless.py:
                                                  engine/target/zakuro-test/release/examples/boot.exe
                                                  (cargo, pinned toolchain, Zakuro at its pin + patches)
    python tools/harness/build.py --server        the persistent server mode of that runner (owner OK "E",
                                                  docs/harness/SERVER.md): tools/harness/patches/zakuro-server
                                                  -> engine/zakuro-server -> engine/target/zakuro-server/release/
                                                  boot-server.exe, below-normal priority; never touches
                                                  engine/target/zakuro-test (boot.exe) or the Zakuro tree
    python tools/harness/build.py --server --stage-to DIR
                                                  the same build in its own target folder
                                                  (engine/target/zakuro-server-stage), the exe and its
                                                  server_build.json copied to DIR; the installed
                                                  engine/target/zakuro-server is not touched (round 68,
                                                  tools/release/install.py installs it)

Options: --rom (else FE_ROM, else "rom" in play/config.json, else the .cci in roms/), --recomp (else FE_3DSRECOMP, else
engine/target/3dsrecomp/release/3dsrecomp.exe, the build that made the played program; falls back
to the 3dsrecomp-verify build; an --recomp or FE_3DSRECOMP that names no file is an error, never a
silent fallback). 3dsrecomp is run as built, unmodified, exactly as
tools/readable/verify.py runs it: ALWAYS with an output folder (without one it would install the
library into %APPDATA%\\3dsrecomp, where Zakuro runs it for the owner's game) and with MSYS2's gcc
first on PATH.

Default mode baked into the staged files: original. The library is a harness tool, never the
shipped game; with FE_READABLE unset it behaves exactly like the game's own code. Capture runs set
FE_READABLE=capture, replay.exe runs it with FE_READABLE=original.

Writes only under build/harness/ (gitignored): overrides/ (staged files), probe_src/, lib/ (the
generated C, objects, recomp.h and <title id>.dll), lib/harness_build.json (what was built
from what: hashes of targets.csv, the staged files and the 3dsrecomp exe), build.log.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))

import check as rcheck  # noqa: E402
import gen_stubs  # noqa: E402  (same folder)
import stage  # noqa: E402
import verify  # noqa: E402  (find_rom, tool_env, run_logged, recomp_argv, under, Setup)

EXE = ".exe" if os.name == "nt" else ""
OUT = os.path.join(ROOT, "build", "harness")
RECOMP_PLAIN = os.path.join(ROOT, "engine", "target", "3dsrecomp", "release", "3dsrecomp" + EXE)
RECOMP_VERIFY = os.path.join(ROOT, "engine", "target", "3dsrecomp-verify", "release", "3dsrecomp" + EXE)
LIBRARY = verify.LIBRARY
MODE = "original"
MANIFEST = "harness_build.json"


def find_recomp(given: str | None, env: dict | None = None) -> str:
    env = os.environ if env is None else env
    for p, what in ((given, "--recomp"), (env.get("FE_3DSRECOMP"), "FE_3DSRECOMP")):
        if p:  # named explicitly: that file or nothing
            if os.path.isfile(p):
                return os.path.abspath(p)
            raise verify.Setup(f"{what} names no file: {p}")
    for p in (RECOMP_PLAIN, RECOMP_VERIFY):
        if os.path.isfile(p):
            return os.path.abspath(p)
    raise verify.Setup("no 3dsrecomp (python tools/engine/engine.py build 3dsrecomp, or --recomp)")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def untracked_sources() -> list[str]:
    """src/readable .c files git does not track (another area's work in progress). [] when git is missing."""
    try:
        r = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", "src/readable"],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode:
        return []
    return sorted(os.path.normcase(os.path.abspath(os.path.join(ROOT, p)))
                  for p in r.stdout.splitlines() if p.endswith(".c"))


def file_markers(path: str) -> list[str]:
    return [lit for lit, _e, _l in rcheck.markers(rcheck.strip_code(open(path, encoding="utf-8").read()))]


def stage_all(out_dir: str, say=print, skip: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Stage the readable sources and the probe stubs into out_dir/overrides. Returns (staged, probes).
    skip: source files left out (the self-test's untracked files); their override addresses leave the marker gate."""
    skip_set = {os.path.normcase(os.path.abspath(p)) for p in (skip or [])}
    skipped_addr = {a for p in skip_set if os.path.isfile(p) for a in file_markers(p)}
    real_sources = stage.sources
    if skip_set:
        stage.sources = lambda: [p for p in real_sources() if os.path.normcase(os.path.abspath(p)) not in skip_set]
    try:
        return _stage_all(out_dir, say, skipped_addr)
    finally:
        stage.sources = real_sources


def _stage_all(out_dir: str, say, skipped_addr: set) -> tuple[list[str], list[str]]:
    overrides = os.path.join(out_dir, "overrides")
    assert verify.under(overrides, os.path.join(ROOT, "build"))
    rc, rows = gen_stubs.check_targets(gen_stubs.guard_callers(), say=say)
    if rc:
        raise verify.Setup("config/harness/targets.csv has problems (tools/harness/gen_stubs.py --check)")
    staged = stage.stage(MODE, overrides)
    probes = gen_stubs.generate(rows, overrides, os.path.join(out_dir, "probe_src"))
    names = {os.path.basename(p) for p in staged}
    if "core__capture.c" not in names or "core__runtime.c" not in names:
        raise verify.Setup(f"staging lost core/capture.c or core/runtime.c ({len(staged)} file(s))")
    want = sorted(r["address"] for r in rows if r["kind"] in ("override", "probe")  # writer rows: never a marker
                  and r["address"] not in skipped_addr)
    got = sorted(lit for p in staged + probes for lit in file_markers(p))
    if want != got:
        raise verify.Setup(f"staged markers ({len(got)}) differ from targets.csv ({len(want)}): "
                           f"{sorted(set(want) ^ set(got))[:6]}")
    say(f"staged {len(staged)} readable file(s) (default mode {MODE}) and {len(probes)} probe file(s) "
        f"({sum(r['kind'] == 'probe' for r in rows)} probe(s)) into {rcheck.rel(overrides)}; "
        f"{len(got)} override marker(s), as targets.csv lists")
    return staged, probes


def freshness(out_dir: str = OUT, say=print) -> tuple[bool, str]:
    """Is out_dir/lib's library the one built from today's targets.csv and sources? Stages again into
    build/harness/fresh_check and compares the hashes with lib/harness_build.json. No manifest (never
    built, or the last build failed) counts as stale."""
    lib_dir = os.path.join(os.path.abspath(out_dir), "lib")
    man_path, library = os.path.join(lib_dir, MANIFEST), os.path.join(lib_dir, LIBRARY)
    if not os.path.isfile(library):
        return False, f"no {rcheck.rel(library)} (python tools/harness/build.py)"
    if not os.path.isfile(man_path):
        return False, f"no {rcheck.rel(man_path)}: the last build failed or predates the manifest; rebuild"
    try:
        with open(man_path, encoding="utf-8") as fh:
            m = json.load(fh)
    except (OSError, ValueError) as e:
        return False, f"unreadable {rcheck.rel(man_path)}: {e}"
    if m.get("library_sha256") != sha256(library):
        return False, f"{LIBRARY} is not the library the manifest describes; rebuild"
    if m.get("mode") != MODE:
        return False, f"built in default mode {m.get('mode')!r}, want {MODE!r}; rebuild"
    if m.get("targets_sha256") != sha256(gen_stubs.TARGETS):
        return False, "config/harness/targets.csv changed since the build; rebuild"
    # one scratch folder per process: two h4a runs started together raced on a shared fresh_check/
    # (one deleted the staged files while the other hashed them; FileNotFoundError, round 3)
    scratch = os.path.join(ROOT, "build", "harness", "fresh_check", f"p{os.getpid()}")
    try:
        staged, probes = stage_all(scratch, say=lambda *_a, **_k: None)
        now = {os.path.basename(p): sha256(p) for p in staged + probes}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    was = m.get("staged") or {}
    if now != was:
        diff = sorted(k for k in set(now) | set(was) if now.get(k) != was.get(k))
        return False, f"{len(diff)} staged file(s) changed since the build ({', '.join(diff[:4])}); rebuild"
    return True, f"capture library is fresh ({len(now)} staged file(s), built {m.get('date')})"


def pipeline(rom: str, recomp: str, out_dir: str, env: dict, stage_only: bool = False, say=print) -> int:
    out_dir = os.path.abspath(out_dir)
    if not verify.under(out_dir, os.path.join(ROOT, "build")) or ".." in rcheck.rel(out_dir).split("/"):
        raise verify.Setup(f"output folder must be under build/ (got {out_dir})")
    staged, probes = stage_all(out_dir, say)
    if stage_only:
        return 0
    lib_dir = os.path.join(out_dir, "lib")
    overrides = os.path.join(out_dir, "overrides")
    library = os.path.join(lib_dir, LIBRARY)
    assert verify.under(lib_dir, os.path.join(ROOT, "build"))  # a folder, never %APPDATA%\3dsrecomp
    old = os.path.join(lib_dir, MANIFEST)
    if os.path.isfile(old):
        os.remove(old)  # a failed build must not leave the last good manifest beside new files
    manifest = {
        "tool": "tools/harness/build.py", "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "recomp": recomp, "recomp_sha256": sha256(recomp) if os.path.isfile(recomp) else None,
        "rom": rom, "rom_size": os.path.getsize(rom), "mode": MODE,
        "targets_sha256": sha256(gen_stubs.TARGETS),
        "staged": {os.path.basename(p): sha256(p) for p in staged + probes},
        "cc": verify.tool_env()[1] if not env.get("CC") else env["CC"],
    }
    log_path = os.path.join(out_dir, "build.log")
    with open(log_path, "a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n==== {manifest['date']} tools/harness/build.py\n")
        say(f"building the capture library into {rcheck.rel(lib_dir)} (the whole game) ...")
        rc, took = verify.run_logged(verify.recomp_argv(recomp, "build", rom, lib_dir, "--overrides", overrides),
                                     env, log, verify.BUILD_TIMEOUT)
    manifest.update(exit=rc, seconds=round(took, 1))
    if rc != 0 or not os.path.isfile(library):
        say(f"harness-build: FAILED (exit {rc} after {took:.0f}s; log {rcheck.rel(log_path)})")
        return 1
    manifest["library_size"] = os.path.getsize(library)
    manifest["library_sha256"] = sha256(library)
    with open(os.path.join(lib_dir, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
        fh.write("\n")
    say(f"harness-build: OK ({rcheck.rel(library)}, {manifest['library_size']:,} bytes, {took:.0f}s)")
    return 0


NEXT = os.path.join(ROOT, "build", "harness", "next")


def swap_library(src_lib: str, dst_lib: str, say=print) -> str:
    """Put src_lib's DLL and manifest into dst_lib while a running boot.exe may hold dst_lib's DLL open. Windows lets a
    loaded DLL be renamed but not overwritten or deleted, so: the manifest goes first (a stop half-way leaves STALE,
    never a wrong FRESH), the old DLL is renamed aside (<dll>.old-<time>), the new one is copied to a .tmp and renamed
    in, the manifest last. Old copies no longer held are deleted; held ones stay for a later swap. Returns the aside."""
    for d in (src_lib, dst_lib):
        if not verify.under(os.path.abspath(d), os.path.join(ROOT, "build")):
            raise verify.Setup(f"swap: {d} is not under build/")
    new_dll, new_man = os.path.join(src_lib, LIBRARY), os.path.join(src_lib, MANIFEST)
    if not (os.path.isfile(new_dll) and os.path.isfile(new_man)):
        raise verify.Setup(f"swap: {rcheck.rel(src_lib)} has no built library and manifest")
    with open(new_man, encoding="utf-8") as fh:
        if json.load(fh).get("library_sha256") != sha256(new_dll):
            raise verify.Setup("swap: the new manifest does not describe the new library")
    os.makedirs(dst_lib, exist_ok=True)
    dll, man = os.path.join(dst_lib, LIBRARY), os.path.join(dst_lib, MANIFEST)
    if os.path.isfile(man):
        os.remove(man)
    aside = ""
    if os.path.isfile(dll):
        aside = f"{dll}.old-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
        os.replace(dll, aside)
    shutil.copy2(new_dll, dll + ".tmp")
    os.replace(dll + ".tmp", dll)
    shutil.copy2(new_man, man + ".tmp")
    os.replace(man + ".tmp", man)
    kept = []
    for f in sorted(os.listdir(dst_lib)):
        if f.startswith(LIBRARY + ".old-"):
            try:
                os.remove(os.path.join(dst_lib, f))
            except OSError:
                kept.append(f)  # still loaded by a running boot.exe
    say(f"harness-build: swapped {rcheck.rel(dll)} from {rcheck.rel(src_lib)}"
        + (f"; still held open, kept aside: {', '.join(kept)}" if kept else ""))
    return aside


# ------------------------------------------------------------------ self-test
FAKE = r'''
import os, sys
a = sys.argv[1:]
if len(a) != 5 or a[0] != "build" or a[3] != "--overrides":
    print("no folder given: this would install into %APPDATA%"); sys.exit(9)
files = sorted(f for f in os.listdir(a[4]) if f.endswith(".c"))
if "core__capture.c" not in files or any("#define FE_DEFAULT_MODE FE_MODE_ORIGINAL\n"
                                         not in open(os.path.join(a[4], f), encoding="utf-8", errors="replace").read()
                                         for f in files if not f.startswith("harness__")):
    print("overrides not staged in original mode with capture.c"); sys.exit(8)
os.makedirs(a[2], exist_ok=True)
if os.environ.get("FAKE_FAIL"):
    sys.exit(1)
open(os.path.join(a[2], "LIBNAME"), "wb").write(b"MZ" + str(len(files)).encode())
print(f"wrote 1 file, {len(files)} overrides"); sys.exit(0)
'''.replace("LIBNAME", LIBRARY)


def selftest(skip: list[str] | None = None) -> tuple[list[str], str]:
    real_stage_all = globals()["stage_all"]
    if skip:  # every stage_all of the self-test leaves the untracked files out
        globals()["stage_all"] = lambda out_dir, say=print, skip=skip: real_stage_all(out_dir, say, skip)
    try:
        return _selftest()
    finally:
        globals()["stage_all"] = real_stage_all


def _selftest() -> tuple[list[str], str]:
    import tempfile
    global MODE
    errs: list[str] = []
    n = 0
    quiet = lambda *_a, **_k: None  # noqa: E731

    def expect(cond: bool, what: str):
        nonlocal n
        n += 1
        if not cond:
            errs.append(f"build self-test: {what}")

    scratch = os.path.join(ROOT, "build", "harness", "selftest")
    os.makedirs(scratch, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="build_py_") as td:
        fake = os.path.join(td, "fake_3dsrecomp.py")
        open(fake, "w", encoding="utf-8").write(FAKE)
        rom = os.path.join(td, "game.cci")
        open(rom, "wb").close()
        env = dict(os.environ)
        rc = pipeline(rom, fake, os.path.join(td, "out"), env, say=quiet)
        lib = os.path.join(td, "out", "lib", LIBRARY)
        expect(rc == 0 and os.path.isfile(lib), f"fake build exit {rc}")
        man = os.path.join(td, "out", "lib", MANIFEST)
        m = json.load(open(man, encoding="utf-8")) if os.path.isfile(man) else {}
        expect(m.get("mode") == MODE and "core__capture.c" in m.get("staged", {}) and m.get("exit") == 0,
               "manifest lacks mode, capture.c or exit")
        expect(m.get("targets_sha256") == sha256(gen_stubs.TARGETS), "manifest targets hash")
        expect(MODE == "original", f"default mode {MODE!r}: the capture library must default to original")
        ok, why = freshness(os.path.join(td, "out"), say=quiet)
        expect(ok, f"a just-built library is called stale: {why}")
        if m.get("staged") and os.path.isfile(lib):  # else the checks above have failed already
            good = json.dumps(m)
            m2 = json.loads(good)
            m2["staged"][sorted(m2["staged"])[0]] = "0" * 64
            with open(man, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(m2))
            expect(not freshness(os.path.join(td, "out"), say=quiet)[0], "a changed staged file went unnoticed")
            with open(man, "w", encoding="utf-8") as fh:
                fh.write(good)
            with open(lib, "ab") as fh:
                fh.write(b"x")
        expect(not freshness(os.path.join(td, "out"), say=quiet)[0], "a library the manifest does not describe")
        # the fake refuses files staged in another default mode, so a wrong MODE fails the build
        keep_mode, MODE = MODE, "readable"
        try:
            rc = pipeline(rom, fake, os.path.join(td, "wrong_mode"), env, say=quiet)
        finally:
            MODE = keep_mode
        expect(rc == 1, "files staged in readable mode were built")
        # the marker gate: staged override markers must be exactly targets.csv's addresses
        real_check = gen_stubs.check_targets
        for what, change in (("an extra override row", lambda rows: rows + [dict(rows[0], address="0x00100010")]),
                             ("a missing override row", lambda rows: rows[1:])):
            gen_stubs.check_targets = lambda g, say=print, _c=change: (0, _c(real_check(g, say)[1]))
            try:
                stage_all(os.path.join(td, "gate"), say=quiet)
                expect(False, f"{what} passed the marker gate")
            except verify.Setup:
                expect(True, "")
            finally:
                gen_stubs.check_targets = real_check
        try:
            find_recomp(None, {"FE_3DSRECOMP": os.path.join(td, "no_such.exe")})
            expect(False, "a missing FE_3DSRECOMP fell back to another 3dsrecomp")
        except verify.Setup:
            expect(True, "")
        rc = pipeline(rom, fake, os.path.join(td, "out"), dict(env, FAKE_FAIL="1"), say=quiet)
        expect(rc == 1 and not os.path.isfile(man), "a failed build kept the old manifest or exited 0")
        expect(not freshness(os.path.join(td, "out"), say=quiet)[0], "a library left by a failed build is fresh")
        try:
            pipeline(rom, fake, os.path.join(ROOT, "docs", "x"), env, say=quiet)
            expect(False, "an output folder outside build/ was accepted")
        except verify.Setup:
            expect(not os.path.exists(os.path.join(ROOT, "docs", "x")), "refused folder was created")
        rc = pipeline(rom, fake, os.path.join(td, "stage"), env, stage_only=True, say=quiet)
        expect(rc == 0 and not os.path.isdir(os.path.join(td, "stage", "lib")), "--stage-only ran 3dsrecomp")
        # round 9: the marker gate compares only override/probe rows (a writer row never has a marker)
        gen_stubs.check_targets = lambda g, say=print: (0, real_check(g, say)[1] + [
            dict(real_check(g, say)[1][0], address="0x00100020", kind="writer")])
        try:
            stage_all(os.path.join(td, "gate"), say=quiet)
            expect(True, "")
        except verify.Setup as e:
            expect(False, f"a writer row was compared with the staged markers: {e}")
        finally:
            gen_stubs.check_targets = real_check
        # round 9: a skipped source's addresses leave the gate; its file is not staged
        srcs = stage.sources()
        some = next((p for p in srcs if file_markers(p)), None)
        if some:
            try:
                st, _pr = stage_all(os.path.join(td, "skip"), say=quiet, skip=[some])
                expect(stage.staged_name(some) not in {os.path.basename(p) for p in st}, "a skipped source was staged")
            except verify.Setup as e:
                expect(False, f"a skipped source's markers stayed in the gate: {e}")
            expect(stage.sources() == srcs, "stage.sources was not restored after a skip")
        # round 9: swap while the old DLL is loaded (Windows: a loaded DLL can be renamed, not overwritten)
        swap_dst = os.path.join(td, "swap", "lib")
        os.makedirs(swap_dst)
        held = None
        py3 = os.path.join(sys.base_prefix, "python3.dll")
        if os.name == "nt" and os.path.isfile(py3):
            import ctypes
            shutil.copy2(py3, os.path.join(swap_dst, LIBRARY))
            held = ctypes.WinDLL(os.path.join(swap_dst, LIBRARY))
        else:
            open(os.path.join(swap_dst, LIBRARY), "wb").write(b"old")
        try:
            pipeline(rom, fake, os.path.join(td, "next"), env, say=quiet)
            aside = swap_library(os.path.join(td, "next", "lib"), swap_dst, say=quiet)
            expect(sha256(os.path.join(swap_dst, LIBRARY)) == sha256(os.path.join(td, "next", "lib", LIBRARY)),
                   "swap: the new DLL is not in place")
            expect(freshness(os.path.join(td, "swap"), say=quiet)[0], "swap: the swapped library is not FRESH")
            expect(held is None or os.path.isfile(aside), "swap: the held old DLL was not kept aside")
        except (OSError, verify.Setup) as e:
            expect(False, f"swap failed with the old DLL held open: {e!r}")
        finally:
            if held is not None:
                ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(held._handle))
        os.remove(os.path.join(td, "next", "lib", MANIFEST))
        try:
            swap_library(os.path.join(td, "next", "lib"), swap_dst, say=quiet)
            expect(False, "swap: a build with no manifest was swapped in")
        except verify.Setup:
            expect(os.path.isfile(os.path.join(swap_dst, MANIFEST)), "swap: a refused swap removed the good manifest")
    return errs, f"harness build self-test: {n - len(errs)}/{n} checks passed (fake 3dsrecomp)"


BOOT_TARGET = os.path.join(ROOT, "engine", "target", "zakuro-test")
BOOT_EXE = os.path.join(BOOT_TARGET, "release", "examples", "boot" + EXE)


def boot_command() -> tuple[list[str], dict, str]:
    """cargo for Zakuro's windowless runner (crates/zakuro-core/examples/boot.rs), the same conventions as
    tools/engine/engine.py build: pinned toolchain (config/upstream.json), --locked, the C tool variables
    removed. Only the example is built, into engine/target/zakuro-test (gitignored), from the patched pin."""
    with open(os.path.join(ROOT, "config", "upstream.json"), encoding="utf-8") as fh:
        toolchain = json.load(fh)["toolchain"]
    env = {k: v for k, v in os.environ.items() if k not in ("CC", "CXX", "AR", "CFLAGS", "CXXFLAGS", "ARFLAGS")}
    env["RUSTUP_TOOLCHAIN"] = toolchain
    cmd = ["cargo", "build", "--release", "--locked", "-p", "zakuro-core", "--example", "boot",
           "--target-dir", BOOT_TARGET]
    return cmd, env, os.path.join(ROOT, "engine", "zakuro")


def build_boot() -> int:
    cmd, env, cwd = boot_command()
    status = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "engine", "engine.py"), "status"],
                            capture_output=True, text=True)
    if status.returncode != 0:  # Zakuro must be exactly the pin + patches/zakuro (engine.py apply)
        print(status.stdout + status.stderr)
        print("harness-build: engine sources are off their pins: python tools/engine/engine.py apply")
        return 3
    started = time.time()
    rc = subprocess.run(cmd, cwd=cwd, env=env).returncode
    if rc or not os.path.isfile(BOOT_EXE):
        print(f"harness-build: cargo failed (exit {rc})")
        return 1
    print(f"harness-build: {rcheck.rel(BOOT_EXE)} ({os.path.getsize(BOOT_EXE):,} bytes, sha256 {sha256(BOOT_EXE)}, "
          f"{time.time() - started:.0f}s)")
    return 0



# ------------------------------------------------------------------ the server mode (owner OK "E", 2026-11-13)
SERVER_SRC = os.path.join(HERE, "patches", "zakuro-server")  # tracked: Cargo.toml + src/main.rs
SERVER_CRATE = os.path.join(ROOT, "engine", "zakuro-server")  # gitignored copy beside the pin (never inside it)
SERVER_TARGET = os.path.join(ROOT, "engine", "target", "zakuro-server")
SERVER_EXE = os.path.join(SERVER_TARGET, "release", "boot-server" + EXE)
SERVER_FILES = ("Cargo.toml", os.path.join("src", "main.rs"))
BELOW_NORMAL = 0x00004000


SERVER_STAGE_TARGET = os.path.join(ROOT, "engine", "target", "zakuro-server-stage")


def zakuro_facts() -> dict:
    """what boot-server links (engine/zakuro by path): its HEAD and our patch list, so a Zakuro patch change can be
    seen to make boot-server stale (round 68; older server_build.json files have neither key and still read)"""
    zakuro = os.path.join(ROOT, "engine", "zakuro")
    try:
        head = subprocess.run(["git", "-C", zakuro, "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=60).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        head = None
    pdir = os.path.join(ROOT, "patches", "zakuro")
    patches = sorted(f for f in os.listdir(pdir) if f[:4].isdigit() and f.endswith(".patch")) if os.path.isdir(pdir) else []
    return {"zakuro_head": head, "zakuro_patches": patches}


def server_command(jobs: int | None = None, target: str | None = None) -> tuple[list[str], dict, str]:
    """cargo for the server crate: the pinned toolchain, --offline (only crates the Zakuro build already fetched), its
    own target folder. Its Cargo.lock starts as a copy of engine/zakuro's, so every shared crate keeps its version."""
    with open(os.path.join(ROOT, "config", "upstream.json"), encoding="utf-8") as fh:
        toolchain = json.load(fh)["toolchain"]
    env = {k: v for k, v in os.environ.items() if k not in ("CC", "CXX", "AR", "CFLAGS", "CXXFLAGS", "ARFLAGS")}
    env["RUSTUP_TOOLCHAIN"] = toolchain
    cmd = ["cargo", "build", "--release", "--offline", "--target-dir", target or SERVER_TARGET]
    if jobs:
        cmd += ["-j", str(jobs)]
    return cmd, env, SERVER_CRATE


def stage_server(say=print) -> list[str]:
    """Copies the tracked crate into engine/zakuro-server (each file written whole, then renamed); the lock file is
    engine/zakuro's, copied once. Returns the files that changed."""
    if os.path.abspath(SERVER_TARGET) == os.path.abspath(BOOT_TARGET) or os.path.abspath(SERVER_EXE) == os.path.abspath(BOOT_EXE):
        raise verify.Setup("the server build would write over boot.exe's target folder")
    zakuro = os.path.join(ROOT, "engine", "zakuro")
    if os.path.commonpath([os.path.abspath(SERVER_CRATE), os.path.abspath(zakuro)]) == os.path.abspath(zakuro):
        raise verify.Setup("the server crate must not be inside the Zakuro tree")
    changed = []
    for name in SERVER_FILES:
        src, dst = os.path.join(SERVER_SRC, name), os.path.join(SERVER_CRATE, name)
        with open(src, "rb") as fh:
            data = fh.read()
        if os.path.isfile(dst) and open(dst, "rb").read() == data:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst + ".tmp", "wb") as fh:
            fh.write(data)
        os.replace(dst + ".tmp", dst)
        changed.append(name)
    lock = os.path.join(SERVER_CRATE, "Cargo.lock")
    if not os.path.isfile(lock):
        shutil.copy2(os.path.join(zakuro, "Cargo.lock"), lock + ".tmp")
        os.replace(lock + ".tmp", lock)
        changed.append("Cargo.lock (from engine/zakuro)")
    return changed


def build_server(jobs: int | None = None, stage_to: str | None = None) -> int:
    status = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "engine", "engine.py"), "status"],
                            capture_output=True, text=True)
    if status.returncode != 0:  # the same rule as --boot: Zakuro exactly at its pin + patches/zakuro
        print(status.stdout + status.stderr)
        print("harness-build: engine sources are off their pins: python tools/engine/engine.py apply")
        return 3
    try:
        changed = stage_server()
    except verify.Setup as e:
        print(f"harness-build: {e}")
        return 3
    print(f"harness-build: server crate {rcheck.rel(SERVER_CRATE)} ({', '.join(changed) or 'unchanged'})")
    if stage_to:
        stage_to = os.path.abspath(stage_to)
        if not verify.under(stage_to, os.path.join(ROOT, "build")):
            print(f"harness-build: --stage-to {stage_to} is not under build/")
            return 3
    target = SERVER_STAGE_TARGET if stage_to else SERVER_TARGET
    exe = os.path.join(target, "release", "boot-server" + EXE)
    cmd, env, cwd = server_command(jobs, target)
    started = time.time()
    flags = BELOW_NORMAL if os.name == "nt" else 0  # cargo and every rustc it starts inherit the class
    rc = subprocess.run(cmd, cwd=cwd, env=env, creationflags=flags).returncode
    if rc or not os.path.isfile(exe):
        print(f"harness-build: cargo failed (exit {rc})")
        return 1
    record = {"exe": rcheck.rel(SERVER_EXE), "bytes": os.path.getsize(exe), "sha256": sha256(exe),
              "seconds": round(time.time() - started), "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "source_sha256": {n.replace(os.sep, "/"): sha256(os.path.join(SERVER_SRC, n)) for n in SERVER_FILES},
              "command": " ".join(cmd), **zakuro_facts()}
    out_dir = SERVER_TARGET
    if stage_to:  # the record names where the exe will sit once installed; the copy goes to stage_to
        os.makedirs(stage_to, exist_ok=True)
        record["staged_in"] = rcheck.rel(os.path.join(stage_to, "boot-server" + EXE))
        shutil.copy2(exe, os.path.join(stage_to, "boot-server" + EXE + ".tmp"))
        os.replace(os.path.join(stage_to, "boot-server" + EXE + ".tmp"), os.path.join(stage_to, "boot-server" + EXE))
        out_dir = stage_to
    with open(os.path.join(out_dir, "server_build.json.tmp"), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    os.replace(os.path.join(out_dir, "server_build.json.tmp"), os.path.join(out_dir, "server_build.json"))
    shown = record.get("staged_in") or record["exe"]
    print(f"harness-build: {shown} ({record['bytes']:,} bytes, sha256 {record['sha256']}, {record['seconds']}s)"
          + (" STAGED ONLY, nothing installed" if stage_to else ""))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom")
    ap.add_argument("--recomp")
    ap.add_argument("--out", default=OUT, help="output folder (under build/)")
    ap.add_argument("--stage-only", action="store_true")
    ap.add_argument("--check-setup", action="store_true")
    ap.add_argument("--check-fresh", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--swap", action="store_true", help="build into build/harness/next, then swap the DLL into "
                    "--out's lib/ (safe while a look-ahead holds the old DLL open)")
    ap.add_argument("--boot", action="store_true", help="build Zakuro's windowless boot.exe (headless runs)")
    ap.add_argument("--server", action="store_true", help="build the server mode of the windowless boot "
                    "(engine/target/zakuro-server; docs/harness/SERVER.md)")
    ap.add_argument("--jobs", type=int, help="--server: cargo -j (default: cargo's)")
    ap.add_argument("--stage-to", help="--server: build in engine/target/zakuro-server-stage and copy the exe and its "
                    "server_build.json to this folder (under build/); the installed boot-server is not touched")
    a = ap.parse_args(argv)
    if a.stage_to and not a.server:
        print("harness-build: --stage-to goes with --server")
        return 2
    if a.server:
        return build_server(a.jobs, a.stage_to)
    if a.boot:
        return build_boot()
    if a.selftest:
        wip = untracked_sources()
        if wip:
            print(f"build self-test: leaving out {len(wip)} untracked src/readable file(s): "
                  + ", ".join(rcheck.rel(p) for p in wip[:4]))
        errs, line = selftest(skip=wip)
        for e in errs:
            print(e)
        print(line)
        return 1 if errs else 0
    try:
        if a.check_fresh:
            ok, why = freshness(a.out)
            print(f"harness-build: {'FRESH' if ok else 'STALE'}: {why}")
            return 0 if ok else 1
        if a.stage_only:
            return pipeline("", "", a.out, {}, stage_only=True)
        recomp = find_recomp(a.recomp)
        rom = verify.find_rom(a.rom)
        env, cc = verify.tool_env()
        print(f"3dsrecomp: {rcheck.rel(recomp)}\nROM: {rom}\nC compiler: {cc}")
        if shutil.which("ar", path=env.get("PATH")) is None and not env.get("AR"):
            print("note: no ar on PATH (3dsrecomp may need one)")
        if a.check_setup:
            print("harness-build: setup OK")
            return 0
        if a.swap:
            if os.path.abspath(a.out) == os.path.abspath(NEXT):
                raise verify.Setup("--swap: --out must not be build/harness/next")
            rc = pipeline(rom, recomp, NEXT, env)
            if rc == 0:
                swap_library(os.path.join(NEXT, "lib"), os.path.join(os.path.abspath(a.out), "lib"))
            return rc
        return pipeline(rom, recomp, a.out, env)
    except verify.Setup as e:
        print(f"harness-build: SETUP MISSING: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
