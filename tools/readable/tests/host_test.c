/* Host-side test of the readable layer's glue and the Fates pilot functions,
   run by `python tools/readable/check.py` (built against tools/readable/stub/).

   What it proves: FE_ENTRY's modes (readable, shadow match and mismatch,
   original), that scratch registers and flags come back as the caller left
   them, READ_FIELD widths and signs, and that each pilot function computes
   what its comment says on made-up records.
   What it does NOT prove: that the comments describe the game. Only the
   3dsrecomp verify run and the tier-4 harness compare against the original
   code (docs/READABLE.md, docs/HARNESS.md).

   All records here are invented test values, not game data. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fe.h"

/* ---- a tiny fake guest: three mapped windows, the rest faults */
#define DATA_BASE 0x00600000u /* covers the G_* globals (.data/.bss of Fates: 0x006B4000..) */
#define DATA_SIZE 0x00200000u
#define HEAP_BASE 0x08000000u
#define HEAP_SIZE 0x00100000u
#define STACK_TOP 0x10000000u

static uint8_t *data_mem, *heap_mem, *stack_mem;
static uint8_t **pages;
static unsigned faults;

static uint8_t *host_at(uint32_t a) {
    if (a - DATA_BASE < DATA_SIZE) return data_mem + (a - DATA_BASE);
    if (a - HEAP_BASE < HEAP_SIZE) return heap_mem + (a - HEAP_BASE);
    if (a - (STACK_TOP - 0x10000u) < 0x10000u) return stack_mem + (a - (STACK_TOP - 0x10000u));
    return NULL;
}
static uint8_t cb_read8(Context *c, uint32_t a) { (void)c; uint8_t *p = host_at(a); if (!p) { faults++; return 0; } return *p; }
static uint16_t cb_read16(Context *c, uint32_t a) { return (uint16_t)(cb_read8(c, a) | cb_read8(c, a + 1) << 8); }
static uint32_t cb_read32(Context *c, uint32_t a) { return (uint32_t)cb_read16(c, a) | (uint32_t)cb_read16(c, a + 2) << 16; }
static void cb_write8(Context *c, uint32_t a, uint8_t v) { (void)c; uint8_t *p = host_at(a); if (p) *p = v; else faults++; }
static void cb_write16(Context *c, uint32_t a, uint16_t v) { cb_write8(c, a, (uint8_t)v); cb_write8(c, a + 1, (uint8_t)(v >> 8)); }
static void cb_write32(Context *c, uint32_t a, uint32_t v) { cb_write16(c, a, (uint16_t)v); cb_write16(c, a + 2, (uint16_t)(v >> 16)); }
static void cb_interpret(Context *c, uint32_t a, uint32_t o) { (void)c; (void)a; (void)o; }
static void cb_svc(Context *c, uint32_t n) { (void)c; (void)n; }
static Code cb_lookup(Context *c, uint32_t a) { (void)c; (void)a; return NULL; } /* the pilot calls no guest code */

/* "the original": the stand-in maps every RECOMP_ORIGINAL here */
static uint32_t g_original_result;
static int g_original_calls;
void fe_stub_original(Context *ctx) {
    g_original_calls++;
    ctx->r[0] = g_original_result;
    ctx->r[1] = 0xDEAD0001u; /* an original may leave junk in scratch registers */
    ctx->r[15] = ctx->r[14] & ~3u;
}

static const Host host = {cb_read8, cb_read16, cb_read32, cb_write8, cb_write16, cb_write32, cb_interpret, cb_lookup, cb_svc};
static uint32_t vfp[32], fpscr;

static Context fresh(void) {
    Context c;
    memset(&c, 0, sizeof c);
    c.read_pages = pages;
    c.write_pages = pages;
    c.vfp = vfp;
    c.fpscr = &fpscr;
    c.host = &host;
    c.r[13] = STACK_TOP - 0x1000u;
    c.r[14] = 0x00123450u;
    c.budget = 1000;
    return c;
}

/* ---- writing test records */
static void w8(uint32_t a, uint8_t v) { *host_at(a) = v; }
static void w16(uint32_t a, uint16_t v) { memcpy(host_at(a), &v, 2); }
static void w32(uint32_t a, uint32_t v) { memcpy(host_at(a), &v, 4); }
#define SET(T, base, m, v) _Generic(FE_MEMBER(T, m), int8_t: w8, uint8_t: w8, int16_t: w16, uint16_t: w16, \
    int32_t: w32, uint32_t: w32)(FIELD_ADDR(T, base, m), (v))

static int failures, checks;
#define CHECK(cond) do { checks++; if (!(cond)) { failures++; printf("  FAIL line %d: %s\n", __LINE__, #cond); } } while (0)
#define CHECK_EQ(got, want) do { long long g_ = (long long)(got), w_ = (long long)(want); checks++; \
    if (g_ != w_) { failures++; printf("  FAIL line %d: %s = %lld, want %lld\n", __LINE__, #got, g_, w_); } } while (0)

/* overrides under test (names from 3dsrecomp's marker) */
void override_0x00543DF4(Context *ctx);
void override_0x00543E0C(Context *ctx);
void override_0x00543E28(Context *ctx);
void override_0x00543E44(Context *ctx);
void override_0x00543E58(Context *ctx);
void override_0x00543E6C(Context *ctx);
void override_0x004C8584(Context *ctx);
void override_0x004C8544(Context *ctx);
void override_0x00508584(Context *ctx);
void override_0x0053C3E0(Context *ctx);
void override_0x004F62CC(Context *ctx);
void override_0x00533208(Context *ctx);

/* test layout in the fake heap */
#define T_VALUE   (HEAP_BASE + 0x0000u)
#define T_UNITS   (HEAP_BASE + 0x1000u) /* unit k at T_UNITS + k * 0x200 */
#define T_FORCES  (HEAP_BASE + 0x4000u)
#define T_ROOT    (HEAP_BASE + 0x5000u)
#define T_STATE   (HEAP_BASE + 0x5100u)
#define T_FLAGS   (HEAP_BASE + 0x6000u)
#define T_BITS    (HEAP_BASE + 0x6100u)
#define UNIT(k) (T_UNITS + (uint32_t)(k) * 0x200u)
#define FORCE(t) (T_FORCES + (uint32_t)(t) * (uint32_t)sizeof(Force))

static void test_layout(void) {
    /* the generated structs carry the offsets read from the code */
    CHECK_EQ(offsetof(Unit, next), 0x14);
    CHECK_EQ(offsetof(Unit, ai_arguments), 0x6A);
    CHECK_EQ(offsetof(Unit, force), 0xA4);
    CHECK_EQ(offsetof(Unit, map_x), 0xF4);
    CHECK_EQ(offsetof(Unit, map_y), 0xF5);
    CHECK_EQ(sizeof(Force), 0xC);
    CHECK_EQ(offsetof(Force, type), 0x8);
    CHECK_EQ(offsetof(FlagManager, bits), 0xC);
    CHECK_EQ(offsetof(UnitPool, forces), 0x4);
    CHECK_EQ(FE_GAME_GUARD_ENTRY & 1u, FE_GAME_GUARD ? 1 : 0); /* Fates' guard is Thumb */
}

static void test_ai_value(void) {
    Context c = fresh();
    static const int16_t vals[] = {-8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 7, 0x7FFF, -32768};
    for (unsigned i = 0; i < sizeof vals / sizeof vals[0]; i++) {
        int16_t v = vals[i];
        w16(T_VALUE, (uint16_t)v);
        CHECK_EQ(ai_value_is_argument(&c, T_VALUE), v >= -7 && v <= -4);
        CHECK_EQ(ai_value_is_max(&c, T_VALUE), v == -2);
        CHECK_EQ(ai_value_is_skip(&c, T_VALUE), v == -3);
        CHECK_EQ(ai_value_is_signal(&c, T_VALUE), v < 0);
        CHECK_EQ(ai_value_is_default(&c, T_VALUE), v == -1);
    }
    /* GetArgument: unit + 0x6A + 2 * (order * 4 + (-4 - value)) */
    w16(T_VALUE, (uint16_t)-4);
    CHECK_EQ(ai_value_argument_address(&c, T_VALUE, 0, UNIT(0)), UNIT(0) + 0x6Au);
    w16(T_VALUE, (uint16_t)-7);
    CHECK_EQ(ai_value_argument_address(&c, T_VALUE, 3, UNIT(0)), UNIT(0) + 0x6Au + 2u * (3u * 4u + 3u));
    w16(T_VALUE, 5); /* not an argument: used as it comes, wraps at 32 bits */
    CHECK_EQ(ai_value_argument_address(&c, T_VALUE, 1, UNIT(0)), (uint32_t)(UNIT(0) + 0x6Au + 2u * (4u - 9u)));
    CHECK_EQ(faults, 0);

    /* the overrides in readable mode: result in r0, return to lr, scratch kept */
    fe_force_mode(FE_MODE_READABLE);
    w16(T_VALUE, (uint16_t)-5);
    c = fresh(); c.r[0] = T_VALUE; c.r[2] = 0x77u; c.z = 1;
    override_0x00543DF4(&c);
    CHECK_EQ(c.r[0], 1);
    CHECK_EQ(c.r[15], 0x00123450u);
    CHECK_EQ(c.r[2], 0x77u);
    CHECK_EQ(c.z, 1);
    c = fresh(); c.r[0] = T_VALUE; c.r[1] = 2; c.r[2] = UNIT(1);
    override_0x00543E0C(&c);
    CHECK_EQ(c.r[0], UNIT(1) + 0x6Au + 2u * (2u * 4u + 1u));
    w16(T_VALUE, (uint16_t)-2);
    c = fresh(); c.r[0] = T_VALUE; override_0x00543E28(&c); CHECK_EQ(c.r[0], 1);
    c = fresh(); c.r[0] = T_VALUE; override_0x00543E44(&c); CHECK_EQ(c.r[0], 0);
    c = fresh(); c.r[0] = T_VALUE; override_0x00543E58(&c); CHECK_EQ(c.r[0], 1);
    c = fresh(); c.r[0] = T_VALUE; override_0x00543E6C(&c); CHECK_EQ(c.r[0], 0);
}

static void test_ai_think(void) {
    Context c = fresh();
    w32(G_AIThinkHolder, T_ROOT);
    SET(AIThinkRoot, T_ROOT, state, T_STATE);
    SET(Unit, UNIT(0), map_x, (int8_t)5);
    SET(Unit, UNIT(0), map_y, (int8_t)-3);
    SET(AIThinkState, T_STATE, move_over, 0u);
    CHECK_EQ(ai_think_is_move_over(&c), 0);
    CHECK_EQ(ai_think_is_move_over_at(&c, UNIT(0), 5, (uint32_t)-3), 0);   /* no target: unit not read */
    CHECK_EQ(ai_think_is_move_over_at(&c, 0xDEAD0000u, 5, 0), 0);          /* ... so a bad unit cannot fault */
    CHECK_EQ(faults, 0);
    SET(AIThinkState, T_STATE, move_over, 0x80000000u);
    CHECK_EQ(ai_think_is_move_over(&c), 1);
    CHECK_EQ(ai_think_is_move_over_at(&c, UNIT(0), 5, (uint32_t)-3), 1);   /* signed tile bytes */
    CHECK_EQ(ai_think_is_move_over_at(&c, UNIT(0), 5, 0xFDu), 0);          /* -3 is not 253 */
    CHECK_EQ(ai_think_is_move_over_at(&c, UNIT(0), 4, (uint32_t)-3), 0);

    fe_force_mode(FE_MODE_READABLE);
    c = fresh(); c.r[0] = UNIT(0); c.r[1] = 5; c.r[2] = (uint32_t)-3;
    override_0x004C8544(&c);
    CHECK_EQ(c.r[0], 1);
    c = fresh(); override_0x004C8584(&c); CHECK_EQ(c.r[0], 1);
}

static void test_flags(void) {
    Context c = fresh();
    SET(FlagManager, T_FLAGS, bits, T_BITS + 0x10u);
    w8(T_BITS + 0x10u, 0x81u);     /* flags 0 and 7 */
    w8(T_BITS + 0x12u, 0x04u);     /* flag 18 */
    w8(T_BITS + 0x0Fu, 0x80u);     /* flag -1: byte -1 (arithmetic shift), bit 7 */
    CHECK_EQ(flag_manager_get(&c, T_FLAGS, 0), 1);
    CHECK_EQ(flag_manager_get(&c, T_FLAGS, 1), 0);
    CHECK_EQ(flag_manager_get(&c, T_FLAGS, 7), 1);
    CHECK_EQ(flag_manager_get(&c, T_FLAGS, 18), 1);
    CHECK_EQ(flag_manager_get(&c, T_FLAGS, 17), 0);
    CHECK_EQ(flag_manager_get(&c, T_FLAGS, (uint32_t)-1), 1);
    fe_force_mode(FE_MODE_READABLE);
    c = fresh(); c.r[0] = T_FLAGS; c.r[1] = 18; override_0x00508584(&c); CHECK_EQ(c.r[0], 1);
}

static void test_forces(void) {
    Context c = fresh();
    memset(host_at(T_FORCES), 0, 10 * sizeof(Force));
    SET(UnitPool, G_UnitPool, forces, T_FORCES);
    for (uint32_t t = 0; t < 10; t++)
        SET(Force, FORCE(t), type, (uint8_t)t);
    CHECK_EQ(unit_pool_force(&c, 3), FORCE(3));

    /* allied: same type, or 0 with 2 either way */
    for (uint32_t a = 0; a < 4; a++)
        for (uint32_t b = 0; b < 4; b++)
            CHECK_EQ(force_is_allied(&c, FORCE(a), b), a == b || (a == 0 && b == 2) || (a == 2 && b == 0));
    CHECK_EQ(force_is_allied(&c, FORCE(0), 0x100u), 0);    /* full 32-bit compare with the byte */

    /* lists: force 1: u1 -> u2; force 3: u3; force 9: u9 */
    SET(Force, FORCE(1), first_unit, UNIT(1));
    SET(Force, FORCE(3), first_unit, UNIT(3));
    SET(Force, FORCE(9), first_unit, UNIT(9));
    SET(Unit, UNIT(1), next, UNIT(2));
    SET(Unit, UNIT(2), next, 0u);
    SET(Unit, UNIT(3), next, 0u);
    SET(Unit, UNIT(9), next, 0u);
    SET(Unit, UNIT(1), force, FORCE(1));
    SET(Unit, UNIT(2), force, FORCE(1));
    SET(Unit, UNIT(3), force, FORCE(3));
    SET(Unit, UNIT(9), force, FORCE(9));
    CHECK_EQ(unit_pool_first(&c, 0x3FFu), UNIT(1));
    CHECK_EQ(unit_pool_first(&c, 1u << 3 | 1u << 9), UNIT(3));
    CHECK_EQ(unit_pool_first(&c, 1u << 0 | 1u << 2), 0);     /* empty forces */
    CHECK_EQ(unit_pool_first(&c, 1u << 10), 0);              /* types past 9 are never looked at */
    CHECK_EQ(unit_next(&c, UNIT(1), 0), UNIT(2));             /* own list first, whatever the mask */
    CHECK_EQ(unit_next(&c, UNIT(2), 0x3FFu), UNIT(3));        /* then higher forces in the mask */
    CHECK_EQ(unit_next(&c, UNIT(2), 1u << 9 | 1u << 1), UNIT(9)); /* lower or own types are skipped */
    CHECK_EQ(unit_next(&c, UNIT(9), 0x3FFu), 0);
    CHECK_EQ(faults, 0);

    /* through the overrides, each mode */
    fe_force_mode(FE_MODE_READABLE);
    c = fresh(); c.r[0] = FORCE(2); c.r[1] = 0; g_original_calls = 0;
    override_0x0053C3E0(&c);
    CHECK_EQ(c.r[0], 1);
    CHECK_EQ(g_original_calls, 0);
    c = fresh(); c.r[0] = 0x3FFu; override_0x004F62CC(&c); CHECK_EQ(c.r[0], UNIT(1));
    c = fresh(); c.r[0] = UNIT(2); c.r[1] = 0x3FFu; override_0x00533208(&c); CHECK_EQ(c.r[0], UNIT(3));

    fe_force_mode(FE_MODE_SHADOW);
    c = fresh(); c.r[0] = UNIT(2); c.r[1] = 0x3FFu;
    g_original_result = UNIT(3); g_original_calls = 0;
    override_0x00533208(&c);
    CHECK_EQ(g_original_calls, 1);
    CHECK_EQ(c.r[0], UNIT(3));
    CHECK_EQ(c.r[1], 0xDEAD0001u); /* shadow keeps exactly the original's state */
    CHECK_EQ(fe_mismatch_count(0x00533208), 0);
    CHECK_EQ(fe_event_count(FE_EVENT_SHADOW_MATCH, 0x00533208), 1);
    c = fresh(); c.r[0] = UNIT(2); c.r[1] = 0x3FFu;
    g_original_result = UNIT(9);   /* pretend the game disagrees */
    override_0x00533208(&c);
    CHECK_EQ(c.r[0], UNIT(9));     /* the game's answer is what the caller gets */
    CHECK_EQ(fe_mismatch_count(0x00533208), 1);

    fe_force_mode(FE_MODE_ORIGINAL);
    c = fresh(); c.r[0] = FORCE(2); c.r[1] = 0;
    g_original_result = 42; g_original_calls = 0;
    override_0x0053C3E0(&c);
    CHECK_EQ(g_original_calls, 1);
    CHECK_EQ(c.r[0], 42);
    CHECK_EQ(fe_event_count(FE_EVENT_SHADOW_MATCH, 0x0053C3E0), 0);
}

int main(void) {
    data_mem = calloc(DATA_SIZE, 1);
    heap_mem = calloc(HEAP_SIZE, 1);
    stack_mem = calloc(0x10000u, 1);
    pages = calloc(1u << 20, sizeof *pages); /* every page null: all accesses go through the host */
    if (!data_mem || !heap_mem || !stack_mem || !pages) {
        printf("host test: out of memory\n");
        return 2;
    }
    test_layout();
    test_ai_value();
    test_ai_think();
    test_flags();
    test_forces();
    printf("host test: %d/%d checks passed\n", checks - failures, checks);
    return failures ? 1 : 0;
}
