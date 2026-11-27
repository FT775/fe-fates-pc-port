/* The first readable writer, kept OFF: setting the game's own options block
   (GameConfigData, G_GameConfig) the way the game's options screen stores it.
   Sources: src/readable/menu/menu_config_writer.c. Rules and what must pass
   before it may be switched on: docs/WRITERS.md. Gate and undo log:
   src/readable/core/fe_writer.h.

   Never write the override marker in this header (staging pastes it into
   each file). */

#ifndef FE_MENU_WRITER_H
#define FE_MENU_WRITER_H

#include "menus.h"
#include "../core/fe_writer.h"

/* guest functions the danger-zone line calls (both read 2026-11-14):
   Map::Get returns the map object pointer (a global) or 0 off the map;
   map::Image::Danger::Update rebuilds the danger zone: a game WRITER (it
   clears and refills the four tile sets), called through fe_writer_call so
   every store it makes is logged and undone with the line */
#define MN_MapGet 0x00342574u
#define MN_DangerUpdate 0x0038F834u

/* the lines this writer sets, in the order it sets them (the block's byte
   order: +0x8, +0xC, +0xE, +0x16) */
#define MN_SET_BATTLE 0x1u     /* battle animations, 0 .. 4 (Battle::GetNum 5) */
#define MN_SET_GAME_SPEED 0x2u /* game speed, 0 .. 2 (GameSpeed::GetNum 3) */
#define MN_SET_DANGER 0x4u     /* danger zone, 0 .. 2 (DangerPanel::GetNum 3) */
#define MN_SET_HP_GAUGE 0x8u   /* map HP bars, 0 .. 1 (HPGauge::GetNum 2) */
#define MN_SET_ALL 0xFu

typedef struct ConfigOptionsWanted {
    uint32_t lines;      /* MN_SET_* bits: the lines to set; the others are not touched */
    uint32_t battle;
    uint32_t game_speed;
    uint32_t danger;
    uint32_t hp_gauge;
} ConfigOptionsWanted;

/* The writer: FE_WRITER_OK (the lines are set; a line that already held its
   value is left alone, as the screen does), FE_WRITER_OFF (switched off:
   nothing read, nothing stored), FE_WRITER_REFUSED (a value past the line's
   last value, or an unknown line bit: nothing read, nothing stored) or
   FE_WRITER_ROLLED_BACK (a store or call failed: every store put back).
   The guest registers are as they were on the way in. */
int config_write_options(Context *ctx, const ConfigOptionsWanted *want);

/* The same, for W2's give-up restore only (inside a save): every line as above, but the danger line
   stores its byte without the zone rebuild (Danger::Update), which the game never runs inside a save
   (docs/OPTIONS_WIRING.md section 13, round 38 T6). */
int config_restore_options(Context *ctx, const ConfigOptionsWanted *want);

/* The same, for W1's apply at a load or game reset: the screen's value range for every line (a value past it is
   refused), but the danger line stores its byte without the zone rebuild; the game rebuilds the zone itself
   after the load (docs/OPTIONS_WIRING.md section 15, round 40 T2). */
int config_apply_options(Context *ctx, const ConfigOptionsWanted *want);

/* The four setters (each one line's SetValue(int)): they store only inside an
   open session of the gate (fe_writer_begin); outside one they store nothing.
   1 = done, 0 = a store or call failed. */
int config_set_battle(Context *ctx, uint32_t value);
int config_set_game_speed(Context *ctx, uint32_t value);
int config_set_danger(Context *ctx, uint32_t value);
int config_set_hp_gauge(Context *ctx, uint32_t value);

/* ---- the options wiring around config_write_options (docs/OPTIONS_WIRING.md section 4;
   src/readable/menu/menu_options_hook.c). Both OFF: no override marker in this tree; the OK A
   test tree wires them (src/readable/menu/options_hooks_overrides.txt). */

/* the game's stream calls W2 makes, as GameConfigData::Serialize makes them (both read
   2026-11-18: each stores the stream position word +0x10, then the byte(s) at buffer +0x4 +
   position; WriteLong does that four times, low byte first) */
#define MN_StreamWriteByte 0x0044C3DCu
#define MN_StreamWriteLong 0x0044C41Cu

#define MN_OPT_LINES 4 /* battle +0x8, game speed +0xC, danger +0xE, HP bars +0x16 (MN_SET_* order) */

typedef struct ConfigOptionsState {
    uint32_t lines;               /* MN_SET_* bits W1 set at the last apply (0: nothing to guard) */
    uint8_t own[MN_OPT_LINES];    /* the game's own value of each set line (the save's, or the reset's) */
    uint8_t applied[MN_OPT_LINES];/* the value W1 stored */
    uint32_t depth;               /* GameConfigData::Serialize calls running (W2 counts every one) */
    uint32_t calls;               /* W1 runs that passed step 0 (global block, not in a save, switched on) */
    uint32_t applies;             /* W1 runs that stored (config_write_options OK) */
    uint32_t saves;               /* W2 runs that wrote the record themselves */
    uint32_t give_ups;            /* W2 runs that could not write and restored own[] instead */
} ConfigOptionsState;

/* W1: the body of the override of GameConfigData::Reset (0x001D06DC) and of
   GameConfigData::Deserialize (0x001D0374). r0 = the block; original = the game's function
   (RECOMP_ORIGINAL of that address). Returns as the game's function does. */
void config_options_hook(Context *ctx, Code original);

/* W2: the body of the override of GameConfigData::Serialize (0x0050AEA0). r0 = the block,
   r1 = the stream; original = the game's Serialize. */
void config_serialize_guard(Context *ctx, Code original);

/* the record of the last apply (a copy; nothing in the game) */
void config_options_state(ConfigOptionsState *out);

#ifdef FE_WRITER_TESTS
void config_options_test_reset(void);
#endif

#endif /* FE_MENU_WRITER_H */
