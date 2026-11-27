/* How loud are the four volume lines (Fates options screen: the four
   Volume*::GetValue). Plain-language description: docs/VOLUME.md.

   All four are readers: they store nothing. Each reads one byte of the
   options block (GameConfigData +0x10 .. +0x13, through G_GameConfig) and
   scales it to the line's steps: the byte 0xFF ("full", what Reset stores)
   is the line's maximum; any other byte is divided by 256 / maximum. The
   maximum comes from the line's class table (+0x94, VolumeItemBase::GetMax,
   32 in every table of the game), called through the guest as the game calls
   it. So in the game: 0xFF -> 32, any other byte -> byte / 8 (0 .. 31).

   Not here: SetValue (stores the byte and the sound volume), ResetValue,
   Deserialize (stores the bytes and pushes them to the sound system) and the
   options writer (writers stay off, docs/DECISIONS.md F-021). The menu
   readers (src/readable/menu/) are unchanged.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/volume/tests/volume_diff.py. */

#include "volume.h"

/* RVCT's signed division (0x002FFA0C), which the game calls: toward zero, and
   0 for a division by zero (its handler, 0x0013F8B4, returns 0). The most
   negative value over -1 stays itself, as the game's negation leaves it. */
static int32_t rvct_div(int32_t a, int32_t b) {
    if (b == 0)
        return 0;
    if (b == -1)
        return (int32_t)(0u - (uint32_t)a);
    return a / b;
}

/* One volume line's value. `field` is the byte's offset in GameConfigData.
   The game reads the line's GetMax slot and the byte first; when the byte is
   0xFF it answers GetMax itself (a tail call). Otherwise it calls GetMax,
   then reads the options block and the byte again (after the call) and
   divides: byte / (256 / maximum). */
static int32_t volume_value(Context *ctx, gaddr item, size_t field) {
    gaddr get_max = guest_ptr(ctx, guest_ptr(ctx, item) + VOL_SLOT_GET_MAX);
    uint32_t stored = guest_u8(ctx, guest_ptr(ctx, G_GameConfig) + (gaddr)field);
    if (stored >= VOL_FULL)
        return (int32_t)guest_call1(ctx, get_max, item);
    int32_t max = (int32_t)guest_call1(ctx, get_max, item);
    int32_t step = rvct_div(VOL_BYTE_RANGE, max);
    stored = guest_u8(ctx, guest_ptr(ctx, G_GameConfig) + (gaddr)field);
    return rvct_div((int32_t)stored, step);
}

/* The music volume (GameConfigData.volume_bgm).
   Guest function: 0x003BCA4C anonymous_namespace::VolumeBGM::GetValue(void). */
int32_t volume_bgm_value(Context *ctx, gaddr item) {
    return volume_value(ctx, item, offsetof(GameConfigData, volume_bgm));
}

/* The sound-effect volume (GameConfigData.volume_se).
   Guest function: 0x003BC7C4 anonymous_namespace::VolumeSE::GetValue(void). */
int32_t volume_se_value(Context *ctx, gaddr item) {
    return volume_value(ctx, item, offsetof(GameConfigData, volume_se));
}

/* The system-sound volume (GameConfigData.volume_sys_se).
   Guest function: 0x003BB078 anonymous_namespace::VolumeSysSE::GetValue(void). */
int32_t volume_sys_se_value(Context *ctx, gaddr item) {
    return volume_value(ctx, item, offsetof(GameConfigData, volume_sys_se));
}

/* The voice volume (GameConfigData.volume_voice).
   Guest function: 0x003BB168 anonymous_namespace::VolumeVoice::GetValue(void). */
int32_t volume_voice_value(Context *ctx, gaddr item) {
    return volume_value(ctx, item, offsetof(GameConfigData, volume_voice));
}

RECOMP_OVERRIDE(0x003BCA4C) {
    FE_ENTRY(0x003BCA4C, volume_bgm_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003BC7C4) {
    FE_ENTRY(0x003BC7C4, volume_se_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003BB078) {
    FE_ENTRY(0x003BB078, volume_sys_se_value, FE_ARG(0));
}

RECOMP_OVERRIDE(0x003BB168) {
    FE_ENTRY(0x003BB168, volume_voice_value, FE_ARG(0));
}
