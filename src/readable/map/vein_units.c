/* Who may use a dragon vein (Fates classes Unit, Person, the map command
   TransformTerrain and the script). Plain-language description: docs/VEINS.md.

   - Unit::CanDragonVein: the unit, its Person or its class carries one
     personal-flag bit (looked up by name once and cached). A unit with one
     state bit set must also be a download person.
   - Person::IsDownload: a personal-flag bit, or the Person's number lies in
     a loaded Person block marked as such.
   - the map command (TransformTerrain::BuildAttribute): shown when the unit
     being ordered may use a vein and stands where a usable vein is.
   - the script's UnitCanDragonVein: the same unit check for a unit number,
     refusing numbers outside 1..250 and units of force 9.

   Every function here only reads guest memory and calls no guest function;
   the two one-time caches make it give up while they are cold.

   Status: UNVERIFIED (below shadow-clean). Each function agrees with the
   original ARM code on generated inputs in the host differential test
   (src/readable/map/tests/vein_diff.py); that is not a shadow result. */

#include "veins.h"

/* The unit with pool number `number` (1 and up), 0 for number 0. No range check.
   Guest function: UnitPool::Get(int) 0x004F6174 (not an override here). */
static gaddr unit_pool_get(Context *ctx, uint32_t number) {
    if (number == 0)
        return 0;
    gaddr units = READ_FIELD(ctx, UnitPool, G_UnitPool, units);
    return units + (number - 1u) * (gaddr)sizeof(Unit);
}

/* The PersonFlag words of a unit, its Person and its class, ORed. */
static uint64_t unit_person_flags(Context *ctx, gaddr unit) {
    return READ_FIELD(ctx, Unit, unit, private_flags) |
           READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), flags) |
           READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), flags);
}

/* Whether the Person's number lies in [first_number, first_number + count) of a block. */
static int block_holds(Context *ctx, gaddr block, uint32_t number) {
    uint32_t first = READ_FIELD(ctx, PersonBlock, block, first_number);
    return first <= number && number < first + READ_FIELD(ctx, PersonBlock, block, count);
}

/* Whether a Person is a download person: it carries the cached personal-flag
   bit; or else the first loaded Person block (G_PersonBlocks list) that holds
   its number has flag_07 set and is not the list's first block. (The game
   tests the first block's range and flag again after finding the block; that
   second test can only fail when the found block IS the first one, which is
   what is written here.) Gives up while the cache is cold.
   Guest function: 0x0053DFEC Person::IsDownload(void) const. */
int32_t person_is_download(Context *ctx, gaddr person) {
    if (!fe_static_ready(ctx, S_DownloadGuard))
        return (int32_t)fe_use_original(ctx);
    if ((READ_FIELD(ctx, PersonData, person, flags) & guest_u64(ctx, S_DownloadMask)) != 0)
        return 1;
    uint32_t number = READ_FIELD(ctx, PersonData, person, pid_number);
    gaddr head = guest_ptr(ctx, G_PersonBlocks);
    for (gaddr node = head; node != 0; node = READ_FIELD(ctx, PersonBlockNode, node, next)) {
        gaddr block = READ_FIELD(ctx, PersonBlockNode, node, block);
        if (!block_holds(ctx, block, number))
            continue;
        if (READ_FIELD(ctx, PersonBlock, block, flag_07) == 0)
            return 0;
        return node != head;
    }
    return 0;
}

/* Whether a unit may use a dragon vein: the unit, its Person or its class
   carries the cached personal-flag bit; and a unit with state bit 28 set must
   also be a download person. Gives up while either cache is cold.
   Guest function: 0x0052DFE8 Unit::CanDragonVein(void) const. */
int32_t unit_can_dragon_vein(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, S_VeinGuard))
        return (int32_t)fe_use_original(ctx);
    if ((unit_person_flags(ctx, unit) & guest_u64(ctx, S_VeinMask)) == 0)
        return 0;
    if ((READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_VEIN_DOWNLOAD_ONLY) == 0)
        return 1;
    int32_t download = person_is_download(ctx, READ_FIELD(ctx, Unit, unit, person));
    if (fe_gave_up(ctx))
        return 0;
    return download != 0;
}

/* The script's vein check for a unit number: 0 outside 1..250 and for a unit
   of force 9, otherwise unit_can_dragon_vein.
   Guest function: 0x003ABD8C anonymous_namespace::UnitCanDragonVein(cmvm::CmContext*,int). */
int32_t script_unit_can_dragon_vein(Context *ctx, gaddr cm, int32_t number) {
    (void)cm;
    if (number <= 0 || number > 250)
        return 0;
    gaddr unit = unit_pool_get(ctx, (uint32_t)number);
    if (READ_FIELD(ctx, Force, READ_FIELD(ctx, Unit, unit, force), type) == FORCE_TYPE_NO_VEIN)
        return 0;
    return unit_can_dragon_vein(ctx, unit);
}

/* The map command "dragon vein": shown (1) when the unit being ordered may use
   a vein and stands where a usable vein is (trick_at_access, type 11); not in
   the menu (4) otherwise. `item` (the menu item) is not read.
   Guest function: 0x0037B138 map::anonymous_namespace::TransformTerrain::BuildAttribute(void). */
uint32_t vein_command_attribute(Context *ctx, gaddr item) {
    (void)item;
    if (!fe_static_ready(ctx, S_VeinGuard)) /* the cache unit_can_dragon_vein needs: give up before reading */
        return fe_use_original(ctx);
    gaddr mind = guest_ptr(ctx, G_MapMind);
    gaddr unit = unit_pool_get(ctx, READ_FIELD(ctx, MapMind, mind, unit_index));
    int32_t can = unit_can_dragon_vein(ctx, unit);
    if (fe_gave_up(ctx))
        return 0;
    if (!can)
        return MENU_ATTR_HIDDEN;
    gaddr vein = trick_at_access(ctx, READ_FIELD(ctx, Unit, unit, map_x), READ_FIELD(ctx, Unit, unit, map_y),
                                 TRICK_TYPE_VEIN);
    return vein != 0 ? MENU_ATTR_SHOWN : MENU_ATTR_HIDDEN;
}

RECOMP_OVERRIDE(0x0053DFEC) {
    FE_ENTRY(0x0053DFEC, person_is_download, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052DFE8) {
    FE_ENTRY(0x0052DFE8, unit_can_dragon_vein, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003ABD8C) {
    FE_ENTRY(0x003ABD8C, script_unit_can_dragon_vein, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0037B138) {
    FE_ENTRY(0x0037B138, vein_command_attribute, FE_ARG(0));
}
