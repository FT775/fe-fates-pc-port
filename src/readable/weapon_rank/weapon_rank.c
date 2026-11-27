/* Weapon rank, the part the triangle batch did not take (Fates classes Unit
   and the event script's anonymous_namespace): the rank an event script asks
   for, the weapon exp the class showcase shows, and the weapon exp a
   unit starts with. Plain-language description: docs/WEAPON_RANK.md.

   - script_unit_weapon_rank and unit_weapon_exp_for_job_intro are readers:
     they store nothing.
   - unit_first_weapon_exp is a helper (F-017): Unit::CaclulateFirstWeaponExp
     stores eight bytes through its pointer argument (Unit::CreateImpl passes
     the new unit's own Unit.weapon_exp), so it is a writer and has no
     override. The helper gives the eight bytes back in host memory.

   Get, GetLevel, GetWeaponExp and GetWeaponExpLimit are the triangle batch's
   (src/readable/battle/triangle_tables.c); they are reached here through the
   guest, as the game calls them. The adders (Unit::AddWeaponExp,
   GrowSequence::GainWeaponExp, DualGainWeaponExp) store and are left out;
   ShowWeaponLevelUp is the rank-up window.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/weapon_rank/tests/weapon_rank_diff.py. */

#include "weapon_rank.h"

/* Unit::GetWeaponExpLimit's three caches are filled (its override cannot give
   up inside a guest call). */
static int exp_limit_ready(Context *ctx) {
    return fe_static_ready(ctx, S_WrExpLimitGuardA) && fe_static_ready(ctx, S_WrExpLimitGuardB) &&
           fe_static_ready(ctx, S_WrExpLimitGuardC);
}

/* The event script's "weapon rank of unit N in kind K": 0 for a pool number
   outside 1 .. 250 or a unit of force 9; otherwise the rank (0 = S .. 5 = E,
   6 = none) of the unit's weapon exp in that kind: the stored byte as it is
   when `capped` is 0, else Unit::GetWeaponExp's value (capped at the class's
   limit). The kind is not range-checked (as in the game).
   Guest function: 0x003AC430 anonymous_namespace::UnitGetWeaponLevel(cmvm::CmContext*,int,int,bool). */
int32_t script_unit_weapon_rank(Context *ctx, gaddr script, int32_t unit_index, uint32_t kind, uint32_t capped) {
    (void)script;
    if (unit_index <= 0 || unit_index > WR_SCRIPT_UNIT_MAX)
        return 0;
    /* GetWeaponExp's override reads GetWeaponExpLimit's caches: asked first */
    if (capped != 0 && !exp_limit_ready(ctx))
        return (int32_t)fe_use_original(ctx);
    gaddr unit = guest_call1(ctx, WR_UnitPoolGet, (uint32_t)unit_index);
    gaddr force = READ_FIELD(ctx, Unit, unit, force);
    if (READ_FIELD(ctx, Force, force, type) == WR_FORCE_TYPE_ABSENT)
        return 0;
    unit = guest_call1(ctx, WR_UnitPoolGet, (uint32_t)unit_index);
    uint32_t exp;
    if (capped == 0)
        exp = guest_u8(ctx, FIELD_ADDR(Unit, unit, weapon_exp) + kind);
    else /* the game passes the kind's low byte, sign-extended */
        exp = guest_call2(ctx, WR_UnitGetWeaponExp, unit, (uint32_t)(int32_t)(int8_t)(uint8_t)kind);
    gaddr level = guest_call(ctx, WR_WeaponLevelGet, 0u, 0u, 0u, 0u);
    return (int32_t)guest_call2(ctx, WR_WeaponLevelGetLevel, level, exp);
}

/* The PersonFlag words of a unit, its Person and its class, ORed. */
static uint64_t unit_person_flags(Context *ctx, gaddr unit) {
    return READ_FIELD(ctx, Unit, unit, private_flags) |
           READ_FIELD(ctx, PersonData, READ_FIELD(ctx, Unit, unit, person), flags) |
           READ_FIELD(ctx, JobData, READ_FIELD(ctx, Unit, unit, job), flags);
}

/* The weapon exp the class showcase (ProcJobIntro, the castle file JobIntro) shows for a kind: the stored byte
   (Unit.weapon_exp, not capped), except 0 for stones (kind 7) when the unit,
   its Person or its class carries the flag bit of the stone limit. The game
   fills one cache at entry; while it is cold the readable code gives up.
   Guest function: 0x00532060 Unit::GetWeaponExpForJobIntro(ItemKind::Type) const. */
int32_t unit_weapon_exp_for_job_intro(Context *ctx, gaddr unit, uint32_t kind) {
    if (!fe_static_ready(ctx, S_JobIntroGuard))
        return (int32_t)fe_use_original(ctx);
    if (kind == WR_KIND_STONE && (guest_u64(ctx, S_JobIntroStoneMask) & unit_person_flags(ctx, unit)) != 0)
        return 0;
    return guest_u8(ctx, FIELD_ADDR(Unit, unit, weapon_exp) + kind);
}

/* The weapon exp a unit starts with, one byte per kind (what the game stores
   into the Unit::CreateImpl / Unit::Handover buffer):
     limit = the class's limit (Unit::GetWeaponExpLimit), at least 1;
     floor = 1; except, when the Person's unit_kind is not 1 or 3 and the limit
             asked again is above 0: the rank C threshold on hard, the rank S
             threshold on lunatic (each at most limit);
     the Person's own weapon exp for the kind, at most limit, unless the
     floor is higher (then the floor).
   GetWeaponExpLimit is asked once or twice per kind and WeaponLevel::Get once
   per floor, through the guest, in the game's order. Gives up (nothing in
   out) while GetWeaponExpLimit's caches are cold.
   Guest function: helper of 0x00531C5C Unit::CaclulateFirstWeaponExp(ItemKind::Data*) const
   (a writer: the whole function, without its eight stores). */
void unit_first_weapon_exp(Context *ctx, gaddr unit, uint8_t out[WR_KINDS]) {
    if (!exp_limit_ready(ctx)) {
        fe_use_original(ctx);
        return;
    }
    gaddr user = guest_call(ctx, WR_GameUserDataGet, 0u, 0u, 0u, 0u);
    uint32_t difficulty = READ_FIELD(ctx, GameUserData, user, difficulty);
    for (int32_t kind = 0; kind < WR_KINDS; kind++) {
        int32_t least = 1;
        int32_t limit = (int32_t)guest_call2(ctx, WR_UnitGetWeaponExpLimit, unit, (uint32_t)kind);
        gaddr person = READ_FIELD(ctx, Unit, unit, person);
        if (limit < 1)
            limit = 1;
        uint32_t unit_kind = READ_FIELD(ctx, PersonData, person, unit_kind);
        if (unit_kind != WR_PERSON_KIND_NO_FLOOR_A && unit_kind != WR_PERSON_KIND_NO_FLOOR_B &&
            (int32_t)guest_call2(ctx, WR_UnitGetWeaponExpLimit, unit, (uint32_t)kind) > 0) {
            if (difficulty == WR_DIFFICULTY_HARD)
                least = guest_u8(ctx, FIELD_ADDR(WeaponLevelData, guest_call(ctx, WR_WeaponLevelGet, 0u, 0u, 0u, 0u),
                                                 threshold) + WR_FLOOR_RANK_HARD);
            else if (difficulty == WR_DIFFICULTY_LUNATIC)
                least = guest_u8(ctx, FIELD_ADDR(WeaponLevelData, guest_call(ctx, WR_WeaponLevelGet, 0u, 0u, 0u, 0u),
                                                 threshold) + WR_FLOOR_RANK_LUNATIC);
            if (least > limit)
                least = limit;
        }
        person = READ_FIELD(ctx, Unit, unit, person);
        int32_t own = guest_u8(ctx, FIELD_ADDR(PersonData, person, weapon_exp) + (gaddr)kind);
        int32_t start = least > own ? least : (own > limit ? limit : own);
        out[kind] = (uint8_t)start;
    }
}

RECOMP_OVERRIDE(0x003AC430) {
    FE_ENTRY(0x003AC430, script_unit_weapon_rank, FE_ARG(0), FE_ARG_S(1), FE_ARG(2), FE_ARG(3));
}

RECOMP_OVERRIDE(0x00532060) {
    FE_ENTRY(0x00532060, unit_weapon_exp_for_job_intro, FE_ARG(0), FE_ARG(1));
}
