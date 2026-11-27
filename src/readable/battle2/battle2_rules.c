/* Battle numbers, second batch: the rules a fight's numbers and outcome
   depend on (Fates classes Job and map::Situation): is a class promoted or
   giant, is the game in casual or phoenix mode, does this map record deaths
   and kills, and which kind of fight the map music is for.
   Plain-language description: docs/BATTLE2.md section 6.

   All are readers: they store nothing. Job::IsHigh and Job::IsGiant read a
   one-time cache; the readable code gives up while it is cold, before reading
   anything else. GameUserData::Get (a function that returns the word at
   0x006DA248) is read directly, as situation_can_dual (stance batch) does.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/battle2/tests/battle2_diff.py. */

#include "battle2.h"

/* Whether a class has the PersonFlag bit "promoted class" (the class sort,
   the battle model and the class-change lists ask it).
   Guest function: 0x00524804 Job::IsHigh(void) const. */
uint32_t job_is_promoted(Context *ctx, gaddr job) {
    if (!fe_static_ready(ctx, S_HighGuard))
        return fe_use_original(ctx);
    return (READ_FIELD(ctx, JobData, job, flags) & guest_u64(ctx, S_HighMask)) != 0 ? 1u : 0u;
}

/* Whether a class has the PersonFlag bit "giant" (the large-model classes;
   Unit::IsSpecialBattle, the sheet batch's unit_is_special_battle, asks it).
   Guest function: 0x005249F8 Job::IsGiant(void) const. */
uint32_t job_is_giant(Context *ctx, gaddr job) {
    if (!fe_static_ready(ctx, S_GiantGuard))
        return fe_use_original(ctx);
    return (READ_FIELD(ctx, JobData, job, flags) & guest_u64(ctx, S_GiantMask)) != 0 ? 1u : 0u;
}

static uint32_t user_mode(Context *ctx) {
    return READ_FIELD(ctx, GameUserData, guest_ptr(ctx, B2_G_GameUserData), mode_flags);
}

/* Whether fallen units come back (casual): always in casual mode (the save's
   mode bit 2); otherwise, unless the caller says to ignore the map, when the
   map's rule bit 9 is set.
   Guest function: 0x005281F8 map::Situation::IsCasual(bool) const. */
uint32_t situation_is_casual(Context *ctx, gaddr situation, uint32_t ignore_map) {
    if (user_mode(ctx) & B2_USER_CASUAL)
        return 1;
    if (ignore_map != 0)
        return 0;
    return (READ_FIELD(ctx, Situation, situation, flags) & B2_SITUATION_CASUAL) != 0 ? 1u : 0u;
}

/* Whether fallen units come back the next turn (phoenix): the save's mode bit
   3, unless the map's rule bit 19 turns it off (then the save is not read).
   Guest function: 0x0052824C map::Situation::IsPhoenix(void) const. */
uint32_t situation_is_phoenix(Context *ctx, gaddr situation) {
    if (READ_FIELD(ctx, Situation, situation, flags) & B2_SITUATION_NO_PHOENIX)
        return 0;
    return (user_mode(ctx) & B2_USER_PHOENIX) != 0 ? 1u : 0u;
}

/* Whether a death of a unit of force 0 .. 2 is recorded on this map: the
   map's per-force byte (Situation +0 .. +2) is 1 and the map's rule bit 24 is
   clear. Any other force number gives 0 without reading the map.
   Guest function: 0x00527E80 map::Situation::IsRecordDead(Force::Type) const. */
uint32_t situation_records_death(Context *ctx, gaddr situation, uint32_t force) {
    if (force >= 3u)
        return 0;
    if (READ_FIELD(ctx, Situation, situation, flags) & B2_SITUATION_NO_DEATH_RECORD)
        return 0;
    return guest_u8(ctx, situation + force) == 1 ? 1u : 0u;
}

/* The same for a kill, with the map's rule bit 23.
   Guest function: 0x00527EA4 map::Situation::IsRecordKill(Force::Type) const. */
uint32_t situation_records_kill(Context *ctx, gaddr situation, uint32_t force) {
    if (force >= 3u)
        return 0;
    if (READ_FIELD(ctx, Situation, situation, flags) & B2_SITUATION_NO_KILL_RECORD)
        return 0;
    return guest_u8(ctx, situation + force) == 1 ? 1u : 0u;
}

/* Whether the fight the map music is set for is an "individual" one: the
   kind byte (+0x18C) of the battle record map::sound keeps (the pointer at
   +8 of its state block at 0x006D7F38) is 4 [low for what kind 4 is]. The pinch-music test of
   every map fight (map::sound::util::IsPinchBattle) asks it. No pointer is
   checked, as in the game.
   Guest function: 0x00397FB4 map::sound::IsIndividualBattle(void). */
uint32_t sound_is_individual_battle(Context *ctx) {
    gaddr battle = guest_ptr(ctx, B2_G_SoundState + B2_SOUND_BATTLE);
    return guest_u8(ctx, battle + B2_SOUND_BATTLE_KIND) == 4 ? 1u : 0u;
}

RECOMP_OVERRIDE(0x00524804) {
    FE_ENTRY(0x00524804, job_is_promoted, FE_ARG(0));
}

RECOMP_OVERRIDE(0x005249F8) {
    FE_ENTRY(0x005249F8, job_is_giant, FE_ARG(0));
}

RECOMP_OVERRIDE(0x005281F8) {
    FE_ENTRY(0x005281F8, situation_is_casual, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x0052824C) {
    FE_ENTRY(0x0052824C, situation_is_phoenix, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00527E80) {
    FE_ENTRY(0x00527E80, situation_records_death, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00527EA4) {
    FE_ENTRY(0x00527EA4, situation_records_kill, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x00397FB4) {
    FE_ENTRY0(0x00397FB4, sound_is_individual_battle);
}
