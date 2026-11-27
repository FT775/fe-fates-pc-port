/* The options wiring's two pieces around config_write_options, both OFF
   (docs/OPTIONS_WIRING.md sections 3 to 6; F-021, F-034):

   W1 config_options_hook: runs in place of GameConfigData::Reset (0x001D06DC)
      and GameConfigData::Deserialize (0x001D0374). It runs the game's own
      function first, then, only on the global block and never inside a save,
      reads the PC options file (src/readable/core/options.c) and hands the
      lines set there to config_apply_options (config_write_options' gate
      session and rules, gate name "config_options", but the danger byte is
      stored without the zone rebuild: the game rebuilds the zone itself after
      a load; round 40, OK A T2),
      remembering the game's own value of each line (own[]) and what was
      stored (applied[]). It stores nothing itself.
   W2 config_serialize_guard: runs in place of GameConfigData::Serialize
      (0x0050AEA0). On the global block, with a line W1 set, it writes the
      same 20 bytes in the same order through the game's own stream calls,
      inside a gate session of its own (gate name "config_save_guard"), but
      for a line still holding applied[line] it writes own[line]: a save never
      keeps a PC value. A line changed since on the game's own screen is
      written as the block holds it and becomes the new own[line]. If it
      cannot run, it first puts own[] back into the block (config_restore_options:
      the bytes only, no zone rebuild inside a save; a session of its own), drops
      the PC choice until the next load or reset, and lets the game's own
      Serialize run.

   Neither is an override in this tree: no override marker here (a writer
   never has one, docs/WRITERS.md). The OK A test tree (build/oka/tree, never
   git) wires them with three small override bodies, kept as text in
   src/readable/menu/options_hooks_overrides.txt, and arms the three gate
   entries there. In every library built from git the table in
   src/readable/core/writer.c has config_options_hook, config_save_guard and
   config_options at 0, so W1 runs the game's function only (it does not even
   read the block pointer or the file) and W2, with no line set, runs the
   game's Serialize only.

   The rules, in the order section 4 gives them:
   W1 0. Only the global block, never inside a save: `this` (r0) is
         *G_GameConfig, not 0, its 0x17 bytes are mapped, and no
         GameConfigData::Serialize is running (W2's depth count is 0).
         Otherwise the game's function only: not the file, not own[], not the
         gate. (Every Versus file write, GameBackup type 7, runs Reset three times
         and Deserialize once on the versus copy; the boot Reset runs before the pointer is stored.)
      1. The game's own function, first.
      2. The options file: danger_zone, hp_bars, animation_skip, anim_speed.
      3. All four 0: return; nothing read from the game, nothing stored, the
         gate not asked. (The record of the last apply is cleared: the block
         holds the save's or the reset's values now.)
      4. own[line] = the block's value, then config_apply_options with the
         lines set; applied[line] = the value stored. Only when W2's writer
         is switched on too (W1 alone would let the PC value into saves).
   W2 counts every call it passes through (the versus copy included) in the
      depth count W1 checks; with no line set it opens no session and runs
      the game's Serialize.

   Page value -> block byte (section 4's table):
     danger_zone (+0xE)     1 -> 0 (the game's reset style)  2 -> not touched
                            (round 38, OK A T3: no value of the byte hides the
                            zone. Danger::Add picks its move-search flags from it,
                            0 -> 0x50000, 2 -> 0x30000, else 0x10000, and
                            Panel::Danger::SetVertex draws for every value, with a
                            second colour pair for 1; so "not drawn" cannot be
                            had through this byte and page value 2 stores nothing)
     hp_bars (+0x16)        1 -> 1 (shown)      2 -> 0 (hidden)
     animation_skip (+0x8)  1 -> 0 (on the map) 2 -> 1 (the picture)
     anim_speed (+0xC)      1 -> 1 (always)     2 -> 2 (while A held)  3 -> 0 (never)

   Status: UNVERIFIED, OFF. Host differential test against the game's own
   Reset / Deserialize / Serialize / SetValue code, with every planted bug of
   section 7 and the made-up suspend save order:
   src/readable/menu/tests/w12_diff.py. */

#include <string.h>

#include "menu_writer.h"
#include "../core/fe_options.h"

/* the record of the last apply (library memory, never the game's) */
static ConfigOptionsState mn_opt;

/* a page value with no game value behind it: W1 leaves the line alone */
#define MN_NOT_OFFERED 0xFFu

/* the lines in the block's byte order (MN_SET_* bits) */
static const struct {
    uint32_t bit;
    uint32_t offset; /* GameConfigData byte */
    int page;        /* FE_OPT_* line of the options file */
    uint8_t to_byte[4]; /* page value -> block byte (index 0 unused: not touched; MN_NOT_OFFERED: not touched) */
} mn_opt_lines[MN_OPT_LINES] = {
    {MN_SET_BATTLE, 0x8u, FE_OPT_ANIMATION_SKIP, {0, 0, 1, 0}},
    {MN_SET_GAME_SPEED, 0xCu, FE_OPT_ANIM_SPEED, {0, 1, 2, 0}},
    {MN_SET_DANGER, 0xEu, FE_OPT_DANGER_ZONE, {0, 0, MN_NOT_OFFERED, 0}},
    {MN_SET_HP_GAUGE, 0x16u, FE_OPT_HP_BARS, {0, 1, 0, 0}},
};

void config_options_state(ConfigOptionsState *out) { *out = mn_opt; }

#ifdef FE_WRITER_TESTS
void config_options_test_reset(void) { memset(&mn_opt, 0, sizeof mn_opt); }
#endif

/* the game's own function (as FE_ENTRY's original path: it returns to the
   caller's lr by itself) */
static void mn_call_original(Context *ctx, Code original) { CALL(original); }

/* the block's bytes +0x0 .. +0x16 all have a direct page (a store there can
   be logged and undone) */
static int mn_block_mapped(Context *ctx, gaddr block) {
    return ctx->write_pages[block >> 12] != NULL && ctx->write_pages[(block + 0x16u) >> 12] != NULL;
}

/* the global block (*G_GameConfig), mapped, and `self` is it */
static int mn_is_global(Context *ctx, gaddr self) {
    if (self == 0)
        return 0;
    return self == guest_ptr(ctx, G_GameConfig) && mn_block_mapped(ctx, self);
}

static void mn_want_set(ConfigOptionsWanted *w, uint32_t bit, uint32_t value) {
    w->lines |= bit;
    if (bit == MN_SET_BATTLE)
        w->battle = value;
    else if (bit == MN_SET_GAME_SPEED)
        w->game_speed = value;
    else if (bit == MN_SET_DANGER)
        w->danger = value;
    else
        w->hp_gauge = value;
}

void config_options_hook(Context *ctx, Code original) {
    gaddr self = ctx->r[0];
    int apply = fe_writer_switched_on(FE_WRITER_CONFIG_OPTIONS_HOOK) && mn_opt.depth == 0 && mn_is_global(ctx, self);
    mn_call_original(ctx, original); /* step 1: the game's Reset / Deserialize */
    if (!apply || fe_gave_up(ctx))
        return; /* step 0: the versus copy, the boot Reset, inside a save, or off */
    mn_opt.lines = 0; /* the block holds the save's (or the reset's) own values now */
    mn_opt.calls++;
    FeOptions file;
    if (!fe_options_read(&file))
        return; /* step 3: nothing set in the file */
    if (!fe_writer_switched_on(FE_WRITER_CONFIG_SAVE_GUARD))
        return; /* never W1 without W2 */
    ConfigOptionsWanted want;
    memset(&want, 0, sizeof want);
    uint8_t own[MN_OPT_LINES] = {0}, value[MN_OPT_LINES] = {0};
    for (int i = 0; i < MN_OPT_LINES; i++) {
        uint8_t page = file.line[mn_opt_lines[i].page];
        if (page == 0 || mn_opt_lines[i].to_byte[page & 3u] == MN_NOT_OFFERED)
            continue;
        value[i] = mn_opt_lines[i].to_byte[page & 3u];
        own[i] = guest_u8(ctx, self + mn_opt_lines[i].offset);
        mn_want_set(&want, mn_opt_lines[i].bit, value[i]);
    }
    if (want.lines == 0)
        return; /* only lines with no game value behind them: nothing to store, the gate not asked */
    /* the danger byte without a zone rebuild: the game rebuilds the zone after the load itself (round 40, T2) */
    if (config_apply_options(ctx, &want) != FE_WRITER_OK)
        return; /* off, refused or rolled back: nothing stays stored, nothing to guard */
    for (int i = 0; i < MN_OPT_LINES; i++)
        if (want.lines & mn_opt_lines[i].bit) {
            mn_opt.own[i] = own[i];
            mn_opt.applied[i] = value[i];
        }
    mn_opt.lines = want.lines;
    mn_opt.applies++;
}

void config_serialize_guard(Context *ctx, Code original) {
    gaddr self = ctx->r[0], stream = ctx->r[1];
    mn_opt.depth++;
    if (mn_opt.lines == 0 || !mn_is_global(ctx, self)) {
        mn_call_original(ctx, original); /* the copy, or nothing set: the game's own Serialize */
        mn_opt.depth--;
        return;
    }
    /* the 17 values the game writes (config_saved_record's order), with own[] for a line still applied */
    uint32_t word = guest_u32(ctx, FIELD_ADDR(GameConfigData, self, option_bits));
    uint8_t bytes[15];
    for (uint32_t k = 0; k < 15; k++)
        bytes[k] = guest_u8(ctx, FIELD_ADDR(GameConfigData, self, battle_mode) + k);
    for (int i = 0; i < MN_OPT_LINES; i++) {
        if (!(mn_opt.lines & mn_opt_lines[i].bit))
            continue;
        uint8_t *b = &bytes[mn_opt_lines[i].offset - 0x8u];
        if (*b == mn_opt.applied[i])
            *b = mn_opt.own[i]; /* the PC value: the save keeps the game's own */
        else
            mn_opt.own[i] = *b; /* changed on the game's own screen since: that is the new own value */
    }
    FeState entry;
    fe_save(ctx, &entry);
    int done = 0;
    if (fe_writer_begin(ctx, FE_WRITER_CONFIG_SAVE_GUARD)) {
        (void)fe_writer_call(ctx, MN_StreamWriteByte, stream, 1u, 0u, 0u); /* the record's version */
        (void)fe_writer_call(ctx, MN_StreamWriteLong, stream, word, 0u, 0u);
        for (uint32_t k = 0; k < 15; k++)
            (void)fe_writer_call(ctx, MN_StreamWriteByte, stream, bytes[k], 0u, 0u);
        done = fe_writer_end(ctx, !fe_gave_up(ctx)) == FE_WRITER_OK;
    }
    fe_load(ctx, &entry, 0); /* the registers as they were; a stopped call's exit is cleared */
    if (done) {
        mn_opt.saves++;
        mn_opt.depth--;
        RETURN_TO(ctx->r[14]);
    }
    /* W2 could not run: own[] back into the block first, so the game's own Serialize writes a clean save.
       The bytes only, never the danger zone's rebuild (config_restore_options): the game never runs
       Danger::Update inside a save, and running it here changed what the rest of the battle save holds
       (round 38, OK A T6: 252 bytes of Map0.bak, gone without the rebuild). The zone keeps its tiles from
       the PC value until the game next rebuilds it (a display effect only). */
    ConfigOptionsWanted back;
    memset(&back, 0, sizeof back);
    for (int i = 0; i < MN_OPT_LINES; i++)
        if (mn_opt.lines & mn_opt_lines[i].bit)
            mn_want_set(&back, mn_opt_lines[i].bit, mn_opt.own[i]);
    (void)config_restore_options(ctx, &back); /* refused too: the one residual case (T6) */
    mn_opt.lines = 0; /* the PC choice is dropped until the next load or game reset */
    mn_opt.give_ups++;
    mn_call_original(ctx, original);
    mn_opt.depth--;
}
