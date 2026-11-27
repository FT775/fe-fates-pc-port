# Wiring every unwired randomizer module (round 56 plan; replaces WIRE_55 as the one plan)

**Status 2026-11-21 (round 59):** this plan has been carried out. Rounds 57-58 (W1/W2) wired the modules, and round 59 (E1) put the shuffle, music, enemy levels and tougher bosses on the in-game page. Nuzlocke (E2) and the full swap look (E3/E4) are still open. Results: docs/RANDOMIZER.md sections 10-14.

Round 56, F-046 / F-047, 2026-11-20. **Nothing on this page is done yet.** It is the plan for the wiring rounds that
come after rounds 53 and 54 free the shared files and the engine. It covers all eight modules that exist but are not
wired:

| Module | Round | Owner page | Tests today |
|---|---|---|---|
| `children.py` | 55 | docs/rando/CHILDREN.md | 17 |
| `promotions.py` | 55 | docs/rando/PROMOTIONS.md | 19 |
| `music.py` | 55 | docs/rando/MUSIC.md | 21 |
| `nuzlocke.py` | 55 | docs/rando/NUZLOCKE.md | 21 |
| `recruit.py` (character shuffle) | 56 | docs/rando/RECRUIT.md, RECRUIT_WIRE.md | 14 (about 90 s) |
| `weapons.py` | 56 | docs/rando/WEAPONS.md | 17 |
| `stats.py` | 56 | docs/rando/STATS.md | 17 |
| `misc.py` (enemy drops, assign evenly, class movement) | 56 | docs/rando/MISC.md | 21 |

docs/rando/WIRE_55.md and RECRUIT_WIRE.md stay as the detailed per-track notes. Where this page and those disagree,
this page wins (it orders all eight together). Nothing counts as done until the owner says ok (F-037).

Sources for this page: the eight modules' entry points and `DEFAULT_OPTS` (read only), `tools/randomizer/ingame.py
schema()`, `tools/play/rando.py OPTIONS/SUGGESTED`, docs/RANDOMIZER.md section 9, docs/RANDOMIZER_RECRUIT.md
section 8, docs/collab/RANDO_REST_GROK.md, docs/DECISIONS.md F-046/F-047, and the round-56 track reviews.

## 0. Rules for every module (unchanged from WIRE_55, now for eight)

- **Off = byte-identical.** Every new option defaults to "changes nothing". `tracks.active()` stays false with all
  new options at their defaults, so the fixture seeds `r50def`, `r50all` and `r50shops` give the same files byte for
  byte. A module whose option is off is **not imported** (recruit R8 depends on this).
- **Sub-seeds from the seed text, one per module.** Never pass a shared `random.Random`. The key is
  `sha256(TOOL \x1f seed-part \x1f TRACK)`:

  | Module | Key function | TOOL string |
  |---|---|---|
  | children | `children.sub_seed(seed)` | `rando-children-v1` |
  | promotions | `promotions.track_key(seed)` | `rando-promotions-v1` |
  | music | `music.track_key(seed)` | `rando-music-v1` |
  | nuzlocke | none (draws nothing) | `rando-nuzlocke-v1` |
  | recruit | `recruit.sub_seed(seed)` | `rando-recruit-v1` |
  | weapons | `weapons.sub_rng(seed, opts)` (then one sub-stream per purpose) | `rando-weapons-v1` |
  | stats | `stats.track_key(seed)` | `rando-stats-v1` |
  | misc | `misc.track_key(seed)` (one stream per part) | `rando-misc-v1` |

  Note: weapons hashes the bare seed, the others hash `"seed:" + seed`. Both are stable; leave it, because changing it
  changes every weapons seed. Bump a TOOL string only on purpose.
- **Guards with the same opts.** Each module's guard function gets exactly the opts its plan used. All guard results go
  into `plan["guards"]` under `<module>.`. Any failure: exit 2, no mod folder, no patch, the page shows "this seed
  failed a check".
- **Spoiler.** One `_section(...)` per module in `spoiler.txt`. Options go into `mod.json` (`randomizer.topts`, and
  for recruit a separate `randomizer.ropts`, see section 1).
- **F-047 (every path, Seal of Flames included).** Every module already takes a tables object. The wiring passes the
  same `facts`/tables object to all of them and never adds an original-only fact in `tracks.py`. The one known gap:
  the scope rules `STORY_FILE` / `GUARDED` live in `enemies.py` (used by enemies, weapons, misc). The wiring round
  moves them onto the tables object (`tables.story_file`, `tables.guarded`) with the original values as defaults.

## 1. Options and `rando.py make` flags

Add to `tracks.DEFAULT_TOPTS` / `CHOICES` / `BOOLS`, a flag in `rando.py make` (argparse, `default=D[...]`), and a row
in `tools/play/rando.py OPTIONS` (+ `SUGGESTED` for "Everything on"). `ingame.schema()` picks the rows up by itself.
Percent chances are `number` rows 0-100 where **0 means off** (the page already has number rows); the module gets
`0`/`"off"` as it expects.

| key | flag | values | default | Everything on | module opts |
|---|---|---|---|---|---|
| `children` | `--children` (exists) | on/off | off | on | children `children` (+ slice 1 switches, growth/skill opts, see WIRE_55 s.1) |
| `promotions` | `--promotions` | off/on | off | on | promotions `promotions` |
| `promotion_sides` | `--promotion-sides` | any/own | any | any | promotions `sides` |
| `reclass` | `--reclass` | keep/random | keep | random | promotions `reclass` |
| `music` | `--music` | off/maps/maps+battles | off | maps+battles | music `music` |
| `nuzlocke` | `--nuzlocke` | on/off | off | **off** (never in Everything on) | nuzlocke `nuzlocke` |
| `recruits` | `--recruits` | all/first | all | all | nuzlocke `recruits` |
| `recruit` | `--recruit` | off/route/any | off | route | recruit `recruit` |
| `recruit_look` | `--recruit-look` | keep/full | keep | keep | recruit `recruit_look` |
| `recruit_class` | `--recruit-class` | own/slot | own | own | recruit `recruit_class` |
| `recruit_stats` | `--recruit-stats` | autolevel/slot | autolevel | autolevel | recruit `recruit_stats` |
| `weapon_stats` | `--weapon-stats` | off/on | off | on | weapons `stats` (variance = Grok's defaults: might 2, hit 10, crit 5, avoid 5, staff uses 2) |
| `weapon_traits` | `--weapon-traits` | 0-100 | 0 | 25 | weapons `traits` |
| `wild_traits` | `--wild-traits` | off/on | off | off | weapons `wild_traits` |
| `enemy_upgrade` | `--enemy-upgrade` | 0-100 | 0 | 25 | weapons `enemy_upgrade` |
| `upgrade_rank` | `--upgrade-rank` | same/next | same | same | weapons `upgrade_rank` |
| `class_growths` | `--class-growths` | off/delta | off | delta | stats `class_growths` |
| `class_growth_variance` | `--class-growth-variance` | 0-50 | 10 | 10 | stats |
| `class_bases` | `--class-bases` | off/delta | off | delta | stats `class_bases` |
| `class_base_variance` | `--class-base-variance` | 1-5 | 2 | 2 | stats |
| `enemy_growths` | `--enemy-growths` | off/flat/scaling | off | flat | stats `enemy_growths` |
| `enemy_buff` | `--enemy-buff` | 0-100 | 10 | 10 | stats |
| `enemy_levels` | `--enemy-levels` | 0-5 | 0 | 0 | stats |
| `boss_stats` | `--boss-stats` | off/linear/ease | off | linear | stats `boss_stats` |
| `boss_max_boost` | `--boss-max-boost` | 1-20 | 5 | 5 | stats |
| `boss_variance` | `--boss-variance` | 0-5 | 0 | 0 | stats |
| `enemy_drops` | `--enemy-drops` | 0-100 (steps of 5) | 0 | 10 | misc `enemy_drops` |
| `class_move` | `--class-move` | off/small/wide | off | small | misc `class_move` |
| `assign_evenly` | `--assign-evenly` | on/off | off | on | misc `assign_evenly` |

Internal, never a row or flag: promotions `choices` stays `"2"` (`"3"` refused; F-046 keeps two choices),
stats `class_growth_max` stays 60, weapons per-stat variance stays at Grok's numbers (a `--weapon-variance` flag
exists for the CLI only).

**Recruit options are a separate `ropts` dict, not `topts`** (RECRUIT_WIRE s.1): adding them to `topts` would change
`mod.json` of old seeds that have a track on. `ropts` goes into `mod.json`, the plan and the spoiler header only when
`recruit != "off"`. `cmd_check` passes the saved `ropts` back.

**Children and slice 1:** keep `randolib.make_plan` seeing `children=False` (strip the switch, route it to
`plan_children` only); drop the "(not built)" label, `fixed: True` and the PLAY RANDOMIZED `--children off`
override.

`tracks.py` mapping helpers, in the style of `growth_opts()`: `children_opts`, `promotions_opts`, `music_opts`,
`nuzlocke_opts` (exactly as WIRE_55 s.1), plus

```
weapons_opts(o)  = {"stats": o["weapon_stats"] == "on", "traits": o["weapon_traits"], "wild_traits": o["wild_traits"],
                    "enemy_upgrade": o["enemy_upgrade"], "upgrade_rank": o["upgrade_rank"]}
stats_opts(o)    = {k: o[k] for k in stats.DEFAULT_OPTS if k != "class_growth_max"}
misc_opts(o)     = {"enemy_drops": o["enemy_drops"], "class_move": o["class_move"], "assign_evenly": o["assign_evenly"]}
active(): + children, promotions/reclass, music, nuzlocke (WIRE_55), weapons (any of stats/traits/upgrade),
            stats (any mode not off, or enemy_levels > 0), misc.active(misc_opts(o)); recruit is checked via ropts
```

## 2. Order inside `tracks.make_all` (one order for all eight)

Each module has its own sub-seed, so the order never moves a draw. It matters only where modules share cells or facts.

| Step | What | Why here |
|---|---|---|
| 1 | **recruit** (only if `ropts.recruit != off`): `plan_recruit(load_tables(facts), seed, ropts)`, `run_guards`, then `facts = shuffled_facts(facts, r_edits)` | every later step plans on the shuffled army |
| 2 | slice 1 `R.make_plan(facts, seed, sw)` (children stripped) | |
| 3 | **misc assign evenly**: `classes, lines = misc.assign_evenly(facts, plan, seed, mo)`, then `plan = R.make_plan(facts, seed, sw, classes=classes)`, `misc.run_even_guards(facts, before, plan)` | growth, skills, promotions, children all read the final class. Needs the new `classes=` argument in `randolib.make_plan`; then delete `misc._EvenFacts` / `make_plan_even` |
| 4 | growth track (unchanged) | |
| 5 | **promotions, Job part** → `promo_after` | skills and children need the new promotion lines |
| 6 | skills track, with `SkillFacts(promotions=promo_after)` | |
| 7 | **children** with `base_plan`, `skill_rows`, `taken_personal`, `job_promotions=promo_after` | fixes the job_low gap (WIRE_55 s.2) |
| 8 | items, then enemies (unchanged) | |
| 9 | **stats** `plan_stats(stats.load_tables(), seed, stats_opts)` | boss bounds read the boss's own PersonChapter class; the game clamps a changed boss class anyway |
| 10 | **misc enemy drops** `plan_drops(t', seed, mo)` with `t'` = EnemyTables copy with the enemies `jid`/item edits applied | drops mark the final enemy items |
| 11 | **weapons** `plan_weapons(t'', weapons.sub_rng(seed), weapons_opts | {"enemies_edits": e_edits})`, `t''` = `t'` plus the drop marks | weapons already leaves marked (dropped) slots alone, so a drop is never an upgraded weapon |
| 12 | **misc class movement** `plan_movement(t'', seed, mo)` + `run_move_guards` on the same `t''` (final enemy classes) | fixes the known gap: the no-stuck check read the original enemy classes |
| 13 | **music** (load `music.load_tables()` only when on) | |
| 14 | **nuzlocke**: no table edits; with it on write `nuzlocke.json` = `make_rules(facts, nuzlocke_opts)` | |
| 15 | **cross guards** on the final edits of all modules (section 2a) | |

### 2a. Cross guards (new, in `tracks.py`)

- `job_low_fits_final_promotions`: every player-army Person row (children included) with a non-empty `job_low` has it
  among the final promotions of its final `job` (WIRE_55; seeds w55a/b/c failed 14-16 of 22 child rows without it).
- `no_stuck_final`: every in-scope enemy can still reach 3/4 of its old tiles in 3 turns with its **final** class
  and the **final** Move (enemies + misc).
- `weapons_usable_final`: every carried weapon of every placement is usable by the final class, after recruit, slice
  1, enemies and weapons (recruit and weapons check this alone today).
- `one_writer_per_cell`: no `(file, row, column)` is written by two modules with different values, except the listed
  chains (recruit → slice 1 Person cells; enemies → weapons DisposUnit item cells), where `old` must equal the
  earlier module's `new`.

### 2b. Shared files: merge by columns, one CSV per table

| Table | Written by | Rule |
|---|---|---|
| `tables/Person.csv` (GameData) | recruit, slice 1, growth, skills, children, promotions (job_low, reclass) | recruit first, slice 1 over it (slice 1 wins), then the rest by column; children vs promotions job_low: children write their own rows, promotions skip them |
| `GameData/Person/{A,B,C}_HANDOVER` Person CSVs | recruit (`laid_by: person_hook`) | own CSVs in the mod folder; not in the in-game patch until engine round E1 (section 6); spoiler says "route-variant joins keep the spot's starting stats" |
| `tables/Job.csv` | promotions (`promotion.1/.2`), stats (`growth`, `base`, `enemy_growth`), misc (`mov`) | columns never overlap; one row per Job index (`misc.job_csv_with_edits` keeps the others' columns) |
| `tables/Item.csv` | items (other columns), weapons (might/hit/crit/avoid/uses/flags/effective/stat_bonus) | by column |
| `tables/DisposUnit.csv` | recruit (`jid`, items), items, enemies (`jid`, items), weapons (items), misc (`item_N_flags`) | in step order; teach `_dispos_csv` the `item_N_flags` columns so `one_writer_per_cell` covers them |
| `tables/PersonChapter.csv` | stats (`level`, boss bases), music (`combat_music`) | by `(file, index)` and column |
| `romfs/map/config/*.bin` | music | whole files rebuilt from the game's own bytes |
| `nuzlocke.json` | nuzlocke | rules file only |
| plan JSON only | recruit FaceData / Message records (`laid_by: engine`) | for full identity, engine rounds E3/E4 |

### 2c. Module fixes the wiring round makes first (found by the round-56 reviews)

- **misc pair map** (review, minor but real): `misc.family()` strips only the 男/女 ending, so Monk/Shrine Maiden,
  Great Master/Priestess and Butler/Maid count as separate classes: their Move can differ (seed rv1 wide: Monk 7,
  Shrine Maiden 5) and assign evenly counts them twice. Fix: an explicit male/female pair map on the tables object
  (F-047), used by `family()` and by the guard `male_and_female_rows_move_together`; add a test with those three pairs.
- **misc promoted Move upper bound**: also check the upper bound for promoted classes in the guard.
- **weapons, effective weapons** (design call for Grok, not a bug): "better enemy weapons" may swap a Wyrmslayer for a
  Steel Sword (+1 might, loses the dragon bonus; seed rv3). Suggested rule, to confirm with Grok in that round: never
  upgrade a weapon that has an `effective` cell to one without it.
- **stats `bosses_beatable`** can never fail as written (each stat is already capped). Replace with an independent
  check: a boss's Def + Res gain at most `boss_max_boost` combined above what the original seed had, or drop it and
  say so. Low priority.
- **misc class movement design** (Grok question, player-facing): with the no-stuck rule, losing 1 Move almost always
  fails on open ground, so the option mostly makes classes faster, enemies included. MISC.md s.6 lists the choices.

## 3. The in-game page: the full row list after wiring

The page builds its rows from `rando.py schema`, so new rows need **no engine build**. The core lays only `GameData`
and `GameData/Dispos/**` today; rows whose files it cannot lay are grey ("fixed") until their engine round, and
`make --patch-out` refuses them with the reason, so a half-made patch can never happen. Every row defaults to off /
"changes nothing". Labels are for a player who never read the docs. Order (two-space indent = belongs to the row above):

| # | Row label on the page | Values | Default | Notes / when live |
|---|---|---|---|---|
| 1 | Randomizer | on/off | off | exists |
| 2 | Seed | text | (new) | exists |
| 3 | **Who joins where** (character shuffle) | off / this route / any route | off | grey until engine round E1 (recruit plan round 3) |
| 4 | Shuffled people look like | the spot's person / themselves (full swap) | the spot's person | "themselves" offered only after recruit plan round 6 |
| 5 | Shuffled people's class | their own / the spot's | their own | with row 3 |
| 6 | Shuffled people's level and stats | fit the spot's level / the spot's | fit the spot's level | with row 3 |
| 7 | Classes | on/off | on | exists |
| 8 | Class trees (own side / any) | own/any | own | exists |
| 9 | Royals keep their classes | on/off | on | exists |
| 10 | Spread classes evenly (fewer repeats) | on/off | off | new (misc) |
| 11 | Growths | on/off | on | exists |
| 12 | Growths mode, variance, min, max, Adjust HP | | | exist (5 rows) |
| 13 | Join stats | on/off | on | exists |
| 14 | Bases mode, Base variance, Scale to join level | | | exist (3 rows) |
| 15 | Personal skills / Skill slots | | | exist (2 rows) |
| 16 | **Random promotions** (Master Seal choices) | off/on | off | new |
| 17 | Promotions stay on own side | any/own | any | new, indented |
| 18 | Heart Seal classes | keep/random | keep | new |
| 19 | **Children** (class, growths, one skill; parents stay) | on/off | off | was grey "(not built)" |
| 20 | **Class growth rates** | off / changed | off | new (stats) |
| 21 | How much (in 5s) | 0-50 | 10 | indented |
| 22 | **Class base stats** | off / changed | off | new (stats) |
| 23 | How much | 1-5 | 2 | indented |
| 24 | **Class movement** | off / ±1 / ±2 | off | new (misc) |
| 25 | Starting items | on/off | off | exists |
| 26 | Shops / Shop sides | | | exist (2 rows) |
| 27 | Castle rewards | on/off | off | exists |
| 28 | **Weapon stats** (might, hit, crit, avoid, staff uses) | off/on | off | new |
| 29 | **Weapon special powers** (chance per weapon) | 0-100 % | 0 | new |
| 30 | Wild powers too (brave, double counter, heal) | on/off | off | indented |
| 31 | Enemy classes | on/off | off | exists |
| 32 | Boss classes | on/off | off | exists |
| 33 | Enemy class trees (own side / any) | own/any | own | exists |
| 34 | Enemy weapons (shuffled, same kind) | on/off | off | exists; label sharpened so it is not confused with row 35 |
| 35 | **Stronger enemy weapons** (chance) | 0-100 % | 0 | new (weapons) |
| 36 | Stronger weapons may be one rank higher | same/next | same | indented; "next" only after its robot check |
| 37 | **Enemies grow faster** | off / flat / more later in the story | off | new (stats) |
| 38 | Extra growth % | 0-100 | 10 | indented |
| 39 | **Enemy levels up** | 0-5 | 0 | new (stats) |
| 40 | **Tougher bosses** | off / steady / more later in the story | off | new (stats: linear / ease) |
| 41 | Most extra points per stat | 1-20 | 5 | indented |
| 42 | Random spread | 0-5 | 0 | indented |
| 43 | **Enemies drop items** (chance per enemy) | 0-100 % | 0 | new (misc) |
| 44 | **Music** | off / maps / maps and battles | off | grey "(PLAY RANDOMIZED only until the next engine round)" until engine round E1 |
| 45 | **Nuzlocke** (Classic only: the fallen stay fallen after a reset) | on/off | off | grey until engine round E2 |
| 46 | Only the first new ally per chapter | all/first | all | indented, grey with row 45 |

Help line under the page (one sentence each, in RANDOMIZER.md): who never moves in the shuffle (Corrin, Azura, the
royals, Gunter, the children; Nyx and Shura held until their chapters pass); traits show only in the spoiler; enemy
growths also speed up allied NPCs; music never touches scenes, the title or songs a character sings.

PLAY RANDOMIZED (`tools/play/rando.py`, menu "choose") shows the same rows in the same order, because both read
`OPTIONS`. Music works there from wiring round W2 (mod folder path). Recruit "keep the face" works there from W2 for
everything except the route-variant starting stats (person_hook).

## 4. `config/randomizer/rules.json`

- `tracks.modules`: add `children`, `promotions`, `music`, `nuzlocke`, `recruit`, `weapons`, `stats`, `misc` →
  `tools/randomizer/<name>.py`. `tracks.about` → round 56 / F-046, F-047.
- New block `"recruit"` = `recruit.DEFAULT_RULES` (keys in RECRUIT_WIRE s.2: `recruit_fixed`, `recruit_hold`,
  `recruit_castle`, `recruit_flier_before`, `flier_job_category`, `recruit_keep_cells`, `recruit_full_cells`).
- New block `"scope"` (F-047): `story_file`, `guarded` (moved from `enemies.py`), `job_pairs` (the male/female pair
  map from 2c). IDs only, no game values.
- Optional ID-only blocks for children/promotions/music/nuzlocke as in WIRE_55 s.4, each with a test that module and
  rules agree. A Seal of Flames rules file later carries its own `recruit` and `scope` blocks.

## 5. `tools/check_all.py` rows and samples

Rows (same style as today: `require` `^Ran [1-9]\d* tests? in ` and `^OK\b`, `reject` Traceback / FAILED):

| Row | Command | Cost / timeout |
|---|---|---|
| new `rando-more-tracks-tests` | `{py} -m unittest tests.test_rando_children tests.test_rando_promotions tests.test_rando_music tests.test_rando_nuzlocke` (78 tests) | medium / 1800 |
| new `rando-r56-tracks-tests` | `{py} -m unittest tests.test_rando_weapons tests.test_rando_stats tests.test_rando_misc` (55 tests) | medium / 1800 |
| new `rando-recruit-tests` | `{py} -m unittest tests.test_rando_recruit` (14 tests, about 90 s) | slow / 1800 (weekly run, F-028) |
| extend `rando-tracks-tests` | `tests.test_rando_integrate`: defaults byte-identical with all new options present; Everything on passes every guard + the four cross guards; independence (each module on/off moves no other module's cells) | as today |
| extend `rando-ingame-tests` | `tests.test_rando_ingame`: schema has rows 3-46 with the defaults above; grey rows fixed; `--patch-out` with the table-only options on equals the mods tool's rebuilt GameData/Dispos cell for cell; `--patch-out` with music or nuzlocke on is refused with the reason | as today |

Fixed samples (host only, write under `build/`; also the seeds for the robot rounds):

| Sample | Command | Expected |
|---|---|---|
| defaults | `rando.py make --seed r56def` | slice 1 byte for byte (= r50def) |
| table-only all on | `rando.py make --seed r56tab` + children, promotions on / reclass random, weapon stats on, traits 25, upgrade 25, class growths/bases delta, enemy growths flat, boss stats linear, drops 10, class move small, assign evenly on | every guard + cross guards; mods tool accepts Job/Item/DisposUnit/PersonChapter CSVs |
| everything | `r56all` = r56tab + music maps+battles + `--recruit route` | as above; `check` reproduces it |
| recruit full | `recruit.py plan --seed abc --recruit any --recruit-look full` | all guards ok (2895 edits today) |
| children | `children.py check --seeds 50` (3 sets, WIRE_55) | 0 failures |
| promotions | seed `w55a`, on / random / own | all guards |
| music | `music.py make --seed demo55 --music maps+battles` | 252 cells, 7 guards |
| nuzlocke | `nuzlocke.py rules --recruits first` | 5 never-benched rows |
| weapons | `weapons.py make --seed w1 --stats on --traits 25 --enemy-upgrade 25` | 637 stat values / 35 traits / 478 upgrades, 5 guards |
| stats | `stats.py make` everything on, seeds rev1-rev3 | about 3400 edits, all guards |
| misc | `misc.py make --seed m56a --enemy-drops 20 --class-move wide --assign-evenly on` | all guards (numbers change after the pair-map fix) |

## 6. Robot checks (headless, own data folder and APPDATA/LOCALAPPDATA under build/, existing recordings only, STOP_ROUND checked first)

| Module | Check | Can it run now? |
|---|---|---|
| all | every new option off: memory and saves byte-identical to today (round-51 T4 re-run) | yes |
| promotions | seed w55a via the in-game patch: Job promotion cells and Person job_low/reclass in memory = the patch; a Master Seal menu if a recording has one | (1) yes, (2) only if a recording reaches a seal |
| stats | r56tab: Job rows in memory = plan; one boss and one generic enemy on Chapter 2 created with the planned stats and level (answers "does PersonChapter.level show as the map level") | yes |
| weapons | Item rows in memory = plan; on an early chapter, an upgraded enemy attacks with its new weapon and its weapon exp (Unit+0xE8) allows it; repeat with `upgrade_rank next` before "next" may be offered as more than a choice | yes |
| misc | a marked enemy drops its item when beaten (the robot's existing fights); a class with new Move moves that far | yes where a recording beats a marked enemy |
| music | PLAY RANDOMIZED mod folder, seed demo55: the chapter's current song name in `map::sound`; one boss fight; does hearing a song unlock it in the Sound Room | yes (mod folder) |
| children | one child paralogue join read back (class, job_low, items) | **blocked**: no recording reaches a child paralogue, F-025 forbids marrying for coverage → cheat poke (OK'd, F-046) |
| recruit keep | Chapter 2, Revelation 9 (Hayato), Revelation 13, Conquest 9: joined unit's class, items, growths, personal skill; off = original | after E1 |
| recruit full | the swapped speaker scene, battle model, names in dialogue, silenced voice; Revelation 8, Conquest 16, ninja doors | after E3/E4; Rev 8 / Con 16 / ninja doors need cheat pokes (OK'd, F-046) |
| nuzlocke | a death written once; Restart / battle save / older save / state load bring the unit back dead; Corrin not written; second join benched; off = byte-identical | after E2 |

## 7. Engine work still needed (all OK'd: F-046 engine OK and addendum; each with an exe backup first, only after round 53 frees the engine)

| Engine round | What | Unlocks | Size |
|---|---|---|---|
| **E1: two new file kinds in the core** (`fates_rando.rs` + `ingame.make_patch`) | `GameData/Person/**` as a placement-like kind, and `map/config/*.bin` (`mapconfig`) | recruit "keep the face" fully on the page (route-variant HANDOVER rows; = recruit plan round 3), music on the page (rows 3-6 and 44 stop being grey) | 1 engine round with its robot checks |
| **E2: Nuzlocke hooks C1-C6** (NUZLOCKE.md s.4) | page start + rules file, death hook `Unit::Transfer` 0x003D8C00, join hook, load hook after `UnitPool::Deserialize` 0x004F5BE8, Classic lock, "This run" | rows 45-46 | 1 engine round + 1 robot round; first settle the 0x800 bench bit on forced deploys |
| **E3: full identity P1-P3 (+P5)** = recruit plan round 4 | a resident patch at New Game for FaceData / AssetTable (both load once at boot), `aid` for the map head, chapter Person copies | swapped portraits, models, names in menus | 1 engine round |
| **E4: full identity P4** = recruit plan round 6 | hook on `Mess::Get` 0x003D1CEC for names in dialogue; voice lines silenced | "themselves" offered in row 4 | 1 engine round |
| not planned | third promotion choice (`ClassChangeEnumerator::Enumerate` 0x0021B148): **not** OK'd and Grok said no; inherited class / parent bonuses for children; a live drop roll | | |

## 8. Counted rounds to a complete randomizer (F-027: each is one sitting with its own time box)

| # | Round | Engine? | Robot? | Delivers |
|---|---|---|---|---|
| 1 | **W1** wiring, host | no | no | children, promotions, stats, weapons, misc wired; module fixes 2c; cross guards; rules.json; check_all rows; page rows 10, 16-43 live; music/nuzlocke/recruit rows grey; fixtures |
| 2 | **W2** wiring, host | no | no | recruit wired to CLI + PLAY RANDOMIZED (ropts), music in PLAY RANDOMIZED, nuzlocke.json written; slice-1 HANDOVER jid fix **if the owner says yes**; RANDOMIZER.md section 9 moved to "on the page" |
| 3 | **T1** robot | no | yes | the "yes" checks in section 6 for W1/W2 (off = byte-identical, promotions, stats, weapons, misc, music via mod folder) |
| 4 | **E1** core file kinds = recruit plan round 3 | yes | yes | recruit keep the face on the page; music on the page; Chapter 2 / Rev 9 / Rev 13 / Con 9 |
| 5 | **E2** Nuzlocke hooks | yes | no | Nuzlocke rows live |
| 6 | **T2** Nuzlocke robot | no | yes | the Nuzlocke checks |
| 7 | **E3** full identity P1-P3 = recruit 4 | yes | yes | speaker scene, battle model |
| 8 | recruit 5: missing expressions, fallback, map sprite | no | yes | expression scene |
| 9 | **E4** full identity P4 = recruit 6 | yes | yes | names in dialogue, voices silent; "themselves" on the page |
| 10 | recruit 7: full identity robot pass where recordings reach | no | yes | Rev 13, Con 9, Chapter 2, Rev 9 |
| 11 | cheat-poke round (OK'd, F-046) | no | yes (cheat track) | Rev 8, Con 16, ninja doors, one child paralogue; free Nyx and Shura if they pass |
| 12 | owner review of the whole randomizer: fixes, help text, docs | no | reruns only | done when the owner says ok |

**12 counted rounds**, up to **15** with three named slips: W1 too big for one sitting (8 modules plus fixes), the
missing-expression case needing the file way (recruit), and Conquest 9 not fitting the recordings (moves to round 11).

## 9. What needs the owner's yes

1. **Slice-1 fix for route-variant joins** (RECRUIT_WIRE s.4): with Classes on today, Revelation joins (and some
   Birthright/Conquest ones) keep their original class and weapons. The fix writes the new class into their placement.
   It changes the output of existing seeds with Classes on, so the fixture seeds are updated in the same round.
2. Already OK'd (F-046), listed for reference: **cheat pokes** to reach chapters no recording reaches: Revelation 8, Conquest 16, the ninja door maps, and one
   child paralogue (F-025 forbids marrying for coverage). Cheats only in the test game, never in real play (F-030
   pattern).
3. **Freeing Nyx and Shura** in the shuffle once Conquest 9 / 16 pass.
4. Not a yes, information: the third promotion choice stays not planned (not OK'd, Grok said no).

Grok questions for W1 (creative lead, facts-only): the effective-weapon upgrade rule (2c), and what "Class movement"
should do given the no-stuck rule (MISC.md s.6).
