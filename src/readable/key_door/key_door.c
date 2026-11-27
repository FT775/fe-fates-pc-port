/* Can this unit open a door (Fates Unit::CanKeyDoor). Plain-language
   description: docs/KEY_DOOR.md.

   A reader: it stores nothing. The game's function fills one one-time cache
   of its own the first time it runs (the lock-opening skill's number, found
   by name); the readable code gives up while that cache is cold, before it
   reads or calls anything else, so the game's own code fills it exactly as
   before. The two questions it asks (does the unit have the skill, which
   carried item opens doors) stay the game's own functions, called as guests
   in the game's order: the item is asked only when the skill says no.

   Not here: Unit::IsMoveNear and Unit::IsEnemyInsideAttackArea (they store a
   move image), and the AI's door rule (src/readable/ai/ai_permission.c, not
   edited, still calls this function through the guest call).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/key_door/tests/key_door_diff.py. */

#include "key_door.h"

/* May this unit open doors? 1 or 0.
   Yes when it has the lock-opening skill, else when it carries an item that
   opens doors (any slot but "none").
   Guest function: 0x00529E20 Unit::CanKeyDoor(void) const. */
int32_t key_door_unit_can_open(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, S_KeyDoorGuard))
        return (int32_t)fe_use_original(ctx);
    int32_t skill = guest_s16(ctx, S_KeyDoorSkill);
    if (guest_call2(ctx, KD_UnitIsEquipSkill, unit, (uint32_t)skill) != 0)
        return 1;
    return (int32_t)guest_call1(ctx, KD_UnitKeyItemIndex, unit) != KD_NO_ITEM;
}

RECOMP_OVERRIDE(0x00529E20) {
    FE_ENTRY(0x00529E20, key_door_unit_can_open, FE_ARG(0));
}
