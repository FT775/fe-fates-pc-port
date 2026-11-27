/* The first readable writer, kept OFF: set lines of the game's own options
   block (GameConfigData, G_GameConfig) the way the options screen stores
   them. Plain-language rules: docs/WRITERS.md; the block: docs/MENUS.md
   section 1.

   How the game stores a line (read 2026-11-14 in the game's ARM code):
   anonymous_namespace::ConfigItem::KeyCall (0x003BA714) asks the line's
   GetValue, and only when the new value differs calls its SetValue(int),
   then marks the menu for redraw and plays the cursor sound (screen work,
   not the block: not reproduced). The four SetValue bodies:
     Battle::SetValue     0x003BC36C  stores the byte +0x8
     GameSpeed::SetValue  0x003BC968  stores the byte +0xC
     HPGauge::SetValue    0x003BC51C  stores the byte +0x16
     DangerPanel::SetValue 0x003BAF00 stores the byte +0xE, then calls
                          Map::Get and, when it is not 0, tail-calls
                          map::Image::Danger::Update on MapImage +0x1008
                          (a game writer: it rebuilds the zone).
   Each line's value range is its GetNum (5, 3, 2, 3): the screen never
   stores past it, so this writer refuses such a value before it reads or
   stores anything.

   Every store goes through the writer gate (src/readable/core/fe_writer.h):
   OFF unless switched on, never in shadow mode, every store logged with its
   old value and undone exactly on a failure or by fe_writer_undo_last.

   A save carries this block (GameUserData::Serialize writes it into every
   game save): once the block is set, the next save the player makes holds
   these values (docs/WRITERS.md, keep_game_options).

   Status: UNVERIFIED, OFF. Host differential test against the game's own
   GetValue / SetValue code with ordered store and guest-call lists:
   src/readable/menu/tests/writer_diff.py. */

#include "menu_writer.h"

/* Battle::SetValue(int) 0x003BC36C (r0, the line, is not read) */
int config_set_battle(Context *ctx, uint32_t value) {
    gaddr config = guest_ptr(ctx, G_GameConfig);
    return fe_writer_store(ctx, FIELD_ADDR(GameConfigData, config, battle_mode), 1, value);
}

/* GameSpeed::SetValue(int) 0x003BC968 */
int config_set_game_speed(Context *ctx, uint32_t value) {
    gaddr config = guest_ptr(ctx, G_GameConfig);
    return fe_writer_store(ctx, FIELD_ADDR(GameConfigData, config, game_speed), 1, value);
}

/* HPGauge::SetValue(int) 0x003BC51C */
int config_set_hp_gauge(Context *ctx, uint32_t value) {
    gaddr config = guest_ptr(ctx, G_GameConfig);
    return fe_writer_store(ctx, FIELD_ADDR(GameConfigData, config, hp_gauge), 1, value);
}

/* DangerPanel::SetValue(int) 0x003BAF00: the byte, then the zone is rebuilt
   when a map exists. Map::Get gets the block pointer in r0, as the game
   leaves it there; G_MapImage is read only after Map::Get answered. */
int config_set_danger(Context *ctx, uint32_t value) {
    gaddr config = guest_ptr(ctx, G_GameConfig);
    if (!fe_writer_store(ctx, FIELD_ADDR(GameConfigData, config, danger), 1, value))
        return 0;
    if (fe_writer_call(ctx, MN_MapGet, config, 0u, 0u, 0u) != 0) {
        gaddr map = guest_ptr(ctx, G_MapImage);
        (void)fe_writer_call(ctx, MN_DangerUpdate, FIELD_ADDR(MapImage, map, danger), 0u, 0u, 0u);
    }
    return !fe_gave_up(ctx);
}

/* one line: the screen's compare (GetValue, a reader of this batch), then
   SetValue only when the value differs */
typedef uint32_t (*MnLineValue)(Context *ctx, gaddr item);
typedef int (*MnLineSet)(Context *ctx, uint32_t value);

static void set_line(Context *ctx, MnLineValue get, MnLineSet set, uint32_t value) {
    if (fe_gave_up(ctx))
        return;
    if (get(ctx, 0) != value)
        (void)set(ctx, value);
}

/* DangerPanel::SetValue's store without its rebuild: W1's applies at a load or game reset, and W2's give-up
   restore (inside a save) */
static int config_store_danger(Context *ctx, uint32_t value) {
    gaddr config = guest_ptr(ctx, G_GameConfig);
    return fe_writer_store(ctx, FIELD_ADDR(GameConfigData, config, danger), 1, value);
}

static int mn_write_lines(Context *ctx, const ConfigOptionsWanted *want, int rebuild, int any_byte) {
    /* refused before anything is read or stored */
    if (want == NULL || (want->lines & ~MN_SET_ALL) != 0)
        return FE_WRITER_REFUSED;
    /* a screen choice: never past the line's last value. W2's restore (any_byte) puts back the save's own
       byte, whatever it is (a save may hold a value the screen never offers; refusing it left the PC value in
       the next save: round 38, w12_diff clean saves), but never more than a byte */
    uint32_t last[4] = {4u, 2u, 2u, 1u};
    if (any_byte)
        last[0] = last[1] = last[2] = last[3] = 0xFFu;
    if (((want->lines & MN_SET_BATTLE) && want->battle > last[0]) ||
        ((want->lines & MN_SET_GAME_SPEED) && want->game_speed > last[1]) ||
        ((want->lines & MN_SET_DANGER) && want->danger > last[2]) ||
        ((want->lines & MN_SET_HP_GAUGE) && want->hp_gauge > last[3]))
        return FE_WRITER_REFUSED;
    if (!fe_writer_begin(ctx, FE_WRITER_CONFIG_OPTIONS))
        return FE_WRITER_OFF;
    FeState entry;
    fe_save(ctx, &entry);
    if (want->lines & MN_SET_BATTLE)
        set_line(ctx, config_battle_value, config_set_battle, want->battle);
    if (want->lines & MN_SET_GAME_SPEED)
        set_line(ctx, config_game_speed_value, config_set_game_speed, want->game_speed);
    if (want->lines & MN_SET_DANGER)
        set_line(ctx, config_danger_value, rebuild ? config_set_danger : config_store_danger, want->danger);
    if (want->lines & MN_SET_HP_GAUGE)
        set_line(ctx, config_hp_gauge_value, config_set_hp_gauge, want->hp_gauge);
    int result = fe_writer_end(ctx, !fe_gave_up(ctx));
    fe_load(ctx, &entry, 0); /* the registers as they were; the time spent stays charged */
    return result;
}

int config_write_options(Context *ctx, const ConfigOptionsWanted *want) { return mn_write_lines(ctx, want, 1, 0); }

/* W1's apply (src/readable/menu/menu_options_hook.c), right after the game's own Deserialize or Reset of the
   global block: the screen's compare-then-store and value range for every line, but the danger line stores its
   byte only. The game rebuilds the zone itself after a load (two Danger::Update calls, lr 0x001DA1B8 and
   0x00397104, with the stored byte already in place), and a rebuild inside the load, while the map is still
   being set up, changed what the map start allocates: 2,554 bytes of the heap laid out differently from the
   game's own (round 40, OK A T2 danger 2 -> 0; docs/OPTIONS_WIRING.md section 15). */
int config_apply_options(Context *ctx, const ConfigOptionsWanted *want) { return mn_write_lines(ctx, want, 0, 0); }

/* W2's give-up restore (src/readable/menu/menu_options_hook.c): the same compare-then-store for every
   line, any byte value (the save's own), but the danger line stores its byte only. The game never rebuilds the zone inside a save, and a
   rebuild there changed the rest of the battle save (round 38, OK A T6). */
int config_restore_options(Context *ctx, const ConfigOptionsWanted *want) { return mn_write_lines(ctx, want, 0, 1); }
