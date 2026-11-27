/* The support table and the family record (Fates classes Reliance and
   unit::Family): which partners a person may support, how many points each
   support level needs, how support points turn into a level (C = 1, B = 2,
   A = 3, S = 4), a child's parents and grandparents, and whether the current
   map lets units gain support points at all.
   Plain-language description: docs/SUPPORT.md sections 1 to 3.

   All are readers: they store nothing and read no one-time cache, so none of
   them can give up by itself. Guest calls left: Person::Get (support.h).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/support/tests/support_diff.py. */

#include "support.h"

static uint32_t points_needed(Context *ctx, gaddr reliance, int32_t level) {
    return guest_u8(ctx, reliance + RELIANCE_POINTS + (gaddr)level);
}

/* The highest support level this pair can reach: the highest of S, A, B, C
   whose "points needed" is not the 99 that marks a missing level; 0 when none
   exists. Guest function: 0x005467F0 Reliance::GetMaxLevel(void) const. */
int32_t reliance_max_level(Context *ctx, gaddr reliance) {
    for (int32_t level = 4; level > 1; level--)
        if (points_needed(ctx, reliance, level) < RELIANCE_POINTS_NEVER)
            return level;
    return points_needed(ctx, reliance, 1) < RELIANCE_POINTS_NEVER ? 1 : 0;
}

/* The level a pair has with this many points: the highest level whose
   "points needed" is at most the points (a missing level needs 99).
   Guest function: 0x00546878 Reliance::GetLevel(int) const. */
int32_t reliance_level(Context *ctx, gaddr reliance, int32_t points) {
    for (int32_t level = 4; level > 1; level--)
        if ((int32_t)points_needed(ctx, reliance, level) <= points)
            return level;
    return (int32_t)points_needed(ctx, reliance, 1) <= points ? 1 : 0;
}

/* The partner's Person record (Person::Get of the entry's person number).
   Guest function: 0x005468BC Reliance::GetPerson(void) const. */
gaddr reliance_person(Context *ctx, gaddr reliance) {
    return guest_call1(ctx, SUP_PersonGet, guest_u16(ctx, reliance + RELIANCE_PARTNER));
}

/* 1 when the pair has an S level (marriage or a sworn bond): its S threshold
   is not the 99 of a missing level.
   Guest function: 0x005468C4 Reliance::IsRomance(void) const. */
uint32_t reliance_is_romance(Context *ctx, gaddr reliance) {
    return points_needed(ctx, reliance, 4) < RELIANCE_POINTS_NEVER ? 1u : 0u;
}

/* The first chain node of a person's support list, or 0 (a person with a
   negative support id has none). *id gets the id. */
static gaddr first_node(Context *ctx, gaddr person, int32_t *id) {
    *id = READ_FIELD(ctx, PersonData, person, support_id);
    if (*id < 0)
        return 0;
    gaddr buckets = guest_ptr(ctx, G_RelianceTable);
    return guest_ptr(ctx, buckets + ((uint32_t)*id & RELIANCE_BUCKETS_MASK) * 4u);
}

static gaddr node_record(Context *ctx, gaddr node) { return guest_ptr(ctx, node + RELIANCE_NODE_RECORD); }
static gaddr node_next(Context *ctx, gaddr node) { return guest_ptr(ctx, node + RELIANCE_NODE_NEXT); }
static gaddr entry_at(gaddr record, int32_t i) {
    return record + RELIANCE_REC_ENTRIES + (gaddr)i * RELIANCE_ENTRY_SIZE;
}

/* How many support partners the person has: the entry counts of every record
   of the person's chain that carries the person's support id.
   Guest function: 0x004F1284 Reliance::GetNum(const Person*). */
int32_t reliance_count(Context *ctx, gaddr person) {
    int32_t id;
    gaddr node = first_node(ctx, person, &id);
    if (id < 0)
        return 0;
    int32_t count = 0;
    while (node != 0) {
        gaddr record = node_record(ctx, node);
        node = node_next(ctx, node);
        if (guest_u16(ctx, record + RELIANCE_REC_ID) == (uint32_t)id)
            count = fe_add32(count, guest_u16(ctx, record + RELIANCE_REC_COUNT));
    }
    return count;
}

/* The person's index-th support partner entry (counted over the matching
   records in chain order), or 0 past the end. A negative index is not
   checked: it gives an address before the first matching record's entries.
   Guest function: 0x004F10EC Reliance::Get(const Person*, int). */
gaddr reliance_entry(Context *ctx, gaddr person, int32_t index) {
    int32_t id;
    gaddr node = first_node(ctx, person, &id);
    if (id < 0)
        return 0;
    for (; node != 0; node = node_next(ctx, node)) {
        gaddr record = node_record(ctx, node);
        if (guest_u16(ctx, record + RELIANCE_REC_ID) != (uint32_t)id)
            continue;
        int32_t count = guest_u16(ctx, record + RELIANCE_REC_COUNT);
        if (count <= index) {
            index -= count;
            continue;
        }
        /* the game reads the node's record pointer again here */
        return entry_at(node_record(ctx, node), index);
    }
    return 0;
}

/* The entry for the pair (person, other): the first entry of the person's
   matching records whose partner number is other's person number, or 0.
   The game's search goes two entries at a time after an odd first one and
   reads other's number once for that first entry and once for the pairs.
   Guest function: 0x004F0FDC Reliance::GetFromPerson(const Person*, const Person*). */
gaddr reliance_find(Context *ctx, gaddr person, gaddr other) {
    int32_t id;
    gaddr node = first_node(ctx, person, &id);
    if (id < 0)
        return 0;
    for (; node != 0; node = node_next(ctx, node)) {
        gaddr record = node_record(ctx, node);
        if (guest_u16(ctx, record + RELIANCE_REC_ID) != (uint32_t)id)
            continue;
        int32_t count = guest_u16(ctx, record + RELIANCE_REC_COUNT);
        if (count == 0)
            continue;
        int32_t i = count & 1;
        if (i) {
            uint32_t wanted = READ_FIELD(ctx, PersonData, other, pid_number);
            if (guest_u16(ctx, entry_at(record, 0) + RELIANCE_PARTNER) == wanted)
                return entry_at(record, 0);
        }
        if (i < count) {
            uint32_t wanted = READ_FIELD(ctx, PersonData, other, pid_number);
            for (; i < count; i++)
                if (guest_u16(ctx, entry_at(record, i) + RELIANCE_PARTNER) == wanted)
                    return entry_at(record, i);
        }
    }
    return 0;
}

/* Of a child's two parents, the record of the one who is this unit's person,
   or 0. Guest function: 0x0053BECC unit::Family::GetParent(const Unit*) const. */
gaddr family_parent_record(Context *ctx, gaddr family, gaddr unit) {
    gaddr first = guest_ptr(ctx, family + FAMILY_PARENT_A + FAMILY_PARENT_PERSON);
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    if (first == person)
        return family + FAMILY_PARENT_A;
    if (guest_ptr(ctx, family + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) == person)
        return family + FAMILY_PARENT_B;
    return 0;
}

/* Parent and child support levels come from fixed thresholds, not from the
   support table: 1 point = C, 5 = B, 10 = A (no S). */
static int32_t family_level(int32_t points) {
    if (points >= 10)
        return 3;
    if (points >= 5)
        return 2;
    return points >= 1 ? 1 : 0;
}

/* Guest function: 0x0053B800 unit::Family::ParentSingle::GetLevel(int) const
   (the record itself is not read). */
int32_t family_parent_level(Context *ctx, gaddr parent, int32_t points) {
    (void)ctx;
    (void)parent;
    return family_level(points);
}

/* The same thresholds between siblings.
   Guest function: 0x0053B864 unit::Family::BrotherSingle::GetLevel(int) const. */
int32_t family_sibling_level(Context *ctx, gaddr sibling, int32_t points) {
    (void)ctx;
    (void)sibling;
    return family_level(points);
}

/* A grandparent of a child with both parents set: the first parent's, else the
   second parent's (field `which` of a ParentSingle); 0 without both parents. */
static gaddr grandparent(Context *ctx, gaddr family, gaddr which) {
    if (guest_ptr(ctx, family + FAMILY_PARENT_A + FAMILY_PARENT_PERSON) == 0 ||
        guest_ptr(ctx, family + FAMILY_PARENT_B + FAMILY_PARENT_PERSON) == 0)
        return 0;
    gaddr g = guest_ptr(ctx, family + FAMILY_PARENT_A + which);
    return g != 0 ? g : guest_ptr(ctx, family + FAMILY_PARENT_B + which);
}

/* Guest function: 0x0053BAC8 unit::Family::GetGrandFather(void) const. */
gaddr family_grandfather(Context *ctx, gaddr family) {
    return grandparent(ctx, family, FAMILY_PARENT_GRANDFATHER);
}

/* Guest function: 0x0053BAF4 unit::Family::GetGrandMother(void) const. */
gaddr family_grandmother(Context *ctx, gaddr family) {
    return grandparent(ctx, family, FAMILY_PARENT_GRANDMOTHER);
}

/* 1 when units of this force (0, 1 or 2) gain support points on the current
   map: the map's "no support points" flag is clear and the force's byte at the
   start of the Situation is 1 (the byte map::Situation::CanDual reads too).
   Guest function: 0x00527EC8 map::Situation::CanGainReliance(Force::Type) const. */
uint32_t situation_can_gain_support(Context *ctx, gaddr situation, uint32_t force) {
    if (force >= 3)
        return 0;
    if (READ_FIELD(ctx, Situation, situation, flags) & SITUATION_NO_SUPPORT_GAIN)
        return 0;
    return guest_u8(ctx, situation + force) == 1 ? 1u : 0u;
}

RECOMP_OVERRIDE(0x005467F0) {
    FE_ENTRY(0x005467F0, reliance_max_level, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00546878) {
    FE_ENTRY(0x00546878, reliance_level, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x005468BC) {
    FE_ENTRY(0x005468BC, reliance_person, FE_ARG(0));
}

RECOMP_OVERRIDE(0x005468C4) {
    FE_ENTRY(0x005468C4, reliance_is_romance, FE_ARG(0));
}

RECOMP_OVERRIDE(0x004F1284) {
    FE_ENTRY(0x004F1284, reliance_count, FE_ARG(0));
}

RECOMP_OVERRIDE(0x004F10EC) {
    FE_ENTRY(0x004F10EC, reliance_entry, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x004F0FDC) {
    FE_ENTRY(0x004F0FDC, reliance_find, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0053BECC) {
    FE_ENTRY(0x0053BECC, family_parent_record, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0053B800) {
    FE_ENTRY(0x0053B800, family_parent_level, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0053B864) {
    FE_ENTRY(0x0053B864, family_sibling_level, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0053BAC8) {
    FE_ENTRY(0x0053BAC8, family_grandfather, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0053BAF4) {
    FE_ENTRY(0x0053BAF4, family_grandmother, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00527EC8) {
    FE_ENTRY(0x00527EC8, situation_can_gain_support, FE_ARG(0), FE_ARG(1));
}
