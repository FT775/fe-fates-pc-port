# The rest of the randomizer

**For the owner.** The fun is a different army, not a broken scene. Shuffle who joins inside the route you picked, and leave their face and their lines alone until a later switch. Children get a new class, not a new parent. Promotions stay two choices. Music shuffles the maps, not the song. A Nuzlocke is one extra rule: a death stays dead after a reset. Classic already does the rest.

Status 2026-11-20. Read: `docs/collab/FATES_RANDO_RESEARCH_GROK.md`. Public pages for the seals, the class trees, and Classic. No code copied.

Sources: [Ignis](https://github.com/thane98/ignis), [the 2016 thread](https://gbatemp.net/threads/wip-fire-emblem-fates-randomizer.452268/), [the upgraded script](https://github.com/lashoun/upgraded-fefates-randomizer), [Heart Seal](https://fireemblemwiki.org/wiki/Heart_Seal), [Hoshidan classes](https://serenesforest.net/fire-emblem-fates/hoshidan-classes/), [Classic](https://www.thonky.com/fire-emblem-fates/starting-the-game), [children](https://www.thonky.com/fire-emblem-fates/marriage-and-children).

## Character shuffle

Three switches, not one.

- **Off.** Nobody moves.
- **Within this route.** The default. A person who joins on this route can take another's join spot. Corrin stays Corrin. Azura stays Azura. The royal a chapter is named for stays that royal.
- **Any route.** Off unless you ask. A Birthright join level is wrong on Conquest. That is how a chapter becomes unwinnable.

Two ways to do the swap.

- **Keep the face.** The person who speaks stays. Their class, growths, and items are the ones from the spot they took. This is the fun one that does not rewrite a scene. Build this first.
- **Full identity.** The other person appears in the scene, with their voice and their model. Ignis does this, and the public notes still list crashes. Build it second, off by default.

Test a full swap on a fresh save, in this order, and stop at the first break: the first chapter after the choice, Revelation 8 (a missing replacement can recruit two of the same person), Conquest 9 (a talk before a wall breaks can crash), Conquest 16 (a spare prompt can freeze), Revelation 13 (obstacles can vanish). Do not edit the spare scene to force it. Do not start from an old branch.

## Children

Randomize the child's class, growths, and one skill, inside what the parents can already pass on. The child who exists stays that child. The paralogue stays that paralogue.

Leave alone: who the parents are, whether a child is born, Kana, and the scene. A public tool tried random parents and called it experimental. We do not. If a parent would have been dead in a Nuzlocke, that child does not appear. No new child row. The person list is full.

## Promotions

Fates already gives two promotions from a Master Seal. A Heart Seal changes class by personality and does not reset the level. A third choice is a Sacred Stones idea, not a Fates one. It is not worth the default. It can offer a class the unit cannot hold.

Shuffle the two existing choices among classes of the same side, the same gender, and a weapon that class can hold. Do not add a third.

Leave these out of the shuffle: Songstress (no promotion), Kitsune and Wolfskin (one promotion each), Nohr Prince or Princess (the promotion is the route's noble, not a free pick). Download classes stay out.

## Music

Shuffle map themes and battle themes. The same seed gives the same track.

Never shuffle the title, a story scene, the choice of a side, a game-over sting, or the song a character sings. Those are timed to a scene. A swapped song can finish before the picture does, or play over a line that expected silence.

## Nuzlocke

Classic already removes a fallen unit for that save. That is the rule players mean by "dead is dead," and the game enforces it. [Thonky](https://www.thonky.com/fire-emblem-fates/starting-the-game).

The one rule the game does not enforce: a reset before the death is written brings them back. Build that. A side file next to the save lists the dead. Loading any save of that seed puts them back in the grave. A death that ends the chapter (Corrin, or someone the map says must live) is not written down. You restart as usual. Casual is ignored for that seed.

Do not build, yet: nicknames, "only one new ally a chapter" (this game's joins are written into the chapter), a capture quota, or a lock on the castle. Those are house rules. A written line in the page is enough.

A dedicated Fates rules page did not open. The two rules above are the ones the Sacred Stones port already proved, matched to Classic. Do not invent a third.

## What you decide

1. Within this route, keep the face, lords fixed, as the shuffle we build now?
2. Full identity stays off until those four chapters pass on a test seed?
3. Children keep their parents, and only class, growth, and one skill change?
4. Promotions stay two choices, with Songstress, the beasts, and the prince or princess left out?
5. Music is maps and battles only?
6. Nuzlocke is the graveyard that survives a reset, and nothing else?
