/* Skills (Fates): the declarations shared by src/readable/skill/skill_has.c
   and skill_battle.c, the guest functions they still call, and the game's
   one-time caches they read.

   Plain-language description (which skills are data and which are code, how
   an activation is rolled, the number and order of the dice): docs/SKILLS.md.

   This header lives next to its sources, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_SKILL_SKILLS_H
#define FE_SKILL_SKILLS_H

#include "fe.h"
#include "../unit/growth.h"  /* GrowthRandom, growth_random_below: the game's Random on a host copy */

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-13: it stores nothing
   outside its own stack frame, or only fills a one-time cache of its own.
   Where the game calls a function that has a readable override (this batch's
   or an older one), the readable code calls it through the guest too, in the
   game's order and with the game's arguments (docs/DECISIONS.md F-018). */
#define SKILL_UnitPoolGet 0x004F6174u          /* UnitPool::Get(int) -> the unit of a pool index; reads only */
#define SKILL_EquipSkillByName 0x001758C4u     /* EquipSkill::Get(const char*) -> the Skill record of a SEID label
                                                  (a branch into IdentHash::GetSurely: a hash lookup; reads only) */
#define SKILL_IdentHashGetIdent 0x00127330u    /* IdentHash::GetIdent(const char*) const -> the label's entry or 0;
                                                  reads only */
#define SKILL_HasRallyCapability 0x00532124u   /* Unit::HasCheerSkillCapability(void) const -> 1 when the unit has
                                                  one of the stat rally skills; one-time caches inside */
#define SKILL_ItemToData 0x003D0EA4u           /* unit::Item::ToData(void) const -> the Item record; reads only */
#define SKILL_UnitGetCapability 0x0052F7A0u    /* Unit::GetCapabilityImpl(int,const unit::Item*,bool,bool,Type) const:
                                                  the stat getter of a stat; takes two words on the guest stack, so
                                                  guest_call cannot pass them (see SkillStatFn) */

/* this batch's overrides, called through the guest where the game calls them */
#define SKILL_UnitIsEquipSkill 0x0052DD04u     /* Unit::IsEquipSkill(short) const: unit_has_skill */
#define SKILL_EquipSkillGet 0x001758E4u        /* EquipSkill::Get(short): skill_record */
#define SKILL_EquipSkillGetCommonNum 0x001758B4u /* EquipSkill::GetCommonNum(void): skill_common_total */
#define SKILL_HasBattleSkill 0x003A34B4u       /* map::battle::detail::HasBattleSkill: battle_side_has_skill */

/* ---- one-time caches (guard word, bit 0 = filled; the value the game looked
   up by name the first time). Readable code reads a cached value only when its
   guard says it is filled and gives up otherwise, before reading anything
   else. Addresses from each function's literal pool. The skill names are the
   game's ID labels (SEID_ = equip skill, SPID_ = PersonFlag bit, ISID_ = item
   flag bit), given here in English [med for the English names]. */
#define S_JobHighGuard 0x006D39B0u        /* Job::GetEquipSkill (also Job::IsHigh): guard of S_JobHighMask */
#define S_JobHighMask 0x006D3A10u         /* u64 PersonFlag bit SPID "promoted class" */
#define S_RallyMoveGuard 0x006D9978u      /* Unit::HasCheerSkill / HasCheerSkillMove: guard of the skill below */
#define S_RallyMoveSkill 0x006D96C0u      /* s16 SEID "rally movement" */
#define S_NohrSkillGuard 0x006D6848u      /* HasBattleSkill: guard of the skill below */
#define S_NohrSkillId 0x006D676Au         /* s16 SEID "Nohr" (Nohrian Trust): use the paired side's skills */
#define S_KillGuardMask 0x006D6854u       /* IsInvalidKill: guard of S_KillImmuneMask */
#define S_KillImmuneMask 0x006D6910u      /* u64 PersonFlag bit SPID "Lethality immune" */
#define S_KillGuardSkin 0x006D6850u
#define S_KillSkinSkill 0x006D676Cu       /* s16 SEID "dragon scale" (Dragonskin) */
#define S_KillGuardShield 0x006D684Cu
#define S_KillShieldSkill 0x006D676Eu     /* s16 SEID "divine shield" (meaning not traced) */
#define S_ChanceGuardHoshido 0x006D97FCu  /* GetEquipSkillProbability: guard of the skill below */
#define S_ChanceHoshidoSkill 0x006D966Cu  /* s16 SEID "Hoshido" (Hoshidan Unity): +10 to every activation */
#define S_ChanceGuardCharm 0x006D97F8u
#define S_ChanceCharmSkill 0x006D966Eu    /* s16 SEID "luck charm": +20 to luck-based activations */
#define S_ChanceGuardForbid 0x006D97F4u
#define S_ChanceForbidMask 0x006D9AF8u    /* u64 PersonFlag bit SPID "skill activation forbidden": 0 */
#define S_ChanceGuardForce 0x006D97F0u
#define S_ChanceForceMask 0x006D9B00u     /* u64 PersonFlag bit SPID "forced skill activation": 100 */
/* map::BattleCalculator::CalculateAttack: nine attack skills tried in this
   order, one more skill that raises their chance, one item flag */
#define SKILL_ATTACK_COUNT 9
#define S_AttackGuard0 0x006D67A4u        /* guards of the ten skill numbers: S_AttackGuard0 - 4 * i */
#define S_AttackSkill0 0x006D6724u        /* s16 skill numbers: S_AttackSkill0 + 2 * i, i = 0 .. 9:
                                             Lethality, Aether, Astra, Dragon Fang, Sol, Luna, Ignis,
                                             Rend Heaven, Vengeance, then Quixotic (the chance bonus) */
#define S_AttackGuardItem 0x006D677Cu
#define S_AttackNoSkillMask 0x006D6890u   /* u64 item flag bit ISID "no critical, no skill" of the weapon */

#define SKILL_ATTACK_AETHER 1             /* index of Aether in the list above: struck as Sol, then Luna */
#define SKILL_ATTACK_ASTRA 2              /* Astra: up to five strikes */
#define SKILL_ATTACK_SOL 4
#define SKILL_ATTACK_LUNA 5
#define SKILL_ATTACK_QUIXOTIC 9

/* SkillIndexProvider::GetSkillEffectName: the effect-name strings are
   constants in the code; the skill numbers they belong to are words of the
   SkillIndexProvider object that SkillIndexProvider::Initialize fills */
#define SKILL_EFFECT_NAMES 23

/* ---- overrides (readers) */
uint32_t unit_has_skill(Context *ctx, gaddr unit, uint32_t skill);
int32_t unit_personal_skill(Context *ctx, gaddr unit);
int32_t unit_equipped_skill_count(Context *ctx, gaddr unit);
gaddr skill_record(Context *ctx, uint32_t number);
uint32_t skill_total(Context *ctx);
uint32_t skill_common_total(Context *ctx);
uint32_t job_class_skill(Context *ctx, gaddr job, int32_t level);
uint32_t skill_pool_test(Context *ctx, gaddr pool, int32_t number);
uint32_t skill_is_unknown(Context *ctx, gaddr record);
uint32_t script_unit_has_skill(Context *ctx, gaddr script, int32_t unit_index, gaddr seid);
uint32_t unit_has_rally_move_skill(Context *ctx, gaddr unit);
uint32_t unit_has_rally_skill(Context *ctx, gaddr unit);
uint32_t battle_side_has_skill(Context *ctx, gaddr info, uint32_t side, uint32_t skill);
uint32_t unit_lethality_immune(Context *ctx, gaddr unit);
gaddr skill_effect_name(Context *ctx, int32_t number);

/* ---- helpers (F-017: their game functions compute through a callee that
   takes stack words, or store; these return what the game would compute or
   store and write nothing) */

/* The stat an activation chance uses: Unit::GetCapabilityImpl(stat, no item,
   true, true, 0), i.e. the stat with all extras. guest_call cannot pass the
   two stack words, so the caller supplies it. */
typedef int32_t (*SkillStatFn)(Context *ctx, void *env, gaddr unit, uint32_t stat);

/* Unit::GetEquipSkillProbability(short skill, bool quixotic): the activation
   chance in percent (0 .. 100). Returns 0 when it gave up (a cold cache) or
   when the skill's divisor is 0 (the game's division would trap), else 1. */
int unit_skill_chance(Context *ctx, gaddr unit, uint32_t skill, uint32_t quixotic, SkillStatFn stat, void *env,
                      int32_t *chance);

/* The attack-skill choice of map::BattleCalculator::CalculateAttack: which of
   the nine attack skills activates for one attack of a side, the dice it
   takes from the battle's Random (G_BattleRandom, read into a host copy) and
   what the game would store into its new scene. */
typedef struct SkillAttackPick {
    int32_t skill;         /* the activated skill number (0: none); stored at scene +0x8 */
    uint32_t side;         /* stored at scene +0x4 (with the kind 4 at scene +0x5) when skill != 0 */
    int draws;             /* GetValue(100) calls made on the battle Random */
    GrowthRandom random;   /* the battle Random's four words afterwards */
    int32_t strikes[2];    /* the skill CalculateAttackSingle gets first and (Aether: Luna) second; the
                              game stops early when a strike returns 1, and strikes up to five times
                              with Astra */
} SkillAttackPick;
int battle_attack_skill_pick(Context *ctx, gaddr calculator, uint32_t side, SkillStatFn stat, void *env,
                             SkillAttackPick *out);

#endif /* FE_SKILL_SKILLS_H */
