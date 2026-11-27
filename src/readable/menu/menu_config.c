/* The options screen's stored settings and the readers that decide from
   them (Fates class GameConfigData, the option items of the options screen,
   two Unit flag readers). Plain-language description: docs/MENUS.md
   sections 1 and 2.

   The options live in one GameConfigData object (G_GameConfig points to it).
   Each option item of the options screen (anonymous_namespace::DangerPanel,
   HPGauge, Battle, GameSpeed, ...) reads its own byte in GetValue and stores
   it in SetValue; on/off items share the word option_bits, one bit per item
   (the item's GetMask). The battle-animation decision (IsDetailBattle), the
   support-picture decision (IsDetailSupport) and the fast-movement decision
   (IsSpeedFast) read those bytes; they store nothing.

   Every function here is a reader. The SetValue functions, Reset and
   Deserialize are writers and are not rewritten (F-017).

   The game reads some words only when an earlier test failed; the readable
   code reads in the same order and stops at the same point, so a made-up
   state with an unmapped object faults the same number of bytes (tier 2
   compares that).

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/menu/tests/menu_diff.py. */

#include "menus.h"

static gaddr config_object(Context *ctx) {
    return guest_ptr(ctx, G_GameConfig);
}

/* ---- the option items' GetValue (the item itself is not read, except by
   EncountBGM and ConfigItem) */

/* The danger-zone option (0 .. 2; the panel draws for 0 and 2).
   Guest function: 0x003BAEEC anonymous_namespace::DangerPanel::GetValue(void). */
uint32_t config_danger_value(Context *ctx, gaddr item) {
    (void)item;
    return READ_FIELD(ctx, GameConfigData, config_object(ctx), danger);
}

/* The map HP bar option (0 = no bars).
   Guest function: 0x003BC508 anonymous_namespace::HPGauge::GetValue(void). */
uint32_t config_hp_gauge_value(Context *ctx, gaddr item) {
    (void)item;
    return READ_FIELD(ctx, GameConfigData, config_object(ctx), hp_gauge);
}

/* The battle-animation option (0 .. 4, see config_is_detail_battle).
   Guest function: 0x003BC358 anonymous_namespace::Battle::GetValue(void). */
uint32_t config_battle_value(Context *ctx, gaddr item) {
    (void)item;
    return READ_FIELD(ctx, GameConfigData, config_object(ctx), battle_mode);
}

/* The game-speed option (see config_is_speed_fast).
   Guest function: 0x003BC954 anonymous_namespace::GameSpeed::GetValue(void). */
uint32_t config_game_speed_value(Context *ctx, gaddr item) {
    (void)item;
    return READ_FIELD(ctx, GameConfigData, config_object(ctx), game_speed);
}

/* The enemy-phase skip option.
   Guest function: 0x003BC130 anonymous_namespace::AISkip::GetValue(void). */
uint32_t config_ai_skip_value(Context *ctx, gaddr item) {
    (void)item;
    return READ_FIELD(ctx, GameConfigData, config_object(ctx), ai_skip);
}

/* The camera-distance option.
   Guest function: 0x003BC628 anonymous_namespace::Distance::GetValue(void). */
uint32_t config_distance_value(Context *ctx, gaddr item) {
    (void)item;
    return READ_FIELD(ctx, GameConfigData, config_object(ctx), distance_option);
}

/* The battle-music option: the position of the stored value in the item's
   own list of values (count at +0x4C, list of words at +0x50), 0 when it is
   not in the list or the list is empty.
   Guest function: 0x003BAD1C anonymous_namespace::EncountBGM::GetValue(void). */
#define MN_BGM_COUNT 0x4Cu
#define MN_BGM_LIST 0x50u
uint32_t config_encounter_bgm_value(Context *ctx, gaddr item) {
    int32_t count = guest_s32(ctx, item + MN_BGM_COUNT);
    if (count <= 0)
        return 0;
    gaddr list = guest_ptr(ctx, item + MN_BGM_LIST);
    uint32_t stored = READ_FIELD(ctx, GameConfigData, config_object(ctx), encounter_bgm);
    for (int32_t i = 0; i < count; i++)
        if (guest_u32(ctx, list + 4u * (uint32_t)i) == stored)
            return (uint32_t)i;
    return 0;
}

/* An on/off option item: 1 when its bit (the item's virtual GetMask, slot
   +0x80 of its class table, called through the guest) is set in option_bits.
   Guest function: 0x003BA88C anonymous_namespace::ConfigItem::GetValue(void). */
uint32_t config_item_value(Context *ctx, gaddr item) {
    gaddr table = guest_ptr(ctx, item);
    uint32_t mask = guest_call1(ctx, guest_ptr(ctx, table + MN_ITEM_GETMASK_SLOT), item);
    return (mask & READ_FIELD(ctx, GameConfigData, config_object(ctx), option_bits)) != 0 ? 1u : 0u;
}

/* ---- GameConfigData's own readers */

/* Whether map movements run fast: game_speed 1 = always, 2 = while A is
   held (Pad.held bit 0), anything else = never. The pad is read only when
   the option is not 1.
   Guest function: 0x0050AA68 GameConfigData::IsSpeedFast(void) const. */
uint32_t config_is_speed_fast(Context *ctx, gaddr config) {
    uint32_t speed = READ_FIELD(ctx, GameConfigData, config, game_speed);
    if (speed == 1)
        return 1;
    gaddr pad = guest_ptr(ctx, G_Pad);
    if ((READ_FIELD(ctx, Pad, pad, held) & 1u) && speed == 2)
        return 1;
    return 0;
}

/* Whether B or Start was pressed this frame (Pad.pressed & 0xA): the input
   that skips an effect. The object itself is not read.
   Guest function: 0x0050AA4C GameConfigData::IsSkipInput(void) const. */
uint32_t config_is_skip_input(Context *ctx, gaddr config) {
    (void)config;
    return (READ_FIELD(ctx, Pad, guest_ptr(ctx, G_Pad), pressed) & 0xAu) != 0 ? 1u : 0u;
}

/* The unit-information level: 2 with option bit 29, else 1 with bit 30,
   else 0.
   Guest function: 0x0050AE40 GameConfigData::GetInfoCapability(void) const. */
uint32_t config_info_capability(Context *ctx, gaddr config) {
    uint32_t bits = READ_FIELD(ctx, GameConfigData, config, option_bits);
    if (bits & 0x20000000u)
        return 2;
    return (bits & 0x40000000u) != 0 ? 1u : 0u;
}

/* What the battle-animation option (battle_mode) says for one unit of a
   fight: 1 = on; 2 = on when the unit's army is one of the map's
   force_dual armies (the byte Situation + army type is 1); 3 = on when the
   byte at Situation + (Situation byte +0x8) is 1; 4 = on when the unit's
   state bit 31 is set; 0 and anything else = off. The option byte is read
   each time, as the game does. */
static uint32_t option_says_picture(Context *ctx, gaddr config, gaddr situation, gaddr unit) {
    switch (READ_FIELD(ctx, GameConfigData, config, battle_mode)) {
    case 1:
        return 1;
    case 2: {
        gaddr force = READ_FIELD(ctx, Unit, unit, force);
        return guest_u8(ctx, situation + READ_FIELD(ctx, Force, force, type)) == 1 ? 1u : 0u;
    }
    case 3:
        return guest_u8(ctx, situation + READ_FIELD(ctx, Situation, situation, force_index)) == 1 ? 1u : 0u;
    case 4:
        return READ_FIELD(ctx, Unit, unit, state_flags) >> 31;
    default:
        return 0;
    }
}

/* Whether a fight between two units gets the battle picture (1) or is shown
   on the map (0): the option for either unit (above; no unit, or no map
   Situation, counts as off), flipped when the caller's bool is not 0 (the
   battle sequence passes "L is held"), then forced on when either unit has
   the "always" PersonFlag (Unit::IsDetailBattleMust) and forced off when
   either has the "never" one (Unit::IsDetailBattleNotAllow): "never" wins.
   The four unit checks are made through the guest in this order (a, b, then
   a, b), whatever the answer so far.
   Every cache the two unit checks need is asked first: a give-up comes before
   any read (an early give-up is always safe).
   Guest function: 0x0050AAA0 GameConfigData::IsDetailBattle(const Unit*,const Unit*,bool) const. */
uint32_t config_is_detail_battle(Context *ctx, gaddr config, gaddr unit_a, gaddr unit_b, uint32_t flip) {
    if ((unit_a != 0 || unit_b != 0) &&
        (!fe_static_ready(ctx, MN_MustGuardA) || !fe_static_ready(ctx, MN_MustGuardB) ||
         !fe_static_ready(ctx, MN_NotAllowGuard)))
        return fe_use_original(ctx);
    gaddr situation = guest_ptr(ctx, G_Situation);
    uint32_t picture = 0;
    if (unit_a != 0 && situation != 0)
        picture = option_says_picture(ctx, config, situation, unit_a);
    if (unit_b != 0 && situation != 0 && option_says_picture(ctx, config, situation, unit_b))
        picture = 1;
    if (flip != 0)
        picture ^= 1u;
    if (unit_a != 0 && guest_call1(ctx, MN_UnitDetailMust, unit_a) != 0)
        picture = 1;
    if (unit_b != 0 && guest_call1(ctx, MN_UnitDetailMust, unit_b) != 0)
        picture = 1;
    if (unit_a != 0 && guest_call1(ctx, MN_UnitDetailNotAllow, unit_a) != 0)
        picture = 0;
    if (unit_b != 0 && guest_call1(ctx, MN_UnitDetailNotAllow, unit_b) != 0)
        picture = 0;
    return picture;
}

/* Unit.private_flags | Person.flags | Job.flags (the PersonFlag words) */
static uint64_t unit_person_flags(Context *ctx, gaddr unit) {
    gaddr person = READ_FIELD(ctx, Unit, unit, person);
    uint64_t f = READ_FIELD(ctx, Unit, unit, private_flags);
    gaddr job = READ_FIELD(ctx, Unit, unit, job);
    f |= READ_FIELD(ctx, PersonData, person, flags);
    return f | READ_FIELD(ctx, JobData, job, flags);
}

/* Whether a support (or dance) scene between two units gets its picture: the
   same battle_mode rule per unit, but a unit counts only when option bit 1
   (option_bits & 2) is also set; flipped by the bool; then off when either
   unit has the "no support picture" PersonFlag (one one-time cache).
   Guest function: 0x0050AC04 GameConfigData::IsDetailSupport(const Unit*,const Unit*,bool) const. */
uint32_t config_is_detail_support(Context *ctx, gaddr config, gaddr unit_a, gaddr unit_b, uint32_t flip) {
    if (!fe_static_ready(ctx, MN_SupportGuard))
        return fe_use_original(ctx);
    gaddr situation = guest_ptr(ctx, G_Situation);
    uint32_t picture = 0;
    if (unit_a != 0) {
        uint32_t says = situation != 0 ? option_says_picture(ctx, config, situation, unit_a) : 0u;
        if ((READ_FIELD(ctx, GameConfigData, config, option_bits) & 2u) && says)
            picture = 1;
    }
    if (unit_b != 0) {
        uint32_t says = situation != 0 ? option_says_picture(ctx, config, situation, unit_b) : 0u;
        if ((READ_FIELD(ctx, GameConfigData, config, option_bits) & 2u) && says)
            picture = 1;
    }
    if (flip != 0)
        picture ^= 1u;
    uint64_t never = guest_u64(ctx, MN_SupportMask);
    if (unit_a != 0 && (unit_person_flags(ctx, unit_a) & never))
        picture = 0;
    if (unit_b != 0 && (unit_person_flags(ctx, unit_b) & never))
        picture = 0;
    return picture;
}

/* 1 when the unit (its own, Person or Job PersonFlag word) has either of the
   two "always the battle picture" bits (two one-time caches).
   Guest function: 0x00530884 Unit::IsDetailBattleMust(void) const. */
uint32_t unit_is_detail_battle_must(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, MN_MustGuardA) || !fe_static_ready(ctx, MN_MustGuardB))
        return fe_use_original(ctx);
    uint64_t always = guest_u64(ctx, MN_MustMaskA) | guest_u64(ctx, MN_MustMaskB);
    return (unit_person_flags(ctx, unit) & always) != 0 ? 1u : 0u;
}

/* 1 when the unit has the "never the battle picture" bit (one one-time cache).
   Guest function: 0x00531BA8 Unit::IsDetailBattleNotAllow(void) const. */
uint32_t unit_is_detail_battle_not_allow(Context *ctx, gaddr unit) {
    if (!fe_static_ready(ctx, MN_NotAllowGuard))
        return fe_use_original(ctx);
    uint64_t never = guest_u64(ctx, MN_NotAllowMask);
    return (unit_person_flags(ctx, unit) & never) != 0 ? 1u : 0u;
}

/* Helper for 0x0050AEA0 GameConfigData::Serialize(Stream*) const (it writes
   to the stream): the 17 values in the order it writes them. */
int config_saved_record(Context *ctx, gaddr config, MenuSavedEntry out[MN_SAVED_ENTRIES]) {
    out[0].kind = 1;
    out[0].value = 1;  /* the record's version */
    out[1].kind = 4;
    out[1].value = READ_FIELD(ctx, GameConfigData, config, option_bits);
    for (uint32_t i = 0; i < 15; i++) {
        out[2 + i].kind = 1;
        out[2 + i].value = guest_u8(ctx, FIELD_ADDR(GameConfigData, config, battle_mode) + i);
    }
    return !fe_gave_up(ctx);
}

RECOMP_OVERRIDE(0x003BAEEC) {
    FE_ENTRY(0x003BAEEC, config_danger_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003BC508) {
    FE_ENTRY(0x003BC508, config_hp_gauge_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003BC358) {
    FE_ENTRY(0x003BC358, config_battle_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003BC954) {
    FE_ENTRY(0x003BC954, config_game_speed_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003BC130) {
    FE_ENTRY(0x003BC130, config_ai_skip_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003BC628) {
    FE_ENTRY(0x003BC628, config_distance_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003BAD1C) {
    FE_ENTRY(0x003BAD1C, config_encounter_bgm_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003BA88C) {
    FE_ENTRY(0x003BA88C, config_item_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0050AA68) {
    FE_ENTRY(0x0050AA68, config_is_speed_fast, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0050AA4C) {
    FE_ENTRY(0x0050AA4C, config_is_skip_input, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0050AE40) {
    FE_ENTRY(0x0050AE40, config_info_capability, FE_ARG(0));
}

RECOMP_OVERRIDE(0x0050AAA0) {
    FE_ENTRY(0x0050AAA0, config_is_detail_battle, FE_ARG(0), FE_ARG(1), FE_ARG(2), FE_ARG(3));
}

RECOMP_OVERRIDE(0x0050AC04) {
    FE_ENTRY(0x0050AC04, config_is_detail_support, FE_ARG(0), FE_ARG(1), FE_ARG(2), FE_ARG(3));
}

RECOMP_OVERRIDE(0x00530884) {
    FE_ENTRY(0x00530884, unit_is_detail_battle_must, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00531BA8) {
    FE_ENTRY(0x00531BA8, unit_is_detail_battle_not_allow, FE_ARG(0));
}
