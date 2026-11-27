/* What the shop window greys out (Fates: the castle shop's buy list): the
   declarations of src/readable/shop_grey/shop_grey.c and the guest functions
   it still calls.

   Plain-language description (what each function decides): docs/SHOP_GREY.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_SHOP_GREY_SHOP_GREY_H
#define FE_SHOP_GREY_SHOP_GREY_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-16: it stores nothing.
   Where the game calls a function (BL, or a virtual BLX), the readable code
   makes the same guest call in the game's order with the game's arguments
   (docs/DECISIONS.md F-018), also when the callee is an override of an
   older batch. */
#define SG_ItemToData 0x003D0EA4u      /* unit::Item::ToData(void) const (readable: item_to_data) */
#define SG_GameUserDataGet 0x001B3AFCu /* GameUserData::Get(void) -> the word at 0x006DA248; reads only */

/* The buy list's class table (address point 0x0063CA64; docs/SHOP_GREY.md 4).
   The readable code calls whatever the menu item's table holds, as the game
   does. In the buy list's own table:
     +0x6C  ItemBuyMenuItem::GetUnitItem 0x0052834C (this + 0x3A, reads nothing)
     +0x74  ItemBuyMenuItem::GetPrice    0x00528454 (readable: shop_buy_price) */
#define SG_SLOT_GET_UNIT_ITEM 0x6Cu
#define SG_SLOT_GET_PRICE 0x74u

/* ---- the buy-list menu item (anonymous_namespace::ItemBuyMenuItem) */
#define SG_MENU_DISCOUNT 0x38u   /* u8: not 0 = the price is cut to 19/20 here [low for when the
                                    game sets it; GetPrice itself does not cut it] */
#define SG_MENU_STOCK 0x40u      /* ptr: the line's stock record, or 0 (no stock limit) */
#define SG_STOCK_COUNT 0x02u     /* u8 of the stock record: how many are left */
#define SG_NO_STOCK (-1)         /* GetStock's answer when the line has no stock record */

/* ---- the price cut: price * 19 / 20, a signed 32-bit product (wraps) and a
   division toward zero, as the game's multiply-by-reciprocal does */
#define SG_DISCOUNT_MUL 19
#define SG_DISCOUNT_DIV 20

/* ---- the save's gold: GameUserData +0x38 (a signed word) [medium: the buy
   list compares it with the price and divides it by the price; no other use
   was traced] */
#define SG_USER_GOLD 0x38u

/* ---- the shop's own data: the word at 0x006D8A68 points to it
   (ShopSequence::Create 0x001BEC40 allocates it and stores the pointer there;
   the shop functions all read it through this word) */
#define SG_ShopSequenceData 0x006D8A68u
#define SG_SHOP_OWNER 0x31u      /* u8: ShopSequence::Create's third argument (ShopOwner::Type);
                                    not 0 = at most 1 per buy [low for which owners] */
#define SG_MAX_OTHER_OWNER 1     /* the buy limit when the owner byte is not 0 */
#define SG_MAX_OWN 99            /* the buy limit otherwise */

/* ---- the readable functions (override entries at the end of the file) */
int32_t shop_stock(Context *ctx, gaddr menu_item);
uint32_t shop_price_disabled(Context *ctx, gaddr menu_item);
int32_t shop_buy_max(Context *ctx, gaddr menu_item);

#endif /* FE_SHOP_GREY_SHOP_GREY_H */
