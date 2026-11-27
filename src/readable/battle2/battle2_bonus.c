/* Battle numbers, second batch: bonuses that feed a unit's stats and the
   healing a staff does (Fates classes Unit, unit::Edit, unit::Enhance).
   Plain-language description: docs/BATTLE2.md section 5.

   All are readers: they store nothing. unit_has_rally_stat_skill reads
   one-time caches the game fills the first time; it gives up while one is
   cold, before reading anything else. Guest calls left: the ones the game makes
   (battle2.h), in the game's order (docs/DECISIONS.md F-018).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/battle2/tests/battle2_diff.py. */

#include "battle2.h"

/* The unit::Item in slot `slot` (0 .. 4) of the unit. */
static gaddr slot_item(gaddr unit, uint32_t slot) {
    return FIELD_ADDR(Unit, unit, items) + slot * 4u;
}

/* What the unit's carried items add to one stat (stat 0 .. 7: HP, Str, Mag,
   Skl, Spd, Lck, Def, Res): for each of the five slots whose item's bonus
   applies to the unit (Unit::IsItemEnhanceHave, asked with "false"), the
   item record's signed byte extra_data[stat] (+0x40). The stat is not
   range-checked. The stat getters (formula and sheet batches) call this for
   every stat they read.
   Guest function: 0x0033A790 anonymous_namespace::GetEnhanceHave(const Unit*,int). */
int32_t unit_item_stat_bonus(Context *ctx, gaddr unit, int32_t stat) {
    int32_t total = 0;
    for (uint32_t slot = 0; slot < 5u; slot++) {
        gaddr item = slot_item(unit, slot);
        if (guest_call3(ctx, B2_UnitIsItemEnhanceHave, unit, item, 0u) != 0) {
            gaddr data = guest_call1(ctx, B2_ItemToData, item);
            total = fe_add32(total, guest_s8(ctx, data + (gaddr)stat + B2_ITEM_EXTRA));
        }
    }
    return total;
}

/* The Personality record of a boon or bane number (Personality::Get: the
   table at G_PersonalityTable, 0x40 bytes a record; no range check). */
static gaddr personality(Context *ctx, uint32_t index) {
    return guest_ptr(ctx, B2_G_PersonalityTable) + index * (gaddr)sizeof(PersonalityData);
}

/* What the avatar's boon and bane add to one base stat: the boon record's
   boon_base[stat] plus the bane record's bane_base[stat] (signed bytes; the
   stat is not range-checked). The stat getters call this for the avatar.
   Guest function: 0x0053ABEC unit::Edit::GetCapability(int) const. */
int32_t edit_stat_bonus(Context *ctx, gaddr edit, int32_t stat) {
    gaddr boon = personality(ctx, READ_FIELD(ctx, UnitEdit, edit, boon));
    gaddr bane = personality(ctx, READ_FIELD(ctx, UnitEdit, edit, bane));
    return fe_add32(guest_s8(ctx, FIELD_ADDR(PersonalityData, boon, boon_base) + (gaddr)stat),
                    guest_s8(ctx, FIELD_ADDR(PersonalityData, bane, bane_base) + (gaddr)stat));
}

/* Whether a unit's enhance record (the rally bits) holds the rally of one
   stat at a given strength: stat 1 .. 10 maps to bit stat + 22 (cut to a
   byte) of the record; a rally value above 2 never counts (above 4 for stat
   31, which the first test already refuses: (31 + 22) is not a rally bit, so
   that branch is never taken). Unit::CanItemUse asks this before a rally
   item is used.
   Guest function: 0x0041B38C unit::Enhance::TstCheerFromCapabilityIndex(int,int) const. */
uint32_t enhance_has_rally_bonus(Context *ctx, gaddr enhance, int32_t stat, int32_t value) {
    uint32_t bit = ((uint32_t)stat + 22u) & 0xFFu;
    if (bit - 23u > 9u)
        return 0;
    if (value > (stat == 31 ? 4 : 2))
        return 0;
    return (guest_u8(ctx, enhance + (bit >> 3)) & (1u << (bit & 7u))) != 0 ? 1u : 0u;
}

static int rally_ready(Context *ctx) {
    for (uint32_t i = 0; i < B2_RALLY_SKILLS; i++)
        if (!fe_static_ready(ctx, S_RallyGuard0 - 4u * i))
            return 0;
    return 1;
}

/* Whether the unit has one of the nine stat rally skills (asked in a fixed
   order through Unit::IsEquipSkill; the first it has answers 1).
   Unit::HasCheerSkill (the skills batch's unit_has_rally_skill) and the AI's
   move enumeration ask this.
   Guest function: 0x00532124 Unit::HasCheerSkillCapability(void) const. */
uint32_t unit_has_rally_stat_skill(Context *ctx, gaddr unit) {
    if (!rally_ready(ctx))
        return fe_use_original(ctx);
    for (uint32_t i = 0; i < B2_RALLY_SKILLS; i++) {
        int32_t skill = guest_s16(ctx, S_RallySkills + 2u * i);
        if (guest_call2(ctx, B2_UnitIsEquipSkill, unit, (uint32_t)skill) != 0)
            return 1;
    }
    return 0;
}

RECOMP_OVERRIDE(0x0033A790) {
    FE_ENTRY(0x0033A790, unit_item_stat_bonus, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0053ABEC) {
    FE_ENTRY(0x0053ABEC, edit_stat_bonus, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0041B38C) {
    FE_ENTRY(0x0041B38C, enhance_has_rally_bonus, FE_ARG(0), FE_ARG_S(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x00532124) {
    FE_ENTRY(0x00532124, unit_has_rally_stat_skill, FE_ARG(0));
}
