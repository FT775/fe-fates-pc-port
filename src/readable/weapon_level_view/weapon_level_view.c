/* The weapon-rank line of the unit screen (Fates GameInfoViewer): which
   weapon icon goes on line N. Plain-language description:
   docs/WEAPON_LEVEL_VIEW.md.

   weapon_level_view_kind is a reader: it stores nothing. Its callers are draw
   code (ViewerUnitStatus::DrawDetail, HelpItemWeaponLv::Draw and ::IsInside,
   castle::ShopBuyUnitInfoDrawer::Draw) and stay in the game. The rank-up
   window (ProcWeaponExp::ShowWeaponLevelUp) and Unit::AddWeaponExp (a writer)
   are not here.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/weapon_level_view/tests/weapon_level_view_diff.py. */

#include "weapon_level_view.h"

/* Unit::GetWeaponExpLimit's three caches are filled (Unit::GetWeaponExp's
   override reads them and cannot give up inside a guest call). */
static int exp_limit_ready(Context *ctx) {
    return fe_static_ready(ctx, S_WlvExpLimitGuardA) && fe_static_ready(ctx, S_WlvExpLimitGuardB) &&
           fe_static_ready(ctx, S_WlvExpLimitGuardC);
}

/* The weapon sub-kind shown on line `line` (counted from 0) of a unit's
   weapon-rank list: the lines are the weapon kinds 0 .. 7 in which the unit
   has weapon exp above 0 (Unit::GetWeaponExp, capped at the class limit), in
   kind order. For the kind of that line, the answer is the first ItemSubKind
   number 0 .. 20 whose record has that kind; for stones (kind 7) the unit's
   class must also be able to use the sub-kind (Job::CanEquipFromSubKind).
   -1 when the unit has fewer lines, or when no sub-kind fits (the game then
   still asks GetWeaponExp for the kinds after it, and never finds a line).
   `line` is compared as a full signed word, not range-checked.
   Guest function: 0x001D13A4 GameInfoViewer::GetWeaponLevelKind(const Unit*,int). */
int32_t weapon_level_view_kind(Context *ctx, gaddr unit, int32_t line) {
    if (!exp_limit_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    int32_t seen = 0;
    for (int32_t kind = 0; kind < WLV_KINDS; kind++) {
        /* the game passes the kind sign-extended from its low byte */
        int32_t exp = (int32_t)guest_call2(ctx, WLV_UnitGetWeaponExp, unit, (uint32_t)(int32_t)(int8_t)kind);
        if (exp <= 0)
            continue;
        if (seen == line) {
            for (int32_t sub = 0; sub < WLV_SUBKINDS; sub++) {
                gaddr record = guest_call1(ctx, WLV_ItemSubKindGet, (uint32_t)sub);
                if (guest_s8(ctx, FIELD_ADDR(ItemSubKindData, record, kind)) != kind)
                    continue;
                if (kind != WLV_KIND_STONE ||
                    guest_call2(ctx, WLV_JobCanEquipFromSubKind, READ_FIELD(ctx, Unit, unit, job),
                                (uint32_t)(int32_t)(int8_t)sub) != 0)
                    return (int32_t)(int8_t)sub;
            }
        }
        seen++;
    }
    return WLV_NONE;
}

RECOMP_OVERRIDE(0x001D13A4) {
    FE_ENTRY(0x001D13A4, weapon_level_view_kind, FE_ARG(0), FE_ARG_S(1));
}
