/* Is this unit, or this person, female (Fates Unit::IsFemale and
   Person::IsFemale): the declarations of src/readable/female/female.c and the
   one-time caches it reads.

   Plain-language description (what the two functions decide): docs/FEMALE.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_FEMALE_FEMALE_H
#define FE_FEMALE_FEMALE_H

#include "fe.h"

/* ---- the two one-time caches (read in the code on 2026-11-17). Each holds
   1 << (the index of the PersonFlag ID "female", SPID_ in the game), found by
   name the first time its function runs (PrivateSkill::Get, then a 64-bit
   shift); the game then stores the u64 and never again. The two functions
   keep a cache each. The readable code reads a cache only after the game
   filled it (bit 0 of the guard word) and gives up before anything else while
   it is cold. No call is left in either body once its cache is filled. */
#define S_FemUnitGuard 0x006D97ECu     /* Unit::IsFemale (literal 0x006D9A28 - 0x23C) */
#define S_FemUnitMask 0x006D9AF0u      /* u64, behind S_FemUnitGuard (literal 0x006D9A28 + 0xC8) */
#define S_FemPersonGuard 0x006D3B2Cu   /* Person::IsFemale (literal 0x006D3B28 + 4) */
#define S_FemPersonMask 0x006D3B70u    /* u64, behind S_FemPersonGuard (literal 0x006D3B28 + 0x48) */

/* ---- the readable functions (override entries at the end of the file) */
int32_t female_unit_is_female(Context *ctx, gaddr unit);
int32_t female_person_is_female(Context *ctx, gaddr person);

#endif /* FE_FEMALE_FEMALE_H */
