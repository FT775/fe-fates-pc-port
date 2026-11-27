# Randomizer track "growth": growth modes and bases modes (round 49, F-043 #2)

**For the owner.** Slice 1 already shuffled each person's growths and join stats while keeping their totals.
This track adds the choices the Sacred Stones port has: share the growth total out again with a bit of give
(Redistribute), nudge each growth (Delta), or roll every growth new between a low and a high limit (Full), plus
the same for the join stats (Redistribute or Delta). The default stays slice 1's way, so every seed made before
gives exactly the same files. Nothing counts as done until you say ok (F-037).

Module `tools/randomizer/growth.py`, tests `tests/test_rando_growth.py`. Our own code. The algorithms follow our
own FE8 port (`port/reforged/reforged_rando.c`, the sister project). The public Fates randomizers (GPL) were
used for facts only: per-person growth and base totals, scaled to the level of the join spot. No code was copied.

## 1. The options (same names and defaults as the FE8 port, docs/port/PLAYING.md "Randomizer")

| Option | Values (default in bold) | What it does |
|---|---|---|
| Growths | **slice1** / redistribute / delta / full | slice1: slice 1's own shuffle (same total; the default, no edits from this track). Redistribute: the total moves by up to Growth variance and is shared out again. Delta: each growth moves by up to Growth variance. Full: each growth is new, between Growth min and Growth max |
| Growth variance | 0-100, **30** | percentage points. Redistribute: how far the total moves. Delta: how far each growth moves |
| Growth min | 0-100, **5** | no randomized growth goes below this |
| Growth max | 0-125, **80** | no randomized growth goes above this (the game's cell is a signed byte; slice 1's guard allows 0-127) |
| Adjust HP growths | on / **off** | Redistribute: HP gets 4 of 11 picks instead of 2 of 9. Delta: HP never goes down. Full: an HP growth in the lower half is raised by half the range |
| Bases | **slice1** / redistribute / delta | Redistribute: the personal base total moves by up to the base variance, then is shared out again 1-3 points at a time. Delta: each personal base moves by up to the base variance |
| Base variance | 1-10, **5** | points |
| Scale to level | **on** / off | the base variance grows with the join level (below) |

Every growth this track writes is a multiple of 5, like all of the game's own (min is rounded up and max down to
a multiple of 5; a min/max pair with no multiple of 5 between them is refused). Bases always stay within the
person's new class: personal + class base between 0 (HP 1) and Job.max + the person's limit modifier, the same
caps slice 1 uses. Classes, class lines, weapon exp and carried items are slice 1's and are never touched here.

**Join level.** Fates' personal bases already include the levels a person joins with. The base variance is
scaled to that: join level = level + internal level, or level + 20 for a promoted class with no internal level;
variance used = base variance x (19 + join level) / 20, rounded. With the default 5: level 1 gets 5, level 11
gets 8, level 21 gets 10, Fuga (promoted, level 10) gets 12. Scale to level off: the plain base variance. This
is our own formula, written in the spoiler log per person.

Fates differences from the FE8 port, said plainly: 8 stats (Magic and Luck are ordinary stats here, so Luck is
not rolled apart as FE8 does); steps of 5 for every growth mode (FE8's Delta and Full use steps of 1); growth
max tops at 125 instead of 255.

## 2. How the track plugs in (for the integrate step)

```
edits, lines = growth.plan_growth(facts, run_seed, dict(opts, base_plan=slice1_plan))
plan = growth.apply_edits(slice1_plan, edits, opts)     # same object back when there are no edits
```

- `edits`: `{"table": "Person", "index", "label", "cell": "growth.hp" ... "base.res", "old", "new"}`, only cells
  that differ from the slice-1 plan. `lines`: spoiler lines (one header line, then per person old -> new with
  totals; bases also show the join level and the variance used).
- Own sub-seed: SHA-256 of (`rando-growth-v1`, run seed, `growth`), then one stream per (growths or bases,
  that part's option text, person). Slice 1's switches never move this track's draws, and the growths options
  never move the bases draws (tested). A `random.Random` may be passed instead of the seed text.
- `apply_edits` adds `plan["tracks"]["growth"] = {"tool", "opts"}` when it changes anything, so `rando.py check`
  can remake it once rando.py passes the options on.
- `growth.check_bounds(facts, plan, opts)`: this track's guard, recomputed from the plan and the original rows.
- **Needs a change in randolib's guard when integrating:** slice 1's `stats_within_caps` fails a person whose
  personal base total grew. Redistribute and Delta bases may raise the total by up to the variance (that is
  what the FE8 options mean), so with a bases mode on, that one line must give way to `check_bounds`. Every
  other line of that guard still holds (tested on the real tables).
- The page and rando.py flags are the integrate step's: suggested `--growths`, `--growth-variance`,
  `--growth-min`, `--growth-max`, `--adjust-hp`, `--bases`, `--base-variance`, `--scale-to-level`
  (`growth.py make` already takes these for host work).
- Corrin's two rows (male and female) are drawn separately, as slice 1 does.

## 3. Tests (`python -m unittest tests.test_rando_growth`, 10 tests, all pass)

| Test | What it proves |
|---|---|
| `test_default_is_slice1_byte_identical` | default options: no edits, the very same plan object, and the rendered files equal slice 1's byte for byte (50 seeds x 3 switch sets) |
| `test_each_mode_bounds_hold_over_50_seeds` | 13 option sets x 50 seeds: growths within min/max and multiples of 5; Redistribute total within the variance; Delta each growth within the variance; Adjust HP never lowers HP; bases within the class caps; Redistribute base total at most + variance; Delta each base within the variance; classes, weapon exp and items equal slice 1's |
| `test_full_spread_and_adjust_hp` | Full reaches both 5 and 80; Adjust HP raises HP |
| `test_same_seed_same_edits_other_seed_differs` | repeatable, and seeds differ |
| `test_own_sub_seed` | slice 1's switches do not move the growth draws; growths and bases streams are apart |
| `test_bad_options_refused`, `test_level_scaling`, `test_spoiler_and_render` | option checks, the level formula, the spoiler header and CSV shape |
| `test_real_default_byte_identical` (real tables) | default = slice 1 byte for byte for seeds `same`, `r47robot`, `x1` |
| `test_real_modes_bounds_and_slice1_guards` (real tables) | 13 option sets x 10 seeds: `check_bounds` empty; every slice-1 guard passes except the "total grew" line above with a bases mode on |

`tests.test_randomizer` (slice 1, 17 tests) still passes unchanged.

## 4. Robot check (round 49), in the robot's own test game only

2026-11-20. One robot job (`growth.py robot`, which runs slice 1's `robot_check.py` driver with its folders moved
to `build/rando49/growth/`), below-normal priority, headless (boot-server.exe, no window), 4 runs one after
another, 4 min 54 s in all. Results: `build/rando49/growth/robot/g49.json`, pictures
`build/rando49/growth/robot/shots/` (not tracked: game pictures). Not touched: %APPDATA%, %LOCALAPPDATA%, the
owner's saves, Zakuro settings, cheats, `mods/`, play/, build/oka, routes.json, markers.json. Real recorded
presses only; memory was only read.

**The mod.** `growth.py make --seed r49growth --growths full --adjust-hp on --bases redistribute --out
build/rando49/growth/mods`: slice 1 (default switches) plus ONLY this track. 2234 changed cells; slice-1 guards
all PASS except `stats_within_caps` "total grew" (expected, section 2); `growth_track_bounds` PASS. Installed
with `mods.py ... --zakuro-dir build/rando49/growth/zak install` (101 files). A second folder `zakoff` got the
same install and then `uninstall` (0 files left) for the off runs. After the job `zak` was uninstalled too
(0 files left).

| Run | Start save | Presses (route, up to frame) | Reads | Mod |
|---|---|---|---|---|
| mod-ch1 | new-game-empty | bt-prologue to 38810 | 38810 | installed |
| mod-ch2 | bt-ch1-clear | bt-ch2 to 5117 | 4800, 5117 | installed |
| off-ch1 | new-game-empty | bt-prologue to 38810 | 38810 | uninstalled (0 files) |
| off-ch2 | bt-ch1-clear | bt-ch2 to 5117 | 4800, 5117 | uninstalled (0 files) |

| Check | Result |
|---|---|
| All 49 people's Person rows in memory (class, class line, 8 bases, 8 growths, 8 weapon exp) equal the plan | **PASS, 0 mismatches** at all 3 mod reads (49 checked each) |
| Corrin on his first map | personal bases 2 1 3 0 0 3 2 0 = the plan (class Nohr Prince kept); growths in memory 70 45 80 30 65 80 60 80 = the plan (Full, Adjust HP) |
| Gunter on the Chapter 2 map (his first) | class Adventurer (slice 1), personal bases 7 3 0 3 4 0 3 0 = the plan (Redistribute, join level 8, variance 7); growths 65 30 5 45 20 50 40 60 = the plan |
| Felicia on the Chapter 2 map (her first) | class Berserker (slice 1), personal bases 3 0 6 4 5 0 0 2 = the plan; growths 50 25 65 40 30 10 80 20 = the plan |
| Off = original | off runs: the 49 rows equal the original tables, **0 mismatches** at all 3 reads; Corrin, Gunter and Felicia's unit stats equal round 47's no-mod run (rc-none) exactly at the same frames |

Said plainly:
- **The prologue presses stop fitting with this mod.** At frame 38810 the mod game was still on the prologue
  map (Takumi and the prologue's enemies in the unit list, Corrin at 20/22 HP), not on the Chapter 1 map as in
  round 47 and the off run. Corrin's new join stats (Skill and Speed lower, Strength, Magic and Defence higher) changed the recorded prologue fight.
  Corrin's first map is the prologue, so his read there is still his first-map read; the game ran normally.
  Recorded presses fit a randomized game only while nobody's stats matter.
- The whole-memory hash of the off runs was taken at frames 38810 and 5117; round 47's no-mod hashes were taken
  at 39000 and 5300, so the hashes cannot be compared. The off proof here is the 49 rows plus the unit stats
  above, not a hash.
- The Chapter 2 save was made in the original game, so Corrin's level-2 gains there come from the original
  growths; his personal bases, and Gunter and Felicia (who join there), come from the mod.
- Jakob is not in the unit lists at these frames; his row was checked in the Person table only (0 mismatches).

## 5. Not done here

- rando.py flags, the randomizer page and the guard change in section 2: the integrate step.
- "Class growths: transfer" (FE8 port option) is not in this track.
- Enemy growths, children and supports: not part of this track.
