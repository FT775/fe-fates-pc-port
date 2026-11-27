# What the shop window greys out (Fates): stock, "too dear", and the buy limit

**In plain words.** This batch (docs/tracks/REWRITE_ORDER3.md row 4) rewrites three questions the
castle shop's buy list asks about one line. How many are left in stock. Whether the line is greyed out
because the save has less gold than the price. And how many one buy may take. All three only read.
None of them takes gold, adds an item, or draws anything. The function that changes the save's gold
still has no name in the symbol list, so it is not guessed here.

Status 2026-11-16 (round 16 batch `shop_grey`). All three are **UNVERIFIED** in the project's sense:

- **3 readable overrides** (`src/readable/shop_grey/shop_grey.c`, registry and target rows added):
  `shop_stock`, `shop_price_disabled`, `shop_buy_max`.
- No helper. No function was left out for storing: none of the three stores anything.

Each one matches the game's own ARM code on made-up cases (two seeds): the same guest calls in the
same order, and the same unmapped reads. The planted bugs and the tier-2 result are in section 6. It
has not been in a live compare yet. A separate capture step does that. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-16) [high unless marked]. No table values or game text are copied here.

---

## 1. How many are left (override)

**`anonymous_namespace::ItemBuyMenuItem::GetStock`** (0x00528470, `shop_stock`). A leaf: no calls.

```
stock = the menu item's word +0x40      (the line's stock record, or 0)
stock == 0:  -1                          (no stock limit)
else:        the stock record's byte +2  (how many are left, 0 .. 255)
```

## 2. Greyed out for its price (override)

**`anonymous_namespace::ItemBuyMenuItem::IsPriceDisable`** (0x005283F0, `shop_price_disabled`).

```
item   = the menu item's virtual GetUnitItem(menu item)    class table slot +0x6C, through the guest
record = unit::Item::ToData(item)                           through the guest
price  = record.buy_price (ItemData +0x2C)
the menu item's byte +0x38 not 0:  price = price * 19 / 20  (32-bit product that wraps, division
                                                              toward zero)
user   = GameUserData::Get()                                through the guest
answer = 1 when user's word +0x38 (the gold) < price, else 0   (signed compare)
```

So a line is greyed out when the save cannot pay for one. The cut to 19/20 is a 5% discount. Which
shops set the byte at +0x38 was not traced [low]. The shop-price batch's `shop_buy_price` (the price
the list shows) does **not** apply that cut; only these two readers do. That is what the game's code
does, and the readable code keeps it.

The gold is GameUserData's word +0x38 [medium: this list compares it with the price and divides it by
the price; no other use was traced]. It is a local name in `shop_grey.h` (`SG_USER_GOLD`), not a new
field in the shared struct table.

## 3. How many one buy may take (override)

**`anonymous_namespace::ItemBuyMenuItem::GetBuySellMax`** (0x00528354, `shop_buy_max`).

```
price = the menu item's virtual GetPrice(menu item)         class table slot +0x74, through the guest
the menu item's byte +0x38 not 0:  price = price * 19 / 20  (as in section 2)
user  = GameUserData::Get()                                 through the guest
most  = gold / price                                        RVCT signed division 0x002FFA0C: toward
                                                             zero; 0 when the price is 0 (its handler
                                                             0x0013F8B4 returns 0); the most negative
                                                             gold over -1 stays itself
stock record (+0x40) not 0, and most > its count:  most = the count
shop = the word at 0x006D8A68 (the shop's own data)
shop's byte +0x31 not 0:  most = at most 1
else:                     most = at most 99
answer = most                                               (nothing raises a negative answer)
```

The shop's own data is made by `ShopSequence::Create` (0x001BEC40), which stores the pointer in the
word at 0x006D8A68. Its byte +0x31 is Create's third argument, the `ShopOwner::Type`. Which owners are
not 0 (for example another player's castle) was not traced [low]. The division is the game's own
runtime helper, not a call of interest; in C it is a small function in `shop_grey.c` (`rvct_div`),
the same rule as the AI batch's `ai_div`.

In the buy list's own class table, slot +0x74 is `ItemBuyMenuItem::GetPrice`, which is the shop-price
batch's `shop_buy_price`. The readable code calls whatever the table holds, as the game does.

## 4. Reach

No BL calls any of the three. Each is reached only through the ItemBuyMenuItem class table (address
point 0x0063CA64): GetUnitItem at slot +0x6C (0x0063CAD0), GetStock +0x70 (0x0063CAD4), GetPrice +0x74
(0x0063CAD8), IsPriceDisable +0x78 (0x0063CADC), GetBuySellMax +0x80 (0x0063CAE4). Which window
functions call them through the table was not traced [low]. The plan row names the routes that may meet
them: the five shop routes the shop-price batch recorded, plus the cheat forge route. Whether they
open the buy list, and so meet these readers, is for the capture step to say. A Conquest or Revelation
shop is not on any named route (F-025 has them paused).

A shop mod can be checked against these three. None of them can change a price, the stock, or the gold.
That would be a table edit or a writer.

## 5. Not here, and why

- **They store** (writers, or worse): `ItemBuyMenuItem::ACall` (0x003B433C, the buy action),
  `Transporter::Add` (0x001A7050, puts the item in the convoy), and the gold change (**not named** in
  the symbol list, so none is guessed).
- **The window**: every draw function (`castle::ShopBuyUnitInfoDrawer::Draw`, `ItemMenuItem::DrawPrice`,
  `GetColorPrice`, `ItemMenu::DrawTitle`) and the menu creators (`ProcSequence::CreateItemBuyMenu`).
- **Not in the row**: the sell list's own `ItemSellMenuItem::GetStock`, `GetBuySellMax` and
  `IsPriceDisable` (0x005284B8 .. 0x00528540). They sit next to these and look small, but the plan row
  names the buy list only.

## 6. Checks and results

**Host differential test:** `python src/readable/shop_grey/tests/shop_grey_diff.py` (the method of
shop_price_diff.py). The ARM interpreter src/readable/battle/tests/arm_mini.py runs on
extracted/text.bin, and the readable C is built with the host gcc. Both sides compare r0, the unmapped
reads, and the whole ordered list of guest calls with their argument registers. Each callee is answered
by one table on both sides and listed: unit::Item::ToData, GameUserData::Get,
ItemBuyMenuItem::GetUnitItem, ItemBuyMenuItem::GetPrice, and two made-up functions a class table may
hold in either slot instead. The division runs inside arm_mini, the game's own code, divide-by-zero
handler included. No callee gives up, and nothing here reads a one-time cache, so no early give-up is
allowed.

The made-up states are random test values, never game data, often outside what the game uses:
unmapped menu items (GetStock only), records, stock records, GameUserData and shop data, the 0x006D8A68
word missing, slots holding another function, prices of 0, -1, negative, or so large the 19/20 cut
wraps, gold of 0, negative or huge, gold set right at the price, the cut price, or a cap times the price,
stock counts of 0 and past 127, and discount and owner bytes of any value.

**Planted bugs** (`--plant`, 37): every small change found that can change an answer (F-027). For the
stock: the wrong field or count offset, 0 instead of -1, a signed count. For "greyed out": the wrong
slot or `this`, the virtual call or ToData skipped, ToData asked for the menu item, the sell price, the
discount test inverted, on the wrong byte, or skipped, `<=` instead of `<`, an unsigned compare, the
gold offset, GameUserData read directly. For the cut: 18 or 19 instead of 19 or 20, a 64-bit product,
an unsigned division. For the buy limit: the wrong slot or `this`, the gold asked before the price
(call order), the cut skipped, a division by zero that gives the gold, -1 not negating, a floor
division, the wrong stock offset, the stock cap skipped or signed, the wrong shop word or owner byte,
the owner test inverted, caps of 2 or 100, and a floor at 0 the game does not have. A change that
cannot change an answer ("more than the stock" written "at least the stock", the stock and owner caps
in the other order) is not a bug and is not planted.

- Host test, seed 20261116, 300 cases per function, with `--plant`: **900 cases, 0 mismatches,
  37/37 planted bugs caught** (plants on 300 cases per function of seed 20261117).
- Host test, seed 7, with `--plant`: **900 cases, 0 mismatches, 37/37 planted bugs caught**.
- Host test, seed 7, 1500 cases per function: **4,500 cases, 0 mismatches**.
- Paths met (seed 20261116): stock with no record, a record, a count past 127, an unmapped record and an
  unmapped menu item; "greyed out" and "not greyed out", each with and without the discount, through
  GetUnitItem and another slot function, and with an unmapped GameUserData; the buy limit at 0, 1 (owner),
  99, negative and other values, with and without stock and the discount, a price of 0, another slot
  function and an unmapped GameUserData.
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_shop_grey --only
  0x00528470,0x005283F0,0x00528354`; the verify library was built from the tree
  as it stood then, which took 383 s): **1 ABI-ONLY, 2 UNSAMPLED, 0 MISMATCH** (`readable-verify: OK`).
  `shop_stock` is ABI-ONLY: the readable r0 equals the game's, and the only difference is verify's own
  count of unmapped reads (the original's plus the readable code's same reads in the shadow pass), not
  guest state. `shop_price_disabled` and `shop_buy_max` are UNSAMPLED, as `shop_buy_price` was: in
  verify's made-up state the game's own code (and the generated original) runs past the interpreter's
  instruction limit in both passes, so nothing was compared. That proves nothing either way. The likely
  cause is the same as for `shop_buy_price`: the made-up menu item's class-table slot sends the virtual
  call into junk [low: not traced]. The host test is the check that counts for these two until the
  capture step records them.
