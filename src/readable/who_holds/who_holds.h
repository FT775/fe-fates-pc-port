/* May this class hold this kind of weapon (Fates Job::CanEquipFromSubKind):
   the declarations of src/readable/who_holds/who_holds.c and the guest
   functions and one-time caches it reads.

   Plain-language description (what the function decides): docs/WHO_HOLDS.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_WHO_HOLDS_WHO_HOLDS_H
#define FE_WHO_HOLDS_WHO_HOLDS_H

#include "fe.h"

/* ---- guest function called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Read on 2026-11-17: it stores nothing. The
   readable code makes the same call in the game's order with the game's
   argument (docs/DECISIONS.md F-018). */
#define WH_ItemSubKindGet 0x0019B97Cu /* ItemSubKind::Get(int) (readable: item_subkind_record) */

/* ---- the function's five one-time caches (read in the code on 2026-11-17).
   Each holds 1 << (the index of a JobCategory ID), found by name the first
   time the function runs; the game then stores the u16 and never again. The
   readable code reads them only after the game filled them (bit 0 of the
   guard word), and gives up before anything else while one is cold. The game
   asks the guards in this order: */
#define S_WhGuardDragon 0x006D39D0u     /* JCID_ "manakete" (dragon blood) */
#define S_WhGuardBeast 0x006D39CCu      /* JCID_ "laguz" (beast) */
#define S_WhGuardMonster 0x006D39C8u    /* JCID_ "mamono" (monster) */
#define S_WhGuardHumanoid 0x006D39C4u   /* JCID_ "hitogata" (human shape) */
#define S_WhGuardTransform 0x006D39C0u  /* JCID_ "henshin" (transforms) */
#define S_WhMaskDragon 0x006D3994u      /* u16 category bit, behind S_WhGuardDragon */
#define S_WhMaskBeast 0x006D3996u       /* u16, behind S_WhGuardBeast */
#define S_WhMaskMonster 0x006D3998u     /* u16, behind S_WhGuardMonster */
#define S_WhMaskHumanoid 0x006D399Au    /* u16, behind S_WhGuardHumanoid */
#define S_WhMaskTransform 0x006D399Cu   /* u16, behind S_WhGuardTransform */

/* ---- the one kind with its own rules, and its six sub-kinds (read in the
   code on 2026-11-17) */
#define WH_KIND_STONE 7        /* ItemKind: dragonstones and beaststones */
#define WH_STONE_FIRST 14      /* ItemSubKind numbers 14 .. 19 have a rule each; other stone sub-kinds: no */
#define WH_STONE_COUNT 6
#define WH_ORIGIN_HOSHIDO 1    /* JobData.origin (docs/ROUTES.md) */
#define WH_ORIGIN_NOHR 2

/* ---- the readable function (override entry at the end of the file) */
int32_t who_holds_can_equip_subkind(Context *ctx, gaddr job, int32_t sub);

#endif /* FE_WHO_HOLDS_WHO_HOLDS_H */
