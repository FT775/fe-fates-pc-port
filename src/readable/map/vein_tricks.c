/* Map gimmicks and the dragon vein tile (Fates classes map::Trick,
   map::trick::Data, map::trick::Enumerator). Plain-language description:
   docs/VEINS.md.

   Every map gimmick (the game calls them tricks: dragon veins, the regions a
   vein changes, cannons, breakable walls, villages, ...) is one 0x1C-byte
   trick::Data in a list (G_Trick -> Trick.first -> TrickData.next ...). The
   chapter's script declares them; map::Trick::Regist builds the list when the
   map starts. Each has an area (x, y, width, height), a type (11 = dragon
   vein) and a state byte (1 usable, 2 used, 4 ruined).

   The game asks "which gimmick is here" with a trick::Enumerator: a search
   kind, a position, a type (0 = any) and a state mask (0 = any). It walks the
   whole list and keeps every match; every caller rewritten here only uses the
   first match, so trick_find stops there (same answer, nothing allocated).

   Every function here only reads guest memory and calls no guest function.

   Status: UNVERIFIED (below shadow-clean). Each function agrees with the
   original ARM code on generated inputs in the host differential test
   (src/readable/map/tests/vein_diff.py); that is not a shadow result. */

#include "veins.h"

/* The tile a unit stands on to use a cannon, from the cannon's side byte:
   1 left of the area, 2 right of it, 4 below it, 8 above it (each at the
   middle of that edge, rounding toward the top / left), otherwise its middle.
   Returns the column; the row goes to *ay. Reads only the fields the game
   reads for that side (verify counts every read of unmapped memory).
   Guest function: map::trick::Data::GetAccessForCannon(int*,int*) const 0x005269E8. */
int32_t trick_cannon_access(Context *ctx, gaddr data, int32_t *ay) {
    uint8_t side = READ_FIELD(ctx, TrickData, data, cannon_side);
    int32_t x = READ_FIELD(ctx, TrickData, data, x);
    switch (side) {
    case 1:
        *ay = READ_FIELD(ctx, TrickData, data, y) + fe_asr(READ_FIELD(ctx, TrickData, data, height) - 1, 1);
        return x - 1;
    case 2: {
        int32_t ax = x + READ_FIELD(ctx, TrickData, data, width);
        *ay = READ_FIELD(ctx, TrickData, data, y) + fe_asr(READ_FIELD(ctx, TrickData, data, height) - 1, 1);
        return ax;
    }
    case 4: {
        int32_t ax = x + fe_asr(READ_FIELD(ctx, TrickData, data, width) - 1, 1);
        *ay = READ_FIELD(ctx, TrickData, data, y) + READ_FIELD(ctx, TrickData, data, height);
        return ax;
    }
    case 8: {
        int32_t ax = x + fe_asr(READ_FIELD(ctx, TrickData, data, width) - 1, 1);
        *ay = READ_FIELD(ctx, TrickData, data, y) - 1;
        return ax;
    }
    default: {
        int32_t ax = x + fe_asr(READ_FIELD(ctx, TrickData, data, width) - 1, 1);
        *ay = READ_FIELD(ctx, TrickData, data, y) + fe_asr(READ_FIELD(ctx, TrickData, data, height) - 1, 1);
        return ax;
    }
    }
}

/* (x, y) lies in the area x .. x + width - 1, y .. y + height - 1 (signed). */
static int in_area(int32_t x, int32_t y, int32_t x0, int32_t y0, int32_t w, int32_t h) {
    return x0 <= x && x <= x0 + w - 1 && y0 <= y && y <= y0 + h - 1;
}

/* The map's current terrain record under a tile index i = x | y << 5 (no
   range check: the game reads whatever lies there). */
static gaddr terrain_under(Context *ctx, uint32_t tile) {
    gaddr image = guest_ptr(ctx, G_MapImage);
    uint8_t number = guest_u8(ctx, FIELD_ADDR(MapImage, image, terrain) + tile);
    gaddr header = guest_ptr(ctx, G_TerrainHeader);
    return READ_FIELD(ctx, TerrainHeaderData, header, tile_table) + (gaddr)number * (gaddr)sizeof(TerrainTileData);
}

/* Whether a unit standing on (x, y) can reach this gimmick. By type:
   - 25..27 (cannons): only the one tile trick_cannon_access names;
   - 1..8, 11 (dragon veins), 13, 14, 23, 24: any tile of the area;
   - 9, 10: the area grown by one tile on every side, without its four corners;
   - 29: a tile of the area whose current terrain can change (TerrainTile.change_to[0] != 0);
   - every other type (0, 12 = the region a vein changes, 15..22, 28, 30 and up): none.
   Guest function: 0x00526BA0 map::trick::Data::IsAccess(int,int) const. */
int32_t trick_is_access(Context *ctx, gaddr data, int32_t x, int32_t y) {
    uint32_t type = READ_FIELD(ctx, TrickData, data, type);
    if (type - 25u <= 2u) {
        int32_t ay;
        int32_t ax = trick_cannon_access(ctx, data, &ay);
        return x == ax && y == ay;
    }
    switch (type) {
    case 1: case 2: case 3: case 4: case 5: case 6: case 7: case 8:
    case TRICK_TYPE_VEIN: case 13: case 14: case 23: case 24:
    case 9: case 10:
    case TRICK_TYPE_STANDABLE:
        break;
    default:
        return 0; /* the area is not read for these types */
    }
    int32_t x0 = READ_FIELD(ctx, TrickData, data, x), y0 = READ_FIELD(ctx, TrickData, data, y);
    int32_t w = READ_FIELD(ctx, TrickData, data, width), h = READ_FIELD(ctx, TrickData, data, height);
    switch (type) {
    case 9: case 10:
        if (x < x0 - 1 || x > x0 + w || y < y0 - 1 || y > y0 + h)
            return 0;
        if (x != x0 - 1 && x != x0 + w)
            return 1;
        return y != y0 - 1 && y != y0 + h;
    case TRICK_TYPE_STANDABLE:
        if (!in_area(x, y, x0, y0, w, h))
            return 0;
        return READ_FIELD(ctx, TerrainTileData, terrain_under(ctx, (uint32_t)x | (uint32_t)y << 5), change_to[0]) != 0;
    default:
        return in_area(x, y, x0, y0, w, h);
    }
}

/* The first gimmick of the list a map::trick::Enumerator would find:
   - type: 0 takes every type, otherwise TrickData.type must equal it (a byte);
   - mask: 0 takes every state, otherwise TrickData.state must share a bit with it (a byte);
   - search TRICK_SEARCH_AT: the area's top-left corner is (x, y), a negative
     x or y taking any column or row; TRICK_SEARCH_ACCESS: trick_is_access(x, y),
     except that (negative, negative) takes every gimmick.
   0 when none matches. (Guest function: map::trick::Enumerator::Enumerate
   0x00399AB0 keeps every match; the base Enumerator excludes none.) */
gaddr trick_find(Context *ctx, uint32_t search, int32_t x, int32_t y, uint32_t type, uint32_t mask) {
    type &= 0xFFu;
    mask &= 0xFFu;
    gaddr list = guest_ptr(ctx, G_Trick);
    for (gaddr d = READ_FIELD(ctx, Trick, list, first); d != 0; d = READ_FIELD(ctx, TrickData, d, next)) {
        if (type != TRICK_TYPE_ANY && READ_FIELD(ctx, TrickData, d, type) != type)
            continue;
        if (mask != 0 && (READ_FIELD(ctx, TrickData, d, state) & mask) == 0)
            continue;
        if (search == TRICK_SEARCH_AT) {
            if (x >= 0 && READ_FIELD(ctx, TrickData, d, x) != x)
                continue;
            if (y >= 0 && READ_FIELD(ctx, TrickData, d, y) != y)
                continue;
        } else if (!(x < 0 && y < 0) && !trick_is_access(ctx, d, x, y)) {
            continue;
        }
        return d;
    }
    return 0;
}

/* "Is this tile a dragon vein": the first usable gimmick of a type that a unit
   on (x, y) can reach, or 0. With type 11 that is the vein a unit there could
   use (the AI's vein action asks exactly this).
   Guest function: 0x004CF5B4 AIThink::GetTrickFromAccess(int,int,map::trick::Type). */
gaddr trick_at_access(Context *ctx, int32_t x, int32_t y, uint32_t type) {
    return trick_find(ctx, TRICK_SEARCH_ACCESS, x, y, type, TRICK_USABLE);
}

/* The script's state test: the first gimmick of a type whose top-left corner
   is (x, y) (negative = any), and whether its state shares a bit with the
   mask (the fifth argument, on the stack: stack = sp at entry). 0 when no
   gimmick is there. With mask 2 it answers "has this vein been used".
   Guest function: 0x003B0A44 anonymous_namespace::TrickTst(cmvm::CmContext*,int,int,int,int). */
int32_t script_trick_test(Context *ctx, gaddr cm, int32_t x, int32_t y, uint32_t type, gaddr stack) {
    (void)cm;
    uint32_t mask = guest_u32(ctx, stack);
    gaddr d = trick_find(ctx, TRICK_SEARCH_AT, x, y, type, 0);
    if (d == 0)
        return 0;
    return (READ_FIELD(ctx, TrickData, d, state) & mask) != 0;
}

RECOMP_OVERRIDE(0x00526BA0) {
    FE_ENTRY(0x00526BA0, trick_is_access, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x004CF5B4) {
    FE_ENTRY(0x004CF5B4, trick_at_access, FE_ARG_S(0), FE_ARG_S(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x003B0A44) {
    FE_ENTRY(0x003B0A44, script_trick_test, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2), FE_ARG(3), FE_ARG(13));
}
