/* Class change and seals: what kind of class change a seal item asks for,
   whether a unit's supports block the support-based class changes, a
   character's base class, which stat seal a fight side's unit applies, and
   (a helper) how a new stat seal merges with the one already there.
   Plain-language description: docs/CLASS_CHANGE.md.

   The four overrides are readers: they store nothing (F-017, F-021).
   seal_merged_value is the pure part of MergeSeal, which stores the merged
   byte: it returns that byte and writes nothing; it has no override marker.
   No function here reads a one-time cache, so none gives up on its own; a
   guest call that cannot finish makes it give up (the original runs).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/class_change/tests/class_change_diff.py. */

#include "class_change.h"

/* The kind of class change a class-change item asks for, from the item's
   signed kind byte (+0x40): 0 stays 0, 4 gives 2, 6 gives 3, every other value
   gives 1. Asked when the class-change step starts (GrowSequence::
   ClassChangeCalculate passes it to Unit::ClassChange) and by the two skill
   steps after it (BranchSkill acts only on 3). Which item is which kind is
   table data (the enumerator's switch, docs/CLASS_CHANGE.md section 2).
   Guest function: 0x001951B0 ClassChange::GetType(const Item*). */
uint32_t class_change_type(Context *ctx, gaddr item) {
    int8_t kind = guest_s8(ctx, item + CC_ITEM_KIND_BYTE);
    if (kind == 0)
        return 0;
    if (kind == 4)
        return 2;
    if (kind == 6)
        return 3;
    return 1;
}

/* Whether a unit's supports do not count for the support-based class changes
   (the Partner and Friendship Seal lists): only a unit with state bit 28 set
   (the same "download-only" bit the dragon-vein check reads) that is not a
   download person. A unit without the bit gives 0 without the guest call.
   Guest function: 0x00532D60 Unit::IsRelianceInvalidForClassChange(void) const. */
uint32_t unit_reliance_blocks_class_change(Context *ctx, gaddr unit) {
    if ((READ_FIELD(ctx, Unit, unit, state_flags) & CC_UNIT_DOWNLOAD_ONLY) == 0)
        return 0;
    uint32_t download = guest_call1(ctx, CC_PersonIsDownload, READ_FIELD(ctx, Unit, unit, person));
    return download == 0 ? 1u : 0u;
}

/* A character's base class number: the Person record's class (+0x2C), or,
   when that class is a promoted one (Job::IsHigh of its record), the record's
   unpromoted class (+0x2E). The class number is read again for the answer, as
   the game does. The Heart Seal list (the "parallel" classes), the child
   class inheritance and the unit packet ask it.
   Guest function: 0x0053E198 Person::GetLowJobIndex(void) const. */
uint32_t person_base_job_index(Context *ctx, gaddr person) {
    gaddr job = guest_call1(ctx, CC_JobGet, READ_FIELD(ctx, PersonData, person, job));
    if (guest_call1(ctx, CC_JobIsHigh, job) != 0)
        return READ_FIELD(ctx, PersonData, person, job_low);
    return READ_FIELD(ctx, PersonData, person, job);
}

/* One step of battle_seal_effect: when the unit has the skill of this label,
   the skill record (looked up a second time, as the game does); else 0. */
static gaddr seal_if_has(Context *ctx, gaddr unit, gaddr label) {
    gaddr skill = guest_call1(ctx, CC_EquipSkillGet, label);
    int16_t number = guest_s16(ctx, skill + CC_SKILL_INDEX);
    if (guest_call2(ctx, CC_UnitIsEquipSkill, unit, (uint32_t)(int32_t)number) == 0)
        return 0;
    return guest_call1(ctx, CC_EquipSkillGet, label);
}

/* Which stat seal the unit of one fight side applies with this strike: the
   skill record of the first seal skill it has, or 0.

   No seal at all while the sequence's skip word is set, its mode has bit 2 or
   13, its seal step is not active (that word is then the answer, 0), or either
   side's flag word of the strike has bit 10. Then, in this order: dragon curse,
   Seal Strength, Magic, Speed, Defense, Resistance; for side 0 only, "dirty
   fight" (unless the fight record's word +0x23C is above 0) and "clumsy" (only
   with bit 7 of side 0's strike word); a seal skill the unit has whose second
   lookup gives 0 is passed over. Last, from the side's own strike word: bit 15
   gives the ninja technique's record and bit 16 "ice blood"'s, whether the unit
   has the skill or not (the game tail-calls the lookup).
   Guest function: 0x00357120 map::SequenceBattle::(anonymous)::ProcSequence::
   GetSealEffect(map::BattleSide::Type). Asked by SetSeal (side 0, then side 1)
   and by the weakness effect steps of the map fight. */
gaddr battle_seal_effect(Context *ctx, gaddr sequence, uint32_t side) {
    static const gaddr first[] = {CC_SEID_DragonCurse, CC_SEID_SealStr, CC_SEID_SealMag,
                                  CC_SEID_SealSpd, CC_SEID_SealDef, CC_SEID_SealRes};
    if (guest_u32(ctx, sequence + CC_SEQ_SKIP) != 0)
        return 0;
    if (guest_u32(ctx, sequence + CC_SEQ_MODE) & CC_SEQ_MODE_NO_SEAL)
        return 0;
    uint32_t active = guest_u32(ctx, sequence + CC_SEQ_ACTIVE);
    if (active == 0)
        return 0;
    gaddr strike = guest_ptr(ctx, sequence + CC_SEQ_STRIKE);
    if (guest_u32(ctx, strike + CC_STRIKE_FLAGS) & CC_STRIKE_NO_SEAL)
        return 0;
    if (guest_u32(ctx, strike + CC_STRIKE_FLAGS + 4u) & CC_STRIKE_NO_SEAL)
        return 0;
    gaddr unit = guest_ptr(ctx, sequence + CC_SEQ_UNIT_OF_SIDE + side * 4u);
    for (size_t i = 0; i < sizeof first / sizeof first[0]; i++) {
        gaddr skill = seal_if_has(ctx, unit, first[i]);
        if (skill != 0)
            return skill;
    }
    if (side == 0) {
        gaddr fight = guest_ptr(ctx, sequence + CC_SEQ_FIGHT);
        if (guest_s32(ctx, fight + CC_FIGHT_DIRTY_OFF) <= 0) {
            gaddr skill = seal_if_has(ctx, unit, CC_SEID_DirtyFight);
            if (skill != 0)
                return skill;
        }
        strike = guest_ptr(ctx, sequence + CC_SEQ_STRIKE);
        if (guest_u32(ctx, strike + CC_STRIKE_FLAGS) & CC_STRIKE_CLUMSY) {
            gaddr skill = seal_if_has(ctx, unit, CC_SEID_Clumsy);
            if (skill != 0)
                return skill;
        }
    }
    strike = guest_ptr(ctx, sequence + CC_SEQ_STRIKE);
    uint32_t own = guest_u32(ctx, strike + side * 4u + CC_STRIKE_FLAGS);
    if (own & CC_STRIKE_NINJA)
        return guest_call1(ctx, CC_EquipSkillGet, CC_SEID_NinjaReturn);
    if (own & CC_STRIKE_ICE)
        return guest_call1(ctx, CC_EquipSkillGet, CC_SEID_IceBlood);
    return 0;
}

/* Helper (F-017): the byte MergeSeal stores for one stat of a seal block
   (Capability, one byte per stat; SetSeal passes a block on its own stack and
   the stat seal's amount). When the unit has the "chain of seals" skill the
   seals add up (the old byte read unsigned, plus the amount, cut to 8 bits);
   otherwise the larger of the old byte (read signed) and the amount counts.
   Returns that byte (0 .. 255) and writes nothing.
   Guest function: 0x00354D2C map::SequenceBattle::(anonymous)::(anonymous)::
   MergeSeal(Capability*,const Unit*,int,int), a writer (it stores the byte). */
uint32_t seal_merged_value(Context *ctx, gaddr capability, gaddr unit, int32_t stat, int32_t value) {
    gaddr skill = guest_call1(ctx, CC_EquipSkillGet, CC_SEID_SealChain);
    int16_t number = guest_s16(ctx, skill + CC_SKILL_INDEX);
    gaddr at = capability + (gaddr)stat;
    if (guest_call2(ctx, CC_UnitIsEquipSkill, unit, (uint32_t)(int32_t)number) != 0)
        return (uint8_t)((uint32_t)value + guest_u8(ctx, at));
    int32_t old = guest_s8(ctx, at);
    return (uint8_t)(old < value ? value : old);
}

RECOMP_OVERRIDE(0x001951B0) {
    FE_ENTRY(0x001951B0, class_change_type, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00532D60) {
    FE_ENTRY(0x00532D60, unit_reliance_blocks_class_change, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0053E198) {
    FE_ENTRY(0x0053E198, person_base_job_index, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00357120) {
    FE_ENTRY(0x00357120, battle_seal_effect, FE_ARG(0), FE_ARG(1));
}
