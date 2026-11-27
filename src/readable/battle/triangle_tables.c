/* Weapon ranks and the rule tables behind the weapon triangle (Fates classes
   ItemSubKind, WeaponLevel, WeaponBonus, WeaponInteract, Unit). Plain-language
   description: docs/TRIANGLE.md; the table layouts: docs/TABLES.md.

   - ItemSubKind: one 16-byte record per weapon sub-kind (Item.weapon_kind picks
     it); its byte +0x1 is the weapon kind (ItemKind: sword, lance, axe, dagger,
     bow, tome, staff, stone) that the triangle and the rank bonus use.
   - WeaponLevel: six exp thresholds, S first. A unit's rank in a kind is the
     first threshold its (capped) weapon exp reaches; none reached = 6.
   - WeaponBonus: per kind, an (attack, hit) pair per rank, added by
     Unit::GetAttack / Unit::GetHit when asked to.
   - WeaponInteract: an (attack, hit) pair per rank for the triangle, then the
     8x8 matrix of +1 / -1 / 0 (attacker kind row, defender kind column).
   - Unit weapon exp: one byte per kind (Unit +0xE8), capped by the class's
     limit (Job +0x44), with two exceptions found by flag bits (one-time caches).

   Every function here only reads guest memory; the one guest call
   (unit::Item::ToData) only reads. The two helpers return the rank-bonus term
   of Unit::GetAttack / GetHit; those functions also call stat functions that
   are not rewritten, so they stay game code.

   Status: UNVERIFIED (below shadow-clean). Each function agrees with the
   original ARM code on generated inputs in the host differential test
   (src/readable/battle/tests/triangle_diff.py); that is not a tier-2 or shadow
   result. */

#include "triangle.h"

/* The record of weapon sub-kind `index` (16 bytes each; no range check, as in the game).
   Guest function: 0x0019B97C ItemSubKind::Get(int). */
gaddr item_subkind_record(Context *ctx, int32_t index) {
    return guest_ptr(ctx, G_ItemSubKindTable) + (gaddr)index * (gaddr)sizeof(ItemSubKindData);
}

/* The rank-bonus row of weapon kind `kind` (12 bytes each; no range check).
   Guest function: 0x001A8090 WeaponBonus::Get(ItemKind::Type). */
gaddr weapon_bonus_record(Context *ctx, uint32_t kind) {
    return guest_ptr(ctx, G_WeaponBonus) + kind * (gaddr)sizeof(WeaponBonusData);
}

/* Guest function: 0x001A80D4 WeaponLevel::Get(void): the rank threshold record. */
gaddr weapon_level_record(Context *ctx) {
    return guest_ptr(ctx, G_WeaponLevel);
}

/* Guest function: 0x001D77B8 WeaponInteract::Get(void): the triangle record. */
gaddr weapon_interact_record(Context *ctx) {
    return guest_ptr(ctx, G_WeaponInteract);
}

/* The rank reached with `exp` weapon exp: the first of the six thresholds (S, A,
   B, C, D, E) that exp reaches, as 0 .. 5; WEAPON_RANK_NONE (6) when it reaches
   none. Signed comparison, as in the game.
   Guest function: 0x005090A4 WeaponLevel::GetLevel(int) const. */
int32_t weapon_rank_of_exp(Context *ctx, gaddr level, int32_t exp) {
    for (int32_t rank = 0; rank < WEAPON_RANK_NONE; rank++) {
        int32_t threshold = guest_u8(ctx, FIELD_ADDR(WeaponLevelData, level, threshold) + (gaddr)rank);
        if (threshold <= exp)
            return rank;
    }
    return WEAPON_RANK_NONE;
}

/* The PersonFlag words of a unit, its Person and its class, ORed. */
static uint64_t unit_person_flags(Context *ctx, gaddr unit) {
    return READ_FIELD(ctx, Unit, unit, private_flags) |
           READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), flags) |
           READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), flags);
}

/* The most weapon exp this unit can hold in a kind: its class's limit
   (Job.max_weapon_exp), except
   - stones (kind 7): 0 when the unit, its Person or its class carries one flag bit;
   - staves (kind 6): at least the rank B threshold when they carry another one.
   The game fills three one-time caches at entry; while any is cold the readable
   code gives up.
   Guest function: 0x0052F824 Unit::GetWeaponExpLimit(ItemKind::Type) const. */
int32_t unit_weapon_exp_limit(Context *ctx, gaddr unit, uint32_t kind) {
    if (!fe_static_ready(ctx, S_ExpLimitGuardA) || !fe_static_ready(ctx, S_ExpLimitGuardB) ||
        !fe_static_ready(ctx, S_ExpLimitGuardC))
        return (int32_t)fe_use_original(ctx);
    if (kind == TRIANGLE_KIND_STONE && (unit_person_flags(ctx, unit) & guest_u64(ctx, S_StoneLimitMask)) != 0)
        return 0;
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    int32_t limit = guest_u8(ctx, FIELD_ADDR(JobData, job, max_weapon_exp) + kind);
    if (kind == TRIANGLE_KIND_STAFF && (unit_person_flags(ctx, unit) & guest_u64(ctx, S_StaffLimitMask)) != 0) {
        int32_t floor = guest_s32(ctx, S_StaffLimitFloor);
        if (limit < floor)
            limit = floor;
    }
    return limit;
}

/* The unit's weapon exp in a kind (Unit.weapon_exp), capped at its limit.
   Guest function: 0x0052DC54 Unit::GetWeaponExp(ItemKind::Type) const. */
int32_t unit_weapon_exp(Context *ctx, gaddr unit, uint32_t kind) {
    int32_t limit = unit_weapon_exp_limit(ctx, unit, kind);
    if (fe_gave_up(ctx))
        return 0;
    int32_t exp = guest_u8(ctx, FIELD_ADDR(Unit, unit, weapon_exp) + kind);
    return limit < exp ? limit : exp;
}

/* The weapon kind (ItemKind, signed byte) of a unit::Item: its record's
   sub-kind, then that sub-kind's kind. */
int32_t item_weapon_kind(Context *ctx, gaddr item) {
    gaddr data = guest_call1(ctx, GUEST_ItemToData, item);
    gaddr sub = item_subkind_record(ctx, READ_FIELD(ctx, ItemData, data, weapon_kind));
    return guest_s8(ctx, FIELD_ADDR(ItemSubKindData, sub, kind));
}

/* The weapon-rank bonus of a unit with a weapon: for kinds below 8, the
   WeaponBonus row of that kind at the unit's rank in it (rank from its capped
   weapon exp), column attack or hit; 0 for other kinds. A negative kind is not
   refused (the game compares signed). */
static int32_t weapon_rank_bonus(Context *ctx, gaddr unit, gaddr item, int column) {
    int32_t kind = item_weapon_kind(ctx, item);
    if (kind >= TRIANGLE_KINDS)
        return 0;
    gaddr row = weapon_bonus_record(ctx, (uint32_t)kind);
    int32_t exp = unit_weapon_exp(ctx, unit, (uint32_t)kind);
    if (fe_gave_up(ctx))
        return 0;
    int32_t rank = weapon_rank_of_exp(ctx, weapon_level_record(ctx), exp);
    return guest_s8(ctx, row + (gaddr)rank * 2u + (gaddr)column);
}

/* What Unit::GetAttack adds for weapon rank when its bool argument is set (the
   fight passes 0 there for a side at a triangle disadvantage).
   Guest function: helper of 0x00534188 Unit::GetAttack(const unit::Item*,bool) const
   (the region 0x005341FC .. 0x005342A0). */
int32_t unit_weapon_rank_attack(Context *ctx, gaddr unit, gaddr item) {
    return weapon_rank_bonus(ctx, unit, item, RANK_COLUMN_ATTACK);
}

/* What Unit::GetHit adds for weapon rank when its bool argument is set.
   Guest function: helper of 0x00532DC4 Unit::GetHit(const unit::Item*,bool) const
   (the region 0x00532F2C .. 0x00532FD4). */
int32_t unit_weapon_rank_hit(Context *ctx, gaddr unit, gaddr item) {
    return weapon_rank_bonus(ctx, unit, item, RANK_COLUMN_HIT);
}

RECOMP_OVERRIDE(0x0019B97C) {
    FE_ENTRY(0x0019B97C, item_subkind_record, FE_ARG_S(0));
}

RECOMP_OVERRIDE(0x001A8090) {
    FE_ENTRY(0x001A8090, weapon_bonus_record, FE_ARG(0));
}

RECOMP_OVERRIDE(0x001A80D4) {
    FE_ENTRY0(0x001A80D4, weapon_level_record);
}

RECOMP_OVERRIDE(0x001D77B8) {
    FE_ENTRY0(0x001D77B8, weapon_interact_record);
}

RECOMP_OVERRIDE(0x005090A4) {
    FE_ENTRY(0x005090A4, weapon_rank_of_exp, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0052F824) {
    FE_ENTRY(0x0052F824, unit_weapon_exp_limit, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052DC54) {
    FE_ENTRY(0x0052DC54, unit_weapon_exp, FE_ARG(0), FE_ARG(1));
}
