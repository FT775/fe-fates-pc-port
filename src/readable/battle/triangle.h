/* Weapon triangle and weapon ranks (Fates): the declarations shared by
   src/readable/battle/triangle_tables.c and triangle_battle.c, the guest
   function they still call, and the game's one-time caches they read.

   Plain-language description of the system: docs/TRIANGLE.md.

   This header lives next to its sources for the same reason as stances.h
   (the battle area owns only src/readable/battle/). The integrate step may
   move the declarations into include/readable/fe_functions.h and the callee
   into fe_callees.h.

   Never write the override marker in this header (staging pastes it into
   each file). */

#ifndef FE_BATTLE_TRIANGLE_H
#define FE_BATTLE_TRIANGLE_H

#include "fe.h"

/* ---- guest function still called through guest_call() (docs/READABLE.md,
   rule 4: no side effects). Read on 2026-11-11: loads and compares only, no
   store, no call. */
#define GUEST_ItemToData 0x003D0EA4u /* unit::Item::ToData(void) const -> the Item record of the unit::Item's
                                        item number (walks the loaded item archives; a fallback record when
                                        no archive holds the number) */

/* ---- one-time caches of the game (guard word, bit 0 = filled; the value the
   game looked up by name the first time). Readable code reads a value only
   when its guard says it is filled, and gives up otherwise. */
#define S_ReverseGuard 0x006D6978u   /* map::BattleInfo::CalculateDetail 0x00347A10: guard of the mask below */
#define S_ReverseMask 0x006D6A88u    /* u64: one ItemFlag bit (1 << ItemSkill number) marking a weapon that
                                        reverses the weapon triangle (literal 0x006D6918 + 0x170) */
#define S_ExpLimitGuardA 0x006D97B4u /* Unit::GetWeaponExpLimit 0x0052F838: guard of S_StoneLimitMask */
#define S_StoneLimitMask 0x006D9A90u /* u64: one PersonFlag bit; a unit, Person or class carrying it gets
                                        weapon exp limit 0 for kind 7 (stones) */
#define S_ExpLimitGuardB 0x006D97B0u /* Unit::GetWeaponExpLimit 0x0052F87C: guard of S_StaffLimitMask */
#define S_StaffLimitMask 0x006D9A98u /* u64: one PersonFlag bit; carrying it raises the staff (kind 6) limit
                                        to at least S_StaffLimitFloor */
#define S_ExpLimitGuardC 0x006D97ACu /* Unit::GetWeaponExpLimit 0x0052F8C4: guard of S_StaffLimitFloor */
#define S_StaffLimitFloor 0x006D97B8u /* s32: WeaponLevel threshold[2] (the rank B threshold), cached */

/* weapon kinds (ItemKind numbers; the order of WeaponInteract's columns) */
#define TRIANGLE_KIND_STAFF 6
#define TRIANGLE_KIND_STONE 7
#define TRIANGLE_KINDS 8        /* Unit::GetHit/GetAttack add a rank bonus only for kinds below this */
#define WEAPON_RANK_NONE 6      /* WeaponLevel::GetLevel: below the E threshold (0 = S .. 5 = E) */
#define TRIANGLE_REVERSED 0x2000u /* BattleSide.flags: this side's weapon reverses the triangle */

/* the two columns of a WeaponBonus / WeaponInteract rank row */
#define RANK_COLUMN_ATTACK 0
#define RANK_COLUMN_HIT 1

/* ---- what the helpers give back (host memory, never guest memory) */

/* map::BattleInfo::CalculateDetail's triangle lookup for one side */
typedef struct TriangleLookup {
    int looked_up;       /* 1 when the side and the opposing lead both hold a weapon (else nothing is stored) */
    int32_t triangle;    /* the WeaponInteract cell stored into BattleSide.triangle: +1, -1 or 0 */
    uint32_t flags;      /* BattleSide.flags afterwards (TRIANGLE_REVERSED added for a reversing weapon) */
} TriangleLookup;

/* the triangle part of map::BattleInfo::Side::CalculateDetailHit / CalculateDetailAttack */
typedef struct TriangleRankBonus {
    int applies;          /* 0: the game stores 0 for this number and skips the rest (no unit, no weapon,
                             an opposing follow-up side, or for attack the side's flag 0x40) */
    int keep_rank_bonus;  /* the bool the game passes to Unit::GetHit/GetAttack: 0 at a triangle disadvantage */
    int32_t bonus;        /* added to that number: WeaponInteract rank row column * BattleSide.triangle */
} TriangleRankBonus;

/* ---- table getters and weapon exp (src/readable/battle/triangle_tables.c) */
gaddr item_subkind_record(Context *ctx, int32_t index);                           /* 0x0019B97C ItemSubKind::Get(int) */
gaddr weapon_bonus_record(Context *ctx, uint32_t kind);                           /* 0x001A8090 WeaponBonus::Get(ItemKind::Type) */
gaddr weapon_level_record(Context *ctx);                                          /* 0x001A80D4 WeaponLevel::Get(void) */
gaddr weapon_interact_record(Context *ctx);                                       /* 0x001D77B8 WeaponInteract::Get(void) */
int32_t weapon_rank_of_exp(Context *ctx, gaddr level, int32_t exp);               /* 0x005090A4 WeaponLevel::GetLevel(int) const */
int32_t unit_weapon_exp_limit(Context *ctx, gaddr unit, uint32_t kind);           /* 0x0052F824 Unit::GetWeaponExpLimit(ItemKind::Type) const */
int32_t unit_weapon_exp(Context *ctx, gaddr unit, uint32_t kind);                 /* 0x0052DC54 Unit::GetWeaponExp(ItemKind::Type) const */
int32_t item_weapon_kind(Context *ctx, gaddr item);                               /* ItemSubKind of a unit::Item -> its ItemKind (s8) */
int32_t unit_weapon_rank_attack(Context *ctx, gaddr unit, gaddr item);            /* helper of 0x00534188 Unit::GetAttack(const unit::Item*,bool) */
int32_t unit_weapon_rank_hit(Context *ctx, gaddr unit, gaddr item);               /* helper of 0x00532DC4 Unit::GetHit(const unit::Item*,bool) */

/* ---- the triangle in a fight (src/readable/battle/triangle_battle.c) */
int triangle_item_reverses(Context *ctx, gaddr item);                             /* the weapon carries the reversing flag */
void triangle_side_lookup(Context *ctx, gaddr info, uint32_t side, TriangleLookup *out); /* helper of 0x003475BC map::BattleInfo::CalculateDetail */
int32_t triangle_after_reverse(Context *ctx, gaddr info, uint32_t side);          /* part of 0x003475BC (no registry row of its own) */
void triangle_hit_bonus(Context *ctx, gaddr side, gaddr opposing, TriangleRankBonus *out);    /* helper of 0x00348FF0 Side::CalculateDetailHit */
void triangle_attack_bonus(Context *ctx, gaddr side, gaddr opposing, TriangleRankBonus *out); /* helper of 0x00349880 Side::CalculateDetailAttack */

#endif /* FE_BATTLE_TRIANGLE_H */
