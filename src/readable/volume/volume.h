/* How loud are the four volume lines (Fates options screen: music, sound
   effects, system sounds, voices): the declarations of
   src/readable/volume/volume.c.

   Plain-language description (what the four functions answer): docs/VOLUME.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_VOLUME_VOLUME_H
#define FE_VOLUME_VOLUME_H

#include "fe.h"

/* ---- the option line's class table (read 2026-11-17 in the game's rodata,
   read only). The four volume lines share one base class
   (anonymous_namespace::VolumeItemBase); each class table holds its own
   GetValue at +0x84 and VolumeItemBase::GetMax (0x003BB3F8: returns 32,
   reads nothing, stores nothing) at +0x94. The readable code calls whatever
   the line's table holds at +0x94, through the guest, as the game does
   (docs/DECISIONS.md F-018). */
#define VOL_SLOT_GET_MAX 0x94u
#define VOL_FULL 0xFFu      /* the stored byte that means "full" (Reset stores it) */
#define VOL_BYTE_RANGE 0x100 /* the stored byte's range, divided by the line's maximum */

/* ---- the readable functions (override entries at the end of the file) */
int32_t volume_bgm_value(Context *ctx, gaddr item);
int32_t volume_se_value(Context *ctx, gaddr item);
int32_t volume_sys_se_value(Context *ctx, gaddr item);
int32_t volume_voice_value(Context *ctx, gaddr item);

#endif /* FE_VOLUME_VOLUME_H */
