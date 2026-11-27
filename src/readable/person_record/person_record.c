/* The person record for a person name (Fates Person::Get(const char*)), and
   the person record for a person number (Person::Get(unsigned short)).
   Plain-language description: docs/PERSON_RECORD.md.

   Readers: they store nothing and call no guest function, and never give up.

   Person::Get(const char*) is four words: it takes the ID label hash table
   from G_IdentHash and branches into IdentHash::GetSurely(const char*) const
   (0x00549484), the same lookup as EquipSkill::Get(const char*)
   (src/readable/skill_record/, docs/SKILL_RECORD.md section 1). That folder
   keeps its GetSurely step `static` and is not edited by this batch, so the
   step is written again here, the same way, as a static step of
   person_record_by_name. IdentHash::GetSurely itself is not overridden
   (UniqueArchiveObject::GetSurely runs on into it). It is an OVERRIDE: the
   word before 0x0044A6DC is a literal pool, so nothing runs on into it.

   Person::Get(unsigned short) walks the list of loaded person blocks, the
   shape of Job::Get(unsigned short) (docs/JOB_RECORD.md). It is a HELPER,
   not an override: AIValue::GetPerson (0x0044A6F0: a halfword load and a
   no-op) runs on into 0x0044A6F8, the shape tier 2 could not pick for
   UnitPool::Get and Job::Get (docs/PERSON_RECORD.md section 2). So the game
   keeps running its own Person::Get(unsigned short); readable code that
   needs a person record by number may call person_record_get directly.

   Not here: a join that stores the unit into the army (castle joins and
   Unit::Create), the loading of the person blocks and of the label table,
   and AIValue::GetPerson. The callers (the castle-join reader in
   src/readable/castle_join/, the growth, stance and support readers and the
   game's own call sites) are unchanged.

   Status: UNVERIFIED. Host differential test against the original ARM code:
   src/readable/person_record/tests/person_record_diff.py. */

#include "person_record.h"

/* IdentHash::GetSurely(const char*) const on the table at `hash`: the value
   of the entry of label `name`, or 0. The game reads the first byte once
   before the loop and then, for each byte, the byte as signed and the next
   byte for the end test; the readable code makes the same reads. With 0
   buckets the remainder is the dividend (the runtime's division-by-zero
   path, 0x002FFC28, returns it). */
static gaddr ident_hash_get_surely(Context *ctx, gaddr hash, gaddr name) {
    if (name == 0)
        return 0;
    uint8_t first = guest_u8(ctx, name);
    uint32_t count = guest_u32(ctx, hash + PR_HASH_COUNT);
    uint32_t bucket_hash = 0, key = 0;
    if (first != 0) {
        gaddr p = name;
        uint8_t next;
        do {
            uint32_t c = (uint32_t)(int32_t)guest_s8(ctx, p);
            next = guest_u8(ctx, p + 1);
            p++;
            key = key * PR_KEY_MUL + c;
            bucket_hash = bucket_hash * PR_BUCKET_MUL + c;
        } while (next != 0);
    }
    uint32_t bucket = count != 0 ? bucket_hash % count : bucket_hash;
    gaddr entry = guest_u32(ctx, guest_u32(ctx, hash + PR_HASH_BUCKETS) + (bucket << 2));
    while (entry != 0) {
        if (guest_u32(ctx, entry + PR_ENTRY_KEY) == key)
            return guest_u32(ctx, entry + PR_ENTRY_VALUE);
        entry = guest_u32(ctx, entry + PR_ENTRY_NEXT);
    }
    return 0;
}

/* The Person record of an ID label ("PID_..."), or 0 when no entry matches.
   Guest function: 0x0044A6DC Person::Get(const char*). */
gaddr person_record_by_name(Context *ctx, gaddr name) {
    return ident_hash_get_surely(ctx, guest_u32(ctx, G_IdentHash), name);
}

/* The record of person number `number`, or the fallback.
   For each loaded block in list order: if first <= number < first + count
   (signed 32-bit compares on the whole register, as the game's), the answer
   is block + 0x10 + (number - first) * 0x98, unless that sum is 0 (only on
   made-up memory), in which case the game falls back too. With no block
   holding the number, or with an empty list, the answer is the first node's
   block + 0x10 (an empty list reads its block from address 0).
   Guest function: helper of 0x0044A6F8 Person::Get(unsigned short) (not
   overridden: AIValue::GetPerson at 0x0044A6F0 falls through into it). */
uint32_t person_record_get(Context *ctx, uint32_t number) {
    int32_t n = (int32_t)number;
    gaddr head = guest_u32(ctx, G_PersonBlocks);
    if (head != 0) {
        gaddr node = head;
        do {
            gaddr block = guest_u32(ctx, node + PR_NODE_BLOCK);
            int32_t first = guest_u16(ctx, block + PR_BLOCK_FIRST);
            if (n >= first) {
                int32_t end = first + guest_u16(ctx, block + PR_BLOCK_COUNT);
                if (end > n) {
                    /* the game reads the node's block again here */
                    block = guest_u32(ctx, node + PR_NODE_BLOCK);
                    uint32_t record = block + PR_BLOCK_RECORDS +
                                      ((uint32_t)n - (uint32_t)first) * PR_RECORD_SIZE;
                    if (record != 0)
                        return record;
                    break;
                }
            }
            node = guest_u32(ctx, node + PR_NODE_NEXT);
        } while (node != 0);
    }
    return guest_u32(ctx, head + PR_NODE_BLOCK) + PR_BLOCK_RECORDS;
}

RECOMP_OVERRIDE(0x0044A6DC) {
    FE_ENTRY(0x0044A6DC, person_record_by_name, FE_ARG(0));
}
