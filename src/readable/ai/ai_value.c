/* AI script argument values (Fates class AIValue).

   An AI script argument is an s16. Some values are special [high for the
   tests, names from the game's symbol map]:
     -1  Default   the script's default ("any" in the Awakening port)
     -2  Max       the largest value (meaning not traced)
     -3  Skip      the script runners skip the entry
     -4 .. -7      Argument: AI argument 0 .. 3 of the unit's current order
   Any other value is used as it is.

   Each unit holds sixteen AI arguments (Unit.ai_arguments, s16, four per
   order). AIValue::GetArgument finds the one an argument value names.

   All six functions are byte-for-byte the same code as six Awakening
   functions the Awakening port rewrote (config/readable/xmap_reference.csv,
   confidence high), with only the struct offset in GetArgument moved (0x6A
   in Fates): the same reads in the same order, widths and signs.

   None of these functions writes guest memory, calls guest code or uses a
   one-time cache, so none can give up.

   Status: UNVERIFIED (below shadow-clean): not yet run against the game
   (tier 2 needs the 3dsrecomp verify build; docs/READABLE.md). */

#include "fe.h"

#define AI_VALUE_DEFAULT (-1)
#define AI_VALUE_MAX (-2)
#define AI_VALUE_SKIP (-3)
#define AI_VALUE_ARGUMENT_FIRST (-4) /* -4 .. -7: argument 0 .. 3 of the order */
#define AI_ARGUMENTS_PER_ORDER 4

static int32_t ai_value(Context *ctx, gaddr value) {
    return guest_s16(ctx, value);
}

/* Whether the value names one of the four AI arguments, i.e. is -7 .. -4.
   The game tests it as one unsigned comparison of (value + 7) with 3.
   Guest function: 0x00543DF4 AIValue::IsArgument() const -> 1 or 0. */
int ai_value_is_argument(Context *ctx, gaddr value) {
    int32_t v = ai_value(ctx, value);
    return v <= AI_VALUE_ARGUMENT_FIRST && v > AI_VALUE_ARGUMENT_FIRST - AI_ARGUMENTS_PER_ORDER;
}

/* Guest address of the AI argument a value names: argument (-4 - value) of
   the given order, an s16 in Unit.ai_arguments. Nothing is checked (callers
   test ai_value_is_argument first): every input is used as it comes and the
   address wraps at 32 bits like the game's arithmetic.
   Guest function: 0x00543E0C AIValue::GetArgument(Order::Type, Unit*) const
   -> address of an s16. */
gaddr ai_value_argument_address(Context *ctx, gaddr value, uint32_t order, gaddr unit) {
    uint32_t argument = (uint32_t)AI_VALUE_ARGUMENT_FIRST - (uint32_t)ai_value(ctx, value);
    uint32_t slot = order * AI_ARGUMENTS_PER_ORDER + argument;
    return FIELD_ADDR(Unit, unit, ai_arguments) + slot * 2u;
}

/* Guest function: 0x00543E28 AIValue::IsMax() const -> 1 or 0. */
int ai_value_is_max(Context *ctx, gaddr value) {
    return ai_value(ctx, value) == AI_VALUE_MAX;
}

/* Guest function: 0x00543E44 AIValue::IsSkip() const -> 1 or 0. */
int ai_value_is_skip(Context *ctx, gaddr value) {
    return ai_value(ctx, value) == AI_VALUE_SKIP;
}

/* Whether the value is negative (any special value).
   Guest function: 0x00543E58 AIValue::IsSignal() const -> 1 or 0. */
int ai_value_is_signal(Context *ctx, gaddr value) {
    return ai_value(ctx, value) < 0;
}

/* Guest function: 0x00543E6C AIValue::IsDefault() const -> 1 or 0. */
int ai_value_is_default(Context *ctx, gaddr value) {
    return ai_value(ctx, value) == AI_VALUE_DEFAULT;
}

RECOMP_OVERRIDE(0x00543DF4) {
    FE_ENTRY(0x00543DF4, ai_value_is_argument, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00543E0C) {
    FE_ENTRY(0x00543E0C, ai_value_argument_address, FE_ARG(0), FE_ARG(1), FE_ARG(2));
}

RECOMP_OVERRIDE(0x00543E28) {
    FE_ENTRY(0x00543E28, ai_value_is_max, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00543E44) {
    FE_ENTRY(0x00543E44, ai_value_is_skip, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00543E58) {
    FE_ENTRY(0x00543E58, ai_value_is_signal, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00543E6C) {
    FE_ENTRY(0x00543E6C, ai_value_is_default, FE_ARG(0));
}
