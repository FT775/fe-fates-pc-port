/* One dragon vein effect: the ground a vein changes (Fates classes
   map::trick::PositionEnumerator and map::trick::Data::SetDeploy).
   Plain-language description: docs/VEINS.md.

   What a vein does is decided by the chapter's script: using one runs the
   script's event for that tile (event::Poke with type 11). The most common
   effect changes the ground: the script switches the state of the regions the
   vein names (gimmicks of type 12) and each tile of a region turns into the
   tile its terrain record names. The vein names its regions in a string
   (TrickData.positions): "x,y,x,y,..." top-left corners, or None / All /
   EnableAll / DoneAll / RuinAll.

   The game's own preview of that effect, drawn while the cursor rests on a
   vein (and before the command is confirmed), is trick::Data::SetDeploy: it
   marks, in a 32x32 bitmap of MapDeploy, each tile of each named region whose
   terrain record says it changes in the region's current state (attribute
   bits 0x400 usable, 0x800 done, 0x1000 ruined), plus that tile's whole
   column or row of the play area for the bits 0x2000 / 0x4000.

   SetDeploy writes that bitmap, so it stays game code (project rule: no
   writer until the harness steps H6/H8 are green on Fates). The helper here
   returns the marks it would leave and writes nothing: exactly what a
   display-only vein highlight needs, and it cannot fire the vein.

   Every function here only reads guest memory and calls no guest function.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/map/tests/vein_diff.py. */

#include "veins.h"

#define VEIN_MAX_TEXT 4096 /* a positions string longer than this: give up */

/* Whether the guest string at `text` equals `word` (the game uses sut::strcmp). */
static int text_is(Context *ctx, gaddr text, const char *word) {
    for (gaddr i = 0;; i++) {
        uint8_t c = guest_u8(ctx, text + i);
        if (c != (uint8_t)word[i])
            return 0;
        if (c == 0)
            return 1;
    }
}

/* The state mask of the four "every region" words, or -1 for any other text. */
static int32_t every_region_mask(Context *ctx, gaddr text) {
    if (text_is(ctx, text, "All"))
        return 0;
    if (text_is(ctx, text, "EnableAll"))
        return TRICK_USABLE;
    if (text_is(ctx, text, "DoneAll"))
        return TRICK_DONE;
    if (text_is(ctx, text, "RuinAll"))
        return TRICK_RUINED;
    return -1;
}

/* The positions a gimmick's text names:
   - "None": none;
   - "All" / "EnableAll" / "DoneAll" / "RuinAll": the top-left corner of every
     region (type 12) in any state / usable / used / ruined, in list order;
   - anything else: numbers separated by commas, read as x, y pairs. Each
     comma ends a number; characters other than digits and commas are skipped;
     an empty number is -1; a number is kept as its low byte (signed). The
     count is (commas + 1) / 2, so an odd last number is ignored.
   Gives up past VEIN_MAX_POSITIONS positions or VEIN_MAX_TEXT characters.
   (Guest function: map::trick::PositionEnumerator::PositionEnumerator(const char*) 0x0039A02C.) */
void trick_positions(Context *ctx, gaddr text, VeinPositions *out) {
    out->count = 0;
    if (text_is(ctx, text, "None"))
        return;
    int32_t mask = every_region_mask(ctx, text);
    if (mask >= 0) {
        gaddr list = guest_ptr(ctx, G_Trick);
        for (gaddr d = READ_FIELD(ctx, Trick, list, first); d != 0; d = READ_FIELD(ctx, TrickData, d, next)) {
            if (READ_FIELD(ctx, TrickData, d, type) != TRICK_TYPE_VEIN_REGION)
                continue;
            if (mask != 0 && (READ_FIELD(ctx, TrickData, d, state) & (uint32_t)mask) == 0)
                continue;
            if (out->count == VEIN_MAX_POSITIONS) {
                fe_use_original(ctx);
                return;
            }
            out->x[out->count] = READ_FIELD(ctx, TrickData, d, x);
            out->y[out->count] = READ_FIELD(ctx, TrickData, d, y);
            out->count++;
        }
        return;
    }
    int32_t values = 0, number = -1;
    for (gaddr i = 0;; i++) {
        if (i == VEIN_MAX_TEXT || values > 2 * VEIN_MAX_POSITIONS) {
            fe_use_original(ctx);
            return;
        }
        int8_t c = guest_s8(ctx, text + i);
        if (c >= '0' && c <= '9') {
            if (number < 0)
                number = 0;
            number = fe_add32(fe_mul32(number, 10), c - '0');
        } else if (c == ',' || c == 0) {
            if (values < 2 * VEIN_MAX_POSITIONS) {
                if (values % 2 == 0)
                    out->x[values / 2] = (int8_t)(uint8_t)number;
                else
                    out->y[values / 2] = (int8_t)(uint8_t)number;
            }
            values++;
            number = -1;
            if (c == 0)
                break;
        }
    }
    out->count = values / 2;
}

/* Sets the mark of tile i = x | y << 5 (bit i & 7 of byte i >> 3, an arithmetic shift). */
static void mark(Context *ctx, VeinMarks *out, uint32_t tile) {
    int32_t at = fe_asr((int32_t)tile, 3) + VEIN_MARKS_BEFORE;
    if (at < 0 || at >= VEIN_MARKS_BYTES) {
        fe_use_original(ctx);
        return;
    }
    out->bytes[at] |= (uint8_t)(1u << (tile & 7u));
}

/* Whether a tile's terrain changes in the region's current state. */
static int tile_changes(uint32_t attributes, uint32_t state) {
    return ((attributes & TERRAIN_CHANGES_WHEN_USABLE) && (state & TRICK_USABLE)) ||
           ((attributes & TERRAIN_CHANGES_WHEN_DONE) && (state & TRICK_DONE)) ||
           ((attributes & TERRAIN_CHANGES_WHEN_RUINED) && (state & TRICK_RUINED));
}

/* The marks of the regions a vein names (see the top of this file). Each
   named position takes the first region (type 12) whose top-left corner is
   there; its tiles are counted from the NAMED position (they differ only when
   a name holds -1, which matches any column or row). */
static void vein_marks(Context *ctx, gaddr vein, VeinMarks *out) {
    VeinPositions pos;
    trick_positions(ctx, READ_FIELD(ctx, TrickData, vein, positions), &pos);
    if (fe_gave_up(ctx))
        return;
    for (int32_t i = 0; i < pos.count; i++) {
        gaddr region = trick_find(ctx, TRICK_SEARCH_AT, pos.x[i], pos.y[i], TRICK_TYPE_VEIN_REGION, 0);
        if (region == 0)
            continue;
        for (int32_t row = 0; row < READ_FIELD(ctx, TrickData, region, height); row++) {
            for (int32_t col = 0; col < READ_FIELD(ctx, TrickData, region, width); col++) {
                int32_t tx = pos.x[i] + col, ty = pos.y[i] + row;
                uint32_t tile = (uint32_t)tx | (uint32_t)ty << 5;
                gaddr image = guest_ptr(ctx, G_MapImage);
                gaddr header = guest_ptr(ctx, G_TerrainHeader);
                uint8_t number = guest_u8(ctx, FIELD_ADDR(MapImage, image, terrain) + tile);
                gaddr terrain = READ_FIELD(ctx, TerrainHeaderData, header, tile_table) +
                                (gaddr)number * (gaddr)sizeof(TerrainTileData);
                uint32_t attributes = READ_FIELD(ctx, TerrainTileData, terrain, attributes);
                if (!tile_changes(attributes, READ_FIELD(ctx, TrickData, region, state)))
                    continue;
                mark(ctx, out, tile);
                if (attributes & TERRAIN_MARK_COLUMN)
                    for (int32_t y2 = READ_FIELD(ctx, MapImage, image, play_y_min);
                         y2 < READ_FIELD(ctx, MapImage, image, play_y_end); y2++)
                        mark(ctx, out, (uint32_t)tx | (uint32_t)y2 << 5);
                if (attributes & TERRAIN_MARK_ROW)
                    for (int32_t x2 = READ_FIELD(ctx, MapImage, image, play_x_min);
                         x2 < READ_FIELD(ctx, MapImage, image, play_x_end); x2++)
                        mark(ctx, out, (uint32_t)x2 | (uint32_t)ty << 5);
                out->result = 1;
                if (fe_gave_up(ctx))
                    return;
            }
        }
    }
}

/* What trick::Data::SetDeploy leaves for one gimmick, without writing it:
   - type 11 (a dragon vein): the marks of the regions it names (vein_marks), result 1 when any;
   - type 28: the first named position alone, result 1 when there is one;
   - types 25..27 (cannons): kind VEIN_MARKS_CANNON (the game asks map::Deploy::Cannon);
   - any other type: nothing, result 0.
   The game first clears its bitmap; out->bytes starts clear the same way.
   Guest function: helper of 0x00526D98 map::trick::Data::SetDeploy(void) const (a writer). */
void trick_preview_marks(Context *ctx, gaddr data, VeinMarks *out) {
    memset(out, 0, sizeof *out);
    uint32_t type = READ_FIELD(ctx, TrickData, data, type);
    if (type == TRICK_TYPE_VEIN) {
        out->kind = VEIN_MARKS_TILES;
        vein_marks(ctx, data, out);
    } else if (type == TRICK_TYPE_MARK_ONE) {
        out->kind = VEIN_MARKS_TILES;
        VeinPositions pos;
        trick_positions(ctx, READ_FIELD(ctx, TrickData, data, positions), &pos);
        if (!fe_gave_up(ctx) && pos.count >= 1) {
            mark(ctx, out, (uint32_t)(int32_t)pos.x[0] | (uint32_t)(int32_t)pos.y[0] << 5);
            out->result = 1;
        }
    } else if (type - 25u <= 2u) {
        out->kind = VEIN_MARKS_CANNON;
    }
}
