/* Who the AI may attack, heal or leave idle (Fates class AIThink): the
   declarations shared by src/readable/ai/ai_permission.c, ai_area.c and
   ai_items.c, the guest functions they still call, and the game's one-time
   caches they read.

   Plain-language description (what each question decides): docs/AI.md.

   This header lives next to its sources, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_AI_AI_PERM_H
#define FE_AI_AI_PERM_H

#include "fe.h"
#include "../sheet/sheet.h" /* unit_move (the tail branch of GetMovePowerSlow), the stat getters' caches */
#include "../move/move.h"   /* the map image fields, terrain_cost_for_unit's cache */

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-15: it stores nothing
   outside its own stack frame, or only fills a one-time cache of its own.
   Where the game calls (BL) a function, the readable code makes the same
   guest call in the game's order with the game's arguments (docs/DECISIONS.md
   F-018), also when the callee is an override of this batch or an older one.
   Where the game ends with a plain branch (B) into an override, 3dsrecomp
   keeps that code inside the caller (docs/MOVE.md section 9), so the readable
   code runs the override's C directly and makes no guest call. */
#define AI_UnitIsDontAttack 0x0052DC90u     /* Unit::IsDontAttack(const Unit*,bool) const (readable: unit_may_not_attack) */
#define AI_UnitGetMHP 0x0052A364u           /* Unit::GetMHPImpl(bool,bool,EnhanceDefinition::Type) const (unit_max_hp) */
#define AI_UnitGetMovePower 0x0052D5E4u     /* Unit::GetMovePower(bool,EnhanceDefinition::Type) const (unit_move) */
#define AI_GameUserDataGet 0x001B3AFCu      /* GameUserData::Get(void) -> the GameUserData; reads only */
#define AI_UnitCanKeyDoor 0x00529E20u       /* Unit::CanKeyDoor(void) const: may the unit open doors (skill or key);
                                               reads, one-time cache of its own; not rewritten */
#define AI_ForceIsAllied 0x0053C3E0u        /* Force::IsAllied(Force::Type) const (readable: force_is_allied) */
#define AI_ImageUnitGetUnit 0x00526424u     /* map::Image::Unit::GetUnit(int,int) const (readable: image_unit_at) */
#define AI_TerrainCostFromUnit 0x001A6708u  /* TerrainCost::GetCostFromUnit(const Unit*,int) (terrain_cost_for_unit) */
#define AI_GetTrickFromAccess 0x004CF5B4u   /* AIThink::GetTrickFromAccess(int,int,map::trick::Type) (trick_at_access) */
#define AI_ValueIsArgument 0x00543DF4u      /* AIValue::IsArgument() const (ai_value_is_argument) */
#define AI_ValueGetArgument 0x00543E0Cu     /* AIValue::GetArgument(Order::Type,Unit*) const (ai_value_argument_address) */
#define AI_ValueIsSkip 0x00543E44u          /* AIValue::IsSkip() const (ai_value_is_skip) */
#define AI_ValueGetPerson 0x0044A6F0u       /* AIValue::GetPerson() const -> the Person the value names; reads only
                                               (its s16, then falls into Person::Get) */
#define AI_ValueGetJob 0x00543E3Cu          /* AIValue::GetJob() const -> the Job the value names; reads only */
#define AI_ItemToData 0x003D0EA4u           /* unit::Item::ToData(void) const (readable: item_to_data) */
#define AI_ItemSubKindGet 0x0019B97Cu       /* ItemSubKind::Get(int) (readable: item_subkind_record) */
#define AI_ItemIsMagic 0x005290B8u          /* Item::IsMagic(void) const (readable: item_is_magic) */
#define AI_UnitCanItemEquip 0x0052C634u     /* Unit::CanItemEquip(const unit::Item*,bool,bool) const; reads only
                                       (readable: unit_can_equip_item) */
#define AI_UnitCanItemUse 0x0052920Cu       /* Unit::CanItemUse(const unit::Item*) const: may the unit use this item
                                               now; reads only; not rewritten */
#define AI_UnitGetRangeO 0x00534510u        /* Unit::GetRangeO(const unit::Item*) const (readable: unit_range_max) */
/* this batch's own overrides, called through the guest where the game calls them */
#define AI_IsActiveCommand 0x004CB280u      /* AIThink::IsActiveCommand(Unit*,AICommand*): ai_command_is_active */
#define AI_IsAttackPermissionOnlyCommand 0x004D4770u /* ai_attack_permission_for_command */

/* ---- globals (addresses from the functions' literal pools) */
#define G_AICommandTable 0x0070560Cu /* ptr[3]: one array of AI sequences per order type (0 .. 2); a unit's
                                        sequence for order type t is array[t][Unit byte 0x65 + t] */

/* ---- one-time caches (guard word, bit 0 = filled; the value the game looked
   up by name the first time). Readable code reads a cached value only when its
   guard says it is filled and gives up otherwise, before reading anything
   else; it also asks the caches of the overrides it calls, so none of them
   gives up inside it. The names are the game's ID labels (ISID_ = item skill
   flag, SPID_ = PersonFlag bit, IUID_ = item use kind) given in English [med
   for the English, low where marked]. */
/* AIThink::GetItemIndexHeal: two ItemUse kinds (u16) */
#define S_AiHealGuard0 0x006D1070u
#define S_AiHealUse0 0x006D1058u      /* IUID "heal" (vulneraries) [low for the English] */
#define S_AiHealGuard1 0x006D106Cu
#define S_AiHealUse1 0x006D105Au      /* IUID "heal all" [low] */
/* AIThink::GetItemIndexDoping: four ItemUse kinds (u16); the fourth is the
   one that needs no stat test */
#define S_AiDopeGuard0 0x006D1080u
#define S_AiDopeUse0 0x006D105Cu
#define S_AiDopeGuard1 0x006D107Cu
#define S_AiDopeUse1 0x006D105Eu
#define S_AiDopeGuard2 0x006D1078u
#define S_AiDopeUse2 0x006D1060u
#define S_AiDopeGuard3 0x006D1074u
#define S_AiDopeUse3 0x006D1062u
/* AIThink::HasHealRod */
#define S_AiRodGuard 0x006D1084u
#define S_AiRodMask 0x006D10D0u       /* u64: ItemFlag bit ISID "heal rod" [low for the English] */
/* AIThink::IsAttackPermissionOnlyCommand */
#define S_AiOnlyGuard 0x006D12B0u
#define S_AiOnlyMask 0x006D1310u      /* u64: PersonFlag bit (a private skill looked up by name) [low] */
/* the callees' own caches, asked first (item.h, sheet.h, move.h) */
#define S_AiMagicGuard 0x006D38D4u    /* Item::IsMagic (item.h S_ItemMagicGuard) */
#define S_AiRangeOGuard 0x006D989Cu   /* Unit::GetRangeO (item.h S_RangeOGuard) */

/* ---- record fields this batch reads that config/readable/structs/ does not
   name yet (offsets read in the code on 2026-11-15; the integrate step may add
   them). [high for the offsets, med or low for the names as marked] */
#define AITHINK_UNIT 0x00u            /* AIThink: ptr, the unit it thinks for */
#define AISTATE_IDLE_MUTATION 0x150u  /* AIThinkState: s8, "idle units may change their order" [low] */
#define UNIT_STATE_GONE 0x04u         /* Unit.state_flags bit 2: the AI never attacks or heals such a unit
                                         [high for the effect here, low for what the bit means] */
#define UNIT_AI_FLAGS 0x054u          /* u32: AI bits (move.h UNIT_IMMOBILE_WORD is bit 8 of it) */
#define UNIT_AI_ROD_BITS 0x300000u    /* bits 20-21: may be healed with a rod [low for the meaning] */
#define UNIT_AI_CROSSFIRE_BIT 0x200000u /* bit 21: the attack-command codes 40/41 count */
#define UNIT_AI_DOORS 0x2000u         /* bit 13: ask Unit::CanKeyDoor */
#define UNIT_AI_FREE_A 0x8000u        /* bit 15 -> deploy flag 0x400 */
#define UNIT_AI_FREE_B 0x10000u       /* bit 16 -> deploy flag 0x1000000 */
#define UNIT_AI_PAIR_ROD 0x80u        /* bit 7: HasHealRod also looks at the partner's items */
#define UNIT_AI_KEY 0x05Au            /* u8: compared with a command's value (code 6) [low] */
#define UNIT_AI_BAND 0x05Bu           /* u8: the AI group a command's condition byte names [low] */
#define UNIT_AI_HEAL_PERCENT 0x05Du   /* u8: the HP percentage below which a non-player unit seeks healing */
#define UNIT_AI_SEQUENCE 0x065u       /* u8[3]: per order type, the index of the unit's AI sequence */
/* UNIT_HP (s8 +0xF3, current HP) comes from sheet.h */
#define UNIT_SECRET_BITS 0x028u       /* the bytes GetItemIndexDoping tests bit by bit (bit 8 + stat, from
                                         Unit.conditions); HasHealRod tests bit 3 of the first one [low] */
#define ITEM_SLOT_LOCKED 0x8000u      /* unit::Item halfword +2 bit 15: the AI never uses this item [low] */
#define ITEMDATA_USE 0x1Bu            /* ItemData u8: the ItemUse kind */
#define ITEMDATA_KIND 0x1Au           /* ItemData s8: the weapon sub-kind (ItemSubKind::Get) */
#define ITEMDATA_DOPE 0x40u           /* ItemData u8[8]: the stats a booster raises (non-zero = this stat) */
#define SUBKIND_KIND 0x01u            /* ItemSubKind u8: the weapon kind (8: a heal item) */
#define AICOMMAND_SIZE 12u            /* AICommand: u8 kind, u8 code, s8 condition, pad, AIValue at +4 and +8 */
#define AISEQUENCE_FIRST 8u           /* an AI sequence's first command */
#define AICMD_KIND 0u
#define AICMD_CODE 1u
#define AICMD_CONDITION 2u
#define AICMD_VALUE1 4u
#define AICMD_VALUE2 8u
#define AI_ORDER_ATTACK 2u            /* the order type HasActiveCommand passes to GetArgument, and Crossfire's */
#define AI_HEAL_PERCENT_PLAYER 75     /* the player's own units seek healing below 75% */

/* ---- the readable functions (override entries at the end of each file) */
/* ai_permission.c */
uint32_t ai_attack_permission(Context *ctx, gaddr unit, gaddr target, uint32_t ignore_state);
uint32_t ai_attack_permission_self(Context *ctx, gaddr think, gaddr target, uint32_t ignore_state);
uint32_t ai_heal_rod_permission(Context *ctx, gaddr think, gaddr target);
uint32_t ai_is_clever(Context *ctx);
int32_t ai_allow_idle_mutation(Context *ctx);
uint32_t ai_command_is_active(Context *ctx, gaddr unit, gaddr command);
uint32_t ai_deploy_free_move_flag(Context *ctx, gaddr unit);
int32_t ai_move_power_slow(Context *ctx, gaddr think);
uint32_t ai_heal_condition_for_entrust(Context *ctx, gaddr unit);
uint32_t ai_attack_permission_for_command(Context *ctx, int32_t code, gaddr value1, gaddr value2, gaddr unit);
uint32_t ai_has_active_command(Context *ctx, uint32_t order, gaddr unit);
uint32_t ai_has_crossfire_command(Context *ctx, gaddr unit, gaddr target);
/* ai_area.c */
uint32_t ai_is_escape_position(Context *ctx, gaddr think, int32_t x, int32_t y);
uint32_t ai_sigh_of_death_score(Context *ctx, int32_t x, int32_t y);
uint32_t ai_is_dual_support_unit(Context *ctx, gaddr unit, int32_t x, int32_t y);
/* ai_items.c */
int32_t ai_item_index_heal(Context *ctx, gaddr think, gaddr unit, uint32_t check_kind, uint32_t with_partner);
int32_t ai_item_index_doping(Context *ctx, gaddr think, gaddr unit);
uint32_t ai_has_heal_rod(Context *ctx, gaddr unit, uint32_t needs_range);

/* RVCT's signed division (0x002FFA0C), which the game calls: toward zero, and
   0 for a division by zero (its handler returns 0). */
static inline int32_t ai_div(int32_t a, int32_t b) {
    if (b == 0)
        return 0;
    if (b == -1)
        return (int32_t)(0u - (uint32_t)a);
    return a / b;
}

/* |v| as the game's RSBLT forms it (the most negative value stays itself) */
static inline int32_t ai_abs(int32_t v) {
    return v < 0 ? (int32_t)(0u - (uint32_t)v) : v;
}

#endif /* FE_AI_AI_PERM_H */
