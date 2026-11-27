/* The battle forecast (Fates class map::BattleInfo and its Side): the shown
   hit, critical, number of strikes, and the per-side critical / critical
   avoid / speed numbers they are made from. Plain-language description:
   docs/FORMULAS.md section 4.

   A fight has four sides (docs/STANCES.md): 0 and 1 the leads, 2 and 3 the
   Attack Stance followers. Each side keeps two BattleDetail rows: row 0 is
   used against a lead, row 1 against a follower. map::BattleInfo::Calculate
   runs Side::CalculateDetail for every side (attack, defense, hit, avoid,
   critical, critical avoid, the two speeds), then CalculateSimple turns them
   into what the forecast shows:

     shown hit      = side hit - other side's avoid, clamped 0 .. 100 (Side::GetSimpleHit)
     shown critical = side crit - other side's crit avoid, clamped 0 .. 100 (CalculateSimple)
     strikes        = 2 when attack speed >= the other side's defense speed + 5, else 1,
                      0 when the side cannot strike (Side::GetSimpleTimes)

   forecast_hit and forecast_strikes are const functions of the game (pure
   readers) and are overrides. forecast_detail and forecast_crit are helpers:
   their game functions store into the BattleInfo, so they return what the
   game would store and write nothing (project rule F-017: no readable writer
   until the harness steps H6/H8 are green on Fates).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/battle/tests/formula_diff.py. */

#include "formulas.h"

/* 1 when a side is an Attack Stance follower (side type 2 or 3) */
static uint32_t is_follower(Context *ctx, gaddr side) {
    uint8_t type = READ_FIELD(ctx, BattleSide, side, side_type);
    return type == 2 || type == 3;
}

static gaddr detail_row(gaddr side, uint32_t row) {
    return FIELD_ADDR(BattleSide, side, detail) + row * (gaddr)sizeof(BattleDetail);
}

static gaddr side_item(gaddr side) {
    return FIELD_ADDR(BattleSide, side, item);
}

/* Bit `id` of a side's equipped-skill bit set (an arithmetic shift for the
   byte, as in the game). */
static int side_has_skill_bit(Context *ctx, gaddr side, uint32_t row, int32_t id) {
    gaddr bits = FIELD_ADDR(BattleSide, side, skill_bits) + row * BATTLE_BONUS_STRIDE;
    return (guest_u8(ctx, bits + (gaddr)fe_asr(id, 3)) >> (id & 7)) & 1;
}

static uint64_t unit_flag_words(Context *ctx, gaddr unit) {
    return READ_FIELD(ctx, Unit, unit, private_flags) |
           READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), flags) |
           READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), flags);
}

static int32_t clamp_percent(int32_t v) {
    return v < 0 ? 0 : v > 100 ? 100 : v;
}

/* The shown hit of `side` against `other`: 0 without a weapon; 100 for a
   staff that is not a hindering staff; else the side's hit minus the other
   side's avoid, and for a hindering staff 0 or half against resistant
   targets; clamped 0 .. 100.
   Guest function: 0x00525090 map::BattleInfo::Side::GetSimpleHit(const map::BattleInfo::Side*) const. */
int32_t forecast_hit(Context *ctx, gaddr side, gaddr other) {
    if (!fe_static_ready(ctx, S_FhStaffResistGuard) || !fe_static_ready(ctx, S_FhStaffImmuneGuard) ||
        !fe_static_ready(ctx, S_FhStaffItemGuard) || !fe_static_ready(ctx, S_FhStatusResistGuard) ||
        !fe_static_ready(ctx, S_FhStatusImmuneGuard))
        return (int32_t)fe_use_original(ctx);
    if (READ_FIELD(ctx, BattleSide, side, item) == 0)
        return 0;
    uint32_t flags = READ_FIELD(ctx, BattleSide, side, flags);
    if (flags & SIDE_STAFF) {
        gaddr data = guest_call1(ctx, GUEST_ItemToData, side_item(side));
        if ((READ_FIELD(ctx, ItemData, data, flags) & guest_u64(ctx, S_FhStaffItemMask)) == 0)
            return 100;
    }
    int32_t hit = READ_FIELD(ctx, BattleDetail, detail_row(side, 0), hit) -
                  READ_FIELD(ctx, BattleDetail, detail_row(other, is_follower(ctx, side)), avoid);
    if (flags & SIDE_HINDER) {
        gaddr target = READ_FIELD(ctx, BattleSide, other, unit);
        uint64_t words = unit_flag_words(ctx, target);
        if (words & guest_u64(ctx, S_FhStaffImmuneMask))
            hit = 0;
        if (words & guest_u64(ctx, S_FhStaffResistMask))
            hit /= 2;
        if (guest_call2(ctx, GUEST_UnitIsEquipSkill, target, (uint32_t)(int32_t)guest_s16(ctx, S_FhStatusImmuneId)))
            hit = 0;
        if (guest_call2(ctx, GUEST_UnitIsEquipSkill, READ_FIELD(ctx, BattleSide, other, unit),
                        (uint32_t)(int32_t)guest_s16(ctx, S_FhStatusResistId)))
            hit /= 2;
        if (guest_u32(ctx, guest_ptr(ctx, S_FhRuleWord) + 4u) & 0x40000u)
            hit /= 2;
    }
    return clamp_percent(hit);
}

/* How many times `side` strikes `other` at `distance` tiles: 0, 1 or 2.
   info_flags = the BattleInfo's flag word (BattleInfo + 0x804).
   - 0: no weapon; a magic weapon while the unit's condition bit 3 is set;
     out of range (unless info bit 0 or the side is a follower); a side that
     did not start the fight and holds a long-range (siege) weapon, or whose
     opponent holds a staff or a siege weapon, or info bit 5; a staff or siege
     side that is a follower.
   - 1: a staff or siege side; a weapon that never follows up; the "defensive formation"
     skill bit on either side; a follower.
   - 2: when its attack speed is at least the other side's defense speed + 5.
   Guest function: 0x005259D4 map::BattleInfo::Side::GetSimpleTimes(const map::BattleInfo::Side*,int,const map::BattleInfo::Flag*) const. */
int32_t forecast_strikes(Context *ctx, gaddr side, gaddr other, int32_t distance, gaddr info_flags) {
    if (!fe_static_ready(ctx, S_FsNoFollowGuard) || !fe_static_ready(ctx, S_FsNoDoubleGuard) ||
        !fe_static_ready(ctx, S_FsRangeIGuard))
        return (int32_t)fe_use_original(ctx);
    uint32_t row = is_follower(ctx, side);
    if (READ_FIELD(ctx, BattleSide, side, item) == 0)
        return 0;
    gaddr unit = READ_FIELD(ctx, BattleSide, side, unit);
    if (guest_u8(ctx, FIELD_ADDR(Unit, unit, conditions)) & 0x08u) {
        if (guest_call1(ctx, GUEST_ItemIsMagic, guest_call1(ctx, GUEST_ItemToData, side_item(side))))
            return 0;
    }
    uint32_t info = guest_u32(ctx, info_flags);
    if (!(info & 1u) && !(READ_FIELD(ctx, BattleSide, side, flags) & SIDE_FOLLOW_UP)) {
        if (distance == 0)
            return 0;
        if ((int32_t)guest_call2(ctx, GUEST_UnitGetRangeI, READ_FIELD(ctx, BattleSide, side, unit), side_item(side)) >
            distance)
            return 0;
        if (distance >
            (int32_t)guest_call2(ctx, GUEST_UnitGetRangeO, READ_FIELD(ctx, BattleSide, side, unit), side_item(side)))
            return 0;
    }
    uint32_t flags = READ_FIELD(ctx, BattleSide, side, flags);
    if (!(flags & SIDE_INITIATOR)) {
        if (flags & SIDE_NO_STRIKE)
            return 0;
        if (READ_FIELD(ctx, BattleSide, other, flags) & (SIDE_STAFF | SIDE_NO_STRIKE))
            return 0;
        if (guest_u32(ctx, info_flags) & 0x20u)
            return 0;
    }
    if (flags & (SIDE_STAFF | SIDE_NO_STRIKE))
        return (flags & SIDE_FOLLOW_UP) ? 0 : 1;
    gaddr data = guest_call1(ctx, GUEST_ItemToData, side_item(side));
    if (READ_FIELD(ctx, ItemData, data, flags) & guest_u64(ctx, S_FsNoFollowMask))
        return 1;
    int32_t no_double = guest_s16(ctx, S_FsNoDoubleId);
    if (side_has_skill_bit(ctx, side, 0, no_double) || side_has_skill_bit(ctx, other, row, no_double))
        return 1;
    if (READ_FIELD(ctx, BattleSide, side, flags) & SIDE_FOLLOW_UP)
        return 1;
    int32_t mine = READ_FIELD(ctx, BattleDetail, detail_row(side, 0), attack_speed);
    int32_t theirs = READ_FIELD(ctx, BattleDetail, detail_row(other, row), defense_speed);
    return mine >= fe_add32(theirs, 5) ? 2 : 1;
}

/* The critical, critical-avoid and the two speeds of Side::CalculateDetail: what
   the game stores into the side's BattleDetail row for `other` (row 1 when
   `other` is a follower). Critical: only with both units, a weapon, not a
   staff side and against a lead: Unit::GetCritical + three bonus words (skills
   and the other battle bonuses), as a 16-bit number, never below 0. Critical
   avoid: with both units: Unit::GetSecure + three bonus words, the same way.
   Speeds: with both units and against a lead: Unit::GetContinuous /
   GetUnderContinuous + a bonus word each; else 0.
   Guest function: helper of 0x00348754 map::BattleInfo::Side::CalculateDetail(const map::BattleInfo::Side*)
   (the region 0x00348788 .. 0x0034899C, after its four Calculate* calls). */
void forecast_detail(Context *ctx, gaddr side, gaddr other, ForecastDetail *out) {
    uint32_t row = is_follower(ctx, other);
    gaddr unit = READ_FIELD(ctx, BattleSide, side, unit);
    int both = unit != 0 && READ_FIELD(ctx, BattleSide, other, unit) != 0;
    out->detail = row;
    out->crit = 0;
    out->crit_avoid = 0;
    out->attack_speed = 0;
    out->defense_speed = 0;
    if (both && READ_FIELD(ctx, BattleSide, side, item) != 0 && !(READ_FIELD(ctx, BattleSide, side, flags) & SIDE_STAFF) &&
        row == 0) {
        uint32_t sum = (uint32_t)unit_crit(ctx, unit, side_item(side));
        if (fe_gave_up(ctx))
            return;
        sum += READ_FIELD(ctx, BattleSide, side, bonus_crit);
        sum += READ_FIELD(ctx, BattleSide, side, skill_crit);
        sum += READ_FIELD(ctx, BattleSide, side, extra_crit);
        int16_t crit = (int16_t)(uint16_t)sum;
        out->crit = crit < 0 ? 0 : crit;
    }
    if (both) {
        uint32_t sum = (uint32_t)unit_crit_avoid(ctx, unit, side_item(side));
        if (fe_gave_up(ctx))
            return;
        sum += guest_u16(ctx, FIELD_ADDR(BattleSide, side, bonus_crit_avoid) + row * BATTLE_BONUS_STRIDE);
        sum += READ_FIELD(ctx, BattleSide, side, skill_crit_avoid);
        sum += READ_FIELD(ctx, BattleSide, side, extra_crit_avoid);
        int16_t crit_avoid = (int16_t)(uint16_t)sum;
        out->crit_avoid = crit_avoid < 0 ? 0 : crit_avoid;
    }
    if (both && row == 0) {
        out->attack_speed = fe_add32(unit_attack_speed(ctx, unit, side_item(side)),
                                     READ_FIELD(ctx, BattleSide, side, bonus_attack_speed));
        out->defense_speed = fe_add32(unit_defense_speed(ctx, unit, side_item(side)),
                                      READ_FIELD(ctx, BattleSide, side, bonus_defense_speed));
    }
}

/* The shown critical of `side` against `other` (BattleSide.crit_rate): 0
   without a weapon or for a staff side; else the side's critical minus the
   other side's critical avoid, clamped 0 .. 100; 0 again for a weapon that can
   never crit or a side with the no-critical bit.
   Guest function: helper of 0x00347C3C map::BattleInfo::CalculateSimple(void)
   (its region 0x00347CEC .. 0x00347DDC, once per side). */
int32_t forecast_crit(Context *ctx, gaddr side, gaddr other) {
    if (!fe_static_ready(ctx, S_FcNoCritGuard))
        return (int32_t)fe_use_original(ctx);
    if (READ_FIELD(ctx, BattleSide, side, item) == 0 || (READ_FIELD(ctx, BattleSide, side, flags) & SIDE_STAFF))
        return 0;
    int32_t crit = clamp_percent(READ_FIELD(ctx, BattleDetail, detail_row(side, 0), crit) -
                                 READ_FIELD(ctx, BattleDetail, detail_row(other, is_follower(ctx, side)), crit_avoid));
    gaddr data = guest_call1(ctx, GUEST_ItemToData, side_item(side));
    if (READ_FIELD(ctx, ItemData, data, flags) & guest_u64(ctx, S_FcNoCritMask))
        crit = 0;
    if (READ_FIELD(ctx, BattleSide, side, flags) & SIDE_NO_CRIT)
        crit = 0;
    return crit;
}

RECOMP_OVERRIDE(0x00525090) {
    FE_ENTRY(0x00525090, forecast_hit, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x005259D4) {
    FE_ENTRY(0x005259D4, forecast_strikes, FE_ARG(0), FE_ARG(1), FE_ARG_S(2), FE_ARG(3));
}
