/* May this staff be used on that unit (Fates
   map::ItemHelper::Rod::(anonymous)::CanUseTarget).
   Plain-language description: docs/ROD_TARGET.md.

   rod_can_use_target is a reader: it stores nothing. The game's function
   fills thirteen one-time caches of its own the first time it runs (two
   PrivateSkill bits, eight ItemUse numbers and three EquipSkill numbers, each
   found by its ID label) and keeps the staff's eight stat amounts in a small
   buffer on its own stack. The readable code gives up while any cache is
   cold, before it reads or calls anything else, so the game's own code fills
   them exactly as before; the buffer is a local array here.

   Not here: AttackTo, the AI score bodies that call this function
   (docs/AI_SCORE.md, parked: they store), Random::GetValue.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/rod_target/tests/rod_target_diff.py. */

#include "rod_target.h"

/* Every one of the function's thirteen caches is filled, asked in the game's order. */
static int caches_ready(Context *ctx) {
    static const gaddr guards[] = {
        S_RtGuardNoMove, S_RtGuardNoWarp, S_RtGuardHeal,    S_RtGuardHealAll, S_RtGuardRescue,
        S_RtGuardDraw,   S_RtGuardWeakness, S_RtGuardFreeze, S_RtGuardSilence, S_RtGuardCurse,
        S_RtGuardResist, S_RtGuardImmune, S_RtGuardChain,
    };
    for (size_t i = 0; i < sizeof guards / sizeof guards[0]; i++)
        if (!fe_static_ready(ctx, guards[i]))
            return 0;
    return 1;
}

/* The staff in this item slot has the cached ItemUse number at `use`: the
   game asks unit::Item::ToData again for every test and compares the item
   record's byte +0x1B with the u16 number (all 16 bits). */
static int staff_is(Context *ctx, gaddr item, gaddr use) {
    gaddr data = guest_call1(ctx, RT_ItemToData, item);
    return READ_FIELD(ctx, ItemData, data, item_subkind) == guest_u16(ctx, use);
}

/* Unit::IsEquipSkill on the cached EquipSkill number at `number` (passed sign-extended, as the game's ldrsh). */
static int has_skill(Context *ctx, gaddr unit, gaddr number) {
    return guest_call2(ctx, RT_UnitHasSkill, unit, (uint32_t)(int32_t)guest_s16(ctx, number)) != 0;
}

/* heal and heal all: the target has lost HP (its maximum HP, GetMHPImpl(1, 0, 0), above its current HP). */
static int is_hurt(Context *ctx, gaddr target) {
    int32_t max_hp = (int32_t)guest_call(ctx, RT_UnitMaxHp, target, 1u, 0u, 0u);
    return max_hp > guest_s8(ctx, target + RT_UNIT_HP);
}

/* rescue and draw: the map allows it, and neither the "no move" nor the "no
   warp" bit is in the unit's own, its person's or its class's flags. The game
   reads all three flag words and the "no move" bit before the first test, and
   the "no warp" bit only after it passed. */
static int may_be_moved(Context *ctx, gaddr target) {
    gaddr situation = guest_ptr(ctx, G_Situation);
    if (READ_FIELD(ctx, Situation, situation, flags) & RT_SITUATION_NO_WARP)
        return 0;
    gaddr person = READ_FIELD(ctx, Unit, target, person);
    uint64_t flags = READ_FIELD(ctx, Unit, target, private_flags);
    flags |= READ_FIELD(ctx, PersonData, person, flags);
    gaddr job = READ_FIELD(ctx, Unit, target, job);
    flags |= READ_FIELD(ctx, JobData, job, flags);
    if (flags & guest_u64(ctx, S_RtMaskNoMove))
        return 0;
    return (flags & guest_u64(ctx, S_RtMaskNoWarp)) == 0;
}

/* weakness: the staff's eight amounts (the item record's extra_data, hp
   first) after the target's skills: all 0 with "status immunity", else
   halved (rounding down) with "status resistance", the hp amount never
   halved. With the user's "negative chain" any amount but hp above 0 is
   enough; otherwise one must be above what the target already has lost of
   that stat (Unit.debuff). */
static int weakness_takes(Context *ctx, gaddr user, gaddr item, gaddr target) {
    gaddr data = guest_call1(ctx, RT_ItemToData, item);
    int8_t amount[8];
    for (int stat = 0; stat < 8; stat++)
        amount[stat] = READ_FIELD(ctx, ItemData, data, extra_data[stat]);
    if (has_skill(ctx, target, S_RtSkillImmune)) {
        for (int stat = 0; stat < 8; stat++)
            amount[stat] = 0;
    } else if (has_skill(ctx, target, S_RtSkillResist)) {
        for (int stat = 1; stat < 8; stat++)
            amount[stat] = (int8_t)fe_asr(amount[stat], 1);
    }
    if (has_skill(ctx, user, S_RtSkillChain)) {
        for (int stat = 1; stat < 8; stat++)
            if (amount[stat] > 0)
                return 1;
        return 0;
    }
    for (int stat = 1; stat < 8; stat++)
        if (amount[stat] > READ_FIELD(ctx, Unit, target, debuff[stat]))
            return 1;
    return 0;
}

/* silence: the target has tome or staff experience above 0, or carries (in
   slot order) an item that Item::IsMagic calls magic and Unit::CanItemEquip
   (1, 1) lets it hold. */
static int casts_magic(Context *ctx, gaddr target) {
    if ((int32_t)guest_call2(ctx, RT_UnitWeaponExp, target, RT_KIND_TOME) > 0)
        return 1;
    if ((int32_t)guest_call2(ctx, RT_UnitWeaponExp, target, RT_KIND_STAFF) > 0)
        return 1;
    for (int slot = 0; slot < RT_ITEM_SLOTS; slot++) {
        gaddr item = FIELD_ADDR(Unit, target, items[slot]);
        gaddr data = guest_call1(ctx, RT_ItemToData, item);
        if (guest_call1(ctx, RT_ItemIsMagic, data) != 0 &&
            guest_call(ctx, RT_UnitCanEquipItem, target, item, 1u, 1u) != 0)
            return 1;
    }
    return 0;
}

/* May `user` use the staff in its item slot `slot` on `target`? 1 or 0.
     - No target: no.
     - A target allied to the army in Situation.force_index (Force::IsAllied
       on the target's force):
         heal, heal all: the target has lost HP
         rescue: the map and the target allow a move (may_be_moved)
         any other staff: no
     - Any other target:
         weakness: weakness_takes      draw: may_be_moved
         freeze, silence, curse: the target is not already frozen, silenced
           or cursed (Unit.conditions[0] bits); silence also needs a target
           that uses magic (casts_magic)
         any other staff: no
   The staff is the item record of unit::Item::ToData on user + 0x108 + 4 *
   slot (slot is not range-checked); the tests come in the game's order, and
   the first staff number that matches decides.
   Guest function: 0x0034AC30 map::ItemHelper::Rod::(anonymous)::CanUseTarget(const Unit*,int,Unit*). */
int32_t rod_can_use_target(Context *ctx, gaddr user, int32_t slot, gaddr target) {
    if (!caches_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    gaddr item = FIELD_ADDR(Unit, user, items) + ((gaddr)slot << 2);
    if (target == 0)
        return 0;
    gaddr situation = guest_ptr(ctx, G_Situation);
    uint8_t army = READ_FIELD(ctx, Situation, situation, force_index);
    if (guest_call2(ctx, RT_ForceIsAllied, READ_FIELD(ctx, Unit, target, force), army) != 0) {
        if (staff_is(ctx, item, S_RtUseHeal))
            return is_hurt(ctx, target);
        if (staff_is(ctx, item, S_RtUseHealAll))
            return is_hurt(ctx, target);
        if (staff_is(ctx, item, S_RtUseRescue))
            return may_be_moved(ctx, target);
        return 0;
    }
    if (staff_is(ctx, item, S_RtUseWeakness))
        return weakness_takes(ctx, user, item, target);
    if (staff_is(ctx, item, S_RtUseDraw))
        return may_be_moved(ctx, target);
    if (staff_is(ctx, item, S_RtUseFreeze))
        return (READ_FIELD(ctx, Unit, target, conditions[0]) & RT_COND_FROZEN) == 0;
    if (staff_is(ctx, item, S_RtUseSilence))
        return casts_magic(ctx, target) && (READ_FIELD(ctx, Unit, target, conditions[0]) & RT_COND_SILENCED) == 0;
    if (staff_is(ctx, item, S_RtUseCurse))
        return (READ_FIELD(ctx, Unit, target, conditions[0]) & RT_COND_CURSED) == 0;
    return 0;
}

RECOMP_OVERRIDE(0x0034AC30) {
    FE_ENTRY(0x0034AC30, rod_can_use_target, FE_ARG(0), FE_ARG_S(1), FE_ARG(2));
}
