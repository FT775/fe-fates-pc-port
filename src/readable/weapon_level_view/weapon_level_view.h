/* The weapon-rank line of the unit screen (Fates GameInfoViewer): the
   declarations of src/readable/weapon_level_view/weapon_level_view.c and the
   guest functions it still calls.

   Plain-language description (what the function decides): docs/WEAPON_LEVEL_VIEW.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_WEAPON_LEVEL_VIEW_WEAPON_LEVEL_VIEW_H
#define FE_WEAPON_LEVEL_VIEW_WEAPON_LEVEL_VIEW_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-17: it stores nothing, or
   only fills a one-time cache of its own. Where the game calls a function
   (BL), the readable code makes the same guest call in the game's order with
   the game's arguments (docs/DECISIONS.md F-018), also when the callee is an
   override of an older batch. */
#define WLV_UnitGetWeaponExp 0x0052DC54u     /* Unit::GetWeaponExp(ItemKind::Type) const (readable: unit_weapon_exp;
                                                gives up while GetWeaponExpLimit's caches are cold) */
#define WLV_ItemSubKindGet 0x0019B97Cu       /* ItemSubKind::Get(int) (readable: item_subkind_record) */
#define WLV_JobCanEquipFromSubKind 0x00524420u /* Job::CanEquipFromSubKind(ItemSubKind::Type) const (not rewritten;
                                                  as src/readable/equip_use/equip_use.h) */

/* ---- the caches of the override it calls (asked first, so a cold one never
   makes Unit::GetWeaponExp's override give up inside this one) */
#define S_WlvExpLimitGuardA 0x006D97B4u      /* src/readable/battle/triangle.h S_ExpLimitGuardA .. C */
#define S_WlvExpLimitGuardB 0x006D97B0u
#define S_WlvExpLimitGuardC 0x006D97ACu

/* ---- loop bounds and the one kind with an extra test (read in the code
   on 2026-11-17) */
#define WLV_KINDS 8          /* weapon kinds 0 .. 7, asked in order */
#define WLV_SUBKINDS 21      /* ItemSubKind numbers 0 .. 20 searched for each kind */
#define WLV_KIND_STONE 7     /* ItemKind: dragonstone and beaststone; the class must be able to use the sub-kind */
#define WLV_NONE (-1)        /* the answer when there is no such line */

/* ---- the readable function (override entry at the end of the file) */
int32_t weapon_level_view_kind(Context *ctx, gaddr unit, int32_t line);

#endif /* FE_WEAPON_LEVEL_VIEW_WEAPON_LEVEL_VIEW_H */
