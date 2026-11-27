/* Where the options take effect in a fight and on the map (Fates): the
   battle-picture decision of the map battle sequence and the map HP bar
   decision. Plain-language description: docs/MENUS.md section 3.

   Both decisions sit inside functions that store (the battle sequence's
   constructor, map::Actor::Tick), so they are helpers (F-017): they return
   what the game would store and write nothing.

   Status: UNVERIFIED (below shadow-clean). Host differential test against the
   original ARM code: src/readable/menu/tests/menu_diff.py. */

#include "menus.h"

/* Helper for the battle-picture decision in 0x0035D2E8
   map::SequenceBattle::anonymous_namespace::ProcSequence::ProcSequence(const map::SequenceBattle::EventData*)
   (the part at 0x0035D8A0 .. 0x0035D96C): the flags word it would leave.
   Bit 0 (no battle picture) is set when forced_map is not 0, when flags
   bit 1 is already set, or when the option check answers 0. The option check
   is GameConfigData::IsDetailSupport for a sequence with flags bit 2 (a
   support or a dance), else IsDetailBattle, both through the guest with the
   two units and "L is held" (Pad.held bit 9) as the flip. Every cache the
   two checks need is asked first. */
int battle_picture_choice(Context *ctx, gaddr sequence, uint32_t *flags_after) {
    if (!fe_static_ready(ctx, MN_SupportGuard) || !fe_static_ready(ctx, MN_MustGuardA) ||
        !fe_static_ready(ctx, MN_MustGuardB) || !fe_static_ready(ctx, MN_NotAllowGuard))
        return 0;
    int map_only = READ_FIELD(ctx, BattleSequence, sequence, forced_map) != 0;
    uint32_t flags = 0;
    if (!map_only) {
        flags = READ_FIELD(ctx, BattleSequence, sequence, flags);
        map_only = (flags & 2u) != 0;
    }
    if (!map_only) {
        uint32_t flip = (READ_FIELD(ctx, Pad, guest_ptr(ctx, G_Pad), held) & 0x200u) != 0 ? 1u : 0u;
        gaddr a = READ_FIELD(ctx, BattleSequence, sequence, unit_a);
        gaddr b = READ_FIELD(ctx, BattleSequence, sequence, unit_b);
        gaddr config = guest_ptr(ctx, G_GameConfig);
        uint32_t picture = guest_call(ctx, (flags & 4u) ? MN_ConfigDetailSupport : MN_ConfigDetailBattle, config,
                                      a, b, flip);
        map_only = picture == 0;
    }
    if (map_only)
        flags = READ_FIELD(ctx, BattleSequence, sequence, flags) | 1u;  /* the game reads the word again */
    *flags_after = flags;
    return !fe_gave_up(ctx);
}

/* Helper for the HP bar decision in 0x0038D2B4 map::Actor::Tick(void) (the
   part at 0x0038D408 .. 0x0038D44C): 1 when the actor's map HP bar would be
   shown (stored as bit 4 of its draw word): the HP-bar option is not 0, the
   map has not hidden the bars (Situation.flags bit 0, set by the script
   command ChapterSetHideHpGauge) and the unit is not a carried pair partner
   (state bit 2). The map Situation pointer is not checked for 0, as in the
   game. */
int actor_hp_bar_shown(Context *ctx, gaddr actor, uint32_t *shown) {
    *shown = 0;
    if (READ_FIELD(ctx, GameConfigData, guest_ptr(ctx, G_GameConfig), hp_gauge) != 0 &&
        (READ_FIELD(ctx, Situation, guest_ptr(ctx, G_Situation), flags) & 1u) == 0 &&
        (READ_FIELD(ctx, Unit, READ_FIELD(ctx, MapActor, actor, unit), state_flags) & MN_STATE_PARTNER) == 0)
        *shown = 1;
    return !fe_gave_up(ctx);
}
