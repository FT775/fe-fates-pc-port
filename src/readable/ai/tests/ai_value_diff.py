#!/usr/bin/env python3
"""Host differential test of src/readable/ai/ai_value.c and ai_think.c against the game's own ARM code.

    python src/readable/ai/tests/ai_value_diff.py              all 8 functions, 300 cases each
    python src/readable/ai/tests/ai_value_diff.py -n 1500 --seed 7     the long run
    python src/readable/ai/tests/ai_value_diff.py --only ai_value_argument_address
    python src/readable/ai/tests/ai_value_diff.py --plant      also plant bugs: each must be caught

Round 17 (these two files had no host test; src/readable/ai/tests/ai_perm_diff.py tests the other three files
of the folder). The method and the shared code: src/readable/battle/tests/leaf_diff.py. Made-up states (test
values only): AI script argument values (s16) of every special kind (-1 .. -8, 0) and random or extreme ones,
orders 0 .. 3 and huge, value pointers that are unmapped; the AI think holder chain (G_AIThinkHolder ->
root -> state -> move_over) with links that are 0 or unmapped and move_over values of every bit width (every pointer to a word aligned, as the game's are); units
whose signed tile bytes are compared with x and y given sign-extended, zero-extended, equal or not.

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

NAME = "ai_value_diff"
SRC_AI = SRC_DIR = os.path.join(ROOT, "src", "readable", "ai")
FILES = ("ai_value.c", "ai_think.c")
HEADER = '#include "fe.h"'
OUT = os.path.join(ROOT, "build", "readable", "ai_value")

OVERRIDES = {
    "ai_value_is_argument": 0x00543DF4, "ai_value_argument_address": 0x00543E0C, "ai_value_is_max": 0x00543E28,
    "ai_value_is_skip": 0x00543E44, "ai_value_is_signal": 0x00543E58, "ai_value_is_default": 0x00543E6C,
    "ai_think_is_move_over": 0x004C8584, "ai_think_is_move_over_at": 0x004C8544,
}

G_AITHINK_HOLDER = 0x006D0EBC
VAL = 0x08000100   # the s16 argument value (always 2-aligned: arm_mini aligns word loads down, the game's fields are aligned)
ROOT_OBJ = 0x08001000
STATE = 0x08002000
UNIT = lambda k: 0x08010000 + k * 0x140  # noqa: E731
VALUES = [-1, -2, -3, -4, -5, -6, -7, -8, 0, 0, 1, 3, -1, -4, -7]
VALUES_ODD = [-0x8000, 0x7FFF, -9, -100, 100, 0x4000, -0x7FF9, 7, 4]


def put_value(st, rng) -> int:
    """The s16 value at a random aligned address with junk around it; or an unmapped pointer."""
    if rng.random() < 0.05:
        return rng.choice(L.UNMAPPED)
    addr = VAL + rng.choice([0, 0, 2, 4, 6])
    st.fill(addr - 4, 12)
    st.put(addr, 2, L.pick(rng, VALUES, VALUES_ODD, 0.2) & 0xFFFF)
    return addr


def gen_value(rng):
    st = L.base_state(rng)
    return st, [put_value(st, rng), rng.randrange(1 << 32), rng.randrange(1 << 32)]  # junk in r1, r2


def gen_argument_address(rng):
    st = L.base_state(rng)
    v = put_value(st, rng)
    order = L.pick(rng, [0, 1, 2, 3], [4, 5, 0xFF, 0x7FFFFFFF, 0xFFFFFFFF, 0x80000000, 0x40000000], 0.2)
    unit = L.pick(rng, [UNIT(0), UNIT(1), UNIT(2) + 1], [0, 0xFFFFFFF0, 0x7FFFFFFF, rng.randrange(1 << 32)], 0.2)
    return st, [v, order, unit]


def put_think(st, rng) -> None:
    """The holder chain; each link sometimes 0 or unmapped (never misaligned: arm_mini aligns word loads down)."""
    r = rng.random()
    root = ROOT_OBJ if r > 0.1 else rng.choice([0] + L.UNMAPPED)
    st.put(G_AITHINK_HOLDER, 4, root)
    if root == ROOT_OBJ:
        st.fill(ROOT_OBJ, 0x20)
        r = rng.random()
        state = STATE if r > 0.1 else rng.choice([0, STATE + 0x40] + L.UNMAPPED)
        st.put(ROOT_OBJ + 0x10, 4, state)
        if state in (STATE, STATE + 0x40):
            st.fill(state + 0x140, 0x18)
            mo = L.pick(rng, [0, 0, 0, 1, 1, 2], [0x100, 0x10000, 0x1000000, 0x80000000, 0xFFFFFFFF], 0.25)
            st.put(state + 0x14C, 4, mo)


def gen_move_over(rng):
    st = L.base_state(rng)
    put_think(st, rng)
    return st, [rng.randrange(1 << 32) for _ in range(3)]  # junk argument registers


def gen_move_over_at(rng):
    st = L.base_state(rng)
    put_think(st, rng)
    unit = UNIT(rng.randrange(3)) if rng.random() > 0.05 else rng.choice(L.UNMAPPED)
    if unit not in L.UNMAPPED:
        st.fill(unit, 0x140)
        st.put(unit + 0xF4, 1, L.pick(rng, [0, 1, 5, 12, 20, 31], [0xFF, 0x80, 0x7F, 0xFE], 0.25))
        st.put(unit + 0xF5, 1, L.pick(rng, [0, 2, 7, 15, 31], [0xFF, 0x80, 0x7F, 0xFD], 0.25))
    mx = st.mem.get(unit + 0xF4, 0) if unit not in L.UNMAPPED else 0
    my = st.mem.get(unit + 0xF5, 0) if unit not in L.UNMAPPED else 0

    def coord(b):
        r = rng.random()
        if r < 0.5:
            return L.s32(L.sx(b, 8))       # the same, sign-extended
        if r < 0.65:
            return b                       # zero-extended: equal only when b < 0x80
        if r < 0.8:
            return L.s32(L.sx(b, 8) + rng.choice([1, -1, 0x100, -0x100]))
        return rng.randrange(1 << 32)
    return st, [unit, coord(mx), coord(my)]


FUNCS = {
    "ai_value_is_argument": gen_value, "ai_value_argument_address": gen_argument_address,
    "ai_value_is_max": gen_value, "ai_value_is_skip": gen_value, "ai_value_is_signal": gen_value,
    "ai_value_is_default": gen_value,
    "ai_think_is_move_over": gen_move_over, "ai_think_is_move_over_at": gen_move_over_at,
}


def note_path(fname, st, args, exp):
    if fname.startswith("ai_think"):
        root = int.from_bytes(bytes(st.mem.get(G_AITHINK_HOLDER + i, 0) for i in range(4)), "little")
        return ("unmapped link" if exp[2] else "chain read") + (", yes" if exp[1] else ", no")
    if fname == "ai_value_argument_address":
        return "unmapped value" if exp[2] else "value read"
    return ("unmapped value" if exp[2] else "value read") + (", yes" if exp[1] else ", no")


# planted bugs: (file, exact text, replacement); each text occurs once in its file
V, T = "ai_value.c", "ai_think.c"
PLANTS = [
    (V, "    return guest_s16(ctx, value);", "    return guest_u16(ctx, value);"),
    (V, "    return v <= AI_VALUE_ARGUMENT_FIRST && v > AI_VALUE_ARGUMENT_FIRST - AI_ARGUMENTS_PER_ORDER;",
     "    return v <= AI_VALUE_ARGUMENT_FIRST && v >= AI_VALUE_ARGUMENT_FIRST - AI_ARGUMENTS_PER_ORDER;"),
    (V, "    return v <= AI_VALUE_ARGUMENT_FIRST && v > AI_VALUE_ARGUMENT_FIRST - AI_ARGUMENTS_PER_ORDER;",
     "    return v < AI_VALUE_ARGUMENT_FIRST && v > AI_VALUE_ARGUMENT_FIRST - AI_ARGUMENTS_PER_ORDER;"),
    (V, "(uint32_t)AI_VALUE_ARGUMENT_FIRST - (uint32_t)ai_value(ctx, value);",
     "(uint32_t)ai_value(ctx, value) - (uint32_t)AI_VALUE_ARGUMENT_FIRST;"),
    (V, "    uint32_t slot = order * AI_ARGUMENTS_PER_ORDER + argument;",
     "    uint32_t slot = order * 3u + argument;"),
    (V, "ai_arguments) + slot * 2u;", "ai_arguments) + slot;"),
    (V, "    return FIELD_ADDR(Unit, unit, ai_arguments) + slot * 2u;",
     "    return FIELD_ADDR(Unit, unit, ai_arguments) + (slot & 0xFFFFu) * 2u;"),
    (V, "    return ai_value(ctx, value) == AI_VALUE_MAX;", "    return ai_value(ctx, value) == AI_VALUE_SKIP;"),
    (V, "    return ai_value(ctx, value) == AI_VALUE_SKIP;", "    return ai_value(ctx, value) <= AI_VALUE_SKIP;"),
    (V, "    return ai_value(ctx, value) < 0;", "    return ai_value(ctx, value) <= 0;"),
    (V, "    return ai_value(ctx, value) == AI_VALUE_DEFAULT;", "    return (ai_value(ctx, value) & 0xFF) == 0xFF;"),
    (T, "    return READ_FIELD(ctx, AIThinkState, state, move_over);",
     "    return READ_FIELD(ctx, AIThinkState, state, move_over) & 0xFFu;"),
    (T, "    gaddr state = READ_FIELD(ctx, AIThinkRoot, root, state);",
     "    gaddr state = guest_ptr(ctx, root + 0x14u);"),
    (T, "    return move_over(ctx) != 0;", "    return move_over(ctx) == 1;"),
    (T, "    if (move_over(ctx) == 0)\n        return 0;\n", ""),
    (T, "    if ((uint32_t)(int32_t)READ_FIELD(ctx, Unit, unit, map_x) != x)",
     "    if ((uint32_t)(uint8_t)READ_FIELD(ctx, Unit, unit, map_x) != x)"),
    (T, "    return (uint32_t)(int32_t)READ_FIELD(ctx, Unit, unit, map_y) == y;",
     "    return (uint32_t)(int32_t)READ_FIELD(ctx, Unit, unit, map_x) == y;"),
    (T, "    return (uint32_t)(int32_t)READ_FIELD(ctx, Unit, unit, map_y) == y;",
     "    return (uint8_t)READ_FIELD(ctx, Unit, unit, map_y) == (uint8_t)y;"),
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
