# The plan now

**For the owner.** The game is a PC port. Finished means the options menu is on, then a short package, then the first randomizer. Not more chapters. Not a decomp. Not every screen.

Status 2026-11-20. Read: `docs/DECISIONS.md` F-040 and F-041. The 60 fps, 3x, and 16:9 defaults are already in a new first-run. Your existing settings file was not replaced. It still says 4x and 5:3. You tick those two boxes yourself. Do not overwrite that file.

One correction. The randomizer is not finished when the page exists. It is finished, for this promise, when a new game starts from a seed and plays those class and growth changes, and your normal game is untouched. Later slices are extras. Do not hold the package for them. The 0.917 battle measurement is a note, not a reason to rebuild. Seal of Flames stays not yet. It also has a code patch our recomp may not apply. Do not try it on the way.

## Left, in order

1. **Finish the options test.** Rerun the two routes that were cut off, headless, in their own folder. Claude. A few hours [low]. Do not restart the coverage replay.
2. **You say ok on the rule changes, then yes or no to the options menu in your game.** You. One line. If yes, Claude switches it on. Hours [low]. If no, the port is still playable. The menu waits.
3. **Package.** Shortcut, a one-page readme, the short modding guide. The two looks that were never seen stay out unless they are quick. Claude. About a day [low]. Do not reopen the 30-minute sitting as a gate.
4. **Randomizer slice 1, already running.** Class, growth, join stats. Children off. Robot boots one new game in its own folder and stops. Hours to a day [low]. Same seed, same result. Normal PLAY.bat unchanged.

Do not: replay chapters for coverage, schedule fuzz nights, start a decomp round, open a game window, or write your settings file.

## After slice 1

Items and shops, then skills, then enemy gear, then who joins. One at a time, only if you ask. Children, supports, and random maps last. The randomizer counts as done for this promise at the end of step 4. The later slices are a longer toy, not the finish line.

## How a round stays stopped

A round script has a wall-time cap and a stop file. If the stop file is there, it exits. It does not launch itself again. One script does not start a second copy of the same round.

Every test is headless and exits by itself. Its data folder and its APPDATA are both under `build/`. Zakuro still reads `%APPDATA%\zakuro\settings.toml` even when the game data is elsewhere, so APPDATA has to be the build folder too, or the test will see your settings and may open a window. If a window appears, that run is a failure and the script stops. It does not retry in a visible window.

## What you decide

1. After the two cut-off routes are clean, may the options menu be turned on in your game?
2. Is the randomizer done for now when slice 1 starts a new game, with later slices only if you ask?
3. Seal of Flames stays not yet?
