/* May this staff be used on that unit (Fates
   map::ItemHelper::Rod::(anonymous)::CanUseTarget): the declarations of
   src/readable/rod_target/rod_target.c and the guest functions and one-time
   caches it reads.

   Plain-language description (what the function decides): docs/ROD_TARGET.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_ROD_TARGET_ROD_TARGET_H
#define FE_ROD_TARGET_ROD_TARGET_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each is a readable override already and stores
   nothing; the readable code makes the same calls in the game's order with
   the game's arguments (docs/DECISIONS.md F-018). */
#define RT_ItemToData 0x003D0EA4u       /* unit::Item::ToData() const (readable: item_to_data) */
#define RT_ForceIsAllied 0x0053C3E0u    /* Force::IsAllied(Force::Type) const (force_is_allied) */
#define RT_UnitMaxHp 0x0052A364u        /* Unit::GetMHPImpl(bool,bool,EnhanceDefinition::Type) const (unit_max_hp) */
#define RT_UnitHasSkill 0x0052DD04u     /* Unit::IsEquipSkill(short) const (unit_has_skill) */
#define RT_UnitWeaponExp 0x0052DC54u    /* Unit::GetWeaponExp(ItemKind::Type) const (unit_weapon_exp) */
#define RT_ItemIsMagic 0x005290B8u      /* Item::IsMagic() const (item_is_magic) */
#define RT_UnitCanEquipItem 0x0052C634u /* Unit::CanItemEquip(const unit::Item*,bool,bool) const (unit_can_equip_item) */

/* ---- the function's thirteen one-time caches (read in the code on
   2026-11-17). Each is found by its ID label the first time the function
   runs; the game then stores it and never again. The readable code reads them
   only after the game filled them (bit 0 of the guard word), and gives up
   before anything else while one is cold. The game asks the guards in this
   order; the values behind them follow. */
#define S_RtGuardNoMove 0x006D74C0u   /* SPID_ "no move": u64 1 << PrivateSkill index */
#define S_RtGuardNoWarp 0x006D74BCu   /* SPID_ "no warp": u64 */
#define S_RtGuardHeal 0x006D74B8u     /* IUID_ "heal": u16 ItemUse number */
#define S_RtGuardHealAll 0x006D74B4u  /* IUID_ "heal all" */
#define S_RtGuardRescue 0x006D74B0u   /* IUID_ "rescue" */
#define S_RtGuardDraw 0x006D74ACu     /* IUID_ "draw" (pull the unit next to the user) */
#define S_RtGuardWeakness 0x006D74A8u /* IUID_ "weakness" (lowers stats) */
#define S_RtGuardFreeze 0x006D74A4u   /* IUID_ "freeze" */
#define S_RtGuardSilence 0x006D74A0u  /* IUID_ "silence" */
#define S_RtGuardCurse 0x006D749Cu    /* IUID_ "curse" */
#define S_RtGuardResist 0x006D7498u   /* SEID_ "status resistance": s16 EquipSkill number (record +0x10) */
#define S_RtGuardImmune 0x006D7494u   /* SEID_ "status immunity" */
#define S_RtGuardChain 0x006D7490u    /* SEID_ "negative chain" */

#define S_RtMaskNoMove 0x006D7550u    /* u64, behind S_RtGuardNoMove */
#define S_RtMaskNoWarp 0x006D7558u    /* u64, behind S_RtGuardNoWarp */
#define S_RtUseHeal 0x006D7450u       /* u16, behind S_RtGuardHeal */
#define S_RtUseHealAll 0x006D7452u
#define S_RtUseRescue 0x006D7454u
#define S_RtUseDraw 0x006D7456u
#define S_RtUseWeakness 0x006D7458u
#define S_RtUseFreeze 0x006D745Au
#define S_RtUseSilence 0x006D745Cu
#define S_RtUseCurse 0x006D745Eu
#define S_RtSkillResist 0x006D7460u   /* s16, behind S_RtGuardResist */
#define S_RtSkillImmune 0x006D7462u
#define S_RtSkillChain 0x006D7464u

/* ---- fields and bits read in the code (2026-11-17); not yet in
   config/readable/structs (new files only in this batch) */
#define RT_UNIT_HP 0xF3u                 /* s8: current HP (sheet.h UNIT_HP) */
#define RT_SITUATION_NO_WARP 0x08000000u /* Situation.flags bit 27: no rescue or draw on this map [low for the meaning] */
#define RT_COND_FROZEN 0x02u             /* Unit.conditions[0] bits: freeze answers no when set */
#define RT_COND_SILENCED 0x08u           /* silence answers no when set */
#define RT_COND_CURSED 0x20u             /* curse answers no when set */
#define RT_KIND_TOME 5                   /* ItemKind numbers asked by the silence rule */
#define RT_KIND_STAFF 6
#define RT_ITEM_SLOTS 5                  /* Unit.items */

/* ---- the readable function (override entry at the end of the file) */
int32_t rod_can_use_target(Context *ctx, gaddr user, int32_t slot, gaddr target);

#endif /* FE_ROD_TARGET_ROD_TARGET_H */
