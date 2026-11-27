# Where a download should put the ROM

**For the owner.** The people who do this well do not leave the game file in the same pile as the code. You download their program, they ask for your copy, they check it is the right one, and they refuse a bad one in plain words. Saves live in a folder that is yours, not in the download. We should do that. We still cannot ship the game, the built program, or Seal of Flames.

Status 2026-11-20. Public pages only. No game file opened.

Sources: [Zelda 64 Recompiled](https://github.com/Zelda64Recomp/Zelda64Recomp) (you pick the ROM in the menu; saves go in the user folder; the release has no game files), [Ship of Harkinian](https://github.com/HarbourMasters/Shipwright) (a release zip, a hash list, a file picker, saves beside the program only if that folder already has the config), [Unleashed Recompiled](https://github.com/hedge-dev/UnleashedRecomp) (a release, then a wizard that takes the game, the update, and optional DLC, and refuses a modified copy), [OpenGOAL](https://github.com/open-goal/jak-project) (the GitHub page is for builders; players are sent elsewhere; the disc contents go in a named `iso_data` folder, never in the root).

## What they do

The release is a small zip. The source repo is for people who build. The ROM is never in either. The first run asks for the file, or looks in one named folder, then checks a hash and says what is wrong. Saves and settings go in a user folder, with a way to keep them next to the program if you want a portable copy. Mods go in a `mods` folder, or you drop them on the window. Credits and third-party notices are their own files.

We are different in one way. Their release can be a program that reads the ROM at run time. Ours cannot ship the built program, because that program contains the game. The download is the source, plus one double-click that builds. The first build is still 30 to 60 minutes, and it needs Python. Say that on the first page. Do not hide it.

## The tree

What a person sees after unzip:

```
Read Me First.txt
PLAY.bat
PLAY RANDOMIZED.bat
PLAY SEAL OF FLAMES.bat
roms/                 empty. A one-line note inside.
  README.txt          "Put the Special Edition USA .cci here. Nothing else."
  seal/               empty. "Put the Seal of Flames zip here. Do not unzip it."
play/                 made by the build. Not in the download.
  Fire Emblem Fates.exe
  saves/
  randomizer/<seed>/
  seal-of-flames/
  logs/
```

The ROM is checked by title and the hash we already use. A wrong edition, or an update file beside it, stops with one sentence. Seal of Flames is installed from their zip into `play/seal-of-flames/`. We do not edit their zip, and we do not unpack it into the root. Credit: Laz14, the GameBanana page, CC BY-NC-ND 4.0, not included.

`build/`, `extracted/`, and `asm/` stay off to the side, gitignored, for the robot. Tests keep their own APPDATA under `build/`. The owner's real Zakuro folder in `%APPDATA%` is never the place a test writes.

Do not move `tools/`, `src/`, `patches/`, `config/`, `docs/`, `tests/`, or `scout/` yet. A move breaks every path the robot already uses. The Read Me is what hides them. A later release zip can be just the three bats, the Read Me, and `roms/`, with the rest fetched as source. Not this week.

Third-party: Zakuro and 3dsrecomp get a credits line and a link. 3dsrecomp has no licence, so it is cloned at build time and never put in the zip. Seal of Flames gets a credit line and no files.

## What moves, and what can break

Move the `.cci` from the root into `roms/`. Move the unzipped Seal folder out of the root. The tool reads the zip from `roms/seal/`. `play/config.json` must not keep a path from this PC. The robot and the tests must keep writing under `build/`, not into `roms/` or `play/saves/`.

## What you decide

1. The ROM goes in `roms/`, hash-checked, not in the root?
2. The Seal zip goes in `roms/seal/`, and we never unpack it into the root?
3. Saves for a person who downloaded this stay in `play/`, not in `%APPDATA%`?
4. Leave the code folders where they are, and only add the Read Me and `roms/` for now?
