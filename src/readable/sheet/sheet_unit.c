/* Small questions about a unit (Fates class Unit): its class categories
   (dragon, beast, flying ...), the equipped item, the level shown and the
   "low" level used for experience, how many items it carries, its weapon's
   shortest range, whom it may never attack, whether it is unique, a giant
   (special battle), invisible, capturable, and which item it holds.
   Plain-language description: docs/SHEET.md sections 3 and 4.

   All are readers: they store nothing. Some fill one-time caches (a category
   bit or a PersonFlag bit found by name); the readable code gives up while
   one is cold, before reading anything else. Guest calls left: the ones the
   game makes (sheet.h), in the game's order (docs/DECISIONS.md F-018).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/sheet/tests/sheet_diff.py. */

#include "sheet.h"

/* The unit's class categories (JobCategory bits, u16): the class's own, plus
   "dragon" for a unit, person or class with the "manakete" PersonFlag bit,
   plus "beast" for the "laguz" bit, minus "dragon" for the "cannot use special
   weapons" bit (the three flag words ORed together, as the game does).
   Guest function: 0x0052B728 Unit::GetCategory(void) const. */
uint32_t unit_category(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, S_CatGuard0) || !fe_static_ready(ctx, S_CatGuard1) ||
        !fe_static_ready(ctx, S_CatGuard2) || !fe_static_ready(ctx, S_CatGuard3) ||
        !fe_static_ready(ctx, S_CatGuard4))
        return fe_use_original(ctx);
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    uint64_t flags = READ_FIELD(ctx, Unit, unit, private_flags);
    flags |= READ_FIELD(ctx, PersonData, person, flags);
    flags |= READ_FIELD(ctx, JobData, job, flags);
    uint32_t category = READ_FIELD(ctx, JobData, job, category);
    if (flags & guest_u64(ctx, S_CatDragonFlag))
        category |= guest_u16(ctx, S_CatDragon);
    if (flags & guest_u64(ctx, S_CatBeastFlag))
        category |= guest_u16(ctx, S_CatBeast);
    if (flags & guest_u64(ctx, S_CatNoDragonFlag))
        category &= ~(uint32_t)guest_u16(ctx, S_CatDragon);
    return category;
}

static gaddr equipped_item(Context *ctx, gaddr unit) {
    int32_t slot = (int32_t)guest_call1(ctx, SHEET_UnitGetItemIndexEquipped, unit);
    if (slot < 0)
        return 0;
    return FIELD_ADDR(Unit, unit, items) + (gaddr)slot * 4u;
}

/* The equipped item (its unit::Item in the unit's list), or 0.
   Guest function: 0x0052EFE8 Unit::GetItemEquipped(void) const. */
gaddr unit_equipped_item(Context *ctx, gaddr unit) {
    return equipped_item(ctx, unit);
}

/* The same code a second time in the game (the non-const form).
   Guest function: 0x003D5FB0 Unit::GetItemEquipped(void). */
gaddr unit_equipped_item_mutable(Context *ctx, gaddr unit) {
    return equipped_item(ctx, unit);
}

/* The level shown: the level byte, at most 99.
   Guest function: 0x0052DC44 Unit::GetShowLevel(void) const. */
int32_t unit_shown_level(Context *ctx, gaddr unit) {
    int32_t level = READ_FIELD(ctx, Unit, unit, level);
    return level > 99 ? 99 : level;
}

/* The level counted from the first class: the level, plus 20 in a class with
   the "promoted class" PersonFlag bit.
   Guest function: 0x0052BBCC Unit::GetLowLevel(void) const. */
int32_t unit_low_level(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, S_LowLevelGuard))
        return (int32_t)fe_use_original(ctx);
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    uint64_t mask = guest_u64(ctx, S_LowLevelMask);
    int32_t level = READ_FIELD(ctx, Unit, unit, level);
    if (READ_FIELD(ctx, JobData, job, flags) & mask)
        level += 20;
    return level;
}

/* How many items the unit carries: the slot of the first empty item (item
   number 0), or 5.
   Guest function: 0x0052E594 Unit::GetHasItemNum(void) const. */
int32_t unit_item_count(Context *ctx, gaddr unit) {
    for (int32_t slot = 0; slot < UNIT_ITEM_SLOT_COUNT; slot++)
        if (guest_u16(ctx, FIELD_ADDR(Unit, unit, items) + (gaddr)slot * 4u) == 0)
            return slot;
    return UNIT_ITEM_SLOT_COUNT;
}

/* The item's sub-kind's weapon kind (ItemSubKind::Get of the record's s8). */
static uint32_t item_weapon_kind(Context *ctx, gaddr item) {
    gaddr data = guest_call1(ctx, SHEET_ItemToData, item);
    gaddr subkind = guest_call1(ctx, SHEET_ItemSubKindGet, (uint32_t)(int32_t)guest_s8(ctx, data + ITEM_SUBKIND));
    return guest_u8(ctx, subkind + SUBKIND_KIND);
}

/* The item's shortest range: the record's, but 1 for a bow (kind 4) whose
   shortest range is 2 or more when the unit has the "close shot" skill.
   Guest function: 0x00534474 Unit::GetRangeI(const unit::Item*) const. */
int32_t unit_range_min(Context *ctx, gaddr unit, gaddr item) {
    if (!fe_static_ready(ctx, S_RangeGuard))
        return (int32_t)fe_use_original(ctx);
    gaddr data = guest_call1(ctx, SHEET_ItemToData, item);
    int32_t range = guest_u8(ctx, data + ITEM_RANGE_MIN);
    if (range < 2)
        return range;
    if (item_weapon_kind(ctx, item) == 4 &&
        guest_call2(ctx, SHEET_UnitIsEquipSkill, unit, (uint32_t)(int32_t)guest_s16(ctx, S_RangeSkill)) != 0)
        return 1;
    return range;
}

/* 1 when the unit may never attack the other: either has state bit 22 (not
   asked when the third argument is set), the other's Person is the one this
   unit is told never to attack, or the other's force type is a bit of this
   unit's "never attack" force set.
   Guest function: 0x0052DC90 Unit::IsDontAttack(const Unit*,bool) const. */
uint32_t unit_may_not_attack(Context *ctx, gaddr unit, gaddr other, uint32_t ignore_state) {
    if (!ignore_state) {
        if (READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_NO_ATTACK)
            return 1;
        if (READ_FIELD(ctx, Unit, other, state_flags) & UNIT_STATE_NO_ATTACK)
            return 1;
    }
    gaddr person = guest_u32(ctx, unit + UNIT_NO_ATTACK_PERSON);
    if (person != 0 && READ_FIELD(ctx, Unit, other, person) == person)
        return 1;
    uint32_t forces = guest_u8(ctx, unit + UNIT_NO_ATTACK_FORCES);
    if (forces == 0)
        return 0;
    gaddr force = READ_FIELD(ctx, Unit, other, force);
    uint32_t type = READ_FIELD(ctx, Force, force, type);
    /* the game shifts by a register: 32 or more gives 0 */
    return (type < 32u && (forces & (1u << type)) != 0) ? 1u : 0u;
}

/* 1 for a unique unit: not with state bit 18; with state bit 28 only when its
   Person is a downloaded (DLC) one.
   Guest function: 0x00533A80 Unit::IsUnique(void) const. */
uint32_t unit_is_unique(Context *ctx, gaddr unit) {
    if (READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_NOT_UNIQUE)
        return 0;
    if (!(READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_MAYBE_CLONE))
        return 1;
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    return guest_call1(ctx, SHEET_PersonIsDownload, person) != 0 ? 1u : 0u;
}

/* 1 when the unit's fights are "special battles": its class is a giant
   (Job::IsGiant) or has its special-battle byte set; 0 without a class.
   Guest function: 0x0052F234 Unit::IsSpecialBattle(void) const. */
uint32_t unit_is_special_battle(Context *ctx, gaddr unit) {
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    if (job == 0)
        return 0;
    if (guest_call1(ctx, SHEET_JobIsGiant, job) != 0)
        return 1;
    job = READ_FIELD(ctx, Unit, unit, job);
    return READ_FIELD(ctx, JobData, job, special_battle) != 0 ? 1u : 0u;
}

static uint32_t belong_flags(Context *ctx, gaddr unit) {
    gaddr belong = guest_call1(ctx, SHEET_BelongGet, guest_u8(ctx, unit + UNIT_BELONG));
    return guest_u8(ctx, belong + BELONG_FLAGS);
}

/* Bit 0 of the unit's Belong record's flags.
   Guest function: 0x0052C61C Unit::IsInvisible(void) const. */
uint32_t unit_is_invisible(Context *ctx, gaddr unit) {
    return belong_flags(ctx, unit) & 1u;
}

/* 1 when the unit can be captured: its Person's word +0xC is set or its
   Belong allows it (bit 1), and its Person becomes someone for its class
   (Person::GetCaptureChange).
   Guest function: 0x0052AE20 Unit::CanCaptured(void) const. */
uint32_t unit_can_be_captured(Context *ctx, gaddr unit) {
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    if (guest_u32(ctx, person + PERSON_CAPTURE_WORD) == 0 && (belong_flags(ctx, unit) & 2u) == 0)
        return 0;
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    uint32_t job_number = READ_FIELD(ctx, JobData, job, job_number);
    person = READ_FIELD(ctx, Unit, unit, person);
    return guest_call2(ctx, SHEET_PersonGetCaptureChange, person, job_number) != 0 ? 1u : 0u;
}

/* The slot of the item the unit holds: the equipped one, else the first staff
   (kind 6) it may wield (Unit::CanItemEquip(item, true, true)); -1 for none.
   Each slot is tested in turn, the equipped bit first.
   Guest function: 0x0052F474 Unit::GetItemIndexHold(void) const. */
int32_t unit_held_item_index(Context *ctx, gaddr unit) {
    for (int32_t slot = 0; slot < UNIT_ITEM_SLOT_COUNT; slot++) {
        gaddr item = FIELD_ADDR(Unit, unit, items) + (gaddr)slot * 4u;
        if (guest_u16(ctx, item + 2u) & UNIT_ITEM_IS_EQUIPPED)
            return slot;
        if (item_weapon_kind(ctx, item) == 6 && guest_call(ctx, SHEET_UnitCanItemEquip, unit, item, 1u, 1u) != 0)
            return slot;
    }
    return -1;
}

RECOMP_OVERRIDE(0x0052B728) {
    FE_ENTRY(0x0052B728, unit_category, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052EFE8) {
    FE_ENTRY(0x0052EFE8, unit_equipped_item, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003D5FB0) {
    FE_ENTRY(0x003D5FB0, unit_equipped_item_mutable, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052DC44) {
    FE_ENTRY(0x0052DC44, unit_shown_level, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052BBCC) {
    FE_ENTRY(0x0052BBCC, unit_low_level, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052E594) {
    FE_ENTRY(0x0052E594, unit_item_count, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00534474) {
    FE_ENTRY(0x00534474, unit_range_min, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052DC90) {
    FE_ENTRY(0x0052DC90, unit_may_not_attack, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x00533A80) {
    FE_ENTRY(0x00533A80, unit_is_unique, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052F234) {
    FE_ENTRY(0x0052F234, unit_is_special_battle, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052C61C) {
    FE_ENTRY(0x0052C61C, unit_is_invisible, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052AE20) {
    FE_ENTRY(0x0052AE20, unit_can_be_captured, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052F474) {
    FE_ENTRY(0x0052F474, unit_held_item_index, FE_ARG(0));
}
