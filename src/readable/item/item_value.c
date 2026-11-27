/* What a carried item (Fates class unit::Item: the u16 item number, then a
   u16 of small fields) is worth: its might, hit and crit with the forge
   bonus, uses left, forge rank, whether two items are the same, whether it
   is used up, whether the smithy may forge it, and its sell price.
   Plain-language description: docs/ITEM.md section 3.

   All are readers: they store nothing. Some fill one-time caches (an
   ItemSkill flag bit found by name); the readable code gives up while one is
   cold, before reading anything else. Guest calls left: the ones the game
   makes (item.h), in the game's order (docs/DECISIONS.md F-018): the game
   asks Item::Get and Item::IsWeapon again and again instead of keeping the
   answer, and so does the readable code.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/item/tests/item_diff.py. */

#include "item.h"

/* Item::Get of the unit::Item's number, read again each time (as the game does). */
static gaddr record_of(Context *ctx, gaddr item) {
    return guest_call1(ctx, ITEM_ItemGet, guest_u16(ctx, item));
}

static uint32_t is_weapon(Context *ctx, gaddr record) {
    return guest_call1(ctx, ITEM_ItemIsWeapon, record);
}

static uint32_t item_bits(Context *ctx, gaddr item) {
    return guest_u16(ctx, item + ITEM_BITS);
}

/* bits 8-13: the forge rank of a weapon, the uses left of anything else */
static int32_t count_field(uint32_t bits) {
    return (int32_t)((bits >> ITEM_BITS_COUNT_SHIFT) & ITEM_BITS_COUNT_MASK);
}

/* The count field of a weapon, 0 for anything else (Item::IsWeapon asked first). */
static int32_t weapon_rank(Context *ctx, gaddr item, gaddr record) {
    return is_weapon(ctx, record) ? count_field(item_bits(ctx, item)) : 0;
}

/* A record value plus the forge bonus: a weapon with a forge rank, or any item
   with a forged name slot (2 and up), adds column `column` of its forge
   table's row for its rank (the second forge table for name slot 1), unless
   bit 7 says no bonus. */
static int32_t with_forge_bonus(Context *ctx, gaddr item, int32_t value, uint32_t column) {
    int forged;
    if (is_weapon(ctx, record_of(ctx, item)) && count_field(item_bits(ctx, item)) != 0)
        forged = 1;
    else
        forged = (item_bits(ctx, item) & ITEM_BITS_NAME) >= 2;
    if (!forged)
        return value;
    uint32_t bits = item_bits(ctx, item);
    if (bits & ITEM_BITS_NO_FORGE)
        return value;
    uint32_t table = (bits & ITEM_BITS_NAME) == 1 ? guest_u8(ctx, record_of(ctx, item) + ITEM_REFINE_TABLE_2)
                                                   : READ_FIELD(ctx, ItemData, record_of(ctx, item), refine_index);
    int32_t rank = weapon_rank(ctx, item, record_of(ctx, item));
    gaddr row = guest_call2(ctx, ITEM_ItemRefineGet, table, (uint32_t)rank);
    return fe_add32(value, guest_u8(ctx, row + column));
}

/* The weapon's might: the record's (u8) plus the forge bonus.
   Guest function: 0x0053B4B4 unit::Item::GetPower(void) const. */
int32_t item_might(Context *ctx, gaddr item) {
    int32_t might = READ_FIELD(ctx, ItemData, record_of(ctx, item), might);
    return with_forge_bonus(ctx, item, might, 1);
}

/* The weapon's hit: the record's (s16) plus the forge bonus.
   Guest function: 0x0053B2A4 unit::Item::GetHit(void) const. */
int32_t item_hit(Context *ctx, gaddr item) {
    int32_t hit = READ_FIELD(ctx, ItemData, record_of(ctx, item), hit);
    return with_forge_bonus(ctx, item, hit, 2);
}

/* The weapon's crit: the record's (s16) plus the forge bonus.
   Guest function: 0x0053AD54 unit::Item::GetCritical(void) const. */
int32_t item_crit(Context *ctx, gaddr item) {
    int32_t crit = READ_FIELD(ctx, ItemData, record_of(ctx, item), crit);
    return with_forge_bonus(ctx, item, crit, 3);
}

/* Uses left: the count field of anything that is not a weapon; 0 for a weapon
   (Fates weapons do not wear out).
   Guest function: 0x0053AE48 unit::Item::GetEndurance(void) const. */
int32_t item_uses_left(Context *ctx, gaddr item) {
    if (is_weapon(ctx, record_of(ctx, item)))
        return 0;
    return count_field(item_bits(ctx, item));
}

/* The forge rank: the count field of a weapon, 0 for anything else.
   Guest function: 0x0053B278 unit::Item::GetRefineRank(void) const. */
int32_t item_forge_rank(Context *ctx, gaddr item) {
    return weapon_rank(ctx, item, record_of(ctx, item));
}

/* 1 when both are the same item with the same name slot (the convoy stacks
   such items).
   Guest function: 0x0053AE18 unit::Item::IsIntegrate(const unit::Item*) const. */
uint32_t item_same_kind(Context *ctx, gaddr item, gaddr other) {
    if (guest_u16(ctx, item) != guest_u16(ctx, other))
        return 0;
    return (item_bits(ctx, item) & ITEM_BITS_NAME) == (item_bits(ctx, other) & ITEM_BITS_NAME) ? 1u : 0u;
}

/* 1 when both are the same item, name slot and count field.
   Guest function: 0x0053B470 unit::Item::IsEqual(const unit::Item*) const. */
uint32_t item_equals(Context *ctx, gaddr item, gaddr other) {
    if (guest_u16(ctx, item) != guest_u16(ctx, other))
        return 0;
    uint32_t a = item_bits(ctx, item), b = item_bits(ctx, other);
    if ((a & ITEM_BITS_NAME) != (b & ITEM_BITS_NAME))
        return 0;
    return count_field(a) == count_field(b) ? 1u : 0u;
}

/* 1 for an item that is used up (anything but a weapon, unless it has the
   "unlimited uses" flag bit).
   Guest function: 0x0053B578 unit::Item::IsExpend(void) const. */
uint32_t item_is_consumable(Context *ctx, gaddr item) {
    if (!fe_static_ready(ctx, S_ExpendGuard))
        return fe_use_original(ctx);
    gaddr record = record_of(ctx, item);
    if (is_weapon(ctx, record))
        return 0;
    return (READ_FIELD(ctx, ItemData, record, flags) & guest_u64(ctx, S_ExpendMask)) == 0 ? 1u : 0u;
}

/* 1 when the smithy may forge it: a weapon without the "cannot be forged",
   "valuable" or "cannot be removed" flag bits, whose sub-kind's forge group
   is not negative.
   Guest function: 0x0053B0F8 unit::Item::IsShopRefine(void) const. */
uint32_t item_can_forge(Context *ctx, gaddr item) {
    if (!fe_static_ready(ctx, S_ForgeGuard0) || !fe_static_ready(ctx, S_ForgeGuard1) ||
        !fe_static_ready(ctx, S_ForgeGuard2))
        return fe_use_original(ctx);
    gaddr record = record_of(ctx, item);
    if (!is_weapon(ctx, record))
        return 0;
    uint64_t flags = READ_FIELD(ctx, ItemData, record, flags);
    if (flags & guest_u64(ctx, S_ForgeMaskNoForge))
        return 0;
    if (flags & guest_u64(ctx, S_ForgeMaskValuable))
        return 0;
    if (flags & guest_u64(ctx, S_ForgeMaskLocked))
        return 0;
    gaddr sub = guest_call1(ctx, ITEM_ItemSubKindGet, (uint32_t)(int32_t)READ_FIELD(ctx, ItemData, record, weapon_kind));
    return READ_FIELD(ctx, ItemSubKindData, sub, refine_group) >= 0 ? 1u : 0u;
}

/* 1 when the item may be forged and the other is the same item with the same
   forge rank (the smithy's "forge together" test).
   Guest function: 0x0053B070 unit::Item::IsShopRefine(const unit::Item*) const. */
uint32_t item_can_forge_with(Context *ctx, gaddr item, gaddr other) {
    /* the guards of IsShopRefine(void), asked before its guest call (no give-up inside it) */
    if (!fe_static_ready(ctx, S_ForgeGuard0) || !fe_static_ready(ctx, S_ForgeGuard1) ||
        !fe_static_ready(ctx, S_ForgeGuard2))
        return fe_use_original(ctx);
    if (guest_call1(ctx, ITEM_ItemIsShopRefine, item) == 0)
        return 0;
    uint32_t number = guest_u16(ctx, item);
    if (number != guest_u16(ctx, other))
        return 0;
    /* the number just read goes to Item::Get (not read again) */
    int32_t rank = weapon_rank(ctx, item, guest_call1(ctx, ITEM_ItemGet, number));
    return rank == weapon_rank(ctx, other, record_of(ctx, other)) ? 1u : 0u;
}

/* The sell price: -1 (cannot be sold) with the "valuable" or "cannot be
   removed" flag bits; a weapon's record price doubled once per forge rank;
   anything else's record price times uses left over the record's full uses
   (unsigned division; the full price with no uses left or a record of 0 uses).
   Guest function: 0x0053AE8C unit::Item::GetSellPrice(void) const. */
int32_t item_sell_price(Context *ctx, gaddr item) {
    if (!fe_static_ready(ctx, S_SellGuard0) || !fe_static_ready(ctx, S_SellGuard1))
        return (int32_t)fe_use_original(ctx);
    gaddr record = record_of(ctx, item);
    uint64_t barred = guest_u64(ctx, S_SellMaskLocked) | guest_u64(ctx, S_SellMaskValuable);
    if (READ_FIELD(ctx, ItemData, record, flags) & barred)
        return -1;
    if (is_weapon(ctx, record)) {
        uint32_t price = (uint32_t)READ_FIELD(ctx, ItemData, record, sell_price);
        int32_t doubled = 0;
        if (!is_weapon(ctx, record_of(ctx, item)) || count_field(item_bits(ctx, item)) <= 0)
            return (int32_t)price;
        do {
            price <<= 1;
            doubled++;
        } while (weapon_rank(ctx, item, record_of(ctx, item)) > doubled);
        return (int32_t)price;
    }
    if (is_weapon(ctx, record_of(ctx, item)))
        return READ_FIELD(ctx, ItemData, record, sell_price);
    int32_t uses = count_field(item_bits(ctx, item));
    if (uses <= 0)
        return READ_FIELD(ctx, ItemData, record, sell_price);
    uint32_t full = READ_FIELD(ctx, ItemData, record, uses);
    if (full == 0)
        return READ_FIELD(ctx, ItemData, record, sell_price);
    uint32_t price = (uint32_t)READ_FIELD(ctx, ItemData, record, sell_price);
    return (int32_t)(((uint32_t)uses * price) / full);
}

RECOMP_OVERRIDE(0x0053B4B4) {
    FE_ENTRY(0x0053B4B4, item_might, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0053B2A4) {
    FE_ENTRY(0x0053B2A4, item_hit, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0053AD54) {
    FE_ENTRY(0x0053AD54, item_crit, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0053AE48) {
    FE_ENTRY(0x0053AE48, item_uses_left, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0053B278) {
    FE_ENTRY(0x0053B278, item_forge_rank, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0053AE18) {
    FE_ENTRY(0x0053AE18, item_same_kind, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0053B470) {
    FE_ENTRY(0x0053B470, item_equals, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0053B578) {
    FE_ENTRY(0x0053B578, item_is_consumable, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0053B0F8) {
    FE_ENTRY(0x0053B0F8, item_can_forge, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0053B070) {
    FE_ENTRY(0x0053B070, item_can_forge_with, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0053AE8C) {
    FE_ENTRY(0x0053AE8C, item_sell_price, FE_ARG(0));
}
