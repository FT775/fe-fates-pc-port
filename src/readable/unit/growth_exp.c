/* Experience amounts and level limits (Fates class Unit, ExpTable, Job,
   map::Situation). Plain-language description: docs/GROWTH.md section 4.

   Every amount starts from the two units' "experience levels"
   (Unit::GetLevelForCalculateExp: level + Unit.exp_level_offset, + 6 with one
   PersonFlag bit, clamped 1 .. 40) and reads one row of an experience table;
   the row is the difficulty (GameUserData.difficulty). The tables and their
   index rules: docs/TABLES.md ExpTableHeader .. ExpSupport.

   ExpMode (the second argument; the symbol map names the type, not its
   values): 2 and 3 replace the other unit's level by the lower of the two
   levels minus 2 (clamped 1 .. 38) and give 0 when the other unit has no
   weapon equipped; 3 also halves the amount. Mode 0/1 change nothing.

   The game asks GameUserData::Get() for the difficulty each time; the readable
   code reads G_GameUserData each time (the same bytes). Where the game calls
   a function with a readable override (the ExpTable getters, the experience
   level, Job::GetLimitLevel, GetItemIndexEquipped, GetExpDamage) the readable
   code calls it through the guest, in the same order (F-018).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/unit/tests/growth_diff.py. */

#include "growth.h"

static int32_t clamp(int32_t v, int32_t lo, int32_t hi) {
    if (v < lo)
        return lo;
    return v > hi ? hi : v;
}

static int32_t difficulty(Context *ctx) {
    return READ_FIELD(ctx, GameUserData, guest_ptr(ctx, G_GameUserData), difficulty);
}

static int32_t exp_level_of(Context *ctx, gaddr unit) {
    return (int32_t)guest_call1(ctx, GROW_UnitExpLevel, unit);
}

/* the other unit's level as the amount uses it (modes 2 and 3: the lower of
   both levels minus 2, clamped 1 .. 38) */
static int32_t target_level(int32_t mode, int32_t mine, int32_t theirs) {
    if (mode != 2 && mode != GROW_EXP_MODE_HALF)
        return theirs;
    int32_t a = fe_add32(theirs, -2), b = fe_add32(mine, -2);
    return clamp(b >= a ? a : b, 1, 38);
}

/* a 64-bit PersonFlag word of a unit, its Person and its Job, ORed */
static uint64_t unit_flags(Context *ctx, gaddr unit) {
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    uint64_t f = READ_FIELD(ctx, Unit, unit, private_flags) | READ_FIELD(ctx, PersonData, person, flags);
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    return f | READ_FIELD(ctx, JobData, job, flags);
}

static gaddr exp_row(Context *ctx, gaddr header_field, int32_t difficulty, uint32_t stride) {
    gaddr header = guest_ptr(ctx, G_ExpTable);
    return guest_ptr(ctx, header + header_field) + (gaddr)difficulty * stride;
}

/* The six ExpTable getters: the row of one sub-table for a difficulty.
   Guest functions: 0x004E6368 ExpTable::GetBattle(int), 0x004E6314
   GetBattleThreshold(int), 0x004E634C GetDance(int), 0x004E62F8
   GetSupportDecline(int), 0x004E62C4 GetRodDecline(int), 0x004E62E0
   GetRodHighDecline(int). */
gaddr exp_table_battle(Context *ctx, int32_t d) {
    return exp_row(ctx, offsetof(ExpTableHeaderData, battle), d, 0x48u);
}
gaddr exp_table_battle_threshold(Context *ctx, int32_t d) {
    return exp_row(ctx, offsetof(ExpTableHeaderData, battle_threshold), d, 0x18u);
}
gaddr exp_table_dance(Context *ctx, int32_t d) {
    return exp_row(ctx, offsetof(ExpTableHeaderData, dance), d, 0x28u);
}
gaddr exp_table_support_decline(Context *ctx, int32_t d) {
    return exp_row(ctx, offsetof(ExpTableHeaderData, support_decline), d, 0x28u);
}
gaddr exp_table_rod_decline(Context *ctx, int32_t d) {
    return exp_row(ctx, offsetof(ExpTableHeaderData, rod_decline), d, 0x28u);
}
gaddr exp_table_rod_high_decline(Context *ctx, int32_t d) {
    return exp_row(ctx, offsetof(ExpTableHeaderData, rod_high_decline), d, 4u);
}

/* The level a unit counts as for experience: level + Unit.exp_level_offset,
   + 6 when the unit, its Person or its Job has one PersonFlag bit; 1 .. 40.
   Guest function: 0x00531F24 Unit::GetLevelForCalculateExp(void) const. */
int32_t unit_exp_level(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, S_ExpLevelGuard))
        return (int32_t)fe_use_original(ctx);
    int32_t level = fe_add32(READ_FIELD(ctx, Unit, unit, level), READ_FIELD(ctx, Unit, unit, exp_level_offset));
    uint64_t mask = guest_u64(ctx, S_ExpLevelMask);
    if (unit_flags(ctx, unit) & mask)
        level = fe_add32(level, 6);
    return clamp(level, 1, 40);
}

/* Experience for hitting (damaging) the other unit: ExpBattle.damage at
   (other's level - own level + 10, clamped 0 .. 33), at least
   ExpBattleFloor.damage_min at (other's level - 31, clamped 0 .. 9); halved in
   mode 3; 0 in modes 2/3 when the other unit has no weapon equipped; on
   difficulty 2 and above, minus the other unit's exp_decline - 2 (not below
   0), never below 0.
   Guest function: 0x0052D418 Unit::GetExpDamage(Unit::ExpMode::Type,const Unit*) const. */
int32_t unit_exp_damage(Context *ctx, gaddr unit, int32_t mode, gaddr other) {
    if (!fe_static_ready(ctx, S_ExpLevelGuard))  /* the cache the two level calls need: ask first */
        return (int32_t)fe_use_original(ctx);
    int32_t mine = exp_level_of(ctx, unit);
    int32_t theirs = target_level(mode, mine, exp_level_of(ctx, other));
    gaddr row = guest_call1(ctx, GROW_ExpGetBattle, difficulty(ctx));
    int32_t v = guest_s8(ctx, row + (gaddr)clamp(fe_add32(fe_add32(theirs, -mine), 10), 0, 33));
    gaddr floor_row = guest_call1(ctx, GROW_ExpGetBattleThreshold, difficulty(ctx));
    int32_t floor = guest_s8(ctx, floor_row + (gaddr)clamp(fe_add32(theirs, -31), 0, 9));
    if (v < floor)
        v = floor;
    if (mode == GROW_EXP_MODE_HALF)
        v = fe_asr(v, 1);
    if (other != 0 && (mode == 2 || mode == GROW_EXP_MODE_HALF) &&
        (int32_t)guest_call1(ctx, GROW_UnitEquippedIndex, other) < 0)
        v = 0;
    if ((uint32_t)difficulty(ctx) >= 2) {
        int32_t decline = fe_add32(READ_FIELD(ctx, Unit, other, exp_decline), -2);
        v = fe_add32(v, -(decline < 0 ? 0 : decline));
        if (v < 0)
            v = 0;
    }
    return v;
}

/* The pair-up partner's share of damage experience: half of GetExpDamage's
   amount (arithmetic shift) when it is 2 or more.
   Guest function: 0x0052F274 Unit::GetDualExpDamage(Unit::ExpMode::Type,const Unit*) const. */
int32_t unit_dual_exp_damage(Context *ctx, gaddr unit, int32_t mode, gaddr other) {
    if (!fe_static_ready(ctx, S_ExpLevelGuard))  /* the cache GetExpDamage's level calls need: ask first */
        return (int32_t)fe_use_original(ctx);
    int32_t v = (int32_t)guest_call3(ctx, GROW_UnitGetExpDamage, unit, (uint32_t)mode, other);
    return v >= 2 ? fe_asr(v, 1) : v;
}

/* Experience for defeating the other unit: ExpBattle.defeat at (other's level
   - own level + 10, clamped 0 .. 33), at least ExpBattleFloor.defeat_min;
   that base b, for a boss (the bool): b + b/2 below 20, else b + 10; then by
   the other unit's PersonFlag bits (unit | Person | Job): masks 1, 2 or 4 add
   b, at most 20; mask 3 takes (b + 1) / 2 off when b >= 2; mask 4 makes it at
   least 20. Halved in mode 3, 0 in modes 2/3 without an equipped weapon.
   Guest function: 0x0052E184 Unit::GetExpDestroy(Unit::ExpMode::Type,const Unit*,bool) const. */
int32_t unit_exp_destroy(Context *ctx, gaddr unit, int32_t mode, gaddr other, uint32_t boss) {
    if (!fe_static_ready(ctx, S_DestroyGuard1) || !fe_static_ready(ctx, S_DestroyGuard2) ||
        !fe_static_ready(ctx, S_DestroyGuard3) || !fe_static_ready(ctx, S_DestroyGuard4) ||
        !fe_static_ready(ctx, S_ExpLevelGuard))
        return (int32_t)fe_use_original(ctx);
    int32_t mine = exp_level_of(ctx, unit);
    int32_t theirs = target_level(mode, mine, exp_level_of(ctx, other));
    gaddr row = guest_call1(ctx, GROW_ExpGetBattle, difficulty(ctx));
    int32_t base = guest_s8(ctx, row + offsetof(ExpBattleData, defeat) +
                                     (gaddr)clamp(fe_add32(fe_add32(theirs, -mine), 10), 0, 33));
    gaddr floor_row = guest_call1(ctx, GROW_ExpGetBattleThreshold, difficulty(ctx));
    int32_t floor = guest_s8(ctx, floor_row + offsetof(ExpBattleFloorData, defeat_min) +
                                      (gaddr)clamp(fe_add32(theirs, -31), 0, 9));
    if (base < floor)
        base = floor;
    int32_t v = base;
    if (boss != 0)  /* the game compares the whole word */
        v = base < 20 ? fe_add32(base, fe_asr(base, 1)) : fe_add32(base, 10);
    uint64_t m4 = guest_u64(ctx, S_DestroyMask4);
    uint64_t m124 = guest_u64(ctx, S_DestroyMask1) | guest_u64(ctx, S_DestroyMask2) | m4;
    if (unit_flags(ctx, other) & m124)
        v = fe_add32(v, base < 20 ? base : 20);
    uint64_t m3 = guest_u64(ctx, S_DestroyMask3);
    if ((unit_flags(ctx, other) & m3) && base >= 2)
        v = fe_add32(v, -(int32_t)((uint32_t)fe_add32(base, 1) >> 1));
    if ((unit_flags(ctx, other) & m4) && v < 20)
        v = 20;
    if (mode == GROW_EXP_MODE_HALF)
        v = fe_asr(v, 1);
    if (other != 0 && (mode == 2 || mode == GROW_EXP_MODE_HALF) &&
        (int32_t)guest_call1(ctx, GROW_UnitEquippedIndex, other) < 0)
        v = 0;
    return v;
}

/* Experience for dancing (singing) for the other unit: ExpDance at (own
   level - 1, clamped 0 .. 39), at most 10 in modes 2/3, + ExpSupport at
   (other's level - own level + 39, clamped 0 .. 39); halved in mode 3; at
   least 1.
   Guest function: 0x0052BAD0 Unit::GetExpDance(Unit::ExpMode::Type,const Unit*) const. */
int32_t unit_exp_dance(Context *ctx, gaddr unit, int32_t mode, gaddr other) {
    if (!fe_static_ready(ctx, S_ExpLevelGuard))
        return (int32_t)fe_use_original(ctx);
    int32_t mine = exp_level_of(ctx, unit);
    int32_t theirs = target_level(mode, mine, exp_level_of(ctx, other));
    gaddr row = guest_call1(ctx, GROW_ExpGetDance, difficulty(ctx));
    int32_t dance = guest_s8(ctx, row + (gaddr)clamp(fe_add32(mine, -1), 0, 39));
    if ((mode == 2 || mode == GROW_EXP_MODE_HALF) && dance > 10)
        dance = 10;
    gaddr gap_row = guest_call1(ctx, GROW_ExpGetSupportDecline, difficulty(ctx));
    int32_t v = fe_add32(guest_s8(ctx, gap_row + (gaddr)clamp(fe_add32(fe_add32(theirs, -mine), 39), 0, 39)), dance);
    if (mode == GROW_EXP_MODE_HALF)
        v = fe_asr(v, 1);
    return v < 1 ? 1 : v;
}

/* Experience for using a staff (on the other unit when it is given):
   Item.staff_exp (at most 30 in modes 2/3) + ExpRod at (own level - 1,
   clamped 0 .. 39), + ExpRodHigh when the class can carry any weapon but
   staves (Job.max_weapon_exp of a kind other than staff not 0), + ExpSupport
   at the level gap when there is another unit; halved in mode 3; at least 1.
   Guest function: 0x005342F4 Unit::GetExpRod(Unit::ExpMode::Type,const unit::Item*,const Unit*) const. */
int32_t unit_exp_rod(Context *ctx, gaddr unit, int32_t mode, gaddr item, gaddr other) {
    if (!fe_static_ready(ctx, S_ExpLevelGuard))
        return (int32_t)fe_use_original(ctx);
    gaddr data = guest_call1(ctx, GROW_ItemToData, item);
    int32_t mine = exp_level_of(ctx, unit);
    int32_t v = READ_FIELD(ctx, ItemData, data, staff_exp);
    if ((mode == 2 || mode == GROW_EXP_MODE_HALF) && v > 30)
        v = 30;
    gaddr row = guest_call1(ctx, GROW_ExpGetRodDecline, difficulty(ctx));
    v = fe_add32(v, guest_s8(ctx, row + (gaddr)clamp(fe_add32(mine, -1), 0, 39)));
    for (uint32_t kind = 0; kind < 8; kind++) {
        if (kind == 6)  /* staff */
            continue;
        gaddr job = READ_FIELD(ctx, Unit, unit, job);  /* read for every kind, as the game does */
        if (guest_u8(ctx, FIELD_ADDR(JobData, job, max_weapon_exp) + kind) != 0) {
            gaddr high = guest_call1(ctx, GROW_ExpGetRodHighDecline, difficulty(ctx));
            v = fe_add32(v, guest_s8(ctx, high));
            break;
        }
    }
    if (other != 0) {
        int32_t theirs = target_level(mode, mine, exp_level_of(ctx, other));
        gaddr gap_row = guest_call1(ctx, GROW_ExpGetSupportDecline, difficulty(ctx));
        v = fe_add32(v, guest_s8(ctx, gap_row + (gaddr)clamp(fe_add32(fe_add32(theirs, -mine), 39), 0, 39)));
    }
    if (mode == GROW_EXP_MODE_HALF)
        v = fe_asr(v, 1);
    return v < 1 ? 1 : v;
}

/* the class level limit, raised by Unit.level_limit_raises steps when it is
   above 20 or the class is promoted (Job::IsHigh); the job word is read again
   before IsHigh, as the game does */
static int32_t raised_limit(Context *ctx, gaddr unit) {
    int32_t limit = (int32_t)guest_call1(ctx, GROW_JobGetLimitLevel, READ_FIELD(ctx, Unit, unit, job));
    if (limit > 20 || guest_call1(ctx, GROW_JobIsHigh, READ_FIELD(ctx, Unit, unit, job)) != 0)
        limit = fe_add32(limit, (int32_t)((uint32_t)READ_FIELD(ctx, Unit, unit, level_limit_raises) *
                                          (uint32_t)guest_s32(ctx, S_LevelLimitStep)));
    return limit;
}

static int job_limit_caches_ready(Context *ctx) {
    return fe_static_ready(ctx, S_JobLimitGuard1) && fe_static_ready(ctx, S_JobHighGuard);
}

/* A unit's level limit (the class limit, raised as above).
   Guest function: 0x0052E5EC Unit::GetLimitLevel(void) const. */
int32_t unit_level_limit(Context *ctx, gaddr unit) {
    if (!job_limit_caches_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    return raised_limit(ctx, unit);
}

/* The experience a unit can take: at most 100; 0 at or above the level limit;
   on the last level below the limit, at most what fills the bar to 100.
   Guest function: 0x0052D34C Unit::ExpNormalize(int) const. */
int32_t unit_exp_normalize(Context *ctx, gaddr unit, int32_t amount) {
    if (!job_limit_caches_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    if (amount > 100)
        amount = 100;
    if ((int32_t)READ_FIELD(ctx, Unit, unit, level) >= raised_limit(ctx, unit))
        return 0;
    if (fe_add32(READ_FIELD(ctx, Unit, unit, exp), amount) >= 100) {
        int32_t limit = raised_limit(ctx, unit);
        if (limit <= fe_add32(READ_FIELD(ctx, Unit, unit, level), 1)) {
            int32_t room = 100 - (int32_t)READ_FIELD(ctx, Unit, unit, exp);
            if (room < amount)
                amount = room;
        }
    }
    return amount;
}

/* A class's level limit: 101 for one class found by name, 20 for a promoted
   class or one that has a promotion (Job.promotion[0]), else 40.
   Guest function: 0x005242F0 Job::GetLimitLevel(void) const. */
int32_t job_level_limit(Context *ctx, gaddr job) {
    if (!fe_static_ready(ctx, S_JobLimitGuard1))
        return (int32_t)fe_use_original(ctx);
    if (job == guest_ptr(ctx, S_JobLimitSpecial))
        return 101;
    if (!fe_static_ready(ctx, S_JobHighGuard))
        return (int32_t)fe_use_original(ctx);
    if ((guest_u64(ctx, S_JobHighMask) & READ_FIELD(ctx, JobData, job, flags)) != 0)
        return 20;
    return READ_FIELD(ctx, JobData, job, promotion[0]) != 0 ? 20 : 40;
}

/* Whether a force (army) may gain experience on this map: only forces 0 .. 2,
   never when Situation.no_exp is 1, else when that force's byte is 1.
   Guest function: 0x00527D90 map::Situation::CanGainExp(Force::Type) const. */
uint32_t situation_can_gain_exp(Context *ctx, gaddr situation, uint32_t force) {
    if (force >= 3)
        return 0;
    if (READ_FIELD(ctx, Situation, situation, no_exp) == 1)
        return 0;
    return guest_u8(ctx, situation + force) == 1 ? 1u : 0u;
}

RECOMP_OVERRIDE(0x004E6368) {
    FE_ENTRY(0x004E6368, exp_table_battle, FE_ARG_S(0));
}

RECOMP_OVERRIDE(0x004E6314) {
    FE_ENTRY(0x004E6314, exp_table_battle_threshold, FE_ARG_S(0));
}

RECOMP_OVERRIDE(0x004E634C) {
    FE_ENTRY(0x004E634C, exp_table_dance, FE_ARG_S(0));
}

RECOMP_OVERRIDE(0x004E62F8) {
    FE_ENTRY(0x004E62F8, exp_table_support_decline, FE_ARG_S(0));
}

RECOMP_OVERRIDE(0x004E62C4) {
    FE_ENTRY(0x004E62C4, exp_table_rod_decline, FE_ARG_S(0));
}

RECOMP_OVERRIDE(0x004E62E0) {
    FE_ENTRY(0x004E62E0, exp_table_rod_high_decline, FE_ARG_S(0));
}

RECOMP_OVERRIDE(0x00531F24) {
    FE_ENTRY(0x00531F24, unit_exp_level, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052D418) {
    FE_ENTRY(0x0052D418, unit_exp_damage, FE_ARG(0), FE_ARG_S(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x0052F274) {
    FE_ENTRY(0x0052F274, unit_dual_exp_damage, FE_ARG(0), FE_ARG_S(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x0052E184) {
    FE_ENTRY(0x0052E184, unit_exp_destroy, FE_ARG(0), FE_ARG_S(1), FE_ARG(2), FE_ARG(3));
}

RECOMP_OVERRIDE(0x0052BAD0) {
    FE_ENTRY(0x0052BAD0, unit_exp_dance, FE_ARG(0), FE_ARG_S(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x005342F4) {
    FE_ENTRY(0x005342F4, unit_exp_rod, FE_ARG(0), FE_ARG_S(1), FE_ARG(2), FE_ARG(3));
}

RECOMP_OVERRIDE(0x0052D34C) {
    FE_ENTRY(0x0052D34C, unit_exp_normalize, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0052E5EC) {
    FE_ENTRY(0x0052E5EC, unit_level_limit, FE_ARG(0));
}

RECOMP_OVERRIDE(0x005242F0) {
    FE_ENTRY(0x005242F0, job_level_limit, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00527D90) {
    FE_ENTRY(0x00527D90, situation_can_gain_exp, FE_ARG(0), FE_ARG(1));
}
