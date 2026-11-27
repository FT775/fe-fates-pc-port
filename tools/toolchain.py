#!/usr/bin/env python3
"""Locate the user-installed GNU ARM binutils and record them in tools/config.local.json.

Never installs anything. Search order: existing config ("binutils_dir"), the extra
directories listed under "toolchain_search" in tools/config.local.json, $ARM_GNU_BIN,
$DEVKITARM, C:/devkitPro/devkitARM, tools/bin/arm-gnu-toolchain (Arm GNU Toolchain
14.2.rel1 zip, SHA-256 f074615953f76036e9a51b87f6577fdb4ed8e77d3322a6f68214e92e7859888f),
a sibling port's copy (../*/tools/bin/arm-gnu-toolchain/bin, e.g. the Awakening port
next to this repo: used read-only, nothing is copied), then PATH.

Usage:
    python tools/toolchain.py                    # detect, print versions, write config
    python tools/toolchain.py --check            # exit 1 if anything is missing (no write)
    python tools/toolchain.py --use DIR          # record DIR (a .../bin with arm-none-eabi-*)
    python tools/toolchain.py --selftest         # search logic against fake toolchains
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "tools" / "config.local.json"
TOOLS = ("as", "ld", "objdump", "objcopy", "nm")
PREFIX = "arm-none-eabi-"
EXE = ".exe" if os.name == "nt" else ""


def candidate_dirs(cfg: dict, root: Path = ROOT) -> list[Path]:
    dirs = []
    if cfg.get("binutils_dir"):
        dirs.append(Path(cfg["binutils_dir"]))
    extra = cfg.get("toolchain_search") or []
    if isinstance(extra, str):
        extra = [extra]
    dirs += [Path(x) for x in extra]
    if os.environ.get("ARM_GNU_BIN"):
        dirs.append(Path(os.environ["ARM_GNU_BIN"]))
    if os.environ.get("DEVKITARM"):
        p = os.environ["DEVKITARM"]
        # devkitPro sets msys-style paths like /opt/devkitpro/devkitARM
        if p.startswith("/opt/devkitpro"):
            p = "C:/devkitPro" + p[len("/opt/devkitpro"):]
        dirs.append(Path(p) / "bin")
    dirs.append(Path("C:/devkitPro/devkitARM/bin"))
    # Project-local Arm GNU Toolchain (unzipped into the gitignored tools/bin/).
    dirs.append(root / "tools" / "bin" / "arm-gnu-toolchain" / "bin")
    # A sibling port (same parent folder) that already unzipped the same toolchain.
    parent = root.parent
    if parent.is_dir():
        for sib in sorted(parent.iterdir()):
            if sib != root and sib.is_dir():
                dirs.append(sib / "tools" / "bin" / "arm-gnu-toolchain" / "bin")
    return dirs


def complete(d: Path) -> bool:
    return all((d / f"{PREFIX}{t}{EXE}").is_file() for t in TOOLS)


def find(cfg: dict, root: Path = ROOT, use_path: bool = True) -> Path | None:
    for d in candidate_dirs(cfg, root):
        if complete(d):
            return d
    w = shutil.which(f"{PREFIX}as") if use_path else None
    if w:
        d = Path(w).parent
        if all((d / f"{PREFIX}{t}{EXE}").is_file() for t in TOOLS):
            return d
    return None


def selftest() -> int:
    """Fake toolchains in a temp folder: config wins, then search list, then siblings."""
    import tempfile
    fails = 0

    def check(what, got, want):
        nonlocal fails
        ok = (got.resolve() if got else None) == (want.resolve() if want else None)
        fails += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {what}: {got}")

    def fake(d: Path, tools=TOOLS):
        d.mkdir(parents=True, exist_ok=True)
        for t in tools:
            (d / f"{PREFIX}{t}{EXE}").write_bytes(b"")
        return d

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        me = t / "ports" / "FE Fates"
        (me / "tools").mkdir(parents=True)
        sib = fake(t / "ports" / "FE Awakening" / "tools" / "bin" / "arm-gnu-toolchain" / "bin")
        old = {k: os.environ.pop(k, None) for k in ("ARM_GNU_BIN", "DEVKITARM")}
        try:
            check("sibling port", find({}, me, use_path=False), sib)
            extra = fake(t / "elsewhere" / "bin")
            check("toolchain_search beats sibling", find({"toolchain_search": [str(extra)]}, me, False), extra)
            own = fake(me / "tools" / "bin" / "arm-gnu-toolchain" / "bin")
            check("own tools/bin beats sibling", find({}, me, False), own)
            cfgd = fake(t / "cfg" / "bin")
            check("binutils_dir wins", find({"binutils_dir": str(cfgd)}, me, False), cfgd)
            part = fake(t / "partial" / "bin", TOOLS[:2])
            check("incomplete dir skipped", find({"binutils_dir": str(part)}, me, False), own)
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v
    print(f"toolchain selftest: {'OK' if not fails else f'{fails} failure(s)'}")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--use", metavar="DIR")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()

    cfg = json.loads(CONFIG.read_text()) if CONFIG.is_file() else {}
    if a.use:
        if not complete(Path(a.use)):
            print(f"{a.use}: not every arm-none-eabi-{{{','.join(TOOLS)}}} is there")
            return 1
        cfg["binutils_dir"] = a.use
    d = find(cfg)
    if d is None:
        print("GNU ARM binutils not found. Install devkitARM (devkitPro installer, '3DS Development')")
        print("or the Arm GNU Toolchain, or set \"binutils_dir\" in tools/config.local.json.")
        return 1

    versions = {}
    for t in TOOLS:
        out = subprocess.run([str(d / f"{PREFIX}{t}{EXE}"), "--version"],
                             capture_output=True, text=True).stdout.splitlines()
        versions[t] = out[0] if out else "?"
        print(f"{t:8} {versions[t]}")

    if not a.check:
        cfg["binutils_dir"] = str(d)
        cfg["binutils_versions"] = versions
        CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
        print(f"wrote {CONFIG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
