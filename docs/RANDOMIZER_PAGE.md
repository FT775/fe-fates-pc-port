# Randomized games: the "New randomized game" page

**For the owner.** A randomized game is a game of its own. It has its own saves and its own mods, in its own folder. Your normal PLAY.bat, your normal save and your normal mods are not used and not changed. Delete the folder and that randomized game is gone. The original game was never changed.

Status 2026-11-19 (round 47, F-041 #4). Built: the page (a small menu), the profile folder, the start. No engine, Zakuro or cargo build. The randomizer itself (tools/randomizer/rando.py, written by another helper at the same time) arrived during this round, and the page now calls it (`make`). If it is ever missing when you make a game, the game gets a **stub**: it plays the original tables, and the page says so each time you start it.

**Round 50 (F-044 addendum, 2026-11-20).** The main way will be the **Randomizer** page inside the game, right after
you pick Casual / Classic in a New Game (docs/RANDOMIZER_INGAME.md). That page is not built yet (round 51). Until it
is, this menu is how you play a randomized game, and afterwards it stays as the fallback: it works without the new
program, with the program you have now. Nothing on this page changed in round 50.

**Round 51 (2026-11-20).** The in-game page is now built into the program PLAY.bat starts (docs/RANDOMIZER_INGAME.md
section 12); it waits for your look. This menu did not change and stays as the fallback. A randomized profile made here
has its mod laid at boot, so the in-game page's guard is meant to see changed tables and refuse, and the two never
stack (by design; not tried in a robot run). One finding on this side: in a robot run of an installed randomized mod,
one internal label (`033_MyCastleDefense`) read as `033_MyCastleeeeeeee` in memory although the file on disk is right;
it looks like the mods tool's compression and the game's decompression disagree on one spot, not the randomizer.
What that label does in play is not checked. Not fixed yet.

**Round W1 (2026-11-20).** More options in this menu: spread classes evenly, random promotions and Heart Seal
classes, **children** (now built; they moved from the switches to More options), class growth rates and base stats,
class movement, weapon stats and special powers, stronger enemy weapons, enemies grow faster, enemy levels, tougher
bosses and enemy drops (docs/RANDOMIZER.md section 10). All off unless you pick them; `a` (everything on) turns on the
suggested values (Nuzlocke is never part of it). Enemy levels and tougher bosses work here but are grey on the in-game
page until the next engine round.

## Steps

1. Double-click **PLAY RANDOMIZED.bat** in the project folder (next to PLAY.bat).
2. Type **1** (New randomized game) and press Enter.
3. **Seed:** type one (letters, digits, `-` or `_`, up to 32), or just press Enter and it makes one, for example `K7QXM2HRTA`. The same seed and the same switches give the same game. You can send the seed to someone.
4. **Switches:** Classes, Growths, Join stats. Press Enter for yes, or type `n` for no. Children are under More options (round W1).
   **More options** (round 49): press Enter for none (randomized as before), type `a` for everything on with the suggested values (Growths and Bases Redistribute, personal skills shuffled, class skills follow the new class, starting items, shops, castle rewards, enemy weapons, enemy and boss classes), or `c` to choose each row (Enter keeps that row's default). The rows are those of docs/RANDOMIZER.md section 6.
5. It makes the folder, runs the randomizer into that folder's mods, and starts the game. In the game, pick **New Game** on an empty file.

Next time:

1. Double-click **PLAY RANDOMIZED.bat**.
2. Type **2** (Continue randomized game). It lists your randomized games by seed, with the switches, whether it is a stub, and whether it has a save.
3. Type the number or the seed. It starts that game with its own save.

Type **3** to only see the list. `PLAY RANDOMIZED.bat --dry-run` checks everything and starts nothing.

Your normal game: **PLAY.bat**, exactly as before.

## Where things are

```
play\randomizer\<seed>\
    profile.json     the seed, the switches, when it was made, whether the mod is a stub
    randomizer.log   what the randomizer printed
    mod\Rando-<seed>\  the randomizer's mod folder: spreadsheets, plan.json, spoiler.txt (SPOILERS: who became what)
    stage\           the mods tool's work folder
    data\            this game's own Zakuro folder
        user\        this game's saves only
        mods\0004000000179800\   the randomizer's mod, nothing else
        cheats\      empty
    backups\         a zip of this game's save before each start (the last 10)
```

`play\` is your play area in the project folder. It is not %APPDATA%. Nothing of it goes into git.

## Why a separate folder

Zakuro reads one mods folder per data folder. So a mod "for that save only" needs a data folder of its own. The page starts the game with `--data` pointing at `play\randomizer\<seed>\data` and `ZAKURO_DATA` set to the same folder, the way the test robot runs its own copies. Your other mods are never copied in, so nothing mixes.

## What stays shared

- Zakuro's own settings (window size, picture scale, keys). Zakuro keeps them in %APPDATA%\zakuro\settings.toml whatever the data folder is. That is the same as normal play. The page never writes that file.
- The ROM and the program (play\game\Fire Emblem Fates.exe, or Zakuro). The same checks as PLAY.bat run first: ROM, recompiled code, update files beside the ROM, and "already running".

## Rules it keeps

- It never writes %APPDATA%\zakuro, play\data or your mods\ workspace. A test proves it (below).
- It never reuses a seed: "New" on a seed that exists stops and sends you to Continue.
- If the randomizer stops with an error, nothing is left behind and nothing starts.
- Any `--data` in your own `zakuro_args` (play\config.json) is dropped for a randomized game, so it cannot point back at your normal save.

## Tests (2026-11-19)

- `python -m unittest tests.test_rando_profile`: 9 tests, all pass (and `tests.test_play`, PLAY's own 52, still pass). Fake folders only. They check the folder layout, the stub, two fake randomizer command lines (plain flags, and the real one's `make` subcommand with `--out`), seed rules, no reused seed, a failed randomizer leaving nothing, the profile's own backups, the guard against the normal save places, and that PLAY.bat's dry run is unchanged. Each test also checks that a fake normal %APPDATA%\zakuro (a save, a mod, settings) and a fake play\data are byte-for-byte the same afterwards.
- Real places, read only: a SHA-256 snapshot of %APPDATA%\zakuro (15 files), play\ (2 files; play\game left out) and mods\ (1 file) before and after all the smoke runs: 0 files changed. No play\randomizer folder was made.
- Smoke start in a build copy (build\rando_page\play, not play\): a profile `SMOKE1` made by the page there (stub mod, the randomizer was not written yet). The test robot (headless, below normal, one job) booted a copy of its data folder with the empty start save and pressed the verified `title` route's buttons: frame 2990 shows the title screen ("PRESS ANY BUTTON"), boot 1.0 s, its mods folder held only the stub file. The page's own start was also run from the build copy (APPDATA/LOCALAPPDATA pointed at build\rando_page\): Zakuro's log says it used that profile's mods folder and formatted a new save inside `SMOKE1\data\user`. Those starts opened a game window; that is not done again (owner rule 2026-11-19: test starts are headless only). Honest note: the windowed starts from the page ended by themselves after 10 to 46 seconds, exit code 1 or -1, with no error in Zakuro's log and no crash in Windows' log; one start of the same program with the same arguments through PowerShell stayed up 70 seconds until the test stopped it. Another helper was rebuilding and running play\game\Fire Emblem Fates.exe at the same time, so the windows were most likely closed from outside; that is not proven.
- Second smoke with the REAL randomizer: profile `SMOKE2` made by the page in the build copy (classes, growths, join stats on; 14 s; the mods tool installed GameData.bin.lz and the Dispos files into `SMOKE2\data\mods\0004000000179800`). The robot booted a copy of that data folder the same way: frame 2990 is the title screen again, and the memory hash at frame 2990 differs from the stub run's (the changed tables are loaded). Not yet seen: a randomized unit on a map (that is the randomizer's own check).

## For the randomizer's writer: the command line this page calls

The page looks for `tools\randomizer\randomizer.py` (or `rando.py`, `cli.py`, `__main__.py`), reads its `--help`, and uses only the flags it finds:

- `--seed SEED` (required, or the profile is a stub)
- `--classes on|off`, `--growths on|off`, `--join-stats on|off` (or `--no-classes` and the like); `--children on` only when asked (round W1: an option, no longer always sent as off)
- round 49's options, only those not at their default: `--growth-mode`, `--growth-variance`, `--growth-min`, `--growth-max`, `--adjust-hp`, `--bases-mode`, `--base-variance`, `--scale-to-level`, `--personal-skills`, `--skill-slots`, `--starting-items`, `--shops`, `--shop-sides`, `--rewards`, `--enemy-weapons`, `--enemy-classes`, `--boss-classes`, `--enemy-trees` (values as in docs/RANDOMIZER.md section 6), and round W1's `--assign-evenly`, `--promotions`, `--promotion-sides`, `--reclass`, `--children`, `--class-growths`, `--class-growth-variance`, `--class-bases`, `--class-base-variance`, `--class-move`, `--weapon-stats`, `--weapon-traits`, `--wild-traits`, `--enemy-upgrade`, `--upgrade-rank`, `--enemy-growths`, `--enemy-buff`, `--enemy-levels`, `--boss-stats`, `--boss-max-boost`, `--boss-variance`, `--enemy-drops` (docs/RANDOMIZER.md section 10). If the randomizer's help lacks one that was asked for, the page stops instead of making a different game. The same flags work on the page's own command line: `python tools/play/rando.py new --seed S --growth-mode full --enemy-classes on`. profile.json keeps them under `options`; the list shows the ones that are not default.
- where to write, the first one found: `--zakuro-dir DATA` (the profile's data folder, as tools\mods\mods.py takes it), `--data-dir DATA`, `--mods-out MODS`, `--out MODS` (MODS = `DATA\mods\0004000000179800`)
- a subcommand `generate`, `make`, `build` or `new` if the help shows one in `{...}`

Today that gives: `python tools\randomizer\rando.py make --seed S --classes on --growths on --join-stats on --zakuro-dir <profile>\data --out <profile>\mod` (plus any option not at its default). Exit 0 is success. Anything else stops the page and removes the half-made profile. The page runs it from the project folder with ZAKURO_DATA removed from its environment.

## Not done here

- The in-game page: F-044 (2026-11-20) gave the OK for the Zakuro build it needs. Design and round-50 parts: docs/RANDOMIZER_INGAME.md. The page itself is round 51; this menu stays as the fallback.
- Items, skills and enemy gear arrived in round 49 (above); joins come later.
