/* One strike's damage (Fates class map::BattleInfo::Side): the declarations
   of src/readable/strike/strike.c, the guest functions it still calls, and
   the game's one-time caches it reads.

   Plain-language description (what the function decides): docs/STRIKE.md.

   This header lives next to its source, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_STRIKE_STRIKE_H
#define FE_STRIKE_STRIKE_H

#include "fe.h"

/* ---- guest functions called through guest_call() / guest_call5()
   (docs/READABLE.md rule 4: a replay must be safe). Each was read on
   2026-11-17 (and by the battle2 batch on 2026-11-15): it stores nothing
   outside its own stack frame, or only fills a one-time cache of its own.
   Where the game calls (BL) a function, the readable code makes the same
   guest call in the game's order with the game's arguments (docs/DECISIONS.md
   F-018). Every one of them is an override of an older batch. */
#define ST_ItemToData 0x003D0EA4u   /* unit::Item::ToData(void) const (readable: item_to_data) */
#define ST_ItemIsMagic 0x005290B8u  /* Item::IsMagic(void) const (readable: item_is_magic) */
#define ST_UnitGetAttack 0x00534188u /* Unit::GetAttack(const unit::Item*,bool) const (readable: unit_attack) */
#define ST_UnitGetStrImpl 0x0052A80Cu /* Unit::GetStrImpl(item, extras, loss, rally kind) (readable: unit_strength);
                                         the rally kind is the fifth word, on the guest stack: guest_call5 */
#define ST_UnitGetPowImpl 0x0052A500u /* Unit::GetPowImpl(item, extras, loss, rally kind) (readable: unit_magic);
                                         the magic stat; five words as above */

/* ---- one-time caches (guard word, bit 0 = filled; the value the game looked
   up by name the first time). GetSimplePower fills its nine itself, at its
   start, in this order (Astra first, the item flag last). The readable code
   reads a cached value only when every guard says it is filled and gives up
   otherwise, before reading anything else. Names are the game's ID labels
   (SEID_ = equip skill, ISID_ = item skill flag) given in English [med for
   the English]. */
#define S_StAstraGuard 0x006D69ECu
#define S_StAstra 0x006D6934u      /* s16: SEID "Astra" (the damage is halved; 35 % against Dragonskin) */
#define S_StFangGuard 0x006D69E8u
#define S_StFang 0x006D6936u       /* s16: SEID "Dragon Fang" (adds half the attack) */
#define S_StLunaGuard 0x006D69E4u
#define S_StLuna 0x006D6938u       /* s16: SEID "Luna" (gives back half the defense) */
#define S_StIgnisGuard 0x006D69E0u
#define S_StIgnis 0x006D693Au      /* s16: SEID "Ignis" (adds half of the attack stat the weapon does not use) */
#define S_StRendGuard 0x006D69DCu
#define S_StRend 0x006D693Cu       /* s16: SEID "Rend Heaven" (adds half of the foe's matching attack stat) */
#define S_StVengeGuard 0x006D69D8u
#define S_StVenge 0x006D693Eu      /* s16: SEID "Vengeance" (adds the value passed in) */
#define S_StScaleGuard 0x006D69D4u
#define S_StScale 0x006D6940u      /* s16: SEID "Dragonskin" (tested as a bit of the other side's skill bits) */
#define S_StAegisGuard 0x006D69D0u
#define S_StAegis 0x006D6942u      /* s16: the "halve damage" skill bit [low for which skill] */
#define S_StPierceGuard 0x006D69CCu
#define S_StPierceMask 0x006D6AD8u /* u64: ISID "pierces Dragonskin": x 3/4 instead of x 1/2 */

/* Caches of the callees, asked before the guest call that would reach them,
   so that no override gives up inside this one (a nested give-up):
   - Item::IsMagic's own cache (item batch, item.h S_ItemMagicGuard);
   - Unit::GetStrImpl / GetPowImpl's caches, asked through
     unit_stat_caches_ready (src/readable/battle/formula_stats.c), which
     Unit::GetAttack needs too;
   - Unit::GetWeaponExpLimit's three caches (triangle batch), read by
     GetAttack's rank bonus. */
#define S_StMagicGuard 0x006D38D4u
#define S_StExpLimitGuardA 0x006D97B4u
#define S_StExpLimitGuardB 0x006D97B0u
#define S_StExpLimitGuardC 0x006D97ACu
int unit_stat_caches_ready(Context *ctx, uint32_t stat); /* src/readable/battle/formula_stats.c */
#define ST_STAT_STR 1u /* formulas.h STAT_STR */
#define ST_STAT_MAG 2u /* formulas.h STAT_MAG */

/* The last step (an Attack Stance follower deals half, then below 0 is 0):
   the stance batch's C function, kept where it is. */
int32_t stance_follow_up_damage(Context *ctx, gaddr side, int32_t damage); /* src/readable/battle/stance_gauge.c */

/* ---- record fields config/readable/structs/ does not name yet (offsets read
   in the code on 2026-11-17) [high for the offsets, med for the names] */
#define ST_SIDE_TERRAIN 0x020u        /* BattleSide: ptr to the TerrainTile the side stands on (0 = none) */
#define ST_SIDE_ROW_STRIDE 0x94u      /* BattleSide: the per-opponent-row stride of the skill bits */
#define ST_SIDE_FLAG_NO_DAMAGE 0x40u  /* BattleSide.flags: the strike does no damage */
#define ST_SIDE_FLAG_MAGIC 0x20u      /* BattleSide.flags: the strike targets resistance */
#define ST_TERRAIN_ATTR_HALF 0x200000u    /* TerrainTile.attributes bit 21: damage taken here is halved */
#define ST_TERRAIN_ATTR_QUARTER 0x400000u /* bit 22: damage taken here is quartered */
#define ST_ASTRA_SKIN_PERCENT 35      /* Astra against Dragonskin: x 35 / 100, toward zero */

/* ---- the readable function (override entry at the end of strike.c) */
int32_t strike_power(Context *ctx, gaddr side, gaddr other, int32_t skill, int32_t vengeance);

#endif /* FE_STRIKE_STRIKE_H */
