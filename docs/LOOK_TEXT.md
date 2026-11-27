# The text look: one renamed name

Prepared 2026-11-16 (round 16, Grok's NEXT_R16 rank 3). About 5 minutes of your time. This look is
what can move PORT_PLAN step 3 ("Text mods"). The percent stays where it is until you have looked.

**In plain words.** One mod, called `LookText`, changes one name: **Jakob** (Corrin's butler) is
called **Jacques** everywhere the game shows his name from its name list (army list, status screen,
the small window when you point at him on a map, the name above his lines in a conversation). You
install it with one command, load a save, look at his name, then take it out with one command. Your
saves, Zakuro settings and other files are not touched. The tool puts its file only into Zakuro's mod
folder for Fates, and uninstall takes out exactly that file again.

## What changes

| Where to look | Before | After |
|---|---|---|
| My Castle: the army / unit list, and Jakob's status screen | **Jakob** | **Jacques** |
| On a map: the small window when the cursor is on him | **Jakob** | **Jacques** |
| A conversation where he speaks: the name above his lines | **Jakob** | **Jacques** (if it changes here too, that is a useful extra answer) |

Only the name changes: his face, class (still called Butler), stats and what he says stay the same.

## Which save

Any save of your own where **Jakob is in your army** (he is in it on every route after the early
chapters, unless he fell in Classic mode) and you can reach **My Castle**. Use a save you play from
now, and **do not save the game while the mod is in** (or save only into a spare slot).

## Steps (about 5 minutes)

1. **Before (1 minute, optional).** Load the save, go to My Castle, open the unit list and find
   Jakob. Quit the game.
2. **Install (one command).** In the repository folder:

   ```bash
   python tools/mods/look_text.py install
   ```

   It makes the mod (`mods/LookText`, from your own game files), builds it and copies it into
   Zakuro's mod folder for Fates. If anything is wrong it stops and does not touch Zakuro's folder.
3. **Look (2-3 minutes).** Start the game in Zakuro again, load the same save, open the unit list in
   My Castle: his name should read **Jacques**. Open his status screen too. A screenshot or a short
   note is perfect: "army list yes, status yes, conversation not tried".
4. **Uninstall (one command).** Quit the game first, then:

   ```bash
   python tools/mods/mods.py uninstall
   python tools/mods/mods.py disable LookText
   ```

   The first command takes the file out of Zakuro's folder; the second switches the mod off in
   `mods/`, so it is not installed again together with the next look. Start the game again: his
   name is Jakob again.

**Doing this look again later:** first run `python tools/mods/mods.py enable LookText`, then the install
command above. Without that the install says "nothing to install" and the game shows no change.

If the game crashes on start or when loading the save, or the name shows as empty boxes or
nonsense letters, please say so: that tells us something real about how the game reads its text.

## What has already been checked (without you)

- **Built and read back** (`python tools/mods/look_text.py check`): the mod builds one game file,
  the English name list (`m/@E/GameData.bin.lz`). It was decoded again with the text tools: the one
  label that says Jakob in the game says Jacques in the built file, and every other label and
  alias is exactly as in the game.
- **Installed and taken out** in a scratch Zakuro-style folder under `build/look_text/check/` (never
  the real one): the installed file equals the build; after uninstall the folder is byte for byte as
  before.
- **The checker itself** was tested once with a planted wrong name (the mod built "Jacquesx" while the
  check expected "Jacques"): it failed as it should.
- **The one install command** was also run with scratch mod, stage and Zakuro folders under
  `build/look_text/`, followed by `mods.py uninstall`: 1 game file in, 0 files left after.
- **Existing tests** (2026-11-16): `python tools/mods/mods.py selftest` 24 of 24 passed,
  `python -m unittest tests.test_text_mods` 55 tests OK.
- **The test robot** (its own game copy, the mod placed in the robot's own scratch data folder
  under `build/harness/data/<run>/mods/`): after booting to the title screen, and again in My Castle
  after loading the robot's Birthright Chapter 25 save, the game's memory holds the new name once and
  the old name one time fewer than without the mod; an unmodded run of the same two routes shows the
  old name and never the new one. So the game really loads the renamed name list. **Not shown by the
  robot:** no screen was looked at. That is what your look adds.

## For developers

- Tool: `tools/mods/look_text.py` (`make`, `install`, `check`; standard library; uses
  `tools/mods/mods.py` for everything, text pipeline T1 through `tools/mods/textmod.py`). The label is
  found at run time as the one `MPID_` name label of `m/@E/GameData.bin.lz` whose English text is
  `Jakob`; the mod file holds only the two header lines and that one label, so no other game text is
  stored. "Jacques" uses only letters the archive already uses (no font warning).
- Robot evidence: `build/look_text/robot_evidence.txt` (UTF-16LE counts of both names in the 56 MiB
  heap dump, deleted afterwards), driver `build/look_text/robot_look.py` (as
  `build/look_step4/robot_look.py`: `headless.run` with the mod installed into the run's own
  `ZAKURO_DATA`; routes `title` from the empty save and an in-memory cut of `bt-ch26`'s first 4,676
  frames from `bt-ch25-clear`; nothing written to routes.json).
- Same pattern as the ExampleText demo (docs/MODDING.md section 2), with a character who is in
  every route's army instead of Ryoma.
