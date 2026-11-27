/* AI attack-score readers (Fates classes AIBattleSimulator, map::ItemHelper::Rod,
   map::trick::Data, map::Situation, versus::Config): the declarations shared by
   src/readable/ai_score/ai_score_sim.c, ai_score_rod.c and ai_score_heal.c, the guest functions
   they still call, and the game's one-time caches they read.

   Plain-language description (what each function decides, and why the five
   AIThink::Get*Score functions themselves are NOT here): docs/AI_SCORE.md.

   This header lives next to its sources, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_AI_SCORE_AI_SCORE_H
#define FE_AI_SCORE_AI_SCORE_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-15: it stores nothing
   outside its own stack frame, or only fills a one-time cache of its own.
   Where the game calls (BL) a function, the readable code makes the same
   guest call in the game's order with the game's arguments
   (docs/DECISIONS.md F-018), also when the callee is an override. None of
   this batch's functions ends in a tail branch (B) to an override; the one tail
   branch, CanUseDisvalueRange's to Rod::CanUseTarget, reaches a guest function
   that is not rewritten, and is made as a guest call (docs/AI_SCORE.md 6). */
#define AS_ItemToData 0x003D0EA4u          /* unit::Item::ToData(void) const (readable: item_to_data) */
#define AS_ItemIsHiddenEffect 0x00528E90u  /* Item::IsHiddenEffect(void) const (readable: item_is_hidden_effect) */
#define AS_UnitIsEquipSkill 0x0052DD04u    /* Unit::IsEquipSkill(short) const (readable: unit_has_skill) */
#define AS_ItemSubKindGet 0x0019B97Cu      /* ItemSubKind::Get(int) (readable: item_subkind_record) */
#define AS_UnitCanItemEquip 0x0052C634u    /* Unit::CanItemEquip(const unit::Item*,bool,bool) const; reads only
                                              (3,352 bytes, not rewritten) */
#define AS_UnitGetRangeI 0x00534474u       /* Unit::GetRangeI(const unit::Item*) const (readable: unit_range_min) */
#define AS_UnitGetRangeO 0x00534510u       /* Unit::GetRangeO(const unit::Item*) const (readable: unit_range_max) */
#define AS_ImageUnitGetUnit 0x00526424u    /* map::Image::Unit::GetUnit(int,int) const (readable: image_unit_at) */
#define AS_ForceGet 0x004F630Cu            /* Force::Get(Force::Type): one NOP, then UnitPool::GetForce; reads only
                                              (not rewritten) */
#define AS_RodCanUseTarget 0x0034AC30u     /* map::ItemHelper::Rod::(anonymous)::CanUseTarget(const Unit*,int,Unit*):
                                              may this staff be used on that unit; 2,184 bytes, stores only into
                                              its own one-time caches (read 2026-11-15; not rewritten) */
#define AS_WeaponBonusGet 0x001A8090u      /* WeaponBonus::Get(ItemKind::Type) (readable: weapon_bonus_record) */
#define AS_WeaponLevelGet 0x001A80D4u      /* WeaponLevel::Get(void) (readable: weapon_level_record) */
#define AS_WeaponLevelGetLevel 0x005090A4u /* WeaponLevel::GetLevel(int) const (readable: weapon_rank_of_exp) */
#define AS_UnitGetWeaponExpLimit 0x0052F824u /* Unit::GetWeaponExpLimit(ItemKind::Type) const (readable:
                                                unit_weapon_exp_limit) */
#define AS_UnitGetPowImpl 0x0052A500u      /* Unit::GetPowImpl(unit, item, extras, loss, rally kind) (readable:
                                              unit_magic): the fifth argument on the stack, through
                                              guest_call5 (round 11, docs/READABLE.md 17) */
#define AS_SituationIsVersus 0x00528238u   /* map::Situation::IsVersus(void) const: situation_is_versus (this batch) */
/* this batch's own override, called through the guest where the game calls it */
#define AS_VersusConfigGet 0x004C5344u     /* versus::Config::Get(void): versus_config_get */

/* ---- globals (addresses from the functions' literal pools) */
#define G_VersusConfig 0x006DA318u         /* ptr: the versus (link battle) configuration, 0 outside versus play */
#define G_Situation 0x006D7ED0u            /* ptr: the map::Situation (passed to IsVersus, which does not read it) */

/* ---- one-time caches (guard word, bit 0 = filled; the value the game looked
   up by name the first time). Readable code reads a cached value only when its
   guard says it is filled and gives up otherwise, before reading anything
   else. The names are the game's ID labels (SEID_ = equip skill, ISID_ = item
   skill flag) given here in English [med for the English; low where marked]. */

/* AIBattleSimulator::IsPower0Attack: eight skill numbers (s16) at
   S_P0Skills + 2 * i, each with its own guard (filled in this order on entry);
   the guard of skill i is S_P0GuardFirst - 4 * i */
#define S_P0Skills 0x006D0EF8u
#define S_P0GuardFirst 0x006D0F40u
#define P0_SKILLS 8
#define P0_SEAL_DEF 0       /* SEID "seal Defence" (the attack lowers Defence by 6) */
#define P0_SEAL_RES 1       /* SEID "seal Resistance" (lowers Resistance by 6) */
#define P0_STATUS_RESIST 2  /* SEID "status resistance" (the target takes half) */
#define P0_STATUS_IMMUNE 3  /* SEID "status immunity" (the target takes none) */
#define P0_SNAKE_VENOM 4    /* SEID "snake venom" [low for the English] */
#define P0_FOUR_FANGS 5     /* SEID "four fangs" [low for the English] */
#define P0_DEATH_BREATH 6   /* SEID "breath of death" [low for the English] */
#define P0_NEGATIVE_CHAIN 7 /* SEID "chain of the negative" [low for the English] */

/* map::ItemHelper::Rod::CanUseDisvalueRange: two ItemUse numbers (u16) */
#define S_RodAreaGuard 0x006D74C8u
#define S_RodAreaUse 0x006D7466u     /* u16: IUID "heal all" (a staff that reaches every unit in a range) */
#define S_RodReviveGuard 0x006D74C4u
#define S_RodReviveUse 0x006D7468u   /* u16: IUID "revival" */
/* Unit::GetRodHealPower */
#define S_RodSkillGuard 0x006D9918u
#define S_RodSkill 0x006D96ACu       /* s16: SEID "absent-minded" [low for the English]: a healed unit with it
                                        gets half again */
#define S_RodMagicGuard 0x006D9914u
#define S_RodMagicMask 0x006D9C40u   /* u64: ItemFlag bit ISID "effect + magic / 3" */
/* Unit::GetWeaponExpLimit's own caches (triangle.h S_ExpLimitGuardA..C): asked
   first by unit_rod_heal_power, so that override never gives up inside it */
#define S_RodLimitGuardA 0x006D97B4u
#define S_RodLimitGuardB 0x006D97B0u
#define S_RodLimitGuardC 0x006D97ACu
/* Unit::GetPowImpl's caches: asked through unit_stat_caches_ready (battle
   batch, src/readable/battle/formula_stats.c; reads only the guard words) */
int unit_stat_caches_ready(Context *ctx, uint32_t stat);
#define AS_STAT_MAG 2u               /* formulas.h STAT_MAG */
/* the range overrides' own caches (sheet.h S_RangeGuard, item.h S_RangeOGuard):
   asked first by rod_can_use_from, so those overrides never give up inside it */
#define S_RodRangeIGuard 0x006D9898u
#define S_RodRangeOGuard 0x006D989Cu
/* Item::IsHiddenEffect's own cache (item.h S_ItemHiddenGuard): asked first by
   ai_sim_is_power0_attack */
#define S_P0HiddenGuard 0x006D38D8u

/* ---- record fields this batch reads that config/readable/structs/ does not
   name yet (offsets read in the code on 2026-11-15; the integrate step may
   add them). [high for the offsets, med for the names, low where marked]

   AIBattleSimulator (built on the AI's stack by AIBattleSimulator::Calculate):
   +0 the attacking Unit*, +4 the target Unit*, +8 a map::BattleInfo whose four
   0x200-byte sides start at +8, +0x208, +0x408, +0x608. */
#define SIM_ATTACKER 0x000u          /* Unit* */
#define SIM_TARGET 0x004u            /* Unit* (0: no target unit) */
#define SIM_ITEM_SIDE0 0x018u        /* side 0 +0x10: the attacker's unit::Item (u16 item number first) */
#define SIM_SIDE1_COUNT 0x244u       /* side 1 +0x3C: s32 [low for the meaning: AIBattleSimulator::Calculate
                                        computes a kill chance for a side only when its +0x3C is above 0] */
#define SIM_SIDE2_COUNT 0x444u       /* side 2 +0x3C: s32, the same field of the third side */
#define SIM_ITEM_SIDE2 0x418u        /* side 2 +0x10: that side's unit::Item */
#define SIM_SIDE1_SKILL_BITS 0x2EEu  /* side 1 +0xE6: one bit per skill number (byte n >> 3, bit n & 7) */
#define SIM_EXTRA_COUNT 0x814u       /* s32 [low]; above 0, the float at SIM_EXTRA_CHANCE decides */
#define SIM_EXTRA_CHANCE 0x820u      /* f32 [low]; compared with 0.0 by VFP code, which readable C does not run */
#define ITEM_DEBUFF_DEF 0x046u       /* ItemData: s8, the Defence lowered by a concealed weapon */
#define ITEM_DEBUFF_RES 0x047u       /* ItemData: s8, the Resistance lowered */
#define ITEM_HEAL 0x01Fu             /* ItemData: u8, the staff's base heal */
#define ITEM_USE 0x01Bu              /* ItemData: u8, the ItemUse number (structs name it item_subkind) [med] */
#define UNIT_DEBUFF_DEF 0x03Du       /* Unit.debuff (+0x37) + 6: s8, Defence already lowered */
#define UNIT_DEBUFF_RES 0x03Eu       /* Unit.debuff + 7: s8, Resistance already lowered */
#define UNIT_STAFF_EXP 0x0EEu        /* Unit.weapon_exp (+0xE8) + 6: u8, staff exp */
#define UNIT_CONDITION_BYTE 0x028u   /* Unit.conditions: u8; bit 3 stops every staff here [low for the meaning] */
#define UNIT_ITEMS 0x108u            /* Unit.items: five unit::Item of 4 bytes */
#define UNIT_FORCE 0x0A4u            /* Unit.force: Force* */
#define UNIT_PAIR 0x0A8u             /* Unit.pair_partner: Unit* */
#define FORCE_TYPE 0x008u            /* Force: u8 type (0 = the player's army) */
#define FORCE_FIRST 0x004u           /* Force: Unit* the first unit of the force */
#define UNIT_STATE_FLAGS 0x008u      /* Unit.state_flags: u32; bit 7 tested on the dead force's first unit [low] */
#define FORCE_DEAD 4u                /* Force::Type 4: the fallen [med] */
#define MAPIMAGE_UNITS 0x008u        /* map::Image::Unit: the 32 x 32 unit grid inside the map image */
#define MAPIMAGE_PLAY_X_MIN 0x002u   /* u8 play area: first column, first row, column after the last, row after */
#define MAPIMAGE_PLAY_Y_MIN 0x003u
#define MAPIMAGE_PLAY_X_END 0x004u
#define MAPIMAGE_PLAY_Y_END 0x005u
#define TRICK_TYPE 0x00Cu            /* map::trick::Data: u8 the trick type */
#define STAFF_KIND 6u                /* ItemKind: staff */
#define UNIT_CONDITION_NO_STAFF 0x08u
#define P0_SEAL_AMOUNT 6             /* what the two "seal" skills lower */
#define TRICK_CASTLE_OFFENSE_FIRST 15u /* trick types 15..22: castle-offense targets [low for the meaning] */
#define TRICK_CASTLE_OFFENSE_SPAN 7u

/* ---- the readable functions (override entries at the end of each file) */
/* ai_score_sim.c */
uint32_t ai_sim_is_power0_attack(Context *ctx, gaddr sim);
uint32_t trick_is_destroy_target_castle_offense(Context *ctx, gaddr trick);
gaddr versus_config_get(Context *ctx);
uint32_t situation_is_versus(Context *ctx, gaddr situation);
/* ai_score_rod.c */
uint32_t rod_can_use_from(Context *ctx, gaddr unit, int32_t slot, int32_t x, int32_t y);
/* ai_score_heal.c */
int32_t unit_rod_heal_power(Context *ctx, gaddr unit, gaddr item, gaddr target);

#endif /* FE_AI_SCORE_AI_SCORE_H */
