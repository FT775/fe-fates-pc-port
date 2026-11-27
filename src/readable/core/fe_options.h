/* The PC options file, read by the readable library (docs/OPTIONS_WIRING.md
   sections 2, 4 step 2 and 6). Host code only: it reads one small text file
   and never touches guest memory, never writes a file.

   The file is written by the FE options page (tools/zakuro-options, patch
   0002, `fe_options::parse` / `render`). This reader keeps exactly the page's
   rules for the four lines the game's own options screen already has:

     danger_zone    0 .. 2   (0 = the game's choice)
     hp_bars        0 .. 2
     animation_skip 0 .. 2
     anim_speed     0 .. 3

   - the path is FE_OPTIONS, else FEF_OPTIONS (the game's own prefix); unset or
     empty: no file, every line 0;
   - a file that is missing, unreadable, not valid UTF-8 or larger than
     FE_OPTIONS_MAX_BYTES is treated as empty (every line 0);
   - a path inside %APPDATA% or %LOCALAPPDATA% is never opened (every line 0);
   - lines are split at '\n' (a '\r' before it goes with the trim); each line
     is trimmed of Unicode white space (Rust's str::trim); empty lines and lines
     starting with '#' are skipped; a line without '=' is skipped; key and value
     are the trimmed text before and after the first '=';
   - a value is Rust's u8 parse (ASCII digits, one optional leading '+', no
     '-', at most 255) and must be at most the line's last value; anything else
     is 0 ("the game's choice");
   - an unknown key is ignored; when a key occurs twice the last line wins, a
     bad last value included (it gives 0).

   The test lines shared with the page: src/readable/core/tests/options_cases.json
   (checked by src/readable/menu/tests/w12_diff.py --options).

   Status: UNVERIFIED in a game (no writer is armed). Host tests only. */

#ifndef FE_OPTIONS_H
#define FE_OPTIONS_H

#include <stddef.h>
#include <stdint.h>

#define FE_OPTIONS_MAX_BYTES 65536u

enum { FE_OPT_DANGER_ZONE = 0, FE_OPT_HP_BARS = 1, FE_OPT_ANIMATION_SKIP = 2, FE_OPT_ANIM_SPEED = 3, FE_OPT_COUNT = 4 };

typedef struct FeOptions {
    uint8_t line[FE_OPT_COUNT]; /* the page's values, 0 = the game's choice */
} FeOptions;

/* the page's parse of text[0 .. len): fills out (every line 0 first); text
   that is not valid UTF-8 gives every line 0. Returns 1 when a line is not 0. */
int fe_options_parse(const char *text, size_t len, FeOptions *out);

/* reads the file named by FE_OPTIONS / FEF_OPTIONS (above). Returns 1 when a
   line is not 0; every line 0 for no file and every doubt. */
int fe_options_read(FeOptions *out);

/* the same with the path given (NULL or "" = no file) */
int fe_options_read_path(const char *path, FeOptions *out);

#endif /* FE_OPTIONS_H */
