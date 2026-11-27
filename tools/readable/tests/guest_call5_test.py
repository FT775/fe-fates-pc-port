"""Builds and runs tools/readable/tests/guest_call5_test.c (host gcc, no game data).

    python tools/readable/tests/guest_call5_test.py            the test on include/readable/fe_guest.h
    python tools/readable/tests/guest_call5_test.py --plant    also: each planted bug in a copy of the header
                                                               must make the test fail

Round 11 review: item_diff / ai_score_diff run readable functions through FE_ENTRY, which puts every register back,
so they cannot see a guest_call5 that leaves sp lowered; this test calls guest_call5 directly (docs/READABLE.md 17).
Build output goes to build/readable/guest_call5_test/ (never tracked)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
HEADER = os.path.join(ROOT, "include", "readable", "fe_guest.h")
OUT = os.path.join(ROOT, "build", "readable", "guest_call5_test")

# (what, exact text in fe_guest.h, replacement); each text occurs once
PLANTS = [
    ("sp not put back after the call", "    uint32_t r = guest_call(ctx, function, a0, a1, a2, a3);\n    ctx->r[13] = sp;\n",
     "    uint32_t r = guest_call(ctx, function, a0, a1, a2, a3);\n"),
    ("fifth word stored 4 bytes too high", "    guest_set_u32(ctx, low, a4);\n", "    guest_set_u32(ctx, low + 4u, a4);\n"),
    ("no 8-byte alignment", "    uint32_t low = (sp - 8u) & ~7u;\n", "    uint32_t low = sp - 8u;\n"),
    ("only 4 bytes below sp", "    uint32_t low = (sp - 8u) & ~7u;\n", "    uint32_t low = (sp - 4u) & ~3u;\n"),
    ("sp not lowered for the call", "    ctx->r[13] = low;\n    uint32_t r = guest_call(",
     "    uint32_t r = guest_call("),
    ("word stored after the call", "    guest_set_u32(ctx, low, a4);\n    ctx->r[13] = low;\n    uint32_t r = guest_call(ctx, function, a0, a1, a2, a3);\n",
     "    ctx->r[13] = low;\n    uint32_t r = guest_call(ctx, function, a0, a1, a2, a3);\n    guest_set_u32(ctx, low, a4);\n"),
    ("stores although a give-up is pending",
     "                                   uint32_t a3, uint32_t a4) {\n    if (ctx->exit != EXIT_NONE)\n        return 0; /* an earlier step gave up */\n",
     "                                   uint32_t a3, uint32_t a4) {\n"),
]


def build_and_run(cc: str, header_dir: str, out: str) -> tuple[int, str]:
    os.makedirs(out, exist_ok=True)
    exe = os.path.join(out, "guest_call5_test.exe" if os.name == "nt" else "guest_call5_test")
    inc = ["-I", header_dir, "-I", os.path.join(ROOT, "include", "readable"),
           "-I", os.path.join(ROOT, "tools", "readable", "stub"), "-I", os.path.join(ROOT, "include", "readable", "generated")]
    env = dict(os.environ, PATH=os.path.dirname(cc) + os.pathsep + os.environ.get("PATH", ""))
    r = subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1", "-fwrapv"] + inc
                       + [os.path.join(HERE, "guest_call5_test.c"), "-o", exe], capture_output=True, text=True, env=env)
    if r.returncode:
        return 2, r.stdout + r.stderr
    r = subprocess.run([exe], capture_output=True, text=True, env=env)
    return r.returncode, r.stdout


def main(argv: list[str]) -> int:
    import check  # tools/readable/check.py: the same compiler search
    cc = check.find_cc()
    if not cc:
        print("guest_call5_test: no host C compiler found")
        return 2
    rc, out = build_and_run(cc, os.path.dirname(HEADER), os.path.join(OUT, "clean"))
    print(out.strip().splitlines()[-1] if out.strip() else "(no output)")
    if rc:
        print(out)
        return 1
    if "--plant" not in argv:
        return 0
    src = open(HEADER, encoding="utf-8").read()
    missed = 0
    for i, (what, old, new) in enumerate(PLANTS, 1):
        if src.count(old) != 1:
            print(f"  planted bug {i} ({what}): its text occurs {src.count(old)} times (the list is stale)")
            missed += 1
            continue
        d = os.path.join(OUT, f"plant{i}")
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        with open(os.path.join(d, "fe_guest.h"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src.replace(old, new))
        prc, pout = build_and_run(cc, d, d)
        nfail = sum(1 for ln in pout.splitlines() if ln.startswith("FAIL"))
        first = sorted({ln.split(" (sp")[0][5:] for ln in pout.splitlines() if ln.startswith("FAIL")})
        if prc == 0:
            print(f"  planted bug {i} ({what}): NOT CAUGHT")
            missed += 1
        elif prc == 2:
            print(f"  planted bug {i} ({what}): did not build (counts as not caught)\n{pout[:400]}")
            missed += 1
        else:
            print(f"  planted bug {i} ({what}): caught, {nfail} failed checks: {'; '.join(first[:3])}")
    print(f"guest_call5_test --plant: {len(PLANTS) - missed}/{len(PLANTS)} planted bugs caught")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
