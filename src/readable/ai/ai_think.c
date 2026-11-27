/* The AI's move target (Fates class AIThink).

   The AI keeps its sequence state behind a global holder (G_AIThinkHolder ->
   AIThinkRoot -> AIThinkState). AIThinkState.move_over is non-zero while the
   AI sequence has a move target [high for the reads, low for the meaning:
   the Awakening counterpart was the AI sequence's "forced unit" index].

   Both functions are the same code shape as Awakening's ai_has_forced_unit
   and ai_forced_unit_stands_at (config/readable/xmap_reference.csv,
   confidence medium: same instructions, other offsets), re-read in Fates:
   the holder chain at 0x004C8584 / 0x004C8544 and the unit's tile bytes at
   Unit+0xF4 / +0xF5.

   Neither writes guest memory, calls guest code or uses a one-time cache.

   Status: UNVERIFIED (below shadow-clean). */

#include "fe.h"

static uint32_t move_over(Context *ctx) {
    gaddr root = guest_ptr(ctx, G_AIThinkHolder);
    gaddr state = READ_FIELD(ctx, AIThinkRoot, root, state);
    return READ_FIELD(ctx, AIThinkState, state, move_over);
}

/* Whether the AI sequence has a move target.
   Guest function: 0x004C8584 AIThink::IsMoveOver() -> 1 or 0. */
int ai_think_is_move_over(Context *ctx) {
    return move_over(ctx) != 0;
}

/* Whether the AI sequence has a move target and the unit stands on (x, y).
   The unit is not read without a target, and its y only when x matches;
   x and y are compared as full 32-bit values with the signed tile bytes.
   Guest function: 0x004C8544 AIThink::IsMoveOver(Unit*, int, int) -> 1 or 0. */
int ai_think_is_move_over_at(Context *ctx, gaddr unit, uint32_t x, uint32_t y) {
    if (move_over(ctx) == 0)
        return 0;
    if ((uint32_t)(int32_t)READ_FIELD(ctx, Unit, unit, map_x) != x)
        return 0;
    return (uint32_t)(int32_t)READ_FIELD(ctx, Unit, unit, map_y) == y;
}

RECOMP_OVERRIDE(0x004C8584) {
    FE_ENTRY0(0x004C8584, ai_think_is_move_over);
}

RECOMP_OVERRIDE(0x004C8544) {
    FE_ENTRY(0x004C8544, ai_think_is_move_over_at, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}
