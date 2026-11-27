/* Does this carried item add its bonus (Fates Unit::IsItemEnhanceHave).
   Plain-language description: docs/ITEM_ENHANCE.md.

   unit_item_enhance_have is a reader: it stores nothing. The game's function
   fills sixteen one-time caches of its own the first time it runs (six
   PersonFlag bits and nine ItemFlag bits, each found by its ID label, and the
   six "only for" bits ORed into one), and pushes three argument registers on
   its own stack. The readable code gives up while any of those caches is
   cold, or any cache the inlined Unit::CanItemEquip asks, before it reads or
   calls anything else, so the game's own code fills them exactly as before.

   Not here (docs/tracks/REWRITE_ORDER4.md row 5: "do not"): a new map to meet
   one bow, and the forge window.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/item_enhance/tests/item_enhance_diff.py. */

#include "item_enhance.h"

/* Every one of the function's sixteen caches is filled (asked in the game's
   order), and every cache unit_can_equip_item asks before it reads anything
   (its 21 own and the 9 of the overrides it calls; equip_use.c caches_ready). */
static int caches_ready(Context *ctx) {
    for (gaddr g = S_IeGuardFirst; g >= S_IeGuardLast; g -= S_IeGuardStep)
        if (!fe_static_ready(ctx, g))
            return 0;
    for (gaddr g = S_EuGuardFirst; g <= S_EuGuardLast; g += S_EuGuardStep)
        if (!fe_static_ready(ctx, g))
            return 0;
    return fe_static_ready(ctx, S_EuExpLimitGuardA) && fe_static_ready(ctx, S_EuExpLimitGuardB) &&
           fe_static_ready(ctx, S_EuExpLimitGuardC) && fe_static_ready(ctx, S_EuDownloadGuard) &&
           fe_static_ready(ctx, S_EuCatGuard0) && fe_static_ready(ctx, S_EuCatGuard1) &&
           fe_static_ready(ctx, S_EuCatGuard2) && fe_static_ready(ctx, S_EuCatGuard3) &&
           fe_static_ready(ctx, S_EuCatGuard4);
}

/* The six owners, in the game's order: the item's "only for" bit and the
   PersonFlag bit that owner's unit carries. */
static const struct {
    gaddr item_bit;
    gaddr person_bit;
} owners[IE_OWNERS] = {
    {S_IeAvatarOnly, S_IeAvatarFlag}, {S_IeTakumiOnly, S_IeTakumiFlag}, {S_IeRyomaOnly, S_IeRyomaFlag},
    {S_IeLeoOnly, S_IeLeoFlag},       {S_IeXanderOnly, S_IeXanderFlag}, {S_IeOpheliaOnly, S_IeOpheliaFlag},
};

/* The owner's own item in the owner's hands: the unit (its own, its
   Person's and its class's flag words ORed, read afresh) has the owner's
   PersonFlag bit, and either Unit.state_flags bit 28 is clear or
   Person::IsDownload says the Person is a download one. */
static int held_by_owner(Context *ctx, gaddr unit, gaddr person_bit) {
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    uint64_t flags = READ_FIELD(ctx, Unit, unit, private_flags);
    flags |= READ_FIELD(ctx, PersonData, person, flags);
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    flags |= READ_FIELD(ctx, JobData, job, flags);
    if ((flags & guest_u64(ctx, person_bit)) == 0)
        return 0;
    if ((READ_FIELD(ctx, Unit, unit, state_flags) & IE_UNIT_DOWNLOAD_ONLY) == 0)
        return 1;
    return guest_call1(ctx, IE_PersonIsDownload, person) != 0;
}

/* Does `item` (one of the unit's unit::Items) add its bonus while `unit`
   carries it? Nonzero for yes.
     - The item record (unit::Item::ToData) must have the "bonus while
       carried" ItemFlag bit, or, when `named_weapons` is not 0, the Fujin
       Yumi's or the Brynhildr's own bit; otherwise 0.
     - An item "only for" one of six owners (avatar, Takumi, Ryoma, Leo,
       Xander, Ophelia) counts at once (1) when that owner holds it
       (held_by_owner); the six are tried in that order.
     - Otherwise: 1 when the item's sub-kind (ItemSubKind::Get of the
       record's weapon_kind byte, signed) has kind 8; else the answer of
       Unit::CanItemEquip(unit, item, 1, 1), as it is.
   The record's flag word is read again for each owner after the first, as
   the game does. `named_weapons` is tested as a whole word.
   Guest function: 0x0052FB98 Unit::IsItemEnhanceHave(const unit::Item*,bool) const. */
uint32_t unit_item_enhance_have(Context *ctx, gaddr unit, gaddr item, uint32_t named_weapons) {
    if (!caches_ready(ctx))
        return fe_use_original(ctx);
    gaddr data = guest_call1(ctx, IE_ItemToData, item);
    uint64_t wanted = guest_u64(ctx, S_IeCarryBonus);
    if (named_weapons != 0)
        wanted |= guest_u64(ctx, S_IeFujinYumi) | guest_u64(ctx, S_IeBrynhildr);
    uint64_t flags = READ_FIELD(ctx, ItemData, data, flags);
    if ((flags & wanted) == 0)
        return 0;
    if ((flags & guest_u64(ctx, S_IeAnyOnly)) != 0) {
        for (int k = 0; k < IE_OWNERS; k++) {
            if (k > 0)
                flags = READ_FIELD(ctx, ItemData, data, flags);
            if ((flags & guest_u64(ctx, owners[k].item_bit)) != 0 && held_by_owner(ctx, unit, owners[k].person_bit))
                return 1;
        }
    }
    gaddr subkind = guest_call1(ctx, IE_ItemSubKindGet, (uint32_t)(int32_t)READ_FIELD(ctx, ItemData, data, weapon_kind));
    if (READ_FIELD(ctx, ItemSubKindData, subkind, kind) == IE_KIND_ALWAYS)
        return 1;
    return unit_can_equip_item(ctx, unit, item, 1u, 1u); /* the inlined tail branch: no guest call */
}

RECOMP_OVERRIDE(0x0052FB98) {
    FE_ENTRY(0x0052FB98, unit_item_enhance_have, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}
