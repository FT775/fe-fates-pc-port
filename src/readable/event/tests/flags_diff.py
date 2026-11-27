#!/usr/bin/env python3
"""Host differential test of src/readable/event/flags.c against the game's own ARM code.

    python src/readable/event/tests/flags_diff.py              300 cases
    python src/readable/event/tests/flags_diff.py -n 1500 --seed 7     the long run
    python src/readable/event/tests/flags_diff.py --plant      also plant bugs: each must be caught

Round 17 (the file had no host test). The method and the shared code: src/readable/battle/tests/leaf_diff.py.
Made-up states (test values only): a FlagManager whose bit array pointer (+0xC) points into a page of random
bytes, or is 0 or unmapped; flag numbers inside the array, negative ones that reach below it (as the game's
arithmetic shift does), and huge ones that reach unmapped memory. Round 18: a flag number whose byte would
land inside text.bin (mapped for the original only) is drawn again (TEXT_LO below).

Exit 0 only when every case matches (and, with --plant, every planted bug is caught). Needs extracted/text.bin
and a host C compiler; SKIPs (exit 0, says so) without them.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src", "readable", "battle", "tests"))
import leaf_diff as L  # noqa: E402

NAME = "flags_diff"
SRC_EVENT = SRC_DIR = os.path.join(ROOT, "src", "readable", "event")
FILES = ("flags.c",)
HEADER = '#include "fe.h"'
OUT = os.path.join(ROOT, "build", "readable", "flags")

OVERRIDES = {"flag_manager_get": 0x00508584}

FM = 0x08000000
BITS = 0x08001000  # the array; 0x400 bytes below it and 0x400 above it are mapped (random)


# text.bin is loaded at 0x00100000 for the original (arm_mini) but is not mapped for the readable C, so a read
# that lands there would be a false mismatch (round 17: seed 424242 -n 400, case 52, bits 0 + index 0x160bd81).
# 0x00700000 is past the end of text.bin (5,308,700 bytes) with room to spare.
TEXT_LO, TEXT_HI = 0x00100000, 0x00700000


def pick_index(rng):
    r = rng.random()
    if r < 0.6:
        return rng.randrange(0, 0x1800)        # inside the array (or just past it, still mapped)
    if r < 0.8:
        return -rng.randrange(1, 0x1800)       # below the array
    if r < 0.9:
        return rng.choice([0, 1, 7, 8, 9, 15, 16, -1, -8, -9, 0x1FFF, -0x2000])
    return rng.choice([0x7FFFFFFF, -0x80000000, 0x40000000, 0x10000, -0x10000, rng.randrange(-2**31, 2**31)])


def byte_addr(bits, index):
    """The address the game reads: bits + (index asr 3), 32-bit."""
    return (bits + (index >> 3)) & 0xFFFFFFFF  # Python >> on a negative int is an arithmetic shift


def gen_get(rng):
    st = L.base_state(rng)
    fm = FM if rng.random() > 0.04 else rng.choice(L.UNMAPPED)
    if fm == FM:
        st.fill(FM, 0x20)
        r = rng.random()
        bits = BITS + rng.choice([0, 0, 0, 4, 0x100]) if r > 0.08 else rng.choice([0] + L.UNMAPPED)
        st.put(FM + 0xC, 4, bits)
    else:
        bits = None  # the FlagManager itself is unmapped: the bits pointer is never read
    st.fill(BITS - 0x400, 0x800)
    index = pick_index(rng)
    while bits is not None and TEXT_LO <= byte_addr(bits, index) < TEXT_HI:
        index = pick_index(rng)                # never let a read reach text.bin (see TEXT_LO)
    return st, [fm, L.s32(index), rng.randrange(1 << 32)]


FUNCS = {"flag_manager_get": gen_get}


def note_path(fname, st, args, exp):
    i = L.sx(args[1], 32)
    return ("unmapped" if exp[2] else "mapped") + (", negative" if i < 0 else "") + (", set" if exp[1] else ", clear")


# planted bugs: (file, exact text, replacement); each text occurs once in its file
F = "flags.c"
PLANTS = [
    (F, "    gaddr bits = READ_FIELD(ctx, FlagManager, flags, bits);", "    gaddr bits = guest_ptr(ctx, flags + 8u);"),
    (F, "bits + (gaddr)fe_asr((int32_t)index, 3)", "bits + (gaddr)(index >> 3)"),
    (F, "bits + (gaddr)fe_asr((int32_t)index, 3)", "bits + (gaddr)fe_asr((int32_t)index, 4)"),
    (F, "(1u << (index & 7u))", "(1u << (index & 15u))"),
    (F, "(1u << (index & 7u))", "(0x80u >> (index & 7u))"),
    (F, "    return (byte & (1u << (index & 7u))) != 0;", "    return (byte & (1u << (index & 7u)));"),
    (F, "    uint32_t byte = guest_u8(ctx,", "    uint32_t byte = guest_u16(ctx,"),
]

L.install(globals())


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=300, help="cases per function (default 300)")
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument("--only", help="one function name")
    ap.add_argument("--show", type=int, default=5, help="mismatches to print per function")
    ap.add_argument("--plant", action="store_true", help="also check that planted bugs are caught")
    ap.add_argument("--plant-n", type=int, help="cases per function for each planted bug (default: -n)")
    return run(ap.parse_args(argv))  # noqa: F821  (installed by leaf_diff)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
