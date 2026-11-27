/* Battle numbers, second batch (Fates classes map::BattleCalculator,
   map::BattleInfo::Side, Unit, unit::Edit, unit::Enhance, Job,
   map::Situation): the declarations shared by src/readable/battle2/
   battle2_calc.c, battle2_bonus.c and battle2_rules.c, the guest functions
   they still call, and the game's one-time caches they read.

   Plain-language description (what each function decides): docs/BATTLE2.md.

   This header lives next to its sources, as the other areas' headers do
   (tools/readable/stage.py looks in the including file's folder first); the
   integrate step may move the declarations into include/readable/fe_functions.h
   and the callees into fe_callees.h.

   Never write the override marker in this header (staging pastes it into each
   file). */

#ifndef FE_BATTLE2_BATTLE2_H
#define FE_BATTLE2_BATTLE2_H

#include "fe.h"

/* ---- guest functions called through guest_call() (docs/READABLE.md rule 4:
   a replay must be safe). Each was read on 2026-11-15: it stores nothing
   outside its own stack frame, or only fills a one-time cache of its own.
   Where the game calls (BL) a function, the readable code makes the same
   guest call in the game's order with the game's arguments (docs/DECISIONS.md
   F-018), also when the callee is an override of an older batch. */
#define B2_ItemToData 0x003D0EA4u           /* unit::Item::ToData(void) const (readable: item_to_data) */
#define B2_ItemIsMagic 0x005290B8u          /* Item::IsMagic(void) const (readable: item_is_magic) */
#define B2_UnitIsEquipSkill 0x0052DD04u     /* Unit::IsEquipSkill(short) const (readable: unit_has_skill) */
#define B2_UnitIsItemEnhanceHave 0x0052FB98u /* Unit::IsItemEnhanceHave(const unit::Item*,bool) const: does the
                                               carried item's bonus apply to this unit; reads only (not rewritten:
                                               2,500 bytes, a later batch) */
#define B2_UnitGetAttack 0x00534188u        /* Unit::GetAttack(const unit::Item*,bool) const (readable: unit_attack) */
#define B2_UnitGetAvoid 0x00533524u         /* Unit::GetAvoid(const unit::Item*) const (readable: unit_avoid) */
#define B2_ForceIsAllied 0x0053C3E0u        /* Force::IsAllied(Force::Type) const (readable: force_is_allied) */

/* Not callable through guest_call: Unit::GetStrImpl 0x0052A80C, GetPowImpl
   0x0052A500, GetDefImpl 0x0052A000 and GetMdefImpl 0x0052BF6C take a fifth
   argument on the guest stack (the rally kind), and guest_call passes only
   r0..r3 (include/readable/fe_guest.h). Where the game calls one of them the
   readable override gives up (the original runs), or the helper takes the
   value from its caller. */

/* ---- globals (addresses from the functions' literal pools) */
#define B2_G_GameUserData 0x006DA248u /* ptr: GameUserData (GameUserData::Get returns this word) */
#define B2_G_PersonalityTable 0x006D3B98u /* ptr: the Personality records, 0x40 each (Personality::Get) */
#define B2_G_SoundState 0x006D7F38u   /* map::sound's state block (static): +8 a pointer to the battle record it plays for [low] */

/* ---- one-time caches (guard word, bit 0 = filled; the value the game looked
   up by name the first time). Readable code reads a cached value only when its
   guard says it is filled and gives up otherwise, before reading anything
   else. The names are the game's ID labels (SEID_ = equip skill, ISID_ = item
   skill flag, SPID_ = PersonFlag bit) given here in English [med for the
   English]. */

/* map::BattleInfo::Side::GetSimplePower (forecast_damage): eight skills and
   one item flag */
#define S_SpAstraGuard 0x006D69ECu
#define S_SpAstra 0x006D6934u       /* s16: SEID "Astra" (the damage is halved; 35 % against dragonskin) */
#define S_SpFangGuard 0x006D69E8u
#define S_SpFang 0x006D6936u        /* s16: SEID "Dragon Fang" (adds half the attack) */
#define S_SpLunaGuard 0x006D69E4u
#define S_SpLuna 0x006D6938u        /* s16: SEID "Luna" (ignores half the defense) */
#define S_SpIgnisGuard 0x006D69E0u
#define S_SpIgnis 0x006D693Au       /* s16: SEID "Ignis" (adds half of the other attack stat) */
#define S_SpRendGuard 0x006D69DCu
#define S_SpRend 0x006D693Cu        /* s16: SEID "Rend Heaven" (adds half of the foe's attack stat) */
#define S_SpVengeGuard 0x006D69D8u
#define S_SpVenge 0x006D693Eu       /* s16: SEID "Vengeance" (adds the value passed in) */
#define S_SpScaleGuard 0x006D69D4u
#define S_SpScale 0x006D6940u       /* s16: SEID "Dragonskin" (tested as a bit of the other side's skill bits) */
#define S_SpAegisGuard 0x006D69D0u
#define S_SpAegis 0x006D6942u       /* s16: SEID of the "halve damage" skill bit [low for which skill] */
#define S_SpPierceGuard 0x006D69CCu
#define S_SpPierceMask 0x006D6AD8u  /* u64: ISID "pierces dragonskin": x 3/4 instead of x 1/2 */

/* map::BattleInfo::Side::CalculateDetailAvoid / CalculateDetailDefense */
#define S_DaSkillGuard 0x006D69C4u
#define S_DaSkill 0x006D6930u       /* s16: SEID that ignores a negative terrain avoid (attribute bit 8) [low for the name] */
#define S_DdSkillGuard 0x006D69BCu
#define S_DdSkill 0x006D692Eu       /* s16: the same rule for a negative terrain defense */

/* Unit::HasCheerSkillCapability: nine rally skills, tested in this order */
#define S_RallyGuard0 0x006D9974u
#define S_RallySkills 0x006D96AEu   /* s16[9]: the nine SEID "rally <stat>" skills (0x6D96AE .. 0x6D96BE) */
#define B2_RALLY_SKILLS 9u

/* Unit::GetWeaponExpLimit's own caches (triangle.h S_ExpLimitGuardA..C):
   asked by forecast_damage before the Dragon Fang call of Unit::GetAttack
   (with the rank bonus that override reads the limit) */
#define S_B2ExpLimitGuardA 0x006D97B4u
#define S_B2ExpLimitGuardB 0x006D97B0u
#define S_B2ExpLimitGuardC 0x006D97ACu

/* Job::IsHigh / Job::IsGiant */
#define S_HighGuard 0x006D39B0u
#define S_HighMask 0x006D3A10u      /* u64: PersonFlag bit SPID "promoted class" */
#define S_GiantGuard 0x006D39B4u
#define S_GiantMask 0x006D3A18u     /* u64: PersonFlag bit SPID "giant" (the large-model classes) */

/* Unit::GetAttack's caches (formula batch): asked by forecast_damage before
   the Dragon Fang guest call. unit_stat_caches_ready lives in
   src/readable/battle/formula_stats.c. */
int unit_stat_caches_ready(Context *ctx, uint32_t stat); /* stat 1 = Str, 2 = Mag (formulas.h STAT_*) */
#define B2_STAT_STR 1u
#define B2_STAT_MAG 2u

/* ---- record fields this batch reads that config/readable/structs/ does not
   name yet (offsets read in the code on 2026-11-15; the integrate step may
   add them). [high for the offsets, med for the names] */
#define B2_SIDE_SIZE 0x200u          /* BattleInfo.sides stride (BattleCalculator::GetDeadUnit: side << 9) */
#define B2_SIDE_TERRAIN 0x020u       /* BattleSide: ptr to the TerrainTile the side stands on (0 = none) */
#define B2_SIDE_BONUS_DEFENSE 0x12Cu /* BattleSide: s32 x2, the stance defense bonus row of the detail row
                                        (+0x12C/+0x130 lead, +0x1C0/+0x1C4 follower: 0x94 apart) [low for the name] */
#define B2_SIDE_ROW_STRIDE 0x94u     /* BattleSide: the per-opponent-row stride of +0xB4 .. +0x147 */
#define B2_SIDE_EXTRA_DEFENSE 0x1E8u /* BattleSide: s32, added to both defense bonuses [low for the name] */
#define B2_SIDE_EXTRA_DEFENSE2 0x1FCu /* BattleSide: s32, added to both defense bonuses [low for the name] */
#define B2_SIDE_AVOID_A 0x13Cu       /* BattleSide: u16 avoid term of the row (+0x13C, +0x1D0) [low] */
#define B2_SIDE_AVOID_B 0x0B0u       /* BattleSide: u16 avoid term (skill_avoid) */
#define B2_SIDE_AVOID_C 0x1F0u       /* BattleSide: u16 avoid term [low] */
#define B2_SIDE_FLAG_NO_TERRAIN 0x10u /* BattleSide.flags: terrain bonuses do not count */
#define B2_SIDE_FLAG_FOLLOWER 0x02u   /* BattleSide.flags: an Attack Stance follower: damage halved */
#define B2_SIDE_FLAG_NO_DAMAGE 0x40u  /* BattleSide.flags: the strike does no damage */
#define B2_SIDE_FLAG_MAGIC 0x20u      /* BattleSide.flags: the strike targets resistance */
#define B2_SCENE_NEXT 0x0u           /* battle scene record: ptr to the next record */
#define B2_SCENE_SIDE 0x4u           /* u8: the side the record belongs to (0 .. 3) */
#define B2_SCENE_KIND 0x5u           /* u8: what the record is (1 = a strike, 7 = a death, 4/8/9 = ends) [low for the meanings] */
#define B2_ITEM_EXTRA 0x040u         /* ItemData.extra_data: s8[8] the stat bonuses an item gives while carried */
#define B2_TERRAIN_ATTR_LOCKPICK 0x100u  /* TerrainTile.attributes bit 8: S_DaSkill / S_DdSkill lift a negative number */
#define B2_TERRAIN_ATTR_ALLY0 0x80000u   /* bit 19: the bonus is for units not allied with force 0 */
#define B2_TERRAIN_ATTR_ALLY1 0x100000u  /* bit 20: the bonus is for units allied with force 1 */
#define B2_TERRAIN_ATTR_HALF 0x200000u   /* bit 21: damage dealt here is halved */
#define B2_TERRAIN_ATTR_QUARTER 0x400000u /* bit 22: damage dealt here is quartered */
#define B2_SITUATION_NO_PHOENIX 0x80000u  /* Situation.flags bit 19 */
#define B2_SITUATION_CASUAL 0x200u        /* Situation.flags bit 9 */
#define B2_SITUATION_NO_DEATH_RECORD 0x1000000u /* Situation.flags bit 24 */
#define B2_SITUATION_NO_KILL_RECORD 0x800000u   /* Situation.flags bit 23 */
#define B2_USER_CASUAL 0x4u          /* GameUserData.mode_flags bit 2: casual mode */
#define B2_USER_PHOENIX 0x8u         /* GameUserData.mode_flags bit 3: phoenix mode */
#define B2_SOUND_BATTLE 0x8u         /* map::sound state: ptr to the record of the fight being played */
#define B2_SOUND_BATTLE_KIND 0x18Cu  /* that record: u8 kind; 4 = an "individual" fight [low for the meaning] */

/* ---- the readable functions (override entries at the end of each file) */
/* battle2_calc.c */
gaddr battle_dead_unit(Context *ctx, gaddr calculator, gaddr scene);
int32_t battle_strike_run(Context *ctx, gaddr calculator, gaddr scene);
int32_t forecast_damage(Context *ctx, gaddr side, gaddr other, int32_t skill, int32_t vengeance);
uint32_t battle_detail_avoid(Context *ctx, gaddr side, gaddr other);
void battle_detail_defense(Context *ctx, gaddr side, gaddr other, int32_t defense, int32_t resistance,
                           int32_t out[4]);
/* battle2_bonus.c */
int32_t unit_item_stat_bonus(Context *ctx, gaddr unit, int32_t stat);
int32_t edit_stat_bonus(Context *ctx, gaddr edit, int32_t stat);
uint32_t enhance_has_rally_bonus(Context *ctx, gaddr enhance, int32_t stat, int32_t value);
uint32_t unit_has_rally_stat_skill(Context *ctx, gaddr unit);
/* battle2_rules.c */
uint32_t job_is_promoted(Context *ctx, gaddr job);
uint32_t job_is_giant(Context *ctx, gaddr job);
uint32_t situation_is_casual(Context *ctx, gaddr situation, uint32_t ignore_map);
uint32_t situation_is_phoenix(Context *ctx, gaddr situation);
uint32_t situation_records_death(Context *ctx, gaddr situation, uint32_t force);
uint32_t situation_records_kill(Context *ctx, gaddr situation, uint32_t force);
uint32_t sound_is_individual_battle(Context *ctx);

/* The detail row a side reads of the other side: row 1 (against a follower)
   when the side is a follower (type 2 or 3), else row 0. */
static inline uint32_t b2_row_of(Context *ctx, gaddr side) {
    uint32_t type = READ_FIELD(ctx, BattleSide, side, side_type);
    return (type == 2 || type == 3) ? 1u : 0u;
}

/* Bit `bit` of a byte array (the game's `byte[bit >> 3] & 1 << (bit & 7)`,
   with the arithmetic shift a negative skill number gets). */
static inline int b2_bit(Context *ctx, gaddr bytes, int32_t bit) {
    return (guest_u8(ctx, bytes + (gaddr)fe_asr(bit, 3)) & (1u << (bit & 7))) != 0;
}

#endif /* FE_BATTLE2_BATTLE2_H */
