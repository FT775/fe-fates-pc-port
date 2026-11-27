/* Movement and terrain (Fates classes Terrain, TerrainCost, map::Route,
   map::Deploy, map::Image::Unit, UnitPool, Job, the script's Terrain* and
   UnitGetByPosition, AIThink::GetTerrainScore): the declarations shared by
   src/readable/move/move_terrain.c, move_cost.c and move_occupy.c, the guest
   functions they still call, and the game's one-time caches they read.

   Plain-language description (what each function decides): docs/MOVE.md.

   This header lives next to its sources, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_MOVE_MOVE_H
#define FE_MOVE_MOVE_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-14: it stores nothing
   outside its own stack frame, or only fills a one-time cache of its own.
   Where the game calls (BL) or tail-branches (B) to a function, the readable
   code makes the same guest call in the game's order with the game's
   arguments (docs/DECISIONS.md F-018), also when the callee is an override of
   this batch or an older one. */
#define MOVE_ItemToData 0x003D0EA4u         /* unit::Item::ToData(void) const -> the Item record; reads only */
#define MOVE_UnitIsEquipSkill 0x0052DD04u   /* Unit::IsEquipSkill(short) const (readable: unit_has_skill) */
#define MOVE_UnitIsItemEnhanceHave 0x0052FB98u /* Unit::IsItemEnhanceHave(const unit::Item*,bool) const: does the
                                               carried item's bonus apply to this unit; reads only (not rewritten) */
#define MOVE_UnitGetCategory 0x0052B728u    /* Unit::GetCategory(void) const (readable: unit_category, sheet batch) */
#define MOVE_ForceIsAllied 0x0053C3E0u      /* Force::IsAllied(Force::Type) const (readable: force_is_allied) */
#define MOVE_UnitPoolGet 0x004F6174u        /* UnitPool::Get(int) -> the unit of a pool number; reads only. Not an
                                               override: Mind::GetTradeUnit falls through into it and tier 2 cannot
                                               sample it (docs/MOVE.md section 6) */
/* this batch's overrides, called through the guest where the game calls them */
#define MOVE_TerrainGet 0x004E0AFCu         /* Terrain::Get(int): terrain_record */
#define MOVE_MapGet 0x00342574u             /* Map::Get(void): map_get */
#define MOVE_ImageUnitGetUnit 0x00526424u   /* map::Image::Unit::GetUnit(int,int) const: image_unit_at */
#define MOVE_TerrainCostFromUnit 0x001A6708u /* TerrainCost::GetCostFromUnit(const Unit*,int): terrain_cost_for_unit */
#define MOVE_UnitIsCostFree 0x0052AB90u     /* Unit::IsCostFree(void) const: unit_is_cost_free */

/* ---- globals (addresses from the functions' literal pools) */
#define G_TerrainHolder 0x006D3C98u /* Terrain::Get / TerrainCost::Get's block: +4 the TerrainHeader pointer
                                       (G_TerrainHeader), +8 the TerrainCostHeader pointer */
#define G_TerrainCost 0x006D3CA0u   /* ptr: TerrainCostHeader (u32 columns, then the rows, each padded to 4) */
#define G_Map 0x006D72F4u           /* ptr: the loaded Map (Map::Get); 0 while no map is loaded */

/* ---- one-time caches (guard word, bit 0 = filled; the value the game looked
   up by name the first time). Readable code reads a cached value only when its
   guard says it is filled and gives up otherwise, before reading anything
   else (also when the game itself would reach the guard only later, or not at
   all). The names are the game's ID labels (SPID_ = PersonFlag bit, SEID_ =
   equip skill, ISID_ = item skill flag, JCID_ = class category bit, JID_ =
   class) given here in English [med for the English]. */

/* TerrainCost::GetCostFromUnit */
#define S_CostGuard 0x006D3CACu
#define S_CostOwnMask 0x006D3CE0u    /* u64: PersonFlag bit SPID "own terrain cost": an impassable tile costs what
                                        movement class 0 pays there */
/* Terrain::IsCastleUnitDispos */
#define S_CastleGuard 0x006D3CA4u
#define S_CastleRow 0x006D3CA8u      /* ptr: the TerrainCost row of the class JID "Knight (male)" */
/* Unit::IsCostFree */
#define S_FreeItemGuard 0x006D99C8u
#define S_FreeItemMask 0x006D9CD0u   /* u64: ItemFlag bit ISID "Fujin Yumi" (the item skill of the wind bow) */
#define S_FreeSkillGuard 0x006D99C4u
#define S_FreeSkill 0x006D96E0u      /* s16: SEID "amphibious" */
#define S_FreeShooterGuard 0x006D99A8u /* shared with Unit::GetMovePower (sheet.h S_MoveGuard3) */
#define S_FreeShooterMask 0x006D96D8u  /* u16: 1 << JCID "shooter" (ballista classes) */
/* Unit::GetCategory's own caches (sheet.h S_CatGuard0..4): asked first by the
   readers here that call it, so its override never gives up inside them */
#define S_CatGuardA 0x006D97D0u
#define S_CatGuardB 0x006D97CCu
#define S_CatGuardC 0x006D97C8u
#define S_CatGuardD 0x006D97C4u
#define S_CatGuardE 0x006D97C0u
/* map::Deploy::IsFill */
#define S_FillGuard 0x006D7380u
#define S_FillNoMoveMask 0x006D73E0u /* u64: PersonFlag bit SPID "may not move" */
/* Job::IsFlyer / Job::IsRider */
#define S_FlyerGuard 0x006D39A8u
#define S_FlyerMask 0x006D3992u      /* u16: 1 << JCID "flying" */
#define S_RiderGuard 0x006D39A4u
#define S_RiderMask 0x006D3990u      /* u16: 1 << JCID "mounted" */
/* AIThink::GetTerrainScore */
#define S_ScoreFlyerGuard 0x006D108Cu
#define S_ScoreFlyerMask 0x006D1064u /* u16: 1 << JCID "flying" (its own copy) */
#define S_ScoreSkillGuard 0x006D1088u
#define S_ScoreSkill 0x006D1066u     /* s16: SEID "lockpick" [low for what it means on terrain: it lifts the
                                        negative terrain numbers of tiles with attribute bit 8] */

/* ---- record fields this batch reads that config/readable/structs/ does not
   name yet (offsets read in the code on 2026-11-14; the integrate step may
   add them). [high for the offsets, med for the names] */
#define MAPIMAGE_WIDTH 0x000u        /* u8: map width in tiles (TerrainGrid.map_width, script TerrainGetW) */
#define MAPIMAGE_HEIGHT 0x001u       /* u8: map height (TerrainGrid.map_height, script TerrainGetH) */
#define MAPIMAGE_UNITS 0x008u        /* map::Image::Unit: 32 x 32 bytes, the pool number of the unit on each tile */
#define MAPIMAGE_COST_COLUMN 0xC08u  /* 32 x 32 bytes: the TerrainCost column of each tile (map::Route::GetRouteCost) */
#define DEPLOY_UNITS 0x818u          /* map::Deploy: ptr to the map::Image::Unit it tests (IsFill) */
#define DEPLOY_FLAGS 0x1624u         /* map::Deploy: u32 mode bits IsFill tests (4, 0x10, 0x4000) */
#define DEPLOY_FORCE 0x1628u         /* map::Deploy: u8 force type of the side being filled */
#define UNIT_NUMBER 0x0F0u           /* u8: the unit's pool number (script UnitGetByPosition returns it) */
#define UNIT_IMMOBILE_WORD 0x054u    /* u32: bit 8 = the unit may not be stepped past (IsFill) [low for the name] */
#define ROUTE_COUNT 0x80u            /* map::Route: u8 number of steps (GetCross) */
#define ROUTE_START_X 0x81u          /* s8 */
#define ROUTE_START_Y 0x82u          /* s8 */

#define TERRAIN_RECORD_SIZE 0x28u    /* TerrainTile record */
#define TERRAIN_ATTR_BLOCKED 0x08u   /* TerrainTile.attributes bit 3: no unit may stand here (MoveImage::Get: -1) */
#define TERRAIN_ATTR_HAZARD 0x100u   /* attribute bit 8: the "lockpick" skill lifts negative numbers here */
#define ROUTE_END 0x80u              /* route byte: end of the route */
#define DEPLOY_FILL_STOP 0x04u       /* IsFill: any unit stops the fill */
#define DEPLOY_FILL_PASS_TEST 0x10u  /* IsFill: an immobile unit stops it */
#define DEPLOY_FILL_ALLY_TEST 0x4000u /* IsFill: a unit of a side not allied with the filled side stops it */

/* ---- the readable functions (override entries at the end of each file) */
/* move_terrain.c */
gaddr terrain_record(Context *ctx, int32_t tile);
uint32_t terrain_is_castle_unit_dispos(Context *ctx, gaddr terrain);
gaddr cursor_terrain(Context *ctx, gaddr cursor, int32_t x, int32_t y);
gaddr map_get(Context *ctx);
int32_t script_terrain_height(Context *ctx, gaddr script);
int32_t script_terrain_width(Context *ctx, gaddr script);
uint32_t script_terrain_out_of_play_area(Context *ctx, gaddr script, int32_t x, int32_t y);
uint32_t script_terrain_has_flag(Context *ctx, gaddr script, int32_t x, int32_t y, uint32_t flag);
uint32_t camera_play_area_w(Context *ctx, gaddr camera);
uint32_t camera_play_area_h(Context *ctx, gaddr camera);
int32_t ai_terrain_score(Context *ctx, gaddr unit, int32_t x, int32_t y);
/* move_cost.c */
gaddr terrain_cost_row(Context *ctx, int32_t row);
int32_t terrain_cost_for_unit(Context *ctx, gaddr unit, int32_t column);
uint32_t unit_is_cost_free(Context *ctx, gaddr unit);
int32_t route_cost(Context *ctx, gaddr unit, int32_t x, int32_t y, gaddr route);
int32_t route_goal_x(Context *ctx, int32_t x, gaddr route);
int32_t route_goal_y(Context *ctx, int32_t y, gaddr route);
int32_t route_cross(Context *ctx, gaddr route, int32_t x, int32_t y);
uint32_t job_is_flyer(Context *ctx, gaddr job);
uint32_t job_is_rider(Context *ctx, gaddr job);
/* move_occupy.c */
gaddr image_unit_at(Context *ctx, gaddr image, int32_t x, int32_t y);
int32_t script_unit_at(Context *ctx, gaddr script, int32_t x, int32_t y);
int32_t move_image_get(Context *ctx, gaddr image, int32_t x, int32_t y);
uint32_t deploy_is_fill(Context *ctx, gaddr deploy, int32_t x, int32_t y);

/* the tile number of (x, y) in a 32-column grid, as the game forms it
   (x | y << 5, no range check: the caller's coordinates may be anything) */
static inline gaddr move_tile(int32_t x, int32_t y) {
    return (gaddr)x | ((gaddr)y << 5);
}

#endif /* FE_MOVE_MOVE_H */
