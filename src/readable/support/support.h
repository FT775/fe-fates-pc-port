/* Supports, pair-up and family (Fates classes Reliance, unit::Family, Unit):
   the declarations shared by src/readable/support/support_records.c and
   support_unit.c, the guest functions they still call, and the one one-time
   cache they read.

   Plain-language description (what each function decides): docs/SUPPORT.md.

   This header lives next to its sources, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_SUPPORT_SUPPORT_H
#define FE_SUPPORT_SUPPORT_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-14: it stores nothing
   outside its own stack frame. Where the game calls (or tail-branches to) a
   function that has a readable override (this batch's or an older one), the
   readable code calls it through the guest too, in the game's order and with
   the game's arguments (docs/DECISIONS.md F-018). */
#define SUP_PersonIsDownload 0x0053DFECu     /* Person::IsDownload(void) const (readable: person_is_download) */
#define SUP_PersonGet 0x0044A6F8u            /* Person::Get(int) -> the Person record of a number; reads only */
#define SUP_ForceGetMaskSameForce 0x0041C6C4u /* Force::GetMaskSameForce(Force::Type) -> a bit set of force types;
                                                 a jump table, reads nothing */
#define SUP_UnitPoolGetFromPerson 0x004F5EECu /* UnitPool::GetFromPerson(int, unsigned) -> the unique unit of a
                                                 person number in those forces, or 0; reads only */
#define SUP_ParentGetMaxLevel 0x0053B690u    /* unit::Family::ParentSingle::GetMaxLevel(void) const: 3 */
#define SUP_BrotherGetMaxLevel 0x0053B828u   /* unit::Family::BrotherSingle::GetMaxLevel(void) const: 3 */

/* this batch's overrides, called through the guest where the game calls them
   (ParentGetLevel, BrotherGetLevel and RelianceGetLevel are only tail-branch
   targets of Unit::GetRelianceLevel, whose generated code holds them inline:
   unit_support_level runs their C; GetMarrigePid's BL to Reliance::GetLevel
   stays a guest call) */
#define SUP_RelianceGetMaxLevel 0x005467F0u  /* Reliance::GetMaxLevel(void) const: reliance_max_level */
#define SUP_RelianceGetLevel 0x00546878u     /* Reliance::GetLevel(int) const: reliance_level */
#define SUP_RelianceGetPerson 0x005468BCu    /* Reliance::GetPerson(void) const: reliance_person */
#define SUP_RelianceIsRomance 0x005468C4u    /* Reliance::IsRomance(void) const: reliance_is_romance */
#define SUP_RelianceGetNum 0x004F1284u       /* Reliance::GetNum(const Person*): reliance_count */
#define SUP_RelianceGet 0x004F10ECu          /* Reliance::Get(const Person*, int): reliance_entry */
#define SUP_RelianceGetFromPerson 0x004F0FDCu /* Reliance::GetFromPerson(const Person*, const Person*): reliance_find */
#define SUP_FamilyGetParent 0x0053BECCu      /* unit::Family::GetParent(const Unit*) const: family_parent_record */
#define SUP_ParentGetLevel 0x0053B800u       /* unit::Family::ParentSingle::GetLevel(int) const: family_parent_level */
#define SUP_BrotherGetLevel 0x0053B864u      /* unit::Family::BrotherSingle::GetLevel(int) const: family_sibling_level */
#define SUP_FamilyGetGrandFather 0x0053BAC8u /* unit::Family::GetGrandFather(void) const: family_grandfather */
#define SUP_FamilyGetGrandMother 0x0053BAF4u /* unit::Family::GetGrandMother(void) const: family_grandmother */
#define SUP_UnitGetReliance 0x0052C260u      /* Unit::GetReliance(const Reliance*) const: unit_support_points */
#define SUP_UnitGetFamilyChildImpl 0x005306C4u /* Unit::GetFamilyChildImpl(const Unit*) const: unit_family_child */
#define SUP_UnitIsFamilyBrotherSister 0x00531428u /* Unit::IsFamilyBrotherSister(const Unit*) const: unit_is_sibling */
#define SUP_UnitIsFamilyUncleAunt 0x0052FA58u /* Unit::IsFamilyUncleAunt(const Unit*) const: unit_is_uncle_aunt */
#define SUP_UnitIsFamily 0x0053386Cu         /* Unit::IsFamily(const Unit*) const: unit_is_family */
#define SUP_UnitIsRomance 0x005346F0u        /* Unit::IsRomance(const Unit*) const: unit_can_romance */
#define SUP_UnitGetMarrigePid 0x0052E634u    /* Unit::GetMarrigePid(void) const: unit_spouse_pid */

/* ---- the support table (filled when the game data loads; never changed in
   play). G_RelianceTable holds a pointer to 128 chains, chosen by
   Person.support_id & 127; a chain node is {record, next}. A record is
   {u16 support_id, u16 count, count entries of RELIANCE_ENTRY_SIZE bytes}.
   [high for the layout as read; the address is the literal of all four
   Reliance table getters] */
#define G_RelianceTable 0x006D3BD0u
#define RELIANCE_BUCKETS_MASK 0x7Fu
#define RELIANCE_NODE_RECORD 0x0u     /* ptr: the record */
#define RELIANCE_NODE_NEXT 0x4u       /* ptr: the next node, 0 at the end */
#define RELIANCE_REC_ID 0x0u          /* u16: whose list this is (Person.support_id) */
#define RELIANCE_REC_COUNT 0x2u       /* u16: number of entries */
#define RELIANCE_REC_ENTRIES 0x4u     /* the entries */
#define RELIANCE_ENTRY_SIZE 12u
/* one entry (class Reliance): a possible support partner */
#define RELIANCE_PARTNER 0x0u         /* u16: the partner's person number (Person.pid_number) */
#define RELIANCE_SLOT 0x2u            /* u16: index into the support-points bytes (Unit +0x11C) */
#define RELIANCE_POINTS 0x3u          /* u8[1 + level]: points needed for level 1..4 (C, B, A, S) at +4..+7;
                                         99 means "this level does not exist" */
#define RELIANCE_POINTS_NEVER 99
#define RELIANCE_OWNS_POINTS 0x8u     /* u8: not 0 = the points are kept by the asking unit itself */

/* ---- unit::Family (Unit.family): two ParentSingle records and one
   BrotherSingle [high for the offsets read, med for the names] */
#define FAMILY_PARENT_A 0x00u         /* ParentSingle: +0 Person, +8 / +0xC that parent's grandparents,
                                         +0x10 support points with that parent */
#define FAMILY_PARENT_B 0x14u
#define FAMILY_SIBLING 0x28u          /* BrotherSingle: +0 support points with the sibling */
#define FAMILY_PARENT_PERSON 0x0u     /* ptr: the parent's Person */
#define FAMILY_PARENT_GRANDFATHER 0x8u /* ptr: grandparent_a */
#define FAMILY_PARENT_GRANDMOTHER 0xCu /* ptr: grandparent_b */
#define FAMILY_PARENT_POINTS 0x10u    /* u8: support points with this parent */
#define FAMILY_SIBLING_POINTS 0x0u    /* u8 (at FAMILY_SIBLING) */

/* ---- record fields this batch reads that config/readable/structs/ does not
   name yet (read in the code on 2026-11-14; the integrate step may add them
   to Unit.csv). [high for the offsets, med for the names] */
#define UNIT_SUPPORT_POINTS 0x11Cu    /* ptr: the unit's support-points bytes, indexed by Reliance.slot */
#define PERSON_PID_STRING 0x08u       /* PersonData.pid: what GetMarrigePid returns */

#define UNIT_STATE_NOT_UNIQUE_BIT 0x40000u    /* state bit 18: not unique (no supports) */
#define UNIT_STATE_MAYBE_CLONE_BIT 0x10000000u /* state bit 28: unique only with a download Person */
#define SITUATION_NO_SUPPORT_GAIN 0x200000u   /* Situation.flags bit 21: no support points on this map */

/* ---- Unit::CanDoubleTrade's one-time cache: a PersonFlag bit looked up by
   name the first time (label SPID "pair-up forbidden", given in English
   [med for the English name]) */
#define S_TradeGuard 0x006D99BCu
#define S_TradeNoPairMask 0x006D9CC0u /* u64 */

/* ---- the readable functions (override entries at the end of each file) */
int32_t reliance_max_level(Context *ctx, gaddr reliance);
int32_t reliance_level(Context *ctx, gaddr reliance, int32_t points);
gaddr reliance_person(Context *ctx, gaddr reliance);
uint32_t reliance_is_romance(Context *ctx, gaddr reliance);
int32_t reliance_count(Context *ctx, gaddr person);
gaddr reliance_entry(Context *ctx, gaddr person, int32_t index);
gaddr reliance_find(Context *ctx, gaddr person, gaddr other);
gaddr family_parent_record(Context *ctx, gaddr family, gaddr unit);
int32_t family_parent_level(Context *ctx, gaddr parent, int32_t points);
int32_t family_sibling_level(Context *ctx, gaddr sibling, int32_t points);
gaddr family_grandfather(Context *ctx, gaddr family);
gaddr family_grandmother(Context *ctx, gaddr family);
uint32_t situation_can_gain_support(Context *ctx, gaddr situation, uint32_t force);

int32_t unit_support_points(Context *ctx, gaddr unit, gaddr reliance);
int32_t unit_support_level(Context *ctx, gaddr unit, gaddr other);
int32_t unit_support_max_level(Context *ctx, gaddr unit, gaddr other);
uint32_t unit_can_support(Context *ctx, gaddr unit, gaddr other);
gaddr unit_family_child(Context *ctx, gaddr unit, gaddr other);
uint32_t unit_is_parent_child(Context *ctx, gaddr unit, gaddr other);
uint32_t unit_is_sibling(Context *ctx, gaddr unit, gaddr other);
uint32_t unit_is_uncle_aunt(Context *ctx, gaddr unit, gaddr other);
uint32_t unit_is_family(Context *ctx, gaddr unit, gaddr other);
uint32_t unit_can_romance(Context *ctx, gaddr unit, gaddr other);
gaddr unit_spouse_pid(Context *ctx, gaddr unit);
uint32_t unit_can_trade_partner(Context *ctx, gaddr unit, gaddr other);

#endif /* FE_SUPPORT_SUPPORT_H */
