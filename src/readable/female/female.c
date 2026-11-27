/* Is this unit, or this person, female (Fates Unit::IsFemale and
   Person::IsFemale). Plain-language description: docs/FEMALE.md.

   Both are readers: they store nothing. Each of the game's two functions
   fills one one-time cache of its own the first time it runs (the PersonFlag
   bit "female", found by name); the readable code gives up while its cache is
   cold, before it reads anything else, so the game's own code fills it
   exactly as before.

   Unit::IsFemale does not call Person::IsFemale: it ORs the three PersonFlag
   words itself (the unit's own, its Person's and its class's) and tests them
   against its own cache. Job::IsFemale (the class alone) is not part of this
   batch (docs/tracks/REWRITE_ORDER4.md row 3 names the two below).

   Not here: no spouse or child rule (nothing in either body asks about
   family). The callers (Unit::CanItemEquip, unit::Family::GetGrow,
   ParentSingle::GetGrow and the game's own) are unchanged.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/female/tests/female_diff.py. */

#include "female.h"

/* Is this unit female? 1 or 0.
   Yes when the PersonFlag words of the unit itself (Unit.private_flags), of
   its Person record (Unit.person -> PersonData.flags) and of its class
   (Unit.job -> JobData.flags), ORed, share a bit with the cached "female"
   bit. So a class or a unit-level flag can make a unit female too.
   Guest function: 0x00533938 Unit::IsFemale(void) const. */
int32_t female_unit_is_female(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, S_FemUnitGuard))
        return (int32_t)fe_use_original(ctx);
    uint64_t female = guest_u64(ctx, S_FemUnitMask);
    uint64_t flags = READ_FIELD(ctx, Unit, unit, private_flags);
    flags |= READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), flags);
    flags |= READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), flags);
    return (flags & female) != 0;
}

/* Is this person (a PersonData record) female? 1 or 0.
   Yes when PersonData.flags shares a bit with the cached "female" bit.
   Guest function: 0x0053ED90 Person::IsFemale(void) const. */
int32_t female_person_is_female(Context *ctx, gaddr person) {
    if (!fe_static_ready(ctx, S_FemPersonGuard))
        return (int32_t)fe_use_original(ctx);
    uint64_t female = guest_u64(ctx, S_FemPersonMask);
    return (READ_FIELD(ctx, PersonData, person, flags) & female) != 0;
}

RECOMP_OVERRIDE(0x00533938) {
    FE_ENTRY(0x00533938, female_unit_is_female, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0053ED90) {
    FE_ENTRY(0x0053ED90, female_person_is_female, FE_ARG(0));
}
