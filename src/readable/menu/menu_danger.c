/* The danger zone (Fates classes map::Image::Danger and map::Panel::Danger):
   which tiles the enemy can reach, read only. Plain-language description:
   docs/MENUS.md section 4.

   The zone is four 128-byte tile sets at MapImage +0x1008 (struct
   DangerImage; 32x32 tiles, one bit per tile x | y << 5) and a flag word:
     Danger::Update  clears the four sets and calls Danger::Add for every
                     unit of armies 0 .. 2 that is not allied with the viewing
                     army (Situation.view_force), not skipped by its state, and
                     either marked (state bit 16) or with the whole zone on
                     (flags bit 0);
     Danger::Add     runs map::Deploy::UnitMove for the unit (a writer: it
                     fills Deploy's two tile sets, zone_a and zone_b), marks
                     the tiles cannons can hit into zone_a, then ORs zone_a
                     into marked_a (marked units only) and all_a, zone_b into
                     marked_b (marked units only) and all_b, and sets the
                     redraw bit;
     Panel::Danger   SetVertex draws a tile when the option is 0 or 2, the
                     tile's terrain is drawn, and the tile is in marked_b
                     (first colour) or else in all_b (second colour).
   Update and Add are writers; the helpers below return what they would store
   or choose. The readable reader for an option is danger_tile_kind (the
   tile test the panel makes).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/menu/tests/menu_diff.py. */

#include "menus.h"

/* Terrain record bytes the panel tests (Terrain::Get's record, 0x28 bytes) */
#define MN_TERRAIN_DRAWN 0x10u   /* u8: 0 = the panel draws nothing on this terrain */
#define MN_TERRAIN_FLAGS 0x18u   /* u32: bit 3 set = nothing drawn either */

/* 1 when the panel has nothing to draw: its vertex buffer is empty.
   Guest function: 0x005264C4 map::Panel::Danger::IsHide(void) const. */
uint32_t danger_panel_is_hide(Context *ctx, gaddr panel) {
    return guest_call1(ctx, MN_VertexBufferGetSize, guest_ptr(ctx, panel)) == 0 ? 1u : 0u;
}

/* Helper for 0x0038F834 map::Image::Danger::Update(void): the units it would
   pass to Danger::Add, in order, and its flag word afterwards (redraw set).
   Force::Get and Force::IsAllied are called through the guest, in the game's
   order. The flag word and a unit's state are read again where the game reads
   them again. Returns 0 on a give-up or past MN_DANGER_MAX_UNITS units. */
int danger_update_targets(Context *ctx, gaddr image, DangerTargets *out) {
    uint32_t view = READ_FIELD(ctx, Situation, guest_ptr(ctx, G_Situation), view_force);
    out->count = 0;
    for (uint32_t army = 0; army < 3; army++) {
        gaddr force = guest_call1(ctx, MN_ForceGet, army);
        for (gaddr unit = READ_FIELD(ctx, Force, force, first_unit); unit != 0;
             unit = READ_FIELD(ctx, Unit, unit, next)) {
            if (READ_FIELD(ctx, Unit, unit, state_flags) & MN_STATE_DANGER_SKIP)
                continue;
            if (guest_call2(ctx, MN_ForceIsAllied, READ_FIELD(ctx, Unit, unit, force), view) != 0)
                continue;
            if ((READ_FIELD(ctx, DangerImage, image, flags) & MN_DANGER_WHOLE) == 0 &&
                (READ_FIELD(ctx, Unit, unit, state_flags) & MN_STATE_DANGER_MARK) == 0)
                continue;
            if (out->count >= MN_DANGER_MAX_UNITS)
                return 0;
            out->units[out->count++] = unit;
            if (fe_gave_up(ctx))
                return 0;
        }
    }
    out->flags_after = READ_FIELD(ctx, DangerImage, image, flags) | MN_DANGER_REDRAW;
    return !fe_gave_up(ctx);
}

/* sets[k] = image set k OR the 128 bytes at zone, read a word at a time as
   the game does */
static void or_set(Context *ctx, gaddr image, uint32_t k, gaddr zone, uint8_t set[128]) {
    for (uint32_t w = 0; w < 32; w++) {
        uint32_t v = guest_u32(ctx, image + 0x80u * k + 4u * w) | guest_u32(ctx, zone + 4u * w);
        for (uint32_t b = 0; b < 4; b++)
            set[4u * w + b] = (uint8_t)(v >> (8u * b));
    }
}

/* Helper for 0x0038F304 map::Image::Danger::Add(const Unit*,const
   map::trick::EnumeratorCannon*) without its writers: the move-search flags
   it passes to map::Deploy::UnitMove (from the danger option: 0 -> 0x50000,
   2 -> 0x30000, else 0x10000; the call itself is not made) and, taking
   Deploy's zone_a / zone_b as they are (UnitMove's result; the cannon marks
   are not added), the four sets and the flag word Add would leave. For a
   unit without state bit 16 the two marked sets are not touched (and not
   read): sets[0] and sets[2] then hold zeros. */
int danger_add_preview(Context *ctx, gaddr image, gaddr unit, DangerAddPreview *out) {
    uint32_t option = READ_FIELD(ctx, GameConfigData, guest_ptr(ctx, G_GameConfig), danger);
    out->search_flags = option == 0 ? 0x50000u : option == 2 ? 0x30000u : 0x10000u;
    for (uint32_t k = 0; k < 4; k++)
        for (uint32_t i = 0; i < 128; i++)
            out->sets[k][i] = 0;
    if (READ_FIELD(ctx, Unit, unit, state_flags) & MN_STATE_DANGER_MARK) {
        gaddr deploy = guest_ptr(ctx, G_Deploy);
        or_set(ctx, image, 0, READ_FIELD(ctx, MapDeploy, deploy, zone_a), out->sets[0]);
        or_set(ctx, image, 2, READ_FIELD(ctx, MapDeploy, deploy, zone_b), out->sets[2]);
    }
    gaddr deploy = guest_ptr(ctx, G_Deploy);  /* the game loads the pointer again */
    or_set(ctx, image, 1, READ_FIELD(ctx, MapDeploy, deploy, zone_a), out->sets[1]);
    or_set(ctx, image, 3, READ_FIELD(ctx, MapDeploy, deploy, zone_b), out->sets[3]);
    out->flags_after = READ_FIELD(ctx, DangerImage, image, flags) | MN_DANGER_REDRAW;
    return !fe_gave_up(ctx);
}

/* Helper for the tile test of 0x00390F54 map::Panel::Danger::SetVertex(void)
   (it fills a vertex buffer): see menus.h. The tile index is x | y << 5 (an
   OR, as the game computes it), the terrain kind comes from
   MapImage.draw_terrain, Terrain::Get is called through the guest. */
int danger_tile_kind(Context *ctx, int32_t x, int32_t y, uint32_t *kind) {
    *kind = 0;
    uint32_t option = READ_FIELD(ctx, GameConfigData, guest_ptr(ctx, G_GameConfig), danger);
    if (option != 2 && option != 0)
        return !fe_gave_up(ctx);
    gaddr map = guest_ptr(ctx, G_MapImage);
    int32_t tile = (int32_t)((uint32_t)x | ((uint32_t)y << 5));
    gaddr terrain = guest_call1(ctx, MN_TerrainGet, guest_u8(ctx, FIELD_ADDR(MapImage, map, draw_terrain) + (gaddr)tile));
    if (guest_u8(ctx, terrain + MN_TERRAIN_DRAWN) == 0 || (guest_u32(ctx, terrain + MN_TERRAIN_FLAGS) & 8u))
        return !fe_gave_up(ctx);
    gaddr image = FIELD_ADDR(MapImage, map, danger);
    uint32_t bit = 1u << ((uint32_t)tile & 7u);
    if (guest_u8(ctx, FIELD_ADDR(DangerImage, image, marked_b) + (gaddr)fe_asr(tile, 3)) & bit)
        *kind = 1;
    else if (guest_u8(ctx, FIELD_ADDR(DangerImage, image, all_b) + (gaddr)fe_asr(tile, 3)) & bit)
        *kind = 2;
    return !fe_gave_up(ctx);
}

RECOMP_OVERRIDE(0x005264C4) {
    FE_ENTRY(0x005264C4, danger_panel_is_hide, FE_ARG(0));
}
