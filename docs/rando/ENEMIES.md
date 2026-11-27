# Randomizer track "enemies": enemy and boss gear, optional enemy and boss classes

**For the owner.** With this track, enemies carry different weapons, and if you switch it on, enemies and bosses get
different classes too. The number of enemies, where they stand, their levels, their AI, when reinforcements arrive and
what they drop all stay the same. Story units are never changed. Neither are the four chapters where the public
randomizers broke (Conquest 9, Conquest 16, Revelation 8, Revelation 13). A new class has to get around the map
almost as well as the old one. Status 2026-11-20, round 49 (F-043 #1). Our own code. Public randomizers were read for
facts only. Nothing counts as done until you say ok (F-037).

## 1. How to run it

```
python tools/randomizer/enemies.py make --seed S [--gear on|off] [--enemy-classes on|off] [--boss-classes on|off]
                                     [--trees own|any] [--out DIR]
#   -> build/rando/out/Rando-S-enemies/  (mod.json, tables/DisposUnit.csv, spoiler-enemies.txt, plan-enemies.json)
python tools/randomizer/enemies.py scripted [--all]    # the units this track leaves alone, and why
python -m unittest tests.test_rando_enemies            # 11 tests, about 40 s (2 of them on the real tables)
```

Defaults: gear on, enemy classes off, boss classes off, trees own (Hoshido enemies stay in Hoshido classes, Nohr
enemies in Nohr classes; FE8 port: "Boss classes" and "Enemy classes" are off by default too).

For the integrate step: `plan_enemies(tables, rng, opts) -> (edits, spoiler_lines)`, with
`tables = load_tables()`, `rng = track_rng(seed, opts)` (SHA-256 of version, track name "enemies", seed and
options, so no other track can shift these results) and `run_guards(tables, edits, opts)`. An edit is
`{"table": "DisposUnit", "file", "index", "label", "column", "old", "new"}`. Only `jid` and `item_1..item_5` are
written. Slice 1 writes the item cells of the player's own people, a different set of rows (this track never
touches a main-cast person), so the two merge without a conflict. The mods tool merged both in the robot check
(9116 cells from 2 mods).

## 2. What changes

| Cell (DisposUnit) | When | Rule |
|---|---|---|
| `item_N` (a weapon, tome, staff) | gear on | an ordinary shop weapon (no personal, legendary, enemy-only, chapter-only or precious weapon) **of the same rank or lower**, of a kind the unit's class can use (same side's style first). Staves stay staves. Bosses keep the **same kind and the same rank** |
| `jid` (the class; empty = the person's own) | enemy classes on (generic enemies) / boss classes on (bosses) | see section 3 |

Never written: items that are not weapons (gold, keys, Vulneraries, seals: drops stay drops), weapons the unit's
own class could not use anyway (they are only there to be dropped), special weapons, beaststones and dragonstones,
positions, levels, difficulty bits, forge ranks, skills, AI, groups (so reinforcement turns and counts are the
same), PersonChapter (enemy stats). No row is added. The hidden dice are not touched.

Why "same rank or lower": generic enemies have no stored weapon exp. On Normal, the robot read weapon exp 1 (rank E)
in **every** kind for the level-2 Chapter 2 enemies, so the level, not the kind, decides what a generic may use
[med: one map, one level]. The rank the unit already carried is therefore the safe top. Bosses have their own stored
weapon exp per kind, so they keep the same kind and rank.

## 3. A new class (options)

A candidate must have:

- the same gender row, the same tier (base or promoted), the same side with `--trees own`;
- fliers stay fliers and others stay on the ground, beasts stay beasts;
- the same village-breaking class flag (thieves, ninjas, Oni Savages, Berserkers...);
- a weapon kind for the unit's role: a staff user gets a class with staves at that rank, a fighter a class with a
  fighting kind at that rank. Bosses: a class that can use every weapon the boss carries, so **every boss keeps a
  weapon it can use**;
- an ordinary class: monsters (Faceless, Stoneborn), dragons, puppets, enemy-only, downloadable, Villager,
  Lancer, the avatar's line and the Songstress are never given and never changed.

Units that never change class: units placed off the map at the start (no tile to judge), units with private
terrain costs or "never moves", and bosses named by the chapter's script.

**No stuck enemies** (the FE8 port's rule, adapted). Over that chapter's own terrain grid (TerrainGrid/TerrainTile)
and the movement cost table (TerrainCost row = Job.move_cost_class), the new class, with its own Move, must reach at
least **3/4 as many tiles in 3 turns** as the original class from where the unit stands (other units ignored). It
must also stand on its tile at a cost no higher than the original class's. The candidates are tried in a seeded
random order and the first that passes is used. If none passes, the class stays and the spoiler log says so.
Because each class uses its own Move, a 7-Move Cavalier on open ground seldom finds a base class with 5 Move that
passes. That is on purpose (the rule keeps speed as well as terrain). With all options on, 332 of 2916 class rolls kept their class
this way (seed e49test).

## 4. What is never changed (story-scripted and guarded)

`python tools/randomizer/enemies.py scripted` lists every unit. The script names come from the chapter's own event
scripts (`Scripts/**/<chapter>*.cmb` of your RomFS, read at run time, not stored). Counts over all difficulty rows,
story chapters A, B, C and X (the E encounter files and the castle/DLC files are not touched at all):

| Why | Units | Changed |
|---|---:|---|
| guarded chapter: B009 Conquest 9 (Nyx), B016 Conquest 16 (spare prompt), C008 Revelation 8 (Hayato), C013 Revelation 13 (obstacles) | 35 + 52 + 25 + 75 = 187 | nothing |
| story version of a named person (Xander in the prologue, Takumi, the retainers...) | 173 | nothing |
| named person (main cast) on the enemy side | 8 | nothing |
| a unit in an Event group | 228 | nothing |
| named by the chapter's script (not a boss) | 108 | nothing |
| boss named by the chapter's script | 60 | gear only (same kind and rank), never the class |

Enemy units in scope after that: 4149 rows (each difficulty's row counted). Seed e49test, defaults: 3156 weapons
changed. With all options on: 2584 new classes, 4322 weapons changed.

## 5. Guards (each one checked again from the edits alone; tests in tests/test_rando_enemies.py)

| Guard | Test |
|---|---|
| only `jid`/`item_N` cells of existing rows, old values match | `test_guard_catches_bad_edits`, `test_guards_pass_many_seeds` (60 seeds x 4 option sets) |
| only unscripted enemy units of Enemy/Reinforce groups | `test_guarded_chapters_and_scripted_units_unchanged` |
| the four guarded chapters unchanged | same, and real data `test_real_seeds_pass_every_guard` |
| every changed enemy: legal class and a weapon it can use, rank never up, staff stays staff | `test_every_changed_enemy_has_legal_class_and_weapon` |
| terrain rule holds for every new class | `test_terrain_rule` (all-mountain map: no armor or horse; 4-Move armor never replaces a 7-Move horse) |
| bosses keep a usable weapon, same kind and rank | `test_bosses_keep_kind_and_rank`, guard `bosses_keep_a_usable_weapon` |
| same seed, same edits; another seed, other edits; own stream | `test_same_seed_same_edits_and_different_seed_differs`, `test_track_seed_is_its_own` |
| options off: nothing; classes off: no class edit | `test_options_off_changes_nothing_and_classes_off_keeps_classes` |

Result 2026-11-20: `python -m unittest tests.test_rando_enemies`: **11 tests OK** (39.7 s), including 4 real seeds x
2 option sets on your tables, every guard PASS.

## 6. Robot check (round 49), one headless job

In the robot's own test game only, low priority, `build/STOP_ROUND` checked first; no visible window.

- Mods: `rando.py make --seed e49robot` (slice 1) and `enemies.py make --seed e49robot --enemy-classes on
  --boss-classes on`, both into `build/rando49/enemies/mods/`. `mods.py ... --zakuro-dir build/rando49/enemies/zak
  install`: build OK, 9116 cells from 2 mods, 103 files (`build/rando49/enemies/install.log`).
- Run: `enemies.py robot e49robot build/rando49/enemies/mods build/rando49/enemies/zak
  mod-A002:bt-ch1-clear:bt-ch2:5117:4800/5117`. This uses the recorded Chapter 2 presses up to frame 5117, before the
  first move. Server data folder `build/rando49/enemies/server/e49-mod-A002` (headless server, APPDATA/LOCALAPPDATA
  redirected). 13.8 s. Result `build/rando49/enemies/robot.json`, pictures `build/rando49/enemies/shots/` (not
  tracked). Chapter 2 is the first map where this seed changes enemies (Chapter 1's enemies are all story units).
- Memory was only read: the force-1 unit list (class at Unit+0xA0, items at Unit+0x108, weapon exp at Unit+0xE8),
  matched to DisposUnit rows by person and position.

| Check | Result |
|---|---|
| Enemy units on the Chapter 2 map | 4 at both reads (4800, 5117), all 4 matched to their Normal rows |
| Changed units | 2: row 5 Samurai -> **Spear Fighter** with a Brass Naginata; row 6 Samurai -> **Apothecary** with a Brass Yumi. Class and items in memory = the plan |
| Unchanged units | the boss (gear same kind and rank: its only weapon on Normal kept) and Rinka (story version of a named person, untouched): = the original |
| Can every enemy use what it holds? | yes: weapon exp 1 in every kind for the generics, all weapons rank E; boss Dagger exp 21 |
| Mismatches | the first robot pass printed 3, all in the checker: it expected items that the game gives only on Hard/Lunatic (their Normal forge byte is -1, so Unit::SetDisposItem leaves them out). The checker now drops those slots (`enemies.py robot`). Recounted from robot.json with that rule: **0 mismatches** |
| Off = original | `mods.py ... uninstall`: uninstall OK, **0 files left** in the robot data folder. No second robot run was made (one job only). Round 47 showed at memory level that an uninstalled folder runs like no mod at all (same digests) |

Said plainly: one map, two changed enemies, Normal only. The recorded battle later in Chapter 2 was not played (it
would go another way with new enemies). The terrain rule was not watched in play. It is a table rule, tested on the
host.

## 7. Not done / open

- Enemy items that are not weapons (drops, gold, keys) are not randomized (drops would change the economy).
- No "better weapons" or stronger-enemy options (F-043 #3: no rebalance).
- Hard/Lunatic rows get the same rules but were not read by the robot.
- E encounter maps, castle invasions (Z files) and paralogue variants other than X are not touched.
- Integrate step: fold these edits into the one randomizer mod and the page switches (owned by integrate).

## Round 61: boss classes, what they reach, and the random key

- **Random key.** `track_rng` now writes the boss-classes switch as off in its key, so turning boss classes on
  changes the bosses only (every other draw is per unit and stays the same). Runs with boss classes off keep the same
  key as before (byte-identical); runs with boss classes on (the "everything on" runs too) get new enemy draws once.
- **What it reaches.** On the three Fates routes almost every boss is left alone on purpose: about 106 are the
  chapter versions of a named person, 60 are named by the chapter's script, 10 are in guarded chapters, 8 have no
  class that keeps their weapon kind and rank. Only 4 paralogue bosses can change (Paralogues 2, 13, 15, 17; with a
  given seed often only one does). On Seal of Flames 7 boss rows change (R006's two Wyvern Lords, R019, S010, C006 x2,
  X002). Proven by the robot: Fates X002 "Invader" Swordmaster -> Master of Arms (from each path's save), Seal R006
  "Chevois" Wyvern Lord -> Malig Knight, same seed, the boss rows the only difference between the runs.
- Grok's view (docs/collab/BOSS_CLASSES_GROK.md): keep the rule (named characters stay as the story made them) and
  say so on the page: "Boss classes: only bosses with no story role. On Fates, a few paralogue bosses." Owner's call.

