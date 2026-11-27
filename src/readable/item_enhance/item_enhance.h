/* Does this carried item add its bonus (Fates Unit::IsItemEnhanceHave): the
   declarations of src/readable/item_enhance/item_enhance.c and the guest
   functions and one-time caches it reads.

   Plain-language description (what the function decides): docs/ITEM_ENHANCE.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_ITEM_ENHANCE_ITEM_ENHANCE_H
#define FE_ITEM_ENHANCE_ITEM_ENHANCE_H

#include "fe.h"
#include "../equip_use/equip_use.h" /* unit_can_equip_item (the inlined tail branch) and its caches */

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each is a readable override already and stores
   nothing outside its own one-time cache; the readable code makes the same
   calls in the game's order with the game's arguments (docs/DECISIONS.md
   F-018). */
#define IE_ItemToData 0x003D0EA4u       /* unit::Item::ToData() const (readable: item_to_data) */
#define IE_PersonIsDownload 0x0053DFECu /* Person::IsDownload() const (readable: person_is_download) */
#define IE_ItemSubKindGet 0x0019B97Cu   /* ItemSubKind::Get(int) (readable: item_subkind_record) */

/* Unit::CanItemEquip (0x0052C634, readable: unit_can_equip_item) is NOT a
   guest call here. The game ends with a tail branch (B) to it, and 3dsrecomp
   copies CanItemEquip's code into this function's generated function (the
   capture library's f_0052FB98 has `goto L_0052C634;` at 0x0053054C, built
   2026-11-16 and 2026-11-17), so the original never enters that override from
   here: the readable code runs its C directly (docs/MOVE.md 9, the check for
   each batch; capability.c does the same with unit_max_hp). */

/* ---- the function's sixteen one-time caches (read in the code on
   2026-11-17). Each is filled the first time the function runs, from an ID
   label (PrivateSkill::Get or ItemSkill::Get, then 1 << its number), and
   never again. The readable code reads them only after the game filled them
   (bit 0 of the guard word), and gives up before anything else while one is
   cold. The game asks the guards in this order, one word apart. The labels are
   described in English, not copied. */
#define S_IeGuardFirst 0x006D9894u /* the first guard asked */
#define S_IeGuardLast 0x006D9858u  /* the last (the combined "only for" mask) */
#define S_IeGuardStep 4u           /* the guards go DOWN by one word */

/* u64 PersonFlag bits (1 << a PrivateSkill number): the avatar and five royals */
#define S_IeAvatarFlag 0x006D9B98u  /* guard 0x006D9894 */
#define S_IeTakumiFlag 0x006D9BA0u  /* guard 0x006D9890 */
#define S_IeRyomaFlag 0x006D9BA8u   /* guard 0x006D988C */
#define S_IeLeoFlag 0x006D9BB0u     /* guard 0x006D9888 */
#define S_IeXanderFlag 0x006D9BB8u  /* guard 0x006D9884 */
#define S_IeOpheliaFlag 0x006D9BC0u /* guard 0x006D9880 */
/* u64 ItemFlag bits (1 << an ItemSkill number) */
#define S_IeCarryBonus 0x006D9BC8u  /* guard 0x006D987C: "bonus while carried" */
#define S_IeFujinYumi 0x006D9BD0u   /* guard 0x006D9878: the Fujin Yumi's own bit */
#define S_IeBrynhildr 0x006D9BD8u   /* guard 0x006D9874: the Brynhildr's own bit */
#define S_IeAvatarOnly 0x006D9BE0u  /* guard 0x006D9870: "only for the avatar" */
#define S_IeTakumiOnly 0x006D9BE8u  /* guard 0x006D986C */
#define S_IeRyomaOnly 0x006D9BF0u   /* guard 0x006D9868 */
#define S_IeLeoOnly 0x006D9BF8u     /* guard 0x006D9864 */
#define S_IeXanderOnly 0x006D9C00u  /* guard 0x006D9860 */
#define S_IeOpheliaOnly 0x006D9C08u /* guard 0x006D985C */
/* u64: the six "only for" bits above ORed together (guard 0x006D9858; filled once, read as it is) */
#define S_IeAnyOnly 0x006D9C10u

#define IE_OWNERS 6 /* avatar, Takumi, Ryoma, Leo, Xander, Ophelia: the "only for" bit and the PersonFlag bit pair up */

/* ---- fields and numbers read in the code (2026-11-17) */
#define IE_UNIT_DOWNLOAD_ONLY 0x10000000u /* Unit.state_flags bit 28 (equip_use.h EU_UNIT_DOWNLOAD_ONLY,
                                             sheet.h UNIT_STATE_MAYBE_CLONE): the owner's item then also
                                             needs a download Person */
#define IE_KIND_ALWAYS 8                  /* ItemSubKind.kind 8 (not a weapon kind: equip_use.h, kinds 8
                                             and up are not wielded): the bonus counts with no equip test */

/* ---- the readable function (override entry at the end of the file) */
uint32_t unit_item_enhance_have(Context *ctx, gaddr unit, gaddr item, uint32_t named_weapons);

#endif /* FE_ITEM_ENHANCE_ITEM_ENHANCE_H */
