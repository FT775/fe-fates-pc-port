/* May this class hold this kind of weapon (Fates Job::CanEquipFromSubKind).
   Plain-language description: docs/WHO_HOLDS.md.

   who_holds_can_equip_subkind is a reader: it stores nothing. The game's
   function fills five one-time caches of its own the first time it runs (a
   JobCategory bit found by name, each); the readable code gives up while any
   of them is cold, before it reads or calls anything else, so the game's own
   code fills them exactly as before.

   Not here: the buy action, Unit::ItemEquip (stores), Unit::CanItemUse
   (builds an object on its stack, docs/EQUIP_USE.md section 4). The callers
   (Unit::CanItemEquip, GameInfoViewer::GetWeaponLevelKind and the game's
   own) are unchanged.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/who_holds/tests/who_holds_diff.py. */

#include "who_holds.h"

/* Every one of the function's five caches is filled. */
static int caches_ready(Context *ctx) {
    return fe_static_ready(ctx, S_WhGuardDragon) && fe_static_ready(ctx, S_WhGuardBeast) &&
           fe_static_ready(ctx, S_WhGuardMonster) && fe_static_ready(ctx, S_WhGuardHumanoid) &&
           fe_static_ready(ctx, S_WhGuardTransform);
}

/* The class's category bits (JobData.category) include the cached bit at
   `mask`. The game reads the cache first, then the class's word, and keeps
   that word for a second test: it is handed back in *category. */
static int first_has(Context *ctx, gaddr mask, gaddr job, uint16_t *category) {
    uint16_t bit = guest_u16(ctx, mask);
    *category = READ_FIELD(ctx, JobData, job, category);
    return (bit & *category) != 0;
}

/* the second test on the same category word */
static int also_has(Context *ctx, gaddr mask, uint16_t category) {
    return (guest_u16(ctx, mask) & category) != 0;
}

/* May a unit of class `job` hold a weapon of sub-kind `sub`? 1 or 0.
     - Not a stone (the sub-kind record's kind, ItemSubKind::Get(sub)+1 read
       signed, is not 7): yes when the class's weapon-exp cap for that kind,
       the byte JobData.max_weapon_exp[kind], is not 0. The kind is not
       range-checked: the byte at class + 0x44 + kind is read for any kind.
     - A stone: one rule per sub-kind, on the class's category bits:
         14: dragon and does not transform     15: beast
         16: dragon and transforms             17: monster and not human-shaped
         18: human-shaped and a Nohr class     19: human-shaped and a Hoshido class
       Any other stone sub-kind: no.
   Guest function: 0x00524420 Job::CanEquipFromSubKind(ItemSubKind::Type) const. */
int32_t who_holds_can_equip_subkind(Context *ctx, gaddr job, int32_t sub) {
    if (!caches_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    gaddr record = guest_call1(ctx, WH_ItemSubKindGet, (uint32_t)sub);
    int32_t kind = guest_s8(ctx, FIELD_ADDR(ItemSubKindData, record, kind));
    if (kind != WH_KIND_STONE)
        return guest_u8(ctx, FIELD_ADDR(JobData, job, max_weapon_exp) + (gaddr)kind) != 0;
    uint16_t category;
    switch (sub) { /* the game's table covers 14 .. 19 (an unsigned sub - 14 < 6) */
    case WH_STONE_FIRST + 0:
        return first_has(ctx, S_WhMaskDragon, job, &category) && !also_has(ctx, S_WhMaskTransform, category);
    case WH_STONE_FIRST + 1:
        return first_has(ctx, S_WhMaskBeast, job, &category);
    case WH_STONE_FIRST + 2:
        return first_has(ctx, S_WhMaskDragon, job, &category) && also_has(ctx, S_WhMaskTransform, category);
    case WH_STONE_FIRST + 3:
        return first_has(ctx, S_WhMaskMonster, job, &category) && !also_has(ctx, S_WhMaskHumanoid, category);
    case WH_STONE_FIRST + 4:
        return first_has(ctx, S_WhMaskHumanoid, job, &category) &&
               READ_FIELD(ctx, JobData, job, origin) == WH_ORIGIN_NOHR;
    case WH_STONE_FIRST + 5:
        return first_has(ctx, S_WhMaskHumanoid, job, &category) &&
               READ_FIELD(ctx, JobData, job, origin) == WH_ORIGIN_HOSHIDO;
    default:
        return 0;
    }
}

RECOMP_OVERRIDE(0x00524420) {
    FE_ENTRY(0x00524420, who_holds_can_equip_subkind, FE_ARG(0), FE_ARG_S(1));
}
