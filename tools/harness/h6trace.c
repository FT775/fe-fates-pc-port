/* h6trace.c: the block trace of h6sample.py's trace build of replay.exe (H6 sampled mode,
   docs/harness/H56.md section 9). Never part of a normal replay.exe, the capture library or the game.

   The readable sources outside src/readable/core/ are compiled with -fsanitize-coverage=trace-pc,
   so GCC calls __sanitizer_cov_trace_pc() at the start of every basic block they run. replay.c,
   built with -DFE_REPLAY_TRACE, calls fe_trace_begin() before each record and fe_trace_end(out)
   after it, just before the record's JSON line is closed. fe_trace_end adds
       ,"path":"<16 hex>"                    the record's block set, hashed (FNV-1a over the sorted
                                             block offsets); "0000000000000000" = no readable block ran
       ,"blocks":["<hex>",...]               the sorted block offsets, only the first time this process
                                             prints that path (h6sample.py keeps the map)
       ,"trace_full":1                       only if more than TR_SLOTS/2 distinct blocks ran (the set
                                             was cut; the record is then always kept in the sample)
   A block offset is the block's return address minus the address of fe_trace_begin: the same in
   every process whatever the load address (ASLR), as long as the trace build is the same. */

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

void fe_trace_begin(void);
void fe_trace_end(FILE *out);
void __sanitizer_cov_trace_pc(void);

#define TR_SLOTS 16384u     /* blocks per record (open addressing, power of two) */
#define TR_SEEN 262144u     /* distinct paths printed per process */

static uintptr_t tr_set[TR_SLOTS];
static unsigned tr_count, tr_full;
static int tr_on;
static uint64_t tr_seen[TR_SEEN];
static unsigned tr_seen_count;

void __sanitizer_cov_trace_pc(void) {
    if (!tr_on)
        return;
    uintptr_t pc = (uintptr_t)__builtin_return_address(0);
    if (pc == 0)
        return;
    unsigned h = (unsigned)((pc * 0x9E3779B97F4A7C15ull) >> 40) & (TR_SLOTS - 1);
    for (;;) {
        if (tr_set[h] == pc)
            return;
        if (tr_set[h] == 0)
            break;
        h = (h + 1) & (TR_SLOTS - 1);
    }
    if (tr_count >= TR_SLOTS / 2) {
        tr_full = 1;
        return;
    }
    tr_set[h] = pc;
    tr_count++;
}

void fe_trace_begin(void) {
    for (unsigned i = 0; i < TR_SLOTS; i++)
        tr_set[i] = 0;
    tr_count = 0;
    tr_full = 0;
    tr_on = 1;
}

static int tr_cmp(const void *a, const void *b) {
    int64_t x = *(const int64_t *)a, y = *(const int64_t *)b;
    return x < y ? -1 : x > y;
}

void fe_trace_end(FILE *out) {
    tr_on = 0;
    static int64_t offs[TR_SLOTS];
    unsigned n = 0;
    intptr_t base = (intptr_t)(uintptr_t)&fe_trace_begin;
    for (unsigned i = 0; i < TR_SLOTS; i++)
        if (tr_set[i])
            offs[n++] = (int64_t)((intptr_t)tr_set[i] - base);
    qsort(offs, n, sizeof offs[0], tr_cmp);
    uint64_t hash = 0;
    if (n) {
        hash = 1469598103934665603ull;
        for (unsigned i = 0; i < n; i++)
            for (int b = 0; b < 8; b++) {
                hash ^= (uint64_t)((offs[i] >> (8 * b)) & 0xFF);
                hash *= 1099511628211ull;
            }
        if (hash == 0)
            hash = 1;
    }
    fprintf(out, ",\"path\":\"%016" PRIx64 "\"", hash);
    if (tr_full)
        fprintf(out, ",\"trace_full\":1");
    if (!n)
        return;
    unsigned h = (unsigned)((hash * 0x9E3779B97F4A7C15ull) >> 40) & (TR_SEEN - 1);
    for (;;) {
        if (tr_seen[h] == hash)
            return; /* printed before: h6sample.py has its blocks */
        if (tr_seen[h] == 0)
            break;
        h = (h + 1) & (TR_SEEN - 1);
    }
    if (tr_seen_count < TR_SEEN / 2) {
        tr_seen[h] = hash;
        tr_seen_count++;
    }
    fputs(",\"blocks\":[", out);
    for (unsigned i = 0; i < n; i++)
        fprintf(out, "%s\"%" PRIx64 "\"", i ? "," : "", (uint64_t)offs[i]);
    fputs("]", out);
}
