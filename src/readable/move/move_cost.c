/* Movement costs and routes (Fates classes TerrainCost, Unit, map::Route,
   Job): what a step onto a terrain costs a unit, whether a unit ignores
   terrain costs, what a whole route costs and where it ends, and whether a
   class flies or rides.
   Plain-language description: docs/MOVE.md sections 3 and 4.

   The TerrainCost table (GameData) is one row per movement class (Job +0x5C,
   JobData.move_cost_class), one signed byte per terrain cost column (the
   TerrainTile's move_cost_column; the map image keeps each tile's column at
   +0xC08). A negative cost means the class cannot enter. Rows are padded to
   a multiple of 4 bytes.

   A route is a list of step bytes ending with 0x80: bit 0 = one tile left,
   bit 1 = right, bit 3 = up, bit 2 = down (bit 0 wins over bit 1, bit 3 over
   bit 2).

   All are readers: they store nothing. Some fill one-time caches the first
   time; the readable code gives up while one is cold, before reading anything
   else. Guest calls left: the ones the game makes (move.h), in the game's
   order (docs/DECISIONS.md F-018).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/move/tests/move_diff.py. */

#include "move.h"

/* The first byte of a TerrainCost row, and the row stride: the header's
   column count rounded up to 4. */
static gaddr cost_rows(Context *ctx, gaddr *stride) {
    gaddr header = guest_ptr(ctx, G_TerrainCost);
    *stride = (READ_FIELD(ctx, TerrainCostHeaderData, header, columns) + 3u) & ~3u;
    return header + 4u;
}

/* The TerrainCost row of a movement class (its first byte; no range check).
   Guest function: 0x001A67EC TerrainCost::Get(int). */
gaddr terrain_cost_row(Context *ctx, int32_t row) {
    gaddr stride;
    gaddr rows = cost_rows(ctx, &stride);
    return rows + stride * (gaddr)row;
}

/* What entering a tile of this cost column costs the unit: its class's row.
   When that is negative (impassable) and the unit, its Person or its class
   has the "own terrain cost" PersonFlag bit, the cost of movement class 0 is
   used instead (still negative if class 0 cannot enter either).
   Guest function: 0x001A6708 TerrainCost::GetCostFromUnit(const Unit*,int). */
int32_t terrain_cost_for_unit(Context *ctx, gaddr unit, int32_t column) {
    if (!fe_static_ready(ctx, S_CostGuard))
        return (int32_t)fe_use_original(ctx);
    gaddr stride;
    gaddr rows = cost_rows(ctx, &stride);
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    uint32_t move_class = READ_FIELD(ctx, JobData, job, move_cost_class);
    int32_t cost = guest_s8(ctx, rows + stride * move_class + (gaddr)column);
    if (cost >= 0)
        return cost;
    uint64_t mask = guest_u64(ctx, S_CostOwnMask);
    uint64_t flags = READ_FIELD(ctx, Unit, unit, private_flags) |
                     READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), flags) |
                     READ_FIELD(ctx, JobData, job, flags);
    if (flags & mask)
        cost = guest_s8(ctx, rows + (gaddr)column);
    return cost;
}

/* The caches Unit::IsCostFree reads, its own and those of Unit::GetCategory
   (which it calls): asked first, so neither override gives up inside a caller. */
static int cost_free_ready(Context *ctx) {
    return fe_static_ready(ctx, S_FreeItemGuard) && fe_static_ready(ctx, S_FreeSkillGuard) &&
           fe_static_ready(ctx, S_FreeShooterGuard) && fe_static_ready(ctx, S_CatGuardA) &&
           fe_static_ready(ctx, S_CatGuardB) && fe_static_ready(ctx, S_CatGuardC) &&
           fe_static_ready(ctx, S_CatGuardD) && fe_static_ready(ctx, S_CatGuardE);
}

/* Whether the unit pays at most 1 for every passable tile: a unit of the
   "shooter" category (ballistae) with the "amphibious" skill, or a unit
   carrying an item with the "Fujin Yumi" item skill whose bonus applies to it
   (Unit::IsItemEnhanceHave). The items are tested slot by slot.
   Guest function: 0x0052AB90 Unit::IsCostFree(void) const. */
uint32_t unit_is_cost_free(Context *ctx, gaddr unit) {
    if (!cost_free_ready(ctx))
        return fe_use_original(ctx);
    uint32_t shooter = guest_u16(ctx, S_FreeShooterMask);
    if ((guest_call1(ctx, MOVE_UnitGetCategory, unit) & shooter) != 0 &&
        guest_call2(ctx, MOVE_UnitIsEquipSkill, unit, (uint32_t)(int32_t)guest_s16(ctx, S_FreeSkill)) != 0)
        return 1;
    for (uint32_t slot = 0; slot < 5u; slot++) {
        gaddr item = FIELD_ADDR(Unit, unit, items) + slot * 4u;
        gaddr data = guest_call1(ctx, MOVE_ItemToData, item);
        if ((READ_FIELD(ctx, ItemData, data, flags) & guest_u64(ctx, S_FreeItemMask)) != 0 &&
            guest_call3(ctx, MOVE_UnitIsItemEnhanceHave, unit, item, 1u) != 0)
            return 1;
    }
    return 0;
}

/* One route step's moves: -1, 0 or +1 across, and down. */
static int32_t step_dx(uint32_t step) {
    return (step & 1u) ? -1 : (step & 2u) ? 1 : 0;
}

static int32_t step_dy(uint32_t step) {
    return (step & 8u) ? -1 : (step & 4u) ? 1 : 0;
}

/* What walking the route from (x, y) costs the unit: the sum over the tiles
   entered of TerrainCost::GetCostFromUnit for the tile's cost column (the map
   image's +0xC08 grid); a cost above 1 counts 1 for a cost-free unit
   (Unit::IsCostFree, asked only then), a negative one counts 0.
   Guest function: 0x00394BC0 map::Route::GetRouteCost(Unit*,int,int,const unsigned char*). */
int32_t route_cost(Context *ctx, gaddr unit, int32_t x, int32_t y, gaddr route) {
    if (!fe_static_ready(ctx, S_CostGuard) || !cost_free_ready(ctx))
        return (int32_t)fe_use_original(ctx); /* the callees' caches: no give-up inside them */
    int32_t total = 0;
    uint32_t i = 0;
    uint32_t step = guest_u8(ctx, route);
    while (step != ROUTE_END) {
        step = guest_u8(ctx, route + i); /* the game reads each step byte twice */
        x = fe_add32(x, step_dx(step));
        y = fe_add32(y, step_dy(step));
        gaddr image = guest_ptr(ctx, G_MapImage);
        uint32_t column = guest_u8(ctx, image + MAPIMAGE_COST_COLUMN + move_tile(x, y));
        int32_t cost = (int32_t)guest_call2(ctx, MOVE_TerrainCostFromUnit, unit, column);
        if (cost > 1) {
            if (guest_call1(ctx, MOVE_UnitIsCostFree, unit) != 0)
                cost = 1;
        } else if (cost < 0) {
            cost = 0;
        }
        total = fe_add32(total, cost);
        i++;
        step = guest_u8(ctx, route + i);
    }
    return total;
}

/* Where the route ends: the start column (or row) plus every step's move.
   Guest functions: 0x00395B50 map::Route::GetGoalX(int,const unsigned char*),
   0x00395B88 map::Route::GetGoalY(int,const unsigned char*). */
int32_t route_goal_x(Context *ctx, int32_t x, gaddr route) {
    if (guest_u8(ctx, route) & ROUTE_END)
        return x;
    uint32_t next;
    do {
        x = fe_add32(x, step_dx(guest_u8(ctx, route)));
        route++;
        next = guest_u8(ctx, route);
    } while (!(next & ROUTE_END));
    return x;
}

int32_t route_goal_y(Context *ctx, int32_t y, gaddr route) {
    if (guest_u8(ctx, route) & ROUTE_END)
        return y;
    uint32_t next;
    do {
        y = fe_add32(y, step_dy(guest_u8(ctx, route)));
        route++;
        next = guest_u8(ctx, route);
    } while (!(next & ROUTE_END));
    return y;
}

/* The step at which the stored route (map::Route: step bytes, then the step
   count at +0x80 and the start at +0x81/+0x82) stands on (x, y), or -1. The
   start is step 0; the tile reached by the last step is never tested.
   Guest function: 0x0052650C map::Route::GetCross(int,int) const. */
int32_t route_cross(Context *ctx, gaddr route, int32_t x, int32_t y) {
    int32_t count = guest_u8(ctx, route + ROUTE_COUNT);
    int32_t cx = guest_s8(ctx, route + ROUTE_START_X);
    int32_t cy = guest_s8(ctx, route + ROUTE_START_Y);
    for (int32_t i = 0; i < count; i++) {
        if (x == cx && y == cy)
            return i;
        uint32_t step = guest_u8(ctx, route + (gaddr)i);
        cx = fe_add32(cx, step_dx(step));
        cy = fe_add32(cy, step_dy(step));
    }
    return -1;
}

/* Whether a class is in the "flying" (or "mounted") class category.
   Guest functions: 0x00524980 Job::IsFlyer(void) const, 0x00524A7C Job::IsRider(void) const. */
uint32_t job_is_flyer(Context *ctx, gaddr job) {
    if (!fe_static_ready(ctx, S_FlyerGuard))
        return fe_use_original(ctx);
    return (READ_FIELD(ctx, JobData, job, category) & guest_u16(ctx, S_FlyerMask)) != 0 ? 1u : 0u;
}

uint32_t job_is_rider(Context *ctx, gaddr job) {
    if (!fe_static_ready(ctx, S_RiderGuard))
        return fe_use_original(ctx);
    return (READ_FIELD(ctx, JobData, job, category) & guest_u16(ctx, S_RiderMask)) != 0 ? 1u : 0u;
}

RECOMP_OVERRIDE(0x001A67EC) {
    FE_ENTRY(0x001A67EC, terrain_cost_row, FE_ARG_S(0));
}

RECOMP_OVERRIDE(0x001A6708) {
    FE_ENTRY(0x001A6708, terrain_cost_for_unit, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0052AB90) {
    FE_ENTRY(0x0052AB90, unit_is_cost_free, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00394BC0) {
    FE_ENTRY(0x00394BC0, route_cost, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2), FE_ARG(3));
}

RECOMP_OVERRIDE(0x00395B50) {
    FE_ENTRY(0x00395B50, route_goal_x, FE_ARG_S(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00395B88) {
    FE_ENTRY(0x00395B88, route_goal_y, FE_ARG_S(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052650C) {
    FE_ENTRY(0x0052650C, route_cross, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x00524980) {
    FE_ENTRY(0x00524980, job_is_flyer, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00524A7C) {
    FE_ENTRY(0x00524A7C, job_is_rider, FE_ARG(0));
}
