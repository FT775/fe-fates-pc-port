/* Skills in a fight (Fates map::battle, map::BattleCalculator, Unit,
   SkillIndexProvider). Plain-language description: docs/SKILLS.md sections 3
   to 5.

   Activation of an attack skill (map::BattleCalculator::CalculateAttack, one
   attack of one lead side):
     no roll at all for a follower side, a weapon with the item flag "no
     critical, no skill", or side flag 0x100 / 0x4000;
     else the nine attack skills in a fixed order (Lethality, Aether, Astra,
     Dragon Fang, Sol, Luna, Ignis, Rend Heaven, Vengeance; Lethality only
     when the side's power is above 0). For each skill the side has
     (HasBattleSkill: its own, or its pair partner's with Nohrian Trust) the
     game draws ONE value 0 .. 99 from the battle Random FIRST and then asks
     the chance (GetEquipSkillProbability); the skill activates when
     chance > value. The first that activates ends the list; a skill the side
     does not have draws nothing.
   Chance (Unit::GetEquipSkillProbability):
     0 for a skill whose record has no trigger stat (Skill +0x16 = 0);
     else stat * Skill.trigger_factor / Skill.trigger_divisor (the stat with
     all its extras), + 10 with Hoshidan Unity, + 15 when Quixotic is active
     on either side, + 20 with the luck charm for a luck-based skill (stat 5);
     clamped 0 .. 100; then 100 with the PersonFlag "forced skill activation"
     and, after that, 0 with "skill activation forbidden".

   Both are helpers (F-017): CalculateAttack stores a new scene and runs the
   strikes, and GetEquipSkillProbability calls GetCapabilityImpl with two
   stack words, which guest_call cannot pass (the stat comes from a callback).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/skill/tests/skill_diff.py. */

#include "skills.h"

static uint32_t skill_word(Context *ctx, gaddr addr) {
    return (uint32_t)(int32_t)guest_s16(ctx, addr);
}

/* the PersonFlag words of the unit, its Person and its Job, ORed */
static uint64_t unit_flags(Context *ctx, gaddr unit) {
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    uint64_t f = READ_FIELD(ctx, Unit, unit, private_flags);
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    f |= READ_FIELD(ctx, PersonData, person, flags);
    return f | READ_FIELD(ctx, JobData, job, flags);
}

static gaddr side_at(gaddr info, uint32_t side) {
    return info + (side << 9);  /* BattleInfo.sides[side], 0x200 bytes each (the index is not checked) */
}

/* Whether a side of a fight has a skill: its unit's own, or, when its unit
   has Nohrian Trust, the unit of its pair side (lead 0/1 <-> follower 2/3)
   when there is one.
   Guest function: 0x003A34B4 map::battle::detail::HasBattleSkill(const map::BattleInfo*,map::BattleSide::Type,short). */
uint32_t battle_side_has_skill(Context *ctx, gaddr info, uint32_t side, uint32_t skill) {
    if (!fe_static_ready(ctx, S_NohrSkillGuard))
        return fe_use_original(ctx);
    gaddr unit = READ_FIELD(ctx, BattleSide, side_at(info, side), unit);
    if (guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill) != 0)
        return 1;
    if (guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill_word(ctx, S_NohrSkillId)) == 0)
        return 0;
    uint32_t pair = (side < 2u ? side + 2u : side - 2u) & 0xFFu;
    gaddr partner = READ_FIELD(ctx, BattleSide, side_at(info, pair), unit);
    if (partner == 0)
        return 0;
    return guest_call2(ctx, SKILL_UnitIsEquipSkill, partner, skill) != 0;
}

/* Whether Lethality cannot kill this unit: the PersonFlag "Lethality immune"
   on the unit, its Person or its Job, or one of two skills (Dragonskin and
   the "divine shield" skill).
   Guest function: 0x003A3360 map::battle::detail::IsInvalidKill(const Unit*). */
uint32_t unit_lethality_immune(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, S_KillGuardMask) || !fe_static_ready(ctx, S_KillGuardSkin) ||
        !fe_static_ready(ctx, S_KillGuardShield))
        return fe_use_original(ctx);
    if (unit_flags(ctx, unit) & guest_u64(ctx, S_KillImmuneMask))
        return 1;
    if (guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill_word(ctx, S_KillSkinSkill)) != 0)
        return 1;
    return guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill_word(ctx, S_KillShieldSkill)) != 0;
}

/* The activation effect of a skill: the name of the effect (a string constant
   of the code, "Skl_..."), 0 for a skill without one. The skill numbers are
   the words SkillIndexProvider::Initialize stored by name; Aether's word
   (+0x3C) is never asked here (it shows as Sol, then Luna), and two words
   share one effect.
   Guest function: 0x00211BC4 SkillIndexProvider::GetSkillEffectName(int). */
gaddr skill_effect_name(Context *ctx, int32_t number) {
    static const struct {
        uint16_t word;  /* offset of the skill number in the SkillIndexProvider object */
        gaddr name;     /* the effect name's address */
    } names[SKILL_EFFECT_NAMES] = {
        {0x30, 0x00211D1Cu}, {0x34, 0x00211D2Cu}, {0x38, 0x00211D3Cu}, {0x40, 0x00211D4Cu},
        {0x44, 0x00211D5Cu}, {0x48, 0x00211D6Cu}, {0x4C, 0x00211D7Cu}, {0x50, 0x00211D8Cu},
        {0x54, 0x00211D9Cu}, {0x58, 0x00211DACu}, {0x5C, 0x00211DC0u}, {0x60, 0x00211DD0u},
        {0x64, 0x00211DDCu}, {0x68, 0x00211DECu}, {0x6C, 0x00211DF8u}, {0x70, 0x00211E08u},
        {0x74, 0x00211E14u}, {0x78, 0x00211E24u}, {0x7C, 0x00211E3Cu}, {0x80, 0x00211E30u},
        {0x84, 0x00211E3Cu}, {0x88, 0x00211E6Cu}, {0x8C, 0x00211E80u},
    };
    for (int i = 0; i < SKILL_EFFECT_NAMES; i++)
        if (guest_s32(ctx, G_SkillIndexProvider + names[i].word) == number)
            return names[i].name;
    return 0;
}

/* Helper for 0x005324B8 Unit::GetEquipSkillProbability(short,bool) const:
   the chance in percent. The game's guest calls, in order: EquipSkill::Get,
   GetCapabilityImpl (here: the callback), IsEquipSkill (Hoshidan Unity),
   IsEquipSkill (luck charm, only for a luck-based skill). */
int unit_skill_chance(Context *ctx, gaddr unit, uint32_t skill, uint32_t quixotic, SkillStatFn stat, void *env,
                      int32_t *chance) {
    *chance = 0;
    if (!fe_static_ready(ctx, S_ChanceGuardHoshido) || !fe_static_ready(ctx, S_ChanceGuardCharm) ||
        !fe_static_ready(ctx, S_ChanceGuardForbid) || !fe_static_ready(ctx, S_ChanceGuardForce))
        return 0;
    gaddr record = guest_call1(ctx, SKILL_EquipSkillGet, skill);
    uint32_t kind = READ_FIELD(ctx, SkillData, record, trigger_stat);
    if (kind == 0)
        return !fe_gave_up(ctx);
    int32_t v = stat(ctx, env, unit, kind);
    v = fe_mul32(v, READ_FIELD(ctx, SkillData, record, trigger_factor));
    int32_t divisor = READ_FIELD(ctx, SkillData, record, trigger_divisor);
    if (divisor == 0)
        return 0;  /* the game's division routine would trap */
    v /= divisor;  /* toward zero, as the RVCT routine; |divisor| <= 255 cannot overflow */
    if (guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill_word(ctx, S_ChanceHoshidoSkill)) != 0)
        v = fe_add32(v, 10);
    kind = READ_FIELD(ctx, SkillData, record, trigger_stat);  /* the game reads it again */
    if (quixotic != 0)
        v = fe_add32(v, 15);
    if (kind == 5 && guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill_word(ctx, S_ChanceCharmSkill)) != 0)
        v = fe_add32(v, 20);
    v = v < 0 ? 0 : v > 100 ? 100 : v;
    uint64_t flags = unit_flags(ctx, unit);
    if (flags & guest_u64(ctx, S_ChanceForceMask))
        v = 100;
    if (flags & guest_u64(ctx, S_ChanceForbidMask))
        v = 0;
    *chance = v;
    return !fe_gave_up(ctx);
}

static int bit_set(Context *ctx, gaddr bits, int32_t number) {
    return (guest_u8(ctx, bits + (gaddr)fe_asr(number, 3)) & (1u << ((uint32_t)number & 7u))) != 0;
}

/* Helper for the skill choice of 0x00361F70 map::BattleCalculator::CalculateAttack(map::BattleSide::Type):
   what the game would draw and store (it writes the battle Random, a new
   scene and, through the strikes, the fight). Returns 0 when it gave up (a
   cold cache: every cache the choice may need is asked first). */
int battle_attack_skill_pick(Context *ctx, gaddr calculator, uint32_t side, SkillStatFn stat, void *env,
                             SkillAttackPick *out) {
    for (int i = 0; i <= SKILL_ATTACK_QUIXOTIC; i++)
        if (!fe_static_ready(ctx, S_AttackGuard0 - 4u * (gaddr)i))
            return 0;
    if (!fe_static_ready(ctx, S_AttackGuardItem) || !fe_static_ready(ctx, S_NohrSkillGuard) ||
        !fe_static_ready(ctx, S_ChanceGuardHoshido) || !fe_static_ready(ctx, S_ChanceGuardCharm) ||
        !fe_static_ready(ctx, S_ChanceGuardForbid) || !fe_static_ready(ctx, S_ChanceGuardForce))
        return 0;
    out->skill = 0;
    out->side = side;
    out->draws = 0;
    for (uint32_t i = 0; i < 4; i++)
        out->random.s[i] = guest_u32(ctx, G_BattleRandom + 4u * i);

    gaddr info = READ_FIELD(ctx, BattleCalculator, calculator, info);
    gaddr mine = side_at(info, side);
    uint32_t other_index = (side == 0 || side == 2) ? 1u : (side == 1 || side == 3) ? 0u : 5u;
    gaddr other = side_at(info, other_index);
    uint16_t item = READ_FIELD(ctx, BattleSide, mine, item);
    int32_t chosen = 0;
    if (side < 2u) {
        gaddr data = guest_call1(ctx, SKILL_ItemToData, item != 0 ? FIELD_ADDR(BattleSide, mine, item) : 0u);
        int may = (guest_u64(ctx, data) & guest_u64(ctx, S_AttackNoSkillMask)) == 0 &&
                  (READ_FIELD(ctx, BattleSide, mine, flags) & 0x4100u) == 0;
        if (may) {
            int32_t q = guest_s16(ctx, S_AttackSkill0 + 2u * SKILL_ATTACK_QUIXOTIC);
            uint32_t quixotic = bit_set(ctx, FIELD_ADDR(BattleSide, mine, skill_bits), q) ||
                                bit_set(ctx, FIELD_ADDR(BattleSide, other, skill_bits), q);
            for (int i = 0; i < SKILL_ATTACK_COUNT && chosen == 0; i++) {
                gaddr number_at = S_AttackSkill0 + 2u * (gaddr)i;
                if (i == 0 && READ_FIELD(ctx, BattleSide, mine, power) <= 0)
                    continue;  /* Lethality needs damage */
                /* the game loads the calculator's BattleInfo pointer again for every call */
                gaddr again = READ_FIELD(ctx, BattleCalculator, calculator, info);
                if (guest_call3(ctx, SKILL_HasBattleSkill, again, side, skill_word(ctx, number_at)) == 0)
                    continue;
                gaddr unit = READ_FIELD(ctx, BattleSide, mine, unit);
                int32_t roll = growth_random_below(ctx, &out->random, 100);  /* drawn before the chance */
                out->draws++;
                int32_t chance;
                if (!unit_skill_chance(ctx, unit, skill_word(ctx, number_at), quixotic, stat, env, &chance))
                    return 0;
                if (chance > roll)
                    chosen = guest_s16(ctx, number_at);  /* 0 (a skill missing from the data): go on */
            }
        }
    }
    out->skill = chosen;
    int32_t astra = guest_s16(ctx, S_AttackSkill0 + 2u * SKILL_ATTACK_ASTRA);
    int32_t aether = guest_s16(ctx, S_AttackSkill0 + 2u * SKILL_ATTACK_AETHER);
    if (chosen == astra) {
        out->strikes[0] = out->strikes[1] = chosen;  /* up to five strikes */
    } else if (chosen == aether) {
        out->strikes[0] = guest_s16(ctx, S_AttackSkill0 + 2u * SKILL_ATTACK_SOL);
        out->strikes[1] = guest_s16(ctx, S_AttackSkill0 + 2u * SKILL_ATTACK_LUNA);
    } else {
        out->strikes[0] = chosen;
        out->strikes[1] = -1;  /* one strike */
    }
    return !fe_gave_up(ctx);
}

RECOMP_OVERRIDE(0x003A34B4) {
    FE_ENTRY(0x003A34B4, battle_side_has_skill, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x003A3360) {
    FE_ENTRY(0x003A3360, unit_lethality_immune, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00211BC4) {
    FE_ENTRY(0x00211BC4, skill_effect_name, FE_ARG_S(0));
}
