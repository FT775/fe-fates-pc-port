/* Menus and panels the options need (Fates): the options screen's stored
   settings, the battle-picture decision, the map HP bar decision and the
   danger zone. Declarations shared by src/readable/menu/menu_config.c,
   menu_show.c and menu_danger.c, the guest functions they still call and
   the one-time caches they read.

   Plain-language description (what each option would hook, reader or
   writer, what the robot must replay first): docs/MENUS.md.

   This header lives next to its sources, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_MENU_MENUS_H
#define FE_MENU_MENUS_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-13 and stores nothing.
   Where the game calls a function that has a readable override (this batch's
   or an older one), the readable code calls it through the guest too, in the
   game's order and with the game's arguments (docs/DECISIONS.md F-018). */
#define MN_VertexBufferGetSize 0x0013082Cu /* VertexBuffer::GetSize(void) const: 0 without a buffer, else its
                                              count word; reads only */
#define MN_ForceGet 0x004F630Cu            /* Force::Get(Force::Type): one NOP, then UnitPool::GetForce (the
                                              force record of a type); reads only */
#define MN_TerrainGet 0x004E0AFCu          /* Terrain::Get(int): the terrain record of a tile kind (table +
                                              kind * 0x28); reads only */
#define MN_ForceIsAllied 0x0053C3E0u       /* Force::IsAllied(Force::Type) const: readable force_is_allied */
#define MN_UnitDetailMust 0x00530884u      /* Unit::IsDetailBattleMust: this batch's unit_is_detail_battle_must */
#define MN_UnitDetailNotAllow 0x00531BA8u  /* Unit::IsDetailBattleNotAllow: unit_is_detail_battle_not_allow */
#define MN_ConfigDetailBattle 0x0050AAA0u  /* GameConfigData::IsDetailBattle: config_is_detail_battle */
#define MN_ConfigDetailSupport 0x0050AC04u /* GameConfigData::IsDetailSupport: config_is_detail_support */

/* ConfigItem's virtual GetMask (slot +0x80 of an option item's class table):
   every on/off option item returns the bit of GameConfigData.option_bits it
   stands for (AutoTurnEnd::GetMask returns 0x10, Stick::GetMask 1, ...). */
#define MN_ITEM_GETMASK_SLOT 0x80u

/* ---- one-time caches (guard word, bit 0 = filled; a PersonFlag bit the
   game looked up by its SPID label the first time). Readable code reads a
   cached value only when its guard says it is filled and gives up otherwise,
   before reading anything else. Addresses from each function's literal pool.
   The labels are Japanese; their meaning is given from the use [medium]. */
#define MN_SupportGuard 0x006DA0FCu   /* GameConfigData::IsDetailSupport: guard of the mask below */
#define MN_SupportMask 0x006DA130u    /* u64 PersonFlag bit: a unit with it never gets the support picture */
#define MN_MustGuardA 0x006D97E0u     /* Unit::IsDetailBattleMust: guard of MN_MustMaskA */
#define MN_MustMaskA 0x006D9AD0u      /* u64 PersonFlag bit: always the battle picture */
#define MN_MustGuardB 0x006D97DCu     /* Unit::IsDetailBattleMust: guard of MN_MustMaskB */
#define MN_MustMaskB 0x006D9AD8u      /* u64 PersonFlag bit: always the battle picture (a second label) */
#define MN_NotAllowGuard 0x006D97E4u  /* Unit::IsDetailBattleNotAllow: guard of the mask below (also the
                                         guard Unit::IsDetailBattleMust's caches sit next to) */
#define MN_NotAllowMask 0x006D9AE0u   /* u64 PersonFlag bit: never the battle picture (wins over "always") */

/* Unit state bits the danger zone and the HP bar read (Unit.state_flags) */
#define MN_STATE_PARTNER 0x4u          /* the carried pair partner (Unit::DoubleOn): no map HP bar */
#define MN_STATE_DANGER_SKIP 0x24004u  /* Danger::Update skips a unit with one of these bits (bit 2 is the
                                          partner; bits 14 and 17 not traced) */
#define MN_STATE_DANGER_MARK 0x10000u  /* the unit's own zone is shown (UnitShowDanger, the X button on a unit) */

/* DangerImage.flags */
#define MN_DANGER_WHOLE 0x1u           /* the whole zone: every non-allied unit, not only the marked ones */
#define MN_DANGER_REDRAW 0x2u          /* map::Panel::Danger::Tick rebuilds the vertices and clears it */

/* ---- overrides (readers) */
uint32_t config_danger_value(Context *ctx, gaddr item);
uint32_t config_hp_gauge_value(Context *ctx, gaddr item);
uint32_t config_battle_value(Context *ctx, gaddr item);
uint32_t config_game_speed_value(Context *ctx, gaddr item);
uint32_t config_ai_skip_value(Context *ctx, gaddr item);
uint32_t config_distance_value(Context *ctx, gaddr item);
uint32_t config_encounter_bgm_value(Context *ctx, gaddr item);
uint32_t config_item_value(Context *ctx, gaddr item);
uint32_t config_is_speed_fast(Context *ctx, gaddr config);
uint32_t config_is_skip_input(Context *ctx, gaddr config);
uint32_t config_info_capability(Context *ctx, gaddr config);
uint32_t config_is_detail_battle(Context *ctx, gaddr config, gaddr unit_a, gaddr unit_b, uint32_t flip);
uint32_t config_is_detail_support(Context *ctx, gaddr config, gaddr unit_a, gaddr unit_b, uint32_t flip);
uint32_t unit_is_detail_battle_must(Context *ctx, gaddr unit);
uint32_t unit_is_detail_battle_not_allow(Context *ctx, gaddr unit);
uint32_t danger_panel_is_hide(Context *ctx, gaddr panel);

/* ---- helpers (F-017: their game functions store; these return what the
   game would compute or store and write nothing). Each returns 0 when it gave
   up (a cold cache, asked first), else 1. */

/* What GameConfigData::Serialize(Stream*) writes, in order: the version byte
   1, the option word, then the 15 bytes +0x8 .. +0x16. kind 1 = WriteByte,
   4 = WriteLong. For keep_game_options: the record the options page may copy
   into a side file. */
#define MN_SAVED_ENTRIES 17
typedef struct MenuSavedEntry {
    uint32_t kind;
    uint32_t value;
} MenuSavedEntry;
int config_saved_record(Context *ctx, gaddr config, MenuSavedEntry out[MN_SAVED_ENTRIES]);

/* The battle-picture decision of the map::SequenceBattle ProcSequence
   constructor: the BattleSequence.flags word it would leave (bit 0 = no
   battle picture, the fight is shown on the map). */
int battle_picture_choice(Context *ctx, gaddr sequence, uint32_t *flags_after);

/* The map HP bar decision of map::Actor::Tick: 1 when the actor's bar would
   be shown (the value it stores as bit 4 of its draw word). */
int actor_hp_bar_shown(Context *ctx, gaddr actor, uint32_t *shown);

/* The unit choice of map::Image::Danger::Update: the units, in order, it
   would pass to Danger::Add, and the flag word it would leave (its four tile
   sets would be cleared first). */
#define MN_DANGER_MAX_UNITS 256
typedef struct DangerTargets {
    int count;
    gaddr units[MN_DANGER_MAX_UNITS];
    uint32_t flags_after;
} DangerTargets;
int danger_update_targets(Context *ctx, gaddr image, DangerTargets *out);

/* map::Image::Danger::Add without its two writers (map::Deploy::UnitMove,
   which fills Deploy's tile sets, and the cannon marks): the move-search
   flags it would pass to UnitMove, and the four tile sets and the flag word
   it would leave when Deploy's two sets already hold the unit's reach. */
typedef struct DangerAddPreview {
    uint32_t search_flags;  /* 0x50000 for option value 0, 0x30000 for 2, else 0x10000 */
    uint8_t sets[4][128];   /* marked_a, all_a, marked_b, all_b after the OR */
    uint32_t flags_after;
} DangerAddPreview;
int danger_add_preview(Context *ctx, gaddr image, gaddr unit, DangerAddPreview *out);

/* The tile test of map::Panel::Danger::SetVertex's first loop (option values 0
   and 2): 0 = not drawn by that loop (the option value is not 0 or 2, the
   tile's terrain is not drawn, or no set holds it). Option value 1 does not
   hide the zone: SetVertex then runs a second loop (0x00391704, another colour
   pair), not reproduced here (round 38, OK A T3),
   1 = drawn as a marked unit's tile (DangerImage.marked_b), 2 = drawn as a
   whole-zone tile (all_b). */
int danger_tile_kind(Context *ctx, int32_t x, int32_t y, uint32_t *kind);

#endif /* FE_MENU_MENUS_H */
