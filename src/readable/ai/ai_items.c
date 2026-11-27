/* Which item the AI would use: a healing item, a stat booster, a heal rod
   (Fates class AIThink).

   Every function here only reads; the cached item kinds are only read, and
   the code gives up while a cache is empty. Plain-language description:
   docs/AI.md section 5.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   game's ARM code: src/readable/ai/tests/ai_perm_diff.py. */

#include "ai_perm.h"

/* the carried item in a slot of a unit (unit::Item, 4 bytes each) */
static gaddr slot_item(gaddr unit, uint32_t slot) {
    return FIELD_ADDR(Unit, unit, items) + 4u * slot;
}

/* the Item record of a carried item, through the guest as the game asks it */
static gaddr item_record_of(Context *ctx, gaddr item) {
    return guest_call1(ctx, AI_ItemToData, item);
}

/* the ItemUse kind of a carried item (a fresh ToData call each time, as the
   game asks it once per compare) */
static uint32_t use_kind(Context *ctx, gaddr item) {
    return guest_u8(ctx, item_record_of(ctx, item) + ITEMDATA_USE);
}

/* The slot of a healing item the AI's unit may use now (the two cached
   ItemUse kinds; Unit::CanItemUse asked for the AI's own unit), or -1. The
   unit's five slots first; then, only when `with_partner` and the unit has a
   partner, the partner's slots, counted 5 to 9. With `check_kind`, and always
   in the partner's slots, the item's weapon kind must also be 8 (a heal
   item).
   Guest function: 0x004CC684 AIThink::GetItemIndexHeal(Unit*,bool,bool). */
int32_t ai_item_index_heal(Context *ctx, gaddr think, gaddr unit, uint32_t check_kind, uint32_t with_partner) {
    if (!fe_static_ready(ctx, S_AiHealGuard0) || !fe_static_ready(ctx, S_AiHealGuard1))
        return (int32_t)fe_use_original(ctx);
    for (uint32_t pass = 0; pass < 2u; pass++) {
        gaddr holder = unit;
        if (pass == 1) {
            holder = READ_FIELD(ctx, Unit, unit, pair_partner);
            if (holder == 0 || with_partner == 0)
                return -1;
        }
        for (uint32_t slot = 0; slot < 5u; slot++) {
            gaddr item = slot_item(holder, slot);
            if (check_kind != 0 || pass == 1) {
                gaddr record = item_record_of(ctx, item);
                gaddr sub = guest_call1(ctx, AI_ItemSubKindGet, (uint32_t)(int32_t)guest_s8(ctx, record + ITEMDATA_KIND));
                if (guest_u8(ctx, sub + SUBKIND_KIND) != 8)
                    continue;
            }
            if (use_kind(ctx, item) != guest_u16(ctx, S_AiHealUse0) && use_kind(ctx, item) != guest_u16(ctx, S_AiHealUse1))
                continue;
            if (guest_call2(ctx, AI_UnitCanItemUse, guest_ptr(ctx, think + AITHINK_UNIT), item) != 0)
                return (int32_t)(pass * 5u + slot);
        }
    }
    return -1;
}

/* The slot of a stat booster the AI's unit should use now, or -1: an item
   not marked "the AI never uses it" (halfword +2 bit 15) whose ItemUse kind
   is one of the four cached ones and that Unit::CanItemUse allows (asked for
   the AI's own unit). An item of the fourth kind is taken as it is; one of
   the first three only when it raises a stat (record bytes +0x40..+0x47) whose
   bit 8 + stat in the unit's bytes from +0x28 is still clear.
   Guest function: 0x004CF360 AIThink::GetItemIndexDoping(Unit*). */
int32_t ai_item_index_doping(Context *ctx, gaddr think, gaddr unit) {
    if (!fe_static_ready(ctx, S_AiDopeGuard0) || !fe_static_ready(ctx, S_AiDopeGuard1) ||
        !fe_static_ready(ctx, S_AiDopeGuard2) || !fe_static_ready(ctx, S_AiDopeGuard3))
        return (int32_t)fe_use_original(ctx);
    for (uint32_t slot = 0; slot < 5u; slot++) {
        gaddr item = slot_item(unit, slot);
        if (guest_u16(ctx, item + 2u) & ITEM_SLOT_LOCKED)
            continue;
        if (use_kind(ctx, item) != guest_u16(ctx, S_AiDopeUse0) && use_kind(ctx, item) != guest_u16(ctx, S_AiDopeUse1) &&
            use_kind(ctx, item) != guest_u16(ctx, S_AiDopeUse2) && use_kind(ctx, item) != guest_u16(ctx, S_AiDopeUse3))
            continue;
        if (guest_call2(ctx, AI_UnitCanItemUse, guest_ptr(ctx, think + AITHINK_UNIT), item) == 0)
            continue;
        if (use_kind(ctx, item) == guest_u16(ctx, S_AiDopeUse3))
            return (int32_t)slot;
        int wanted = 0;
        for (uint32_t stat = 0; stat < 8u; stat++) {
            if (guest_u8(ctx, item_record_of(ctx, item) + ITEMDATA_DOPE + stat) == 0)
                continue;
            uint32_t bit = stat + 8u;
            if (!(guest_u8(ctx, unit + UNIT_SECRET_BITS + (bit >> 3)) & (1u << (bit & 7u))))
                wanted = 1;
        }
        if (wanted)
            return (int32_t)slot;
    }
    return -1;
}

/* Has the unit a heal rod it can wield (the cached item flag bit,
   Unit::CanItemEquip with both bools 1)? With the unit's byte +0x28 bit 3, a
   magic item (Item::IsMagic) does not count. With `needs_range`, a rod whose
   longest range (Unit::GetRangeO) is 255 does not count. With AI bit 7 the
   partner's items are looked at too, the same way. (Round 10's unit_range_max
   gave up on a record range of 0xFE, which no item of the game has; round 11
   passes that case on with guest_call5, so it no longer gives up there:
   docs/AI.md section 8.)
   Guest function: 0x004C829C AIThink::HasHealRod(Unit*,bool). */
uint32_t ai_has_heal_rod(Context *ctx, gaddr unit, uint32_t needs_range) {
    /* its own cache and those of the two overrides it calls */
    if (!fe_static_ready(ctx, S_AiRodGuard) || !fe_static_ready(ctx, S_AiMagicGuard) ||
        (needs_range != 0 && !fe_static_ready(ctx, S_AiRangeOGuard)))
        return fe_use_original(ctx);
    for (uint32_t pass = 0; pass < 2u; pass++) {
        gaddr holder = unit;
        if (pass == 1) {
            if (!(guest_u32(ctx, unit + UNIT_AI_FLAGS) & UNIT_AI_PAIR_ROD))
                return 0;
            holder = READ_FIELD(ctx, Unit, unit, pair_partner);
            if (holder == 0)
                return 0;
        }
        for (uint32_t slot = 0; slot < 5u; slot++) {
            gaddr item = slot_item(holder, slot);
            gaddr record = item_record_of(ctx, item);
            if ((READ_FIELD(ctx, ItemData, record, flags) & guest_u64(ctx, S_AiRodMask)) == 0)
                continue;
            if ((guest_u8(ctx, holder + UNIT_SECRET_BITS) & 0x08u) &&
                guest_call1(ctx, AI_ItemIsMagic, item_record_of(ctx, item)) != 0)
                continue;
            if (guest_call(ctx, AI_UnitCanItemEquip, holder, item, 1u, 1u) == 0)
                continue;
            if (needs_range != 0 && guest_call2(ctx, AI_UnitGetRangeO, holder, item) == 255)
                continue;
            return 1;
        }
    }
    return 0;
}

RECOMP_OVERRIDE(0x004CC684) {
    FE_ENTRY(0x004CC684, ai_item_index_heal, FE_ARG(0), FE_ARG(1), FE_ARG(2), FE_ARG(3));
}

RECOMP_OVERRIDE(0x004CF360) {
    FE_ENTRY(0x004CF360, ai_item_index_doping, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x004C829C) {
    FE_ENTRY(0x004C829C, ai_has_heal_rod, FE_ARG(0), FE_ARG(1));
}
