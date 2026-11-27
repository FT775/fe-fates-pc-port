/* The class record for a class number (Fates Job::Get(unsigned short)).
   Plain-language description: docs/JOB_RECORD.md.

   A reader: it stores nothing and calls nothing. It walks the list of loaded
   class blocks and answers the address of the record (a JobData pointer). A
   number no block holds gets the first block's record 0, never 0.

   Not here: Unit::ClassChange and the seal stores (writers), Job::Get(const
   char*) (the lookup by ID label, a hash lookup at 0x00341A3C), and
   AIValue::GetJob. The callers (the class-change reader in
   src/readable/class_change/, the castle, the arena and the game's own) are
   unchanged.

   A HELPER, not an override (the UnitPool::Get lesson, docs/MOVE.md
   section 6): castle::CastleButler::GetJob (0x00341A50) ends with a no-op
   and runs on into 0x00341AA4 instead of calling it, and tier 2
   (tools/readable/verify.py) could not pick 0x00341AA4 on its own: NOT-RUN,
   0 functions tested in both passes, no holder in the entry table
   (docs/JOB_RECORD.md section 2). So there is no override marker here and
   the game keeps running its own Job::Get; readable code that needs a class
   record may call job_record_get directly (as unit_pool_force is used for
   UnitPool::GetForce, which Force::Get falls into the same way).

   Status: UNVERIFIED. Host differential test against the original ARM code:
   src/readable/job_record/tests/job_record_diff.py. */

#include "job_record.h"

/* The record of class number `number`, or the fallback.
   For each loaded block in list order: if first <= number < first + count
   (signed 32-bit compares on the whole register, as the game's), the answer
   is block + 8 + (number - first) * 0x80, unless that sum is 0 (it can only
   wrap to 0 on made-up memory), in which case the game falls back too. With
   no block holding the number, or with an empty list, the answer is the first
   node's block + 8 (an empty list reads its block from address 0).
   Guest function: helper of 0x00341AA4 Job::Get(unsigned short) (not
   overridden: castle::CastleButler::GetJob at 0x00341A50 falls through into
   it, and tier 2 cannot pick the address). */
uint32_t job_record_get(Context *ctx, uint32_t number) {
    int32_t n = (int32_t)number;
    gaddr head = guest_u32(ctx, S_JobBlockList);
    if (head != 0) {
        gaddr node = head;
        do {
            gaddr block = guest_u32(ctx, node + JR_NODE_BLOCK);
            int32_t first = guest_u16(ctx, block + JR_BLOCK_FIRST);
            if (n >= first) {
                int32_t end = first + guest_u16(ctx, block + JR_BLOCK_COUNT);
                if (end > n) {
                    /* the game reads the node's block again here */
                    block = guest_u32(ctx, node + JR_NODE_BLOCK);
                    uint32_t record = block + JR_BLOCK_RECORDS +
                                      (((uint32_t)n - (uint32_t)first) << JR_RECORD_SHIFT);
                    if (record != 0)
                        return record;
                    break;
                }
            }
            node = guest_u32(ctx, node + JR_NODE_NEXT);
        } while (node != 0);
    }
    return guest_u32(ctx, head + JR_NODE_BLOCK) + JR_BLOCK_RECORDS;
}
