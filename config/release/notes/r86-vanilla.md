# FE Fates PC port r86 (source only)

The source of a PC port of Fire Emblem Fates (Special Edition, USA): tools, our Zakuro patches with the in-game
randomizer and Nuzlocke mode, tests and guides. **There is no program and no game in this download.** You bring your
own decrypted copy of the game, and the game program is made on your own PC.

r68 was the last public download. The number jumped because it follows our work rounds, not 18 missed releases.

## What's new since r68

- **Full character swap.** On the Randomizer page, the "How they look" row now offers "Full swap" as well as "Keep the
  face": the person who takes a spot brings their own face, name and head on the battle model, also inside story
  scenes. Story movies and My Room keep the original person (castle join scenes show the new one). Corrin, Azura, Gunter, the royals and the
  children do not move, and swaps stay within the same sex.
- **Presets and share code.** Two buttons: Light (classes and growths) and Wild (Light plus enemy classes and weapons,
  map music and who joins where). A share code puts your seed and every setting in one line: the same code always
  makes the same game.
- **Seed guarantees.** Whatever the seed, someone who can open doors, a healer and (where a map needs one) a flier
  join in time for the maps that need them.
- **The Getting ready window.** On the first start, `PLAY.bat` helps you find your game file, points to the game
  program or to Zakuro, and prepares the Randomizer. A freshly unzipped folder keeps its saves inside itself.
- **True hit** (Esc > Helpers, Off at first). The battle forecast also shows the real chance to hit, for example
  "70 (real 79)". It only changes what is shown, never a roll.
- **New Game defaults** (Esc > Helpers). Pick battle animations, map speed, enemy turn skip and HP bars once; every
  New Game then starts with them. Games already going are never changed.
- **The Classic fix.** The randomizer and Nuzlocke now start on Classic too, not only on Casual and Phoenix.
- **Also:** a "Chest and village items" row, growth rates in Preparations (press Y), a "Next New Game" part in
  Esc > Randomizer, and a new build guide, `docs/BUILD.md`.

## What you need

- Windows 11, Python 3.13 and Git for Windows.
- Your own **decrypted** `.cci` of Fire Emblem Fates **Special Edition (USA)**, in the `roms` folder. Its check number
  (SHA-256) is checked. Birthright or Conquest alone, other regions, encrypted copies and update files are refused.
- Then pick a road. **Neither road has been tried on a clean PC yet.**
  - **Road A, no build (plain game only, no randomizer):** install Zakuro (https://github.com/fearkov/zakuro), let
    it recompile the game once, then run `PLAY.bat`. You get the plain game. The Randomizer page, Nuzlocke, True hit,
    New Game defaults and the built-in 60 fps / 16:9 need Road B. We use Zakuro v0.2.32; a newer one was not tried.
  - **Road B, build it:** install Rust, the Visual Studio C++ Build Tools, a C compiler and an archiver, then build
    our patched Zakuro with three commands (`docs/BUILD.md`). You get everything. About 30-60 minutes to install the
    tools and 30-60 minutes for the first build (both estimates). The program you build holds the game's code:
    it is for you only, never share it.
- Start with `Read Me First.txt`.

## Known limits

- Rarely, the randomizer's own safety check refuses a seed (we found one, 6ipff2kc, with everything turned on). If
  that happens, press Back and pick another seed.
- Checked by our test robot on all three stories, randomizer off and on. Not yet played to the end by a person.
- Road A and Road B have not been tried on a clean PC.
- Road A, what should happen: in the Getting ready window press Z and point to the folder that holds zakuro.exe.
  The program row shows [!] until Zakuro has recompiled the game, then [x], and PLAY starts Zakuro with your game.
  Saves stay in Zakuro's own place (%APPDATA%\zakuro). Never tried: a Zakuro newer than v0.2.32, and
  `PLAY RANDOMIZED.bat` on stock Zakuro. The window still offers R (Randomizer preparation) on Road A, but the
  in-game Randomizer page, True hit and New Game defaults exist only in the program you build (Road B).
- After a late change on the Randomizer page, pressing Start can take 6 to 11 seconds.
- In the Getting ready window, key 1 ("look for it") may skip a game file kept in OneDrive. Keys 2 and 3 work.
- A few screens were only checked by robots, never looked at by a person: the True hit label, the Helpers help line,
  and the full face swap in this version of the program.

## Not included

- The game. Use your own copy; it is never shared.
- Any program file: no .exe, no .dll, no game files or game text.

## Credits

Full list: `CREDITS.md`. Zakuro by fearkov (MIT; our patches in `patches/zakuro/`, notices in
`patches/zakuro/NOTICE.md`); 3dsrecomp by fearkov (no licence file; not included; fetched at a pin for your own
build); fe-awakening-recomp by Zelkin1 (MIT); facts from Paragon and mila by thane98 (GPL, read for facts only, never
copied), the fefates-tools wiki, SPICA, 3dbrew, Serenes Forest and the Fire Emblem Wiki. Grok (xAI) is the project's
creative lead. Fire Emblem Fates is by Nintendo and Intelligent Systems; this project is not made or endorsed by them.
Seal of Flames by Laz14 (https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0) is a separate fan mod, not included.
