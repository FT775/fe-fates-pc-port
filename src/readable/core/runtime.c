/* Run-time switches and logging of the readable layer (docs/READABLE.md).

   FE_READABLE      original | readable | shadow | capture   (default: shadow)
   FE_READABLE_LOG  file to append the log to                 (default: stderr)

   capture is opt-in and only for the tier-4 harness (docs/HARNESS.md 3.1,
   src/readable/core/capture.c): the originals run, sampled calls are recorded
   and compared live. An unknown value keeps the default.

   The mode is read once, on the first override call. The counters are plain
   globals: an occasional lost count when two host threads run overrides at
   once only affects the log, never the game. This file has no override. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fe.h"
#include "fe_writer.h"

/* the writer gate's run totals (fe_writer.h): here, not in writer.c, so capture.c can write them into its
   summary in every build that has it, also the host tests that do not link writer.c */
uint32_t fe_writer_totals[FE_WT_COUNT];

#ifndef FE_DEFAULT_MODE
#define FE_DEFAULT_MODE FE_MODE_SHADOW /* every pilot function is unverified */
#endif

#define FE_LOG_FIRST 20      /* lines logged per function and kind before thinning out */
#define FE_LOG_EVERY 1000    /* afterwards, one line per this many */
/* distinct functions counted: must stay above the number of override rows in
   config/readable/functions.csv (tools/readable/check.py enforces it); a full table
   would make counts share slot 0. Power of two with room to grow (281 overrides on
   2026-11-10). Only override rows count: harness probes must not use fe_counts_of
   unless check.py also counts them (docs/HARNESS.md 3.2). */
#define FE_TRACKED 1024

static int fe_mode_value = -1;
static FILE *fe_log_file;

static FILE *fe_log(void) {
    if (fe_log_file == NULL) {
        const char *path = getenv("FE_READABLE_LOG");
        fe_log_file = path && *path ? fopen(path, "a") : NULL;
        if (fe_log_file == NULL)
            fe_log_file = stderr;
    }
    return fe_log_file;
}

FILE *fe_log_stream(void) { return fe_log(); }

static const char *fe_mode_name(int mode) {
    return mode == FE_MODE_ORIGINAL   ? "original"
           : mode == FE_MODE_READABLE ? "readable"
           : mode == FE_MODE_CAPTURE  ? "capture"
                                      : "shadow";
}

int fe_mode(void) {
    if (fe_mode_value < 0) {
        const char *v = getenv("FE_READABLE");
        int mode = FE_DEFAULT_MODE;
        if (v && (!strcmp(v, "original") || !strcmp(v, "off") || !strcmp(v, "0")))
            mode = FE_MODE_ORIGINAL;
        else if (v && (!strcmp(v, "readable") || !strcmp(v, "on") || !strcmp(v, "1")))
            mode = FE_MODE_READABLE;
        else if (v && !strcmp(v, "shadow"))
            mode = FE_MODE_SHADOW;
        else if (v && !strcmp(v, "capture"))
            mode = FE_MODE_CAPTURE; /* opt-in only: never a default */
        fe_mode_value = mode;
        fprintf(fe_log(), "[fe-readable] mode %s (set FE_READABLE=original|readable|shadow|capture)\n", fe_mode_name(mode));
        fflush(fe_log());
    }
    return fe_mode_value;
}

/* per function: how often each kind of event happened */
typedef struct FeCounts {
    uint32_t address;
    uint32_t events[3];
    uint32_t mismatches;
} FeCounts;

static FeCounts fe_counts[FE_TRACKED];

static FeCounts *fe_counts_of(uint32_t address) {
    uint32_t at = (address >> 2) % FE_TRACKED;
    for (int i = 0; i < FE_TRACKED; i++, at = (at + 1) % FE_TRACKED) {
        if (fe_counts[at].address == address || fe_counts[at].address == 0) {
            fe_counts[at].address = address;
            return &fe_counts[at];
        }
    }
    return &fe_counts[0]; /* table full: counts get shared, logging still works */
}

static int fe_worth_logging(uint32_t n) { return n <= FE_LOG_FIRST || n % FE_LOG_EVERY == 0; }

void fe_event(int event, uint32_t address, const char *name) {
    static const char *const what[] = {"gave up, the original ran", "shadow skipped (readable gave up)",
                                       "shadow match"};
    FeCounts *c = fe_counts_of(address);
    uint32_t n = ++c->events[event];
    if (event == FE_EVENT_SHADOW_MATCH) {
        /* one line when a function first matches, then a heartbeat */
        if (n == 1 || n % (FE_LOG_EVERY * 100) == 0)
            fprintf(fe_log(), "[fe-readable] 0x%08X %s: %s (%u so far, %u mismatches)\n", address, name, what[event], n,
                    c->mismatches);
        return;
    }
    if (fe_worth_logging(n)) {
        /* flushed: verify reads "gave up" lines to tell a real pass from a bail-out */
        fprintf(fe_log(), "[fe-readable] 0x%08X %s: %s (%u)\n", address, name, what[event], n);
        fflush(fe_log());
    }
}

/* for tests and a future debug overlay */
void fe_force_mode(int mode) { fe_mode_value = mode; }
uint32_t fe_mismatch_count(uint32_t address) { return fe_counts_of(address)->mismatches; }
uint32_t fe_event_count(int event, uint32_t address) { return fe_counts_of(address)->events[event]; }

void fe_shadow_mismatch(uint32_t address, const char *name, const FeState *entry, uint32_t game, uint32_t readable) {
    FeCounts *c = fe_counts_of(address);
    uint32_t n = ++c->mismatches;
    if (!fe_worth_logging(n))
        return;
    fprintf(fe_log(),
            "[fe-readable] MISMATCH 0x%08X %s(r0=%08X r1=%08X r2=%08X r3=%08X): game %08X (%d), readable %08X (%d)"
            " [%u mismatches, %u matches]\n",
            address, name, entry->r[0], entry->r[1], entry->r[2], entry->r[3], game, (int32_t)game, readable,
            (int32_t)readable, n, c->events[FE_EVENT_SHADOW_MATCH]);
    fflush(fe_log());
}
