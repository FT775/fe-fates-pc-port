/* The unit's status sheet (Fates class Unit): the declarations shared by
   src/readable/sheet/sheet_stats.c and sheet_unit.c, the guest functions they
   still call, and the game's one-time caches they read.

   Plain-language description (what each number is made of, which skills and
   flags move it): docs/SHEET.md.

   This header lives next to its sources, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_SHEET_SHEET_H
#define FE_SHEET_SHEET_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-13: it stores nothing
   outside its own stack frame, or only fills a one-time cache of its own.
   Where the game calls a function that has a readable override (this batch's
   or an older one), the readable code calls it through the guest too, in the
   game's order and with the game's arguments (docs/DECISIONS.md F-018). */
#define SHEET_ItemToData 0x003D0EA4u          /* unit::Item::ToData(void) const -> the Item record; reads only */
#define SHEET_UnitGetLimit 0x005337F0u        /* Unit::GetLimit(int) const -> the stat cap; reads only
                                                 (readable: unit_stat_limit) */
#define SHEET_EditGetCapability 0x0053ABECu   /* unit::Edit::GetCapability(int) const -> the avatar's boon + bane;
                                                 reads only */
#define SHEET_UnitGetDoubleCapability 0x00530A34u /* Unit::GetDoubleCapability(int,const Unit*) const: the Guard
                                                 Stance bonus of the partner (readable: unit_guard_stance_bonus) */
#define SHEET_UnitIsEquipSkill 0x0052DD04u    /* Unit::IsEquipSkill(short) const (readable: unit_has_skill) */
#define SHEET_GetEnhanceHave 0x0033A790u      /* anonymous_namespace::GetEnhanceHave(const Unit*,Capability::Type) ->
                                                 the carried-item bonus of a stat; reads, one-time cache inside */
#define SHEET_UnitGetItemIndexEquipped 0x005310C0u /* Unit::GetItemIndexEquipped(void) const -> slot or -1
                                                 (readable: unit_equipped_index) */
#define SHEET_ItemSubKindGet 0x0019B97Cu      /* ItemSubKind::Get(int) -> the sub-kind record (readable:
                                                 item_subkind_record) */
#define SHEET_BelongGet 0x0044529Cu           /* Belong::Get(int) -> the Belong record of a number; reads only */
#define SHEET_PersonGetCaptureChange 0x0053E1BCu /* Person::GetCaptureChange(unsigned short) const -> what the
                                                 captured person becomes for a class (0: cannot be captured); reads */
#define SHEET_JobIsGiant 0x005249F8u          /* Job::IsGiant(void) const -> 1 for a "giant" class; one-time cache */
#define SHEET_PersonIsDownload 0x0053DFECu    /* Person::IsDownload(void) const (readable: person_is_download) */
#define SHEET_UnitCanItemEquip 0x0052C634u    /* Unit::CanItemEquip(const unit::Item*,bool,bool) const: may the unit
                                                 wield this item; reads only (3,352 bytes, not rewritten) */

/* this batch's override, called through the guest where the game calls it */
#define SHEET_UnitGetCategory 0x0052B728u     /* Unit::GetCategory(void) const: unit_category */

/* ---- one-time caches (guard word, bit 0 = filled; the value the game looked
   up by name the first time). Readable code reads a cached value only when its
   guard says it is filled and gives up otherwise, before reading anything
   else. Addresses from each function's literal pool (base 0x006D9628 or
   0x006D9A28 plus the offset it uses). The names are the game's ID labels
   (SEID_ = equip skill, SPID_ = PersonFlag bit, JCID_ = class category bit),
   given here in English [med for the English names]. */

/* Unit::GetDefImpl: four EquipSkill numbers (s16) */
#define S_DefGuard0 0x006D9788u
#define S_DefGuard1 0x006D9784u
#define S_DefGuard2 0x006D9780u
#define S_DefGuard3 0x006D977Cu
#define S_DefSkillPlus2 0x006D9650u   /* SEID "Def+2": +2 */
#define S_DefSkillMinus1 0x006D9652u  /* SEID "juuken" (the speed-for-defence skill): -1 defence */
#define S_DefSkillAbsorb 0x006D9654u  /* SEID "Def absorb": + Unit.absorbed[def] */
#define S_DefSkillTonic 0x006D9656u   /* SEID "better tonics": +1 more from the defence tonic */
/* Unit::GetMdefImpl */
#define S_ResGuard0 0x006D9794u
#define S_ResGuard1 0x006D9790u
#define S_ResGuard2 0x006D978Cu
#define S_ResSkillPlus2 0x006D9658u   /* SEID "Res+2" */
#define S_ResSkillAbsorb 0x006D965Au  /* SEID "Res absorb" */
#define S_ResSkillTonic 0x006D965Cu   /* SEID "better tonics" */
/* Unit::GetMHPImpl */
#define S_HpGuard0 0x006D9730u
#define S_HpGuard1 0x006D972Cu
#define S_HpSkillPlus5 0x006D9628u    /* SEID "HP+5": +5 */
#define S_HpSkillTonic 0x006D962Au    /* SEID "better tonics": +2 more from the HP tonic */
/* Unit::GetMovePower */
#define S_MoveGuard0 0x006D97A8u
#define S_MoveGuard1 0x006D97A4u
#define S_MoveGuard2 0x006D97A0u
#define S_MoveGuard3 0x006D99A8u      /* asked in the middle of the getter by the game */
#define S_MoveSkillPlus1 0x006D9662u  /* SEID "Move+1": +1 */
#define S_MoveSkillShooter 0x006D9664u /* SEID labelled "amphibious": +1 for a unit of the category below */
#define S_MoveFlyerMask 0x006D9666u   /* u16: 1 << JobCategory "flying" */
#define S_MoveShooterMask 0x006D96D8u /* u16: 1 << JobCategory "shooter" (ballista classes) */
/* Unit::GetCategory */
#define S_CatGuard0 0x006D97D0u
#define S_CatGuard1 0x006D97CCu
#define S_CatGuard2 0x006D97C8u
#define S_CatGuard3 0x006D97C4u
#define S_CatGuard4 0x006D97C0u
#define S_CatDragon 0x006D9668u       /* u16: 1 << JobCategory "dragon" */
#define S_CatBeast 0x006D966Au        /* u16: 1 << JobCategory "beast" */
#define S_CatDragonFlag 0x006D9AA8u   /* u64 PersonFlag bit SPID "manakete": the unit counts as a dragon */
#define S_CatBeastFlag 0x006D9AB0u    /* u64 PersonFlag bit SPID "laguz": the unit counts as a beast */
#define S_CatNoDragonFlag 0x006D9AB8u /* u64 PersonFlag bit SPID "cannot use special weapons": never a dragon */
/* Unit::GetLowLevel */
#define S_LowLevelGuard 0x006D97E8u
#define S_LowLevelMask 0x006D9AE8u    /* u64 PersonFlag bit SPID "promoted class" (read in the class flags) */
/* Unit::GetRangeI */
#define S_RangeGuard 0x006D9898u
#define S_RangeSkill 0x006D9678u      /* SEID "close shot": a bow of that sub-kind reaches from 1 */

/* ---- record fields this batch reads that config/readable/structs/ does not
   name yet (offsets read in the code on 2026-11-13; the integrate step may
   add them to Unit.csv). [high for the offsets, med for the names] */
#define UNIT_HP 0xF3u                 /* s8: current HP (HpWindowUnit::GetHp) */
#define UNIT_NO_ATTACK_PERSON 0xF8u   /* u32: a Person this unit may never attack (Unit::IsDontAttack) */
#define UNIT_MOVE_BONUS 0x12Cu        /* s8: added to the class move unless state bit 30 is set */
#define UNIT_MOVE_LOSS 0x12Du         /* s8: taken off the move (when above 0) */
#define UNIT_NO_ATTACK_FORCES 0x12Eu  /* u8: bit n set = may never attack units of force type n */
#define UNIT_BELONG 0x131u            /* u8: the Belong number (Belong::Get) */
#define HPWINDOW_UNIT 0xE0u           /* map::anonymous_namespace::HpWindowUnit: the Unit pointer */
#define PERSON_CAPTURE_WORD 0x0Cu     /* Person +0xC (fid): not 0 = may be captured whatever the Belong says */
#define BELONG_FLAGS 0x0Cu            /* Belong record: bit 0 invisible, bit 1 may be captured */
#define ITEM_RANGE_MIN 0x28u          /* Item record: shortest range (u8) */
#define ITEM_SUBKIND 0x1Au            /* Item record: sub-kind number (s8) */
#define SUBKIND_KIND 0x01u            /* ItemSubKind record: weapon kind (u8): 4 bow, 6 staff */

#define UNIT_ITEM_SLOT_COUNT 5
#define UNIT_ITEM_IS_EQUIPPED 0x4000u
#define UNIT_STATE_SWAP_PARTNER_BIT 0x200000u /* state bit 21: the partner bit is 4 instead of 2 */
#define UNIT_STATE_LOSS 0x40000000u   /* state bit 30: Unit.stat_loss[] is taken off, the move bonus is not added */
#define UNIT_STATE_NO_ATTACK 0x400000u /* state bit 22: Unit::IsDontAttack says 1 (unless asked to ignore it) */
#define UNIT_STATE_NOT_UNIQUE 0x40000u /* state bit 18: Unit::IsUnique says 0 */
#define UNIT_STATE_MAYBE_CLONE 0x10000000u /* state bit 28: unique only when its Person is a download one */

#define SHEET_STAT_HP 0
#define SHEET_STAT_DEF 6
#define SHEET_STAT_RES 7
#define SHEET_STAT_CAP 99

/* ---- the readable functions (override entries at the end of each file) */
int32_t unit_defense(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp);
int32_t unit_resistance(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp);
int32_t unit_max_hp(Context *ctx, gaddr unit, uint32_t with_extras, uint32_t unused, int32_t kind);
int32_t hp_window_max_hp(Context *ctx, gaddr window);
int32_t hp_window_hp(Context *ctx, gaddr window);
int32_t unit_move(Context *ctx, gaddr unit, uint32_t with_extras, int32_t kind);
uint32_t unit_category(Context *ctx, gaddr unit);
gaddr unit_equipped_item(Context *ctx, gaddr unit);
gaddr unit_equipped_item_mutable(Context *ctx, gaddr unit);
int32_t unit_shown_level(Context *ctx, gaddr unit);
int32_t unit_low_level(Context *ctx, gaddr unit);
int32_t unit_item_count(Context *ctx, gaddr unit);
int32_t unit_range_min(Context *ctx, gaddr unit, gaddr item);
uint32_t unit_may_not_attack(Context *ctx, gaddr unit, gaddr other, uint32_t ignore_state);
uint32_t unit_is_unique(Context *ctx, gaddr unit);
uint32_t unit_is_special_battle(Context *ctx, gaddr unit);
uint32_t unit_is_invisible(Context *ctx, gaddr unit);
uint32_t unit_can_be_captured(Context *ctx, gaddr unit);
int32_t unit_held_item_index(Context *ctx, gaddr unit);

#endif /* FE_SHEET_SHEET_H */
