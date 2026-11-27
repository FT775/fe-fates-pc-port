/* What a staff does (Fates class Unit): how much a healing staff heals, and
   the hit and the resistance of a status staff ("interference rod": the
   staves that hinder a foe instead of healing). The declarations of
   src/readable/staff_range/staff_range.c and the guest functions it still
   calls.

   Plain-language description (what each function decides): docs/STAFF_RANGE.md.

   The batch row (docs/tracks/REWRITE_ORDER3.md batch 2) also names
   Unit::GetRangeO, the weapon's longest range. It already has a readable
   override (unit_range_max, src/readable/item/item_unit.c, docs/ITEM.md 4),
   which passes its stack word with guest_call5 since round 11. Nothing of it
   is here: two overrides of one address cannot both be built.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first).

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_STAFF_RANGE_STAFF_RANGE_H
#define FE_STAFF_RANGE_STAFF_RANGE_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each is a readable override of an older batch and
   stores nothing of the game's (the stat getters fill only their own one-time
   caches, asked first here, see below). Where the game calls a function the
   readable code makes the same guest call in the game's order with the game's
   arguments (docs/DECISIONS.md F-018). */
#define SR_ItemToData 0x003D0EA4u          /* unit::Item::ToData(void) const (readable: item_to_data) */
#define SR_ItemGetHit 0x0053B2A4u          /* unit::Item::GetHit(void) const (readable: item_hit) */
#define SR_UnitIsEquipSkill 0x0052DD04u    /* Unit::IsEquipSkill(short) const (readable: unit_has_skill) */
#define SR_WeaponBonusGet 0x001A8090u      /* WeaponBonus::Get(ItemKind::Type) (readable: weapon_bonus_record) */
#define SR_WeaponLevelGet 0x001A80D4u      /* WeaponLevel::Get(void) (readable: weapon_level_record) */
#define SR_WeaponLevelGetLevel 0x005090A4u /* WeaponLevel::GetLevel(int) const (readable: weapon_rank_of_exp) */
#define SR_UnitGetWeaponExpLimit 0x0052F824u /* Unit::GetWeaponExpLimit(ItemKind::Type) const
                                                (readable: unit_weapon_exp_limit) */
/* The four stat getters take a fifth argument word on the stack (the rally
   kind; the game passes 0 here): called with guest_call5 (docs/READABLE.md 17). */
#define SR_UnitGetPowImpl 0x0052A500u      /* Unit::GetPowImpl: magic (readable: unit_magic) */
#define SR_UnitGetTechImpl 0x0052C30Cu     /* Unit::GetTechImpl: skill (readable: unit_skill) */
#define SR_UnitGetMdefImpl 0x0052BF6Cu     /* Unit::GetMdefImpl: resistance (readable: unit_resistance) */
#define SR_UnitGetLuckImpl 0x0052BC5Cu     /* Unit::GetLuckImpl: luck (readable: unit_luck) */

/* ---- Unit::GetRodHealPower's own two one-time caches (read 2026-11-16) */
#define S_SrHealSkillGuard 0x006D9918u
#define S_SrHealSkill 0x006D96ACu      /* s16: the SEID number of the skill that makes a healed unit get half
                                          again [low for the skill's English name] */
#define S_SrHealMagicGuard 0x006D9914u
#define S_SrHealMagicMask 0x006D9C40u  /* u64: the ItemFlag bit "effect + magic / 3" [med for the English] */

/* ---- the callees' one-time caches, asked first so that no override gives up
   inside a guest call (a nested give-up). Copied from the owners' headers;
   keep in step with them:
   - Unit::GetWeaponExpLimit: src/readable/battle/triangle.h S_ExpLimitGuardA..C
   - Unit::GetMdefImpl: src/readable/sheet/sheet.h S_ResGuard0..2
   - GetPowImpl, GetTechImpl, GetLuckImpl: unit_stat_caches_ready (battle batch,
     src/readable/battle/formula_stats.c), which reads the same table the
     three overrides read. */
#define S_SrExpLimitGuardA 0x006D97B4u
#define S_SrExpLimitGuardB 0x006D97B0u
#define S_SrExpLimitGuardC 0x006D97ACu
#define S_SrResGuard0 0x006D9794u
#define S_SrResGuard1 0x006D9790u
#define S_SrResGuard2 0x006D978Cu
int unit_stat_caches_ready(Context *ctx, uint32_t stat);
#define SR_STAT_MAG 2u                 /* src/readable/battle/formulas.h STAT_MAG */
#define SR_STAT_SKL 3u                 /* STAT_SKL */
#define SR_STAT_LCK 5u                 /* STAT_LCK */

/* ---- numbers of the formulas */
#define SR_STAFF_KIND 6u               /* ItemKind: staff */
#define SR_UNIT_STAFF_EXP 0x0EEu       /* Unit.weapon_exp (+0xE8) + 6: u8, the staff exp */
#define SR_RANK_COLUMN_MIGHT 0u        /* WeaponBonus row: (might, hit) pairs of signed bytes per rank */
#define SR_RANK_COLUMN_HIT 1u
/* the stat getters' arguments as the game passes them here */
#define SR_WITH_EXTRAS 1u
#define SR_WITH_LOSS 1u
#define SR_RALLY_NONE 0u

/* ---- the readable functions (override entries at the end of the file) */
int32_t unit_rod_heal_power(Context *ctx, gaddr unit, gaddr item, gaddr target);
int32_t unit_status_staff_hit(Context *ctx, gaddr unit, gaddr item);
int32_t unit_status_staff_avoid(Context *ctx, gaddr unit, gaddr item);

#endif /* FE_STAFF_RANGE_STAFF_RANGE_H */
