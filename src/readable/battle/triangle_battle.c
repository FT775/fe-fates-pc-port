/* The weapon triangle in a fight (Fates class map::BattleInfo and its Side).
   Plain-language description: docs/TRIANGLE.md.

   A fight has four sides (map::BattleInfo, 0x200 bytes each, docs/STANCES.md):
   0 and 1 are the leads, 2 and 3 the units behind them. Every side is set
   against the opposing lead: sides 0 and 2 against side 1, sides 1 and 3
   against side 0.

   1. map::BattleInfo::CalculateDetail looks up each side's triangle cell in
      WeaponInteract (its weapon kind's row, the opposing lead's weapon kind's
      column: +1 advantage, -1 disadvantage, 0 neutral) and marks a side whose
      weapon carries the reversing flag (triangle_side_lookup).
   2. Then, for every side: when exactly one of it and the opposing lead holds a
      reversing weapon, its cell is multiplied by -2 (reversed and doubled);
      when both do, it stays (triangle_after_reverse).
   3. Side::CalculateDetailHit / CalculateDetailAttack add the rank-scaled
      triangle bonus: the WeaponInteract rank row of the unit that HAS the
      advantage (the side itself when its cell is positive, the opposing lead
      when negative), times the cell. A side whose cell is negative also gets
      no weapon-rank bonus from Unit::GetHit / GetAttack (their bool argument).

   The three game functions write their results into the BattleInfo (and do
   much more); these helpers return what the triangle part would store and
   write nothing (project rule: no writer until the harness steps H6/H8 are
   green on Fates).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code regions: src/readable/battle/tests/triangle_diff.py. */

#include "triangle.h"

/* The fight's opposing lead: 0 and 2 face 1, 1 and 3 face 0 (the game uses
   side 5 for any other value; it never passes one). */
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

static gaddr side_item(gaddr side) {
    return FIELD_ADDR(BattleSide, side, item);
}

/* Whether a weapon (a unit::Item) reverses the weapon triangle: its Item
   record's flag word has the bit the game cached at S_ReverseMask. Gives up
   while that cache is cold. */
int triangle_item_reverses(Context *ctx, gaddr item) {
    if (!fe_static_ready(ctx, S_ReverseGuard))
        return (int)fe_use_original(ctx);
    gaddr data = guest_call1(ctx, GUEST_ItemToData, item);
    return (READ_FIELD(ctx, ItemData, data, flags) & guest_u64(ctx, S_ReverseMask)) != 0;
}

/* Step 1 for one side: when the side has a unit and a weapon and the opposing
   lead has a weapon, the WeaponInteract cell [side's kind][opposing kind]
   (the game stores it into BattleSide.triangle) and TRIANGLE_REVERSED added
   to the side's flags when its weapon reverses the triangle. Otherwise
   nothing is stored (the previous value stays).
   Guest function: helper of 0x003475BC map::BattleInfo::CalculateDetail(void)
   (its third loop, 0x003479B4 .. 0x00347AEC). */
void triangle_side_lookup(Context *ctx, gaddr info, uint32_t side, TriangleLookup *out) {
    if (!fe_static_ready(ctx, S_ReverseGuard)) {
        fe_use_original(ctx);
        return;
    }
    gaddr s = battle_side(info, side);
    gaddr o = battle_side(info, opposing_lead(side));
    out->looked_up = 0;
    out->triangle = 0;
    out->flags = READ_FIELD(ctx, BattleSide, s, flags);
    if (READ_FIELD(ctx, BattleSide, s, unit) == 0 || READ_FIELD(ctx, BattleSide, s, item) == 0 ||
        READ_FIELD(ctx, BattleSide, o, item) == 0)
        return;
    gaddr interact = weapon_interact_record(ctx);
    int32_t own_kind = item_weapon_kind(ctx, side_item(s));
    int32_t other_kind = item_weapon_kind(ctx, side_item(o));
    gaddr cell = FIELD_ADDR(WeaponInteractData, interact, attacker_sword) + (gaddr)own_kind * 8u + (gaddr)other_kind;
    out->looked_up = 1;
    out->triangle = guest_s8(ctx, cell);
    if (triangle_item_reverses(ctx, side_item(s)))
        out->flags |= TRIANGLE_REVERSED;
}

/* Step 2 for one side: its triangle cell after the reversing weapons: times -2
   when exactly one of the side and the opposing lead is marked
   TRIANGLE_REVERSED, unchanged when none or both are.
   Part of 0x003475BC map::BattleInfo::CalculateDetail (its fourth loop,
   0x00347B08 .. 0x00347B68); no registry row of its own. */
int32_t triangle_after_reverse(Context *ctx, gaddr info, uint32_t side) {
    gaddr s = battle_side(info, side);
    gaddr o = battle_side(info, opposing_lead(side));
    int32_t factor = 1;
    if (READ_FIELD(ctx, BattleSide, s, flags) & TRIANGLE_REVERSED)
        factor = -1;
    if (READ_FIELD(ctx, BattleSide, o, flags) & TRIANGLE_REVERSED)
        factor = -factor;
    if (factor < 0)
        factor *= 2;
    return fe_mul32(READ_FIELD(ctx, BattleSide, s, triangle), factor);
}

/* Step 3: the rank-scaled triangle bonus of one battle number (column attack
   or hit) for a side facing `opposing`. The side must have a unit and a weapon,
   the opposing side a unit, and the opposing side must be a lead (not a
   follow-up side: side_type 2 or 3); otherwise the game stores 0 for the number. */
static void triangle_rank_bonus(Context *ctx, gaddr side, gaddr opposing, int column, TriangleRankBonus *out) {
    uint8_t type = READ_FIELD(ctx, BattleSide, opposing, side_type);
    int against_follow_up = type == 2 || type == 3;
    out->applies = 0;
    out->keep_rank_bonus = 0;
    out->bonus = 0;
    if (READ_FIELD(ctx, BattleSide, side, unit) == 0 || READ_FIELD(ctx, BattleSide, opposing, unit) == 0 ||
        READ_FIELD(ctx, BattleSide, side, item) == 0 || against_follow_up)
        return;
    if (column == RANK_COLUMN_ATTACK && (READ_FIELD(ctx, BattleSide, side, flags) & 0x40u))
        return;
    out->applies = 1;
    int32_t triangle = READ_FIELD(ctx, BattleSide, side, triangle);
    out->keep_rank_bonus = triangle >= 0;
    if (triangle == 0)
        return;
    /* the rank of whoever has the advantage */
    gaddr holder = triangle > 0 ? side : opposing;
    int32_t kind = item_weapon_kind(ctx, side_item(holder));
    int32_t exp = unit_weapon_exp(ctx, READ_FIELD(ctx, BattleSide, holder, unit), (uint32_t)kind);
    if (fe_gave_up(ctx))
        return;
    int32_t rank = weapon_rank_of_exp(ctx, weapon_level_record(ctx), exp);
    int32_t per_rank = guest_s8(ctx, weapon_interact_record(ctx) + (gaddr)rank * 2u + (gaddr)column);
    out->bonus = fe_mul32(per_rank, triangle);
}

/* Guest function: helper of 0x00348FF0 map::BattleInfo::Side::CalculateDetailHit(const Side*)
   (the region 0x00349048 .. 0x00349144; the game adds bonus to the 16-bit hit
   it got from Unit::GetHit). */
void triangle_hit_bonus(Context *ctx, gaddr side, gaddr opposing, TriangleRankBonus *out) {
    triangle_rank_bonus(ctx, side, opposing, RANK_COLUMN_HIT, out);
}

/* Guest function: helper of 0x00349880 map::BattleInfo::Side::CalculateDetailAttack(const Side*)
   (the region 0x00349970 .. 0x00349A7C; also no bonus when the side's flag 0x40 is set). */
void triangle_attack_bonus(Context *ctx, gaddr side, gaddr opposing, TriangleRankBonus *out) {
    triangle_rank_bonus(ctx, side, opposing, RANK_COLUMN_ATTACK, out);
}
