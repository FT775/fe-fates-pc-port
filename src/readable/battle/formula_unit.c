/* A unit's battle numbers (Fates class Unit): attack, hit, avoid, critical,
   critical avoid and the two follow-up speeds. Plain-language description:
   docs/FORMULAS.md section 3.

   These are what the status window shows and what a fight starts from
   (map::BattleInfo::Side::CalculateDetail* add terrain, skills, stances and
   the weapon triangle on top; formula_forecast.c and docs/FORMULAS.md 4).

     attack   = weapon might (+forge) + Str (Mag for a magic weapon) [+ weapon-rank bonus]
     hit      = class hit + weapon hit (+forge) + (3 x Skl + Lck) / 2 [+ weapon-rank bonus] + personal +10/+20/+30
     avoid    = class avoid + (3 x Spd + Lck) / 2 + weapon avoid + personal -20/-10/+10/+20, -20 for one condition
     critical = weapon crit (+forge) + class crit (halved for most enemies) + (Skl - 4) / 2 (the last never below 0)
     crit avoid = class dodge + Lck / 2 + weapon dodge
     attack speed  = Spd + the weapon's speed modifier when attacking (never below 0)
     defense speed = Spd + the weapon's speed modifier when attacked (never below 0)

   Divisions are the game's: an arithmetic shift, i.e. rounded down. The stats
   are the readable getters of formula_stats.c (with the weapon, with extras,
   rally kind 0); the weapon-rank bonus uses triangle_tables.c's pieces.

   Every function only reads guest memory. Status: UNVERIFIED (below
   shadow-clean). Host differential test against the original ARM code:
   src/readable/battle/tests/formula_diff.py. */

#include "formulas.h"

static int32_t stat_of(Context *ctx, uint32_t stat, gaddr unit, gaddr item) {
    return unit_stat_value(ctx, stat, unit, item, 1u, 1u, 0);
}

/* The PersonFlag words of a unit, its Person and its class, ORed. */
static uint64_t unit_flag_words(Context *ctx, gaddr unit) {
    return READ_FIELD(ctx, Unit, unit, private_flags) |
           READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), flags) |
           READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), flags);
}

static int has_flag(Context *ctx, uint64_t words, gaddr mask) {
    return (words & guest_u64(ctx, mask)) != 0;
}

/* The unit::Item in slot `slot` (0 .. 4) of the unit, without a range check. */
static gaddr slot_item(gaddr unit, int32_t slot) {
    return FIELD_ADDR(Unit, unit, items) + (gaddr)slot * 4u;
}

/* The slot forms of GetHit / GetAvoid / GetCritical: -1 means the equipped
   weapon; a negative slot (or no equipped weapon) means no weapon. */
static gaddr slot_or_none(Context *ctx, gaddr unit, int32_t slot) {
    if (slot == -1)
        slot = unit_equipped_index(ctx, unit);
    return slot >= 0 ? slot_item(unit, slot) : 0;
}

/* The weapon kind (ItemKind, signed byte) of a unit::Item, looked up the way
   Unit::GetHit / GetAttack do it: unit::Item::ToData, then ItemSubKind::Get
   through the guest (the game calls it, so the readable code calls it too:
   the live shadow compare counts the callee calls, docs/DECISIONS.md F-018),
   then the record's byte +1. Same value and reads as item_weapon_kind
   (triangle_tables.c), which does the table step in C. */
static int32_t rank_weapon_kind(Context *ctx, gaddr item) {
    gaddr data = guest_call1(ctx, GUEST_ItemToData, item);
    if (fe_gave_up(ctx))
        return 0;
    gaddr sub = guest_call1(ctx, GUEST_ItemSubKindGet, (int32_t)READ_FIELD(ctx, ItemData, data, weapon_kind));
    if (fe_gave_up(ctx))
        return 0;
    return guest_s8(ctx, FIELD_ADDR(ItemSubKindData, sub, kind));
}

/* The weapon-rank bonus as Unit::GetHit / GetAttack compute it: the
   triangle batch's readable pieces (triangle_tables.c), in the game's order,
   with its three lookups of the weapon kind, each a ToData and an
   ItemSubKind::Get call as in the game (tier 2 counts the bytes read from
   unmapped memory and the live compare counts the calls, so both must be the
   game's). For kinds below 8: the WeaponBonus row of the kind at the unit's
   rank, column attack or hit. */
static int32_t weapon_rank_term(Context *ctx, gaddr unit, gaddr item, int column) {
    if (rank_weapon_kind(ctx, item) >= TRIANGLE_KINDS || fe_gave_up(ctx))
        return 0;
    int32_t row_kind = rank_weapon_kind(ctx, item);
    if (fe_gave_up(ctx))
        return 0;
    gaddr row = weapon_bonus_record(ctx, (uint32_t)row_kind);
    int32_t kind = rank_weapon_kind(ctx, item);
    if (fe_gave_up(ctx))
        return 0;
    int32_t exp = unit_weapon_exp(ctx, unit, (uint32_t)kind);
    if (fe_gave_up(ctx))
        return 0;
    int32_t rank = weapon_rank_of_exp(ctx, weapon_level_record(ctx), exp);
    return guest_s8(ctx, row + (gaddr)rank * 2u + (gaddr)column);
}

/* Give-up discipline. A readable function that gives up is replayed from the
   start by its original (fe_guest.h FE_ENTRY), and tier 2 counts every byte
   read from unmapped memory, so a give-up must come before any read but the
   guard words. Each function therefore asks first whether every one-time cache
   it may need is filled (its own, the stat getters', the weapon-exp limit's for
   the rank bonus), and gives up at once when one is cold. That is sometimes
   earlier than the game would reach the cache (it may never need it); giving up
   is always safe, the original then runs. */
static int exp_caches_ready(Context *ctx) {
    return fe_static_ready(ctx, S_ExpLimitGuardA) && fe_static_ready(ctx, S_ExpLimitGuardB) &&
           fe_static_ready(ctx, S_ExpLimitGuardC);
}

static int hit_ready(Context *ctx, int rank_bonus) {
    return fe_static_ready(ctx, S_HitGuard10) && fe_static_ready(ctx, S_HitGuard20) &&
           fe_static_ready(ctx, S_HitGuard30) && unit_stat_caches_ready(ctx, STAT_SKL) &&
           unit_stat_caches_ready(ctx, STAT_LCK) && (!rank_bonus || exp_caches_ready(ctx));
}

static int avoid_ready(Context *ctx) {
    return fe_static_ready(ctx, S_AvoidGuardM20) && fe_static_ready(ctx, S_AvoidGuardM10) &&
           fe_static_ready(ctx, S_AvoidGuardP10) && fe_static_ready(ctx, S_AvoidGuardP20) &&
           unit_stat_caches_ready(ctx, STAT_SPD) && unit_stat_caches_ready(ctx, STAT_LCK);
}

static int crit_ready(Context *ctx) {
    return fe_static_ready(ctx, S_NoCritGuard) && unit_stat_caches_ready(ctx, STAT_SKL);
}

static int attack_ready(Context *ctx, int rank_bonus) {
    return unit_stat_caches_ready(ctx, STAT_STR) && unit_stat_caches_ready(ctx, STAT_MAG) &&
           (!rank_bonus || exp_caches_ready(ctx));
}

/* Hit with a weapon; 0 without one. rank_bonus: add the weapon-rank bonus
   (the fight passes 0 at a triangle disadvantage, docs/TRIANGLE.md).
   Guest function: 0x00532DC4 Unit::GetHit(const unit::Item*,bool) const. */
int32_t unit_hit(Context *ctx, gaddr unit, gaddr item, int rank_bonus) {
    if (!fe_static_ready(ctx, S_HitGuard10) || !fe_static_ready(ctx, S_HitGuard20) ||
        !fe_static_ready(ctx, S_HitGuard30))
        return (int32_t)fe_use_original(ctx);
    if (item == 0)
        return 0;
    if (!hit_ready(ctx, rank_bonus))
        return (int32_t)fe_use_original(ctx);
    int32_t hit = fe_add32((int32_t)guest_call1(ctx, GUEST_ItemGetHit, item),
                           READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), hit));
    int32_t skl = stat_of(ctx, STAT_SKL, unit, item);
    int32_t lck = stat_of(ctx, STAT_LCK, unit, item);
    if (fe_gave_up(ctx))
        return 0;
    hit = fe_add32(hit, fe_asr(fe_add32(fe_mul32(skl, 3), lck), 1));
    if (rank_bonus) {
        hit = fe_add32(hit, weapon_rank_term(ctx, unit, item, RANK_COLUMN_HIT));
        if (fe_gave_up(ctx))
            return 0;
    }
    uint64_t words = unit_flag_words(ctx, unit);
    if (has_flag(ctx, words, S_HitMask10))
        hit = fe_add32(hit, 10);
    if (has_flag(ctx, words, S_HitMask20))
        hit = fe_add32(hit, 20);
    if (has_flag(ctx, words, S_HitMask30))
        hit = fe_add32(hit, 30);
    return hit < 0 ? 0 : hit;
}

/* Guest function: 0x00532D90 Unit::GetHit(int,bool) const. */
int32_t unit_hit_of_slot(Context *ctx, gaddr unit, int32_t slot, int rank_bonus) {
    if (!hit_ready(ctx, rank_bonus))
        return (int32_t)fe_use_original(ctx);
    return unit_hit(ctx, unit, slot_or_none(ctx, unit, slot), rank_bonus);
}

/* Avoid (with or without a weapon).
   Guest function: 0x00533524 Unit::GetAvoid(const unit::Item*) const. */
int32_t unit_avoid(Context *ctx, gaddr unit, gaddr item) {
    if (!avoid_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    int32_t spd = stat_of(ctx, STAT_SPD, unit, item);
    int32_t lck = stat_of(ctx, STAT_LCK, unit, item);
    if (fe_gave_up(ctx))
        return 0;
    int32_t avoid = fe_add32(READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), avoid),
                             fe_asr(fe_add32(fe_mul32(spd, 3), lck), 1));
    if (item != 0)
        avoid = fe_add32(avoid, READ_FIELD(ctx, ItemData, guest_call1(ctx, GUEST_ItemToData, item), avoid));
    uint64_t words = unit_flag_words(ctx, unit);
    if (has_flag(ctx, words, S_AvoidMaskM20))
        avoid = fe_add32(avoid, -20);
    if (has_flag(ctx, words, S_AvoidMaskM10))
        avoid = fe_add32(avoid, -10);
    if (has_flag(ctx, words, S_AvoidMaskP10))
        avoid = fe_add32(avoid, 10);
    if (has_flag(ctx, words, S_AvoidMaskP20))
        avoid = fe_add32(avoid, 20);
    if (guest_u8(ctx, FIELD_ADDR(Unit, unit, conditions)) & 0x02u)
        avoid = fe_add32(avoid, -20);
    return avoid < 0 ? 0 : avoid;
}

/* Guest function: 0x005334F0 Unit::GetAvoid(int) const. */
int32_t unit_avoid_of_slot(Context *ctx, gaddr unit, int32_t slot) {
    if (!avoid_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    return unit_avoid(ctx, unit, slot_or_none(ctx, unit, slot));
}

/* Critical rate with a weapon; 0 without one or with a weapon that can never
   crit. An enemy-army unit gets half its class crit unless state bit 5 is set.
   Guest function: 0x0052B9BC Unit::GetCritical(const unit::Item*) const. */
int32_t unit_crit(Context *ctx, gaddr unit, gaddr item) {
    if (!fe_static_ready(ctx, S_NoCritGuard))
        return (int32_t)fe_use_original(ctx);
    if (item == 0)
        return 0;
    if (!crit_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    gaddr data = guest_call1(ctx, GUEST_ItemToData, item);
    if ((READ_FIELD(ctx, ItemData, data, flags) & guest_u64(ctx, S_NoCritMask)) != 0)
        return 0;
    int32_t weapon = (int32_t)guest_call1(ctx, GUEST_ItemGetCritical, item);
    int32_t job_crit = READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), crit);
    int enemy = !(READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_FULL_CRIT) &&
                READ_FIELD(ctx, Force, READ_FIELD(ctx, Unit, unit, force), type) == FORCE_TYPE_ENEMY;
    int32_t crit = fe_add32(weapon, enemy ? fe_asr(job_crit, 1) : job_crit);
    int32_t skl = fe_add32(stat_of(ctx, STAT_SKL, unit, item), -4);
    if (fe_gave_up(ctx))
        return 0;
    if (skl < 0)
        skl = 0;
    crit = fe_add32(crit, fe_asr(skl, 1));
    return crit < 0 ? 0 : crit;
}

/* Guest function: 0x0052B988 Unit::GetCritical(int) const. */
int32_t unit_crit_of_slot(Context *ctx, gaddr unit, int32_t slot) {
    if (!crit_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    return unit_crit(ctx, unit, slot_or_none(ctx, unit, slot));
}

/* Critical avoid ("dodge"): class dodge + Lck / 2 + the weapon's dodge. No
   floor at 0 here (the fight floors its total).
   Guest function: 0x005345E0 Unit::GetSecure(const unit::Item*) const. */
int32_t unit_crit_avoid(Context *ctx, gaddr unit, gaddr item) {
    if (!unit_stat_caches_ready(ctx, STAT_LCK))
        return (int32_t)fe_use_original(ctx);
    int32_t lck = stat_of(ctx, STAT_LCK, unit, item);
    if (fe_gave_up(ctx))
        return 0;
    int32_t dodge = fe_add32(READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), dodge), fe_asr(lck, 1));
    if (item != 0)
        dodge = fe_add32(dodge, READ_FIELD(ctx, ItemData, guest_call1(ctx, GUEST_ItemToData, item), dodge));
    return dodge;
}

/* Attack with a weapon; 0 without one.
   Guest function: 0x00534188 Unit::GetAttack(const unit::Item*,bool) const. */
int32_t unit_attack(Context *ctx, gaddr unit, gaddr item, int rank_bonus) {
    if (item == 0)
        return 0;
    if (!attack_ready(ctx, rank_bonus))
        return (int32_t)fe_use_original(ctx);
    int32_t might = (int32_t)guest_call1(ctx, GUEST_ItemGetPower, item);
    int magic = guest_call1(ctx, GUEST_ItemIsMagic, guest_call1(ctx, GUEST_ItemToData, item)) != 0;
    int32_t attack = fe_add32(stat_of(ctx, magic ? STAT_MAG : STAT_STR, unit, item), might);
    if (fe_gave_up(ctx))
        return 0;
    if (rank_bonus) {
        attack = fe_add32(attack, weapon_rank_term(ctx, unit, item, RANK_COLUMN_ATTACK));
        if (fe_gave_up(ctx))
            return 0;
    }
    return attack < 0 ? 0 : attack;
}

/* The slot form of GetAttack: -1 = the equipped weapon (0 when none);
   other slots are not range-checked (a negative one too, as in the game).
   Guest function: 0x005342B8 Unit::GetAttack(int,bool) const. */
int32_t unit_attack_of_slot(Context *ctx, gaddr unit, int32_t slot, int rank_bonus) {
    if (!attack_ready(ctx, rank_bonus))
        return (int32_t)fe_use_original(ctx);
    if (slot == -1) {
        slot = unit_equipped_index(ctx, unit);
        if (slot == -1)
            return 0;
    }
    return unit_attack(ctx, unit, slot_item(unit, slot), rank_bonus);
}

/* Guest function: 0x00534180 Unit::GetAttackForTerrain(const unit::Item*) const
   (GetAttack with the rank bonus). */
int32_t unit_attack_for_terrain(Context *ctx, gaddr unit, gaddr item) {
    return unit_attack(ctx, unit, item, 1);
}

/* Guest function: 0x005309A0 Unit::GetAttackForTerrain(int) const. */
int32_t unit_attack_for_terrain_of_slot(Context *ctx, gaddr unit, int32_t slot) {
    return unit_attack_of_slot(ctx, unit, slot, 1);
}

/* The speed compared for a follow-up when this unit strikes.
   Guest function: 0x0052E134 Unit::GetContinuous(const unit::Item*) const. */
int32_t unit_attack_speed(Context *ctx, gaddr unit, gaddr item) {
    int32_t speed = stat_of(ctx, STAT_SPD, unit, item);
    if (fe_gave_up(ctx))
        return 0;
    if (item != 0)
        speed = fe_add32(speed, READ_FIELD(ctx, ItemData, guest_call1(ctx, GUEST_ItemToData, item), speed_mod_player));
    return speed < 0 ? 0 : speed;
}

/* The speed the other side must beat by 5 to strike this unit twice.
   Guest function: 0x00530834 Unit::GetUnderContinuous(const unit::Item*) const. */
int32_t unit_defense_speed(Context *ctx, gaddr unit, gaddr item) {
    int32_t speed = stat_of(ctx, STAT_SPD, unit, item);
    if (fe_gave_up(ctx))
        return 0;
    if (item != 0)
        speed = fe_add32(speed, READ_FIELD(ctx, ItemData, guest_call1(ctx, GUEST_ItemToData, item), speed_mod_enemy));
    return speed < 0 ? 0 : speed;
}

/* The bool is passed as the plain register (rank_bonus is only tested for
   non-zero, as `!= 0` did), so capture mode sees r0-r2 as the arguments and
   does not compare r3, which the callers leave as anything (round 20: the
   strike reader's Dragon Fang call of GetAttack left 0, the game 0x1E). */
RECOMP_OVERRIDE(0x00532DC4) {
    FE_ENTRY(0x00532DC4, unit_hit, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x00532D90) {
    FE_ENTRY(0x00532D90, unit_hit_of_slot, FE_ARG(0), FE_ARG_S(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x00533524) {
    FE_ENTRY(0x00533524, unit_avoid, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x005334F0) {
    FE_ENTRY(0x005334F0, unit_avoid_of_slot, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0052B9BC) {
    FE_ENTRY(0x0052B9BC, unit_crit, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052B988) {
    FE_ENTRY(0x0052B988, unit_crit_of_slot, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x005345E0) {
    FE_ENTRY(0x005345E0, unit_crit_avoid, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00534188) {
    FE_ENTRY(0x00534188, unit_attack, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x005342B8) {
    FE_ENTRY(0x005342B8, unit_attack_of_slot, FE_ARG(0), FE_ARG_S(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x00534180) {
    FE_ENTRY(0x00534180, unit_attack_for_terrain, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x005309A0) {
    FE_ENTRY(0x005309A0, unit_attack_for_terrain_of_slot, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0052E134) {
    FE_ENTRY(0x0052E134, unit_attack_speed, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00530834) {
    FE_ENTRY(0x00530834, unit_defense_speed, FE_ARG(0), FE_ARG(1));
}
