/* Flag sets (Fates class FlagManager).

   A FlagManager points to a bit array (FlagManager.bits): flag i is bit
   (i & 7) of byte (i >> 3, arithmetic shift). The same code as Awakening's
   flagset_test (config/readable/xmap_reference.csv, confidence high), with
   the array pointer at +0xC.

   No guest writes, no guest calls, no one-time cache.

   Status: UNVERIFIED (below shadow-clean). */

#include "fe.h"

/* Whether flag number index is set. The index is not range-checked; a
   negative one reaches below the array, as in the game.
   Guest function: 0x00508584 FlagManager::Get(int) const -> 1 or 0. */
int flag_manager_get(Context *ctx, gaddr flags, uint32_t index) {
    gaddr bits = READ_FIELD(ctx, FlagManager, flags, bits);
    uint32_t byte = guest_u8(ctx, bits + (gaddr)fe_asr((int32_t)index, 3));
    return (byte & (1u << (index & 7u))) != 0;
}

RECOMP_OVERRIDE(0x00508584) {
    FE_ENTRY(0x00508584, flag_manager_get, FE_ARG(0), FE_ARG(1));
}
