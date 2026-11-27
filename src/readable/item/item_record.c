/* Item records (Fates class Item and its tables): finding an item's record by
   its number, the record of a unit::Item, the item-kind and forge tables, and
   the questions asked of a record: is it a weapon, a magic weapon, usable, a
   download item, a "concealed" weapon.
   Plain-language description: docs/ITEM.md sections 1 and 2.

   All are readers: they store nothing. Three fill a one-time cache (an
   ItemSkill flag bit found by name); the readable code gives up while it is
   cold, and asks it first: the game asks it only after a quick test (the
   sub-kind) that may already answer, but a give-up must come before any read
   (docs/READABLE.md rule 5), so while the cache is cold (before the game's
   first call) the original runs even where it would not have needed it. Guest calls left: ItemSubKind::Get (the triangle batch's override),
   in the game's order (docs/DECISIONS.md F-018).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/item/tests/item_diff.py. */

#include "item.h"

/* Where a block's records hold this number: the record's address, or 0 when
   no block of the list has it. `zero_is_missing`: Item::Get treats a record
   address that wraps to 0 as not found (TryGet does not look). */
static gaddr find_record(Context *ctx, gaddr head, uint32_t number, int zero_is_missing, int *found) {
    *found = 0;
    for (gaddr node = head; node != 0; node = guest_u32(ctx, node + ITEM_NODE_NEXT)) {
        gaddr block = guest_u32(ctx, node + ITEM_NODE_BLOCK);
        int32_t first = guest_u16(ctx, block + ITEM_BLOCK_FIRST_NUMBER);
        if ((int32_t)number < first)
            continue;
        int32_t end = first + guest_u16(ctx, block + ITEM_BLOCK_COUNT);
        if (end <= (int32_t)number)
            continue;
        /* the game reads the node's block pointer a second time here */
        gaddr record = guest_u32(ctx, node + ITEM_NODE_BLOCK) + ITEM_BLOCK_RECORDS +
                       (number - (uint32_t)first) * ITEM_RECORD_SIZE;
        if (zero_is_missing && record == 0)
            return 0;
        *found = 1;
        return record;
    }
    return 0;
}

/* The Item record of an item number: the record in the first loaded block
   whose numbers [first, first + count) hold it (compared as signed 32-bit
   numbers, as the game does); else the first record of the first block (the
   "no item" record).
   Guest function: 0x003D0EAC Item::Get(unsigned short). */
gaddr item_record(Context *ctx, uint32_t number) {
    gaddr head = guest_u32(ctx, G_ItemArchiveList);
    int found;
    gaddr record = find_record(ctx, head, number, 1, &found);
    if (found)
        return record;
    return guest_u32(ctx, head + ITEM_NODE_BLOCK) + ITEM_BLOCK_RECORDS;
}

/* The Item record of a unit::Item: Item::Get of its item number (the game's
   code falls through into Item::Get: no call).
   Guest function: 0x003D0EA4 unit::Item::ToData(void) const. */
gaddr item_to_data(Context *ctx, gaddr item) {
    return item_record(ctx, guest_u16(ctx, item));
}

/* As item_record, but 0 when no block holds the number.
   Guest function: 0x003D10A0 Item::TryGet(unsigned short). */
gaddr item_try_record(Context *ctx, uint32_t number) {
    int found;
    return find_record(ctx, guest_u32(ctx, G_ItemArchiveList), number, 0, &found);
}

/* The ItemKind record of a weapon kind (no range check).
   Guest function: 0x004EC1CC ItemKind::Get(int). */
gaddr item_kind_record(Context *ctx, uint32_t kind) {
    return guest_u32(ctx, G_ItemKindTable) + kind * ITEM_KIND_RECORD_SIZE;
}

/* The forge bonus record of a forge table and a rank (ten ranks per table,
   no range check): +1 might, +2 hit, +3 crit.
   Guest function: 0x0017CFA8 ItemRefine::Get(int,int). */
gaddr item_refine_record(Context *ctx, uint32_t table, uint32_t rank) {
    return guest_u32(ctx, G_ItemRefineTable) + (table * ITEM_REFINE_ROW + rank) * ITEM_REFINE_RECORD_SIZE;
}

/* The weapon kind of a record (ItemSubKind::Get of its signed sub-kind byte,
   then the sub-kind's kind, read signed or unsigned as each caller does). */
static gaddr subkind_of(Context *ctx, gaddr record) {
    return guest_call1(ctx, ITEM_ItemSubKindGet, (uint32_t)(int32_t)READ_FIELD(ctx, ItemData, record, weapon_kind));
}

/* 1 for anything but a staff (kind 6) or an item of kind 8.
   Guest function: 0x00529164 Item::IsWeapon(void) const. */
uint32_t item_is_weapon(Context *ctx, gaddr record) {
    int32_t kind = guest_s8(ctx, FIELD_ADDR(ItemSubKindData, subkind_of(ctx, record), kind));
    return (kind == 6 || kind == 8) ? 0u : 1u;
}

/* 1 for a tome (kind 5) or a staff (kind 6), else 1 when the record has the
   "magic weapon" flag bit (a magic sword hits with magic).
   Guest function: 0x005290B8 Item::IsMagic(void) const. */
uint32_t item_is_magic(Context *ctx, gaddr record) {
    if (!fe_static_ready(ctx, S_ItemMagicGuard))
        return fe_use_original(ctx);
    int32_t kind = guest_s8(ctx, FIELD_ADDR(ItemSubKindData, subkind_of(ctx, record), kind));
    if (kind == 5 || kind == 6)
        return 1;
    return (READ_FIELD(ctx, ItemData, record, flags) & guest_u64(ctx, S_ItemMagicMask)) != 0 ? 1u : 0u;
}

/* 1 when the record has the "usable" flag bit (the Use command offers it).
   Guest function: 0x00528F3C Item::CanUse(void) const. */
uint32_t item_can_use(Context *ctx, gaddr record) {
    if (!fe_static_ready(ctx, S_ItemUsableGuard))
        return fe_use_original(ctx);
    return (READ_FIELD(ctx, ItemData, record, flags) & guest_u64(ctx, S_ItemUsableMask)) != 0 ? 1u : 0u;
}

/* 1 for a download (DLC) item: its item number is not below the count of the
   first loaded block (the game's own items).
   Guest function: 0x00528E68 Item::IsDownload(void) const. */
uint32_t item_is_download(Context *ctx, gaddr record) {
    uint32_t number = READ_FIELD(ctx, ItemData, record, item_number);
    gaddr block = guest_u32(ctx, guest_u32(ctx, G_ItemArchiveList) + ITEM_NODE_BLOCK);
    return number >= guest_u16(ctx, block + ITEM_BLOCK_COUNT) ? 1u : 0u;
}

/* 1 for a "concealed" weapon (the after-battle stat hit of daggers and
   shuriken): its sub-kind's kind is 3, or its sub-kind byte is 19, or it has
   the "concealed weapon" flag bit.
   Guest function: 0x00528E90 Item::IsHiddenEffect(void) const. */
uint32_t item_is_hidden_effect(Context *ctx, gaddr record) {
    if (!fe_static_ready(ctx, S_ItemHiddenGuard))
        return fe_use_original(ctx);
    if (guest_u8(ctx, FIELD_ADDR(ItemSubKindData, subkind_of(ctx, record), kind)) == 3)
        return 1;
    if (guest_u8(ctx, FIELD_ADDR(ItemData, record, weapon_kind)) == 19)
        return 1;
    return (READ_FIELD(ctx, ItemData, record, flags) & guest_u64(ctx, S_ItemHiddenMask)) != 0 ? 1u : 0u;
}

RECOMP_OVERRIDE(0x003D0EAC) {
    FE_ENTRY(0x003D0EAC, item_record, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003D0EA4) {
    FE_ENTRY(0x003D0EA4, item_to_data, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003D10A0) {
    FE_ENTRY(0x003D10A0, item_try_record, FE_ARG(0));
}

RECOMP_OVERRIDE(0x004EC1CC) {
    FE_ENTRY(0x004EC1CC, item_kind_record, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0017CFA8) {
    FE_ENTRY(0x0017CFA8, item_refine_record, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00529164) {
    FE_ENTRY(0x00529164, item_is_weapon, FE_ARG(0));
}

RECOMP_OVERRIDE(0x005290B8) {
    FE_ENTRY(0x005290B8, item_is_magic, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00528F3C) {
    FE_ENTRY(0x00528F3C, item_can_use, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00528E68) {
    FE_ENTRY(0x00528E68, item_is_download, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00528E90) {
    FE_ENTRY(0x00528E90, item_is_hidden_effect, FE_ARG(0));
}
