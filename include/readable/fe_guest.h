/* The readable layer's view of the guest: memory, guest calls and the entry
   glue that turns a readable C function into a 3dsrecomp override.
   Rules and examples: docs/READABLE.md. Every name here starts with fe_,
   guest_, READ_FIELD / WRITE_FIELD / FE_ so it cannot meet a generated name
   (func_..., override_..., original_..., recomp_...).

   Never write the 3dsrecomp override marker in this header, not even inside
   a macro: tools/readable/stage.py pastes headers into each staged file and
   3dsrecomp's scanner would take the marker for an override. (Comments are
   fine; the scanner ignores them, and so does tools/readable/check.py.) */

#ifndef FE_GUEST_H
#define FE_GUEST_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* 3dsrecomp's: Context, mem_read*, CALL, RETURN_TO, RECOMP_ORIGINAL. Its
   generated overrides.h has no include guard, so ours goes around it. */
#ifndef FE_OVERRIDES_H_INCLUDED
#define FE_OVERRIDES_H_INCLUDED
#include "overrides.h"
#endif
#include "fe_types.h"
#include "fe_capture.h" /* capture mode (docs/HARNESS.md 3.1); needs Context from overrides.h */

/* ------------------------------------------------------------------------
   Reading and writing guest memory.

   The guest is little-endian like every host we target. Reads go through
   3dsrecomp's page tables (or its host callbacks), one access per field, with
   the same width and signedness as the game's own load, so a readable
   function touches memory the way the original does. */

static inline int8_t guest_s8(Context *ctx, gaddr a) { return (int8_t)mem_read8(ctx, a); }
static inline uint8_t guest_u8(Context *ctx, gaddr a) { return (uint8_t)mem_read8(ctx, a); }
static inline int16_t guest_s16(Context *ctx, gaddr a) { return (int16_t)mem_read16(ctx, a); }
static inline uint16_t guest_u16(Context *ctx, gaddr a) { return (uint16_t)mem_read16(ctx, a); }
static inline int32_t guest_s32(Context *ctx, gaddr a) { return (int32_t)mem_read32(ctx, a); }
static inline uint32_t guest_u32(Context *ctx, gaddr a) { return (uint32_t)mem_read32(ctx, a); }
static inline uint64_t guest_u64(Context *ctx, gaddr a) {
    return (uint64_t)mem_read32(ctx, a) | (uint64_t)mem_read32(ctx, a + 4u) << 32;
}
/* a global or field that holds a guest pointer */
static inline gaddr guest_ptr(Context *ctx, gaddr a) { return (gaddr)mem_read32(ctx, a); }

static inline void guest_set_s8(Context *ctx, gaddr a, int8_t v) { mem_write8(ctx, a, (uint8_t)v); }
static inline void guest_set_u8(Context *ctx, gaddr a, uint8_t v) { mem_write8(ctx, a, v); }
static inline void guest_set_s16(Context *ctx, gaddr a, int16_t v) { mem_write16(ctx, a, (uint16_t)v); }
static inline void guest_set_u16(Context *ctx, gaddr a, uint16_t v) { mem_write16(ctx, a, v); }
static inline void guest_set_s32(Context *ctx, gaddr a, int32_t v) { mem_write32(ctx, a, (uint32_t)v); }
static inline void guest_set_u32(Context *ctx, gaddr a, uint32_t v) { mem_write32(ctx, a, v); }
static inline void guest_set_u64(Context *ctx, gaddr a, uint64_t v) {
    mem_write32(ctx, a, (uint32_t)v);
    mem_write32(ctx, a + 4u, (uint32_t)(v >> 32));
}

/* The member m of struct T, as a type only (never evaluated). */
#define FE_MEMBER(T, m) (((T *)0)->m)
/* Number of elements of an array member, e.g. FE_ARRAY_LEN(Unit, skills). */
#define FE_ARRAY_LEN(T, m) ((int)(sizeof(FE_MEMBER(T, m)) / sizeof(FE_MEMBER(T, m)[0])))
/* Guest address of member m of the T at guest address base. The member may
   have a run-time index, e.g. FIELD_ADDR(JobData, job, base_stats[stat]);
   gcc and clang accept that in offsetof. */
#define FIELD_ADDR(T, base, m) ((gaddr)((gaddr)(base) + (gaddr)offsetof(T, m)))

/* READ_FIELD(ctx, JobData, job, move) reads job->move from guest memory with
   the member's own width and signedness (structs: include/readable/generated/
   fe_structs.h). WRITE_FIELD(ctx, T, base, m, value) stores it. */
#define READ_FIELD(ctx, T, base, m) \
    _Generic(FE_MEMBER(T, m), \
        int8_t: guest_s8, uint8_t: guest_u8, int16_t: guest_s16, uint16_t: guest_u16, \
        int32_t: guest_s32, uint32_t: guest_u32, uint64_t: guest_u64)((ctx), FIELD_ADDR(T, base, m))
#define WRITE_FIELD(ctx, T, base, m, value) \
    _Generic(FE_MEMBER(T, m), \
        int8_t: guest_set_s8, uint8_t: guest_set_u8, int16_t: guest_set_s16, uint16_t: guest_set_u16, \
        int32_t: guest_set_s32, uint32_t: guest_set_u32, uint64_t: guest_set_u64)((ctx), FIELD_ADDR(T, base, m), (value))

/* Arithmetic shift right of a signed value, rounding down like the ARM code
   (gcc and clang shift signed values arithmetically). Used where the game
   halves a value that can be negative. */
static inline int32_t fe_asr(int32_t value, int bits) { return value >> bits; }

/* Add and multiply like the ARM add/mul: the result wraps at 32 bits. Used
   where a value from a guest call (any 32-bit number) takes part, so that a
   huge value wraps exactly as in the game instead of being a signed overflow,
   which C leaves undefined. The arithmetic is done unsigned (defined to wrap)
   and the result read back as signed (gcc and clang keep the bits). */
static inline int32_t fe_add32(int32_t a, int32_t b) { return (int32_t)((uint32_t)a + (uint32_t)b); }
static inline int32_t fe_mul32(int32_t a, int32_t b) { return (int32_t)((uint32_t)a * (uint32_t)b); }

/* ------------------------------------------------------------------------
   Giving up: the original runs instead.

   A readable function that meets a case it does not handle (a one-time cache
   the game has not filled yet, a guest call that could not finish) calls
   fe_use_original() and returns its value. FE_ENTRY then restores the guest
   state and runs the game's own function for this call. The flag is
   ctx->exit, which is always EXIT_NONE when an override is entered; while it
   is set, guest calls do nothing and return 0, so the rest of the readable
   function can run on without effect. Readable functions must not write guest
   memory before the point where they might give up (docs/READABLE.md, rule 5). */

static inline uint32_t fe_use_original(Context *ctx) {
    ctx->exit = EXIT_UNWIND;
    return 0;
}
static inline int fe_gave_up(const Context *ctx) { return ctx->exit != EXIT_NONE; }

/* A one-time cache of the game (a function-static local behind a C++ guard
   word, bit 0 = filled). Readable code reads the cached value only after the
   game filled it, and gives up otherwise, so the game's own lookup runs once,
   exactly as before. */
static inline int fe_static_ready(Context *ctx, gaddr guard) { return (guest_u32(ctx, guard) & 1u) != 0; }

/* ------------------------------------------------------------------------
   Calling a guest function that has no readable version yet.

   guest_call(ctx, address, a0, a1, a2, a3) runs the guest function at address
   (bit 0 set for Thumb) with up to four arguments in r0..r3 and returns r0.
   It looks the code up through the host, so it reaches an override if the
   callee has one, and the generated code otherwise.

   - When the host has no code for the callee (it would be interpreted), the
     call gives up before anything runs.
   - The callee runs with a large budget, so it cannot stop for the end of a
     timeslice in the middle; what it spent is charged afterwards (never below
     0). An instruction budget is only a scheduling quantum, so this changes
     timing by at most one slice and never results.
   - If it still stops (nested too deep, an svc the host wants to finish
     outside, code that must be interpreted), the readable function gives up
     and FE_ENTRY replays the call through the original. That replay is safe
     only for callees without side effects, or whose side effects are
     idempotent: readable code calls only such callees (rule 4).
   - Callees taking a fifth word of arguments: guest_call5 below (round 11);
     a fifth and a sixth word: guest_call6 below (round 15).
     More than six words: not supported yet. */

#define FE_GUEST_RETURN 0xFFFFFFE0u /* return address given to guest calls: never code */
#define FE_CALL_BUDGET 0x10000000   /* budget a guest call may use without stopping */

static inline uint32_t guest_call(Context *ctx, gaddr function, uint32_t a0, uint32_t a1, uint32_t a2,
                                  uint32_t a3) {
    if (ctx->exit != EXIT_NONE)
        return 0; /* an earlier step gave up */
    Code code = ctx->host->lookup(ctx, function);
    if (code == 0)
        return fe_use_original(ctx);
    if (ctx->depth + 1 > RECOMP_DEPTH_LIMIT)
        return fe_use_original(ctx);
    ctx->r[0] = a0;
    ctx->r[1] = a1;
    ctx->r[2] = a2;
    ctx->r[3] = a3;
    ctx->r[14] = FE_GUEST_RETURN;
    ctx->r[15] = function & ~1u;
    ctx->thumb = (uint8_t)(function & 1u);
    int32_t budget = ctx->budget;
    ctx->budget = FE_CALL_BUDGET;
    ctx->depth++;
    code(ctx);
    ctx->depth--;
    int32_t spent = FE_CALL_BUDGET - ctx->budget;
    ctx->budget = budget > spent ? budget - spent : 0;
    if (ctx->exit != EXIT_NONE)
        return 0; /* stopped inside: FE_ENTRY replays the call */
    if (ctx->r[15] != FE_GUEST_RETURN || ctx->thumb)
        return fe_use_original(ctx); /* came back somewhere else */
    return ctx->r[0];
}
/* guest_call with a fifth argument word on the guest stack (AAPCS: the word
   at sp when the callee is entered), as the game passes e.g. the rally kind
   of Unit::GetPowImpl. The word is stored at the first 8-byte aligned address
   at least 8 bytes below the readable function's sp, sp is lowered to it for
   the call and put back afterwards. That one store is in the dead stack
   (below sp, where the game's own call stores its frame and this very word
   too): no live guest data is there, capture compares leave it out
   (FE_CAP_STACK_WINDOW) and the host tests count it apart; so it is allowed
   before a possible give-up (docs/READABLE.md section 17: the one exception). */
static inline uint32_t guest_call5(Context *ctx, gaddr function, uint32_t a0, uint32_t a1, uint32_t a2,
                                   uint32_t a3, uint32_t a4) {
    if (ctx->exit != EXIT_NONE)
        return 0; /* an earlier step gave up */
    uint32_t sp = ctx->r[13];
    uint32_t low = (sp - 8u) & ~7u;
    guest_set_u32(ctx, low, a4);
    ctx->r[13] = low;
    uint32_t r = guest_call(ctx, function, a0, a1, a2, a3);
    ctx->r[13] = sp;
    return r;
}
/* guest_call5 with a sixth argument word too (AAPCS: the fifth word at sp,
   the sixth at sp + 4 when the callee is entered), as the game passes e.g.
   the two bools' second and the rally kind of Unit::GetCapabilityImpl. Both
   words go to the same 8-byte aligned slot guest_call5 uses (at least 8 bytes
   below the readable function's sp, so the sixth word is still below sp),
   sp is lowered to that slot for the call and put back afterwards. The two
   stores are in the dead stack, the same exception as guest_call5's
   (docs/READABLE.md section 17). Own test: tools/readable/tests/guest_call6_test.py. */
static inline uint32_t guest_call6(Context *ctx, gaddr function, uint32_t a0, uint32_t a1, uint32_t a2,
                                   uint32_t a3, uint32_t a4, uint32_t a5) {
    if (ctx->exit != EXIT_NONE)
        return 0; /* an earlier step gave up: nothing stored, nothing called */
    uint32_t entry_sp = ctx->r[13];
    uint32_t slot = (entry_sp - 8u) & ~7u; /* the fifth word here, the sixth at slot + 4 */
    guest_set_u32(ctx, slot, a4);
    guest_set_u32(ctx, slot + 4u, a5);
    ctx->r[13] = slot;
    uint32_t result = guest_call(ctx, function, a0, a1, a2, a3);
    ctx->r[13] = entry_sp;
    return result;
}
#define guest_call1(ctx, f, a0) guest_call((ctx), (f), (uint32_t)(a0), 0u, 0u, 0u)
#define guest_call2(ctx, f, a0, a1) guest_call((ctx), (f), (uint32_t)(a0), (uint32_t)(a1), 0u, 0u)
#define guest_call3(ctx, f, a0, a1, a2) guest_call((ctx), (f), (uint32_t)(a0), (uint32_t)(a1), (uint32_t)(a2), 0u)

/* ------------------------------------------------------------------------
   Entry glue.

   Each readable function that replaces a guest function gets a three-line
   override in its source file:

       RECOMP_OVERRIDE(0x0053C3E0) {
           FE_ENTRY(0x0053C3E0, force_is_allied, FE_ARG(0), FE_ARG(1));
       }

   A readable function with no argument besides ctx uses
   FE_ENTRY0(address, function) instead.

   The address is written twice, the same way both times (0x + 8 uppercase hex
   digits): once for 3dsrecomp's marker and once so FE_ENTRY can name the
   original. tools/readable/check.py checks they agree and that the address
   is the function's start in config/functions.csv and in
   config/readable/functions.csv.

   FE_ENTRY runs in one of four modes, chosen at run time by the environment
   variable FE_READABLE (src/readable/core/runtime.c):

   - shadow (default while functions are unverified): the game's original runs
     and its result is what the game sees; then the readable function runs on
     the same inputs and any difference in r0 is logged. Behaviour is the
     original's, whatever the readable code does (for side-effect-free
     functions, which is all the pilot).
   - readable: the readable function's result is used; if it gives up, the
     original runs for that call.
   - original: the override only forwards to the original.
   - capture (opt-in, harness only, docs/HARNESS.md 3.1): the original runs
     exactly as in original mode; sampled calls are recorded on the way
     (fe_capture.h). The readable function runs only on a private copy of a
     recorded call's entry memory (run B), never on the game's state.

   Return value: the readable function returns exactly the 32-bit value the
   game leaves in r0 (signed results sign-extended, bytes and halfwords
   zero-extended as the game does). FE_ENTRY returns with the caller's
   registers r1..r3, r12, flags and VFP registers as they were on entry, which
   AAPCS lets any function do. */

#define FE_ARG(n) (ctx->r[(n)])             /* argument n as unsigned 32 bits (also guest pointers) */
#define FE_ARG_S(n) ((int32_t)ctx->r[(n)])  /* argument n as signed 32 bits */

/* everything FE_ENTRY saves and restores */
typedef struct FeState {
    uint32_t r[16];
    uint8_t n, z, c, v, q, thumb, ge, exclusive;
    uint32_t exclusive_address;
    int32_t budget;
    uint32_t vfp[32];
    uint32_t fpscr;
} FeState;

static inline void fe_save(const Context *ctx, FeState *s) {
    memcpy(s->r, ctx->r, sizeof s->r);
    s->n = ctx->n;
    s->z = ctx->z;
    s->c = ctx->c;
    s->v = ctx->v;
    s->q = ctx->q;
    s->thumb = ctx->thumb;
    s->ge = ctx->ge;
    s->exclusive = ctx->exclusive;
    s->exclusive_address = ctx->exclusive_address;
    s->budget = ctx->budget;
    memcpy(s->vfp, ctx->vfp, sizeof s->vfp);
    s->fpscr = *ctx->fpscr;
}

/* restores s and clears the give-up flag; the budget only when asked */
static inline void fe_load(Context *ctx, const FeState *s, int with_budget) {
    memcpy(ctx->r, s->r, sizeof s->r);
    ctx->n = s->n;
    ctx->z = s->z;
    ctx->c = s->c;
    ctx->v = s->v;
    ctx->q = s->q;
    ctx->thumb = s->thumb;
    ctx->ge = s->ge;
    ctx->exclusive = s->exclusive;
    ctx->exclusive_address = s->exclusive_address;
    if (with_budget)
        ctx->budget = s->budget;
    memcpy(ctx->vfp, s->vfp, sizeof s->vfp);
    *ctx->fpscr = s->fpscr;
    ctx->exit = EXIT_NONE;
}

enum { FE_MODE_ORIGINAL = 0, FE_MODE_READABLE = 1, FE_MODE_SHADOW = 2, FE_MODE_CAPTURE = 3 };
enum { FE_EVENT_GAVE_UP = 0, FE_EVENT_SHADOW_SKIPPED = 1, FE_EVENT_SHADOW_MATCH = 2 };

/* src/readable/core/runtime.c */
int fe_mode(void);
void fe_event(int event, uint32_t address, const char *name);
void fe_shadow_mismatch(uint32_t address, const char *name, const FeState *entry, uint32_t game,
                        uint32_t readable);
void fe_force_mode(int mode); /* tests and debug tools: override FE_READABLE */
uint32_t fe_mismatch_count(uint32_t address);
uint32_t fe_event_count(int event, uint32_t address);

/* capture mode only (docs/HARNESS.md 5 rule 4): which of r0..r3 the readable
   function takes as arguments. FE_ENTRY's argument expressions are evaluated
   once on a block of marked registers (r_n = FE_CAP_ARG_MARK_OF(n)): bit n set =
   r_n is an argument. An expression that is not a plain FE_ARG gives all four.
   The values are kept in 64 bits so that a wider argument (such as a uint64_t
   built from two registers) is seen as not plain instead of being cut to its low
   half; FE_ARG_S marks come back sign-extended (high half all ones).
   A register that is not an argument is not compared in a call's note: a
   caller may leave anything there. */
static inline uint32_t fe_cap_args_mask(const uint64_t *v, unsigned n) {
    uint32_t m = FE_CAP_ARGS_KNOWN;
    for (unsigned i = 0; i < n; i++) {
        uint32_t high = (uint32_t)(v[i] >> 32);
        if (high != 0u && high != 0xFFFFFFFFu)
            return FE_CAP_ARGS_KNOWN | 0xFu; /* wider than 32 bits: not plain */
        unsigned r = 0;
        while (r < 16u && (uint32_t)v[i] != FE_CAP_ARG_MARK_OF(r))
            r++;
        if (r == 16u)
            return FE_CAP_ARGS_KNOWN | 0xFu; /* not a plain FE_ARG */
        if (r < 4u)
            m |= 1u << r;
    }
    return m;
}
#define FE_CAP_ARGS_FIND_(out, ...) do { \
    struct { uint32_t r[16]; } fe_marks_, *ctx = &fe_marks_; /* FE_ARG reads these */ \
    for (unsigned fe_i_ = 0; fe_i_ < 16u; fe_i_++) \
        fe_marks_.r[fe_i_] = FE_CAP_ARG_MARK_OF(fe_i_); \
    const uint64_t fe_v_[] = {__VA_ARGS__}; \
    (out) = fe_cap_args_mask(fe_v_, (unsigned)(sizeof fe_v_ / sizeof fe_v_[0])); \
} while (0)
#define FE_CAP_ARGS_NONE_(out) ((out) = FE_CAP_ARGS_KNOWN)

/* the body shared by FE_ENTRY and FE_ENTRY0; call = the readable function's
   call, find_args = sets fe_args_ to its argument bits (capture mode) */
#define FE_ENTRY_CALL_(address, function, call, find_args) do { \
    int fe_mode_ = fe_mode(); \
    if (fe_mode_ == FE_MODE_ORIGINAL) { \
        CALL(RECOMP_ORIGINAL(address)); \
        return; \
    } \
    if (fe_mode_ == FE_MODE_CAPTURE) { /* the original, recorded when sampled */ \
        static uint32_t fe_args_; /* argument bits, found once */ \
        if (fe_args_ == 0) \
            find_args; \
        if (fe_capture_call(ctx, (address), RECOMP_ORIGINAL(address), \
                            FE_CAP_KIND_OVERRIDE | (int)(fe_args_ << 8)) && \
            fe_capture_b_begin(ctx)) { /* run B on a copy of the entry pages */ \
            uint32_t fe_mine_ = (uint32_t)(call); \
            fe_capture_b_end(ctx, fe_mine_); /* puts the game's state back */ \
        } \
        return; \
    } \
    FeState fe_entry_; \
    fe_save(ctx, &fe_entry_); \
    if (fe_mode_ == FE_MODE_SHADOW) { \
        CALL(RECOMP_ORIGINAL(address)); /* leaves the override if the original stopped */ \
        FeState fe_game_; \
        fe_save(ctx, &fe_game_); \
        fe_load(ctx, &fe_entry_, 1); \
        uint32_t fe_mine_ = (uint32_t)(call); \
        int fe_skipped_ = fe_gave_up(ctx); \
        fe_load(ctx, &fe_game_, 1); /* the game goes on with the original's state */ \
        if (fe_skipped_) \
            fe_event(FE_EVENT_SHADOW_SKIPPED, (address), #function); \
        else if (fe_mine_ != fe_game_.r[0]) \
            fe_shadow_mismatch((address), #function, &fe_entry_, fe_game_.r[0], fe_mine_); \
        else \
            fe_event(FE_EVENT_SHADOW_MATCH, (address), #function); \
        return; \
    } \
    uint32_t fe_result_ = (uint32_t)(call); \
    if (fe_gave_up(ctx)) { \
        fe_event(FE_EVENT_GAVE_UP, (address), #function); \
        fe_load(ctx, &fe_entry_, 1); \
        CALL(RECOMP_ORIGINAL(address)); \
        return; \
    } \
    fe_load(ctx, &fe_entry_, 0); \
    ctx->r[0] = fe_result_; \
    RETURN_TO(ctx->r[14]); \
} while (0)

#define FE_ENTRY(address, function, ...) \
    FE_ENTRY_CALL_(address, function, function(ctx, __VA_ARGS__), FE_CAP_ARGS_FIND_(fe_args_, __VA_ARGS__))
/* the same for a readable function whose only parameter is ctx (C11 does not
   let the variable arguments of FE_ENTRY be left out) */
#define FE_ENTRY0(address, function) FE_ENTRY_CALL_(address, function, function(ctx), FE_CAP_ARGS_NONE_(fe_args_))

/* A harness probe (docs/HARNESS.md 3.2): an override that only forwards to
   the original, so the callee's calls become visible. Generated by
   tools/harness/gen_stubs.py into build/harness/ (never into src/readable/):

       <override marker>(0x00302C6D) { FE_PROBE(0x00302C6D); }   (a Thumb routine: odd literal)

   In capture mode the call is recorded when sampled and noted in every
   record that is open; otherwise a replay tool's sink hears of it. */
#define FE_PROBE(address) do { \
    if (fe_mode() == FE_MODE_CAPTURE) { \
        (void)fe_capture_call(ctx, (address), RECOMP_ORIGINAL(address), FE_CAP_KIND_PROBE); \
        return; \
    } \
    fe_probe_note(ctx, (address)); \
    CALL(RECOMP_ORIGINAL(address)); \
} while (0)

#endif /* FE_GUEST_H */
