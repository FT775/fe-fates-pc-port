/* Host-side test of guest_call6 (include/readable/fe_guest.h) on its own,
   run by tools/readable/tests/guest_call6_test.py (which also plants bugs in
   a copy of the header and checks each one fails here). It is
   guest_call5_test.c with a sixth word (round 15, capability batch).

   Why a test of its own (round 11 review): the item_diff / ai_score_diff
   drivers call readable functions through FE_ENTRY, and FE_ENTRY puts every
   register back (fe_load) when the readable function returns or gives up. So
   a guest_call5 that forgot to put sp back is invisible there, and with the
   fifth word always 0 on a zeroed stack, a word stored in the wrong slot was
   invisible too. Here guest_call5 is called directly, on a dead stack filled
   with non-zero junk, and checked word by word:
   - the callee sees r0..r3 = a0..a3, the fifth word at [sp] and the sixth
     at [sp + 4] (AAPCS);
   - sp seen by the callee is 8-byte aligned and at least 8 bytes below;
   - sp is put back after the call, also when the callee gives up and when
     the callee has no host code;
   - the only guest bytes written are the eight of the two words, below sp;
   - with a give-up already pending nothing is stored and nothing called.
   Test values only. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fe_guest.h"

#define STACK_TOP 0x10000000u
#define STACK_SIZE 0x1000u
#define CALLEE 0x00100000u     /* returns normally */
#define CALLEE_STOP 0x00100100u /* gives up inside (sets exit) */
#define NO_CODE 0x00100200u     /* no host code: guest_call gives up */

static uint8_t stack_mem[STACK_SIZE], before[STACK_SIZE];
static unsigned faults, writes_outside;
static uint8_t *at(uint32_t a) { return a - (STACK_TOP - STACK_SIZE) < STACK_SIZE ? stack_mem + (a - (STACK_TOP - STACK_SIZE)) : NULL; }
static uint8_t r8(Context *c, uint32_t a) { (void)c; uint8_t *p = at(a); if (!p) { faults++; return 0; } return *p; }
static uint16_t r16(Context *c, uint32_t a) { return (uint16_t)(r8(c, a) | r8(c, a + 1) << 8); }
static uint32_t r32(Context *c, uint32_t a) { return (uint32_t)r16(c, a) | (uint32_t)r16(c, a + 2) << 16; }
static void w8(Context *c, uint32_t a, uint8_t v) { (void)c; uint8_t *p = at(a); if (p) *p = v; else writes_outside++; }
static void w16(Context *c, uint32_t a, uint16_t v) { w8(c, a, (uint8_t)v); w8(c, a + 1, (uint8_t)(v >> 8)); }
static void w32(Context *c, uint32_t a, uint32_t v) { w16(c, a, (uint16_t)v); w16(c, a + 2, (uint16_t)(v >> 16)); }
static void interp(Context *c, uint32_t a, uint32_t o) { (void)c; (void)a; (void)o; }
static void svc(Context *c, uint32_t n) { (void)c; (void)n; }

/* what the callee saw */
static int called;
static uint32_t seen_r[4], seen_sp, seen_word, seen_word6;
static void callee(Context *ctx) {
    called++;
    memcpy(seen_r, ctx->r, sizeof seen_r);
    seen_sp = ctx->r[13];
    seen_word = r32(ctx, ctx->r[13]);
    seen_word6 = r32(ctx, ctx->r[13] + 4u);
    ctx->r[0] = 0x0BADF00Du ^ seen_word ^ (seen_word6 * 3u) ^ seen_r[0];
    ctx->r[15] = ctx->r[14];
}
static void callee_stop(Context *ctx) {
    called++;
    seen_sp = ctx->r[13];
    seen_word = r32(ctx, ctx->r[13]);
    seen_word6 = r32(ctx, ctx->r[13] + 4u);
    ctx->exit = EXIT_UNWIND;
}
static Code lookup(Context *c, uint32_t a) {
    (void)c;
    return a == CALLEE ? callee : a == CALLEE_STOP ? callee_stop : NULL;
}

/* fe_use_original's partner in a real build; never reached here */
void fe_stub_original(Context *ctx) { (void)ctx; }

static const Host host = {r8, r16, r32, w8, w16, w32, interp, lookup, svc};
static uint32_t vfp[32], fpscr;
static Context fresh(uint32_t sp) {
    Context c;
    memset(&c, 0, sizeof c);
    c.vfp = vfp;
    c.fpscr = &fpscr;
    c.host = &host;
    c.r[13] = sp;
    c.r[14] = 0x00123450u;
    c.budget = 1000;
    return c;
}

static int fails, checks;
static void check(int ok, const char *what, uint32_t sp, uint32_t a4) {
    checks++;
    if (!ok) {
        fails++;
        printf("FAIL %s (sp %08X, words %08X)\n", what, sp, a4);
    }
}

static void junk(void) {
    for (uint32_t i = 0; i < STACK_SIZE; i++)
        stack_mem[i] = (uint8_t)(0xA5u ^ (i * 37u) ^ (i >> 3)); /* never four zero bytes in a row */
    memcpy(before, stack_mem, sizeof before);
    faults = writes_outside = 0;
    called = 0;
    seen_sp = seen_word = seen_word6 = 0;
}

/* bytes of the stack that changed, other than the eight at [lo, lo + 8) */
static int changed_except(uint32_t lo) {
    int n = 0;
    for (uint32_t i = 0; i < STACK_SIZE; i++) {
        uint32_t a = STACK_TOP - STACK_SIZE + i;
        if (stack_mem[i] != before[i] && !(a >= lo && a < lo + 8u))
            n++;
    }
    return n;
}

int main(void) {
    const uint32_t sps[] = {STACK_TOP - 0x200u, STACK_TOP - 0x204u, STACK_TOP - 0x208u, STACK_TOP - 0x20Cu};
    const uint32_t words[] = {0u, 1u, 0x12345678u, 0xFFFFFFFFu};
    for (unsigned i = 0; i < sizeof sps / sizeof sps[0]; i++) {
        for (unsigned j = 0; j < sizeof words / sizeof words[0]; j++) {
            uint32_t sp = sps[i], a4 = words[j], a5 = words[(j + 1u) % (sizeof words / sizeof words[0])] ^ 0x5A5A0000u;
            junk();
            Context c = fresh(sp);
            uint32_t r = guest_call6(&c, CALLEE, 0x11u, 0x22u, 0x33u, 0x44u, a4, a5);
            check(called == 1, "callee called once", sp, a4);
            check(seen_r[0] == 0x11u && seen_r[1] == 0x22u && seen_r[2] == 0x33u && seen_r[3] == 0x44u,
                  "callee sees r0..r3 = a0..a3", sp, a4);
            check(seen_word == a4, "callee sees the fifth word at [sp]", sp, a4);
            check(seen_word6 == a5, "callee sees the sixth word at [sp + 4]", sp, a4);
            check(seen_sp + 4u < sp, "the sixth word is below the caller's sp", sp, a4);
            check((seen_sp & 7u) == 0, "callee's sp is 8-byte aligned", sp, a4);
            check(seen_sp <= sp - 8u && seen_sp > sp - 16u, "callee's sp is 8..15 bytes below the caller's", sp, a4);
            check(c.r[13] == sp, "sp put back after the call", sp, a4);
            check(r == (0x0BADF00Du ^ a4 ^ (a5 * 3u) ^ 0x11u) && c.exit == EXIT_NONE, "callee's r0 returned, no give-up", sp, a4);
            check(changed_except(seen_sp) == 0 && writes_outside == 0 && faults == 0,
                  "only the two words' eight bytes written, below sp", sp, a4);

            junk();
            c = fresh(sp);
            r = guest_call6(&c, CALLEE_STOP, 1u, 2u, 3u, 4u, a4, a5);
            check(called == 1 && seen_word == a4 && seen_word6 == a5 && r == 0 && c.exit != EXIT_NONE,
                  "callee giving up: 0 returned, give-up kept", sp, a4);
            check(c.r[13] == sp, "sp put back after a callee gave up", sp, a4);

            junk();
            c = fresh(sp);
            r = guest_call6(&c, NO_CODE, 1u, 2u, 3u, 4u, a4, a5);
            check(called == 0 && r == 0 && c.exit != EXIT_NONE && c.r[13] == sp,
                  "no host code: give-up, sp put back", sp, a4);

            junk();
            c = fresh(sp);
            c.exit = EXIT_UNWIND;
            r = guest_call6(&c, CALLEE, 1u, 2u, 3u, 4u, a4, a5);
            check(called == 0 && r == 0 && c.r[13] == sp && memcmp(stack_mem, before, sizeof before) == 0,
                  "give-up pending: nothing stored, nothing called, sp unchanged", sp, a4);
        }
    }
    printf("guest_call6 test: %d/%d ok\n", checks - fails, checks);
    return fails ? 1 : 0;
}
