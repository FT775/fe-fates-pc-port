/* Items and weapons (Fates classes Item, unit::Item, ItemKind, ItemRefine and
   the item questions of Unit): the declarations shared by
   src/readable/item/item_record.c, item_value.c and item_unit.c, the guest
   functions they still call, and the game's one-time caches they read.

   Plain-language description (what each function decides): docs/ITEM.md.

   Two kinds of "item" meet here:
   - the Item record (ItemData, 0x68 bytes, config/readable/structs: the
     game's table row of an item: kind, might, hit, crit, ranges, prices,
     flag word), found by its item number with Item::Get;
   - the unit::Item a unit or the convoy carries (4 bytes): the u16 item
     number, then a u16 of small fields (ITEM_BITS_* below).

   This header lives next to its sources, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first).
   Never write the override marker in this header (staging pastes it into
   each file). */

#ifndef FE_ITEM_ITEM_H
#define FE_ITEM_ITEM_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-14: it stores nothing
   outside its own stack frame, or only fills a one-time cache of its own.
   Where the game calls (BL) a function that has a readable override (this
   batch's or an older one), the readable code calls it through the guest
   too, in the game's order and with the game's arguments
   (docs/DECISIONS.md F-018). A fall-through or a tail branch is not a call:
   the readable code then runs the C directly. */
#define ITEM_ItemSubKindGet 0x0019B97Cu    /* ItemSubKind::Get(int) -> the sub-kind record (readable:
                                              item_subkind_record, the triangle batch) */
#define ITEM_UnitGetPowImpl 0x0052A500u    /* Unit::GetPowImpl(...) (readable: unit_magic): five arguments,
                                              the fifth on the stack: called with guest_call5 (round 11) */
#define ITEM_UnitIsEquipSkill 0x0052DD04u  /* Unit::IsEquipSkill(short) const (readable: unit_has_skill) */
#define ITEM_UnitCanItemEquip 0x0052C634u  /* Unit::CanItemEquip(const unit::Item*,bool,bool) const; reads only
                                              (3,352 bytes; readable since: unit_can_equip_item) */

/* this batch's own overrides, called through the guest where the game calls them */
#define ITEM_ItemToData 0x003D0EA4u        /* unit::Item::ToData(void) const: item_to_data */
#define ITEM_ItemGet 0x003D0EACu           /* Item::Get(unsigned short): item_record */
#define ITEM_ItemRefineGet 0x0017CFA8u     /* ItemRefine::Get(int,int): item_refine_record */
#define ITEM_ItemIsWeapon 0x00529164u      /* Item::IsWeapon(void) const: item_is_weapon */
#define ITEM_ItemIsMagic 0x005290B8u       /* Item::IsMagic(void) const: item_is_magic */
#define ITEM_ItemIsShopRefine 0x0053B0F8u  /* unit::Item::IsShopRefine(void) const: item_can_forge */

/* ---- tables (pointers the game's loaders store; read every call, not caches) */
#define G_ItemArchiveList 0x006D38D0u      /* the first node of the list of loaded Item blocks (or 0) */
#define G_ItemKindTable 0x006D3950u        /* ItemKind::Get(n) = this pointer + n * 0x0C */
#define G_ItemRefineTable 0x006D3958u      /* ItemRefine::Get(t, r) = this pointer + (t * 10 + r) * 4 */

/* an Item block list node: the block, then (+8) the next node */
#define ITEM_NODE_BLOCK 0x00u
#define ITEM_NODE_NEXT 0x08u
/* an Item block: u16 count at +6, the records from +8 (0x68 bytes each); the
   first record's item number (block +0x1C = record 0 +0x14) is the block's
   first number */
#define ITEM_BLOCK_COUNT 0x06u
#define ITEM_BLOCK_FIRST_NUMBER 0x1Cu
#define ITEM_BLOCK_RECORDS 0x08u
#define ITEM_RECORD_SIZE 0x68u
#define ITEM_KIND_RECORD_SIZE 0x0Cu
#define ITEM_REFINE_ROW 10u                /* ranks per forge table */
#define ITEM_REFINE_RECORD_SIZE 4u         /* ItemRefine record: +1 might, +2 hit, +3 crit (u8 each) */

/* ---- one-time caches (guard word, bit 0 = filled; the value the game looked
   up by name the first time). Readable code reads a cached value only when
   its guard says it is filled and gives up otherwise, before reading anything
   else. Addresses from each function's literal pool. The names are the
   game's ID labels (ISID_ = ItemSkill flag bit, SEID_ = equip skill), given
   here in English [med for the English names]. */

/* class Item (literal 0x006D38D0) */
#define S_ItemMagicGuard 0x006D38D4u       /* Item::IsMagic */
#define S_ItemHiddenGuard 0x006D38D8u      /* Item::IsHiddenEffect */
#define S_ItemUsableGuard 0x006D38DCu      /* Item::CanUse */
#define S_ItemMagicMask 0x006D3920u        /* u64 ISID "magic weapon" */
#define S_ItemHiddenMask 0x006D3928u       /* u64 ISID "concealed weapon" */
#define S_ItemUsableMask 0x006D3930u       /* u64 ISID "usable" */
/* class unit::Item (literal 0x006D9EC8) */
#define S_ExpendGuard 0x006D9EC8u          /* unit::Item::IsExpend */
#define S_SellGuard0 0x006D9ED0u           /* unit::Item::GetSellPrice, asked first */
#define S_SellGuard1 0x006D9ECCu
#define S_ForgeGuard0 0x006D9EDCu          /* unit::Item::IsShopRefine(void), in the game's order */
#define S_ForgeGuard1 0x006D9ED8u
#define S_ForgeGuard2 0x006D9ED4u
#define S_ExpendMask 0x006D9F10u           /* u64 ISID "unlimited uses" */
#define S_SellMaskValuable 0x006D9F18u     /* u64 ISID "valuable" */
#define S_SellMaskLocked 0x006D9F20u       /* u64 ISID "cannot be removed" */
#define S_ForgeMaskNoForge 0x006D9F28u     /* u64 ISID "cannot be forged" */
#define S_ForgeMaskValuable 0x006D9F30u    /* u64 ISID "valuable" */
#define S_ForgeMaskLocked 0x006D9F38u      /* u64 ISID "cannot be removed" */
/* class Unit (literals 0x006D9628 / 0x006D9A28) */
#define S_RangeOGuard 0x006D989Cu          /* Unit::GetRangeO */
#define S_RangeOSkill 0x006D967Au          /* s16 SEID "endless staff": a staff reaches at least 10 */
#define S_HealGuard0 0x006D9910u           /* Unit::GetItemHealPower, five guards in the game's order */
#define S_HealGuard1 0x006D990Cu
#define S_HealGuard2 0x006D9908u
#define S_HealGuard3 0x006D9904u
#define S_HealGuard4 0x006D9900u
#define S_HealSkill 0x006D96AAu            /* s16 SEID "potent medicine": half again for the item below */
#define S_HealMask 0x006D9C38u             /* u64 ISID "standing medicine" */

/* ---- record fields read here (ItemData in config/readable/structs/ names
   most of them; these are the ones used as plain offsets) [high] */
#define ITEM_HEAL 0x40u                    /* ItemData.extra_data[0] (s8): the HP an item heals */
#define ITEM_REFINE_TABLE_2 0x49u          /* ItemData.unknown_49: the forge table of a unit::Item whose name slot is 1 */
#define UNIT_CONDITION_0 0x28u             /* Unit condition byte 0: bit 3 = no magic for the cannon check */
#define UNIT_ITEMS 0x108u                  /* Unit: five unit::Items */

/* ---- the unit::Item's second halfword */
#define ITEM_BITS 0x02u
#define ITEM_BITS_NAME 0x7Fu               /* bits 0-6: 0 none, 1 the second forge table, 2+ a forged name slot */
#define ITEM_BITS_NO_FORGE 0x80u           /* bit 7: no forge bonus */
#define ITEM_BITS_COUNT_SHIFT 8u           /* bits 8-13: forge rank of a weapon, uses left of anything else */
#define ITEM_BITS_COUNT_MASK 0x3Fu

#define ITEM_RANGE_MAGIC 0xFEu             /* ItemData.range_max: half the unit's magic (no item uses it) */
#define ITEM_STAFF_RANGE 10
#define ITEM_KIND_STAFF 6                  /* ItemSubKindData.kind */

/* ---- the readable functions (override entries at the end of each file) */
/* item_record.c */
gaddr item_record(Context *ctx, uint32_t number);
gaddr item_to_data(Context *ctx, gaddr item);
gaddr item_try_record(Context *ctx, uint32_t number);
gaddr item_kind_record(Context *ctx, uint32_t kind);
gaddr item_refine_record(Context *ctx, uint32_t table, uint32_t rank);
uint32_t item_is_weapon(Context *ctx, gaddr record);
uint32_t item_is_magic(Context *ctx, gaddr record);
uint32_t item_can_use(Context *ctx, gaddr record);
uint32_t item_is_download(Context *ctx, gaddr record);
uint32_t item_is_hidden_effect(Context *ctx, gaddr record);
/* item_value.c */
int32_t item_might(Context *ctx, gaddr item);
int32_t item_hit(Context *ctx, gaddr item);
int32_t item_crit(Context *ctx, gaddr item);
int32_t item_uses_left(Context *ctx, gaddr item);
int32_t item_forge_rank(Context *ctx, gaddr item);
uint32_t item_same_kind(Context *ctx, gaddr item, gaddr other);
uint32_t item_equals(Context *ctx, gaddr item, gaddr other);
uint32_t item_is_consumable(Context *ctx, gaddr item);
uint32_t item_can_forge(Context *ctx, gaddr item);
uint32_t item_can_forge_with(Context *ctx, gaddr item, gaddr other);
int32_t item_sell_price(Context *ctx, gaddr item);
/* item_unit.c */
int32_t unit_range_max(Context *ctx, gaddr unit, gaddr item);
int32_t unit_item_heal_amount(Context *ctx, gaddr unit, gaddr item);
uint32_t unit_can_cannon_item(Context *ctx, gaddr unit, gaddr item, uint32_t check_magic);
uint32_t unit_has_cannon_item(Context *ctx, gaddr unit, uint32_t check_magic);

#endif /* FE_ITEM_ITEM_H */
