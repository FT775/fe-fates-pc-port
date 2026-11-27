/* The one header a readable source includes (docs/READABLE.md). */

#ifndef FE_H
#define FE_H

#include "fe_guest.h"     /* memory, guest calls, FE_ENTRY (pulls in 3dsrecomp's overrides.h) */
#include "fe_structs.h"   /* generated: guest structs (config/readable/structs, config/tables) */
#include "fe_globals.h"   /* generated: G_* guest addresses of globals */
#include "fe_game.h"      /* generated: per-game constants (title id, guard routine) */
#include "fe_callees.h"   /* guest functions not rewritten yet */
#include "fe_functions.h" /* every readable function */

/* The forces (army sides) of the unit pool: UnitPool::GetFirst and
   Unit::GetNext scan force types 0 .. 9 [high: both loops stop at 10]. */
#define FORCE_COUNT 10u

#endif /* FE_H */
