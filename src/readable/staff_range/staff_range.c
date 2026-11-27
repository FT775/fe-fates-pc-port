/* What a staff does (Fates class Unit). Plain-language description:
   docs/STAFF_RANGE.md.

   - unit_rod_heal_power: how many HP a healing staff restores.
   - unit_status_staff_hit: the hit of a status staff (a staff that hinders a
     foe).
   - unit_status_staff_avoid: how well a unit resists a status staff.

   All three are readers: they store nothing of the game's. Heal fills two
   one-time caches of its own the first time; the stat getters and the exp
   limit fill theirs. The readable code gives up while any cache it may need is
   cold, before reading anything else. The one store it makes is guest_call5's
   fifth argument word in the dead stack below sp (docs/READABLE.md 17), where
   the game's own call puts the same word.

   The longest range (Unit::GetRangeO) of the batch row already has an override
   (unit_range_max, item batch); see staff_range.h.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/staff_range/tests/staff_range_diff.py. */

#include "staff_range.h"

static int exp_limit_caches_ready(Context *ctx) {
    return fe_static_ready(ctx, S_SrExpLimitGuardA) && fe_static_ready(ctx, S_SrExpLimitGuardB) &&
           fe_static_ready(ctx, S_SrExpLimitGuardC);
}

/* One of the unit's stats as the staff formulas ask it: no item given (heal,
   hit) or the staff (avoid), with the extras, with the loss, rally kind 0. */
static int32_t staff_stat(Context *ctx, gaddr getter, gaddr unit, gaddr item) {
    return (int32_t)guest_call5(ctx, getter, unit, item, SR_WITH_EXTRAS, SR_WITH_LOSS, SR_RALLY_NONE);
}

/* The staff rank bonus: the unit's staff exp, capped at its staff exp limit,
   gives a rank (WeaponLevel::GetLevel); the staff kind's WeaponBonus row holds
   a pair of signed bytes per rank, the might first and the hit second. The
   calls in the game's order: WeaponBonus::Get, GetWeaponExpLimit,
   WeaponLevel::Get, GetLevel. */
static int32_t staff_rank_bonus(Context *ctx, gaddr unit, uint32_t column) {
    gaddr bonus = guest_call1(ctx, SR_WeaponBonusGet, SR_STAFF_KIND);
    int32_t exp = guest_u8(ctx, unit + SR_UNIT_STAFF_EXP);
    int32_t limit = (int32_t)guest_call2(ctx, SR_UnitGetWeaponExpLimit, unit, SR_STAFF_KIND);
    int32_t capped = limit < exp ? limit : exp;
    gaddr levels = guest_call(ctx, SR_WeaponLevelGet, 0u, 0u, 0u, 0u);
    int32_t rank = (int32_t)guest_call2(ctx, SR_WeaponLevelGetLevel, levels, (uint32_t)capped);
    return guest_s8(ctx, bonus + ((gaddr)rank << 1) + column);
}

/* How many HP a staff heals:
     the staff's might (its record's +0x1F)
   + a third of the healer's magic (rounded toward zero) when the staff has the
     item flag "effect + magic / 3"
   + the staff rank bonus (the might byte)
   then half again (rounded down) when the healed unit (target, may be 0) has
   the cached skill.
   Guest function: 0x0052F008 Unit::GetRodHealPower(const unit::Item*,const Unit*) const. */
int32_t unit_rod_heal_power(Context *ctx, gaddr unit, gaddr item, gaddr target) {
    if (!fe_static_ready(ctx, S_SrHealSkillGuard) || !fe_static_ready(ctx, S_SrHealMagicGuard) ||
        !exp_limit_caches_ready(ctx) || !unit_stat_caches_ready(ctx, SR_STAT_MAG))
        return (int32_t)fe_use_original(ctx);
    gaddr record = guest_call1(ctx, SR_ItemToData, item);
    int32_t heal = READ_FIELD(ctx, ItemData, record, might);
    if (READ_FIELD(ctx, ItemData, record, flags) & guest_u64(ctx, S_SrHealMagicMask))
        heal = fe_add32(heal, staff_stat(ctx, SR_UnitGetPowImpl, unit, 0u) / 3);
    heal = fe_add32(heal, staff_rank_bonus(ctx, unit, SR_RANK_COLUMN_MIGHT));
    if (target != 0 &&
        guest_call2(ctx, SR_UnitIsEquipSkill, target, (uint32_t)(int32_t)guest_s16(ctx, S_SrHealSkill)) != 0)
        heal = fe_add32(heal, fe_asr(heal, 1));
    return heal;
}

/* The hit of a status staff, at least 0; no staff (item 0) gives 0:
     the item's hit (unit::Item::GetHit) + the class's hit (Job +0x4C)
   + magic + skill (both with no item given)
   + the staff rank bonus (the hit byte).
   Guest function: 0x0053135C Unit::GetInterferenceRodHit(const unit::Item*) const. */
int32_t unit_status_staff_hit(Context *ctx, gaddr unit, gaddr item) {
    if (item == 0)
        return 0; /* the game answers before asking anything */
    if (!unit_stat_caches_ready(ctx, SR_STAT_MAG) || !unit_stat_caches_ready(ctx, SR_STAT_SKL) ||
        !exp_limit_caches_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    int32_t item_hit = (int32_t)guest_call1(ctx, SR_ItemGetHit, item);
    int32_t hit = fe_add32(READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), hit), item_hit);
    int32_t magic = staff_stat(ctx, SR_UnitGetPowImpl, unit, 0u);
    int32_t skill = staff_stat(ctx, SR_UnitGetTechImpl, unit, 0u);
    hit = fe_add32(fe_add32(skill, magic), hit);
    hit = fe_add32(staff_rank_bonus(ctx, unit, SR_RANK_COLUMN_HIT), hit);
    return hit < 0 ? 0 : hit;
}

/* How well a unit resists a status staff, at least 0:
   (3 x resistance + luck) / 2, rounded down; both stats with the staff given.
   Guest function: 0x00531D30 Unit::GetInterferenceRodAvoid(const unit::Item*) const. */
int32_t unit_status_staff_avoid(Context *ctx, gaddr unit, gaddr item) {
    if (!fe_static_ready(ctx, S_SrResGuard0) || !fe_static_ready(ctx, S_SrResGuard1) ||
        !fe_static_ready(ctx, S_SrResGuard2) || !unit_stat_caches_ready(ctx, SR_STAT_LCK))
        return (int32_t)fe_use_original(ctx);
    int32_t resistance = staff_stat(ctx, SR_UnitGetMdefImpl, unit, item);
    int32_t luck = staff_stat(ctx, SR_UnitGetLuckImpl, unit, item);
    int32_t triple = fe_add32(resistance, (int32_t)((uint32_t)resistance << 1));
    int32_t avoid = fe_asr(fe_add32(luck, triple), 1);
    return avoid < 0 ? 0 : avoid;
}

RECOMP_OVERRIDE(0x0052F008) {
    FE_ENTRY(0x0052F008, unit_rod_heal_power, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x0053135C) {
    FE_ENTRY(0x0053135C, unit_status_staff_hit, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00531D30) {
    FE_ENTRY(0x00531D30, unit_status_staff_avoid, FE_ARG(0), FE_ARG(1));
}
