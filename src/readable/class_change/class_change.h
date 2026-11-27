/* Class change and seals (Fates classes ClassChange, Unit, Person and the map
   fight's sequence map::SequenceBattle): the declarations shared by
   src/readable/class_change/class_change.c, the guest functions it still
   calls, and the record fields it reads that config/readable/structs/ does
   not name yet.

   Plain-language description (what each function decides, and what was left
   out and why): docs/CLASS_CHANGE.md.

   "Seal" means two things in this game. The class-change items (Master Seal,
   Heart Seal, Partner Seal, Friendship Seal ...) have no function of their
   own: ClassChange::GetType reads the item's kind byte. The stat seals
   (skills that lower a stat after a hit) are decided by the map fight's
   GetSealEffect and merged by MergeSeal. No function is named after a seal
   item; none is invented here.

   This header lives next to its sources, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_CLASS_CHANGE_CLASS_CHANGE_H
#define FE_CLASS_CHANGE_CLASS_CHANGE_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-16: it stores nothing.
   Where the game calls (BL, or a tail branch B) a function, the readable code
   makes the same guest call in the game's order with the game's arguments
   (docs/DECISIONS.md F-018), also when the callee is an override of an older
   batch. */
#define CC_JobGet 0x00341AA4u          /* Job::Get(unsigned short): the class record of a class number (walks the
                                          loaded class blocks; reads only; not rewritten) */
#define CC_JobIsHigh 0x00524804u       /* Job::IsHigh(void) const (readable: job_is_promoted, battle2 batch) */
#define CC_PersonIsDownload 0x0053DFECu /* Person::IsDownload(void) const (readable: person_is_download, veins batch) */
#define CC_EquipSkillGet 0x001758C4u   /* EquipSkill::Get(const char*): the skill record of an ID label (a hash
                                          lookup, IdentHash::GetSurely; reads only; not rewritten) */
#define CC_UnitIsEquipSkill 0x0052DD04u /* Unit::IsEquipSkill(short) const (readable: unit_has_skill, skills batch) */

/* ---- skill ID labels: NUL-terminated strings in the game's code segment,
   passed by address exactly as the game passes them (the readable code never
   reads the text). Addresses only; the labels are the game's SEID_ names,
   given here in English [med for the English, low where marked]. */
#define CC_SEID_DragonCurse 0x0035739Cu /* "dragon curse" [low for the English] */
#define CC_SEID_SealStr 0x003573A8u     /* "Seal Strength" */
#define CC_SEID_SealMag 0x003573B4u     /* "Seal Magic" */
#define CC_SEID_SealSpd 0x003573C4u     /* "Seal Speed" */
#define CC_SEID_SealDef 0x003573D4u     /* "Seal Defense" */
#define CC_SEID_SealRes 0x003573E4u     /* "Seal Resistance" */
#define CC_SEID_DirtyFight 0x003573F4u  /* "dirty fight" [low] */
#define CC_SEID_Clumsy 0x0035740Cu      /* "clumsy" [low] */
#define CC_SEID_NinjaReturn 0x00357424u /* a ninja technique "wheel return" [low] */
#define CC_SEID_IceBlood 0x00357434u    /* "ice blood" [low] */
#define CC_SEID_SealChain 0x00354D98u   /* "chain of seals" (MergeSeal: seals add up instead of the larger
                                           one counting) [low for the English] */

/* ---- record fields this batch reads that config/readable/structs/ does not
   name yet (offsets read in the code on 2026-11-16; the integrate step may
   add them). [high for the offsets, low for the names unless marked] */
#define CC_ITEM_KIND_BYTE 0x040u        /* ItemData: s8, the class-change kind of a seal item (the same byte is
                                           extra_data[0], the carried-stat bonus of other items) [high offset] */
#define CC_UNIT_DOWNLOAD_ONLY 0x10000000u /* Unit.state_flags bit 28 (veins.h UNIT_STATE_VEIN_DOWNLOAD_ONLY) */
#define CC_SKILL_INDEX 0x010u           /* EquipSkill record: s16, the skill number Unit::IsEquipSkill takes [high] */
/* map::SequenceBattle's ProcSequence (the map fight's sequence object) */
#define CC_SEQ_UNIT_OF_SIDE 0x270u      /* ptr[2]: the unit of fight side 0 / 1 */
#define CC_SEQ_ACTIVE 0x274u            /* word: 0 = no seal step (nothing is sealed) */
#define CC_SEQ_SKIP 0x25Cu              /* word: not 0 = no seal step */
#define CC_SEQ_MODE 0x280u              /* word: bit 2 or bit 13 set = no seal step */
#define CC_SEQ_MODE_NO_SEAL 0x2004u
#define CC_SEQ_STRIKE 0x250u            /* ptr: the strike record; +0x24 / +0x28 a flag word per side */
#define CC_SEQ_FIGHT 0x24Cu             /* ptr: a record whose word +0x23C, when above 0, turns "dirty fight" off */
#define CC_STRIKE_FLAGS 0x024u          /* strike record: u32 flags of side 0 (+0x28: side 1) */
#define CC_STRIKE_NO_SEAL 0x400u        /* in either side's word: no seal */
#define CC_STRIKE_CLUMSY 0x80u          /* side 0's word: the "clumsy" seal may apply */
#define CC_STRIKE_NINJA 0x8000u         /* the side's word: the ninja technique applies */
#define CC_STRIKE_ICE 0x10000u          /* the side's word: "ice blood" applies */
#define CC_FIGHT_DIRTY_OFF 0x23Cu

/* ---- the readable functions (override entries at the end of the source) */
uint32_t class_change_type(Context *ctx, gaddr item);
uint32_t unit_reliance_blocks_class_change(Context *ctx, gaddr unit);
uint32_t person_base_job_index(Context *ctx, gaddr person);
gaddr battle_seal_effect(Context *ctx, gaddr sequence, uint32_t side);
/* helper (F-017): the pure part of a writer, no override marker */
uint32_t seal_merged_value(Context *ctx, gaddr capability, gaddr unit, int32_t stat, int32_t value);

#endif /* FE_CLASS_CHANGE_CLASS_CHANGE_H */
