/* Growth rates and stat caps (Fates class Unit, unit::Edit, unit::Family).
   Plain-language description: docs/GROWTH.md sections 2 and 3.

   Growth rate of a stat (Unit::GetGrow):
     rate = Person.growth[s] (+ the avatar's boon and bane growth, unit::Edit)
     child: rate = (rate + the parent's rate) / 2   (unit::Family::GetGrow; the
            parent's rate is its own growth + its boon and bane growth, averaged
            with one grandparent's growth when both grandparents are known,
            never below 0)
     rate += Job.growth[s] for Person.unit_kind 1, else Job.enemy_growth[s]
     rate += 10 with one equipped skill
   Stat cap (Unit::GetLimit):
     cap = Job.max[s] + Person.limit_mod[s] (+ family terms) (+ boon/bane limit)
           + Unit.limit_bonus[s], clamped 0 .. 99

   The game reads some words twice (the unit's person and family pointers);
   the readable code reads them as often as the game, so a made-up state with
   an unmapped record faults the same number of bytes (tier 2 compares that).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/unit/tests/growth_diff.py. */

#include "growth.h"

/* Personality::Get(int): base of the Personality table + index * 0x40 (the
   table pointer is read each time, as the game's getter does) */
static gaddr personality(Context *ctx, uint32_t index) {
    return guest_ptr(ctx, G_PersonalityTable) + index * (gaddr)sizeof(PersonalityData);
}

static int32_t person_growth(Context *ctx, gaddr person, uint32_t stat) {
    return guest_s8(ctx, FIELD_ADDR(PersonData, person, growth) + stat);
}

static int32_t person_limit(Context *ctx, gaddr person, uint32_t stat) {
    return guest_s8(ctx, FIELD_ADDR(PersonData, person, limit_mod) + stat);
}

/* the C division the game does with "add the sign bit, shift right 1" */
static int32_t half_toward_zero(int32_t v) {
    return v / 2;
}

/* The boon and bane growth of the avatar's choices for one stat.
   Guest function: 0x0053AC20 unit::Edit::GetGrow(int) const. */
int32_t edit_grow(Context *ctx, gaddr edit, uint32_t stat) {
    gaddr boon = personality(ctx, READ_FIELD(ctx, UnitEdit, edit, boon));
    gaddr bane = personality(ctx, READ_FIELD(ctx, UnitEdit, edit, bane));
    return fe_add32(guest_s8(ctx, FIELD_ADDR(PersonalityData, boon, boon_growth) + stat),
                    guest_s8(ctx, FIELD_ADDR(PersonalityData, bane, bane_growth) + stat));
}

/* One parent's growth rate for a child: the parent's own growth plus its boon
   and bane growth; when both grandparent words are set, averaged with one
   grandparent's growth (grandparent_a when the Person named by the parent's
   family_index is female, else grandparent_b); never below 0. 0 when the
   parent is not set.
   Guest function: 0x0053B740 unit::Family::ParentSingle::GetGrow(int) const. */
int32_t family_parent_grow(Context *ctx, gaddr parent, uint32_t stat) {
    if (READ_FIELD(ctx, FamilyParent, parent, person) == 0)
        return 0;
    gaddr bane = personality(ctx, READ_FIELD(ctx, FamilyParent, parent, bane));
    gaddr person = READ_FIELD(ctx, FamilyParent, parent, person);
    gaddr boon = personality(ctx, READ_FIELD(ctx, FamilyParent, parent, boon));
    int32_t rate = fe_add32(fe_add32(guest_s8(ctx, FIELD_ADDR(PersonalityData, boon, boon_growth) + stat),
                                     person_growth(ctx, person, stat)),
                            guest_s8(ctx, FIELD_ADDR(PersonalityData, bane, bane_growth) + stat));
    if (READ_FIELD(ctx, FamilyParent, parent, grandparent_a) != 0 &&
        READ_FIELD(ctx, FamilyParent, parent, grandparent_b) != 0) {
        uint32_t family_index = READ_FIELD(ctx, PersonData, READ_FIELD(ctx, FamilyParent, parent, person), family_index);
        if (family_index != 0 && guest_call1(ctx, GROW_PersonGet, family_index) != 0) {
            /* the game reads the index again and looks the Person up a second time */
            uint32_t again = READ_FIELD(ctx, PersonData, READ_FIELD(ctx, FamilyParent, parent, person), family_index);
            gaddr fixed = again != 0 ? guest_call1(ctx, GROW_PersonGet, again) : 0;
            gaddr grand = guest_call1(ctx, GROW_PersonIsFemale, fixed) != 0
                              ? READ_FIELD(ctx, FamilyParent, parent, grandparent_a)
                              : READ_FIELD(ctx, FamilyParent, parent, grandparent_b);
            rate = half_toward_zero(fe_add32(person_growth(ctx, grand, stat), rate));
        }
    }
    return rate < 0 ? 0 : rate;
}

/* The parent's part of a child's growth rate: when both parent records are
   set and the child's Person names a fixed parent (family_index) that the game
   finds, the rate of the first parent record if that Person is female, else
   of the second; 0 otherwise.
   Guest function: 0x0053B6CC unit::Family::GetGrow(const Person*,int) const. */
int32_t family_grow(Context *ctx, gaddr family, gaddr person, uint32_t stat) {
    if (READ_FIELD(ctx, UnitFamily, family, link_00) == 0 || READ_FIELD(ctx, UnitFamily, family, link_14) == 0)
        return 0;
    uint32_t family_index = READ_FIELD(ctx, PersonData, person, family_index);
    if (family_index == 0 || guest_call1(ctx, GROW_PersonGet, family_index) == 0)
        return 0;
    uint32_t again = READ_FIELD(ctx, PersonData, person, family_index);
    gaddr fixed = again != 0 ? guest_call1(ctx, GROW_PersonGet, again) : 0;
    int female = guest_call1(ctx, GROW_PersonIsFemale, fixed) != 0;
    /* the game branches into ParentSingle::GetGrow (no call of its own): run in C */
    return family_parent_grow(ctx, family + (female ? 0u : (gaddr)sizeof(FamilyParent)), stat);
}

/* A unit's growth rate (percent) for one stat (0 hp .. 7 res).
   Guest function: 0x005330B4 Unit::GetGrow(int) const. */
int32_t unit_grow(Context *ctx, gaddr unit, uint32_t stat) {
    if (!fe_static_ready(ctx, S_GrowGuard))
        return (int32_t)fe_use_original(ctx);
    int32_t rate = person_growth(ctx, READ_FIELD(ctx, Unit, unit, person), stat);
    gaddr edit = READ_FIELD(ctx, Unit, unit, edit);
    if (edit != 0)
        rate = fe_add32(rate, (int32_t)guest_call2(ctx, GROW_EditGetGrow, edit, stat));
    gaddr family = READ_FIELD(ctx, Unit, unit, family);
    if (family != 0 && READ_FIELD(ctx, UnitFamily, family, link_00) != 0 &&
        READ_FIELD(ctx, UnitFamily, family, link_14) != 0) {
        uint32_t family_index = READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), family_index);
        if (family_index != 0 && guest_call1(ctx, GROW_PersonGet, family_index) != 0) {
            gaddr fam = READ_FIELD(ctx, Unit, unit, family);
            gaddr person = READ_FIELD(ctx, Unit, unit, person);
            int32_t parent = (int32_t)guest_call3(ctx, GROW_FamilyGetGrow, fam, person, stat);
            rate = half_toward_zero(fe_add32(parent, rate));
        }
    }
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    int32_t skill = guest_s16(ctx, S_GrowSkill);
    int player = READ_FIELD(ctx, PersonData, person, unit_kind) == 1;
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    rate = fe_add32(rate, guest_s8(ctx, (player ? FIELD_ADDR(JobData, job, growth) : FIELD_ADDR(JobData, job, enemy_growth))
                                            + stat));
    if (guest_call2(ctx, GROW_UnitIsEquipSkill, unit, (uint32_t)skill) != 0)
        rate = fe_add32(rate, 10);
    return rate;
}

/* The boon and bane limit change of the avatar's choices for one stat.
   Guest function: 0x0053AC54 unit::Edit::GetLimit(int) const. */
int32_t edit_limit(Context *ctx, gaddr edit, uint32_t stat) {
    gaddr boon = personality(ctx, READ_FIELD(ctx, UnitEdit, edit, boon));
    gaddr bane = personality(ctx, READ_FIELD(ctx, UnitEdit, edit, bane));
    return fe_add32(guest_s8(ctx, FIELD_ADDR(PersonalityData, boon, boon_limit) + stat),
                    guest_s8(ctx, FIELD_ADDR(PersonalityData, bane, bane_limit) + stat));
}

/* one parent record's limit terms: its Person's limit_mod + its boon and bane
   limit, + both grandparents' limit_mod when both are set */
static int32_t parent_limit(Context *ctx, gaddr parent, uint32_t stat) {
    gaddr bane = personality(ctx, READ_FIELD(ctx, FamilyParent, parent, bane));
    gaddr person = READ_FIELD(ctx, FamilyParent, parent, person);
    gaddr boon = personality(ctx, READ_FIELD(ctx, FamilyParent, parent, boon));
    int32_t v = fe_add32(fe_add32(guest_s8(ctx, FIELD_ADDR(PersonalityData, boon, boon_limit) + stat),
                                  person_limit(ctx, person, stat)),
                         guest_s8(ctx, FIELD_ADDR(PersonalityData, bane, bane_limit) + stat));
    gaddr ga = READ_FIELD(ctx, FamilyParent, parent, grandparent_a);
    if (ga != 0) {
        gaddr gb = READ_FIELD(ctx, FamilyParent, parent, grandparent_b);
        if (gb != 0)
            v = fe_add32(person_limit(ctx, gb, stat), fe_add32(person_limit(ctx, ga, stat), v));
    }
    return v;
}

/* A child's stat cap change: both parents' limit terms, + 1 for every stat but
   hp; 0 when either parent record is missing.
   Guest function: 0x0053BDC4 unit::Family::GetLimit(int) const. */
int32_t family_limit(Context *ctx, gaddr family, uint32_t stat) {
    if (READ_FIELD(ctx, UnitFamily, family, link_00) == 0 || READ_FIELD(ctx, UnitFamily, family, link_14) == 0)
        return 0;
    int32_t first = parent_limit(ctx, family, stat);
    int32_t second = 0;
    if (READ_FIELD(ctx, UnitFamily, family, link_14) != 0)  /* read again by the game */
        second = parent_limit(ctx, family + (gaddr)sizeof(FamilyParent), stat);
    int32_t v = fe_add32(second, first);
    return stat != 0 ? fe_add32(v, 1) : v;
}

/* A unit's stat cap for one stat, 0 .. 99.
   Guest function: 0x005337F0 Unit::GetLimit(int) const. */
int32_t unit_stat_limit(Context *ctx, gaddr unit, uint32_t stat) {
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    gaddr family = READ_FIELD(ctx, Unit, unit, family);
    int32_t cap = fe_add32(person_limit(ctx, person, stat), guest_s8(ctx, FIELD_ADDR(JobData, job, max) + stat));
    if (family != 0)
        cap = fe_add32(cap, (int32_t)guest_call2(ctx, GROW_FamilyGetLimit, family, stat));
    gaddr edit = READ_FIELD(ctx, Unit, unit, edit);
    if (edit != 0)
        cap = fe_add32(cap, (int32_t)guest_call2(ctx, GROW_EditGetLimit, edit, stat));
    cap = fe_add32(guest_s8(ctx, FIELD_ADDR(Unit, unit, limit_bonus) + stat), cap);
    if (cap < 0)
        return 0;
    return cap > 99 ? 99 : cap;
}

RECOMP_OVERRIDE(0x005330B4) {
    FE_ENTRY(0x005330B4, unit_grow, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0053AC20) {
    FE_ENTRY(0x0053AC20, edit_grow, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0053B6CC) {
    FE_ENTRY(0x0053B6CC, family_grow, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x0053B740) {
    FE_ENTRY(0x0053B740, family_parent_grow, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x005337F0) {
    FE_ENTRY(0x005337F0, unit_stat_limit, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0053AC54) {
    FE_ENTRY(0x0053AC54, edit_limit, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0053BDC4) {
    FE_ENTRY(0x0053BDC4, family_limit, FE_ARG(0), FE_ARG(1));
}
