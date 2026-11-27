/* Guest functions the readable layer still calls through guest_call()
   because they have no readable version yet (Fire Emblem Fates).

   Each line: the guest address (#define GUEST_<name> 0x........u), what it
   takes and returns, why we believe it (the symbol map name and the code
   read), and whether it is safe to replay (docs/READABLE.md, rule 4: a guest
   call that stops is replayed through the caller's original, so the callee
   must have no side effects, or only idempotent ones).

   The Fates pilot (ai/ai_value.c, ai/ai_think.c, event/flags.c,
   unit/forces.c) calls no guest code: Force::Get (0x004F630C), which
   Unit::GetNext calls, is a one-word NOP falling into UnitPool::GetForce
   (0x004F6310), a pure address computation the readable code does itself.
   So this list is empty for now. */

#ifndef FE_CALLEES_H
#define FE_CALLEES_H

#endif /* FE_CALLEES_H */
