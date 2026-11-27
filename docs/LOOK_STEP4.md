# The step-4 look: one edit in each stat table, plus one castle edit

Prepared 2026-11-16 (round 15 plan, F-027). About 10-15 minutes of your time. This look is what can move
PORT_PLAN step 4 ("Stat tables", ~68%). The percent stays where it is until you have looked.

**In plain words.** One mod, called `LookStep4`, changes five things you can see within a few minutes
of loading a save. You install it with one command, load a save, look at four or five numbers and
pictures, then take it out with one command. Your saves, Zakuro settings and other files are not
touched. The tool puts its files only into Zakuro's mod folder for Fates, and uninstall takes out
exactly those files again.

## What changes

| # | Table | Change | Where to look | Before | After |
|---|---|---|---|---|---|
| 1 | People (Person) | Corrin's own HP bonus +5 (male and female Corrin) | Corrin's status screen, **HP** (the second number, the maximum) | your number | **+5** (example: 32 -> 37) |
| 2 | Classes (Job) | Corrin's classes move 2 more | Corrin's status screen, **Mov**; also the blue move area on a map | Nohr Prince/Princess **5**, Nohr Noble or Hoshido Noble **6** | **7** / **8** |
| 3 | Items (Item) | Bronze Sword might +10 | The item's info window (**Mt**): in the castle Armory, the convoy, or any unit carrying one | **4** | **14** |
| 4 | Skills (Skill) | Supportive (Corrin's personal skill) gets Nobility's icon | Corrin's status screen, skills page: the personal skill's small picture | Supportive's own picture | **the same picture as Nobility** (the skill Corrin learns first as Nohr Prince/Princess) |
| 5 | Castle (dining hall) | Every dish also gives Luck +2 | The meal result after cooking in the dining hall, and the status screen after eating | meals never give Luck | **Luck +2** on top of the meal's usual bonuses |

Notes on each:

1. HP: the game adds Corrin's own bonus to the class's HP every time it shows it, so the
   change shows in an existing save. If Corrin is already at the HP cap of the class, the number cannot
   go higher (very unlikely mid-game). The first HP number (current HP) may stay as it was until the next
   battle or heal; the second (maximum) is the one that should move.
2. Mov: boots, skills or pair-up that add movement add the same amount before and after, so the
   difference is still exactly 2.
3. Bronze Sword: our file says 4. If the game shows a different "before" number, please tell us
   the number you saw: that is useful too.
4. Skill picture: only the picture changes, not the name or what the skill does.
5. Dining hall: needs the dining hall built and a meal not yet eaten since the last battle. If your save
   cannot cook, skip this one and say so; the other four are enough for most of the step.

## Which save

Any save of your own where **Corrin is in your army** and you can reach **My Castle** (the castle needs
Chapter 7 or later; the dining hall look needs the dining hall). Any route works: Birthright, Conquest
or Revelation. Use a save you play from now, and **do not save the game while the mod is in** (or save
only into a spare slot), so your real save never holds modded numbers.

## Steps (10-15 minutes)

1. **Before (2 minutes).** Start Fire Emblem Fates in Zakuro as usual, load the save, go to My Castle and
   open Corrin's status. Write down HP (both numbers) and Mov, and look at the personal skill's picture.
   If you like, look at a Bronze Sword in the Armory or the convoy (Mt). Quit the game.
2. **Install (one command).** In the repository folder:

   ```bash
   python tools/mods/look_step4.py install
   ```

   It makes the mod (`mods/LookStep4`, from your own game files), checks it, builds it and copies it into
   Zakuro's mod folder for Fates. It prints every change with the old and new number. If anything is
   wrong it stops and does not touch Zakuro's folder. (If you already have other mods switched on in
   `mods/`, they are installed with it; `python tools/mods/mods.py list` shows them.)
3. **Look (5-10 minutes).** Start the game in Zakuro again, load the same save, and check the table
   above: Corrin's HP and Mov, the personal skill picture, a Bronze Sword's Mt, and (if you can) one meal
   in the dining hall. A screenshot or a short note per line is perfect: "1 yes, 2 yes, 3 showed 14,
   4 yes, 5 not tried".
4. **Uninstall (one command).** Quit the game first, then:

   ```bash
   python tools/mods/mods.py uninstall
   ```

   Start the game again: everything is as before.

If the game crashes on start or when loading the save, or a number did not change, please say which
one: each answer tells us something real about how the game reads its tables.

## What has already been checked (without you)

- **Built and read back** (`python tools/mods/look_step4.py check`): the mod builds two game files
  (`GameData/GameData.bin.lz` and `GameData/Castle/DiningData.bin.lz`). Both were decoded again with the
  table tools: exactly the 10 planned table cells and the 55 planned dish cells differ from the game,
  nothing else.
- **Installed and taken out** in a scratch Zakuro-style folder under `build/look_step4/` (never the
  real one): installed files equal the build; after uninstall the folder is byte for byte as before.
- **Existing tests** (2026-11-16): `python tools/mods/mods.py selftest` 24 of 24 passed,
  `python -m unittest tests.test_text_mods` 55 tests OK, `python tools/castle/test_castle.py` 18 OK
  (1 skipped). The checker itself was tested once with a planted wrong expectation (Bronze Sword
  might): it failed as it should.
- **The one install command** was also run with a scratch Zakuro folder (`--zakuro-dir` under
  `build/look_step4/`), followed by `mods.py uninstall`: 2 files in, 0 files left after.
- **The test robot** (its own game copy, the mod placed in the robot's own scratch data folder,
  `build/harness/data/<run>/mods/`): after booting to the title screen, and again after loading the
  robot's Birthright Chapter 25 save, the game's memory holds the **changed** Person, Job, Item and Skill
  records (all 10) and none of the unchanged ones; an unmodded run of the same route shows the reverse.
  So the game really loads the modded tables. **Not shown by the robot:** the dining hall file (it was not
  in memory in the castle; the game most likely reads it only when the dining hall opens), and no
  screen was looked at. That is what your look adds.

## For developers

- Tool: `tools/mods/look_step4.py` (`make`, `install`, `check`; standard library; uses
  `tools/mods/mods.py` for everything). Rows are found at run time by their English names in your own
  game files (`Nohr Prince`, `Bronze Sword`, `Supportive`, `Nobility` ...) and by the avatar labels, so no
  game data is stored in the repository.
- The cells: Person `base.hp` of the two avatar rows 2 -> 7; Job `mov` of rows 1-6 (Nohr Noble m/f
  6 -> 8, Nohr Prince 5 -> 7, Nohr Princess 5 -> 7, Hoshido Noble m/f 6 -> 8); Item `might` of row 1
  (Bronze Sword) 4 -> 14; Skill `icon` of row 160 (Supportive) 128 -> 107 (Nobility's); castle
  `DiningData_Dish.lck` of all 55 dishes 0 -> 2 (dish +0xB, read by `ProcDining::ReflectDishEffect`; the
  res column was avoided because the cooking title code also reads it). Confidence of every column used:
  high (docs/TABLES.md, docs/CASTLE.md). The stat formula (docs/TABLES.md "How a unit's stats are
  computed") says Person.base, Job.base, Job.mov and Item might are read every time they are shown.
- Robot evidence: `build/look_step4/robot_evidence.txt` (pattern counts in the 56 MiB heap dumps, which
  were deleted afterwards), the driver `build/look_step4/robot_look.py` (runs `headless.run` with the mod
  installed into the run's own `ZAKURO_DATA`; the castle route was an in-memory cut of `bt-ch26`'s first
  4,676 frames, nothing written to routes.json).
