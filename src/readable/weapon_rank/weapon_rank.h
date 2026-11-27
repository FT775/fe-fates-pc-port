/* Weapon rank, the part the triangle batch did not take (Fates classes Unit
   and the event script's anonymous_namespace): the declarations of
   src/readable/weapon_rank/weapon_rank.c, the guest functions it still calls,
   and the game's one-time caches it reads.

   Plain-language description (what each function decides): docs/WEAPON_RANK.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_WEAPON_RANK_WEAPON_RANK_H
#define FE_WEAPON_RANK_WEAPON_RANK_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-16: it stores nothing
   outside its own stack frame. Where the game calls a function (BL, or the
   one tail branch B below), the readable code makes the same guest call in
   the game's order with the game's arguments (docs/DECISIONS.md F-018), also
   when the callee is an override of an older batch. */
#define WR_UnitPoolGet 0x004F6174u        /* UnitPool::Get(int) -> the unit of a pool number (0 for 0); reads only */
#define WR_GameUserDataGet 0x001B3AFCu    /* GameUserData::Get(void) -> the word at 0x006DA248; reads only */
#define WR_WeaponLevelGet 0x001A80D4u     /* WeaponLevel::Get(void) (readable: weapon_level_record) */
#define WR_WeaponLevelGetLevel 0x005090A4u /* WeaponLevel::GetLevel(int) const (readable: weapon_rank_of_exp).
                                              UnitGetWeaponLevel reaches it by a tail branch (B), and the
                                              library enters the override there (lib code: CALL(override_
                                              0x005090A4), no copy of its code inside the caller), so this
                                              is a guest call too (docs/MOVE.md 9, the check for each batch) */
#define WR_UnitGetWeaponExp 0x0052DC54u   /* Unit::GetWeaponExp(ItemKind::Type) const (readable: unit_weapon_exp) */
#define WR_UnitGetWeaponExpLimit 0x0052F824u /* Unit::GetWeaponExpLimit(ItemKind::Type) const (readable:
                                                unit_weapon_exp_limit) */

/* ---- one-time caches (guard word, bit 0 = filled). Readable code reads a
   cached value only when its guard says it is filled and gives up otherwise,
   before reading anything else. */

/* Unit::GetWeaponExpLimit's own three caches (src/readable/battle/triangle.h
   S_ExpLimitGuardA..C). Its override gives up while one is cold; a function
   here that calls GetWeaponExp or GetWeaponExpLimit through the guest asks
   them first, so that override never gives up inside the call (a nested
   give-up). */
#define S_WrExpLimitGuardA 0x006D97B4u
#define S_WrExpLimitGuardB 0x006D97B0u
#define S_WrExpLimitGuardC 0x006D97ACu

/* Unit::GetWeaponExpForJobIntro (literal 0x006D9A28 - 0x26C and + 0x78) */
#define S_JobIntroGuard 0x006D97BCu
#define S_JobIntroStoneMask 0x006D9AA0u /* u64: one PersonFlag bit, looked up by the same SPID name as
                                           triangle.h's S_StoneLimitMask (compared byte for byte in the
                                           code; not copied): a unit, Person or class carrying it shows
                                           stone (kind 7) exp 0 [high for "same name", low for its meaning] */

/* ---- record fields this batch reads that config/readable/structs/ does
   not name (offsets read in the code on 2026-11-16). */
#define WR_SCRIPT_UNIT_MAX 250        /* UnitGetWeaponLevel: pool numbers 1 .. 250 only */
#define WR_FORCE_TYPE_ABSENT 9u       /* Force.type the script readers refuse (as veins.h FORCE_TYPE_NO_VEIN,
                                         skill_has.c) [low for what force 9 is] */
#define WR_KIND_STONE 7u              /* ItemKind: dragonstone and beaststone */
#define WR_KINDS 8                    /* weapon kinds, Unit.weapon_exp and PersonData.weapon_exp entries */
#define WR_PERSON_KIND_NO_FLOOR_A 1u  /* PersonData.unit_kind values that get no difficulty floor */
#define WR_PERSON_KIND_NO_FLOOR_B 3u  /*   [low for which units those are] */
#define WR_DIFFICULTY_HARD 1u         /* GameUserData.difficulty: floor = WeaponLevel threshold[3] */
#define WR_DIFFICULTY_LUNATIC 2u      /* GameUserData.difficulty: floor = WeaponLevel threshold[0] */
#define WR_FLOOR_RANK_HARD 3          /* threshold index read on hard (the rank C threshold) */
#define WR_FLOOR_RANK_LUNATIC 0       /* threshold index read on lunatic (the rank S threshold) */

/* ---- the readable functions (override entries at the end of the file) */
int32_t script_unit_weapon_rank(Context *ctx, gaddr script, int32_t unit_index, uint32_t kind, uint32_t capped);
int32_t unit_weapon_exp_for_job_intro(Context *ctx, gaddr unit, uint32_t kind);
/* helper (F-017): the pure part of Unit::CaclulateFirstWeaponExp, a writer; the eight bytes go to host memory */
void unit_first_weapon_exp(Context *ctx, gaddr unit, uint8_t out[WR_KINDS]);

#endif /* FE_WEAPON_RANK_WEAPON_RANK_H */
