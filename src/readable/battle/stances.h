/* Attack Stance and Guard Stance (Fates): the declarations shared by
   src/readable/battle/stance_bonus.c and stance_gauge.c, the guest functions
   they still call, and the game's one-time caches they read.

   Plain-language description of the system: docs/STANCES.md.

   This header lives next to its sources (tools/readable/stage.py looks in the
   including file's folder first) because the battle area owns only
   src/readable/battle/. The integrate step may move the declarations into
   include/readable/fe_functions.h and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into
   each file). */

#ifndef FE_BATTLE_STANCES_H
#define FE_BATTLE_STANCES_H

#include "fe.h"

/* ---- guest functions still called through guest_call() (docs/READABLE.md,
   rule 4: only callees without side effects, so a replay is safe).
   Each was read on 2026-11-11: no store outside its own stack frame. */
#define GUEST_PersonGet 0x0044A6F8u               /* Person::Get(unsigned short) -> Person record or a fallback; reads the loaded archives */
#define GUEST_FamilyGetDualSupport 0x0053B88Cu    /* unit::Family::GetDualSupport(BattleCapability::Type,int) const -> int; reads Person records, calls PersonEnhanceDual::GetEdit */
#define GUEST_FamilyGetDoubleCapability 0x0053BB20u /* unit::Family::GetDoubleCapability(Capability::Type,int) const -> int; same shape with PersonEnhanceDouble */
#define GUEST_UnitGetRelianceLevel 0x0052F518u    /* Unit::GetRelianceLevel(const Unit*) const -> support rank; reads support records */
#define GUEST_UnitIsEquipSkill 0x0052DD04u        /* Unit::IsEquipSkill(short) const -> 1 or 0; reads the unit's skill slots */

/* ---- one-time caches of the game (a C++ guard word, bit 0 = filled, and the
   value the game looked up by name the first time). Readable code reads the
   value only when the guard says it is filled, and gives up otherwise
   (fe_static_ready). Addresses read from each function's literal pool. */
#define S_DualSkillGuard 0x006D69C8u      /* map::BattleInfo::CalculateDual 0x00347390: guard of the skill id below */
#define S_DualSkillId 0x006D6932u         /* s16: EquipSkill number of the skill that lets a paired lead also get the attack follow-up */
#define S_PairSkillGuard 0x006D9798u      /* Unit::GetDoubleCapability 0x00530A48: guard of the skill id below */
#define S_PairSkillId 0x006D965Eu         /* s16: EquipSkill number of the skill that adds 1 to every pair-up stat bonus */
#define S_NoPairGuard 0x006D99B8u         /* Unit::CanDoubleOn 0x0052B620: guard of the mask below */
#define S_NoPairMask 0x006D9CB8u          /* u64: one PersonFlag bit (1 << PrivateSkill number) that forbids pairing up */
#define S_GaugeSkillId 0x006D6760u        /* s16: EquipSkill number of the skill that adds one more gauge point
                                             (map::BattleCalculator::CalculateAttackSingle 0x00364688; the cache is
                                             filled at that function's start, before the gauge code runs) */

/* The shield gauge is full at this many points (game::graphics::DualGuardGauge::Draw
   0x003E78C8 draws 10 cells and shows the "full" cell type when the value is 10 or
   more; map::BattleCalculator::CalculateAttackSingle 0x003637B4 blocks at 10). */
#define STANCE_GAUGE_FULL 10

/* ---- what the helpers give back (host memory, never guest memory) */

/* map::BattleInfo::CalculateDual for one main side */
typedef struct BattleDualPlan {
    uint8_t dual_attack;    /* the side's follow-up may strike (BattleSide.dual_attack) */
    int32_t gauge_total;    /* the pair's shield gauge, both units' points (BattleSide.gauge_total) */
    int clear_follow_up;    /* the follow-up side's attack count is set to 0 */
} BattleDualPlan;

/* the four gauge counters of map::BattleCalculator after one strike */
typedef struct StanceGauges {
    int32_t gauge[4];       /* BattleCalculator.gauge: sides 0, 1 (leads) and 2, 3 (their partners) */
} StanceGauges;

/* one unit at the start of its army's turn */
typedef struct StanceTurnBegin {
    uint32_t flags;         /* Unit.state_flags afterwards */
    uint8_t guard_gauge;    /* Unit.guard_gauge afterwards */
} StanceTurnBegin;

/* ---- stance bonuses (src/readable/battle/stance_bonus.c) */
int32_t stance_attack_bonus_total(Context *ctx, gaddr block, uint32_t type, int32_t rank);     /* 0x0050CBE8 PersonEnhanceDual::GetTotal */
int32_t stance_attack_bonus_edit(Context *ctx, gaddr block, uint32_t type, int32_t rank,
                                 uint32_t boon, gaddr stack);                                /* 0x0050CADC PersonEnhanceDual::GetEdit */
int32_t stance_guard_bonus_total(Context *ctx, gaddr block, uint32_t stat, int32_t rank);      /* 0x0050D968 PersonEnhanceDouble::GetTotal */
int32_t stance_guard_bonus_edit(Context *ctx, gaddr block, uint32_t stat, int32_t rank,
                                uint32_t boon, gaddr stack);                                 /* 0x0050D844 PersonEnhanceDouble::GetEdit */
int32_t unit_attack_stance_bonus(Context *ctx, gaddr unit, uint32_t type, int32_t rank);       /* 0x0052E974 Unit::GetDualSupport */
int32_t unit_guard_stance_bonus(Context *ctx, gaddr unit, uint32_t stat, gaddr partner);       /* 0x00530A34 Unit::GetDoubleCapability */
int32_t unit_guard_stance_move(Context *ctx, gaddr unit, gaddr partner);                       /* 0x00530680 Unit::GetDoubleMovePower */
int unit_can_pair_with(Context *ctx, gaddr unit, gaddr other);                                 /* 0x0052B60C Unit::CanDoubleOn */

/* ---- who may strike or block, the gauge (src/readable/battle/stance_gauge.c) */
int situation_can_dual(Context *ctx, gaddr situation, uint32_t force_type);                    /* 0x005281B8 map::Situation::CanDual */
int battle_dual_plan(Context *ctx, gaddr info, uint32_t side, BattleDualPlan *out);            /* helper of 0x00347350 map::BattleInfo::CalculateDual */
int stance_dual_guard_blocks(Context *ctx, gaddr calc, uint32_t attacker);                     /* part of 0x003628BC (no registry row of its own) */
void stance_gauge_after_strike(Context *ctx, gaddr calc, uint32_t attacker, int blocked,
                               StanceGauges *out);                                             /* helper of 0x003628BC map::BattleCalculator::CalculateAttackSingle */
void stance_gauge_at_turn_begin(Context *ctx, gaddr unit, StanceTurnBegin *out);               /* helper of 0x003A54D8 map::Sequence ProcSequence::TurnBegin */
int32_t stance_follow_up_damage(Context *ctx, gaddr side, int32_t damage);                     /* helper of 0x005253A8 map::BattleInfo::Side::GetSimplePower */

#endif /* FE_BATTLE_STANCES_H */
