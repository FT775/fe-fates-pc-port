/* Capture mode: record real calls of guest functions and compare them live
   (docs/HARNESS.md 3.1, 4.4, 4.5, 5; the interface is include/readable/fe_capture.h).

   Runs only when FE_READABLE=capture. Nothing here changes a guest byte or
   the budget of the game: the recording host passes every access through to
   the real memory (or the real host), and the live replays (run A, run B)
   work on private copies of the recorded pages.

   Threads: one host thread owns the capture at a time (fe_cap_busy). A call
   on another thread, or on another Context, while a record is open runs
   uncaptured. Counting calls takes a small spin lock. Everything else is
   touched only by the owner.

   Every way out of a captured call goes through one place that puts
   ctx->read_pages, ctx->write_pages and ctx->host back: the original
   returns to fe_capture_call whatever made it stop (normal return, budget,
   svc, unwind), because generated code leaves only by returning with
   ctx->exit set. This file has no override. */

#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L /* mkdir */
#endif

#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(_WIN32)
#include <direct.h>
#include <io.h> /* _chsize_s, _fileno */
#else
#include <sys/stat.h>
#include <unistd.h> /* ftruncate */
#endif

#include "fe.h"
#include "fe_writer.h" /* fe_writer_totals only: the gate's run totals for the summary (the array is in runtime.c) */

#define FE_CAP_PAGES_IN_SPACE (1u << 20)
#define FE_CAP_SUMMARY_EVERY 256u /* summary.tsv rewritten after this many finished records */
#define FE_CAP_LOG_FIRST 20u      /* bad-verdict log lines per function */

/* ------------------------------------------------------------------------
   Settings */

typedef struct FeCapSettings {
    int loaded, have_dir, store, live, late;
    char dir[1024];
    uint32_t *only, only_count;
    uint64_t max_bytes;
    uint32_t keep, guard, max_pages;
} FeCapSettings;

static FeCapSettings fe_cap_cfg;
static const FeCapConfig *fe_cap_forced; /* set by fe_capture_configure */
static FeCapConfig fe_cap_forced_copy;
static char fe_cap_forced_dir[1024], fe_cap_forced_only[4096];
static int fe_cap_have_forced;
/* set (release) once fe_cap_cfg is complete; read (acquire) before using it
   without the lock */
static atomic_int fe_cap_ready;

/* ------------------------------------------------------------------------
   Per-function statistics (also the call counter used for sampling) */

typedef struct FeCapFn {
    uint32_t address, kind, calls, records;
    uint32_t verdicts[FE_CAP_V_COUNT];
    uint32_t cold, warm, deep, kept, logged;
    uint32_t signature_count, first_read_bucket;
    uint32_t signatures[FE_CAP_MAX_SIGNATURES], signature_hits[FE_CAP_MAX_SIGNATURES];
} FeCapFn;

static FeCapFn *fe_cap_fns; /* FE_CAP_TRACKED slots, allocated on first use */
static atomic_flag fe_cap_lock = ATOMIC_FLAG_INIT;
static atomic_int fe_cap_busy;
static FeCapStats fe_cap_stats_;
static FeCapInfo fe_cap_last_;
static uint32_t fe_cap_sequence, fe_cap_since_summary;

static void fe_cap_lock_take(void) {
    while (atomic_flag_test_and_set_explicit(&fe_cap_lock, memory_order_acquire)) {
    }
}
static void fe_cap_lock_give(void) { atomic_flag_clear_explicit(&fe_cap_lock, memory_order_release); }

/* host callbacks seen (callbacks.tsv): one row per (kind, key), with the
   function of the outermost open record (or of the replay) that met it first */
typedef struct FeCapCb {
    uint32_t used, kind, key, count, fn;
} FeCapCb;
static FeCapCb *fe_cap_cbs; /* FE_CAP_CB_TRACKED slots, allocated on first use */
static uint32_t fe_cap_cb_rows, fe_cap_cb_dropped;
static uint32_t fe_cap_replay_fn; /* address of the record runs A and B replay */

/* counts one callback (owner thread only; the lock keeps the exit handler's
   flush from reading a half-made row) */
static void fe_cap_cb_note(uint32_t kind, uint32_t key, uint32_t fn) {
    fe_cap_stats_.callbacks[kind]++;
    if (fe_cap_cbs == NULL) {
        fe_cap_cbs = calloc(FE_CAP_CB_TRACKED, sizeof *fe_cap_cbs);
        if (fe_cap_cbs == NULL) {
            fe_cap_cb_dropped++;
            return;
        }
    }
    fe_cap_lock_take();
    uint32_t at = (key * 2654435761u ^ kind * 40503u) % FE_CAP_CB_TRACKED;
    for (uint32_t i = 0; i < FE_CAP_CB_TRACKED; i++, at = (at + 1) % FE_CAP_CB_TRACKED) {
        FeCapCb *c = &fe_cap_cbs[at];
        if (!c->used) {
            if (fe_cap_cb_rows >= FE_CAP_CB_TRACKED * 3 / 4)
                break; /* keep probing short: a full table counts as dropped */
            c->used = 1;
            c->kind = kind;
            c->key = key;
            c->fn = fn;
            c->count = 1;
            fe_cap_cb_rows++;
            fe_cap_lock_give();
            return;
        }
        if (c->kind == kind && c->key == key) {
            c->count++;
            fe_cap_lock_give();
            return;
        }
    }
    fe_cap_cb_dropped++;
    fe_cap_lock_give();
}

/* ------------------------------------------------------------------------
   Records */

typedef struct FeCapPageRec {
    uint32_t base, flags;
    uint8_t *entry; /* FE_CAP_PAGE_SIZE bytes at the record's entry, or NULL (host memory) */
    uint8_t read_bits[FE_CAP_PAGE_SIZE / 8], write_bits[FE_CAP_PAGE_SIZE / 8];
} FeCapPageRec;

typedef struct FeCapRec {
    Context *ctx;
    Code original;
    uint32_t address, kind, call_number, sequence, depth, flags, exit_code, verdict, signature;
    FeCapRegs entry, exit, a_exit;
    FeCapPageRec *pages;
    uint32_t page_count, page_cap;
    uint32_t *index, index_size; /* open addressing: page base -> page index + 1 */
    FeCapEvent *events;
    uint32_t event_count, event_cap;
    FeCapLookup *lookups;
    uint32_t lookup_count, lookup_cap;
    FeCapNote *notes;
    uint32_t note_count, note_cap;
    FeCapFn *fn;
    char detail[160];
} FeCapRec;

/* a private memory for run A or run B, built from a record's entry pages */
typedef struct FeCapReplayPage {
    uint32_t base, synth; /* synth: not in the record, filled with 0xCD */
    uint32_t no_write;    /* the game had no writable pointer for it (FE_CAP_PAGE_NO_WRITE) */
    uint8_t *bytes;
    uint8_t written[FE_CAP_PAGE_SIZE / 8];
} FeCapReplayPage;

#define FE_CAP_R_SVC 0x1u
#define FE_CAP_R_INTERP 0x2u
#define FE_CAP_R_OUTSIDE 0x4u /* read a byte of a page the record does not have */
#define FE_CAP_R_FULL 0x8u    /* too many pages or notes */
#define FE_CAP_R_DEVICE 0x10u /* wrote a page the game had no writable pointer for (HARNESS.md 3.4) */

typedef struct FeCapReplay {
    FeCapReplayPage *pages;
    uint32_t page_count, page_cap;
    uint32_t *index, index_size;
    FeCapNote *notes;
    uint32_t note_count, note_cap;
    uint32_t nest; /* noted calls open right now (FE_CAP_NOTE_NEST) */
    FeCapLookup *lookups;
    uint32_t lookup_count, lookup_cap;
    uint32_t escaped, outside_address;
} FeCapReplay;

/* the whole guest-visible state of a Context, for the live replays */
typedef struct FeCapCtxSave {
    FeCapRegs regs;
    uint32_t exit, svc, depth;
    uint8_t *const *read_pages;
    uint8_t *const *write_pages;
    const Host *host;
} FeCapCtxSave;

static FeCapRec fe_cap_recs[FE_CAP_MAX_DEPTH];
static int fe_cap_depth;                      /* open records (owner only) */
static Context *fe_cap_owner_ctx;
static uint8_t **fe_cap_null_table;           /* 2^20 null pointers, allocated on first use */
static uint8_t *const *fe_cap_real_read;      /* the game's fields while records are open */
static uint8_t *const *fe_cap_real_write;
static const Host *fe_cap_real_host;
static FeCapReplay fe_cap_ra, fe_cap_rb;
static FeCapRec *fe_cap_pending;              /* waits for run B */
static FeCapCtxSave fe_cap_b_save;
static FILE *fe_cap_records_file;
static long fe_cap_records_start = -1;        /* size of records.fecap when this session opened it */
static uint32_t (*fe_cap_created)[4];         /* page files this session created (not found on disk) */
static uint32_t fe_cap_created_count, fe_cap_created_cap;
static uint32_t *fe_cap_hashes, fe_cap_hash_count, fe_cap_hash_size; /* page files written (4 words each) */
static uint32_t fe_cap_bad_total, fe_cap_good_total;

static _Thread_local int fe_cap_owner;      /* this thread holds fe_cap_busy */
static _Thread_local int fe_cap_forwarding; /* inside a forwarded host callback */
static _Thread_local FeCapReplay *fe_cap_replaying;

static const char *const fe_cap_vnames[FE_CAP_V_COUNT] = FE_CAP_V_NAMES;

/* ------------------------------------------------------------------------
   Small helpers */

/* room for need elements: returns the (maybe moved) array, or p unchanged
   with *ok = 0 when memory ran out */
static void *fe_cap_grow(void *p, uint32_t *cap, uint32_t need, size_t elem, int *ok) {
    *ok = 1;
    if (need <= *cap)
        return p;
    uint32_t n = *cap ? *cap : 16;
    while (n < need)
        n *= 2;
    void *q = realloc(p, (size_t)n * elem);
    if (q == NULL) {
        *ok = 0;
        return p;
    }
    *cap = n;
    return q;
}
#define FE_CAP_GROW(array, cap, need, ok) ((array) = fe_cap_grow((array), &(cap), (need), sizeof *(array), &(ok)), (ok))

static void fe_cap_bit_set(uint8_t *bits, uint32_t i) { bits[i >> 3] = (uint8_t)(bits[i >> 3] | (1u << (i & 7))); }
static int fe_cap_bit(const uint8_t *bits, uint32_t i) { return (bits[i >> 3] >> (i & 7)) & 1; }

static uint32_t fe_cap_popcount(const uint8_t *bits, uint32_t bytes) {
    uint32_t n = 0;
    for (uint32_t i = 0; i < bytes; i++)
        for (uint32_t b = bits[i]; b; b &= b - 1)
            n++;
    return n;
}

static uint32_t fe_cap_log2_bucket(uint32_t n) {
    uint32_t b = 0;
    while (n) {
        b++;
        n >>= 1;
    }
    return b; /* 0 for 0, 1 for 1, 2 for 2..3, ... */
}

/* a page index shared by records and replays: base -> position + 1 */
static uint32_t fe_cap_index_find(const uint32_t *index, uint32_t size, const void *items, size_t stride,
                                  uint32_t base) {
    if (size == 0)
        return 0;
    uint32_t at = (base >> 12) * 2654435761u & (size - 1);
    for (;; at = (at + 1) & (size - 1)) {
        uint32_t v = index[at];
        if (v == 0)
            return 0;
        if (*(const uint32_t *)((const char *)items + (size_t)(v - 1) * stride) == base)
            return v;
    }
}

static int fe_cap_index_add(uint32_t **index, uint32_t *size, const void *items, size_t stride, uint32_t count) {
    /* count items exist, the last is new; keep the table at most half full */
    if (count * 2 > *size) {
        uint32_t n = *size ? *size * 2 : 64;
        while (count * 2 > n)
            n *= 2;
        uint32_t *t = calloc(n, sizeof *t);
        if (t == NULL)
            return 0;
        free(*index);
        *index = t;
        *size = n;
        for (uint32_t i = 0; i < count; i++) {
            uint32_t base = *(const uint32_t *)((const char *)items + (size_t)i * stride);
            uint32_t at = (base >> 12) * 2654435761u & (n - 1);
            while (t[at])
                at = (at + 1) & (n - 1);
            t[at] = i + 1;
        }
        return 1;
    }
    uint32_t base = *(const uint32_t *)((const char *)items + (size_t)(count - 1) * stride);
    uint32_t at = (base >> 12) * 2654435761u & (*size - 1);
    while ((*index)[at])
        at = (at + 1) & (*size - 1);
    (*index)[at] = count;
    return 1;
}

static void fe_cap_regs_save(const Context *ctx, FeCapRegs *o) {
    memcpy(o->r, ctx->r, sizeof o->r);
    o->n = ctx->n;
    o->z = ctx->z;
    o->c = ctx->c;
    o->v = ctx->v;
    o->q = ctx->q;
    o->thumb = ctx->thumb;
    o->ge = ctx->ge;
    o->exclusive = ctx->exclusive;
    o->exclusive_address = ctx->exclusive_address;
    o->tls = ctx->tls;
    o->budget = ctx->budget;
    o->fpscr = *ctx->fpscr;
    memcpy(o->vfp, ctx->vfp, sizeof o->vfp);
}

/* everything but tls (read-only) and the budget */
static void fe_cap_regs_load(Context *ctx, const FeCapRegs *s) {
    memcpy(ctx->r, s->r, sizeof s->r);
    ctx->n = (uint8_t)s->n;
    ctx->z = (uint8_t)s->z;
    ctx->c = (uint8_t)s->c;
    ctx->v = (uint8_t)s->v;
    ctx->q = (uint8_t)s->q;
    ctx->thumb = (uint8_t)s->thumb;
    ctx->ge = (uint8_t)s->ge;
    ctx->exclusive = (uint8_t)s->exclusive;
    ctx->exclusive_address = s->exclusive_address;
    *ctx->fpscr = s->fpscr;
    memcpy(ctx->vfp, s->vfp, sizeof s->vfp);
}

/* 0 when equal; else names the first difference in detail */
static int fe_cap_regs_differ(const FeCapRegs *a, const FeCapRegs *b, char *detail, size_t size) {
    for (int i = 0; i < 16; i++)
        if (a->r[i] != b->r[i]) {
            snprintf(detail, size, "r%d %08X vs %08X", i, (unsigned)a->r[i], (unsigned)b->r[i]);
            return 1;
        }
    if (a->n != b->n || a->z != b->z || a->c != b->c || a->v != b->v || a->q != b->q || a->thumb != b->thumb ||
        a->ge != b->ge) {
        snprintf(detail, size, "flags differ");
        return 1;
    }
    if (a->exclusive != b->exclusive || a->exclusive_address != b->exclusive_address) {
        snprintf(detail, size, "exclusive monitor differs");
        return 1;
    }
    if (a->fpscr != b->fpscr) {
        snprintf(detail, size, "fpscr %08X vs %08X", (unsigned)a->fpscr, (unsigned)b->fpscr);
        return 1;
    }
    for (int i = 0; i < 32; i++)
        if (a->vfp[i] != b->vfp[i]) {
            snprintf(detail, size, "s%d %08X vs %08X", i, (unsigned)a->vfp[i], (unsigned)b->vfp[i]);
            return 1;
        }
    return 0;
}

static void fe_cap_ctx_save(const Context *ctx, FeCapCtxSave *s) {
    fe_cap_regs_save(ctx, &s->regs);
    s->exit = ctx->exit;
    s->svc = ctx->svc;
    s->depth = ctx->depth;
    s->read_pages = ctx->read_pages;
    s->write_pages = ctx->write_pages;
    s->host = ctx->host;
}

static void fe_cap_ctx_load(Context *ctx, const FeCapCtxSave *s) {
    fe_cap_regs_load(ctx, &s->regs);
    ctx->budget = s->regs.budget;
    ctx->exit = s->exit;
    ctx->svc = s->svc;
    ctx->depth = s->depth;
    ctx->read_pages = s->read_pages;
    ctx->write_pages = s->write_pages;
    ctx->host = s->host;
}

/* ------------------------------------------------------------------------
   Settings */

/* hex number, 0x optional; *digits = how many hex digits were read */
static uint32_t fe_cap_hex(const char *s, const char **end, int *digits) {
    uint32_t v = 0;
    int n = 0;
    if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X'))
        s += 2;
    for (;; s++, n++) {
        int d = *s >= '0' && *s <= '9' ? *s - '0' : *s >= 'a' && *s <= 'f' ? *s - 'a' + 10
              : *s >= 'A' && *s <= 'F' ? *s - 'A' + 10 : -1;
        if (d < 0)
            break;
        v = v << 4 | (uint32_t)d;
    }
    if (end)
        *end = s;
    if (digits)
        *digits = n;
    return v;
}

/* 1 when the folder prefix (n bytes of dir; 0 = the working folder) holds
   a .git folder or file, i.e. is the root of a git checkout */
static int fe_cap_is_repo_root(const char *dir, size_t n) {
    char path[1100];
    static const char *const marks[2] = {"/.git/HEAD", "/.git"};
    if (n + 16 >= sizeof path)
        return 0;
    if (n == 0) {
        path[0] = '.';
        n = 1;
    } else {
        memcpy(path, dir, n);
    }
    for (int i = 0; i < 2; i++) {
        snprintf(path + n, sizeof path - n, "%s", marks[i]);
        FILE *f = fopen(path, "rb");
        if (f) {
            fclose(f);
            return 1;
        }
    }
    return 0;
}

/* the records hold game memory: only below the build/ or play/ folder at the
   root of a git checkout (both gitignored here: "build/" and "/play/"), and
   never through a ".." component (build/../docs would reach tracked files) */
static int fe_cap_dir_allowed(const char *dir) {
    int ok = 0;
    const char *p = dir;
    while (*p) {
        const char *q = p;
        while (*q && *q != '/' && *q != '\\')
            q++;
        size_t n = (size_t)(q - p);
        if (n == 2 && p[0] == '.' && p[1] == '.')
            return 0;
        int named = (n == 5 && (p[0] | 32) == 'b' && (p[1] | 32) == 'u' && (p[2] | 32) == 'i' &&
                     (p[3] | 32) == 'l' && (p[4] | 32) == 'd') ||
                    (n == 4 && (p[0] | 32) == 'p' && (p[1] | 32) == 'l' && (p[2] | 32) == 'a' && (p[3] | 32) == 'y');
        if (named && !ok) {
            if (p == dir)
                ok = fe_cap_is_repo_root(dir, 0); /* relative: the working folder */
            else if (p - dir > 1)
                ok = fe_cap_is_repo_root(dir, (size_t)(p - dir) - 1); /* without the separator */
            /* "/build": the file system root is no checkout */
        }
        p = *q ? q + 1 : q;
    }
    return ok;
}

static void fe_cap_mkdir_one(const char *path) {
#if defined(_WIN32)
    (void)_mkdir(path);
#else
    (void)mkdir(path, 0777);
#endif
}

static void fe_cap_mkdirs(const char *dir) {
    char buf[1100];
    size_t n = strlen(dir);
    if (n >= sizeof buf)
        return;
    memcpy(buf, dir, n + 1);
    for (size_t i = 1; i < n; i++)
        if (buf[i] == '/' || buf[i] == '\\') {
            if (buf[i - 1] == ':')
                continue; /* C:\ */
            char c = buf[i];
            buf[i] = 0;
            fe_cap_mkdir_one(buf);
            buf[i] = c;
        }
    fe_cap_mkdir_one(buf);
}

static void fe_capture_finish_at_exit(void) { fe_capture_finish(); }

static void fe_cap_load_settings(void) {
    if (fe_cap_cfg.loaded)
        return;
    FeCapSettings s;
    memset(&s, 0, sizeof s);
    const char *dir, *only, *mb, *keep, *store, *live, *guard, *late;
    char numbuf[3][24];
    if (fe_cap_have_forced) {
        const FeCapConfig *c = fe_cap_forced;
        dir = c->dir;
        only = c->only;
        snprintf(numbuf[0], sizeof numbuf[0], "%u", (unsigned)c->max_mb);
        snprintf(numbuf[1], sizeof numbuf[1], "%u", (unsigned)c->keep);
        snprintf(numbuf[2], sizeof numbuf[2], "%X", (unsigned)c->guard);
        mb = c->max_mb ? numbuf[0] : NULL;
        keep = c->keep ? numbuf[1] : NULL;
        guard = c->guard ? numbuf[2] : NULL;
        store = c->store == FE_CAP_STORE_KEEP ? "keep" : c->store ? "1" : NULL;
        live = c->live == FE_CAP_LIVE_A ? "a" : NULL;
        late = c->late ? "1" : "0"; /* zero = off for tools (offline = live on made-up memory) */
        s.max_pages = c->max_pages;
        s.max_bytes = c->max_bytes;
    } else {
        dir = getenv("FE_CAPTURE_DIR");
        only = getenv("FE_CAPTURE_ONLY");
        mb = getenv("FE_CAPTURE_MAX_MB");
        keep = getenv("FE_CAPTURE_KEEP");
        store = getenv("FE_CAPTURE_STORE");
        live = getenv("FE_CAPTURE_LIVE");
        guard = getenv("FE_CAPTURE_GUARD");
        late = getenv("FE_CAPTURE_LATE");
    }
    FILE *log = fe_log_stream();
    if (dir && *dir) {
        if (strlen(dir) >= sizeof s.dir - 64 || !fe_cap_dir_allowed(dir)) {
            fprintf(log, "[fe-capture] FE_CAPTURE_DIR %s refused: it must be below the build/ or play/ folder "
                         "of a git checkout, without '..' (records hold game memory); comparing live, "
                         "writing nothing\n", dir);
        } else {
            snprintf(s.dir, sizeof s.dir, "%s", dir);
            s.have_dir = 1;
        }
    }
    if (only && *only) {
        uint32_t n = 1;
        for (const char *p = only; *p; p++)
            n += *p == ',';
        s.only = calloc(n, sizeof *s.only);
        for (const char *p = only; s.only && *p;) {
            const char *e;
            int digits;
            while (*p == ' ')
                p++;
            uint32_t a = fe_cap_hex(p, &e, &digits);
            if (digits > 0 && digits <= 8)
                s.only[s.only_count++] = a;
            while (*e && *e != ',')
                e++; /* skip anything else up to the next comma */
            p = *e ? e + 1 : e;
        }
    }
    uint64_t max_mb = mb && *mb ? strtoull(mb, NULL, 10) : FE_CAP_DEFAULT_MAX_MB;
    if (s.max_bytes == 0)
        s.max_bytes = max_mb * 1024u * 1024u;
    s.keep = keep && *keep ? (uint32_t)strtoul(keep, NULL, 10) : FE_CAP_DEFAULT_KEEP;
    s.guard = guard && *guard ? fe_cap_hex(guard, NULL, NULL) : FE_CAP_DEFAULT_GUARD;
    s.live = live && (live[0] == 'a' || live[0] == 'A') && live[1] == 0 ? FE_CAP_LIVE_A : FE_CAP_LIVE_AB;
    /* "keep": store every record and keep them even when all pass (to replay game records offline) */
    s.store = !(store && *store && strcmp(store, "0") != 0) ? 0 : strcmp(store, "keep") == 0 ? FE_CAP_STORE_KEEP : 1;
    s.late = !(late && strcmp(late, "0") == 0); /* default on in the game (HARNESS.md 5 rule 5) */
    if (s.store && s.only_count == 0) {
        fprintf(log, "[fe-capture] FE_CAPTURE_STORE ignored: it needs FE_CAPTURE_ONLY (a small working set)\n");
        s.store = 0;
    }
    if (s.max_pages == 0 || s.max_pages > FE_CAP_MAX_PAGES)
        s.max_pages = FE_CAP_MAX_PAGES;
    s.loaded = 1;
    fe_cap_cfg = s;
    atomic_store_explicit(&fe_cap_ready, 1, memory_order_release);
    fprintf(log, "[fe-capture] on: dir %s, %u function(s) selected%s, cap %llu bytes, live %s%s%s\n",
            s.have_dir ? s.dir : "(none)", (unsigned)s.only_count, s.only_count ? "" : " (all)",
            (unsigned long long)s.max_bytes, s.live == FE_CAP_LIVE_A ? "A" : "A+B", s.store == FE_CAP_STORE_KEEP ? ", store all, keep" : s.store ? ", store all" : "",
            s.late ? ", late pages for run B" : "");
    fflush(log);
    static int registered;
    if (!registered) {
        registered = 1;
        atexit(fe_capture_finish_at_exit);
    }
}

static int fe_cap_selected(uint32_t address) {
    if (fe_cap_cfg.only_count == 0)
        return 1;
    for (uint32_t i = 0; i < fe_cap_cfg.only_count; i++)
        if (fe_cap_cfg.only[i] == address)
            return 1;
    return 0;
}

int fe_capture_sampled(uint32_t n) {
    if (n == 0)
        return 0;
    if (n <= FE_CAP_FIRST)
        return 1;
    return n >= 2 * FE_CAP_FIRST && (n & (n - 1)) == 0;
}

/* counts the call (any thread); NULL when the table is full */
static FeCapFn *fe_cap_count_call(uint32_t address, uint32_t kind, uint32_t *n) {
    FeCapFn *found = NULL;
    fe_cap_lock_take();
    fe_cap_stats_.calls++;
    if (fe_cap_fns == NULL)
        fe_cap_fns = calloc(FE_CAP_TRACKED, sizeof *fe_cap_fns);
    if (fe_cap_fns) {
        uint32_t at = (address >> 2) % FE_CAP_TRACKED;
        for (uint32_t i = 0; i < FE_CAP_TRACKED; i++, at = (at + 1) % FE_CAP_TRACKED) {
            FeCapFn *f = &fe_cap_fns[at];
            if (f->address == address || f->calls == 0) {
                if (f->calls == 0) {
                    f->address = address;
                    f->kind = kind;
                }
                *n = ++f->calls;
                found = f;
                break;
            }
        }
    }
    if (found == NULL)
        fe_cap_stats_.untracked++;
    fe_cap_lock_give();
    return found;
}

/* ------------------------------------------------------------------------
   Forwarding a callback to the real host, with the real fields in place */

typedef struct FeCapFwd {
    uint8_t *const *read_pages;
    uint8_t *const *write_pages;
    const Host *host;
} FeCapFwd;

static void fe_cap_fwd_begin(Context *ctx, FeCapFwd *f) {
    f->read_pages = ctx->read_pages;
    f->write_pages = ctx->write_pages;
    f->host = ctx->host;
    ctx->read_pages = fe_cap_real_read;
    ctx->write_pages = fe_cap_real_write;
    ctx->host = fe_cap_real_host;
    fe_cap_forwarding++;
}

static void fe_cap_fwd_end(Context *ctx, const FeCapFwd *f) {
    fe_cap_forwarding--;
    /* the host may have switched tables (a memory map change inside an svc) */
    fe_cap_real_read = ctx->read_pages;
    fe_cap_real_write = ctx->write_pages;
    fe_cap_real_host = ctx->host;
    ctx->read_pages = f->read_pages;
    ctx->write_pages = f->write_pages;
    ctx->host = f->host;
}

/* ------------------------------------------------------------------------
   The recording host */

static void fe_cap_flag_open(uint32_t flags) {
    for (int i = 0; i < fe_cap_depth; i++)
        fe_cap_recs[i].flags |= flags;
}

/* the page of base in record r, copied on its first access (before the access) */
static FeCapPageRec *fe_cap_touch(FeCapRec *r, uint32_t base) {
    uint32_t v = fe_cap_index_find(r->index, r->index_size, r->pages, sizeof *r->pages, base);
    if (v)
        return &r->pages[v - 1];
    int ok;
    if (r->page_count >= fe_cap_cfg.max_pages || !FE_CAP_GROW(r->pages, r->page_cap, r->page_count + 1, ok)) {
        r->flags |= FE_CAP_TRUNCATED;
        return NULL;
    }
    FeCapPageRec *p = &r->pages[r->page_count];
    memset(p, 0, sizeof *p);
    p->base = base;
    uint8_t *src = fe_cap_real_read[base >> 12];
    if (src) {
        p->entry = malloc(FE_CAP_PAGE_SIZE);
        if (p->entry == NULL) {
            r->flags |= FE_CAP_TRUNCATED;
            return NULL;
        }
        memcpy(p->entry, src, FE_CAP_PAGE_SIZE);
        p->flags |= FE_CAP_PAGE_COPIED;
    } else {
        p->flags |= FE_CAP_PAGE_HOSTMEM;
    }
    if (fe_cap_real_write[base >> 12] == NULL)
        p->flags |= FE_CAP_PAGE_NO_WRITE;
    r->page_count++;
    if (!fe_cap_index_add(&r->index, &r->index_size, r->pages, sizeof *r->pages, r->page_count)) {
        r->page_count--;
        free(p->entry);
        r->flags |= FE_CAP_TRUNCATED;
        return NULL;
    }
    return p;
}

static void fe_cap_event(FeCapRec *r, uint32_t kind, uint32_t address, uint32_t old_value, uint32_t new_value) {
    int ok;
    if (r->event_count >= FE_CAP_MAX_EVENTS || !FE_CAP_GROW(r->events, r->event_cap, r->event_count + 1, ok)) {
        r->flags |= FE_CAP_TRUNCATED;
        return;
    }
    FeCapEvent *e = &r->events[r->event_count++];
    e->kind = kind;
    e->address = address;
    e->old_value = old_value;
    e->new_value = new_value;
}

/* sets the read or write bits of the bytes, copying each page on its first
   access (fe_cap_touch); must run before the access changes anything */
static void fe_cap_mark(uint32_t address, uint32_t width, int write) {
    for (int i = 0; i < fe_cap_depth; i++) {
        FeCapRec *r = &fe_cap_recs[i];
        for (uint32_t k = 0; k < width; k++) {
            uint32_t a = address + k;
            FeCapPageRec *p = fe_cap_touch(r, a & ~0xFFFu);
            if (p)
                fe_cap_bit_set(write ? p->write_bits : p->read_bits, a & 0xFFFu);
        }
    }
}

static uint32_t fe_cap_real_bytes(uint8_t *const *table, uint32_t address, uint32_t width) {
    uint32_t v = 0;
    for (uint32_t k = 0; k < width; k++) {
        uint32_t a = address + k;
        v |= (uint32_t)table[a >> 12][a & 0xFFFu] << (8 * k);
    }
    return v;
}

static int fe_cap_all_direct(uint8_t *const *table, uint32_t address, uint32_t width) {
    return table[address >> 12] != NULL && table[(address + width - 1) >> 12] != NULL;
}

static uint32_t fe_cap_read(Context *ctx, uint32_t address, uint32_t width) {
    fe_cap_mark(address, width, 0); /* copies the page(s) first, in every open record */
    if (fe_cap_all_direct(fe_cap_real_read, address, width))
        return fe_cap_real_bytes(fe_cap_real_read, address, width);
    FeCapFwd f;
    uint32_t v;
    fe_cap_fwd_begin(ctx, &f);
    v = width == 1 ? fe_cap_real_host->read8(ctx, address)
        : width == 2 ? fe_cap_real_host->read16(ctx, address) : fe_cap_real_host->read32(ctx, address);
    fe_cap_fwd_end(ctx, &f);
    fe_cap_flag_open(FE_CAP_HOSTMEM_R);
    fe_cap_cb_note(FE_CAP_CB_HOST_READ, address & ~0xFFFu, fe_cap_recs[0].address);
    for (int i = 0; i < fe_cap_depth; i++)
        fe_cap_event(&fe_cap_recs[i], FE_CAP_EV_HOST_READ | FE_CAP_EV_HOSTMEM | width << 8, address, 0, v);
    return v;
}

static void fe_cap_write(Context *ctx, uint32_t address, uint32_t width, uint32_t value) {
    fe_cap_mark(address, width, 1); /* copies the page(s) BEFORE the store, in every open record */
    if (fe_cap_all_direct(fe_cap_real_write, address, width)) {
        uint32_t old = fe_cap_real_bytes(fe_cap_real_write, address, width);
        for (uint32_t k = 0; k < width; k++) {
            uint32_t a = address + k;
            fe_cap_real_write[a >> 12][a & 0xFFFu] = (uint8_t)(value >> (8 * k));
        }
        for (int i = 0; i < fe_cap_depth; i++)
            fe_cap_event(&fe_cap_recs[i], FE_CAP_EV_WRITE | width << 8, address, old, value);
        return;
    }
    FeCapFwd f;
    fe_cap_fwd_begin(ctx, &f);
    if (width == 1)
        fe_cap_real_host->write8(ctx, address, (uint8_t)value);
    else if (width == 2)
        fe_cap_real_host->write16(ctx, address, (uint16_t)value);
    else
        fe_cap_real_host->write32(ctx, address, value);
    fe_cap_fwd_end(ctx, &f);
    fe_cap_flag_open(FE_CAP_HOSTMEM_W);
    fe_cap_cb_note(FE_CAP_CB_HOST_WRITE, address & ~0xFFFu, fe_cap_recs[0].address);
    for (int i = 0; i < fe_cap_depth; i++)
        fe_cap_event(&fe_cap_recs[i], FE_CAP_EV_WRITE | FE_CAP_EV_HOSTMEM | width << 8, address, 0, value);
}

static uint8_t fe_cap_read8(Context *ctx, uint32_t a) { return (uint8_t)fe_cap_read(ctx, a, 1); }
static uint16_t fe_cap_read16(Context *ctx, uint32_t a) { return (uint16_t)fe_cap_read(ctx, a, 2); }
static uint32_t fe_cap_read32(Context *ctx, uint32_t a) { return fe_cap_read(ctx, a, 4); }
static void fe_cap_write8(Context *ctx, uint32_t a, uint8_t v) { fe_cap_write(ctx, a, 1, v); }
static void fe_cap_write16(Context *ctx, uint32_t a, uint16_t v) { fe_cap_write(ctx, a, 2, v); }
static void fe_cap_write32(Context *ctx, uint32_t a, uint32_t v) { fe_cap_write(ctx, a, 4, v); }

static void fe_cap_interpret(Context *ctx, uint32_t address, uint32_t opcode) {
    fe_cap_flag_open(FE_CAP_ESCAPED_INTERP);
    fe_cap_cb_note(FE_CAP_CB_INTERPRET, address, fe_cap_recs[0].address);
    FeCapFwd f;
    fe_cap_fwd_begin(ctx, &f);
    fe_cap_real_host->interpret(ctx, address, opcode);
    fe_cap_fwd_end(ctx, &f);
}

static void fe_cap_svc(Context *ctx, uint32_t number) {
    fe_cap_flag_open(FE_CAP_ESCAPED_SVC);
    fe_cap_cb_note(FE_CAP_CB_SVC, number, fe_cap_recs[0].address);
    FeCapFwd f;
    fe_cap_fwd_begin(ctx, &f);
    fe_cap_real_host->svc(ctx, number);
    fe_cap_fwd_end(ctx, &f);
}

/* appends to a lookup log; returns the (maybe moved) array; *full when it cannot */
static FeCapLookup *fe_cap_lookup_log(FeCapLookup *list, uint32_t *count, uint32_t *cap, uint32_t address,
                                      Code code, int *full) {
    int ok;
    if (*count >= FE_CAP_MAX_LOOKUPS || !FE_CAP_GROW(list, *cap, *count + 1, ok)) {
        *full = 1;
        return list;
    }
    list[*count].address = address;
    list[*count].found = code != NULL;
    (*count)++;
    return list;
}

static Code fe_cap_lookup(Context *ctx, uint32_t address) {
    FeCapFwd f;
    fe_cap_fwd_begin(ctx, &f);
    Code code = fe_cap_real_host->lookup(ctx, address);
    fe_cap_fwd_end(ctx, &f);
    fe_cap_cb_note(code ? FE_CAP_CB_LOOKUP : FE_CAP_CB_LOOKUP_MISS, address, fe_cap_recs[0].address);
    for (int i = 0; i < fe_cap_depth; i++) {
        FeCapRec *r = &fe_cap_recs[i];
        int full = 0;
        r->lookups = fe_cap_lookup_log(r->lookups, &r->lookup_count, &r->lookup_cap, address, code, &full);
        if (full)
            r->flags |= FE_CAP_TRUNCATED;
    }
    return code;
}

static const Host fe_cap_host = {fe_cap_read8,  fe_cap_read16,     fe_cap_read32,
                                 fe_cap_write8, fe_cap_write16,    fe_cap_write32,
                                 fe_cap_interpret, fe_cap_lookup, fe_cap_svc};

/* appends a probe call (callee, r0-r3); returns the (maybe moved) array */
static FeCapNote *fe_cap_note(FeCapNote *list, uint32_t *count, uint32_t *cap, const Context *ctx, uint32_t callee,
                              uint32_t kind, int *full) {
    int ok;
    if (*count >= FE_CAP_MAX_NOTES || !FE_CAP_GROW(list, *cap, *count + 1, ok)) {
        *full = 1;
        return list;
    }
    FeCapNote *n = &list[(*count)++];
    n->callee = callee;
    n->kind = kind;
    memcpy(n->r, ctx->r, sizeof n->r);
    return list;
}

/* ------------------------------------------------------------------------
   The replay host (runs A and B): a private memory made of the record's
   entry pages; never touches the game */

static void fe_cap_replay_clear(FeCapReplay *rp) {
    for (uint32_t i = 0; i < rp->page_count; i++)
        free(rp->pages[i].bytes);
    rp->page_count = 0;
    if (rp->index)
        memset(rp->index, 0, rp->index_size * sizeof *rp->index);
    rp->note_count = 0;
    rp->nest = 0;
    rp->lookup_count = 0;
    rp->escaped = 0;
    rp->outside_address = 0;
}

static void fe_cap_replay_free(FeCapReplay *rp) {
    fe_cap_replay_clear(rp);
    free(rp->pages);
    free(rp->index);
    free(rp->notes);
    free(rp->lookups);
    memset(rp, 0, sizeof *rp);
}

static FeCapReplayPage *fe_cap_replay_add(FeCapReplay *rp, uint32_t base, const uint8_t *bytes) {
    int ok;
    if (rp->page_count >= FE_CAP_MAX_PAGES * 2 || !FE_CAP_GROW(rp->pages, rp->page_cap, rp->page_count + 1, ok))
        return NULL;
    FeCapReplayPage *p = &rp->pages[rp->page_count];
    memset(p, 0, sizeof *p);
    p->base = base;
    p->bytes = malloc(FE_CAP_PAGE_SIZE);
    if (p->bytes == NULL)
        return NULL;
    if (bytes)
        memcpy(p->bytes, bytes, FE_CAP_PAGE_SIZE);
    else {
        memset(p->bytes, 0xCD, FE_CAP_PAGE_SIZE);
        p->synth = 1;
    }
    rp->page_count++;
    if (!fe_cap_index_add(&rp->index, &rp->index_size, rp->pages, sizeof *rp->pages, rp->page_count)) {
        rp->page_count--;
        free(p->bytes);
        return NULL;
    }
    return p;
}

static FeCapReplayPage *fe_cap_replay_page(FeCapReplay *rp, uint32_t base) {
    uint32_t v = fe_cap_index_find(rp->index, rp->index_size, rp->pages, sizeof *rp->pages, base);
    return v ? &rp->pages[v - 1] : NULL;
}

static int fe_cap_replay_setup(FeCapReplay *rp, const FeCapRec *r) {
    fe_cap_replay_clear(rp);
    for (uint32_t i = 0; i < r->page_count; i++) {
        if (!r->pages[i].entry)
            continue;
        FeCapReplayPage *p = fe_cap_replay_add(rp, r->pages[i].base, r->pages[i].entry);
        if (p == NULL)
            return 0;
        p->no_write = (r->pages[i].flags & FE_CAP_PAGE_NO_WRITE) != 0;
    }
    return 1;
}

static FeCapReplayPage *fe_cap_late_page(FeCapReplay *rp, uint32_t base);

static uint8_t fe_cap_replay_byte(FeCapReplay *rp, uint32_t a, int write, uint8_t value) {
    FeCapReplayPage *p = fe_cap_replay_page(rp, a & ~0xFFFu);
    if (p == NULL)
        p = fe_cap_late_page(rp, a & ~0xFFFu);
    if (p == NULL) {
        p = fe_cap_replay_add(rp, a & ~0xFFFu, NULL);
        if (p == NULL) {
            rp->escaped |= FE_CAP_R_FULL;
            return 0xCD;
        }
    }
    uint32_t o = a & 0xFFFu;
    if (write) {
        /* in the game this store would go to the host (device memory or a
           read-only page): run A never does it in a valid record */
        if (p->no_write && !(rp->escaped & (FE_CAP_R_DEVICE | FE_CAP_R_OUTSIDE)))
            rp->outside_address = a;
        if (p->no_write)
            rp->escaped |= FE_CAP_R_DEVICE;
        p->bytes[o] = value;
        fe_cap_bit_set(p->written, o);
        return value;
    }
    if (p->synth && !fe_cap_bit(p->written, o)) {
        if (!(rp->escaped & (FE_CAP_R_OUTSIDE | FE_CAP_R_DEVICE)))
            rp->outside_address = a;
        rp->escaped |= FE_CAP_R_OUTSIDE;
    }
    return p->bytes[o];
}

/* run B reads or writes a page the record does not have. The call never
   touched it (run A reproduced the call from the record's pages alone, and
   nothing ran in the game since the call returned), so the game's bytes
   now are its bytes at entry: with late pages on, copy it from the game
   into the record (FE_CAP_PAGE_LATE, so a kept record replays offline the
   same way) and into run B's memory. Device pages (no readable pointer)
   and a full record stay escapes. HARNESS.md 5 rule 5, risk 16. */
static FeCapReplayPage *fe_cap_late_page(FeCapReplay *rp, uint32_t base) {
    FeCapRec *r = fe_cap_pending;
    /* run B only: run A runs inside fe_cap_decide, before fe_cap_pending is set, so the rp test is
       defensive (a run A that took bytes from the game would hide an unfaithful record) */
    if (rp != &fe_cap_rb || r == NULL || !fe_cap_cfg.late || fe_cap_real_read == NULL)
        return NULL;
    /* a page the record already has but run B lacks is a HOSTMEM page (no bytes, skipped by
       fe_cap_replay_setup): it stays an escape, never a second entry with the same base */
    if (fe_cap_index_find(r->index, r->index_size, r->pages, sizeof *r->pages, base))
        return NULL;
    const uint8_t *src = fe_cap_real_read[base >> 12];
    int ok;
    if (src == NULL || r->page_count >= fe_cap_cfg.max_pages ||
        !FE_CAP_GROW(r->pages, r->page_cap, r->page_count + 1, ok))
        return NULL;
    FeCapPageRec *e = &r->pages[r->page_count];
    memset(e, 0, sizeof *e);
    e->base = base;
    e->entry = malloc(FE_CAP_PAGE_SIZE);
    if (e->entry == NULL)
        return NULL;
    memcpy(e->entry, src, FE_CAP_PAGE_SIZE);
    e->flags = FE_CAP_PAGE_COPIED | FE_CAP_PAGE_LATE;
    if (fe_cap_real_write == NULL || fe_cap_real_write[base >> 12] == NULL)
        e->flags |= FE_CAP_PAGE_NO_WRITE;
    r->page_count++;
    if (!fe_cap_index_add(&r->index, &r->index_size, r->pages, sizeof *r->pages, r->page_count)) {
        r->page_count--;
        free(e->entry);
        return NULL;
    }
    FeCapReplayPage *p = fe_cap_replay_add(rp, base, e->entry);
    if (p == NULL)
        return NULL; /* the record keeps the page; run B escapes (FULL) */
    p->no_write = (e->flags & FE_CAP_PAGE_NO_WRITE) != 0;
    fe_cap_stats_.late_pages++;
    return p;
}

static uint32_t fe_cap_replay_read(uint32_t address, uint32_t width) {
    uint32_t v = 0;
    for (uint32_t k = 0; k < width; k++)
        v |= (uint32_t)fe_cap_replay_byte(fe_cap_replaying, address + k, 0, 0) << (8 * k);
    return v;
}

static void fe_cap_replay_write(uint32_t address, uint32_t width, uint32_t value) {
    for (uint32_t k = 0; k < width; k++)
        fe_cap_replay_byte(fe_cap_replaying, address + k, 1, (uint8_t)(value >> (8 * k)));
}

static uint8_t fe_cap_rp_read8(Context *ctx, uint32_t a) { (void)ctx; return (uint8_t)fe_cap_replay_read(a, 1); }
static uint16_t fe_cap_rp_read16(Context *ctx, uint32_t a) { (void)ctx; return (uint16_t)fe_cap_replay_read(a, 2); }
static uint32_t fe_cap_rp_read32(Context *ctx, uint32_t a) { (void)ctx; return fe_cap_replay_read(a, 4); }
static void fe_cap_rp_write8(Context *ctx, uint32_t a, uint8_t v) { (void)ctx; fe_cap_replay_write(a, 1, v); }
static void fe_cap_rp_write16(Context *ctx, uint32_t a, uint16_t v) { (void)ctx; fe_cap_replay_write(a, 2, v); }
static void fe_cap_rp_write32(Context *ctx, uint32_t a, uint32_t v) { (void)ctx; fe_cap_replay_write(a, 4, v); }

/* an escape stops the replay: nothing outside the private memory may run */
static void fe_cap_rp_interpret(Context *ctx, uint32_t address, uint32_t opcode) {
    (void)opcode;
    fe_cap_replaying->escaped |= FE_CAP_R_INTERP;
    ctx->r[15] = address;
    ctx->exit = EXIT_UNWIND;
}

static void fe_cap_rp_svc(Context *ctx, uint32_t number) {
    (void)number;
    fe_cap_replaying->escaped |= FE_CAP_R_SVC;
    ctx->exit = EXIT_UNWIND;
}

static Code fe_cap_rp_lookup(Context *ctx, uint32_t address) {
    FeCapReplay *rp = fe_cap_replaying;
    FeCapFwd f;
    fe_cap_fwd_begin(ctx, &f);
    fe_cap_replaying = NULL; /* nothing reached from the real lookup belongs to the replay */
    Code code = fe_cap_real_host->lookup(ctx, address);
    fe_cap_replaying = rp;
    fe_cap_fwd_end(ctx, &f);
    fe_cap_cb_note(FE_CAP_CB_REPLAY_LOOKUP, address, fe_cap_replay_fn);
    int full = 0;
    rp->lookups = fe_cap_lookup_log(rp->lookups, &rp->lookup_count, &rp->lookup_cap, address, code, &full);
    if (full)
        rp->escaped |= FE_CAP_R_FULL;
    return code;
}

static const Host fe_cap_replay_host = {fe_cap_rp_read8,  fe_cap_rp_read16,     fe_cap_rp_read32,
                                        fe_cap_rp_write8, fe_cap_rp_write16,    fe_cap_rp_write32,
                                        fe_cap_rp_interpret, fe_cap_rp_lookup, fe_cap_rp_svc};

/* enters a replay on ctx: entry registers, private memory, a budget that
   does not run out; the caller saved ctx */
static void fe_cap_replay_enter(Context *ctx, const FeCapRec *r, FeCapReplay *rp, int32_t budget) {
    fe_cap_regs_load(ctx, &r->entry);
    ctx->budget = budget;
    ctx->exit = EXIT_NONE;
    ctx->read_pages = fe_cap_null_table;
    ctx->write_pages = fe_cap_null_table;
    ctx->host = &fe_cap_replay_host;
    fe_cap_replaying = rp;
    fe_cap_replay_fn = r->address;
}

/* run A: the original again, on the record's entry pages */
static void fe_cap_run_a(Context *ctx, FeCapRec *r, uint32_t *exit_code) {
    FeCapCtxSave save;
    fe_cap_ctx_save(ctx, &save);
    fe_cap_replay_enter(ctx, r, &fe_cap_ra, FE_CALL_BUDGET);
    if (ctx->depth + 1 > RECOMP_DEPTH_LIMIT) {
        ctx->exit = EXIT_UNWIND;
    } else {
        ctx->depth++;
        r->original(ctx);
        ctx->depth--;
    }
    fe_cap_regs_save(ctx, &r->a_exit);
    *exit_code = ctx->exit;
    fe_cap_replaying = NULL;
    fe_cap_ctx_load(ctx, &save);
}

/* one call: 0 when equal, else names the difference (index = position in B);
   regs = which of r0..r3 to compare (bit n = r_n) */
static int fe_cap_note_differs(const FeCapNote *a, const FeCapNote *b, uint32_t index, uint32_t regs, char *detail,
                               size_t size) {
    if (a->callee != b->callee) {
        snprintf(detail, size, "probe call %u: callee %08X vs %08X", (unsigned)index, (unsigned)a->callee,
                 (unsigned)b->callee);
        return 1;
    }
    for (int k = 0; k < 4; k++)
        if ((regs >> k & 1u) && a->r[k] != b->r[k]) {
            snprintf(detail, size, "probe call %u: %08X(r%d=%08X) vs (r%d=%08X)", (unsigned)index,
                     (unsigned)a->callee, k, (unsigned)a->r[k], k, (unsigned)b->r[k]);
            return 1;
        }
    return 0;
}

static int fe_cap_notes_differ(const FeCapNote *a, uint32_t na, const FeCapNote *b, uint32_t nb, char *detail,
                               size_t size) {
    for (uint32_t i = 0; i < na || i < nb; i++) {
        if (i >= na || i >= nb) {
            snprintf(detail, size, "probe calls: %u vs %u", (unsigned)na, (unsigned)nb);
            return 1;
        }
        if (fe_cap_note_differs(&a[i], &b[i], i, 0xFu, detail, size)) /* the fidelity gate: all four */
            return 1;
    }
    return 0;
}

/* the fidelity gate: does run A give what the game did? */
static int fe_cap_faithful(FeCapRec *r, uint32_t a_exit_code) {
    FeCapReplay *rp = &fe_cap_ra;
    if (a_exit_code != EXIT_NONE || rp->escaped) {
        snprintf(r->detail, sizeof r->detail, "run A stopped (exit %u, escape bits %X, outside %08X)",
                 (unsigned)a_exit_code, (unsigned)rp->escaped, (unsigned)rp->outside_address);
        return 0;
    }
    char d[120];
    if (fe_cap_regs_differ(&r->exit, &r->a_exit, d, sizeof d)) {
        snprintf(r->detail, sizeof r->detail, "exit registers, game vs run A: %s", d);
        return 0;
    }
    /* the game's final bytes: entry bytes with the logged writes applied */
    uint8_t *final = malloc(FE_CAP_PAGE_SIZE);
    if (final == NULL) {
        snprintf(r->detail, sizeof r->detail, "out of memory");
        return 0;
    }
    int ok = 1;
    for (uint32_t i = 0; ok && i < r->page_count; i++) {
        const FeCapPageRec *p = &r->pages[i];
        if (p->entry == NULL)
            continue;
        memcpy(final, p->entry, FE_CAP_PAGE_SIZE);
        for (uint32_t e = 0; e < r->event_count; e++) {
            const FeCapEvent *ev = &r->events[e];
            if ((ev->kind & 0xFFu) != FE_CAP_EV_WRITE)
                continue;
            uint32_t width = ev->kind >> 8 & 0xFFu;
            for (uint32_t k = 0; k < width; k++) {
                uint32_t a = ev->address + k;
                if ((a & ~0xFFFu) == p->base)
                    final[a & 0xFFFu] = (uint8_t)(ev->new_value >> (8 * k));
            }
        }
        const FeCapReplayPage *q = fe_cap_replay_page(rp, p->base);
        for (uint32_t o = 0; q && o < FE_CAP_PAGE_SIZE; o++)
            if (final[o] != q->bytes[o]) {
                snprintf(r->detail, sizeof r->detail, "byte %08X: game %02X, run A %02X", (unsigned)(p->base + o),
                         final[o], q->bytes[o]);
                ok = 0;
                break;
            }
    }
    free(final);
    if (!ok)
        return 0;
    for (uint32_t i = 0; i < rp->page_count; i++)
        if (rp->pages[i].synth) { /* only reads can be missed; a write outside the record is a difference */
            snprintf(r->detail, sizeof r->detail, "run A wrote %08X, outside the record", (unsigned)rp->pages[i].base);
            return 0;
        }
    if (fe_cap_notes_differ(r->notes, r->note_count, rp->notes, rp->note_count, d, sizeof d)) {
        snprintf(r->detail, sizeof r->detail, "game vs run A: %s", d);
        return 0;
    }
    if (r->lookup_count != rp->lookup_count ||
        (r->lookup_count && memcmp(r->lookups, rp->lookups, r->lookup_count * sizeof *r->lookups) != 0)) {
        snprintf(r->detail, sizeof r->detail, "lookups differ: %u vs %u", (unsigned)r->lookup_count,
                 (unsigned)rp->lookup_count);
        return 0;
    }
    return 1;
}

/* run B against run A (HARNESS.md 5, rule 4): readable code calls other
   readable functions directly in C, and may do a pure callee's work inline,
   so a callee of run A that run B never called is left out of A's list
   (*inlined counts them). Its memory effects are still compared byte by
   byte, so nothing it wrote can go unnoticed. Every call B made itself must
   match A's list in order: same callee, same argument registers.

   The notes are a tree (FE_CAP_NOTE_NEST). B's own calls are the ones it
   made itself (level 0); a call inside a noted call is that callee's
   original at work. A's calls B is held to: a call whose enclosing noted
   calls were all done inline by B, and whose callee B called itself; the
   calls inside such a call are skipped, as are B's nested ones. So a getter
   that B runs in C, and the pair-up bonus that getter's original calls,
   line up with B's own guest call of the pair-up bonus (H5 route 2).
   Only the callee's argument registers are compared (FE_CAP_NOTE_ARGS, found
   by FE_ENTRY; all four when not known): a caller may leave anything in the
   others. */
static int fe_cap_own(const FeCapNote *n) { return FE_CAP_NOTE_NEST(n->kind) == 0; }

static int fe_cap_b_called(const FeCapReplay *b, uint32_t callee) {
    for (uint32_t j = 0; j < b->note_count; j++)
        if (fe_cap_own(&b->notes[j]) && b->notes[j].callee == callee)
            return 1;
    return 0;
}

typedef struct FeCapWalk {
    uint32_t i;   /* next note of run A */
    uint32_t cut; /* level of the call B made too that we are inside (notes deeper are skipped) */
} FeCapWalk;

/* the next call of run A that B is held to (a->note_count at the end); counts the ones done inline */
static uint32_t fe_cap_a_next(const FeCapReplay *a, const FeCapReplay *b, FeCapWalk *w, uint32_t *inlined) {
    while (w->i < a->note_count) {
        const FeCapNote *n = &a->notes[w->i++];
        uint32_t level = FE_CAP_NOTE_NEST(n->kind);
        if (level > w->cut)
            continue; /* inside a call B made too */
        w->cut = UINT32_MAX;
        if (fe_cap_b_called(b, n->callee)) {
            w->cut = level;
            return w->i - 1;
        }
        if (inlined)
            (*inlined)++; /* done inline by B: the calls inside it stay open */
    }
    return a->note_count;
}

static uint32_t fe_cap_arg_regs(const FeCapNote *n) {
    uint32_t args = FE_CAP_NOTE_ARGS(n->kind);
    return (args & FE_CAP_ARGS_KNOWN) ? args & 0xFu : 0xFu;
}

static int fe_cap_b_notes_differ(const FeCapReplay *a, const FeCapReplay *b, uint32_t *inlined, char *detail,
                                 size_t size) {
    uint32_t na = 0, nb = 0, k = 0;
    *inlined = 0;
    FeCapWalk w = {0, UINT32_MAX};
    while (fe_cap_a_next(a, b, &w, inlined) < a->note_count)
        na++;
    for (uint32_t x = 0; x < b->note_count; x++)
        nb += (uint32_t)fe_cap_own(&b->notes[x]);
    FeCapWalk v = {0, UINT32_MAX};
    for (;;) {
        uint32_t i = fe_cap_a_next(a, b, &v, NULL);
        while (k < b->note_count && !fe_cap_own(&b->notes[k]))
            k++;
        if (i >= a->note_count || k >= b->note_count)
            break;
        if (fe_cap_note_differs(&a->notes[i], &b->notes[k], k, fe_cap_arg_regs(&a->notes[i]), detail, size))
            return 1;
        k++;
    }
    if (na != nb) {
        snprintf(detail, size, "probe calls: %u vs %u (%u done inline by B)", (unsigned)na, (unsigned)nb,
                 (unsigned)*inlined);
        return 1;
    }
    return 0;
}

static int fe_cap_dead_stack(const FeCapRec *r, uint32_t a) {
    uint32_t sp = r->entry.r[13];
    return a < sp && a >= sp - FE_CAP_STACK_WINDOW;
}

/* path signature of run A (= the game): r0 bucket, bytes written outside
   the dead stack, bytes read, probe calls, lookups */
static void fe_cap_signature(FeCapRec *r, uint32_t *read_bucket, int *deep) {
    uint32_t r0 = r->exit.r[0];
    uint32_t r0b = r0 == 0 ? 0 : r0 == 1 ? 1 : r0 == 0xFFFFFFFFu ? 2 : r0 < 0x100 ? 3 : 4;
    uint32_t written = 0, read = 0;
    for (uint32_t i = 0; i < r->page_count; i++) {
        const FeCapPageRec *p = &r->pages[i];
        read += fe_cap_popcount(p->read_bits, sizeof p->read_bits);
        for (uint32_t o = 0; o < FE_CAP_PAGE_SIZE; o++)
            if (fe_cap_bit(p->write_bits, o) && !fe_cap_dead_stack(r, p->base + o))
                written++;
    }
    uint32_t wb = fe_cap_log2_bucket(written), rb = fe_cap_log2_bucket(read);
    uint32_t nb = r->note_count > 15 ? 15 : r->note_count, lb = r->lookup_count > 15 ? 15 : r->lookup_count;
    r->signature = 0x80000000u | r0b | wb << 4 | rb << 10 | nb << 16 | lb << 20;
    *read_bucket = rb;
    *deep = written > 0 || r0b >= 3;
}

/* ------------------------------------------------------------------------
   Writing records (only bad ones, or every one in store mode) */

static uint64_t fe_cap_mix(uint64_t x) {
    x ^= x >> 30;
    x *= 0xBF58476D1CE4E5B9ull;
    x ^= x >> 27;
    x *= 0x94D049BB133111EBull;
    return x ^ (x >> 31);
}

static void fe_cap_page_hash(const uint8_t *p, uint32_t out[4]) {
    uint64_t a = 0x9E3779B97F4A7C15ull, b = 0xC2B2AE3D27D4EB4Full;
    for (uint32_t i = 0; i < FE_CAP_PAGE_SIZE; i += 8) {
        uint64_t w;
        memcpy(&w, p + i, 8);
        a = (a ^ w) * 0xFF51AFD7ED558CCDull;
        a ^= a >> 32;
        b = (b + w + i) * 0xC4CEB9FE1A85EC53ull;
        b ^= b >> 29;
    }
    a = fe_cap_mix(a ^ FE_CAP_PAGE_SIZE);
    b = fe_cap_mix(b ^ a);
    out[0] = (uint32_t)a;
    out[1] = (uint32_t)(a >> 32);
    out[2] = (uint32_t)b;
    out[3] = (uint32_t)(b >> 32);
}

/* 1 when hash is new this session (and remembers it) */
static int fe_cap_hash_new(const uint32_t h[4]) {
    if ((fe_cap_hash_count + 1) * 2 > fe_cap_hash_size) {
        uint32_t n = fe_cap_hash_size ? fe_cap_hash_size * 2 : 1024;
        uint32_t *t = calloc((size_t)n * 4, sizeof *t);
        if (t == NULL)
            return 1;
        for (uint32_t i = 0; i < fe_cap_hash_size; i++) {
            uint32_t *o = &fe_cap_hashes[i * 4];
            if ((o[0] | o[1] | o[2] | o[3]) == 0)
                continue;
            uint32_t at = o[0] & (n - 1);
            while (t[at * 4] | t[at * 4 + 1] | t[at * 4 + 2] | t[at * 4 + 3])
                at = (at + 1) & (n - 1);
            memcpy(&t[at * 4], o, 16);
        }
        free(fe_cap_hashes);
        fe_cap_hashes = t;
        fe_cap_hash_size = n;
    }
    uint32_t at = h[0] & (fe_cap_hash_size - 1);
    for (;; at = (at + 1) & (fe_cap_hash_size - 1)) {
        uint32_t *s = &fe_cap_hashes[at * 4];
        if ((s[0] | s[1] | s[2] | s[3]) == 0) {
            memcpy(s, h, 16);
            fe_cap_hash_count++;
            return 1;
        }
        if (memcmp(s, h, 16) == 0)
            return 0;
    }
}

static void fe_cap_page_path(char *out, size_t size, const uint32_t h[4]) {
    snprintf(out, size, "%s/pages/%08X%08X%08X%08X.pg", fe_cap_cfg.dir, (unsigned)h[3], (unsigned)h[2],
             (unsigned)h[1], (unsigned)h[0]);
}

static int fe_cap_room(uint64_t bytes) { return fe_cap_stats_.bytes_written + bytes <= fe_cap_cfg.max_bytes; }

static int fe_cap_store(FeCapRec *r) {
    if (!fe_cap_cfg.have_dir)
        return 0;
    uint64_t size = sizeof(FeCapHeader) + (uint64_t)r->page_count * sizeof(FeCapPage) +
                    (uint64_t)r->event_count * sizeof(FeCapEvent) + (uint64_t)r->lookup_count * sizeof(FeCapLookup) +
                    (uint64_t)r->note_count * sizeof(FeCapNote);
    uint32_t (*hashes)[4] = calloc(r->page_count ? r->page_count : 1, sizeof *hashes);
    if (hashes == NULL)
        return 0;
    uint64_t page_bytes = 0;
    for (uint32_t i = 0; i < r->page_count; i++)
        if (r->pages[i].entry) {
            fe_cap_page_hash(r->pages[i].entry, hashes[i]);
            page_bytes += FE_CAP_PAGE_SIZE; /* upper bound: some are already on disk */
        }
    if (size > 0xFFFFFFFFu || !fe_cap_room(size + page_bytes)) {
        free(hashes);
        fe_cap_stats_.records_dropped++;
        static int told;
        if (!told++) {
            fprintf(fe_log_stream(), "[fe-capture] size cap reached (%llu bytes): further records dropped\n",
                    (unsigned long long)fe_cap_cfg.max_bytes);
            fflush(fe_log_stream());
        }
        return 0;
    }
    char path[1200];
    if (fe_cap_records_file == NULL) {
        fe_cap_mkdirs(fe_cap_cfg.dir);
        snprintf(path, sizeof path, "%s/pages", fe_cap_cfg.dir);
        fe_cap_mkdir_one(path);
        snprintf(path, sizeof path, "%s/records.fecap", fe_cap_cfg.dir);
        fe_cap_records_file = fopen(path, "ab");
        if (fe_cap_records_file == NULL) {
            free(hashes);
            fe_cap_stats_.records_dropped++;
            return 0;
        }
        /* an earlier session may have kept records here: store-mode cleanup
           cuts the file back to this size, never below */
        if (fe_cap_records_start < 0) {
            fseek(fe_cap_records_file, 0, SEEK_END);
            fe_cap_records_start = ftell(fe_cap_records_file);
        }
    }
    for (uint32_t i = 0; i < r->page_count; i++) {
        if (!r->pages[i].entry)
            continue;
        if (!fe_cap_hash_new(hashes[i])) {
            fe_cap_stats_.pages_deduped++;
            continue;
        }
        fe_cap_page_path(path, sizeof path, hashes[i]);
        FILE *pf = fopen(path, "rb");
        if (pf) { /* from an earlier session in the same folder */
            fclose(pf);
            fe_cap_stats_.pages_deduped++;
            continue;
        }
        pf = fopen(path, "wb");
        if (pf) {
            fwrite(r->pages[i].entry, 1, FE_CAP_PAGE_SIZE, pf);
            fclose(pf);
            fe_cap_stats_.pages_written++;
            fe_cap_stats_.bytes_written += FE_CAP_PAGE_SIZE;
            int ok;
            if (FE_CAP_GROW(fe_cap_created, fe_cap_created_cap, fe_cap_created_count + 1, ok))
                memcpy(fe_cap_created[fe_cap_created_count++], hashes[i], sizeof hashes[i]);
        }
    }
    FeCapHeader h;
    memset(&h, 0, sizeof h);
    memcpy(h.magic, FE_CAP_MAGIC, 8);
    h.version = FE_CAP_VERSION;
    h.header_bytes = sizeof h;
    h.record_bytes = (uint32_t)size;
    h.address = r->address;
    h.kind = r->kind;
    h.call_number = r->call_number;
    h.sequence = r->sequence;
    h.depth = r->depth;
    h.flags = r->flags;
    h.exit_code = r->exit_code;
    h.verdict = r->verdict;
    h.signature = r->signature;
    h.page_count = r->page_count;
    h.event_count = r->event_count;
    h.lookup_count = r->lookup_count;
    h.note_count = r->note_count;
    h.entry = r->entry;
    h.exit = r->exit;
    FILE *f = fe_cap_records_file;
    fwrite(&h, sizeof h, 1, f);
    for (uint32_t i = 0; i < r->page_count; i++) {
        FeCapPage p;
        memset(&p, 0, sizeof p);
        p.address = r->pages[i].base;
        p.flags = r->pages[i].flags;
        if (r->pages[i].entry)
            memcpy(p.hash, hashes[i], sizeof p.hash);
        memcpy(p.read_bits, r->pages[i].read_bits, sizeof p.read_bits);
        memcpy(p.write_bits, r->pages[i].write_bits, sizeof p.write_bits);
        fwrite(&p, sizeof p, 1, f);
    }
    if (r->event_count)
        fwrite(r->events, sizeof *r->events, r->event_count, f);
    if (r->lookup_count)
        fwrite(r->lookups, sizeof *r->lookups, r->lookup_count, f);
    if (r->note_count)
        fwrite(r->notes, sizeof *r->notes, r->note_count, f);
    free(hashes);
    fe_cap_stats_.records_written++;
    fe_cap_stats_.bytes_written += size;
    return 1;
}

/* ------------------------------------------------------------------------
   Summary */

static int fe_cap_is_bad(uint32_t v) {
    return v == FE_CAP_V_MISMATCH_R0 || v == FE_CAP_V_MISMATCH_MEM || v == FE_CAP_V_MISMATCH_CALLS ||
           v == FE_CAP_V_UNFAITHFUL || v == FE_CAP_V_B_ESCAPED;
}

static const char *fe_cap_fn_verdict(const FeCapFn *f) {
    const uint32_t *v = f->verdicts;
    if (v[FE_CAP_V_MISMATCH_R0] || v[FE_CAP_V_MISMATCH_MEM] || v[FE_CAP_V_MISMATCH_CALLS])
        return "MISMATCH";
    if (v[FE_CAP_V_MATCH]) {
        if (f->signature_count < 2)
            return "SHALLOW";
        /* a cold record needs a warm one; that a known guard user has a cold
           record at all is checked by harness.py (targets.csv), HARNESS.md 4.5 */
        if (v[FE_CAP_V_MATCH] >= 8 && f->deep >= 1 && (f->cold == 0 || f->warm >= 1))
            return "REPLAY-CLEAN";
        return "PARTIAL";
    }
    if (v[FE_CAP_V_UNFAITHFUL])
        return "UNFAITHFUL";
    if (v[FE_CAP_V_FAITHFUL])
        return "A-CLEAN";
    return "NO-DATA";
}

/* callbacks.tsv: every host callback kind and target seen with records open */
static void fe_cap_write_callbacks(void) {
    static const char *const names[FE_CAP_CB_KINDS] = FE_CAP_CB_NAMES;
    char path[1200], tmp[1200];
    snprintf(path, sizeof path, "%s/callbacks.tsv", fe_cap_cfg.dir);
    snprintf(tmp, sizeof tmp, "%s/callbacks.tsv.tmp", fe_cap_cfg.dir);
    FILE *f = fopen(tmp, "w");
    if (f == NULL)
        return;
    fprintf(f, "# fe-capture host callbacks seen while records were open (docs/HARNESS.md 3.1); totals:");
    for (int k = 0; k < FE_CAP_CB_KINDS; k++)
        fprintf(f, " %s %u", names[k], (unsigned)fe_cap_stats_.callbacks[k]);
    fprintf(f, "; late pages %u; rows dropped %u\n", (unsigned)fe_cap_stats_.late_pages, (unsigned)fe_cap_cb_dropped);
    fprintf(f, "kind\tkey\tcount\tfirst_function\n");
    fe_cap_lock_take();
    for (int k = 0; k < FE_CAP_CB_KINDS && fe_cap_cbs; k++)
        for (uint32_t i = 0; i < FE_CAP_CB_TRACKED; i++) {
            const FeCapCb *c = &fe_cap_cbs[i];
            if (c->used && c->kind == (uint32_t)k)
                fprintf(f, "%s\t0x%08X\t%u\t0x%08X\n", names[k], (unsigned)c->key, (unsigned)c->count,
                        (unsigned)c->fn);
        }
    fe_cap_lock_give();
    fclose(f);
    remove(path);
    rename(tmp, path);
}

void fe_capture_flush(void) {
    if (fe_cap_records_file)
        fflush(fe_cap_records_file);
    fe_cap_since_summary = 0;
    if (!fe_cap_cfg.have_dir || fe_cap_fns == NULL)
        return;
    char path[1200], tmp[1200];
    fe_cap_mkdirs(fe_cap_cfg.dir);
    snprintf(path, sizeof path, "%s/summary.tsv", fe_cap_cfg.dir);
    snprintf(tmp, sizeof tmp, "%s/summary.tsv.tmp", fe_cap_cfg.dir);
    FILE *f = fopen(tmp, "w");
    if (f == NULL)
        return;
    fprintf(f, "# fe-capture summary (docs/HARNESS.md 5): one row per function seen in capture mode\n");
    fprintf(f, "# verdict = this session only, without the guard-user rule (HARNESS.md 4.5): harness.py report "
               "applies it and merges runs, so build/harness/report.json has the final labels\n");
    {
        /* the writer gate's run totals (docs/WRITERS.md): a capture run never runs a writer, so stores and log
           must be 0 here; tools/harness/parallel.py reads this line into summary.json */
        static const char *const wnames[FE_WT_COUNT] = FE_WT_NAMES;
        fprintf(f, "# writers:");
        for (int w = 0; w < FE_WT_COUNT; w++)
            fprintf(f, "%s %s %u", w ? ";" : "", wnames[w], (unsigned)fe_writer_totals[w]);
        fprintf(f, "\n");
    }
    fprintf(f, "address\tkind\tverdict\tcalls\trecords");
    for (int v = 1; v < FE_CAP_V_COUNT; v++)
        fprintf(f, "\t%s", fe_cap_vnames[v]);
    fprintf(f, "\tcold\twarm\tdeep\tkept\tpaths\tsignatures\n");
    fe_cap_lock_take();
    for (uint32_t i = 0; i < FE_CAP_TRACKED; i++) {
        const FeCapFn *fn = &fe_cap_fns[i];
        if (fn->calls == 0)
            continue;
        fprintf(f, "0x%08X\t%s\t%s\t%u\t%u", (unsigned)fn->address, fn->kind == FE_CAP_KIND_PROBE ? "probe" : "override",
                fe_cap_fn_verdict(fn), (unsigned)fn->calls, (unsigned)fn->records);
        for (int v = 1; v < FE_CAP_V_COUNT; v++)
            fprintf(f, "\t%u", (unsigned)fn->verdicts[v]);
        fprintf(f, "\t%u\t%u\t%u\t%u\t%u\t", (unsigned)fn->cold, (unsigned)fn->warm, (unsigned)fn->deep,
                (unsigned)fn->kept, (unsigned)fn->signature_count);
        for (uint32_t s = 0; s < fn->signature_count; s++)
            fprintf(f, "%s%08X:%u", s ? ";" : "", (unsigned)fn->signatures[s], (unsigned)fn->signature_hits[s]);
        fprintf(f, "\n");
    }
    fe_cap_lock_give();
    fclose(f);
    remove(path); /* Windows: rename does not replace */
    rename(tmp, path);
    fe_cap_write_callbacks();
}

/* ------------------------------------------------------------------------
   Finishing a record */

static void fe_cap_rec_reset(FeCapRec *r) {
    for (uint32_t i = 0; i < r->page_count; i++)
        free(r->pages[i].entry);
    r->page_count = 0;
    if (r->index)
        memset(r->index, 0, r->index_size * sizeof *r->index);
    r->event_count = r->lookup_count = r->note_count = 0;
    r->flags = r->verdict = r->signature = 0;
    r->detail[0] = 0;
}

static void fe_cap_rec_free(FeCapRec *r) {
    fe_cap_rec_reset(r);
    free(r->pages);
    free(r->index);
    free(r->events);
    free(r->lookups);
    free(r->notes);
    memset(r, 0, sizeof *r);
}

static void fe_cap_finalize(FeCapRec *r) {
    FeCapFn *fn = r->fn;
    uint32_t v = r->verdict;
    int stored = 0;
    if (fe_cap_is_bad(v))
        fe_cap_bad_total++;
    else if (v == FE_CAP_V_MATCH || v == FE_CAP_V_FAITHFUL)
        fe_cap_good_total++;
    if (fn) {
        fn->verdicts[v]++;
        if (v == FE_CAP_V_MATCH || v == FE_CAP_V_FAITHFUL) {
            uint32_t read_bucket;
            int deep;
            fe_cap_signature(r, &read_bucket, &deep);
            if (fn->verdicts[FE_CAP_V_MATCH] + fn->verdicts[FE_CAP_V_FAITHFUL] == 1)
                fn->first_read_bucket = read_bucket;
            else if (read_bucket > fn->first_read_bucket)
                deep = 1;
            fn->deep += (uint32_t)deep;
            if (r->flags & FE_CAP_COLD)
                fn->cold++;
            else
                fn->warm++;
            uint32_t s = 0;
            while (s < fn->signature_count && fn->signatures[s] != r->signature)
                s++;
            if (s < fn->signature_count)
                fn->signature_hits[s]++;
            else if (s < FE_CAP_MAX_SIGNATURES) {
                fn->signatures[s] = r->signature;
                fn->signature_hits[s] = 1;
                fn->signature_count++;
            }
        }
        if ((fe_cap_is_bad(v) && fn->kept < fe_cap_cfg.keep) || fe_cap_cfg.store) {
            stored = fe_cap_store(r);
            fn->kept += (uint32_t)(stored && fe_cap_is_bad(v));
        }
        if (fe_cap_is_bad(v) && fn->logged < FE_CAP_LOG_FIRST) {
            fn->logged++;
            fprintf(fe_log_stream(), "[fe-capture] %s 0x%08X call %u: %s%s\n", fe_cap_vnames[v], (unsigned)r->address,
                    (unsigned)r->call_number, r->detail, stored ? " (record kept)" : "");
            fflush(fe_log_stream());
        }
    }
    fe_cap_stats_.verdicts[v]++;
    FeCapInfo *i = &fe_cap_last_;
    i->address = r->address;
    i->kind = r->kind;
    i->call_number = r->call_number;
    i->sequence = r->sequence;
    i->depth = r->depth;
    i->flags = r->flags;
    i->exit_code = r->exit_code;
    i->verdict = v;
    i->signature = r->signature;
    i->page_count = r->page_count;
    i->event_count = r->event_count;
    i->lookup_count = r->lookup_count;
    i->note_count = r->note_count;
    i->stored = (uint32_t)stored;
    memcpy(i->detail, r->detail, sizeof i->detail);
    fe_cap_rec_reset(r);
    if (++fe_cap_since_summary >= FE_CAP_SUMMARY_EVERY)
        fe_capture_flush();
}

static void fe_cap_release(void) {
    fe_cap_owner = 0;
    fe_cap_owner_ctx = NULL;
    atomic_store(&fe_cap_busy, 0);
}

/* after the original ran: verdict of an invalid record, or run A. 1 = run B next */
static int fe_cap_decide(Context *ctx, FeCapRec *r) {
    uint32_t f = r->flags;
    if (f & FE_CAP_TRUNCATED)
        r->verdict = FE_CAP_V_TRUNCATED;
    else if (f & FE_CAP_INCOMPLETE)
        r->verdict = FE_CAP_V_INCOMPLETE;
    else if (f & (FE_CAP_ESCAPED_SVC | FE_CAP_ESCAPED_INTERP))
        r->verdict = FE_CAP_V_ESCAPED;
    else if (f & (FE_CAP_HOSTMEM_R | FE_CAP_HOSTMEM_W))
        r->verdict = FE_CAP_V_HOSTMEM;
    if (r->verdict)
        return 0;
    r->flags |= FE_CAP_VALID;
    uint32_t a_exit = EXIT_NONE;
    if (!fe_cap_replay_setup(&fe_cap_ra, r)) {
        r->verdict = FE_CAP_V_TRUNCATED;
        snprintf(r->detail, sizeof r->detail, "out of memory for run A");
        return 0;
    }
    fe_cap_run_a(ctx, r, &a_exit);
    if (!fe_cap_faithful(r, a_exit)) {
        r->verdict = FE_CAP_V_UNFAITHFUL;
        return 0;
    }
    if (r->kind == FE_CAP_KIND_OVERRIDE && fe_cap_cfg.live == FE_CAP_LIVE_AB)
        return 1;
    r->verdict = FE_CAP_V_FAITHFUL;
    return 0;
}

static int fe_cap_plain(Context *ctx, Code original) {
    if (ctx->depth + 1 > RECOMP_DEPTH_LIMIT) { /* as 3dsrecomp's CALL does */
        ctx->exit = EXIT_UNWIND;
        return 0;
    }
    ctx->depth++;
    original(ctx);
    ctx->depth--;
    return 0;
}

int fe_capture_call(Context *ctx, uint32_t address, Code original, int kind_and_args) {
    uint32_t args = FE_CAP_NOTE_ARGS((uint32_t)kind_and_args); /* the callee's argument registers */
    int kind = kind_and_args & 0xFF;
    if (fe_cap_replaying) { /* inside run A or B: an original, noted */
        int full = 0;
        FeCapReplay *rp = fe_cap_replaying;
        /* with its argument registers and how many noted calls are open (HARNESS.md 5 rule 4) */
        uint32_t k = (uint32_t)kind | args << 8 | (rp->nest < 0xFFFFu ? rp->nest : 0xFFFFu) << 16;
        rp->notes = fe_cap_note(rp->notes, &rp->note_count, &rp->note_cap, ctx, address, k, &full);
        if (full)
            fe_cap_replaying->escaped |= FE_CAP_R_FULL;
        rp->nest++;
        int rc = fe_cap_plain(ctx, original);
        rp->nest--;
        return rc;
    }
    if (fe_cap_forwarding || (fe_cap_owner && ctx != fe_cap_owner_ctx))
        return fe_cap_plain(ctx, original); /* not part of any open record */
    if (!atomic_load_explicit(&fe_cap_ready, memory_order_acquire)) {
        fe_cap_lock_take();
        fe_cap_load_settings(); /* checks again under the lock */
        fe_cap_lock_give();
    }
    if (fe_cap_owner) { /* inside open records: note the call, tag the cold path */
        for (int i = 0; i < fe_cap_depth; i++) {
            FeCapRec *o = &fe_cap_recs[i];
            int full = 0;
            o->notes = fe_cap_note(o->notes, &o->note_count, &o->note_cap, ctx, address, (uint32_t)kind, &full);
            if (full)
                o->flags |= FE_CAP_TRUNCATED;
            if (address == fe_cap_cfg.guard)
                o->flags |= FE_CAP_COLD;
        }
    }
    uint32_t n = 0;
    FeCapFn *fn = fe_cap_count_call(address, (uint32_t)kind, &n);
    int want = fn && fe_cap_selected(address) && fe_capture_sampled(n) && fn->records < FE_CAP_PER_ADDRESS;
    if (want && !fe_cap_owner) {
        if (fe_cap_null_table == NULL)
            fe_cap_null_table = calloc(FE_CAP_PAGES_IN_SPACE, sizeof *fe_cap_null_table);
        if (fe_cap_null_table == NULL || atomic_exchange(&fe_cap_busy, 1) != 0) {
            fe_cap_stats_.busy_skips++;
            want = 0;
        } else {
            fe_cap_owner = 1;
            fe_cap_owner_ctx = ctx;
            fe_cap_depth = 0;
        }
    }
    if (want && fe_cap_depth >= FE_CAP_MAX_DEPTH)
        want = 0;
    if (!want)
        return fe_cap_plain(ctx, original);
    if (ctx->depth + 1 > RECOMP_DEPTH_LIMIT) { /* refused like CALL; nothing was swapped */
        ctx->exit = EXIT_UNWIND;
        if (fe_cap_depth == 0)
            fe_cap_release();
        return 0;
    }

    FeCapRec *r = &fe_cap_recs[fe_cap_depth];
    fe_cap_rec_reset(r);
    r->ctx = ctx;
    r->original = original;
    r->address = address;
    r->kind = (uint32_t)kind;
    r->call_number = n;
    r->sequence = ++fe_cap_sequence;
    r->depth = (uint32_t)fe_cap_depth + 1;
    r->fn = fn;
    fe_cap_regs_save(ctx, &r->entry);
    fn->records++;
    fe_cap_stats_.sampled++;
    if (fe_cap_depth == 0) {
        fe_cap_real_read = ctx->read_pages;
        fe_cap_real_write = ctx->write_pages;
        fe_cap_real_host = ctx->host;
        ctx->read_pages = fe_cap_null_table;
        ctx->write_pages = fe_cap_null_table;
        ctx->host = &fe_cap_host;
    } else {
        r->flags |= FE_CAP_NESTED;
    }
    fe_cap_depth++;

    ctx->depth++;
    original(ctx); /* whatever stops it, it comes back here */
    ctx->depth--;

    fe_cap_depth--;
    if (fe_cap_depth == 0) { /* the one way out: the game's fields back */
        ctx->read_pages = fe_cap_real_read;
        ctx->write_pages = fe_cap_real_write;
        ctx->host = fe_cap_real_host;
    }
    fe_cap_regs_save(ctx, &r->exit);
    r->exit_code = ctx->exit;
    if (ctx->exit != EXIT_NONE)
        r->flags |= FE_CAP_INCOMPLETE;

    if (fe_cap_decide(ctx, r)) {
        fe_cap_pending = r; /* FE_ENTRY runs B, then fe_capture_b_end finishes */
        return 1;
    }
    fe_cap_finalize(r);
    if (fe_cap_depth == 0)
        fe_cap_release();
    return 0;
}

int fe_capture_b_begin(Context *ctx) {
    FeCapRec *r = fe_cap_pending;
    if (r == NULL)
        return 0;
    if (!fe_cap_replay_setup(&fe_cap_rb, r)) {
        fe_cap_pending = NULL;
        r->verdict = FE_CAP_V_TRUNCATED;
        snprintf(r->detail, sizeof r->detail, "out of memory for run B");
        fe_cap_finalize(r);
        if (fe_cap_depth == 0)
            fe_cap_release();
        return 0;
    }
    fe_cap_ctx_save(ctx, &fe_cap_b_save);
    fe_cap_replay_enter(ctx, r, &fe_cap_rb, r->entry.budget);
    return 1;
}

/* compares B's final bytes with A's; 1 = equal outside the dead stack */
static int fe_cap_memory_equal(FeCapRec *r) {
    const FeCapReplay *a = &fe_cap_ra, *b = &fe_cap_rb;
    for (int side = 0; side < 2; side++) {
        const FeCapReplay *x = side ? b : a, *y = side ? a : b;
        for (uint32_t i = 0; i < x->page_count; i++) {
            const FeCapReplayPage *p = &x->pages[i];
            const FeCapReplayPage *q = fe_cap_replay_page((FeCapReplay *)y, p->base);
            const FeCapPageRec *e = NULL;
            uint32_t v = fe_cap_index_find(r->index, r->index_size, r->pages, sizeof *r->pages, p->base);
            if (v)
                e = &r->pages[v - 1];
            for (uint32_t o = 0; o < FE_CAP_PAGE_SIZE; o++) {
                uint32_t addr = p->base + o;
                if (p->synth && !fe_cap_bit(p->written, o))
                    continue; /* never existed on this side */
                uint8_t mine = p->bytes[o];
                /* the other side's final byte: its own copy, else the entry byte (not touched) */
                int have;
                uint8_t other;
                if (q && !(q->synth && !fe_cap_bit(q->written, o))) {
                    other = q->bytes[o];
                    have = 1;
                } else if (e && e->entry) {
                    other = e->entry[o];
                    have = 1;
                } else {
                    other = 0;
                    have = 0;
                }
                if ((!have || mine != other) && !fe_cap_dead_stack(r, addr)) {
                    uint8_t av = side ? other : mine, bv = side ? mine : other;
                    snprintf(r->detail, sizeof r->detail, "byte %08X: run A %02X, run B %02X%s", (unsigned)addr, av,
                             bv, have ? "" : " (one side never had it)");
                    return 0;
                }
            }
        }
    }
    return 1;
}

void fe_capture_b_end(Context *ctx, uint32_t result) {
    FeCapRec *r = fe_cap_pending;
    if (r == NULL)
        return;
    int gave_up = ctx->exit != EXIT_NONE;
    uint32_t inlined = 0;
    fe_cap_replaying = NULL;
    fe_cap_pending = NULL;
    fe_cap_ctx_load(ctx, &fe_cap_b_save); /* the game's state, exactly as before B */
    char d[120];
    if (fe_cap_rb.escaped) {
        r->verdict = FE_CAP_V_B_ESCAPED;
        snprintf(r->detail, sizeof r->detail, "run B escaped (bits %X, first outside or read-only byte %08X)",
                 (unsigned)fe_cap_rb.escaped, (unsigned)fe_cap_rb.outside_address);
    } else if (gave_up) {
        r->verdict = FE_CAP_V_GAVE_UP;
    } else if (result != r->a_exit.r[0]) {
        r->verdict = FE_CAP_V_MISMATCH_R0;
        snprintf(r->detail, sizeof r->detail, "r0: run A %08X, run B %08X (r0=%08X r1=%08X r2=%08X r3=%08X)",
                 (unsigned)r->a_exit.r[0], (unsigned)result, (unsigned)r->entry.r[0], (unsigned)r->entry.r[1],
                 (unsigned)r->entry.r[2], (unsigned)r->entry.r[3]);
    } else if (!fe_cap_memory_equal(r)) {
        r->verdict = FE_CAP_V_MISMATCH_MEM;
    } else if (fe_cap_b_notes_differ(&fe_cap_ra, &fe_cap_rb, &inlined, d, sizeof d)) {
        r->verdict = FE_CAP_V_MISMATCH_CALLS;
        snprintf(r->detail, sizeof r->detail, "run A vs run B: %s", d);
    } else {
        r->verdict = FE_CAP_V_MATCH;
        if (inlined) { /* info only */
            fe_cap_stats_.calls_inlined += inlined;
            snprintf(r->detail, sizeof r->detail, "%u call(s) of run A not made by run B (done inline)",
                     (unsigned)inlined);
        }
    }
    fe_cap_finalize(r);
    if (fe_cap_depth == 0)
        fe_cap_release();
}

/* ------------------------------------------------------------------------
   Probes outside capture mode, stats, settings for tests */

static FeProbeSink fe_probe_sink;
void fe_probe_set_sink(FeProbeSink sink) { fe_probe_sink = sink; }
void fe_probe_note(Context *ctx, uint32_t address) {
    if (fe_probe_sink)
        fe_probe_sink(ctx, address);
}

void fe_capture_stats(FeCapStats *out) { *out = fe_cap_stats_; }
void fe_capture_last(FeCapInfo *out) { *out = fe_cap_last_; }

int fe_capture_fn_stats(uint32_t address, FeCapFnStats *out) {
    memset(out, 0, sizeof *out);
    if (fe_cap_fns == NULL)
        return 0;
    int found = 0;
    fe_cap_lock_take();
    uint32_t at = (address >> 2) % FE_CAP_TRACKED;
    for (uint32_t i = 0; i < FE_CAP_TRACKED; i++, at = (at + 1) % FE_CAP_TRACKED) {
        const FeCapFn *f = &fe_cap_fns[at];
        if (f->calls == 0)
            break;
        if (f->address == address) {
            out->address = f->address;
            out->kind = f->kind;
            out->calls = f->calls;
            out->records = f->records;
            memcpy(out->verdicts, f->verdicts, sizeof out->verdicts);
            out->cold = f->cold;
            out->warm = f->warm;
            out->deep = f->deep;
            out->kept = f->kept;
            out->signature_count = f->signature_count;
            memcpy(out->signatures, f->signatures, sizeof out->signatures);
            memcpy(out->signature_hits, f->signature_hits, sizeof out->signature_hits);
            out->verdict = fe_cap_fn_verdict(f);
            found = 1;
            break;
        }
    }
    fe_cap_lock_give();
    return found;
}

void fe_capture_configure(const FeCapConfig *config) {
    fe_cap_have_forced = config != NULL;
    if (config) {
        fe_cap_forced_copy = *config;
        if (config->dir) {
            snprintf(fe_cap_forced_dir, sizeof fe_cap_forced_dir, "%s", config->dir);
            fe_cap_forced_copy.dir = fe_cap_forced_dir;
        }
        if (config->only) {
            snprintf(fe_cap_forced_only, sizeof fe_cap_forced_only, "%s", config->only);
            fe_cap_forced_copy.only = fe_cap_forced_only;
        }
        fe_cap_forced = &fe_cap_forced_copy;
    }
    atomic_store(&fe_cap_ready, 0);
    free(fe_cap_cfg.only);
    memset(&fe_cap_cfg, 0, sizeof fe_cap_cfg); /* read again on the next call */
}

/* cuts records.fecap back to the size it had before this session (removes
   it when the session created it) */
static void fe_cap_records_cut(void) {
    char path[1200];
    snprintf(path, sizeof path, "%s/records.fecap", fe_cap_cfg.dir);
    if (fe_cap_records_start <= 0) {
        remove(path);
        return;
    }
    FILE *f = fopen(path, "r+b");
    if (f == NULL)
        return;
    fflush(f);
#if defined(_WIN32)
    (void)_chsize_s(_fileno(f), fe_cap_records_start);
#else
    (void)ftruncate(fileno(f), (off_t)fe_cap_records_start);
#endif
    fclose(f);
}

void fe_capture_finish(void) {
    if (!atomic_load_explicit(&fe_cap_ready, memory_order_acquire))
        return;
    /* at exit another host thread may be inside a record: then only the
       summary is written and the files stay open and untouched */
    int took = 0;
    if (!fe_cap_owner) {
        if (atomic_exchange(&fe_cap_busy, 1) != 0) {
            fe_capture_flush();
            fprintf(fe_log_stream(), "[fe-capture] finish: a record is open on another thread; summary "
                                     "written, records left as they are\n");
            fflush(fe_log_stream());
            return;
        }
        took = 1;
    }
    fe_capture_flush();
    if (fe_cap_cfg.store == 1 && fe_cap_cfg.have_dir && fe_cap_bad_total == 0 && fe_cap_good_total > 0 &&
        fe_cap_stats_.records_written > 0) {
        /* the working set passed: remove what this session wrote, and only that */
        if (fe_cap_records_file) {
            fclose(fe_cap_records_file);
            fe_cap_records_file = NULL;
        }
        fe_cap_records_cut();
        char path[1200];
        for (uint32_t i = 0; i < fe_cap_created_count; i++) {
            fe_cap_page_path(path, sizeof path, fe_cap_created[i]);
            remove(path);
        }
        fe_cap_created_count = 0;
        snprintf(path, sizeof path, "%s/pages", fe_cap_cfg.dir);
#if defined(_WIN32)
        (void)_rmdir(path); /* only when empty */
#else
        (void)rmdir(path);
#endif
        fprintf(fe_log_stream(), "[fe-capture] store mode: every record passed, %u record(s) removed\n",
                (unsigned)fe_cap_stats_.records_written);
        fflush(fe_log_stream());
    }
    if (fe_cap_records_file) {
        fclose(fe_cap_records_file);
        fe_cap_records_file = NULL;
    }
    fe_cap_records_start = -1;
    if (took)
        atomic_store(&fe_cap_busy, 0);
}

void fe_capture_reset(void) {
    if (fe_cap_records_file)
        fclose(fe_cap_records_file);
    fe_cap_records_file = NULL;
    for (int i = 0; i < FE_CAP_MAX_DEPTH; i++)
        fe_cap_rec_free(&fe_cap_recs[i]);
    fe_cap_replay_free(&fe_cap_ra);
    fe_cap_replay_free(&fe_cap_rb);
    free(fe_cap_fns);
    fe_cap_fns = NULL;
    free(fe_cap_hashes);
    fe_cap_hashes = NULL;
    fe_cap_hash_count = fe_cap_hash_size = 0;
    free(fe_cap_created);
    fe_cap_created = NULL;
    free(fe_cap_cbs);
    fe_cap_cbs = NULL;
    fe_cap_cb_rows = fe_cap_cb_dropped = 0;
    fe_cap_replay_fn = 0;
    fe_cap_created_count = fe_cap_created_cap = 0;
    fe_cap_records_start = -1;
    atomic_store(&fe_cap_ready, 0);
    free(fe_cap_cfg.only);
    memset(&fe_cap_cfg, 0, sizeof fe_cap_cfg);
    memset(&fe_cap_stats_, 0, sizeof fe_cap_stats_);
    memset(&fe_cap_last_, 0, sizeof fe_cap_last_);
    fe_cap_sequence = fe_cap_since_summary = 0;
    fe_cap_bad_total = fe_cap_good_total = 0;
    fe_cap_depth = 0;
    fe_cap_pending = NULL;
    fe_cap_replaying = NULL;
    fe_cap_forwarding = 0;
    fe_cap_release();
}
