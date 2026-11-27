/* Battle formulas (Fates): the declarations shared by
   src/readable/battle/formula_stats.c, formula_unit.c and formula_forecast.c,
   the guest functions they still call, and the game's one-time caches they read.

   Plain-language description of every formula: docs/FORMULAS.md.

   This header lives next to its sources for the same reason as stances.h
   (the battle area owns only src/readable/battle/). The integrate step may
   move the declarations into include/readable/fe_functions.h and the callees
   into fe_callees.h.

   Never write the override marker in this header (staging pastes it into
   each file). */

#ifndef FE_BATTLE_FORMULAS_H
#define FE_BATTLE_FORMULAS_H

#include "fe.h"
#include "stances.h"   /* GUEST_UnitIsEquipSkill */
#include "triangle.h"  /* GUEST_ItemToData, the weapon-rank helpers */

/* ---- guest functions still called through guest_call() (docs/READABLE.md,
   rule 4: a replay must be safe). Each was read on 2026-11-11: it stores
   nothing outside its own stack frame, or only fills a one-time cache of its
   own (idempotent: the same value every time). */
#define GUEST_UnitGetLimit 0x005337F0u        /* Unit::GetLimit(int) const -> the stat cap: Job.max + Person.limit_mod
                                                 (+ Family/Edit limits) + Unit +0xD0[stat], clamped 0..99; reads only */
#define GUEST_EditGetCapability 0x0053ABECu   /* unit::Edit::GetCapability(int) const -> the avatar's boon + bane for a stat
                                                 (two Personality rows); reads only */
#define GUEST_UnitGetDoubleCapability 0x00530A34u /* Unit::GetDoubleCapability(int,const Unit*) const: the Guard Stance
                                                 bonus; readable as unit_guard_stance_bonus (stance_bonus.c), and
                                                 guest_call reaches that override when it is built */
#define GUEST_GetEnhanceHave 0x0033A790u      /* anonymous_namespace::GetEnhanceHave(const Unit*,Capability::Type) -> the
                                                 carried-item bonus (Item.extra_data[stat] of each of the 5 items that
                                                 Unit::IsItemEnhanceHave accepts); reads, one-time cache inside */
#define GUEST_ItemGetHit 0x0053B2A4u          /* unit::Item::GetHit(void) const -> Item.hit + the forge bonus; reads only */
#define GUEST_ItemGetCritical 0x0053AD54u     /* unit::Item::GetCritical(void) const -> Item.crit + the forge bonus; reads only */
#define GUEST_ItemGetPower 0x0053B4B4u        /* unit::Item::GetPower(void) const -> Item.might + the forge bonus; reads only */
#define GUEST_ItemIsMagic 0x005290B8u         /* Item::IsMagic(void) const -> 1 for a magic weapon; one-time cache inside */
#define GUEST_UnitGetRangeI 0x00534474u       /* Unit::GetRangeI(const unit::Item*) const -> the weapon's shortest range
                                                 (a skill can lower a bow's to 1); one-time cache inside */
#define GUEST_UnitGetRangeO 0x00534510u       /* Unit::GetRangeO(const unit::Item*) const -> the weapon's longest range;
                                                 one-time cache inside */
#define GUEST_ItemSubKindGet 0x0019B97Cu      /* ItemSubKind::Get(int) -> the sub-kind record (table + index * 0x10); reads
                                                 only; readable as item_subkind_record (triangle_tables.c). Called
                                                 through the guest by the rank bonus of unit_hit / unit_attack because
                                                 the game calls it there (3 times; F-018: the same callee calls) */
#define GUEST_UnitGetCritical 0x0052B9BCu     /* Unit::GetCritical(const unit::Item*) const: readable as unit_crit */
#define GUEST_UnitGetSecure 0x005345E0u       /* Unit::GetSecure(const unit::Item*) const: readable as unit_crit_avoid */
#define GUEST_UnitGetContinuous 0x0052E134u   /* Unit::GetContinuous(const unit::Item*) const: readable as unit_attack_speed */
#define GUEST_UnitGetUnderContinuous 0x00530834u /* Unit::GetUnderContinuous(const unit::Item*) const: readable as
                                                 unit_defense_speed */

/* ---- one-time caches (guard word, bit 0 = filled; the value the game looked
   up by name the first time). Readable code reads a value only when its guard
   says it is filled and gives up otherwise. Addresses from each function's
   literal pool (base 0x006D9628 or 0x006D6918 plus the offset it uses). */

/* the five stat getters: one EquipSkill number (s16) per guard */
#define S_StrGuard0 0x006D9740u  /* Unit::GetStrImpl: guard of S_StrSkillPlus2 */
#define S_StrGuard1 0x006D973Cu
#define S_StrGuard2 0x006D9738u
#define S_StrGuard3 0x006D9734u
#define S_StrSkillPlus2 0x006D962Cu  /* SEID "Str+2": +2 */
#define S_StrSkillPlus3 0x006D962Eu  /* SEID "gouken": +3 strength */
#define S_StrSkillAbsorb 0x006D9630u /* SEID "Str absorb": + Unit.absorbed[str] */
#define S_StrSkillTonic 0x006D9632u  /* SEID "better tonics": +1 more from the strength tonic */
#define S_MagGuard0 0x006D974Cu  /* Unit::GetPowImpl */
#define S_MagGuard1 0x006D9748u
#define S_MagGuard2 0x006D9744u
#define S_MagSkillPlus2 0x006D9634u  /* SEID "Mag+2" */
#define S_MagSkillAbsorb 0x006D9636u /* SEID "Mag absorb" */
#define S_MagSkillTonic 0x006D9638u  /* SEID "better tonics" */
#define S_SklGuard0 0x006D9758u  /* Unit::GetTechImpl */
#define S_SklGuard1 0x006D9754u
#define S_SklGuard2 0x006D9750u
#define S_SklSkillPlus2 0x006D963Au  /* SEID "Skl+2" */
#define S_SklSkillAbsorb 0x006D963Cu /* SEID "Skl absorb" */
#define S_SklSkillTonic 0x006D963Eu  /* SEID "better tonics" */
#define S_SpdGuard0 0x006D976Cu  /* Unit::GetQuickImpl */
#define S_SpdGuard1 0x006D9768u
#define S_SpdGuard2 0x006D9764u
#define S_SpdGuard3 0x006D9760u
#define S_SpdGuard4 0x006D975Cu
#define S_SpdSkillPlus2 0x006D9640u  /* SEID "Spd+2" */
#define S_SpdSkillPlus3 0x006D9642u  /* SEID "juuken": +3 speed */
#define S_SpdSkillMinus1 0x006D9644u /* SEID "gouken": -1 speed */
#define S_SpdSkillAbsorb 0x006D9646u /* SEID "Spd absorb" */
#define S_SpdSkillTonic 0x006D9648u  /* SEID "better tonics" */
#define S_LckGuard0 0x006D9778u  /* Unit::GetLuckImpl */
#define S_LckGuard1 0x006D9774u
#define S_LckGuard2 0x006D9770u
#define S_LckSkillPlus4 0x006D964Au  /* SEID "Lck+4" */
#define S_LckSkillAbsorb 0x006D964Cu /* SEID "Lck absorb" */
#define S_LckSkillTonic 0x006D964Eu  /* SEID "better tonics" */

/* Unit::GetHit: three PersonFlag bits (u64 masks) that add 10, 20 and 30 hit */
#define S_HitGuard10 0x006D9924u
#define S_HitGuard20 0x006D9920u
#define S_HitGuard30 0x006D991Cu
#define S_HitMask10 0x006D9C48u  /* SPID "Hit+10" */
#define S_HitMask20 0x006D9C50u  /* SPID "Hit+20" */
#define S_HitMask30 0x006D9C58u  /* SPID "Hit+30" */
/* Unit::GetAvoid: four PersonFlag bits: -20, -10, +10, +20 avoid */
#define S_AvoidGuardM20 0x006D9938u
#define S_AvoidGuardM10 0x006D9934u
#define S_AvoidGuardP10 0x006D9930u
#define S_AvoidGuardP20 0x006D992Cu
#define S_AvoidMaskM20 0x006D9C68u /* SPID "Avoid-20" */
#define S_AvoidMaskM10 0x006D9C70u /* SPID "Avoid-10" */
#define S_AvoidMaskP10 0x006D9C78u /* SPID "Avoid+10" */
#define S_AvoidMaskP20 0x006D9C80u /* SPID "Avoid+20" */
/* Unit::GetCritical: one ItemFlag bit: a weapon that can never crit */
#define S_NoCritGuard 0x006D9928u
#define S_NoCritMask 0x006D9C60u   /* ISID "no critical, no skill" */

/* map::BattleInfo::Side::GetSimpleHit (base 0x006D6918) */
#define S_FhStaffResistGuard 0x006D6A08u
#define S_FhStaffResistMask 0x006D6AE8u  /* SPID "hindering staff resistance": halves a hindering staff's hit */
#define S_FhStaffImmuneGuard 0x006D6A04u
#define S_FhStaffImmuneMask 0x006D6AF0u  /* SPID "hindering staff immunity": a hindering staff never hits */
#define S_FhStaffItemGuard 0x006D6A00u
#define S_FhStaffItemMask 0x006D6AF8u    /* ISID "hindering staff": the weapon is a hindering staff */
#define S_FhStatusResistGuard 0x006D69FCu
#define S_FhStatusResistId 0x006D6946u   /* SEID "status resistance" (s16): halves it */
#define S_FhStatusImmuneGuard 0x006D69F8u
#define S_FhStatusImmuneId 0x006D6948u   /* SEID "status immunity" (s16): 0 */
#define S_FhRuleWord 0x006D7ED0u         /* pointer; its word +4 bit 0x40000 also halves a hindering staff's hit
                                            (what object it is: not traced) */
/* map::BattleInfo::Side::GetSimpleTimes */
#define S_FsNoFollowGuard 0x006D6A14u
#define S_FsNoFollowMask 0x006D6B08u     /* ISID "no follow-up": the weapon never strikes twice */
#define S_FsNoDoubleGuard 0x006D6A10u
#define S_FsRangeIGuard 0x006D9898u /* Unit::GetRangeI's one-time cache: asked before the guest call, so a cold cache gives up here and not inside the nested override unit_range_min (round 8) */
#define S_FsNoDoubleId 0x006D694Au       /* SEID "defensive formation" (s16): in either side's skill bits, no one doubles */
/* map::BattleInfo::CalculateSimple's critical part */
#define S_FcNoCritGuard 0x006D6A0Cu
#define S_FcNoCritMask 0x006D6B00u       /* ISID "no critical, no skill" again (its own cache) */

/* ---- the eight stats (Capability numbers; the element order of every stat array) */
#define STAT_STR 1
#define STAT_MAG 2
#define STAT_SKL 3
#define STAT_SPD 4
#define STAT_LCK 5
#define STAT_CAP 99            /* every shown stat is clamped to 0..99 at the end */

#define UNIT_ITEM_SLOTS 5      /* Unit.items: five unit::Item of 4 bytes */
#define UNIT_ITEM_EQUIPPED 0x4000u /* unit::Item flags (u16 at +2): the equipped weapon */
#define UNIT_STATE_PAIR_SWAP 0x200000u   /* Unit.state_flags bit 21: test the partner bit 2 (4) instead of 1 (2) */
#define UNIT_STATE_STAT_LOSS 0x40000000u /* Unit.state_flags bit 30: Unit.stat_loss[] is taken off the base stat */
#define FORCE_TYPE_ENEMY 1     /* Force.type of the enemy army (Unit::GetCritical halves the class crit) */
#define UNIT_STATE_FULL_CRIT 0x20u /* Unit.state_flags bit 5: an enemy keeps its whole class crit */

/* BattleSide.flags bits these formulas test (meaning from what the code does) */
#define SIDE_INITIATOR 0x1u    /* side 0 of a fight (map::BattleInfo::ComplementConditions) */
#define SIDE_FOLLOW_UP 0x2u    /* sides 2 and 3: the Attack Stance follow-up */
#define SIDE_STAFF 0x40u       /* a staff (weapon kind 6; ComplementConditions 0x0034964C), not a weapon strike */
#define SIDE_HINDER 0x80u      /* a hindering staff (ISID "hindering staff"; ComplementConditions 0x00349680) */
#define SIDE_NO_STRIKE 0x100u  /* a long-range (siege) weapon, ISID "long range" (Side::ComplementConditions
                                  0x003496B4): it never strikes back (GetSimpleTimes gives 0) */
#define SIDE_NO_CRIT 0x4000u   /* no critical for this side (CalculateSimple) */
#define BATTLE_BONUS_STRIDE 0x94u /* the defending bonus fields are repeated 0x94 bytes further for a follow-up side */

/* ---- what the helpers give back (host memory, never guest memory) */

/* the critical / critical-avoid / speed part of map::BattleInfo::Side::CalculateDetail */
typedef struct ForecastDetail {
    uint32_t detail;           /* 0 or 1: the BattleDetail row written (1 when the other side is a follow-up side) */
    int16_t crit;              /* BattleDetail.crit */
    int16_t crit_avoid;        /* BattleDetail.crit_avoid */
    int32_t attack_speed;      /* BattleDetail.attack_speed */
    int32_t defense_speed;     /* BattleDetail.defense_speed */
} ForecastDetail;

/* ---- the stat getters (src/readable/battle/formula_stats.c) */
int32_t unit_equipped_index(Context *ctx, gaddr unit);                    /* 0x005310C0 Unit::GetItemIndexEquipped */
int32_t unit_stat_value(Context *ctx, uint32_t stat, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss,
                        int32_t kind);                                    /* the shared body of the five getters */
int unit_stat_caches_ready(Context *ctx, uint32_t stat);                  /* that getter's one-time caches are all filled */
/* the five getters as overrides: sp = the guest stack pointer at entry (the fifth argument, the rally kind, is there) */
int32_t unit_strength(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp); /* 0x0052A80C */
int32_t unit_magic(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp);    /* 0x0052A500 */
int32_t unit_skill(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp);    /* 0x0052C30C */
int32_t unit_speed(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp);    /* 0x0052D860 */
int32_t unit_luck(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp);     /* 0x0052BC5C */

/* ---- the unit's battle numbers (src/readable/battle/formula_unit.c) */
int32_t unit_hit(Context *ctx, gaddr unit, gaddr item, int rank_bonus);           /* 0x00532DC4 Unit::GetHit(const unit::Item*,bool) */
int32_t unit_hit_of_slot(Context *ctx, gaddr unit, int32_t slot, int rank_bonus); /* 0x00532D90 Unit::GetHit(int,bool) */
int32_t unit_avoid(Context *ctx, gaddr unit, gaddr item);                         /* 0x00533524 Unit::GetAvoid(const unit::Item*) */
int32_t unit_avoid_of_slot(Context *ctx, gaddr unit, int32_t slot);               /* 0x005334F0 Unit::GetAvoid(int) */
int32_t unit_crit(Context *ctx, gaddr unit, gaddr item);                          /* 0x0052B9BC Unit::GetCritical(const unit::Item*) */
int32_t unit_crit_of_slot(Context *ctx, gaddr unit, int32_t slot);                /* 0x0052B988 Unit::GetCritical(int) */
int32_t unit_crit_avoid(Context *ctx, gaddr unit, gaddr item);                    /* 0x005345E0 Unit::GetSecure(const unit::Item*) */
int32_t unit_attack(Context *ctx, gaddr unit, gaddr item, int rank_bonus);        /* 0x00534188 Unit::GetAttack(const unit::Item*,bool) */
int32_t unit_attack_of_slot(Context *ctx, gaddr unit, int32_t slot, int rank_bonus); /* 0x005342B8 Unit::GetAttack(int,bool) */
int32_t unit_attack_for_terrain(Context *ctx, gaddr unit, gaddr item);            /* 0x00534180 Unit::GetAttackForTerrain(const unit::Item*) */
int32_t unit_attack_for_terrain_of_slot(Context *ctx, gaddr unit, int32_t slot);  /* 0x005309A0 Unit::GetAttackForTerrain(int) */
int32_t unit_attack_speed(Context *ctx, gaddr unit, gaddr item);                  /* 0x0052E134 Unit::GetContinuous */
int32_t unit_defense_speed(Context *ctx, gaddr unit, gaddr item);                 /* 0x00530834 Unit::GetUnderContinuous */

/* ---- the forecast (src/readable/battle/formula_forecast.c) */
int32_t forecast_hit(Context *ctx, gaddr side, gaddr other);                      /* 0x00525090 Side::GetSimpleHit */
int32_t forecast_strikes(Context *ctx, gaddr side, gaddr other, int32_t distance, gaddr info_flags); /* 0x005259D4 Side::GetSimpleTimes */
void forecast_detail(Context *ctx, gaddr side, gaddr other, ForecastDetail *out); /* helper of 0x00348754 Side::CalculateDetail */
int32_t forecast_crit(Context *ctx, gaddr side, gaddr other);                     /* helper of 0x00347C3C BattleInfo::CalculateSimple */

#endif /* FE_BATTLE_FORMULAS_H */
