/* May this unit hold this item (Fates Unit::CanItemEquip): the declarations
   of src/readable/equip_use/equip_use.c, the guest functions it still calls
   and the game's one-time caches it reads.

   Plain-language description (what the function decides): docs/EQUIP_USE.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_EQUIP_USE_EQUIP_USE_H
#define FE_EQUIP_USE_EQUIP_USE_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-16: it stores nothing, or
   only fills a one-time cache of its own. Where the game calls a function
   (BL), the readable code makes the same guest call in the game's order with
   the game's arguments (docs/DECISIONS.md F-018), also when the callee is an
   override of an older batch. */
#define EU_ItemToData 0x003D0EA4u          /* unit::Item::ToData(void) const (readable: item_to_data) */
#define EU_ItemSubKindGet 0x0019B97Cu      /* ItemSubKind::Get(int) (readable: item_subkind_record) */
#define EU_UnitGetWeaponExpLimit 0x0052F824u /* Unit::GetWeaponExpLimit(ItemKind::Type) const
                                                (readable: unit_weapon_exp_limit; three one-time caches) */
#define EU_JobCanEquipFromSubKind 0x00524420u /* Job::CanEquipFromSubKind(ItemSubKind::Type) const (not rewritten) */
#define EU_PersonIsDownload 0x0053DFECu    /* Person::IsDownload(void) const (readable: person_is_download;
                                              one one-time cache) */
#define EU_UnitGetCategory 0x0052B728u     /* Unit::GetCategory(void) const (readable: unit_category;
                                              five one-time caches) */
#define EU_UnitIsEquipSkill 0x0052DD04u    /* Unit::IsEquipSkill(short) const (readable: unit_has_skill) */
#define EU_UnitIsFemale 0x00533938u        /* Unit::IsFemale(void) const (not rewritten) */

/* ---- the caches of the overrides it calls (asked first, so a cold one never
   makes the inner override give up inside this one; docs/ITEM.md section 5) */
#define S_EuExpLimitGuardA 0x006D97B4u     /* src/readable/battle/triangle.h S_ExpLimitGuardA */
#define S_EuExpLimitGuardB 0x006D97B0u
#define S_EuExpLimitGuardC 0x006D97ACu
#define S_EuDownloadGuard 0x006D3B3Cu      /* src/readable/map/veins.h S_DownloadGuard */
#define S_EuCatGuard0 0x006D97D0u          /* src/readable/sheet/sheet.h S_CatGuard0 .. 4 */
#define S_EuCatGuard1 0x006D97CCu
#define S_EuCatGuard2 0x006D97C8u
#define S_EuCatGuard3 0x006D97C4u
#define S_EuCatGuard4 0x006D97C0u

/* ---- Unit::CanItemEquip's own one-time caches: 21 guard words, one apart
   from 0x006D9804 to 0x006D9854. Each is filled the first time the game
   asks: a name looked up in a data table (JobCategory, PrivateSkill,
   EquipSkill, ItemSkill or ItemUse ::Get), turned into a bit or kept as a
   number. The readable code only reads the values, after every guard is set.
   The names are described, not copied. */
#define S_EuGuardFirst 0x006D9804u
#define S_EuGuardLast 0x006D9854u
#define S_EuGuardStep 4u

/* u16: 1 << the JobCategory number of the dark-mage class line (strh) */
#define S_EuDarkMageCategory 0x006D9670u
/* s16: the EquipSkill number of the skill that lets other classes use dark-mage-only tomes
   (EquipSkill record +0x10) */
#define S_EuDarkMageSkill 0x006D9672u
/* u16: the ItemUse numbers of the "rescue" and "draw" staffs */
#define S_EuRescueUse 0x006D9674u
#define S_EuDrawUse 0x006D9676u

/* u64 PersonFlag bits (1 << a PrivateSkill number): the avatar, five royals,
   and "no warp" */
#define S_EuAvatarFlag 0x006D9B10u
#define S_EuTakumiFlag 0x006D9B18u
#define S_EuRyomaFlag 0x006D9B20u
#define S_EuLeoFlag 0x006D9B28u
#define S_EuXanderFlag 0x006D9B30u
#define S_EuOpheliaFlag 0x006D9B38u
#define S_EuNoWarpFlag 0x006D9B40u

/* u64 ItemFlag bits (1 << an ItemSkill number): "only for ..." */
#define S_EuAvatarOnly 0x006D9B48u
#define S_EuDarkMageOnly 0x006D9B50u
#define S_EuMaleOnly 0x006D9B58u
#define S_EuFemaleOnly 0x006D9B60u
#define S_EuTakumiOnly 0x006D9B68u
#define S_EuRyomaOnly 0x006D9B70u
#define S_EuLeoOnly 0x006D9B78u
#define S_EuXanderOnly 0x006D9B80u
#define S_EuOpheliaOnly 0x006D9B88u
/* u64: the nine "only for" bits above ORed together (filled once, read as it is) */
#define S_EuAnyOnly 0x006D9B90u

/* ---- record fields read by raw offset */
#define EU_ITEMDATA_USE 0x1Bu              /* ItemData +0x1B: the ItemUse number (structs: item_subkind [low]) */
#define EU_SUBKIND_KIND 0x01u              /* ItemSubKind record +1: the weapon kind (0..7) */
#define EU_KIND_STAFF 6                    /* weapon kind 6: staffs */
#define EU_KIND_STONE 7                    /* weapon kind 7: dragonstones and beaststones */
#define EU_KIND_COUNT 8                    /* kinds 8 and up are not wielded */
#define EU_UNIT_DOWNLOAD_ONLY 0x10000000u  /* Unit.state_flags bit 28 (sheet.h UNIT_STATE_MAYBE_CLONE):
                                              a "royal only" item then also needs a download Person */

/* ---- the readable function (override entry at the end of the file) */
uint32_t unit_can_equip_item(Context *ctx, gaddr unit, gaddr item, uint32_t allow_staff, uint32_t current_rank);

#endif /* FE_EQUIP_USE_EQUIP_USE_H */
