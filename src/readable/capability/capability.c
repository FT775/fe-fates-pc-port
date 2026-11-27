/* The stat getter by number, and the two stat totals (Fates class Unit).
   Plain-language description: docs/CAPABILITY.md.

   - unit_capability: one stat of a unit by its number (0 HP, 1 strength,
     2 magic, 3 skill, 4 speed, 5 luck, 6 defense, 7 resistance). The game
     looks the getter up in a table of member-function pointers and calls it.
   - unit_capability_rating: the sum of stats 1..7 (HP not counted), with the
     extras and with the third bool (the debuffs taken off).
   - unit_capability_rating_no_weakness: the same sum without the third bool.

   All three are readers: they store nothing of the game's. The getters fill
   one-time caches of their own the first time; the readable code gives up
   while any cache it may need is cold, before reading anything else. The only
   stores are the stack words of guest_call5 / guest_call6 in the dead stack
   below sp (docs/READABLE.md 17), where the game's own calls put the same
   words.

   Where the readable code is narrower than the game (it gives up, so the
   game's own code runs; always safe):
   - a stat number of 8 or more (the game would read past the table and call
     whatever it finds there);
   - a table entry with a non-zero "this" adjustment word (a virtual or
     adjusted member pointer; the game's table has none);
   - a table entry naming a function that is not one of the eight getters.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/capability/tests/capability_diff.py. */

#include "capability.h"

/* The one-time caches of the getter at `getter` are all filled; 0 for a
   function that is not one of the getters of stats 1..7. */
static int getter_caches_ready(Context *ctx, gaddr getter) {
    switch (getter) {
    case CAP_UnitGetStrImpl: return unit_stat_caches_ready(ctx, CAP_STAT_STR);
    case CAP_UnitGetPowImpl: return unit_stat_caches_ready(ctx, CAP_STAT_MAG);
    case CAP_UnitGetTechImpl: return unit_stat_caches_ready(ctx, CAP_STAT_SKL);
    case CAP_UnitGetQuickImpl: return unit_stat_caches_ready(ctx, CAP_STAT_SPD);
    case CAP_UnitGetLuckImpl: return unit_stat_caches_ready(ctx, CAP_STAT_LCK);
    case CAP_UnitGetDefImpl:
        return fe_static_ready(ctx, S_CapDefGuard0) && fe_static_ready(ctx, S_CapDefGuard1) &&
               fe_static_ready(ctx, S_CapDefGuard2) && fe_static_ready(ctx, S_CapDefGuard3);
    case CAP_UnitGetMdefImpl:
        return fe_static_ready(ctx, S_CapResGuard0) && fe_static_ready(ctx, S_CapResGuard1) &&
               fe_static_ready(ctx, S_CapResGuard2);
    default: return 0;
    }
}

/* One stat of the unit by its number. Arguments as the game's: the item (may
   be 0), the extras bool in r3, and on the guest stack (sp) the loss bool
   (the third bool of the getters: debuffs taken off) and the rally kind.
   - The table entry of the stat names a getter: that getter is called with
     (unit, item, extras, loss) and the rally kind as its stack word.
   - The entry is empty: stat 0 ends in a tail call of the HP getter with
     (unit, extras, loss, rally kind) (the item is not passed); any other stat
     gives 0. That tail call is a plain branch (B), and 3dsrecomp turns it into
     a direct jump to the HP getter's override inside this function's
     generated code, so in the library the original never makes a guest call
     there; only the HP getter's own calls are seen. A guest call would add
     one: the round-15 live capture (r15-cap-capability, 7 records on
     bt-prologue, bt-ch4, bt-ch5, bt-ch8) showed exactly that call-list
     difference ("probe calls: 0 vs 1"). So the C of unit_max_hp (sheet
     batch) runs directly, as cursor_terrain and hp_window_max_hp do for
     their inlined branches (docs/CAPABILITY.md 2, 10). unit_max_hp asks its two
     caches first, before it reads anything.
   Guest function: 0x0052F7A0 Unit::GetCapabilityImpl(int,const unit::Item*,bool,bool,unit::detail::EnhanceDefinition::Type) const. */
int32_t unit_capability(Context *ctx, gaddr unit, uint32_t stat, gaddr item, uint32_t with_extras, gaddr sp) {
    if (stat >= CAP_STAT_COUNT)
        return (int32_t)fe_use_original(ctx); /* past the table: not followed */
    uint32_t with_loss = guest_u32(ctx, sp);
    uint32_t rally = guest_u32(ctx, sp + 4u);
    gaddr entry = CAP_STAT_TABLE + stat * CAP_STAT_TABLE_STEP;
    gaddr getter = guest_u32(ctx, entry);
    uint32_t adjust = guest_u32(ctx, entry + 4u);
    if (adjust != 0)
        return (int32_t)fe_use_original(ctx); /* a virtual or adjusted member pointer: not followed */
    if (getter == 0) {
        if (stat != 0)
            return 0;
        return unit_max_hp(ctx, unit, with_extras, with_loss, (int32_t)rally); /* the inlined tail branch */
    }
    if (!getter_caches_ready(ctx, getter))
        return (int32_t)fe_use_original(ctx); /* a cold cache, or not one of the getters */
    return (int32_t)guest_call5(ctx, getter, unit, item, with_extras, with_loss, rally);
}

/* The sum of stats 1..7 as Unit::GetCapabilityImpl gives them (no item, with
   the extras, the loss bool given, rally kind 0), added in stat order with
   32-bit wrap as the game's adds do. Every getter's caches are asked first. */
static int32_t capability_total(Context *ctx, gaddr unit, uint32_t with_loss) {
    if (!getter_caches_ready(ctx, CAP_UnitGetStrImpl) || !getter_caches_ready(ctx, CAP_UnitGetPowImpl) ||
        !getter_caches_ready(ctx, CAP_UnitGetTechImpl) || !getter_caches_ready(ctx, CAP_UnitGetQuickImpl) ||
        !getter_caches_ready(ctx, CAP_UnitGetLuckImpl) || !getter_caches_ready(ctx, CAP_UnitGetDefImpl) ||
        !getter_caches_ready(ctx, CAP_UnitGetMdefImpl))
        return (int32_t)fe_use_original(ctx);
    int32_t total = 0;
    for (uint32_t stat = CAP_TOTAL_FIRST; stat < CAP_TOTAL_END; stat++)
        total = fe_add32(total, (int32_t)guest_call6(ctx, CAP_UnitGetCapabilityImpl, unit, stat, CAP_TOTAL_ITEM,
                                                      CAP_TOTAL_EXTRAS, with_loss, CAP_TOTAL_RALLY));
    return total;
}

/* The unit's stat total (strength to resistance), debuffs taken off.
   Guest function: 0x005309E0 Unit::GetCapabilityRating(void) const. */
int32_t unit_capability_rating(Context *ctx, gaddr unit) {
    return capability_total(ctx, unit, CAP_TOTAL_LOSS_RATING);
}

/* The unit's stat total (strength to resistance), debuffs not taken off.
   Guest function: 0x00532B70 Unit::GetNoWeaknessCapabilityRating(void) const. */
int32_t unit_capability_rating_no_weakness(Context *ctx, gaddr unit) {
    return capability_total(ctx, unit, CAP_TOTAL_LOSS_NO_WEAKNESS);
}

RECOMP_OVERRIDE(0x0052F7A0) {
    FE_ENTRY(0x0052F7A0, unit_capability, FE_ARG(0), FE_ARG(1), FE_ARG(2), FE_ARG(3), FE_ARG(13));
}

RECOMP_OVERRIDE(0x005309E0) {
    FE_ENTRY(0x005309E0, unit_capability_rating, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00532B70) {
    FE_ENTRY(0x00532B70, unit_capability_rating_no_weakness, FE_ARG(0));
}
