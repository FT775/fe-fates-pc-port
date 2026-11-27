/* The person record for a person name (Fates Person::Get(const char*)) and
   for a person number (Person::Get(unsigned short)): the declarations of
   src/readable/person_record/person_record.c and the guest addresses and
   offsets they read.

   Plain-language description (what the functions answer): docs/PERSON_RECORD.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_PERSON_RECORD_PERSON_RECORD_H
#define FE_PERSON_RECORD_PERSON_RECORD_H

#include "fe.h"

/* ---- the ID label hash table (read in the code on 2026-11-17).
   Person::Get(const char*) reads the table's address from the word at
   G_IdentHash (0x006DCB44, include/readable/generated/fe_globals.h; its
   literal at 0x0044A6EC) and branches into IdentHash::GetSurely(const char*)
   const (0x00549484), the same lookup as EquipSkill::Get(const char*)
   (docs/SKILL_RECORD.md section 1). Only these offsets are read. */
#define PR_HASH_COUNT 0x04u   /* u32: how many buckets (the divisor of the bucket hash) */
#define PR_HASH_BUCKETS 0x10u /* u32: the bucket array, one word (the first entry, or 0) per bucket */

/* An entry of a bucket's chain. */
#define PR_ENTRY_NEXT 0x0u  /* the next entry of the chain, or 0 */
#define PR_ENTRY_KEY 0x4u   /* u32: the label's second hash (compared; the label itself is not) */
#define PR_ENTRY_VALUE 0xCu /* the answer: the record the label names */

/* The two hashes of a label (signed bytes, 32-bit wrap): the bucket hash
   h = h * 37 + c, the key hash k = k * 31 + c. */
#define PR_BUCKET_MUL 37u
#define PR_KEY_MUL 31u

/* ---- the list of loaded person blocks (read in Person::Get(unsigned short)
   on 2026-11-17). The word G_PersonBlocks (0x006D3B28, fe_globals.h; its
   literal at 0x0044A764) holds the first list node, or 0. */
#define PR_NODE_BLOCK 0x0u /* the block's header */
#define PR_NODE_NEXT 0x8u  /* the next node, or 0 at the end */

/* A block header (only these offsets are read). */
#define PR_BLOCK_COUNT 0x04u   /* u16: how many person records the block holds */
#define PR_BLOCK_RECORDS 0x10u /* the first record */
#define PR_BLOCK_FIRST 0x34u   /* u16: the first record's person number (record 0 + 0x24) */
#define PR_RECORD_SIZE 0x98u   /* the game computes (i * 3 + i * 16) * 8, that is i * 0x98 */

/* ---- the readable functions */
/* an override (0x0044A6DC) */
gaddr person_record_by_name(Context *ctx, gaddr name);
/* a helper, not an override (0x0044A6F8: AIValue::GetPerson runs on into it,
   docs/PERSON_RECORD.md section 2) */
uint32_t person_record_get(Context *ctx, uint32_t number);

#endif /* FE_PERSON_RECORD_PERSON_RECORD_H */
