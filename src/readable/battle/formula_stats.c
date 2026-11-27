/* The five stat getters the battle formulas use (Fates class Unit):
   strength, magic, skill, speed and luck. Plain-language description:
   docs/FORMULAS.md section 2 (and docs/TABLES.md "How a unit's stats are
   computed", which this code confirms).

   The game has one function per stat (Unit::GetStrImpl, GetPowImpl,
   GetTechImpl, GetQuickImpl, GetLuckImpl) with the same shape and different
   numbers; here they are one routine driven by a small table per stat
   (StatRule below). Every one of them:

     base   = Person.base[s] (+ the avatar's boon/bane) + Job.base[s] + Unit.gains[s]
              (- Unit.stat_loss[s] while state bit 30 is set)
     base   = 0 if negative, else at most Unit::GetLimit(s)
   and, when asked for the extras (the second bool; every battle formula asks):
     (strength and magic only: halved by one condition bit when the third bool is set)
     + the Guard Stance bonus of the partner behind the unit
     + equipped skills (+2 .. +4, one -1, or the amount a "stat absorb" skill took)
     + rallies and tonics (a condition bit, or the rally kind passed in the fifth argument)
     + the weapon's stat bonus (Item.stat_bonus[s])
     + carried-item bonuses (anonymous_namespace::GetEnhanceHave)
     (- Unit.debuff[s] when the third bool is set)
   and finally clamps to 0 .. 99.

   Each getter fills a few one-time caches (EquipSkill numbers found by name);
   the readable code gives up while any of them is cold. Guest calls left:
   Unit::GetLimit, unit::Edit::GetCapability, Unit::GetDoubleCapability,
   Unit::IsEquipSkill, GetEnhanceHave, unit::Item::ToData (readers; see
   formulas.h).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/battle/tests/formula_diff.py. */

#include "formulas.h"

/* a rally or tonic: the stat goes up by `add` when the fifth argument equals
   `kind` or the unit has bit `mask` of its condition byte `byte`; a tonic
   gives `tonic` more points (1, or 2 for luck) when the unit has the
   better-tonics skill */
typedef struct StatRally {
    int32_t kind;
    uint8_t byte;
    uint8_t mask;
    int8_t add;
    uint8_t tonic;   /* the better-tonics extra (0: not a tonic) */
} StatRally;

/* an equipped skill: + `add` (or, for an absorb skill, + Unit.absorbed[s]) */
typedef struct StatSkill {
    gaddr id;        /* the cached EquipSkill number (s16) */
    int8_t add;
    uint8_t absorb;
} StatSkill;

typedef struct StatRule {
    uint32_t stat;
    gaddr guards[5];
    unsigned nguards;
    uint8_t halve_mask;        /* strength / magic: Unit.conditions[0] bit that halves the stat (0: none) */
    StatSkill skills[4];
    unsigned nskills;
    StatRally rallies[6];
    unsigned nrallies;
    gaddr tonic_skill;         /* the better-tonics skill number (s16) */
    uint8_t mood_byte;         /* Unit.conditions[mood_byte]: bit mood_up +2, bit mood_down -1 */
    uint8_t mood_up, mood_down;
} StatRule;

/* Read in each getter on 2026-11-11 (addresses in the comments of formulas.h). */
static const StatRule RULE_STR = {
    STAT_STR, {S_StrGuard0, S_StrGuard1, S_StrGuard2, S_StrGuard3, 0}, 4, 0x40,
    {{S_StrSkillPlus2, 2, 0}, {S_StrSkillPlus3, 3, 0}, {S_StrSkillAbsorb, 0, 1}, {0, 0, 0}}, 3,
    {{23, 2, 0x80, 4, 0}, {31, 3, 0x80, 2, 0}, {32, 4, 0x01, 1, 0}, {9, 1, 0x02, 2, 1}, {16, 2, 0x01, 4, 0}, {0, 0, 0, 0, 0}}, 5,
    S_StrSkillTonic, 4, 0x10, 0x20};
static const StatRule RULE_MAG = {
    STAT_MAG, {S_MagGuard0, S_MagGuard1, S_MagGuard2, 0, 0}, 3, 0x80,
    {{S_MagSkillPlus2, 2, 0}, {S_MagSkillAbsorb, 0, 1}, {0, 0, 0}, {0, 0, 0}}, 2,
    {{24, 3, 0x01, 4, 0}, {31, 3, 0x80, 2, 0}, {10, 1, 0x04, 2, 1}, {17, 2, 0x02, 4, 0}, {0, 0, 0, 0, 0}, {0, 0, 0, 0, 0}}, 4,
    S_MagSkillTonic, 4, 0x40, 0x80};
static const StatRule RULE_SKL = {
    STAT_SKL, {S_SklGuard0, S_SklGuard1, S_SklGuard2, 0, 0}, 3, 0,
    {{S_SklSkillPlus2, 2, 0}, {S_SklSkillAbsorb, 0, 1}, {0, 0, 0}, {0, 0, 0}}, 2,
    {{25, 3, 0x02, 4, 0}, {31, 3, 0x80, 2, 0}, {33, 4, 0x02, 3, 0}, {11, 1, 0x08, 2, 1}, {18, 2, 0x04, 4, 0}, {0, 0, 0, 0, 0}}, 5,
    S_SklSkillTonic, 5, 0x01, 0x02};
static const StatRule RULE_SPD = {
    STAT_SPD, {S_SpdGuard0, S_SpdGuard1, S_SpdGuard2, S_SpdGuard3, S_SpdGuard4}, 5, 0,
    {{S_SpdSkillPlus2, 2, 0}, {S_SpdSkillPlus3, 3, 0}, {S_SpdSkillMinus1, -1, 0}, {S_SpdSkillAbsorb, 0, 1}}, 4,
    {{26, 3, 0x04, 4, 0}, {31, 3, 0x80, 2, 0}, {32, 4, 0x01, 1, 0}, {33, 4, 0x02, 3, 0}, {12, 1, 0x10, 2, 1}, {19, 2, 0x08, 4, 0}}, 6,
    S_SpdSkillTonic, 5, 0x04, 0x08};
static const StatRule RULE_LCK = {
    STAT_LCK, {S_LckGuard0, S_LckGuard1, S_LckGuard2, 0, 0}, 3, 0,
    {{S_LckSkillPlus4, 4, 0}, {S_LckSkillAbsorb, 0, 1}, {0, 0, 0}, {0, 0, 0}}, 2,
    {{27, 3, 0x08, 8, 0}, {31, 3, 0x80, 2, 0}, {33, 4, 0x02, 3, 0}, {13, 1, 0x20, 4, 2}, {20, 2, 0x10, 4, 0}, {0, 0, 0, 0, 0}}, 5,
    S_LckSkillTonic, 5, 0x10, 0x20};

/* The slot (0 .. 4) of the unit's equipped weapon: the first of its five items
   whose flag word has the equipped bit; -1 when none has.
   Guest function: 0x005310C0 Unit::GetItemIndexEquipped(void) const. */
int32_t unit_equipped_index(Context *ctx, gaddr unit) {
    for (int32_t slot = 0; slot < UNIT_ITEM_SLOTS; slot++) {
        uint16_t flags = guest_u16(ctx, FIELD_ADDR(Unit, unit, items) + (gaddr)slot * 4u + 2u);
        if (flags & UNIT_ITEM_EQUIPPED)
            return slot;
    }
    return -1;
}

static int unit_has_skill(Context *ctx, gaddr unit, gaddr id) {
    return guest_call2(ctx, GUEST_UnitIsEquipSkill, unit, (uint32_t)(int32_t)guest_s16(ctx, id)) != 0;
}

static uint8_t unit_condition(Context *ctx, gaddr unit, unsigned byte) {
    return guest_u8(ctx, FIELD_ADDR(Unit, unit, conditions) + byte);
}

static const StatRule *stat_rule(uint32_t stat) {
    switch (stat) {
    case STAT_STR: return &RULE_STR;
    case STAT_MAG: return &RULE_MAG;
    case STAT_SKL: return &RULE_SKL;
    case STAT_SPD: return &RULE_SPD;
    default: return &RULE_LCK;
    }
}

/* 1 when every one-time cache of that stat's getter is filled (reads only the
   guard words). The battle numbers ask this before reading anything, so that a
   cold cache makes them give up before any other read (tier 2 counts reads of
   unmapped memory, and a give-up replays the whole original). */
int unit_stat_caches_ready(Context *ctx, uint32_t stat) {
    const StatRule *rule = stat_rule(stat);
    for (unsigned i = 0; i < rule->nguards; i++)
        if (!fe_static_ready(ctx, rule->guards[i]))
            return 0;
    return 1;
}

/* One stat (STAT_STR .. STAT_LCK) of a unit, as the game's getter for that
   stat computes it. with_extras / with_loss are the getter's two bools (any
   non-zero word counts as set, as in the game's compare), kind its fifth
   argument (the rally kind; the battle formulas pass 0). */
int32_t unit_stat_value(Context *ctx, uint32_t stat, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss,
                        int32_t kind) {
    const StatRule *rule = stat_rule(stat);
    if (!unit_stat_caches_ready(ctx, stat))
        return (int32_t)fe_use_original(ctx);
    uint32_t s = rule->stat;

    /* the weapon whose stat bonus counts: the one given, else (with the extras) the equipped one */
    gaddr data = 0;
    if (item == 0 && with_extras) {
        int32_t slot = unit_equipped_index(ctx, unit);
        if (slot >= 0)
            item = FIELD_ADDR(Unit, unit, items) + (gaddr)slot * 4u;
    }
    if (item != 0)
        data = guest_call1(ctx, GUEST_ItemToData, item);

    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    int32_t value = guest_s8(ctx, FIELD_ADDR(PersonData, person, base) + s);
    int32_t limit = (int32_t)guest_call2(ctx, GUEST_UnitGetLimit, unit, s);
    gaddr edit = READ_FIELD(ctx, Unit, unit, edit);
    if (edit != 0)
        value = fe_add32(value, (int32_t)guest_call2(ctx, GUEST_EditGetCapability, edit, s));
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    uint32_t state = READ_FIELD(ctx, Unit, unit, state_flags);
    value = fe_add32(value, guest_s8(ctx, FIELD_ADDR(JobData, job, base) + s));
    value = fe_add32(value, guest_s8(ctx, FIELD_ADDR(Unit, unit, gains) + s));
    if (state & UNIT_STATE_STAT_LOSS)
        value = fe_add32(value, -guest_s8(ctx, FIELD_ADDR(Unit, unit, stat_loss) + s));
    if (value < 0)
        value = 0;
    else if (limit < value)
        value = limit;

    if (with_extras) {
        if (rule->halve_mask && with_loss && (unit_condition(ctx, unit, 0) & rule->halve_mask))
            value -= value / 2;
        /* the pair test reads the state word again as 64 bits, and the partner only
           when the bit is set: the same bytes as the game (tier 2 counts reads of
           unmapped memory) */
        uint32_t partner_bit = (state & UNIT_STATE_PAIR_SWAP) ? 4u : 2u;
        if ((guest_u64(ctx, FIELD_ADDR(Unit, unit, state_flags)) & partner_bit) != 0) {
            gaddr partner = READ_FIELD(ctx, Unit, unit, pair_partner);
            if (partner != 0)
                value = fe_add32(value, (int32_t)guest_call3(ctx, GUEST_UnitGetDoubleCapability, partner, s, unit));
        }
        for (unsigned i = 0; i < rule->nskills; i++) {
            const StatSkill *k = &rule->skills[i];
            if (!unit_has_skill(ctx, unit, k->id))
                continue;
            if (k->absorb)
                value = fe_add32(value, guest_s8(ctx, FIELD_ADDR(Unit, unit, absorbed) + s));
            else
                value = fe_add32(value, k->add);
        }
        for (unsigned i = 0; i < rule->nrallies; i++) {
            const StatRally *r = &rule->rallies[i];
            if (kind != r->kind && !(unit_condition(ctx, unit, r->byte) & r->mask))
                continue;
            value = fe_add32(value, r->add);
            if (r->tonic && unit_has_skill(ctx, unit, rule->tonic_skill))
                value = fe_add32(value, r->tonic);
        }
        uint8_t mood = unit_condition(ctx, unit, rule->mood_byte);
        if (mood & rule->mood_up)
            value = fe_add32(value, 2);
        if (mood & rule->mood_down)
            value = fe_add32(value, -1);
        if (data != 0)
            value = fe_add32(value, guest_s8(ctx, FIELD_ADDR(ItemData, data, stat_bonus) + s));
        value = fe_add32(value, (int32_t)guest_call2(ctx, GUEST_GetEnhanceHave, unit, s));
        if (with_loss)
            value = fe_add32(value, -guest_s8(ctx, FIELD_ADDR(Unit, unit, debuff) + s));
    }
    if (value < 0)
        return 0;
    return value > STAT_CAP ? STAT_CAP : value;
}

/* The fifth argument (the rally kind) is the word at sp.
   Guest function: 0x0052A80C Unit::GetStrImpl(const unit::Item*,bool,bool,unit::detail::EnhanceDefinition::Type) const. */
int32_t unit_strength(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp) {
    return unit_stat_value(ctx, STAT_STR, unit, item, with_extras, with_loss, guest_s32(ctx, sp));
}

/* Guest function: 0x0052A500 Unit::GetPowImpl(const unit::Item*,bool,bool,unit::detail::EnhanceDefinition::Type) const. */
int32_t unit_magic(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp) {
    return unit_stat_value(ctx, STAT_MAG, unit, item, with_extras, with_loss, guest_s32(ctx, sp));
}

/* Guest function: 0x0052C30C Unit::GetTechImpl(const unit::Item*,bool,bool,unit::detail::EnhanceDefinition::Type) const. */
int32_t unit_skill(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp) {
    return unit_stat_value(ctx, STAT_SKL, unit, item, with_extras, with_loss, guest_s32(ctx, sp));
}

/* Guest function: 0x0052D860 Unit::GetQuickImpl(const unit::Item*,bool,bool,unit::detail::EnhanceDefinition::Type) const. */
int32_t unit_speed(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp) {
    return unit_stat_value(ctx, STAT_SPD, unit, item, with_extras, with_loss, guest_s32(ctx, sp));
}

/* Guest function: 0x0052BC5C Unit::GetLuckImpl(const unit::Item*,bool,bool,unit::detail::EnhanceDefinition::Type) const. */
int32_t unit_luck(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp) {
    return unit_stat_value(ctx, STAT_LCK, unit, item, with_extras, with_loss, guest_s32(ctx, sp));
}

/* The getters take a fifth argument on the guest stack (the rally kind, the
   word at sp when they are called): the readable functions get sp and read it. */
#define STAT_ARGS FE_ARG(0), FE_ARG(1), FE_ARG(2), FE_ARG(3), FE_ARG(13)

RECOMP_OVERRIDE(0x005310C0) {
    FE_ENTRY(0x005310C0, unit_equipped_index, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052A80C) {
    FE_ENTRY(0x0052A80C, unit_strength, STAT_ARGS);
}

RECOMP_OVERRIDE(0x0052A500) {
    FE_ENTRY(0x0052A500, unit_magic, STAT_ARGS);
}

RECOMP_OVERRIDE(0x0052C30C) {
    FE_ENTRY(0x0052C30C, unit_skill, STAT_ARGS);
}

RECOMP_OVERRIDE(0x0052D860) {
    FE_ENTRY(0x0052D860, unit_speed, STAT_ARGS);
}

RECOMP_OVERRIDE(0x0052BC5C) {
    FE_ENTRY(0x0052BC5C, unit_luck, STAT_ARGS);
}
