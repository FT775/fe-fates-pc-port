/* Who may strike or block in a stance, and the shield gauge (Fates classes
   map::Situation, map::BattleInfo, map::BattleCalculator; the turn start of
   map::Sequence). Plain-language description: docs/STANCES.md.

   A fight has four sides (map::BattleInfo, 0x200 bytes each): 0 and 1 are the
   two leads, 2 and 3 the units behind them (the "dual" sides: the ally that
   adds a follow-up strike, or the partner of a pair). The calculator
   (map::BattleCalculator) keeps a gauge counter per side; a pair's shield
   gauge is the sum of its two counters, and outside a fight each unit keeps
   its own part (Unit.guard_gauge).

   Only situation_can_dual is an override. The others are the pure part of a
   bigger function that also writes guest memory: each returns what the game
   would write, in host memory, and writes nothing (project rule: no writer
   until the harness steps H6/H8 are green on Fates). They have helper rows in
   config/readable/functions.csv and are tested against the original code
   region they describe.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/battle/tests/stance_diff.py. */

#include "stances.h"

/* The fight's other main side: 0 and 2 fight 1, 1 and 3 fight 0 (the game
   uses side 5 for any other value; it never passes one). */
static uint32_t opposing_lead(uint32_t side) {
    if (side == 0 || side == 2)
        return 1;
    if (side == 1 || side == 3)
        return 0;
    return 5;
}

static gaddr battle_side(gaddr info, uint32_t side) {
    return info + side * (gaddr)sizeof(BattleSide);
}

static gaddr gauge_addr(gaddr calc, uint32_t side) {
    return FIELD_ADDR(BattleCalculator, calc, gauge) + side * 4u;
}

/* Whether stance follow-ups and the shield gauge are on for an army: always,
   unless the game mode bit (GameUserData +0x28 bit 3) is set; then only for the
   armies the map marks (one byte per force type, 1 = on). Bit 19 of the
   situation's flags turns them on for everyone.
   Guest function: 0x005281B8 map::Situation::CanDual(Force::Type) const -> 1 or 0. */
int situation_can_dual(Context *ctx, gaddr situation, uint32_t force_type) {
    if (READ_FIELD(ctx, Situation, situation, flags) & 0x80000u)
        return 1;
    gaddr user = guest_ptr(ctx, G_GameUserData);
    if (!(READ_FIELD(ctx, GameUserData, user, mode_flags) & 0x8u))
        return 1;
    return guest_u8(ctx, FIELD_ADDR(Situation, situation, force_dual) + force_type) == 1;
}

/* The stance part of map::BattleInfo::CalculateDual for main side 0 or 1:
   - an ally next to the lead (not its pair partner) may add a follow-up, unless
     the side's flag 0x100 says no;
   - a pair partner adds the pair's shield gauge (both units' points) and adds a
     follow-up only when the lead has a certain skill (S_DualSkillId), again
     unless flag 0x100;
   - the follow-up side's attack count is cleared when the lead has no attack or
     no follow-up is allowed, and always under the side's flag 0x4000.
   Returns 0 when the game skips the whole step (BattleInfo.flags bit 4, or side
   0's flag 0x40); then *out is not set.
   Guest function: helper of 0x00347350 map::BattleInfo::CalculateDual(void),
   which writes these values into BattleSide.dual_attack / gauge_total and the
   follow-up side's attack_count. */
int battle_dual_plan(Context *ctx, gaddr info, uint32_t side, BattleDualPlan *out) {
    if (READ_FIELD(ctx, BattleInfo, info, flags) & 0x10u)
        return 0;
    if (READ_FIELD(ctx, BattleSide, info, flags) & 0x40u)
        return 0;
    if (!fe_static_ready(ctx, S_DualSkillGuard))
        return (int)fe_use_original(ctx);
    gaddr s = battle_side(info, side);
    gaddr dual = READ_FIELD(ctx, BattleSide, s, dual_unit);
    out->dual_attack = 0;
    out->gauge_total = 0;
    if (dual != 0) {
        gaddr lead = READ_FIELD(ctx, BattleSide, s, unit);
        int may = !(READ_FIELD(ctx, BattleSide, s, flags) & 0x100u);
        if (dual != READ_FIELD(ctx, Unit, lead, pair_partner)) {
            out->dual_attack = (uint8_t)may;
        } else {
            out->gauge_total = (int32_t)READ_FIELD(ctx, Unit, lead, guard_gauge) +
                               (int32_t)READ_FIELD(ctx, Unit, dual, guard_gauge);
            int32_t skill = guest_s16(ctx, S_DualSkillId);
            if (guest_call2(ctx, GUEST_UnitIsEquipSkill, lead, (uint32_t)skill) != 0 && may)
                out->dual_attack = 1;
        }
    }
    out->clear_follow_up = READ_FIELD(ctx, BattleSide, s, attack_count) <= 0 || out->dual_attack == 0 ||
                           (READ_FIELD(ctx, BattleSide, s, flags) & 0x4000u) != 0;
    return 1;
}

/* Whether the defender's pair blocks this strike (Guard Stance): the defending
   lead has a pair partner and either the pair's gauge is full (10 points or
   more), or the strike comes from a follow-up side (2 or 3) while the
   defender's side byte +0x40 is set.
   Part of 0x003628BC map::BattleCalculator::CalculateAttackSingle (the gauge
   sum at 0x00363404, the test at 0x0036378C); no registry row of its own. */
int stance_dual_guard_blocks(Context *ctx, gaddr calc, uint32_t attacker) {
    gaddr info = READ_FIELD(ctx, BattleCalculator, calc, info);
    uint32_t def = opposing_lead(attacker);
    gaddr def_side = battle_side(info, def);
    int32_t gauge = fe_add32(guest_s32(ctx, gauge_addr(calc, def)), guest_s32(ctx, gauge_addr(calc, def + 2)));
    int special = attacker >= 2 && READ_FIELD(ctx, BattleSide, def_side, guard_breaker) != 0;
    if (READ_FIELD(ctx, Unit, READ_FIELD(ctx, BattleSide, def_side, unit), pair_partner) == 0)
        return 0;
    return special || gauge >= STANCE_GAUGE_FULL;
}

/* A pair may gain gauge points in this fight: it is a pair, and the stance
   system is on for its army (situation_can_dual on the current situation). */
static int pair_gains(Context *ctx, gaddr lead) {
    if (READ_FIELD(ctx, Unit, lead, pair_partner) == 0)
        return 0;
    gaddr situation = guest_ptr(ctx, G_Situation);
    if (situation == 0)
        return 0;
    return situation_can_dual(ctx, situation, READ_FIELD(ctx, Force, READ_FIELD(ctx, Unit, lead, force), type));
}

static int has_gauge_skill(Context *ctx, gaddr unit) {
    int32_t skill = guest_s16(ctx, S_GaugeSkillId);
    return guest_call2(ctx, GUEST_UnitIsEquipSkill, unit, (uint32_t)skill) != 0;
}

/* The shield gauge after one strike (hit or miss), as
   map::BattleCalculator::CalculateAttackSingle updates it (0x00364530 .. 0x00364848):
   - defender, blocked by its pair: the pair's gauge empties (both counters 0),
     except for a strike of a follow-up side against a side whose byte +0x40 is
     set (then it stays);
   - defender, not blocked, paired, stance system on: +1 to each counter (2
     points), and one more on the partner's counter when the partner has the
     gauge skill and the pair is still below 10;
   - attacker's pair (the lead's side also for a follow-up strike), paired, side
     flag 0x100 clear, stance system on: +1 to each counter while the sum is
     below 9; at 9 only the smaller counter (the partner's on a tie) gets +1; at
     10 or more nothing; then the gauge-skill point as above.
   The defender's gauge is not capped here: a pair at 9 that takes a hit reaches 11.
   Writes nothing: *out holds the four counters the game would store.
   Guest function: helper of 0x003628BC map::BattleCalculator::CalculateAttackSingle. */
void stance_gauge_after_strike(Context *ctx, gaddr calc, uint32_t attacker, int blocked, StanceGauges *out) {
    if (attacker > 3) { /* never passed by the game; the counters would be out of range */
        fe_use_original(ctx);
        return;
    }
    for (uint32_t i = 0; i < 4; i++)
        out->gauge[i] = guest_s32(ctx, gauge_addr(calc, i));
    gaddr info = READ_FIELD(ctx, BattleCalculator, calc, info);
    uint32_t def = opposing_lead(attacker);
    gaddr def_side = battle_side(info, def);
    int special = attacker >= 2 && READ_FIELD(ctx, BattleSide, def_side, guard_breaker) != 0;
    if (blocked) {
        if (!special) {
            out->gauge[def] = 0;
            out->gauge[def + 2] = 0;
        }
    } else {
        gaddr lead = READ_FIELD(ctx, BattleSide, def_side, unit);
        if (pair_gains(ctx, lead)) {
            out->gauge[def] = fe_add32(out->gauge[def], 1);
            out->gauge[def + 2] = fe_add32(out->gauge[def + 2], 1);
            if (has_gauge_skill(ctx, READ_FIELD(ctx, Unit, lead, pair_partner)) &&
                fe_add32(out->gauge[def], out->gauge[def + 2]) < STANCE_GAUGE_FULL)
                out->gauge[def + 2] = fe_add32(out->gauge[def + 2], 1);
        }
    }
    uint32_t own = attacker >= 2 ? (attacker - 2) & 0xFFu : attacker;
    gaddr own_side = battle_side(info, own);
    gaddr lead = READ_FIELD(ctx, BattleSide, own_side, unit);
    if (READ_FIELD(ctx, Unit, lead, pair_partner) == 0 || (READ_FIELD(ctx, BattleSide, own_side, flags) & 0x100u))
        return;
    if (!pair_gains(ctx, lead))
        return;
    int32_t *front = &out->gauge[own], *back = &out->gauge[own + 2];
    int32_t sum = fe_add32(*front, *back);
    if (sum < STANCE_GAUGE_FULL - 1) {
        *front = fe_add32(*front, 1);
        *back = fe_add32(*back, 1);
    } else if (sum < STANCE_GAUGE_FULL) {
        if (*front < *back)
            *front = fe_add32(*front, 1);
        else
            *back = fe_add32(*back, 1);
    }
    if (has_gauge_skill(ctx, READ_FIELD(ctx, Unit, lead, pair_partner)) && fe_add32(*front, *back) < STANCE_GAUGE_FULL)
        *back = fe_add32(*back, 1);
}

/* One unit at the start of its army's turn: a unit whose "fought" flag
   (Unit.state_flags bit 23) is set keeps its gauge points and loses the flag;
   any other unit loses one point (not below 0).
   Writes nothing: *out holds what the game would store.
   Guest function: helper of 0x003A54D8 map::Sequence::(anonymous)::ProcSequence::TurnBegin(void)
   (the per-unit step at 0x003A557C). */
void stance_gauge_at_turn_begin(Context *ctx, gaddr unit, StanceTurnBegin *out) {
    uint32_t flags = READ_FIELD(ctx, Unit, unit, state_flags);
    uint8_t gauge = READ_FIELD(ctx, Unit, unit, guard_gauge);
    if (flags & 0x800000u) {
        out->flags = flags & ~0x800000u;
        out->guard_gauge = gauge;
    } else {
        out->flags = flags;
        out->guard_gauge = gauge > 0 ? (uint8_t)(gauge - 1u) : gauge;
    }
}

/* The last step of a side's damage: a follow-up side (BattleSide.flags bit 1,
   set on sides 2 and 3 by map::BattleInfo::ComplementConditions) deals half,
   rounded down; then a negative result becomes 0.
   Guest function: helper of 0x005253A8 map::BattleInfo::Side::GetSimplePower
   (its end, 0x005259B0). */
int32_t stance_follow_up_damage(Context *ctx, gaddr side, int32_t damage) {
    if (READ_FIELD(ctx, BattleSide, side, flags) & 0x2u)
        damage = fe_asr(damage, 1);
    return damage < 0 ? 0 : damage;
}

RECOMP_OVERRIDE(0x005281B8) {
    FE_ENTRY(0x005281B8, situation_can_dual, FE_ARG(0), FE_ARG(1));
}
