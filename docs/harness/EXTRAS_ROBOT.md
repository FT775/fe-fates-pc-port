# Robot notes for the screen extras (tools/extras/extras_robot.py)

**In plain words.** The extras (docs/EXTRAS.md) are checked by running the same piece of a route
twice or more, once with everything off and once per switch, and comparing what the game did.
This page is how that tool works and what to watch for. Tags: **[high]** measured, **[med]** inferred.

## How a run differs from a plain robot run

- Same boot.exe, same capture library (original mode), same route and start save as
  `harness.py headless`; the folder constants of headless.py are pointed at
  `build/extras/robot/<session>/jobs/<run>/` (as parallel.py's worker does), and the pool, the job
  objects, the budget and the `%APPDATA%` before/after check are parallel.py's own, imported.
- A cheat file is written to the run's `data/cheats/0004000000179800.txt` (ZAKURO_DATA), with the
  run's switches on (`*citra_enabled`). Zakuro writes code words once a frame and makes the changed
  functions run in the interpreter; boot.log says so
  (`cheats changed the game's code, N functions run in the interpreter`) [high].
- `@FRAME` wraps each switch's lines in `4 06DCA88 <FRAME-16>` ... `D2000000 00000000`: the code
  runs only once GameTime's blank counter has passed that frame. The counter is the boot.exe frame
  minus 16 on every run measured [high]. Before that frame the runs are byte-identical.
- At each sample frame boot.exe dumps GameTime (0x006DCA84, 32 bytes), the battle world pointer
  (0x006BC2F8, BattleWorld::Get), both random generators (0x00752B7C), UnitPool, GameUserData and
  the first heap page; the top screen is kept as a 40x24 grey thumbnail to line runs up.
- At the save frame the savestate's FCRAM holds the whole linear heap (0x30000000 = FCRAM offset 0,
  checked against the dumped page every run [high]); the units of all forces are read from it.
  Words that point into the heap are masked before comparing: where the game put an object (a
  unit's map actor after a battle, Unit +0x120) moves when timing changes and is not game state.
- The in-game save files the route writes are hashed (Chapter0, Global ...): when a route saves,
  that is the cleanest "same game" test.

## Things that were learned the hard way

- The battle world pointer is also set during 3D story scenes (CutSceneMain makes a BattleWorld),
  so "battle" stretches include those. [high]
- Pressing a battle button before the battle's bottom screen is ready does nothing; the buttons
  appear about 220 frames after the battle starts (bt-ch2: by 10620 for a battle at 10392). [high]
- A switch that shortens battles, on from frame 0 of a whole route, breaks the route: later button
  presses land on other screens. Compare one battle with `@FRAME` and `--until` before the next
  press. 60 fps battles and 16:9 do replay whole routes (bt-ch2, bt-ch3) to the same save. [high]
- A sample every 2 frames over ~700 frames costs about 10 s per run (two PPMs per sample).

## Numbers (2026-11-12, this PC)

| Session | Runs | Wall | Peak per run |
|---|---|---|---|
| `check-extras` (5 variants, bt-ch2 to 11110) | 5 at once | 61 s | 355-362 MB |
| `final-ch3` (4 whole bt-ch3 routes) | 4 at once | about 4 minutes | about 360 MB |
| `ch2-full` (5 whole bt-ch2 routes) | 5 at once | about 3 minutes | about 360 MB |

`%APPDATA%\zakuro` and `%APPDATA%\3dsrecomp`: unchanged after every session.
