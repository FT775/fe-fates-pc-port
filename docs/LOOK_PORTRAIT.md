# The portrait look: one portrait swapped

Prepared 2026-11-16 (round 16, Grok's NEXT_R16 rank 3). About 5 minutes of your time. This look is
what can move PORT_PLAN step 5 ("Pictures": the portrait part). The percent stays where it is until
you have looked.

**In plain words.** One mod, called `LookPortrait`, gives **Jakob** (Corrin's butler) **Felicia's
face**: wherever the game shows Jakob's portrait, it should show Felicia's picture instead. It is one
direction only: Felicia keeps her own face, so you may see two Felicias. His name, voice and stats
stay Jakob's. You install it with one command, load a save, look at his picture, then take it out with
one command. Your saves, Zakuro settings and other files are not touched. The tool puts its files only
into Zakuro's mod folder for Fates, and uninstall takes out exactly those files again.

## What changes

| Where to look | Before | After |
|---|---|---|
| A conversation where Jakob talks (his big standing picture) | Jakob's face | **Felicia's face**, every expression (smiling, angry ...) |
| The small talk window picture next to his lines, and his picture on the status / unit screens if the game shows one there | Jakob's face | **Felicia's face** |

Notes:

- Every one of his expressions now shows a Felicia expression: the same expression where she has
  one, her normal face where she has none (two of his expressions have no Felicia twin).
- The small sweat and blush marks the game draws on top of a face stay Jakob's and are placed where
  his face was, so they may sit slightly off on her face. The whole picture may also sit a few pixels
  higher or lower than her own, because the game keeps Jakob's placement numbers. Both are expected.
- Only his two portrait kinds that this look covers change (standing and talk window). If the game
  shows a third, larger "cut-in" picture of him somewhere, that one stays his: please note it if you
  see it.

## Which save

Any save of your own where **Jakob is in your army** and you can reach **My Castle**. The surest
place to see his face is his status screen (or a talk scene at a chapter's start where he
speaks); a support conversation works only if one is ready to view. Use a save you play from now, and **do not save the
game while the mod is in** (or save only into a spare slot).

## Steps (about 5 minutes)

1. **Before (1 minute, optional).** Load the save, open Jakob's status screen or a conversation with
   him and look at his face. Quit the game.
2. **Install (one command).** In the repository folder:

   ```bash
   python tools/mods/look_portrait.py install
   ```

   It makes the mod (`mods/LookPortrait`, from your own game files: Jakob's portrait files with
   Felicia's pictures painted in), builds it and copies it into Zakuro's mod folder for Fates. It takes
   under a minute. If anything is wrong it stops and does not touch Zakuro's folder.
3. **Look (2-3 minutes).** Start the game in Zakuro again, load the same save, and look at Jakob's
   picture in a conversation and on his status screen. A screenshot or a short note is perfect:
   "conversation: Felicia's face yes, talk window yes, status screen showed no picture".
4. **Uninstall (one command).** Quit the game first, then:

   ```bash
   python tools/mods/mods.py uninstall
   python tools/mods/mods.py disable LookPortrait
   ```

   The first command takes the files out of Zakuro's folder; the second switches the mod off in
   `mods/`. Start the game again: Jakob has his own face.

**Doing this look again later:** first run `python tools/mods/mods.py enable LookPortrait`, then the install
command above. Without that the install says "nothing to install" and the game shows no change.

If he shows a garbled, black or empty picture, or the game crashes when he talks, please say so:
each answer tells us something real about how the game reads its pictures.

## What has already been checked (without you)

- **Built and read back** (`python tools/mods/look_portrait.py check`): the mod builds two game files,
  Jakob's standing and talk-window portrait files. Both were decoded again with the picture tools:
  every expression picture in them matches Felicia's picture (the largest average colour difference is
  under 1 in 255, from the game's picture compression), the sweat and blush marks are Jakob's as
  before, and every picture keeps its size.
- **Installed and taken out** in a scratch Zakuro-style folder under `build/look_portrait/check/`
  (never the real one): the installed files equal the build; after uninstall the folder is byte for
  byte as before.
- **The checker itself** was tested once with a planted mistake (the two expressions without a Felicia
  twin left as Jakob's): it failed on exactly those four pictures, as it should.
- **The one install command** was also run with scratch mod, stage and Zakuro folders under
  `build/look_portrait/`, followed by `mods.py uninstall`: 2 game files in, 0 files left after.
- **Existing tests** (2026-11-16): `python tools/mods/mods.py selftest` 24 of 24 passed (it includes
  the ExampleFace portrait build, install and uninstall).
- **The test robot was not tried** for this look: the game most likely reads a portrait only when it
  shows it, and no robot route is known to show Jakob's face, so a memory check like the one for the
  name would probably not see it. It was not tried (no game run, no screen looked
  at). Your look is the
  first time a changed portrait is seen in the game; the earlier blue-Ryoma demo (docs/MODDING.md 6b)
  has not been seen either.

## For developers

- Tool: `tools/mods/look_portrait.py` (`make`, `install`, `check`; standard library). It uses the
  existing portrait mod kind (`faces/`, docs/MODDING.md 6b, the same path as ExampleFace): `mods.py
  face`-style export of Jakob's `_st` and `_bu` packages into `mods/LookPortrait/faces/Jakob_st|_bu/`,
  then each expression PNG is overwritten with Felicia's same-named PNG of the same size (her normal
  expression where the name is missing), exported from the user's game into
  `build/look_portrait/source/`. No new picture format was opened; no picture is stored in the
  repository. The build re-encodes the changed PNGs (ETC1A4) and reads them back, as for any face mod.
- Characters are found at run time by their English name labels and FaceData records. FaceData itself
  (Jakob's layout numbers, overlay positions) is not changed: that is why the overlays and placement
  stay his.
- Read-back gate per swapped picture: mean absolute RGBA difference to Felicia's decoded picture < 6
  and less than a third of the difference to Jakob's; kept pictures (overlays) within 6 of Jakob's.
