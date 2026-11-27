/* Terrain (Fates classes Terrain, Map, map::Cursor, map::Camera, the script's
   Terrain* commands and AIThink::GetTerrainScore): the terrain record of a
   tile kind and of a map tile, the map's size and playable area, whether a
   tile has a terrain attribute, and how much the AI likes a tile's terrain.
   Plain-language description: docs/MOVE.md sections 1 and 2.

   The map image (G_MapImage) holds the 32 x 32 grid of tile kinds at +0x408,
   indexed x | y << 5; Terrain::Get turns a tile kind into its 0x28-byte
   TerrainTile record (TerrainTileData: move cost column, defence, avoid,
   heal, attribute bits).

   All are readers: they store nothing. Two fill one-time caches the first
   time (a class category bit or a skill found by name, a TerrainCost row);
   the readable code gives up while one is cold, before reading anything else.
   Guest calls left: the ones the game makes (move.h), in the game's order
   (docs/DECISIONS.md F-018).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/move/tests/move_diff.py. */

#include "move.h"

/* The TerrainTile record of a tile kind: the loaded terrain file's tile table
   + tile * 0x28 (no range check).
   Guest function: 0x004E0AFC Terrain::Get(int). */
gaddr terrain_record(Context *ctx, int32_t tile) {
    gaddr header = guest_ptr(ctx, G_TerrainHeader);
    gaddr table = READ_FIELD(ctx, TerrainHeaderData, header, tile_table);
    return table + (gaddr)tile * TERRAIN_RECORD_SIZE;
}

/* Whether a castle unit may be placed on this terrain: the tile has a move
   cost column, no "blocked" attribute bit, and the armour knight's movement
   class pays more than 0 there (a negative cost is impassable, 0 is read as
   "not a tile for units").
   Guest function: 0x00545324 Terrain::IsCastleUnitDispos(void) const. */
uint32_t terrain_is_castle_unit_dispos(Context *ctx, gaddr terrain) {
    if (!fe_static_ready(ctx, S_CastleGuard))
        return fe_use_original(ctx);
    uint32_t column = READ_FIELD(ctx, TerrainTileData, terrain, move_cost_column);
    if (column == 0)
        return 0;
    if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & TERRAIN_ATTR_BLOCKED)
        return 0;
    column = READ_FIELD(ctx, TerrainTileData, terrain, move_cost_column); /* the game reads it again */
    return guest_s8(ctx, guest_ptr(ctx, S_CastleRow) + column) > 0 ? 1u : 0u;
}

/* The tile kind at (x, y) of the map image's grid (no range check). */
static uint32_t tile_kind(Context *ctx, int32_t x, int32_t y) {
    gaddr image = guest_ptr(ctx, G_MapImage);
    return guest_u8(ctx, FIELD_ADDR(MapImage, image, draw_terrain) + move_tile(x, y));
}

/* The terrain record of the tile at (x, y) (the cursor object is not read).
   Guest function: 0x0039B7E4 map::Cursor::GetTerrain(int,int). */
gaddr cursor_terrain(Context *ctx, gaddr cursor, int32_t x, int32_t y) {
    (void)cursor;
    /* The game ends with a plain branch into Terrain::Get. 3dsrecomp keeps that
       target's code inside this function's generated code (the library's
       f_0039B7E4 dispatches 0x004E0AFC to its own label), so in the library the
       original never makes a call here. A guest call would add one: the round-10
       live compare (cq-ch9, 27 of 27 records) showed exactly that call-list
       difference. So the C of terrain_record runs directly, as the support
       batch does for its inlined tail branches (docs/SUPPORT.md). */
    return terrain_record(ctx, (int32_t)tile_kind(ctx, x, y));
}

/* The loaded Map, or 0 while none is.
   Guest function: 0x00342574 Map::Get(void). */
gaddr map_get(Context *ctx) {
    return guest_ptr(ctx, G_Map);
}

/* The script's map size: 0 without a loaded map.
   Guest functions: 0x003A7BAC anonymous_namespace::TerrainGetH(cmvm::CmContext*),
   0x003A7BD0 TerrainGetW(cmvm::CmContext*). */
int32_t script_terrain_height(Context *ctx, gaddr script) {
    (void)script;
    if (guest_call(ctx, MOVE_MapGet, 0u, 0u, 0u, 0u) == 0)
        return 0;
    return guest_u8(ctx, guest_ptr(ctx, G_MapImage) + MAPIMAGE_HEIGHT);
}

int32_t script_terrain_width(Context *ctx, gaddr script) {
    (void)script;
    if (guest_call(ctx, MOVE_MapGet, 0u, 0u, 0u, 0u) == 0)
        return 0;
    return guest_u8(ctx, guest_ptr(ctx, G_MapImage) + MAPIMAGE_WIDTH);
}

/* Whether (x, y) lies in the playable area: play_x_min <= x < play_x_end and
   play_y_min <= y < play_y_end (signed compares). The bounds are read one by
   one, each only when the ones before passed, as the game does. */
static int in_play_area(Context *ctx, gaddr image, int32_t x, int32_t y) {
    if ((int32_t)READ_FIELD(ctx, MapImage, image, play_x_min) > x)
        return 0;
    if ((int32_t)READ_FIELD(ctx, MapImage, image, play_y_min) > y)
        return 0;
    if (x >= (int32_t)READ_FIELD(ctx, MapImage, image, play_x_end))
        return 0;
    return y < (int32_t)READ_FIELD(ctx, MapImage, image, play_y_end);
}

/* The script's "is (x, y) outside the playable area": 1 without a loaded map.
   Guest function: 0x003AE294 anonymous_namespace::TerrainIsOutOfPlayArea(cmvm::CmContext*,int,int). */
uint32_t script_terrain_out_of_play_area(Context *ctx, gaddr script, int32_t x, int32_t y) {
    (void)script;
    if (guest_call(ctx, MOVE_MapGet, 0u, 0u, 0u, 0u) == 0)
        return 1;
    return in_play_area(ctx, guest_ptr(ctx, G_MapImage), x, y) ? 0u : 1u;
}

/* The script's "does the terrain at (x, y) have one of these attribute bits":
   0 without a loaded map or outside the playable area.
   Guest function: 0x003AE12C anonymous_namespace::TerrainAttributeIsFlag(cmvm::CmContext*,int,int,int). */
uint32_t script_terrain_has_flag(Context *ctx, gaddr script, int32_t x, int32_t y, uint32_t flag) {
    (void)script;
    if (guest_call(ctx, MOVE_MapGet, 0u, 0u, 0u, 0u) == 0)
        return 0;
    gaddr image = guest_ptr(ctx, G_MapImage);
    if (!in_play_area(ctx, image, x, y))
        return 0;
    gaddr terrain = guest_call1(ctx, MOVE_TerrainGet, guest_u8(ctx, FIELD_ADDR(MapImage, image, draw_terrain) + move_tile(x, y)));
    return (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & flag) != 0 ? 1u : 0u;
}

/* The playable area's width and height in tiles (end - min, as a byte; the
   camera object is not read).
   Guest functions: 0x005270FC map::Camera::GetPlayAreaW(void) const,
   0x005270DC map::Camera::GetPlayAreaH(void) const. */
uint32_t camera_play_area_w(Context *ctx, gaddr camera) {
    (void)camera;
    gaddr image = guest_ptr(ctx, G_MapImage);
    uint32_t end = READ_FIELD(ctx, MapImage, image, play_x_end);
    return (end - READ_FIELD(ctx, MapImage, image, play_x_min)) & 0xFFu;
}

uint32_t camera_play_area_h(Context *ctx, gaddr camera) {
    (void)camera;
    gaddr image = guest_ptr(ctx, G_MapImage);
    uint32_t end = READ_FIELD(ctx, MapImage, image, play_y_end);
    return (end - READ_FIELD(ctx, MapImage, image, play_y_min)) & 0xFFu;
}

/* How much the AI likes the terrain at (x, y) for this unit, 0 .. 63:
   5 + avoid + defence / 5 + heal / 10 (divisions toward zero). A flying unit
   scores 0 (terrain does nothing for it). On a tile with attribute bit 8 a
   unit with the "lockpick" skill counts negative numbers as 0.
   Guest function: 0x004CB124 AIThink::GetTerrainScore(Unit*,int,int). */
int32_t ai_terrain_score(Context *ctx, gaddr unit, int32_t x, int32_t y) {
    if (!fe_static_ready(ctx, S_ScoreFlyerGuard) || !fe_static_ready(ctx, S_ScoreSkillGuard) ||
        !fe_static_ready(ctx, S_CatGuardA) || !fe_static_ready(ctx, S_CatGuardB) ||
        !fe_static_ready(ctx, S_CatGuardC) || !fe_static_ready(ctx, S_CatGuardD) ||
        !fe_static_ready(ctx, S_CatGuardE))
        return (int32_t)fe_use_original(ctx);
    uint32_t flyer = guest_u16(ctx, S_ScoreFlyerMask);
    if (guest_call1(ctx, MOVE_UnitGetCategory, unit) & flyer)
        return 0;
    gaddr terrain = guest_call1(ctx, MOVE_TerrainGet, tile_kind(ctx, x, y));
    uint32_t attributes = READ_FIELD(ctx, TerrainTileData, terrain, attributes);
    int32_t avoid = READ_FIELD(ctx, TerrainTileData, terrain, avoid);
    int32_t defense = READ_FIELD(ctx, TerrainTileData, terrain, defense);
    int32_t heal = READ_FIELD(ctx, TerrainTileData, terrain, heal);
    if ((attributes & TERRAIN_ATTR_HAZARD) &&
        guest_call2(ctx, MOVE_UnitIsEquipSkill, unit, (uint32_t)(int32_t)guest_s16(ctx, S_ScoreSkill)) != 0) {
        avoid = avoid < 0 ? 0 : avoid;
        defense = defense < 0 ? 0 : defense;
        heal = heal < 0 ? 0 : heal;
    }
    int32_t score = defense / 5 + 5 + avoid + heal / 10;
    return score < 0 ? 0 : score > 63 ? 63 : score;
}

RECOMP_OVERRIDE(0x004E0AFC) {
    FE_ENTRY(0x004E0AFC, terrain_record, FE_ARG_S(0));
}

RECOMP_OVERRIDE(0x00545324) {
    FE_ENTRY(0x00545324, terrain_is_castle_unit_dispos, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0039B7E4) {
    FE_ENTRY(0x0039B7E4, cursor_terrain, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x00342574) {
    FE_ENTRY0(0x00342574, map_get);
}

RECOMP_OVERRIDE(0x003A7BAC) {
    FE_ENTRY(0x003A7BAC, script_terrain_height, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003A7BD0) {
    FE_ENTRY(0x003A7BD0, script_terrain_width, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003AE294) {
    FE_ENTRY(0x003AE294, script_terrain_out_of_play_area, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x003AE12C) {
    FE_ENTRY(0x003AE12C, script_terrain_has_flag, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2), FE_ARG(3));
}

RECOMP_OVERRIDE(0x005270FC) {
    FE_ENTRY(0x005270FC, camera_play_area_w, FE_ARG(0));
}

RECOMP_OVERRIDE(0x005270DC) {
    FE_ENTRY(0x005270DC, camera_play_area_h, FE_ARG(0));
}

RECOMP_OVERRIDE(0x004CB124) {
    FE_ENTRY(0x004CB124, ai_terrain_score, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}
