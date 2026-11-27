/* Is this class the female one (Fates Job::IsFemale). Plain-language
   description: docs/JOB_FEMALE.md.

   A reader: it stores nothing. The game's function fills one one-time cache
   of its own the first time it runs (the PersonFlag bit "female", found by
   name); the readable code gives up while that cache is cold, before it reads
   anything else, so the game's own code fills it exactly as before.

   The class-only twin of female_unit_is_female (src/readable/female/, not
   edited): the same test on the class record's flag word alone. Unit::IsFemale
   does not call it (it reads the class's word itself).

   Not here: no spouse or child rule (nothing in the body asks about family).
   The callers (the class-change lists, Swimwear::Get, the battle model name,
   the castle and the game's own) are unchanged.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/job_female/tests/job_female_diff.py. */

#include "job_female.h"

/* Is this class (a JobData record) the female one? 1 or 0.
   Yes when JobData.flags shares a bit with the cached "female" bit.
   Guest function: 0x00524AF4 Job::IsFemale(void) const. */
int32_t job_female_is_female(Context *ctx, gaddr job) {
    if (!fe_static_ready(ctx, S_FemJobGuard))
        return (int32_t)fe_use_original(ctx);
    uint64_t female = guest_u64(ctx, S_FemJobMask);
    return (READ_FIELD(ctx, JobData, job, flags) & female) != 0;
}

RECOMP_OVERRIDE(0x00524AF4) {
    FE_ENTRY(0x00524AF4, job_female_is_female, FE_ARG(0));
}
