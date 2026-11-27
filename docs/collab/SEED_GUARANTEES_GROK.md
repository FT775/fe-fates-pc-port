# Grok (Hermes) on guarantees inside the randomizer (round 79 desk plan)

Asked 2026-11-25 by the round-79 desk session, one consult, facts only (no game data, no private details). The
answer is used in docs/SEED_GUARANTEES_PLAN.md. Grok's answer is kept as given; Claude's notes follow it.

## The question (as sent)

Today the randomizer only promises that each route (Birthright, Conquest, Revelation) has at least one staff user,
one door/chest opener (Locktouch class or skill) and one dragon-vein user somewhere in the route, with no timing.
We now want guarantees built into generation: the needed role joins at or before the first chapter that needs it.
Facts we measured: the first map with chests is chapter 7 on Birthright and Revelation and chapter 9 on Conquest;
the first locked doors are chapter 9 (Birthright), 12 (Conquest), 11 (Revelation). In the unmodded game the first
opener on Revelation only arrives after chapter 8, so the unmodded game itself does not meet "opener before the
first chest map" there. Dragon-vein users are always royals/Corrin, who keep their status. Fliers: the known trouble
maps are Birthright 10 and Revelation 11.

1. Which roles do randomizer players expect to be guaranteed, and by when?
2. Should the rule ever be stricter than the unmodded game, or is "never worse than vanilla" the better default?
3. Always on, or an opt-out "no safety net" switch?
4. Is a seed difficulty label (easy / fair / harsh) still worth having once the guarantees exist?
5. Common pitfalls in other randomizers' guarantee logic.

## Grok's answer

Fans expect a seed they can finish. Guarantee a door opener before the first locked door, a staff user with a staff
before the first long map, and a flier before Birthright 10 and Revelation 11. A vein user is already covered,
because Corrin and the royals keep that. Do not guarantee a horse, an archer, or a hammer. Those are comfort, not a
stuck map.

Do not be stricter than the unmodded game. Revelation's first chest map has no opener in the original, and those
chests can be skipped. Forcing one into chapter 7 changes the early army to fix a problem the game accepts. Do force
an opener before the first locked door. The original game already does that.

The guarantee stays on. A "No safety net" switch can exist for people who want a cruel seed, and it defaults off.
Fans do not want to opt in to being able to finish.

Keep the easy, fair, and harsh label. A healer in time does not make the enemies kind.

Watch for these traps. A guest who leaves, an enemy you must talk to, and a unit who joins the same turn on the wrong
side of a wall do not count. A lockpick class with no lockpick does not count. A staff user with no staff does not
count. A Heart Seal you get later does not count for chapter 7. A Nuzlocke death of the only opener is a failed run,
not a bad seed. A key item moved into a chest behind the door it opens is a softlock. A Birthright opener does not
help Conquest.

## Claude's notes on the answer

- **Taken:** "never stricter than the unmodded game" (plan section 2, call 1); healer must hold a staff (call 3);
  flier only before Birthright 10 and Revelation 11 (call 4); the vein needs no repair (Corrin); always on, no switch
  built now (call 8); Nuzlocke deaths are the player's run, not the seed (call 6); the label stays for later (call 12).
- **Door vs chest:** Grok ties the opener to the first locked **door**. The owner's words were "doors or chests".
  The plan keeps the owner's words (chests count) but applies Grok's "never stricter" rule, so on Revelation the
  chest need moves to the first chest map after the original game's opener arrives (chapter 9). Doors are never
  later than that on any route.
- **"A lockpick class with no lockpick does not count":** in Fates the lock-opening skill comes with the class's
  own skill list or the person's own skills, not with an item, so this trap does not apply as worded. The keys in
  shops are not counted (as today).
- **"A key item moved into a chest behind the door":** the chest track already never moves keys
  (`chests.STORY_ITEMS`, docs/rando/CHESTS.md rule 2), so this cannot happen today. The plan keeps it as a test.
- **"A guest who leaves":** handled by using the army the robot actually read at each chapter (plan section 2),
  not "joined somewhere before".
