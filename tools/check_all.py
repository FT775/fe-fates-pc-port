#!/usr/bin/env python3
"""check-all: every gate of the Fire Emblem Fates port in one command (README.md, "Checks").

    python tools/check_all.py                 default set (fast + medium rows: 127 rows, about 18,500 s =
                                              5 h 10 of recorded row time one after another, 2026-11-23;
                                              those times were taken under --jobs lanes and run about
                                              1.5-2.2x a row alone, e.g. vein-diff 1,514 s recorded vs
                                              675 s alone; use --jobs auto)
    python tools/check_all.py --fast          fast rows only (50 rows, about 138 s recorded; no 2 GiB
                                              image, no M1 tests, no unit suites, no planted-bug passes)
    python tools/check_all.py --core          the release core (round 67): the fast rows plus
                                              engine-selftest and release-selftest (round 68), without the
                                              unit-suite duplicate rows (52 rows, about 159 s recorded + about
                                              50 s for release-selftest; smoke-selftest included)
    python tools/check_all.py --skip-unit-dupes   drop the 17 rows that only re-run unit modules of
                                              tests/ (UNIT_DUPES; plain `python -m unittest discover -s
                                              tests -t .` already runs them; on with --core)
    python tools/check_all.py --slow          also the slow rows (portrait test, full asset
                                              round-trip ~15 min, tools/rom/tests.py: three
                                              2 GiB images, every sheet file through the
                                              castle tool, the long stance, triangle, vein and
                                              formula comparisons, the real-run parallel smoke;
                                              the live round smoke set smoke-set, the Seal edition's
                                              seal-smoke; all 183 rows,
                                              about 25,500 s recorded)
    python tools/check_all.py --list          the rows, what each needs, and whether it is here; with a
                                              profile (--fast, --slow, --core, --only, --skip,
                                              --skip-unit-dupes) also whether that profile runs each
                                              row, its recorded seconds and their sum
    python tools/check_all.py --edition vanilla   no Seal of Flames edition rows (the 6 rows tagged
                                              edition "seal"); --edition seal runs only them; the
                                              default, all, runs both (round 83, F-070). In a folder
                                              without the Seal edition (no tests/seal, config/seal:
                                              the Vanilla+ zip) its test and smoke rows SKIP with a
                                              plain reason and a printed count (round 84, F-072)
    python tools/check_all.py --only a,b      just these rows (any cost)
    python tools/check_all.py --skip a,b      everything selected except these
    python tools/check_all.py --fail-on-skip  a selected row that SKIPs also fails the run (CI)
    python tools/check_all.py --slow --jobs auto   rows side by side (docs/CHECK_ALL.md)
    python tools/check_all.py --slow --cache       reuse PASSes of unchanged host tests (CACHED)

Integrate runs `--slow` ONCE (it already holds every fast and medium row); builders keep a fast
pass. Never a fast pass and then a slow pass: that repeats every fast row (SPEED_AGREED item 1).
Round 67 moved 8 rows from fast to medium (they held 613 of the old 746 recorded s of --fast): the
planted-bug readable diffs volume-diff, job-female-diff, job-record-diff, key-door-diff,
skill-record-diff, person-record-diff, plus parallel-tests and w12-options. The default and --slow
sets still run them; after an edit under src/readable or tools/readable run them by name (--only).
--core and --skip-unit-dupes never drop a test from the repository: the unit-suite rows they skip
are run by the unit suite itself (tools/release/run_tests.py or plain unittest discover).

--jobs N|auto runs rows on up to N lanes (auto: the owner's budget in
config/harness/resources.json, or FEF_CHECK_ALL_SLOTS, minus the robot's running boot.exe runs,
counted again while it runs; never below 1, so a 12-run robot session leaves one lane), longest
first by the last wall times (build/check_all_times.json, else build/check_all.json), at
below-normal priority. FEF_CHECK_ALL_SLOTS=N (a whole number > 0) replaces max_parallel_runs for
this shell, up or down: e.g. `FEF_CHECK_ALL_SLOTS=12 python tools/check_all.py --slow --jobs auto`
on a night with no long live runs. The "[check-all] lanes:" line names the budget's source; a
value that is not a whole number > 0 is ignored and named there; --jobs N is still capped by the
free slots. Rows that share output folders hold a lock and never overlap; in-process
checks and the robot smoke run run alone at the end. The table and the JSON are in row order and
read the same as a serial run. Without --jobs (or --jobs 1) the run is today's serial run.
--cache reuses a stored PASS of a row whose every declared input is unchanged (tools/testcache.py:
key = sha256 of the row, its scripts, sources, headers, ARM bytes, compiler and harness); a hit
says CACHED key=... . --no-cache runs every row and records the weekly clean run the cache needs.
Off by default until round 9.

Every selected row runs, in order, even after a failure. Each row reports
PASS, FAIL, SKIP (reason) or KNOWN (id), with its time; its output goes to
build/check_all/<row>.log, and the whole result to build/check_all.json. A row
that crashes, times out or is interrupted is FAIL with "INCOMPLETE" in its
note: it is never PASS. The exit status is 1 if any row FAILed (or SKIPped,
with --fail-on-skip), 2 on a usage error, else 0. When rows were skipped and
none failed the verdict reads "PASS (N skipped)": a skipped row is not a pass.

Each row declares what it needs:
    rom:code    extracted/code.bin + layout.json (tools/extract_rom.py)
    rom:parts   extracted/rom/manifest.json (tools/rom/extract.py)
    rom:romfs   extracted/romfs/ (tools/assets/romfs.py)
    toolchain   GNU ARM binutils + g++ from tools/config.local.json (tools/toolchain.py)
    armcc       an armcc profile with an existing path (compile.py); only rows whose
                build compiles a src_map row with an armcc profile need it
    git         git on PATH and the root is a git work tree
    host-cc     a host C compiler: FE_HOST_CC, MSYS2 gcc, or gcc/clang/cc on PATH (readable layer)
    rom:cci     the ROM image itself: FE_ROM, "rom" in play/config.json, or the .cci in roms/ (tools/paths.py)
    engine:3dsrecomp-verify
                3dsrecomp built with --features verify: FE_3DSRECOMP, or
                engine/target/3dsrecomp-verify/release/ (tools/engine/engine.py build)
    robot       the test robot's boot.exe (build.py --boot), its capture library
                (build/harness/lib/, parallel.py build) and the empty start save
                (build/harness/saves/new-game-empty.zip); real headless runs, at the owner's
                budget (config/harness/resources.json, through parallel.py)
    file:PATH   a file of the repository (e.g. config/naming/classes.csv, made by the M2
                naming tools; not made for Fates yet)
    after:ROW   ROW passed in this run (if ROW is selected); otherwise SKIP

Options: --root DIR (repository root; default: this file's parent's parent),
--json PATH, --log-dir DIR, --timeout-scale F, -v/--verbose (print each row's log),
--jobs N|auto, --priority idle|below_normal|normal, --times PATH, --cache, --no-cache,
--cache-dir DIR (default build/testcache/).

The first row is the matching gate. Rows are defined in ROWS below; known
failures (status KNOWN, never silently PASS) in KNOWN. Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable



def _game_code_sha1() -> str:
    """SHA-1 of the decompressed code.bin this port must rebuild (config/game.json)."""
    try:
        cfg = json.loads((Path(__file__).resolve().parent.parent / "config" / "game.json")
                         .read_text(encoding="utf-8"))
        return cfg["code_bin_sha1"]
    except (OSError, ValueError, KeyError):
        return "0" * 40


EXPECTED_CODE_SHA1 = _game_code_sha1()      # Fates: 038db5d79786914f645fbef08242a138703f8d70
EXE = ".exe" if os.name == "nt" else ""
BINUTILS = ("as", "ld", "objdump", "objcopy", "nm")
STATUSES = ("PASS", "FAIL", "SKIP", "KNOWN")

# Never tracked (D-003, STRATEGY.md R2): generated from the user's dump or local-only.
FORBIDDEN_DIRS = ("extracted/", "build/", "asm/", "data/", "baserom/", "expected/",
                  "tools/bin/", "romfs/", "exefs/", ".deps/")
FORBIDDEN_FILES = ("tools/config.local.json",)
# mods/<Name>/ holds spreadsheets made from the game's data: only these are tracked there.
MODS_TRACKED = ("mods/README.md", "mods/.gitkeep")
# Extensions of ROM images, Nintendo container/asset formats, binaries and media. A
# tracked file with one of these fails git hygiene unless listed in ALLOWED_TRACKED.
SUSPICIOUS_EXT = {
    ".bin", ".cci", ".3ds", ".cia", ".cxi", ".cfa", ".app", ".nds", ".sav",
    ".lz", ".lz11", ".lz13", ".blz", ".arc", ".darc", ".zar", ".gar", ".sarc",
    ".ctpk", ".cgfx", ".bcres", ".bch", ".bcmdl", ".bctex", ".bclim", ".bflim", ".bcfnt",
    ".bcstm", ".bcwav", ".bcsar", ".bcseq", ".bcwar", ".bcbnk", ".bcgrp", ".bfstm",
    ".cmb", ".moflex", ".shbin", ".bcsdr", ".bccam", ".msbt", ".msbp",
    ".elf", ".axf", ".o", ".obj", ".a", ".lib", ".exe", ".dll", ".so", ".dylib",
    ".zip", ".7z", ".rar", ".gz", ".xz", ".tar",
    ".png", ".bmp", ".tga", ".dds", ".ktx", ".wav", ".ogg", ".mp3", ".mp4",
}
ALLOWED_TRACKED: set[str] = set()   # exact repo paths exempt from the extension/binary checks

# Byte-leak scan of tracked files against extracted/code.bin: WINDOW-byte keys taken
# every STRIDE bytes, so any shared run of WINDOW + STRIDE - 1 bytes or more is found.
LEAK_WINDOW = 32
LEAK_STRIDE = 16
LEAK_MIN_DISTINCT = 8    # keys with fewer distinct byte values (padding, fills) are ignored
IDENT_BYTES = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$")
# Qualified C++ names (nn::pia::inet::NatTraverser::..., Allocator<...>): the game's own
# symbol map names every function (config/functions.csv, F-012), and code.bin holds the same
# names in library debug strings. A window of only these characters is a name, allowed.
NAME_BYTES = IDENT_BYTES | frozenset(b":<>~")
# RomFS file paths (GameData/Castle/DiningData.bin.lz) are file names, allowed by D-003;
# code.bin holds the same paths as load strings. "/", "." and "-" join name characters.
NAME_BYTES |= frozenset(b"/.-")
PRINTABLE = frozenset(range(0x20, 0x7F)) | {0x09, 0x0A, 0x0D}
# code.bin is loaded at CODE_BASE; .bss follows the image. A decoded window whose eight
# little-endian words are all addresses in [CODE_BASE, CODE_BASE + len(code.bin) +
# BSS_SLACK), zero, or small negative offsets (vtable offset-to-top) is a list of
# addresses (vtable slots, as in config/naming/vfuncs.csv): layout metadata, allowed (D-006).
CODE_BASE = 0x00100000
BSS_SLACK = 0x00100000

# Known failures: row id -> list of {"id", "match" (regex over the row's log), "note"}.
# A FAILing row whose log matches every listed entry's regex is KNOWN (named), not PASS.
# A row that passes while an entry is listed says so in its note ("not seen: fixed?").
KNOWN: dict[str, list[dict]] = {
    # round 10 (item batch, docs/ITEM.md 6; Grok review 2026-11-16 #2): verify tests 0 functions at
    # unit::Item::GetSellPrice, which ItemSellMenuItem::GetPrice falls straight into; NOT-RUN is not a pass.
    # Strict: exactly one problem, this NOT-RUN, and no MISMATCH anywhere in the summary line.
    "readable-verify": [
        {"id": "item-sell-price-not-run",
         "match": r"(?s)^\s+NOT-RUN\s+0x0053AE8C item_sell_price: .*"
                  r"^readable-verify: 2 problem\(s\) \((?:(?!MISMATCH)[^)\n])*\b2 NOT-RUN\b",
         "note": "item_sell_price (0x0053AE8C) never sampled by verify (falls in from its neighbour); "
                 "covered by item_diff only, not met in real play yet"},
        # round 22 (docs/ROD_TARGET.md): verify's sampler cannot name Rod::CanUseTarget (0 functions in both passes);
        # covered by rod_target_diff (42/42 planted bugs) and the live capture r22-cap-rod_target (119 records, 0 bad).
        # With the entry above: exactly these two NOT-RUN, 2 problems in all, and no MISMATCH anywhere.
        {"id": "rod-target-not-run",
         "match": r"(?s)^\s+NOT-RUN\s+0x0034AC30 rod_can_use_target: .*"
                  r"^readable-verify: 2 problem\(s\) \((?:(?!MISMATCH)[^)\n])*\b2 NOT-RUN\b",
         "note": "rod_can_use_target (0x0034AC30) never sampled by verify; covered by rod_target_diff and the "
                 "round 22 live capture"},
        # round 23: no entry needed, since GAVE-UP and UNSAMPLED are not problems for verify: unit_item_enhance_have
        # (0x0052FB98) gives GAVE-UP (verify's made-up state has its guard words cold) and the four volume readers
        # (0x003BCA4C, 0x003BC7C4, 0x003BB078, 0x003BB168) give UNSAMPLED (no real class table, so the virtual GetMax
        # runs into junk). The evidence is item_enhance_diff / volume_diff and the captures r23-cap-item_enhance,
        # r23-cap-volume. A NOT-RUN or MISMATCH for them still fails the row.
        # round 25: no entry needed either: job_female_is_female (0x00524AF4) gives GAVE-UP (cold cache in verify's
        # made-up memory; its shadow r0 matched); job_record_get (0x00341AA4) is a helper, not an override, so
        # verify does not sample it. Evidence: job_female_diff / job_record_diff and the capture r25-cap-job_female.
        # round 26: no entry needed: key_door_unit_can_open (0x00529E20) gives GAVE-UP (cold skill-number cache in
        # verify's made-up memory) and skill_record_by_name (0x001758C4) gives ABI-ONLY (0 MISMATCH). Evidence:
        # key_door_diff / skill_record_diff and the captures r26-cap-key_door, r26-cap-skill_record.
        # round 27: no entry needed: person_record_by_name (0x0044A6DC) gives ABI-ONLY (0 MISMATCH);
        # person_record_get (0x0044A6F8) is a helper, not an override, so verify does not sample it. Evidence:
        # person_record_diff and the capture r27-cap-person_record.
    ],
}


# --------------------------------------------------------------------------- rows
@dataclass
class Row:
    id: str
    title: str
    needs: tuple[str, ...] = ()
    cmd: list[str] | None = None            # argv; "{py}" = this Python, "{root}" = root
    func: Callable | None = None            # in-process check: func(ctx) -> (ok, note)
    cost: str = "fast"                      # fast | medium | slow
    timeout: float = 600.0
    require: tuple[str, ...] = ()           # FAIL unless some log line matches each
    reject: tuple[str, ...] = (r"^Traceback \(most recent call last\):",)
    note_rx: tuple[str, ...] = ()           # last match of each goes in the note
    info: bool = False                      # informational: result never fails on content
    dynamic_needs: Callable | None = None   # ctx -> extra needs (e.g. armcc)
    known: list[dict] = field(default_factory=list)
    env: dict = field(default_factory=dict)  # extra environment variables for cmd rows
    edition: str = "shared"                 # shared | seal (round 83, F-070: --edition vanilla skips seal rows)


@dataclass
class Ctx:
    root: Path
    log_dir: Path
    verbose: bool = False
    timeout_scale: float = 1.0
    results: dict = field(default_factory=dict)   # row id -> result dict (this run)
    selected: set = field(default_factory=set)
    py: str = sys.executable
    cache: object = None                          # tools/testcache.py Cache, when --cache/--no-cache
    cache_mode: str = ""                          # "use" (--cache) | "clean" (--no-cache)
    procs: dict | None = None                     # running row processes (--jobs), for Ctrl-C
    creationflags: int = 0                        # extra Popen flags (priority class) for rows


def _src_compilers(root: Path) -> set[str]:
    p = root / "config" / "src_map.csv"
    if not p.is_file():
        return set()
    with p.open(encoding="utf-8", newline="") as fh:
        return {r.get("compiler", "") for r in csv.DictReader(fh)
                if r.get("status") in ("matched", "nonmatching") and r.get("compiler")}


def _local_cfg(root: Path) -> dict:
    p = root / "tools" / "config.local.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except ValueError:
        return {}


def armcc_needs(ctx: Ctx) -> tuple[str, ...]:
    """'armcc' when a src_map row the build compiles uses an armcc-kind profile."""
    cfg = _local_cfg(ctx.root)
    entries = cfg.get("cxx") or []
    if isinstance(entries, dict):
        entries = [entries]
    kinds = {"armcc": "armcc", "gcc-standin": "gcc"}
    for e in entries:
        kind = e.get("kind", "gcc")
        name = e.get("profile") or {"gcc": "gcc-standin", "armcc": "armcc"}.get(kind, kind)
        kinds[name] = kind
    return ("armcc",) if any(kinds.get(c) == "armcc" for c in _src_compilers(ctx.root)) else ()


# same order as tools/readable/check.py CC_CANDIDATES
HOST_CC_CANDIDATES = (r"C:\msys64\ucrt64\bin\gcc.exe", "gcc", "clang", "cc")


def find_host_cc() -> str | None:
    env = os.environ.get("FE_HOST_CC")
    for c in ([env] if env else []) + list(HOST_CC_CANDIDATES):
        if os.path.isfile(c) or shutil.which(c):
            return c
    return None


def rom_image(root: Path) -> str | None:
    """The ROM path tools/readable/verify.py would use (FE_ROM, else play/config.json's when that file is
    there, else the .cci in roms/, then the old root place: tools/paths.py, title checked only here)."""
    if os.environ.get("FE_ROM"):
        return os.environ["FE_ROM"]
    p = root / "play" / "config.json"
    try:
        rom = json.loads(p.read_text(encoding="utf-8")).get("rom") if p.is_file() else None
    except (OSError, ValueError, AttributeError):
        rom = None
    if rom and Path(rom).is_file():
        return rom
    sys.path.append(str(Path(__file__).resolve().parent))
    import paths  # noqa: E402  (tools/paths.py)
    found = paths.try_resolve_rom(repo=root, check="header", use_env=False, use_config=False)
    return str(found) if found else rom


def recomp_verify_exe(root: Path) -> Path:
    env = os.environ.get("FE_3DSRECOMP")
    return Path(env) if env else root / "engine" / "target" / "3dsrecomp-verify" / "release" / f"3dsrecomp{EXE}"


def robot_boot_exe(root: Path) -> Path:
    """Zakuro's windowless runner the test robot drives (tools/harness/headless.py BOOT)."""
    return root / "engine" / "target" / "zakuro-test" / "release" / "examples" / f"boot{EXE}"


def robot_library(root: Path) -> Path:
    """The capture library headless runs load (tools/harness/headless.py LIB)."""
    try:
        title = json.loads((root / "config" / "game.json").read_text(encoding="utf-8")).get("title_id")
    except (OSError, ValueError, AttributeError):
        title = None
    return root / "build" / "harness" / "lib" / f"{title or '0004000000179800'}.dll"


def need_missing(ctx: Ctx, need: str) -> str | None:
    """None when the need is met, else the reason (for the SKIP note)."""
    root = ctx.root
    if need == "rom:code":
        for f in ("code.bin", "layout.json", "text.bin"):
            if not (root / "extracted" / f).is_file():
                return f"no extracted/{f} (python tools/extract_rom.py; it reads the .cci in roms/)"
        return None
    if need == "rom:parts":
        if not (root / "extracted" / "rom" / "manifest.json").is_file():
            return "no extracted/rom/manifest.json (python tools/rom/extract.py; it reads the .cci in roms/)"
        return None
    if need == "rom:romfs":
        if not (root / "extracted" / "romfs").is_dir():
            return "no extracted/romfs/ (python tools/assets/romfs.py; it reads the .cci in roms/)"
        return None
    if need in ("toolchain", "armcc"):
        cfg = _local_cfg(root)
        if need == "toolchain":
            d = cfg.get("binutils_dir")
            if not d:
                return "toolchain not configured (python tools/toolchain.py; no tools/config.local.json binutils_dir)"
            for t in BINUTILS + ("g++",):
                if not (Path(d) / f"arm-none-eabi-{t}{EXE}").is_file():
                    return f"arm-none-eabi-{t}{EXE} not found in binutils_dir"
            return None
        entries = cfg.get("cxx") or []
        if isinstance(entries, dict):
            entries = [entries]
        for e in entries:
            if e.get("kind") == "armcc" and e.get("path") and Path(e["path"]).exists():
                return None
        return "armcc not configured (python tools/compile.py use armcc PATH)"
    if need == "host-cc":
        return None if find_host_cc() else "no host C compiler (set FE_HOST_CC, or install gcc/clang)"
    if need == "rom:cci":
        rom = rom_image(root)
        if not rom or not Path(rom).is_file():
            return f"no ROM image ({rom or 'none configured'}; the .cci in roms/, FE_ROM or \"rom\" in play/config.json)"
        return None
    if need == "engine:3dsrecomp-verify":
        exe = recomp_verify_exe(root)
        if not exe.is_file():
            shown = exe.relative_to(root) if exe.is_relative_to(root) else exe
            return f"no {shown} (python tools/engine/engine.py build 3dsrecomp-verify)"
        return None
    if need == "robot":
        for p, what in ((robot_boot_exe(root), "python tools/harness/build.py --boot"),
                        (robot_library(root), "python tools/harness/parallel.py build")):
            if not p.is_file():
                shown = p.relative_to(root) if p.is_relative_to(root) else p
                return f"no {shown} ({what}; needs the owner's OK for engine builds)"
        if not (root / "build" / "harness" / "saves" / "new-game-empty.zip").is_file():
            return "no build/harness/saves/new-game-empty.zip (docs/ROBOT.md section 2)"
        return None
    if need == "git":
        if shutil.which("git") is None:
            return "git not on PATH"
        if not is_git_root(root):
            return "not the top of a git work tree"
        return None
    if need == "seal-edition":
        return None if seal_edition_here(root) else SEAL_EDITION_MISSING
    if need.startswith("file:"):
        rel = need[len("file:"):]
        return None if (root / rel).is_file() else f"no {rel} (not made for this game yet)"
    if need.startswith("after:"):
        dep = need[len("after:"):]
        if dep not in ctx.selected:
            return None          # not part of this run: the row runs on what is on disk
        r = ctx.results.get(dep)
        if r is None or r["status"] not in ("PASS", "KNOWN"):
            return f"needs {dep} ({'not run' if r is None else r['status']})"
        return None
    return f"unknown need {need!r}"


SEAL_EDITION_MISSING = ("the Seal of Flames edition is not in this folder (no tests/seal or config/seal: the Vanilla+ "
                        "edition); its rows skip")


def seal_edition_here(root: Path) -> bool:
    """Round 84 (F-072): the Seal of Flames edition's tests and harness files are here (the dev folder and the Seal
    zip; the Vanilla+ zip leaves both out). Rows that need them carry the need "seal-edition"."""
    return (root / "tests" / "seal" / "__init__.py").is_file() and (root / "config" / "seal").is_dir()


# ------------------------------------------------------------------ git helpers
def is_git_root(root: Path) -> bool:
    """True when root is the top of a git work tree (not merely inside one: a scratch copy
    under a home folder that is itself a repository must not use that repository)."""
    if shutil.which("git") is None:
        return False
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode:
        return False
    try:
        return Path(r.stdout.strip()).resolve() == Path(root).resolve()
    except OSError:
        return False


def git_files(root: Path, *args: str) -> list[str]:
    r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", *args], capture_output=True)
    if r.returncode:
        raise RuntimeError("git ls-files failed: " + r.stderr.decode(errors="replace").strip())
    return sorted(p for p in r.stdout.decode("utf-8", errors="surrogateescape").split("\0") if p)


def is_binary(data: bytes) -> bool:
    return b"\0" in data[:8192]


# The header line tools/gen_asm.py writes at the top of every asm file it makes from the
# user's code.bin (a comment line starting with "@ GENERATED by tools/gen_asm.py").
_GEN_ASM_MARK = re.compile(rb"(?m)^[ \t]*@[ \t]*GENERATED by tools/gen_asm\.py")


def check_hygiene_paths(ctx: Ctx):
    """Tracked files, and untracked files git does not ignore (what `git add -A` would
    commit next): none under generated/local dirs, no ROM/asset/binary extensions, no
    binary content, no asm written by tools/gen_asm.py."""
    root = ctx.root
    tracked = git_files(root)
    untracked = [p for p in git_files(root, "--others", "--exclude-standard") if p not in set(tracked)]
    bad = []
    for p in tracked + untracked:
        low = p.lower()
        if any(low.startswith(d) for d in FORBIDDEN_DIRS) or p in FORBIDDEN_FILES:
            bad.append(f"{p}: under a never-tracked path")
            continue
        if low.startswith("mods/") and p not in MODS_TRACKED:
            bad.append(f"{p}: mod contents are made from game data (only mods/README.md is tracked)")
            continue
        if p in ALLOWED_TRACKED:
            continue
        ext = os.path.splitext(low)[1]
        if ext in SUSPICIOUS_EXT:
            bad.append(f"{p}: suspicious extension {ext}")
            continue
        fp = root / p
        if fp.is_file():
            data = fp.read_bytes()
            if is_binary(data):
                bad.append(f"{p}: binary content (NUL bytes)")
            elif _GEN_ASM_MARK.search(data):
                bad.append(f"{p}: output of tools/gen_asm.py (made from code.bin; never commit)")
    for b in bad:
        print("FAIL", b)
    note = f"{len(tracked)} tracked + {len(untracked)} untracked files; {len(bad)} problem(s)"
    if bad:
        note += ": " + "; ".join(bad[:3]) + (" ..." if len(bad) > 3 else "")
    return not bad, note


def leak_keys(code: bytes) -> tuple[dict[bytes, int], int]:
    """WINDOW-byte keys every STRIDE bytes of code.bin -> offset (low-entropy keys dropped)."""
    keys: dict[bytes, int] = {}
    dropped = 0
    for o in range(0, len(code) - LEAK_WINDOW + 1, LEAK_STRIDE):
        w = code[o:o + LEAK_WINDOW]
        if len(set(w)) < LEAK_MIN_DISTINCT or is_progression(w):
            dropped += 1
            continue
        keys.setdefault(w, o)
    return keys, dropped


def is_progression(w: bytes) -> bool:
    """Counting sequences (bytes, u16 or u32 n, n+1, n+2 ...): they occur in any numbered
    list, so a match carries no information about code.bin."""
    for k in (1, 2, 4):
        if len({(w[i + k] - w[i]) & 0xFF for i in range(len(w) - k)}) <= 2:
            return True
    return False


def window_kind(w: bytes) -> str:
    """ident (only identifier characters, or a qualified C++ name with :: < > ~ and no
    spaces: symbol/RTTI names), text, or binary."""
    s = set(w)
    if s <= NAME_BYTES:
        return "ident"
    if s <= PRINTABLE:
        return "text"
    return "binary"


def is_pointer_window(w: bytes, code_len: int) -> bool:
    """Every 32-bit little-endian word is 0, an address inside the loaded image, or a
    small negative offset: an address list (vtable slots), not data."""
    hi = CODE_BASE + code_len + BSS_SLACK
    for j in range(0, len(w) - 3, 4):
        v = int.from_bytes(w[j:j + 4], "little")
        if not (v == 0 or CODE_BASE <= v < hi or v >= 0xFFFF0000):
            return False
    return True


# ---- decoding bytes written as text (asm data directives, hex dumps, arrays, escapes)
# Every decoded value is appended to a per-file stream; lines that hold no values (labels,
# .global, blank lines, prose) add nothing and do NOT break the stream, so data split by
# labels or address comments stays contiguous. Each stream is then scanned like raw bytes.
_DIRECTIVE_WIDTH = {
    ".byte": 1, ".1byte": 1, ".dc.b": 1, "dcb": 1, "db": 1,
    ".hword": 2, ".short": 2, ".half": 2, ".2byte": 2, ".dc.w": 2, "dcw": 2, "dw": 2,
    ".word": 4, ".long": 4, ".int": 4, ".4byte": 4, ".dc.l": 4, "dcd": 4, "dd": 4,
    ".quad": 8, ".8byte": 8, "dcq": 8}
_FILL_DIRECTIVES = {".space", ".zero", ".skip"}
_STRING_DIRECTIVES = {".ascii": b"", ".asciz": b"\0", ".string": b"\0"}
_PREFIX_TOKENS = {"*", ">", "-", "+", "|", "//", "/*", "*/", "#", "@", ";", "!"}
_NASM_DIRECTIVES = {"dcb", "db", "dcw", "dw", "dcd", "dd", "dcq"}   # also valid hex bytes
_FILL_CAP = 1 << 16
_HEX_RUN = re.compile(r"[0-9A-Fa-f]{64,}")                  # quoted or embedded hex strings
_DEC_RUN = re.compile(r"(?<![\w.])\d{1,3}(?:\s*,\s*\d{1,3}(?![\w.]))+")   # 1, 2, 3 anywhere
_TOK_SPLIT = re.compile(r"[\s,{}()\[\]=]+")
_XXD_LINE = re.compile(r"^\s*[0-9A-Fa-f]{4,}:\s")          # 00000010: 4142 4344 ...  ASCII
_ASCII_COLUMN = re.compile(r"\s\|[^|]*\|?\s*$")             # hexdump -C  |ASCII|
_HEX_VALUE = re.compile(r"(0[xX])?([0-9A-Fa-f]+)[uUlL]*\Z")
_SYM_ADDR = re.compile(r"[A-Za-z_]\w*?_([0-9A-Fa-f]{8})\Z")  # func_001F5C38 / D_0045A000
_DEC_VALUE = re.compile(r"-?[0-9]+\Z")
_X_TOKEN = re.compile(r"(?<![0-9A-Za-z_])0[xX]([0-9A-Fa-f]+)")
_STR_LITERAL = re.compile(r"""(["'])((?:\\.|(?!\1)[^\\\n])*)\1""")
_ESCAPE = re.compile(r"\\(x[0-9A-Fa-f]{1,2}|[0-7]{1,3}|.)", re.S)
_SIMPLE_ESC = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def _unescape(s: str) -> bytes:
    def rep(m):
        e = m.group(1)
        if e[0] == "x" and len(e) > 1:
            return chr(int(e[1:], 16))
        if e[0] in "01234567":
            return chr(int(e, 8) & 0xFF)
        return _SIMPLE_ESC.get(e, e)
    return _ESCAPE.sub(rep, s).encode("latin-1", errors="replace")


def _split_comment(line: str) -> tuple[str, str]:
    """(code, comment) at the first @ # ; // or /* outside a quoted string."""
    q, i, n = None, 0, len(line)
    while i < n:
        c = line[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        elif c in "\"'":
            q = c
        elif c in "@#;" or (c == "/" and i + 1 < n and line[i + 1] in "/*"):
            return line[:i], line[i:]
        i += 1
    return line, ""


def _segment_values(seg: str, be: bytearray, le: bytearray, dec: bytearray,
                    nasm: bool = True) -> None:
    """Append the leading run of values of one line (or comment) to the streams:
    be = digits as written, le = each value byte-reversed (memory order of .word/.hword
    lists, objdump words, u16/u32 arrays), dec = small decimal numbers as bytes."""
    if _XXD_LINE.match(seg):
        rest = seg.partition(":")[2].lstrip()
        seg = rest.split("  ", 1)[0]           # drop the ASCII column
    elif "  |" in seg:
        seg = seg.split("  |", 1)[0]            # hexdump -C: drop the |ASCII| column
    else:
        seg = _ASCII_COLUMN.sub("", seg)
    toks =[t for t in _TOK_SPLIT.split(seg) if t]
    i, n, directive, width = 0, len(toks), None, 0
    while i < n:                                 # prefixes: comment marks, labels, offsets:
        t = toks[i]
        low = t.lower()
        if t in _PREFIX_TOKENS or t.endswith(":"):
            i += 1
            continue
        if not nasm and low in _NASM_DIRECTIVES:
            break                                # read as a hex byte (second pass)
        if low in _DIRECTIVE_WIDTH or low in _FILL_DIRECTIVES or low in _STRING_DIRECTIVES:
            directive, width = low, _DIRECTIVE_WIDTH.get(low, 0)
            i += 1
        elif low.startswith("."):
            return                               # .global, .section, .balign ...: no data
        break
    if directive in _FILL_DIRECTIVES:
        try:
            count = min(int(toks[i], 0), _FILL_CAP)
            fill = int(toks[i + 1], 0) & 0xFF if i + 1 < n else 0
        except (IndexError, ValueError):
            return
        b = bytes([fill]) * count
        be += b
        le += b
        return
    if directive in _STRING_DIRECTIVES:
        for m in _STR_LITERAL.finditer(seg):
            b = _unescape(m.group(2)) + _STRING_DIRECTIVES[directive]
            be += b
            le += b
        return
    # an offset column (hexdump -C, hexdump, od): a bare number longer than, or of odd
    # length unlike, the values that follow it
    if (directive is None and i + 1 < n and re.fullmatch(r"[0-9A-Fa-f]{4,}", toks[i])
            and _HEX_VALUE.match(toks[i + 1])
            and (len(toks[i]) % 2 or len(toks[i]) > len(toks[i + 1]))):
        i += 1
    dec_open, hex_open = directive is None, True
    for t in toks[i:]:
        m = _HEX_VALUE.match(t)
        if directive:
            if m and m.group(1):
                digits = m.group(2)
            elif _DEC_VALUE.match(t):
                digits = format(int(t) & ((1 << (8 * width)) - 1), "x")
            elif width == 4 and _SYM_ADDR.match(t):
                digits = _SYM_ADDR.match(t).group(1)   # symbols are named by their address
            else:
                break
            digits = digits.rjust(2 * width, "0")[-2 * width:]
        else:
            if dec_open and t.isascii() and t.isdigit() and len(t) <= 3 and int(t) <= 255:
                dec.append(int(t))
            else:
                dec_open = False
            digits = m.group(2) if (m and hex_open) else None
            if digits is not None and len(digits) % 2:
                digits = "0" + digits if m.group(1) else None
            if digits is None:
                hex_open = False
                if not dec_open:
                    break
                continue
        b = bytes.fromhex(digits)
        be += b
        le += b[::-1]


def decoded_streams(data: bytes) -> list[bytes]:
    """Byte streams decoded from a text file, each at least LEAK_WINDOW bytes long:
    leading value runs of every line (asm .word/.hword/.byte/.space/.ascii with symbol
    names read as their address, xxd, hexdump -C, objdump -d, C arrays, contiguous hex,
    decimal byte lists) as written and byte-reversed per value; the same for text inside
    comments; every 0x token in the file; and string literals with escapes (b'\\x41...')."""
    text = data.decode("latin-1")
    code_be, code_le, code_dec = bytearray(), bytearray(), bytearray()
    com_be, com_le, com_dec = bytearray(), bytearray(), bytearray()
    strs = bytearray()
    lines = text.splitlines()
    # db/dd/dw/dcb... are nasm/armasm directives but also hex bytes: if any line starts with
    # one, decode the file a second time reading them as values.
    ambiguous = any(_TOK_SPLIT.split(ln.strip(), 1)[0].lower() in _NASM_DIRECTIVES for ln in lines)
    alt_be, alt_le, alt_dec = bytearray(), bytearray(), bytearray()
    for line in lines:
        if "\\" in line:
            for m in _STR_LITERAL.finditer(line):
                if "\\" in m.group(2):
                    strs += _unescape(m.group(2))
        code, comment = _split_comment(line)
        _segment_values(code, code_be, code_le, code_dec)
        if ambiguous:
            _segment_values(code, alt_be, alt_le, alt_dec, nasm=False)
        if comment:
            _segment_values(comment.lstrip("@#;/*! \t"), com_be, com_le, com_dec)
    x_be, x_le = bytearray(), bytearray()
    for m in _X_TOKEN.finditer(text):
        digits = m.group(1)
        b = bytes.fromhex(digits if len(digits) % 2 == 0 else "0" + digits)
        x_be += b
        x_le += b[::-1]
    runs = bytearray()                           # "a1b2..." in quotes, JSON, fromhex(...)
    for m in _HEX_RUN.finditer(text):
        d = m.group(0)
        runs += bytes.fromhex(d[:len(d) & ~1])
        if len(d) % 2:
            runs += bytes.fromhex(d[1:])
    decs = bytearray()                           # decimal lists after "t[] = {", "x = [" ...
    for m in _DEC_RUN.finditer(text):
        vals = [int(v) for v in re.findall(r"\d+", m.group(0))]
        if max(vals) <= 255:
            decs += bytes(vals)
    out, seen = [], set()
    for s in (code_be, code_le, code_dec, com_be, com_le, com_dec, x_be, x_le, strs,
              alt_be, alt_le, alt_dec, runs, decs):
        s = bytes(s)
        if len(s) >= LEAK_WINDOW and s not in seen:
            seen.add(s)
            out.append(s)
    return out


hex_streams = decoded_streams   # older name, kept for callers


def scan_leaks(keys: dict[bytes, int], data: bytes) -> list[tuple[int, int, str]]:
    """(file offset, code.bin offset, kind) for every key found at any offset of data."""
    hits = []
    W = LEAK_WINDOW
    get = keys.get
    for i in range(len(data) - W + 1):
        o = get(data[i:i + W])
        if o is not None:
            hits.append((i, o, window_kind(data[i:i + W])))
    return hits


def check_hygiene_leak(ctx: Ctx):
    """No tracked file shares a long run of bytes with extracted/code.bin, raw or written
    as text (asm data directives, hex dumps, arrays, escapes: see decoded_streams). Raw
    runs made only of identifier characters are symbol/RTTI names (D-006): counted, allowed.
    Untracked files that are not ignored are scanned the same way: they are what the next
    commit would add, so a leak is found before it is committed."""
    root = ctx.root
    code = (root / "extracted" / "code.bin").read_bytes()
    keys, dropped = leak_keys(code)
    if not keys:
        return False, (f"extracted/code.bin ({len(code)} bytes) gives no keys: empty or "
                       f"truncated, nothing was checked")
    print(f"code.bin {len(code)} bytes: {len(keys)} keys of {LEAK_WINDOW} bytes every "
          f"{LEAK_STRIDE} ({dropped} low-entropy windows ignored); any shared run of "
          f"{LEAK_WINDOW + LEAK_STRIDE - 1}+ bytes is found")
    if hashlib.sha1(code).hexdigest() != EXPECTED_CODE_SHA1:
        print("note: extracted/code.bin is not the retail one (a dummy image?)")
    bad_files, ident_files, ptr_files, scanned, nbytes = [], {}, {}, 0, 0
    allowed = ("ident", "pointers")
    tracked = git_files(root)
    untracked = git_files(root, "--others", "--exclude-standard")
    n_untracked = 0
    for p in tracked + untracked:
        fp = root / p
        if not fp.is_file():
            continue
        data = fp.read_bytes()
        scanned += 1
        n_untracked += p in untracked and p not in tracked
        nbytes += len(data)
        found = [(f"raw @+{i:#x}", o, k) for i, o, k in scan_leaks(keys, data)]
        if not is_binary(data):
            # Bytes decoded from text are never "identifier only" (nobody writes symbol
            # names as hex); they are allowed only when every word is an address.
            for n, s in enumerate(decoded_streams(data)):
                for i, o, _ in scan_leaks(keys, s):
                    kind = ("pointers" if is_pointer_window(code[o:o + LEAK_WINDOW], len(code))
                            else "decoded")
                    found.append((f"decoded stream {n} @+{i:#x}", o, kind))
        serious = [f for f in found if f[2] not in allowed]
        if serious:
            where, o, k = serious[0]
            bad_files.append(f"{p} ({len(serious)} window(s), first {where} = code.bin+{o:#x}, {k})")
        idents = sum(1 for f in found if f[2] == "ident")
        ptrs = sum(1 for f in found if f[2] == "pointers")
        if idents:
            ident_files[p] = idents
        if ptrs:
            ptr_files[p] = ptrs
    for b in bad_files:
        print("FAIL", b)
    for p, n in sorted(ident_files.items()):
        print(f"allowed: {p}: {n} identifier-only window(s) (symbol/RTTI names)")
    for p, n in sorted(ptr_files.items()):
        print(f"allowed: {p}: {n} address-only window(s) (vtable slot lists)")
    note = (f"{scanned - n_untracked} tracked + {n_untracked} untracked files ({nbytes:,} bytes) vs "
            f"{len(keys):,} code.bin keys: "
            f"{len(bad_files)} file(s) with code.bin bytes")
    if bad_files:
        note += ": " + "; ".join(bad_files[:2]) + (" ..." if len(bad_files) > 2 else "")
    if ident_files:
        note += (f"; {sum(ident_files.values())} identifier-only windows in "
                 f"{len(ident_files)} files allowed (RTTI names, D-006)")
    if ptr_files:
        note += (f"; {sum(ptr_files.values())} address-only windows in "
                 f"{len(ptr_files)} files allowed (vtable slots, D-006)")
    return not bad_files, note


def check_py_compile(ctx: Ctx):
    """Every tracked or untracked-but-not-ignored .py file (or, outside git, every .py
    under tools/ and tests/) compiles."""
    root = ctx.root
    if is_git_root(root):
        files = sorted({p for p in git_files(root) + git_files(root, "--others", "--exclude-standard")
                        if p.endswith(".py")})
    else:
        files = sorted(str(p.relative_to(root)).replace("\\", "/")
                       for d in ("tools", "tests") for p in (root / d).rglob("*.py")
                       if "bin" not in p.relative_to(root).parts)
    bad = []
    for p in files:
        fp = root / p
        if not fp.is_file():
            continue
        try:
            compile(fp.read_bytes(), p, "exec", dont_inherit=True)
        except (SyntaxError, ValueError) as e:
            bad.append(f"{p}: {e}")
            print("FAIL", bad[-1])
    if not files:
        return False, "no Python files found (nothing compiled is not a pass)"
    return not bad, f"{len(files)} Python files compiled; {len(bad)} with errors" + (
        ": " + bad[0] if bad else "")


# Round 8 (2026-11-13 evening, F-022): Birthright, Conquest and Revelation side by side.
ROUTE_FAMILIES = {"bt": 0, "cq": 1, "rv": 2, "opt": None}   # route-name prefix -> the route byte its markers must read
BRANCH_SAVE = {"cq-ch6": "bt-ch5-clear", "rv-ch6": "bt-ch5-clear"}   # the branch: the save made before the choice
ROUND8_PACKS = ("cq-ch6-clear", "rv-ch6-clear", "bt-ch10-clear", "bt-ch11-clear",   # in-game saves round 8 made
                "cq-ch7-clear", "rv-ch7-clear", "rv-ch8-clear",                      # its late routes
                "bt-ch12-clear", "rv-ch9-clear",                                    # round 9
                "cq-ch8-clear",                                                     # round 9 (integrate)
                "bt-ch13-clear", "bt-ch14-clear", "bt-ch15-clear", "bt-ch16-clear",  # round 10 (fresh helper
                "bt-ch17-clear", "rv-ch10-clear", "rv-ch11-clear", "rv-ch12-clear",  # per chapter)
                "rv-ch13-clear", "rv-ch14-clear", "cq-ch9-clear",                   # cq-ch9: integrate
                "bt-ch18-clear", "bt-ch19-clear", "bt-ch20-clear", "bt-ch21-clear",  # round 11 (proof its own
                "bt-ch22-clear", "bt-ch23-clear", "cq-ch10-clear", "cq-ch11-clear",  # step); cq-ch13 and rv-ch18
                "cq-ch12-clear", "rv-ch15-clear", "rv-ch16-clear", "rv-ch17-clear",  # stay unverified (F-025)
                "bt-ch24-clear",                                                    # round 12 (Birthright only)
                "bt-ch25-clear",                                                    # round 13 (Birthright only)
                "bt-ch26-clear",                                                    # round 14 (Birthright only)
                "cq-ch13-clear", "cq-ch14-clear", "cq-ch15-clear",                  # round 20 (F-031: Conquest and
                "rv-ch18-clear", "rv-ch19-clear", "rv-ch20-clear",                  # Revelation resumed, real play)
                "cq-ch16-clear", "rv-ch21-clear", "rv-ch22-clear", "rv-ch23-clear",  # round 24 (F-031, real play;
                "rv-ch24-clear",                                                    # cq-ch17 not cleared, left out)
                "rv-ch25-clear", "rv-ch26-clear")                                   # round 31 (F-031, real play;
                                                                                    # rv-ch27 not cleared, left out)
# Round 15: bt-ch27 (King Garon) is verified but has NO packed clear save on purpose: the game makes no save after
# chapter 27 (it goes straight to the Endgame Preparations), and copy 1's save files are byte-for-byte bt-ch26-clear.
# A bt-ch27-clear.zip equal to the save it started from would be a bt-ch26 save under a bt-ch27 name: refused.
NO_CLEAR_SAVE = {"bt-ch27": "bt-ch26-clear"}   # verified route -> the save it starts from (its own clear is not made)

# F-025 (2026-11-15) paused Conquest and Revelation; F-031 (round 20, 2026-11-17) resumed them, real play per
# chapter. A cq-/rv- key is counted here only once its two-copy proof set "verified": true and its clear save is
# packed (then it joins ROUND8_PACKS); any unverified cq-/rv- key (a chain not yet proven) stays out and is named.
UNPROVEN_FAMILIES = ("cq", "rv")
AI_SCORE_DIR = "src/readable/ai_score/"

# Round 19 (F-030): Birthright Endgame finished on the cheat track. The game makes no save after Endgame (it goes
# through the ending to the title screen; the proof's savedata stayed byte-for-byte bt-ch26-clear), so the route has
# no clear save, like bt-ch27 on the real-play side. Any packed <route>-clear.zip would be a mislabelled copy.
CHEAT_NO_CLEAR_SAVE = {"cheat-bt-endgame": "bt-ch26-clear",   # cheat route -> the save it starts from
                       "cheat-rv-ch27": "rv-ch26-clear",     # round 36 (F-035): see below
                       "cheat-rv-endgame": "rv-ch26-clear",  # round 36 (F-030/F-031/F-035), proven at integrate
                       "cheat-cq-ch27": "cheat-cq-ch26-clear",     # round 37 (F-033/F-036): no pokes of its own
                       "cheat-cq-endgame": "cheat-cq-ch26-clear"}  # round 37 (F-030/F-031/F-036): 1 poke (boss HP)
# Round 36 (F-035): cheat-rv-ch27 (Revelation 27 on the cheat track) ends on the Endgame preparations screen; the
# game makes no save after chapter 27, so the proof's savedata stayed byte-for-byte rv-ch26-clear (as bt-ch27).
# The packed cheat-rv-ch27-clear.zip was that rv-ch26 save under a ch27 name, and by the fingerprint rule it made
# rv-ch26-clear itself read as a cheat save; integrate moved it to build/harness/saves-aside/ (F-029). The
# Revelation Endgame (cheat-rv-endgame, from rv-ch26-clear through cheat-rv-ch27's presses) ends on the title
# screen with no save, like cheat-bt-endgame; its two-copy proof (r36-proof2-cheat-rv-endgame) passed at integrate.
# Round 37 (F-033/F-036): Conquest 27 (cheat-cq-ch27) and the Conquest Endgame (cheat-cq-endgame, cheat-cq-ch27's
# presses as its prefix) start from the cheat save cheat-cq-ch26-clear; the game makes no save after chapter 27
# (the proof's packed copy was byte-identical to cheat-cq-ch26-clear and was set aside as NOT-A-CLEAR-SAVE). A
# route that starts from a listed Conquest cheat clear save may declare no pokes of its own (as in CHEAT_CQ_PACKS).


def check_cheat_endgame(ctx: Ctx):
    """F-030: every cheat route of CHEAT_NO_CLEAR_SAVE is a declared cheat route ("cheat": true, at least one
    poke) that starts from its named real-play save, has checkpoints in markers.json, and has NO packed clear
    save under build/harness/saves (the game makes none after Endgame). Verified or not is reported; the
    real-play key bt-endgame stays unwritten (F-030) and is only named in the note."""
    root = ctx.root
    try:
        routes = json.loads((root / "config/harness/routes.json").read_text(encoding="utf-8"))["routes"]
        cps = json.loads((root / "config/harness/markers.json").read_text(encoding="utf-8"))["checkpoints"]
    except (OSError, ValueError, KeyError) as e:
        return False, f"routes.json / markers.json unreadable: {e}"
    saves = root / "build" / "harness" / "saves"
    bad, proven, waiting = [], [], []
    for name, start in CHEAT_NO_CLEAR_SAVE.items():
        r = routes.get(name)
        if not isinstance(r, dict):
            bad.append(f"{name}: missing from routes.json")
            continue
        if r.get("cheat") is not True:
            bad.append(f"{name}: not marked \"cheat\": true")
        from_cheat = start.endswith("-clear") and start[:-len("-clear")] in CHEAT_CQ_PACKS
        if not r.get("pokes") and not from_cheat:
            bad.append(f"{name}: declares no pokes")
        if r.get("save") != start:
            bad.append(f"{name}: starts from {r.get('save')!r}, not {start!r}")
        cp = cps.get(name)
        if not isinstance(cp, dict) or not [k for k in cp if not k.startswith("_")]:
            bad.append(f"{name}: no checkpoints in markers.json")
        if saves.is_dir() and (saves / f"{name}-clear.zip").is_file():
            bad.append(f"build/harness/saves/{name}-clear.zip exists (the game makes no save there)")
        (proven if r.get("verified") is True else waiting).append(name)
    for b in bad:
        print("FAIL", b)
    note = (f"{len(CHEAT_NO_CLEAR_SAVE)} cheat route(s) with no clear save by design"
            + (f"; verified: {', '.join(proven)}" if proven else "")
            + (f"; not yet verified: {', '.join(waiting)}" if waiting else "")
            + ("; real-play bt-endgame unwritten (F-030)" if "bt-endgame" not in routes else "")
            + f"; {len(bad)} problem(s)")
    if bad:
        note += ": " + "; ".join(bad[:3]) + (" ..." if len(bad) > 3 else "")
    return not bad, note


# Round 29 (F-033, owner 2026-11-18: "just maximize movement options for conquest to make sure the combat and
# animations etc work"): Conquest from chapter 17 goes on the cheat track with a declared movement cheat (unit
# move bonus s8 Unit+0x12C), counted apart from real play (F-019). Every cheat-cq-* chapter proven this way is
# named here with the save it starts from; it must be a declared, verified cheat route with checkpoints, and its
# packed clear save must exist and carry the cheat mark (harness-cheat.json), so it can never start real play.
# A real-play cq-ch17+ key joins ROUND8_PACKS only if one is truly won with no poke (none so far).
# Round 32: a chapter played on from an earlier listed chapter's cheat clear save (the move bonus already in the
# save) may declare no pokes of its own: it is a cheat route because its start save is a cheat save.
CHEAT_CQ_PACKS = {"cheat-cq-ch17": "cq-ch16-clear",          # round 29 (28 movement pokes)
                  "cheat-cq-ch18": "cheat-cq-ch17-clear",    # round 32 (no pokes of its own)
                  "cheat-cq-ch19": "cheat-cq-ch18-clear",    # round 32 (no pokes of its own)
                  "cheat-cq-ch20": "cheat-cq-ch19-clear",    # round 34 (no pokes of its own)
                  "cheat-cq-ch21": "cheat-cq-ch20-clear",    # round 34 (no pokes; escape on turn 1)
                  "cheat-cq-ch22": "cheat-cq-ch21-clear",    # round 34 (no pokes of its own)
                  "cheat-cq-ch23": "cheat-cq-ch22-clear",    # round 34 (no pokes of its own)
                  "cheat-cq-ch24": "cheat-cq-ch23-clear",    # round 37 (F-036: 106 declared HP/Def/Res/move pokes)
                  "cheat-cq-ch25": "cheat-cq-ch24-clear",    # round 37 (F-036: 8 pokes, the new unit Leo)
                  "cheat-cq-ch26": "cheat-cq-ch25-clear"}    # round 37 (no pokes of its own)
# cheat-cq-ch27 and cheat-cq-endgame (round 37) have no clear save by design: they are in CHEAT_NO_CLEAR_SAVE.
CHEAT_MARK = "harness-cheat.json"


def check_cheat_conquest(ctx: Ctx):
    """F-033: every route of CHEAT_CQ_PACKS is a declared cheat route ("cheat": true, at least one poke unless
    it starts from another listed route's cheat clear save) from its named save, verified, with checkpoints in markers.json, and (when build/harness/saves exists)
    its packed <route>-clear.zip is there and carries the cheat mark. Unlisted cheat-cq-* keys are named."""
    import zipfile
    root = ctx.root
    try:
        routes = json.loads((root / "config/harness/routes.json").read_text(encoding="utf-8"))["routes"]
        cps = json.loads((root / "config/harness/markers.json").read_text(encoding="utf-8"))["checkpoints"]
    except (OSError, ValueError, KeyError) as e:
        return False, f"routes.json / markers.json unreadable: {e}"
    saves = root / "build" / "harness" / "saves"
    have_saves = saves.is_dir()
    bad = []
    for name, start in CHEAT_CQ_PACKS.items():
        r = routes.get(name)
        if not isinstance(r, dict):
            bad.append(f"{name}: missing from routes.json")
            continue
        if r.get("cheat") is not True:
            bad.append(f"{name}: not marked \"cheat\": true")
        from_cheat = start.endswith("-clear") and start[:-len("-clear")] in CHEAT_CQ_PACKS
        if not r.get("pokes") and not from_cheat:
            bad.append(f"{name}: declares no pokes")
        if r.get("save") != start:
            bad.append(f"{name}: starts from {r.get('save')!r}, not {start!r}")
        if r.get("verified") is not True:
            bad.append(f"{name}: not verified")
        cp = cps.get(name)
        if not isinstance(cp, dict) or not [k for k in cp if not k.startswith("_")]:
            bad.append(f"{name}: no checkpoints in markers.json")
        if have_saves:
            z = saves / f"{name}-clear.zip"
            if not z.is_file():
                bad.append(f"build/harness/saves/{name}-clear.zip is missing")
            else:
                try:
                    with zipfile.ZipFile(z) as zf:
                        if CHEAT_MARK not in zf.namelist():
                            bad.append(f"build/harness/saves/{name}-clear.zip carries no {CHEAT_MARK}")
                except (OSError, zipfile.BadZipFile) as e:
                    bad.append(f"build/harness/saves/{name}-clear.zip unreadable: {e}")
    for b in bad:
        print("FAIL", b)
    others = sorted(k for k, r in routes.items() if k.startswith("cheat-cq-") and k not in CHEAT_CQ_PACKS
                    and k not in CHEAT_NO_CLEAR_SAVE)
    note = (f"{len(CHEAT_CQ_PACKS)} proven Conquest cheat route(s): {', '.join(CHEAT_CQ_PACKS)}"
            + ("" if have_saves else " (no build/harness/saves: clear saves not checked)")
            + (f"; not listed (not proven): {', '.join(others)}" if others else "")
            + f"; {len(bad)} problem(s)")
    if bad:
        note += ": " + "; ".join(bad[:3]) + (" ..." if len(bad) > 3 else "")
    return not bad, note


def check_ai_score_parked(ctx: Ctx):
    """F-025: the AI attack-score batch stays parked: no *.c under src/readable/ai_score/ (its bodies are
    kept as *.c.parked, which stage.py / build.py / check.py never pick up) and no row of
    config/readable/functions.csv or config/harness/targets.csv names that folder."""
    root = ctx.root
    bad = []
    d = root / AI_SCORE_DIR
    if d.is_dir():
        bad += [f"{f.relative_to(root).as_posix()} is a .c file (parked bodies must stay *.c.parked)"
                for f in sorted(d.rglob("*.c"))]
    for rel in ("config/readable/functions.csv", "config/harness/targets.csv"):
        f = root / rel
        if not f.is_file():
            bad.append(f"{rel} missing")
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            norm = line.replace("\\", "/")
            if AI_SCORE_DIR in norm or "ai_score/" in norm:
                bad.append(f"{rel} line {i} names {AI_SCORE_DIR}")
    for b in bad:
        print("FAIL", b)
    parked = len(list(d.glob("*.c.parked"))) if d.is_dir() else 0
    note = f"ai_score parked: {parked} .c.parked file(s), {len(bad)} problem(s)"
    if bad:
        note += ": " + "; ".join(bad[:3]) + (" ..." if len(bad) > 3 else "")
    return not bad, note


def check_robot_routes(ctx: Ctx):
    """Every verified real-play route (bt-*, cq-*, rv-*, opt-*) of config/harness/routes.json has
    checkpoints in config/harness/markers.json; a route byte its checkpoints read is the family's
    (Birthright 0, Conquest 1, Revelation 2; a cq-*/rv-* route must read it at least once); the
    Conquest and Revelation branches start from the Birthright save made before the choice; and,
    when build/harness/saves exists, every start save and round 8's packed saves are there."""
    root = ctx.root
    try:
        routes = json.loads((root / "config/harness/routes.json").read_text(encoding="utf-8"))["routes"]
        cps = json.loads((root / "config/harness/markers.json").read_text(encoding="utf-8"))["checkpoints"]
    except (OSError, ValueError, KeyError) as e:
        return False, f"routes.json / markers.json unreadable: {e}"
    saves = root / "build" / "harness" / "saves"
    have_saves = saves.is_dir()
    bad, n = [], 0
    for name, r in routes.items():
        fam = name.split("-", 1)[0]
        if fam not in ROUTE_FAMILIES or not isinstance(r, dict) or r.get("verified") is not True:
            continue
        if "options" in r:   # the options track (opt-* with "options"): scored apart, never real play (F-032)
            continue
        n += 1
        cp = cps.get(name)
        if not isinstance(cp, dict) or not [k for k in cp if not k.startswith("_")]:
            bad.append(f"{name}: verified but no checkpoints in markers.json")
            cp = {}
        read = {c["state"]["route"] for c in cp.values()
                if isinstance(c, dict) and isinstance(c.get("state"), dict) and "route" in c["state"]}
        want = ROUTE_FAMILIES[fam]
        if want is not None and read - {want}:
            bad.append(f"{name}: checkpoints read route byte {sorted(read)}, a {fam}-* route must read {want}")
        if fam in ("cq", "rv") and want not in read:
            bad.append(f"{name}: no checkpoint reads the route byte (must show {want})")
        if name in BRANCH_SAVE and r.get("save") != BRANCH_SAVE[name]:
            bad.append(f"{name}: starts from {r.get('save')!r}, not the pre-choice save {BRANCH_SAVE[name]!r}")
        if have_saves and r.get("save") and not (saves / f"{r['save']}.zip").is_file():
            bad.append(f"{name}: start save build/harness/saves/{r['save']}.zip is missing")
    for name in BRANCH_SAVE:
        if not isinstance(routes.get(name), dict) or routes[name].get("verified") is not True:
            bad.append(f"{name}: missing or not verified in routes.json")
    if have_saves:
        bad += [f"build/harness/saves/{z}.zip is missing" for z in ROUND8_PACKS if not (saves / f"{z}.zip").is_file()]
        for name, start in NO_CLEAR_SAVE.items():
            own, prev = saves / f"{name}-clear.zip", saves / f"{start}.zip"
            if own.is_file() and prev.is_file() and own.read_bytes() == prev.read_bytes():
                bad.append(f"build/harness/saves/{name}-clear.zip is byte-identical to {start}.zip (the game makes "
                           f"no save after {name}: a mislabelled copy)")
    for b in bad:
        print("FAIL", b)
    paused = sorted(k for k, r in routes.items() if k.split("-", 1)[0] in UNPROVEN_FAMILIES
                    and isinstance(r, dict) and r.get("verified") is not True)
    note = (f"{n} verified real-play route(s) checked" + ("" if have_saves else " (no build/harness/saves: "
            "saves not checked)") + (f"; unverified cq-/rv- key(s) left out: {', '.join(paused)}" if paused else "")
            + (f"; no clear save by design: {', '.join(sorted(NO_CLEAR_SAVE))}" if NO_CLEAR_SAVE else "")
            + f"; {len(bad)} problem(s)")
    if bad:
        note += ": " + "; ".join(bad[:3]) + (" ..." if len(bad) > 3 else "")
    return not bad, note


def check_progress(ctx: Ctx):
    """Informational: run tools/progress.py and say whether README's block is current."""
    root = ctx.root
    r = subprocess.run([ctx.py, str(root / "tools" / "progress.py")], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=300,
                       env=child_env())
    sys.stdout.write(r.stdout + r.stderr)
    if r.returncode:
        return False, f"progress.py exit {r.returncode}"
    out = [l.rstrip() for l in r.stdout.splitlines() if l.strip()]
    head = next((l for l in out if l.startswith("**Matching progress")), "")
    m = re.search(r"(\d[\d,]*) / ([\d,]+) functions, (\d[\d,]*) / ([\d,]+) bytes \(([\d.]+)%\)", head)
    summary = (f"game {m.group(1)}/{m.group(2)} functions matched ({m.group(5)}% of bytes)"
               if m else "no summary line")
    readme = root / "README.md"
    state = "README.md missing"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        bm = re.search(r"<!-- progress -->\n(.*?)<!-- /progress -->", text, re.S)
        if bm:
            block = [l.rstrip() for l in bm.group(1).splitlines() if l.strip()]
            mine = [l for l in out if l.startswith(("|", "**"))]
            theirs = [l for l in block if l.startswith(("|", "**"))]
            state = ("README progress block current" if mine == theirs else
                     "README progress block STALE (python tools/progress.py --readme)")
        else:
            state = "README has no progress markers"
    return True, f"info: {summary}; {state}"


def assets_quick_cmd() -> list[str]:
    return ["{py}", "{root}/tools/check_all.py", "--root", "{root}", "--internal", "assets-quick"]


def internal_assets_quick(root: Path) -> int:
    """A deterministic sample of RomFS files through roundtrip_all's whole chain (LZ ->
    editable form -> rebuild -> LZ), each first checked against the RomFS manifest hash.
    Up to 3 files (first, middle, last by path) per (top directory, extension) group."""
    sys.path.insert(0, str(root / "tools" / "assets"))
    import roundtrip_all as RA  # noqa: E402  (imports the converters; writes nothing)
    import romfs as RF          # noqa: E402
    base = Path(RA.ROMFS)
    groups: dict[tuple[str, str], list[str]] = {}
    for dp, _dn, fn in os.walk(base):
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), base).replace("\\", "/")
            top = rel.split("/")[0] if "/" in rel else "."
            groups.setdefault((top, os.path.splitext(f)[1].lower()), []).append(rel)
    sample = []
    for k in sorted(groups):
        files = sorted(groups[k])
        idx = sorted({0, len(files) // 2, len(files) - 1})
        sample += [files[i] for i in idx]
    manifest = RF.load_manifest()   # rel path -> (size, sha1), from the extractor
    t0 = time.time()
    ok = hashed = 0
    kinds: dict[str, list[int]] = {}
    fails = []
    for rel in sample:
        path = str(base / rel)
        want = manifest.get(rel)
        if want is not None:
            with open(path, "rb") as fh:
                d = fh.read()
            hashed += 1
            if len(d) != want[0] or hashlib.sha1(d).hexdigest() != want[1]:
                fails.append(f"{rel}\tedited (size/SHA-1 differ from the RomFS manifest)")
                continue
        _p, kind, good, err = RA._chain_one(path)
        kk = kinds.setdefault(kind, [0, 0])
        kk[1] += 1
        kk[0] += good
        ok += good
        if not good:
            fails.append(f"{rel}\t{kind}\t{err}")
    for f in fails:
        print("FAIL", f)
    print(f"ASSETS QUICK: {ok}/{len(sample)} sampled files identical through the chain "
          f"({len(groups)} groups); " + ", ".join(f"{k}={v[0]}/{v[1]}" for k, v in sorted(kinds.items()))
          + f"; {hashed} checked against the RomFS manifest ({time.time() - t0:.0f}s)")
    return 0 if ok == len(sample) and sample else 1


W12_PLANT_FLOOR = r"(3[4-9]|[4-9]\d|[1-9]\d{2,})"   # round 40: at least 34 W1/W2 plants, all caught (round 38: 32)


ROWS: list[Row] = [
    # ---- code: the byte-identical asm build (M1) and what C++ will add to it
    Row("code-hash", "matching gate: lint + gen asm (ARM and Thumb) + compile C++ + link + hash (build.py all)",
        needs=("rom:code", "toolchain"), dynamic_needs=armcc_needs,
        cmd=["{py}", "{root}/tools/build.py", "all"], timeout=1800,
        require=(rf"^code\.bin OK\s+sha1 {EXPECTED_CODE_SHA1}",),
        reject=(r"^Traceback \(most recent call last\):", r"^\S+\s+FAIL\b"),
        note_rx=(r"^(thumb_insn\s+\d+)", r"^(linked \d+ C\+\+ function\(s\).*)$")),
    Row("lint", "config/src_map.csv + data_map.csv + NONMATCHING spelling (build.py lint)",
        cmd=["{py}", "{root}/tools/build.py", "lint"], timeout=300, require=(r"^lint: OK",),
        note_rx=(r"^(lint: .*)$",)),
    Row("m1-tests", "clean/determinism, mutation and shift tests of the asm build (m1_tests.py all)",
        needs=("rom:code", "toolchain"), dynamic_needs=armcc_needs, cost="medium",
        cmd=["{py}", "{root}/tools/m1_tests.py", "all"], timeout=3600,
        require=(r"^== summary: clean PASS, mutation PASS, shift PASS",),
        note_rx=(r"^== summary: (.*)$",)),
    Row("diff-func", "every src_map function compiled alone vs the original (diff_func.py --all)",
        needs=("rom:code", "toolchain"), dynamic_needs=armcc_needs,
        cmd=["{py}", "{root}/tools/diff_func.py", "--all"], timeout=1800,
        require=(r"^summary: .* 0 matched row\(s\) failing",),
        note_rx=(r"^summary: (.*)$",)),
    Row("gen-headers", "generated class headers compile and match RTTI layouts (gen_headers.py check)",
        needs=("toolchain", "file:config/naming/classes.csv"),
        cmd=["{py}", "{root}/tools/gen_headers.py", "check"], timeout=1200,
        require=(r"^RESULT: PASS",), note_rx=(r"^(problems: \d+)",)),
    # ---- symbols: the function registry from the game's own symbol map (docs/SYMBOLS.md)
    Row("symbols", "function registry tests: tiling, ARM/Thumb alignment, calls are starts, reviewed "
        "boundaries (fates/test_symbols.py)",
        cost="medium", cmd=["{py}", "{root}/tools/fates/test_symbols.py"], timeout=900,
        require=(r"^OK\b",), reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK.*)$")),
    Row("symbols-spotcheck", "symbol names checked against the code: SVC numbers, strings, vtables "
        "(fates/spotcheck.py)",
        needs=("rom:code", "rom:romfs"), cmd=["{py}", "{root}/tools/fates/spotcheck.py"], timeout=600,
        require=(r"^spotcheck: ok",), note_rx=(r"^(1\. .*)$",)),
    Row("symbols-flow", "control-flow walker self-test used for function boundaries (fates/flow.py)",
        cmd=["{py}", "{root}/tools/fates/flow.py"], timeout=300,
        require=(r"^flow selftest: 0 failures",), note_rx=(r"^(flow selftest: .*)$",)),
    # ---- tables (docs/TABLES.md)
    Row("tables-test", "table layouts, rebuild, edit and code-evidence tests (tables/test_tables.py)",
        needs=("rom:romfs",), cost="medium", cmd=["{py}", "{root}/tools/tables/test_tables.py"],
        timeout=900, require=(r"^OK\b",), reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$",)),
    Row("tables-gen", "generated field docs and C structs current, structs compile with offset asserts "
        "(tables/gen.py check)",
        needs=("toolchain",), cmd=["{py}", "{root}/tools/tables/gen.py", "check"], timeout=300,
        require=(r"^generated files up to date",), note_rx=(r"^(structs: .*)$",)),
    Row("tables-check", "data-table layouts vs every record, plus broken-layout self-test (tables/check.py)",
        needs=("rom:romfs",), cmd=["{py}", "{root}/tools/tables/check.py", "--selftest"], timeout=900,
        require=(r"^(\d+)/\1 layouts pass", r"^self-test: (\d+)/\1 mutated layouts rejected"),
        note_rx=(r"^(\d+/\d+ layouts pass.*)$", r"^self-test: (.*)$")),
    Row("tables-rebuild", "table files rebuilt from the dumps, byte-identical (tables/build.py --check)",
        needs=("rom:romfs",), cmd=["{py}", "{root}/tools/tables/build.py", "--check", "--no-write"],
        timeout=900, require=(r"^rebuilt .*: (\d+)/\1 byte-identical",),
        note_rx=(r"^rebuilt (.*)$",)),
    # ---- assets (docs/ASSETS.md)
    Row("assets-quick", "RomFS sample (3 per directory/extension) through the asset round-trip chain",
        needs=("rom:romfs",), cost="medium", cmd=assets_quick_cmd(), timeout=900,
        require=(r"^ASSETS QUICK: (\d+)/\1 ",), note_rx=(r"^ASSETS QUICK: (.*)$",)),
    Row("assets-bch", "BCH texture edit self-test: non-ETC with mips, ETC1A4, stored file, a portrait "
        "resized up and down, a bad size refused (assets/bch.py selftest)",
        needs=("rom:romfs",), cost="medium", cmd=["{py}", "{root}/tools/assets/bch.py", "selftest"],
        timeout=900, require=(r"^\s+PASS nonetc_mips:", r"^\s+PASS etc:", r"^\s+PASS stored:",
                              r"^\s+PASS resize doubled:", r"^\s+PASS resize halved:",
                              r"^\s+PASS refuse non-power-of-two"),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+(?:FAIL|SKIP)\s"),
        note_rx=(r"^\s+PASS (stored: .*)$",)),
    Row("assets-bchwrite", "relocating BCH writer self-test: made-up files grown, shrunk, re-formatted, "
        "refusals, relocation scan, 4 game samples (assets/bchwrite.py selftest)",
        needs=("rom:romfs",), cost="medium", cmd=["{py}", "{root}/tools/assets/bchwrite.py", "selftest"],
        timeout=900, require=(r"^\s+PASS synthetic: two textures resized at once",
                              r"^\s+PASS synthetic: coverage scan notices removed relocations",
                              r"^\s+PASS ROM "),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+(?:FAIL|SKIP)\s"),
        note_rx=(r"^\s+PASS (synthetic: coverage scan .*)$",)),
    Row("assets-bchwrite-all", "every BCH in the game through the relocating writer: unedited identical, "
        "relocation scan, every texture resized and restored (assets/bchwrite.py test, ~1.5 min)",
        needs=("rom:romfs",), cost="slow", cmd=["{py}", "{root}/tools/assets/bchwrite.py", "test"],
        timeout=3600, require=(r"^\s+unedited rebuild through the relocating writer identical: (\d+)/\1$",
                               r"^\s+relocation coverage scan clean .*: (\d+)/\1$",
                               r"^\s+textures resized .*: (\d+)/\1 \("),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^\s+(unedited rebuild .*)$", r"^\s+(textures resized .*)$")),
    Row("assets-arc", "every .arc rebuilt from its members, byte-identical (assets/arc.py test)",
        needs=("rom:romfs",), cost="medium", cmd=["{py}", "{root}/tools/assets/arc.py", "test"],
        timeout=900, require=(r"^\.arc archives: (\d+)/\1 rebuild byte-identically",),
        note_rx=(r"^\.arc archives: (.*)$",)),
    Row("assets-portrait", "every portrait file exported to PNG layers and rebuilt, plus an edit test "
        "(assets/portrait.py test)",
        needs=("rom:romfs",), cost="slow", cmd=["{py}", "{root}/tools/assets/portrait.py", "test"],
        timeout=1800, require=(r"^portrait files exported to PNG and rebuilt byte-identically: (\d+)/\1 ",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^portrait files exported to PNG and rebuilt byte-identically: (.*)$",)),
    Row("assets-full", "every converter over the whole RomFS (assets/roundtrip_all.py, ~10 min)",
        needs=("rom:romfs",), cost="slow", cmd=["{py}", "{root}/tools/assets/roundtrip_all.py"],
        timeout=3600, require=(r"^ALL STAGES 100%",),
        note_rx=(r"(whole RomFS rebuilt from editable forms: \d+/\d+ files identical)",)),
    # ---- maps (docs/MAPS.md)
    Row("maps-test", "map tools: round trip, unit moves and additions, refusals, tile edits, preview "
        "(maps/test_maps.py)",
        needs=("rom:romfs",), cost="medium", cmd=["{py}", "{root}/tools/maps/test_maps.py"], timeout=900,
        require=(r"^OK\b",), reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$",)),
    Row("maps-roundtrip", "every Dispos and Terrain file through the map spreadsheets and back, "
        "byte-identical (maps/maps.py roundtrip)",
        needs=("rom:romfs",), cmd=["{py}", "{root}/tools/maps/maps.py", "roundtrip"], timeout=600,
        require=(r"^Dispos: (\d+)/\1 byte-identical; Terrain: (\d+)/\2 byte-identical",),
        note_rx=(r"^(Dispos: \d+/\d+ byte-identical; Terrain: \d+/\d+ byte-identical)",)),
    # ---- castle sheets (docs/CASTLE.md)
    Row("castle-test", "castle sheets: layouts vs files, byte-identical rebuilds, one-cell edits, dining "
        "row additions, refusals (castle/test_castle.py)",
        needs=("rom:romfs",), cmd=["{py}", "{root}/tools/castle/test_castle.py"], timeout=600,
        require=(r"^OK\b",), reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$",)),
    Row("castle-all", "every sheet-shaped RomFS file round-trips with its declared types; the malformed "
        "one is reported (castle/test_castle.py -k every, ~70 s)",
        needs=("rom:romfs",), cost="slow", cmd=["{py}", "{root}/tools/castle/test_castle.py", "-k", "every"],
        env={"FEF_CASTLE_ALL": "1"}, timeout=1800,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK$"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b", r"^OK \(skipped="),
        note_rx=(r"^(Ran \d+ tests? in .*)$",)),
    # ---- mods and the PLAY launcher (docs/MODDING.md, docs/PLAY.md)
    Row("mods-selftest", "data mods: diff/merge/conflicts/validation/install-uninstall in a temp folder (mods/mods.py selftest)",
        needs=("rom:romfs",), cost="medium", cmd=["{py}", "{root}/tools/mods/mods.py", "selftest"], timeout=600,
        require=(r"^mods selftest: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^mods selftest: (.*)$",)),
    Row("text-mods", "text, whole-file, map and portrait mods: parser, checks, conflicts, build, install "
        "and uninstall in a scratch Zakuro folder (tests.test_text_mods)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_text_mods"], timeout=900,
        require=(r"^OK\b",), reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$",)),
    Row("play-tests", "PLAY launcher: ROM check, saves, backups, settings, mods, in temp folders (tests.test_play)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_play"], timeout=900,
        require=(r"^OK\b",), reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$",)),
    Row("rando-page-tests", "PLAY RANDOMIZED page (F-041 #4): per-seed profile layout, stub and fake randomizer "
        "CLIs, seed rules, failed randomizer leaves nothing, guard against normal save places "
        "(tests.test_rando_profile; temp folders, no game)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_rando_profile"], timeout=600,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("sof-path-tests", "Seal of Flames optional path (rounds 52-53; the owner's own mod by Laz14, never tracked): "
        "sof.py install on synthetic zips (layout, idempotent, unsafe entries refused, nothing outside its profile "
        "and build/), start = PLAY's command + --game seal --seal-profile in the normal environment (no "
        "APPDATA/LOCALAPPDATA redirect, no FEF_RANDO_TOOL), PLAY.bat's Seal options, one-way save import; the "
        "code.ips host checks skip without extracted/code.bin or the installed code.ips (tests.seal.test_sof_path); "
        "round 84 (F-072): the Seal halves of the PLAY tests (the launcher's Seal row, --backup-seal, the roms/seal "
        "finder) and the Seal smoke set's shape (tests.seal.test_launcher_seal, test_play_seal, test_paths_seal, "
        "test_smoke_seal)",
        needs=("seal-edition",), edition="seal", cost="medium",
        cmd=["{py}", "-m", "unittest", "tests.seal.test_sof_path", "tests.seal.test_launcher_seal",
             "tests.seal.test_play_seal", "tests.seal.test_paths_seal", "tests.seal.test_smoke_seal"], timeout=900,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("randomizer-tests", "new-game randomizer slice 1 (F-041 #4-5): same seed byte-identical, legal classes, "
        "usable weapons, staff/door/vein user per route, stats in caps, only allowed cells; real-data tests "
        "(25 seeds x 3 switch sets, mods-tool diff) skip without the extracted tables (tests.test_randomizer)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_randomizer"], timeout=900,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-tracks-tests", "randomizer round-49 tracks (F-043): growth/base modes, skills, items/shops/rewards, "
        "enemy gear and classes, and the integrate step with the round-W1 modules (defaults = slice 1 byte for "
        "byte, W1 options at default change nothing, everything on: every guard + the four cross guards, modules "
        "independent, job_low gap closed, mods-tool diff, rando.py check, PLAY RANDOMIZED options, rules.json = "
        "modules); real-data tests skip without the extracted tables (tests.test_rando_integrate, _growth, "
        "_skills, _items, _enemies)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_rando_integrate", "tests.test_rando_growth",
                          "tests.test_rando_skills", "tests.test_rando_items", "tests.test_rando_enemies"], timeout=1800,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-ingame-tests", "in-game randomizer, Python side (F-044 addendum, round 50; rows of round W1): "
        "rando.py schema = PLAY RANDOMIZED's lists in WIRE_56's order (rows the core cannot lay yet grey: the full "
        "swap look, one rank higher, recruits first; music and shuffle live since round 59, Nuzlocke live since "
        "round 60 and in PLAY RANDOMIZED since round 61), route-variant skill rows laid as person files, make --patch-out laid on memory images of the original files = the mods tool's "
        "rebuilt files (4 seeds, one with every W1 table-only option), PersonChapter options refused with the "
        "reason, guard refuses a second apply, revert = original; real-data tests skip without the extracted "
        "tables (tests.test_rando_ingame)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_rando_ingame"], timeout=900,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-more-tracks-tests", "randomizer round-55 modules (F-046): children, promotions, music, Nuzlocke rules "
        "(made-up tables over many seeds, every guard, job_low follows the final promotions, low_also rows); "
        "real-data tests skip without the extracted tables (tests.test_rando_children, _promotions, _music, "
        "_nuzlocke)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_rando_children", "tests.test_rando_promotions",
                          "tests.test_rando_music", "tests.test_rando_nuzlocke"], timeout=1800,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-r56-tracks-tests", "randomizer round-56 modules (F-046): weapon stats/traits and stronger enemy "
        "weapons (never losing an effective bonus), class/enemy/boss stats (boss gain follows the story), enemy "
        "drops, class movement (the three Fates class pairs as one, promoted upper bound), assign evenly via "
        "make_plan(classes=); real-data tests skip without the extracted tables (tests.test_rando_weapons, "
        "_stats, _misc)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_rando_weapons", "tests.test_rando_stats",
                          "tests.test_rando_misc"], timeout=1800,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-r63-boss-might", "randomizer round-63 tougher-bosses weapon might (F-049, F-051): +1 / +2 / +3 "
        "might as the player sees it on Easy / Normal / Hard (forge row picked as the game does: unknown_49 for "
        "enemies and bosses, refine_index for a playable person), capped at forge 7 with a spoiler note, and an "
        "independent shown-might recompute over the made runs; real-data tests skip without the extracted tables "
        "(tests.test_rando_boss_might)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_rando_boss_might"], timeout=1800,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-r64-seal-bosses", "randomizer round-64 Seal of Flames boss list (F-049 for Seal): seal_rules.json's "
        "boss_classes block comes from config/seal/seal_bosses.json (ids only, Fates' never-change list kept), "
        "rules.json's Fates list is unchanged, final and dragon forms never on the Seal list, every listed Seal boss "
        "may change and a seed changes each one; real-data tests skip without the extracted tables or the installed "
        "mod (tests.seal.test_rando_seal_bosses)",
        needs=("seal-edition",), edition="seal", cost="medium",
        cmd=["{py}", "-m", "unittest", "tests.seal.test_rando_seal_bosses"], timeout=1800,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-r62-tracks-tests", "randomizer round-62 picks (F-049): growth floor (every randomized total "
        "growth 20-100, zeros raised, Move untouched, spoiler = laid tables), weapon ladder per difficulty (one rung "
        "or a forge, kept weapons never move, guard catches a sidegrade or a leap), tier-matched boss classes with "
        "the never-change list (incl. the singer) and the scaled tougher-bosses boost, Seal Children grey; "
        "real-data tests skip without the extracted tables (tests.test_rando_r62)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_rando_r62"], timeout=1800,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-recruit-tests", "randomizer character shuffle module (F-046, round 56; not wired until W2): "
        "who joins where, keep the face and full identity plans, every guard (tests.test_rando_recruit; about "
        "90 s, so slow / weekly, F-028)",
        cost="slow", cmd=["{py}", "-m", "unittest", "tests.test_rando_recruit"], timeout=1800,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-seal-tests", "randomizer for Seal of Flames (F-047, round 58): sources.activate builds the mod's "
        "layered tables, seal_rules.json = the rules rebuilt from the mod's data, everything on / shuffle / music / "
        "Nuzlocke on five seeds with every guard green, guarded chapters keep their enemies, the core's make "
        "patch lays on Seal and is refused on Fates, back to Fates after activate('fates'); skips without the "
        "extracted tables or the installed mod (tests.seal.test_rando_seal; about 140 s)",
        needs=("seal-edition",), edition="seal", cost="medium",
        cmd=["{py}", "-m", "unittest", "tests.seal.test_rando_seal"], timeout=1800,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-ingame-core", "in-game randomizer, engine core (F-044, rounds 50-51 and 53, patches 0007/0008/0010/0011; off for Seal of Flames via Config::fates_rando): "
        "zakuro-core unit tests on fake memory: patch parse/guard/apply/revert, mode-pick watch, a load is not a "
        "new game, save side files on every save read, state side files, placement files patched in the read "
        "(LZ11, IS .bin), Python started with CREATE_NO_WINDOW; cargo build, so slow (weekly, F-028)",
        needs=("file:engine/zakuro/Cargo.toml",), cost="slow",
        cmd=["cargo", "test", "--manifest-path", "{root}/engine/zakuro/Cargo.toml", "-p", "zakuro-core", "--lib",
             "--target-dir", "{root}/engine/target/zakuro-core-test"], timeout=3600,
        require=(r"^test result: ok\. [1-9]\d* passed; 0 failed",),
        reject=(r"^Traceback \(most recent call last\):", r"^test result: FAILED", r"^error(\[E\d+\])?:"),
        note_rx=(r"^(test result: .*)$",)),
    Row("rando-ingame-page", "in-game randomizer, the Randomizer page (F-044, round 51, patch 0009): RandoForm rows, "
        "defaults, Everything on, seed rules, answers JSON, Python hidden, This run; no window "
        "(cargo test -p zakuro --lib rando; slow, weekly)",
        needs=("file:engine/zakuro/Cargo.toml",), cost="slow",
        cmd=["cargo", "test", "--manifest-path", "{root}/engine/zakuro/Cargo.toml", "-p", "zakuro", "--lib",
             "--target-dir", "{root}/engine/target/zakuro-core-test", "--", "rando"], timeout=3600,
        require=(r"^test result: ok\. [1-9]\d* passed; 0 failed",),
        reject=(r"^Traceback \(most recent call last\):", r"^test result: FAILED", r"^error(\[E\d+\])?:"),
        note_rx=(r"^(test result: .*)$",)),
    Row("game-picker-page", "Choose your game page (round 53, patch 0012; Seal of Flames by Laz14 shown only when "
        "installed): picker state and pre-select, remembered choice (command line, then variable, then file), "
        "installed check by names, Seal game settings kept apart and the owner's put back, hidden isolated "
        "install, --game parse, report ranges; no window "
        "(cargo test -p zakuro --lib game_pick the_game_to_pick report_ranges; slow, weekly)",
        needs=("file:engine/zakuro/Cargo.toml",), cost="slow",
        cmd=["cargo", "test", "--manifest-path", "{root}/engine/zakuro/Cargo.toml", "-p", "zakuro", "--lib",
             "--target-dir", "{root}/engine/target/zakuro-core-test", "--", "game_pick", "the_game_to_pick",
             "report_ranges"], timeout=3600,
        require=(r"^test result: ok\. [1-9]\d* passed; 0 failed",),
        reject=(r"^Traceback \(most recent call last\):", r"^test result: FAILED", r"^error(\[E\d+\])?:"),
        note_rx=(r"^(test result: .*)$",)),
    Row("engine-selftest", "engine chain: patch apply logic on a throwaway repo + port helpers; builds nothing "
        "(engine/engine.py selftest)",
        cost="medium", cmd=["{py}", "{root}/tools/engine/engine.py", "selftest"], timeout=900,
        require=(r"^engine selftest: (\d+)/\1",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(engine selftest: .*)$",)),
    # ---- screen extras (docs/EXTRAS.md)
    Row("extras-verify", "screen extras (60 fps battles and scenes, faster battles, 16:9): every patch site "
        "checked against extracted/code.bin, original bytes by SHA-1 and the instruction shapes around it "
        "(extras/usa_extras.py verify, Fates' native map config/extras/fe14.json; writes nothing)",
        needs=("rom:code", "toolchain"),
        cmd=["{py}", "{root}/tools/extras/usa_extras.py", "verify"], timeout=300,
        require=(r"^\d+ words in [1-9]\d* extras: all check out$",),
        reject=(r"^Traceback \(most recent call last\):", r"^\[ NO\]", r"SOME FAIL", r"^refusing"),
        note_rx=(r"^(\d+ words in .*)$",)),
    # ---- readable layer and test robot (docs/READABLE.md, docs/HARNESS.md)
    Row("readable", "readable layer: lint, compile vs stub, staged files, host test, broken inputs, "
        "verify-pipeline self-test (readable/check.py --selftest)",
        needs=("host-cc",), cost="medium", cmd=["{py}", "{root}/tools/readable/check.py", "--selftest"], timeout=600,
        require=(r"^readable: OK$", r"^verify pipeline self-test: (\d+)/\1 checks passed"),
        note_rx=(r"^(host test: .*)$", r"^(self-test: .*)$")),
    Row("harness-selftest", "test robot on fakelib: ABI gate, capture runtime records, live vs offline replay, "
        "original-vs-original, planted bugs, damaged records, targets.csv vs registry, probe stubs and "
        "capture-library staging (harness/harness.py --selftest)",
        needs=("host-cc",), cost="medium", cmd=["{py}", "{root}/tools/harness/harness.py", "--selftest"], timeout=600,
        require=(r"^harness selftest: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(harness selftest: .*)$",)),
    Row("gen-stubs-selftest", "targets.csv and probe stubs: kinds override / probe / writer, a writer row is never "
        "stubbed and never probed, guard tags against code.bin, on made-up inputs (harness/gen_stubs.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/gen_stubs.py", "--selftest"], timeout=300,
        require=(r"^gen_stubs self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(gen_stubs self-test: .*)$",)),
    Row("gen-stubs-check", "config/harness/targets.csv against the registry: every override listed, every guard "
        "user tagged (code.bin calls), writer rows OFF (harness/gen_stubs.py --check)",
        needs=("rom:code",),
        cmd=["{py}", "{root}/tools/harness/gen_stubs.py", "--check"], timeout=300,
        require=(r"^targets: OK \(\d+ override\(s\), .*never stubbed\)$",),
        reject=(r"^Traceback \(most recent call last\):", r"^targets: \d+ problem"),
        note_rx=(r"^targets: (OK .*)$",)),
    Row("markers-selftest", "test robot screen markers: process walk, game-state reads (gold, supports, veins, "
        "pairs, levels keyed by person with repeats, forge levels 0..63 with flag bits, ore, the 19 saved option bytes "
        "of GameConfigData) on made-up memory "
        "(harness/markers.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/markers.py", "--selftest"], timeout=300,
        require=(r"^markers self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(markers self-test: .*)$",)),
    Row("build-selftest", "capture-library build on a fake 3dsrecomp: staging only git-tracked readable files, writer rows never staged as markers, --swap with the old DLL loaded (harness/build.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/build.py", "--selftest"], timeout=300,
        require=(r"^harness build self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s*FAIL\b"),
        note_rx=(r"^(harness build self-test: .*)$",)),
    Row("fastlook-selftest", "robot look-ahead tool (F-023): chains, rollback resets the disk, verify judge, without a game run (harness/robot/fastlook.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/robot/fastlook.py", "--selftest"], timeout=300,
        require=(r"^fastlook selftest: (\d+)/\1 ok",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s*FAIL\b"),
        note_rx=(r"^(fastlook selftest: .*)$",)),
    Row("splitcfg-selftest", "shared routes.json / markers.json writer: only the own key changes, other keys byte-identical, temp + rename (harness/robot/splitcfg.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/robot/splitcfg.py", "--selftest"], timeout=300,
        require=(r"^splitcfg selftest: (\d+)/\1 ok",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s*FAIL\b"),
        note_rx=(r"^(splitcfg selftest: .*)$",)),
    Row("offline-selftest", "offline replay of stored records (owner OK C): source gate, compare exit codes, escaped counted, one-sided routes (harness/offline.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/offline.py", "--selftest"], timeout=300,
        require=(r"^offline selftest: OK",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s*FAIL\b"),
        note_rx=(r"^(offline selftest: .*)$",)),
    Row("h6cache-selftest", "H6 result cache (owner OK A of the speed plan): keys, a failed store never stops a run (harness/h6cache.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/h6cache.py", "--selftest"], timeout=300,
        require=(r"^h6cache self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s*FAIL\b"),
        note_rx=(r"^(h6cache self-test: .*)$",)),
    Row("h6sample-selftest", "H6 sampled mode (F-024): block cover kept, one record per input signature, content order, sample folder bytes (harness/h6sample.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/h6sample.py", "--selftest"], timeout=300,
        require=(r"^h6sample self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s*FAIL\b"),
        note_rx=(r"^(h6sample self-test: .*)$",)),
    Row("testcache-selftest", "check_all result cache: 7-day refusal, compiler change refused, a FAIL never stored (testcache.py selftest)",
        cmd=["{py}", "{root}/tools/testcache.py", "selftest"], timeout=300,
        require=(r"^testcache selftest: (\d+)/\1 ok",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s*FAIL\b"),
        note_rx=(r"^(testcache selftest: .*)$",)),
    Row("harness-levelups", "level-up listing from marker runs, on made-up marker sessions "
        "(harness/levelups.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/levelups.py", "--selftest"], timeout=120,
        require=(r"^levelups self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(levelups self-test: .*)$",)),
    # cheat track (docs/CHEATS.md, DECISIONS F-entry 2026-11-13): pokes only in the robot's own test runs
    Row("cheats-selftest", "test robot cheat track: poke paths through config/readable layouts, FCRAM mapping, "
        "savestate patching, route rules (harness/cheats.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/cheats.py", "--selftest"], timeout=120,
        require=(r"^cheats self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(cheats self-test: .*)$",)),
    Row("rando-colours-tests", "randomizer recolour (round 59, F-047): model table and FaceData parsed to the "
        "terminator, a swapped spot gets the filler's hair cell and FaceData colour (taken from the original tables, "
        "so a cycle never chains), boss copies skipped, own hair rows kept in new classes, pictures option, patch "
        "lines; real-data tests skip without the extracted tables (tests.test_rando_colours)",
        cost="medium", cmd=["{py}", "-m", "unittest", "tests.test_rando_colours"], timeout=900,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("rando-cache-tests", "randomizer table cache (round 59, F-047 start delay): a cached make is byte-identical "
        "to an uncached one, any game file / code / layout / argument change misses, the owner's rule host half "
        "(rows changed after a finished make = a fresh make of the final rows), progress lines in order "
        "(tests.test_rando_cache; about 4 min, so slow / weekly)",
        cost="slow", cmd=["{py}", "-m", "unittest", "tests.test_rando_cache"], timeout=1800,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK \(skipped=\d+\))$")),
    Row("engine-seal-person-name", "Seal of Flames battle save (round 59, patch 0018): a mod's chapter person file "
        "named after the file it was copied from is served under its own name, everything else left alone; the "
        "zakuro-fs Fix hook sees only the mod's files and no fix = the same image "
        "(cargo test -p zakuro-core -p zakuro-fs --lib person_name a_fix; slow, weekly)",
        needs=("file:engine/zakuro/Cargo.toml",), edition="seal", cost="slow",
        cmd=["cargo", "test", "--manifest-path", "{root}/engine/zakuro/Cargo.toml", "-p", "zakuro-core", "-p",
             "zakuro-fs", "--lib", "--target-dir", "{root}/engine/target/zakuro-core-test", "--", "person_name",
             "a_fix"], timeout=3600,
        require=(r"^test result: ok\. [1-9]\d* passed; 0 failed",),
        reject=(r"^Traceback \(most recent call last\):", r"^test result: FAILED", r"^error(\[E\d+\])?:"),
        note_rx=(r"^(test result: .*)$",)),
    Row("engine-seal-person-order", "Seal of Flames battle save and chapter people (round 60, patches 0022 and "
        "0023): a mod's person file whose numbers are its range reordered is numbered in file order (anything "
        "else left alone), and a randomized chapter person file too big for the read is found in the Person "
        "archive list by name to be laid in memory (cargo test -p zakuro-core --lib people_out_of_file_order "
        "numbers_that_are_not_a_reordering a_chapter_person_archive; slow, weekly)",
        needs=("file:engine/zakuro/Cargo.toml",), edition="seal", cost="slow",
        cmd=["cargo", "test", "--manifest-path", "{root}/engine/zakuro/Cargo.toml", "-p", "zakuro-core", "--lib",
             "--target-dir", "{root}/engine/target/zakuro-core-test", "--", "people_out_of_file_order",
             "numbers_that_are_not_a_reordering", "a_chapter_person_archive"], timeout=3600,
        require=(r"^test result: ok\. 3 passed; 0 failed",),
        reject=(r"^Traceback \(most recent call last\):", r"^test result: FAILED", r"^error(\[E\d+\])?:"),
        note_rx=(r"^(test result: .*)$",)),
    Row("engine-nuzlocke-core", "in-game Nuzlocke, engine core (round 60, patch 0024; round 61, patch 0025): deaths "
        "written at once and kept after a reload, a fallen unit moved back the way TransferImpl does it with the "
        "lists kept whole, Corrin never written and a unit on the map waits, graveyard file = the Python Ledger "
        "format, cp932 label keys, a run's nuzlocke.json means on, the gate is the player army (not GameConfigData "
        "+0xB, the camera angle), a death needs a living sighting and carries turn and name, a PLAY RANDOMIZED "
        "profile with Nuzlocke starts a Nuzlocke game (cargo test -p zakuro-core --lib nuzlocke; slow, weekly)",
        needs=("file:engine/zakuro/Cargo.toml",), cost="slow",
        cmd=["cargo", "test", "--manifest-path", "{root}/engine/zakuro/Cargo.toml", "-p", "zakuro-core", "--lib",
             "--target-dir", "{root}/engine/target/zakuro-core-test", "--", "nuzlocke"], timeout=3600,
        require=(r"^test result: ok\. (9|[1-9]\d+) passed; 0 failed",),
        reject=(r"^Traceback \(most recent call last\):", r"^test result: FAILED", r"^error(\[E\d+\])?:"),
        note_rx=(r"^(test result: .*)$",)),
    Row("engine-pagebot-hook", "real Randomizer page robot hook (round 61, patch 0026): the page reports where it "
        "draws each control and which guesses it threw away, for FEF_PAGEBOT only (cargo test -p zakuro --lib "
        "the_page_reports_its_controls; frontend build, so slow, weekly)",
        needs=("file:engine/zakuro/Cargo.toml",), cost="slow",
        cmd=["cargo", "test", "--manifest-path", "{root}/engine/zakuro/Cargo.toml", "-p", "zakuro", "--lib",
             "--target-dir", "{root}/engine/target/zakuro-frontend-test", "--", "the_page_reports_its_controls"],
        timeout=3600,
        require=(r"^test result: ok\. 1 passed; 0 failed",),
        reject=(r"^Traceback \(most recent call last\):", r"^test result: FAILED", r"^error(\[E\d+\])?:"),
        note_rx=(r"^(test result: .*)$",)),
    Row("audioproof-selftest", "music proven by sound (round 61): the WAV fingerprint of boot-server's audio "
        "command recordings on synthetic tones, the same tone about 1 and another tone low; no live run "
        "(harness/audioproof.py selftest)",
        cmd=["{py}", "{root}/tools/harness/audioproof.py", "selftest"], timeout=120,
        require=(r"^audioproof selftest: same 0\.9\d+ other -?0\.\d+ OK$",),
        reject=(r"^Traceback \(most recent call last\):", r"^audioproof selftest: .* FAIL"),
        note_rx=(r"^(audioproof selftest: .*)$",)),
    Row("smoke-selftest", "round smoke tool (round 67, release part A goal 5) on a fake runner: pass, fail, timeout, "
        "missing / wrong-sha input, a window kills everything, STOP_ROUND, lanes cap, the round-59 job rules, the "
        "memory judge, a baseline mismatch names the job and frame, a partial run never exits 0; no game "
        "(harness/smoke.py selftest = tests/test_smoke.py)",
        cmd=["{py}", "{root}/tools/harness/smoke.py", "selftest"], timeout=300,
        require=(r"^smoke selftest: (\d+)/\1 ok$",),
        reject=(r"^Traceback \(most recent call last\):", r"^smoke selftest: .* FAIL", r"^FAILED\b",
                r"^(FAIL|ERROR): "),
        note_rx=(r"^(smoke selftest: .*)$",)),
    Row("release-selftest", "the one-command release (round 68, release part B, docs/RELEASE.md): release.py step "
        "order, stop at the first failure, dry-run writes nothing, rehearse writes only its folder, tag free, FULL-due "
        "question, --yes refused for push/undo, undo keeps a pushed tag, CRLF .bat files; package.py zip/bundle/sums "
        "and every gate (planted private string in HEAD fails, in history only blocks the push, planted long byte "
        "run fails, notes masked); the two editions (Vanilla+ leave-out archive + edition gate + one-line credits, Seal "
        "edition full zip, both folders side by side, release.py packaging seal then vanilla); install.py backup/install/rollback/verify/undo in temp folders with fake files; "
        "nothing built, installed, tagged or pushed (release.py selftest = tests.test_release + test_package + "
        "test_install side by side; medium cost, about 40-60 s; in --core through CORE_EXTRA)",
        cost="medium", cmd=["{py}", "{root}/tools/release/release.py", "selftest"], timeout=900,
        require=(r"^release selftest: ([1-9]\d*)/\1 tests passed\b",),
        reject=(r"^Traceback \(most recent call last\):", r"^release selftest: .* FAIL", r"^FAILED\b",
                r"^(FAIL|ERROR): "),
        note_rx=(r"^(release selftest: .*)$",)),
    Row("smoke-set", "the live round smoke (round 67, docs/harness/SMOKE.md; the Vanilla+ set since round 84, "
        "F-072): Birthright A011, Conquest B016, Revelation C012, each randomizer off and everything-on all1 re-made "
        "with today's code, plus the randomizer-off memory compare at boot/3000/4600/5200/end, against "
        "config/harness/smoke_baseline.json; headless frozen copies in build/fixtures/smoke, 2 lanes; a missing "
        "input FAILS (harness/smoke.py run; slow, runs alone; the release core runs it as its own step)",
        needs=("rom:romfs",), cost="slow", cmd=["{py}", "{root}/tools/harness/smoke.py", "run", "--lanes", "2"],
        timeout=1800,
        require=(r"^PASS: jobs 6/6, memory compare equal, baseline equal\b",),
        reject=(r"^Traceback \(most recent call last\):", r"^FAIL\b", r"^MISMATCH: ", r"^PARTIAL\b",
                r"^STOPPED\b"),
        note_rx=(r"^((?:PASS|FAIL): .*)$",)),
    Row("seal-smoke", "the Seal of Flames edition's smoke (round 84, F-072; docs/seal/CHECK.md, the small Seal "
        "check): Seal R011 randomizer off and everything-on all1 re-made with today's code, against "
        "config/seal/smoke_baseline.json; no memory compare (it boots Fates: the Vanilla+ set has it); the same "
        "frozen copies and the mod copy in build/fixtures/smoke, 2 lanes (harness/smoke.py --set "
        "config/seal/smoke_set.json run; slow, runs alone)",
        needs=("rom:romfs", "seal-edition"), edition="seal", cost="slow",
        cmd=["{py}", "{root}/tools/harness/smoke.py", "--set", "{root}/config/seal/smoke_set.json", "run",
             "--lanes", "2"], timeout=1800,
        require=(r"^PASS: jobs 2/2, baseline equal \(no memory compare in this set\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^FAIL\b", r"^MISMATCH: ", r"^PARTIAL\b",
                r"^STOPPED\b"),
        note_rx=(r"^((?:PASS|FAIL): .*)$",)),
    Row("pagebot-selftest", "robot for the real in-game Randomizer page (round 60): the judge on made-up page events (the owner's "
        "rule: rows changed after a finished make = a fresh make of the final rows, stale guesses dropped, nothing "
        "laid before Start game, Start game to avatar timing), no hook = refused, row plans; no live run "
        "(harness/pagebot.py selftest)",
        cmd=["{py}", "{root}/tools/harness/pagebot.py", "selftest"], timeout=120,
        require=(r"^pagebot selftest: (\d+)/\1$",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s*FAIL\s"),
        note_rx=(r"^(pagebot selftest: .*)$",)),
    Row("rcheck-selftest", "robot check driver (round 59): strict pairs (same screen, frame, history and unit; the "
        "setting's field differs; pixels differ; ON not byte-identical to another setting's ON); round 66: "
        "judge_boost's capped flag passes only when the ON base HP is max(OFF base HP, the boss's own HP cap from "
        "the run's tables, boss_hp_cap), a fake cap or no cap fails; no live run (harness/rcheck.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/rcheck.py", "--selftest"], timeout=120,
        require=(r"^rcheck selftest: (\d+)/\1$",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(rcheck selftest: .*)$",)),
    Row("chapsel-selftest", "test robot chapter select on the cheat track (round 58): world-map spot record "
        "and GameUserData patch plans, base-save choice per chapter, Seal of Flames spot lending, list-position "
        "search, no live run (harness/chapsel.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/chapsel.py", "--selftest"], timeout=120,
        require=(r"^chapsel selftest: (\d+)/\1$",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(chapsel selftest: .*)$",)),
    Row("cheat-routes", "the cheat-* routes of config/harness/routes.json and the packed start saves of "
        "real-play routes against docs/CHEATS.md's rules (harness/cheats.py --check)",
        cmd=["{py}", "{root}/tools/harness/cheats.py", "--check"], timeout=60,
        require=(r"^cheats: \d+ cheat route\(s\), rules OK$",),
        reject=(r"^Traceback \(most recent call last\):", r"is a cheat save"),
        note_rx=(r"^(real-play start saves: \d+ packed one\(s\) checked)", r"^cheats: (\d+ cheat route\(s\)), rules OK$")),
    Row("robot-routes", "real-play routes of all three campaigns (F-022): every verified bt-/cq-/rv-/opt- route has "
        "checkpoints, Conquest reads route byte 1 and Revelation 2, the branches start from bt-ch5-clear, start "
        "saves and the packed saves of rounds 8-12 exist when build/ is there", func=check_robot_routes, timeout=60),
    Row("cheat-endgame", "F-030/F-035: every cheat route of CHEAT_NO_CLEAR_SAVE (cheat-bt-endgame from bt-ch26-clear, "
        "cheat-rv-ch27 and cheat-rv-endgame from rv-ch26-clear, cheat-cq-ch27 and cheat-cq-endgame from "
        "cheat-cq-ch26-clear) is a declared cheat route with pokes (or a cheat start save) and "
        "checkpoints, and has no packed clear save (the game makes none after chapter 27 or Endgame)",
        func=check_cheat_endgame, timeout=60),
    Row("cheat-conquest", "F-033: every proven Conquest cheat route (CHEAT_CQ_PACKS: cheat-cq-ch17 from "
        "cq-ch16-clear, cheat-cq-ch18 to cheat-cq-ch26 each from the one before's cheat clear save) is a declared, "
        "verified cheat route with pokes (or a cheat start save) and checkpoints, and its packed clear save "
        "exists and carries the cheat mark", func=check_cheat_conquest, timeout=60),
    Row("headless-selftest", "headless runner: route rules, savestate LZ4 decoding, state digests, setup "
        "refusals, without a game run (harness/headless.py selftest)",
        cmd=["{py}", "-c", "import sys; sys.path.insert(0, r'{root}/tools/harness'); import headless; "
             "e, s = headless.selftest(); [print('  FAIL  ' + x) for x in e]; print(s); sys.exit(1 if e else 0)"],
        timeout=300, require=(r"^headless self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(headless self-test: .*)$",)),
    Row("parallel-tests", "side-by-side robot runs: budget, priority, job objects, saves, determinism verdict, "
        "a capture run FAILs on any mismatch record, a cheat save never starts a real-play route or packs under a "
        "plain name, --store-keep keeps every sampled record for H5/H6, with fake child commands (harness/test_parallel.py)",
        cost="medium",   # round 67: retagged from fast (recorded parallel-tests; F-052 runs it by name on readable edits)
        cmd=["{py}", "{root}/tools/harness/test_parallel.py"], timeout=600,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$",)),
    Row("watchdog-tests", "robot watchdogs (F-039 step 3): crash, hang, stuck frame (with allow-list), soft-lock and "
        "savestate round trip on made-up samples, each verdict one line with the press index; a corrupted reload is "
        "caught (harness/test_watchdog.py; no game)",
        cmd=["{py}", "{root}/tools/harness/test_watchdog.py"], timeout=120,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$",)),
    Row("parallel-smoke", "one real robot check: title x3 side by side and one after another, DETERMINISTIC "
        "with one memory hash, %APPDATA% untouched (harness/test_parallel.py --smoke; boot.exe, the capture "
        "library and the ROM)",
        needs=("rom:cci", "robot"), cost="slow", cmd=["{py}", "{root}/tools/harness/test_parallel.py", "--smoke"],
        timeout=1800, require=(r"^OK\b", r"^smoke: PASS: "),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b", r"^smoke: FAIL"),
        note_rx=(r"^smoke: PASS: (.*)$",)),
    Row("stance-armmini", "small ARM interpreter used by the stance comparison: self-test "
        "(src/readable/battle/tests/arm_mini.py)",
        cmd=["{py}", "{root}/src/readable/battle/tests/arm_mini.py"], timeout=120,
        require=(r"^arm_mini selftest: (\d+)/\1 checks passed",),
        note_rx=(r"^(arm_mini selftest: .*)$",)),
    Row("stance-diff", "Attack/Guard Stance: the game's ARM code against the readable C, 14 functions x 400 "
        "made-up cases (src/readable/battle/tests/stance_diff.py)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/battle/tests/stance_diff.py"], timeout=900,
        require=(r"^stance_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"^stance_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^stance_diff: (OK .*)$",)),
    Row("stance-diff-long", "the same stance comparison with another seed, 14 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/battle/tests/stance_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^stance_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"^stance_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^stance_diff: (OK .*)$",)),
    Row("triangle-diff", "weapon triangle and weapon ranks: the game's ARM code against the readable C, 13 "
        "functions x 400 made-up cases, and 18 planted bugs that must all be caught "
        "(src/readable/battle/tests/triangle_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/battle/tests/triangle_diff.py", "--plant"], timeout=1200,
        require=(r"^triangle_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT",
                r"^triangle_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^triangle_diff: (OK .*)$",)),
    Row("triangle-diff-long", "the same triangle comparison with another seed, 13 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/battle/tests/triangle_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^triangle_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"^triangle_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^triangle_diff: (OK .*)$",)),
    Row("vein-diff", "dragon veins: the game's ARM code against the readable C, 8 functions x 400 made-up "
        "cases (out-of-range inputs included), and the planted bugs that must all be caught "
        "(src/readable/map/tests/vein_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/map/tests/vein_diff.py", "--plant"], timeout=1800,
        require=(r"^vein_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT",
                r"^vein_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^vein_diff: (OK .*)$",)),
    Row("vein-diff-long", "the same dragon vein comparison with another seed, 8 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/map/tests/vein_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^vein_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"^vein_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^vein_diff: (OK .*)$",)),
    Row("formula-diff", "battle formulas (stats, attack, hit, avoid, crit, crit avoid, follow-up, forecast): "
        "the game's ARM code against the readable C, 23 functions x 300 made-up cases, unmapped reads and "
        "ItemSubKind::Get calls compared, and 31 planted bugs that must all be caught (src/readable/battle/tests/formula_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/battle/tests/formula_diff.py", "--plant"], timeout=2400,
        require=(r"^formula_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # formula_diff does not compare early give-ups, so an override that always gives up would still
        # say OK: 90 or more early give-ups of a function's 300 cases (30 %) fail the row (2026-11-12: at most 15)
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT",
                r"could not run", r"^formula_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^formula_diff: (OK .*)$",)),
    Row("formula-diff-long", "the same formula comparison with another seed, 23 functions x 1000 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/battle/tests/formula_diff.py", "-n", "1000", "--seed", "7"],
        timeout=3600,
        require=(r"^formula_diff: OK \(\d+ cases, 0 mismatches\)",),
        # 300 or more early give-ups of a function's 1000 cases (30 %) fail the row, as in formula-diff
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^formula_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[3-9]\d{2}) early give-ups"),
        note_rx=(r"^formula_diff: (OK .*)$",)),
    Row("growth-diff", "growth, level-up and experience: the game's ARM code against the readable C, 26 "
        "functions x 300 made-up cases, r0, unmapped reads and the ordered list of guest calls compared, and 37 "
        "planted bugs (a nested give-up is a mismatch) that must all be caught (src/readable/unit/tests/growth_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/unit/tests/growth_diff.py", "--plant"], timeout=2400,
        require=(r"^growth_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # as in formula-diff: 90 or more early give-ups of a function's 300 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT",
                r"could not run", r"^growth_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^growth_diff: (OK .*)$",)),
    Row("growth-diff-long", "the same growth comparison with another seed, 26 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/unit/tests/growth_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^growth_diff: OK \(\d+ cases, 0 mismatches\)",),
        # 450 or more early give-ups of a function's 1500 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^growth_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^growth_diff: (OK .*)$",)),
    Row("skill-diff", "skill readers (has-skill checks, skill records, activation chance, attack-skill pick): "
        "the game's ARM code against the readable C, 17 functions x 300 made-up cases, r0, unmapped reads and the "
        "ordered list of guest calls compared, a nested give-up is a mismatch, and 34 planted bugs that must all "
        "be caught (src/readable/skill/tests/skill_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/skill/tests/skill_diff.py", "--plant"], timeout=2400,
        require=(r"^skill_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # as in formula-diff: 90 or more early give-ups of a function's 300 cases (30 %) fail the row
        # (2026-11-13: at most 30, battle_attack_skill_pick, which asks 16 caches first; 26 with the menus batch's generator)
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT",
                r"could not run", r"^skill_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^skill_diff: (OK .*)$",)),
    Row("skill-diff-long", "the same skill comparison with another seed, 17 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/skill/tests/skill_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^skill_diff: OK \(\d+ cases, 0 mismatches\)",),
        # 450 or more early give-ups of a function's 1500 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^skill_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^skill_diff: (OK .*)$",)),
    Row("menu-diff", "option readers (the options screen's values, battle picture or map, game speed, HP bars, "
        "danger zone): the game's ARM code against the readable C, 22 functions x 300 made-up cases, r0, unmapped "
        "reads and the ordered list of guest calls compared, a nested give-up is a mismatch, and 41 planted bugs "
        "that must all be caught (src/readable/menu/tests/menu_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/menu/tests/menu_diff.py", "--plant"], timeout=2400,
        require=(r"^menu_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # as in formula-diff: 90 or more early give-ups of a function's 300 cases (30 %) fail the row
        # (2026-11-14: at most 38, battle_picture_choice, which asks four caches first)
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT",
                r"could not run", r"^menu_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^menu_diff: (OK .*)$",)),
    Row("menu-diff-long", "the same option-reader comparison with another seed, 22 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/menu/tests/menu_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^menu_diff: OK \(\d+ cases, 0 mismatches\)",),
        # 450 or more early give-ups of a function's 1500 cases (30 %) fail the row (2026-11-14: at most 183)
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^menu_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^menu_diff: (OK .*)$",)),
    Row("sheet-diff", "status-sheet readers (defence, resistance, maximum HP and the HP window, move, class categories, "
        "equipped and held item, item count, shown and low level, shortest range, may-not-attack, unique, special battle, "
        "invisible, capturable): the game's ARM code against the readable C, 19 functions x 300 made-up cases, r0, unmapped "
        "reads and the ordered list of guest calls compared, a nested give-up is a mismatch, and 40 planted bugs that must "
        "all be caught (src/readable/sheet/tests/sheet_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/sheet/tests/sheet_diff.py", "--plant"], timeout=2400,
        require=(r"^sheet_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # as in formula-diff: 90 or more early give-ups of a function's 300 cases (30 %) fail the row
        # (2026-11-13: 0 early give-ups in every function)
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT",
                r"could not run", r"^sheet_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^sheet_diff: (OK .*)$",)),
    Row("sheet-diff-long", "the same status-sheet comparison with another seed, 19 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/sheet/tests/sheet_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^sheet_diff: OK \(\d+ cases, 0 mismatches\)",),
        # 450 or more early give-ups of a function's 1500 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^sheet_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^sheet_diff: (OK .*)$",)),
    # round 10 reader batches (docs/ITEM.md, docs/MOVE.md, docs/SUPPORT.md), read only
    Row("item-diff", "item readers (item record, kind, forge bonus, weapon / magic / staff tests, uses, price, range): the game's ARM code against the readable C, 25 functions x 300 made-up cases, r0, "
        "unmapped reads and the ordered list of guest calls compared, a nested give-up is a mismatch, and 52 planted "
        "bugs that must all be caught (src/readable/item/tests/item_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/item/tests/item_diff.py", "--plant"], timeout=2400,
        require=(r"^item_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # 90 or more early give-ups of a function's 300 cases (30 %) fail the row (round 10 batch: at most 4 %)
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT",
                r"could not run", r"^item_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^item_diff: (OK .*)$",)),
    Row("item-diff-long", "the same item comparison with another seed, 25 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/item/tests/item_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^item_diff: OK \(\d+ cases, 0 mismatches\)",),
        # 450 or more early give-ups of a function's 1500 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^item_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^item_diff: (OK .*)$",)),
    Row("move-diff", "movement readers (map tiles, terrain records, the class cost table, cost of a tile for a unit, occupancy, deploy): the game's ARM code against the readable C, 24 functions x 300 made-up cases, r0, "
        "unmapped reads and the ordered list of guest calls compared, a nested give-up is a mismatch, and 48 planted "
        "bugs that must all be caught (src/readable/move/tests/move_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/move/tests/move_diff.py", "--plant"], timeout=2400,
        require=(r"^move_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # 90 or more early give-ups of a function's 300 cases (30 %) fail the row (round 10 batch: at most 4 %)
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT",
                r"could not run", r"^move_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^move_diff: (OK .*)$",)),
    Row("move-diff-long", "the same move comparison with another seed, 24 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/move/tests/move_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^move_diff: OK \(\d+ cases, 0 mismatches\)",),
        # 450 or more early give-ups of a function's 1500 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^move_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^move_diff: (OK .*)$",)),
    Row("support-diff", "support readers (support records and chains, levels and points, family and sibling parts, S entries, trade partner): the game's ARM code against the readable C, 25 functions x 300 made-up cases, r0, "
        "unmapped reads and the ordered list of guest calls compared, a nested give-up is a mismatch, and 56 planted "
        "bugs that must all be caught (src/readable/support/tests/support_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/support/tests/support_diff.py", "--plant"], timeout=2400,
        require=(r"^support_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # 90 or more early give-ups of a function's 300 cases (30 %) fail the row (round 10 batch: at most 4 %)
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT",
                r"could not run", r"^support_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^support_diff: (OK .*)$",)),
    Row("support-diff-long", "the same support comparison with another seed, 25 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/support/tests/support_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^support_diff: OK \(\d+ cases, 0 mismatches\)",),
        # 450 or more early give-ups of a function's 1500 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^support_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^support_diff: (OK .*)$",)),
    # round 11 reader batches (docs/AI.md, docs/BATTLE2.md), read only; the AI attack-score batch is parked (F-025)
    Row("ai-perm-diff", "AI permission readers (attack / heal / item / escape / crossfire permission, active commands, "
        "AI item indexes, heal rod): the game's ARM code against the readable C, 18 functions x 300 made-up cases, r0, "
        "unmapped reads and the ordered list of guest calls compared, a nested give-up is a mismatch (round 18: a "
        "cold IsMagic / GetRangeO guard is a nested give-up, and heal-rod give-ups with warm caches count), and 48 "
        "planted bugs that must all be caught (src/readable/ai/tests/ai_perm_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/ai/tests/ai_perm_diff.py", "--plant"], timeout=2400,
        require=(r"^ai_perm_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # 90 or more early give-ups of a function's 300 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^ai_perm_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^ai_perm_diff: (OK .*)$",)),
    Row("ai-perm-diff-long", "the same AI permission comparison with another seed, 18 functions x 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/ai/tests/ai_perm_diff.py", "-n", "1500", "--seed", "7"], timeout=3600,
        require=(r"^ai_perm_diff: OK \(\d+ cases, 0 mismatches\)",),
        # 450 or more early give-ups of a function's 1500 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^ai_perm_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^ai_perm_diff: (OK .*)$",)),
    Row("battle2-diff", "battle numbers batch 3 (item stat bonus, forecast damage, phoenix / versus situation, promoted / "
        "giant class, rally skills ...): the game's ARM code against the readable C, 300 made-up cases per function, "
        "r0, unmapped reads and the ordered list of guest calls compared, and 39 planted bugs that must all be caught "
        "(src/readable/battle2/tests/battle2_diff.py --plant; one build folder, so never two at once: lock readable:battle2)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/battle2/tests/battle2_diff.py", "--plant"], timeout=2400,
        require=(r"^battle2_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^battle2_diff: (?:FAILED|SKIPPED)", r"^battle2_diff: .*failed", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^battle2_diff: (OK .*)$",)),
    Row("battle2-diff-long", "the same battle-numbers comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/battle2/tests/battle2_diff.py", "-n", "1500", "--seed", "7"], timeout=3600,
        require=(r"^battle2_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^battle2_diff: (?:FAILED|SKIPPED)", r"^battle2_diff: .*failed",
                r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^battle2_diff: (OK .*)$",)),
    # round 12 reader batches (docs/CLASS_CHANGE.md, docs/WEAPON_RANK.md), read only
    Row("class-change-diff", "class change and seals (ClassChange::GetType, Unit::IsRelianceInvalidForClassChange, "
        "Person::GetLowJobIndex, the battle's GetSealEffect and MergeSeal's pure helper): the game's ARM code against the "
        "readable C, 300 made-up cases per function, r0, unmapped reads and the ordered list of guest calls compared, and "
        "28 planted bugs that must all be caught (src/readable/class_change/tests/class_change_diff.py --plant; one "
        "build folder, so never two at once: lock readable:class_change)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/class_change/tests/class_change_diff.py", "--plant"], timeout=2400,
        require=(r"^class_change_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^class_change_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^class_change_diff: (OK .*)$",)),
    Row("class-change-diff-long", "the same class-change comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/class_change/tests/class_change_diff.py", "-n", "1500", "--seed", "7"],
        timeout=3600,
        require=(r"^class_change_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^class_change_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^class_change_diff: (OK .*)$",)),
    Row("weapon-rank-diff", "weapon rank (the script's UnitGetWeaponLevel, Unit::GetWeaponExpForJobIntro and "
        "CaclulateFirstWeaponExp's pure helper): the game's ARM code against the readable C, 300 made-up cases per "
        "function, r0, unmapped reads and the ordered list of guest calls (the tail call into WeaponLevel::GetLevel "
        "included) compared, and 23 planted bugs that must all be caught "
        "(src/readable/weapon_rank/tests/weapon_rank_diff.py --plant; one build folder: lock readable:weapon_rank)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/weapon_rank/tests/weapon_rank_diff.py", "--plant"], timeout=600,
        require=(r"^weapon_rank_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # 90 or more early give-ups of a function's 300 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^weapon_rank_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^weapon_rank_diff: (OK .*)$",)),
    Row("weapon-rank-diff-long", "the same weapon-rank comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/weapon_rank/tests/weapon_rank_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^weapon_rank_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^weapon_rank_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^weapon_rank_diff: (OK .*)$",)),
    # round 13 reader batches (docs/SHOP_PRICE.md, docs/CASTLE_JOIN.md), read only
    Row("shop-price-diff", "shop price (ItemBuyMenuItem::GetPrice and Transporter's 64-bit GetPrice helper, both halves "
        "folded): the game's ARM code against the readable C, 300 made-up cases per function, r0, unmapped reads and "
        "the ordered list of guest calls compared, and 22 planted bugs that must all be caught "
        "(src/readable/shop_price/tests/shop_price_diff.py --plant; one build folder: lock readable:shop_price)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/shop_price/tests/shop_price_diff.py", "--plant"], timeout=600,
        require=(r"^shop_price_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^shop_price_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^shop_price_diff: (OK .*)$",)),
    Row("shop-price-diff-long", "the same shop-price comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/shop_price/tests/shop_price_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^shop_price_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^shop_price_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^shop_price_diff: (OK .*)$",)),
    Row("castle-join-diff", "castle join offer (the selection rule of castle::JoinSequence::GetJoinPersonList, a "
        "helper on an already loaded file; the game function stores and is not an override): the game's whole ARM "
        "function against the readable C, 300 made-up cases, the stored list, return value, unmapped reads and the "
        "ordered list of guest calls compared, and 20 planted bugs that must all be caught "
        "(src/readable/castle_join/tests/castle_join_diff.py --plant; one build folder: lock readable:castle_join)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/castle_join/tests/castle_join_diff.py", "--plant"], timeout=600,
        require=(r"^castle_join_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        # 90 or more early give-ups of the function's 300 cases (30 %) fail the row
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^castle_join_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^castle_join_diff: (OK .*)$",)),
    Row("castle-join-diff-long", "the same castle-join comparison with another seed, 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/castle_join/tests/castle_join_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^castle_join_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^castle_join_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^castle_join_diff: (OK .*)$",)),
    # round 14 reader batches (docs/EQUIP_USE.md, docs/STAFF_RANGE.md; REWRITE_ORDER3 batches 1 and 2), read only
    Row("equip-use-diff", "equip check (Unit::CanItemEquip): the game's ARM code against the readable C, 300 made-up "
        "cases, r0, unmapped reads and the ordered list of guest calls compared; each of the 30 one-time cache guards "
        "made cold in turn (a cold guard must give up, every guard warm must equal the original), and 39 planted bugs "
        "that must all be caught (src/readable/equip_use/tests/equip_use_diff.py --plant; one build folder: lock "
        "readable:equip_use)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/equip_use/tests/equip_use_diff.py", "--plant"], timeout=900,
        require=(r"^equip_use_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^equip_use_diff: (?:FAILED|SKIPPED)", r"a guard was never cold",
                r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^equip_use_diff: (OK .*)$",)),
    Row("equip-use-diff-s7", "the same equip-check comparison and planted bugs on the seed-7 case set "
        "(equip_use_diff.py --seed 7 --plant; same build folder, so never beside equip-use-diff)",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/equip_use/tests/equip_use_diff.py", "--seed", "7", "--plant"], timeout=900,
        require=(r"^equip_use_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^equip_use_diff: (?:FAILED|SKIPPED)", r"a guard was never cold",
                r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^equip_use_diff: (OK .*)$",)),
    Row("staff-range-diff", "staff readers (Unit::GetRodHealPower, GetInterferenceRodHit, GetInterferenceRodAvoid): the "
        "game's ARM code against the readable C, 300 made-up cases per function, r0, unmapped reads and the ordered "
        "list of guest calls with the fifth stack word compared, and 36 planted bugs that must all be caught "
        "(src/readable/staff_range/tests/staff_range_diff.py --plant; one build folder: lock readable:staff_range)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/staff_range/tests/staff_range_diff.py", "--plant"], timeout=600,
        require=(r"^staff_range_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^staff_range_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^staff_range_diff: (OK .*)$",)),
    Row("staff-range-diff-long", "the same staff comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/staff_range/tests/staff_range_diff.py", "-n", "1500", "--seed", "7"],
        timeout=600,
        require=(r"^staff_range_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^staff_range_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^staff_range_diff: (OK .*)$",)),
    # round 15 reader batch (docs/CAPABILITY.md; REWRITE_ORDER3 batch 3), read only
    Row("capability-diff", "capability readers (Unit::GetCapabilityImpl, GetCapabilityRating, "
        "GetNoWeaknessCapabilityRating): the game's ARM code against the readable C, 300 made-up cases per function, "
        "r0, unmapped reads and the ordered list of guest calls with both stack words compared (stat 0's tail branch "
        "into GetMHPImpl is not a call: the original's GetMHPImpl runs on), and 35 planted bugs that must all be "
        "caught (src/readable/capability/tests/capability_diff.py --plant; one build folder: lock readable:capability)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/capability/tests/capability_diff.py", "--plant"], timeout=600,
        require=(r"^capability_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^capability_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^capability_diff: (OK .*)$",)),
    Row("capability-diff-long", "the same capability comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/capability/tests/capability_diff.py", "-n", "1500", "--seed", "7"],
        timeout=900,
        require=(r"^capability_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^capability_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^capability_diff: (OK .*)$",)),
    # round 16 reader batch (docs/SHOP_GREY.md; REWRITE_ORDER3 row 4), read only
    Row("shop-grey-diff", "shop buy-list readers (ItemBuyMenuItem::GetStock, IsPriceDisable, GetBuySellMax): the "
        "game's ARM code against the readable C, 300 made-up cases per function, r0, unmapped reads and the ordered "
        "list of guest calls compared, and 37 planted bugs that must all be caught "
        "(src/readable/shop_grey/tests/shop_grey_diff.py --plant; one build folder: lock readable:shop_grey)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/shop_grey/tests/shop_grey_diff.py", "--plant"], timeout=600,
        require=(r"^shop_grey_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^shop_grey_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^shop_grey_diff: (OK .*)$",)),
    Row("shop-grey-diff-long", "the same shop buy-list comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/shop_grey/tests/shop_grey_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^shop_grey_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^shop_grey_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^shop_grey_diff: (OK .*)$",)),
    # round 17 host tests for files that had none (ai_value, ai_think, event/flags, unit/forces), read only;
    # the shared leaf driver is src/readable/battle/tests/leaf_diff.py
    Row("ai-value-diff", "AI value and think leaves (src/readable/ai/ai_value.c and ai_think.c, 8 functions): the game's ARM code against the readable C, 300 made-up cases per function, r0, "
        "unmapped reads and the ordered list of guest calls compared, and 18 planted bugs that must all be caught "
        "(src/readable/ai/tests/ai_value_diff.py --plant; one build folder: lock readable:ai_value)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/ai/tests/ai_value_diff.py", "--plant"], timeout=600,
        require=(r"^ai_value_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^ai_value_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^ai_value_diff: (OK .*)$",)),
    Row("ai-value-diff-long", "the same ai_value comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/ai/tests/ai_value_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^ai_value_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^ai_value_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^ai_value_diff: (OK .*)$",)),
    Row("flags-diff", "event flag bit read (src/readable/event/flags.c): the game's ARM code against the readable C, 300 made-up cases per function, r0, "
        "unmapped reads and the ordered list of guest calls compared, and 7 planted bugs that must all be caught "
        "(src/readable/event/tests/flags_diff.py --plant; one build folder: lock readable:flags)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/event/tests/flags_diff.py", "--plant"], timeout=600,
        require=(r"^flags_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^flags_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^flags_diff: (OK .*)$",)),
    Row("flags-diff-long", "the same flags comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/event/tests/flags_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^flags_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^flags_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^flags_diff: (OK .*)$",)),
    Row("flags-diff-s424242", "the flags comparison on seed 424242, 400 cases: round 17's false mismatch (the case "
        "maker sent a read into text.bin, mapped only on the original side); round 18 fixed the case maker, this "
        "row keeps it fixed",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/event/tests/flags_diff.py", "-n", "400", "--seed", "424242"],
        timeout=900,
        require=(r"^flags_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^flags_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[2-9]\d{2}|1[2-9]\d) early give-ups"),
        note_rx=(r"^flags_diff: (OK .*)$",)),
    Row("forces-diff", "force (army) readers (src/readable/unit/forces.c, 3 functions): the game's ARM code against the readable C, 300 made-up cases per function, r0, "
        "unmapped reads and the ordered list of guest calls compared, and 14 planted bugs that must all be caught "
        "(src/readable/unit/tests/forces_diff.py --plant; one build folder: lock readable:forces)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/unit/tests/forces_diff.py", "--plant"], timeout=600,
        require=(r"^forces_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^forces_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^forces_diff: (OK .*)$",)),
    Row("forces-diff-long", "the same forces comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/unit/tests/forces_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^forces_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^forces_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^forces_diff: (OK .*)$",)),
    # round 18 reader batch (docs/WEAPON_LEVEL_VIEW.md; REWRITE_ORDER3 row 6), read only
    Row("weapon-level-view-diff", "weapon-rank line reader (GameInfoViewer::GetWeaponLevelKind, "
        "src/readable/weapon_level_view): the game's ARM code against the readable C, 300 made-up cases, r0, "
        "unmapped reads and the ordered list of guest calls compared, no early give-up allowed, and 22 planted bugs "
        "that must all be caught (src/readable/weapon_level_view/tests/weapon_level_view_diff.py --plant; one build "
        "folder: lock readable:weapon_level_view)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/weapon_level_view/tests/weapon_level_view_diff.py", "--plant"],
        timeout=600,
        require=(r"^weapon_level_view_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^weapon_level_view_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^weapon_level_view_diff: (OK .*)$",)),
    Row("weapon-level-view-diff-long", "the same weapon-rank line comparison with another seed, 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/weapon_level_view/tests/weapon_level_view_diff.py", "-n", "1500",
             "--seed", "7"],
        timeout=1800,
        require=(r"^weapon_level_view_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^weapon_level_view_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[5-9]\d{2}|4[5-9]\d) early give-ups"),
        note_rx=(r"^weapon_level_view_diff: (OK .*)$",)),
    # round 21 reader batches (docs/STRIKE.md, docs/WHO_HOLDS.md; REWRITE_ORDER4 rows 1 and 2), read only
    Row("strike-diff", "one-strike damage reader (map::BattleInfo::Side::GetSimplePower, src/readable/strike): the "
        "game's ARM code against the readable C, 300 made-up cases, r0, unmapped reads and the ordered list of guest "
        "calls (fifth stack word too) compared, early give-ups allowed only before a cold getter, and 35 planted bugs "
        "that must all be caught (src/readable/strike/tests/strike_diff.py --plant; one build folder: lock "
        "readable:strike)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/strike/tests/strike_diff.py", "--plant"], timeout=900,
        require=(r"^strike_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^strike_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{2,}|9\d) early give-ups"),
        note_rx=(r"^strike_diff: (OK .*)$",)),
    Row("strike-diff-long", "the same one-strike damage comparison with another seed, 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/strike/tests/strike_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^strike_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^strike_diff: (?:FAILED|SKIPPED)", r"\b(?:[1-9]\d{3,}|[2-9]\d{2}) early give-ups"),
        note_rx=(r"^strike_diff: (OK .*)$",)),
    Row("who-holds-diff", "class weapon sub-kind reader (Job::CanEquipFromSubKind, src/readable/who_holds): the "
        "game's ARM code against the readable C, 300 made-up cases, r0, unmapped reads and the ordered list of guest "
        "calls compared, no early give-up allowed, and 24 planted bugs that must all be caught "
        "(src/readable/who_holds/tests/who_holds_diff.py --plant; one build folder: lock readable:who_holds)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/who_holds/tests/who_holds_diff.py", "--plant"], timeout=900,
        require=(r"^who_holds_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^who_holds_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* early give-ups"),
        note_rx=(r"^who_holds_diff: (OK .*)$",)),
    Row("who-holds-diff-long", "the same class weapon sub-kind comparison with another seed, 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/who_holds/tests/who_holds_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^who_holds_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^who_holds_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* early give-ups"),
        note_rx=(r"^who_holds_diff: (OK .*)$",)),
    # round 22 reader batches (docs/FEMALE.md, docs/ROD_TARGET.md; REWRITE_ORDER4 rows 3 and 4), read only
    Row("female-diff", "female readers (Unit::IsFemale and Person::IsFemale, src/readable/female): the game's ARM "
        "code against the readable C, 300 made-up cases each, r0 and unmapped reads compared, a cold one-time cache "
        "gives up at entry on both sides, no early give-up allowed, and 19 planted bugs that must all be caught "
        "(src/readable/female/tests/female_diff.py --plant; one build folder: lock readable:female)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/female/tests/female_diff.py", "--plant"], timeout=900,
        require=(r"^female_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^female_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* early give-ups"),
        note_rx=(r"^female_diff: (OK .*)$",)),
    Row("female-diff-long", "the same female reader comparison with another seed, 1500 cases each",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/female/tests/female_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^female_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^female_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* early give-ups"),
        note_rx=(r"^female_diff: (OK .*)$",)),
    Row("rod-target-diff", "staff target reader (Rod::CanUseTarget, src/readable/rod_target): the game's ARM code "
        "against the readable C, 300 made-up cases, r0, unmapped reads and the ordered list of guest calls compared, "
        "no early give-up allowed, and 42 planted bugs that must all be caught "
        "(src/readable/rod_target/tests/rod_target_diff.py --plant; one build folder: lock readable:rod_target)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/rod_target/tests/rod_target_diff.py", "--plant"], timeout=900,
        require=(r"^rod_target_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^rod_target_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* early give-ups"),
        note_rx=(r"^rod_target_diff: (OK .*)$",)),
    Row("rod-target-diff-long", "the same staff target comparison with another seed, 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/rod_target/tests/rod_target_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^rod_target_diff: OK \(\d+ cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^rod_target_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* early give-ups"),
        note_rx=(r"^rod_target_diff: (OK .*)$",)),
    # round 23 (docs/ITEM_ENHANCE.md): early give-ups are allowed here on purpose: a CanItemEquip cache cold before
    # the tail branch, where the original answers first (about 35 per 300 cases); a mismatch, a missed plant or a
    # case the interpreter could not run still fails. Both rows share one build folder (lock readable:item_enhance),
    # so two runs of this test never overlap (two at once crash with WinError 32).
    Row("item-enhance-diff", "item bonus-while-carried reader (Unit::IsItemEnhanceHave, src/readable/item_enhance): "
        "the game's ARM code, run on through its tail branch into CanItemEquip, against the readable C, 300 made-up "
        "cases, r0, unmapped reads and the ordered list of guest calls compared, every own and CanItemEquip guard "
        "made cold alone, and 29 planted bugs that must all be caught "
        "(src/readable/item_enhance/tests/item_enhance_diff.py --plant; one build folder: lock readable:item_enhance)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/item_enhance/tests/item_enhance_diff.py", "--plant"], timeout=900,
        require=(r"^item_enhance_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^item_enhance_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^item_enhance_diff: (OK .*)$",)),
    Row("item-enhance-diff-long", "the same item bonus-while-carried comparison with another seed, 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/item_enhance/tests/item_enhance_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^item_enhance_diff: OK \(1500 cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^item_enhance_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^item_enhance_diff: (OK .*)$",)),
    # round 23 (docs/VOLUME.md): no cache, so no give-up of any kind is allowed (cold or early).
    Row("volume-diff", "four volume readers (Volume*::GetValue, src/readable/volume): the game's ARM code against "
        "the readable C, 300 made-up cases each, r0, unmapped reads and the ordered list of guest calls compared, no "
        "give-up allowed, and 19 planted bugs that must all be caught "
        "(src/readable/volume/tests/volume_diff.py --plant; one build folder: lock readable:volume)",
        needs=("rom:code", "host-cc"),
        cost="medium",   # round 67: retagged from fast (recorded volume-diff; F-052 runs it by name on readable edits)
        cmd=["{py}", "{root}/src/readable/volume/tests/volume_diff.py", "--plant"], timeout=600,
        require=(r"^volume_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^volume_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* (?:cold:|early give-ups)"),
        note_rx=(r"^volume_diff: (OK .*)$",)),
    Row("volume-diff-long", "the same four volume comparisons with another seed, 1500 cases each",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/volume/tests/volume_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^volume_diff: OK \(6000 cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^volume_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* (?:cold:|early give-ups)"),
        note_rx=(r"^volume_diff: (OK .*)$",)),
    # round 25 (docs/JOB_FEMALE.md; Grok's REWRITE_ORDER5 row 1): give-ups at entry while the one-time cache is cold
    # are allowed on purpose (the game's own code then fills the cache; about 24 per 300 cases); a mismatch, a missed
    # plant or a case the interpreter could not run still fails. One build folder: lock readable:job_female.
    Row("job-female-diff", "class female reader (Job::IsFemale, src/readable/job_female): the game's ARM code "
        "against the readable C, 300 made-up cases, r0, unmapped reads and the ordered list of guest calls compared, "
        "cold-cache give-ups at entry allowed, and 13 planted bugs that must all be caught "
        "(src/readable/job_female/tests/job_female_diff.py --plant; one build folder: lock readable:job_female)",
        needs=("rom:code", "host-cc"),
        cost="medium",   # round 67: retagged from fast (recorded job-female-diff; F-052 runs it by name on readable edits)
        cmd=["{py}", "{root}/src/readable/job_female/tests/job_female_diff.py", "--plant"], timeout=600,
        require=(r"^job_female_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^job_female_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^job_female_diff: (OK .*)$",)),
    Row("job-female-diff-long", "the same class female comparison with another seed, 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/job_female/tests/job_female_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^job_female_diff: OK \(1500 cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^job_female_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^job_female_diff: (OK .*)$",)),
    # round 25 (docs/JOB_RECORD.md; REWRITE_ORDER5 row 2): Job::Get is a registered HELPER, not an override (tier-2
    # verify cannot pick a fall-through target; the UnitPool::Get lesson). The host test still guards the C that
    # later readers may call. No cache, so no give-up of any kind is allowed. One build folder: lock readable:job_record.
    Row("job-record-diff", "class record lookup helper (Job::Get, src/readable/job_record, kind helper): the game's "
        "ARM code against the readable C, 300 made-up class block lists, r0 and unmapped reads compared, no give-up "
        "allowed, and 18 planted bugs that must all be caught "
        "(src/readable/job_record/tests/job_record_diff.py --plant; one build folder: lock readable:job_record)",
        needs=("rom:code", "host-cc"),
        cost="medium",   # round 67: retagged from fast (recorded job-record-diff; F-052 runs it by name on readable edits)
        cmd=["{py}", "{root}/src/readable/job_record/tests/job_record_diff.py", "--plant"], timeout=600,
        require=(r"^job_record_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^job_record_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* (?:cold:|early give-ups)"),
        note_rx=(r"^job_record_diff: (OK .*)$",)),
    Row("job-record-diff-long", "the same class record lookup comparison with another seed, 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/job_record/tests/job_record_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^job_record_diff: OK \(1500 cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^job_record_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* (?:cold:|early give-ups)"),
        note_rx=(r"^job_record_diff: (OK .*)$",)),
    # round 26 (docs/KEY_DOOR.md; Grok's REWRITE_ORDER5 row 5): give-ups at entry while the one-time skill-number
    # cache is cold are allowed on purpose (the game's own code then fills the cache; about 34 per 300 cases); a
    # mismatch, a missed plant or a case the interpreter could not run still fails. One build folder: lock
    # readable:key_door.
    Row("key-door-diff", "door key reader (Unit::CanKeyDoor, src/readable/key_door): the game's ARM code against "
        "the readable C, 300 made-up cases, r0, unmapped reads and the ordered list of guest calls compared, "
        "cold-cache give-ups at entry allowed, and 18 planted bugs that must all be caught "
        "(src/readable/key_door/tests/key_door_diff.py --plant; one build folder: lock readable:key_door)",
        needs=("rom:code", "host-cc"),
        cost="medium",   # round 67: retagged from fast (recorded key-door-diff; F-052 runs it by name on readable edits)
        cmd=["{py}", "{root}/src/readable/key_door/tests/key_door_diff.py", "--plant"], timeout=600,
        require=(r"^key_door_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^key_door_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^key_door_diff: (OK .*)$",)),
    Row("key-door-diff-long", "the same door key comparison with another seed, 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/key_door/tests/key_door_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^key_door_diff: OK \(1500 cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^key_door_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^key_door_diff: (OK .*)$",)),
    # round 26 (docs/SKILL_RECORD.md; REWRITE_ORDER5 row 3): EquipSkill::Get(const char*) by ID label. No cache and
    # no guest call, so no give-up of any kind is allowed (the 0-bucket table follows the runtime's division by 0,
    # which hands back the dividend). One build folder: lock readable:skill_record.
    Row("skill-record-diff", "skill record by label (EquipSkill::Get(const char*), src/readable/skill_record): the "
        "game's ARM code against the readable C, 300 made-up ID hash tables, r0 and unmapped reads compared, no "
        "give-up allowed, and 20 planted bugs that must all be caught "
        "(src/readable/skill_record/tests/skill_record_diff.py --plant; one build folder: lock readable:skill_record)",
        needs=("rom:code", "host-cc"),
        cost="medium",   # round 67: retagged from fast (recorded skill-record-diff; F-052 runs it by name on readable edits)
        cmd=["{py}", "{root}/src/readable/skill_record/tests/skill_record_diff.py", "--plant"], timeout=600,
        require=(r"^skill_record_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^skill_record_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* (?:cold:|early give-ups)"),
        note_rx=(r"^skill_record_diff: (OK .*)$",)),
    Row("skill-record-diff-long", "the same skill record comparison with another seed, 1500 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/skill_record/tests/skill_record_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^skill_record_diff: OK \(1500 cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^skill_record_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* (?:cold:|early give-ups)"),
        note_rx=(r"^skill_record_diff: (OK .*)$",)),
    # round 27 (docs/PERSON_RECORD.md; Grok's REWRITE_ORDER5 row 4): Person::Get(const char*) by ID label (override)
    # and Person::Get(unsigned short) (helper, a fall-through target). No cache and no guest call, so no give-up of
    # any kind is allowed. Made-up states whose data read lands in the game's code are drawn again on the ARM side
    # before the C runs (printed as "drawn again"; it cannot hide a mismatch). Two functions, so -n 1500 prints
    # 3000 cases. One build folder: lock readable:person_record.
    Row("person-record-diff", "person record (Person::Get by label and by number, src/readable/person_record): the "
        "game's ARM code against the readable C, 300 made-up cases per function, r0 and unmapped reads compared, no "
        "give-up allowed, and 38 planted bugs that must all be caught "
        "(src/readable/person_record/tests/person_record_diff.py --plant; one build folder: lock readable:person_record)",
        needs=("rom:code", "host-cc"),
        cost="medium",   # round 67: retagged from fast (recorded person-record-diff; F-052 runs it by name on readable edits)
        cmd=["{py}", "{root}/src/readable/person_record/tests/person_record_diff.py", "--plant"], timeout=600,
        require=(r"^person_record_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"NOT CAUGHT", r"could not run",
                r"^person_record_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* (?:cold:|early give-ups)"),
        note_rx=(r"^person_record_diff: (OK .*)$",)),
    Row("person-record-diff-long", "the same person record comparison with another seed, 1500 cases per function",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/person_record/tests/person_record_diff.py", "-n", "1500", "--seed", "7"],
        timeout=1800,
        require=(r"^person_record_diff: OK \(3000 cases, 0 mismatches\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\s", r"could not run",
                r"^person_record_diff: (?:FAILED|SKIPPED)", r"\b[1-9]\d* (?:cold:|early give-ups)"),
        note_rx=(r"^person_record_diff: (OK .*)$",)),
    Row("guest-call6-test", "guest_call6 (include/readable/fe_guest.h, round 15): a guest call with two stack words "
        "on a host-built fake machine (words at [sp] and [sp + 4], a callee's give-up kept, nothing stored while a "
        "give-up is pending) and 10 planted bugs that must all be caught (tools/readable/tests/guest_call6_test.py "
        "--plant)",
        needs=("host-cc",),
        cmd=["{py}", "{root}/tools/readable/tests/guest_call6_test.py", "--plant"], timeout=300,
        require=(r"^guest_call6_test --plant: (\d+)/\1 planted bugs caught",),
        reject=(r"^Traceback \(most recent call last\):", r"NOT CAUGHT", r"^guest_call6_test --plant: (\d+)/(?!\1\b)\d+"),
        note_rx=(r"^(guest_call6_test --plant: .*)$",)),
    Row("look-step4", "the step-4 look mod (docs/LOOK_STEP4.md, round 15): tools/mods/look_step4.py check builds "
        "mods/LookStep4 from the owner's own files into build/look_step4/check/, reads back exactly the planned table "
        "and dish cells, installs into a scratch Zakuro-style folder there and uninstalls back byte-identical (never "
        "%APPDATA%; one scratch folder: lock look_step4)",
        needs=("rom:romfs",), cost="medium",
        cmd=["{py}", "{root}/tools/mods/look_step4.py", "check"], timeout=900,
        require=(r"^CHECK PASS$",),
        reject=(r"^Traceback \(most recent call last\):", r"^CHECK FAIL", r"^\s+build error:", r"^ERROR:",
                r"uninstall back byte-identical: BAD"),
        note_rx=(r"^\s+(built \d+ file\(s\).*)$",)),
    # round 16 looks step (docs/LOOK_TEXT.md, docs/LOOK_PORTRAIT.md): built and read back without the game
    Row("look-text", "the step-3 text look (docs/LOOK_TEXT.md, round 16): tools/mods/look_text.py check builds "
        "mods/LookText (one English name label, Jakob -> Jacques, found at run time) into build/look_text/check/, "
        "reads it back (only that label differs), installs into a scratch Zakuro-style folder there and uninstalls "
        "back byte-identical (never %APPDATA%; one scratch folder: lock look_text)",
        needs=("rom:romfs",),
        cmd=["{py}", "{root}/tools/mods/look_text.py", "check"], timeout=600,
        require=(r"^CHECK PASS$", r"uninstall back byte-identical: OK"),
        reject=(r"^Traceback \(most recent call last\):", r"^CHECK FAIL", r"^\s+build error:", r"^ERROR:",
                r"uninstall back byte-identical: BAD"),
        note_rx=(r"^\s+(built \d+ file\(s\).*)$",)),
    Row("look-portrait", "the step-5 portrait look (docs/LOOK_PORTRAIT.md, round 16): tools/mods/look_portrait.py "
        "check builds mods/LookPortrait (Jakob's 7 standing and talk-window expressions get Felicia's pictures, faces/ "
        "mod kind) into build/look_portrait/check/, decodes them again against Felicia's, installs into a scratch "
        "Zakuro-style folder there and uninstalls back byte-identical (never %APPDATA%; lock look_portrait)",
        needs=("rom:romfs",), cost="medium",
        cmd=["{py}", "{root}/tools/mods/look_portrait.py", "check"], timeout=900,
        require=(r"^CHECK PASS$", r"uninstall back byte-identical: OK"),
        reject=(r"^Traceback \(most recent call last\):", r"^CHECK FAIL", r"^\s+build error:", r"^ERROR:",
                r"uninstall back byte-identical: BAD"),
        # the built file names are Japanese (Jakob's face files): an ASCII note, or a cp1252 console cannot print it
        note_rx=(r"^\s+(built \d+ file\(s\))", r"^\s+(uninstall back byte-identical: OK .*)$")),
    Row("battle2-shadow-count", "unit_item_stat_bonus tier-2 shadow pass: the unmapped-read counts predicted from the "
        "original's cold one-time caches and item_to_data's nested override equal the logged ones (310 / 440 on "
        "2026-11-15; src/readable/battle2/tests/shadow_count.py, needs verify's battle2 output, docs/BATTLE2.md 8)",
        needs=("rom:code", "file:build/readable/verify_battle2/0033A790.shadow.txt"),
        cmd=["{py}", "{root}/src/readable/battle2/tests/shadow_count.py"], timeout=600,
        require=(r"^shadow_count: OK \(tier 2 shadow pass: (\d+) faults against (\d+); predicted \1 against \2\)",),
        reject=(r"^Traceback \(most recent call last\):", r"^shadow_count: (?:DIFFERENT|SKIPPED)", r"prediction only"),
        note_rx=(r"^shadow_count: (OK .*)$",)),
    Row("ai-score-parked", "the AI attack-score batch stays parked (F-025): no *.c under src/readable/ai_score/ and no "
        "functions.csv / targets.csv row names it, so no unproven score body is built into any library",
        func=check_ai_score_parked, timeout=60),
    # writers (docs/WRITERS.md, DECISIONS F-021): compiled in, every one OFF; these rows test the gate on the PC only
    Row("writer-gate", "writer gate and undo log on a fake machine: off/shadow/capture/original modes store nothing, "
        "every store (the writer's own and a called game function's) logged before it lands and undone exactly, a "
        "changed byte refuses the undo, the log is bounded, every writer armed=0 in the source and only FE_WRITERS "
        "and the mode are read, the run totals published for every capture summary, and 19 planted bugs "
        "that must all be caught (src/readable/core/tests/"
        "writer_gate_test.py --plant; about 4 minutes, one plant ends on its 60 s timeout)",
        needs=("host-cc",), cost="medium",
        cmd=["{py}", "{root}/src/readable/core/tests/writer_gate_test.py", "--plant"], timeout=1800,
        require=(r"^gate test: (\d+)/\1 checks passed",
                 r"^writer_gate_test: OK \(source checks clean, (\d+)/\1 planted bugs caught\)"),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\b", r"NOT CAUGHT", r"does not build",
                r"the list is stale", r"^writer_gate_test: (?:FAILED|SKIPPED)"),
        note_rx=(r"^writer_gate_test: (OK .*)$",)),
    Row("writer-diff", "the first writer (game options block, OFF) against the game's GetValue/SetValue ARM code: "
        "ordered stores and guest calls, bytes read, the undo log and undo back to the start compared; off, refused "
        "and stray cases must store nothing; 25 planted bugs that must all be caught "
        "(src/readable/menu/tests/writer_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/menu/tests/writer_diff.py", "--plant"], timeout=2400,
        require=(r"^writer_diff: exercised: [1-9]\d* cases that stored, [1-9]\d* that rebuilt the zone",
                 r"^writer_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)"),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\b", r"NOT CAUGHT", r"the list is stale",
                r"^writer_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^writer_diff: (OK .*)$",)),
    Row("writer-diff-long", "the same writer comparison with another seed, 3000 cases",
        needs=("rom:code", "host-cc"), cost="slow",
        cmd=["{py}", "{root}/src/readable/menu/tests/writer_diff.py", "-n", "3000", "--seed", "7"], timeout=3600,
        require=(r"^writer_diff: exercised: [1-9]\d* cases that stored, [1-9]\d* that rebuilt the zone",
                 r"^writer_diff: OK \(\d+ cases, 0 mismatches\)"),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\b", r"^writer_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^writer_diff: (OK .*)$",)),
    Row("oka-host-seed1", "OK A host test (F-032, docs/OPTIONS_WIRING.md section 10 item 1), seed 1: the written "
        "options writer config_write_options with every planted bug, 0 mismatches and all plants caught. W1 "
        "(config_options_hook) and W2 (config_serialize_guard) have their own rows (w12-host-seed1/2): this row covers "
        "only config_write_options (src/readable/menu/tests/writer_diff.py --plant --seed 1)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/menu/tests/writer_diff.py", "--plant", "--seed", "1"], timeout=2400,
        require=(r"^writer_diff: the game's .*config_write_options through the writer gate, seed 1$",
                 r"^writer_diff: exercised: [1-9]\d* cases that stored, [1-9]\d* that rebuilt the zone",
                 r"^writer_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)"),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\b", r"NOT CAUGHT", r"the list is stale",
                r"^writer_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^writer_diff: (OK .*)$",)),
    Row("oka-host-seed2", "OK A host test (F-032, docs/OPTIONS_WIRING.md section 10 item 1), seed 2: the written "
        "options writer config_write_options with every planted bug, 0 mismatches and all plants caught. W1 "
        "(config_options_hook) and W2 (config_serialize_guard) have their own rows (w12-host-seed1/2): this row covers "
        "only config_write_options (src/readable/menu/tests/writer_diff.py --plant --seed 2)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/menu/tests/writer_diff.py", "--plant", "--seed", "2"], timeout=2400,
        require=(r"^writer_diff: the game's .*config_write_options through the writer gate, seed 2$",
                 r"^writer_diff: exercised: [1-9]\d* cases that stored, [1-9]\d* that rebuilt the zone",
                 r"^writer_diff: OK \(\d+ cases, 0 mismatches, (\d+)/\1 planted bugs caught\)"),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+MISMATCH\b", r"NOT CAUGHT", r"the list is stale",
                r"^writer_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^writer_diff: (OK .*)$",)),
    # Round 40 (F-034): w12_diff plants 34 bugs; round 40 added 'apply rebuilds the zone' from the hook and from the
    # writer (W1 now stores the danger byte through config_apply_options, without the mid-load zone rebuild).
    # Round 38 (F-034): w12_diff plants 32 bugs (round 35 had 26; round 38 added the danger page value 2 store, the
    # restore rebuilding the zone from the hook and from the writer, the restore refusing the save's own byte, the
    # gate asked for nothing, and the partly mapped G_GameConfig block). A run that catches all of fewer plants
    # (a plant list that shrank) no longer passes.
    # OK A W1/W2 host tests (F-034, round 35; docs/OPTIONS_WIRING.md sections 7 and 12): the game's own Reset /
    # Deserialize / Serialize against W1 (config_options_hook) and W2 (config_serialize_guard), unarmed in git
    Row("w12-host-seed1", "OK A host test of W1/W2 (F-034), seed 20261118: the game's Reset / Deserialize / Serialize / "
        "SetValue ARM code against W1 (config_options_hook) and W2 (config_serialize_guard) through the writer gate, "
        "the unarmed table, the options file reader, clean saves equal to the game's own, every planted bug caught "
        "(src/readable/menu/tests/w12_diff.py --plant)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/menu/tests/w12_diff.py", "--plant"], timeout=3600,
        require=(r"^w12_diff: the game's Reset / Deserialize / Serialize / SetValue .* against W1/W2 through the writer gate, seed 20261118$",
                 r"^w12_diff: exercised: [1-9]\d* scenarios where W1 stored, [1-9]\d* where W2 wrote a save itself, [1-9]\d* where W2 could not",
                 r"^w12_diff: unarmed table .*: [1-9]\d* scenarios, 0 mismatches",
                 r"^w12_diff: clean saves: [1-9]\d* scenarios .*: 0 differ from the game's own saves with no options file, 0 differ from section 4's model$",
                 r"^w12_diff: OK \(\d+ scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; " + W12_PLANT_FLOOR + r"/\1 planted bugs caught\)$"),
        reject=(r"^Traceback \(most recent call last\):", r"MISMATCH\b", r"NOT CAUGHT", r"the list is stale",
                r"^w12_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^w12_diff: (OK .*)$",)),
    Row("w12-host-seed2", "the same W1/W2 host test with seed 2, every planted bug caught "
        "(src/readable/menu/tests/w12_diff.py --plant --seed 2)",
        needs=("rom:code", "host-cc"), cost="medium",
        cmd=["{py}", "{root}/src/readable/menu/tests/w12_diff.py", "--plant", "--seed", "2"], timeout=3600,
        require=(r"^w12_diff: the game's Reset / Deserialize / Serialize / SetValue .* against W1/W2 through the writer gate, seed 2$",
                 r"^w12_diff: exercised: [1-9]\d* scenarios where W1 stored, [1-9]\d* where W2 wrote a save itself, [1-9]\d* where W2 could not",
                 r"^w12_diff: unarmed table .*: [1-9]\d* scenarios, 0 mismatches",
                 r"^w12_diff: clean saves: [1-9]\d* scenarios .*: 0 differ from the game's own saves with no options file, 0 differ from section 4's model$",
                 r"^w12_diff: OK \(\d+ scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; " + W12_PLANT_FLOOR + r"/\1 planted bugs caught\)$"),
        reject=(r"^Traceback \(most recent call last\):", r"MISMATCH\b", r"NOT CAUGHT", r"the list is stale",
                r"^w12_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^w12_diff: (OK .*)$",)),
    Row("w12-options", "options file reader (src/readable/core/options.c, F-034): the shared test lines of "
        "options_cases.json, 2,000 made-up files, the 64 KB limit, %APPDATA% / %LOCALAPPDATA% refused "
        "(src/readable/menu/tests/w12_diff.py --options)",
        needs=("rom:code", "host-cc"),
        cost="medium",   # round 67: retagged from fast (recorded w12-options; F-052 runs it by name on readable edits)
        cmd=["{py}", "{root}/src/readable/menu/tests/w12_diff.py", "--options"], timeout=900,
        require=(r"^w12_diff: options file: [1-9]\d* files .*, 0 mismatches$",),
        reject=(r"^Traceback \(most recent call last\):", r"MISMATCH\b", r"^w12_diff: (?:FAILED|SKIPPED)"),
        note_rx=(r"^w12_diff: (options file: .*)$",)),
    Row("options-track-selftest", "options track rules (opt-* routes, F-032/F-034): a route with \"options\" is "
        "named opt-* and never a cheat route, its saves carry the options mark and are named opts-*, an options "
        "save never starts a real-play route, report/recapture leave options runs out (harness/options_track.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/options_track.py", "--selftest"], timeout=120,
        require=(r"^options track self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(options track self-test: .*)$",)),
    Row("options-track-routes", "the opt-* options routes of config/harness/routes.json and the packed saves "
        "against the options track rules (harness/options_track.py --check)",
        cmd=["{py}", "{root}/tools/harness/options_track.py", "--check"], timeout=120,
        require=(r"^options_track: \d+ options route\(s\), rules OK$",),
        reject=(r"^Traceback \(most recent call last\):", r"carries the options mark"),
        note_rx=(r"^options_track: (\d+ options route\(s\)), rules OK$",)),
    # H5/H6 on kept game records (docs/harness/H56.md); real play and the cheat track never mixed (F-019)
    Row("h56-selftest", "test robot H5/H6 on game records: record folders (real play and cheat track never mixed, "
        "F-019), gcov JSON reading, readable call closure (harness/h56.py --selftest)",
        cmd=["{py}", "{root}/tools/harness/h56.py", "--selftest"], timeout=120,
        require=(r"^h56 self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(h56 self-test: .*)$",)),
    Row("h6three-tests", "the three-number gate report (F-026; tools/harness/h6three.py): recordings on reached lines, "
        "host test on the same planted bugs and live compare per family are kept apart and never added, the reasons "
        "list and candidate classes read right, on made-up inputs (harness/test_h6three.py)",
        cmd=["{py}", "-W", "error::ResourceWarning", "{root}/tools/harness/test_h6three.py"], timeout=300,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK\b"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$",)),
    Row("h6host-test", "the bug-planting host test's time limit reaches borrowed test code (round 18; "
        "tools/harness/h6host.py): a made-up runaway in a borrowed module is stopped and judged \"runaway\", a module "
        "outside src/readable is left alone, and move_diff / leaf_diff / sheet_diff get the limit "
        "(harness/test_h6host.py; no compiler, no text.bin)",
        cmd=["{py}", "{root}/tools/harness/test_h6host.py"], timeout=300,
        require=(r"^Ran [1-9]\d* tests? in ", r"^OK$"),
        reject=(r"^Traceback \(most recent call last\):", r"^FAILED\b"),
        note_rx=(r"^(Ran \d+ tests? in .*)$",)),
    Row("h56-h5", "H5 offline on the kept real-play records of round 18's compare (sessions r10-capb: the 38 older "
        "routes with the 203 older overrides, kept for the offline replay; r11-capo: the same routes, the 31 round 11 "
        "overrides live; r11-capn: the 12 routes new in round 11, every override; r12-cap-class_change: the class "
        "change batch's own capture on the 50 routes (Grok's round 12 fix); r12-capn: bt-ch24, every override; "
        "r13-cap-shop_price: the shop-price batch's own capture on the 5 shop routes; r13-capn: bt-ch25, every "
        "override; r14-cap-equip_use: the equip batch's own capture on 8 Birthright routes; r14-cap-staff_range: the "
        "staff batch's kept 37 runs; r14-capn: bt-ch26, every override; r15-cap-capabilityb: the capability batch's "
        "retry capture on 8 Birthright routes (r15-cap-capability, before the fix, is left out); r15-capn: bt-ch27, "
        "every override; r16-cap-shop_grey: the shop buy-list batch's own capture on the 5 real-play shop routes (its "
        "cheat run moved to r16-capc-shop_grey, F-019); r18-cap-weapon_level_view: the weapon-rank line batch's own "
        "capture on 6 Birthright routes; r21-cap-strike: the one-strike damage batch's own capture on bt-ch2; "
        "r21-cap-who_holds: the class weapon sub-kind batch's own capture on 6 Birthright routes; r22-cap-female: "
        "the female batch's own capture on bt-ch4; r22-cap-rod_target: the staff target reader's live capture on 8 "
        "routes, round 22 integrate; r20-cap-newb: round 20's six new Conquest/Revelation routes (cq-ch13 to "
        "cq-ch15, rv-ch18 to rv-ch20), every override, the clean retry after the GetAttack argument fix; r20-cap-new, "
        "before it, is left out; r23-cap-item_enhance: the item bonus-while-carried batch's own capture on bt-ch4; "
        "r23-cap-volume: the volume batch's own capture on opt-ch8-reload; r25-cap-job_female: the class female "
        "batch's own capture on bt-ch4; r26-cap-key_door and r26-cap-skill_record: the door key and skill record "
        "batches' own captures on bt-ch4; r27-cap-person_record: the person record batch's own capture on "
        "bt-ch6-castle; r24-capn: round 24's five new routes (cq-ch16, rv-ch21 to rv-ch24), every override, live "
        "on the round 27 library; r31-cap-rv-ch25 and r31-cap-rv-ch26: round 31's proof captures of rv-ch25 and "
        "rv-ch26, every override, on the same library): the "
        "original replays "
        "clean on every folder, offline verdict = live verdict on every record, 0 "
        "bad records with today's src/readable; each run writes build/harness/h56/check/runs/<id>/ and updates "
        "build/harness/h56/check/h5.json only when it is complete (label 'check', so the integrate's 'play' results "
        "stay; harness/h56.py h5; H6 is not a row: its rate is a measurement against the F-017 gate, not a pass/fail)",
        needs=("host-cc", "file:build/parallel/r10-capb/records/r10-capb-1/run.json",
               "file:build/parallel/r11-capo/records/r11-capo-1/run.json",
               "file:build/parallel/r11-capn/records/r11-capn-1/run.json",
               "file:build/parallel/r12-cap-class_change/records/r12-cap-class_change-1/run.json",
               "file:build/parallel/r12-capn/records/r12-capn-1/run.json",
               "file:build/parallel/r13-cap-shop_price/records/r13-cap-shop_price-1/run.json",
               "file:build/parallel/r13-capn/records/r13-capn-1/run.json",
               "file:build/parallel/r14-cap-equip_use/records/r14-cap-equip_use-1/run.json",
               "file:build/parallel/r14-cap-staff_range/records/r14-cap-staff_range-1/run.json",
               "file:build/parallel/r14-capn/records/r14-capn-1/run.json",
               "file:build/parallel/r15-cap-capabilityb/records/r15-cap-capabilityb-1/run.json",
               "file:build/parallel/r15-capn/records/r15-capn-1/run.json",
               "file:build/parallel/r16-cap-shop_grey/records/r16-cap-shop_grey-1/run.json",
               "file:build/parallel/r18-cap-weapon_level_view/records/r18-cap-weapon_level_view-1/run.json",
               "file:build/parallel/r21-cap-strike/records/r21-cap-strike-1/run.json",
               "file:build/parallel/r21-cap-who_holds/records/r21-cap-who_holds-1/run.json",
               "file:build/parallel/r22-cap-female/records/r22-cap-female-1/run.json",
               "file:build/parallel/r22-cap-rod_target/records/r22-cap-rod_target-1/run.json",
               "file:build/parallel/r20-cap-newb/records/r20-cap-newb-1/run.json",
               "file:build/parallel/r23-cap-item_enhance/records/r23-cap-item_enhance-1/run.json",
               "file:build/parallel/r23-cap-volume/records/r23-cap-volume-1/run.json",
               "file:build/parallel/r25-cap-job_female/records/r25-cap-job_female-1/run.json",
               "file:build/parallel/r26-cap-key_door/records/r26-cap-key_door-1/run.json",
               "file:build/parallel/r26-cap-skill_record/records/r26-cap-skill_record-1/run.json",
               "file:build/parallel/r27-cap-person_record/records/r27-cap-person_record-1/run.json",
               "file:build/parallel/r24-capn/records/r24-capn-1/run.json",
               "file:build/parallel/r31-cap-rv-ch25/records/r31-cap-rv-ch25-1/run.json",
               "file:build/parallel/r31-cap-rv-ch26/records/r31-cap-rv-ch26-1/run.json"),
        cost="slow",
        cmd=["{py}", "{root}/tools/harness/h56.py", "h5", "--sessions",
             "r10-capb,r11-capn,r11-capo,r12-cap-class_change,r12-capn,r13-cap-shop_price,r13-capn,r14-cap-equip_use,"
             "r14-cap-staff_range,r14-capn,r15-cap-capabilityb,r15-capn,r16-cap-shop_grey,r18-cap-weapon_level_view,"
             "r21-cap-strike,r21-cap-who_holds,r22-cap-female,r22-cap-rod_target,r20-cap-newb,"
             "r23-cap-item_enhance,r23-cap-volume,r25-cap-job_female,r26-cap-key_door,r26-cap-skill_record,"
             "r27-cap-person_record,r24-capn,r31-cap-rv-ch25,r31-cap-rv-ch26",
             "--label", "check",
             "--no-exact"],   # round 11: per-override exact cover (hours on 166k records) deferred to the weekly run
        # round 12: the first pass runs in lanes (FEF_ROBOT_JOBS / max_parallel_runs; docs/harness/H56.md 10)
        # 2026-11-14: 18 min alone for 31,334 records; over 60 min beside H6 and other rows.
        # 2026-11-15: 71 min alone for 106,426 records (r10-capb); timed out at 120 min beside H6
        timeout=4 * 3600,
        require=(r"^h5 \(check\): [1-9]\d* of \d+ overrides met, [1-9]\d* records \(\d+ match, \d+ gave up, 0 bad; "
                 r"offline != live: 0\)",),
        reject=(r"^Traceback \(most recent call last\):", r"HARNESS PROBLEM", r"NOT CLEAN", r"^h56: SETUP"),
        note_rx=(r"^h5 \(check\): (\d+ of \d+ overrides met, \d+ records)",)),
    Row("mutate-writer-fake", "writer H6 plumbing on fakelib: the made-up writer slots' callees found and every "
        "planted bug in them caught (harness/harness.py --mutate --fake --writer-callees; a real writer H6 needs a "
        "test build with that writer armed, owner OK A)",
        needs=("host-cc",), cost="medium",
        cmd=["{py}", "{root}/tools/harness/harness.py", "--mutate", "--fake", "--writer-callees"], timeout=1200,
        require=(r"^mutate: writer H6 \(fake\): [1-9]\d* callee\(s\)", r"^mutate: (\d+)/\1 caught \("),
        reject=(r"^Traceback \(most recent call last\):", r"^mutate: SETUP"),
        note_rx=(r"^mutate: (\d+/\d+ caught)",)),
    Row("readable-verify", "readable tier 2: 3dsrecomp verify on every override, readable + shadow pass "
        "(readable/verify.py; needs a 3dsrecomp build, which needs the owner's OK)",
        needs=("rom:cci", "engine:3dsrecomp-verify", "host-cc", "after:readable"), cost="slow",
        cmd=["{py}", "{root}/tools/readable/verify.py"], timeout=5 * 3600,
        require=(r"^readable-verify: OK \(",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+(?:MISMATCH|NOT-RUN)\s",
                r"^readable-verify: SETUP MISSING"),
        note_rx=(r"^verify-logs: (.*)$",)),
    # ---- the ROM image (docs/ROM_REBUILD.md)
    Row("rom-rebuild", "whole .cci rebuilt from build/code.bin + parts, byte-identical (rom/rebuild.py)",
        needs=("rom:parts", "after:code-hash"), cost="medium",
        cmd=["{py}", "{root}/tools/rom/rebuild.py"], timeout=1800,
        require=(r"^VERDICT: BYTE-IDENTICAL",), note_rx=(r"^(regions: .*)$", r"^VERDICT: (.*)$")),
    Row("rom-tests", ".cci rebuild mutation/shift tests, three 2 GiB images (rom/tests.py all)",
        needs=("rom:parts",), cost="slow", cmd=["{py}", "{root}/tools/rom/tests.py", "all"],
        timeout=3600, require=(r"^(\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\s"),
        note_rx=(r"^(\d+/\d+ checks passed)",)),
    # ---- repository hygiene and the harness itself
    Row("evidence-selftest", "evidence packs and build-folder cleanup on a made-up build folder: packs keep the text "
        "proof, clean never touches saves, libraries or kept sessions (tools/evidence/evidence.py --selftest)",
        cmd=["{py}", "{root}/tools/evidence/evidence.py", "--selftest"], timeout=300,
        require=(r"^evidence self-test: (\d+)/\1 checks passed",),
        reject=(r"^Traceback \(most recent call last\):", r"^\s+FAIL\b"),
        note_rx=(r"^(evidence self-test: .*)$",)),
    Row("hygiene-paths", "git hygiene: nothing tracked under generated dirs, no ROM/asset/binary files",
        needs=("git",), func=check_hygiene_paths, timeout=300),
    Row("hygiene-leak", "git hygiene: no tracked file shares a long byte run with extracted/code.bin",
        needs=("git", "rom:code"), func=check_hygiene_leak, timeout=900),
    Row("py-compile", "every tracked or new (not ignored) Python file compiles", func=check_py_compile, timeout=300),
    Row("selftest", "check_all harness self-tests (tests/test_check_all.py)", cost="medium",
        cmd=["{py}", "-m", "unittest", "discover", "-s", "{root}/tests", "-t", "{root}", "-p", "test_check_all.py"],
        timeout=1200, require=(r"^OK\b",), note_rx=(r"^(Ran \d+ tests? in .*)$", r"^(OK.*)$")),
    Row("progress", "informational: matching progress (progress.py) and README block",
        func=check_progress, info=True, timeout=300),
]

# Round 67 (release plan part A, build/RELEASE_PLAN_2026-11-23.md): rows that only re-run unit
# modules of tests/. Plain `python -m unittest discover -s tests -t .` (and
# tools/release/run_tests.py) already runs every one of them, so --skip-unit-dupes (on in --core)
# drops these rows instead of running the same tests twice. Nothing loses coverage: the unit suite
# still runs them; the plain default, --fast and --slow sets keep the rows (tests/test_check_all.py
# checks that each row here is a pure `-m unittest` run of exactly these modules).
UNIT_DUPES: dict[str, tuple[str, ...]] = {
    "text-mods": ("tests.test_text_mods",),
    "play-tests": ("tests.test_play",),
    "rando-page-tests": ("tests.test_rando_profile",),
    "sof-path-tests": ("tests.seal.test_sof_path", "tests.seal.test_launcher_seal", "tests.seal.test_play_seal",
                       "tests.seal.test_paths_seal", "tests.seal.test_smoke_seal"),
    "randomizer-tests": ("tests.test_randomizer",),
    "rando-tracks-tests": ("tests.test_rando_integrate", "tests.test_rando_growth", "tests.test_rando_skills",
                           "tests.test_rando_items", "tests.test_rando_enemies"),
    "rando-ingame-tests": ("tests.test_rando_ingame",),
    "rando-more-tracks-tests": ("tests.test_rando_children", "tests.test_rando_promotions",
                                "tests.test_rando_music", "tests.test_rando_nuzlocke"),
    "rando-r56-tracks-tests": ("tests.test_rando_weapons", "tests.test_rando_stats", "tests.test_rando_misc"),
    "rando-r62-tracks-tests": ("tests.test_rando_r62",),
    "rando-r63-boss-might": ("tests.test_rando_boss_might",),
    "rando-r64-seal-bosses": ("tests.seal.test_rando_seal_bosses",),
    "rando-recruit-tests": ("tests.test_rando_recruit",),
    "rando-seal-tests": ("tests.seal.test_rando_seal",),
    "rando-colours-tests": ("tests.test_rando_colours",),
    "rando-cache-tests": ("tests.test_rando_cache",),
    "selftest": ("tests.test_check_all",),
}
# --core: the fast rows (after the round-67 retag) minus UNIT_DUPES, plus these (engine patch chain; round 68: the
# release tool's own selftest, medium cost, so the release command proves itself in the core it runs).
CORE_EXTRA: tuple[str, ...] = ("engine-selftest", "release-selftest")


# ------------------------------------------------------------------ the runner
def fmt_time(s: float) -> str:
    s = int(round(s))
    return f"{s}s" if s < 60 else f"{s // 60}m{s % 60:02d}s"


def fmt_limit(s: float) -> str:
    """A timeout limit: fractions shown below 10 s (0.5 s is not '0s')."""
    return f"{s:.3g}s" if s < 10 else fmt_time(s)


def child_env() -> dict:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("PYTHONSTARTUP", None)
    return env


def kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        proc.kill()
    except OSError:
        pass


def run_cmd(ctx: Ctx, row: Row, log_path: Path) -> tuple[int | None, str]:
    """(exit code or None when it did not finish, problem text)."""
    argv = [a.replace("{py}", ctx.py).replace("{root}", str(ctx.root)) for a in row.cmd]
    timeout = row.timeout * ctx.timeout_scale
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("$ " + subprocess.list2cmdline(argv) + "\n")
        log.flush()
        kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | ctx.creationflags} if os.name == "nt" else {
            "start_new_session": True}
        try:
            proc = subprocess.Popen(argv, cwd=str(ctx.root), stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env={**child_env(), **row.env}, **kw)
        except OSError as e:
            return None, f"INCOMPLETE: could not start: {e}"
        procs = ctx.procs
        if procs is not None:
            procs[row.id] = proc
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            proc.wait()
            return None, f"INCOMPLETE: timed out after {fmt_limit(timeout)}"
        except KeyboardInterrupt:
            kill_tree(proc)
            proc.wait()
            raise
        finally:
            if procs is not None:
                procs.pop(row.id, None)
    return rc, ""


class ThreadStdout:
    """sys.stdout that sends each thread's writes to that thread's buffer, if it has one,
    else to the real stream. Unlike contextlib.redirect_stdout (a global swap undone only
    when the thread ends), a check thread abandoned after a timeout keeps writing into its
    own buffer while the runner's table and verdict still reach the real stdout."""

    def __init__(self, real):
        self.real = real
        self.local = threading.local()

    def _target(self):
        buf = getattr(self.local, "buf", None)
        return self.real if buf is None else buf

    def write(self, s):
        return self._target().write(s)

    def flush(self):
        return self._target().flush()

    def __getattr__(self, name):
        return getattr(self._target(), name)


def run_func(ctx: Ctx, row: Row, log_path: Path) -> tuple[bool | None, str]:
    """In-process check in a thread with the row's timeout; output captured to the log."""
    box: dict = {}
    import io
    buf = io.StringIO()
    prev = sys.stdout
    proxy = prev if isinstance(prev, ThreadStdout) else ThreadStdout(prev)
    sys.stdout = proxy

    def target():
        proxy.local.buf = buf
        try:
            box["res"] = row.func(ctx)
        except BaseException as e:  # noqa: BLE001  a crash is a FAIL, never a PASS
            import traceback
            box["err"] = f"{type(e).__name__}: {e}"
            box["tb"] = traceback.format_exc()

    th = threading.Thread(target=target, daemon=True)
    th.start()
    th.join(row.timeout * ctx.timeout_scale)
    text = buf.getvalue()
    if not th.is_alive() and sys.stdout is proxy:
        sys.stdout = prev       # a timed-out thread keeps the proxy (and its own buffer)
    if th.is_alive():
        log_path.write_text(text + "\n[check_all] timed out\n", encoding="utf-8", errors="replace")
        return None, f"INCOMPLETE: timed out after {fmt_limit(row.timeout * ctx.timeout_scale)}"
    if "err" in box:
        log_path.write_text(text + box["tb"], encoding="utf-8", errors="replace")
        return None, f"INCOMPLETE: crashed: {box['err']}"
    res = box.get("res")
    if not (isinstance(res, tuple) and len(res) == 2 and isinstance(res[0], bool)):
        log_path.write_text(text, encoding="utf-8", errors="replace")
        return None, f"INCOMPLETE: check returned {res!r}, not (bool, note)"
    log_path.write_text(text, encoding="utf-8", errors="replace")
    return res[0], str(res[1])


def judge_lines(row: Row, lines: list[str]) -> list[str]:
    """Problems from the row's output patterns: a required line missing, a rejected one seen."""
    problems = []
    for rx in row.require:
        if not any(re.search(rx, l) for l in lines):
            problems.append(f"missing /{rx}/")
    for rx in row.reject:
        hit = next((l for l in lines if re.search(rx, l)), None)
        if hit is not None:
            problems.append(f"found /{rx}/: {hit.strip()[:80]}")
    return problems


def run_row(ctx: Ctx, row: Row) -> dict:
    res = {"id": row.id, "title": row.title, "status": "SKIP", "note": "", "seconds": 0.0,
           "exit": None, "known": [], "cost": row.cost, "info": row.info,
           "needs": list(row.needs), "log": "", "command": None}
    try:
        needs = list(row.needs) + list(row.dynamic_needs(ctx) if row.dynamic_needs else ())
        res["needs"] = needs
        for n in needs:
            why = need_missing(ctx, n)
            if why:
                res["note"] = why
                return res
        ctx.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = ctx.log_dir / f"{row.id}.log"
        res["log"] = str(log_path)
        t0 = time.time()
        problems, notes = [], []
        if row.cmd is not None:
            res["command"] = subprocess.list2cmdline(
                [a.replace("{py}", ctx.py).replace("{root}", str(ctx.root)) for a in row.cmd])
            rc, why = run_cmd(ctx, row, log_path)
            res["exit"] = rc
            ok = rc == 0
            if rc is None:
                problems.append(why)
            elif rc != 0:
                problems.append(f"exit {rc}")
        else:
            ok_f, why = run_func(ctx, row, log_path)
            ok = bool(ok_f)
            if ok_f is None:
                problems.append(why)
            else:
                notes.append(why)
        res["seconds"] = time.time() - t0
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        incomplete = any(p.startswith("INCOMPLETE") for p in problems)
        if not incomplete:
            problems += judge_lines(row, lines)
        for rx in row.note_rx:
            hits = [m for m in (re.search(rx, l) for l in lines) if m]
            if hits:
                m = hits[-1]
                notes.append((m.group(1) if m.groups() else m.group(0)).strip())
        ok = ok and not problems
        known = row.known or KNOWN.get(row.id, [])
        if not ok and known and not incomplete:
            text = "\n".join(lines)
            if all(re.search(k["match"], text, re.M) for k in known):
                res["status"] = "KNOWN"
                res["known"] = [k["id"] for k in known]
                notes.insert(0, "; ".join(f"{k['id']}: {k.get('note', '')}" for k in known))
                res["note"] = "; ".join(x for x in problems + notes if x)
                return res
        if ok and known:
            notes.append("known " + ", ".join(k["id"] for k in known) + " not seen: fixed?")
        res["status"] = "PASS" if ok else "FAIL"
        res["note"] = "; ".join(x for x in problems + notes if x)
        return res
    except KeyboardInterrupt:
        raise
    except BaseException as e:  # noqa: BLE001  a broken row is a failed row, never a missing one
        res["status"] = "FAIL"
        res["note"] = f"INCOMPLETE: check_all.py error: {type(e).__name__}: {e}"
        return res


def unit_dupe_reason(rid: str) -> str:
    mods = ", ".join(m.split(".", 1)[-1] for m in UNIT_DUPES[rid])
    return f"unit-suite duplicate (--skip-unit-dupes): the unit suite already runs {mods}"


EDITIONS = ("all", "vanilla", "seal")


def edition_reason(row: Row, edition: str) -> str:
    """Why --edition leaves this row out ("" = it runs). Round 83 (F-070, docs/SEAL_EDITION_PLAN.md section 5):
    vanilla skips the Seal of Flames edition rows, seal runs only them, all (the default) runs both."""
    if edition == "vanilla" and row.edition == "seal":
        return "Seal of Flames edition row: not run with --edition vanilla"
    if edition == "seal" and row.edition != "seal":
        return f"{row.edition} row: not run with --edition seal (Seal of Flames edition rows only)"
    return ""


def select_rows(rows: list[Row], only, skip, fast: bool, slow: bool, core: bool = False,
                skip_unit_dupes: bool = False, edition: str = "all"):
    """(rows to show, {id: reason not run}); --only shows just those rows.

    core: the fast rows plus CORE_EXTRA, never a UNIT_DUPES row. skip_unit_dupes (always on with
    core) drops the UNIT_DUPES rows from any selection, --only included. edition (round 83): all (default),
    vanilla (no Seal of Flames edition rows) or seal (only them); it applies to --only too."""
    if edition not in EDITIONS:
        raise SystemExit(f"check_all: unknown edition {edition!r} (editions: {', '.join(EDITIONS)})")
    ids = [r.id for r in rows]
    for name in (only or []) + (skip or []):
        if name not in ids:
            raise SystemExit(f"check_all: unknown row {name!r} (rows: {', '.join(ids)})")
    skip_unit_dupes = skip_unit_dupes or core
    shown, reasons = [], {}
    for r in rows:
        why_edition = edition_reason(r, edition)
        if only:
            if r.id not in only:
                continue
            shown.append(r)
            if r.id in (skip or []):
                reasons[r.id] = "not selected (--skip)"
            elif why_edition:
                reasons[r.id] = why_edition
            elif skip_unit_dupes and r.id in UNIT_DUPES:
                reasons[r.id] = unit_dupe_reason(r.id)
            continue
        shown.append(r)
        if r.id in (skip or []):
            reasons[r.id] = "not selected (--skip)"
        elif why_edition:
            reasons[r.id] = why_edition
        elif skip_unit_dupes and r.id in UNIT_DUPES:
            reasons[r.id] = unit_dupe_reason(r.id)
        elif core:
            if r.cost != "fast" and r.id not in CORE_EXTRA:
                reasons[r.id] = f"{r.cost} row: not in the --core profile"
        elif r.cost == "slow" and not slow:
            reasons[r.id] = "slow row: run with --slow (or --only " + r.id + ")"
        elif fast and r.cost != "fast":
            reasons[r.id] = f"{r.cost} row: not run with --fast"
    return shown, reasons


def run_all(ctx: Ctx, rows: list[Row], reasons: dict, stream=sys.stdout) -> list[dict]:
    ctx.selected = {r.id for r in rows if r.id not in reasons}
    out = []
    interrupted = False
    for r in rows:
        if r.id in reasons:
            res = {"id": r.id, "title": r.title, "status": "SKIP", "note": reasons[r.id],
                   "seconds": 0.0, "exit": None, "known": [], "cost": r.cost, "info": r.info,
                   "needs": list(r.needs), "log": "", "command": None, "selected": False}
        elif interrupted:
            res = {"id": r.id, "title": r.title, "status": "FAIL", "note": "INCOMPLETE: interrupted",
                   "seconds": 0.0, "exit": None, "known": [], "cost": r.cost, "info": r.info,
                   "needs": list(r.needs), "log": "", "command": None, "selected": True}
        else:
            print(f"[check-all] {r.id}: {r.title} ... ({time.strftime('%H:%M:%S')})", file=stream, flush=True)
            try:
                res = run_row(ctx, r) if ctx.cache is None else run_row_cached(ctx, r)
            except KeyboardInterrupt:
                interrupted = True
                res = {"id": r.id, "title": r.title, "status": "FAIL", "note": "INCOMPLETE: interrupted",
                       "seconds": 0.0, "exit": None, "known": [], "cost": r.cost, "info": r.info,
                       "needs": list(r.needs), "log": "", "command": None}
            res["selected"] = True
            if res["status"] not in STATUSES:   # defensive: an unknown status is a failure
                res["note"] = f"INCOMPLETE: bad status {res['status']!r}"
                res["status"] = "FAIL"
            print(f"[check-all] {r.id}: {res['status']} ({fmt_time(res['seconds'])})"
                  + (f"  {res['note']}" if res["note"] else ""), file=stream, flush=True)
            if ctx.verbose and res.get("log") and os.path.exists(res["log"]):
                stream.write(Path(res["log"]).read_text(encoding="utf-8", errors="replace"))
        ctx.results[r.id] = res
        out.append(res)
    return out


def verdict(results: list[dict], fail_on_skip: bool = False) -> tuple[str, int, dict]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    sel_skips = sum(1 for r in results if r["status"] == "SKIP" and r.get("selected", True))
    ran = sum(1 for r in results if r["status"] != "SKIP")
    bad = counts.get("FAIL", 0) + (sel_skips if fail_on_skip else 0) + (0 if ran else 1)
    if counts.get("FAIL"):
        v = "FAIL"
    elif not ran:
        v = "FAIL (no row ran: nothing checked is not a pass)"
    elif fail_on_skip and sel_skips:
        v = f"FAIL ({sel_skips} selected row(s) skipped, --fail-on-skip)"
    else:
        extra = [x for x in (f"{counts['SKIP']} skipped" if counts.get("SKIP") else "",
                             f"{counts['KNOWN']} known" if counts.get("KNOWN") else "") if x]
        v = "PASS" + (f" ({', '.join(extra)})" if extra else "")
    return v, (1 if bad else 0), counts


def table(results: list[dict], v: str, counts: dict, json_path: Path, width: int = 110) -> str:
    idw = max([13] + [len(r["id"]) for r in results])
    out = ["", "=" * width, f"check-all ({time.strftime('%Y-%m-%d %H:%M')}): {len(results)} rows",
           "-" * width, f"{'Row':<{idw}} {'Result':<7} {'Time':>6}  Note", "-" * width]
    for r in results:
        lead = f"{r['id']:<{idw}} {r['status']:<7} {fmt_time(r['seconds']):>6}  "
        wrapped = textwrap.wrap(r["note"] or "-", max(20, width - len(lead))) or ["-"]
        keep = wrapped[:1 if r["status"] == "PASS" else 3]
        if len(keep) < len(wrapped):
            keep[-1] = keep[-1][:max(0, width - len(lead) - 3)] + "..."
        out.append(lead + keep[0])
        out += [" " * len(lead) + k for k in keep[1:]]
    out.append("-" * width)
    out.append(f"CHECK-ALL: {v}: " + ", ".join(f"{counts[k]} {k.lower()}" for k in STATUSES if k in counts)
               + f"; full notes in {json_path}")
    out.append("=" * width)
    return "\n".join(out)


# ------------------------------------------------------------------ parallel rows (--jobs, owner item B)
# Rows that write the same output folder or temp files never run at the same time: each row lists
# the folders it shares (a lock). Found 2026-11-13 by reading every row's tool (docs/CHECK_ALL.md):
# the -long variants reuse their base row's build/readable/<area>/ program and plant folder; build.py,
# m1_tests.py, diff_func.py and readable/check.py share build/ (obj, code.bin, fe1.elf,
# cache/analysis.json); harness.py --selftest removes build/harness/selftest/, where headless.py and
# h56.py write theirs; test_parallel.py uses build/parallel/test-*/ in both of its rows; and so on.
PARALLEL_LOCKS: dict[str, tuple[str, ...]] = {
    "code-hash": ("build:code",), "lint": ("build:code",), "m1-tests": ("build:code",),
    "diff-func": ("build:code",), "gen-headers": ("build:code",), "extras-verify": ("build:code",),
    "readable": ("build:code",), "rom-rebuild": ("build:code", "build:rom"), "rom-tests": ("build:rom",),
    "symbols": ("build:symbols",), "symbols-spotcheck": ("build:symbols",),
    "tables-test": ("build:tables",), "tables-gen": ("build:tables",), "tables-check": ("build:tables",),
    "tables-rebuild": ("build:tables",),
    "maps-test": ("build:maps",), "maps-roundtrip": ("build:maps",),
    "castle-test": ("build:castle",), "castle-all": ("build:castle",),
    "assets-bch": ("build:assets",), "assets-portrait": ("build:assets",),
    "assets-full": ("build:assets",),   # round 9: its portrait stage shares build/assets/portrait_test with assets-portrait
    "harness-selftest": ("build:harness",), "headless-selftest": ("build:harness",),
    "h56-selftest": ("build:harness",), "h56-h5": ("build:harness",), "markers-selftest": ("build:harness",),
    "cheats-selftest": ("build:harness",), "cheat-routes": ("build:harness",),
    "harness-levelups": ("build:harness",), "gen-stubs-selftest": ("build:harness",),
    "gen-stubs-check": ("build:harness",), "mutate-writer-fake": ("build:harness",),
    "sheet-diff": ("readable:sheet",), "sheet-diff-long": ("readable:sheet",),
    "item-diff": ("readable:item",), "item-diff-long": ("readable:item",),
    "move-diff": ("readable:move",), "move-diff-long": ("readable:move",),
    "support-diff": ("readable:support",), "support-diff-long": ("readable:support",),
    "ai-perm-diff": ("readable:ai",), "ai-perm-diff-long": ("readable:ai",),
    "battle2-diff": ("readable:battle2",), "battle2-diff-long": ("readable:battle2",),
    "battle2-shadow-count": ("readable:battle2",),
    "class-change-diff": ("readable:class_change",), "class-change-diff-long": ("readable:class_change",),
    "weapon-rank-diff": ("readable:weapon_rank",), "weapon-rank-diff-long": ("readable:weapon_rank",),
    "shop-price-diff": ("readable:shop_price",), "shop-price-diff-long": ("readable:shop_price",),
    "equip-use-diff": ("readable:equip_use",), "equip-use-diff-s7": ("readable:equip_use",),
    "staff-range-diff": ("readable:staff_range",), "staff-range-diff-long": ("readable:staff_range",),
    "capability-diff": ("readable:capability",), "capability-diff-long": ("readable:capability",),
    "look-step4": ("look_step4",),
    "shop-grey-diff": ("readable:shop_grey",), "shop-grey-diff-long": ("readable:shop_grey",),
    "ai-value-diff": ("readable:ai_value",), "ai-value-diff-long": ("readable:ai_value",),
    "flags-diff": ("readable:flags",), "flags-diff-long": ("readable:flags",),
    "forces-diff": ("readable:forces",), "forces-diff-long": ("readable:forces",),
    "flags-diff-s424242": ("readable:flags",),
    "weapon-level-view-diff": ("readable:weapon_level_view",),
    "weapon-level-view-diff-long": ("readable:weapon_level_view",),
    "strike-diff": ("readable:strike",), "strike-diff-long": ("readable:strike",),
    "who-holds-diff": ("readable:who_holds",), "who-holds-diff-long": ("readable:who_holds",),
    "female-diff": ("readable:female",), "female-diff-long": ("readable:female",),
    "rod-target-diff": ("readable:rod_target",), "rod-target-diff-long": ("readable:rod_target",),
    "item-enhance-diff": ("readable:item_enhance",), "item-enhance-diff-long": ("readable:item_enhance",),
    "volume-diff": ("readable:volume",), "volume-diff-long": ("readable:volume",),
    "job-female-diff": ("readable:job_female",), "job-female-diff-long": ("readable:job_female",),
    "job-record-diff": ("readable:job_record",), "job-record-diff-long": ("readable:job_record",),
    "key-door-diff": ("readable:key_door",), "key-door-diff-long": ("readable:key_door",),
    "skill-record-diff": ("readable:skill_record",), "skill-record-diff-long": ("readable:skill_record",),
    "person-record-diff": ("readable:person_record",), "person-record-diff-long": ("readable:person_record",),
    "look-text": ("look_text",), "look-portrait": ("look_portrait",),
    "castle-join-diff": ("readable:castle_join",), "castle-join-diff-long": ("readable:castle_join",),
    "parallel-tests": ("build:parallel",), "parallel-smoke": ("build:parallel",),
    "stance-diff": ("readable:stances",), "stance-diff-long": ("readable:stances",),
    "triangle-diff": ("readable:triangle",), "triangle-diff-long": ("readable:triangle",),
    "vein-diff": ("readable:veins",), "vein-diff-long": ("readable:veins",),
    "formula-diff": ("readable:formula",), "formula-diff-long": ("readable:formula",),
    "growth-diff": ("readable:growth",), "growth-diff-long": ("readable:growth",),
    "skill-diff": ("readable:skill",), "skill-diff-long": ("readable:skill",),
    "menu-diff": ("readable:menu",), "menu-diff-long": ("readable:menu",),
    "writer-gate": ("readable:writers",), "writer-diff": ("readable:writers",),
    "writer-diff-long": ("readable:writers",),
    "oka-host-seed1": ("readable:writers",), "oka-host-seed2": ("readable:writers",),   # same build folder
    "w12-host-seed1": ("readable:writers",), "w12-host-seed2": ("readable:writers",),   # build/readable/writers/w12
    "w12-options": ("readable:writers",),
    "readable-verify": ("readable:verify",),
}
# Run alone, after the parallel rows, in row order: the in-process checks (they share this
# process's stdout and look at the whole work tree, which the other rows write into) and the real
# robot smoke run (it times three boot.exe runs side by side against one after another), and the round
# smoke sets (smoke-set and the Seal edition's seal-smoke: 2 headless robot lanes each, round 84).
PARALLEL_EXCLUSIVE = frozenset({"hygiene-paths", "hygiene-leak", "py-compile", "progress", "parallel-smoke",
                                "smoke-set", "seal-smoke"})
# Rows that start their own pool of worker processes (cpu_count - 1) take two lanes.
PARALLEL_WEIGHT: dict[str, int] = {"assets-arc": 2, "assets-bch": 2, "assets-bchwrite": 2,
                                   "assets-bchwrite-all": 2, "rom-tests": 2}
DEFAULT_JOBS = "1"          # round 9 switches integrate to --jobs auto (docs/CHECK_ALL.md)
COST_GUESS = {"fast": 5.0, "medium": 60.0, "slow": 300.0}
PRIORITY_CLASS = {"idle": 0x00000040, "below_normal": 0x00004000, "normal": 0x00000020}
PRIORITY_NICE = {"idle": 19, "below_normal": 10, "normal": 0}


def row_exclusive(row: Row) -> bool:
    return row.func is not None or row.id in PARALLEL_EXCLUSIVE


def robot_runs_active() -> int | None:
    """Running boot.exe processes (the test robot's runs), or None when they cannot be counted."""
    try:
        if os.name == "nt":
            r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq boot.exe", "/FO", "CSV", "/NH"],
                               capture_output=True, text=True, timeout=30)
            if r.returncode:
                return None
            return sum(1 for l in r.stdout.splitlines() if l.lower().startswith('"boot.exe"'))
        r = subprocess.run(["pgrep", "-x", "boot"], capture_output=True, text=True, timeout=30)
        return len(r.stdout.split()) if r.returncode in (0, 1) else None
    except (OSError, subprocess.SubprocessError):
        return None


def slot_budget_from(root: Path, env: dict | None = None) -> tuple[int, str]:
    """The owner's run budget and where it came from: FEF_CHECK_ALL_SLOTS (a whole number > 0; it
    replaces resources.json for this shell, up or down: e.g. 12 on a night with no long live runs),
    else config/harness/resources.json max_parallel_runs (the day budget, 6), else 1. A set but
    unusable FEF_CHECK_ALL_SLOTS is ignored and the source says so (never a silent fallback)."""
    env = os.environ if env is None else env
    raw = env.get("FEF_CHECK_ALL_SLOTS")
    note = ""
    if raw is not None and raw.strip():
        v = raw.strip()
        if v.isdigit() and int(v) > 0:
            return int(v), "FEF_CHECK_ALL_SLOTS"
        note = f"; FEF_CHECK_ALL_SLOTS={raw!r} ignored (not a whole number > 0)"
    try:
        v = json.loads((root / "config" / "harness" / "resources.json").read_text(encoding="utf-8"))
        n = int(v.get("max_parallel_runs", 1))
        return max(1, n), "resources.json max_parallel_runs" + note
    except (OSError, ValueError, TypeError, AttributeError):
        return 1, "no resources.json budget" + note


def slot_budget(root: Path) -> int:
    """The owner's run budget (slot_budget_from without the source)."""
    return slot_budget_from(root)[0]


def lanes_now(root: Path, asked: int | None, counter=robot_runs_active) -> tuple[int, str]:
    """Lanes allowed right now: the budget minus the robot runs going (never below 1), and no
    more than asked (None = --jobs auto). A robot session holding its slots leaves check_all one lane."""
    budget, source = slot_budget_from(root)
    active = counter()
    if active is None:
        return 1, f"robot runs could not be counted: 1 lane (budget {budget}, {source})"
    free = max(1, budget - active)
    n = free if asked is None else max(1, min(asked, free))
    why = f"budget {budget} ({source}) - {active} robot run(s) = {budget - active} free"
    if asked is not None and n < asked:
        why += f": {asked} asked, {n} used"
    return n, why


def set_priority(name: str) -> str:
    """Lower this process (and so every child it starts) to idle / below_normal; '' if done."""
    try:
        if os.name == "nt":
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            if not k32.SetPriorityClass(ctypes.c_void_p(k32.GetCurrentProcess()), PRIORITY_CLASS[name]):
                return "SetPriorityClass failed"
        else:
            cur = os.nice(0)
            if PRIORITY_NICE[name] > cur:
                os.nice(PRIORITY_NICE[name] - cur)
        return ""
    except (OSError, AttributeError, KeyError) as e:
        return str(e)


def times_path_default(root: Path) -> Path:
    return root / "build" / "check_all_times.json"


def load_times(paths: list[Path]) -> dict[str, float]:
    """Last wall time per row: the times file (merged over runs), then check_all.json rows."""
    out: dict[str, float] = {}
    for p in paths:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and isinstance(d.get("rows"), list):
            for r in d["rows"]:
                if r.get("status") in ("PASS", "FAIL", "KNOWN") and r.get("seconds") and r["id"] not in out:
                    out[r["id"]] = float(r["seconds"])
        elif isinstance(d, dict):
            for k, v in (d.get("seconds") or {}).items():
                out.setdefault(k, float(v))
    return out


def save_times(path: Path, results: list[dict], keep: set | None = None) -> None:
    """Merge this run's real wall times (not cache hits, not skips) into the times file.

    keep: the row ids that still exist (main passes ROWS); entries of rows that were removed or
    folded into another row (round 67: rando-r66-rcheck-selftest) are dropped."""
    try:
        old = json.loads(path.read_text(encoding="utf-8")).get("seconds", {})
    except (OSError, ValueError, AttributeError):
        old = {}
    if keep is not None:
        old = {k: v for k, v in old.items() if k in keep}
    for r in results:
        if r["status"] in ("PASS", "FAIL", "KNOWN") and not r.get("cached") and r.get("seconds", 0) > 0:
            old[r["id"]] = round(r["seconds"], 2)
    write_atomic(path, json.dumps({"tool": "tools/check_all.py", "format": 1,
                                   "date": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": old},
                                  indent=1, sort_keys=True) + "\n")


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def skip_result(r: Row, note: str, selected: bool) -> dict:
    return {"id": r.id, "title": r.title, "status": "SKIP", "note": note, "seconds": 0.0, "exit": None,
            "known": [], "cost": r.cost, "info": r.info, "needs": list(r.needs), "log": "", "command": None,
            "selected": selected}


def interrupted_result(r: Row) -> dict:
    return {"id": r.id, "title": r.title, "status": "FAIL", "note": "INCOMPLETE: interrupted",
            "seconds": 0.0, "exit": None, "known": [], "cost": r.cost, "info": r.info,
            "needs": list(r.needs), "log": "", "command": None, "selected": True}


def finish_line(ctx: Ctx, r: Row, res: dict, stream) -> None:
    if res["status"] not in STATUSES:   # defensive: an unknown status is a failure
        res["note"] = f"INCOMPLETE: bad status {res['status']!r}"
        res["status"] = "FAIL"
    print(f"[check-all] {r.id}: {res['status']} ({fmt_time(res['seconds'])})"
          + (f"  {res['note']}" if res["note"] else ""), file=stream, flush=True)
    if ctx.verbose and res.get("log") and os.path.exists(res["log"]):
        stream.write(Path(res["log"]).read_text(encoding="utf-8", errors="replace"))


def run_parallel(ctx: Ctx, rows: list[Row], reasons: dict, jobs: int | None, stream=sys.stdout,
                 times: dict | None = None, counter=robot_runs_active) -> list[dict]:
    """The selected rows on up to `jobs` lanes (None: as many as the budget leaves free), longest
    first by the last wall times; rows sharing a lock never overlap; exclusive rows run alone at
    the end, in row order. Results come back in row order, as from run_all."""
    ctx.selected = {r.id for r in rows if r.id not in reasons}
    times = times or {}
    order = {r.id: i for i, r in enumerate(rows)}
    todo = [r for r in rows if r.id not in reasons]
    by_id = {r.id: r for r in todo}

    def deps(r: Row) -> list[str]:
        return [n[len("after:"):] for n in r.needs if n.startswith("after:") and n[len("after:"):] in ctx.selected]

    alone = {r.id for r in todo if row_exclusive(r)}
    changed = True
    while changed:                      # a row waiting on an exclusive row runs alone too
        changed = False
        for r in todo:
            if r.id not in alone and any(d in alone for d in deps(r)):
                alone.add(r.id)
                changed = True
    pool = sorted((r for r in todo if r.id not in alone),
                  key=lambda r: (-times.get(r.id, COST_GUESS.get(r.cost, 60.0)), order[r.id]))
    results: dict[str, dict] = {}
    cond = threading.Condition()
    held: dict[str, str] = {}           # lock -> row
    running: dict[str, int] = {}        # row -> weight
    ctx.procs = {}
    lanes_cache = [0.0, 1, ""]
    interrupted = False

    def lanes() -> int:
        """Called with cond held. The count (tasklist, up to 30 s) runs with cond released, so finishing rows
        never wait on it (round 8 review)."""
        if time.time() - lanes_cache[0] > 5:
            cond.release()
            try:
                n, why = lanes_now(ctx.root, jobs, counter)
            finally:
                cond.acquire()
            if n != lanes_cache[1] or not lanes_cache[2]:      # say it when the lane count changes
                print(f"[check-all] lanes: {n} ({why})", file=stream, flush=True)
            lanes_cache[:] = [time.time(), n, why]
        return lanes_cache[1]

    def worker(r: Row):
        try:
            res = run_row_cached(ctx, r)
        except KeyboardInterrupt:
            res = interrupted_result(r)
        except BaseException as e:  # noqa: BLE001  a broken row is a failed row
            res = dict(interrupted_result(r), note=f"INCOMPLETE: check_all.py error: {type(e).__name__}: {e}")
        res["selected"] = True
        with cond:
            if interrupted:
                res = interrupted_result(r)
            results[r.id] = res
            ctx.results[r.id] = res
            for lk in PARALLEL_LOCKS.get(r.id, ()):
                held.pop(lk, None)
            running.pop(r.id, None)
            finish_line(ctx, r, res, stream)
            cond.notify_all()

    threads = []
    try:
        with cond:
            while pool:
                cap = lanes()
                used = sum(running.values())
                pick = None
                for r in pool:
                    if any(d not in results for d in deps(r)):
                        continue
                    if any(lk in held for lk in PARALLEL_LOCKS.get(r.id, ())):
                        continue
                    w = PARALLEL_WEIGHT.get(r.id, 1)
                    if used and used + w > cap:
                        continue
                    pick = r
                    break
                if pick is None:
                    if not running:     # nothing can start and nothing runs: a dependency cycle
                        for r in list(pool):
                            alone.add(r.id)
                        pool.clear()
                        break
                    cond.wait(timeout=5)
                    continue
                pool.remove(pick)
                for lk in PARALLEL_LOCKS.get(pick.id, ()):
                    held[lk] = pick.id
                running[pick.id] = PARALLEL_WEIGHT.get(pick.id, 1)
                print(f"[check-all] {pick.id}: {pick.title} ... ({time.strftime('%H:%M:%S')})",
                      file=stream, flush=True)
                th = threading.Thread(target=worker, args=(pick,), daemon=True)
                threads.append(th)
                th.start()
            while running:
                cond.wait(timeout=5)
    except KeyboardInterrupt:
        interrupted = True
        for p in list(ctx.procs.values()):
            kill_tree(p)
        for th in threads:
            th.join(timeout=30)
    ctx.procs = None
    for r in sorted((by_id[i] for i in alone), key=lambda r: order[r.id]):
        if interrupted:
            res = interrupted_result(r)
        else:
            print(f"[check-all] {r.id}: {r.title} ... ({time.strftime('%H:%M:%S')}, alone)", file=stream, flush=True)
            try:
                res = run_row_cached(ctx, r)
            except KeyboardInterrupt:
                interrupted = True
                res = interrupted_result(r)
            res["selected"] = True
            finish_line(ctx, r, res, stream)
        results[r.id] = res
        ctx.results[r.id] = res
    out = []
    for r in rows:
        res = skip_result(r, reasons[r.id], False) if r.id in reasons else results.get(r.id) or interrupted_result(r)
        ctx.results[r.id] = res
        out.append(res)
    return out


# ------------------------------------------------------------------ row-result cache (owner item A)
# A row is cached only with a declared input list that tools/testcache.py shows complete (imports,
# repository paths its scripts name, the preprocessor's header list); the key covers every input.
_READABLE_INPUTS = ["src/readable/**", "include/readable/**", "tools/readable/**"]
_READABLE_INC = ["tools/readable/stub", "include/readable", "include/readable/generated"]


def _readable_cache(script: str, rom: bool = True) -> dict:
    return {"files": _READABLE_INPUTS + (["extracted/text.bin", "extracted/code.bin"] if rom else []),
            "py": [script], "c_dirs": ["src/readable"], "include": _READABLE_INC, "host_cc": True}



CACHE_SPECS: dict[str, dict] = {
    "stance-diff": _readable_cache("src/readable/battle/tests/stance_diff.py"),
    "stance-diff-long": _readable_cache("src/readable/battle/tests/stance_diff.py"),
    "triangle-diff": _readable_cache("src/readable/battle/tests/triangle_diff.py"),
    "triangle-diff-long": _readable_cache("src/readable/battle/tests/triangle_diff.py"),
    "vein-diff": _readable_cache("src/readable/map/tests/vein_diff.py"),
    "vein-diff-long": _readable_cache("src/readable/map/tests/vein_diff.py"),
    "formula-diff": _readable_cache("src/readable/battle/tests/formula_diff.py"),
    "formula-diff-long": _readable_cache("src/readable/battle/tests/formula_diff.py"),
    "growth-diff": _readable_cache("src/readable/unit/tests/growth_diff.py"),
    "growth-diff-long": _readable_cache("src/readable/unit/tests/growth_diff.py"),
    "skill-diff": _readable_cache("src/readable/skill/tests/skill_diff.py"),
    "skill-diff-long": _readable_cache("src/readable/skill/tests/skill_diff.py"),
    "menu-diff": _readable_cache("src/readable/menu/tests/menu_diff.py"),
    "menu-diff-long": _readable_cache("src/readable/menu/tests/menu_diff.py"),
    "writer-diff": _readable_cache("src/readable/menu/tests/writer_diff.py"),
    "writer-diff-long": _readable_cache("src/readable/menu/tests/writer_diff.py"),
    "oka-host-seed1": _readable_cache("src/readable/menu/tests/writer_diff.py"),
    "oka-host-seed2": _readable_cache("src/readable/menu/tests/writer_diff.py"),
    "w12-host-seed1": _readable_cache("src/readable/menu/tests/w12_diff.py"),
    "w12-host-seed2": _readable_cache("src/readable/menu/tests/w12_diff.py"),
    "w12-options": _readable_cache("src/readable/menu/tests/w12_diff.py"),
    "item-diff": _readable_cache("src/readable/item/tests/item_diff.py"),
    "item-diff-long": _readable_cache("src/readable/item/tests/item_diff.py"),
    "move-diff": _readable_cache("src/readable/move/tests/move_diff.py"),
    "move-diff-long": _readable_cache("src/readable/move/tests/move_diff.py"),
    "support-diff": _readable_cache("src/readable/support/tests/support_diff.py"),
    "support-diff-long": _readable_cache("src/readable/support/tests/support_diff.py"),
    "ai-perm-diff": _readable_cache("src/readable/ai/tests/ai_perm_diff.py"),
    "ai-perm-diff-long": _readable_cache("src/readable/ai/tests/ai_perm_diff.py"),
    "battle2-diff": _readable_cache("src/readable/battle2/tests/battle2_diff.py"),
    "battle2-diff-long": _readable_cache("src/readable/battle2/tests/battle2_diff.py"),
    "class-change-diff": _readable_cache("src/readable/class_change/tests/class_change_diff.py"),
    "class-change-diff-long": _readable_cache("src/readable/class_change/tests/class_change_diff.py"),
    "weapon-rank-diff": _readable_cache("src/readable/weapon_rank/tests/weapon_rank_diff.py"),
    "weapon-rank-diff-long": _readable_cache("src/readable/weapon_rank/tests/weapon_rank_diff.py"),
    "shop-price-diff": _readable_cache("src/readable/shop_price/tests/shop_price_diff.py"),
    "shop-price-diff-long": _readable_cache("src/readable/shop_price/tests/shop_price_diff.py"),
    "equip-use-diff": _readable_cache("src/readable/equip_use/tests/equip_use_diff.py"),
    "equip-use-diff-s7": _readable_cache("src/readable/equip_use/tests/equip_use_diff.py"),
    "staff-range-diff": _readable_cache("src/readable/staff_range/tests/staff_range_diff.py"),
    "staff-range-diff-long": _readable_cache("src/readable/staff_range/tests/staff_range_diff.py"),
    "capability-diff": _readable_cache("src/readable/capability/tests/capability_diff.py"),
    "capability-diff-long": _readable_cache("src/readable/capability/tests/capability_diff.py"),
    "shop-grey-diff": _readable_cache("src/readable/shop_grey/tests/shop_grey_diff.py"),
    "shop-grey-diff-long": _readable_cache("src/readable/shop_grey/tests/shop_grey_diff.py"),
    "ai-value-diff": _readable_cache("src/readable/ai/tests/ai_value_diff.py"),
    "ai-value-diff-long": _readable_cache("src/readable/ai/tests/ai_value_diff.py"),
    "flags-diff": _readable_cache("src/readable/event/tests/flags_diff.py"),
    "flags-diff-long": _readable_cache("src/readable/event/tests/flags_diff.py"),
    "forces-diff": _readable_cache("src/readable/unit/tests/forces_diff.py"),
    "forces-diff-long": _readable_cache("src/readable/unit/tests/forces_diff.py"),
    "flags-diff-s424242": _readable_cache("src/readable/event/tests/flags_diff.py"),
    "weapon-level-view-diff": _readable_cache("src/readable/weapon_level_view/tests/weapon_level_view_diff.py"),
    "weapon-level-view-diff-long": _readable_cache("src/readable/weapon_level_view/tests/weapon_level_view_diff.py"),
    "strike-diff": _readable_cache("src/readable/strike/tests/strike_diff.py"),
    "strike-diff-long": _readable_cache("src/readable/strike/tests/strike_diff.py"),
    "who-holds-diff": _readable_cache("src/readable/who_holds/tests/who_holds_diff.py"),
    "who-holds-diff-long": _readable_cache("src/readable/who_holds/tests/who_holds_diff.py"),
    "female-diff": _readable_cache("src/readable/female/tests/female_diff.py"),
    "female-diff-long": _readable_cache("src/readable/female/tests/female_diff.py"),
    "rod-target-diff": _readable_cache("src/readable/rod_target/tests/rod_target_diff.py"),
    "rod-target-diff-long": _readable_cache("src/readable/rod_target/tests/rod_target_diff.py"),
    # item_enhance_diff imports equip_use_diff (base states, answers, guard lists): both scripts are in its key
    "item-enhance-diff": {**_readable_cache("src/readable/item_enhance/tests/item_enhance_diff.py"),
                          "py": ["src/readable/item_enhance/tests/item_enhance_diff.py",
                                 "src/readable/equip_use/tests/equip_use_diff.py"]},
    "item-enhance-diff-long": {**_readable_cache("src/readable/item_enhance/tests/item_enhance_diff.py"),
                               "py": ["src/readable/item_enhance/tests/item_enhance_diff.py",
                                      "src/readable/equip_use/tests/equip_use_diff.py"]},
    "volume-diff": _readable_cache("src/readable/volume/tests/volume_diff.py"),
    "volume-diff-long": _readable_cache("src/readable/volume/tests/volume_diff.py"),
    "job-female-diff": _readable_cache("src/readable/job_female/tests/job_female_diff.py"),
    "job-female-diff-long": _readable_cache("src/readable/job_female/tests/job_female_diff.py"),
    "job-record-diff": _readable_cache("src/readable/job_record/tests/job_record_diff.py"),
    "job-record-diff-long": _readable_cache("src/readable/job_record/tests/job_record_diff.py"),
    "key-door-diff": _readable_cache("src/readable/key_door/tests/key_door_diff.py"),
    "key-door-diff-long": _readable_cache("src/readable/key_door/tests/key_door_diff.py"),
    "skill-record-diff": _readable_cache("src/readable/skill_record/tests/skill_record_diff.py"),
    "skill-record-diff-long": _readable_cache("src/readable/skill_record/tests/skill_record_diff.py"),
    "person-record-diff": _readable_cache("src/readable/person_record/tests/person_record_diff.py"),
    "person-record-diff-long": _readable_cache("src/readable/person_record/tests/person_record_diff.py"),
    "castle-join-diff": _readable_cache("src/readable/castle_join/tests/castle_join_diff.py"),
    "castle-join-diff-long": _readable_cache("src/readable/castle_join/tests/castle_join_diff.py"),
    "writer-gate": _readable_cache("src/readable/core/tests/writer_gate_test.py", rom=False),
}


def row_definition(row: Row) -> dict:
    """What of the row itself goes into its cache key."""
    return {"id": row.id, "cmd": row.cmd, "env": row.env, "require": list(row.require),
            "reject": list(row.reject), "note_rx": list(row.note_rx), "needs": list(row.needs),
            "info": row.info}


def open_cache(directory: Path):
    """tools/testcache.py's Cache (imported only when the cache is asked for)."""
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    import testcache  # noqa: E402
    return testcache.Cache(directory)


def run_row_cached(ctx: Ctx, row: Row) -> dict:
    """run_row, through the row-result cache when it is on (--cache, or --no-cache to refresh it)."""
    spec = CACHE_SPECS.get(row.id)
    if ctx.cache is None or spec is None:
        return run_row(ctx, row)
    if row.known or KNOWN.get(row.id):
        res = run_row(ctx, row)
        res["cache"] = {"state": "uncacheable", "why": ["the row has known failures listed"]}
        return res
    try:
        needs = list(row.needs) + list(row.dynamic_needs(ctx) if row.dynamic_needs else ())
        if any(need_missing(ctx, n) for n in needs):
            return run_row(ctx, row)        # SKIPs with its reason, no hashing
        t0 = time.time()
        cc = find_host_cc() if spec.get("host_cc") else None
        key, info, problems = ctx.cache.key_for(ctx.root, row_definition(row), spec, cc)
    except Exception as e:  # noqa: BLE001  a cache problem never changes a verdict
        key, info, problems = "", {}, [f"key error: {type(e).__name__}: {e}"]
    if problems:
        res = run_row(ctx, row)
        res["cache"] = {"state": "uncacheable", "why": problems[:5]}
        return res
    why = "--no-cache"
    if ctx.cache_mode == "use":
        entry, why = ctx.cache.get(row.id, key, info)
        if entry is not None:
            ctx.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = ctx.log_dir / f"{row.id}.log"
            age = (time.time() - entry["date"]) / 3600
            log_path.write_text(f"[check_all] CACHED key={key} (stored {age:.1f} h ago, "
                                f"{entry.get('seconds', 0):.0f}s run)\n" + entry.get("log", ""),
                                encoding="utf-8", errors="replace")
            note = f"CACHED key={key}" + (f"; {entry['note']}" if entry.get("note") else "")
            return {"id": row.id, "title": row.title, "status": "PASS", "note": note,
                    "seconds": time.time() - t0, "exit": 0, "known": [], "cost": row.cost, "info": row.info,
                    "needs": needs, "log": str(log_path), "command": None, "cached": True,
                    "cache": {"state": "hit", "key": key, "stored": entry["date"],
                              "run_seconds": entry.get("seconds", 0)}}
    res = run_row(ctx, row)
    res["cache"] = {"state": "miss", "key": key, "why": why}
    if res["status"] == "PASS":
        try:
            log_text = Path(res["log"]).read_text(encoding="utf-8", errors="replace") if res.get("log") else ""
            ctx.cache.put(row.id, key, res, log_text, info)
            res["cache"]["state"] = "stored"
            if ctx.cache_mode == "clean":
                ctx.cache.record_clean(row.id, info)
        except OSError as e:
            res["cache"]["why"] = f"not stored: {e}"
    return res


def list_rows(ctx: Ctx, rows: list[Row], reasons: dict | None = None, times: dict | None = None,
              profile: str = "") -> str:
    """The rows, what each needs and whether it is here. With reasons (the selection of a profile:
    default, --fast, --slow, --core, --only, --skip, --skip-unit-dupes) each row also says whether
    that profile runs it, with its last recorded seconds, and a footer sums the selected rows."""
    if reasons is None:
        out = [f"{'Row':<18} {'Cost':<7} {'Needs':<34} Here?"]
    else:
        out = [f"{'Row':<18} {'Cost':<7} {'Run':<4} {'Secs':>8} {'Needs':<34} Here?"]
    times = times or {}
    n_run, secs, untimed = 0, 0.0, []
    for r in rows:
        needs = list(r.needs) + list(r.dynamic_needs(ctx) if r.dynamic_needs else ())
        miss = [w for w in (need_missing(ctx, n) for n in needs if not n.startswith("after:")) if w]
        here = "yes" if not miss else "SKIP: " + miss[0]
        if reasons is None:
            out.append(f"{r.id:<18} {r.cost:<7} {', '.join(needs) or '-':<34} " + here)
            out.append(f"{'':<18} {r.title}")
            continue
        run = r.id not in reasons
        t = times.get(r.id)
        if run:
            n_run += 1
            if t is None:
                untimed.append(r.id)
            else:
                secs += t
        shown_t = f"{t:.2f}" if t is not None else "n/a"
        out.append(f"{r.id:<18} {r.cost:<7} {'yes' if run else 'no':<4} {shown_t:>8} "
                   f"{', '.join(needs) or '-':<34} " + here)
        out.append(f"{'':<18} {r.title}")
        if not run:
            out.append(f"{'':<18} not run: {reasons[r.id]}")
    if reasons is not None:
        out.append(f"profile {profile or 'default'}: {n_run} of {len(rows)} rows run; their last recorded "
                   f"seconds add up to {secs:.1f} s one after another (recorded under lanes, so on the high "
                   f"side)" + (f"; no recorded time: {', '.join(untimed)}" if untimed else ""))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    pg = ap.add_mutually_exclusive_group()
    pg.add_argument("--fast", action="store_true")
    pg.add_argument("--slow", action="store_true")
    pg.add_argument("--core", action="store_true",
                    help="release core: fast rows + engine-selftest, without the unit-suite duplicate rows")
    ap.add_argument("--skip-unit-dupes", action="store_true",
                    help="drop the rows that only re-run unit modules of tests/ (on with --core)")
    ap.add_argument("--edition", choices=EDITIONS, default="all",
                    help="all (default: both editions live here), vanilla (skip the Seal of Flames edition rows) "
                         "or seal (only them); round 83, F-070")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--fail-on-skip", action="store_true")
    ap.add_argument("--json", default=None)
    ap.add_argument("--log-dir", default=None)
    ap.add_argument("--timeout-scale", type=float, default=1.0)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--jobs", default=DEFAULT_JOBS, help="lanes: N or auto (default 1: serial)")
    ap.add_argument("--priority", choices=sorted(PRIORITY_CLASS), default=None,
                    help="process priority of check_all and its rows (default: below_normal with --jobs > 1)")
    ap.add_argument("--times", default=None, help="last wall time per row (default build/check_all_times.json)")
    cg = ap.add_mutually_exclusive_group()
    cg.add_argument("--cache", action="store_true", help="reuse stored PASSes of unchanged host tests")
    cg.add_argument("--no-cache", action="store_true", help="run every row; record the weekly clean run")
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--internal", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    if a.internal == "assets-quick":
        return internal_assets_quick(root)
    if a.internal:
        ap.error(f"unknown --internal {a.internal}")
    ctx = Ctx(root=root, log_dir=Path(a.log_dir) if a.log_dir else root / "build" / "check_all",
              verbose=a.verbose, timeout_scale=a.timeout_scale)
    split = lambda s: [x.strip() for x in s.split(",") if x.strip()]  # noqa: E731
    try:
        rows, reasons = select_rows(ROWS, split(a.only), split(a.skip), a.fast, a.slow, core=a.core,
                                    skip_unit_dupes=a.skip_unit_dupes, edition=a.edition)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2
    times_path = Path(a.times) if a.times else times_path_default(root)
    if a.list:
        profile = "+".join(n for n, on in (("only", bool(a.only)), ("fast", a.fast), ("slow", a.slow),
                                           ("core", a.core), ("skip", bool(a.skip)),
                                           ("skip-unit-dupes", a.skip_unit_dupes and not a.core),
                                           ("edition-" + a.edition, a.edition != "all")) if on)
        print(list_rows(ctx, rows, reasons, load_times([times_path, root / "build" / "check_all.json"]),
                        profile))
        return 0
    if not seal_edition_here(root):
        n_seal = sum(1 for r in rows if r.id not in reasons and "seal-edition" in r.needs)
        print(f"[check-all] {SEAL_EDITION_MISSING}: {n_seal} selected row(s) skip", flush=True)
    jobs_arg = str(a.jobs).strip().lower()
    if jobs_arg in ("auto", "0"):
        asked = None
    elif jobs_arg.isdigit() and int(jobs_arg) >= 1:
        asked = int(jobs_arg)
    else:
        print(f"check_all: --jobs must be a number or auto, not {a.jobs!r}", file=sys.stderr)
        return 2
    parallel = asked is None or asked > 1
    prio = a.priority or ("below_normal" if parallel else None)
    if prio:
        err = set_priority(prio)
        if os.name == "nt":
            ctx.creationflags = PRIORITY_CLASS[prio]
        print(f"[check-all] priority {prio}" + (f" (not set: {err})" if err else ""), flush=True)
    if a.cache or a.no_cache:
        ctx.cache = open_cache(Path(a.cache_dir) if a.cache_dir else root / "build" / "testcache")
        ctx.cache_mode = "use" if a.cache else "clean"
    json_path = Path(a.json) if a.json else root / "build" / "check_all.json"
    t0 = time.time()
    if parallel:
        times = load_times([times_path, root / "build" / "check_all.json"])
        results = run_parallel(ctx, rows, reasons, asked, times=times)
    else:
        results = run_all(ctx, rows, reasons)
    v, rc, counts = verdict(results, a.fail_on_skip)
    print(table(results, v, counts, json_path))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps({
        "tool": "tools/check_all.py", "format": 1, "root": str(root),
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": round(time.time() - t0, 1),
        "python": sys.version.split()[0], "platform": sys.platform,
        "options": dict({"only": a.only, "skip": a.skip, "fast": a.fast, "slow": a.slow,
                         "fail_on_skip": a.fail_on_skip, "core": a.core,
                         "skip_unit_dupes": a.skip_unit_dupes or a.core, "edition": a.edition},
                        **({"jobs": jobs_arg} if parallel else {}),
                        **({"cache": ctx.cache_mode} if ctx.cache is not None else {})),
        "verdict": v, "exit": rc, "counts": counts,
        "rows": [dict(r, seconds=round(r["seconds"], 2)) for r in results],
    }, indent=1) + "\n", encoding="utf-8")
    try:
        save_times(times_path, results, keep={r.id for r in ROWS})
    except OSError as e:
        print(f"[check-all] times not saved: {e}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
