# Items and weapons (Fates): records, might / hit / crit, uses, forging, prices, read from the code

**In plain words.** Every fight, forecast and menu asks the same small questions about items:
which table row (record) belongs to this item, how strong the weapon is once forged, how many uses
a potion has left, whether it is a weapon or a tome, whether the smithy may forge it, what the shop
pays for it, how far a staff reaches, how much a vulnerary heals. This batch rewrites **25 of
those readers** as readable C (`src/readable/item/`). The status-sheet batch (docs/SHEET.md)
already did the equipped / held item and the item count; the triangle batch (docs/TRIANGLE.md) the
sub-kind table and weapon ranks; this batch does not repeat them.

All 25 are **readers**: they store nothing (docs/DECISIONS.md F-017, F-021: no writers, nothing
armed). They were written with host builds only (no robot runs, no capture-library build).

Status 2026-11-14: 25 readable overrides, all **UNVERIFIED** in the project's sense. Every one gives
the same answers as the game's own ARM code on made-up cases, with the same guest calls in the same
order and the same unmapped reads (section 6); every planted bug was caught. Not yet in a live
compare: tonight's round-10 integrate rebuilds the capture library and compares them in real play.
Nothing changes in the game.

Real play already reaches them: the round-9 capture runs (build/parallel/*/records/*/callbacks.tsv)
show the older overrides calling `unit::Item::ToData` 14,162 times, `GetPower` and `IsMagic` 553
times each, `GetHit` 483, `GetCritical` 427 and `GetRangeO` 286 times on the bt / cq / rv routes;
the rest are their callees or their neighbours in the same menus.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-14) [high unless marked]. No table values or game text are copied here; flag and skill
names are the game's ID labels (`ISID_` = item flag bit, `SEID_` = equip skill) given in English
[med for the English].

---

## 1. Finding an item's record

Two things are called "item" in the game:

- the **Item record**: the item's row of the item table (0x68 bytes: kind, might, hit, crit,
  ranges, prices, a 64-bit flag word ...; `ItemData` in config/readable/structs);
- the **carried item** (`unit::Item`, 4 bytes, in a unit's five slots or the convoy): the item's
  number, then a halfword of small fields: bits 0-6 a "name slot" (0 none, 1 = use the second forge
  table, 2 and up = a forged item's custom name), bit 7 "no forge bonus", bits 8-13 a **count**
  (the forge rank of a weapon, the uses left of anything else), bit 14 equipped.

| Function | Game name | What it decides |
|---|---|---|
| `item_record` | `Item::Get(unsigned short)` 0x003D0EAC | Walks the list of loaded item blocks (the game's own, then download ones). The first block whose numbers include this number gives the record. A number no block has gives the first record of the first block (the "nothing" item), so a bad number never crashes. |
| `item_to_data` | `unit::Item::ToData` 0x003D0EA4 | The record of a carried item: `Item::Get` of its number. |
| `item_try_record` | `Item::TryGet` 0x003D10A0 | Like `Item::Get`, but "none" (0) instead of the fallback. |
| `item_kind_record` | `ItemKind::Get(int)` 0x004EC1CC | The weapon-kind row (sword, lance ...): table + kind x 12. No range check. |
| `item_refine_record` | `ItemRefine::Get(int,int)` 0x0017CFA8 | The forge-bonus row of a forge table and a rank (ten ranks per table): its bytes 1, 2, 3 are the might, hit and crit bonus. |

## 2. Questions asked of a record

| Function | Game name | Yes when |
|---|---|---|
| `item_is_weapon` | `Item::IsWeapon` 0x00529164 | the item's kind is not a staff (6) and not kind 8 (the non-weapon items). |
| `item_is_magic` | `Item::IsMagic` 0x005290B8 | the kind is a tome (5) or a staff (6), or the record has the "magic weapon" flag (a magic sword or lance hits with magic). |
| `item_can_use` | `Item::CanUse` 0x00528F3C | the record has the "usable" flag (the Use command offers it). |
| `item_is_download` | `Item::IsDownload` 0x00528E68 | the item's number is not below the count of the first block (the game's own items): a download item. |
| `item_is_hidden_effect` | `Item::IsHiddenEffect` 0x00528E90 | a "concealed weapon": daggers and shuriken (sub-kind kind 3), sub-kind 19, or the "concealed weapon" flag (the after-battle stat hit). |

## 3. What a carried item is worth

**Might, hit and crit** (`unit::Item::GetPower` 0x0053B4B4, `GetHit` 0x0053B2A4, `GetCritical`
0x0053AD54): the record's value, plus a forge bonus when the item is a weapon with a forge rank
above 0 **or** any item with a custom name slot (2 and up), unless bit 7 says no bonus. The bonus is
byte 1 (might), 2 (hit) or 3 (crit) of the forge row for (the record's forge table, the item's rank)
(name slot 1 uses the record's second forge table). A non-weapon's rank counts as 0.

| Function | Game name | What it gives |
|---|---|---|
| `item_uses_left` | `unit::Item::GetEndurance` 0x0053AE48 | the count field for anything that is not a weapon; 0 for a weapon (Fates weapons do not break). |
| `item_forge_rank` | `unit::Item::GetRefineRank` 0x0053B278 | the count field for a weapon; 0 for anything else. |
| `item_same_kind` | `unit::Item::IsIntegrate` 0x0053AE18 | same item number and same name slot (what the convoy stacks). |
| `item_equals` | `unit::Item::IsEqual` 0x0053B470 | same number, name slot and count. |
| `item_is_consumable` | `unit::Item::IsExpend` 0x0053B578 | not a weapon, and no "unlimited uses" flag: it gets used up. |
| `item_can_forge` | `unit::Item::IsShopRefine()` 0x0053B0F8 | a weapon without the "cannot be forged", "valuable" or "cannot be removed" flags, whose sub-kind's forge group is not negative. |
| `item_can_forge_with` | `unit::Item::IsShopRefine(const unit::Item*)` 0x0053B070 | the item may be forged and the other one is the same item at the same forge rank (the smithy needs two equal weapons). |
| `item_sell_price` | `unit::Item::GetSellPrice` 0x0053AE8C | "cannot be sold" (-1) with the "valuable" or "cannot be removed" flag; a weapon's record price doubled once per forge rank; anything else's record price x uses left / full uses (whole-number division, unsigned), or the full price when no uses are left or the record says 0 uses. |

The game asks `Item::Get` and `Item::IsWeapon` again and again inside one function instead of
keeping the answer (up to seven calls for one might). The readable code makes the same calls in
the same order: the live compare checks the call list (F-018), and it costs nothing in results.

## 4. Item questions about a unit

| Function | Game name | What it decides |
|---|---|---|
| `unit_range_max` | `Unit::GetRangeO` 0x00534510 | the weapon's longest range (record byte +0x29); a staff reaches at least 10 when the unit has the skill labelled "endless staff". A record range of 0xFE means "half the unit's magic (rounded down), at least 1": no item of the game has it (checked in build/tables/Item.csv: range_max values 0 to 10 and 255 only). The game asks `Unit::GetPowImpl(unit, no item, with extras, with loss, rally kind 0)`, the rally kind as a fifth word on the stack; since round 11 the readable code passes it with `guest_call5` (docs/READABLE.md 17) instead of giving up, and the staff rule then applies to that range as to any other. |
| `unit_item_heal_amount` | `Unit::GetItemHealPower` 0x0052F288 | the HP an item heals (record byte +0x40), half again (rounded toward zero) for an item with the "standing medicine" flag when the unit has the skill labelled "potent medicine". |
| `unit_can_cannon_item` | `Unit::CanCannonItem` 0x0052DF90 | the unit may fire a ballista with this item: `Unit::CanItemEquip(item, false, true)` says yes, and, when the caller asks and condition byte 0 has bit 3, the item is not magic. |
| `unit_has_cannon_item` | `Unit::IsItemCanCannon` 0x0052F1AC | the same test passes for any of the unit's five slots. |

## 5. Guest calls and one-time caches

Guest calls left (`src/readable/item/item.h`): `ItemSubKind::Get` (the triangle batch's override),
`Unit::IsEquipSkill` (the skill batch's), `Unit::CanItemEquip` (3,352 bytes; since rewritten as `unit_can_equip_item`, docs/EQUIP_USE.md) and,
inside this batch, `Item::Get`, `unit::Item::ToData`, `ItemRefine::Get`, `Item::IsWeapon`,
`Item::IsMagic` and `unit::Item::IsShopRefine()` wherever the game calls them. `ToData` itself
falls through into `Item::Get` (no call), so its C calls the C directly.

Eight functions read one-time caches (an item flag bit or a skill number looked up by name the
first time): `IsMagic`, `IsHiddenEffect`, `CanUse`, `IsExpend`, `IsShopRefine()`, `GetSellPrice`,
`GetRangeO`, `GetItemHealPower` (the "guard user" tag in config/harness/targets.csv). The readable
code asks every cache it needs **before reading anything** and gives up while one is cold (only
before the game's first call). Two consequences, both safe:

- `IsMagic` and `IsHiddenEffect` ask their cache first, though the game asks it only after a quick
  test that may already answer; while cold, the original runs even where it would not have needed
  the cache.
- `unit_can_cannon_item`, `unit_has_cannon_item` and `item_can_forge_with` ask the caches of the
  overrides they call through the guest (`IsMagic`, `IsShopRefine()`) first, so a cold cache never
  makes the inner override give up inside the outer one (a nested give-up).

## 6. Checks

**Host differential test** `python src/readable/item/tests/item_diff.py` (the sheet test's C
driver and compare, arm_mini.py on extracted/text.bin): made-up states with values outside the
game's ranges on purpose: item numbers past every block, negative and 32-bit numbers, blocks of 0
or 1 records, overlapping blocks, an unmapped block, an empty block list, forge tables past the
mapped table, bools that are not 0/1, unmapped carried items and a "torn" item whose second
halfword is unmapped (so a read the game makes or skips shows as a count of unmapped reads). For
each override it compares r0, the unmapped reads and the list of guest calls with their argument
registers in order; a nested give-up is a mismatch. `Item::Get`, `ToData`, `ItemRefine::Get`,
`IsWeapon`, `IsMagic` and `IsShopRefine()` run as ARM code on one side and as the readable overrides
on the other, so the callers test them too.

Until round 11 one rule was added to the compare for the 0xFE range of section 4 (a give-up where
the original calls `Unit::GetPowImpl` was accepted as benign, "stack-call give-ups"). That rule is
gone: the readable code now makes the call with `guest_call5`, and both sides list it with its
fifth argument (the ARM side reads the word at sp when the BL is made; the C driver reads the word
at the callee's sp). The C driver counts a store into the 0x400 bytes below the case's sp (the
fifth word) apart from guest writes, so any other store is still a `WROTE-GUEST` failure.

Round 11 review: the dead stack below sp now holds random bytes, not zeros. With zeros a fifth word
stored in the wrong slot was read back as 0, the same as the real fifth word, and the review's planted
bug (word 4 bytes too high in `include/readable/fe_guest.h`) gave 0 mismatches; it is now in the
`--plant` list (fe.h and fe_guest.h are copied into the plant folder) and caught by 20 mismatches.
A guest_call5 that does not put sp back can not be seen here at all, because FE_ENTRY puts every
register back after the readable function; `tools/readable/tests/guest_call5_test.py --plant` tests
guest_call5 directly for that and five other bugs (docs/READABLE.md 17). The junk stack changed the
random cases, and the plant "IsMagic guard not asked by the slot loop" (caught by only 2 cases before)
was then NOT caught; `unit_has_cannon_item` now has 20 % focused cases with that guard cold and
check_magic on, and the plant is caught by 20 mismatches.

Also round 11: sheet_diff's compare counts a readable give-up with no unmapped read, where the
original did not give up, as an "early give-up" (always safe). That also hid a give-up in the
middle of a function after mapped reads and guest calls (the old 0xFE give-up: the planted bug that
puts it back was first NOT caught). item_diff now accepts early give-ups only for the five functions
that ask a cache before the game does (section 5: `IsMagic`, `IsHiddenEffect`, the two cannon
tests, `item_can_forge_with`); anywhere else such a give-up is a mismatch. And `unit_range_max`'s
cases are focused: 30 % have every record's range set to 0xFE (twice as often), 9 or 10, and the
magic answer includes 0, 1, odd and negative values, so the floor of 1 and the arithmetic halving
are tested. New planted bugs: wrong fifth word, wrong register argument, no floor, a logical
halving, the give-up put back.

Results 2026-11-14:

| Run | Cases | Mismatches | Planted bugs |
|---|---|---|---|
| default (`--plant`, seed 20261114, 300 per function) | 7,500 | 0 | 46/46 caught |
| second seed (`--seed 7`, 300 per function) | 7,500 | 0 | - |
| long (`-n 1500 --seed 11`) | 37,500 | 0 | - |
| round 11 default (`--plant`), guest_call5 + strict give-ups | 7,500 | 0 | 51/51 caught |
| round 11 second seed (`--seed 7`) | 7,500 | 0 | - |
| round 11 long (`-n 1500 --seed 11`) | 37,500 | 0 | - |
| round 11 review (`--plant`): junk dead stack, focused cannon cases, whole tree | 7,500 | 0 | 52/52 caught |
| round 11 review second seed (`--seed 7`), whole tree | 7,500 | 0 | - |

Round 11 runs were on a build/ copy of the tracked sources plus these edits (build/speed/r11-fixes/stage*,
scratch): other helpers' untracked folders in src/readable/ currently define the same override twice
(0x0052F008), which breaks the link step of a whole-tree build. The six new planted bugs were caught
by 8 (range 9), 22, 22, 9, 6 and 22 mismatches. Before the focused cases and the strict give-up rule,
two of them (the logical halving, the give-up put back) were NOT caught and the range-9 plant only
sometimes.

Early give-ups (the readable code gave up on a cold cache before any read, where the original would
not have needed it) were 0.3 % to 4 % of `IsMagic`, `IsHiddenEffect` and the two cannon tests' cases;
cold caches (both sides gave up at the cache) 3 % to 13 % of a guard user's cases, by design.

The first plant runs missed four bugs (a record address that wraps to 0, a re-read of the item
number, a staff range of exactly 9, a negative odd heal amount) and later one more (a signed price
division); the generator now makes those cases on purpose and all 46 are caught.

The test found two faults while it was written: `IsMagic` / `IsHiddenEffect` first asked their
cache after the sub-kind (as the game does), which read an unmapped sub-kind before giving up; they
now ask it first. And the 0xFE range above.

**Tier 2** (`tools/readable/verify.py`'s pipeline, only this batch's 25 addresses,
`build/readable/verify_item`, the other batches' sources whose rows were not yet registered left
out of the staged set, library build about 8 minutes): **0 MISMATCH**: 14 ABI-ONLY, 10 GAVE-UP,
1 NOT-RUN.

- ABI-ONLY (the five record lookups, `IsWeapon`, `IsDownload`, might / hit / crit, uses left, forge
  rank, same kind, equals, `ItemRefine::Get`): same r0; only scratch registers and flags differ,
  which AAPCS allows. Shadow surplus of unmapped reads is the classifier's known "readable code run
  after the original" shape.
- GAVE-UP (the eight guard users and the two cannon tests): verify's made-up memory has every
  one-time cache cold, so the readable code gave up and the original ran, as in every earlier batch.
  Proves nothing either way; the host test and the live compare cover them.
- NOT-RUN `item_sell_price` (0x0053AE8C): verify tested 0 functions in both passes (rerun with
  `--skip-build`: the same). **Why verify cannot sample it, and why that cannot be fixed here**
  (round 11, read in the code and the build, no new build):
  - verify does not test the build's functions: 3dsrecomp's `sample()` (engine/3dsrecomp/src/main.rs)
    takes the function list of its OWN fresh `discover::analyze` pass, with no seeds, filtered by
    `codegen::recompiles`; `VERIFY_ONLY` only filters that list. The build, which the overrides seed
    with every override address, has `0x0053AE8C` as its own function (lib/entries.c:
    `{0x0053AE8Cu, override_0x0053AE8C}` and f_0053AE8C) [high].
  - In the game's code `GetSellPrice` is reached two ways only [high, a scan of text.bin for branches
    and of rodata/data for pointers]: by falling through from `ItemSellMenuItem::GetPrice` 0x0053AE74
    (a virtual call, `pop`, then a `nop` where a branch would be) and by one BL at 0x005284E4 in
    `ItemSellMenuItem::IsPriceDisable` 0x005284D4; both of those are reached only through the
    ItemSellMenuItem vtable at 0x0063CC8C (no BL to either anywhere). An unseeded discovery that does
    not take 0x0053AE8C as a function start (code it walks into from 0x0053AE74 is that function's)
    has nothing to sample there [med: the discovery was not run alone to show it].
  - 3dsrecomp is built unmodified at its pin (tools/engine/engine.py), so its sampler cannot be
    changed from this repo, and verify.py has no other way to name a function. So: not fixable here;
    the verdict stays NOT-RUN, which is not a pass. The classifier says "no holder" because the
    entry table lists no label of 0x0053AE8C under another function: in the library the
    fall-through leaves f_0053AE74 through its dispatch (`target = 0x0053AE8Cu; goto dispatch`, then
    the host call), so in play the override IS entered from both callers.
  - Coverage instead: the host test (300 + 300 + 1,500 cases, and round 11's runs below) and the
    live compare when a route opens the shop's sell list (section 8). A classifier rule that names a
    fall-through holder (the previous function ends at this address without a branch) would turn this
    NOT-RUN into UNSAMPLED; that is a policy change for the classifier owner, not made here.

## 7. Not this batch, and why

- `Unit::GetRodHealPower` 0x0052F008 (a staff's healing: might + magic / 3 + a rank bonus, half
  again with a skill) and `GetInterferenceRodHit` / `Avoid`: they call `Unit::GetPowImpl` with its
  fifth argument on the stack on every call. Round 11's `guest_call5` lifts that limit, so they can
  be a later batch (another helper's untracked battle2 folder already has a 0x0052F008 override in
  progress, not looked at here).
- `Unit::CanItemEquip` 0x0052C634 (3,352 bytes) and `Unit::CanItemUse` 0x0052920C (3,092 bytes):
  too large for an idle-fill batch; worth a batch of their own. (Since then the equip_use batch
  rewrote CanItemEquip as `unit_can_equip_item`; CanItemUse is still skipped: docs/EQUIP_USE.md.)
- `unit::Item::GetSort` 0x0053B3B4 returns 64 bits (r0:r1); `Item::GetName` / `GetHelp` and
  `unit::Item::GetName` return text through `Mess::Get`.
- Weight: Fates item records have no weight field (ItemData in config/readable/structs); "brave"
  and "effective" are flag bits and a category word read inside the battle code, not getters of
  their own.

## 8. Where these will be met (live compare)

Expected on every route [med, not yet run]: `ToData`, `Item::Get`, might / hit / crit, `IsMagic`,
`IsWeapon` and the longest range in every fight and forecast; uses left, `IsExpend` and the heal
amount when a vulnerary is used; the sell price and the forge tests only in the shop and smithy
menus (My Castle), which the chapter routes may not visit; the cannon tests on maps with ballistae.
