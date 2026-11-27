# Speed, picture size, and a new-game randomizer

**For the owner.** Run the game at 60. Do not run the rules at 120. Draw the 3D sharper, up to the limit Zakuro already has. A randomizer is a choice before a new game, written as its own mod for that save, not mixed into your other mods. The first two are mostly already built. The randomizer is the long one.

Status 2026-11-19. Read: `docs/EXTRAS.md`, Zakuro's settings and menus, `docs/tracks/RANDOMIZER_PLAN.md`, `docs/TABLES.md`. No game file opened. No code copied.

## 60, not 120

The map already draws 60 pictures a second. Battles were 30. Our extra makes them 60 by shortening the wait, not by changing the rules. Units, the hidden dice, and the save stayed the same. That is the speed to ship.

120 as game logic would mean the rules advance twice as often. The frame step is a whole number. There is no half step. That would change timing, the dice, and saves. Zakuro can draw an in-between picture for a game that runs at 30. That is a smoother picture, not a faster game, and it is not 120. Do not build a 120 mode.

Story scenes at 60 change the hidden dice. Leave that switch off. Do not "fix" it by guessing. It stays off until a test shows the dice and the save match the original.

**Recommendation: 60 for the game.** Battles use the extra we already proved. The map stays as it is. Story scenes stay at their original speed.

## How sharp

Zakuro already draws the 3D at 1 to 8 times the console picture (400 by 240 on top). The slider stops at 8. A sample in the settings code uses 3. Words can be drawn again at 4 times, as a separate switch. 16:9 is a shape, not a size: Zakuro's 16:9 shape and our 16:9 extra must both be on, or the picture stretches. The window size is a third knob. Pixels can stay blocky or be smoothed.

A higher 3D scale does not sharpen the flat pictures or the menus. Those stay the old size unless the word switch is on. Cost grows with the square: 3 times is 9 times the pixels, 8 times is 64.

**Recommendation: default 3 times, ceiling 8 times, do not raise the ceiling.** Turn 16:9 shape and the 16:9 extra on together. Turn the sharper words on if the menus look soft. Leave smoothing off if you want the old pixels.

## The randomizer

A page before a new game: a seed, and a few switches. The same seed gives the same game. You can send the seed. It writes a mod folder for that save only, through the table tools we already have. It does not poke memory at boot. It does not turn a writer on. It does not merge with your other mods. A normal save never sees it. Delete that folder and the game is the original tables.

Public tools to learn from, not to copy: [Paragon](https://github.com/thane98/paragon) (GPL, edits the tables), [the upgraded Fates randomizer](https://github.com/lashoun/upgraded-fefates-randomizer) (writes a list; personal skills were applied by hand), [the older thread](https://gbatemp.net/threads/wip-fire-emblem-fates-randomizer.452268/). FEBuilder is the other-game shape, not a Fates tool, and it is GPL. Do not copy it.

Include, in this order:

1. Class, growth, and the stats someone joins with, on rows that already exist. No new person. The list is full.
2. What they hold, and what a shop sells, if the equip check still passes.
3. Skills, only in slots someone already has.
4. Enemy gear. Not how the enemy thinks.
5. Who joins which existing spot, same route only. A Birthright list is not a Conquest list.
6. Children, supports, and random maps last. Children may be off. A random map waits until one moved unit has been seen.

Do not randomize away the last person who can use a vein, open a door, or use a staff, on a map that needs one. Do not give a class the person cannot be, or a weapon that class cannot hold. Gender-locked classes stay locked. The singer, the lords, and anyone a scene calls by name stay those people. Dragonstone stays on the person the story transforms. Do not add a person. Do not change the hidden dice.

Size: the page and the first slice are about two rounds [low]. Items and skills, one round each. Joins, one round. Children and maps are not in the first build.

## Order

1. Ship 60. Story 60 stays off. Hours. Already proved.
2. Set the picture default to 3 times, ceiling 8, 16:9 on as a pair. Hours.
3. Randomizer page, seed, per-save folder, class and growth only. About two rounds [low]. The rest waits.

## What you decide

1. 60 for the game, and no 120 logic?
2. Story scenes stay at their original speed until a test shows the dice match?
3. Default 3 times, ceiling 8, 16:9 shape and extra on together?
4. The randomizer writes a folder for that save only, and does not touch your other mods?
5. The first build is class, growth, and join stats, with children off?
