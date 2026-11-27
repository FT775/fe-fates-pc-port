# Screen and speed extras for Fates (roadmap step 7)

**In plain words.** Four switches you can turn on in Zakuro's Cheats window while you play:
smoother battles (60 pictures a second instead of 30, same speed), faster battle animations
(150% by default), a 16:9 picture for the 3D scenes, and a test switch for 60 fps story scenes.
They are small changes to the game's own code, found by reading this game's code (its function
names come from the game's own symbol map). All of them start **off**. Off is the original game.
Nothing is installed for you: the tool writes one cheat file into `build/extras/`, and you copy
it into Zakuro's cheats folder yourself (5 minutes, below).

**Update 2026-11-19 (F-041, docs/DEFAULTS_60FPS_3X.md).** The game program `play\game\Fire Emblem Fates.exe`
now has all four built in: Esc, Cheats, block **Enhancements** (same codes; off works at once). On a first run
with no Zakuro settings file, 60 fps battles and 16:9 top screen start **on** with the 16:9 top shape; an
existing settings file (yours) is never changed. The cheat file below is still how plain Zakuro gets them.

Status 2026-11-12. Checked headless with the test robot (docs/ROBOT.md) on two Birthright chapters;
not yet seen by the owner in a window. Tags: **[high]** measured by the robot or checked by a
script, **[med]** strong evidence, **[low]** a guess.

| Switch (name in Zakuro) | What you get | Game results | Evidence |
|---|---|---|---|
| **60 fps battles (Fates port extra)** | battles draw 60 pictures a second; the map already does | unchanged [high] | a battle lasts 666 vertical blanks instead of 682 (2.3% shorter); units, the game's random generator and the in-game save are byte-identical; two whole chapters replay to the same save |
| **Faster battles 150% (Fates port extra)** | battle animations at 150% (100 to 200 with `--speed`); fast-forward and pause still work | unchanged [high] | the same battle: 610 instead of 682 (150%), 580 (200%); fast-forward 562 instead of 604; units and random generator identical |
| **16:9 top screen (Fates port extra)** | the 3D map and battles drawn for a 16:9 screen (turn on Zakuro's 16:9 shape too) | unchanged [high] | battle lengths identical, two whole chapters replay to the same save; picture: `build/extras/wide_vs_off.png` |
| **60 fps story scenes (Fates port extra, test)** | 3D story scenes and the title at 60 fps | **changes the game's random values** [high] | scene length kept (1360 vs 1364), but the random generator and the units' hidden random values differ afterwards. Leave it off |

## 1. Five-minute owner check

1. Make the file (once, or after changing the speed):
   `python tools\extras\usa_extras.py build` (or `... build --speed 200`). It checks every
   changed word against your `extracted/code.bin` and writes
   `build\extras\cheats\0004000000179800.txt`, every switch off.
2. Start the game with `PLAY.bat`. Press **Esc**, then **Cheats**, then **Open the cheats folder**.
   Copy `0004000000179800.txt` into that folder. If a file of that name is already there, keep a
   copy of the old one first (this file replaces it). Back in the Cheats window press **Reload**.
3. Tick **60 fps battles** and **Faster battles 150%**. Load a save and start any fight. It should
   look smoother and play faster, and the hit numbers and HP should be what the forecast said.
   During the fight, hold **A** (or touch **>>**): faster still. Touch the pause button (or press **B**): it stops;
   touch the round middle button to go on.
4. For 16:9: Esc, **Settings for this game**, top screen shape **16:9**, then tick
   **16:9 top screen** in Cheats. The map and battles should look wider and not stretched (units
   keep their shape). Menus, faces and text are stretched a little: that is expected (section 4).
5. Turning a switch off: untick it, then **restart the game** (Zakuro keeps a player cheat's
   changes until the game restarts; a restart is the original game again).

Leave **60 fps story scenes (test)** off. If anything looks wrong, untick, restart, and tell me the
chapter and what you did.

## 2. 60 fps battles: how it was found [high]

The game has one clock for frame timing, `GameTime` at 0x006DCA84 (names from config/functions.csv):

- `TickVSync` 0x001063AC, the vertical-blank callback, counts blanks (+0x4).
- `Graphics::WaitVSync` 0x00106150 waits until at least *step-min* blanks (+0x10) have passed since
  the last game frame; `GameTime::Tick` stores the blanks that really passed, clamped to
  [min, max] (+0x10, +0x14), as the **step** (+0x18 = 0x006DCA9C).
- `SceneSystem::GetDeltaTime` 0x001A3858 and `BattleUnit::GetTimeRate` 0x0050527C scale animation by
  that step, and `ProcInst::RecursiveTick` subtracts it from process waits. So the game was written
  to run at a variable rate.
- `GameTime::ResetFrameStep(n)` 0x004EBB38 sets min = max = step = n. Callers with 1 (60 fps):
  `map::World::Setup`, the castle, movies. Callers with 2 (30 fps): `BattleSeq::Initialize`
  0x004FBB9C, `BattleUtil::BattleInitialize` 0x00193900 (class change, job intro),
  `CutSceneMain::CutSceneMain` 0x001AD9A4, `Title::Create` 0x00420F28.

The switch changes the two battle callers to 1. Alone that made a battle 20% shorter (542 instead
of 682 blanks): three battle clocks add a fixed amount per game frame, so at twice the frames they
ran twice as fast. Found by lining up the screens of the two runs (the robot's thumbnails):

| Clock | Where | Fix | Battle length after |
|---|---|---|---|
| - | only the two `mov r0, #2` -> `#1` | - | 542 (-20.5%) |
| hit-stop (freeze) and slow-motion periods | `TimeController::Tick` 0x001D5E08 and 0x001D5EAC, `freeze -= rate` | `bl` to 0x00610440: subtract rate x step / 2 | 576 (-15.5%) |
| battle zoom-in / zoom-out camera | `TransitionCamera::Tick` 0x001F1A80, `time += 1.0` | `bl` to 0x00610480: add step / 2 | **666 (-2.3%)** |

At 30 fps the step is 2, so step / 2 = 1 and the game is exactly as before; at 60 fps the
amount per frame is halved. The two small routines live in the spare bytes after the code
(.text ends 0x0061011C, its last page 0x00611000; all zero, checked by the tool). The 2.3% that is
left (2.5% on a boss fight) was not traced; it is about a quarter of a second per battle [med:
the screens line up within 4 frames through the fight and drift at the end].

What the robot saw (tools/extras/extras_robot.py, section 5):

| Run (bt-ch2: Corrin's Attack Stance battle, switch on from frame 10300) | Battle (blanks) | Game frames per blank | Units / random generator / save |
|---|---:|---:|---|
| all off | 682 | 0.5 | reference |
| 60 fps battles | 666 | **1.0** | same / same / same |
| bt-ch3 boss fight, from frame 21950, off / 60 fps | 1218 / 1188 | 0.5 / 1.0 | same / same / same |
| whole routes bt-ch2 (20,040 frames) and bt-ch3 (34,240) with 60 fps from the start | - | 1.0 in every battle | the in-game save the route writes at the end (Chapter0, Global) byte-identical to the run with everything off |

The map: already 60 fps in the original game (`map::World::Setup` passes 1); the robot measured
0.94-0.96 game frames per blank on the map in every run, with and without the switch.

Not the old double-speed cheat: that kind of code makes the game do one frame of work per blank
without telling the animation code, so everything plays twice as fast. Here the game is told the
truth (step 1), and its own scaling keeps the speed.

On a real 3DS (not our target) the battle might not reach 60 and would then slow down, because
min = max = 1. In Zakuro it holds 60 (every sample in every battle had step 1).

### Story scenes (test switch)

`CutSceneMain` and `Title::Create` also pass 2. The test switch passes 1. A story scene kept its
length (1360 vs 1364 blanks), but right after it the game's random generator differed (first at
frame 4532 of bt-ch2) and the units then had other hidden random values (Unit +0x20, +0xBC..+0xC7).
That is a real change of game state, so the switch is marked test and should stay off.

## 3. Faster battles [high]

`TimeController::Tick` 0x001D5CAC asks `TimerButtonController::GetSelected` which battle button is
held and sets the battle's time rate (+0x24): 2 slow motion (0.5), 3 pause (0), 4 fast (2.0),
anything else 1.0; `SceneSystem::SetTimeRate` then scales the battle animations. The buttons are
the touch buttons under a battle and keys read by `TimerButtonProc::Tick` 0x001E7840 (A held = fast,
Y held = slow, B = pause; checked by the robot below).

The patch rewrites the ten words that pick the rate (0x001D5D74..0x001D5D98). Normal becomes
`speed`/100, fast-forward twice that, slow motion keeps the game's own 0.5 (0x001D5F18) and pause
keeps 0. The block ends by storing the rate where the original's cases did (0x001D5DC0).

| Run (same battle, switch from frame 10300) | Battle (blanks) |
|---|---:|
| off / 150% / 200% | 682 / 610 / 580 |
| off + touch >> at 10640 / 150% + >> / 200% + >> | 604 / 562 / 544 |
| off + A held 6 frames at 10640 / 150% + A | 676 / 606 |
| off + pause / 150% + pause (touch pause at 10640, the middle button at 10760) | still running at 11110 in both (120 frames of pause added) |
| 60 fps + 150% + 16:9 together / + >> | 572 / 534 |

Units, random generator and saves were the same in every run. Only the animations are faster:
the zoom-in, zoom-out and the EXP bar keep their speed, which is why 150% shortens a whole battle
by about 11%, not 33%. The fixed speed is set when the file is built (`--speed 100..200`); a slider
would need a Zakuro build.

A whole chapter with faster battles from frame 0 does not replay the robot's button list (the
fights end earlier, so later presses land on other screens); that is a property of the scripted
test, not of the patch, so this switch is compared right after one battle.

## 4. 16:9 [high for the 3D, by design for the rest]

The top-screen projection is built in `ICamera::UpdateProj` 0x004DADD4 (the map camera reaches it
from `FieldCamera::UpdateProj`) and `ICamera::UpdateStereo` 0x004DB474, both with
`nn::math::MTX44PerspectiveRadC_FAST(out, fovy, aspect, near, far)`. The camera's aspect is 5:3
(400/240: `ICamera::ICamera`, `ICamera::Reset`, `CameraParam`). Both calls now go through a routine
at 0x00610400: when the aspect is exactly 5:3 it is multiplied by 16/15 (= 16:9), then the original
function runs. Other aspects (the bottom screen's 4:3, render targets) are left alone.

Zakuro's top screen shape 16:9 shows the 400x240 picture wider (crates/zakuro/src/settings.rs
`TopShape`: "games still draw it at the console's shape, so only turn this on with a widescreen
code"). With both, the 3D scene is wider and not stretched: `build/extras/wide_vs_off.png` puts the
original (left) beside the patched picture shown at 16:9 (right), map, a hit and a follow-up.

Not changed, and why:
- **2D** (menus, faces, text, the map's info boxes) is drawn with orthographic cameras
  (`ICamera::SetupOrtho` -> `SetParallax`); widening those would leave empty bars or move touch
  areas. They are stretched by 6.7%.
- **The 3D slider**: the console's stereo path (`nn::ulcd::CTR::StereoCamera::CalculateMatrices`,
  `MTX44FrustumC_FAST`) was not hooked. Zakuro runs with 3D off by default.
- **21:9**: the same routine with another factor (1.4) would do it; not offered.

## 5. The robot check

`tools/extras/extras_robot.py` (notes: [harness/EXTRAS_ROBOT.md](harness/EXTRAS_ROBOT.md)) runs a
route with and without switches, side by side through `tools/harness/parallel.py`'s pool (the
owner's budget: up to 6 runs, below-normal priority, 8 GB; each run peaked at about 360 MB).
The cheat file for a run is laid into that run's own scratch folder only; `%APPDATA%\zakuro` and
`%APPDATA%\3dsrecomp` were unchanged after every session (checked by the tool).

```bash
python tools/extras/extras_robot.py compare --route bt-ch2 --until 11110 --window 10380:11110:2 \
    --every 2000 --check --variant off --variant fps60@10300 --variant battle_speed@10300 \
    --variant wide@10300 --variant all=fps60,battle_speed,wide@10300      # about 1 minute
```

`@10300` switches the patch on only from that frame (a code-type-4 test on GameTime's blank
counter), so both runs are identical up to the battle and any difference is the patch's.
`--check` fails unless units, random generator and saves are the same, 60 fps battles run at one
game frame per blank and within 5% of the original length, faster battles are shorter, and 16:9
changes no length. Last run 2026-11-12: all met.

## 6. Where things are

| File | What |
|---|---|
| `config/extras/fe14.json` | every site: address, function, original instruction shape and SHA-1, our words and their expected disassembly (no original bytes) |
| `tools/extras/usa_extras.py` | `verify`, `build [--speed N]`; uses config/extras/fe14.json for Fates (the Awakening map stays for `--game fe13`) |
| `tools/extras/native.py` | the checks and the cheat file; `--selftest` |
| `tools/extras/extras_robot.py` | the robot comparison; `--selftest` |
| `build/extras/cheats/0004000000179800.txt` | the cheat file (gitignored), all off |
| `build/extras/fe14_map.csv` | every word with its original and new bytes and text (gitignored: holds code bytes) |
| `build/extras/robot/<session>/report.json` | robot results (gitignored) |

Public codes: the GBAtemp 60 fps thread (Foxes, 2026; docs/tracks/EXTRAS_FATES.md) was not opened
for this work and no code was copied; the sites above come from the symbol-map names and the
disassembly. Whether the public patch uses the same sites is unknown.

## 7. Open

- The last 2-3% of battle time at 60 fps (a quarter of a second per battle) is not traced.
- Not seen in a window by the owner yet; the frame interpolation in Zakuro's Graphics settings is
  a different, emulator-side way to smooth battles and should not be on together with this.
- Other battle kinds (critical cut-ins, skill banners, dual guard, dragon-vein effects) ran inside
  the two whole chapters with identical saves, but were not timed one by one.
- The story-scene switch changes random values; finding why (what consumes the random generator
  per frame in or right after a scene) would be the next step before it could be recommended.
