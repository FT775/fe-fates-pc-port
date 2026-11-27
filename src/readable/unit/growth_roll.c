/* The level-up roll (Fates Random and Unit::LevelUp): helpers only.
   Plain-language description: docs/GROWTH.md sections 5 and 6.

   Every function here stands for game code that stores (the generator's
   state, the unit's seed, level and gains), so under docs/DECISIONS.md F-017
   they are helpers: they work on a host-side copy or return what the game
   would store, and write nothing to guest memory.

   The generator (Random::Initialize 0x0044ABC4, GetValue(void) 0x0044AE14,
   GetValue(int) 0x0044ADF8) is a 128-bit xorshift: four words filled from the
   seed with the multiplier 0x6C078965 (the Mersenne-twister seeding rule),
   then 20 values thrown away; each value is the new fourth word with its top
   bit cleared; GetValue(n) is that value modulo n (signed division).
   The generator helpers and the plan are pure: their Context is not used
   (the registry wants it first; NULL is fine).

   A level-up (Unit::LevelUp 0x003D8154): a fresh generator from the unit's
   growth seed; its first value becomes the next growth seed; level + 1; then
   for each stat 0 .. 7 with a growth rate above 0: one point per full 100 of
   the rate, then one value modulo 100, and one more point when it is below the
   rest of the rate; a point counts only while the stat is below its cap. When
   no stat got a point or a successful roll (caps aside), the eight stats are
   rolled again, at most 4 passes in all.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/unit/tests/growth_diff.py. */

#include "growth.h"

#define GROW_SEED_MULT 0x6C078965u
#define GROW_SEED_DISCARD 20

/* Random::Initialize(unsigned int). */
void growth_random_seed(Context *ctx, GrowthRandom *r, uint32_t seed) {
    uint32_t prev = seed;
    for (uint32_t i = 0; i < 4; i++) {
        r->s[i] = GROW_SEED_MULT * (prev ^ (prev >> 30)) + i;
        prev = r->s[i];
    }
    for (int i = 0; i < GROW_SEED_DISCARD; i++)
        (void)growth_random_next(ctx, r);
}

/* Random::GetValue(void): 0 .. 0x7FFFFFFF. */
uint32_t growth_random_next(Context *ctx, GrowthRandom *r) {
    (void)ctx;
    uint32_t t = r->s[0] ^ (r->s[0] << 11);
    uint32_t w = r->s[3];
    r->s[0] = r->s[1];
    r->s[1] = r->s[2];
    r->s[2] = w;
    r->s[3] = (t ^ (t >> 8)) ^ (w ^ (w >> 19));
    return r->s[3] & 0x7FFFFFFFu;
}

/* Random::GetValue(int): the value modulo n (n > 0; the game's division
   routine stops on n == 0, so callers never pass it). */
int32_t growth_random_below(Context *ctx, GrowthRandom *r, int32_t n) {
    int32_t v = (int32_t)growth_random_next(ctx, r);  /* 0 .. 0x7FFFFFFF: v % n never overflows */
    return v % n;
}

/* The roll decision: a stat gains its extra point when the value modulo 100
   is below what is left of the rate after the full hundreds. */
int growth_roll_hits(int32_t roll, int32_t rate) {
    return roll < rate;
}

/* The points of one level-up before the caps, from the seed and the rates
   alone (the caps never change which values are drawn). */
void growth_level_up_plan(Context *ctx, uint32_t seed, const int32_t rates[GROW_STATS], GrowthPlan *plan) {
    GrowthRandom r;
    growth_random_seed(ctx, &r, seed);
    plan->next_seed = growth_random_next(ctx, &r);
    plan->passes = 0;
    plan->draws = 0;
    for (int p = 0; p < GROW_PASSES; p++)
        for (uint32_t s = 0; s < GROW_STATS; s++)
            plan->points[p][s] = 0;
    int rose = 0;
    for (int pass = 0; pass < GROW_PASSES && !rose; pass++) {
        plan->passes++;
        for (uint32_t s = 0; s < GROW_STATS; s++) {
            int32_t rate = rates[s];
            if (rate <= 0)
                continue;
            while (rate >= 100) {
                rate -= 100;
                plan->points[pass][s]++;
                rose = 1;
            }
            plan->draws++;
            if (growth_roll_hits(growth_random_below(ctx, &r, 100), rate)) {
                plan->points[pass][s]++;
                rose = 1;
            }
        }
    }
}

/* one point of a stat, when the stat (with the points of this level-up so
   far, see GrowthCapFn) is still below its cap; returns 1 when it counted */
static int add_point(Context *ctx, gaddr unit, uint32_t stat, GrowthCapFn capability, void *env, int32_t *gains) {
    int32_t now = capability(ctx, env, unit, stat, (int8_t)*gains);
    int32_t cap = (int32_t)guest_call2(ctx, GROW_UnitGetLimit, unit, stat);
    if (now < cap) {
        *gains = fe_add32(*gains, 1);
        return 1;
    }
    return 0;
}

/* What Unit::LevelUp would store into the unit: the next growth seed, the
   level, the eight gains bytes and the eight stat_loss bytes (the points of a
   pass are added to stat_loss too while Unit.level_limit_raises is above
   Person.level_cap). Calls Unit::GetGrow and Unit::GetLimit through the guest
   in the game's order; the stat now comes from `capability`. Returns 1, or 0
   when a guest call gave up (out is then incomplete). */
int unit_level_up_preview(Context *ctx, gaddr unit, GrowthCapFn capability, void *env, GrowthLevelUp *out) {
    GrowthRandom r;
    growth_random_seed(ctx, &r, READ_FIELD(ctx, Unit, unit, growth_seed));
    out->growth_seed = growth_random_next(ctx, &r);
    out->level = (uint8_t)(READ_FIELD(ctx, Unit, unit, level) + 1u);
    for (uint32_t s = 0; s < GROW_STATS; s++) {
        out->gains[s] = guest_s8(ctx, FIELD_ADDR(Unit, unit, gains) + s);
        out->stat_loss[s] = guest_s8(ctx, FIELD_ADDR(Unit, unit, stat_loss) + s);
    }
    out->passes = 0;
    int rose = 0;
    for (int pass = 0; pass < GROW_PASSES && !rose; pass++) {
        out->passes++;
        for (uint32_t s = 0; s < GROW_STATS; s++) {
            int32_t rate = (int32_t)guest_call2(ctx, GROW_UnitGetGrow, unit, s);
            if (fe_gave_up(ctx))
                return 0;
            if (rate <= 0)
                continue;
            int32_t gains = out->gains[s];
            int32_t added = 0;
            while (rate >= 100) {
                rate -= 100;
                added += add_point(ctx, unit, s, capability, env, &gains);
                out->gains[s] = (int8_t)gains;
                rose = 1;
            }
            if (growth_roll_hits(growth_random_below(ctx, &r, 100), rate)) {
                added += add_point(ctx, unit, s, capability, env, &gains);
                rose = 1;
            }
            out->gains[s] = (int8_t)gains;
            gaddr person = READ_FIELD(ctx, Unit, unit, person);
            if ((int32_t)READ_FIELD(ctx, Unit, unit, level_limit_raises) > READ_FIELD(ctx, PersonData, person, level_cap))
                out->stat_loss[s] = (int8_t)(uint8_t)((uint8_t)out->stat_loss[s] + (uint32_t)added);
            if (fe_gave_up(ctx))
                return 0;
        }
    }
    return 1;
}
