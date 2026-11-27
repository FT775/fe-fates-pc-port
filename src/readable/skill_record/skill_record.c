/* The skill record for a skill name (Fates EquipSkill::Get(const char*)).
   Plain-language description: docs/SKILL_RECORD.md.

   A reader: it stores nothing and calls no guest function. The game's
   function is four words: it takes the ID label hash table from G_IdentHash
   and branches into IdentHash::GetSurely(const char*) const (0x00549484),
   which hashes the label twice, picks a bucket with the runtime's unsigned
   division (0x0012A0E4, the remainder) and walks the bucket's chain for an
   entry with the same second hash. The readable code does all of that in C.
   A label no entry matches, or a null label, gives 0. It never gives up.

   A table with 0 buckets: the runtime's division then takes its
   division-by-zero path (0x002FFC28), which calls this build's __rt_div0
   (0x0013F8B4: a no-op and a return) and hands back the dividend itself as
   the remainder, so the bucket is the bucket hash unchanged. The readable
   code answers the same way (docs/SKILL_RECORD.md section 1).

   Not here: learning a skill, Unit::AddEquipSkill, the skill picture, and
   EquipSkill::Get(short) (the record by number, skill_record in
   src/readable/skill/, not edited). IdentHash::GetSurely is not overridden:
   UniqueArchiveObject::GetSurely (0x0054947C) ends with a no-op and runs on
   into it (the UnitPool::Get lesson, docs/SKILL_RECORD.md section 2); its
   body is rewritten here as a static step of this function only. The
   callers (the stat seal reader in src/readable/class_change/, the skills
   batch's guest calls in src/readable/skill/, and the game's own 514 call
   sites) are unchanged.

   Status: UNVERIFIED. Host differential test against the original ARM code:
   src/readable/skill_record/tests/skill_record_diff.py. */

#include "skill_record.h"

/* IdentHash::GetSurely(const char*) const on the table at `hash`: the value
   of the entry of label `name`, or 0. The game reads the first byte once
   before the loop and then, for each byte, the byte as signed and the next
   byte for the end test; the readable code makes the same reads. With 0
   buckets the remainder is the dividend (the runtime's division-by-zero
   path returns it). */
static gaddr ident_hash_get_surely(Context *ctx, gaddr hash, gaddr name) {
    if (name == 0)
        return 0;
    uint8_t first = guest_u8(ctx, name);
    uint32_t count = guest_u32(ctx, hash + SR_HASH_COUNT);
    uint32_t bucket_hash = 0, key = 0;
    if (first != 0) {
        gaddr p = name;
        uint8_t next;
        do {
            uint32_t c = (uint32_t)(int32_t)guest_s8(ctx, p);
            next = guest_u8(ctx, p + 1);
            p++;
            key = key * SR_KEY_MUL + c;
            bucket_hash = bucket_hash * SR_BUCKET_MUL + c;
        } while (next != 0);
    }
    uint32_t bucket = count != 0 ? bucket_hash % count : bucket_hash;
    gaddr entry = guest_u32(ctx, guest_u32(ctx, hash + SR_HASH_BUCKETS) + (bucket << 2));
    while (entry != 0) {
        if (guest_u32(ctx, entry + SR_ENTRY_KEY) == key)
            return guest_u32(ctx, entry + SR_ENTRY_VALUE);
        entry = guest_u32(ctx, entry + SR_ENTRY_NEXT);
    }
    return 0;
}

/* The Skill record of an ID label ("SEID_..."), or 0 when no entry matches.
   Guest function: 0x001758C4 EquipSkill::Get(const char*). */
gaddr skill_record_by_name(Context *ctx, gaddr name) {
    return ident_hash_get_surely(ctx, guest_u32(ctx, G_IdentHash), name);
}

RECOMP_OVERRIDE(0x001758C4) {
    FE_ENTRY(0x001758C4, skill_record_by_name, FE_ARG(0));
}
