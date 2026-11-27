/* One strike's damage (Fates class map::BattleInfo::Side): how hard one
   strike of a fight side hits the other side, with the attack and defense
   numbers the fight already worked out, the six damage skills, the other
   side's Dragonskin and "halve damage" skill bits, its terrain, and the
   Attack Stance follower's half.
   Plain-language description: docs/STRIKE.md.

   strike_power is the whole of map::BattleInfo::Side::GetSimplePower, a
   reader: it stores nothing into the game. The game's own code fills nine
   one-time caches at its start (skill numbers and an item flag looked up by
   name); the readable code gives up while one is cold, before reading
   anything else (the original runs and fills it). It calls the game's
   getters in the game's order with the game's arguments (docs/DECISIONS.md
   F-018); Unit::GetStrImpl and GetPowImpl take a fifth word on the guest
   stack and go through guest_call5 (its one store is in the dead stack,
   docs/READABLE.md section 17). Before each getter call it asks that getter's
   own caches, so no override gives up inside this one.

   It was first written as forecast_damage in src/readable/battle2/ (round 11),
   without the Ignis and Rend Heaven steps (no guest_call5 yet) and without a
   registry row. This file is the complete one and holds the row; the battle2
   copy is left as it was (new files only, docs/STRIKE.md section 5).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/strike/tests/strike_diff.py. */

#include "strike.h"

/* The detail row a side reads of the other side: row 1 (against a follower)
   when the striking side is a follower (type 2 or 3), else row 0. */
static uint32_t row_of(Context *ctx, gaddr side) {
    uint32_t type = READ_FIELD(ctx, BattleSide, side, side_type);
    return (type == 2 || type == 3) ? 1u : 0u;
}

/* Bit `bit` of a byte array (the game's `byte[bit >> 3] & 1 << (bit & 7)`,
   with the arithmetic shift a negative skill number gets). */
static int has_bit(Context *ctx, gaddr bytes, int32_t bit) {
    return (guest_u8(ctx, bytes + (gaddr)fe_asr(bit, 3)) & (1u << (bit & 7))) != 0;
}

/* Whether the other side's row has Dragonskin (the skill number is read from
   its cache each time, as the game does). */
static int has_skin(Context *ctx, gaddr bits) {
    return has_bit(ctx, bits, guest_s16(ctx, S_StScale));
}

static int own_caches_ready(Context *ctx) {
    return fe_static_ready(ctx, S_StAstraGuard) && fe_static_ready(ctx, S_StFangGuard) &&
           fe_static_ready(ctx, S_StLunaGuard) && fe_static_ready(ctx, S_StIgnisGuard) &&
           fe_static_ready(ctx, S_StRendGuard) && fe_static_ready(ctx, S_StVengeGuard) &&
           fe_static_ready(ctx, S_StScaleGuard) && fe_static_ready(ctx, S_StAegisGuard) &&
           fe_static_ready(ctx, S_StPierceGuard);
}

/* The caches of the getters a skill step calls: Item::IsMagic's, and
   Unit::GetStrImpl's and GetPowImpl's (Unit::GetAttack reads both stats'
   and, for its rank bonus, the weapon-exp limit's). */
static int stat_caches_ready(Context *ctx) {
    return fe_static_ready(ctx, S_StMagicGuard) && unit_stat_caches_ready(ctx, ST_STAT_STR) &&
           unit_stat_caches_ready(ctx, ST_STAT_MAG);
}

static int attack_caches_ready(Context *ctx) {
    return stat_caches_ready(ctx) && fe_static_ready(ctx, S_StExpLimitGuardA) &&
           fe_static_ready(ctx, S_StExpLimitGuardB) && fe_static_ready(ctx, S_StExpLimitGuardC);
}

/* A stat through Unit::GetStrImpl / GetPowImpl with extras and losses on and
   rally kind 0 (the fifth word), as the game asks it here. */
static int32_t stat_of(Context *ctx, gaddr getter, gaddr unit, gaddr item) {
    return (int32_t)guest_call5(ctx, getter, unit, item, 1u, 1u, 0u);
}

/* Whether the striking side's weapon is magic (Item::IsMagic of its record). */
static int weapon_is_magic(Context *ctx, gaddr side) {
    gaddr data = guest_call1(ctx, ST_ItemToData, FIELD_ADDR(BattleSide, side, item));
    return guest_call1(ctx, ST_ItemIsMagic, data) != 0;
}

/* The damage one strike of `side` does to `other`, as the forecast shows it
   (skill 0) or as a strike with an activated skill (the skill's number):

     0 when the side holds no item, or its "no damage" flag (0x40) is set.
     damage = own attack - the other's defense (its resistance when the side's
              flag 0x20 says the strike is magic) - the matching bonus
       Luna:        + half the defense back (a quarter against Dragonskin)
       Dragon Fang: + half of Unit::GetAttack (a quarter against Dragonskin)
       Ignis:       + half of the own Str for a magic weapon, of the own Mag
                    otherwise (a quarter against Dragonskin)
       Rend Heaven: + half of the other's Mag for a magic weapon, of its Str
                    otherwise (a quarter against Dragonskin)
       Vengeance:   + the value passed in (half against Dragonskin)
       Astra:       halved (x 35 / 100, toward zero, against Dragonskin)
     then: the other's Dragonskin halves it (x 3/4 with a "pierces Dragonskin"
     weapon), the other's "halve damage" bit halves it, the other's terrain
     halves and/or quarters it, an Attack Stance follower deals half, and a
     result below 0 is 0.

   The skill tests are separate ifs in the game's order, so a skill number
   that two caches share takes both steps. Every halving is the game's
   arithmetic shift (rounds down, also for a negative number). The other
   side's skill bits are its row of BattleSide.skill_bits (+0xE6, row 1 when
   the striking side is a follower).
   Guest function: 0x005253A8 map::BattleInfo::Side::GetSimplePower(const Side*,int,int) const. */
int32_t strike_power(Context *ctx, gaddr side, gaddr other, int32_t skill, int32_t vengeance) {
    if (!own_caches_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    int32_t astra = guest_s16(ctx, S_StAstra), fang = guest_s16(ctx, S_StFang);
    int32_t ignis = guest_s16(ctx, S_StIgnis), rend = guest_s16(ctx, S_StRend);
    /* the getters a skill step calls must not give up inside this function */
    if ((skill == ignis || skill == rend) && !stat_caches_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    if (skill == fang && !attack_caches_ready(ctx))
        return (int32_t)fe_use_original(ctx);

    if (READ_FIELD(ctx, BattleSide, side, item) == 0)
        return 0;
    uint32_t flags = READ_FIELD(ctx, BattleSide, side, flags);
    if (flags & ST_SIDE_FLAG_NO_DAMAGE)
        return 0;
    uint32_t row = row_of(ctx, side);
    gaddr bits = FIELD_ADDR(BattleSide, other, skill_bits) + row * ST_SIDE_ROW_STRIDE;
    gaddr detail = FIELD_ADDR(BattleSide, other, detail) + row * (gaddr)sizeof(BattleDetail);
    gaddr guard = (flags & ST_SIDE_FLAG_MAGIC) ? FIELD_ADDR(BattleDetail, detail, resistance)
                                               : FIELD_ADDR(BattleDetail, detail, defense);
    int32_t attack = READ_FIELD(ctx, BattleSide, side, detail[0].attack);
    int32_t defense = guest_s32(ctx, guard);
    int32_t damage = fe_add32(attack, -defense);
    if (skill == guest_s16(ctx, S_StLuna))
        damage = fe_add32(damage, fe_asr(defense, has_skin(ctx, bits) ? 2 : 1));
    damage = fe_add32(damage, -guest_s32(ctx, guard + 4u)); /* the bonus word after the stat */

    if (skill == fang) {
        int32_t triangle = READ_FIELD(ctx, BattleSide, side, triangle);
        gaddr unit = READ_FIELD(ctx, BattleSide, side, unit);
        /* GetAttack's bool (the rank bonus) is off only at a triangle disadvantage */
        int32_t att = (int32_t)guest_call3(ctx, ST_UnitGetAttack, unit, FIELD_ADDR(BattleSide, side, item),
                                           triangle < 0 ? 0u : 1u);
        if (fe_gave_up(ctx))
            return 0;
        damage = fe_add32(damage, fe_asr(att, has_skin(ctx, bits) ? 2 : 1));
    }
    if (skill == ignis) {
        /* the attack stat the weapon does not use: Str for a magic weapon, Mag otherwise */
        int magic = weapon_is_magic(ctx, side);
        gaddr unit = READ_FIELD(ctx, BattleSide, side, unit);
        int32_t stat = stat_of(ctx, magic ? ST_UnitGetStrImpl : ST_UnitGetPowImpl, unit,
                               FIELD_ADDR(BattleSide, side, item));
        if (fe_gave_up(ctx))
            return 0;
        damage = fe_add32(damage, fe_asr(stat, has_skin(ctx, bits) ? 2 : 1));
    }
    if (skill == rend) {
        /* the foe's stat that matches the striking weapon (Mag for a magic one), with the foe's own item;
           the game tests Dragonskin before this call */
        int magic = weapon_is_magic(ctx, side);
        int skin = has_skin(ctx, bits);
        gaddr foe = READ_FIELD(ctx, BattleSide, other, unit);
        int32_t stat = stat_of(ctx, magic ? ST_UnitGetPowImpl : ST_UnitGetStrImpl, foe,
                               FIELD_ADDR(BattleSide, other, item));
        if (fe_gave_up(ctx))
            return 0;
        damage = fe_add32(damage, fe_asr(stat, skin ? 2 : 1));
    }
    if (skill == guest_s16(ctx, S_StVenge))
        damage = fe_add32(damage, has_skin(ctx, bits) ? fe_asr(vengeance, 1) : vengeance);
    if (skill == astra) {
        if (has_skin(ctx, bits))
            damage = fe_mul32(damage, ST_ASTRA_SKIN_PERCENT) / 100; /* toward zero, as the multiply-high does */
        else
            damage = fe_asr(damage, 1);
    }

    if (has_skin(ctx, bits)) {
        gaddr data = guest_call1(ctx, ST_ItemToData, FIELD_ADDR(BattleSide, side, item));
        if (READ_FIELD(ctx, ItemData, data, flags) & guest_u64(ctx, S_StPierceMask))
            damage = fe_asr(fe_mul32(damage, 3), 2);
        else
            damage = fe_asr(damage, 1);
    }
    if (has_bit(ctx, bits, guest_s16(ctx, S_StAegis)))
        damage = fe_asr(damage, 1);
    gaddr terrain = guest_ptr(ctx, other + ST_SIDE_TERRAIN); /* read once; its attributes twice */
    if (terrain != 0) {
        if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & ST_TERRAIN_ATTR_HALF)
            damage = fe_asr(damage, 1);
        if (READ_FIELD(ctx, TerrainTileData, terrain, attributes) & ST_TERRAIN_ATTR_QUARTER)
            damage = fe_asr(damage, 2);
    }
    return stance_follow_up_damage(ctx, side, damage);
}

RECOMP_OVERRIDE(0x005253A8) {
    FE_ENTRY(0x005253A8, strike_power, FE_ARG(0), FE_ARG(1), FE_ARG_S(2), FE_ARG_S(3));
}
