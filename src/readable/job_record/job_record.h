/* The class record for a class number (Fates Job::Get(unsigned short)): the
   declaration of src/readable/job_record/job_record.c and the guest addresses
   it reads.

   Plain-language description (what the function answers): docs/JOB_RECORD.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declaration into include/readable/fe_functions.h.

   Never write the override marker in this header (staging pastes it into each
   file); this batch has none (a helper). */

#ifndef FE_JOB_RECORD_JOB_RECORD_H
#define FE_JOB_RECORD_JOB_RECORD_H

#include "fe.h"

/* ---- the list of loaded class blocks (read in the code on 2026-11-17).
   The game keeps one list node per loaded block of class records (the main
   game data, and any added block). Job::Load and Job::Free change the list;
   Job::Get only walks it. */
#define S_JobBlockList 0x006D39A0u /* the first list node, or 0 (literal 0x006D3990 + 0x10) */

/* A list node (offsets read in Job::Get; nothing else of the node is read). */
#define JR_NODE_BLOCK 0x0u /* the block's header */
#define JR_NODE_NEXT 0x8u  /* the next node, or 0 at the end */

/* A block header (docs/TABLES.md, Classes: records start at header + 0x8,
   0x80 bytes each). */
#define JR_BLOCK_COUNT 0x06u   /* u16: how many class records the block holds */
#define JR_BLOCK_RECORDS 0x08u /* the first record */
#define JR_BLOCK_FIRST 0x20u   /* u16: the first record's class number (record 0 + 0x18, job_number) */
#define JR_RECORD_SHIFT 7      /* record size 0x80 */

/* ---- the readable function (a helper: no override entry, docs/JOB_RECORD.md section 2) */
uint32_t job_record_get(Context *ctx, uint32_t number);

#endif /* FE_JOB_RECORD_JOB_RECORD_H */
