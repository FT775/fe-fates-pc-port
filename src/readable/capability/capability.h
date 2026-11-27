/* The stat getter by number (Fates class Unit) and the two stat totals built
   on it. The declarations of src/readable/capability/capability.c and the
   guest functions it calls.

   Plain-language description (what each function decides): docs/CAPABILITY.md.
   Plan row: docs/tracks/REWRITE_ORDER3.md batch 3 ("the stat getter a class
   change would pass through").

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first).

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_CAPABILITY_CAPABILITY_H
#define FE_CAPABILITY_CAPABILITY_H

#include "fe.h"

/* ---- the table Unit::GetCapabilityImpl reads: one C++ member-function
   pointer per stat number (8 bytes each: the function, then the "this"
   adjustment word whose bit 0 means "virtual"), in the data segment. Read
   2026-11-16 (objdump of extracted/text.bin; the entries seen in
   extracted/data.bin are the eight getters below, stat 0 empty). Nothing of
   the table's contents is copied here, only where it is. */
#define CAP_STAT_TABLE 0x006D9CE0u
#define CAP_STAT_TABLE_STEP 8u
#define CAP_STAT_COUNT 8u           /* stats 0..7: HP, Str, Mag, Skl, Spd, Lck, Def, Res */

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each is a readable override of an older batch and
   stores nothing of the game's (the stat getters fill only their own one-time
   caches, asked first here). Where the game calls a function the readable code
   makes the same guest call in the game's order with the game's arguments
   (docs/DECISIONS.md F-018). */
/* Unit::GetMHPImpl (0x0052A364): stat 0's empty table entry ends in a tail
   branch (B) to it, which 3dsrecomp keeps inside this function's generated
   code (no guest call in the library). So it is not guest-called: the C of
   unit_max_hp (sheet batch) runs directly. Its declaration is copied from
   src/readable/sheet/sheet.h (keep in step); it asks its own two caches
   (S_HpGuard0..1) first, before it reads anything. */
int32_t unit_max_hp(Context *ctx, gaddr unit, uint32_t with_extras, uint32_t unused, int32_t kind);
/* The seven getters of stats 1..7 take a fifth argument word on the stack
   (the rally kind): called with guest_call5 (docs/READABLE.md 17). */
#define CAP_UnitGetStrImpl 0x0052A80Cu   /* strength (readable: unit_strength, battle batch) */
#define CAP_UnitGetPowImpl 0x0052A500u   /* magic (unit_magic) */
#define CAP_UnitGetTechImpl 0x0052C30Cu  /* skill (unit_skill) */
#define CAP_UnitGetQuickImpl 0x0052D860u /* speed (unit_speed) */
#define CAP_UnitGetLuckImpl 0x0052BC5Cu  /* luck (unit_luck) */
#define CAP_UnitGetDefImpl 0x0052A000u   /* defense (unit_defense, sheet batch) */
#define CAP_UnitGetMdefImpl 0x0052BF6Cu  /* resistance (unit_resistance, sheet batch) */
/* The two totals call Unit::GetCapabilityImpl itself, which takes two words
   on the stack: guest_call6 (round 15, include/readable/fe_guest.h). */
#define CAP_UnitGetCapabilityImpl 0x0052F7A0u /* readable: unit_capability (this batch) */

/* ---- the callees' one-time caches, asked first so that no override gives up
   inside a guest call (a nested give-up). Copied from the owners' headers;
   keep in step with them:
   - GetDefImpl, GetMdefImpl: src/readable/sheet/sheet.h
     S_DefGuard0..3, S_ResGuard0..2 (GetMHPImpl's S_HpGuard0..1 are asked by
     unit_max_hp itself)
   - the five battle getters: unit_stat_caches_ready (battle batch,
     src/readable/battle/formula_stats.c), which reads the same table the
     five overrides read. */
#define S_CapDefGuard0 0x006D9788u
#define S_CapDefGuard1 0x006D9784u
#define S_CapDefGuard2 0x006D9780u
#define S_CapDefGuard3 0x006D977Cu
#define S_CapResGuard0 0x006D9794u
#define S_CapResGuard1 0x006D9790u
#define S_CapResGuard2 0x006D978Cu
int unit_stat_caches_ready(Context *ctx, uint32_t stat);
#define CAP_STAT_STR 1u                 /* src/readable/battle/formulas.h STAT_STR */
#define CAP_STAT_MAG 2u                 /* STAT_MAG */
#define CAP_STAT_SKL 3u                 /* STAT_SKL */
#define CAP_STAT_SPD 4u                 /* STAT_SPD */
#define CAP_STAT_LCK 5u                 /* STAT_LCK */

/* ---- what the two totals pass for each of stats 1..7 */
#define CAP_TOTAL_FIRST 1u
#define CAP_TOTAL_END 8u                /* stats 1..7: HP is not counted */
#define CAP_TOTAL_ITEM 0u               /* no item given */
#define CAP_TOTAL_EXTRAS 1u             /* with the extras */
#define CAP_TOTAL_LOSS_RATING 1u        /* GetCapabilityRating: with the third bool */
#define CAP_TOTAL_LOSS_NO_WEAKNESS 0u   /* GetNoWeaknessCapabilityRating: without it */
#define CAP_TOTAL_RALLY 0u              /* rally kind 0 */

/* ---- the readable functions (override entries at the end of the file) */
int32_t unit_capability(Context *ctx, gaddr unit, uint32_t stat, gaddr item, uint32_t with_extras, gaddr sp);
int32_t unit_capability_rating(Context *ctx, gaddr unit);
int32_t unit_capability_rating_no_weakness(Context *ctx, gaddr unit);

#endif /* FE_CAPABILITY_CAPABILITY_H */
