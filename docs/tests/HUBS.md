# Hubs: where each screen visit can start (F-039 step 1b, round 45)

**For the owner.** A screen visit (F-039 step 2) is a short labelled run: load a save we already have, walk to one
screen, press each item once, leave, save, load. This page says, for every playable screen in
[SCREENS.md](SCREENS.md), which save we already have is closest, how many presses and frames it would take, and
where we have no save yet. It also lists what the watchdogs (step 3) can reuse from our tools.

Status 2026-11-19, host only. Nothing was run: no game, no robot, no build. Read: `config/harness/routes.json`
(119 routes), `build/harness/saves/` (77 packed saves), `config/harness/markers.json`, docs/ROBOT.md, docs/CHEATS.md,
docs/CASTLE.md, docs/harness/PARALLEL.md, docs/harness/SERVER.md, `config/functions.csv` (class names only),
`tools/harness/{parallel,headless,server,markers,offline,cheats}.py`, `tools/harness/robot/fastlook.py`.
Tags: **[high]** an existing route already reaches that screen from that save; **[med]** read in our notes or the
symbol names, no route yet; **[low]** a guess (press counts, frames, building lists not yet seen).

## The short answer

| | screens (SCREENS.md in-scope rows) |
|---|---|
| An existing route already opens the screen from a packed save (copy its presses, add "press each item, leave") | 16 |
| An existing save is the hub; the walk to the screen is new but short (castle Build, a menu item) | 13 (3 of them [low]: hot spring, mine / farm, castle difficulty change) |
| Needs a new hub. A labelled cheat poke can make it (F-019) | 2 (game over, S support / marriage) |
| Needs a new hub. Real play only (a chapter not yet played, or something not yet in any save) | 2 (challenge maps, fortune teller), both [low] |
| Owner question in SCREENS.md, no hub looked for | 1 (castle invasion aftermath) |

No visit may start a real-play route (F-019, F-039 #3). A visit's own save is never packed as a parent: visits are
named `visit-*` (a proposed prefix: step 2 decides), carry a label, and a visit that pokes is a `cheat-*` route with
its pokes declared like every cheat route (docs/CHEATS.md).

## How long a visit takes [low]

- **The load prefix is fixed.** Every packed in-game save loads with the same 8 presses
  (`300:A,700:A,1200:START,1500:START,2000:A,2400:A,2800:A,3200:A`): extra-data prompts, movie, title, Continue,
  slot 1. The game is then in the castle or the preparations at about frame 3,200 to 4,700 (bt-castle-shop 3,596,
  bt-ch8-support 3,600, bt-ch10 4,400, bt-ch20/bt-ch27 4,676 with slower press gaps).
- **Speed.** `title` (3,000 frames) took 4.8 s of boot.exe alone and 7.9 s with 3 side by side (PARALLEL.md 2).
  The planning bound `parallel.py run_timeout` uses is 0.006 s a frame at 6 lanes (original mode, measured plus
  margin), plus about 15 to 20 s of Python per run (hash the state, contact sheet). So a 10,000-frame visit is
  under about 80 s at 6 lanes, a 6,000-frame visit under about 55 s.
- **One visit = load prefix + walk + "each item once" + leave + save.** Most land at 6,000 to 12,000 frames and
  40 to 150 presses. The save-then-load half is a second short route from the visit's save: about 4,500 frames
  (like `opt-ch8-reload`, 38 presses).

## Hubs per screen

"Path" starts after the load prefix. Frames are the whole visit from frame 0, both halves (visit, reload) together.

### Castle

| Screen (SCREENS.md) | Nearest hub (packed save) | Path from the hub | Already seen by | Presses / frames [low] | Hub status |
|---|---|---|---|---|---|
| Armory / shop | `bt-ch6-clear` (first castle visit), `bt-castle-forge`, `bt-ch9-clear` | walk to the Dawn Armory door, Buy > a unit > item > Yes, Sell once, leave | `bt-ch6-castle` 30807/31056, `bt-castle-forge` buy [high] | 120 / 12,000 | have |
| Staff / rod store (MagicCardShop) | `bt-castle-shop` (Rod Shop, Birthright); `cq-ch10-clear` (Staff Store, Conquest) | walk to the door, Buy > Corrin > Vulnerary (as `bt-castle-shop` 7634/7932), Sell once, leave | `bt-castle-shop`, `cq-ch10` [high] | 130 / 10,500 | have |
| Lottery shop | `bt-castle-ore` | walk to the Lottery Shop, Dawn Lottery > Yes (free, once a day) | `bt-ch9-ore` 157201 [high] | 90 / 9,000 | have (one draw a day: the fixed clock means the same prize every time) |
| Smithy (forge) | `bt-castle-ore`, `bt-castle-forge` | Smithy > Forge, Carve Name, Erase Name, Ore Swap, each opened once | `bt-castle-forge`, `bt-ch9-ore` [high] | 110 / 10,000 | have |
| Building placement / arrange | `bt-ch8-clear` (2 DVP), `bt-ch9-clear` (1 DVP) | START > Buildings > Build > a building > place on a blue spot > Yes; also Move and Remove once | `bt-castle-forge`, `bt-ch9-ore` [high] | 60 / 7,000 | have |
| Accessory shop | `bt-ch9-clear` (1 DVP; "Accessory Shop" is on its build list) | Build > Accessory Shop, walk in, Buy / Sell / Wear, leave | build list seen in `bt-ch9-ore` [med] | 150 / 12,000 | have (build it in the visit) |
| Mess hall (dining) | `bt-ch9-clear` (Mess Hall on the build list) | Build > Mess Hall, walk in, eat once (pick a cook), leave | build list [med] | 150 / 12,000 | have (build it) [low: a meal may need food stock] |
| Arena | `bt-ch9-clear` (Arena on the build list) | Build > Arena, walk in, one bet, one fight | build list [med] | 200 / 14,000 | have (build it) |
| Prison | `bt-ch9-clear` (Prison on the build list) | Build > Prison, walk in, open its menu (empty: no captured unit) | build list [med] | 120 / 11,000 | have for the empty menu. A prisoner needs a Capture in a chapter: new play [low] |
| Private quarters (My Room) | any castle save (`bt-ch9-clear`) [low: the room is there from the start] | walk to it, open the room menu, leave. Invite / petting is Live2D: out (F-008) | none | 80 / 9,000 | have |
| Hot spring | a later Birthright castle save, `bt-ch19-clear` .. `bt-ch26-clear` [low] | Build > Hot Spring if listed, walk in, leave | none | 120 / 11,000 | probably have [low: not on the chapter-9 list; a later save's build list must be looked at] |
| Statue | `bt-ch9-clear` (statues on the build list) | Build > a statue, walk to it, look | build list [med] | 80 / 9,000 | have |
| Lilith's temple | `cq-ch15-clear` / `cq-ch16-clear` (Lilith's castle talk opens these) | walk to the temple, its menu, leave | `cq-ch15`, `cq-ch16` openings (Lilith's talk only) [med] | 100 / 10,000 | have [low: which saves have the temple menu] |
| Mine / farm / resources | a later castle save [low] | Build > the ore or food spring, collect once | none; `bt-ch9-ore` notes "the ore springs come later" | 120 / 11,000 | probably have in `bt-ch19-clear`+ [low] |
| Fortune teller | none known | | none | | **new hub, real play** [low: not seen on any build list yet] |
| Difficulty / mode change (castle) | any castle save | the castle menu or options item that lowers difficulty / switches to Casual, look and back out (B, never Yes) | none | 40 / 6,000 | have [low: where the game offers it; may only follow a game over] |
| Menus, unit list, shared building code | any castle save | START castle menu: each item once (Buildings, Units, Next Battle, Save, Options) | many routes [high] | 60 / 7,000 | have |

### Preparations, units, supports

| Screen | Nearest hub | Path | Already seen by | Presses / frames [low] | Hub status |
|---|---|---|---|---|---|
| Prep sub-menus (Select Units, Inventory, View Map, Equip Skills, Fight!, R Options) | `bt-ch8-support` (the save opens chapter 8's preparations at about 3,600) | each item once, B | `bt-ch8-support`, `bt-ch8-options`, `cheat-forge-katana` (Equip Skills), `cq-ch8` [high] | 80 / 7,500 | have |
| Trade / convoy / equip (prep) | `bt-ch8-support`, `bt-ch6-clear` | Inventory > Corrin > Items / Trade / Convoy (the pool, 31833) | `bt-ch6-castle` [high] | 60 / 7,000 | have |
| Reclass / promotion | `bt-ch10-clear` (Takumi and Saizo carry Master Seals, ROBOT.md 3e); `rv-ch26-clear` (a Heart Seal in the convoy, ROBOT.md rv-ch27 notes) | Inventory > Saizo > Items > Master Seal > Use > class > Yes; Heart Seal the same on the Revelation save | a Master Seal was used on the map in the Birthright Endgame tries (ROBOT.md 3w) [med]; the prep Use path is new | 60 / 7,500 | have |
| Unit status / lists | `bt-ch8-support` | map system menu > Units, each page (as `bt-ch8-options`) | `bt-ch8-options` [high] | 70 / 6,900 | have |
| Supports: talk, rank-up | `bt-ch8-support` (C ready); `bt-ch9-clear` (five ready); `bt-ch19-clear` (Felicia-Saizo A ready, played in `bt-ch20`) | Preparations > Support > pair > talk (START skips the talk; A reads it) | `bt-ch8-support`, `bt-ch10`, `bt-ch20` [high] | 60 / 8,000 | have (C, B, A) |
| Marriage / children / family | none: no route reached S | an S talk, the ring, the child's paralogue on the world map | none; `cheat-family` pokes a family record for the readers only | 80 / 9,000 | **new hub. Cheat poke possible:** raise one pair's support value (Unit +0x11C, rel.py) to "S ready" on a castle save (`bt-ch19-clear`: Felicia-Saizo already A), then Support > S talk. A `cheat-*` route; real play would need more paired chapters |
| Options / settings | `bt-ch8-support` | map system menu > Options, every line DOWN only (as `bt-ch8-options`) | `bt-ch8-options`, `opt-ch8-reload` [high] | 70 / 6,900 | have |
| Tutorials / guide | `bt-ch8-support` | map system menu > Guide, open each topic once | menu item seen (ROBOT.md 3d) [med] | 70 / 7,000 | have |

### Save, load, battle save, game over

| Screen | Nearest hub | Path | Already seen by | Presses / frames [low] | Hub status |
|---|---|---|---|---|---|
| Save, suspend and load (file menu, bookmark) | any castle save | castle Save > slot 1 > Yes, then title > Continue > slot 1; also slot 2 and copy / delete looked at, never Yes on delete | every chapter route saves [high]. A separate single-player suspend file was not found: the robot's battle save makes no suspend copy, that copy is Versus only (OPTIONS_WIRING round 38) [med] | 50 / 5,000 + reload 4,500 | have. Whether Fates has a single-player "bookmark" at all (Classic mode?) is a SCREENS.md question [low] |
| Mid-battle save and resume | `bt-ch8-support` | `opt-t5-bsave-base`'s input (chapter 8 player phase 4,470, system menu > Save, battle save at about 5,100), then `opt-ch8-reload`-style reload (title > Continue > battle save > slot 1, map at 3,100) | `opt-ch8-set` + `opt-ch8-reload`, `opt-t5-bsave-*` [high] | 80 / 5,300 + reload 4,500 | have. Note `opt-ch8-set` changes options: use the bsave-base path for a plain visit |
| Game over | none: no route ever lost Corrin (0 hits in ROBOT.md and every report) | chapter 8 turn 1 from `bt-ch8-support`, Corrin left in enemy reach, End; the game-over screen (`title::ProcGameOver`, `map::Sequence ... GameOver`), then its continue / title choice | none | real play: unknown turns. With a poke: about 60 / 7,000 | **new hub. Cheat poke possible:** at 4,470 set Corrin's HP to 1 (a declared poke through the readable unit layout, expected old value checked), End turn. A `cheat-*` visit: allowed, labelled, never a parent. F-039 says press a difficulty rather than poke it; it says nothing against an HP poke. Real-play alternative: walk Corrin into the boss on a later map [low] |

### Title, new game, world map, extras

| Screen | Nearest hub | Path | Already seen by | Presses / frames [low] | Hub status |
|---|---|---|---|---|---|
| Title / new game / difficulty / mode | `new-game-empty` | `new-game`'s presses (title 2,100, New Game 3,000, difficulty 3,400, mode 3,700); visit: DOWN once on the difficulty list (Hard), DOWN twice (Lunatic), on the mode list UP (Phoenix) and DOWN (Classic), each A then B back | `title`, `new-game`, `opt-t4-newgame` (Normal, Casual only) [high] | 20 / 5,000 each | have. Pressing, not poking (F-039) |
| Avatar creation | `new-game-empty` | `bt-prologue`'s first part; visit every creator page once instead of START to OK | `bt-prologue` (defaults only) [high] | 80 / 8,000 | have |
| Support log / Extras (museum, music, support viewer) | `bt-ch26-clear` (the latest real-play save: most unlocked); `new-game-empty` shows Extras too (main menu at 3,300) | title > DOWN to Extras > each item once, B. Movie playback is out (F-008) | the menu item only (`new-game` 3,300) [high] | 60 / 6,000 | have |
| Chapter flow / world map | any castle save, e.g. `bt-ch9-clear` | START butler > Next Battle (DOWN x4) > world map: move over each entry, B. "Paralogue 1" is listed since chapter 9 (ROBOT.md 3e) | every chapter route [high] | 40 / 6,000 | have |
| Challenge / invasion maps | none known | | not seen in any route note [low]. The "Dragon's Gate" notice at chapter 7 is most likely the DLC gate: out (F-039 #2) [med] | | **new hub, real play** [low: if the world map offers challenges on a later Birthright or Revelation save, that save is the hub and only the entry + preparations are a visit] |
| Castle invasion aftermath | | | | | owner question in SCREENS.md; no hub looked for |

### Battle map rows

SCREENS.md's battle-map rows (commands, trade / items in battle, gimmicks, pair up, AI, battle scene, event
commands, event runtime) are reached by playing chapters, not by a menu visit. Their hubs are the 77 packed
chapter saves and the existing routes; the weekly replay (layer 1) covers them. Short visits that help: map
Trade / Items / Convoy from `bt-ch8-support` turn 1 (`bt-ch8-pair`'s opening, 4,470) [high]; Switch / Separate
(`bt-ch8-pair`) [high]. Gimmicks not met need the chapter that has them (SCREENS.md lists which).

### Faster starts (look-ahead only, never for kept visits)

`build/harness/robot/states/` holds 740 look-ahead savestates (212 under `bt/`, for example `b10prep`, `b10sup`,
`b10t1`) and `build/speed/*` holds fastlook chains. A server (`server.py load_file`) can start a try from one in
about 1 s instead of replaying the load prefix. They are scratch: a state is tied to the boot.exe and library it was
made with, and a kept visit must replay from frame 0 of a packed save (as every route does). Use them to find the
presses; record the visit from the zip.

## What the watchdogs can reuse (F-039 step 3)

| Watchdog | What exists | Where | What is missing |
|---|---|---|---|
| **Crash** | boot.exe's exit code and outcome line in each run's run.json (`exit_code`, `outcome`); `parallel.py` marks a run not ok, keeps boot and worker logs of failed runs under the session's `logs/`; the server replies `@@zs err outcome ...` | headless.py `run` (about line 684-693), parallel.py `finish` / `collect`, server.py `_reply` | nothing: a visit run through `parallel.py runs` is already judged |
| **Hang (the process stops answering)** | per-run wall limit scaled by route length (`run_timeout`: 120 s + frames x 0.006 s at 6 lanes, floor 900 s), whole process tree killed by a job object; server steps carry their own timeout and the client kills a silent server | parallel.py `run_timeout`, `Pool.run` (kill "timeout"), server.py `cmd(timeout=)`; fastlook `clean_timeout` | a lower limit for short visits (900 s floor is long for a 6,000-frame visit; `--timeout` already overrides it) |
| **Stuck frame (the game runs but the screen never changes)** | frame dumps at chosen frames (`ZAKURO_DUMP_AT`, the PNGs the contact sheet is made from); `server.shot()`; screen markers per shot: the current main-sequence process and every live process class (markers.py, run.json `markers`), and `markers.check` against expected classes (markers.json `checkpoints`) | headless.py `contact_sheet`, server.py `shot` / `markers`, markers.py | **no picture hash exists yet.** Needed: hash each dumped frame's pixels; call it stuck when the picture hash AND the markers' current process stay the same over K presses that should change the screen. A still menu waiting for input is not stuck, so the check must follow presses, not time. Caution: a screenshot writes the GPU picture back into guest memory (server.py `prove`), so a run with extra shots can end on a different memory hash than one without; compare runs with the same shots |
| **"Did the visit return"** | markers' current process at the last shot (back to `castle__Sequence`, the preparations, or the map player phase); `fastlook.screen_of` | markers.py, fastlook.py | a per-visit expected end screen in markers.json `checkpoints` (the existing mechanism, new keys) |
| **Save then load** | the game's own save files: `headless.pack_save`, `save_fingerprint` (sha256 of the save members), fastlook `disk_digest` (names + bytes of the scratch save folder); named game-state facts at every marker frame (`markers.game_state`: difficulty, mode, route, gold, units, supports...); the opt-ch8-set / opt-ch8-reload pair and the opt-t5 base/file routes are the pattern | headless.py, fastlook.py, markers.json `state` | A full memory hash after a load will never equal the hash before the save (another screen, another heap layout), so "save->load memory hash" should mean: (1) save, load, save again: the second save's files equal the first byte for byte (round 8 already compared in-game save files this way), and (2) the `markers.game_state` facts read after the load equal those read before the save. Both use existing code; a small compare script is the new part |
| **Same game twice (determinism)** | `parallel.py determinism --copies 2` (one memory hash for all copies); `server.py prove` / `prove_roundtrip` (emulator savestate round trips give the original's hash and instruction count) | parallel.py, server.py | nothing for visits; run once per new visit, not nightly |
| **No writes outside build/** | `parallel.py` snapshots `%APPDATA%\zakuro` and `%APPDATA%\3dsrecomp` before and after every session | parallel.py `appdata_dirs` / `snapshot_diff` | nothing |
| **Cheat and options rules** | `cheats.py` (declared pokes, expected old value, cheat mark on packed saves, refusal of cheat saves as real-play parents); `options_track.py` (an options save never starts a route without "options") | cheats.py, options_track.py, headless `check_start_save` | nothing: visit routes go through the same `load_routes` checks |
| **offline.py** | re-judges capture records without playing when only readable code changed | offline.py | not a watchdog: it decides capture verdicts, not crashes or hangs. Useful only if a visit is captured |

## Open points for step 2

1. Hot spring, mine / farm springs, fortune teller: open the Build list on `bt-ch19-clear` .. `bt-ch26-clear`
   once (one short look route) to see which are offered. [low]
2. Challenge maps: look at the world-map list on a late Birthright and a late Revelation save. [low]
3. Bookmark: does Fates have a single-player suspend (Classic?) beside the battle save? A SCREENS.md / code question.
4. Two cheat visits need the owner's usual cheat-track rules only (F-019): game over (Corrin HP 1) and an S support
   (one pair's support value). Each is a `cheat-*` route with declared pokes; neither save may parent real play.
5. A visit that builds a castle building spends a Dragon Vein point in the visit's own copy only; the packed hub
   save is never changed (routes copy the zip).

## Counted time (F-027)

Step 1b: cap 50 min; used about 45 min, host only. Step 2 at the rates above [low]: 29 visits that have a hub,
about 3 to 6 an evening to find and record (look-ahead with fastlook, then two copies), so 5 to 9 evenings; the two
cheat visits one more evening; the two real-play hubs are not counted (they may be out of reach without new chapters).
