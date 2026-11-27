/* Item questions about a unit and one of its items (Fates class Unit): the
   weapon's longest range for this unit, the HP an item heals when this unit
   uses it, and whether a unit may fire a ballista ("cannon") with an item or
   has any item it may fire one with.
   Plain-language description: docs/ITEM.md section 4.

   All are readers: they store nothing. Two fill one-time caches (an equip
   skill or an ItemSkill flag bit found by name); the readable code gives up
   while one is cold, before reading anything else. Guest calls left: the
   ones the game makes (item.h), in the game's order (docs/DECISIONS.md F-018).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/item/tests/item_diff.py. */

#include "item.h"

static gaddr to_data(Context *ctx, gaddr item) {
    return guest_call1(ctx, ITEM_ItemToData, item);
}

static uint32_t has_skill(Context *ctx, gaddr unit, gaddr skill_cache) {
    return guest_call2(ctx, ITEM_UnitIsEquipSkill, unit, (uint32_t)(int32_t)guest_s16(ctx, skill_cache));
}

/* The weapon's longest range: the record's, but at least 10 for a staff
   (kind 6) when the unit has the "endless staff" skill. A record range of
   0xFE means half the unit's magic (rounded down, at least 1): the game
   calls Unit::GetPowImpl(unit, no item, with extras, with loss, rally kind 0)
   with the fifth argument on the stack, passed here with guest_call5 (round
   11; before, the readable code gave up there). No item of the game has that
   range (docs/ITEM.md section 4).
   Guest function: 0x00534510 Unit::GetRangeO(const unit::Item*) const. */
int32_t unit_range_max(Context *ctx, gaddr unit, gaddr item) {
    if (!fe_static_ready(ctx, S_RangeOGuard))
        return (int32_t)fe_use_original(ctx);
    int32_t range = READ_FIELD(ctx, ItemData, to_data(ctx, item), range_max);
    if (range == ITEM_RANGE_MAGIC) {
        int32_t half = fe_asr((int32_t)guest_call5(ctx, ITEM_UnitGetPowImpl, unit, 0u, 1u, 1u, 0u), 1);
        range = half < 1 ? 1 : half;
    }
    gaddr record = to_data(ctx, item);
    gaddr sub = guest_call1(ctx, ITEM_ItemSubKindGet, (uint32_t)(int32_t)READ_FIELD(ctx, ItemData, record, weapon_kind));
    if (READ_FIELD(ctx, ItemSubKindData, sub, kind) == ITEM_KIND_STAFF && has_skill(ctx, unit, S_RangeOSkill) != 0 &&
        range < ITEM_STAFF_RANGE)
        range = ITEM_STAFF_RANGE;
    return range;
}

/* The HP an item heals when this unit uses it: the record's heal amount
   (s8), half again (rounded toward zero) for an item with the "standing
   medicine" flag bit when the unit has the "potent medicine" skill.
   Guest function: 0x0052F288 Unit::GetItemHealPower(const unit::Item*) const. */
int32_t unit_item_heal_amount(Context *ctx, gaddr unit, gaddr item) {
    if (!fe_static_ready(ctx, S_HealGuard0) || !fe_static_ready(ctx, S_HealGuard1) ||
        !fe_static_ready(ctx, S_HealGuard2) || !fe_static_ready(ctx, S_HealGuard3) ||
        !fe_static_ready(ctx, S_HealGuard4))
        return (int32_t)fe_use_original(ctx);
    gaddr record = to_data(ctx, item);
    int32_t heal = guest_s8(ctx, record + ITEM_HEAL);
    if (has_skill(ctx, unit, S_HealSkill) != 0 &&
        (READ_FIELD(ctx, ItemData, record, flags) & guest_u64(ctx, S_HealMask)) != 0)
        heal += heal / 2;
    return heal;
}

/* May the unit fire a ballista with this item: Unit::CanItemEquip(item,
   false, true) must say yes; then, when asked to check magic and condition
   byte 0 has bit 3, a magic weapon is refused. */
static int cannon_item(Context *ctx, gaddr unit, gaddr item, uint32_t check_magic) {
    if (guest_call(ctx, ITEM_UnitCanItemEquip, unit, item, 0u, 1u) == 0)
        return 0;
    if (check_magic == 0 || (guest_u8(ctx, unit + UNIT_CONDITION_0) & 0x08u) == 0)
        return 1;
    return guest_call1(ctx, ITEM_ItemIsMagic, to_data(ctx, item)) == 0;
}

/* Guest function: 0x0052DF90 Unit::CanCannonItem(const unit::Item*,bool) const. */
uint32_t unit_can_cannon_item(Context *ctx, gaddr unit, gaddr item, uint32_t check_magic) {
    /* Item::IsMagic's guard, asked before its guest call (no give-up inside it) */
    if (!fe_static_ready(ctx, S_ItemMagicGuard))
        return fe_use_original(ctx);
    return cannon_item(ctx, unit, item, check_magic) ? 1u : 0u;
}

/* 1 when any of the unit's five item slots passes the test above.
   Guest function: 0x0052F1AC Unit::IsItemCanCannon(bool) const. */
uint32_t unit_has_cannon_item(Context *ctx, gaddr unit, uint32_t check_magic) {
    if (!fe_static_ready(ctx, S_ItemMagicGuard))
        return fe_use_original(ctx);
    for (uint32_t slot = 0; slot < 5u; slot++)
        if (cannon_item(ctx, unit, unit + UNIT_ITEMS + slot * 4u, check_magic))
            return 1;
    return 0;
}

RECOMP_OVERRIDE(0x00534510) {
    FE_ENTRY(0x00534510, unit_range_max, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052F288) {
    FE_ENTRY(0x0052F288, unit_item_heal_amount, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052DF90) {
    FE_ENTRY(0x0052DF90, unit_can_cannon_item, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x0052F1AC) {
    FE_ENTRY(0x0052F1AC, unit_has_cannon_item, FE_ARG(0), FE_ARG(1));
}
