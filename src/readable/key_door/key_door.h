/* Can this unit open a door (Fates Unit::CanKeyDoor): the declaration of
   src/readable/key_door/key_door.c, the guest functions it calls and the
   one-time cache it reads.

   Plain-language description (what the function decides): docs/KEY_DOOR.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declaration into include/readable/fe_functions.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_KEY_DOOR_KEY_DOOR_H
#define FE_KEY_DOOR_KEY_DOOR_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a callee keeps its own code; each is called exactly as the game calls it) */
#define KD_UnitIsEquipSkill 0x0052DD04u   /* Unit::IsEquipSkill(short) const -> 1 or 0 (readable: unit_has_skill) */
#define KD_UnitKeyItemIndex 0x00530BDCu   /* Unit::GetItemIndexKeyDoor(void) const -> the slot of an item that
                                             opens doors, or -1 */

/* ---- the one-time cache (read in the code on 2026-11-17). It holds the s16
   EquipSkill number of the skill ID "SEID_" + the lock-opening skill (the
   name is a literal right after the function), found by name the first time
   the function runs (EquipSkill::Get, then the record's +0x10 half-word); the
   game then stores it and never again. The readable code reads it only after
   the game filled it (bit 0 of the guard word) and gives up before anything
   else while it is cold. */
#define S_KeyDoorGuard 0x006D98F8u     /* Unit::CanKeyDoor (literal 0x006D9628 + 0x2D0) */
#define S_KeyDoorSkill 0x006D96A0u     /* s16, behind S_KeyDoorGuard (literal 0x006D9628 + 0x78) */

/* the answer of Unit::GetItemIndexKeyDoor when no carried item opens doors */
#define KD_NO_ITEM (-1)

/* ---- the readable function (override entry at the end of the file) */
int32_t key_door_unit_can_open(Context *ctx, gaddr unit);

#endif /* FE_KEY_DOOR_KEY_DOOR_H */
