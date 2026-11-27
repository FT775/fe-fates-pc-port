#!/usr/bin/env python3
"""Host differential test of src/readable/unit/forces.c against the game's own ARM code.

    python src/readable/unit/tests/forces_diff.py              all 3 functions, 300 cases each
    python src/readable/unit/tests/forces_diff.py -n 1500 --seed 7     the long run
    python src/readable/unit/tests/forces_diff.py --only unit_next
    python src/readable/unit/tests/forces_diff.py --plant      also plant bugs: each must be caught

Round 17 (the file had no host test: src/readable/unit/tests/growth_diff.py tests the growth files of the same
folder). The method and the shared code: src/readable/battle/tests/leaf_diff.py. Made-up states (test values
only): the unit pool (G_UnitPool) with its Force array (10 records of 12 bytes, type bytes that match their
index or not, up to 0xFF), force lists that are empty or hold made-up units chained by Unit.next, units whose
force pointer is a record, another record or unmapped; force masks of every shape (0, one bit, several, bits
above 9, all ones); other force types 0 .. 3, past 9, and with high bits set (the game compares the full
32-bit value with the type byte).

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

NAME = "forces_diff"
SRC_UNIT = SRC_DIR = os.path.join(ROOT, "src", "readable", "unit")
FILES = ("forces.c",)
HEADER = '#include "fe.h"'
OUT = os.path.join(ROOT, "build", "readable", "forces")

OVERRIDES = {"force_is_allied": 0x0053C3E0, "unit_pool_first": 0x004F62CC, "unit_next": 0x00533208}

# Force::Get (0x004F630C), a one-word NOP that runs into UnitPool::GetForce: 3dsrecomp keeps it inside the caller
# (forces.c's header), so the readable C makes no guest call there; arm_mini runs it and does not list it
NOT_LISTED = (0x004F630C,)

G_UNIT_POOL = 0x006D9F40
FORCES = 0x08000000
UNIT = lambda k: 0x08010000 + k * 0x140  # noqa: E731
NUNITS = 12


def word(st, a):
    return int.from_bytes(bytes(st.mem.get(a + i, 0) for i in range(4)), "little")


def pool(st, rng) -> None:
    """The pool, its forces (types 0 .. 9, each list empty or a chain of made-up units) and the units."""
    st.fill(G_UNIT_POOL, 8)
    st.put(G_UNIT_POOL + 4, 4, FORCES if rng.random() > 0.03 else rng.choice(L.UNMAPPED))
    st.fill(FORCES, 12 * 12)  # two records past the tenth: junk
    for k in range(NUNITS):
        st.fill(UNIT(k), 0x140)
    order = list(range(NUNITS))
    rng.shuffle(order)
    empty = rng.random()
    for t in range(10):
        f = FORCES + t * 12
        st.put(f + 8, 1, t if rng.random() > 0.15 else L.pick(rng, list(range(10)), [0xFF, 0x0A, 0x80], 0.3))
        if rng.random() < empty or not order:
            st.put(f, 4, 0)
            continue
        chain = [order.pop() for _ in range(min(len(order), rng.choice([1, 1, 2, 3])))]
        st.put(f, 4, UNIT(chain[0]))
        for a, b in zip(chain, chain[1:] + [None]):
            st.put(UNIT(a) + 0x14, 4, UNIT(b) if b is not None else 0)
            st.put(UNIT(a) + 0xA4, 4, f if rng.random() > 0.08 else
                   rng.choice([FORCES + rng.randrange(12) * 12] + L.UNMAPPED))
    for k in order:  # units in no list
        st.put(UNIT(k) + 0x14, 4, rng.choice([0, 0, UNIT(rng.randrange(NUNITS))]))
        st.put(UNIT(k) + 0xA4, 4, rng.choice([FORCES + rng.randrange(12) * 12, FORCES + 9 * 12] + L.UNMAPPED))


def mask(rng) -> int:
    r = rng.random()
    if r < 0.15:
        return 1 << rng.randrange(10)
    if r < 0.75:
        return rng.randrange(1 << 10)
    if r < 0.85:
        return rng.choice([0, 0x3FF, 0xFFFFFFFF, 0x400, 0xFFFFFC00, 0x80000000, 0x5, 0x200])
    return rng.randrange(1 << 32)


def gen_allied(rng):
    st = L.base_state(rng)
    f = FORCES + rng.randrange(3) * 12 if rng.random() > 0.04 else rng.choice(L.UNMAPPED)
    st.fill(FORCES, 3 * 12)
    if f not in L.UNMAPPED:
        st.put(f + 8, 1, L.pick(rng, [0, 0, 1, 2, 2, 3], [9, 0x80, 0xFF, 0x0A], 0.15))
    other = L.pick(rng, [0, 0, 1, 2, 2, 3], [0x100, 0x102, 0xFFFFFFFF, 0x80000000, 9, 0xFF, 0x200], 0.2)
    return st, [f, other]


def gen_first(rng):
    st = L.base_state(rng)
    pool(st, rng)
    return st, [mask(rng)]


def gen_next(rng):
    st = L.base_state(rng)
    pool(st, rng)
    u = UNIT(rng.randrange(NUNITS)) if rng.random() > 0.03 else rng.choice(L.UNMAPPED)
    return st, [u, mask(rng)]


FUNCS = {"force_is_allied": gen_allied, "unit_pool_first": gen_first, "unit_next": gen_next}


def note_path(fname, st, args, exp):
    if fname == "force_is_allied":
        return "yes" if exp[1] else "no"
    if fname == "unit_next" and args[0] not in L.UNMAPPED and word(st, args[0] + 0x14):
        return "own list"
    return ("unit" if exp[1] else "none") + (", unmapped reads" if exp[2] else "")


# planted bugs: (file, exact text, replacement); each text occurs once in its file
F = "forces.c"
PLANTS = [
    (F, "    return forces + type * (gaddr)sizeof(Force);", "    return forces + type * 8u;"),
    (F, "    gaddr forces = READ_FIELD(ctx, UnitPool, G_UnitPool, forces);",
     "    gaddr forces = guest_ptr(ctx, G_UnitPool);"),
    (F, "    if (type == other_type)\n        return 1;\n", ""),
    (F, "    if (type == other_type)\n", "    if ((type & 0xFFu) == (other_type & 0xFFu))\n"),
    (F, "    if (other_type == 0 && type == FORCE_TYPE_ALLY_OF_ZERO)\n        return 1;\n", ""),
    (F, "    return type == 0 && other_type == FORCE_TYPE_ALLY_OF_ZERO;", "    return type == 0 && other_type == 1u;"),
    (F, "    for (uint32_t type = from; type < FORCE_COUNT; type++) {",
     "    for (uint32_t type = from; type < FORCE_COUNT - 1; type++) {"),
    (F, "    for (uint32_t type = from; type < FORCE_COUNT; type++) {",
     "    for (uint32_t type = from; type <= FORCE_COUNT; type++) {"),
    (F, "        if (!(force_mask & (1u << type)))", "        if (force_mask & (1u << type))"),
    (F, "        if (unit != 0)\n            return unit;", "        return unit;"),
    (F, "    return first_unit_from(ctx, force_mask, 0);", "    return first_unit_from(ctx, force_mask, 1);"),
    (F, "    if (next != 0)\n        return next;\n", ""),
    (F, "(uint32_t)READ_FIELD(ctx, Force, force, type) + 1u);", "(uint32_t)READ_FIELD(ctx, Force, force, type));"),
    (F, "    gaddr next = READ_FIELD(ctx, Unit, unit, next);", "    gaddr next = guest_ptr(ctx, unit + 0x10u);"),
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
