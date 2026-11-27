/* Shop price, not the shop window (Fates: the castle shop's buy list and the
   convoy). Plain-language description: docs/SHOP_PRICE.md.

   - shop_buy_price is a reader: the price the buy list shows for one line
     (the item record's buy price). It stores nothing.
   - convoy_stack_value is a helper: the value Transporter::Add gives a stack
     when the convoy is full, to choose which stack makes room. It stores
     nothing, but the game's function returns 64 bits (r0:r1) and an override
     entry gives back r0 only, so it has no override; the host test checks
     both halves.

   Not here: the sell price and "may this be forged" (the item batch,
   src/readable/item/item_value.c), the gold the shop takes (a store; the
   gold writer is not named), the buy list's window and its creators
   (ShopBuyUnitInfoDrawer::Draw, ProcSequence::CreateItemBuyMenu).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/shop_price/tests/shop_price_diff.py. */

#include "shop_price.h"

/* The buy price of one line of the shop's buy list: the menu item's unit::Item
   (its class's virtual GetUnitItem, called through the guest), then its Item
   record's buy price (unit::Item::ToData through the guest).
   Guest function: 0x00528454 anonymous_namespace::ItemBuyMenuItem::GetPrice(void) const. */
int32_t shop_buy_price(Context *ctx, gaddr menu_item) {
    gaddr table = guest_ptr(ctx, menu_item);
    gaddr item = guest_call1(ctx, guest_ptr(ctx, table + SP_MENU_GET_UNIT_ITEM_SLOT), menu_item);
    gaddr record = guest_call1(ctx, SP_ItemToData, item);
    return READ_FIELD(ctx, ItemData, record, buy_price);
}

/* Whether the item counts as forged here: a forge rank (GetRefineRank through
   the guest), or else a name slot of 2 and up. */
static int counts_as_forged(Context *ctx, gaddr item) {
    if (guest_call1(ctx, SP_ItemGetRefineRank, item) != 0)
        return 1;
    return (guest_u16(ctx, item + SP_ITEM_BITS) & SP_ITEM_BITS_NAME) >= SP_NAMED_FORGE_SLOT;
}

/* The worth of one of the item: the record's buy price, scaled by the uses
   left over the record's full uses when both are above 0 (unsigned 32-bit
   product and division, as the game does). */
static uint32_t unit_worth(Context *ctx, gaddr record, int32_t uses) {
    if (uses <= 0)
        return (uint32_t)READ_FIELD(ctx, ItemData, record, buy_price);
    uint32_t full = READ_FIELD(ctx, ItemData, record, uses);
    if (full == 0)
        return (uint32_t)READ_FIELD(ctx, ItemData, record, buy_price);
    return ((uint32_t)READ_FIELD(ctx, ItemData, record, buy_price) * (uint32_t)uses) / full;
}

/* The value the convoy gives a stack of `count` of `item` with `uses` uses
   left (64 bits; bigger = kept first):
     high word = forge rank << 28 (a forged item only: GetRefineRank asked again)
               + 0x08000000 when the record's pool ranks 0 and 1 are both below 0
               + for an item of buy price 0: count << 16, plus 0xFFFF - its item number
     plus      the unit worth times count (a signed 64-bit product, added to the
               whole 64 bits, so it may carry into the high word).
   Every add wraps as the game's does. ToData is asked again for each record
   read, through the guest, in the game's order.
   Guest function: helper of 0x001A6F4C Transporter::anonymous_namespace::GetPrice(const unit::Item*,int,int)
   (a reader whose 64-bit result an override cannot give back). */
uint64_t convoy_stack_value(Context *ctx, gaddr item, int32_t uses, int32_t count) {
    uint32_t high = 0;
    if (counts_as_forged(ctx, item))
        high = guest_call1(ctx, SP_ItemGetRefineRank, item) << SP_RANK_SHIFT;
    int pooled = 0;
    for (int i = 0; i < SP_POOL_RANKS_ASKED && !pooled; i++) {
        gaddr record = guest_call1(ctx, SP_ItemToData, item);
        pooled = guest_s8(ctx, FIELD_ADDR(ItemData, record, pool_rank) + (gaddr)i) >= 0;
    }
    if (!pooled)
        high += SP_UNPOOLED_BIT;
    if (READ_FIELD(ctx, ItemData, guest_call1(ctx, SP_ItemToData, item), buy_price) == 0) {
        high += (uint32_t)count << SP_COUNT_SHIFT;
        high += SP_NUMBER_FLIP - READ_FIELD(ctx, ItemData, guest_call1(ctx, SP_ItemToData, item), item_number);
    }
    uint32_t worth = unit_worth(ctx, guest_call1(ctx, SP_ItemToData, item), uses);
    int64_t total = (int64_t)(int32_t)worth * (int64_t)count;
    return ((uint64_t)high << 32) + (uint64_t)total;
}

RECOMP_OVERRIDE(0x00528454) {
    FE_ENTRY(0x00528454, shop_buy_price, FE_ARG(0));
}
