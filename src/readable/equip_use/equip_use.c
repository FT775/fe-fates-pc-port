/* May this unit hold this item (Fates Unit::CanItemEquip). Plain-language
   description: docs/EQUIP_USE.md.

   unit_can_equip_item is a reader: it stores nothing. The game's function
   fills 21 one-time caches of its own the first time it runs (names looked up
   in the data tables); the readable code gives up while any of them, or a
   cache of an override it calls, is cold, before reading anything else.

   Not here: Unit::CanItemUse (0x0052920C, "may this unit use this item now").
   It builds a ClassChangeEnumerator object in its own 1,040-byte stack frame
   and has ClassChangeEnumerator::Enumerate fill it, and it calls
   Unit::GetCapabilityImpl with two words on the stack. The readable side
   cannot hand a callee a guest stack object without writing guest memory,
   and guest_call5 passes one stack word, not two (docs/EQUIP_USE.md
   section 4).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/equip_use/tests/equip_use_diff.py. */

#include "equip_use.h"

/* Every cache this function reads, and those of the overrides it calls. */
static int caches_ready(Context *ctx) {
    for (gaddr g = S_EuGuardFirst; g <= S_EuGuardLast; g += S_EuGuardStep)
        if (!fe_static_ready(ctx, g))
            return 0;
    return fe_static_ready(ctx, S_EuExpLimitGuardA) && fe_static_ready(ctx, S_EuExpLimitGuardB) &&
           fe_static_ready(ctx, S_EuExpLimitGuardC) && fe_static_ready(ctx, S_EuDownloadGuard) &&
           fe_static_ready(ctx, S_EuCatGuard0) && fe_static_ready(ctx, S_EuCatGuard1) &&
           fe_static_ready(ctx, S_EuCatGuard2) && fe_static_ready(ctx, S_EuCatGuard3) &&
           fe_static_ready(ctx, S_EuCatGuard4);
}

/* The record's ItemFlag word has one of the bits in the cache at `mask`
   (the record's flags are read again each time, as the game does). */
static int item_has(Context *ctx, gaddr record, gaddr mask) {
    return (READ_FIELD(ctx, ItemData, record, flags) & guest_u64(ctx, mask)) != 0;
}

/* The unit's PersonFlag bits: its own word ORed with its Person's and its
   class's, read afresh; the Person pointer read on the way is handed back. */
static uint64_t unit_flags(Context *ctx, gaddr unit, gaddr *person) {
    *person = READ_FIELD(ctx, Unit, unit, person);
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    return READ_FIELD(ctx, Unit, unit, private_flags) | READ_FIELD(ctx, PersonData, *person, flags) |
           READ_FIELD(ctx, JobData, job, flags);
}

/* A "royal only" item (its ItemFlag word `flags` has the bit in the
   cache at `item_mask`): the unit (or its Person or class) must carry the
   matching PersonFlag bit at `person_mask`, and a unit with state bit 28 must
   have a download Person as well. Returns 0 when that rules the item out. */
static int personal_ok(Context *ctx, gaddr unit, uint64_t flags, gaddr item_mask, gaddr person_mask) {
    if ((flags & guest_u64(ctx, item_mask)) == 0)
        return 1;
    gaddr person;
    if ((unit_flags(ctx, unit, &person) & guest_u64(ctx, person_mask)) == 0)
        return 0;
    if ((READ_FIELD(ctx, Unit, unit, state_flags) & EU_UNIT_DOWNLOAD_ONLY) &&
        guest_call1(ctx, EU_PersonIsDownload, person) == 0)
        return 0;
    return 1;
}

/* the record's ItemFlag word, read afresh (the game reads it again for each test but the first) */
static uint64_t item_flags(Context *ctx, gaddr record) {
    return READ_FIELD(ctx, ItemData, record, flags);
}

/* The ItemSubKind record of the record's sub-kind (its byte +1 is the weapon kind; a fresh
   ItemSubKind::Get each time, as the game asks it). */
static gaddr subkind_of(Context *ctx, gaddr record) {
    return guest_call1(ctx, EU_ItemSubKindGet, (uint32_t)(int32_t)READ_FIELD(ctx, ItemData, record, weapon_kind));
}

/* May `unit` hold `item` (a unit::Item)? 1 or 0.
     - kinds 8 and up never; a staff only with `allow_staff`;
     - the rank: the weapon experience needed (ItemData.weapon_rank) must be
       reached by the class's cap for the kind (GetWeaponExpLimit) or, with
       `current_rank`, by the unit's own experience in that kind, capped;
     - a stone also needs the class to accept the sub-kind;
     - "only for" items (when any of the nine bits is set): avatar and the
       five royals (each with its PersonFlag bit), dark-mage line (the
       class category, or the skill that opens dark tomes), male, female;
     - a unit with the "no warp" bit may not hold a rescue or draw staff.
   Guest function: 0x0052C634 Unit::CanItemEquip(const unit::Item*,bool,bool) const. */
uint32_t unit_can_equip_item(Context *ctx, gaddr unit, gaddr item, uint32_t allow_staff, uint32_t current_rank) {
    if (!caches_ready(ctx))
        return fe_use_original(ctx);
    gaddr record = guest_call1(ctx, EU_ItemToData, item);
    int32_t kind = guest_s8(ctx, subkind_of(ctx, record) + EU_SUBKIND_KIND);
    if (allow_staff == 0 && kind == EU_KIND_STAFF)
        return 0;
    if (kind >= EU_KIND_COUNT)
        return 0;

    int32_t reach;
    if (current_rank != 0) {
        int32_t exp = guest_u8(ctx, FIELD_ADDR(Unit, unit, weapon_exp) + (gaddr)kind);
        int32_t cap = (int32_t)guest_call2(ctx, EU_UnitGetWeaponExpLimit, unit, (uint32_t)kind);
        reach = cap < exp ? cap : exp;
    } else {
        reach = (int32_t)guest_call2(ctx, EU_UnitGetWeaponExpLimit, unit, (uint32_t)kind);
    }
    if (reach < (int32_t)READ_FIELD(ctx, ItemData, record, weapon_rank))
        return 0;

    if (guest_u8(ctx, subkind_of(ctx, record) + EU_SUBKIND_KIND) == EU_KIND_STONE &&
        guest_call2(ctx, EU_JobCanEquipFromSubKind, READ_FIELD(ctx, Unit, unit, job),
                    (uint32_t)(int32_t)READ_FIELD(ctx, ItemData, record, weapon_kind)) == 0)
        return 0;

    uint64_t flags = item_flags(ctx, record);
    if ((flags & guest_u64(ctx, S_EuAnyOnly)) != 0) {
        /* the avatar test uses the word just read; every later test reads it again */
        if (!personal_ok(ctx, unit, flags, S_EuAvatarOnly, S_EuAvatarFlag))
            return 0;
        if (item_has(ctx, record, S_EuDarkMageOnly) &&
            (guest_call1(ctx, EU_UnitGetCategory, unit) & guest_u16(ctx, S_EuDarkMageCategory)) == 0 &&
            guest_call2(ctx, EU_UnitIsEquipSkill, unit, (uint32_t)(int32_t)guest_s16(ctx, S_EuDarkMageSkill)) == 0)
            return 0;
        if (item_has(ctx, record, S_EuMaleOnly) && guest_call1(ctx, EU_UnitIsFemale, unit) != 0)
            return 0;
        if (item_has(ctx, record, S_EuFemaleOnly) && guest_call1(ctx, EU_UnitIsFemale, unit) == 0)
            return 0;
        if (!personal_ok(ctx, unit, item_flags(ctx, record), S_EuTakumiOnly, S_EuTakumiFlag) ||
            !personal_ok(ctx, unit, item_flags(ctx, record), S_EuRyomaOnly, S_EuRyomaFlag) ||
            !personal_ok(ctx, unit, item_flags(ctx, record), S_EuLeoOnly, S_EuLeoFlag) ||
            !personal_ok(ctx, unit, item_flags(ctx, record), S_EuXanderOnly, S_EuXanderFlag) ||
            !personal_ok(ctx, unit, item_flags(ctx, record), S_EuOpheliaOnly, S_EuOpheliaFlag))
            return 0;
    }

    gaddr person;
    if ((unit_flags(ctx, unit, &person) & guest_u64(ctx, S_EuNoWarpFlag)) == 0)
        return 1;
    if (guest_u8(ctx, subkind_of(ctx, record) + EU_SUBKIND_KIND) != EU_KIND_STAFF)
        return 1;
    uint32_t use = guest_u8(ctx, record + EU_ITEMDATA_USE);
    if (use == guest_u16(ctx, S_EuRescueUse) || use == guest_u16(ctx, S_EuDrawUse))
        return 0;
    return 1;
}

RECOMP_OVERRIDE(0x0052C634) {
    FE_ENTRY(0x0052C634, unit_can_equip_item, FE_ARG(0), FE_ARG(1), FE_ARG(2), FE_ARG(3));
}
