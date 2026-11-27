/* Growth, level-up and experience (Fates): the declarations shared by
   src/readable/unit/growth_rates.c, growth_exp.c and growth_roll.c, the guest
   functions they still call, and the game's one-time caches they read.

   Plain-language description of every rule: docs/GROWTH.md.

   This header lives next to its sources, as the battle area's formulas.h does;
   the integrate step may move the declarations into
   include/readable/fe_functions.h and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_UNIT_GROWTH_H
#define FE_UNIT_GROWTH_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-12: it stores nothing
   outside its own stack frame, or only fills a one-time cache of its own.
   Where the game calls a function that has a readable override (this batch's
   or an older one), the readable code calls it through the guest too, in the
   game's order and with the game's arguments, so the live shadow compare sees
   the same list of calls (docs/DECISIONS.md F-018). */
#define GROW_PersonGet 0x0044A6F8u          /* Person::Get(unsigned short) -> a Person record (or a fallback);
                                               walks the loaded Person blocks; reads only */
#define GROW_PersonIsFemale 0x0053ED90u     /* Person::IsFemale(void) const -> 1 or 0; one-time cache inside */
#define GROW_UnitIsEquipSkill 0x0052DD04u   /* Unit::IsEquipSkill(short) const -> 1 or 0; reads the skill slots */
#define GROW_JobIsHigh 0x00524804u          /* Job::IsHigh(void) const -> 1 for a promoted class; one-time cache inside */
#define GROW_ItemToData 0x003D0EA4u         /* unit::Item::ToData(void) const -> the Item record; reads only */
#define GROW_UnitEquippedIndex 0x005310C0u  /* Unit::GetItemIndexEquipped(void) const: readable unit_equipped_index
                                               (src/readable/battle/formula_stats.c) */
#define GROW_UnitGetCapability 0x0052F7A0u  /* Unit::GetCapabilityImpl(int,const unit::Item*,bool,bool,Type) const:
                                               dispatches to the stat getter of the stat (a table of member
                                               pointers at 0x006D9CE0); takes two words on the guest stack, so it
                                               cannot be called through guest_call (see GrowthCapFn) */

/* this batch's overrides, called through the guest where the game calls them */
#define GROW_UnitGetGrow 0x005330B4u
#define GROW_EditGetGrow 0x0053AC20u
#define GROW_FamilyGetGrow 0x0053B6CCu
#define GROW_UnitGetLimit 0x005337F0u
#define GROW_EditGetLimit 0x0053AC54u
#define GROW_FamilyGetLimit 0x0053BDC4u
#define GROW_ExpGetBattle 0x004E6368u
#define GROW_ExpGetBattleThreshold 0x004E6314u
#define GROW_ExpGetDance 0x004E634Cu
#define GROW_ExpGetSupportDecline 0x004E62F8u
#define GROW_ExpGetRodDecline 0x004E62C4u
#define GROW_ExpGetRodHighDecline 0x004E62E0u
#define GROW_UnitExpLevel 0x00531F24u
#define GROW_UnitGetExpDamage 0x0052D418u
#define GROW_JobGetLimitLevel 0x005242F0u

/* ---- one-time caches (guard word, bit 0 = filled). Readable code reads a
   cached value only when its guard says it is filled and gives up otherwise,
   before reading anything else. Addresses from each function's literal pool. */
#define S_GrowGuard 0x006D979Cu        /* Unit::GetGrow: guard of S_GrowSkill (0x006D9628 + 0x174) */
#define S_GrowSkill 0x006D9660u        /* SEID number (s16) of the skill that adds 10 to every growth */
#define S_ExpLevelGuard 0x006D993Cu    /* Unit::GetLevelForCalculateExp: guard of S_ExpLevelMask */
#define S_ExpLevelMask 0x006D9C88u     /* PersonFlag bit (u64): 6 more levels for experience */
#define S_DestroyGuard1 0x006D994Cu    /* Unit::GetExpDestroy: four PersonFlag bits (u64 masks) */
#define S_DestroyGuard2 0x006D9948u
#define S_DestroyGuard3 0x006D9944u
#define S_DestroyGuard4 0x006D9940u
#define S_DestroyMask1 0x006D9C90u     /* with mask 2 or 4: + the base, at most 20 */
#define S_DestroyMask2 0x006D9C98u
#define S_DestroyMask3 0x006D9CA0u     /* - half the base (rounded up), when the base is 2 or more */
#define S_DestroyMask4 0x006D9CA8u     /* also: at least 20 */
#define S_JobLimitGuard1 0x006D39B8u   /* Job::GetLimitLevel: guard of S_JobLimitSpecial */
#define S_JobLimitSpecial 0x006D39BCu  /* the Job record found by a JID name: level limit 101 */
#define S_JobHighGuard 0x006D39B0u     /* Job::GetLimitLevel and Job::IsHigh: guard of S_JobHighMask */
#define S_JobHighMask 0x006D3A10u      /* PersonFlag bit (u64) of a promoted class */
#define S_LevelLimitStep 0x006D96E4u   /* s32 read (no guard) by Unit::GetLimitLevel / ExpNormalize: levels
                                          added to the limit per Unit.level_limit_raises */

#define GROW_STATS 8u                  /* hp, str, mag, skl, spd, lck, def, res */
#define GROW_PASSES 4                  /* Unit::LevelUp rolls the eight stats again, at most 4 times in all,
                                          while no stat has risen */
#define GROW_EXP_MODE_HALF 3           /* Unit::ExpMode::Type 3: the amount is halved (and the target level
                                          rule of mode 2 applies); names of the modes not in the symbol map */

/* ---- overrides (readers) */
int32_t unit_grow(Context *ctx, gaddr unit, uint32_t stat);
int32_t edit_grow(Context *ctx, gaddr edit, uint32_t stat);
int32_t family_grow(Context *ctx, gaddr family, gaddr person, uint32_t stat);
int32_t family_parent_grow(Context *ctx, gaddr parent, uint32_t stat);
int32_t unit_stat_limit(Context *ctx, gaddr unit, uint32_t stat);
int32_t edit_limit(Context *ctx, gaddr edit, uint32_t stat);
int32_t family_limit(Context *ctx, gaddr family, uint32_t stat);

gaddr exp_table_battle(Context *ctx, int32_t difficulty);
gaddr exp_table_battle_threshold(Context *ctx, int32_t difficulty);
gaddr exp_table_dance(Context *ctx, int32_t difficulty);
gaddr exp_table_support_decline(Context *ctx, int32_t difficulty);
gaddr exp_table_rod_decline(Context *ctx, int32_t difficulty);
gaddr exp_table_rod_high_decline(Context *ctx, int32_t difficulty);
int32_t unit_exp_level(Context *ctx, gaddr unit);
int32_t unit_exp_damage(Context *ctx, gaddr unit, int32_t mode, gaddr other);
int32_t unit_dual_exp_damage(Context *ctx, gaddr unit, int32_t mode, gaddr other);
int32_t unit_exp_destroy(Context *ctx, gaddr unit, int32_t mode, gaddr other, uint32_t boss);
int32_t unit_exp_dance(Context *ctx, gaddr unit, int32_t mode, gaddr other);
int32_t unit_exp_rod(Context *ctx, gaddr unit, int32_t mode, gaddr item, gaddr other);
int32_t unit_exp_normalize(Context *ctx, gaddr unit, int32_t amount);
int32_t unit_level_limit(Context *ctx, gaddr unit);
int32_t job_level_limit(Context *ctx, gaddr job);
uint32_t situation_can_gain_exp(Context *ctx, gaddr situation, uint32_t force);

/* ---- helpers (F-017: the game functions store; these return what would be
   stored and write nothing) */

/* The game's Random (Random::Initialize, GetValue(void), GetValue(int)): four
   words of xorshift128 state. A host-side copy: nothing here touches guest
   memory. */
typedef struct GrowthRandom {
    uint32_t s[4];
} GrowthRandom;
void growth_random_seed(Context *ctx, GrowthRandom *r, uint32_t seed);  /* ctx unused (pure), may be NULL */
uint32_t growth_random_next(Context *ctx, GrowthRandom *r);
int32_t growth_random_below(Context *ctx, GrowthRandom *r, int32_t n);
int growth_roll_hits(int32_t roll, int32_t rate);

/* The stat rises of one level-up before the caps: what Unit::LevelUp decides
   from the unit's seed and its eight growth rates alone. */
typedef struct GrowthPlan {
    uint32_t next_seed;                  /* what the game stores into Unit.growth_seed */
    int passes;                          /* passes over the eight stats (1 .. 4) */
    int draws;                           /* GetValue(100) calls (one per stat with a rate above 0, per pass) */
    int32_t points[GROW_PASSES][GROW_STATS]; /* per pass: guaranteed points (rate / 100) + 1 for a roll below
                                                the rest; each still needs room under the cap */
} GrowthPlan;
void growth_level_up_plan(Context *ctx, uint32_t seed, const int32_t rates[GROW_STATS], GrowthPlan *plan);

/* What Unit::LevelUp would store, with the caps. The cap check is the stat
   now (Unit::GetCapabilityImpl, which takes two stack words) against
   Unit::GetLimit; since nothing is written, the stat "now" must count the
   points this level-up has already added: the callback gets the gains byte
   the game would have stored by then and returns the stat with it. */
typedef int32_t (*GrowthCapFn)(Context *ctx, void *env, gaddr unit, uint32_t stat, int8_t gains_now);
typedef struct GrowthLevelUp {
    uint32_t growth_seed;            /* Unit +0xC0 */
    uint8_t level;                   /* Unit +0xF1 */
    int8_t gains[GROW_STATS];        /* Unit +0xC8 */
    int8_t stat_loss[GROW_STATS];    /* Unit +0xE0 */
    int passes;
} GrowthLevelUp;
int unit_level_up_preview(Context *ctx, gaddr unit, GrowthCapFn capability, void *env, GrowthLevelUp *out);

#endif /* FE_UNIT_GROWTH_H */
