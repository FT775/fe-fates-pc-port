/* The writer gate and the writer undo log (src/readable/core/fe_writer.h,
   docs/WRITERS.md). Game-agnostic.

   Every writer is compiled in and OFF: the `armed` column below is 0 for
   every writer. Switching one on takes a source edit here (after robot H6
   and an owner OK, docs/WRITERS.md) AND its name in FE_WRITERS AND
   FE_READABLE=readable. Nothing here reads a report, the registry or a file.

   Stores are made through the direct page pointers of write_pages (the
   game's own fields), never through mem_write: a byte without a pointer
   cannot be put back exactly, so such a store is refused. Inside
   fe_writer_call the gate's own host is installed with write_pages pointed
   at a table of null pointers, the way src/readable/core/undo.c does it
   (read there for the reasons), so the callee's stores are logged too.

   State is static: one session, one Context, one host thread at a time.
   UNVERIFIED: tested on fakes only (src/readable/core/tests/
   writer_gate_test.py). This file has no override. */

#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>

#include "fe_writer.h"

#define FE_WRITER_PAGES_IN_SPACE (1u << 20)

typedef struct FeWriterInfo {
    const char *name; /* the FE_WRITERS name */
    int armed;        /* 0 = compiled in, OFF. Changing it needs H6 + an owner OK */
} FeWriterInfo;

/* const in every library build: only the host tests (FE_WRITER_TESTS) may arm */
#ifdef FE_WRITER_TESTS
#define FE_WRITER_TABLE_CONST
#else
#define FE_WRITER_TABLE_CONST const
#endif

static FE_WRITER_TABLE_CONST FeWriterInfo fe_writer_table[FE_WRITER_COUNT] = {
    {"", 0},
    {"config_options", 0},
    {"config_options_hook", 0}, /* W1 (docs/OPTIONS_WIRING.md section 4): OFF */
    {"config_save_guard", 0},   /* W2: OFF */
};

static FeWriterEntry fe_writer_log[FE_WRITER_LOG_MAX];
static uint32_t fe_writer_count;      /* entries in the log */
static uint32_t fe_writer_start;      /* first entry of the open session */
static uint32_t fe_writer_session;    /* number of the open session (0 = none) */
static uint32_t fe_writer_sessions;   /* sessions opened so far */
static int fe_writer_id;              /* writer of the open session */
static int fe_writer_fail;
static uint32_t fe_writer_frame;
static Context *fe_writer_ctx;
static atomic_int fe_writer_busy;
static uint32_t fe_writer_refused, fe_writer_wrong_mode, fe_writer_stray, fe_writer_drop;
static uint32_t fe_writer_stored, fe_writer_restored, fe_writer_opened; /* run totals only (fe_writer_totals) */

/* the run totals the capture summary prints (fe_writer.h, the array in runtime.c) */
static void fe_writer_publish(void) {
    fe_writer_totals[FE_WT_LOG] = fe_writer_count;
    fe_writer_totals[FE_WT_STORES] = fe_writer_stored;
    fe_writer_totals[FE_WT_RESTORED] = fe_writer_restored;
    fe_writer_totals[FE_WT_SESSIONS] = fe_writer_opened;
    fe_writer_totals[FE_WT_REFUSALS] = fe_writer_refused;
    fe_writer_totals[FE_WT_MODE_REFUSALS] = fe_writer_wrong_mode;
    fe_writer_totals[FE_WT_STRAY] = fe_writer_stray;
    fe_writer_totals[FE_WT_DROPPED] = fe_writer_drop;
}

/* FE_WRITERS: the names switched on at run time (read once) */
static int fe_writer_listed[FE_WRITER_COUNT];
static int fe_writer_listed_read;

static void fe_writer_parse(const char *list) {
    memset(fe_writer_listed, 0, sizeof fe_writer_listed);
    fe_writer_listed_read = 1;
    if (list == NULL)
        return;
    for (int w = 1; w < FE_WRITER_COUNT; w++) {
        size_t n = strlen(fe_writer_table[w].name);
        for (const char *p = list; *p;) {
            const char *end = strchr(p, ',');
            size_t len = end ? (size_t)(end - p) : strlen(p);
            if (len == n && n > 0 && strncmp(p, fe_writer_table[w].name, n) == 0)
                fe_writer_listed[w] = 1;
            if (!end)
                break;
            p = end + 1;
        }
    }
}

int fe_writer_switched_on(int writer) {
    if (writer <= FE_WRITER_NONE || writer >= FE_WRITER_COUNT)
        return 0;
    if (!fe_writer_table[writer].armed)
        return 0;
    if (!fe_writer_listed_read)
        fe_writer_parse(getenv("FE_WRITERS"));
    if (!fe_writer_listed[writer])
        return 0;
    return fe_mode() == FE_MODE_READABLE;
}

const char *fe_writer_name(int writer) {
    return writer > FE_WRITER_NONE && writer < FE_WRITER_COUNT ? fe_writer_table[writer].name : "";
}

void fe_writer_set_frame(uint32_t frame) { fe_writer_frame = frame; }

/* ------------------------------------------------------------------------
   The log */

/* room for n more entries: drops the oldest kept sessions whole; 0 when the
   open session alone would not fit */
static int fe_writer_room(uint32_t n) {
    if (fe_writer_count + n <= FE_WRITER_LOG_MAX)
        return 1;
    if ((fe_writer_count - fe_writer_start) + n > FE_WRITER_LOG_MAX)
        return 0;
    uint32_t cut = 0;
    while (fe_writer_count - cut + n > FE_WRITER_LOG_MAX) {
        uint32_t s = fe_writer_log[cut].session; /* drop this whole session */
        while (cut < fe_writer_start && fe_writer_log[cut].session == s)
            cut++;
        fe_writer_drop++;
    }
    memmove(fe_writer_log, fe_writer_log + cut, (fe_writer_count - cut) * sizeof fe_writer_log[0]);
    fe_writer_count -= cut;
    fe_writer_start -= cut;
    fe_writer_publish();
    return 1;
}

static void fe_writer_give_up(Context *ctx, int why) {
    if (fe_writer_fail == FE_WRITER_FAIL_NONE)
        fe_writer_fail = why;
    if (ctx != NULL)
        ctx->exit = EXIT_UNWIND;
}

/* the host byte behind a guest address in the given write table, or NULL */
static uint8_t *fe_writer_byte(uint8_t *const *table, uint32_t a) {
    uint8_t *page = table[a >> 12];
    return page ? page + (a & 0xFFFu) : NULL;
}

/* logs and stores; table = the game's own write table */
static int fe_writer_put(Context *ctx, uint8_t *const *table, uint32_t address, uint32_t size, uint32_t value) {
    if (size != 1 && size != 2 && size != 4) {
        fe_writer_give_up(ctx, FE_WRITER_FAIL_SIZE);
        return 0;
    }
    uint8_t *bytes[4];
    for (uint32_t k = 0; k < size; k++) /* all or nothing: every byte first */
        if ((bytes[k] = fe_writer_byte(table, address + k)) == NULL) {
            fe_writer_give_up(ctx, FE_WRITER_FAIL_HOSTMEM);
            return 0;
        }
    if (!fe_writer_room(1)) {
        fe_writer_give_up(ctx, FE_WRITER_FAIL_FULL);
        return 0;
    }
    FeWriterEntry *e = &fe_writer_log[fe_writer_count++];
    uint32_t old = 0;
    for (uint32_t k = 0; k < size; k++)
        old |= (uint32_t)*bytes[k] << (8 * k);
    e->address = address;
    e->size = size;
    e->old_value = old;
    e->new_value = size == 4 ? value : value & ((1u << (8 * size)) - 1u);
    e->writer = (uint32_t)fe_writer_id;
    e->frame = fe_writer_frame;
    e->session = fe_writer_session;
    for (uint32_t k = 0; k < size; k++)
        *bytes[k] = (uint8_t)(value >> (8 * k));
    fe_writer_stored++;
    fe_writer_publish();
    return 1;
}

/* puts entries [from, fe_writer_count) back, newest first, through table */
static void fe_writer_restore(uint8_t *const *table, uint32_t from) {
    if (fe_writer_count > from)
        fe_writer_restored += fe_writer_count - from;
    while (fe_writer_count > from) {
        FeWriterEntry *e = &fe_writer_log[--fe_writer_count];
        for (uint32_t k = 0; k < e->size; k++) {
            uint8_t *b = fe_writer_byte(table, e->address + k);
            if (b) /* was there at the store; a page that went away cannot be written */
                *b = (uint8_t)(e->old_value >> (8 * k));
        }
    }
    fe_writer_publish();
}

/* ------------------------------------------------------------------------
   The session's host (inside fe_writer_call only) */

static uint8_t *const *fe_writer_real_write; /* the game's fields while a call runs */
static const Host *fe_writer_real_host;
static uint8_t **fe_writer_null_table;       /* 2^20 null pointers, allocated on first use */
static const Host fe_writer_host;

typedef struct FeWriterFwd {
    uint8_t *const *write_pages;
    const Host *host;
} FeWriterFwd;

static void fe_writer_fwd_begin(Context *ctx, FeWriterFwd *f) {
    f->write_pages = ctx->write_pages;
    f->host = ctx->host;
    ctx->write_pages = fe_writer_real_write;
    ctx->host = fe_writer_real_host;
}

static void fe_writer_fwd_end(Context *ctx, const FeWriterFwd *f) {
    fe_writer_real_write = ctx->write_pages; /* the host may have switched tables */
    fe_writer_real_host = ctx->host;
    ctx->write_pages = f->write_pages;
    ctx->host = f->host;
}

static uint32_t fe_writer_read(Context *ctx, uint32_t address, uint32_t width) {
    FeWriterFwd f;
    uint32_t v;
    fe_writer_fwd_begin(ctx, &f);
    v = width == 1 ? fe_writer_real_host->read8(ctx, address)
        : width == 2 ? fe_writer_real_host->read16(ctx, address) : fe_writer_real_host->read32(ctx, address);
    fe_writer_fwd_end(ctx, &f);
    return v;
}

static uint8_t fe_writer_read8(Context *ctx, uint32_t a) { return (uint8_t)fe_writer_read(ctx, a, 1); }
static uint16_t fe_writer_read16(Context *ctx, uint32_t a) { return (uint16_t)fe_writer_read(ctx, a, 2); }
static uint32_t fe_writer_read32(Context *ctx, uint32_t a) { return fe_writer_read(ctx, a, 4); }
static void fe_writer_write8(Context *ctx, uint32_t a, uint8_t v) { (void)fe_writer_put(ctx, fe_writer_real_write, a, 1, v); }
static void fe_writer_write16(Context *ctx, uint32_t a, uint16_t v) { (void)fe_writer_put(ctx, fe_writer_real_write, a, 2, v); }
static void fe_writer_write32(Context *ctx, uint32_t a, uint32_t v) { (void)fe_writer_put(ctx, fe_writer_real_write, a, 4, v); }

static void fe_writer_interpret(Context *ctx, uint32_t address, uint32_t opcode) {
    (void)address;
    (void)opcode;
    fe_writer_give_up(ctx, FE_WRITER_FAIL_INTERP); /* never forwarded: its stores would not be logged */
}

static void fe_writer_svc(Context *ctx, uint32_t number) {
    (void)number;
    fe_writer_give_up(ctx, FE_WRITER_FAIL_SVC); /* never forwarded: no rollback after an svc */
}

static Code fe_writer_lookup(Context *ctx, uint32_t address) {
    FeWriterFwd f;
    fe_writer_fwd_begin(ctx, &f);
    Code code = fe_writer_real_host->lookup(ctx, address);
    fe_writer_fwd_end(ctx, &f);
    return code;
}

static const Host fe_writer_host = {fe_writer_read8,  fe_writer_read16,    fe_writer_read32,
                                    fe_writer_write8, fe_writer_write16,   fe_writer_write32,
                                    fe_writer_interpret, fe_writer_lookup, fe_writer_svc};

/* ------------------------------------------------------------------------
   Sessions */

int fe_writer_begin(Context *ctx, int writer) {
    if (!fe_writer_switched_on(writer)) {
        fe_writer_refused++;
        if (writer > FE_WRITER_NONE && writer < FE_WRITER_COUNT && fe_mode() != FE_MODE_READABLE)
            fe_writer_wrong_mode++; /* shadow, capture or original: never a writer */
        fe_writer_publish();
        return 0;
    }
    if (ctx == NULL || ctx->exit != EXIT_NONE)
        return 0;
    int expected = 0;
    if (!atomic_compare_exchange_strong(&fe_writer_busy, &expected, 1))
        return 0; /* a session is open somewhere */
    fe_writer_ctx = ctx;
    fe_writer_id = writer;
    fe_writer_fail = FE_WRITER_FAIL_NONE;
    fe_writer_start = fe_writer_count;
    fe_writer_session = ++fe_writer_sessions;
    fe_writer_opened++;
    fe_writer_publish();
    return 1;
}

int fe_writer_open(void) { return fe_writer_session != 0; }
int fe_writer_failure(void) { return fe_writer_fail; }

static int fe_writer_in_session(Context *ctx) {
    return fe_writer_session != 0 && ctx == fe_writer_ctx && fe_mode() == FE_MODE_READABLE;
}

int fe_writer_store(Context *ctx, gaddr address, uint32_t size, uint32_t value) {
    if (!fe_writer_in_session(ctx)) {
        fe_writer_stray++; /* no session: nothing is stored */
        fe_writer_publish();
        return 0;
    }
    if (fe_writer_fail != FE_WRITER_FAIL_NONE || ctx->exit != EXIT_NONE)
        return 0;
    return fe_writer_put(ctx, ctx->write_pages, address, size, value);
}

uint32_t fe_writer_call(Context *ctx, gaddr function, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3) {
    if (!fe_writer_in_session(ctx)) {
        fe_writer_stray++;
        fe_writer_publish();
        return 0;
    }
    if (fe_writer_fail != FE_WRITER_FAIL_NONE || ctx->exit != EXIT_NONE)
        return 0;
    if (fe_writer_null_table == NULL)
        fe_writer_null_table = calloc(FE_WRITER_PAGES_IN_SPACE, sizeof *fe_writer_null_table);
    if (fe_writer_null_table == NULL) {
        fe_writer_give_up(ctx, FE_WRITER_FAIL_HOSTMEM);
        return 0;
    }
    fe_writer_real_write = ctx->write_pages;
    fe_writer_real_host = ctx->host;
    ctx->write_pages = (uint8_t *const *)fe_writer_null_table;
    ctx->host = &fe_writer_host;
    uint32_t r = guest_call(ctx, function, a0, a1, a2, a3);
    ctx->write_pages = fe_writer_real_write;
    ctx->host = fe_writer_real_host;
    if (ctx->exit != EXIT_NONE)
        fe_writer_give_up(ctx, FE_WRITER_FAIL_EXIT);
    return r;
}

int fe_writer_end(Context *ctx, int keep) {
    if (fe_writer_session == 0 || ctx != fe_writer_ctx)
        return FE_WRITER_OFF;
    if (ctx->exit != EXIT_NONE && fe_writer_fail == FE_WRITER_FAIL_NONE)
        fe_writer_fail = FE_WRITER_FAIL_EXIT;
    int kept = keep && fe_writer_fail == FE_WRITER_FAIL_NONE;
    if (!kept)
        fe_writer_restore(ctx->write_pages, fe_writer_start);
    fe_writer_session = 0;
    fe_writer_ctx = NULL;
    fe_writer_id = FE_WRITER_NONE;
    atomic_store(&fe_writer_busy, 0);
    return kept ? FE_WRITER_OK : FE_WRITER_ROLLED_BACK;
}

/* 1 when byte b of entry i is the newest store of its session to that byte */
static int fe_writer_newest(uint32_t i, uint32_t a, uint32_t end) {
    for (uint32_t j = i + 1; j < end; j++) {
        const FeWriterEntry *n = &fe_writer_log[j];
        if (a >= n->address && a < n->address + n->size)
            return 0;
    }
    return 1;
}

int fe_writer_undo_last(Context *ctx) {
    if (ctx == NULL || fe_writer_session != 0 || fe_writer_count == 0)
        return FE_WRITER_NOTHING;
    int expected = 0;
    if (!atomic_compare_exchange_strong(&fe_writer_busy, &expected, 1))
        return FE_WRITER_NOTHING;
    uint32_t end = fe_writer_count, from = end;
    uint32_t s = fe_writer_log[end - 1].session;
    while (from > 0 && fe_writer_log[from - 1].session == s)
        from--;
    /* exact: every byte must still hold the value this session left there */
    for (uint32_t i = from; i < end; i++) {
        const FeWriterEntry *e = &fe_writer_log[i];
        for (uint32_t k = 0; k < e->size; k++) {
            if (!fe_writer_newest(i, e->address + k, end))
                continue;
            uint8_t *b = fe_writer_byte(ctx->write_pages, e->address + k);
            if (b == NULL || *b != (uint8_t)(e->new_value >> (8 * k))) {
                atomic_store(&fe_writer_busy, 0);
                return FE_WRITER_CONFLICT;
            }
        }
    }
    fe_writer_restore(ctx->write_pages, from);
    atomic_store(&fe_writer_busy, 0);
    return FE_WRITER_OK;
}

uint32_t fe_writer_log_count(void) { return fe_writer_count; }

int fe_writer_log_entry(uint32_t index, FeWriterEntry *out) {
    if (index >= fe_writer_count || out == NULL)
        return 0;
    *out = fe_writer_log[index];
    return 1;
}

uint32_t fe_writer_refusals(void) { return fe_writer_refused; }
uint32_t fe_writer_mode_refusals(void) { return fe_writer_wrong_mode; }
uint32_t fe_writer_stray_stores(void) { return fe_writer_stray; }
uint32_t fe_writer_dropped(void) { return fe_writer_drop; }

#ifdef FE_WRITER_TESTS
void fe_writer_test_arm(int writer, int armed) {
    if (writer > FE_WRITER_NONE && writer < FE_WRITER_COUNT)
        fe_writer_table[writer].armed = armed;
}

void fe_writer_test_switches(const char *list) { fe_writer_parse(list); }

void fe_writer_test_reset(void) {
    for (int w = 0; w < FE_WRITER_COUNT; w++)
        fe_writer_table[w].armed = 0;
    memset(fe_writer_listed, 0, sizeof fe_writer_listed);
    fe_writer_listed_read = 1;
    fe_writer_count = fe_writer_start = fe_writer_session = 0;
    fe_writer_id = FE_WRITER_NONE;
    fe_writer_fail = FE_WRITER_FAIL_NONE;
    fe_writer_frame = 0;
    fe_writer_ctx = NULL;
    fe_writer_refused = fe_writer_wrong_mode = fe_writer_stray = fe_writer_drop = 0;
    fe_writer_stored = fe_writer_restored = fe_writer_opened = 0;
    fe_writer_publish();
    atomic_store(&fe_writer_busy, 0);
}
#endif
