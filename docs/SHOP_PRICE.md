# Shop price, not the shop window (Fates): the buy list's price, and the convoy's "which stack makes room" value

**In plain words.** This batch (docs/tracks/REWRITE_ORDER2.md batch 6) rewrites the two price
questions the plan names. The first is the price the castle shop's buy list shows for one line:
the item's buy price from its item record. The second is the number the convoy gives a stack when
the convoy is full and a new item comes in: the stack with the smallest number makes room. The sell
price and "may this be forged" were already done by the item batch (docs/ITEM.md). Nothing here
takes or gives gold. That would be a store, and the function that does it has no name in the symbol
list, so it is not guessed here.

Status 2026-11-16 (round 12+ batch `shop_price`). Both are **UNVERIFIED** in the project's sense:

- **1 readable override** (`src/readable/shop_price/shop_price.c`, registry and target rows added):
  `shop_buy_price`.
- **1 helper**: `convoy_stack_value`. The game's function only reads, but it returns 64 bits
  (r0:r1). An override entry (`FE_ENTRY`, include/readable/fe_guest.h) gives back r0 only, and
  every compare (shadow, capture, verify) checks r0 only. So it has no override, and the host test
  checks both halves.

Each one matches the game's own ARM code on made-up cases (two seeds): the same guest calls in the
same order, and the same unmapped reads. The planted bugs and the tier-2 result are in section 5.
It has not been in a live compare yet. A separate capture step does that. Nothing changes in the
game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-16) [high unless marked]. No table values or game text are copied here.

---

## 1. The buy list's price (override)

**`anonymous_namespace::ItemBuyMenuItem::GetPrice`** (0x00528454, `shop_buy_price`). This is one line of
the shop's buy list.

```
item   = the menu item's virtual GetUnitItem(menu item)   class table slot +0x6C, through the guest
record = unit::Item::ToData(item)                          through the guest (the item batch's item_to_data)
price  = record.buy_price (ItemData +0x2C)                 returned as is (a signed word)
```

In the buy list's own class table (the address point is 0x0063CA64, and the slot is at 0x0063CAD0),
slot +0x6C is `ItemBuyMenuItem::GetUnitItem` (0x0052834C). That function returns the menu item's
address + 0x3A, the unit::Item it sells, and reads nothing. The readable code calls whatever the
table holds, the same way the game does (as `config_item_value` does, docs/MENUS.md).

**Reach.** No BL calls it. It is only reached through the ItemBuyMenuItem class table (0x0063CAD8).
Which window functions call it through the table was not traced [low].
`bt-castle-shop` opens the castle shop. Whether that route opens the buy list, and so meets this
reader, is for the capture step to say. A Conquest or Revelation shop is not on any named route
(F-025 has them paused).

## 2. The convoy's value of a stack (helper)

**`Transporter::anonymous_namespace::GetPrice`** (0x001A6F4C, `convoy_stack_value`). Its arguments
are a unit::Item, the uses left, and the stack's count. It returns 64 bits. Bigger means kept first.

```
high word (32 bits, every add wraps):
  forged = GetRefineRank(item) != 0, or (item's second halfword & 0x7F) >= 2
  forged:                       high  = GetRefineRank(item) << 28      (asked a second time)
  record.pool_rank[0] < 0 and record.pool_rank[1] < 0:
                                high += 0x08000000                    (ToData asked per entry read)
  record.buy_price == 0:        high += count << 16
                                high += 0xFFFF - record.item_number
worth = record.buy_price * uses / record.uses     when uses > 0 and record.uses != 0
        (unsigned 32-bit product and division)
      = record.buy_price                          otherwise
result = (high << 32) + worth * count             (signed 32 x 32 -> 64 product, added to all
                                                   64 bits, so a negative product borrows from high)
```

In plain words, a forged weapon always outranks an unforged one, and a higher forge rank outranks a
lower one. Next come items whose first two pool ranks are both below 0 [low for what those pool
ranks mean: ItemData.pool_rank names them gain0_hoshido and gain0_nohr, config/readable/structs].
An item with no buy price is ranked by its count and then by a lower item number. The rest is the
stack's buy-price worth: the price scaled by the uses left, times the count.

Each record read asks `unit::Item::ToData` again, through the guest, as the game does: once or twice
for the pool ranks (it stops at the first rank that is 0 or above), once for the price test, once
more for a price of 0, and once for the worth. `GetRefineRank` is the item batch's `item_forge_rank`,
asked once or twice. The division is the game's `text_udiv` (0x0012A0E4). That is a runtime helper,
not a call of interest, and in C it is a plain `/`.

**Reach.** Its only caller is `Transporter::Add` (0x001A7050), on its "convoy full" path. All 500
stacks are in use, and none of them is the same item. Add also works out this same value inline for
every stack and swaps out the smallest one if the new item is worth more. That inline copy is part
of Add, which stores, so it is not a reader. No named route fills the convoy [high: no route comes
close to 500 stacks]. So this helper is never met in play, and the host test is its only check.

A shop-price or convoy mod can be checked against these two. It cannot change a price. That would
be a table edit or a writer.

## 3. Not here, and why

- **They store** (writers, or worse): the gold the shop takes or pays. The function that changes
  the save's gold is **not named** in the symbol list, so none is guessed. `Transporter::Add` puts
  the item into the convoy. `ItemBuyMenuItem::ACall` (0x003B433C) is the buy action.
- **The window**: `castle::ShopBuyUnitInfoDrawer::Draw` (0x00461184),
  `anonymous_namespace::ProcSequence::CreateItemBuyMenu` (0x003B3360) and the other buy-menu
  creators, `ItemMenuItem::DrawPrice` / `GetColorPrice`, and `ItemBuyMenuItem::IsPriceDisable`,
  `GetStock` and `GetBuySellMax`. These draw the window or decide what it greys out. They are not in
  the plan row. (Round 16: the last three are now the `shop_grey` batch, docs/SHOP_GREY.md.)
- **Already done** (item batch): `unit::Item::GetSellPrice` (`item_sell_price`, reached by falling
  through from `ItemSellMenuItem::GetPrice`), `IsShopRefine` (`item_can_forge`,
  `item_can_forge_with`).
- **Not looked at further**: `game::packet::Unit::GetPrice` / `GetPriceForDictionary` (a unit's
  price in the online packet code, not the shop).

## 4. Checks

**Host differential test:** `python src/readable/shop_price/tests/shop_price_diff.py` (the method of
weapon_rank_diff.py). The ARM interpreter src/readable/battle/tests/arm_mini.py runs on
extracted/text.bin, and the readable C is built with the host gcc. Both sides compare r0 (for the
helper, r0:r1 folded together with FNV-1a), the unmapped reads, and the whole ordered list of guest
calls with their argument registers. Nested give-ups and guest writes are flagged. Each callee is
answered by one table on both sides and listed: unit::Item::ToData, unit::Item::GetRefineRank,
ItemBuyMenuItem::GetUnitItem, and two made-up functions that a class table may hold at slot +0x6C
instead. No callee gives up, and nothing here reads a one-time cache, so no early give-up is
allowed. The helper runs through a test-only entry of the generated driver, never as a marker in
src/readable/.

The made-up states are random test values, never game data. They are often outside what the game
uses: unmapped menu items, items and records, a slot that holds another function, buy prices of 0,
negative or huge, full uses of 0, uses and counts of 0, negative or huge, forge ranks past 63, and
name slots with bit 7 set. The test prints which paths the cases met.

**Planted bugs** (`--plant`, 22): the wrong slot, `this`, or the call skipped; ToData done directly;
sell price instead of buy price; each boundary of "forged", "pooled", "price 0", "uses > 0" and
"full uses 0"; the rank shift; the rank not asked a second time; the pool loop too short or not
stopping; the count and item-number terms; signed instead of unsigned division; an unsigned product
or count; and the low word not carried into the high word.

**Tier 2** (`tools/readable/verify.py`): section 5.

## 5. Results (2026-11-16)

- Host test, seed 20261116, 300 cases per function, with `--plant`: **600 cases, 0 mismatches,
  22/22 planted bugs caught** (plants on 300 cases per function of seed 20261117). Paths met: the
  buy price went through GetUnitItem 254 times and through another slot function 46 times, with
  price 0 and unmapped records among them. The convoy value covered forged and plain items, each
  with pooled and unpooled records, price 0, scaled-by-uses and unmapped-record cases.
- Host test, seed 7, with `--plant`: **600 cases, 0 mismatches, 22/22 planted bugs caught**.
- Host test, seed 7, 1500 cases per function: **3,000 cases, 0 mismatches** (1,106 distinct convoy
  values).
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_shop_price --only 0x00528454`;
  the verify library was built from the tree as it stood then, which took 368 s): **1 UNSAMPLED,
  0 MISMATCH** (`readable-verify: OK`). UNSAMPLED means that in verify's made-up state the game's own
  code (and the generated original) runs past the interpreter's instruction limit in both passes, so
  nothing was compared. That proves nothing either way. The likely cause is that the made-up menu
  item's class-table slot sends the virtual call into junk, but this is [low]: it was not traced.
  The classifier was not changed. The helper has no override, so verify does not apply to it.
- `python tools/readable/check.py --selftest`: readable OK (lint 276 rows 0 problems, 47 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs, verify pipeline 28/28).
  `python tools/harness/gen_stubs.py --check`: OK (241 overrides at the time of the run).
