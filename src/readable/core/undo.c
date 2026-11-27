/* The undo log (include/readable/fe_undo.h, docs/READABLE.md "The undo log",
   docs/tracks/WRITER_HOOKS.md). H8 groundwork: DISABLED, nothing calls it.

   Built like capture.c's recording host: write_pages is pointed at a table of
   null pointers so every store reaches a host callback. read_pages is never
   touched (reads stay real). Forwarded callbacks (reads, lookup) see the real
   write_pages and host, as capture.c's fe_cap_fwd_begin / fe_cap_fwd_end do;
   any table the host switches to while forwarding is kept (read_pages
   directly, write_pages and host through fe_undo_real_*). The log keeps the
   host pointer of every byte it changed, so a restore writes exactly the
   byte the store changed even if the host switched tables since.

   State is static: one Context on one host thread at a time. This file has
   no override. */

#include <stdatomic.h>
#include <stdlib.h>

#include "fe_undo.h"

#define FE_UNDO_PAGES_IN_SPACE (1u << 20)

/* the log: the host byte each store changed and its old value, oldest first */
static uint8_t *fe_undo_byte[FE_UNDO_MAX_BYTES];
static uint8_t fe_undo_old[FE_UNDO_MAX_BYTES];
static uint32_t fe_undo_count;                 /* entries in the log */
static uint32_t fe_undo_limit = FE_UNDO_MAX_BYTES;
static uint32_t fe_undo_frames[FE_UNDO_MAX_DEPTH]; /* fe_undo_count when each frame began */
static int fe_undo_open;                       /* open frames */
static int fe_undo_fail;                       /* FE_UNDO_OK or the first reason the stack failed */
static Context *fe_undo_ctx;                   /* the Context that holds the log */
static uint8_t **fe_undo_null_table;           /* 2^20 null pointers, allocated on first use */
static uint8_t *const *fe_undo_real_write;     /* the game's fields while a frame is open */
static const Host *fe_undo_real_host;
static atomic_int fe_undo_busy;                /* a host thread holds the log */
static _Thread_local int fe_undo_owner;

static const Host fe_undo_host;

/* ------------------------------------------------------------------------
   Forwarding a callback to the real host, with the real fields in place */

typedef struct FeUndoFwd {
    uint8_t *const *write_pages;
    const Host *host;
} FeUndoFwd;

/* read_pages is already the real table: it is left alone both ways */
static void fe_undo_fwd_begin(Context *ctx, FeUndoFwd *f) {
    f->write_pages = ctx->write_pages;
    f->host = ctx->host;
    ctx->write_pages = fe_undo_real_write;
    ctx->host = fe_undo_real_host;
}

static void fe_undo_fwd_end(Context *ctx, const FeUndoFwd *f) {
    fe_undo_real_write = ctx->write_pages; /* the host may have switched tables */
    fe_undo_real_host = ctx->host;
    ctx->write_pages = f->write_pages;
    ctx->host = f->host;
}

/* the whole stack fails: every open frame will roll back */
static void fe_undo_give_up(Context *ctx, int why) {
    if (fe_undo_fail == FE_UNDO_OK)
        fe_undo_fail = why;
    ctx->exit = EXIT_UNWIND;
}

/* ------------------------------------------------------------------------
   The undo host */

static uint32_t fe_undo_read(Context *ctx, uint32_t address, uint32_t width) {
    FeUndoFwd f;
    uint32_t v;
    fe_undo_fwd_begin(ctx, &f);
    v = width == 1 ? fe_undo_real_host->read8(ctx, address)
        : width == 2 ? fe_undo_real_host->read16(ctx, address) : fe_undo_real_host->read32(ctx, address);
    fe_undo_fwd_end(ctx, &f);
    return v;
}

static void fe_undo_write(Context *ctx, uint32_t address, uint32_t width, uint32_t value) {
    for (uint32_t k = 0; k < width; k++) /* all or nothing: check every byte first */
        if (fe_undo_real_write[(address + k) >> 12] == NULL) {
            fe_undo_give_up(ctx, FE_UNDO_FAIL_HOSTMEM); /* cannot be undone: dropped */
            return;
        }
    if (fe_undo_count + width > fe_undo_limit) {
        fe_undo_give_up(ctx, FE_UNDO_FAIL_OVERFLOW); /* dropped; the log is kept whole */
        return;
    }
    for (uint32_t k = 0; k < width; k++) {
        uint32_t a = address + k;
        uint8_t *byte = &fe_undo_real_write[a >> 12][a & 0xFFFu];
        fe_undo_byte[fe_undo_count] = byte;
        fe_undo_old[fe_undo_count] = *byte;
        fe_undo_count++;
        *byte = (uint8_t)(value >> (8 * k));
    }
}

static uint8_t fe_undo_read8(Context *ctx, uint32_t a) { return (uint8_t)fe_undo_read(ctx, a, 1); }
static uint16_t fe_undo_read16(Context *ctx, uint32_t a) { return (uint16_t)fe_undo_read(ctx, a, 2); }
static uint32_t fe_undo_read32(Context *ctx, uint32_t a) { return fe_undo_read(ctx, a, 4); }
static void fe_undo_write8(Context *ctx, uint32_t a, uint8_t v) { fe_undo_write(ctx, a, 1, v); }
static void fe_undo_write16(Context *ctx, uint32_t a, uint16_t v) { fe_undo_write(ctx, a, 2, v); }
static void fe_undo_write32(Context *ctx, uint32_t a, uint32_t v) { fe_undo_write(ctx, a, 4, v); }

static void fe_undo_interpret(Context *ctx, uint32_t address, uint32_t opcode) {
    (void)address;
    (void)opcode;
    fe_undo_give_up(ctx, FE_UNDO_FAIL_INTERP); /* never forwarded: its stores would not be logged */
}

static void fe_undo_svc(Context *ctx, uint32_t number) {
    (void)number;
    fe_undo_give_up(ctx, FE_UNDO_FAIL_SVC); /* never forwarded: no rollback after an svc */
}

static Code fe_undo_lookup(Context *ctx, uint32_t address) {
    FeUndoFwd f;
    fe_undo_fwd_begin(ctx, &f);
    Code code = fe_undo_real_host->lookup(ctx, address);
    fe_undo_fwd_end(ctx, &f);
    return code;
}

static const Host fe_undo_host = {fe_undo_read8,  fe_undo_read16,    fe_undo_read32,
                                  fe_undo_write8, fe_undo_write16,   fe_undo_write32,
                                  fe_undo_interpret, fe_undo_lookup, fe_undo_svc};

/* ------------------------------------------------------------------------
   Frames */

int fe_undo_begin(Context *ctx) {
    if (fe_undo_open > 0) {
        if (!fe_undo_owner || ctx != fe_undo_ctx || fe_undo_open >= FE_UNDO_MAX_DEPTH ||
            fe_undo_fail != FE_UNDO_OK)
            return 0;
        fe_undo_frames[fe_undo_open++] = fe_undo_count;
        return 1;
    }
    int expected = 0;
    if (!atomic_compare_exchange_strong(&fe_undo_busy, &expected, 1))
        return 0; /* another host thread holds the log */
    if (fe_undo_null_table == NULL)
        fe_undo_null_table = calloc(FE_UNDO_PAGES_IN_SPACE, sizeof *fe_undo_null_table);
    if (fe_undo_null_table == NULL) {
        atomic_store(&fe_undo_busy, 0);
        return 0;
    }
    fe_undo_owner = 1;
    fe_undo_ctx = ctx;
    fe_undo_count = 0;
    fe_undo_fail = FE_UNDO_OK;
    fe_undo_real_write = ctx->write_pages;
    fe_undo_real_host = ctx->host;
    ctx->write_pages = (uint8_t *const *)fe_undo_null_table;
    ctx->host = &fe_undo_host;
    fe_undo_frames[0] = 0;
    fe_undo_open = 1;
    return 1;
}

int fe_undo_end(Context *ctx, int keep) {
    if (fe_undo_open <= 0 || !fe_undo_owner || ctx != fe_undo_ctx)
        return 0; /* no frame of this Context: nothing logged here */
    uint32_t start = fe_undo_frames[fe_undo_open - 1];
    keep = keep && ctx->exit == EXIT_NONE && fe_undo_fail == FE_UNDO_OK;
    if (!keep) {
        while (fe_undo_count > start) { /* newest first: a byte stored twice gets its oldest value */
            fe_undo_count--;
            /* the logged host byte, not a fresh table lookup: a table switch
               in a forwarded callback cannot redirect or skip the restore */
            *fe_undo_byte[fe_undo_count] = fe_undo_old[fe_undo_count];
        }
    }
    /* kept by an inner frame: the entries stay and now belong to the parent */
    fe_undo_open--;
    if (fe_undo_open == 0) {
        fe_undo_count = 0; /* the outermost frame commits (or has just restored everything) */
        fe_undo_fail = FE_UNDO_OK;
        ctx->write_pages = fe_undo_real_write;
        ctx->host = fe_undo_real_host;
        fe_undo_ctx = NULL;
        fe_undo_owner = 0;
        atomic_store(&fe_undo_busy, 0);
    }
    return keep;
}

int fe_undo_depth(void) { return fe_undo_open; }
uint32_t fe_undo_logged(void) { return fe_undo_count; }
int fe_undo_failure(void) { return fe_undo_fail; }

int fe_undo_set_limit(uint32_t bytes) {
    if (fe_undo_open > 0 || bytes > FE_UNDO_MAX_BYTES)
        return 0;
    fe_undo_limit = bytes ? bytes : FE_UNDO_MAX_BYTES;
    return 1;
}
