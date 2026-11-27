# Randomizer track "misc": enemy drops, assign evenly, class movement

Round 56, F-046 ("build the other missing parts too"), 2026-11-20. Module `tools/randomizer/misc.py`, tests
`tests/test_rando_misc.py`. **Built as a module with tests. Not wired**: there is no page row, no `rando.py` flag and
no spoiler section yet. The integrate round does that (section 4). Nothing counts as done until the owner says ok (F-037).

## 1. For the owner

This covers three rows from the FE8 port's Randomizer screen that Fates did not have. **Enemy drops**: you choose a
chance (5 to 100 %). Each ordinary enemy then has that chance of carrying one of its own items as a drop, which you get
when you defeat it. Drops the game already has stay as they are. Story items, personal weapons and enemy-only gear never
become drops. **Assign evenly**: when classes are randomized, the classes are spread out, so the same class (male and
female counted as one) does not turn up three or four times in one route while other classes are never used. **Class
movement**: each class's Move changes a little, by 1 (small) or up to 2 (wide). Armor stays slow, at most 5. Fliers,
horses and beasts stay fast, at least 5. A promoted class never has less Move than the class it comes from, and the male
and female versions of a class always match. A class keeps its Move whenever a lower value would leave an enemy stuck
(the same rule the enemy track uses). Because of that rule, Move goes **up** much more often than down (see section 6).
With all three left off, nothing changes and seeds stay byte-identical. Host checks only so far; nothing has been tried
in the game.

## 2. Facts (read from the code, docs/TABLES.md and the user's own tables; counts only, no game values)

- **The drop mark is bit 0 of `DisposUnit.item_N_flags`.** `Unit::SetDisposItem` 003D8C38 turns it into bit 15 (0x8000)
  of the unit's item (`unit::Item+0x2`), **except** for an item with `ISID_敵専用` and no `ISID_即換金` (enemy-only gear
  never drops; gold does). `map::SequenceBattle` `ProcSequence::ItemDrop` 0035C548 tests that bit on the loser's items.
  `UnitItemClearDrop` 003AC058 clears it on all of a unit's items. (Asm read: `asm/text/text_003D5AE0.s`.)
- In the original tables 348 item slots have the mark. All of them are on team 1 (enemies). 345 units carry them, 3 of
  those with two. 195 are items and 153 are weapons. None has level bits, and all but one have no forge.
- If a slot with the mark is forged, `SetDisposItem` splits it: the unit keeps the forged weapon and a plain copy, which
  is the drop, goes into a free slot. If no slot is free, the copy is lost. Bits 1-4 of the flag byte give the item only
  at some levels. **So this track never marks a forged slot or one with level bits.** It also skips a slot that is not
  given on every difficulty (any forge cell not 0).
- `Job.mov` (+0x5D) is the class's Move (`Unit::GetMovePower` 0052D5E4). Job rows in the real data: Move 4 to 8 (the empty row 0 aside).
- The no-stuck rule is the enemies track's (docs/rando/ENEMIES.md): over the chapter's own terrain grid, with the
  TerrainCost row `Job.move_cost_class`, the unit must reach at least 3/4 as many tiles in 3 turns as it did before.
- Slice 1 draws each person's class first. Job_low, weapon exp, bases, growths and carried weapons all follow from that
  class (`randolib.make_plan` steps 1-4). **So "assign evenly" cannot be a cell edit after the plan is made.** It has to
  give slice 1 the classes and let slice 1 run its later steps again (section 4).

## 3. What is built

### 3.1 Enemy drops: `plan_drops(tables, seed, opts)`, `run_drop_guards`

- Option `enemy_drops`: `0` (off, the default) or 5-100 in steps of 5. `check_opts` also accepts `"25%"` and `"off"`.
- Scope: the enemies track's own scope (`EnemyTables.out_of_scope` / `scripted`). That means team 1 units of the Enemy\*
  and Reinforce\* groups in story chapters, and never in the four guarded chapters (Conquest 9 and 16, Revelation 8 and
  13). Named cast, story versions, units the script names and Event groups are never touched. A boss the script names
  can get a drop: that changes nothing in the story. A unit that already drops something is skipped.
- Each unit in scope rolls its own stream: `sha256(key, "drop", file#index)`, with key = `track_key(seed)`. On a hit,
  one slot gets the mark: an ordinary item (vulnerary, seal, gold) if the unit carries one, else an ordinary weapon.
- Never marked: an empty slot, an unknown item, an item with any `replacement_refuse_item_flags` (enemy-only,
  chapter-only, precious, legendary, cannot-remove) or any `…専用` flag (personal / class-only), level bits, a forge.
- Edits: `{"table": "DisposUnit", "file", "index", "label", "column": "item_N_flags", "old", "new"}`, where new = old | 1.
- Guards: `drops_only_on_ordinary_items_of_unscripted_enemies` (the column, the old value, only bit 0 added, scope and
  item rules re-checked from the edits alone), `at_most_one_new_drop_per_enemy`, `drops_off_no_edits`.
- Real tables, seed m56a at 20 %: 3857 enemies in scope, 599 got a drop. At 100 %: 3058. The rest carry nothing
  that may be marked. All guards ok.

### 3.2 Class movement: `plan_movement(tables, seed, opts)`, `run_move_guards`

- Option `class_move`: `off` (default) / `small` (±1) / `wide` (±2).
- Classes: every normal class of a side (`Job.origin` 1 or 2, not `excluded_job`, has a weapon). Story classes,
  enemy-only classes, monsters, dragons, the Songstress, Villager and downloadable/special classes keep their Move.
- The male and female rows of a class (the label without its trailing 男/女) get one draw. If the two rows already
  differ in the original, the class is left alone.
- Bounds by kind (from `Job.category`): armor 3-5, foot 4-7, mounted / flier / beast 5-8. The original value is
  always allowed, even outside these.
- Base classes are drawn first. A promoted class's minimum is the highest new Move of the base classes that promote
  into it (`promotion.1/2`). A second pass lifts a promoted class again if the no-stuck rule raised one of its bases.
- **No stuck enemies:** when a class would lose Move, every team 1 or 2 unit of that class standing on a known tile
  in any chapter is checked with the new Move. If one would reach less than 3/4 of its tiles, the next value up is
  tried, until the original. The spoiler names each class where this happened.
- Edits: `{"table": "Job", "index", "label", "column": "mov", "old", "new"}`.
- Guards: `only_mov_of_normal_classes`, `movement_off_no_edits`, `move_within_bounds`,
  `promoted_never_slower_than_its_base`, `male_and_female_rows_move_together`, `no_stuck_enemies` (recomputed).
- Real tables: wide m56a gave 52 rows changed (50 up, 2 down), and 9 losses were made smaller. Small m56b gave 43 up
  and 0 down; small m56c gave 39 up and 2 down. All guards ok. A host run takes about 3 s for all three parts.

### 3.3 Assign evenly: `assign_evenly(facts, plan, seed, opts)`, `make_plan_even`, `run_even_guards`

- Option `assign_evenly`: off (default) / on. It does nothing when slice 1's `classes` switch is off.
- Input: slice 1's finished plan. Output: `{pid: class}` for every person whose class slice 1 may change (not `kept`).
- Method: people with the fewest legal classes choose first (then by index). Each person takes a class whose highest
  use count across that person's routes is the lowest. Slice 1's own pick is kept whenever it is among those; other
  ties are drawn from `sha256(key, "even", pid)`. Story-fixed people (Corrin, Azura, keep-royals) count toward the
  totals but never move. The male and female rows count as one class.
- Route roles: if a route had a staff user or a lock opener in slice 1's plan and loses it, slice 1's pick comes back
  for the first person whose slice-1 class had that role.
- If the pass would leave any route more crowded than slice 1 had it, slice 1's classes are kept, and the spoiler
  says so. This happened in 0 of 40 real seeds (20 seeds × trees own/any).
- `make_plan_even(facts, seed, sw, opts)` runs slice 1, then runs it again with the even classes. That way job_low,
  weapon exp, stats and carried weapons follow the new class. Guards are recomputed with the real `Facts`, plus
  `misc: story_fixed_people_unmoved`, `even_classes_legal`, `no_route_more_crowded` and `route_roles_kept`.
  It does this through a small `Facts` subclass (`_EvenFacts`). Only the plain `legal_classes(p, sw)` call is narrowed
  to the even class, so the draw in step 1 lands on it. The job_low lookups (`promoted=...`) see every class, as before.
  **This is a bridge.** See section 4.
- Real tables: 9 to 17 of 41 people moved per seed. Most-used class per route went from ×3/×4 down to ×2. All guards ok.

### 3.4 Writing the cells

- `job_csv_with_edits(facts, files, edits)` adds a `mov` column to `tables/Job.csv`, or makes a new file. The promotions
  track's rows and its `promotion.1/2` columns are kept. Rows it did not write get the original Move.
- `dispos_csv_with_edits(dispos, files, edits)` adds the `item_N_flags` columns to `tables/DisposUnit.csv`. The rows and
  cells other tracks wrote are kept, and only the flag columns are filled.

## 4. How to wire it (the integrate round; owner of tracks.py, rando.py, ingame.py, rules.json, RANDOMIZER.md)

1. `tracks.DEFAULT_TOPTS` / `CHOICES` / `BOOLS`: `enemy_drops` (choices `off,5,10,...,100`, default `off`),
   `class_move` (`off/small/wide`, default `off`), `assign_evenly` (bool, default off). `rando.py make` flags:
   `--enemy-drops`, `--class-move`, `--assign-evenly`. `tools/play/rando.py OPTIONS` labels (suggested): "Enemy drops
   (chance)", "Class movement (small = ±1, wide = ±2)", "Assign classes evenly". In "Everything on", use
   `enemy_drops=10`, `class_move=small`, `assign_evenly=on`. `ingame.schema()` then picks them up from `PR.OPTIONS`.
2. `misc_opts(o) = {"enemy_drops": o["enemy_drops"], "class_move": o["class_move"], "assign_evenly": o["assign_evenly"]}`.
   `active()`: add `"misc": misc.active(misc_opts(o))`. Seeds with these options at their defaults must stay
   byte-identical (r50def / r50all).
3. **Assign evenly, the proper way.** Give `randolib.make_plan` an optional `classes: dict | None` argument. In step 1,
   when `pid in classes`, use that class instead of the draw. It must be in `legal_classes(p, sw)`, else RandoError.
   Then `tracks.make_all` does: `plan = R.make_plan(...)`; if assign evenly is on,
   `classes, lines = misc.assign_evenly(facts, plan, seed, mo)` and `plan = R.make_plan(facts, seed, sw, classes=classes)`;
   then add `misc.run_even_guards(facts, plan_before, plan)` under `misc: `. Delete `_EvenFacts` and `make_plan_even`
   once that exists, or keep `make_plan_even` as a thin wrapper. This comes before every other track: growth, skills,
   promotions and children all read the final class.
4. Drops and movement come after the enemies track, so the enemy classes are final. Use
   `misc.plan_drops(t, seed, mo)` and `misc.plan_movement(t, seed, mo)` with the same `EnemyTables`. Run
   `run_drop_guards` and `run_move_guards` with exactly the opts the plans used. **Known gap:** the no-stuck re-check
   reads the *original* enemy classes. With enemy classes on, pass the enemies track's `jid` edits in. The simplest
   way is to apply them to a copy of `t.dispos` before calling `plan_movement` and `run_move_guards`. Add a cross guard
   that runs the stuck rule with both the new classes and the new Move.
5. Files: `files = misc.job_csv_with_edits(facts, files, m_edits)` after the promotions track. Then
   `files = misc.dispos_csv_with_edits(facts.dispos, files, d_edits)` after `_dispos_csv`. Or teach `_dispos_csv` the
   `item_N_flags` columns; then the "written by two tracks" check covers them too. Spoiler: one `_section` per part.
   In `mod.json`: `randomizer.topts` / `tracks.misc = "rando-misc-v1"`.
6. The mods tool must accept `tables/Job.csv` with a `mov` column and `tables/DisposUnit.csv` with `item_N_flags`
   columns. Both are ordinary cells in the table registry (docs/TABLES.md), but the mods tool has not been run with
   them yet.

## 5. What needs the core or the game later

- **In-game check (robot, a later round):** an enemy marked by this track drops its item when defeated (green name in
  its inventory, item gained). A class with new Move moves that far, for the player and for enemies.
- **F-047 / the Seal edition:** every function takes its tables as a passed-in object (`EnemyTables`, `Facts`). The scope
  test (`STORY_FILE`, `GUARDED`) and the bounds live in `enemies.py` and here. For another story, the tables object
  should carry its own chapter pattern and guarded list. That is a change to `enemies.py`, so it belongs to the wiring round.
- Enemy drops are deterministic per seed, the same in every playthrough of that seed. A drop chance rolled live, like
  FE8's, would need an engine hook. Not planned.

## 6. Open question for the owner or Grok (player-facing)

With the no-stuck rule as it is (3/4 of the tiles in 3 turns), losing even 1 Move almost always fails on open ground.
On an open map, 5 to 4 Move covers about (12/15)² = 64 % of the tiles. So "class movement" in practice makes classes
**faster** or leaves them as they are, and that makes enemies faster too. There are two other ways to do it:
(a) check the stuck rule only for losses below the class kind's floor; or (b) let player-only classes move down freely
and keep the rule for classes that enemies use. Today the build follows the rule as written. This needs a decision
before the row goes on the page.

## 7. Tests

`python -m unittest tests.test_rando_misc` runs 21 tests. 19 use made-up tables, borrowed from the slice-1 and enemies
tests. 2 use the user's own RomFS (skipped without it). All passed on 2026-11-20 (about 20 s). They cover: off makes no
edits and slice 1 stays byte-identical; bad options are refused; the sub-seed; drops guards over 40 seeds × 3 chances;
which slot gets marked (item before weapon, existing drop, precious, forged, enemy-only, scripted, event, other army,
guarded); the guards catch bad edits; the CSV merges keep other tracks' cells; movement guards over 40 seeds × 2 modes;
bounds, gender pairs, promoted ≥ base and the no-stuck rule; assign evenly guards over 3 table sets × 30 seeds × 2 tree
modes; an even spread (max − min ≤ 1) when everyone has the same choices; the plan follows the even class; story people
and route roles stay; real seeds pass every guard.
