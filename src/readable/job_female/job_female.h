/* Is this class the female one (Fates Job::IsFemale): the declaration of
   src/readable/job_female/job_female.c and the one-time cache it reads.

   Plain-language description (what the function decides): docs/JOB_FEMALE.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declaration into include/readable/fe_functions.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_JOB_FEMALE_JOB_FEMALE_H
#define FE_JOB_FEMALE_JOB_FEMALE_H

#include "fe.h"

/* ---- the one-time cache (read in the code on 2026-11-17). It holds
   1 << (the index of the PersonFlag ID "female", SPID_ in the game), found by
   name the first time the function runs (PrivateSkill::Get, then a 64-bit
   shift); the game then stores the u64 and never again. It is Job::IsFemale's
   own cache: not the one of Unit::IsFemale or Person::IsFemale
   (src/readable/female/female.h). The readable code reads it only after the
   game filled it (bit 0 of the guard word) and gives up before anything else
   while it is cold. No call is left in the body once the cache is filled. */
#define S_FemJobGuard 0x006D39ACu      /* Job::IsFemale (literal 0x006D3990 + 0x1C) */
#define S_FemJobMask 0x006D3A08u       /* u64, behind S_FemJobGuard (literal 0x006D3990 + 0x78) */

/* ---- the readable function (override entry at the end of the file) */
int32_t job_female_is_female(Context *ctx, gaddr job);

#endif /* FE_JOB_FEMALE_JOB_FEMALE_H */
