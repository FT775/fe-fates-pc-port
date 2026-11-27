# 60 fps battles, 3x and 16:9 as the shipped defaults (F-041 #1-3)

## Owner note (2 minutes)

The game program (`play\game\Fire Emblem Fates.exe`, what PLAY.bat starts) was rebuilt on 2026-11-19
with your OK ("do it"). On a **first run** (no Zakuro settings file yet) it now starts with:

- **60 fps battles on** (the proven extra; units, hidden random values and saves unchanged),
- **3D at 3x**, slider still 1x to 8x,
- **top screen 16:9 together with the 16:9 extra** (wider, not stretched),
- **faster battles off, 60 fps story scenes off** (story scenes change the hidden dice; leave it off).

**Your own setup does not change.** You already have `%APPDATA%\zakuro\settings.toml` (3D at 4x, top screen
5:3). The new program reads it as before and never replaces it, so you will not see the new defaults
unless you choose them yourself. Nothing of yours was written: no settings, saves, cheats or mods.

What is new for you anyway: the four Fates extras are now **built in**. Esc, **Cheats**, the top block
**Enhancements** lists them with a short note each. No cheat file to copy any more, and turning one off
works at once (no restart). To get the defaults yourself: tick **60 fps battles** and **16:9 top screen**
there, then Esc, **Settings for this game**, tick **Top screen shape** and pick **16:9**. Resolution is
under Settings (yours is 4x; 3x is the default).

To go back: copy `build\backup\Fire Emblem Fates.exe.2026-11-10` over `play\game\Fire Emblem Fates.exe`
(section 5).

## 1. How the shipped program gets its settings (the facts)

Read in `engine/zakuro` (our pin + patch series) and `tools/play/play.py`:

| What | Where it comes from |
|---|---|
| Zakuro settings (resolution, top shape, window scale, enhancements on) | `%APPDATA%\zakuro\settings.toml`, always: `settings.rs` `path()` uses `APPDATA` only. `--data` and PLAY's `portable_saves` move saves, mods and cheats, **not** the settings. There is no portable settings file next to the exe. |
| Missing settings file | `Settings::default()` (before this change): resolution 3, slider `1..=8` (`menus.rs` `resolution`), top shape 5:3, no enhancements. |
| Our extras (60 fps battles, 16:9, faster battles, story 60 fps) | Before: only a player cheat file the owner copies by hand into `<data>\cheats\0004000000179800.txt` (docs/EXTRAS.md section 1); on/off is the `*citra_enabled` line inside that file. |
| First save of settings | `lib.rs` writes the file on the first start, when `console_id` is 0 (a new file). An existing file with a console id is never rewritten on start. |

## 2. Why it needed the engine build

The no-build routes do not work:

- A portable `settings.toml` beside the exe is never read (no portable mode; path fixed to `%APPDATA%`).
- A first-run copy by PLAY would have to write `%APPDATA%\zakuro\settings.toml` and the cheats folder, which we
  never write, and would not cover a double-click on the exe.
- Pointing `APPDATA` at another folder for the game would also move the saves, so the owner's saves would vanish
  from the game. Not acceptable.

So: the smallest source change, as one more patch in our Zakuro series.

## 3. What changed

`patches/zakuro/0006-frontend-Fire-Emblem-Fates-first-run-starts-with-the.patch` (commit `052e21b` on the local
`fe14` branch of `engine/zakuro`; `engine.py apply` reports it as part of the series, "unchanged"):

1. `crates/zakuro-core/src/enhancements.txt`: a block for `0004000000179800`, build `rev0` (the clean dump's
   remaster version, read from `extracted/exheader.bin`), with our four extras. The codes are the same words
   `tools/extras/usa_extras.py build` writes (checked: all four blocks identical to the robot's cheat file, line for
   line). Only our own instruction words and addresses, already tracked in `config/extras/fe14.json`; no original
   bytes. A game with an update installed gets none of them (other build string).
2. `crates/zakuro-core/src/enhancements.rs`: the credit line for these says "Made by the Fates port from this game's
   own code (its docs/EXTRAS.md)" instead of the GBAtemp thread line the other enhancements carry. Test added.
3. `crates/zakuro/src/settings.rs`: `Settings::load()` returns `Settings::first_run()` only when the file is
   **not found**. `first_run()` = the defaults + for Fates its own top shape 16:9 + enhancements
   "60 fps battles (Fates port extra)" and "16:9 top screen (Fates port extra)". An existing file, even empty or
   unreadable, is handled exactly as before. Resolution stays the general default 3; the slider is unchanged. Test added.

Not changed: the extras' code, the game's code, PLAY, the owner's files, `play/config.json`.

Build: `python tools/engine/engine.py port`, below normal priority, 2026-11-19 23:27-23:29 (generated code up to date,
cargo 112 s). New exe: 143,605,760 bytes, SHA-256 `2736a85d...3d69`; `--help` same text as `cli.rs`; Cargo.lock
same crate versions as Zakuro's. The unit tests in the patch were **not run** (`cargo test` is a Zakuro build outside
the OK, which covered the standalone exe only).

## 4. How it was verified

All in test folders under `build/defaults/` with `APPDATA` and `LOCALAPPDATA` pointed there
(`build/defaults/run_fresh.py`, `build/defaults/win/drive_win.py`). The owner's `%APPDATA%\zakuro\settings.toml` was only
read (resolution 4, top shape console, a console id), never written.

| Check | Result |
|---|---|
| First run, headless 3,000 frames (`fresh1`) | Completed, 0 fatal errors. Log: "no settings ... yet, a first run"; "4 enhancements for this build, rev0, on: 60 fps battles (Fates port extra), 16:9 top screen (Fates port extra)"; "drawing ... at 3x"; "cheats changed the game's code, 6 functions run in the interpreter" (the recompiled code checks itself). New `settings.toml`: `resolution = 3`, general `top_shape = "console"`, `[per_game.0004000000179800] top_shape = "wide16x9"`, `[enhancements]` the two names. |
| Second run on that file | file byte-identical before and after (SHA-256 checked); same two enhancements on. |
| An existing owner-like file (resolution 4, console shape, console id, an Awakening entry; `existing`) | file byte-identical after the run; "on: none"; drawn at 4x. The defaults never land on an existing file. |
| Window, first run (`fresh5`) | Boots to the game's "must be initialized" and SD-card messages, then the opening, then **Main Menu** (`build/defaults/fresh5/shots/sheet_title.png`). The top screen is drawn 16:9 (window 1281 px wide at 150% Windows scaling = 427 x 2, not 400 x 2). |
| Zakuro's menus, first run | **Settings for this game**: Resolution 3x (slider 1x-8x), Top screen shape ticked, **16:9** (`shots/gamesettings2.png`). **Cheats > Enhancements**: 60 fps battles **on**, 16:9 top screen **on**, Faster battles 150% off, 60 fps story scenes (test) off, each with its note and the port's credit (`shots/cheats2.png`). |
| Replay, robot (bt-ch2 whole route, 20,040 frames, `defaults-r47`) off vs 60 fps battles + 16:9 from frame 0, same codes | **save files same** (format, Chapter0, Global), **units same**, **game random generator same**; battle 10700-14000 at 1.0 game frames per blank, step 1 (off: 0.702, step 2); map 1.0. `%APPDATA%` unchanged. The `--check` row failed only on a sampling artifact (a one-sample "battle" at frame 18000 has no rate with `--every 2000`); the rerun with the dense window is below. |
| Replay rerun, denser samples (`defaults-r47b`, 434 sample frames) | **save files same, units same, game random generator same**; `%APPDATA%` unchanged. Battles 2-7 at **1.0** game frames per blank, step 1 (off: 0.5, step 2). `--check` failed on the last battle (18000-19200): 0.917 per blank, steps [1, 2] (off 0.583), so part of its samples ran at step 2. Not explained yet; see section 6. |
| Robot check as in docs/EXTRAS.md section 5 (`defaults-r47c`: bt-ch2 to frame 11110, dense window 10380-11110 over the battle, `--check`) | **check: all met.** Battle 10392-11070: 678 blanks at **1.0** game frames per blank, step 1 (off: 682 at 0.5, step 2; -0.6%). Units, game random generator and save files the same; map 1.0; `%APPDATA%` unchanged. |

The robot runs boot.exe with the codes as a cheat file, not the exe itself (the exe has no route replay). The codes are
identical line for line, and in the exe they run through the same Zakuro cheat engine (built-in enhancements are
cheats marked built-in).

Clicks in the window: posted mouse messages were ignored, so three clicks used the real cursor on the game window
for well under a second each; the cursor and the window in front were put back afterwards.

## 5. How to undo

1. Close the game.
2. Copy `build\backup\Fire Emblem Fates.exe.2026-11-10` to `play\game\Fire Emblem Fates.exe` (SHA-256
   `19799f2d...c8ca`, the 2026-11-10 build). Its record is `build\backup\build-record.json.2026-11-10`.
3. Optional, to make a rebuild match: delete `patches/zakuro/0006-*.patch`, then `python tools/engine/engine.py apply`
   (resets `fe14` to the pin + 5 patches).

A `settings.toml` written by the new exe on a first run stays valid for the old one: the old exe has no Fates
enhancements, so the two names in `[enhancements]` are ignored; the 16:9 top shape stays until changed in
Settings for this game.

## 6. Open

- Rerun `defaults-r47b`: the rules that matter (saves, units, hidden random values) hold; the 60 fps rate check fails only for the last battle (0.917, not 1.0; some samples at step 2). Likely the battle's end or a menu inside the sample range, not checked. Same codes as the earlier proven extra, so this is a measuring question for the robot, not a change made by this build. Looked at the samples: the only step-2 sample in that stretch is frame 19200, a **black screen** right after the fight (battle flag still set, steps 1 before and after). That fits a fade or story-scene start, which stays at 30 by choice (story 60 fps is off, F-041 #2); not proven. The standard check (`defaults-r47c`) is all met.
- The patch's unit tests were not run (no Zakuro build OK beyond the exe).
- The owner has an existing settings file, so the defaults reach only new players / a new PC. Ticking the two
  enhancements and the 16:9 shape (owner note) gives the same result.
