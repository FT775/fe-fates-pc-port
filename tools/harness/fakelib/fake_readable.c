/* Readable counterparts of fakelib.c's invented functions, compiled into the
   self-test's replay.exe instead of src/readable (docs/HARNESS.md 3.5). They
   go through the real FE_ENTRY of include/readable/fe_guest.h. Some are
   right, some carry planted bugs the harness must catch:

     0x00200000 heal      right (writes memory)                  -> match
     0x00200100 cached    right, gives up while the cache is cold -> gave_up / match
     0x00200300 sum3      PLANTED: negates a negative third value -> mismatch_r0
     0x00200400 svc       never replayed: the original escapes    -> escaped
     0x00200500 caller    right, does double() inline            -> match, 1 call done inline
     0x00200700 caller2   PLANTED: calls double() with b + 1     -> mismatch_calls
     0x00200800 peek      PLANTED: reads a page the record lacks -> b_escaped
     0x00200900 store2    PLANTED: stores v instead of v + 1     -> mismatch_mem
     0x00200B00 version   PLANTED: writes read-only data         -> b_escaped (DEVICE)
     0x00200C00 mark      PLANTED: one store too many            -> mismatch_mem (a byte only B wrote)
     0x00200D00 plus1     PLANTED: r7 left changed               -> mismatch_regs offline (rule 3)
     0x00200E00 plus1     PLANTED: s20 left changed              -> mismatch_regs offline
     0x00200F00 plus1     PLANTED: FPSCR rounding mode changed   -> mismatch_regs offline
     0x00201000 twice     PLANTED: calls double() a second time  -> mismatch_calls (a repeated callee)
     0x00201200 extra     PLANTED: calls triple() after double() -> mismatch_calls (an extra call at the end)
     0x00201300 outp      PLANTED: out-parameter at sp + 0 wrong -> mismatch_mem (caller's frame, rule 1)
     0x00201400 touch     right, stores *p back unchanged        -> match, same-value writes counted (rule 2)
     0x00201500 plus1     right, changes only AAPCS scratch      -> match (r2, r3, r12, s0-s15, FPSCR flags)
     0x00201600 clampst   right (struct fields, two clamps)      -> match   } H6 mutation targets
     0x00201700 count     right (a loop, a signed test)          -> match   } (tools/harness/mutate.py
     0x00201800 diff      right (a two-argument helper, 2 stores) -> match  }  plants bugs in the
     0x00201900 gated     right, gives up while its cache is cold -> gave_up / match } right rows)

   The four plus1 rows need a register FE_ENTRY never leaves changed, so in
   readable mode (replay.exe's run B) they take a hand-written broken return
   path instead of FE_ENTRY; in capture mode they go through FE_ENTRY, whose
   live run B compares r0 only. Live they match, offline they must not.

   Not under src/readable: tools/readable/check.py's lint and stage.py never
   see this file, and nothing here ships. */

#include "fe_guest.h"
#include "replay_abi.h"

static uint32_t fake_heal(Context *ctx, gaddr unit, uint32_t amount) {
    uint32_t hp = guest_u16(ctx, unit + 0x10), max = guest_u16(ctx, unit + 0x12);
    uint32_t v = (hp + amount) & 0xFFFFu;
    if (v > max)
        v = max;
    guest_set_u16(ctx, unit + 0x10, (uint16_t)v);
    return v;
}
RECOMP_OVERRIDE(0x00200000) { FE_ENTRY(0x00200000, fake_heal, FE_ARG(0), FE_ARG(1)); }

static uint32_t fake_cached(Context *ctx, uint32_t x) {
    if (!fe_static_ready(ctx, 0x00180000u))
        return fe_use_original(ctx);
    return guest_u32(ctx, 0x00180004u) + x;
}
RECOMP_OVERRIDE(0x00200100) { FE_ENTRY(0x00200100, fake_cached, FE_ARG(0)); }

static int32_t fake_sum3(Context *ctx, gaddr p) {
    int32_t a = guest_s16(ctx, p), b = guest_s16(ctx, p + 2), c = guest_s16(ctx, p + 4);
    if (c < 0)
        c = -c; /* planted bug */
    return a + b + c;
}
RECOMP_OVERRIDE(0x00200300) { FE_ENTRY(0x00200300, fake_sum3, FE_ARG(0)); }

static uint32_t fake_svc(Context *ctx, gaddr p) {
    (void)guest_u32(ctx, p);
    return 1;
}
RECOMP_OVERRIDE(0x00200400) { FE_ENTRY(0x00200400, fake_svc, FE_ARG(0)); }

static uint32_t fake_caller(Context *ctx, gaddr p) {
    uint32_t v = guest_u32(ctx, p + 8) * 2u; /* double() done inline */
    guest_set_u32(ctx, p + 0xC, v);
    return v;
}
RECOMP_OVERRIDE(0x00200500) { FE_ENTRY(0x00200500, fake_caller, FE_ARG(0)); }

static uint32_t fake_caller2(Context *ctx, gaddr p) {
    (void)guest_call1(ctx, 0x00200600u, guest_u32(ctx, p + 8) + 1u); /* planted bug */
    return 0;
}
RECOMP_OVERRIDE(0x00200700) { FE_ENTRY(0x00200700, fake_caller2, FE_ARG(0)); }

static uint32_t fake_peek(Context *ctx, gaddr p) {
    (void)guest_u32(ctx, p + 0x100000u); /* planted: a page the original never touched */
    return guest_u32(ctx, p);
}
RECOMP_OVERRIDE(0x00200800) { FE_ENTRY(0x00200800, fake_peek, FE_ARG(0)); }

static uint32_t fake_store2(Context *ctx, gaddr p, uint32_t v) {
    guest_set_u32(ctx, p + 4, v);
    guest_set_u32(ctx, p + 8, v); /* planted bug: the original stores v + 1 */
    return 0;
}
RECOMP_OVERRIDE(0x00200900) { FE_ENTRY(0x00200900, fake_store2, FE_ARG(0), FE_ARG(1)); }

static uint32_t fake_version(Context *ctx) {
    uint32_t v = guest_u32(ctx, 0x00100010u);
    guest_set_u32(ctx, 0x00100010u, v); /* planted: the game cannot write this page */
    return v;
}
RECOMP_OVERRIDE(0x00200B00) { FE_ENTRY0(0x00200B00, fake_version); }

static uint32_t fake_mark(Context *ctx, gaddr p) {
    guest_set_u8(ctx, p + 1, 1);
    guest_set_u8(ctx, p + 2, (uint8_t)(guest_u8(ctx, p + 2) ^ 0x80u)); /* planted: the original never stores here */
    return 0;
}
RECOMP_OVERRIDE(0x00200C00) { FE_ENTRY(0x00200C00, fake_mark, FE_ARG(0)); }

static uint32_t fake_plus1(Context *ctx, uint32_t x) {
    (void)ctx;
    return x + 1u;
}

/* a broken entry path for the register cases: right r0, then return */
static void fake_raw_return(Context *ctx, uint32_t r0) {
    ctx->r[0] = r0;
    RETURN_TO(ctx->r[14]);
}

RECOMP_OVERRIDE(0x00200D00) {
    if (fe_mode() == FE_MODE_READABLE) {
        uint32_t r0 = ctx->r[0] + 1u;
        ctx->r[7] ^= 0x10u; /* planted: a callee-saved register */
        fake_raw_return(ctx, r0);
        return;
    }
    FE_ENTRY(0x00200D00, fake_plus1, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00200E00) {
    if (fe_mode() == FE_MODE_READABLE) {
        uint32_t r0 = ctx->r[0] + 1u;
        ctx->vfp[20] ^= 0x1u; /* planted: s20, callee-saved */
        fake_raw_return(ctx, r0);
        return;
    }
    FE_ENTRY(0x00200E00, fake_plus1, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00200F00) {
    if (fe_mode() == FE_MODE_READABLE) {
        uint32_t r0 = ctx->r[0] + 1u;
        *ctx->fpscr ^= 0x00C00000u; /* planted: the rounding mode, an FPSCR control field */
        fake_raw_return(ctx, r0);
        return;
    }
    FE_ENTRY(0x00200F00, fake_plus1, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00201500) {
    if (fe_mode() == FE_MODE_READABLE) {
        uint32_t r0 = ctx->r[0] + 1u;
        ctx->r[2] ^= 1u; /* all AAPCS scratch: never a mismatch */
        ctx->r[3] ^= 1u;
        ctx->r[12] ^= 1u;
        for (int i = 0; i < 16; i++)
            ctx->vfp[i] ^= 1u;
        *ctx->fpscr ^= 0xF000009Fu; /* NZCV and the cumulative exception bits */
        fake_raw_return(ctx, r0);
        return;
    }
    FE_ENTRY(0x00201500, fake_plus1, FE_ARG(0));
}

static uint32_t fake_twice(Context *ctx, gaddr p) {
    uint32_t v = guest_call1(ctx, 0x00200600u, guest_u32(ctx, p + 8));
    (void)guest_call1(ctx, 0x00200600u, guest_u32(ctx, p + 8)); /* planted: the same callee again */
    guest_set_u32(ctx, p + 0xC, v);
    return v;
}
RECOMP_OVERRIDE(0x00201000) { FE_ENTRY(0x00201000, fake_twice, FE_ARG(0)); }

static uint32_t fake_extra(Context *ctx, gaddr p) {
    uint32_t v = guest_call1(ctx, 0x00200600u, guest_u32(ctx, p + 8));
    guest_set_u32(ctx, p + 0xC, v);
    (void)guest_call1(ctx, 0x00201100u, v); /* planted: a call the original never makes, last */
    return v;
}
RECOMP_OVERRIDE(0x00201200) { FE_ENTRY(0x00201200, fake_extra, FE_ARG(0)); }

static uint32_t fake_outp(Context *ctx, uint32_t x) {
    guest_set_u32(ctx, ctx->r[13], x * 3u + 1u); /* planted: the out-parameter is off by one */
    return 0;
}
RECOMP_OVERRIDE(0x00201300) { FE_ENTRY(0x00201300, fake_outp, FE_ARG(0)); }

static uint32_t fake_touch(Context *ctx, gaddr p) {
    uint32_t v = guest_u32(ctx, p);
    guest_set_u32(ctx, p, v); /* the same value back: rule 2 info, still a match */
    return v;
}
RECOMP_OVERRIDE(0x00201400) { FE_ENTRY(0x00201400, fake_touch, FE_ARG(0)); }

/* ---- H6 mutation targets: right, written like real readable code */

typedef struct FakeUnit {
    uint8_t pad_00[0x20];
    uint8_t stats[8]; /* +0x20 */
    uint8_t caps[8];  /* +0x28 */
} FakeUnit;

typedef struct FakePair {
    uint32_t a;     /* +0x0 */
    uint32_t b;     /* +0x4 */
    uint32_t d;     /* +0x8 */
    uint8_t flags;  /* +0xC */
} FakePair;

#define FAKE_STAT_MASK 7u
#define FAKE_STAT_HP 0
#define FAKE_MIN_HP 1u
#define FAKE_COUNT_MAX 6u
#define FAKE_PAIR_NEGATIVE 0x02u
#define FAKE_GATED_GUARD 0x00180010u
#define FAKE_GATED_CACHE 0x00180014u

static uint32_t fake_clampst(Context *ctx, gaddr unit, uint32_t stat) {
    uint32_t s = stat & FAKE_STAT_MASK;
    uint32_t v = READ_FIELD(ctx, FakeUnit, unit, stats[s]);
    uint32_t cap = READ_FIELD(ctx, FakeUnit, unit, caps[s]);
    if (v >= cap)
        v = cap;
    if (s == FAKE_STAT_HP && v < FAKE_MIN_HP)
        v = FAKE_MIN_HP;
    return v;
}
RECOMP_OVERRIDE(0x00201600) { FE_ENTRY(0x00201600, fake_clampst, FE_ARG(0), FE_ARG(1)); }

static uint32_t fake_count(Context *ctx, gaddr p, uint32_t n) {
    uint32_t k = n < FAKE_COUNT_MAX ? n : FAKE_COUNT_MAX, c = 0;
    for (uint32_t i = 0; i < k; i++)
        if (guest_s16(ctx, p + 2 * i) > 0)
            c++;
    return c;
}
RECOMP_OVERRIDE(0x00201700) { FE_ENTRY(0x00201700, fake_count, FE_ARG(0), FE_ARG(1)); }

static uint32_t fake_sub(Context *ctx, uint32_t a, uint32_t b) {
    (void)ctx;
    return a - b;
}

static uint32_t fake_diff(Context *ctx, gaddr p) {
    uint32_t d = fake_sub(ctx, READ_FIELD(ctx, FakePair, p, a), READ_FIELD(ctx, FakePair, p, b));
    WRITE_FIELD(ctx, FakePair, p, d, d);
    uint8_t f = READ_FIELD(ctx, FakePair, p, flags);
    if ((int32_t)d < 0)
        f |= FAKE_PAIR_NEGATIVE;
    else
        f &= (uint8_t)~FAKE_PAIR_NEGATIVE;
    WRITE_FIELD(ctx, FakePair, p, flags, f);
    return d;
}
RECOMP_OVERRIDE(0x00201800) { FE_ENTRY(0x00201800, fake_diff, FE_ARG(0)); }

static uint32_t fake_gated(Context *ctx, gaddr p) {
    if (!fe_static_ready(ctx, FAKE_GATED_GUARD))
        return fe_use_original(ctx);
    return guest_u16(ctx, p + 2 * (guest_u32(ctx, FAKE_GATED_CACHE) & 3u));
}
RECOMP_OVERRIDE(0x00201900) { FE_ENTRY(0x00201900, fake_gated, FE_ARG(0)); }

const FeReplayOverride fe_replay_overrides[] = {
    {0x00200000u, override_0x00200000, "fake_heal"},    {0x00200100u, override_0x00200100, "fake_cached"},
    {0x00200300u, override_0x00200300, "fake_sum3"},    {0x00200400u, override_0x00200400, "fake_svc"},
    {0x00200500u, override_0x00200500, "fake_caller"},  {0x00200700u, override_0x00200700, "fake_caller2"},
    {0x00200800u, override_0x00200800, "fake_peek"},    {0x00200900u, override_0x00200900, "fake_store2"},
    {0x00200B00u, override_0x00200B00, "fake_version"}, {0x00200C00u, override_0x00200C00, "fake_mark"},
    {0x00200D00u, override_0x00200D00, "fake_plus1_r7"}, {0x00200E00u, override_0x00200E00, "fake_plus1_s20"},
    {0x00200F00u, override_0x00200F00, "fake_plus1_fpscr"}, {0x00201000u, override_0x00201000, "fake_twice"},
    {0x00201200u, override_0x00201200, "fake_extra"},   {0x00201300u, override_0x00201300, "fake_outp"},
    {0x00201400u, override_0x00201400, "fake_touch"},   {0x00201500u, override_0x00201500, "fake_plus1_scratch"},
    {0x00201600u, override_0x00201600, "fake_clampst"}, {0x00201700u, override_0x00201700, "fake_count"},
    {0x00201800u, override_0x00201800, "fake_diff"},    {0x00201900u, override_0x00201900, "fake_gated"},
};
const unsigned fe_replay_override_count = sizeof fe_replay_overrides / sizeof fe_replay_overrides[0];
