/* Who stands where, and where a unit may go (Fates classes UnitPool,
   map::Image::Unit, map::Deploy, the script's UnitGetByPosition): the unit of
   a pool number, the unit on a tile, the move image's value of a tile, and
   whether the move-range fill may spread through a tile.
   Plain-language description: docs/MOVE.md section 5.

   The map image keeps, at +0x8, a 32 x 32 grid of pool numbers (0 = nobody;
   map::Image::Unit); UnitPool::Get (a guest call, not rewritten: docs/MOVE.md
   section 6) turns a number into its Unit (0x140 bytes each, numbers from 1). A move image is a 32 x 32 grid of signed bytes the
   move-range code fills (below 0: not reached).

   All are readers: they store nothing. map::Deploy::IsFill fills a one-time
   cache the first time (a PersonFlag bit found by name); the readable code
   gives up while it is cold, before reading anything else. Guest calls left:
   the ones the game makes (move.h), in the game's order (docs/DECISIONS.md
   F-018). Force::Get (a NOP that runs into UnitPool::GetForce) is done inline,
   as in src/readable/unit/forces.c.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/move/tests/move_diff.py. */

#include "move.h"

/* The unit standing on (x, y) of this unit grid, or 0.
   Guest function: 0x00526424 map::Image::Unit::GetUnit(int,int) const. */
gaddr image_unit_at(Context *ctx, gaddr image, int32_t x, int32_t y) {
    return guest_call1(ctx, MOVE_UnitPoolGet, guest_u8(ctx, image + move_tile(x, y)));
}

/* The script's "pool number of the unit on (x, y)": 0 without a loaded map or
   when nobody stands there.
   Guest function: 0x003ABE80 anonymous_namespace::UnitGetByPosition(cmvm::CmContext*,int,int). */
int32_t script_unit_at(Context *ctx, gaddr script, int32_t x, int32_t y) {
    (void)script;
    if (guest_call(ctx, MOVE_MapGet, 0u, 0u, 0u, 0u) == 0)
        return 0;
    gaddr units = guest_ptr(ctx, G_MapImage) + MAPIMAGE_UNITS;
    gaddr unit = guest_call3(ctx, MOVE_ImageUnitGetUnit, units, (uint32_t)x, (uint32_t)y);
    if (unit == 0)
        return 0;
    return guest_u8(ctx, unit + UNIT_NUMBER);
}

/* The terrain record of the tile at (x, y) of the map image's grid. */
static gaddr terrain_at(Context *ctx, int32_t x, int32_t y) {
    gaddr image = guest_ptr(ctx, G_MapImage);
    return guest_call1(ctx, MOVE_TerrainGet, guest_u8(ctx, FIELD_ADDR(MapImage, image, draw_terrain) + move_tile(x, y)));
}

/* The move image's value at (x, y): -1 on a tile whose terrain has the
   "blocked" attribute bit, else the image's signed byte.
   Guest function: 0x005278A0 map::Deploy::MoveImage::Get(int,int) const. */
int32_t move_image_get(Context *ctx, gaddr image, int32_t x, int32_t y) {
    gaddr terrain = terrain_at(ctx, x, y);
    if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & TERRAIN_ATTR_BLOCKED)
        return -1;
    return guest_s8(ctx, image + move_tile(x, y));
}

/* Whether the move-range fill may spread through (x, y): not through a
   "blocked" tile or one the move image has not reached (below 0); always
   through a tile at 0 (the start) or without a unit. With a unit there, the
   deploy's mode bits decide: bit 2 stops at any unit; bit 4 stops at a unit
   that has the "may not move" PersonFlag bit (unit, Person or class) or bit 8
   of Unit +0x54; bit 14 stops at a unit whose force is not allied with the
   deploy's force (Force::IsAllied).
   Guest function: 0x00527734 map::Deploy::IsFill(int,int) const. */
uint32_t deploy_is_fill(Context *ctx, gaddr deploy, int32_t x, int32_t y) {
    if (!fe_static_ready(ctx, S_FillGuard))
        return fe_use_original(ctx);
    gaddr image = READ_FIELD(ctx, MapDeploy, deploy, move_image);
    gaddr terrain = terrain_at(ctx, x, y);
    if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & TERRAIN_ATTR_BLOCKED)
        return 0;
    int32_t reached = guest_s8(ctx, image + move_tile(x, y));
    if (reached < 0)
        return 0;
    if (reached == 0)
        return 1;
    gaddr unit = guest_call3(ctx, MOVE_ImageUnitGetUnit, guest_ptr(ctx, deploy + DEPLOY_UNITS), (uint32_t)x, (uint32_t)y);
    if (unit == 0)
        return 1;
    uint32_t mode = guest_u32(ctx, deploy + DEPLOY_FLAGS);
    if (mode & DEPLOY_FILL_STOP)
        return 0;
    if (mode & DEPLOY_FILL_PASS_TEST) {
        uint64_t mask = guest_u64(ctx, S_FillNoMoveMask);
        uint64_t flags = READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), flags) |
                         READ_FIELD(ctx, Unit, unit, private_flags) |
                         READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), flags);
        if (flags & mask)
            return 0;
        if (guest_u32(ctx, unit + UNIT_IMMOBILE_WORD) & 0x100u)
            return 0;
    }
    if (!(mode & DEPLOY_FILL_ALLY_TEST))
        return 1;
    uint32_t side = guest_u8(ctx, deploy + DEPLOY_FORCE);
    gaddr force = READ_FIELD(ctx, UnitPool, G_UnitPool, forces) + side * (gaddr)sizeof(Force);
    uint32_t type = READ_FIELD(ctx, Force, READ_FIELD(ctx, Unit, unit, force), type);
    return guest_call2(ctx, MOVE_ForceIsAllied, force, type) != 0 ? 1u : 0u;
}

RECOMP_OVERRIDE(0x00526424) {
    FE_ENTRY(0x00526424, image_unit_at, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x003ABE80) {
    FE_ENTRY(0x003ABE80, script_unit_at, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x005278A0) {
    FE_ENTRY(0x005278A0, move_image_get, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x00527734) {
    FE_ENTRY(0x00527734, deploy_is_fill, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}
