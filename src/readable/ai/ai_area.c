/* What the AI sees around a tile: an escape edge, enemies close by, a partner
   to pair with (Fates class AIThink).

   Every function here only reads. Plain-language description: docs/AI.md
   section 4.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   game's ARM code: src/readable/ai/tests/ai_perm_diff.py. */

#include "ai_perm.h"

/* the map image (map width, height and the playable area in bytes 0..5) */
static gaddr map_image(Context *ctx) {
    return guest_ptr(ctx, G_MapImage);
}

/* Can the AI's unit leave the map from (x, y)? On each edge of the playable
   area that (x, y) lies on, in the order left, top, right, bottom: the tile
   one step outside (its TerrainCost column in the map image) costs the unit
   0 or more (TerrainCost::GetCostFromUnit). Otherwise: a gimmick of type 6
   reachable from (x, y) (AIThink::GetTrickFromAccess). Coordinates are not
   checked; the edges are compared as full 32-bit values.
   Guest function: 0x004CC978 AIThink::IsEscapePosition(int,int). */
uint32_t ai_is_escape_position(Context *ctx, gaddr think, int32_t x, int32_t y) {
    if (!fe_static_ready(ctx, S_CostGuard)) /* GetCostFromUnit's cache */
        return fe_use_original(ctx);
    gaddr image = map_image(ctx);
    if ((int32_t)READ_FIELD(ctx, MapImage, image, play_x_min) == x) {
        uint32_t column = guest_u8(ctx, image + MAPIMAGE_COST_COLUMN + move_tile(x - 1, y));
        if ((int32_t)guest_call2(ctx, AI_TerrainCostFromUnit, guest_ptr(ctx, think + AITHINK_UNIT), column) >= 0)
            return 1;
    }
    image = map_image(ctx);
    if ((int32_t)READ_FIELD(ctx, MapImage, image, play_y_min) == y) {
        uint32_t column = guest_u8(ctx, image + MAPIMAGE_COST_COLUMN + move_tile(x, y - 1));
        if ((int32_t)guest_call2(ctx, AI_TerrainCostFromUnit, guest_ptr(ctx, think + AITHINK_UNIT), column) >= 0)
            return 1;
    }
    image = map_image(ctx);
    if ((int32_t)READ_FIELD(ctx, MapImage, image, play_x_end) - 1 == x) {
        uint32_t column = guest_u8(ctx, image + MAPIMAGE_COST_COLUMN + move_tile(x + 1, y));
        if ((int32_t)guest_call2(ctx, AI_TerrainCostFromUnit, guest_ptr(ctx, think + AITHINK_UNIT), column) >= 0)
            return 1;
    }
    image = map_image(ctx);
    if ((int32_t)READ_FIELD(ctx, MapImage, image, play_y_end) - 1 == y) {
        uint32_t column = guest_u8(ctx, image + MAPIMAGE_COST_COLUMN + move_tile(x, y + 1));
        if ((int32_t)guest_call2(ctx, AI_TerrainCostFromUnit, guest_ptr(ctx, think + AITHINK_UNIT), column) >= 0)
            return 1;
    }
    return guest_call3(ctx, AI_GetTrickFromAccess, (uint32_t)x, (uint32_t)y, 6u) != 0 ? 1u : 0u;
}

/* The box the two area scans walk: radius r around (x, y), cut to the
   playable area, each bound kept to 16 bits (signed) as the game stores it. */
typedef struct {
    int32_t x0, y0, x1, y1;
} AiBox;

static AiBox area_box(Context *ctx, int32_t x, int32_t y, int32_t r) {
    AiBox b;
    int32_t v, lim;
    v = fe_add32(x, -r);
    lim = READ_FIELD(ctx, MapImage, map_image(ctx), play_x_min);
    b.x0 = (int16_t)(v < lim ? lim : v);
    v = fe_add32(y, -r);
    lim = READ_FIELD(ctx, MapImage, map_image(ctx), play_y_min);
    b.y0 = (int16_t)(v < lim ? lim : v);
    v = fe_add32(x, r);
    lim = (int32_t)READ_FIELD(ctx, MapImage, map_image(ctx), play_x_end) - 1;
    b.x1 = (int16_t)(lim < v ? lim : v);
    v = fe_add32(y, r);
    lim = (int32_t)READ_FIELD(ctx, MapImage, map_image(ctx), play_y_end) - 1;
    b.y1 = (int16_t)(lim < v ? lim : v);
    return b;
}

/* |dx| + |dy| between (x, y) and (tx, ty), with the game's 32-bit wrap */
static int32_t distance(int32_t x, int32_t y, int32_t tx, int32_t ty) {
    return fe_add32(ai_abs(fe_add32(x, -tx)), ai_abs(fe_add32(y, -ty)));
}

/* How dangerous is (x, y) for the AI's army: the number of units 1 or 2
   tiles away (|dx| + |dy|) inside the playable area whose force is not
   allied with the force of the current turn (the map situation's force byte)
   and that have more than 1 HP; at most 63.
   Guest function: 0x004D0820 AIThink::GetSighOfDeathScore(int,int). */
uint32_t ai_sigh_of_death_score(Context *ctx, int32_t x, int32_t y) {
    AiBox b = area_box(ctx, x, y, 2);
    uint32_t count = 0;
    for (int32_t ty = b.y0; ty <= b.y1; ty++) {
        for (int32_t tx = b.x0; tx <= b.x1; tx++) {
            if ((uint32_t)distance(x, y, tx, ty) - 1u >= 2u)
                continue;
            gaddr unit = guest_call3(ctx, AI_ImageUnitGetUnit, map_image(ctx) + MAPIMAGE_UNITS, (uint32_t)tx,
                                     (uint32_t)ty);
            if (unit == 0)
                continue;
            uint32_t turn = READ_FIELD(ctx, Situation, guest_ptr(ctx, G_Situation), force_index);
            if (guest_call2(ctx, AI_ForceIsAllied, READ_FIELD(ctx, Unit, unit, force), turn) != 0)
                continue;
            if (guest_s8(ctx, unit + UNIT_HP) > 1)
                count++;
        }
    }
    return count > 63u ? 63u : count;
}

/* Could the unit pair up from (x, y)? Always when it already has a partner;
   otherwise when a unit of the same force type stands on one of the four
   tiles next to (x, y) inside the playable area.
   Guest function: 0x004CDF40 AIThink::IsDualSupportUnit(Unit*,int,int). */
uint32_t ai_is_dual_support_unit(Context *ctx, gaddr unit, int32_t x, int32_t y) {
    if (READ_FIELD(ctx, Unit, unit, pair_partner) != 0)
        return 1;
    AiBox b = area_box(ctx, x, y, 1);
    for (int32_t ty = b.y0; ty <= b.y1; ty++) {
        for (int32_t tx = b.x0; tx <= b.x1; tx++) {
            if (distance(x, y, tx, ty) != 1)
                continue;
            gaddr other = guest_call3(ctx, AI_ImageUnitGetUnit, map_image(ctx) + MAPIMAGE_UNITS, (uint32_t)tx,
                                      (uint32_t)ty);
            if (other == 0)
                continue;
            gaddr force = READ_FIELD(ctx, Unit, other, force);
            gaddr own = READ_FIELD(ctx, Unit, unit, force);
            if (READ_FIELD(ctx, Force, force, type) == READ_FIELD(ctx, Force, own, type))
                return 1;
        }
    }
    return 0;
}

RECOMP_OVERRIDE(0x004CC978) {
    FE_ENTRY(0x004CC978, ai_is_escape_position, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x004D0820) {
    FE_ENTRY(0x004D0820, ai_sigh_of_death_score, FE_ARG_S(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x004CDF40) {
    FE_ENTRY(0x004CDF40, ai_is_dual_support_unit, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}
