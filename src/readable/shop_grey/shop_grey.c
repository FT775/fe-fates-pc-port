/* What the shop window greys out (Fates: the castle shop's buy list).
   Plain-language description: docs/SHOP_GREY.md.

   Three readers of one buy-list line. Each stores nothing:
   - shop_stock: how many the line has left (-1 = no stock limit).
   - shop_price_disabled: 1 when the save's gold is below the line's price
     (cut to 19/20 when the line's discount byte is set), so the line is
     greyed out.
   - shop_buy_max: how many one buy may take: the gold over the price, then no
     more than the stock, then no more than 1 (another owner's shop) or 99.

   Not here: the buy action (ItemBuyMenuItem::ACall, which stores), the
   convoy's Transporter::Add (stores), the gold change (a store; the function
   is not named in the symbol list, so none is guessed), and every draw
   function of the window. The line's price is the shop-price batch's
   shop_buy_price (src/readable/shop_price/), which shop_buy_max reaches
   through the class table, as the game does.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/shop_grey/tests/shop_grey_diff.py. */

#include "shop_grey.h"

/* RVCT's signed division (0x002FFA0C), which the game calls: toward zero, and
   0 for a division by zero (its handler, 0x0013F8B4, returns 0). The most
   negative value over -1 stays itself, as the game's negation leaves it. */
static int32_t rvct_div(int32_t a, int32_t b) {
    if (b == 0)
        return 0;
    if (b == -1)
        return (int32_t)(0u - (uint32_t)a);
    return a / b;
}

/* The price cut to 19/20 (the product wraps, the division goes toward zero). */
static int32_t cut_price(int32_t price) {
    return (int32_t)((uint32_t)price * (uint32_t)SG_DISCOUNT_MUL) / SG_DISCOUNT_DIV;
}

/* The save's gold: GameUserData::Get through the guest, then its word +0x38. */
static int32_t save_gold(Context *ctx) {
    gaddr user = guest_call(ctx, SG_GameUserDataGet, 0u, 0u, 0u, 0u);
    return guest_s32(ctx, user + SG_USER_GOLD);
}

/* How many the buy-list line has left: its stock record's count, or -1 when
   the line has no stock record.
   Guest function: 0x00528470 anonymous_namespace::ItemBuyMenuItem::GetStock(void) const. */
int32_t shop_stock(Context *ctx, gaddr menu_item) {
    gaddr stock = guest_ptr(ctx, menu_item + SG_MENU_STOCK);
    if (stock == 0)
        return SG_NO_STOCK;
    return guest_u8(ctx, stock + SG_STOCK_COUNT);
}

/* Whether the line is greyed out for its price: the line's unit::Item (the
   class's virtual GetUnitItem, through the guest), its Item record (ToData,
   through the guest), the record's buy price, cut to 19/20 when the line's
   discount byte is set; 1 when the save's gold is below that (signed).
   Guest function: 0x005283F0 anonymous_namespace::ItemBuyMenuItem::IsPriceDisable(void) const. */
uint32_t shop_price_disabled(Context *ctx, gaddr menu_item) {
    gaddr table = guest_ptr(ctx, menu_item);
    gaddr item = guest_call1(ctx, guest_ptr(ctx, table + SG_SLOT_GET_UNIT_ITEM), menu_item);
    gaddr record = guest_call1(ctx, SG_ItemToData, item);
    int32_t price = READ_FIELD(ctx, ItemData, record, buy_price);
    if (guest_u8(ctx, menu_item + SG_MENU_DISCOUNT) != 0)
        price = cut_price(price);
    return save_gold(ctx) < price ? 1u : 0u;
}

/* How many one buy may take: the line's price (the class's virtual GetPrice,
   through the guest), cut to 19/20 when the discount byte is set; the save's
   gold over that price (0 when the price is 0); no more than the stock count
   when the line has a stock record; then no more than 1 when the shop's owner
   byte is set, else no more than 99. Nothing raises a negative answer.
   Guest function: 0x00528354 anonymous_namespace::ItemBuyMenuItem::GetBuySellMax(void) const. */
int32_t shop_buy_max(Context *ctx, gaddr menu_item) {
    gaddr table = guest_ptr(ctx, menu_item);
    int32_t price = (int32_t)guest_call1(ctx, guest_ptr(ctx, table + SG_SLOT_GET_PRICE), menu_item);
    if (guest_u8(ctx, menu_item + SG_MENU_DISCOUNT) != 0)
        price = cut_price(price);
    int32_t most = rvct_div(save_gold(ctx), price);
    gaddr stock = guest_ptr(ctx, menu_item + SG_MENU_STOCK);
    if (stock != 0) {
        int32_t left = guest_u8(ctx, stock + SG_STOCK_COUNT);
        if (most > left)
            most = left;
    }
    gaddr shop = guest_ptr(ctx, SG_ShopSequenceData);
    if (guest_u8(ctx, shop + SG_SHOP_OWNER) != 0) {
        if (most > SG_MAX_OTHER_OWNER)
            most = SG_MAX_OTHER_OWNER;
    } else if (most > SG_MAX_OWN) {
        most = SG_MAX_OWN;
    }
    return most;
}

RECOMP_OVERRIDE(0x00528470) {
    FE_ENTRY(0x00528470, shop_stock, FE_ARG(0));
}

RECOMP_OVERRIDE(0x005283F0) {
    FE_ENTRY(0x005283F0, shop_price_disabled, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00528354) {
    FE_ENTRY(0x00528354, shop_buy_max, FE_ARG(0));
}
