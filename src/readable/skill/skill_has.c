/* "Does this unit have skill X" (Fates class Unit, Job, EquipSkill,
   unit::EquipSkillPool, the event script). Plain-language description:
   docs/SKILLS.md sections 1 and 2.

   A unit has a skill when it is its personal skill or one of its five
   equipped skills:
     personal skill = Person.personal_skill[difficulty]   (one per difficulty)
     equipped       = Unit.equip_skills[0 .. 4]           (s16 each, 0 = empty)
   Fates has no passive "class skills": a class only names the skills a unit
   learns at some levels (Job::GetEquipSkill); learned skills go to the pool
   (unit::EquipSkillPool, one bit per common skill) and count only once
   equipped.

   Skill records (the Skill table, docs/TABLES.md) are found by number with
   EquipSkill::Get(short): table + number * 0x20, without a range check.

   The game reads some words only when an earlier test failed; the readable
   code reads in the same order and stops at the same point, so a made-up
   state with an unmapped record faults the same number of bytes (tier 2
   compares that).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/skill/tests/skill_diff.py. */

#include "skills.h"

static int32_t difficulty(Context *ctx) {
    return READ_FIELD(ctx, GameUserData, guest_ptr(ctx, G_GameUserData), difficulty);
}

/* the s16 at addr, widened as the game's compare sees it */
static uint32_t skill_word(Context *ctx, gaddr addr) {
    return (uint32_t)(int32_t)guest_s16(ctx, addr);
}

/* 1 when the skill is the unit's personal skill (for the difficulty now) or
   one of its five equipped skills; 0 for skill 0. The whole register is
   compared, as the game does.
   Guest function: 0x0052DD04 Unit::IsEquipSkill(short) const. */
uint32_t unit_has_skill(Context *ctx, gaddr unit, uint32_t skill) {
    if (skill == 0)
        return 0;
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    gaddr personal = FIELD_ADDR(PersonData, person, personal_skill) + 2u * (uint32_t)difficulty(ctx);
    gaddr slots = FIELD_ADDR(Unit, unit, equip_skills);
    if (skill_word(ctx, personal) == skill || skill_word(ctx, slots) == skill)
        return 1;
    if (skill_word(ctx, slots + 2u) == skill || skill_word(ctx, slots + 4u) == skill)
        return 1;
    if (skill_word(ctx, slots + 6u) == skill || skill_word(ctx, slots + 8u) == skill)
        return 1;
    return 0;
}

/* The unit's personal skill for the difficulty now.
   Guest function: 0x00530814 Unit::GetIndividualSkill(void) const. */
int32_t unit_personal_skill(Context *ctx, gaddr unit) {
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    return guest_s16(ctx, FIELD_ADDR(PersonData, person, personal_skill) + 2u * (uint32_t)difficulty(ctx));
}

/* How many of the five equipped-skill slots are not empty.
   Guest function: 0x00530B90 Unit::GetHasEquipSkillNum(void) const. */
int32_t unit_equipped_skill_count(Context *ctx, gaddr unit) {
    int32_t n = 0;
    for (uint32_t i = 0; i < 5; i++)
        if (guest_u16(ctx, FIELD_ADDR(Unit, unit, equip_skills) + 2u * i) != 0)
            n++;
    return n;
}

/* The Skill record of a number: table + number * 0x20 (no range check).
   Guest function: 0x001758E4 EquipSkill::Get(short). */
gaddr skill_record(Context *ctx, uint32_t number) {
    return READ_FIELD(ctx, EquipSkillTable, G_EquipSkill, table) + (number << 5);
}

/* How many Skill records there are.
   Guest function: 0x001758F8 EquipSkill::GetNum(void). */
uint32_t skill_total(Context *ctx) {
    return READ_FIELD(ctx, EquipSkillTable, G_EquipSkill, count);
}

/* How many of them are "common" skills (the ones a unit can learn and keep
   in its pool; the pool has one bit per common skill).
   Guest function: 0x001758B4 EquipSkill::GetCommonNum(void). */
uint32_t skill_common_total(Context *ctx) {
    return READ_FIELD(ctx, EquipSkillTable, G_EquipSkill, common_count);
}

/* The skill a class teaches at a level, 0 for other levels: a promoted class
   (PersonFlag "promoted class" in Job.flags) at levels 5 and 15 (its first
   two skills), any other class at levels 1, 10, 25 and 35 (four skills).
   Guest function: 0x00524224 Job::GetEquipSkill(int) const. */
uint32_t job_class_skill(Context *ctx, gaddr job, int32_t level) {
    if (!fe_static_ready(ctx, S_JobHighGuard))
        return fe_use_original(ctx);
    uint64_t mask = guest_u64(ctx, S_JobHighMask);
    gaddr skills = FIELD_ADDR(JobData, job, skill);
    if (READ_FIELD(ctx, JobData, job, flags) & mask) {
        if (level == 5)
            return guest_u16(ctx, skills);
        if (level == 15)
            return guest_u16(ctx, skills + 2u);
        return 0;
    }
    if (level == 1)
        return guest_u16(ctx, skills);
    if (level == 10)
        return guest_u16(ctx, skills + 2u);
    if (level == 25)
        return guest_u16(ctx, skills + 4u);
    if (level == 35)
        return guest_u16(ctx, skills + 6u);
    return 0;
}

/* Whether a learned-skill pool holds a common skill: 0 for a number at or
   past the common count, else the pool's bit (the masked byte, not 0/1: the
   game returns the byte AND the bit). The byte index is number >> 3 with the
   sign kept, as the game computes it.
   Guest function: 0x0053AA74 unit::EquipSkillPool::Tst(int) const. */
uint32_t skill_pool_test(Context *ctx, gaddr pool, int32_t number) {
    int32_t common = (int32_t)guest_call(ctx, SKILL_EquipSkillGetCommonNum, 0u, 0u, 0u, 0u);
    if (common <= number)
        return 0;
    return guest_u8(ctx, pool + (gaddr)fe_asr(number, 3)) & (1u << ((uint32_t)number & 7u));
}

/* Whether a skill shows as "???" in the menus: only a record of kind 5 can,
   and it does while the message table has no text for its name label (no
   entry, or an entry whose word +0xC is 0).
   Guest function: 0x00506034 EquipSkill::IsUnknown(void) const. */
uint32_t skill_is_unknown(Context *ctx, gaddr record) {
    if (READ_FIELD(ctx, SkillData, record, kind) != 5)
        return 0;
    gaddr name = READ_FIELD(ctx, SkillData, record, mseid_name);
    gaddr entry = guest_call2(ctx, SKILL_IdentHashGetIdent, guest_ptr(ctx, G_IdentHash), name);
    if (entry == 0)
        return 1;
    return guest_u32(ctx, entry + 0xCu) != 0 ? 0 : 1;
}

/* The event script's "does unit N have skill SEID_x": 0 for a pool index
   outside 1 .. 250 or a unit of force 9, else Unit::IsEquipSkill of the
   skill's number. The game reaches IsEquipSkill by a branch (no call of its
   own), so it runs in C here.
   Guest function: 0x003AB148 anonymous_namespace::UnitIsEquipSkill(cmvm::CmContext*,int,const char*). */
uint32_t script_unit_has_skill(Context *ctx, gaddr script, int32_t unit_index, gaddr seid) {
    (void)script;
    if (unit_index <= 0 || unit_index > 250)
        return 0;
    gaddr unit = guest_call1(ctx, SKILL_UnitPoolGet, (uint32_t)unit_index);
    gaddr force = READ_FIELD(ctx, Unit, unit, force);
    if (READ_FIELD(ctx, Force, force, type) == 9)
        return 0;
    unit = guest_call1(ctx, SKILL_UnitPoolGet, (uint32_t)unit_index);
    gaddr record = guest_call1(ctx, SKILL_EquipSkillByName, seid);
    return unit_has_skill(ctx, unit, skill_word(ctx, FIELD_ADDR(SkillData, record, skill_number)));
}

/* Whether the unit has the "rally movement" skill.
   Guest function: 0x0052F9F8 Unit::HasCheerSkillMove(void) const. */
uint32_t unit_has_rally_move_skill(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, S_RallyMoveGuard))
        return fe_use_original(ctx);
    return guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill_word(ctx, S_RallyMoveSkill)) != 0;
}

/* Whether the unit has any rally skill: a stat rally (asked first, through
   the guest) or the movement rally. The cache of the second is asked before
   anything, so a give-up comes first (the game would look at it only when the
   unit has no stat rally).
   Guest function: 0x0052E6E4 Unit::HasCheerSkill(void) const. */
uint32_t unit_has_rally_skill(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, S_RallyMoveGuard))
        return fe_use_original(ctx);
    if (guest_call1(ctx, SKILL_HasRallyCapability, unit) != 0)
        return 1;
    return guest_call2(ctx, SKILL_UnitIsEquipSkill, unit, skill_word(ctx, S_RallyMoveSkill)) != 0;
}

RECOMP_OVERRIDE(0x0052DD04) {
    FE_ENTRY(0x0052DD04, unit_has_skill, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00530814) {
    FE_ENTRY(0x00530814, unit_personal_skill, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00530B90) {
    FE_ENTRY(0x00530B90, unit_equipped_skill_count, FE_ARG(0));
}

RECOMP_OVERRIDE(0x001758E4) {
    FE_ENTRY(0x001758E4, skill_record, FE_ARG(0));
}

RECOMP_OVERRIDE(0x001758F8) {
    FE_ENTRY0(0x001758F8, skill_total);
}

RECOMP_OVERRIDE(0x001758B4) {
    FE_ENTRY0(0x001758B4, skill_common_total);
}

RECOMP_OVERRIDE(0x00524224) {
    FE_ENTRY(0x00524224, job_class_skill, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x0053AA74) {
    FE_ENTRY(0x0053AA74, skill_pool_test, FE_ARG(0), FE_ARG_S(1));
}

RECOMP_OVERRIDE(0x00506034) {
    FE_ENTRY(0x00506034, skill_is_unknown, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003AB148) {
    FE_ENTRY(0x003AB148, script_unit_has_skill, FE_ARG(0), FE_ARG_S(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x0052F9F8) {
    FE_ENTRY(0x0052F9F8, unit_has_rally_move_skill, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0052E6E4) {
    FE_ENTRY(0x0052E6E4, unit_has_rally_skill, FE_ARG(0));
}
