/* Every readable function, by game system, with the guest function it
   stands for (Fire Emblem Fates; names of the guest functions from the
   game's own symbol map, extracted/romfs/debug/name.StackTrace).

   Status of every function below: UNVERIFIED (below shadow-clean). The
   registry with the same list, and each function's tier-2 status, is
   config/readable/functions.csv. */

#ifndef FE_FUNCTIONS_H
#define FE_FUNCTIONS_H

#include "fe_types.h"
#ifndef FE_OVERRIDES_H_INCLUDED /* 3dsrecomp's overrides.h has no include guard */
#define FE_OVERRIDES_H_INCLUDED
#include "overrides.h"
#endif

/* ---- ai: AI script argument values (src/readable/ai/ai_value.c) */
int ai_value_is_argument(Context *ctx, gaddr value);                          /* 0x00543DF4 AIValue::IsArgument */
gaddr ai_value_argument_address(Context *ctx, gaddr value, uint32_t order, gaddr unit); /* 0x00543E0C AIValue::GetArgument */
int ai_value_is_max(Context *ctx, gaddr value);                               /* 0x00543E28 AIValue::IsMax */
int ai_value_is_skip(Context *ctx, gaddr value);                              /* 0x00543E44 AIValue::IsSkip */
int ai_value_is_signal(Context *ctx, gaddr value);                            /* 0x00543E58 AIValue::IsSignal */
int ai_value_is_default(Context *ctx, gaddr value);                           /* 0x00543E6C AIValue::IsDefault */

/* ---- ai: the AI's move target (src/readable/ai/ai_think.c) */
int ai_think_is_move_over(Context *ctx);                                      /* 0x004C8584 AIThink::IsMoveOver() */
int ai_think_is_move_over_at(Context *ctx, gaddr unit, uint32_t x, uint32_t y); /* 0x004C8544 AIThink::IsMoveOver(Unit*,int,int) */

/* ---- event: flags (src/readable/event/flags.c) */
int flag_manager_get(Context *ctx, gaddr flags, uint32_t index);              /* 0x00508584 FlagManager::Get(int) */

/* ---- unit: forces and the unit lists (src/readable/unit/forces.c) */
gaddr unit_pool_force(Context *ctx, uint32_t type);                           /* helper of 0x004F6310 UnitPool::GetForce */
int force_is_allied(Context *ctx, gaddr force, uint32_t other_type);          /* 0x0053C3E0 Force::IsAllied */
gaddr unit_pool_first(Context *ctx, uint32_t force_mask);                     /* 0x004F62CC UnitPool::GetFirst */
gaddr unit_next(Context *ctx, gaddr unit, uint32_t force_mask);               /* 0x00533208 Unit::GetNext */

#endif /* FE_FUNCTIONS_H */
