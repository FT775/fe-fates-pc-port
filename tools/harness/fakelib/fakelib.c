/* fakelib: a tiny stand-in for a 3dsrecomp library, for the harness
   self-test (docs/HARNESS.md 3.5). Every function, address and value here is
   invented: no game code, no game data. It exports what replay.exe needs
   from a real library (tools/harness/replay_abi.h): recomp_abi = 5 and a
   sorted recomp_entries table. The "originals" are written the way generated
   code behaves: they take a Context, touch guest memory only through the
   mem_read / mem_write helpers (with null page tables every access reaches
   the host), call other code through the host's lookup with r15 set, and
   return by setting r15 to lr.

   Built by tools/harness/harness.py with host gcc as build/harness/selftest/
   fakelib.dll; its readable counterparts, including planted bugs, are in
   fake_readable.c. */

#include "overrides.h"
#include "replay_abi.h"

#if defined(_WIN32)
#define FL_EXPORT __declspec(dllexport)
#else
#define FL_EXPORT __attribute__((visibility("default")))
#endif

#define FL_GUARD 0x00180000u /* a one-time cache: guard word (bit 0 = filled) ... */
#define FL_CACHE 0x00180004u /* ... and the cached value */
#define FL_TABLE 0x00181000u

static void fl_return(Context *ctx, uint32_t r0) {
    ctx->r[0] = r0;
    ctx->thumb = 0;
    ctx->r[15] = ctx->r[14] & ~3u;
}

/* a call through the host, as generated code makes an indirect call */
static uint32_t fl_call(Context *ctx, uint32_t f, uint32_t a0, uint32_t ret) {
    Code code = ctx->host->lookup(ctx, f);
    if (code == 0) {
        ctx->exit = EXIT_UNWIND;
        return 0;
    }
    ctx->r[0] = a0;
    ctx->r[14] = ret;
    ctx->r[15] = f;
    ctx->thumb = 0;
    if (++ctx->depth > RECOMP_DEPTH_LIMIT) {
        ctx->depth--;
        ctx->exit = EXIT_UNWIND;
        return 0;
    }
    code(ctx);
    ctx->depth--;
    return ctx->r[0];
}

/* 0x00200000 heal(unit, amount): hp += amount up to max hp (u16 at +0x10,
   +0x12); a scratch word below sp; junk left in r1-r3 */
static void fl_heal(Context *ctx) {
    uint32_t unit = ctx->r[0], amount = ctx->r[1], lr = ctx->r[14];
    uint32_t hp = mem_read16(ctx, unit + 0x10), max = mem_read16(ctx, unit + 0x12);
    mem_write32(ctx, ctx->r[13] - 8, hp);
    uint32_t v = (hp + amount) & 0xFFFFu;
    if (v > max)
        v = max;
    mem_write16(ctx, unit + 0x10, (uint16_t)v);
    ctx->r[1] = 0xDEAD0001u;
    ctx->r[2] = hp;
    ctx->r[3] = max;
    ctx->r[14] = lr;
    fl_return(ctx, v);
}

/* 0x00200100 cached(x): fills the one-time cache through the guard routine
   on first use, then returns cache + x */
static void fl_cached(Context *ctx) {
    uint32_t x = ctx->r[0], lr = ctx->r[14];
    uint32_t guard = mem_read32(ctx, FL_GUARD);
    if (!(guard & 1u)) {
        (void)fl_call(ctx, 0x00200A00u, FL_GUARD, 0x00200120u);
        if (ctx->exit)
            return;
        mem_write32(ctx, FL_CACHE, mem_read32(ctx, FL_TABLE) * 3u + 1u);
        mem_write32(ctx, FL_GUARD, guard | 1u);
    }
    ctx->r[14] = lr;
    fl_return(ctx, mem_read32(ctx, FL_CACHE) + x);
}

/* 0x00200300 sum3(p): three signed halfwords added */
static void fl_sum3(Context *ctx) {
    uint32_t p = ctx->r[0];
    int32_t a = (int16_t)mem_read16(ctx, p), b = (int16_t)mem_read16(ctx, p + 2), c = (int16_t)mem_read16(ctx, p + 4);
    fl_return(ctx, (uint32_t)(a + b + c));
}

/* 0x00200400 asks the system something: an svc inside */
static void fl_svc(Context *ctx) {
    (void)mem_read32(ctx, ctx->r[0]);
    ctx->host->svc(ctx, 0x28);
    if (ctx->exit)
        return;
    fl_return(ctx, 1);
}

/* 0x00200500 caller(p): p->c = double(p->b) through the lookup */
static void fl_caller(Context *ctx) {
    uint32_t p = ctx->r[0], lr = ctx->r[14];
    uint32_t v = fl_call(ctx, 0x00200600u, mem_read32(ctx, p + 8), 0x00200520u);
    if (ctx->exit)
        return;
    mem_write32(ctx, p + 0xC, v);
    ctx->r[14] = lr;
    fl_return(ctx, v);
}

/* 0x00200600 double(x) (a probe) */
static void fl_double(Context *ctx) { fl_return(ctx, ctx->r[0] * 2u); }

/* 0x00200700 caller2(p): calls double(p->b) for nothing, returns 0 */
static void fl_caller2(Context *ctx) {
    uint32_t p = ctx->r[0], lr = ctx->r[14];
    (void)fl_call(ctx, 0x00200600u, mem_read32(ctx, p + 8), 0x00200720u);
    if (ctx->exit)
        return;
    ctx->r[14] = lr;
    fl_return(ctx, 0);
}

/* 0x00200800 peek(p) = *p */
static void fl_peek(Context *ctx) { fl_return(ctx, mem_read32(ctx, ctx->r[0])); }

/* 0x00200900 store2(p, v): p[1] = v, p[2] = v + 1 */
static void fl_store2(Context *ctx) {
    uint32_t p = ctx->r[0], v = ctx->r[1];
    mem_write32(ctx, p + 4, v);
    mem_write32(ctx, p + 8, v + 1u);
    fl_return(ctx, 0);
}

/* 0x00200B00 version(): a word of read-only data (no writable pointer) */
static void fl_version(Context *ctx) { fl_return(ctx, mem_read32(ctx, 0x00100010u)); }

/* 0x00200C00 mark(p): p->flag = 1 (a byte) */
static void fl_mark(Context *ctx) {
    mem_write8(ctx, ctx->r[0] + 1, 1);
    fl_return(ctx, 0);
}

/* 0x00200D00, 0x00200E00, 0x00200F00, 0x00201500 plus1(x) = x + 1: four copies, each paired
   with a readable side that leaves a different register behind (fake_readable.c) */
static void fl_plus1(Context *ctx) { fl_return(ctx, ctx->r[0] + 1u); }

/* 0x00201000 twice(p) and 0x00201200 extra(p): p->c = double(p->b) through the lookup,
   like caller; their readable sides make one call too many (rule 4) */
static void fl_twice(Context *ctx) {
    uint32_t p = ctx->r[0], lr = ctx->r[14];
    ctx->r[1] = ctx->r[2] = ctx->r[3] = 0; /* a one-argument call with clean r1-r3, as guest_call makes it
                                               (so only the planted extra call differs; HARNESS risk 13) */
    uint32_t v = fl_call(ctx, 0x00200600u, mem_read32(ctx, p + 8), 0x00201020u);
    if (ctx->exit)
        return;
    mem_write32(ctx, p + 0xC, v);
    ctx->r[14] = lr;
    fl_return(ctx, v);
}

/* 0x00201100 triple(x) (a probe) */
static void fl_triple(Context *ctx) { fl_return(ctx, ctx->r[0] * 3u); }

/* 0x00201300 outp(x): *(sp + 0) = x * 3, an out-parameter in the caller's frame (rule 1:
   compared, not dead stack) */
static void fl_outp(Context *ctx) {
    mem_write32(ctx, ctx->r[13], ctx->r[0] * 3u);
    fl_return(ctx, 0);
}

/* 0x00201400 touch(p) = *p (its readable side stores the same value back: rule 2) */
static void fl_touch(Context *ctx) { fl_return(ctx, mem_read32(ctx, ctx->r[0])); }

/* H6 mutation targets (docs/HARNESS.md 5 "Mutation"): four more invented functions whose
   readable sides in fake_readable.c are right, written the way real readable code is
   (struct fields, named constants, a loop, a helper with two arguments, a give-up). */

/* 0x00201600 clampst(unit, stat): s = stat & 7; v = unit->stats[s] (u8 at +0x20), at most
   unit->caps[s] (u8 at +0x28); HP (s == 0) is at least 1 */
static void fl_clampst(Context *ctx) {
    uint32_t unit = ctx->r[0], s = ctx->r[1] & 7u;
    uint32_t v = mem_read8(ctx, unit + 0x20 + s), cap = mem_read8(ctx, unit + 0x28 + s);
    if (v >= cap)
        v = cap;
    if (s == 0 && v < 1)
        v = 1;
    fl_return(ctx, v);
}

/* 0x00201700 count(p, n): how many of the first min(n, 6) signed halfwords at p are above 0 */
static void fl_count(Context *ctx) {
    uint32_t p = ctx->r[0], n = ctx->r[1], c = 0;
    uint32_t k = n < 6 ? n : 6;
    for (uint32_t i = 0; i < k; i++)
        if ((int16_t)mem_read16(ctx, p + 2 * i) > 0)
            c++;
    fl_return(ctx, c);
}

/* 0x00201800 diff(p): d = p->a - p->b (u32 at +0, +4); p->d = d (+8); bit 0x02 of the byte at
   +0xC set when d is negative, cleared otherwise; returns d */
static void fl_diff(Context *ctx) {
    uint32_t p = ctx->r[0];
    uint32_t d = mem_read32(ctx, p) - mem_read32(ctx, p + 4);
    mem_write32(ctx, p + 8, d);
    uint8_t f = mem_read8(ctx, p + 0xC);
    mem_write8(ctx, p + 0xC, (uint8_t)((int32_t)d < 0 ? (f | 0x02u) : (f & ~0x02u)));
    fl_return(ctx, d);
}

/* 0x00201900 gated(p): a second one-time cache (guard 0x00180010, value 0x00180014) filled through
   the guard routine; returns the u16 at p + 2 * (cache & 3) */
static void fl_gated(Context *ctx) {
    uint32_t p = ctx->r[0], lr = ctx->r[14];
    uint32_t guard = mem_read32(ctx, 0x00180010u);
    if (!(guard & 1u)) {
        (void)fl_call(ctx, 0x00200A00u, 0x00180010u, 0x00201920u);
        if (ctx->exit)
            return;
        mem_write32(ctx, 0x00180014u, mem_read32(ctx, FL_TABLE + 4) ^ 5u);
        mem_write32(ctx, 0x00180010u, guard | 1u);
    }
    ctx->r[14] = lr;
    fl_return(ctx, mem_read16(ctx, p + 2 * (mem_read32(ctx, 0x00180014u) & 3u)));
}

/* 0x00200A00 the guard routine (a probe): says "fill it" */
static void fl_guard(Context *ctx) { fl_return(ctx, 1); }

#ifndef FL_ABI
#define FL_ABI 5 /* the self-test also builds a copy with another value: replay.exe must refuse it */
#endif
FL_EXPORT const uint32_t recomp_abi = FL_ABI;
FL_EXPORT const FeRpEntry recomp_entries[] = {
    {0x00200000u, fl_heal},  {0x00200100u, fl_cached}, {0x00200300u, fl_sum3},  {0x00200400u, fl_svc},
    {0x00200500u, fl_caller}, {0x00200600u, fl_double}, {0x00200700u, fl_caller2}, {0x00200800u, fl_peek},
    {0x00200900u, fl_store2}, {0x00200A00u, fl_guard},  {0x00200B00u, fl_version},
    {0x00200C00u, fl_mark},   {0x00200D00u, fl_plus1},  {0x00200E00u, fl_plus1},  {0x00200F00u, fl_plus1},
    {0x00201000u, fl_twice},  {0x00201100u, fl_triple}, {0x00201200u, fl_twice},  {0x00201300u, fl_outp},
    {0x00201400u, fl_touch},  {0x00201500u, fl_plus1},  {0x00201600u, fl_clampst}, {0x00201700u, fl_count},
    {0x00201800u, fl_diff},   {0x00201900u, fl_gated},
};
FL_EXPORT const uint32_t recomp_entry_count = sizeof recomp_entries / sizeof recomp_entries[0];
