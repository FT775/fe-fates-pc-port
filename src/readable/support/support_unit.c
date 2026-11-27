/* Supports between two units (Fates class Unit): a pair's support points and
   level, the highest level the pair can reach, whether two units may support
   at all, the family tests (parent and child, siblings, uncle or aunt and
   nephew or niece), whether a pair may reach S (romance), the married
   partner, and whether two units may trade pair-up partners.
   Plain-language description: docs/SUPPORT.md sections 4 to 6.

   All are readers: they store nothing. Only unit_can_trade_partner reads a
   one-time cache (a PersonFlag bit found by name); it gives up while that is
   cold, before reading anything else. Guest calls left: the ones the game
   makes (support.h), in the game's order (docs/DECISIONS.md F-018). Tail
   branches: to a guest function that is not an override (Person::Get, the two
   GetMaxLevel) the readable code makes a guest call; to an override (only in
   unit_support_level) it runs the C, as the generated original runs the
   target's code inline.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/support/tests/support_diff.py. */

#include "support.h"

/* Unit::IsUnique as the game writes it inline at the top of every support
   function (the state word is read twice): a unit with state bit 18 has no
   supports; one with state bit 28 only when its Person is a download one. */
static int is_unique(Context *ctx, gaddr unit) {
    if (READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_NOT_UNIQUE_BIT)
        return 0;
    if (!(READ_FIELD(ctx, Unit, unit, state_flags) & UNIT_STATE_MAYBE_CLONE_BIT))
        return 1;
    return guest_call1(ctx, SUP_PersonIsDownload, READ_FIELD(ctx, Unit, unit, person)) != 0;
}

static int both_unique(Context *ctx, gaddr unit, gaddr other) {
    return is_unique(ctx, unit) && is_unique(ctx, other);
}

static gaddr find_entry(Context *ctx, gaddr unit, gaddr other) {
    gaddr theirs = READ_FIELD(ctx, Unit, other, person);
    gaddr mine = READ_FIELD(ctx, Unit, unit, person);
    return guest_call2(ctx, SUP_RelianceGetFromPerson, mine, theirs);
}

/* The pair's support points: a byte of the support-points array kept by the
   unit itself (when the entry says so) or by the partner's unit (the unique
   unit of the partner's person number in this unit's side of the war), at the
   entry's slot; 0 for a unit that is not unique or when there is no array.
   Guest function: 0x0052C260 Unit::GetReliance(const Reliance*) const. */
int32_t unit_support_points(Context *ctx, gaddr unit, gaddr reliance) {
    if (!is_unique(ctx, unit))
        return 0;
    gaddr keeper = unit;
    if (guest_u8(ctx, reliance + RELIANCE_OWNS_POINTS) == 0) {
        gaddr force = READ_FIELD(ctx, Unit, unit, force);
        uint32_t mask = guest_call1(ctx, SUP_ForceGetMaskSameForce, READ_FIELD(ctx, Force, force, type));
        keeper = guest_call2(ctx, SUP_UnitPoolGetFromPerson, guest_u16(ctx, reliance + RELIANCE_PARTNER), mask);
        if (keeper == 0)
            return 0;
    }
    gaddr points = guest_ptr(ctx, keeper + UNIT_SUPPORT_POINTS);
    if (points == 0)
        return 0;
    return guest_u8(ctx, points + guest_u16(ctx, reliance + RELIANCE_SLOT));
}

/* The pair's support level (0 none, 1 C, 2 B, 3 A, 4 S): parent and child use
   the child's family record (points with that parent), siblings the sibling
   record, everyone else the support table and the points.
   The game ends in a tail branch to ParentSingle::GetLevel, BrotherSingle::
   GetLevel or Reliance::GetLevel; 3dsrecomp keeps a copy of those three inside
   this function's generated code (reached with a plain goto; their inner labels
   are listed under f_0052F518 in the build's lib/entries.c), so the original never
   enters their overrides from here: the readable code runs their C directly
   (no guest call), which keeps the capture's call lists equal (F-018).
   Guest function: 0x0052F518 Unit::GetRelianceLevel(const Unit*) const. */
int32_t unit_support_level(Context *ctx, gaddr unit, gaddr other) {
    if (!both_unique(ctx, unit, other))
        return 0;
    gaddr child = guest_call2(ctx, SUP_UnitGetFamilyChildImpl, unit, other);
    if (child != 0) {
        gaddr parent_unit = child == unit ? other : unit;
        gaddr parent = guest_call2(ctx, SUP_FamilyGetParent, READ_FIELD(ctx, Unit, child, family), parent_unit);
        if (parent == 0)
            return 0;
        return family_parent_level(ctx, parent, guest_u8(ctx, parent + FAMILY_PARENT_POINTS));
    }
    if (guest_call2(ctx, SUP_UnitIsFamilyBrotherSister, unit, other) != 0) {
        gaddr sibling = READ_FIELD(ctx, Unit, unit, family) + FAMILY_SIBLING;
        return family_sibling_level(ctx, sibling, guest_u8(ctx, sibling + FAMILY_SIBLING_POINTS));
    }
    gaddr entry = find_entry(ctx, unit, other);
    if (entry == 0)
        return 0;
    int32_t points = (int32_t)guest_call2(ctx, SUP_UnitGetReliance, unit, entry);
    return reliance_level(ctx, entry, points);
}

/* The highest level the pair can reach: 3 (A) for family, else the support
   table's, where an S becomes A when either unit's Person is a download one.
   Guest function: 0x00530D2C Unit::GetRelianceMaxLevel(const Unit*) const. */
int32_t unit_support_max_level(Context *ctx, gaddr unit, gaddr other) {
    if (!both_unique(ctx, unit, other))
        return 0;
    gaddr child = guest_call2(ctx, SUP_UnitGetFamilyChildImpl, unit, other);
    if (child != 0) {
        gaddr parent_unit = child == unit ? other : unit;
        gaddr parent = guest_call2(ctx, SUP_FamilyGetParent, READ_FIELD(ctx, Unit, child, family), parent_unit);
        if (parent == 0)
            return 0;
        return (int32_t)guest_call1(ctx, SUP_ParentGetMaxLevel, parent);
    }
    if (guest_call2(ctx, SUP_UnitIsFamilyBrotherSister, unit, other) != 0)
        return (int32_t)guest_call1(ctx, SUP_BrotherGetMaxLevel, READ_FIELD(ctx, Unit, unit, family) + FAMILY_SIBLING);
    gaddr entry = find_entry(ctx, unit, other);
    if (entry == 0)
        return 0;
    int32_t level = (int32_t)guest_call1(ctx, SUP_RelianceGetMaxLevel, entry);
    if (level == 4 && (guest_call1(ctx, SUP_PersonIsDownload, READ_FIELD(ctx, Unit, unit, person)) != 0 ||
                       guest_call1(ctx, SUP_PersonIsDownload, READ_FIELD(ctx, Unit, other, person)) != 0))
        level = 3;
    return level;
}

/* 1 when the two units have a support: family always; an uncle or aunt with
   a nephew or niece not when the pair could romance; everyone else when the
   support table has the pair.
   Guest function: 0x0052AD24 Unit::IsReliance(const Unit*) const. */
uint32_t unit_can_support(Context *ctx, gaddr unit, gaddr other) {
    if (!both_unique(ctx, unit, other))
        return 0;
    if (guest_call2(ctx, SUP_UnitIsFamily, unit, other) != 0)
        return 1;
    if (guest_call2(ctx, SUP_UnitIsFamilyUncleAunt, unit, other) != 0 &&
        guest_call2(ctx, SUP_UnitIsRomance, unit, other) != 0)
        return 0;
    return find_entry(ctx, unit, other) != 0 ? 1u : 0u;
}

/* Is one of the two a parent of the other (through the other's family
   record)? Returns the child unit, or 0.
   Guest function: 0x005306C4 Unit::GetFamilyChildImpl(const Unit*) const. */
gaddr unit_family_child(Context *ctx, gaddr unit, gaddr other) {
    if (!both_unique(ctx, unit, other))
        return 0;
    gaddr family = READ_FIELD(ctx, Unit, unit, family);
    if (family != 0) {
        gaddr first = guest_ptr(ctx, family + FAMILY_PARENT_A + FAMILY_PARENT_PERSON);
        gaddr parent = READ_FIELD(ctx, Unit, other, person);
        if (first == parent || guest_ptr(ctx, family + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) == parent)
            return unit;
    }
    family = READ_FIELD(ctx, Unit, other, family);
    if (family != 0) {
        gaddr first = guest_ptr(ctx, family + FAMILY_PARENT_A + FAMILY_PARENT_PERSON);
        gaddr parent = READ_FIELD(ctx, Unit, unit, person);
        if (first == parent || guest_ptr(ctx, family + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) == parent)
            return other;
    }
    return 0;
}

/* Guest function: 0x00530E84 Unit::IsFamilyParentChild(const Unit*) const. */
uint32_t unit_is_parent_child(Context *ctx, gaddr unit, gaddr other) {
    return guest_call2(ctx, SUP_UnitGetFamilyChildImpl, unit, other) != 0 ? 1u : 0u;
}

/* 1 for two children with a family record each that share their first
   parent, or else their second parent (both set).
   Guest function: 0x00531428 Unit::IsFamilyBrotherSister(const Unit*) const. */
uint32_t unit_is_sibling(Context *ctx, gaddr unit, gaddr other) {
    if (!both_unique(ctx, unit, other))
        return 0;
    gaddr mine = READ_FIELD(ctx, Unit, unit, family);
    if (mine == 0)
        return 0;
    gaddr theirs = READ_FIELD(ctx, Unit, other, family);
    if (theirs == 0)
        return 0;
    gaddr a = guest_ptr(ctx, mine + FAMILY_PARENT_A + FAMILY_PARENT_PERSON);
    if (a != 0) {
        gaddr b = guest_ptr(ctx, theirs + FAMILY_PARENT_A + FAMILY_PARENT_PERSON);
        if (b != 0 && a == b)
            return 1;
    }
    a = guest_ptr(ctx, mine + FAMILY_PARENT_B + FAMILY_PARENT_PERSON);
    if (a == 0)
        return 0;
    gaddr b = guest_ptr(ctx, theirs + FAMILY_PARENT_B + FAMILY_PARENT_PERSON);
    return b != 0 && a == b ? 1u : 0u;
}

/* both parents of a family record set (the game's test before using it) */
static int has_both_parents(Context *ctx, gaddr family) {
    return guest_ptr(ctx, family + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) != 0 &&
           guest_ptr(ctx, family + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) != 0;
}

/* 1 when one unit's grandparent is the other unit's parent: the unit's
   grandfather is the other's first parent or its grandmother the other's
   second parent, then the same the other way round. Not for parent and child.
   The game reads the family words again at each step; so does this.
   Guest function: 0x0052FA58 Unit::IsFamilyUncleAunt(const Unit*) const. */
uint32_t unit_is_uncle_aunt(Context *ctx, gaddr unit, gaddr other) {
    if (guest_call2(ctx, SUP_UnitGetFamilyChildImpl, unit, other) != 0)
        return 0;
    gaddr mine = READ_FIELD(ctx, Unit, unit, family);
    if (mine != 0 && has_both_parents(ctx, mine)) {
        gaddr grandfather = guest_call1(ctx, SUP_FamilyGetGrandFather, mine);
        if (grandfather != 0) {
            gaddr theirs = READ_FIELD(ctx, Unit, other, family);
            if (theirs != 0) {
                gaddr a = guest_ptr(ctx, theirs + FAMILY_PARENT_A + FAMILY_PARENT_PERSON);
                if (a != 0 && guest_ptr(ctx, theirs + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) != 0 && a == grandfather)
                    return 1;
            }
        }
        gaddr grandmother = guest_call1(ctx, SUP_FamilyGetGrandMother, READ_FIELD(ctx, Unit, unit, family));
        if (grandmother != 0) {
            gaddr theirs = READ_FIELD(ctx, Unit, other, family);
            if (theirs == 0)
                return 0;
            if (guest_ptr(ctx, theirs + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) != 0) {
                gaddr b = guest_ptr(ctx, theirs + FAMILY_PARENT_B + FAMILY_PARENT_PERSON);
                if (b != 0 && b == grandmother)
                    return 1;
            }
            goto other_way;
        }
    }
    if (READ_FIELD(ctx, Unit, other, family) == 0)
        return 0;
other_way:;
    gaddr theirs = READ_FIELD(ctx, Unit, other, family);
    if (!has_both_parents(ctx, theirs))
        return 0;
    gaddr grandfather = guest_call1(ctx, SUP_FamilyGetGrandFather, theirs);
    if (grandfather != 0) {
        mine = READ_FIELD(ctx, Unit, unit, family);
        if (mine != 0) {
            gaddr a = guest_ptr(ctx, mine + FAMILY_PARENT_A + FAMILY_PARENT_PERSON);
            if (a != 0 && guest_ptr(ctx, mine + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) != 0 && a == grandfather)
                return 1;
        }
    }
    gaddr grandmother = guest_call1(ctx, SUP_FamilyGetGrandMother, READ_FIELD(ctx, Unit, other, family));
    if (grandmother == 0)
        return 0;
    mine = READ_FIELD(ctx, Unit, unit, family);
    if (mine == 0 || guest_ptr(ctx, mine + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) == 0)
        return 0;
    gaddr b = guest_ptr(ctx, mine + FAMILY_PARENT_B + FAMILY_PARENT_PERSON);
    return b != 0 && b == grandmother ? 1u : 0u;
}

/* 1 for parent and child or siblings (both units unique).
   Guest function: 0x0053386C Unit::IsFamily(const Unit*) const. */
uint32_t unit_is_family(Context *ctx, gaddr unit, gaddr other) {
    if (!both_unique(ctx, unit, other))
        return 0;
    if (guest_call2(ctx, SUP_UnitGetFamilyChildImpl, unit, other) != 0)
        return 1;
    return guest_call2(ctx, SUP_UnitIsFamilyBrotherSister, unit, other) != 0 ? 1u : 0u;
}

/* 1 when the pair could reach S: both unique, not family, and their support
   table entry has an S level.
   Guest function: 0x005346F0 Unit::IsRomance(const Unit*) const. */
uint32_t unit_can_romance(Context *ctx, gaddr unit, gaddr other) {
    if (!both_unique(ctx, unit, other))
        return 0;
    if (guest_call2(ctx, SUP_UnitIsFamily, unit, other) != 0)
        return 0;
    gaddr entry = find_entry(ctx, unit, other);
    if (entry == 0)
        return 0;
    return guest_call1(ctx, SUP_RelianceIsRomance, entry) != 0 ? 1u : 0u;
}

/* The married partner: the PID (Person.pid) of the first support partner,
   in table order, with whom the unit is at S; 0 when none or not unique.
   Guest function: 0x0052E634 Unit::GetMarrigePid(void) const. */
gaddr unit_spouse_pid(Context *ctx, gaddr unit) {
    if (!is_unique(ctx, unit))
        return 0;
    int32_t count = (int32_t)guest_call1(ctx, SUP_RelianceGetNum, READ_FIELD(ctx, Unit, unit, person));
    for (int32_t i = 0; i < count; i++) {
        gaddr entry = guest_call2(ctx, SUP_RelianceGet, READ_FIELD(ctx, Unit, unit, person), (uint32_t)i);
        uint32_t points = guest_call2(ctx, SUP_UnitGetReliance, unit, entry);
        if ((int32_t)guest_call2(ctx, SUP_RelianceGetLevel, entry, points) >= 4) {
            gaddr person = guest_call1(ctx, SUP_RelianceGetPerson, entry);
            return guest_ptr(ctx, person + PERSON_PID_STRING);
        }
    }
    return 0;
}

/* the unit's, its Person's and its class's PersonFlag words together */
static uint64_t all_flags(Context *ctx, gaddr unit) {
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    return READ_FIELD(ctx, Unit, unit, private_flags) | READ_FIELD(ctx, PersonData, person, flags) |
           READ_FIELD(ctx, JobData, job, flags);
}

static uint32_t force_type(Context *ctx, gaddr unit) {
    gaddr force = READ_FIELD(ctx, Unit, unit, force);
    return READ_FIELD(ctx, Force, force, type);
}

/* 1 when the two units may trade pair-up partners: neither has the "pair-up
   forbidden" PersonFlag bit (unit, person or class), at least one of them is
   paired, both are on the same force type, and each partner present is too.
   Guest function: 0x0052E818 Unit::CanDoubleTrade(const Unit*) const. */
uint32_t unit_can_trade_partner(Context *ctx, gaddr unit, gaddr other) {
    if (!fe_static_ready(ctx, S_TradeGuard))
        return fe_use_original(ctx);
    uint64_t forbidden = guest_u64(ctx, S_TradeNoPairMask);
    if (all_flags(ctx, unit) & forbidden)
        return 0;
    if (all_flags(ctx, other) & forbidden)
        return 0;
    gaddr mine = READ_FIELD(ctx, Unit, unit, pair_partner);
    if (mine == 0 && READ_FIELD(ctx, Unit, other, pair_partner) == 0)
        return 0;
    uint32_t type = force_type(ctx, unit);
    if (force_type(ctx, other) != type)
        return 0;
    if (mine != 0 && force_type(ctx, mine) != type)
        return 0;
    gaddr theirs = READ_FIELD(ctx, Unit, other, pair_partner);
    if (theirs == 0)
        return 1;
    return force_type(ctx, theirs) == type ? 1u : 0u;
}

RECOMP_OVERRIDE(0x0052C260) {
    FE_ENTRY(0x0052C260, unit_support_points, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052F518) {
    FE_ENTRY(0x0052F518, unit_support_level, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00530D2C) {
    FE_ENTRY(0x00530D2C, unit_support_max_level, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052AD24) {
    FE_ENTRY(0x0052AD24, unit_can_support, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x005306C4) {
    FE_ENTRY(0x005306C4, unit_family_child, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00530E84) {
    FE_ENTRY(0x00530E84, unit_is_parent_child, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00531428) {
    FE_ENTRY(0x00531428, unit_is_sibling, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052FA58) {
    FE_ENTRY(0x0052FA58, unit_is_uncle_aunt, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0053386C) {
    FE_ENTRY(0x0053386C, unit_is_family, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x005346F0) {
    FE_ENTRY(0x005346F0, unit_can_romance, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052E634) {
    FE_ENTRY(0x0052E634, unit_spouse_pid, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052E818) {
    FE_ENTRY(0x0052E818, unit_can_trade_partner, FE_ARG(0), FE_ARG(1));
}
