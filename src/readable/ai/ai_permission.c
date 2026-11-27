/* Who the AI may attack, heal or leave idle: the yes/no questions of the
   enemy phase (Fates class AIThink).

   Every function here only reads: it stores nothing in game memory (the
   one-time caches it needs are only read, and it gives up while one is
   empty). Plain-language description: docs/AI.md sections 2 and 3.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   game's ARM code: src/readable/ai/tests/ai_perm_diff.py. */

#include "ai_perm.h"

/* May `unit` attack `target`? Never a target with state bit 2; always when
   there is no attacker; otherwise not when Unit::IsDontAttack says so (with
   the caller's bool, passed on as it came).
   Guest function: 0x004CF624 AIThink::IsAttackPermission(Unit*,Unit*,bool). */
uint32_t ai_attack_permission(Context *ctx, gaddr unit, gaddr target, uint32_t ignore_state) {
    if (READ_FIELD(ctx, Unit, target, state_flags) & UNIT_STATE_GONE)
        return 0;
    if (unit == 0)
        return 1;
    return guest_call3(ctx, AI_UnitIsDontAttack, unit, target, ignore_state) != 0 ? 0u : 1u;
}

/* The same for the unit this AI thinks for (AIThink +0, read even when the
   target is refused).
   Guest function: 0x004CF658 AIThink::IsAttackPermission(Unit*,bool). */
uint32_t ai_attack_permission_self(Context *ctx, gaddr think, gaddr target, uint32_t ignore_state) {
    uint32_t state = READ_FIELD(ctx, Unit, target, state_flags);
    gaddr unit = guest_ptr(ctx, think + AITHINK_UNIT);
    if (state & UNIT_STATE_GONE)
        return 0;
    if (unit == 0)
        return 1;
    return guest_call3(ctx, AI_UnitIsDontAttack, unit, target, ignore_state) != 0 ? 0u : 1u;
}

/* May the AI heal `target` with a rod? Not with state bit 2; otherwise when
   either of the AI bits 20-21 is set.
   Guest function: 0x004D0ADC AIThink::IsHealRodPermission(Unit*). */
uint32_t ai_heal_rod_permission(Context *ctx, gaddr think, gaddr target) {
    (void)think;
    if (READ_FIELD(ctx, Unit, target, state_flags) & UNIT_STATE_GONE)
        return 0;
    return (guest_u32(ctx, target + UNIT_AI_FLAGS) & UNIT_AI_ROD_BITS) != 0 ? 1u : 0u;
}

/* "Clever" AI: the map situation's force byte (+8) is not 1.
   Guest function: 0x004D61E4 AIThink::IsClever(void). */
uint32_t ai_is_clever(Context *ctx) {
    return READ_FIELD(ctx, Situation, guest_ptr(ctx, G_Situation), force_index) != 1 ? 1u : 0u;
}

/* The AI sequence state's signed byte +0x150 (holder -> +0x10 -> +0x150), as
   the game returns it (sign-extended).
   Guest function: 0x004D0AC0 AIThink::IsAllowIdleMutation(void). */
int32_t ai_allow_idle_mutation(Context *ctx) {
    gaddr root = guest_ptr(ctx, G_AIThinkHolder);
    gaddr state = READ_FIELD(ctx, AIThinkRoot, root, state);
    return guest_s8(ctx, state + AISTATE_IDLE_MUTATION);
}

/* Is this AI command active for the unit? By the command's signed condition
   byte: -1 always; -2 only while the unit's AI group byte is 0; 0 only while
   it is not 0; any other value only when it equals the group byte.
   Guest function: 0x004CB280 AIThink::IsActiveCommand(Unit*,AICommand*). */
uint32_t ai_command_is_active(Context *ctx, gaddr unit, gaddr command) {
    int32_t condition = guest_s8(ctx, command + AICMD_CONDITION);
    if (condition == -2)
        return guest_u8(ctx, unit + UNIT_AI_BAND) == 0 ? 1u : 0u;
    if (condition == -1)
        return 1;
    int32_t band = guest_u8(ctx, unit + UNIT_AI_BAND);
    if (condition == 0)
        return band != 0 ? 1u : 0u;
    return condition == band ? 1u : 0u;
}

/* The move-range flags an AI unit may ignore: 0x200 when AI bit 13 is set and
   the unit can open doors (Unit::CanKeyDoor), 0x400 with AI bit 15,
   0x1000000 with AI bit 16. The AI word is read again after the call.
   Guest function: 0x004D24D4 AIThink::GetDeployFreeMoveFlag(const Unit*). */
uint32_t ai_deploy_free_move_flag(Context *ctx, gaddr unit) {
    uint32_t flags = 0;
    if ((guest_u32(ctx, unit + UNIT_AI_FLAGS) & UNIT_AI_DOORS) && guest_call1(ctx, AI_UnitCanKeyDoor, unit) != 0)
        flags = 0x200u;
    uint32_t ai = guest_u32(ctx, unit + UNIT_AI_FLAGS);
    if (ai & UNIT_AI_FREE_A)
        flags |= 0x400u;
    if (ai & UNIT_AI_FREE_B)
        flags |= 0x1000000u;
    return flags;
}

/* The move the AI plans with for a slow approach: the unit's move (with the
   extras) minus 1 on difficulty 1, unchanged on difficulty 2, minus 2 on any
   other. On difficulty 2 the game ends with a plain branch into
   Unit::GetMovePower, which 3dsrecomp keeps inside this function: the
   readable code runs unit_move directly there (no guest call).
   Guest function: 0x004CC818 AIThink::GetMovePowerSlow(void). */
int32_t ai_move_power_slow(Context *ctx, gaddr think) {
    /* unit_move's caches (with the extras: all of them, and GetCategory's) */
    if (!fe_static_ready(ctx, S_MoveGuard0) || !fe_static_ready(ctx, S_MoveGuard1) ||
        !fe_static_ready(ctx, S_MoveGuard2) || !fe_static_ready(ctx, S_MoveGuard3) ||
        !fe_static_ready(ctx, S_CatGuard0) || !fe_static_ready(ctx, S_CatGuard1) ||
        !fe_static_ready(ctx, S_CatGuard2) || !fe_static_ready(ctx, S_CatGuard3) ||
        !fe_static_ready(ctx, S_CatGuard4))
        return (int32_t)fe_use_original(ctx);
    gaddr data = guest_call(ctx, AI_GameUserDataGet, 0u, 0u, 0u, 0u);
    uint32_t difficulty = READ_FIELD(ctx, GameUserData, data, difficulty);
    gaddr unit = guest_ptr(ctx, think + AITHINK_UNIT);
    if (difficulty == 1)
        return fe_add32((int32_t)guest_call3(ctx, AI_UnitGetMovePower, unit, 1u, 0u), -1);
    if (difficulty == 2)
        return unit_move(ctx, unit, 1u, 0);
    return fe_add32((int32_t)guest_call3(ctx, AI_UnitGetMovePower, unit, 1u, 0u), -2);
}

/* Does an entrusted unit want healing? Its HP is below its maximum HP (with
   the extras) and HP x 100 / max HP (toward zero; 0 when the maximum is 0) is
   below 75 for a unit of force 0, or below the unit's own byte +0x5D for any
   other force.
   Guest function: 0x004D4054 AIThink::IsHealConditionForEntrust(Unit*). */
uint32_t ai_heal_condition_for_entrust(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, S_HpGuard0) || !fe_static_ready(ctx, S_HpGuard1))
        return fe_use_original(ctx);
    int32_t hp = guest_s8(ctx, unit + UNIT_HP);
    int32_t max_hp = (int32_t)guest_call(ctx, AI_UnitGetMHP, unit, 1u, 0u, 0u);
    if (hp >= max_hp)
        return 0;
    int32_t percent = ai_div(hp * 100, max_hp);
    gaddr force = READ_FIELD(ctx, Unit, unit, force);
    int32_t limit = guest_u8(ctx, unit + UNIT_AI_HEAL_PERCENT);
    if (READ_FIELD(ctx, Force, force, type) == 0)
        limit = AI_HEAL_PERCENT_PLAYER;
    return percent < limit ? 1u : 0u;
}

/* Does an attack command with this code allow `unit` as its target? Codes 3
   to 9 test the unit against the command's first value; every other code
   allows it. 3: the unit, its Person or its class has the cached PersonFlag
   bit; 4: the value names the unit's Person; 5: it does not; 6: the unit's
   byte +0x5A is not the value; 7 and 8: the value names the unit's class;
   9: the value is the unit's force type. The second value is not used.
   Guest function: 0x004D4770 AIThink::IsAttackPermissionOnlyCommand(int,AIValue*,AIValue*,Unit*). */
uint32_t ai_attack_permission_for_command(Context *ctx, int32_t code, gaddr value1, gaddr value2, gaddr unit) {
    (void)value2;
    if (!fe_static_ready(ctx, S_AiOnlyGuard))
        return fe_use_original(ctx);
    switch (code) {
    case 3: {
        uint64_t mask = guest_u64(ctx, S_AiOnlyMask);
        uint64_t flags = READ_FIELD(ctx, Unit, unit, private_flags) |
                         guest_u64(ctx, READ_FIELD(ctx, Unit, unit, person)) |
                         guest_u64(ctx, READ_FIELD(ctx, Unit, unit, job));
        return (mask & flags) != 0 ? 1u : 0u;
    }
    case 4:
        return guest_call1(ctx, AI_ValueGetPerson, value1) == READ_FIELD(ctx, Unit, unit, person) ? 1u : 0u;
    case 5:
        return guest_call1(ctx, AI_ValueGetPerson, value1) == READ_FIELD(ctx, Unit, unit, person) ? 0u : 1u;
    case 6:
        return (int32_t)guest_u8(ctx, unit + UNIT_AI_KEY) == guest_s16(ctx, value1) ? 0u : 1u;
    case 7:
    case 8:
        return guest_call1(ctx, AI_ValueGetJob, value1) == READ_FIELD(ctx, Unit, unit, job) ? 1u : 0u;
    case 9:
        return (int32_t)READ_FIELD(ctx, Force, READ_FIELD(ctx, Unit, unit, force), type) == guest_s16(ctx, value1)
                   ? 1u : 0u;
    default:
        return 1;
    }
}

/* The first command of the unit's AI sequence for an order type (array per
   type, then the unit's sequence index byte for that type). */
static gaddr first_command(Context *ctx, uint32_t order, gaddr unit) {
    gaddr sequences = guest_ptr(ctx, G_AICommandTable + order * 4u);
    uint32_t index = guest_u8(ctx, unit + order + UNIT_AI_SEQUENCE);
    return guest_ptr(ctx, sequences + index * 4u) + AISEQUENCE_FIRST;
}

/* A command's two values, each replaced by the unit's AI argument it names
   (with order type 2, whatever the sequence's own type); 1 when neither is
   "skip". */
static int values_usable(Context *ctx, gaddr command, gaddr unit, gaddr *value1, gaddr *value2) {
    gaddr v1 = command + AICMD_VALUE1;
    gaddr v2 = command + AICMD_VALUE2;
    if (guest_call1(ctx, AI_ValueIsArgument, v1) != 0)
        v1 = guest_call3(ctx, AI_ValueGetArgument, v1, AI_ORDER_ATTACK, unit);
    if (guest_call1(ctx, AI_ValueIsArgument, v2) != 0)
        v2 = guest_call3(ctx, AI_ValueGetArgument, v2, AI_ORDER_ATTACK, unit);
    *value1 = v1;
    *value2 = v2;
    if (guest_call1(ctx, AI_ValueIsSkip, v1) != 0)
        return 0;
    return guest_call1(ctx, AI_ValueIsSkip, v2) == 0;
}

/* Has the unit an active attack command (kind 3) in its sequence for this
   order type? Code 0x51 never counts; codes 40 and 41 only with AI bit 21;
   a command whose value is "skip" does not count. The sequence ends at a
   command of kind 0.
   Guest function: 0x004CC870 AIThink::HasActiveCommand(AIValue::Order::Type,Unit*). */
uint32_t ai_has_active_command(Context *ctx, uint32_t order, gaddr unit) {
    for (gaddr command = first_command(ctx, order, unit);; command += AICOMMAND_SIZE) {
        if (guest_u8(ctx, command + AICMD_KIND) == 0)
            return 0;
        if (guest_call2(ctx, AI_IsActiveCommand, unit, command) == 0)
            continue;
        if (guest_u8(ctx, command + AICMD_KIND) != 3)
            continue;
        uint32_t code = guest_u8(ctx, command + AICMD_CODE);
        if (code == 0x51)
            continue;
        if ((code == 40 || code == 41) && !(guest_u32(ctx, unit + UNIT_AI_FLAGS) & UNIT_AI_CROSSFIRE_BIT))
            continue;
        gaddr v1, v2;
        if (values_usable(ctx, command, unit, &v1, &v2))
            return 1;
    }
}

/* Has the unit an active attack command (kind 3, code below 12) in its
   sequence for order type 2 that allows `target`
   (AIThink::IsAttackPermissionOnlyCommand)? Used for joint attacks.
   Guest function: 0x004D48BC AIThink::HasActiveAttackCommandForCrossfire(Unit*,Unit*). */
uint32_t ai_has_crossfire_command(Context *ctx, gaddr unit, gaddr target) {
    if (!fe_static_ready(ctx, S_AiOnlyGuard)) /* the cache of the override it calls */
        return fe_use_original(ctx);
    for (gaddr command = first_command(ctx, AI_ORDER_ATTACK, unit);; command += AICOMMAND_SIZE) {
        if (guest_u8(ctx, command + AICMD_KIND) == 0)
            return 0;
        if (guest_call2(ctx, AI_IsActiveCommand, unit, command) == 0)
            continue;
        if (guest_u8(ctx, command + AICMD_KIND) != 3)
            continue;
        if (guest_u8(ctx, command + AICMD_CODE) >= 12)
            continue;
        gaddr v1, v2;
        if (!values_usable(ctx, command, unit, &v1, &v2))
            continue;
        if (guest_call(ctx, AI_IsAttackPermissionOnlyCommand, guest_u8(ctx, command + AICMD_CODE), v1, v2, target) != 0)
            return 1;
    }
}

RECOMP_OVERRIDE(0x004CF624) {
    FE_ENTRY(0x004CF624, ai_attack_permission, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x004CF658) {
    FE_ENTRY(0x004CF658, ai_attack_permission_self, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x004D0ADC) {
    FE_ENTRY(0x004D0ADC, ai_heal_rod_permission, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x004D61E4) {
    FE_ENTRY0(0x004D61E4, ai_is_clever);
}

RECOMP_OVERRIDE(0x004D0AC0) {
    FE_ENTRY0(0x004D0AC0, ai_allow_idle_mutation);
}

RECOMP_OVERRIDE(0x004CB280) {
    FE_ENTRY(0x004CB280, ai_command_is_active, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x004D24D4) {
    FE_ENTRY(0x004D24D4, ai_deploy_free_move_flag, FE_ARG(0));
}

RECOMP_OVERRIDE(0x004CC818) {
    FE_ENTRY(0x004CC818, ai_move_power_slow, FE_ARG(0));
}

RECOMP_OVERRIDE(0x004D4054) {
    FE_ENTRY(0x004D4054, ai_heal_condition_for_entrust, FE_ARG(0));
}

RECOMP_OVERRIDE(0x004D4770) {
    FE_ENTRY(0x004D4770, ai_attack_permission_for_command, FE_ARG_S(0), FE_ARG(1), FE_ARG(2), FE_ARG(3));
}

RECOMP_OVERRIDE(0x004CC870) {
    FE_ENTRY(0x004CC870, ai_has_active_command, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x004D48BC) {
    FE_ENTRY(0x004D48BC, ai_has_crossfire_command, FE_ARG(0), FE_ARG(1));
}
