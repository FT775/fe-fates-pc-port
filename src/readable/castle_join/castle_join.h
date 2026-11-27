/* Who a visited castle can add (Fates class castle::JoinSequence): the
   declarations of src/readable/castle_join/castle_join.c, the guest functions
   it still calls, the one-time cache it asks, and the fields of the castle
   join file it reads.

   Plain-language description (what the helper decides, and what was left out
   and why): docs/CASTLE_JOIN.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_CASTLE_JOIN_CASTLE_JOIN_H
#define FE_CASTLE_JOIN_CASTLE_JOIN_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-16 (objdump of
   extracted/text.bin, read only), with what it calls: it stores nothing
   outside its own stack frame. The helper makes the same guest calls in the
   game's order with the game's arguments (docs/DECISIONS.md F-018). */
#define CJ_UnitPoolGetFromPerson 0x004F5E74u /* UnitPool::GetFromPerson(const char*, unsigned): Person::Get, then
                                                the first unique unit (Unit::IsUnique, readable unit_is_unique)
                                                of that Person in one of the forces of the mask; or 0 */
#define CJ_CutIsCleared 0x00469D34u          /* castle::cut::IsCleared(const char*): 0 for 0; else Chapter::Get,
                                                Spot::GetData, 1 when that spot's state byte is 2 */
#define CJ_CastleGet 0x0044544Cu             /* Castle::Get(void): the word at 0x006D1998 */
#define CJ_CastleGetData 0x0044545Cu         /* Castle::GetData(void): one of three records, by the castle kind */
#define CJ_BuildingDisposIsBuilt 0x00455610u /* castle::BuildingDispos::IsBuilt(castle::EventType, int,
                                                const char*): walks the placed buildings; reads only */
#define CJ_PersonGet 0x0044A6DCu             /* Person::Get(const char*): IdentHash::GetSurely; reads only */

/* ---- the one-time cache asked first. UnitPool::GetFromPerson reaches
   Unit::IsUnique and, for a unit with state bit 28, Person::IsDownload, whose
   readable override (src/readable/map/vein_units.c) gives up while its cache
   is cold. A give-up inside a guest call (nested) counts as a mismatch, so the
   helper asks that guard before anything else. */
#define S_CjDownloadGuard 0x006D3B3Cu /* src/readable/map/veins.h S_DownloadGuard */

/* ---- the castle join file (castle/castle_join.bin.lz) as the game reads it
   once it is loaded; offsets read in GetJoinPersonList's code on 2026-11-16.
   config/readable/structs/ does not name them. No table values are copied. */
#define CJ_FILE_BODY 0x70u          /* word in the loaded file: its body, 0 for none */
#define CJ_BODY_TABLE 0x20u         /* the join table: a signed count, then the records */
#define CJ_TABLE_RECORDS 4u         /* first record, after the count */
#define CJ_RECORD_SIZE 32u
#define CJ_REC_PERSON 4u            /* const char*: the Person's ID label */
#define CJ_REC_CHAPTER 8u           /* three const char*: chapter labels, 0 = unused */
#define CJ_REC_BUILDING 20u         /* three words: building event types, -1 = unused */
#define CJ_CONDITIONS 3             /* entries in each of the two lists */
#define CJ_NO_BUILDING (-1)

#define CJ_JOIN_FORCES 0x59u        /* the force mask GetJoinPersonList passes: forces 0, 3, 4 and 6 [low for
                                       which forces those are] */
#define CJ_BUILDING_RANK 3          /* IsBuilt's second argument, as the game passes it [low for its meaning:
                                       IsBuilt compares it with a byte of the building's record] */
#define CJ_DATA_DISPOS 4u           /* Castle::GetData record: its castle::BuildingDispos */
#define CJ_LIST_MAX 6               /* castle::JoinPersonList_t holds six Persons (its count sits after them) */

/* What GetJoinPersonList would store into its list, in host memory. */
typedef struct CastleJoinOffer {
    int32_t count;               /* 0 .. CJ_LIST_MAX */
    gaddr person[CJ_LIST_MAX];   /* the Person records, in table order */
} CastleJoinOffer;

/* ---- the readable functions */
/* helper (F-017): castle::JoinSequence::GetJoinPersonList without its loads and
   stores; returns 1 when at least one Person qualified (also past the sixth) */
int32_t castle_join_offer(Context *ctx, gaddr file, CastleJoinOffer *out);

#endif /* FE_CASTLE_JOIN_CASTLE_JOIN_H */
