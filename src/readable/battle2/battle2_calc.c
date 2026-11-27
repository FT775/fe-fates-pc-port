/* Battle numbers, second batch: the fight's own records (Fates classes
   map::BattleCalculator and map::BattleInfo::Side). Who died in a strike
   list, how many strikes one side makes in a row, the damage of one strike,
   and the avoid and defense numbers a side gets against the other.
   Plain-language description: docs/BATTLE2.md sections 1 to 4.

   battle_dead_unit and battle_strike_run are readers and overrides.

   forecast_damage is the whole of map::BattleInfo::Side::GetSimplePower, a
   reader (it stores nothing). It is written and host-tested but has NO
   override marker and NO registry row yet: the address 0x005253A8 is held in
   config/readable/functions.csv by the stance batch's helper row
   (stance_follow_up_damage, its last step), and a registry address may be
   listed only once. docs/BATTLE2.md section 3 names the change the integrate
   step would make. Its Ignis and Rend Heaven steps call Unit::GetStrImpl /
   GetPowImpl, which take a fifth argument on the guest stack: for those two
   skills it gives up (the original runs).

   battle_detail_avoid and battle_detail_defense are helpers (F-017): the
   pure part of map::BattleInfo::Side::CalculateDetailAvoid and
   CalculateDetailDefense, which store into the fight side (writers in this
   project's sense). They return what the game would store and write
   nothing. battle_detail_defense takes the unit's defense and resistance from
   its caller, because GetDefImpl / GetMdefImpl take a stack argument.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/battle2/tests/battle2_diff.py. */

#include "battle2.h"

int32_t stance_follow_up_damage(Context *ctx, gaddr side, int32_t damage); /* src/readable/battle/stance_gauge.c */

/* ------------------------------------------------------------------ the strike list */

/* The unit that dies in a list of battle scene records, or 0. The records are
   walked from the first (the word the list object points to): a record of
   kind 1, 4, 8 or 9 ends the search with no unit; a record of kind 7 names
   the dead unit, the unit of that record's side in the fight
   (calculator->info->sides[side].unit).
   Guest function: 0x00525FE0 map::BattleCalculator::GetDeadUnit(const ...) const. */
gaddr battle_dead_unit(Context *ctx, gaddr calculator, gaddr scene) {
    if (scene == 0)
        return 0;
    gaddr rec = guest_ptr(ctx, scene + B2_SCENE_NEXT);
    while (rec != 0) {
        uint32_t kind = guest_u8(ctx, rec + B2_SCENE_KIND);
        if (kind == 1 || kind == 4 || kind == 8 || kind == 9)
            return 0;
        if (kind == 7) {
            uint32_t side = guest_u8(ctx, rec + B2_SCENE_SIDE);
            gaddr info = READ_FIELD(ctx, BattleCalculator, calculator, info);
            return READ_FIELD(ctx, BattleSide, info + side * B2_SIDE_SIZE, unit);
        }
        rec = guest_ptr(ctx, rec + B2_SCENE_NEXT);
    }
    return 0;
}

/* How many strikes in a row a strike record starts: 0 when the record is
   missing or is not a strike (kind 1); else 1 plus every later strike record
   of the same side, until a record of another side or of kind 8 (or the end
   of the list). Records of the same side that are not strikes are passed
   over. The calculator is not read.
   Guest function: 0x0052603C map::BattleCalculator::GetAttackContinuousCount(...) const. */
int32_t battle_strike_run(Context *ctx, gaddr calculator, gaddr scene) {
    (void)calculator;
    if (scene == 0)
        return 0;
    if (guest_u8(ctx, scene + B2_SCENE_KIND) != 1)
        return 0;
    int32_t count = 1;
    gaddr rec = guest_ptr(ctx, scene + B2_SCENE_NEXT);
    while (rec != 0) {
        uint32_t kind = guest_u8(ctx, rec + B2_SCENE_KIND);
        if (kind == 8)
            break;
        /* the game reads both side bytes again for every record */
        if (guest_u8(ctx, rec + B2_SCENE_SIDE) != guest_u8(ctx, scene + B2_SCENE_SIDE))
            break;
        rec = guest_ptr(ctx, rec + B2_SCENE_NEXT);
        if (kind == 1)
            count++;
    }
    return count;
}

/* ------------------------------------------------------------------ one strike's damage */

static int skill_ready(Context *ctx) {
    return fe_static_ready(ctx, S_SpAstraGuard) && fe_static_ready(ctx, S_SpFangGuard) &&
           fe_static_ready(ctx, S_SpLunaGuard) && fe_static_ready(ctx, S_SpIgnisGuard) &&
           fe_static_ready(ctx, S_SpRendGuard) && fe_static_ready(ctx, S_SpVengeGuard) &&
           fe_static_ready(ctx, S_SpScaleGuard) && fe_static_ready(ctx, S_SpAegisGuard) &&
           fe_static_ready(ctx, S_SpPierceGuard);
}

/* Unit::GetAttack's caches (its stat bodies and, with the rank bonus, the
   weapon-exp limit): asked before the Dragon Fang guest call, so that override
   never gives up inside this one. */
static int attack_caches_ready(Context *ctx) {
    return unit_stat_caches_ready(ctx, B2_STAT_STR) && unit_stat_caches_ready(ctx, B2_STAT_MAG) &&
           fe_static_ready(ctx, S_B2ExpLimitGuardA) && fe_static_ready(ctx, S_B2ExpLimitGuardB) &&
           fe_static_ready(ctx, S_B2ExpLimitGuardC);
}

/* The damage one strike of `side` does to `other`, as the forecast shows it
   (skill 0) or as a strike with an activated skill (the skill's number):

     damage = own attack - the other's defense (resistance for a magic strike)
              - the other's defense bonus
       Luna: half the defense back (a quarter against Dragonskin)
       Dragon Fang: + half the attack (a quarter against Dragonskin)
       Vengeance: + the value passed in (half against Dragonskin)
       Astra: halved (35 %, rounded toward zero, against Dragonskin)
     then: the other's Dragonskin halves it (x 3/4 with a "pierces dragonskin"
     weapon), the other's "halve damage" bit halves it, the other's terrain
     halves and/or quarters it, an Attack Stance follower deals half, and a
     negative result is 0.

   Every halving is the game's arithmetic shift (rounds down). The other
   side's skill bits are its row of BattleSide.skill_bits (+0xE6, row 1 when
   the striking side is a follower).
   Guest function: 0x005253A8 map::BattleInfo::Side::GetSimplePower(const Side*,int,int) const. */
int32_t forecast_damage(Context *ctx, gaddr side, gaddr other, int32_t skill, int32_t vengeance) {
    if (!skill_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    int32_t astra = guest_s16(ctx, S_SpAstra), fang = guest_s16(ctx, S_SpFang);
    int32_t luna = guest_s16(ctx, S_SpLuna), ignis = guest_s16(ctx, S_SpIgnis);
    int32_t rend = guest_s16(ctx, S_SpRend), venge = guest_s16(ctx, S_SpVenge);
    /* Ignis and Rend Heaven read Str / Mag through getters with a stack argument */
    if (skill == ignis || skill == rend)
        return (int32_t)fe_use_original(ctx);
    if (skill == fang && !attack_caches_ready(ctx))
        return (int32_t)fe_use_original(ctx);

    if (READ_FIELD(ctx, BattleSide, side, item) == 0)
        return 0;
    uint32_t flags = READ_FIELD(ctx, BattleSide, side, flags);
    if (flags & B2_SIDE_FLAG_NO_DAMAGE)
        return 0;
    uint32_t row = b2_row_of(ctx, side);
    gaddr bits = FIELD_ADDR(BattleSide, other, skill_bits) + row * B2_SIDE_ROW_STRIDE;
    gaddr detail = FIELD_ADDR(BattleSide, other, detail) + row * (gaddr)sizeof(BattleDetail);
    gaddr guard = (flags & B2_SIDE_FLAG_MAGIC) ? FIELD_ADDR(BattleDetail, detail, resistance)
                                               : FIELD_ADDR(BattleDetail, detail, defense);
    int32_t attack = READ_FIELD(ctx, BattleSide, side, detail[0].attack);
    int32_t defense = guest_s32(ctx, guard);
    int32_t damage = fe_add32(attack, -defense);
    if (skill == luna)
        damage = fe_add32(damage, fe_asr(defense, b2_bit(ctx, bits, guest_s16(ctx, S_SpScale)) ? 2 : 1));
    damage = fe_add32(damage, -guest_s32(ctx, guard + 4u)); /* the bonus word after the stat */

    if (skill == fang) {
        int32_t triangle = READ_FIELD(ctx, BattleSide, side, triangle);
        gaddr unit = READ_FIELD(ctx, BattleSide, side, unit);
        int32_t att = (int32_t)guest_call3(ctx, B2_UnitGetAttack, unit, FIELD_ADDR(BattleSide, side, item),
                                           triangle < 0 ? 0u : 1u);
        if (fe_gave_up(ctx))
            return 0;
        damage = fe_add32(damage, fe_asr(att, b2_bit(ctx, bits, guest_s16(ctx, S_SpScale)) ? 2 : 1));
    }
    if (skill == venge)
        damage = fe_add32(damage, b2_bit(ctx, bits, guest_s16(ctx, S_SpScale)) ? fe_asr(vengeance, 1) : vengeance);
    if (skill == astra) {
        if (b2_bit(ctx, bits, guest_s16(ctx, S_SpScale)))
            damage = fe_mul32(damage, 35) / 100; /* rounds toward zero, as the game's multiply-high does */
        else
            damage = fe_asr(damage, 1);
    }

    if (b2_bit(ctx, bits, guest_s16(ctx, S_SpScale))) {
        gaddr data = guest_call1(ctx, B2_ItemToData, FIELD_ADDR(BattleSide, side, item));
        if (READ_FIELD(ctx, ItemData, data, flags) & guest_u64(ctx, S_SpPierceMask))
            damage = fe_asr(fe_mul32(damage, 3), 2);
        else
            damage = fe_asr(damage, 1);
    }
    if (b2_bit(ctx, bits, guest_s16(ctx, S_SpAegis)))
        damage = fe_asr(damage, 1);
    gaddr terrain = guest_ptr(ctx, other + B2_SIDE_TERRAIN);
    if (terrain != 0) {
        if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & B2_TERRAIN_ATTR_HALF)
            damage = fe_asr(damage, 1);
        if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & B2_TERRAIN_ATTR_QUARTER)
            damage = fe_asr(damage, 2);
    }
    return stance_follow_up_damage(ctx, side, damage);
}

/* ------------------------------------------------------------------ avoid and defense (helpers) */

/* Whether the side's terrain bonus counts for its unit (the shared test of
   CalculateDetailAvoid and CalculateDetailDefense): not when the terrain
   number (avoid or defense, the signed byte at `number_at` of the record) is
   negative on a tile with attribute bit 8 and the unit has the skill that
   lifts it; not on a bit-19 tile for a unit allied with force 0; not on a
   bit-20 tile for a unit allied with force 1. The game reads the side's
   terrain pointer again before each test. */
static int terrain_counts(Context *ctx, gaddr side, gaddr terrain, gaddr number_at, gaddr lift_skill) {
    int counts = 1;
    if ((READ_FIELD(ctx, TerrainTileData, terrain, attributes) & B2_TERRAIN_ATTR_LOCKPICK) &&
        guest_s8(ctx, terrain + number_at) < 0) {
        if (guest_call2(ctx, B2_UnitIsEquipSkill, READ_FIELD(ctx, BattleSide, side, unit),
                        (uint32_t)(int32_t)guest_s16(ctx, lift_skill)) != 0)
            counts = 0;
    }
    terrain = guest_ptr(ctx, side + B2_SIDE_TERRAIN);
    if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & B2_TERRAIN_ATTR_ALLY0) {
        gaddr force = READ_FIELD(ctx, Unit, READ_FIELD(ctx, BattleSide, side, unit), force);
        if (guest_call2(ctx, B2_ForceIsAllied, force, 0u) != 0)
            counts = 0;
    }
    terrain = guest_ptr(ctx, side + B2_SIDE_TERRAIN);
    if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & B2_TERRAIN_ATTR_ALLY1) {
        gaddr force = READ_FIELD(ctx, Unit, READ_FIELD(ctx, BattleSide, side, unit), force);
        if (guest_call2(ctx, B2_ForceIsAllied, force, 1u) != 0)
            return 0;
    }
    return counts;
}

/* The side's terrain when its bonus may count at all: none without a
   terrain or when the side's flag 0x10 is set. */
static gaddr side_terrain(Context *ctx, gaddr side) {
    gaddr terrain = guest_ptr(ctx, side + B2_SIDE_TERRAIN);
    if (terrain == 0 || (READ_FIELD(ctx, BattleSide, side, flags) & B2_SIDE_FLAG_NO_TERRAIN))
        return 0;
    return terrain;
}

/* The avoid the side gets against the other side's lead (or follower, row 1
   when the other side is a follower), as CalculateDetailAvoid stores it into
   BattleSide.detail[row].avoid (a halfword):

     avoid = the unit's avoid with its item (Unit::GetAvoid)
             + the terrain's avoid (when it counts, see terrain_counts)
             + three halfword bonus terms of the side (+0x13C of the row, +0xB0, +0x1F0)
     a negative result (as a signed halfword) is stored as 0.

   0 when either side has no unit. The game keeps the running value in that
   halfword, so the unit's avoid and the terrain step are cut to 16 bits the
   way the game reads them back; the last three additions are not.
   Guest function: helper of 0x003491F8 map::BattleInfo::Side::CalculateDetailAvoid(const Side*). */
uint32_t battle_detail_avoid(Context *ctx, gaddr side, gaddr other) {
    if (!fe_static_ready(ctx, S_DaSkillGuard))
        return fe_use_original(ctx);
    uint32_t row = b2_row_of(ctx, other);
    gaddr unit = READ_FIELD(ctx, BattleSide, side, unit);
    if (unit == 0 || READ_FIELD(ctx, BattleSide, other, unit) == 0)
        return 0;
    uint16_t avoid = (uint16_t)guest_call2(ctx, B2_UnitGetAvoid, unit, FIELD_ADDR(BattleSide, side, item));
    gaddr terrain = side_terrain(ctx, side);
    if (terrain != 0 && terrain_counts(ctx, side, terrain, offsetof(TerrainTileData, avoid), S_DaSkill)) {
        terrain = guest_ptr(ctx, side + B2_SIDE_TERRAIN);
        avoid = (uint16_t)(avoid + READ_FIELD(ctx, TerrainTileData, terrain, avoid));
    }
    uint32_t sum = (uint32_t)avoid + guest_u16(ctx, side + B2_SIDE_AVOID_A + row * B2_SIDE_ROW_STRIDE);
    sum += guest_u16(ctx, side + B2_SIDE_AVOID_B);
    sum += guest_u16(ctx, side + B2_SIDE_AVOID_C);
    int16_t result = (int16_t)(uint16_t)sum;
    return result < 0 ? 0u : (uint32_t)result;
}

/* The defense numbers the side gets against the other side's lead (row 0) or
   follower (row 1), as CalculateDetailDefense stores them into
   BattleSide.detail[row]: out[0] defense, out[1] defense bonus, out[2]
   resistance, out[3] resistance bonus.

     defense / resistance = the unit's own (Unit::GetDefImpl / GetMdefImpl with
                            its item; the caller passes them in), never below 0
     defense bonus    = side words +0x12C and +0x130 of the row, + side +0x1E8 and +0x1FC
     resistance bonus = side words +0x12C and +0x134 of the row, + side +0x1E8 and +0x1FC
     both bonuses     + the terrain's defense when it counts (see terrain_counts)

   All four are 0 when either side has no unit. The side record itself must
   be readable: the game stores into it.
   Guest function: helper of 0x00349CF0 map::BattleInfo::Side::CalculateDetailDefense(const Side*). */
void battle_detail_defense(Context *ctx, gaddr side, gaddr other, int32_t defense, int32_t resistance,
                           int32_t out[4]) {
    out[0] = out[1] = out[2] = out[3] = 0;
    if (!fe_static_ready(ctx, S_DdSkillGuard)) {
        fe_use_original(ctx);
        return;
    }
    uint32_t row = b2_row_of(ctx, other);
    gaddr unit = READ_FIELD(ctx, BattleSide, side, unit);
    if (unit == 0 || READ_FIELD(ctx, BattleSide, other, unit) == 0)
        return;
    gaddr bonus = side + B2_SIDE_BONUS_DEFENSE + row * B2_SIDE_ROW_STRIDE;
    int32_t extra = fe_add32(guest_s32(ctx, side + B2_SIDE_EXTRA_DEFENSE), guest_s32(ctx, side + B2_SIDE_EXTRA_DEFENSE2));
    int32_t def_bonus = fe_add32(fe_add32(guest_s32(ctx, bonus), guest_s32(ctx, bonus + 4u)), extra);
    int32_t res_bonus = fe_add32(fe_add32(guest_s32(ctx, bonus), guest_s32(ctx, bonus + 8u)), extra);
    gaddr terrain = side_terrain(ctx, side);
    if (terrain != 0 && terrain_counts(ctx, side, terrain, offsetof(TerrainTileData, defense), S_DdSkill)) {
        terrain = guest_ptr(ctx, side + B2_SIDE_TERRAIN);
        def_bonus = fe_add32(def_bonus, READ_FIELD(ctx, TerrainTileData, terrain, defense));
        terrain = guest_ptr(ctx, side + B2_SIDE_TERRAIN);
        res_bonus = fe_add32(res_bonus, READ_FIELD(ctx, TerrainTileData, terrain, defense));
    }
    out[0] = defense > 0 ? defense : 0;
    out[1] = def_bonus;
    out[2] = resistance > 0 ? resistance : 0;
    out[3] = res_bonus;
}

RECOMP_OVERRIDE(0x00525FE0) {
    FE_ENTRY(0x00525FE0, battle_dead_unit, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052603C) {
    FE_ENTRY(0x0052603C, battle_strike_run, FE_ARG(0), FE_ARG(1));
}
