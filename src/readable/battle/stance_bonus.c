/* Stance bonuses and who may pair up (Fates classes PersonEnhanceDual,
   PersonEnhanceDouble, Unit). Plain-language description: docs/STANCES.md.

   Two bonus blocks hang off every Person record:
   - Person.attack_stance_bonus (+0x1C) -> the Attack Stance block: 4 signed
     bytes per support rank, one per battle number (BattleCapability::Type).
     It is what a unit gives the ally it fights next to.
   - Person.guard_stance_bonus (+0x20) -> the Guard Stance block: 8 signed
     bytes per support rank, one per stat (Capability::Type). It is what a
     unit gives the lead it is paired with.
   The bonus at rank r is the sum of the rows 0 .. r ("Total"). An avatar's
   boon and bane (unit::Edit +0x1A / +0x1B, two Personality records) move
   part of it between columns ("Edit"). A child unit (Person.family_index set)
   takes its bonus from its family record or from the family's Person.

   The guard (pair-up) bonus of a lead also adds its class's pair_up byte
   (Job +0x3C + stat) and one more point when the partner has a certain
   skill. The pair-up move bonus is the class's pair_up byte 0.

   Pairing up (Unit::CanDoubleOn): both units unpaired, in the same army, and
   neither carries the PersonFlag bit that forbids pairing (unit, its Person
   or its class).

   Every function here only reads guest memory. The guest calls are readers
   (src/readable/battle/stances.h). Caches are read only once the game has
   filled them; otherwise the function gives up and the original runs.

   Status: UNVERIFIED (below shadow-clean). Each function agrees with the
   original ARM code on generated inputs in the host differential test
   (src/readable/battle/tests/stance_diff.py, an ARM interpreter written for
   it); that is not a tier-2 or shadow result. */

#include "stances.h"

/* Sum of the signed bytes block[stride * i + column] for i = first .. last
   (none when last < first). Addresses wrap at 32 bits, as in the game: the
   column is any 32-bit value the caller passes. */
static int32_t bonus_rows(Context *ctx, gaddr block, uint32_t stride, uint32_t column, int32_t first,
                          int32_t last) {
    int32_t sum = 0;
    for (int32_t i = first; i <= last; i++)
        sum = fe_add32(sum, guest_s8(ctx, block + column + stride * (uint32_t)i));
    return sum;
}

/* A Personality record (the table global holds its base; Personality::Get(int)
   0x001A0B1C is that base + index * 0x40, done here without a guest call). */
static gaddr personality(Context *ctx, uint32_t index) {
    return guest_ptr(ctx, G_PersonalityTable) + index * (gaddr)sizeof(PersonalityData);
}

/* The Attack Stance bonus of one battle number at a support rank: rows 0 .. rank
   of column type (4 bytes per row). A negative rank gives 0.
   Guest function: 0x0050CBE8 PersonEnhanceDual::GetTotal(BattleCapability::Type,int) const. */
int32_t stance_attack_bonus_total(Context *ctx, gaddr block, uint32_t type, int32_t rank) {
    return rank < 0 ? 0 : bonus_rows(ctx, block, 4u, type, 0, rank);
}

/* The Guard Stance bonus of one stat at a support rank: rows 0 .. rank of
   column stat (8 bytes per row). A negative rank gives 0.
   Guest function: 0x0050D968 PersonEnhanceDouble::GetTotal(Capability::Type,int) const. */
int32_t stance_guard_bonus_total(Context *ctx, gaddr block, uint32_t stat, int32_t rank) {
    return rank < 0 ? 0 : bonus_rows(ctx, block, 8u, stat, 0, rank);
}

/* The avatar's change to an Attack Stance bonus. Each of the boon and bane
   Personality records names one battle number (PersonalityData.dual_group, -1 =
   none). Only when both name one, they differ, and the asked type is one of them:
   the bane's column, rows 1 .. rank, is summed; it counts against the bane's own
   number, and for the boon's number it is scaled by 5/3 when the bane names
   number 1 or by 3/5 when the boon names number 1 (divisions round toward 0).
   Guest function: 0x0050CADC PersonEnhanceDual::GetEdit(BattleCapability::Type,int,int,int) const. */
static int32_t attack_bonus_edit(Context *ctx, gaddr block, uint32_t type, int32_t rank, uint32_t boon,
                                 uint32_t bane) {
    int32_t boon_group = READ_FIELD(ctx, PersonalityData, personality(ctx, boon), dual_group);
    int32_t bane_group = READ_FIELD(ctx, PersonalityData, personality(ctx, bane), dual_group);
    if (boon_group == bane_group || type == 0xFFFFFFFFu)
        return 0;
    if (boon_group == -1 || bane_group == -1)
        return 0;
    if (type != (uint32_t)boon_group && type != (uint32_t)bane_group)
        return 0;
    int32_t moved = bonus_rows(ctx, block, 4u, (uint32_t)bane_group, 1, rank);
    if (type == (uint32_t)bane_group)
        return fe_mul32(moved, -1);
    if (bane_group == 1)
        return fe_mul32(moved, 5) / 3;
    if (boon_group == 1)
        return fe_mul32(moved, 3) / 5;
    return moved;
}

/* The avatar's change to a Guard Stance bonus. The boon and bane records each
   list three stats (PersonalityData.dual_stats, 0 = none); pair j counts when
   both name a stat, the two differ, and the asked stat is one of them: the bane
   stat's column, rows 1 .. rank, is summed, negative for the bane stat itself.
   The asked stat also gets +1 when it is the boon's first stat and the rank is
   at least 4.
   Guest function: 0x0050D844 PersonEnhanceDouble::GetEdit(Capability::Type,int,int,int) const. */
static int32_t guard_bonus_edit(Context *ctx, gaddr block, uint32_t stat, int32_t rank, uint32_t boon,
                                uint32_t bane) {
    gaddr boon_rec = personality(ctx, boon);
    gaddr bane_rec = personality(ctx, bane);
    int32_t total = 0;
    for (int j = 0; j < FE_ARRAY_LEN(PersonalityData, dual_stats); j++) {
        uint32_t boon_stat = READ_FIELD(ctx, PersonalityData, boon_rec, dual_stats[j]);
        uint32_t bane_stat = READ_FIELD(ctx, PersonalityData, bane_rec, dual_stats[j]);
        int counts = stat != 0 && boon_stat != 0 && bane_stat != 0 && boon_stat != bane_stat &&
                     (stat == boon_stat || stat == bane_stat);
        if (counts) {
            int32_t moved = bonus_rows(ctx, block, 8u, bane_stat, 1, rank);
            total = fe_add32(total, stat == bane_stat ? fe_mul32(moved, -1) : moved);
        }
        if (j == 0 && stat == boon_stat && rank >= 4)
            total = fe_add32(total, 1);
    }
    return total;
}

/* The game passes the bane, the fifth argument, on the stack: stack = sp at entry.
   Guest function: 0x0050CADC PersonEnhanceDual::GetEdit (see attack_bonus_edit). */
int32_t stance_attack_bonus_edit(Context *ctx, gaddr block, uint32_t type, int32_t rank, uint32_t boon,
                                 gaddr stack) {
    return attack_bonus_edit(ctx, block, type, rank, boon, guest_u32(ctx, stack));
}

/* Guest function: 0x0050D844 PersonEnhanceDouble::GetEdit (see guard_bonus_edit); bane on the stack. */
int32_t stance_guard_bonus_edit(Context *ctx, gaddr block, uint32_t stat, int32_t rank, uint32_t boon,
                                gaddr stack) {
    return guard_bonus_edit(ctx, block, stat, rank, boon, guest_u32(ctx, stack));
}

/* A child unit takes its stance bonus from its family: the Person record named
   by Person.family_index, when the game finds one. Returns that record or 0. */
static gaddr family_person(Context *ctx, gaddr person) {
    uint32_t family_index = READ_FIELD(ctx, PersonData, person, family_index);
    if (family_index == 0)
        return 0;
    return guest_call1(ctx, GUEST_PersonGet, family_index);
}

/* The unit's family record is set up (the record and two of its words are not 0). */
static int family_ready(Context *ctx, gaddr family) {
    return family != 0 && READ_FIELD(ctx, UnitFamily, family, link_00) != 0 &&
           READ_FIELD(ctx, UnitFamily, family, link_14) != 0;
}

/* What this unit gives the ally it fights next to (Attack Stance), for one
   battle number, at their support rank: its Person's Attack Stance rows (plus
   the avatar's change), or for a child the family's.
   Guest function: 0x0052E974 Unit::GetDualSupport(BattleCapability::Type,int) const -> int. */
int32_t unit_attack_stance_bonus(Context *ctx, gaddr unit, uint32_t type, int32_t rank) {
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    gaddr family_rec = family_person(ctx, person);
    if (family_rec != 0) {
        gaddr family = READ_FIELD(ctx, Unit, unit, family);
        if (family_ready(ctx, family))
            return (int32_t)guest_call3(ctx, GUEST_FamilyGetDualSupport, family, type, (uint32_t)rank);
        return stance_attack_bonus_total(ctx, READ_FIELD(ctx, PersonData, family_rec, attack_stance_bonus), type,
                                         rank);
    }
    gaddr block = READ_FIELD(ctx, PersonData, person, attack_stance_bonus);
    int32_t total = stance_attack_bonus_total(ctx, block, type, rank);
    gaddr edit = READ_FIELD(ctx, Unit, unit, edit);
    if (edit != 0)
        total = fe_add32(total, attack_bonus_edit(ctx, block, type, rank, READ_FIELD(ctx, UnitEdit, edit, boon),
                                                         READ_FIELD(ctx, UnitEdit, edit, bane)));
    return total;
}

/* What this unit, standing behind a lead in Guard Stance, gives that lead for
   one stat: its class's pair-up byte, plus its Guard Stance rows at the pair's
   support rank (its own plus the avatar's change, or for a child the family's),
   plus 1 when the lead has the pair-up skill. Stat 0 gives 0.
   Guest function: 0x00530A34 Unit::GetDoubleCapability(int,const Unit*) const -> int. */
int32_t unit_guard_stance_bonus(Context *ctx, gaddr unit, uint32_t stat, gaddr partner) {
    if (!fe_static_ready(ctx, S_PairSkillGuard))
        return (int32_t)fe_use_original(ctx);
    if (stat == 0)
        return 0;
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    int32_t class_bonus = guest_s8(ctx, FIELD_ADDR(JobData, job, pair_up) + stat);
    int32_t rank = (int32_t)guest_call2(ctx, GUEST_UnitGetRelianceLevel, unit, partner);
    uint32_t stat8 = stat & 0xFFu;
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    gaddr family_rec = family_person(ctx, person);
    int32_t rows;
    if (family_rec != 0) {
        gaddr family = READ_FIELD(ctx, Unit, unit, family);
        if (family_ready(ctx, family))
            rows = (int32_t)guest_call3(ctx, GUEST_FamilyGetDoubleCapability, family, stat8, (uint32_t)rank);
        else
            rows = stance_guard_bonus_total(ctx, READ_FIELD(ctx, PersonData, family_rec, guard_stance_bonus), stat8,
                                            rank);
    } else {
        gaddr block = READ_FIELD(ctx, PersonData, person, guard_stance_bonus);
        rows = stance_guard_bonus_total(ctx, block, stat8, rank);
        gaddr edit = READ_FIELD(ctx, Unit, unit, edit);
        if (edit != 0)
            rows = fe_add32(rows, guard_bonus_edit(ctx, block, stat8, rank, READ_FIELD(ctx, UnitEdit, edit, boon),
                                                          READ_FIELD(ctx, UnitEdit, edit, bane)));
    }
    int32_t total = fe_add32(rows, class_bonus);
    int32_t skill = guest_s16(ctx, S_PairSkillId);
    if (guest_call2(ctx, GUEST_UnitIsEquipSkill, partner, (uint32_t)skill) != 0)
        total = fe_add32(total, 1);
    return total;
}

/* The move bonus of a pair: the class's pair-up byte 0 (the partner is not read).
   Guest function: 0x00530680 Unit::GetDoubleMovePower(const Unit*) const -> int. */
int32_t unit_guard_stance_move(Context *ctx, gaddr unit, gaddr partner) {
    (void)partner;
    return READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), pair_up[0]);
}

/* The unit, its Person or its class carries the flag bit that forbids pairing up. */
static int pairing_forbidden(Context *ctx, gaddr unit, uint64_t mask) {
    uint64_t flags = READ_FIELD(ctx, Unit, unit, private_flags) |
                     READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), flags) |
                     READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), flags);
    return (flags & mask) != 0;
}

static uint32_t force_type(Context *ctx, gaddr unit) {
    return READ_FIELD(ctx, Force, READ_FIELD(ctx, Unit, unit, force), type);
}

/* Whether this unit may pair up with the other (Guard Stance): neither may
   carry the forbidding flag, both must be unpaired, and they must belong to
   the same army (force type).
   Guest function: 0x0052B60C Unit::CanDoubleOn(const Unit*) const -> 1 or 0. */
int unit_can_pair_with(Context *ctx, gaddr unit, gaddr other) {
    if (!fe_static_ready(ctx, S_NoPairGuard))
        return (int)fe_use_original(ctx);
    uint64_t mask = guest_u64(ctx, S_NoPairMask);
    if (pairing_forbidden(ctx, unit, mask) || pairing_forbidden(ctx, other, mask))
        return 0;
    if (READ_FIELD(ctx, Unit, unit, pair_partner) != 0 || READ_FIELD(ctx, Unit, other, pair_partner) != 0)
        return 0;
    return force_type(ctx, unit) == force_type(ctx, other);
}

RECOMP_OVERRIDE(0x0050CBE8) {
    FE_ENTRY(0x0050CBE8, stance_attack_bonus_total, FE_ARG(0), FE_ARG(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x0050D968) {
    FE_ENTRY(0x0050D968, stance_guard_bonus_total, FE_ARG(0), FE_ARG(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x0050CADC) {
    FE_ENTRY(0x0050CADC, stance_attack_bonus_edit, FE_ARG(0), FE_ARG(1), FE_ARG_S(2), FE_ARG(3), FE_ARG(13));
}

RECOMP_OVERRIDE(0x0050D844) {
    FE_ENTRY(0x0050D844, stance_guard_bonus_edit, FE_ARG(0), FE_ARG(1), FE_ARG_S(2), FE_ARG(3), FE_ARG(13));
}

RECOMP_OVERRIDE(0x0052E974) {
    FE_ENTRY(0x0052E974, unit_attack_stance_bonus, FE_ARG(0), FE_ARG(1), FE_ARG_S(2));
}

RECOMP_OVERRIDE(0x00530A34) {
    FE_ENTRY(0x00530A34, unit_guard_stance_bonus, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x00530680) {
    FE_ENTRY(0x00530680, unit_guard_stance_move, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052B60C) {
    FE_ENTRY(0x0052B60C, unit_can_pair_with, FE_ARG(0), FE_ARG(1));
}
