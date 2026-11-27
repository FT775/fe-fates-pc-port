/* Tests of the capture runtime (src/readable/core/capture.c, docs/HARNESS.md 3.1, 4.4, 5).

   Built by tools/readable/check.py against the stand-in overrides.h, linked
   with the two files in src/readable/core/ only, and run with one argument: a scratch
   folder below build/, as an absolute path, which is also the working folder
   (check.py empties it first), so even a broken folder check writes there. Every value here is
   invented; no game data. The "originals" are small C functions that touch
   a fake guest memory through the same mem_read / mem_write helpers
   generated code uses, so with null page tables every access reaches the
   capture host, as in the game.

   Prints "capture test: N/M checks passed". */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fe.h"

/* src/readable/core/runtime.c: the writer gate's run totals (fe_writer.h FE_WT_*, in that order), printed by capture.c */
extern uint32_t fe_writer_totals[];

/* each test original has its own name, as 3dsrecomp's generated header
   gives each override its own original_<address> */
#undef RECOMP_ORIGINAL
#define RECOMP_ORIGINAL(address) test_original_##address

static int failures, checks;
#define CHECK(cond) do { checks++; if (!(cond)) { failures++; printf("  FAIL line %d: %s\n", __LINE__, #cond); } } while (0)
#define CHECK_EQ(got, want) do { long long g_ = (long long)(got), w_ = (long long)(want); checks++; \
    if (g_ != w_) { failures++; printf("  FAIL line %d: %s = %lld, want %lld\n", __LINE__, #got, g_, w_); } } while (0)

/* ------------------------------------------------------------------------
   Fake machine */

#define RAM 0x00100000u   /* two writable pages */
#define ROM 0x00200000u   /* readable, not writable */
#define DEV 0x1EC00000u   /* no pointer at all: the host handles it */
#define STK 0x0FFF0000u   /* 16 writable stack pages */
#define SP0 0x0FFFF000u
#define LR0 0x00123450u

static uint8_t **rtab, **wtab;
static uint8_t **rtab2, **wtab2; /* the host switches to these inside an svc (SVC_SWITCH) */
static uint8_t **exp_r, **exp_w; /* the tables forwarded callbacks must see */
static uint8_t ram[2][4096], ram2[4096], rom[4096], stk[16][4096];
static uint32_t vfp[32], fpscr;
static int fwd_bad, svc_count, svc_mode, interp_count, dev_reads, dev_writes;
static uint32_t dev_last;

enum { SVC_IN_PLACE, SVC_UNWIND, SVC_LEAVE, SVC_OTHER_CTX, SVC_SWITCH };
static int lookup_toggle;

static const Host fake_host;

/* forwarded callbacks must see the game's own fields */
static void real_fields(Context *c) {
    if (c->read_pages != (uint8_t *const *)exp_r || c->write_pages != (uint8_t *const *)exp_w || c->host != &fake_host)
        fwd_bad++;
}

static uint8_t mem_byte(uint32_t a) {
    uint8_t *p = exp_r[a >> 12];
    if (p)
        return p[a & 0xFFF];
    dev_reads++;
    return 0x5A;
}
static void mem_put(uint32_t a, uint8_t v) {
    uint8_t *p = exp_w[a >> 12];
    if (p)
        p[a & 0xFFF] = v;
    else {
        dev_writes++;
        dev_last = a;
    }
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

static void probe_0x00101F00(Context *ctx);
static void ov_wrap(Context *ctx);
static Context other_ctx;
static Code h_lookup(Context *c, uint32_t a) {
    real_fields(c);
    if (a == 0x00101F0Cu) /* an override whose original makes a probe call */
        return ov_wrap;
    if (a == 0x00101F04u) /* found every other time: hidden host state */
        return (lookup_toggle++ & 1) ? NULL : probe_0x00101F00;
    if (a == 0x00101F08u) { /* the host runs another guest thread while it looks up */
        other_ctx.r[0] = 1;
        probe_0x00101F00(&other_ctx);
        return probe_0x00101F00;
    }
    return a == 0x00101F00u ? probe_0x00101F00 : NULL;
}
static void h_svc(Context *c, uint32_t n) {
    real_fields(c);
    svc_count++;
    if (svc_mode == SVC_UNWIND)
        c->exit = EXIT_UNWIND;
    else if (svc_mode == SVC_LEAVE) {
        c->svc = n;
        c->exit = EXIT_SVC;
    } else if (svc_mode == SVC_OTHER_CTX) {
        /* the host runs another guest thread here: its calls are not part of the record */
        other_ctx.r[0] = 1;
        probe_0x00101F00(&other_ctx);
    } else if (svc_mode == SVC_SWITCH) { /* a memory map change: new tables */
        c->read_pages = (uint8_t *const *)rtab2;
        c->write_pages = (uint8_t *const *)wtab2;
        exp_r = rtab2;
        exp_w = wtab2;
    }
}
static const Host fake_host = {h_read8, h_read16, h_read32, h_write8, h_write16, h_write32, h_interpret, h_lookup, h_svc};

static Context fresh(void) {
    Context c;
    memset(&c, 0, sizeof c);
    c.read_pages = (uint8_t *const *)rtab;
    c.write_pages = (uint8_t *const *)wtab;
    c.vfp = vfp;
    c.fpscr = &fpscr;
    c.host = &fake_host;
    c.r[13] = SP0;
    c.r[14] = LR0;
    c.budget = 1000;
    return c;
}

static int restored(const Context *c) {
    return c->read_pages == (uint8_t *const *)rtab && c->write_pages == (uint8_t *const *)wtab && c->host == &fake_host;
}

static void set32(uint32_t a, uint32_t v) {
    for (int k = 0; k < 4; k++)
        mem_put(a + (uint32_t)k, (uint8_t)(v >> (8 * k)));
}
static uint32_t get32(uint32_t a) {
    return (uint32_t)mem_byte(a) | (uint32_t)mem_byte(a + 1) << 8 | (uint32_t)mem_byte(a + 2) << 16 |
           (uint32_t)mem_byte(a + 3) << 24;
}

/* ------------------------------------------------------------------------
   Test originals (stand-ins for generated code) */

static void ret(Context *ctx, uint32_t r0) {
    ctx->r[0] = r0;
    ctx->r[15] = ctx->r[14] & ~3u;
}

/* r0 = two words added; a scratch word below sp (dead stack) */
static void orig_sum(Context *ctx) {
    mem_write32(ctx, ctx->r[13] - 8, 0xDEADBEEFu);
    ret(ctx, mem_read32(ctx, RAM + 0x10) + mem_read32(ctx, RAM + 0x14));
}
void test_original_0x00100100(Context *ctx) { orig_sum(ctx); }
void test_original_0x00100104(Context *ctx) { orig_sum(ctx); }
void test_original_0x00100108(Context *ctx) { orig_sum(ctx); }
void test_original_0x0010010C(Context *ctx) { orig_sum(ctx); }
void test_original_0x00100110(Context *ctx) { orig_sum(ctx); }
void test_original_0x00100114(Context *ctx) { orig_sum(ctx); }
void test_original_0x0010011C(Context *ctx) { orig_sum(ctx); }
void test_original_0x00100120(Context *ctx) { orig_sum(ctx); }
void test_original_0x00100124(Context *ctx) { orig_sum(ctx); }
void test_original_0x00100128(Context *ctx) { orig_sum(ctx); }

/* a writer: returns the old value, stores old + 1; reads a ROM word too */
void test_original_0x00100200(Context *ctx) {
    uint32_t v = mem_read32(ctx, RAM + 0x20);
    (void)mem_read32(ctx, ROM + 0x8);
    mem_write32(ctx, RAM + 0x20, v + 1);
    ret(ctx, v);
}
void test_original_0x00100300(Context *ctx) { mem_write8(ctx, RAM + 0x30, 1); ctx->exit = EXIT_BUDGET; }
void test_original_0x00100400(Context *ctx) { (void)mem_read8(ctx, RAM + 0x31); ctx->exit = EXIT_UNWIND; }
void test_original_0x00100500(Context *ctx) {
    (void)mem_read32(ctx, RAM + 0x40);
    ctx->host->svc(ctx, 0x28);
    if (ctx->exit)
        return;
    ret(ctx, 1);
}
void test_original_0x00100600(Context *ctx) { ctx->host->interpret(ctx, 0x00100600u, 0xEE000000u); ret(ctx, 2); }
void test_original_0x00100700(Context *ctx) { ret(ctx, mem_read32(ctx, DEV + 4)); }
void test_original_0x00100800(Context *ctx) { mem_write8(ctx, ROM + 1, 3); ret(ctx, 0); }
/* hidden host state: replays differently */
void test_original_0x00100900(Context *ctx) {
    static uint32_t k;
    (void)mem_read32(ctx, RAM + 0x44);
    ret(ctx, k++);
}
/* ... in a store only (r0 the same) */
void test_original_0x00100908(Context *ctx) {
    static uint32_t k;
    mem_write32(ctx, RAM + 0x48, k++);
    ret(ctx, 0);
}
/* ... in a probe call made only the first time */
static void probe_0x00101F00(Context *ctx);
void test_original_0x00100904(Context *ctx) {
    static int done;
    if (!done++) {
        ctx->r[0] = 1;
        probe_0x00101F00(ctx);
    }
    ret(ctx, 0);
}
/* stores an out-parameter in the caller's frame, just above the entry sp */
void test_original_0x00100118(Context *ctx) {
    mem_write32(ctx, ctx->r[13] + 4, 0x11223344u);
    ret(ctx, 0);
}

/* hidden host state in one exit field each: run A must notice */
void test_original_0x00100910(Context *ctx) { static uint32_t k; ret(ctx, 0); ctx->vfp[5] = k++; }
void test_original_0x00100914(Context *ctx) { static uint32_t k; ret(ctx, 0); ctx->n = (uint8_t)(k++ & 1); }
void test_original_0x00100918(Context *ctx) { static uint32_t k; ret(ctx, 0); ctx->exclusive_address = k++; }
void test_original_0x0010091C(Context *ctx) { static uint32_t k; ret(ctx, 0); ctx->r[15] += 4 * k++; }
void test_original_0x00100920(Context *ctx) { static uint32_t k; ret(ctx, 0); *ctx->fpscr = (k++ & 3) << 22; }
/* ... in r1 of a probe call (r0 the same) */
void test_original_0x00100924(Context *ctx) {
    static uint32_t k;
    ctx->r[0] = 1;
    ctx->r[1] = k++;
    probe_0x00101F00(ctx);
    ctx->r[1] = 0; /* only the call saw it */
    ret(ctx, 0);
}
/* ... in what lookup finds */
void test_original_0x00100928(Context *ctx) { (void)ctx->host->lookup(ctx, 0x00101F04u); ret(ctx, 0); }
/* ... in where it writes: the first time the same value back, then to a page the record lacks */
void test_original_0x0010092C(Context *ctx) {
    static uint32_t k;
    uint32_t v = mem_read32(ctx, RAM + 0x4C);
    mem_write32(ctx, k++ ? RAM + 0x1804 : RAM + 0x4C, v);
    ret(ctx, 0);
}
/* ... in whether it stops */
void test_original_0x00100930(Context *ctx) {
    static uint32_t k;
    if (k++)
        ctx->exit = EXIT_BUDGET;
    else
        ret(ctx, 0);
}
/* faithful: byte stores at odd addresses */
void test_original_0x00100934(Context *ctx) {
    mem_write8(ctx, RAM + 0x35, (uint8_t)(mem_read8(ctx, RAM + 0x35) + 1));
    mem_write16(ctx, RAM + 0x37, 0x1234);
    ret(ctx, 0);
}
/* faithful: the host runs guest code while it looks up (nothing of it is noted) */
void test_original_0x00100938(Context *ctx) { (void)ctx->host->lookup(ctx, 0x00101F08u); ret(ctx, 0); }
/* an svc that changes the memory map, then a read through the new tables */
void test_original_0x0010093C(Context *ctx) {
    ctx->host->svc(ctx, 0x29);
    ret(ctx, mem_read32(ctx, RAM + 0x10));
}

static void probe_0x00100B00(Context *ctx);
/* outer writes, calls inner (a probe), reads what inner wrote */
void test_original_0x00100A00(Context *ctx) {
    mem_write32(ctx, RAM + 0x50, 7);
    probe_0x00100B00(ctx);
    if (ctx->exit)
        return;
    ret(ctx, mem_read32(ctx, RAM + 0x54));
}
void test_original_0x00100B00(Context *ctx) {
    uint32_t v = mem_read32(ctx, RAM + 0x50);
    mem_write32(ctx, RAM + 0x54, v * 2);
    ret(ctx, v);
}
/* touches two pages, the second through a word that crosses the boundary */
void test_original_0x00100C00(Context *ctx) { ret(ctx, mem_read32(ctx, RAM + 0xFFE)); }

/* an indirect call through lookup, as generated code does for a virtual call */
static void call_pure(Context *ctx) {
    Code code = ctx->host->lookup(ctx, 0x00101F00u);
    if (code == NULL) {
        ctx->exit = EXIT_UNWIND;
        return;
    }
    uint32_t lr = ctx->r[14];
    ctx->r[0] = 5;
    ctx->r[1] = ctx->r[2] = ctx->r[3] = 0;
    ctx->r[14] = FE_GUEST_RETURN;
    code(ctx);
    ctx->r[14] = lr;
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
void test_original_0x00100D00(Context *ctx) { call_pure(ctx); }
void test_original_0x00100D04(Context *ctx) { call_pure(ctx); }
void test_original_0x00100D08(Context *ctx) { call_pure(ctx); }
void test_original_0x00100D0C(Context *ctx) { call_pure(ctx); }
void test_original_0x00101F00(Context *ctx) { ret(ctx, ctx->r[0] + 1); } /* pure */

/* a one-time cache behind the guard routine */
static void probe_0x00100F00(Context *ctx);
void test_original_0x00100E00(Context *ctx) {
    if (mem_read32(ctx, RAM + 0x60) == 0) {
        probe_0x00100F00(ctx);
        mem_write32(ctx, RAM + 0x60, 1);
    }
    ret(ctx, mem_read32(ctx, RAM + 0x64));
}
void test_original_0x00100F00(Context *ctx) { ret(ctx, 1); }

/* an override that uses the guard: the cache filled on the cold path */
void test_original_0x00100E04(Context *ctx) {
    if (mem_read32(ctx, RAM + 0x68) == 0) {
        probe_0x00100F00(ctx);
        mem_write32(ctx, RAM + 0x68, 1);
    }
    ret(ctx, mem_read32(ctx, RAM + 0x6C));
}

/* a chain six calls deep */
static void probe_0x00101004(Context *ctx);
static void probe_0x00101008(Context *ctx);
static void probe_0x0010100C(Context *ctx);
static void probe_0x00101010(Context *ctx);
static void probe_0x00101014(Context *ctx);
void test_original_0x00101000(Context *ctx) { (void)mem_read8(ctx, RAM + 0x70); probe_0x00101004(ctx); }
void test_original_0x00101004(Context *ctx) { (void)mem_read8(ctx, RAM + 0x71); probe_0x00101008(ctx); }
void test_original_0x00101008(Context *ctx) { (void)mem_read8(ctx, RAM + 0x72); probe_0x0010100C(ctx); }
void test_original_0x0010100C(Context *ctx) { (void)mem_read8(ctx, RAM + 0x73); probe_0x00101010(ctx); }
void test_original_0x00101010(Context *ctx) { (void)mem_read8(ctx, RAM + 0x74); probe_0x00101014(ctx); }
void test_original_0x00101014(Context *ctx) { ret(ctx, mem_read8(ctx, RAM + 0x75)); }

/* probes, as tools/harness/gen_stubs.py will write them */
static void probe_0x00100300(Context *ctx) { FE_PROBE(0x00100300); }
static void probe_0x00100400(Context *ctx) { FE_PROBE(0x00100400); }
static void probe_0x00100500(Context *ctx) { FE_PROBE(0x00100500); }
static void probe_0x00100600(Context *ctx) { FE_PROBE(0x00100600); }
static void probe_0x00100700(Context *ctx) { FE_PROBE(0x00100700); }
static void probe_0x00100800(Context *ctx) { FE_PROBE(0x00100800); }
static void probe_0x00100900(Context *ctx) { FE_PROBE(0x00100900); }
static void probe_0x00100904(Context *ctx) { FE_PROBE(0x00100904); }
static void probe_0x00100908(Context *ctx) { FE_PROBE(0x00100908); }
static void probe_0x00100910(Context *ctx) { FE_PROBE(0x00100910); }
static void probe_0x00100914(Context *ctx) { FE_PROBE(0x00100914); }
static void probe_0x00100918(Context *ctx) { FE_PROBE(0x00100918); }
static void probe_0x0010091C(Context *ctx) { FE_PROBE(0x0010091C); }
static void probe_0x00100920(Context *ctx) { FE_PROBE(0x00100920); }
static void probe_0x00100924(Context *ctx) { FE_PROBE(0x00100924); }
static void probe_0x00100928(Context *ctx) { FE_PROBE(0x00100928); }
static void probe_0x0010092C(Context *ctx) { FE_PROBE(0x0010092C); }
static void probe_0x00100930(Context *ctx) { FE_PROBE(0x00100930); }
static void probe_0x00100934(Context *ctx) { FE_PROBE(0x00100934); }
static void probe_0x00100938(Context *ctx) { FE_PROBE(0x00100938); }
static void probe_0x0010093C(Context *ctx) { FE_PROBE(0x0010093C); }
static void probe_0x00100A00(Context *ctx) { FE_PROBE(0x00100A00); }
static void probe_0x00100B00(Context *ctx) { FE_PROBE(0x00100B00); }
static void probe_0x00100C00(Context *ctx) { FE_PROBE(0x00100C00); }
static void probe_0x00100E00(Context *ctx) { FE_PROBE(0x00100E00); }
static void probe_0x00100F00(Context *ctx) { FE_PROBE(0x00100F00); }
static void probe_0x00101000(Context *ctx) { FE_PROBE(0x00101000); }
static void probe_0x00101004(Context *ctx) { FE_PROBE(0x00101004); }
static void probe_0x00101008(Context *ctx) { FE_PROBE(0x00101008); }
static void probe_0x0010100C(Context *ctx) { FE_PROBE(0x0010100C); }
static void probe_0x00101010(Context *ctx) { FE_PROBE(0x00101010); }
static void probe_0x00101014(Context *ctx) { FE_PROBE(0x00101014); }
static void probe_0x00101F00(Context *ctx) { FE_PROBE(0x00101F00); }

/* ------------------------------------------------------------------------
   Readable functions under FE_ENTRY (run B) */

static uint32_t rd_sum(Context *ctx) { return guest_u32(ctx, RAM + 0x10) + guest_u32(ctx, RAM + 0x14); }
static uint32_t rd_sum_bad(Context *ctx) { return rd_sum(ctx) + 1; }
static uint32_t rd_sum_give_up(Context *ctx) { return fe_use_original(ctx); }
static uint32_t rd_sum_outside(Context *ctx) { return rd_sum(ctx) + 0 * guest_u32(ctx, RAM + 0x1800); }
static int rd_sum_runs;
static uint32_t rd_sum_counted(Context *ctx) { rd_sum_runs++; return rd_sum(ctx); }
/* returns the old value but does not store (a missing write) */
static uint32_t rd_inc(Context *ctx) { return guest_u32(ctx, RAM + 0x20); }
static uint32_t rd_call_pure(Context *ctx) { return guest_call1(ctx, 0x00101F00u, 5); }
static uint32_t rd_skip_call(Context *ctx) { (void)ctx; return 6; }
static uint32_t rd_no_out(Context *ctx) { (void)ctx; return 0; } /* forgets the out-parameter */
static uint32_t rd_call_wrong(Context *ctx) { (void)guest_call1(ctx, 0x00101F00u, 4); return 6; } /* wrong argument */
/* a stray store to a page the record does not have */
static uint32_t rd_sum_stray(Context *ctx) { guest_set_u32(ctx, RAM + 0x1800, 1); return rd_sum(ctx); }
/* calls another readable function directly in C, as stats.c does */
static uint32_t rd_outer(Context *ctx) { return rd_sum(ctx); }
static uint32_t rd_cache(Context *ctx) {
    if (guest_u32(ctx, RAM + 0x68) == 0)
        guest_set_u32(ctx, RAM + 0x68, 1);
    return guest_u32(ctx, RAM + 0x6C);
}

static void ov_sum(Context *ctx) { FE_ENTRY0(0x00100100, rd_sum); }
static void ov_sum_bad(Context *ctx) { FE_ENTRY0(0x00100104, rd_sum_bad); }
static void ov_sum_give_up(Context *ctx) { FE_ENTRY0(0x00100108, rd_sum_give_up); }
static void ov_sum_outside(Context *ctx) { FE_ENTRY0(0x0010010C, rd_sum_outside); }
static void ov_sum_clean(Context *ctx) { FE_ENTRY0(0x00100110, rd_sum); }
static void ov_sum_counted(Context *ctx) { FE_ENTRY0(0x00100114, rd_sum_counted); }
static void ov_inc(Context *ctx) { FE_ENTRY0(0x00100200, rd_inc); }
/* writes back the ROM word the original only reads: same value, so the
   memory compare alone would pass; the game could not do that store */
static uint32_t rd_inc_rom(Context *ctx) {
    guest_set_u32(ctx, ROM + 0x8, guest_u32(ctx, ROM + 0x8));
    uint32_t v = guest_u32(ctx, RAM + 0x20);
    guest_set_u32(ctx, RAM + 0x20, v + 1);
    return v;
}
static void ov_inc_rom(Context *ctx) { FE_ENTRY0(0x00100200, rd_inc_rom); }
static void ov_call_pure(Context *ctx) { FE_ENTRY0(0x00100D00, rd_call_pure); }
static void ov_skip_call(Context *ctx) { FE_ENTRY0(0x00100D04, rd_skip_call); }
static void ov_no_out(Context *ctx) { FE_ENTRY0(0x00100118, rd_no_out); }
static void ov_call_wrong(Context *ctx) { FE_ENTRY0(0x00100D08, rd_call_wrong); }
static void ov_sum_stray(Context *ctx) { FE_ENTRY0(0x0010011C, rd_sum_stray); }
/* late pages (HARNESS.md 5 rule 5): B reads a word of a page the original never
   touched, and uses it (wrong when the word is not 0) */
static uint32_t rd_sum_late_bad(Context *ctx) { return rd_sum(ctx) + guest_u32(ctx, RAM + 0x1804); }
static void ov_sum_late_bad(Context *ctx) { FE_ENTRY0(0x00100120, rd_sum_late_bad); }
/* B reads a device page (no pointer): never a late page */
static uint32_t rd_sum_dev(Context *ctx) { return rd_sum(ctx) + 0 * guest_u32(ctx, DEV + 0x10); }
static void ov_sum_dev(Context *ctx) { FE_ENTRY0(0x00100124, rd_sum_dev); }
/* B stores the same value back into a read-only page the original never touched: a late page
   keeps the game's "no writable pointer", so this is DEVICE, not a match */
static uint32_t rd_sum_rom_late(Context *ctx) { guest_set_u32(ctx, ROM + 0x10, guest_u32(ctx, ROM + 0x10)); return rd_sum(ctx); }
static void ov_sum_rom_late(Context *ctx) { FE_ENTRY0(0x00100128, rd_sum_rom_late); }
void test_original_0x00100130(Context *ctx);
static void ov_outer(Context *ctx) { FE_ENTRY0(0x00100130, rd_outer); }
/* the override call done inline, then a probe call B makes too */
static uint32_t rd_outer_call(Context *ctx) { (void)rd_sum(ctx); return guest_call1(ctx, 0x00101F00u, 5); }
void test_original_0x00100134(Context *ctx);
static void ov_outer_call(Context *ctx) { FE_ENTRY0(0x00100134, rd_outer_call); }
/* one call more than the original */
static uint32_t rd_call_twice(Context *ctx) { (void)guest_call1(ctx, 0x00101F00u, 5); return guest_call1(ctx, 0x00101F00u, 5); }
static void ov_call_twice(Context *ctx) { FE_ENTRY0(0x00100D0C, rd_call_twice); }
static void ov_cache(Context *ctx) { FE_ENTRY0(0x00100E04, rd_cache); }

/* the original of ov_outer calls the override of 0x00100100 the way generated
   code does (CALL(override_...)), so that call is noted in run A */
void test_original_0x00100130(Context *ctx) {
    ov_sum(ctx);
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
void test_original_0x00100134(Context *ctx) {
    uint32_t lr = ctx->r[14];
    ov_sum(ctx);
    if (ctx->exit)
        return;
    ctx->r[0] = 5;
    ctx->r[1] = ctx->r[2] = ctx->r[3] = 0;
    ctx->r[14] = FE_GUEST_RETURN;
    probe_0x00101F00(ctx);
    ctx->r[14] = lr;
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}

/* nested calls (HARNESS.md 5 rule 4, H5 route 2): the original of 0x0010013C
   makes the probe call 0x00101F00(5) itself, then calls the override
   0x00101F0C(3), whose original makes the probe call 0x00101F00(7). The
   readable side does the first call's work inline and calls 0x00101F0C
   through guest_call, so the probe call (7) in its list is made inside a
   noted call: only the calls a run made itself are compared */
void test_original_0x00101F0C(Context *ctx);
void test_original_0x0010013C(Context *ctx);
static uint32_t rd_wrap(Context *ctx, uint32_t x) { return guest_call1(ctx, 0x00101F00u, x + 4); }
static void ov_wrap(Context *ctx) { FE_ENTRY(0x00101F0C, rd_wrap, FE_ARG(0)); }
static void call_with(Context *ctx, Code code, uint32_t r0) {
    uint32_t lr = ctx->r[14];
    ctx->r[0] = r0;
    ctx->r[1] = ctx->r[2] = ctx->r[3] = 0;
    ctx->r[14] = FE_GUEST_RETURN;
    code(ctx);
    ctx->r[14] = lr;
}
void test_original_0x00101F0C(Context *ctx) {
    call_with(ctx, probe_0x00101F00, ctx->r[0] + 4);
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
void test_original_0x0010013C(Context *ctx) {
    call_with(ctx, probe_0x00101F00, 5);
    if (ctx->exit)
        return;
    call_with(ctx, ov_wrap, 3);
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
/* the other order: 0x00101F0C(3) first, then its own probe call 0x00101F00(5), which
   B makes too; B's nested call (7) sits between its own two calls */
void test_original_0x00100140(Context *ctx);
void test_original_0x00100140(Context *ctx) {
    call_with(ctx, ov_wrap, 3);
    if (ctx->exit)
        return;
    call_with(ctx, probe_0x00101F00, 5);
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
static uint32_t rd_wrap_then(Context *ctx) { (void)guest_call1(ctx, 0x00101F0Cu, 3); return guest_call1(ctx, 0x00101F00u, 5); }
static void ov_wrap_then(Context *ctx) { FE_ENTRY0(0x00100140, rd_wrap_then); }
/* composition: the original of 0x00100144 calls the override 0x00100148, whose
   original calls 0x00101F0C(3); the readable side runs 0x00100148's readable
   function in C, and that one calls 0x00101F0C through guest_call */
void test_original_0x00100144(Context *ctx);
void test_original_0x00100148(Context *ctx);
static uint32_t rd_mid(Context *ctx) { return guest_call1(ctx, 0x00101F0Cu, 3); }
static void ov_mid(Context *ctx) { FE_ENTRY0(0x00100148, rd_mid); }
void test_original_0x00100148(Context *ctx) {
    call_with(ctx, ov_wrap, 3);
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
void test_original_0x00100144(Context *ctx) {
    call_with(ctx, ov_mid, 0);
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
static uint32_t rd_top(Context *ctx) { return rd_mid(ctx); }
static void ov_top(Context *ctx) { FE_ENTRY0(0x00100144, rd_top); }
/* registers that are not arguments: the original of 0x0010014C leaves 0x55 in r1
   when it calls 0x00101F0C (one argument, FE_ENTRY says) and when it calls the
   probe 0x00101F00 (arguments not known: all four compared) */
void test_original_0x0010014C(Context *ctx);
void test_original_0x0010014C(Context *ctx) {
    uint32_t lr = ctx->r[14];
    ctx->r[0] = 3;
    ctx->r[1] = 0x55;
    ctx->r[14] = FE_GUEST_RETURN;
    ov_wrap(ctx);
    ctx->r[14] = lr;
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
void test_original_0x00100150(Context *ctx);
void test_original_0x00100150(Context *ctx) {
    uint32_t lr = ctx->r[14];
    ctx->r[0] = 5;
    ctx->r[1] = 0x55;
    ctx->r[14] = FE_GUEST_RETURN;
    probe_0x00101F00(ctx);
    ctx->r[14] = lr;
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
static uint32_t rd_r1_wrap(Context *ctx) { return guest_call1(ctx, 0x00101F0Cu, 3); }
static uint32_t rd_r1_probe(Context *ctx) { return guest_call1(ctx, 0x00101F00u, 5); }
static void ov_r1_wrap(Context *ctx) { FE_ENTRY0(0x0010014C, rd_r1_wrap); }
static void ov_r1_probe(Context *ctx) { FE_ENTRY0(0x00100150, rd_r1_probe); }
static uint32_t rd_outer_wrap(Context *ctx) { return guest_call1(ctx, 0x00101F0Cu, 3); }
/* ... with another argument for the call it makes itself */
static uint32_t rd_outer_wrap_bad(Context *ctx) { (void)guest_call1(ctx, 0x00101F0Cu, 2); return 8; }
/* ... making the nested call itself, and not the one the original made */
static uint32_t rd_outer_wrap_own(Context *ctx) { (void)guest_call1(ctx, 0x00101F00u, 7); return 8; }
static void ov_outer_wrap(Context *ctx) { FE_ENTRY0(0x0010013C, rd_outer_wrap); }
static void ov_outer_wrap_bad(Context *ctx) { FE_ENTRY0(0x0010013C, rd_outer_wrap_bad); }
static void ov_outer_wrap_own(Context *ctx) { FE_ENTRY0(0x0010013C, rd_outer_wrap_own); }
/* the walk after a matched call: the original of 0x00100154 calls
   0x00101F0C(3) (B calls it too), then the override 0x00100148, whose original
   calls 0x00101F0C(3) again. B calls 0x00101F0C itself, then runs 0x00100148's
   readable function in C: the second 0x00101F0C sits inside a call B did
   inline, after a matched call, and is still one of the calls B is held to */
void test_original_0x00100154(Context *ctx);
void test_original_0x00100154(Context *ctx) {
    call_with(ctx, ov_wrap, 3);
    if (ctx->exit)
        return;
    call_with(ctx, ov_mid, 0);
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
static uint32_t rd_wrap_mid(Context *ctx) { (void)guest_call1(ctx, 0x00101F0Cu, 3); return rd_mid(ctx); }
static void ov_wrap_mid(Context *ctx) { FE_ENTRY0(0x00100154, rd_wrap_mid); }
/* three levels: the original of 0x00100158 calls the override 0x00100148
   (done inline by B), whose original calls 0x00101F0C(3) (B calls it), whose
   original calls 0x00101F00(7) at level 2 (skipped); then it calls
   0x00101F00(5) itself, as B does. Levels cut to 0/1 would hold B's
   0x00101F00(5) against the level-2 0x00101F00(7) */
void test_original_0x00100158(Context *ctx);
void test_original_0x00100158(Context *ctx) {
    call_with(ctx, ov_mid, 0);
    if (ctx->exit)
        return;
    call_with(ctx, probe_0x00101F00, 5);
    if (ctx->exit)
        return;
    ret(ctx, ctx->r[0]);
}
static uint32_t rd_mid_then(Context *ctx) { (void)rd_mid(ctx); return guest_call1(ctx, 0x00101F00u, 5); }
static void ov_mid_then(Context *ctx) { FE_ENTRY0(0x00100158, rd_mid_then); }

/* ------------------------------------------------------------------------
   Helpers */

static char base_dir[900];

static void dir_of(char *out, size_t size, const char *name) { snprintf(out, size, "%s/%s", base_dir, name); }

static void config(const char *dir_name, const char *only, int store, int live, uint32_t keep, uint32_t max_pages,
                   uint64_t max_bytes) {
    static char dir[1000];
    fe_capture_reset();
    FeCapConfig c;
    memset(&c, 0, sizeof c);
    if (dir_name) {
        dir_of(dir, sizeof dir, dir_name);
        c.dir = dir;
    }
    c.only = only;
    c.store = store;
    c.live = live;
    c.keep = keep;
    c.max_pages = max_pages;
    c.max_bytes = max_bytes;
    c.guard = 0x00100F00u;
    fe_capture_configure(&c);
}

static FeCapInfo last(void) {
    FeCapInfo i;
    fe_capture_last(&i);
    return i;
}
static FeCapStats stats(void) {
    FeCapStats s;
    fe_capture_stats(&s);
    return s;
}
static FeCapFnStats fn(uint32_t address) {
    FeCapFnStats s;
    fe_capture_fn_stats(address, &s);
    return s;
}

static long file_size(const char *path) {
    FILE *f = fopen(path, "rb");
    if (f == NULL)
        return -1;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fclose(f);
    return n;
}

/* reads records.fecap: up to max headers and, for each, its pages */
typedef struct Parsed {
    FeCapHeader h;
    FeCapPage pages[8];
    FeCapEvent events[8];
    FeCapNote notes[4];
} Parsed;

static int parse_records(const char *dir, Parsed *out, int max) {
    char path[1100];
    snprintf(path, sizeof path, "%s/records.fecap", dir);
    FILE *f = fopen(path, "rb");
    if (f == NULL)
        return -1;
    int n = 0;
    while (n < max) {
        Parsed *p = &out[n];
        memset(p, 0, sizeof *p);
        if (fread(&p->h, sizeof p->h, 1, f) != 1)
            break;
        if (memcmp(p->h.magic, FE_CAP_MAGIC, 8) != 0 || p->h.version != FE_CAP_VERSION ||
            p->h.header_bytes != sizeof p->h) {
            n = -2;
            break;
        }
        for (uint32_t i = 0; i < p->h.page_count; i++) {
            FeCapPage pg;
            if (fread(&pg, sizeof pg, 1, f) != 1)
                goto done;
            if (i < 8)
                p->pages[i] = pg;
        }
        for (uint32_t i = 0; i < p->h.event_count; i++) {
            FeCapEvent e;
            if (fread(&e, sizeof e, 1, f) != 1)
                goto done;
            if (i < 8)
                p->events[i] = e;
        }
        fseek(f, (long)(p->h.lookup_count * sizeof(FeCapLookup)), SEEK_CUR);
        for (uint32_t i = 0; i < p->h.note_count; i++) {
            FeCapNote e;
            if (fread(&e, sizeof e, 1, f) != 1)
                goto done;
            if (i < 4)
                p->notes[i] = e;
        }
        n++;
    }
done:
    fclose(f);
    return n;
}

static const FeCapPage *page_of(const Parsed *p, uint32_t base) {
    for (uint32_t i = 0; i < p->h.page_count && i < 8; i++)
        if (p->pages[i].address == base)
            return &p->pages[i];
    return NULL;
}

static int read_page_file(const char *dir, const FeCapPage *pg, uint8_t *out) {
    char path[1200];
    snprintf(path, sizeof path, "%s/pages/%08X%08X%08X%08X.pg", dir, (unsigned)pg->hash[3], (unsigned)pg->hash[2],
             (unsigned)pg->hash[1], (unsigned)pg->hash[0]);
    FILE *f = fopen(path, "rb");
    if (f == NULL)
        return 0;
    size_t n = fread(out, 1, 4096, f);
    fclose(f);
    return n == 4096;
}

static int bit(const uint8_t *bits, uint32_t i) { return (bits[i >> 3] >> (i & 7)) & 1; }

/* ------------------------------------------------------------------------
   Tests */

static void test_sampling(void) {
    CHECK(!fe_capture_sampled(0));
    for (uint32_t n = 1; n <= 16; n++)
        CHECK(fe_capture_sampled(n));
    CHECK(!fe_capture_sampled(17));
    CHECK(!fe_capture_sampled(31));
    CHECK(fe_capture_sampled(32));
    CHECK(!fe_capture_sampled(48));
    CHECK(fe_capture_sampled(64));
    CHECK(fe_capture_sampled(1024));
    CHECK(!fe_capture_sampled(1025));

    config(NULL, NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    Context c = fresh();
    for (int i = 0; i < 100; i++) {
        c.r[0] = (uint32_t)i;
        probe_0x00101F00(&c);
        CHECK_EQ(c.r[0], (uint32_t)i + 1);
    }
    FeCapFnStats s = fn(0x00101F00u);
    CHECK_EQ(s.calls, 100);
    CHECK_EQ(s.records, 18); /* 1..16, 32, 64 */
    CHECK_EQ(s.verdicts[FE_CAP_V_FAITHFUL], 18);
    CHECK_EQ(stats().sampled, 18);
    CHECK(restored(&c));
}

static void test_paths_restore(void) {
    config(NULL, NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    Context c = fresh();
    uint32_t before;

    /* budget exit inside: INCOMPLETE, the exit stays for the host, the write happened once */
    ram[0][0x30] = 0;
    probe_0x00100300(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.exit, EXIT_BUDGET);
    CHECK_EQ(ram[0][0x30], 1);
    CHECK_EQ(last().verdict, FE_CAP_V_INCOMPLETE);
    CHECK(last().flags & FE_CAP_INCOMPLETE);
    CHECK_EQ(last().exit_code, EXIT_BUDGET);
    CHECK_EQ(c.depth, 0);

    c = fresh();
    probe_0x00100400(&c); /* unwind */
    CHECK(restored(&c));
    CHECK_EQ(c.exit, EXIT_UNWIND);
    CHECK_EQ(last().verdict, FE_CAP_V_INCOMPLETE);

    /* svc run in place: ESCAPED; the real host saw its own fields */
    c = fresh();
    fwd_bad = 0;
    svc_mode = SVC_IN_PLACE;
    before = (uint32_t)svc_count;
    probe_0x00100500(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.exit, EXIT_NONE);
    CHECK_EQ(c.r[0], 1);
    CHECK_EQ((uint32_t)svc_count, before + 1);
    CHECK_EQ(last().verdict, FE_CAP_V_ESCAPED);
    CHECK(last().flags & FE_CAP_ESCAPED_SVC);
    CHECK_EQ(fwd_bad, 0);

    /* svc that stops the code (thread switch) */
    c = fresh();
    svc_mode = SVC_UNWIND;
    probe_0x00100500(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.exit, EXIT_UNWIND);
    CHECK(last().flags & FE_CAP_INCOMPLETE);
    CHECK(last().flags & FE_CAP_ESCAPED_SVC);

    /* svc left for the host's loop */
    c = fresh();
    svc_mode = SVC_LEAVE;
    probe_0x00100500(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.exit, EXIT_SVC);
    CHECK_EQ(c.svc, 0x28);

    /* the host runs another guest thread inside the svc: not recorded, not noted */
    c = fresh();
    svc_mode = SVC_OTHER_CTX;
    other_ctx = fresh();
    uint32_t pure_calls = fn(0x00101F00u).calls, pure_records = fn(0x00101F00u).records;
    probe_0x00100500(&c);
    CHECK(restored(&c));
    CHECK(restored(&other_ctx));
    CHECK_EQ(other_ctx.r[0], 2);
    CHECK_EQ(fn(0x00101F00u).calls, pure_calls);     /* ran plain, inside a forwarded callback */
    CHECK_EQ(fn(0x00101F00u).records, pure_records);
    CHECK_EQ(last().note_count, 0);
    CHECK_EQ(fwd_bad, 0);
    svc_mode = SVC_IN_PLACE;

    /* interpreter */
    c = fresh();
    probe_0x00100600(&c);
    CHECK(restored(&c));
    CHECK_EQ(interp_count, 1);
    CHECK(last().flags & FE_CAP_ESCAPED_INTERP);
    CHECK_EQ(last().verdict, FE_CAP_V_ESCAPED);

    /* device memory read; write to a page without a writable pointer */
    c = fresh();
    before = (uint32_t)dev_reads;
    probe_0x00100700(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 0x5A5A5A5Au);
    CHECK_EQ((uint32_t)dev_reads, before + 4);
    CHECK(last().flags & FE_CAP_HOSTMEM_R);
    CHECK_EQ(last().verdict, FE_CAP_V_HOSTMEM);
    c = fresh();
    before = (uint32_t)dev_writes;
    probe_0x00100800(&c);
    CHECK(restored(&c));
    CHECK_EQ((uint32_t)dev_writes, before + 1); /* forwarded to the real host */
    CHECK_EQ(dev_last, ROM + 1);
    CHECK(last().flags & FE_CAP_HOSTMEM_W);

    /* the depth limit: refused like CALL, nothing swapped, the original never ran */
    c = fresh();
    c.depth = RECOMP_DEPTH_LIMIT;
    uint32_t sampled = stats().sampled;
    ram[0][0x30] = 0;
    probe_0x00100300(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.exit, EXIT_UNWIND);
    CHECK_EQ(c.depth, RECOMP_DEPTH_LIMIT);
    CHECK_EQ(ram[0][0x30], 0);
    CHECK_EQ(stats().sampled, sampled);

    /* a call that is not sampled (17th) swaps nothing either */
    for (int i = 0; i < 20; i++) {
        c = fresh();
        probe_0x00100C00(&c);
        CHECK(restored(&c));
    }
    CHECK_EQ(fn(0x00100C00u).records, 16);
    CHECK_EQ(fn(0x00100C00u).calls, 20);
    CHECK_EQ(fn(0x00100C00u).verdicts[FE_CAP_V_FAITHFUL], 16); /* crossing word, two pages */

    /* hidden host state: run A differs, UNFAITHFUL */
    c = fresh();
    probe_0x00100900(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_UNFAITHFUL);
    CHECK(strstr(last().detail, "r0") != NULL);
    c = fresh();
    probe_0x00100908(&c);
    CHECK_EQ(last().verdict, FE_CAP_V_UNFAITHFUL);
    CHECK(strstr(last().detail, "byte 00100048") != NULL);
    c = fresh();
    probe_0x00100904(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_UNFAITHFUL);
    CHECK(strstr(last().detail, "probe calls: 1 vs 0") != NULL);
}

static void test_truncated(void) {
    config(NULL, NULL, 0, FE_CAP_LIVE_AB, 0, 1, 0);
    Context c = fresh();
    probe_0x00100C00(&c); /* needs two pages, the cap is one */
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_TRUNCATED);
    CHECK(last().flags & FE_CAP_TRUNCATED);
    CHECK_EQ(last().page_count, 1);
}

static void test_live_compare(void) {
    config("live", NULL, 0, FE_CAP_LIVE_AB, 2, 0, 0);
    char dir[1000];
    dir_of(dir, sizeof dir, "live");
    Context c;

    set32(RAM + 0x10, 40);
    set32(RAM + 0x14, 2);
    c = fresh();
    ov_sum(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 42);
    CHECK_EQ(c.exit, EXIT_NONE);
    CHECK_EQ(c.r[15], LR0);
    CHECK_EQ(c.budget, 1000);
    CHECK_EQ(c.depth, 0);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK_EQ(get32(SP0 - 8), 0xDEADBEEFu); /* the game's own write happened (once) */

    c = fresh();
    ov_sum_bad(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 42); /* the game still gets the original's result */
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_R0);
    CHECK(strstr(last().detail, "run B 0000002B") != NULL);
    CHECK(last().stored);

    c = fresh();
    ov_sum_give_up(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 42);
    CHECK_EQ(c.exit, EXIT_NONE);
    CHECK_EQ(last().verdict, FE_CAP_V_GAVE_UP);
    CHECK(!last().stored);

    c = fresh();
    ov_sum_outside(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_B_ESCAPED);

    /* a store to a page the game had no writable pointer for (DEVICE) is an
       escape even when it stores the value already there (HARNESS.md 3.4) */
    c = fresh();
    ov_inc_rom(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_B_ESCAPED);
    CHECK(strstr(last().detail, "bits 10") != NULL);
    CHECK(strstr(last().detail, "00200008") != NULL);

    /* a missing write: B runs on the ENTRY snapshot (it reads the old value,
       so r0 agrees) and the memory compare catches the store B left out */
    set32(RAM + 0x20, 9);
    c = fresh();
    ov_inc(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 9);
    CHECK_EQ(get32(RAM + 0x20), 10); /* incremented exactly once: runs A and B never touch the game */
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_MEM);
    CHECK(strstr(last().detail, "byte 00100020: run A 0A, run B 09") != NULL);

    /* probe calls: through guest_call they match; a pure call done inline
       (never made by B) is info; a call B makes with another argument is a mismatch */
    c = fresh();
    ov_call_pure(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 6);
    CHECK_EQ(fn(0x00100D00u).verdicts[FE_CAP_V_MATCH], 1);
    CHECK_EQ(stats().calls_inlined, 0);
    c = fresh();
    ov_skip_call(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK(strstr(last().detail, "1 call(s) of run A not made by run B") != NULL);
    CHECK_EQ(stats().calls_inlined, 1);
    CHECK_EQ(last().lookup_count, 1);
    CHECK_EQ(last().note_count, 1);
    c = fresh();
    ov_call_wrong(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 6);
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_CALLS);
    CHECK(strstr(last().detail, "(r0=00000005) vs (r0=00000004)") != NULL);

    /* the caller's frame above the entry sp is compared (only the call's own dead stack is not) */
    c = fresh();
    ov_no_out(&c);
    CHECK(restored(&c));
    CHECK_EQ(get32(SP0 + 4), 0x11223344u);
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_MEM);
    CHECK(strstr(last().detail, "byte 0FFFF004") != NULL);

    /* keep: at most 2 bad records of one function on disk */
    for (int i = 0; i < 3; i++) {
        c = fresh();
        ov_sum_bad(&c);
    }
    FeCapFnStats s = fn(0x00100104u);
    CHECK_EQ(s.verdicts[FE_CAP_V_MISMATCH_R0], 4);
    CHECK_EQ(s.kept, 2);
    CHECK_EQ(strcmp(s.verdict, "MISMATCH"), 0);

    /* a function that passes on several paths, deep ones included */
    static const uint32_t a[10] = {0, 1, 0, 0x100000, 7, 0, 0, 3, 0xFFFFFFFFu, 20};
    for (int i = 0; i < 10; i++) {
        set32(RAM + 0x10, a[i]);
        set32(RAM + 0x14, 0);
        c = fresh();
        ov_sum_clean(&c);
        CHECK_EQ(c.r[0], a[i]);
    }
    s = fn(0x00100110u);
    CHECK_EQ(s.verdicts[FE_CAP_V_MATCH], 10);
    CHECK(s.signature_count >= 2);
    CHECK(s.deep >= 1);
    CHECK_EQ(strcmp(s.verdict, "REPLAY-CLEAN"), 0);

    /* only the bad ones went to disk */
    FeCapStats st = stats();
    CHECK_EQ(st.records_written, 7); /* sum_bad (2 of 4 kept), outside, inc_rom, inc, call_wrong, no_out */
    fe_capture_flush();
    char path[1100];
    snprintf(path, sizeof path, "%s/summary.tsv", dir);
    FILE *f = fopen(path, "r");
    CHECK(f != NULL);
    if (f) {
        char line[2048];
        int header = 0, clean_row = 0, writers = 0;
        while (fgets(line, sizeof line, f)) {
            if (!strncmp(line, "address\tkind\tverdict\tcalls\trecords\tmatch\t", 41))
                header = 1;
            if (!strncmp(line, "0x00100110\toverride\tREPLAY-CLEAN\t10\t10\t10\t", 41))
                clean_row = 1;
            /* the writer gate's run totals (docs/WRITERS.md): no writer in a capture, every count 0 */
            if (!strcmp(line, "# writers: log 0; stores 0; restored 0; sessions 0; refusals 0; mode_refusals 0; "
                              "stray 0; dropped 0\n"))
                writers = 1;
        }
        fclose(f);
        CHECK(header);
        CHECK(clean_row);
        CHECK(writers);
    }
    /* the totals are printed as runtime.c holds them (writer.c keeps them current in a library build) */
    fe_writer_totals[1] = 3; /* stores */
    fe_writer_totals[4] = 7; /* refusals */
    fe_capture_flush();
    f = fopen(path, "r");
    CHECK(f != NULL);
    if (f) {
        char line[2048];
        int seen = 0;
        while (fgets(line, sizeof line, f))
            if (!strcmp(line, "# writers: log 0; stores 3; restored 0; sessions 0; refusals 7; mode_refusals 0; "
                              "stray 0; dropped 0\n"))
                seen = 1;
        fclose(f);
        CHECK(seen);
    }
    fe_writer_totals[1] = fe_writer_totals[4] = 0;
    Parsed recs[8];
    int n = parse_records(dir, recs, 8);
    CHECK_EQ(n, (int)st.records_written);
    if (n > 0) {
        CHECK_EQ(recs[0].h.address, 0x00100104u);
        CHECK_EQ(recs[0].h.verdict, FE_CAP_V_MISMATCH_R0);
        CHECK(recs[0].h.flags & FE_CAP_VALID);
    }
}

static void test_fe_entry_modes(void) {
    /* outside capture mode nothing here runs */
    fe_force_mode(FE_MODE_SHADOW);
    config(NULL, NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    set32(RAM + 0x10, 1);
    set32(RAM + 0x14, 2);
    Context c = fresh();
    ov_sum_counted(&c);
    CHECK_EQ(c.r[0], 3);
    CHECK_EQ(stats().calls, 0);
    CHECK_EQ(rd_sum_runs, 1); /* shadow ran it on the real state */
    fe_force_mode(FE_MODE_CAPTURE);
    c = fresh();
    ov_sum_counted(&c);
    CHECK_EQ(c.r[0], 3);
    CHECK_EQ(stats().calls, 1);
    CHECK_EQ(rd_sum_runs, 2); /* run B only */
    /* FE_CAPTURE_LIVE=a: no run B */
    config(NULL, NULL, 0, FE_CAP_LIVE_A, 0, 0, 0);
    c = fresh();
    ov_sum_counted(&c);
    CHECK_EQ(rd_sum_runs, 2);
    CHECK_EQ(last().verdict, FE_CAP_V_FAITHFUL);
}

static int sink_calls;
static uint32_t sink_callee;
static void sink(Context *ctx, uint32_t callee) {
    (void)ctx;
    sink_calls++;
    sink_callee = callee;
}

static void test_probe_outside_capture(void) {
    fe_force_mode(FE_MODE_ORIGINAL);
    config(NULL, NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    Context c = fresh();
    probe_0x00101F00(&c); /* no sink: just the original */
    c.r[0] = 10;
    fe_probe_set_sink(sink);
    probe_0x00101F00(&c);
    fe_probe_set_sink(NULL);
    CHECK_EQ(c.r[0], 11);
    CHECK_EQ(sink_calls, 1);
    CHECK_EQ(sink_callee, 0x00101F00u);
    CHECK_EQ(stats().calls, 0);
    fe_force_mode(FE_MODE_CAPTURE);
}

static void test_nesting_and_store(void) {
    char dir[1000];
    dir_of(dir, sizeof dir, "nest");
    config("nest", "0x00100A00,00100B00", 1, FE_CAP_LIVE_AB, 0, 0, 0);
    set32(RAM + 0x50, 1);
    set32(RAM + 0x54, 0);
    Context c = fresh();
    probe_0x00100A00(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 14);
    CHECK_EQ(get32(RAM + 0x54), 14);
    CHECK_EQ(fn(0x00100B00u).verdicts[FE_CAP_V_FAITHFUL], 1); /* needs the inner snapshot to hold 7 */
    CHECK_EQ(fn(0x00100A00u).verdicts[FE_CAP_V_FAITHFUL], 1); /* replays inner too, with a note */
    fe_capture_flush();
    Parsed recs[4];
    int n = parse_records(dir, recs, 4);
    CHECK_EQ(n, 2);
    if (n == 2) {
        const Parsed *in = &recs[0], *out = &recs[1]; /* the inner one finishes first */
        CHECK_EQ(in->h.address, 0x00100B00u);
        CHECK_EQ(in->h.depth, 2);
        CHECK(in->h.flags & FE_CAP_NESTED);
        CHECK_EQ(out->h.address, 0x00100A00u);
        CHECK_EQ(out->h.depth, 1);
        CHECK(!(out->h.flags & FE_CAP_NESTED));
        CHECK_EQ(out->h.note_count, 1);
        CHECK_EQ(out->notes[0].callee, 0x00100B00u);
        CHECK(out->h.sequence < in->h.sequence);
        uint8_t bytes[4096];
        const FeCapPage *pi = page_of(in, RAM), *po = page_of(out, RAM);
        CHECK(pi && po);
        if (pi && po) {
            /* page copy at each record's own entry, before its first write */
            CHECK(read_page_file(dir, pi, bytes));
            CHECK_EQ(bytes[0x50], 7);
            CHECK(read_page_file(dir, po, bytes));
            CHECK_EQ(bytes[0x50], 1);
            CHECK_EQ(bytes[0x54], 0);
            CHECK(bit(po->write_bits, 0x50));
            CHECK(bit(po->write_bits, 0x54)); /* the inner call's write is in the outer record too */
            CHECK(bit(po->read_bits, 0x54));
            CHECK(!bit(po->read_bits, 0x58));
            CHECK(po->flags & FE_CAP_PAGE_COPIED);
        }
        CHECK_EQ(out->h.event_count, 2);
        CHECK_EQ(out->events[0].address, RAM + 0x50);
        CHECK_EQ(out->events[0].old_value, 1);
        CHECK_EQ(out->events[0].new_value, 7);
        CHECK_EQ(out->events[0].kind, FE_CAP_EV_WRITE | 4u << 8);
        CHECK_EQ(out->h.exit.r[0], 14);
        CHECK_EQ(out->h.entry.r[13], SP0);
    }
    /* same state again: every page is already on disk */
    set32(RAM + 0x50, 1);
    set32(RAM + 0x54, 0);
    uint32_t written = stats().pages_written;
    c = fresh();
    probe_0x00100A00(&c);
    CHECK_EQ(stats().pages_written, written);
    CHECK(stats().pages_deduped >= 2);
    /* everything passed: the working set is removed at the end */
    fe_capture_finish();
    char path[1100];
    snprintf(path, sizeof path, "%s/records.fecap", dir);
    CHECK_EQ(file_size(path), -1);
    snprintf(path, sizeof path, "%s/summary.tsv", dir);
    CHECK(file_size(path) > 0); /* the summary stays */

    /* six deep: records at depth 1-4 only */
    config(NULL, NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    c = fresh();
    probe_0x00101000(&c);
    CHECK(restored(&c));
    for (uint32_t k = 0; k < 6; k++) {
        FeCapFnStats s = fn(0x00101000u + 4 * k);
        CHECK_EQ(s.calls, 1);
        CHECK_EQ(s.records, k < FE_CAP_MAX_DEPTH ? 1u : 0u);
    }
    CHECK_EQ(last().address, 0x00101000u);
    CHECK_EQ(last().verdict, FE_CAP_V_FAITHFUL);
}

static void test_store_rules(void) {
    char dir[1000], path[1100];
    /* store without a working set is ignored: good records stay in memory */
    config("store_all", NULL, 1, FE_CAP_LIVE_AB, 0, 0, 0);
    Context c = fresh();
    ov_sum(&c);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK_EQ(stats().records_written, 0);
    fe_capture_finish();
    dir_of(dir, sizeof dir, "store_all");
    snprintf(path, sizeof path, "%s/records.fecap", dir);
    CHECK_EQ(file_size(path), -1);

    /* a store-mode session with a bad verdict keeps its files */
    config("store_bad", "00100104, 0x00100100", 1, FE_CAP_LIVE_AB, 0, 0, 0);
    c = fresh();
    ov_sum_bad(&c);
    c = fresh();
    ov_sum(&c); /* a good one too: the bad one still keeps the files */
    CHECK_EQ(fn(0x00100100u).verdicts[FE_CAP_V_MATCH], 1);
    c = fresh();
    ov_sum_clean(&c); /* not selected: counted, never recorded */
    CHECK_EQ(fn(0x00100110u).calls, 1);
    CHECK_EQ(fn(0x00100110u).records, 0);
    CHECK_EQ(stats().records_written, 2);
    fe_capture_finish();
    dir_of(dir, sizeof dir, "store_bad");
    snprintf(path, sizeof path, "%s/records.fecap", dir);
    CHECK(file_size(path) > 0);

    /* store and keep: every record passed, the files stay (offline replay of game records) */
    config("store_keep", "0x00100100", FE_CAP_STORE_KEEP, FE_CAP_LIVE_AB, 0, 0, 0);
    c = fresh();
    ov_sum(&c);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK_EQ(stats().records_written, 1);
    fe_capture_finish();
    dir_of(dir, sizeof dir, "store_keep");
    snprintf(path, sizeof path, "%s/records.fecap", dir);
    CHECK(file_size(path) > 0);

    /* the size cap */
    config("cap", NULL, 0, FE_CAP_LIVE_AB, 0, 0, 64);
    c = fresh();
    ov_sum_bad(&c);
    CHECK_EQ(stats().records_dropped, 1);
    CHECK_EQ(stats().records_written, 0);
    CHECK(!last().stored);

    /* a folder outside build/ or play/ is refused: nothing is written */
    fe_capture_reset();
    FeCapConfig cfg;
    memset(&cfg, 0, sizeof cfg);
    cfg.dir = "capture_test_refused";
    fe_capture_configure(&cfg);
    c = fresh();
    ov_sum_bad(&c);
    CHECK_EQ(stats().records_written, 0);
    CHECK_EQ(file_size("capture_test_refused/records.fecap"), -1);
}

static void test_cold_warm(void) {
    config(NULL, NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    set32(RAM + 0x60, 0);
    set32(RAM + 0x64, 5);
    for (int i = 0; i < 3; i++) {
        Context c = fresh();
        probe_0x00100E00(&c);
        CHECK(restored(&c));
        CHECK_EQ(c.r[0], 5);
    }
    FeCapFnStats s = fn(0x00100E00u);
    CHECK_EQ(s.verdicts[FE_CAP_V_FAITHFUL], 3);
    CHECK_EQ(s.cold, 1);
    CHECK_EQ(s.warm, 2);
    CHECK_EQ(fn(0x00100F00u).records, 1);
}

/* run A must notice every kind of difference from the game (hidden host state) */
static void test_fidelity_fields(void) {
    config(NULL, NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    static void (*const probes[])(Context *) = {probe_0x00100910, probe_0x00100914, probe_0x00100918,
                                                probe_0x0010091C, probe_0x00100920, probe_0x00100924,
                                                probe_0x00100928, probe_0x0010092C, probe_0x00100930};
    static const char *const want[] = {"s5 ", "flags differ", "exclusive monitor", "r15 ", "fpscr ", "(r1=",
                                       "lookups differ", "run A wrote 00101000, outside the record",
                                       "run A stopped (exit"};
    for (int i = 0; i < 9; i++) {
        Context c = fresh();
        uint32_t keep_vfp = vfp[5], keep_fpscr = fpscr;
        probes[i](&c);
        CHECK(restored(&c));
        CHECK_EQ(last().verdict, FE_CAP_V_UNFAITHFUL);
        if (strstr(last().detail, want[i]) == NULL) {
            checks++;
            failures++;
            printf("  FAIL fidelity case %d: detail \"%s\", want \"%s\"\n", i, last().detail, want[i]);
        }
        vfp[5] = keep_vfp;
        fpscr = keep_fpscr;
    }
    /* the game's values, not run A's, stay in the Context */
    vfp[5] = 0;
    Context c = fresh();
    probe_0x00100910(&c); /* k = 2 in the game, 3 in run A */
    CHECK_EQ(vfp[5], 2);
    vfp[5] = 0;

    /* faithful: odd-address stores; guest code run inside a forwarded lookup */
    c = fresh();
    probe_0x00100934(&c);
    CHECK_EQ(last().verdict, FE_CAP_V_FAITHFUL);
    other_ctx = fresh();
    fwd_bad = 0;
    c = fresh();
    probe_0x00100938(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_FAITHFUL);
    CHECK_EQ(last().note_count, 0);
    CHECK_EQ(fwd_bad, 0);

    /* the host switches tables inside an svc: the new ones are kept, used and left in place */
    set32(RAM + 0x10, 0x1111);
    ram2[0x10] = 0x22;
    ram2[0x11] = ram2[0x12] = ram2[0x13] = 0;
    svc_mode = SVC_SWITCH;
    fwd_bad = 0;
    c = fresh();
    probe_0x0010093C(&c);
    CHECK(c.read_pages == (uint8_t *const *)rtab2);
    CHECK(c.write_pages == (uint8_t *const *)wtab2);
    CHECK(c.host == &fake_host);
    CHECK_EQ(c.r[0], 0x22); /* read through the new table */
    CHECK_EQ(last().verdict, FE_CAP_V_ESCAPED);
    CHECK_EQ(fwd_bad, 0);
    svc_mode = SVC_IN_PLACE;
    exp_r = rtab;
    exp_w = wtab;
}

/* more run B cases */
static void test_run_b_more(void) {
    config(NULL, NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    set32(RAM + 0x10, 40);
    set32(RAM + 0x14, 2);
    /* a readable function calling another one in C: the original's override call is done inline */
    Context c = fresh();
    ov_outer(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 42);
    CHECK_EQ(fn(0x00100130u).verdicts[FE_CAP_V_MATCH], 1);
    CHECK_EQ(fn(0x00100100u).verdicts[FE_CAP_V_MATCH], 1); /* the nested override, recorded on its own */

    /* an inline call before one B makes: only the inline one is left out */
    c = fresh();
    ov_outer_call(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 6);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK(strstr(last().detail, "1 call(s) of run A") != NULL);
    /* B's guest call of an override whose original makes a call that A made
       itself too: the nested call is not one of B's own (H5 route 2) */
    c = fresh();
    ov_outer_wrap(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 8);
    CHECK_EQ(last().address, 0x0010013Cu);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK(strstr(last().detail, "1 call(s) of run A") != NULL);
    CHECK_EQ(last().note_count, 3); /* the game's list stays whole: 1F00(5), 1F0C(3), 1F00(7) */
    c = fresh();
    ov_outer_wrap_bad(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_CALLS);
    CHECK(strstr(last().detail, "00101F0C(r0=00000003) vs (r0=00000002)") != NULL);
    c = fresh();
    ov_outer_wrap_own(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_CALLS);
    CHECK(strstr(last().detail, "00101F00(r0=00000005) vs (r0=00000007)") != NULL);
    c = fresh();
    ov_wrap_then(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 6);
    CHECK_EQ(last().address, 0x00100140u);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    /* composition: A's call of 0x00101F0C sits inside a call B did inline */
    c = fresh();
    ov_top(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 8);
    CHECK_EQ(last().address, 0x00100144u);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK(strstr(last().detail, "1 call(s) of run A") != NULL);
    /* a call inside a call B did inline, right after a matched call */
    c = fresh();
    ov_wrap_mid(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 8);
    CHECK_EQ(last().address, 0x00100154u);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK(strstr(last().detail, "1 call(s) of run A") != NULL);
    CHECK_EQ(last().note_count, 5); /* 1F0C(3), 1F00(7), 0148, 1F0C(3), 1F00(7) */
    /* three levels of noted calls */
    c = fresh();
    ov_mid_then(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 6);
    CHECK_EQ(last().address, 0x00100158u);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK(strstr(last().detail, "1 call(s) of run A") != NULL);
    CHECK_EQ(last().note_count, 4); /* 0148, 1F0C(3), 1F00(7), 1F00(5) */
    /* a register that is not an argument is not compared; with a probe (arguments not known) it is */
    c = fresh();
    ov_r1_wrap(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 8);
    CHECK_EQ(last().address, 0x0010014Cu);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    c = fresh();
    ov_r1_probe(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().address, 0x00100150u);
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_CALLS);
    CHECK(strstr(last().detail, "00101F00(r1=00000055) vs (r1=00000000)") != NULL);
    /* the argument bits FE_ENTRY finds */
    uint32_t bits = 0;
    FE_CAP_ARGS_FIND_(bits, FE_ARG(0));
    CHECK_EQ(bits, FE_CAP_ARGS_KNOWN | 0x1u);
    FE_CAP_ARGS_FIND_(bits, FE_ARG_S(1), FE_ARG(3), FE_ARG(13)); /* r0 skipped, a stack argument */
    CHECK_EQ(bits, FE_CAP_ARGS_KNOWN | 0xAu);
    FE_CAP_ARGS_FIND_(bits, FE_ARG(0), FE_ARG(1) + 4u); /* not a plain FE_ARG: all four */
    CHECK_EQ(bits, FE_CAP_ARGS_KNOWN | 0xFu);
    /* a 64-bit argument made of r2 and r3 (as in ai_tile_queries.c): not plain, all four */
    FE_CAP_ARGS_FIND_(bits, FE_ARG(0), ((uint64_t)FE_ARG(3) << 32) | FE_ARG(2));
    CHECK_EQ(bits, FE_CAP_ARGS_KNOWN | 0xFu);
    FE_CAP_ARGS_FIND_(bits, FE_ARG(0), (int64_t)FE_ARG_S(2)); /* widened, still plain r2 */
    CHECK_EQ(bits, FE_CAP_ARGS_KNOWN | 0x5u);
    FE_CAP_ARGS_NONE_(bits);
    CHECK_EQ(bits, FE_CAP_ARGS_KNOWN);
    /* one call more than run A */
    c = fresh();
    ov_call_twice(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_CALLS);
    CHECK(strstr(last().detail, "probe calls: 1 vs 2") != NULL);

    /* a store by B to a page the record does not have: compared from B's side */
    uint8_t before = ram[1][0x800];
    c = fresh();
    ov_sum_stray(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 42);
    CHECK_EQ(ram[1][0x800], before); /* never reaches the game */
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_MEM);
    CHECK(strstr(last().detail, "byte 00101800") != NULL);

    /* new settings without a reset in between are read again */
    FeCapConfig cfg;
    memset(&cfg, 0, sizeof cfg);
    cfg.live = FE_CAP_LIVE_A;
    fe_capture_configure(&cfg);
    c = fresh();
    ov_sum_clean(&c);
    CHECK_EQ(last().verdict, FE_CAP_V_FAITHFUL);
}

/* late pages for run B (FeCapConfig.late, FE_CAPTURE_LATE) and callbacks.tsv */
static void test_late_pages(void) {
    char dir[1000];
    dir_of(dir, sizeof dir, "late");
    FeCapConfig cfg;
    memset(&cfg, 0, sizeof cfg);
    cfg.dir = dir;
    cfg.live = FE_CAP_LIVE_AB;
    cfg.keep = 4;
    cfg.guard = 0x00100F00u;
    cfg.late = 1;
    fe_capture_configure(&cfg);
    set32(RAM + 0x10, 40);
    set32(RAM + 0x14, 2);
    set32(RAM + 0x1800, 0);
    set32(RAM + 0x1804, 7);
    /* the read outside the record is taken from the game: a real comparison */
    Context c = fresh();
    ov_sum_outside(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 42);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK_EQ(last().page_count, 3); /* RAM and the stack page the original touches, plus the late page */
    CHECK_EQ(stats().late_pages, 1);
    /* a store by B to a page the record lacks is still compared: B's byte vs the game's */
    uint8_t before = ram[1][0x800];
    c = fresh();
    ov_sum_stray(&c);
    CHECK_EQ(ram[1][0x800], before); /* never reaches the game */
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_MEM);
    CHECK(strstr(last().detail, "byte 00101800: run A 00, run B 01") != NULL);
    /* B uses the late word: a real mismatch, kept with the late page in the record */
    c = fresh();
    ov_sum_late_bad(&c);
    CHECK(restored(&c));
    CHECK_EQ(c.r[0], 42);
    CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_R0);
    CHECK(strstr(last().detail, "run B 00000031") != NULL);
    CHECK(last().stored);
    /* a device page has no bytes to take: still an escape */
    int dev_before = dev_reads;
    c = fresh();
    ov_sum_dev(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_B_ESCAPED);
    CHECK(strstr(last().detail, "bits 4") != NULL);
    CHECK_EQ(dev_reads, dev_before); /* run B never reached the device */
    c = fresh();
    ov_sum_rom_late(&c);
    CHECK(restored(&c));
    CHECK_EQ(last().verdict, FE_CAP_V_B_ESCAPED);
    CHECK(strstr(last().detail, "bits 10") != NULL);
    fe_capture_flush();
    Parsed recs[8];
    int n = parse_records(dir, recs, 8);
    CHECK(n >= 2);
    const Parsed *bad = NULL;
    for (int i = 0; i < n; i++)
        if (recs[i].h.address == 0x00100120u)
            bad = &recs[i];
    CHECK(bad != NULL);
    if (bad) {
        const FeCapPage *lp = page_of(bad, RAM + 0x1000);
        CHECK(lp != NULL);
        if (lp) {
            CHECK_EQ(lp->flags, FE_CAP_PAGE_COPIED | FE_CAP_PAGE_LATE);
            int any = 0;
            for (int i = 0; i < 512; i++)
                any |= lp->read_bits[i] | lp->write_bits[i];
            CHECK_EQ(any, 0); /* the original never touched it */
            uint8_t bytes[4096];
            CHECK(read_page_file(dir, lp, bytes));
            CHECK_EQ(bytes[0x804], 7); /* the game's bytes, as they were at entry */
        }
        const FeCapPage *rp = page_of(bad, RAM);
        CHECK(rp != NULL && !(rp->flags & FE_CAP_PAGE_LATE));
    }
    /* callbacks.tsv lists what the capture forwarded: the device read of the original is none here,
       but the totals line and header are written */
    char path[1200], line[512];
    snprintf(path, sizeof path, "%s/callbacks.tsv", dir);
    FILE *f = fopen(path, "r");
    CHECK(f != NULL);
    if (f) {
        CHECK(fgets(line, sizeof line, f) != NULL && strstr(line, "late pages 4") != NULL);
        CHECK(fgets(line, sizeof line, f) != NULL && strncmp(line, "kind\tkey\tcount\t", 15) == 0);
        fclose(f);
    }
    /* late pages off (the default for tools): the same read escapes */
    cfg.late = 0;
    fe_capture_configure(&cfg);
    c = fresh();
    ov_sum_outside(&c);
    CHECK_EQ(last().verdict, FE_CAP_V_B_ESCAPED);
    CHECK_EQ(stats().late_pages, 4);
}

/* every forwarded host callback is counted by kind and target (callbacks.tsv) */
static void test_callback_log(void) {
    char dir[1000];
    dir_of(dir, sizeof dir, "callbacks");
    config("callbacks", NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    FeCapStats s0 = stats();
    Context c = fresh();
    probe_0x00100700(&c); /* reads device memory: a host_read */
    c = fresh();
    probe_0x00100938(&c); /* one lookup, forwarded while recording, and again by run A */
    c = fresh();
    svc_mode = SVC_IN_PLACE;
    probe_0x00100500(&c); /* an svc forwarded while recording */
    FeCapStats s1 = stats();
    CHECK_EQ(s1.callbacks[FE_CAP_CB_HOST_READ] - s0.callbacks[FE_CAP_CB_HOST_READ] >= 1, 1);
    CHECK_EQ(s1.callbacks[FE_CAP_CB_LOOKUP] + s1.callbacks[FE_CAP_CB_LOOKUP_MISS] -
                 s0.callbacks[FE_CAP_CB_LOOKUP] - s0.callbacks[FE_CAP_CB_LOOKUP_MISS], 1);
    CHECK(s1.callbacks[FE_CAP_CB_REPLAY_LOOKUP] - s0.callbacks[FE_CAP_CB_REPLAY_LOOKUP] >= 1);
    CHECK_EQ(s1.callbacks[FE_CAP_CB_SVC] - s0.callbacks[FE_CAP_CB_SVC], 1);
    fe_capture_flush();
    char path[1200], line[512];
    snprintf(path, sizeof path, "%s/callbacks.tsv", dir);
    FILE *f = fopen(path, "r");
    CHECK(f != NULL);
    int saw_dev = 0, saw_svc = 0, saw_lookup = 0;
    while (f && fgets(line, sizeof line, f)) {
        unsigned key = 0, count = 0, first = 0;
        char kind[32];
        if (sscanf(line, "%31s 0x%x %u 0x%x", kind, &key, &count, &first) != 4)
            continue;
        saw_dev |= strcmp(kind, "host_read") == 0 && key == DEV;
        saw_svc |= strcmp(kind, "svc") == 0 && count >= 1;
        saw_lookup |= strncmp(kind, "lookup", 6) == 0 && count == 1;
    }
    if (f)
        fclose(f);
    CHECK(saw_dev);
    CHECK(saw_svc);
    CHECK(saw_lookup);
}

/* a function with cold records needs a warm one before it passes */
static void test_cold_needs_warm(void) {
    config(NULL, NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    static const uint32_t v[10] = {0, 1, 0, 0x100000, 7, 0, 0, 3, 0xFFFFFFFFu, 20};
    for (int i = 0; i < 10; i++) {
        set32(RAM + 0x68, 0);
        set32(RAM + 0x6C, v[i]);
        Context c = fresh();
        ov_cache(&c);
        CHECK_EQ(c.r[0], v[i]);
        CHECK_EQ(get32(RAM + 0x68), 1);
    }
    FeCapFnStats s = fn(0x00100E04u);
    CHECK_EQ(s.verdicts[FE_CAP_V_MATCH], 10);
    CHECK_EQ(s.cold, 10);
    CHECK_EQ(s.warm, 0);
    CHECK(s.signature_count >= 2);
    CHECK(s.deep >= 1);
    CHECK_EQ(strcmp(s.verdict, "PARTIAL"), 0);
    Context c = fresh();
    ov_cache(&c); /* warm now */
    s = fn(0x00100E04u);
    CHECK_EQ(s.warm, 1);
    CHECK_EQ(strcmp(s.verdict, "REPLAY-CLEAN"), 0);
}

/* the folder rule: only below build/ or play/ at a checkout's root, never through ".." */
static void test_dir_rule(void) {
    char dir[1000], path[1100];
    const char *refused[3] = {"nowhere/build/x", "play/x", NULL};
    snprintf(dir, sizeof dir, "%s/sub/../dotdot", base_dir);
    refused[2] = dir;
    for (int i = 0; i < 3; i++) {
        fe_capture_reset();
        FeCapConfig cfg;
        memset(&cfg, 0, sizeof cfg);
        cfg.dir = refused[i];
        fe_capture_configure(&cfg);
        Context c = fresh();
        ov_sum_bad(&c);
        CHECK_EQ(last().verdict, FE_CAP_V_MISMATCH_R0);
        CHECK_EQ(stats().records_written, 0);
        fe_capture_finish();
        snprintf(path, sizeof path, "%s/records.fecap", refused[i]);
        CHECK_EQ(file_size(path), -1);
        snprintf(path, sizeof path, "%s/summary.tsv", refused[i]);
        CHECK_EQ(file_size(path), -1);
    }
    snprintf(path, sizeof path, "%s/dotdot/records.fecap", base_dir);
    CHECK_EQ(file_size(path), -1);
}

/* a passing store session removes only what it wrote */
static void test_store_keeps_earlier(void) {
    char dir[1000], path[1100];
    dir_of(dir, sizeof dir, "shared");
    set32(RAM + 0x10, 40);
    set32(RAM + 0x14, 2);
    config("shared", NULL, 0, FE_CAP_LIVE_AB, 0, 0, 0);
    Context c = fresh();
    ov_sum_bad(&c);
    CHECK(last().stored);
    fe_capture_finish();
    snprintf(path, sizeof path, "%s/records.fecap", dir);
    long size1 = file_size(path);
    CHECK(size1 > 0);

    set32(RAM + 0x18, 0x777); /* a new RAM page content: a page file of its own */
    config("shared", "0x00100100", 1, FE_CAP_LIVE_AB, 0, 0, 0);
    c = fresh();
    ov_sum(&c);
    CHECK_EQ(last().verdict, FE_CAP_V_MATCH);
    CHECK(last().stored);
    fe_capture_flush();
    Parsed recs[3];
    int n = parse_records(dir, recs, 3);
    CHECK_EQ(n, 2);
    fe_capture_finish();
    CHECK_EQ(file_size(path), size1); /* cut back, not removed */
    if (n == 2) {
        uint8_t bytes[4096];
        const FeCapPage *old_ram = page_of(&recs[0], RAM), *new_ram = page_of(&recs[1], RAM);
        CHECK(old_ram && new_ram);
        if (old_ram && new_ram) {
            CHECK(read_page_file(dir, old_ram, bytes)); /* the earlier session's page stays */
            CHECK(!read_page_file(dir, new_ram, bytes)); /* this session's page is gone */
        }
        /* a page this session met again (same bytes as the earlier one) stays */
        const FeCapPage *old_stk = page_of(&recs[0], SP0 - 0x1000), *new_stk = page_of(&recs[1], SP0 - 0x1000);
        CHECK(old_stk && new_stk);
        if (old_stk && new_stk) {
            CHECK(memcmp(old_stk->hash, new_stk->hash, sizeof old_stk->hash) == 0);
            CHECK(read_page_file(dir, new_stk, bytes));
        }
        CHECK_EQ(parse_records(dir, recs, 3), 1);
        CHECK_EQ(recs[0].h.address, 0x00100104u);
    }
}

int main(int argc, char **argv) {
    if (argc < 2 || strlen(argv[1]) >= sizeof base_dir) {
        printf("usage: capture_test <scratch folder below build/>\n");
        return 2;
    }
    snprintf(base_dir, sizeof base_dir, "%s", argv[1]);
    rtab = calloc(1u << 20, sizeof *rtab);
    wtab = calloc(1u << 20, sizeof *wtab);
    rtab2 = calloc(1u << 20, sizeof *rtab2);
    wtab2 = calloc(1u << 20, sizeof *wtab2);
    if (!rtab || !wtab || !rtab2 || !wtab2)
        return 2;
    exp_r = rtab;
    exp_w = wtab;
    for (int i = 0; i < 2; i++)
        rtab[(RAM >> 12) + (uint32_t)i] = wtab[(RAM >> 12) + (uint32_t)i] = ram[i];
    rtab[ROM >> 12] = rom;
    for (int i = 0; i < 16; i++)
        rtab[(STK >> 12) + (uint32_t)i] = wtab[(STK >> 12) + (uint32_t)i] = stk[i];
    for (int i = 0; i < 4096; i++)
        rom[i] = (uint8_t)(i * 7);
    memcpy(rtab2, rtab, (sizeof *rtab) << 20);
    memcpy(wtab2, wtab, (sizeof *wtab) << 20);
    rtab2[RAM >> 12] = wtab2[RAM >> 12] = ram2;
    fe_force_mode(FE_MODE_CAPTURE);

    test_sampling();
    test_paths_restore();
    test_truncated();
    test_live_compare();
    test_fe_entry_modes();
    test_probe_outside_capture();
    test_nesting_and_store();
    test_store_rules();
    test_cold_warm();
    test_fidelity_fields();
    test_run_b_more();
    test_cold_needs_warm();
    test_late_pages();
    test_callback_log();
    test_dir_rule();
    test_store_keeps_earlier();
    fe_capture_reset();

    printf("capture test: %d/%d checks passed\n", checks - failures, checks);
    return failures ? 1 : 0;
}
