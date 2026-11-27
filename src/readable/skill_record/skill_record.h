/* The skill record for a skill name (Fates EquipSkill::Get(const char*)):
   the declaration of src/readable/skill_record/skill_record.c and the guest
   addresses and offsets it reads.

   Plain-language description (what the function answers): docs/SKILL_RECORD.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declaration into include/readable/fe_functions.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_SKILL_RECORD_SKILL_RECORD_H
#define FE_SKILL_RECORD_SKILL_RECORD_H

#include "fe.h"

/* ---- the ID label hash table (read in the code on 2026-11-17).
   EquipSkill::Get(const char*) reads the table's address from the word at
   G_IdentHash (0x006DCB44, include/readable/generated/fe_globals.h; its
   literal at 0x001758D4) and branches into IdentHash::GetSurely(const char*)
   const (0x00549484). Only these offsets are read. */
#define SR_HASH_COUNT 0x04u   /* u32: how many buckets (the divisor of the bucket hash) */
#define SR_HASH_BUCKETS 0x10u /* u32: the bucket array, one word (the first entry, or 0) per bucket */

/* An entry of a bucket's chain. */
#define SR_ENTRY_NEXT 0x0u  /* the next entry of the chain, or 0 */
#define SR_ENTRY_KEY 0x4u   /* u32: the label's second hash (compared; the label itself is not) */
#define SR_ENTRY_VALUE 0xCu /* the answer: the record the label names */

/* The two hashes of a label (signed bytes, 32-bit wrap): the bucket hash
   h = h * 37 + c, the key hash k = k * 31 + c. */
#define SR_BUCKET_MUL 37u
#define SR_KEY_MUL 31u

/* ---- the readable function (an override) */
gaddr skill_record_by_name(Context *ctx, gaddr name);

#endif /* FE_SKILL_RECORD_SKILL_RECORD_H */
