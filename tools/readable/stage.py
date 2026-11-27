#!/usr/bin/env python3
"""Stage the readable layer for 3dsrecomp (docs/READABLE.md, "Building").

Standard library only. Writes nothing outside build/readable/.

    python tools/readable/stage.py                  write build/readable/overrides/*.c
    python tools/readable/stage.py --mode readable  bake another default mode in
                                                    (original | readable | shadow; the
                                                    FE_READABLE variable still wins)
    python tools/readable/stage.py --commands ROM   also print the 3dsrecomp commands

Why staging: `3dsrecomp build --overrides DIR` reads only the *.c files directly
in DIR (no subfolders), copies each to <out>/hand/ and compiles it with
`-I <out>` only. So each source in src/readable/<system>/ becomes one
self-contained file, build/readable/overrides/<system>__<file>.c, with our own
headers (include/readable/, include/readable/generated/) pasted in, once each,
behind #line markers so compiler messages still name the real files.
"overrides.h" and system headers stay #includes: 3dsrecomp writes overrides.h
next to the generated code.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(ROOT, "src", "readable")
INCLUDE_DIRS = [os.path.join(ROOT, "include", "readable"), os.path.join(ROOT, "include", "readable", "generated")]
OUT = os.path.join(ROOT, "build", "readable", "overrides")
KEEP = {"overrides.h"}  # provided by 3dsrecomp
INCLUDE_RX = re.compile(r'^\s*#\s*include\s+"([^"]+)"\s*(?:/\*.*\*/\s*|//.*)?$')
MODES = {"original": "FE_MODE_ORIGINAL", "readable": "FE_MODE_READABLE", "shadow": "FE_MODE_SHADOW"}
sys.path.append(os.path.join(ROOT, "tools"))  # gamecfg (appended: tools/build.py must not shadow tools/harness/build.py)
from gamecfg import GAME  # noqa: E402

TITLE_ID = GAME.title_id  # 3dsrecomp names the built library after it (config/game.json)


def rel(path: str) -> str:
    try:
        return os.path.relpath(path, ROOT).replace(os.sep, "/")
    except ValueError:          # another drive (an --out folder outside the repo)
        return path.replace(os.sep, "/")


def sources() -> list[str]:
    out = []
    for dp, _dn, fn in os.walk(SRC):
        out += [os.path.join(dp, f) for f in fn if f.endswith(".c")]
    return sorted(out)


def staged_name(path: str) -> str:
    parts = os.path.relpath(path, SRC).replace(os.sep, "/").split("/")
    return "__".join(parts)


def find_header(name: str, including: str) -> str | None:
    for d in [os.path.dirname(including)] + INCLUDE_DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def flatten(path: str, seen: set[str], out: list[str]) -> None:
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    out.append(f'#line 1 "{rel(path)}"')
    for i, line in enumerate(lines, 1):
        m = INCLUDE_RX.match(line)
        if m and m.group(1) not in KEEP:
            header = find_header(m.group(1), path)
            if header is None:
                raise SystemExit(f"{rel(path)}:{i}: cannot find \"{m.group(1)}\" in include/readable/")
            key = os.path.normcase(os.path.abspath(header))
            if key not in seen:
                seen.add(key)
                flatten(header, seen, out)
                out.append(f'#line {i + 1} "{rel(path)}"')
            else:
                out.append(f"/* {m.group(1)}: already pasted above */")
            continue
        out.append(line)


OVERRIDE_RX = re.compile(r"RECOMP_OVERRIDE\(\s*(0x[0-9A-Fa-f]+)\s*\)")


def check_fates_only(srcs: list[str]) -> None:
    """Refuse to stage an override that is not this game's: every RECOMP_OVERRIDE address
    must be a function start of config/functions.csv (Fates) and a row of
    config/readable/functions.csv naming that source. Catches an Awakening source or
    address carried over from the Awakening port's tree."""
    sys.path.insert(0, HERE)
    import check  # noqa: E402  (same folder)
    starts = check.function_starts()
    reg = {int(r["address"], 16): r for r in check.registry() if r.get("kind") == "override"}
    bad = []
    for src in srcs:
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
        for m in OVERRIDE_RX.finditer(text):
            a = int(m.group(1), 16)
            row = reg.get(a)
            if a not in starts:
                bad.append(f"{rel(src)}: RECOMP_OVERRIDE({m.group(1)}) is not a {GAME.game} function start "
                           "(config/functions.csv)")
            elif row is None or row.get("source", "").strip() != rel(src):
                bad.append(f"{rel(src)}: RECOMP_OVERRIDE({m.group(1)}) has no config/readable/functions.csv "
                           "override row naming this source")
    if bad:
        raise SystemExit("stage: refusing to stage:\n  " + "\n  ".join(bad))


def stage(mode: str, out_dir: str = OUT) -> list[str]:
    check_fates_only(sources())
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    written = []
    for src in sources():
        body: list[str] = []
        flatten(src, set(), body)
        text = "\n".join([
            f"/* STAGED by tools/readable/stage.py from {rel(src)} -- do not edit, edit the",
            "   source and stage again. Our own headers are pasted in; overrides.h comes",
            "   from 3dsrecomp. Nothing here is game code. */",
            f"#define FE_DEFAULT_MODE {MODES[mode]}",
            "",
        ] + body) + "\n"
        dst = os.path.join(out_dir, staged_name(src))
        with open(dst, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        written.append(dst)
    return written


def print_commands(rom: str) -> None:
    sys.path.insert(0, HERE)
    import check  # noqa: E402  (same folder)
    overrides = [r for r in check.registry() if r["kind"] == "override"]
    recomp = r"engine\target\3dsrecomp-verify\release\3dsrecomp.exe"
    out = os.path.join(ROOT, "build", "readable", "verify")
    lib = os.path.join(out, "lib", f"{TITLE_ID}.dll")
    win = lambda path: rel(path).replace("/", "\\")  # noqa: E731  (paths in cmd lines)
    print("# 1. build 3dsrecomp with verify once (Rust; fetches crates; writes only engine/ and the cargo cache):")
    print("python tools/engine/engine.py build 3dsrecomp-verify")
    print("# 2. tier 2 in one command: stage (readable mode), build into build/readable/verify/lib (a")
    print("#    folder, so nothing is installed for Zakuro), verify every override twice, classify:")
    print(f'python tools/readable/verify.py --rom "{rom}"')
    print("#    by hand, the same steps:")
    print(f'python tools/readable/stage.py --mode readable --out "{win(os.path.join(out, "overrides"))}"')
    print(f'set "PATH=C:\\msys64\\ucrt64\\bin;%PATH%"')
    print(f'{recomp} build "{rom}" "{win(os.path.dirname(lib))}" --overrides "{win(os.path.join(out, "overrides"))}"')
    for r in overrides:
        a = r["address"][2:]
        print(f'set VERIFY_ONLY={a}&& set FE_READABLE=readable&& set FE_READABLE_LOG={win(out)}\\{a}.readable.log&& '
              f'{recomp} verify "{rom}" "{win(lib)}" > {win(out)}\\{a}.txt')
    print(f"python tools/readable/check.py --verify-logs {win(out)}")
    print("# 3. play in shadow mode (owner): zakuro.exe --recompiled <that dll> <rom>, then read the log")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=sorted(MODES), default="shadow")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--commands", metavar="ROM", help="print the 3dsrecomp commands for this ROM path")
    a = ap.parse_args(argv)
    written = stage(a.mode, a.out)
    for w in written:
        print(f"staged {rel(w)}")
    print(f"stage: {len(written)} file(s) in {rel(a.out)} (default mode {a.mode})")
    if a.commands:
        print_commands(a.commands)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
