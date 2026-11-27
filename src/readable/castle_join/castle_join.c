/* Who a visited castle can add (Fates class castle::JoinSequence): the Persons
   the castle join file offers once their conditions are met. Plain-language
   description: docs/CASTLE_JOIN.md.

   - castle_join_offer is a helper (F-017), not a reader with an override:
     castle::JoinSequence::GetJoinPersonList loads castle/castle_join.bin.lz
     into the heap (ArchiveFile), stores the count and the Persons into the
     caller's castle::JoinPersonList_t and frees the file. Those are stores and
     a file load, so the function gets no override. The helper starts from the
     loaded file (the pointer the game's ArchiveFile holds), makes the same
     read-only guest calls in the game's order, and gives the list back in
     host memory. It loads, frees and stores nothing.
   - castle::JoinSequence::Create is the join scene (a new ProcInst, the
     message file, a scene object): not here.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/castle_join/tests/castle_join_diff.py. */

#include "castle_join.h"

/* The record's chapter condition: none (all three labels 0), or at least one
   of the three chapters cleared (castle::cut::IsCleared is asked for each in
   turn, 0 labels included, until one says yes). */
static int join_chapter_met(Context *ctx, gaddr record) {
    gaddr chapter = record + CJ_REC_CHAPTER;
    if (guest_u32(ctx, chapter) == 0 && guest_u32(ctx, chapter + 4u) == 0 && guest_u32(ctx, chapter + 8u) == 0)
        return 1;
    for (int32_t i = 0; i < CJ_CONDITIONS; i++)
        if (guest_call1(ctx, CJ_CutIsCleared, guest_u32(ctx, chapter + 4u * (gaddr)i)) != 0)
            return 1;
    return 0;
}

/* The record's building condition: none (all three words -1), or at least one
   of the three building types built (BuildingDispos::IsBuilt with the type's
   low byte, sign-extended, and the rank 3; -1 words are asked too). The game
   asks Castle::Get and Castle::GetData again for each type. */
static int join_building_met(Context *ctx, gaddr record) {
    gaddr building = record + CJ_REC_BUILDING;
    if (guest_s32(ctx, building) == CJ_NO_BUILDING && guest_s32(ctx, building + 4u) == CJ_NO_BUILDING &&
        guest_s32(ctx, building + 8u) == CJ_NO_BUILDING)
        return 1;
    for (int32_t i = 0; i < CJ_CONDITIONS; i++) {
        gaddr castle = guest_call(ctx, CJ_CastleGet, 0u, 0u, 0u, 0u);
        gaddr data = guest_call1(ctx, CJ_CastleGetData, castle);
        gaddr dispos = guest_ptr(ctx, data + CJ_DATA_DISPOS);
        uint32_t type = (uint32_t)(int32_t)(int8_t)(uint8_t)guest_u32(ctx, building + 4u * (gaddr)i);
        if (guest_call(ctx, CJ_BuildingDisposIsBuilt, dispos, type, (uint32_t)CJ_BUILDING_RANK, 0u) != 0)
            return 1;
    }
    return 0;
}

/* Who the castle offers to join, from the loaded castle join file (`file`:
   the buffer the game's ArchiveFile holds; its body word 0 or a file of 0
   give the table at address 0, read as the game reads it). For each record in
   order: skipped when a unique unit of that Person already stands in one of
   the forces 0x59 (UnitPool::GetFromPerson); otherwise taken when its chapter
   condition and then its building condition are met. A taken Person
   (Person::Get of the record's label) is listed while fewer than six are; the
   return value is 1 when any record was taken (also past the sixth), else 0.
   The table's count is signed and read again after every record, as in the
   game. Gives up (count 0) while Person::IsDownload's cache is cold.
   Guest function: helper of 0x00451DF4
   castle::JoinSequence::GetJoinPersonList(castle::JoinPersonList_t*) (it loads
   the file, stores into the list and frees the file: none of that here). */
int32_t castle_join_offer(Context *ctx, gaddr file, CastleJoinOffer *out) {
    out->count = 0;
    if (!fe_static_ready(ctx, S_CjDownloadGuard))
        return (int32_t)fe_use_original(ctx);
    gaddr table = 0;
    if (file != 0) {
        gaddr body = guest_ptr(ctx, file + CJ_FILE_BODY);
        if (body != 0)
            table = body + CJ_BODY_TABLE;
    }
    int32_t found = 0;
    for (int32_t i = 0; i < guest_s32(ctx, table); i++) {
        gaddr record = table + CJ_TABLE_RECORDS + (gaddr)i * CJ_RECORD_SIZE;
        if (guest_call2(ctx, CJ_UnitPoolGetFromPerson, guest_u32(ctx, record + CJ_REC_PERSON), CJ_JOIN_FORCES) != 0)
            continue; /* already in the army */
        if (!join_chapter_met(ctx, record) || !join_building_met(ctx, record))
            continue;
        gaddr person = guest_call1(ctx, CJ_PersonGet, guest_u32(ctx, record + CJ_REC_PERSON));
        if (out->count != CJ_LIST_MAX)
            out->person[out->count++] = person;
        found = 1;
    }
    return found;
}
