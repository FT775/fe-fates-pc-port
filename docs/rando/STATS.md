# Randomizer track "stats": class growths, class bases, enemy growths, enemy levels, boss stats

Round 56, 2026-11-20. The owner asked to "build the other missing parts too". This track covers these rows of the
FE8 port's Randomizer screen, which docs/RANDOMIZER.md section 9 lists as "not built": **Class growths**,
**Class bases**, **Enemy growths** + **Enemy buff**, **Boss stats** + **Boss max boost**. Only the host side is
built: the module, its tests and this page. It is **not wired yet**: no rando.py flag, nothing on the in-game page,
nothing in check_all. Nothing counts as done until the owner says ok (F-037).

## For the owner (one paragraph)

Four new switches, all off by default. Off means the game is exactly as before, byte for byte. **Class growths**
and **Class bases** nudge each class's own growth rates and starting stats up or down a little, so a Cavalier or a
Samurai feels a bit different every game. The male and female versions of one class always move together. A
class's HP base never goes down, so nobody can start with 0 HP. **Enemy growths** makes generic enemies grow
stronger as they level, the same way as the FE8 port: Flat adds a number, Scaling adds a percentage. **Enemy
levels** adds 1 to 5 levels to generic enemies (at most level 20). **Boss stats** gives bosses extra stats, more
the later their chapter comes in the story, with an optional small random wobble. It never touches a character who
later joins your army, never pushes a stat past the class's cap, and no stat gains more than "Boss max boost". So
bosses stay beatable. Tested on 50 seeds with made-up tables, and on 50 seeds with your own game's tables (every
guard passes, and the mods tool accepts the folder). Nothing has been run in the game yet.

## Facts (from docs/TABLES.md, "How a unit's stats are computed")

- **Class growths** are `Job.growth` (+0x24). The game adds them to a unit's personal growth **only when
  `Person.unit_kind == 1`** (player characters; `Unit::GetGrow` 005330B4). Fates already adds class growth to
  personal growth by itself, so the FE8 port's "Keep / Transfer" choice has no meaning here (slice 1 already acts
  like Keep). This track's Class growths changes the class numbers themselves.
- **Enemy growths** are `Job.enemy_growth` (+0x2C). All other units use them: `unit_kind` 0, 2 and 3, which means
  enemies, bosses, other armies' units, and the automatic level gains of generic units
  (`Unit::CaclulateAutoGrowCapability` 00532880). Allied NPCs (green units) level with them too, so Enemy growths
  makes them a little stronger as well. That is a side effect, and the spoiler log shows it.
- **Class bases** are `Job.base` (+0x1C). They are added to **every** unit's personal base in that class: player
  characters, joiners and enemies alike (`Unit::Get*Impl`). The shown stat is clamped to 0 and to
  `Job.max + Person.limit_mod`.
- **Generic enemies** (`unit_kind 0`) get automatic gains `G = round(growth x L / 100)`, where
  `L = level - 1 (+19 when promoted)`, plus the difficulty columns. Named units (`unit_kind` 1, 2, 3) start from
  their `Person.base` as written. So a generic enemy's strength comes from its PersonChapter row's **level** and the
  class's **enemy growths**. Almost every enemy placement leaves `DisposUnit.level` at 0, which means "the person's
  own level" (all but 12 of the team-1 placements). That is why Enemy levels writes `PersonChapter.level` and not
  the placements.
- **The difficulty fields**: `Person.normal_extra_levels` / `lunatic_extra_levels` and `normal_mod` / `lunatic_mod`.
  Hard has no column of its own (Hard uses the record as it is). This track leaves all four alone, so the game's own
  difficulty curve stays on top of whatever this track adds, on every difficulty.
- **Item level gates**: `DisposUnit.item_N_flags` bits 1-4 give an item only at some levels (unpromoted <= 20,
  promoted <= 10 / >= 11, ...). Enemy levels never goes above 20 and never moves a promoted enemy across 10 -> 11,
  so no enemy gains or loses an item because of it.
- **Bosses**: by default a PersonChapter row is a boss when its label has `ボス` (the game's own boss rows), or when
  it is `unit_kind 2` and only the enemy team places it in that chapter. In both cases the row is skipped if its
  name (`mpid_name`) belongs to a person of the player's army. So story versions of people who join (royals,
  recruitable enemies) are never buffed, and a unit recruited in the middle of a map never brings boss stats with
  it. In the user's own tables: 81 boss rows, 966 generic enemy rows, 129 class rows (the excluded classes from
  rules.json, such as downloadable ones and story forms, are never written).
- **Story position** (for Boss stats): the chapter number divided by the largest number of that route letter
  (A/B/C). Paralogues and anything else count as halfway (0.5). Chapter 0 counts as 0, so no buff there. Both
  defaults can be replaced through the tables object (see "Every path", below).

## What is built

`tools/randomizer/stats.py` (our own code; the formulas follow the FE8 port's `ApplyEnemyGrowth` and
`BossBuffAmount`):

    plan_stats(tables, rng, opts) -> (edits, spoiler_lines)
    run_guards(tables, edits, opts) -> {guard: {"ok", "detail"}}
    edits_to_files(tables, edits) -> {"tables/Job.csv", "tables/PersonChapter.csv"}
    load_tables() -> StatsTables     (the user's own RomFS through tools/mods, read only)
    python tools/randomizer/stats.py make --seed S [options] --out build/...   (this track alone, one mod folder)

| opts key | values (default first) | what it does |
|---|---|---|
| `class_growths` | off / delta | each `Job.growth` moves by up to `class_growth_variance` (0-50, **10**), in steps of 5, kept within 0..`class_growth_max` (0-125, **60**; a class that already has more keeps its number as the ceiling) |
| `class_bases` | off / delta | each `Job.base` moves by up to `class_base_variance` (1-5, **2**), kept within 0..`Job.max`; HP only goes up or stays |
| `enemy_growths` | off / flat / scaling | `Job.enemy_growth` + `enemy_buff` (flat) or + `enemy_buff` % (scaling); `enemy_buff` 0-100, **10**; rounded half up to steps of 5, at most 125, never lower; negative cells untouched |
| `enemy_levels` | **0**-5 | generic enemy rows (`unit_kind 0`, placed only on the enemy team in their chapter, including the E variant files) gain this many levels, at most 20; promoted ones at level <= 10 stop at 10 |
| `boss_stats` | off / linear / ease | each boss stat + `ceil(boost x f)` (linear) or `ceil(boost x f^2 / (f^2 + (1-f)^2))` (ease), where f is the story position and boost is `boss_max_boost` (1-20, **5**) |
| `boss_variance` | **0**-5 | each boss stat also moves by up to this many either way (it also works with boss_stats off) |

Draws: the track's own sub-seed, `sha256(TOOL \x1f "seed:"+seed \x1f "stats")`, with
`TOOL = rando-stats-v1`. On top of that there is one stream per (purpose, row), where row is the class-pair key or
`file#index`. So turning on another track never moves this one, and the same seed always gives the same cells.
Every growth this track writes is a multiple of 5, so the mods tool needs no `--allow-odd-growth`.

Guards (`run_guards`, recomputed from the edits and the original rows alone): `only_stat_cells` (Job
growth/base/enemy_growth, PersonChapter level/base, and nothing else; the old value is the original),
`cells_fit` (signed byte), `class_growths_bounded`, `class_bases_bounded` (HP never lower), `enemy_growths_formula`
(exactly the formula), `enemy_levels_bounded` (generic enemy rows only, <= 20, no 10/11 crossing, <= the option),
`boss_stats_bounded` (boss rows only, never an army person, at most +max boost / -variance, within 0 (HP 1)..cap),
`bosses_beatable` (HP + Def + Res gain together at most 3 x max boost; this already follows from the per-stat
bound and is kept as a second check), `off_means_no_edits`.

Tests: `python -m unittest tests.test_rando_stats` (17 tests). Made-up tables: off = no edits over 50 seeds,
all 16 option sets over 50 seeds through every guard, the same seed gives the same cells, class pairs share a draw,
HP class bases never lower, the enemy growth formula with worked numbers, enemy levels only on generic enemies
(not allies, not unit_kind 3, not excluded classes, the 20 cap and the 10/11 gate), the boss curve rising and
capped, army people never buffed, the cap respected, boss variance never below the floor, the tables object
deciding order and bosses (F-047), every guard catching a tampered edit, bad options refused, and the CSV files.
The user's own tables (skipped when they are not there): off = no edits, 50 seeds x 4 option sets through every
guard, and `mods.compute` accepts the folder with no errors. All 17 pass (2026-11-20).

## Every path, the Seal edition included (F-047)

Every fact comes from the `StatsTables` object that is passed in: the Job rows, the resident Person rows (used
only to know who is in the army), the PersonChapter rows, the placements, and the rules. The two Fates-specific
conventions can be replaced when the object is built:

- `chapter_order={chapter key: fraction 0..1}` sets each chapter's story position, for a story whose chapter
  numbering is not A/B/C + 3 digits, or to place paralogues properly;
- `boss_pids={labels}` lists the boss rows, for a story whose bosses are not named `..._ボス`.

Fates' three routes need nothing extra: Person and Dispos files below `A/`, `B/` and `C/` are matched by their
chapter key, and the story position is counted per route letter. A Seal edition table set (once the game picker
round can hand one over) passes its own rows to the same object.

## How to wire it (for the integrate round; this track edits none of these files)

1. `tracks.py`: add `stats_opts(o)`, mapping topts to the track's opts with the same names. Suggested topts and
   flags: `class_growths` / `--class-growths off|delta`, `class_growth_variance`, `class_bases` /
   `--class-bases off|delta`, `class_base_variance`, `enemy_growths` / `--enemy-growths off|flat|scaling`,
   `enemy_buff`, `enemy_levels`, `boss_stats` / `--boss-stats off|linear|ease`, `boss_max_boost`, `boss_variance`.
   `class_growth_max` stays internal (60). With all of them at their defaults, `tracks.active()` must stay false.
   Suggested "Everything on": delta 10 / delta 2 / flat 10 / 0 levels / linear 5 / variance 0. That is the FE8
   port's own default strength, and it leaves enemy levels for players who want them.
2. `rando.py make_all`: build `stats.load_tables()` once (it shares the loaders with `enemies.load_tables`), call
   `plan_stats(tables, seed, stats_opts)` with the **seed text**, put `run_guards(...)` under `stats.` in
   `plan["guards"]` (any failure means exit 2 and no mod), and add the spoiler lines in their own section.
3. **Merging cells** with other tracks: `tables/Job.csv` is also written by promotions (`promotion.1/.2`), and
   `tables/PersonChapter.csv` by music (`combat_music`). The cells never overlap, so the integrate step merges
   them as columns of one CSV per table (one row per Job index, or per PersonChapter `file`+`index`), not as two
   files.
4. **Order with the enemies track**: enemy and boss classes change only DisposUnit `jid`. Boss stats bounds use
   the boss's own class from its PersonChapter row. If boss classes are on, the game still clamps to the new
   class's cap. A boss that lands in a weaker class keeps its buffed personal numbers, which is fine, because the
   boost is per stat and bounded.
5. `ingame.py` / `tools/play/rando.py OPTIONS`: the labels "Class growths", "Class bases", "Enemy growths",
   "Enemy buff", "Enemy levels", "Boss stats", "Boss max boost", "Boss variance", plus the help lines from the table
   above. The in-game page needs no engine change: these are table cells applied at New Game like every other
   track's.
6. `docs/RANDOMIZER.md` section 9: move "Class growths / Class bases", "Enemy growths, Enemy buff" and
   "Boss stats, Boss max boost" from "not built" to "built (host), not wired", and then to "on the page" once wired.
7. Robot check (a later lane): one headless run with all-on cells. The mods tool reads `Job` and `PersonChapter`
   back from memory, and the check confirms the class rows in memory equal the plan, plus one boss's and one
   generic enemy's created stats on Chapter 2 (the robot's existing read points).

## What needs the core later

- **A per-difficulty buff** (for example "Hard only"): the only per-difficulty columns are Normal and Lunatic
  (`*_extra_levels`, `*_mod`). Hard uses the record as it is, so a Hard-only buff needs a game-code change (an
  engine round with owner OK). This track avoids those columns on purpose.
- **"Class growths: Transfer" / "Class bases: Personal"** in the FE8 sense (a character's growths following a new
  class): Fates adds class growth and class base by itself, so slice 1 already behaves like Keep / Final. A real
  Transfer would mean rewriting personal growths when slice 1 changes a class. That belongs in slice 1 or the
  growth track, not here.
- **Paralogue story positions**: the default 0.5 is a guess. The Chapter table's `required_chapter` could place
  each paralogue after the chapter that unlocks it. That needs the Chapter rows in the tables object (a small
  later step, no engine change).
- **Not checked in the game yet**: whether a changed `PersonChapter.level` shows on the map as the new level (the
  table reader says Unit::CreateFromDispos uses the person's level when the placement level is 0), and the extra
  EXP from higher-level enemies. The robot check in step 7 answers both.
