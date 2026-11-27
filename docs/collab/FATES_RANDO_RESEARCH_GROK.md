# What the public Fates randomizers already learned

**For the owner.** The public tools already found the crashes. We should copy that list, not their code. The cheap way to feel like the Sacred Stones randomizer is: new class, new growths, new items, same face. Swapping who appears in a voiced scene is the long job, and their bugs say so. Slice 1 already did the first part.

Status 2026-11-20. Public pages only. No code copied. Paragon, Ignis, and the upgraded script are GPL. Do not copy them.

## The tools

| Tool | Link | License | What it covers | Learn | Do not copy |
|---|---|---|---|---|---|
| Ignis | [thane98/ignis](https://github.com/thane98/ignis) | GPL-3.0 | The successor. Classes, skills, stats, join order, chest and village items. Route-specific stats. Weapon experience adjusted so the new class can fight. Cutscenes follow a swap | Give it a folder of game files and write a folder out. Language matters: North American English is not European English | The program. It is GPL |
| The 2016 randomizer | [GBAtemp thread](https://gbatemp.net/threads/wip-fire-emblem-fates-randomizer.452268/) | The thread points at Ignis now | Join order with dialogue and 3D scenes rewritten. Stats, skills, join items. A later beta tried parent and child pairs | A swap is not done until the scene shows the new person. Untested chapters will break | Any patch file from the thread |
| Upgraded script | [lashoun/upgraded-fefates-randomizer](https://github.com/lashoun/upgraded-fefates-randomizer) | GPL-3.0 | Growth totals and base totals, then a small shuffle. Class spread so one route does not get five of the same class. Option to keep the usual face. Personal skills printed for a person to type in. Children can be banned | Scale stats to the level of the spot. Keep the model until the scenes are ready. A fresh save only | Their weapon changes, new classes, and bundled visual mods |
| Paragon | [thane98/paragon](https://github.com/thane98/paragon) | GPL-3.0 | An editor for this game's tables, not a one-button randomizer. Ignis is built on it | One table edit should be visible to the others | The editor. GPL |
| FEAT, FEFTwiddler | Pages did not open | Not read | Not described here | Nothing, until a page opens | Do not guess their fields |
| Silent Waves randomizer | [akimiandkea/FEFSW-Randomizer](https://github.com/akimiandkea/FEFSW-Randomizer) | Not read | A hack's units, not the retail game | Not our tables | Do not use it as a map of retail files |

## What gets cheaper

The 20 to 27 rounds assumed recruitment, with voices and models, was in the first build. The public tools say that is the last build, and they still ship known breaks.

| Piece | Was | Now | Why |
|---|---|---|---|
| Growth modes (share the total, nudge each, or roll new) | several | 1 round [low] | We already edit growths. Their lesson is a total, then a small shuffle, scaled to the join level |
| Bases and join stats | in slice 1 | done | Slice 1. Add the three modes beside it, not a new system |
| Items, shops, chests | 3 | 1 to 2 [low] | Ignis already treats chests and villages as a separate switch. Our item tables rebuild |
| Skills in existing slots | 2 | 1 [low] | They print the skill and type it by hand. We can write the slot. Do not add a skill row |
| Enemy and boss gear | 2 | 1 to 2 [low] | Same unit list. Keep the last staff, door, and vein user. We already guard those |
| Same person, new class | part of the 20 | 1 [low] | Their switch that keeps the model. No scene rewrite |
| Who appears in the story | most of the 20 to 27 | still 8 to 12 [low] | Ignis exists to rewrite scenes, and the upgraded script still has a duplicate Hayato, a freeze, and a crash |
| Music | 1 | not found | No public Fates tool in this set randomizes music. Do not invent it |
| Nuzlocke | 2 | still 2, later | Not in these tools. A death log beside the save. Not a table |
| Children, supports, random maps | last | last | They ban children by default. So should we |

Honest total. The playable set, without swapping faces in scenes: about 6 to 8 more rounds after slice 1 [low]. The full Sacred Stones list, including recruitment theatre, music, and Nuzlocke: about 16 to 22 [low]. The saving is the pitfall list and not doing scenes first. It is not a free recruitment swap.

## Guard these from day one

- A fresh game only. Their note says an existing branch is unstable.
- One route's list is not another's. Revelation levels are wrong if you use another route's spots.
- North American text is not European text. Pick the language the files were built for.
- Keep the face until a scene pass exists. A class change does not need a new model.
- Conquest 9: talking to Nyx before the wall is broken can crash. Do not move that talk.
- Conquest 16: the spare prompt can freeze. Do not edit that scene file to "fix" it.
- Revelation 8: Hayato's replacement can fail, and you recruit two of him. Test that chapter before any join swap is called done.
- Revelation 13: obstacles can turn invisible. Do not ship a join swap that has not played that chapter.
- Two ninja maps need a flier, or one tile moved, or the door cannot be opened. We already keep a vein user. Keep a path too.
- A personal skill printed in a log is not in the game until a table edit writes it.
- Their ending-save change was not tested. Our endings still have no save. Do not add one.
- Do not take their weapon and class rebalance. That is a different game.
- Do not copy their visual pack, or the code folder one of them adds. Our recomp may not apply a code patch. Seal of Flames already showed that risk.

## Build order

1. Growth modes on the slice we have. One round.
2. Items, shops, and chests. One to two.
3. Skills in slots that exist. One.
4. Enemy gear, with the guards we have. One to two.
5. Stop. That is the playable randomizer. Same person, new class, seed in its own folder.
6. Join order only if you ask, and only after Revelation 8, Conquest 9, Conquest 16, and Revelation 13 have been played on a test seed.
7. Nuzlocke, music, children, and random maps after that, each its own yes.

## What you decide

1. Is the next build the playable set, with the same face, and join-order scenes left until you ask?
2. May we add the three growth modes on slice 1 before items?
3. Do we leave their weapon and class rebalance out?
4. Do children stay off until a later yes?
5. Is Nuzlocke out of this promise?
