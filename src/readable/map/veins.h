/* Dragon veins (Fates): the declarations shared by src/readable/map/vein_*.c,
   and the game's one-time caches they read.

   Plain-language description of the system: docs/VEINS.md.

   This header lives next to its sources, as src/readable/battle/stances.h
   and triangle.h do. The integrate step may move the declarations into
   include/readable/fe_functions.h.

   Never write the override marker in this header (staging pastes it into
   each file). */

#ifndef FE_MAP_VEINS_H
#define FE_MAP_VEINS_H

#include "fe.h"

/* ---- one-time caches of the game (guard word, bit 0 = filled; the value the
   game looked up by name the first time). Readable code reads a value only
   when its guard says it is filled, and gives up otherwise. */
#define S_VeinGuard 0x006D99C0u     /* Unit::CanDragonVein 0x0052E004: guard of S_VeinMask */
#define S_VeinMask 0x006D9CC8u      /* u64: one PersonFlag bit (1 << PrivateSkill number): the units allowed to
                                       use a dragon vein carry it on the unit, its Person or its class */
#define S_DownloadGuard 0x006D3B3Cu /* Person::IsDownload 0x0053E004: guard of S_DownloadMask */
#define S_DownloadMask 0x006D3B90u  /* u64: one PersonFlag bit marking a download person */

/* ---- map::trick::Type numbers used here (trick::Data.type) */
#define TRICK_TYPE_ANY 0u          /* an Enumerator searching type 0 takes every type */
#define TRICK_TYPE_VEIN 11u        /* a dragon vein (TransformTerrain::BuildAttribute, AIThink::ActionMindTransform) */
#define TRICK_TYPE_VEIN_REGION 12u /* a region a vein changes (SetDeploy, PositionEnumerator) */
#define TRICK_TYPE_MARK_ONE 28u    /* SetDeploy marks the first listed position only */
#define TRICK_TYPE_STANDABLE 29u   /* IsAccess: a tile of the area whose terrain can change */
#define TRICK_TYPE_COUNT 30u       /* IsAccess: types from here on are never reachable */

/* trick::Data.state bits */
#define TRICK_USABLE 1u /* Enable: the gimmick works (the vein command needs it) */
#define TRICK_DONE 2u   /* Done: used up (a used vein) */
#define TRICK_RUINED 4u /* Ruin */

/* the two Enumerator searches the readable code repeats (map::trick::Enumerator::Search) */
#define TRICK_SEARCH_AT 0u     /* the gimmick's top-left corner is (x, y); -1 takes any column / row */
#define TRICK_SEARCH_ACCESS 2u /* (x, y) is in the gimmick's area (trick::Data::IsAccess); (-1, -1) takes all */

/* Unit.state_flags bit: such a unit may use a vein only when its Person is a download person */
#define UNIT_STATE_VEIN_DOWNLOAD_ONLY 0x10000000u
/* Force.type a script vein check refuses (UnitCanDragonVein) */
#define FORCE_TYPE_NO_VEIN 9u
/* map command attribute (BuildAttribute): shown, or not in the menu */
#define MENU_ATTR_SHOWN 1u
#define MENU_ATTR_HIDDEN 4u
/* TerrainTile.attributes bits SetDeploy reads */
#define TERRAIN_CHANGES_WHEN_USABLE 0x400u  /* marked while the region is usable */
#define TERRAIN_CHANGES_WHEN_DONE 0x800u    /* marked while the region is done */
#define TERRAIN_CHANGES_WHEN_RUINED 0x1000u /* marked while the region is ruined */
#define TERRAIN_MARK_COLUMN 0x2000u         /* a marked tile also marks its whole column of the play area */
#define TERRAIN_MARK_ROW 0x4000u            /* ... and its whole row */

/* ---- what the helpers give back (host memory, never guest memory) */

/* The positions a vein lists (map::trick::PositionEnumerator over TrickData.positions). */
#define VEIN_MAX_POSITIONS 128
typedef struct VeinPositions {
    int32_t count;                  /* the game's count (values / 2) */
    int8_t x[VEIN_MAX_POSITIONS];   /* signed bytes, as the game stores them */
    int8_t y[VEIN_MAX_POSITIONS];
} VeinPositions;

/* The preview marks of trick::Data::SetDeploy. The game sets bit (i & 7) of
   byte (i >> 3) of MapDeploy.trick_marks for each marked tile i = x | y << 5;
   for a tile off the 32x32 map that byte lies outside the bitmap, so the
   window here reaches VEIN_MARKS_BEFORE bytes before it and past its end. */
#define VEIN_MARKS_BEFORE 1024
#define VEIN_MARKS_BYTES 3072
typedef struct VeinMarks {
    int kind;                       /* VEIN_MARKS_NONE / _TILES / _CANNON */
    uint32_t result;                /* what SetDeploy returns (kind _TILES: 1 when it marked something) */
    uint8_t bytes[VEIN_MARKS_BYTES]; /* byte k is trick_marks byte k - VEIN_MARKS_BEFORE; starts all clear */
} VeinMarks;
#define VEIN_MARKS_NONE 0   /* a type SetDeploy marks nothing for (it returns 0) */
#define VEIN_MARKS_TILES 1  /* types 11 and 28: bytes[] and result are what the game would leave */
#define VEIN_MARKS_CANNON 2 /* types 25..27: the game asks map::Deploy::Cannon (not rewritten) */

/* ---- the gimmick list and the vein tile (src/readable/map/vein_tricks.c) */
int32_t trick_cannon_access(Context *ctx, gaddr data, int32_t *ay);            /* trick::Data::GetAccessForCannon: x, *ay */
int32_t trick_is_access(Context *ctx, gaddr data, int32_t x, int32_t y);       /* 0x00526BA0 map::trick::Data::IsAccess(int,int) const */
gaddr trick_find(Context *ctx, uint32_t search, int32_t x, int32_t y, uint32_t type, uint32_t mask); /* first match of a trick::Enumerator */
gaddr trick_at_access(Context *ctx, int32_t x, int32_t y, uint32_t type);      /* 0x004CF5B4 AIThink::GetTrickFromAccess(int,int,map::trick::Type) */
int32_t script_trick_test(Context *ctx, gaddr cm, int32_t x, int32_t y, uint32_t type, gaddr stack); /* 0x003B0A44 TrickTst */

/* ---- who may use a vein (src/readable/map/vein_units.c) */
int32_t person_is_download(Context *ctx, gaddr person);                         /* 0x0053DFEC Person::IsDownload(void) const */
int32_t unit_can_dragon_vein(Context *ctx, gaddr unit);                         /* 0x0052DFE8 Unit::CanDragonVein(void) const */
int32_t script_unit_can_dragon_vein(Context *ctx, gaddr cm, int32_t number);    /* 0x003ABD8C UnitCanDragonVein (script) */
uint32_t vein_command_attribute(Context *ctx, gaddr item);                      /* 0x0037B138 TransformTerrain::BuildAttribute */

/* ---- one vein effect: the ground it changes (src/readable/map/vein_effect.c) */
void trick_positions(Context *ctx, gaddr text, VeinPositions *out);             /* trick::PositionEnumerator(const char*) */
void trick_preview_marks(Context *ctx, gaddr data, VeinMarks *out);             /* helper of 0x00526D98 trick::Data::SetDeploy */

#endif /* FE_MAP_VEINS_H */
