/* Shop price, not the shop window (Fates: the castle shop's buy list and the
   convoy's "which stack makes room" value): the declarations of
   src/readable/shop_price/shop_price.c and the guest functions it still
   calls.

   Plain-language description (what each function decides): docs/SHOP_PRICE.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_SHOP_PRICE_SHOP_PRICE_H
#define FE_SHOP_PRICE_SHOP_PRICE_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-16: it stores nothing.
   Where the game calls a function (BL, or a virtual BLX), the readable code
   makes the same guest call in the game's order with the game's arguments
   (docs/DECISIONS.md F-018), also when the callee is an override of an
   older batch. */
#define SP_ItemToData 0x003D0EA4u        /* unit::Item::ToData(void) const (readable: item_to_data) */
#define SP_ItemGetRefineRank 0x0053B278u /* unit::Item::GetRefineRank(void) const (readable: item_forge_rank) */

/* ItemBuyMenuItem's virtual GetUnitItem: slot +0x6C of the menu item's class
   table. In the buy list's own table (the class table at 0x0063CA64, the
   entry at 0x0063CAD0) it is ItemBuyMenuItem::GetUnitItem 0x0052834C, which
   returns the menu item's address + 0x3A (the unit::Item it sells) and reads
   nothing [high]. The readable code calls whatever the table holds, as the
   game does. */
#define SP_MENU_GET_UNIT_ITEM_SLOT 0x6Cu

/* ---- the unit::Item's second halfword (as src/readable/item/item.h ITEM_BITS) */
#define SP_ITEM_BITS 0x02u
#define SP_ITEM_BITS_NAME 0x7Fu         /* bits 0-6: 0 none, 1 the second forge table, 2+ a forged name slot */
#define SP_NAMED_FORGE_SLOT 2u          /* a name slot of 2 and up counts as forged */

/* ---- the convoy value's high word (docs/SHOP_PRICE.md 2) */
#define SP_RANK_SHIFT 28u               /* forge rank, shifted to bits 28-31 */
#define SP_UNPOOLED_BIT 0x08000000u     /* both ItemData.pool_rank[0] and [1] below 0 [low for what that means] */
#define SP_POOL_RANKS_ASKED 2           /* ItemData.pool_rank entries the game reads: 0 and 1 */
#define SP_COUNT_SHIFT 16u              /* an item of buy price 0: its stack count, shifted to bit 16 */
#define SP_NUMBER_FLIP 0xFFFFu          /* an item of buy price 0: 0xFFFF - its item number */

/* ---- the readable functions (override entry at the end of the file) */
int32_t shop_buy_price(Context *ctx, gaddr menu_item);
/* helper (no override): Transporter::GetPrice returns 64 bits in r0:r1, and
   an override entry gives back r0 only (fe_guest.h FE_ENTRY) */
uint64_t convoy_stack_value(Context *ctx, gaddr item, int32_t uses, int32_t count);

#endif /* FE_SHOP_PRICE_SHOP_PRICE_H */
