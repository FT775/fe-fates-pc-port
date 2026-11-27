/* Forces (army sides) and the unit lists (Fates classes Force, UnitPool, Unit).

   The unit pool (G_UnitPool) holds an array of Force records, one per force
   type 0 .. 9 (UnitPool.forces, 12 bytes each). A force's units form a list:
   Force.first_unit, then Unit.next. A unit knows its force (Unit.force), and
   the force its type (Force.type).

   Walking several forces at once takes a mask of force types (bit t = force
   type t): UnitPool::GetFirst gives the first unit of the lowest force in
   the mask that has one, Unit::GetNext the unit after a given one, moving on
   to the next force in the mask when a list ends.

   Force types 0 and 2 are allied with each other (and every type with
   itself) [high for the test; names of the types not traced: in Awakening
   0 was the player and 2 the allied side].

   Unit::GetNext calls Force::Get (0x004F630C), a one-word NOP that runs into
   UnitPool::GetForce (0x004F6310): forces + type * 12. unit_pool_force does
   that computation here; there is no guest call.

   No guest writes, no guest calls, no one-time cache.

   Status: UNVERIFIED (below shadow-clean). */

#include "fe.h"

#define FORCE_TYPE_ALLY_OF_ZERO 2u /* the type allied with type 0 */

/* The Force record of a force type (type is not range-checked, as in the game).
   Guest function: helper of 0x004F6310 UnitPool::GetForce(int) (not
   overridden: Force::Get at 0x004F630C falls through into it, so 3dsrecomp
   keeps it inside that function). */
gaddr unit_pool_force(Context *ctx, uint32_t type) {
    gaddr forces = READ_FIELD(ctx, UnitPool, G_UnitPool, forces);
    return forces + type * (gaddr)sizeof(Force);
}

/* Whether a force and another force type fight on the same side: the same
   type, or the pair (0, 2) in either order. The other type is compared as a
   full 32-bit value with the force's type byte.
   Guest function: 0x0053C3E0 Force::IsAllied(Force::Type) const -> 1 or 0. */
int force_is_allied(Context *ctx, gaddr force, uint32_t other_type) {
    uint32_t type = READ_FIELD(ctx, Force, force, type);
    if (type == other_type)
        return 1;
    if (other_type == 0 && type == FORCE_TYPE_ALLY_OF_ZERO)
        return 1;
    return type == 0 && other_type == FORCE_TYPE_ALLY_OF_ZERO;
}

/* The first unit of the forces in the mask, starting at force type `from`:
   the first unit of the lowest such force that has one, or 0. */
static gaddr first_unit_from(Context *ctx, uint32_t force_mask, uint32_t from) {
    for (uint32_t type = from; type < FORCE_COUNT; type++) {
        if (!(force_mask & (1u << type)))
            continue;
        gaddr unit = READ_FIELD(ctx, Force, unit_pool_force(ctx, type & 0xFFu), first_unit);
        if (unit != 0)
            return unit;
    }
    return 0;
}

/* Guest function: 0x004F62CC UnitPool::GetFirst(unsigned int mask) -> unit or 0. */
gaddr unit_pool_first(Context *ctx, uint32_t force_mask) {
    return first_unit_from(ctx, force_mask, 0);
}

/* The unit after this one: the next unit of its own force (whatever the
   mask says), else the first unit of a higher force type in the mask, else 0.
   Guest function: 0x00533208 Unit::GetNext(unsigned int mask) const -> unit or 0. */
gaddr unit_next(Context *ctx, gaddr unit, uint32_t force_mask) {
    gaddr next = READ_FIELD(ctx, Unit, unit, next);
    if (next != 0)
        return next;
    gaddr force = READ_FIELD(ctx, Unit, unit, force);
    return first_unit_from(ctx, force_mask, (uint32_t)READ_FIELD(ctx, Force, force, type) + 1u);
}

RECOMP_OVERRIDE(0x0053C3E0) {
    FE_ENTRY(0x0053C3E0, force_is_allied, FE_ARG(0), FE_ARG(1));
}

RECOMP_OVERRIDE(0x004F62CC) {
    FE_ENTRY(0x004F62CC, unit_pool_first, FE_ARG(0));
}

RECOMP_OVERRIDE(0x00533208) {
    FE_ENTRY(0x00533208, unit_next, FE_ARG(0), FE_ARG(1));
}
