# A first guide for players

**In plain words.** You can already change words, the number tables, a face, and how battles are drawn. You cannot yet change a rule the game uses while it plays, and you cannot yet roll the dice of who joins. Those come later. Nothing in this guide has been seen by you in a window. The tools have checked the files. The window is still yours.

Status 2026-11-17. Drawn from `docs/MODDING.md`, `docs/LOOK_SITTING.md`, `docs/LOOK_TEXT.md`, `docs/LOOK_STEP4.md`, `docs/LOOK_PORTRAIT.md`, `docs/EXTRAS.md`, `docs/OPTIONS_WIRING.md`, `docs/CAPABILITY.md`, `docs/tracks/WRITER_ORDER1.md`, and `docs/tracks/RANDOMIZER_PLAN.md`. A line marked **[not yet checked]** has no script result for that claim.

## What you can change today

| What | How it shows up | Checked by a script? | Seen in a window? |
|---|---|---|---|
| A name or a line of text | Jakob's name can be changed to Jacques in the army list | Yes: the text look builds, reads back, and uninstalls to the same bytes | **[not yet checked]** |
| One cell in each stat table, and one castle meal | More health, more move, a harder weapon, a different skill picture, a meal that also gives luck | Yes: the stat look reads back the planned cells. The robot saw the four table edits in memory. It did not open the dining hall | **[not yet checked]** |
| A portrait | Jakob can show Felicia's face. Felicia keeps her own, so you may see two | Yes: the portrait look swaps the pictures and uninstalls clean | **[not yet checked]** |
| Smoother or faster battles, and a wider 3D picture | Switches in Zakuro's Cheats window. They start off. Off is the original game | Yes, headless: two chapters replayed to the same save with the first three switches | **[not yet checked]** |

The PC options page (Esc, then FE options) only writes a small text file. Nothing in the game reads that file yet. Turning a switch there does not change the game. That is not a mod you can use today.

## What comes later

1. **Writers, after a separate yes.** A writer is a change the game stores while it plays: remembering your options, a class change, a level-up roll. The first one to test is the options writer, on a test copy, not in the game you play. Saying yes to that test does not turn it on for you. Class change, the level-up, and how an enemy picks a target stay off until each has its own proof and its own yes.
2. **A randomizer, after the port is finished.** Public tools already edit the tables. We do not copy them. The first later build is class, growth, and the stats someone joins with, on rows that already exist. Children and random maps are last.

## How a mod is laid out

A mod is a folder under `mods/`. The notes describe it like this:

```
mods/MyMod/
  mod.json          the name, and whether it is on
  text/             words, as a plain text file. Keep the labels. Change the words
  tables/           spreadsheets: people, classes, items, skills
  faces/            one folder of pictures per person
  maps/             one folder per chapter
  castle/           one folder per castle file, such as the dining hall
  romfs/            a whole replacement file, at the same path the game uses
```

Commands, from the mod note: `python tools/mods/mods.py build` checks and merges what is on. `install` copies that into Zakuro's folder for Fates. `uninstall` takes out exactly what install put there. `list` and `status` tell you what is on and whether it matches.

The three looks are already made that way. You do not have to build them by hand:

- `python tools/mods/look_text.py install`
- `python tools/mods/look_step4.py install`
- `python tools/mods/look_portrait.py install`

Take each out before the next: quit the game, then `python tools/mods/mods.py uninstall`. The sitting page has the exact order.

Screen extras are not a mod folder. One command writes a cheat file. You copy it into Zakuro's cheats folder yourself. Keep a copy of any file already there with the same name. The extras note has the five steps.

## What is safe

- One change at a time. If something looks odd, we then know which change did it.
- Do not save while a mod is in. Or save only into a spare slot. Your real save should not keep modded numbers.
- Quit the game before uninstall. Then start once more and confirm it is the original game.
- Off is the original game, for every extras switch. Untick it and restart. Zakuro keeps a cheat's change until the game restarts.
- If the tool says something is wrong, it stops and does not touch Zakuro's folder. That is the safe stop.
- Two mods that change the same word or the same cell stop the build and name both. That is what you want. Do not set the override switch unless you mean the later mod to win.

## What is not safe

- The story-scene 60 fps switch. It changes the game's hidden random values. Leave it off. The other three extras switches did not, in the headless check.
- A name much longer than the original. It may not fit the box. **[not yet checked]** in a window.
- Deleting a row, or adding a person. The port already refused new people: the list has a fixed size. A new item row is the first new row the notes allow, and it is a demo, not this guide.
- A map that puts more than 50 people in one army. The install can succeed, and the game will not create the extras. That was a review finding.
- Stacking the three looks. Take one out before the next.
- Treating the options file as a mod. Nothing reads it.
- Saving a game that was started with a mod in, and then loading that save with the mod taken out. The numbers may already be in the save. That is why you do not save.

## A short example

Rename one person: install the text look, load a save where Jakob is in the army, open the unit list. If his name is Jacques, the text path works. Quit, uninstall, and start again. His name should be Jakob. The same shape is how a stat edit and a face swap are checked. Write down what you saw, including "not tried" or "crashed when". That look is what moves the step. The tools do not.
