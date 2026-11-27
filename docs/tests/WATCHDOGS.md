# Watchdogs for short robot runs (F-039 step 3, round 46)

Tool: `tools/harness/watchdog.py`. Tests: `tools/harness/test_watchdog.py` (check_all row `watchdog-tests`, fast,
no game). Allow-list: `config/harness/watchdog.json`. Nothing here counts as done until the owner says ok (F-037).

## What it does

It runs boot.exe on one existing route and watches the run while it goes. Every 30 frames boot.exe writes both
screens and the game's own data+bss block (0x006B4000, 0xC9000 bytes, from the segments in `config/game.json`).
The watchdog hashes each sample as soon as it appears, then deletes the files. Each watchdog gives a one-line
verdict, and the verdict names the press: the route's button entries, counted from 1, for example
`press 9 of 12 (frame 1840 SELECT)`.

| Watchdog | Fires when | Press named |
|---|---|---|
| crash | boot.exe ends early: an exit code other than 0, an outcome other than Completed, fewer frames than asked for, or a panic line in its log | the last press before the last frame |
| hang | no new frame for 120 s of wall time (`--hang-s`), or the game's data+bss does not change for 600 frames (frames keep coming but the game does not move) | the last press before the hang |
| stuck | no new picture for 600 frames while at least 3 presses went in. A loop of the same few pictures, such as a blinking cursor, counts as no new picture. Screens that are meant to be static go in the allow-list | the first press into the unchanged screen |
| softlock | 6 presses in a row, over at least 600 frames, change nothing in the game's data+bss except its own tickers. Tickers are 256-byte blocks that changed in at least half of the last 16 stretches with no press: timers, ring buffers, animations | the first press that had no effect |
| roundtrip | a savestate taken at the route's save frame (its hub) is loaded by a second boot.exe and saved again straight away. The guest memory (FCRAM, VRAM, DSP RAM, AXI WRAM) must match byte for byte, and the metadata must pass headless.py's h4a rule | the last press before the save frame |

Allow-list (`static_ok`): each entry gives a route plus a frame range, or a picture hash, and a `why`. An entry
with no `why` is refused. An entry only excuses a stuck frame. It never excuses a crash, a hang or a soft-lock.
The list is empty today: none of the three clean routes needed an entry.

Limits and safety: boot.exe runs below normal priority with no window. Every file goes below
`build/watchdog/<session>/`: the copied start save, the data and tmp folders, the APPDATA and LOCALAPPDATA copies,
and the results. Each run's folder is deleted once its result is written. Only `results/*.json`, verdict
pictures (`*.png`) and `summary.json` are kept (260 KB in total). Cheat routes and options routes are refused.
So are cheat saves and options saves as start saves. If the build drive has less than 8 GB free, the live
self-test stops before it starts and skips any run still waiting. The %APPDATA% folders are checked before and
after each run (parallel.py snapshot).

## Commands

    python tools/harness/watchdog.py --selftest                 # 21 checks on made-up samples, no game
    python tools/harness/test_watchdog.py                       # 12 unit tests, no game (check_all: watchdog-tests)
    python tools/harness/watchdog.py run --route title --roundtrip
    FEF_ROBOT_JOBS=2 python tools/harness/watchdog.py live-selftest --jobs 2   # the 8 rows below

## Self-test result (2026-11-19, 2 robot jobs side by side, about 2 min 45 s of wall time)

`build/watchdog/live-final.log`, `build/watchdog/selftest/summary.json`: **8/8 as expected, %APPDATA% untouched.**

| Row | Fault planted | Verdict |
|---|---|---|
| clean-title | none | CLEAN: 3000 frames, 103 samples, all 5 presses. ROUNDTRIP OK at frame 2990, memory c3cbbe489525 both times |
| clean-new-game | none | CLEAN: 4600 frames, 154 samples, all 9 presses. ROUNDTRIP OK at frame 4590, memory d328d6712726 |
| clean-bt-ch8-pair | none | CLEAN: 9800 frames, 330 samples, all 51 presses. ROUNDTRIP OK at frame 9790, memory 047fe5711706 |
| plant-kill | boot.exe killed after the frame 1500 sample | CRASH: boot.exe stopped early (exit code 1, outcome none; last sample frame 1530); at frame 1530, press 3 of 5 (frame 1200 A) |
| plant-pause | boot.exe suspended (NtSuspendProcess) after the frame 1500 sample; hang limit 15 s for the test | HANG: no new frame for 15 s of wall time after frame 1500; at frame 1500, press 3 of 5 (frame 1200 A) |
| plant-static | new-game cut at frame 1000, then 10 SELECT presses 120 frames apart on the main menu (only the stuck watchdog on) | STUCK: no new picture for 600 frames (last 7cd89126a0dc) while 4 presses went in; at frame 2430, press 9 of 12 (frame 1840 SELECT) |
| plant-softlock | the same cut, with 18 SELECT presses (stuck watchdog off) | SOFTLOCK: 6 presses in 630 frames changed nothing in the game's data+bss beyond its tickers; at frame 2220, press 7 of 20 (frame 1600 SELECT) |
| plant-corrupt | title savestate at frame 2990; byte 0x100000 of FCRAM flipped in the copy that is loaded again (robot data only) | ROUNDTRIP: guest memory DIFFERS (fcram); press 5 of 5 (frame 2100 START) |

The memory hashes of the three clean routes are the same ones the earlier h4a runs recorded (title c3cbbe489525,
new-game d328d6712726, bt-ch8-pair 047fe5711706). So taking samples does not change the run. The verdict picture
for each planted fault is `build/watchdog/selftest/results/plant-*.png`. The static plant ends on the Main Menu,
with the New Game cursor pulsing.

Both watchdogs catch the static-screen fault. With both on (third try), the soft-lock fired first at frame 2220
and the stuck frame would have fired at 2430. In the final rows each plant runs with only its own watchdog on.

## What is not proven yet (honest limits)

- Hang by "the game's data+bss does not change" is tested only on made-up samples. Freezing the guest while frames
  still run would need an engine change, and no engine build was approved. Freezing the whole process is tested
  live (plant-pause).
- The soft-lock rule was tuned on one screen. On the main menu, the first version (per byte, then per word) missed
  the fault: ring buffers write a new slot every sample. Comparing 256-byte blocks fixed it, with 78 of 3216 blocks
  ticking on that screen. It gave no false alarm on the 3 clean routes (64 presses). Longer routes may still need
  allow-list entries or a tuned limit. Any entry has to be looked at first.
- The round trip is a savestate round trip (memory hash equal), not an in-game save slot. The in-game save then
  load check stays with the screen visits (F-039 item 1).
- The cost of watching is not measured cleanly yet. bt-ch8-pair took 119 s watched (with 2 jobs, while about 11
  other boot.exe runs from the other tracks were going), against 16-17 s for the plain h4a runs on a quiet
  machine. The dumps every 30 frames (about 1.3 MB each) are part of that; `--every` can be raised.
