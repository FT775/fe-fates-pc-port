/* Tests of the undo log (src/readable/core/undo.c, include/readable/fe_undo.h;
   docs/HARNESS.md H8 groundwork, docs/tracks/WRITER_HOOKS.md "The undo log").

   Built by tools/readable/check.py against the stand-in overrides.h, linked
   with src/readable/core/{undo,capture,runtime}.c, and run with no argument.
   Every value here is invented; no game data. The "guest functions" are small
   C functions that store the way generated code does: through
   ctx->write_pages when the page has a pointer, else through the host
   callback, so the null table the undo log installs is what routes a store
   to it.

   The undo log is not wired into FE_ENTRY; entry() below is the model of how
   a future writer hook would use it (begin, readable, end; the original on a
   give-up). The checks that matter: after a give-up at any depth every old
   byte is back, and after a commit every new byte stays.

   Prints "undo test: N/M checks passed". */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fe_undo.h"

static int failures, checks;
#define CHECK(cond) do { checks++; if (!(cond)) { failures++; printf("  FAIL line %d: %s\n", __LINE__, #cond); } } while (0)
#define CHECK_EQ(got, want) do { long long g_ = (long long)(got), w_ = (long long)(want); checks++; \
    if (g_ != w_) { failures++; printf("  FAIL line %d: %s = %lld, want %lld\n", __LINE__, #got, g_, w_); } } while (0)

/* ------------------------------------------------------------------------
   Fake machine */

#define RAM 0x00100000u /* four writable pages */
#define ROM 0x00200000u /* readable, not writable */
#define DEV 0x1EC00000u /* no pointer at all: the host handles it */
#define NPAGES 4

static uint8_t **rtab, **wtab;
static uint8_t **game_r, **game_w; /* the tables the fake host uses now (switched by SWITCH) */
static uint8_t **alt_r, **alt_w;   /* what a lookup of SWITCH switches to */
#define SWITCH 0x00100F08u
static uint8_t ram[NPAGES][4096], rom[4096];
static uint8_t snap[NPAGES][4096];
static uint32_t vfp[32], fpscr;
static int fwd_bad, svc_count, interp_count, dev_reads, dev_writes, lookups;

static const Host fake_host, fake_host2; /* fake_host2: the same callbacks, what SWITCH installs */
static const Host *game_host = &fake_host;

/* forwarded callbacks must see the game's own fields */
static void real_fields(Context *c) {
    if (c->read_pages != (uint8_t *const *)game_r || c->write_pages != (uint8_t *const *)game_w || c->host != game_host)
        fwd_bad++;
}
static uint8_t mem_byte(uint32_t a) {
    uint8_t *p = game_r[a >> 12];
    if (p)
        return p[a & 0xFFF];
    dev_reads++;
    return 0x5A;
}
static void mem_put(uint32_t a, uint8_t v) {
    uint8_t *p = game_w[a >> 12];
    if (p)
        p[a & 0xFFF] = v;
    else
        dev_writes++;
}
static uint8_t h_read8(Context *c, uint32_t a) { real_fields(c); return mem_byte(a); }
static uint16_t h_read16(Context *c, uint32_t a) { real_fields(c); return (uint16_t)(mem_byte(a) | mem_byte(a + 1) << 8); }
static uint32_t h_read32(Context *c, uint32_t a) {
    real_fields(c);
    return (uint32_t)mem_byte(a) | (uint32_t)mem_byte(a + 1) << 8 | (uint32_t)mem_byte(a + 2) << 16 |
           (uint32_t)mem_byte(a + 3) << 24;
}
static void h_write8(Context *c, uint32_t a, uint8_t v) { real_fields(c); mem_put(a, v); }
static void h_write16(Context *c, uint32_t a, uint16_t v) { real_fields(c); mem_put(a, (uint8_t)v); mem_put(a + 1, (uint8_t)(v >> 8)); }
static void h_write32(Context *c, uint32_t a, uint32_t v) {
    real_fields(c);
    for (int k = 0; k < 4; k++)
        mem_put(a + (uint32_t)k, (uint8_t)(v >> (8 * k)));
}
static void h_interpret(Context *c, uint32_t a, uint32_t op) {
    (void)a;
    (void)op;
    real_fields(c);
    interp_count++;
}
static void g_inner_writer(Context *ctx);
static void g_plain_stop(Context *ctx);
static Code h_lookup(Context *c, uint32_t a) {
    real_fields(c);
    lookups++;
    if (a == SWITCH) { /* the host remaps memory while a lookup is forwarded */
        game_r = alt_r;
        game_w = alt_w;
        game_host = &fake_host2;
        c->host = &fake_host2;
        c->read_pages = (uint8_t *const *)alt_r;
        c->write_pages = (uint8_t *const *)alt_w;
        return NULL;
    }
    return a == 0x00100F00u ? g_inner_writer : a == 0x00100F04u ? g_plain_stop : NULL;
}
static void h_svc(Context *c, uint32_t n) {
    (void)n;
    real_fields(c);
    svc_count++;
}
static const Host fake_host = {h_read8, h_read16, h_read32, h_write8, h_write16, h_write32, h_interpret, h_lookup, h_svc};
static const Host fake_host2 = {h_read8, h_read16, h_read32, h_write8, h_write16, h_write32, h_interpret, h_lookup, h_svc};

static Context fresh(void) {
    Context c;
    memset(&c, 0, sizeof c);
    c.read_pages = (uint8_t *const *)rtab;
    c.write_pages = (uint8_t *const *)wtab;
    c.vfp = vfp;
    c.fpscr = &fpscr;
    c.host = &fake_host;
    c.r[13] = RAM + 0x3F00;
    c.r[14] = 0x00123450u;
    c.budget = 1000;
    return c;
}
static int restored(const Context *c) {
    return c->read_pages == (uint8_t *const *)rtab && c->write_pages == (uint8_t *const *)wtab && c->host == &fake_host;
}

/* fills RAM with a pattern and remembers it */
static void reset_ram(uint32_t seed) {
    for (int p = 0; p < NPAGES; p++)
        for (int i = 0; i < 4096; i++)
            /* 0x80..0x8F: no store in these tests writes such a byte, so ram_diffs counts every store */
            ram[p][i] = (uint8_t)(0x80u | (((uint32_t)(p * 4096 + i) * 2654435761u >> 24 ^ seed) & 0x0Fu));
    memcpy(snap, ram, sizeof ram);
}
static int ram_unchanged(void) { return memcmp(snap, ram, sizeof ram) == 0; }
static int ram_diffs(void) {
    int n = 0;
    for (int p = 0; p < NPAGES; p++)
        for (int i = 0; i < 4096; i++)
            n += snap[p][i] != ram[p][i];
    return n;
}
static uint32_t peek32(uint32_t a) {
    return (uint32_t)mem_byte(a) | (uint32_t)mem_byte(a + 1) << 8 | (uint32_t)mem_byte(a + 2) << 16 |
           (uint32_t)mem_byte(a + 3) << 24;
}

/* ------------------------------------------------------------------------
   Stores and reads the way generated code does them */

static void gw8(Context *ctx, uint32_t a, uint8_t v) {
    uint8_t *p = ctx->write_pages[a >> 12];
    if (p)
        p[a & 0xFFF] = v;
    else
        ctx->host->write8(ctx, a, v);
}
static void gw16(Context *ctx, uint32_t a, uint16_t v) {
    uint8_t *p = ctx->write_pages[a >> 12];
    if (p && (a & 0xFFF) <= 0xFFE) {
        p[a & 0xFFF] = (uint8_t)v;
        p[(a & 0xFFF) + 1] = (uint8_t)(v >> 8);
    } else
        ctx->host->write16(ctx, a, v);
}
static void gw32(Context *ctx, uint32_t a, uint32_t v) {
    uint8_t *p = ctx->write_pages[a >> 12];
    if (p && (a & 0xFFF) <= 0xFFC)
        for (int k = 0; k < 4; k++)
            p[(a & 0xFFF) + (uint32_t)k] = (uint8_t)(v >> (8 * k));
    else
        ctx->host->write32(ctx, a, v);
}
static uint32_t gr32(Context *ctx, uint32_t a) {
    uint8_t *p = ctx->read_pages[a >> 12];
    if (p && (a & 0xFFF) <= 0xFFC)
        return (uint32_t)p[a & 0xFFF] | (uint32_t)p[(a & 0xFFF) + 1] << 8 | (uint32_t)p[(a & 0xFFF) + 2] << 16 |
               (uint32_t)p[(a & 0xFFF) + 3] << 24;
    return ctx->host->read32(ctx, a);
}
static void ret(Context *ctx, uint32_t r0) {
    ctx->r[0] = r0;
    ctx->r[15] = ctx->r[14] & ~3u;
}

/* ------------------------------------------------------------------------
   The model of a writer hook: what FE_ENTRY would do with the undo log.
   The readable function stores, then maybe gives up; on a give-up its bytes
   are restored and the original runs (inside the parent frame when nested). */

typedef uint32_t (*Readable)(Context *ctx);
static int entries, originals;

static void entry(Context *ctx, Readable readable, Code original) {
    FeState s;
    entries++;
    fe_save(ctx, &s);
    if (!fe_undo_begin(ctx)) {
        originals++;
        original(ctx);
        return;
    }
    uint32_t r = readable(ctx);
    if (!fe_undo_end(ctx, !fe_gave_up(ctx))) {
        fe_load(ctx, &s, 1);
        originals++;
        original(ctx);
        return;
    }
    fe_load(ctx, &s, 0);
    ctx->r[0] = r;
    ctx->r[15] = ctx->r[14] & ~3u;
}

/* a store of each width, one across a page boundary, one byte twice, a push */
static int mode; /* what the readable stand-ins do after their stores */
enum { M_KEEP, M_GIVE_UP, M_BUDGET, M_UNWIND, M_SVC, M_INTERP, M_HOSTMEM, M_ROM };

static void after(Context *ctx) {
    switch (mode) {
    case M_GIVE_UP: (void)fe_use_original(ctx); break;
    case M_BUDGET: ctx->exit = EXIT_BUDGET; break;
    case M_UNWIND: ctx->exit = EXIT_UNWIND; break;
    case M_SVC: ctx->host->svc(ctx, 0x28); break;
    case M_INTERP: ctx->host->interpret(ctx, RAM, 0xEE000000u); break;
    case M_HOSTMEM: gw32(ctx, DEV + 8, 0x01020304u); break;
    case M_ROM: gw8(ctx, ROM + 3, 9); break;
    default: break;
    }
}
static uint32_t r_plant(Context *ctx) {
    gw8(ctx, RAM + 0x10, 0xA1);
    gw16(ctx, RAM + 0x21, 0xB2C3);
    gw32(ctx, RAM + 0x40, 0xD4E5F607u);
    gw32(ctx, RAM + 0xFFE, 0x11223344u); /* crosses into page 1 */
    gw8(ctx, RAM + 0x10, 0xA2);          /* the same byte again */
    gw32(ctx, ctx->r[13] - 4, 0xCAFEF00Du); /* a push */
    after(ctx);
    return 77;
}
static void o_plant(Context *ctx) { ret(ctx, 5); } /* the original stores nothing */

/* nested: outer stores, calls a hook that stores, stores again */
static int inner_mode;
static uint32_t r_inner(Context *ctx) {
    gw32(ctx, RAM + 0x1100, 0x99887766u);
    gw8(ctx, RAM + 0x1104, 0x55);
    int m = mode;
    mode = inner_mode;
    after(ctx);
    mode = m;
    return 3;
}
static void o_inner(Context *ctx) { gw8(ctx, RAM + 0x1108, 0x44); ret(ctx, 4); }
static void h_inner(Context *ctx) { entry(ctx, r_inner, o_inner); }

static int outer_mode;
static uint32_t r_outer(Context *ctx) {
    gw32(ctx, RAM + 0x2000, 0x13572468u);
    h_inner(ctx);
    if (fe_gave_up(ctx))
        return 0;
    gw16(ctx, RAM + 0x2004, (uint16_t)ctx->r[0]);
    int m = mode;
    mode = outer_mode;
    after(ctx);
    mode = m;
    return 1;
}
static void o_outer(Context *ctx) { gw8(ctx, RAM + 0x2008, 0x33); ret(ctx, 2); }

/* three deep: a -> b -> c, each stores; c's mode, then b's, then a's */
static int mode_a, mode_b, mode_c;
static uint32_t run_with(Context *ctx, int m) {
    int saved = mode;
    mode = m;
    after(ctx);
    mode = saved;
    return 0;
}
static uint32_t r_c(Context *ctx) { gw32(ctx, RAM + 0x3000, 0xC0C0C0C0u); return run_with(ctx, mode_c); }
static void o_c(Context *ctx) { gw8(ctx, RAM + 0x3010, 0xCC); ret(ctx, 0); }
static uint32_t r_b(Context *ctx) {
    gw32(ctx, RAM + 0x3004, 0xB0B0B0B0u);
    entry(ctx, r_c, o_c);
    if (fe_gave_up(ctx))
        return 0;
    return run_with(ctx, mode_b);
}
static void o_b(Context *ctx) { gw8(ctx, RAM + 0x3014, 0xBB); entry(ctx, r_c, o_c); if (!ctx->exit) ret(ctx, 0); }
static uint32_t r_a(Context *ctx) {
    gw32(ctx, RAM + 0x3008, 0xA0A0A0A0u);
    entry(ctx, r_b, o_b);
    if (fe_gave_up(ctx))
        return 0;
    return run_with(ctx, mode_a);
}
static void o_a(Context *ctx) { gw8(ctx, RAM + 0x3018, 0xAA); ret(ctx, 0); }

/* an override reached through guest_call (lookup): a hook inside */
static uint32_t r_gc_inner(Context *ctx) { gw32(ctx, RAM + 0x1200, 0x0BADF00Du); return run_with(ctx, inner_mode); }
static void o_gc_inner(Context *ctx) { gw8(ctx, RAM + 0x1210, 0x77); ret(ctx, 0); }
static void g_inner_writer(Context *ctx) { entry(ctx, r_gc_inner, o_gc_inner); }
/* generated code without a hook: stores, then stops (budget, unwind) or comes back somewhere else */
static int stop_how;
static void g_plain_stop(Context *ctx) {
    gw32(ctx, RAM + 0x1400, 0xFEEDFACEu);
    gw8(ctx, ctx->r[13] - 1, 0x01);
    if (stop_how == 0)
        ctx->exit = EXIT_BUDGET;
    else if (stop_how == 1)
        ctx->exit = EXIT_UNWIND;
    else if (stop_how == 2)
        ctx->r[15] = 0x00100004u; /* not the return address */
    else
        ret(ctx, 9);
}
static uint32_t gc_target = 0x00100F00u;
static uint32_t r_gc_outer(Context *ctx) {
    gw32(ctx, RAM + 0x1300, 0x600DCAFEu);
    uint32_t v = guest_call(ctx, gc_target, 1, 2, 3, 4);
    if (fe_gave_up(ctx))
        return 0;
    return run_with(ctx, outer_mode) + v;
}
static void o_gc_outer(Context *ctx) { ret(ctx, 0); }

/* many stores: fills the log */
static int fill_count;
static uint32_t r_fill(Context *ctx) {
    for (int i = 0; i < fill_count; i++)
        gw8(ctx, RAM + 0x800 + (uint32_t)i, (uint8_t)(i ^ 0x5A));
    return 0;
}

/* ------------------------------------------------------------------------ */

static void check_clean_state(const Context *c, int line) {
    if (fe_undo_depth() != 0 || fe_undo_logged() != 0 || !restored(c) || fe_undo_failure() != FE_UNDO_OK) {
        failures++;
        printf("  FAIL line %d: not clean after the outermost frame (depth %d, logged %u, failure %d, fields %d)\n",
               line, fe_undo_depth(), fe_undo_logged(), fe_undo_failure(), restored(c));
    }
    checks++;
}
#define CLEAN(c) check_clean_state((c), __LINE__)

static void test_off_by_default(void) {
    Context c = fresh();
    reset_ram(1);
    CHECK_EQ(fe_undo_depth(), 0);
    gw32(&c, RAM + 0x10, 0x12345678u); /* no frame: a plain store, nothing logged */
    CHECK_EQ(peek32(RAM + 0x10), 0x12345678u);
    CHECK_EQ(fe_undo_logged(), 0);
    CHECK(restored(&c));
    CHECK_EQ(fe_undo_end(&c, 0), 0); /* no frame: nothing to roll back, ram kept */
    CHECK_EQ(peek32(RAM + 0x10), 0x12345678u);
}

static void test_fields(void) {
    Context c = fresh();
    reset_ram(2);
    CHECK_EQ(fe_undo_begin(&c), 1);
    CHECK(c.read_pages == (uint8_t *const *)rtab);    /* reads stay real */
    CHECK(c.write_pages != (uint8_t *const *)wtab);   /* stores reach the host */
    CHECK(c.write_pages[RAM >> 12] == NULL && c.write_pages[(RAM >> 12) + 1] == NULL);
    CHECK(c.host != &fake_host);
    CHECK_EQ(fe_undo_depth(), 1);
    gw8(&c, RAM + 5, 0xEE);
    CHECK_EQ(fe_undo_logged(), 1);
    CHECK_EQ(ram[0][5], 0xEE);                        /* the store is live: reads see it */
    CHECK_EQ(gr32(&c, RAM + 4) >> 8 & 0xFF, 0xEE);
    CHECK_EQ(fe_undo_end(&c, 1), 1);
    CLEAN(&c);
    CHECK_EQ(ram[0][5], 0xEE);
    CHECK_EQ(fwd_bad, 0);
}

static void test_plant(int m, int want_kept, int want_fail) {
    Context c = fresh();
    reset_ram((uint32_t)(10 + m));
    mode = m;
    entries = originals = 0;
    svc_count = interp_count = dev_writes = 0;
    entry(&c, r_plant, o_plant);
    mode = M_KEEP;
    CLEAN(&c);
    CHECK_EQ(c.exit, EXIT_NONE);
    if (want_kept) {
        CHECK_EQ(originals, 0);
        CHECK_EQ(c.r[0], 77);
        CHECK_EQ(ram[0][0x10], 0xA2);
        CHECK_EQ(ram[0][0x21], 0xC3);
        CHECK_EQ(ram[0][0x22], 0xB2);
        CHECK_EQ(peek32(RAM + 0x40), 0xD4E5F607u);
        CHECK_EQ(peek32(RAM + 0xFFE), 0x11223344u);
        CHECK_EQ(peek32(RAM + 0x3F00 - 4), 0xCAFEF00Du);
        CHECK_EQ(ram_diffs(), 1 + 2 + 4 + 4 + 4);
    } else {
        CHECK_EQ(originals, 1);
        CHECK_EQ(c.r[0], 5);
        CHECK(ram_unchanged()); /* every old byte is back */
    }
    (void)want_fail;
    CHECK_EQ(svc_count, 0);    /* never forwarded */
    CHECK_EQ(interp_count, 0);
    CHECK_EQ(dev_writes, 0);   /* the device store was dropped */
    CHECK_EQ(fwd_bad, 0);
}

static void test_failure_reasons(void) {
    static const struct { int mode, fail; } cases[] = {
        {M_SVC, FE_UNDO_FAIL_SVC}, {M_INTERP, FE_UNDO_FAIL_INTERP},
        {M_HOSTMEM, FE_UNDO_FAIL_HOSTMEM}, {M_ROM, FE_UNDO_FAIL_HOSTMEM}};
    for (unsigned i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        Context c = fresh();
        reset_ram(30 + i);
        mode = cases[i].mode;
        CHECK_EQ(fe_undo_begin(&c), 1);
        (void)r_plant(&c);
        mode = M_KEEP;
        CHECK_EQ(fe_undo_failure(), cases[i].fail);
        CHECK_EQ(c.exit, EXIT_UNWIND);
        CHECK_EQ(fe_undo_begin(&c), 0); /* a failed stack opens no frame */
        c.exit = EXIT_NONE;              /* even if the caller ignored the give-up ... */
        CHECK_EQ(fe_undo_end(&c, 1), 0); /* ... the frame rolls back */
        CLEAN(&c);
        CHECK(ram_unchanged());
        CHECK_EQ(rom[3], 0);
    }
}

/* the hook layer asks to keep, but the guest code stopped: the stores still go back */
static void test_keep_refused(void) {
    static const uint32_t exits[] = {EXIT_BUDGET, EXIT_UNWIND, EXIT_SVC};
    for (unsigned i = 0; i < 3; i++) {
        Context c = fresh();
        reset_ram(150 + i);
        CHECK_EQ(fe_undo_begin(&c), 1);
        CHECK_EQ(fe_undo_begin(&c), 1);
        gw32(&c, RAM + 0x60, 0x01020304u);
        c.exit = exits[i];
        CHECK_EQ(fe_undo_end(&c, 1), 0); /* inner */
        CHECK_EQ(peek32(RAM + 0x60), peek32(RAM + 0x60) & 0xFFFFFFFFu);
        CHECK_EQ(ram[0][0x60], snap[0][0x60]);
        CHECK_EQ(c.exit, exits[i]);      /* left for the caller */
        gw8(&c, RAM + 0x70, 0x0F);
        CHECK_EQ(fe_undo_end(&c, 1), 0); /* outer, exit still set */
        CLEAN(&c);
        CHECK(ram_unchanged());
    }
}

/* a store that starts on a writable page and ends on one without a pointer is dropped whole */
static void test_straddle_hostmem(void) {
    Context c = fresh();
    reset_ram(160);
    uint32_t last = RAM + NPAGES * 4096u; /* the first byte past the fake RAM: no page */
    dev_writes = 0;
    CHECK_EQ(fe_undo_begin(&c), 1);
    gw32(&c, last - 2, 0x0A0B0C0Du);
    CHECK_EQ(fe_undo_failure(), FE_UNDO_FAIL_HOSTMEM);
    CHECK_EQ(c.exit, EXIT_UNWIND);
    CHECK_EQ(fe_undo_logged(), 0);
    CHECK_EQ(ram[NPAGES - 1][4094], snap[NPAGES - 1][4094]);
    CHECK_EQ(ram[NPAGES - 1][4095], snap[NPAGES - 1][4095]);
    gw16(&c, RAM + 0xFFF, 0x0102); /* writable on both sides: logged even after the failure */
    CHECK_EQ(fe_undo_logged(), 2);
    CHECK_EQ(fe_undo_end(&c, 1), 0);
    c.exit = EXIT_NONE;
    CLEAN(&c);
    CHECK(ram_unchanged());
    CHECK_EQ(dev_writes, 0);
}

/* outer/inner: every combination of give-up and keep */
static void test_nested(void) {
    static const int modes[] = {M_KEEP, M_GIVE_UP, M_BUDGET, M_UNWIND, M_SVC};
    for (unsigned i = 0; i < 5; i++) {
        for (unsigned o = 0; o < 5; o++) {
            Context c = fresh();
            reset_ram(40 + i * 5 + o);
            inner_mode = modes[i];
            outer_mode = modes[o];
            mode = M_KEEP;
            originals = 0;
            entry(&c, r_outer, o_outer);
            CLEAN(&c);
            int inner_ok = modes[i] == M_KEEP;
            int poison = modes[i] == M_SVC; /* an svc fails the whole stack */
            int outer_ok = modes[o] == M_KEEP && !poison;
            if (outer_ok) {
                /* inner kept: its stores merged into the outer frame and committed */
                CHECK_EQ(peek32(RAM + 0x2000), 0x13572468u);
                if (inner_ok) {
                    CHECK_EQ(peek32(RAM + 0x1100), 0x99887766u);
                    CHECK_EQ(ram[1][0x104], 0x55);
                    CHECK_EQ(ram[1][0x108], snap[1][0x108]); /* the inner original did not run */
                    CHECK_EQ(ram[2][4] | ram[2][5] << 8, 3);
                } else {
                    /* inner gave up: its bytes restored, its original ran inside the outer frame */
                    CHECK_EQ(peek32(RAM + 0x1100), (uint32_t)(snap[1][0x100] | snap[1][0x101] << 8 |
                                                              snap[1][0x102] << 16 | (uint32_t)snap[1][0x103] << 24));
                    CHECK_EQ(ram[1][0x104], snap[1][0x104]);
                    CHECK_EQ(ram[1][0x108], 0x44);
                    CHECK_EQ(ram[2][4] | ram[2][5] << 8, 4);
                }
                CHECK_EQ(c.r[0], 1);
            } else {
                /* the outer gave up: nothing of either readable stays; the outer original ran */
                CHECK_EQ(c.r[0], 2);
                CHECK_EQ(ram[2][8], 0x33);
                CHECK_EQ(ram_diffs(), 1);
            }
        }
    }
    CHECK_EQ(svc_count, 0);
    CHECK_EQ(fwd_bad, 0);
}

/* three deep: a give-up at each depth */
static void test_three_deep(void) {
    for (int depth = 0; depth <= 3; depth++) {
        for (int how = 0; how < 3; how++) {
            int m = how == 0 ? M_GIVE_UP : how == 1 ? M_BUDGET : M_UNWIND;
            Context c = fresh();
            reset_ram((uint32_t)(80 + depth * 3 + how));
            mode_a = depth == 1 ? m : M_KEEP;
            mode_b = depth == 2 ? m : M_KEEP;
            mode_c = depth == 3 ? m : M_KEEP;
            mode = M_KEEP;
            originals = 0;
            entry(&c, r_a, o_a);
            CLEAN(&c);
            CHECK_EQ(c.exit, EXIT_NONE);
            uint8_t *p = ram[3];
            if (depth == 0) { /* nothing gave up: all three readables' stores committed */
                CHECK_EQ(originals, 0);
                CHECK_EQ(peek32(RAM + 0x3000), 0xC0C0C0C0u);
                CHECK_EQ(peek32(RAM + 0x3004), 0xB0B0B0B0u);
                CHECK_EQ(peek32(RAM + 0x3008), 0xA0A0A0A0u);
                CHECK_EQ(ram_diffs(), 12);
            } else if (depth == 1) { /* a gave up: only a's original */
                CHECK_EQ(originals, 1);
                CHECK_EQ(p[0x18], 0xAA);
                CHECK_EQ(ram_diffs(), 1);
            } else if (depth == 2) { /* b gave up: c's bytes (merged into b) and b's restored */
                CHECK_EQ(peek32(RAM + 0x3008), 0xA0A0A0A0u);
                CHECK_EQ(p[0x14], 0xBB);                   /* b's original ran ... */
                CHECK_EQ(peek32(RAM + 0x3000), 0xC0C0C0C0u); /* ... and called c's hook again */
                CHECK_EQ(p[0x04], snap[3][0x04]);
                CHECK_EQ(ram_diffs(), 4 + 1 + 4);
            } else { /* c gave up: c's original inside b */
                CHECK_EQ(peek32(RAM + 0x3008), 0xA0A0A0A0u);
                CHECK_EQ(peek32(RAM + 0x3004), 0xB0B0B0B0u);
                CHECK_EQ(p[0x10], 0xCC);
                CHECK_EQ(p[0x00], snap[3][0x00]);
                CHECK_EQ(ram_diffs(), 4 + 4 + 1);
            }
        }
    }
    mode_a = mode_b = mode_c = M_KEEP;
}

/* through guest_call: a hook callee keeps or gives up; a plain callee that stops after
   storing (budget, unwind, came back somewhere else) makes the outer give up, and its
   stores, logged in the outer frame, go back with the outer's */
static void test_guest_call(void) {
    for (int i = 0; i < 2; i++) {
        Context c = fresh();
        reset_ram(100u + (uint32_t)i);
        gc_target = 0x00100F00u;
        inner_mode = i == 0 ? M_KEEP : M_GIVE_UP;
        outer_mode = M_KEEP;
        lookups = originals = 0;
        entry(&c, r_gc_outer, o_gc_outer);
        CLEAN(&c);
        CHECK_EQ(lookups, 1); /* forwarded to the real host */
        CHECK_EQ(peek32(RAM + 0x1300), 0x600DCAFEu);
        if (i == 0) {
            CHECK_EQ(peek32(RAM + 0x1200), 0x0BADF00Du);
            CHECK_EQ(ram_diffs(), 8);
            CHECK_EQ(originals, 0);
        } else {
            CHECK_EQ(ram[1][0x200], snap[1][0x200]);
            CHECK_EQ(ram[1][0x210], 0x77);
            CHECK_EQ(ram_diffs(), 5);
            CHECK_EQ(originals, 1);
        }
    }
    for (int how = 0; how < 4; how++) {
        Context c = fresh();
        reset_ram(104u + (uint32_t)how);
        gc_target = 0x00100F04u;
        stop_how = how;
        outer_mode = M_KEEP;
        originals = 0;
        entry(&c, r_gc_outer, o_gc_outer);
        CLEAN(&c);
        CHECK_EQ(c.exit, EXIT_NONE);
        if (how == 3) { /* returned normally: everything kept */
            CHECK_EQ(c.r[0], 9);
            CHECK_EQ(peek32(RAM + 0x1400), 0xFEEDFACEu);
            CHECK_EQ(ram_diffs(), 4 + 4 + 1);
        } else {
            CHECK_EQ(originals, 1);
            CHECK(ram_unchanged());
        }
    }
    /* too deep for a guest call: the outer gives up before its callee runs */
    Context c = fresh();
    reset_ram(110);
    gc_target = 0x00100F00u;
    c.depth = RECOMP_DEPTH_LIMIT;
    lookups = 0;
    entry(&c, r_gc_outer, o_gc_outer);
    CLEAN(&c);
    CHECK(ram_unchanged());
    CHECK_EQ(lookups, 1);
    CHECK_EQ(fwd_bad, 0);
}

static void test_overflow(void) {
    CHECK_EQ(fe_undo_set_limit(8), 1);
    Context c = fresh();
    reset_ram(120);
    fill_count = 8; /* exactly fits */
    originals = 0;
    entry(&c, r_fill, o_plant);
    CLEAN(&c);
    CHECK_EQ(originals, 0);
    CHECK_EQ(ram_diffs(), 8);

    reset_ram(121);
    fill_count = 9; /* one too many: give up, never truncate */
    CHECK_EQ(fe_undo_begin(&c), 1);
    (void)r_fill(&c);
    CHECK_EQ(fe_undo_failure(), FE_UNDO_FAIL_OVERFLOW);
    CHECK_EQ(fe_undo_logged(), 8);
    CHECK_EQ(ram[0][0x808], snap[0][0x808]); /* the ninth store was dropped */
    CHECK_EQ(c.exit, EXIT_UNWIND);
    CHECK_EQ(fe_undo_end(&c, 1), 0);
    CLEAN(&c);
    CHECK(ram_unchanged()); /* the eight before it are back too */

    /* a word that does not fit is dropped whole */
    reset_ram(122);
    c = fresh();
    CHECK_EQ(fe_undo_begin(&c), 1);
    for (int i = 0; i < 6; i++)
        gw8(&c, RAM + 0x900 + (uint32_t)i, 1);
    gw32(&c, RAM + 0x910, 0xFFFFFFFFu);
    CHECK_EQ(fe_undo_logged(), 6);
    CHECK_EQ(peek32(RAM + 0x910), peek32(RAM + 0x910) & 0xFFFFFFFFu);
    CHECK_EQ(ram[0][0x910], snap[0][0x910]);
    CHECK_EQ(ram[0][0x911], snap[0][0x911]);
    CHECK_EQ(fe_undo_end(&c, 1), 0);
    CLEAN(&c);
    CHECK(ram_unchanged());

    /* overflow inside an inner frame fails the outer too */
    reset_ram(123);
    c = fresh();
    CHECK_EQ(fe_undo_begin(&c), 1);
    gw32(&c, RAM + 0x20, 1);
    CHECK_EQ(fe_undo_begin(&c), 1);
    gw32(&c, RAM + 0x24, 2);
    gw8(&c, RAM + 0x28, 3);
    CHECK_EQ(fe_undo_end(&c, 1), 0);
    c.exit = EXIT_NONE;
    CHECK_EQ(fe_undo_end(&c, 1), 0);
    CLEAN(&c);
    CHECK(ram_unchanged());

    CHECK_EQ(fe_undo_set_limit(0), 1);
    CHECK_EQ(fe_undo_set_limit(FE_UNDO_MAX_BYTES + 1), 0);
}

static void test_merge_and_limits(void) {
    Context c = fresh();
    reset_ram(130);
    CHECK_EQ(fe_undo_begin(&c), 1);
    gw32(&c, RAM + 0x10, 1);
    CHECK_EQ(fe_undo_begin(&c), 1);
    gw16(&c, RAM + 0x20, 2);
    CHECK_EQ(fe_undo_depth(), 2);
    CHECK_EQ(fe_undo_logged(), 6);
    CHECK_EQ(fe_undo_end(&c, 1), 1); /* merged: the entries stay, now the outer's */
    CHECK_EQ(fe_undo_depth(), 1);
    CHECK_EQ(fe_undo_logged(), 6);
    CHECK(!restored(&c));             /* still swapped: the outer frame is open */
    CHECK_EQ(fe_undo_set_limit(4), 0); /* refused while a frame is open */
    CHECK_EQ(fe_undo_end(&c, 0), 0);  /* the outer gives up: the inner's merged bytes go back too */
    CLEAN(&c);
    CHECK(ram_unchanged());

    /* a second Context cannot open a frame while one is open */
    Context other = fresh();
    CHECK_EQ(fe_undo_begin(&c), 1);
    CHECK_EQ(fe_undo_begin(&other), 0);
    CHECK_EQ(fe_undo_end(&other, 1), 0); /* and cannot close one */
    CHECK_EQ(fe_undo_depth(), 1);
    CHECK(restored(&other));
    CHECK_EQ(fe_undo_end(&c, 1), 1);
    CLEAN(&c);

    /* FE_UNDO_MAX_DEPTH frames, no more */
    int opened = 0;
    while (opened < FE_UNDO_MAX_DEPTH + 2 && fe_undo_begin(&c))
        opened++;
    CHECK_EQ(opened, FE_UNDO_MAX_DEPTH);
    gw8(&c, RAM + 0x30, 0x42);
    for (int i = 0; i < FE_UNDO_MAX_DEPTH + 2 && fe_undo_depth() > 1; i++) /* bounded: a broken log may not pop */
        CHECK_EQ(fe_undo_end(&c, 1), 1);
    CHECK_EQ(fe_undo_logged(), 1);
    CHECK_EQ(fe_undo_end(&c, 0), 0);
    CLEAN(&c);
    CHECK(ram_unchanged());

    /* a byte stored many times in many frames gets its oldest value */
    reset_ram(131);
    CHECK_EQ(fe_undo_begin(&c), 1);
    for (int i = 0; i < 5; i++) {
        CHECK_EQ(fe_undo_begin(&c), 1);
        gw8(&c, RAM + 0x77, (uint8_t)i);
        gw32(&c, RAM + 0x74, (uint32_t)i * 0x01010101u);
    }
    for (int i = 0; i < 5; i++)
        CHECK_EQ(fe_undo_end(&c, 1), 1);
    CHECK_EQ(peek32(RAM + 0x74), 0x04040404u);
    CHECK_EQ(fe_undo_end(&c, 0), 0);
    CLEAN(&c);
    CHECK(ram_unchanged());

    /* a later begin after a failed stack starts clean */
    reset_ram(132);
    CHECK_EQ(fe_undo_begin(&c), 1);
    c.host->svc(&c, 1);
    CHECK_EQ(fe_undo_end(&c, 1), 0);
    c.exit = EXIT_NONE;
    CLEAN(&c);
    CHECK_EQ(fe_undo_begin(&c), 1);
    gw8(&c, RAM + 1, 0);
    CHECK_EQ(fe_undo_end(&c, 1), 1);
    CLEAN(&c);
    CHECK_EQ(ram[0][1], 0);
}

/* reads: direct from the real table; device reads forwarded with the real fields */
static void test_reads(void) {
    Context c = fresh();
    reset_ram(140);
    dev_reads = 0;
    CHECK_EQ(fe_undo_begin(&c), 1);
    CHECK_EQ(gr32(&c, DEV + 4), 0x5A5A5A5Au);
    CHECK_EQ(dev_reads, 4);
    CHECK_EQ(c.host->read8(&c, RAM + 3), snap[0][3]);
    CHECK_EQ(c.host->read16(&c, RAM + 3), snap[0][3] | snap[0][4] << 8);
    CHECK_EQ(fe_undo_logged(), 0); /* reads log nothing */
    CHECK_EQ(fe_undo_end(&c, 1), 1);
    CLEAN(&c);
    CHECK_EQ(fwd_bad, 0);
}

/* the host switches tables (and its Host) inside a forwarded lookup, after a store to a page the new
   write table no longer maps: the switch is kept, and a give-up still puts that byte back */
static void test_table_switch(int keep) {
    Context c = fresh();
    reset_ram(170u + (uint32_t)keep);
    CHECK_EQ(fe_undo_begin(&c), 1);
    gw32(&c, RAM + 0x1010, 0x01020304u); /* page 1, through the old table */
    CHECK(c.host->lookup(&c, SWITCH) == NULL);
    CHECK(c.read_pages == (uint8_t *const *)alt_r);  /* the new read table is used at once */
    CHECK(c.write_pages[RAM >> 12] == NULL);         /* stores still reach the undo host */
    CHECK(c.host != &fake_host && c.host != &fake_host2);
    CHECK_EQ(c.host->read8(&c, RAM + 0x20), snap[0][0x20]); /* forwarded to the new host */
    gw8(&c, RAM + 0x20, 0x0E);                       /* page 0, mapped in both tables */
    CHECK_EQ(fe_undo_logged(), 5);
    CHECK_EQ(c.exit, EXIT_NONE);
    CHECK_EQ(fe_undo_end(&c, keep), keep);
    CHECK(c.read_pages == (uint8_t *const *)alt_r);  /* the switch is kept on the way out */
    CHECK(c.write_pages == (uint8_t *const *)alt_w);
    CHECK(c.host == &fake_host2);
    CHECK_EQ(fe_undo_depth(), 0);
    CHECK_EQ(fe_undo_logged(), 0);
    if (keep) {
        CHECK_EQ(ram[1][0x10], 0x04);
        CHECK_EQ(ram[1][0x13], 0x01);
        CHECK_EQ(ram[0][0x20], 0x0E);
        CHECK_EQ(ram_diffs(), 5);
    } else
        CHECK(ram_unchanged()); /* including page 1, which alt_w does not map */
    CHECK_EQ(fwd_bad, 0);
    game_r = rtab;
    game_w = wtab;
    game_host = &fake_host;
}

/* a frame opened while capture.c records: the "real" write table is capture's null table,
   so the first store gives up and nothing changes (a writer cannot commit under capture) */
static void test_under_capture(void) {
    uint8_t **null_w = calloc(1u << 20, sizeof *null_w);
    CHECK(null_w != NULL);
    if (!null_w)
        return;
    Context c = fresh();
    c.write_pages = (uint8_t *const *)null_w;
    reset_ram(180);
    dev_writes = 0;
    CHECK_EQ(fe_undo_begin(&c), 1);
    gw32(&c, RAM + 0x30, 0x01020304u);
    CHECK_EQ(fe_undo_failure(), FE_UNDO_FAIL_HOSTMEM);
    CHECK_EQ(c.exit, EXIT_UNWIND);
    CHECK_EQ(fe_undo_logged(), 0);
    CHECK_EQ(fe_undo_end(&c, 1), 0);
    CHECK(c.write_pages == (uint8_t *const *)null_w);
    CHECK(c.read_pages == (uint8_t *const *)rtab);
    CHECK(c.host == &fake_host);
    CHECK_EQ(fe_undo_depth(), 0);
    CHECK(ram_unchanged());
    CHECK_EQ(dev_writes, 0);
    free(null_w);
}

int main(void) {
    rtab = calloc(1u << 20, sizeof *rtab);
    wtab = calloc(1u << 20, sizeof *wtab);
    if (!rtab || !wtab) {
        printf("undo test: out of memory\n");
        return 2;
    }
    for (int p = 0; p < NPAGES; p++)
        rtab[(RAM >> 12) + (uint32_t)p] = wtab[(RAM >> 12) + (uint32_t)p] = ram[p];
    rtab[ROM >> 12] = rom; /* readable only */
    game_r = rtab;
    game_w = wtab;
    alt_r = calloc(1u << 20, sizeof *alt_r);
    alt_w = calloc(1u << 20, sizeof *alt_w);
    if (!alt_r || !alt_w) {
        printf("undo test: out of memory\n");
        return 2;
    }
    memcpy(alt_r, rtab, (1u << 20) * sizeof *rtab);
    memcpy(alt_w, wtab, (1u << 20) * sizeof *wtab);
    alt_w[(RAM >> 12) + 1] = NULL; /* page 1 is no longer writable after the switch */

    test_off_by_default();
    test_fields();
    test_plant(M_KEEP, 1, FE_UNDO_OK);
    test_plant(M_GIVE_UP, 0, FE_UNDO_OK);
    test_plant(M_BUDGET, 0, FE_UNDO_OK);
    test_plant(M_UNWIND, 0, FE_UNDO_OK);
    test_plant(M_SVC, 0, FE_UNDO_FAIL_SVC);
    test_plant(M_INTERP, 0, FE_UNDO_FAIL_INTERP);
    test_plant(M_HOSTMEM, 0, FE_UNDO_FAIL_HOSTMEM);
    test_plant(M_ROM, 0, FE_UNDO_FAIL_HOSTMEM);
    test_failure_reasons();
    test_keep_refused();
    test_straddle_hostmem();
    test_nested();
    test_three_deep();
    test_guest_call();
    test_overflow();
    test_merge_and_limits();
    test_reads();
    test_table_switch(0);
    test_table_switch(1);
    test_under_capture();

    printf("undo test: %d/%d checks passed\n", checks - failures, checks);
    return failures ? 1 : 0;
}
