/* The PC options file reader (src/readable/core/fe_options.h; the rules and
   why: docs/OPTIONS_WIRING.md sections 4 step 2 and 6). Host code below the
   readable layer: it opens one file for reading, never guest memory, never
   writes anything, never opens a path inside %APPDATA% or %LOCALAPPDATA%.

   The parse is the FE options page's own (tools/zakuro-options patch 0002,
   fe_options::parse with parse_max), kept to the byte: Rust's str::lines,
   str::trim (Unicode White_Space), split_once('='), u8::from_str and
   "value <= the line's last value, else 0".

   Status: UNVERIFIED in a game (no writer is armed: nothing calls this in any
   library build today). Host tests: src/readable/menu/tests/w12_diff.py
   (--options: the shared test lines, src/readable/core/tests/options_cases.json). */

#if defined(_MSC_VER) && !defined(_CRT_SECURE_NO_WARNINGS)
#define _CRT_SECURE_NO_WARNINGS /* fopen / getenv: plain C, no _s variants */
#endif

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fe_options.h"

static const struct {
    const char *key;
    uint8_t last; /* the page's GAME list length */
} fe_options_lines[FE_OPT_COUNT] = {
    {"danger_zone", 2},
    {"hp_bars", 2},
    {"animation_skip", 2},
    {"anim_speed", 3},
};

/* one UTF-8 character at s[i] (valid input only): its code point and length */
static uint32_t fe_utf8_at(const unsigned char *s, size_t i, size_t *n) {
    unsigned char c = s[i];
    if (c < 0x80) {
        *n = 1;
        return c;
    }
    if (c < 0xE0) {
        *n = 2;
        return ((uint32_t)(c & 0x1F) << 6) | (s[i + 1] & 0x3F);
    }
    if (c < 0xF0) {
        *n = 3;
        return ((uint32_t)(c & 0x0F) << 12) | ((uint32_t)(s[i + 1] & 0x3F) << 6) | (s[i + 2] & 0x3F);
    }
    *n = 4;
    return ((uint32_t)(c & 0x07) << 18) | ((uint32_t)(s[i + 1] & 0x3F) << 12) | ((uint32_t)(s[i + 2] & 0x3F) << 6) |
           (s[i + 3] & 0x3F);
}

/* strict UTF-8, as Rust's String::from_utf8 (read_to_string): no overlong
   form, no surrogate, nothing past U+10FFFF */
static int fe_utf8_valid(const unsigned char *s, size_t len) {
    size_t i = 0;
    while (i < len) {
        unsigned char c = s[i];
        size_t n;
        uint32_t lo = 0x80, hi = 0xBF;
        if (c < 0x80) {
            i++;
            continue;
        }
        if (c >= 0xC2 && c <= 0xDF)
            n = 2;
        else if (c >= 0xE0 && c <= 0xEF) {
            n = 3;
            if (c == 0xE0)
                lo = 0xA0;
            if (c == 0xED)
                hi = 0x9F;
        } else if (c >= 0xF0 && c <= 0xF4) {
            n = 4;
            if (c == 0xF0)
                lo = 0x90;
            if (c == 0xF4)
                hi = 0x8F;
        } else
            return 0;
        if (len - i < n)
            return 0;
        if (s[i + 1] < lo || s[i + 1] > hi)
            return 0;
        for (size_t k = 2; k < n; k++)
            if (s[i + k] < 0x80 || s[i + k] > 0xBF)
                return 0;
        i += n;
    }
    return 1;
}

/* Rust's char::is_whitespace (the Unicode White_Space property) */
static int fe_is_space(uint32_t c) {
    return (c >= 0x09 && c <= 0x0D) || c == 0x20 || c == 0x85 || c == 0xA0 || c == 0x1680 ||
           (c >= 0x2000 && c <= 0x200A) || c == 0x2028 || c == 0x2029 || c == 0x202F || c == 0x205F || c == 0x3000;
}

/* str::trim on s[*b .. *e) (valid UTF-8): moves *b and *e inwards */
static void fe_trim(const unsigned char *s, size_t *b, size_t *e) {
    while (*b < *e) {
        size_t n;
        if (!fe_is_space(fe_utf8_at(s, *b, &n)))
            break;
        *b += n;
    }
    while (*e > *b) {
        size_t start = *e - 1, n;
        while (start > *b && (s[start] & 0xC0) == 0x80) /* back to the first byte of the last character */
            start--;
        if (!fe_is_space(fe_utf8_at(s, start, &n)))
            break;
        *e = start;
    }
}

/* u8::from_str, then "at most last" (fe_options::parse_max); -1 when refused */
static int fe_parse_max(const unsigned char *s, size_t b, size_t e, uint8_t last) {
    if (b < e && s[b] == '+' && e - b > 1)
        b++;
    if (b >= e)
        return -1;
    unsigned value = 0;
    for (size_t i = b; i < e; i++) {
        if (s[i] < '0' || s[i] > '9')
            return -1;
        value = value * 10u + (unsigned)(s[i] - '0');
        if (value > 255u)
            return -1;
    }
    return value <= last ? (int)value : -1;
}

int fe_options_parse(const char *text, size_t len, FeOptions *out) {
    const unsigned char *s = (const unsigned char *)text;
    memset(out, 0, sizeof *out);
    if (text == NULL || !fe_utf8_valid(s, len))
        return 0;
    size_t at = 0;
    while (at < len) {
        size_t end = at;
        while (end < len && s[end] != '\n')
            end++;
        size_t b = at, e = end, next = end < len ? end + 1 : len;
        if (e > b && s[e - 1] == '\r') /* str::lines drops one '\r' before '\n' (trim would too) */
            e--;
        at = next;
        fe_trim(s, &b, &e);
        if (b == e || s[b] == '#')
            continue;
        size_t eq = b;
        while (eq < e && s[eq] != '=')
            eq++;
        if (eq == e)
            continue; /* no '=': kept by the page as a line it does not own; nothing here */
        size_t kb = b, ke = eq, vb = eq + 1, ve = e;
        fe_trim(s, &kb, &ke);
        fe_trim(s, &vb, &ve);
        for (int k = 0; k < FE_OPT_COUNT; k++) {
            size_t n = strlen(fe_options_lines[k].key);
            if (ke - kb == n && memcmp(s + kb, fe_options_lines[k].key, n) == 0) {
                int v = fe_parse_max(s, vb, ve, fe_options_lines[k].last);
                out->line[k] = (uint8_t)(v < 0 ? 0 : v); /* the last line wins, a bad one too */
                break;
            }
        }
    }
    for (int k = 0; k < FE_OPT_COUNT; k++)
        if (out->line[k])
            return 1;
    return 0;
}

/* 1 when path lies inside the folder named by the environment variable var
   (case and slash direction ignored) */
static int fe_path_inside(const char *path, const char *var) {
    const char *dir = getenv(var);
    if (dir == NULL || dir[0] == '\0')
        return 0;
    size_t n = strlen(dir);
    while (n > 0 && (dir[n - 1] == '\\' || dir[n - 1] == '/'))
        n--;
    if (n == 0)
        return 0;
    for (size_t i = 0; i < n; i++) {
        char a = path[i], b = dir[i];
        if (a == '\0')
            return 0;
        if (a == '/')
            a = '\\';
        if (b == '/')
            b = '\\';
        if (a >= 'A' && a <= 'Z')
            a = (char)(a - 'A' + 'a');
        if (b >= 'A' && b <= 'Z')
            b = (char)(b - 'A' + 'a');
        if (a != b)
            return 0;
    }
    return path[n] == '\0' || path[n] == '\\' || path[n] == '/';
}

int fe_options_read_path(const char *path, FeOptions *out) {
    memset(out, 0, sizeof *out);
    if (path == NULL || path[0] == '\0')
        return 0;
    if (fe_path_inside(path, "APPDATA") || fe_path_inside(path, "LOCALAPPDATA"))
        return 0; /* never read there (the owner's Zakuro settings and saves live there) */
    FILE *f = fopen(path, "rb");
    if (f == NULL)
        return 0;
    static char buf[FE_OPTIONS_MAX_BYTES + 1];
    size_t n = fread(buf, 1, sizeof buf, f);
    int bad = ferror(f);
    fclose(f);
    if (bad || n > FE_OPTIONS_MAX_BYTES)
        return 0; /* unreadable, or larger than 64 KB: treated as empty */
    return fe_options_parse(buf, n, out);
}

int fe_options_read(FeOptions *out) {
    const char *path = getenv("FE_OPTIONS");
    if (path == NULL || path[0] == '\0')
        path = getenv("FEF_OPTIONS");
    return fe_options_read_path(path, out);
}
