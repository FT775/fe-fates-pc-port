/* The rest of the unit's stats (Fates class Unit): defence, resistance,
   maximum HP and move, plus the two numbers of the map's HP window.
   Plain-language description: docs/SHEET.md sections 1 and 2.

   Defence and resistance have the same shape as the five stats of
   src/readable/battle/formula_stats.c (Unit::GetDefImpl / GetMdefImpl):

     base   = Person.base[s] (+ the avatar's boon/bane) + Job.base[s] + Unit.gains[s]
              (- Unit.stat_loss[s] while state bit 30 is set)
     base   = 0 if negative, else at most Unit::GetLimit(s)
   and, when asked for the extras (the second bool):
     + the Guard Stance bonus of the partner behind the unit
     + equipped skills (+2, one -1, or the amount a "stat absorb" skill took)
     + rallies and tonics (a condition bit, or the rally kind passed in the fifth argument)
     + a mood bit +2, another -1
     + the weapon's stat bonus (Item.stat_bonus[s]) and carried-item bonuses
     (- Unit.debuff[s] when the third bool is set)
   and finally clamps to 0 .. 99.

   This file has its own small copy of that rule table (one per stat) and does
   not call the battle batch's C code: a guest call reaches each callee the
   game calls, in the game's order (docs/DECISIONS.md F-018).

   Maximum HP (Unit::GetMHPImpl) is simpler: no weapon, no partner, no
   carried items, no debuff; a condition bit halves it, HP+5 adds 5, the HP
   tonic 5 (7 with the better-tonics skill). Move (Unit::GetMovePower) is the
   class move plus a per-unit bonus minus a per-unit loss, and with the extras
   a rally, the partner's class pair-up move, two skills, two condition bits
   that add or take half the class move (by whether the unit flies) and one
   that makes it 0.

   Each getter fills a few one-time caches (EquipSkill numbers found by name);
   the readable code gives up while any of them is cold, before reading
   anything else.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/sheet/tests/sheet_diff.py. */

#include "sheet.h"

/* a rally or tonic: + `add` when the fifth argument equals `kind` or the unit
   has bit `mask` of its condition byte `byte`; a tonic gives `tonic` more with
   the better-tonics skill */
typedef struct SheetRally {
    int32_t kind;
    uint8_t byte;
    uint8_t mask;
    int8_t add;
    uint8_t tonic;
} SheetRally;

typedef struct SheetSkill {
    gaddr id;        /* the cached EquipSkill number (s16) */
    int8_t add;
    uint8_t absorb;  /* 1: + Unit.absorbed[s] instead of add */
} SheetSkill;

typedef struct SheetRule {
    uint32_t stat;
    gaddr guards[4];
    unsigned nguards;
    SheetSkill skills[3];
    unsigned nskills;
    SheetRally rallies[4];
    unsigned nrallies;
    gaddr tonic_skill;
    uint8_t mood_byte;       /* Unit.conditions[mood_byte]: bit mood_up +2, bit mood_down -1 */
    uint8_t mood_up, mood_down;
} SheetRule;

/* Read in each getter on 2026-11-13. */
static const SheetRule RULE_DEF = {
    SHEET_STAT_DEF, {S_DefGuard0, S_DefGuard1, S_DefGuard2, S_DefGuard3}, 4,
    {{S_DefSkillPlus2, 2, 0}, {S_DefSkillMinus1, -1, 0}, {S_DefSkillAbsorb, 0, 1}}, 3,
    {{28, 3, 0x10, 4, 0}, {31, 3, 0x80, 2, 0}, {14, 1, 0x40, 2, 1}, {21, 2, 0x20, 4, 0}}, 4,
    S_DefSkillTonic, 5, 0x40, 0x80};
static const SheetRule RULE_RES = {
    SHEET_STAT_RES, {S_ResGuard0, S_ResGuard1, S_ResGuard2, 0}, 3,
    {{S_ResSkillPlus2, 2, 0}, {S_ResSkillAbsorb, 0, 1}, {0, 0, 0}}, 2,
    {{29, 3, 0x20, 4, 0}, {31, 3, 0x80, 2, 0}, {15, 1, 0x80, 2, 1}, {22, 2, 0x40, 4, 0}}, 4,
    S_ResSkillTonic, 6, 0x01, 0x02};

static int has_skill(Context *ctx, gaddr unit, gaddr id) {
    return guest_call2(ctx, SHEET_UnitIsEquipSkill, unit, (uint32_t)(int32_t)guest_s16(ctx, id)) != 0;
}

static uint8_t condition(Context *ctx, gaddr unit, unsigned byte) {
    return guest_u8(ctx, FIELD_ADDR(Unit, unit, conditions) + byte);
}

/* the base part shared by defence, resistance and HP: Person + boon/bane +
   Job + gains (- loss), clamped to 0 .. the cap; *state_out gets the state
   word it read (the game tests the pair bits in that same copy) */
static int32_t base_stat(Context *ctx, gaddr unit, uint32_t s, uint32_t *state_out) {
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    int32_t value = guest_s8(ctx, FIELD_ADDR(PersonData, person, base) + s);
    int32_t limit = (int32_t)guest_call2(ctx, SHEET_UnitGetLimit, unit, s);
    gaddr edit = READ_FIELD(ctx, Unit, unit, edit);
    if (edit != 0)
        value = fe_add32(value, (int32_t)guest_call2(ctx, SHEET_EditGetCapability, edit, s));
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    uint32_t state = READ_FIELD(ctx, Unit, unit, state_flags);
    *state_out = state;
    value = fe_add32(value, guest_s8(ctx, FIELD_ADDR(JobData, job, base) + s));
    value = fe_add32(value, guest_s8(ctx, FIELD_ADDR(Unit, unit, gains) + s));
    if (state & UNIT_STATE_LOSS)
        value = fe_add32(value, -guest_s8(ctx, FIELD_ADDR(Unit, unit, stat_loss) + s));
    if (value < 0)
        return 0;
    return limit < value ? limit : value;
}

/* the pair test: picks the partner bit from the state word already read,
   reads the word again as 64 bits, and the partner only when the bit is set
   (the same bytes as the game) */
static gaddr pair_partner(Context *ctx, gaddr unit, uint32_t state) {
    uint32_t bit = (state & UNIT_STATE_SWAP_PARTNER_BIT) ? 4u : 2u;
    if ((guest_u64(ctx, FIELD_ADDR(Unit, unit, state_flags)) & bit) == 0)
        return 0;
    return READ_FIELD(ctx, Unit, unit, pair_partner);
}

static int32_t clamp_stat(int32_t value) {
    if (value < 0)
        return 0;
    return value > SHEET_STAT_CAP ? SHEET_STAT_CAP : value;
}

/* defence or resistance, as Unit::GetDefImpl / GetMdefImpl compute it */
static int32_t guard_stat(Context *ctx, const SheetRule *rule, gaddr unit, gaddr item, uint32_t with_extras,
                          uint32_t with_loss, int32_t kind) {
    for (unsigned i = 0; i < rule->nguards; i++)
        if (!fe_static_ready(ctx, rule->guards[i]))
            return (int32_t)fe_use_original(ctx);
    uint32_t s = rule->stat;

    /* the weapon whose stat bonus counts: the one given, else (with the extras) the equipped one */
    if (item == 0 && with_extras) {
        int32_t slot = (int32_t)guest_call1(ctx, SHEET_UnitGetItemIndexEquipped, unit);
        if (slot >= 0)
            item = FIELD_ADDR(Unit, unit, items) + (gaddr)slot * 4u;
    }
    gaddr data = item != 0 ? guest_call1(ctx, SHEET_ItemToData, item) : 0;

    uint32_t state = 0;
    int32_t value = base_stat(ctx, unit, s, &state);
    if (!with_extras)
        return clamp_stat(value);

    gaddr partner = pair_partner(ctx, unit, state);
    if (partner != 0)
        value = fe_add32(value, (int32_t)guest_call3(ctx, SHEET_UnitGetDoubleCapability, partner, s, unit));
    for (unsigned i = 0; i < rule->nskills; i++) {
        const SheetSkill *k = &rule->skills[i];
        if (!has_skill(ctx, unit, k->id))
            continue;
        if (k->absorb)
            value = fe_add32(value, guest_s8(ctx, FIELD_ADDR(Unit, unit, absorbed) + s));
        else
            value = fe_add32(value, k->add);
    }
    for (unsigned i = 0; i < rule->nrallies; i++) {
        const SheetRally *r = &rule->rallies[i];
        if (kind != r->kind && !(condition(ctx, unit, r->byte) & r->mask))
            continue;
        value = fe_add32(value, r->add);
        if (r->tonic && has_skill(ctx, unit, rule->tonic_skill))
            value = fe_add32(value, r->tonic);
    }
    uint8_t mood = condition(ctx, unit, rule->mood_byte);
    if (mood & rule->mood_up)
        value = fe_add32(value, 2);
    if (mood & rule->mood_down)
        value = fe_add32(value, -1);
    if (data != 0)
        value = fe_add32(value, guest_s8(ctx, FIELD_ADDR(ItemData, data, stat_bonus) + s));
    value = fe_add32(value, (int32_t)guest_call2(ctx, SHEET_GetEnhanceHave, unit, s));
    if (with_loss)
        value = fe_add32(value, -guest_s8(ctx, FIELD_ADDR(Unit, unit, debuff) + s));
    return clamp_stat(value);
}

/* The fifth argument (the rally kind) is the word at sp.
   Guest function: 0x0052A000 Unit::GetDefImpl(const unit::Item*,bool,bool,unit::detail::EnhanceDefinition::Type) const. */
int32_t unit_defense(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp) {
    return guard_stat(ctx, &RULE_DEF, unit, item, with_extras, with_loss, guest_s32(ctx, sp));
}

/* Guest function: 0x0052BF6C Unit::GetMdefImpl(const unit::Item*,bool,bool,unit::detail::EnhanceDefinition::Type) const. */
int32_t unit_resistance(Context *ctx, gaddr unit, gaddr item, uint32_t with_extras, uint32_t with_loss, gaddr sp) {
    return guard_stat(ctx, &RULE_RES, unit, item, with_extras, with_loss, guest_s32(ctx, sp));
}

/* Maximum HP. The third argument (the debuff bool of the other getters) is
   not read; the fourth is the rally kind (8 = the HP tonic).
   Guest function: 0x0052A364 Unit::GetMHPImpl(bool,bool,unit::detail::EnhanceDefinition::Type) const. */
int32_t unit_max_hp(Context *ctx, gaddr unit, uint32_t with_extras, uint32_t unused, int32_t kind) {
    (void)unused;
    if (!fe_static_ready(ctx, S_HpGuard0) || !fe_static_ready(ctx, S_HpGuard1))
        return (int32_t)fe_use_original(ctx);
    uint32_t state = 0;
    int32_t value = base_stat(ctx, unit, SHEET_STAT_HP, &state);
    if (with_extras) {
        if (condition(ctx, unit, 0) & 0x20u)
            value -= value / 2;  /* halved, rounded toward zero, as the game does */
        if (has_skill(ctx, unit, S_HpSkillPlus5))
            value = fe_add32(value, 5);
        if (kind == 8 || (condition(ctx, unit, 1) & 0x01u)) {
            value = fe_add32(value, 5);
            if (has_skill(ctx, unit, S_HpSkillTonic))
                value = fe_add32(value, 2);
        }
        uint8_t mood = condition(ctx, unit, 4);
        if (mood & 0x04u)
            value = fe_add32(value, 2);
        if (mood & 0x08u)
            value = fe_add32(value, -1);
    }
    return clamp_stat(value);
}

/* The map HP window's maximum: the window's unit, with the extras, no rally
   kind. The game's code falls through into GetMHPImpl (no call), so this
   calls the C function, not the guest.
   Guest function: 0x0052A350 map::anonymous_namespace::HpWindowUnit::GetMaxHp(void). */
int32_t hp_window_max_hp(Context *ctx, gaddr window) {
    /* the caches of GetMHPImpl asked before the window is read: a give-up
       reads nothing (the original then reads the window itself) */
    if (!fe_static_ready(ctx, S_HpGuard0) || !fe_static_ready(ctx, S_HpGuard1))
        return (int32_t)fe_use_original(ctx);
    gaddr unit = guest_ptr(ctx, window + HPWINDOW_UNIT);
    return unit_max_hp(ctx, unit, 1u, 0u, 0);
}

/* The map HP window's current HP: the unit's HP byte.
   Guest function: 0x00373954 map::anonymous_namespace::HpWindowUnit::GetHp(void). */
int32_t hp_window_hp(Context *ctx, gaddr window) {
    gaddr unit = guest_ptr(ctx, window + HPWINDOW_UNIT);
    return guest_s8(ctx, unit + UNIT_HP);
}

/* half the class move, added or taken off by a condition bit, by whether the
   unit is in the flying category */
static int32_t half_move_for_flyers(Context *ctx, gaddr unit, int32_t value, int flyer_gains) {
    uint32_t mask = guest_u16(ctx, S_MoveFlyerMask);
    uint32_t category = guest_call1(ctx, SHEET_UnitGetCategory, unit);
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    int32_t half = (int32_t)(READ_FIELD(ctx, JobData, job, mov) >> 1);
    int flies = (category & mask) != 0;
    return fe_add32(value, flies == flyer_gains ? half : -half);
}

/* Move. kind is the rally kind (30 = the move rally).
   Guest function: 0x0052D5E4 Unit::GetMovePower(bool,unit::detail::EnhanceDefinition::Type) const. */
int32_t unit_move(Context *ctx, gaddr unit, uint32_t with_extras, int32_t kind) {
    if (!fe_static_ready(ctx, S_MoveGuard0) || !fe_static_ready(ctx, S_MoveGuard1) ||
        !fe_static_ready(ctx, S_MoveGuard2))
        return (int32_t)fe_use_original(ctx);
    /* with the extras the game also asks one more cache in the middle and calls
       GetCategory, whose override asks its own five: asked here first, so
       neither gives up after a guest call */
    if (with_extras && (!fe_static_ready(ctx, S_MoveGuard3) || !fe_static_ready(ctx, S_CatGuard0) ||
                        !fe_static_ready(ctx, S_CatGuard1) || !fe_static_ready(ctx, S_CatGuard2) ||
                        !fe_static_ready(ctx, S_CatGuard3) || !fe_static_ready(ctx, S_CatGuard4)))
        return (int32_t)fe_use_original(ctx);

    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    uint32_t state = READ_FIELD(ctx, Unit, unit, state_flags);
    int32_t value = READ_FIELD(ctx, JobData, job, mov);
    if (!(state & UNIT_STATE_LOSS))
        value += guest_s8(ctx, unit + UNIT_MOVE_BONUS);
    int32_t loss = guest_s8(ctx, unit + UNIT_MOVE_LOSS);
    value = fe_add32(value, -(loss < 0 ? 0 : loss));
    if (!with_extras)
        return value < 0 ? 0 : value;

    if (kind == 30 || (condition(ctx, unit, 3) & 0x40u))
        value = fe_add32(value, 1);
    gaddr partner = pair_partner(ctx, unit, state);
    if (partner != 0) {
        gaddr partner_job = READ_FIELD(ctx, Unit, partner, job);
        value = fe_add32(value, guest_s8(ctx, FIELD_ADDR(JobData, partner_job, pair_up)));
    }
    if (has_skill(ctx, unit, S_MoveSkillPlus1))
        value = fe_add32(value, 1);
    uint32_t shooter = guest_u16(ctx, S_MoveShooterMask);
    if ((guest_call1(ctx, SHEET_UnitGetCategory, unit) & shooter) != 0 && has_skill(ctx, unit, S_MoveSkillShooter))
        value = fe_add32(value, 1);
    if (condition(ctx, unit, 6) & 0x04u)
        value = half_move_for_flyers(ctx, unit, value, 1);
    if (condition(ctx, unit, 6) & 0x08u)
        value = half_move_for_flyers(ctx, unit, value, 0);
    if (condition(ctx, unit, 0) & 0x02u)
        return 0;
    return value < 0 ? 0 : value;
}

/* The getters of defence and resistance take a fifth argument on the guest
   stack (the rally kind, the word at sp when they are called). */
#define GUARD_ARGS FE_ARG(0), FE_ARG(1), FE_ARG(2), FE_ARG(3), FE_ARG(13)

RECOMP_OVERRIDE(0x0052A000) {
    FE_ENTRY(0x0052A000, unit_defense, GUARD_ARGS);
}

RECOMP_OVERRIDE(0x0052BF6C) {
    FE_ENTRY(0x0052BF6C, unit_resistance, GUARD_ARGS);
}

RECOMP_OVERRIDE(0x0052A364) {
    FE_ENTRY(0x0052A364, unit_max_hp, FE_ARG(0), FE_ARG(1), FE_ARG(2), FE_ARG_S(3));
}

RECOMP_OVERRIDE(0x0052A350) {
    FE_ENTRY(0x0052A350, hp_window_max_hp, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00373954) {
    FE_ENTRY(0x00373954, hp_window_hp, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052D5E4) {
    FE_ENTRY(0x0052D5E4, unit_move, FE_ARG(0), FE_ARG(1), FE_ARG_S(2));
}
