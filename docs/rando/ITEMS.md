# Randomizer track "items" (round 49, F-043 #1)

**For the owner.** This track changes the items people start with, what the castle shops sell, and the
castle's battle and visit rewards. Chests and villages are not in the game's tables (each chapter's script holds
them), so this track cannot change them yet. Nothing a story scene needs is touched. Same seed, same result. Off
means the original game. Status 2026-11-20. **Nothing counts as done until you say ok (F-037).**

Our own code (`tools/randomizer/items.py`). The public randomizers (Ignis and the others, GPL) were read for facts
only. No code was copied.

## 1. What changes

Only cells of rows that already exist. No new rows. No prices changed.

| Switch (default) | Table and cells | What it means in the game |
|---|---|---|
| `inventories` (on) | DisposUnit `item_1..5` of the player's own placements (team 0) of the people slice 1 randomizes | starting items. A bought weapon becomes another bought weapon the person's (new) class can use. A healing staff becomes another healing staff. A healing item, tonic or stat booster becomes another of the same sort, at most twice the price. The person gets the same new item in every chapter they join. |
| `shops` (on), `shop_sides own\|mixed` (own) | Item `dawn_stock`, `dusk_stock`, `rod_stock`, `staff_stock` (`.lv1..lv3`) | what the four castle shops sell at shop level 1, 2 and 3: the Hoshido and Nohr armories, the Hoshido and Nohr item shops. Inside one shop, items of one **band** trade their stock pattern. A band is one weapon type at one rank, or one staff rank (healing or not), or one sort of item. So each shop level keeps the same number of goods per band, and every price is still the item's own. `mixed` also lets a shop take items the other side's matching shop sold. |
| `rewards` (on) | AchieveBonusBattle / AchieveBonusVisit `item` | the castle rewards for battles won and castle visits. Each becomes an item of the same band. Within a list the same item is not given twice when another fits. |

Never changed, moved, or newly placed: personal weapons, legendary weapons, story items (precious, chapter-only,
can't remove), door keys and chest keys, money items, trophies (Battle Seal, Visitation Seal, Master Emblem),
dragonstones and beaststones, every seal, enemy-only items, and downloadable items. Story-fixed people keep their
starting items: Corrin, Azura, the four royals (with keep-royals on), and anyone in a special class. Slots that
the game gives only at some levels (`item_N_flags` bits 1-4) are left alone.

**"Master Seals only" for Fates.** In Sacred Stones this option turns the class-specific promotion items into
Master Seals. Fates has no such items in the normal game: the Master Seal already promotes every class. The only
class-specific seals here are the downloadable ones (Dread Scroll, Ebon Wing, Sighting Lens, Witch's Mark), and
this track never places those. So the Fates version of the option is simpler: **every seal (Master, Heart,
Partner, Friendship, Eternal, Offspring) keeps its shop stock and stays wherever a person starts with it.** The
seal supply is the original game's on every route. No separate switch is needed.

## 2. The guards (each one is re-checked from the output alone, `check_items`)

| Guard | How it is kept | Test (tests/test_rando_items.py) |
|---|---|---|
| Same seed, same output | the track's own random stream: SHA-256 of (tool version, seed, "items", this track's own switches); one stream per purpose and person/shop/reward row; no clock, no dict order. Another track's switches cannot move this track's results | `test_same_seed_same_output_and_seeds_differ`, `test_track_independent_of_slice1_switches`, real data `test_same_seed_same_bytes` |
| No unusable starting weapon | if the person could use the old weapon from the moment they join, the new one must be usable with the same weapon exp (after slice 1). If the old weapon only became usable through a later chapter's own person record (a route join at a higher level), the new one is the same type and rank | `test_no_unusable_starting_weapon`, guard `starting_items_usable_and_story_kept` |
| Every route keeps healing | healing staves stay healing staves; healing items stay healing items. Vulnerary, Heal and Bloom Festal keep their stock in every shop. A shop that sold healing at level 1 still does. Per route, someone on the player's side carries healing | `test_healing_and_door_opening_kept_per_route` (also the made-up route whose only healer is one person), guard `healing_and_doors_per_route`, `shops_sane` |
| Every route keeps door opening | door keys are never moved (counted per route, before = after). The lock skill (thieves) is a person skill, which this track never edits. Slice 1's `door_opener_per_route` guard covers classes | same test; `test_guard_catches_bad_edit` (removing a key fails) |
| Prices sane | no price cell is written. A band trades only among items with a price. Nothing with no price is ever sold. A level-1 slot can only go to an item of the same band, so a rank-A weapon cannot become a level-1 good | `test_shops_sane` |
| No downloadable or story items placed | only items with legal_player_weapon 1 or 2, no story/key/enemy/personal flags | `test_no_dlc_or_story_items_placed`, `test_rewards_same_band` |
| Off = original | all three switches off give no edits at all | `test_off_means_nothing`; robot check below |
| The mods tool accepts it | slice 1 + items written as one mod folder, then diffed by tools/mods | real data `test_mods_tool_accepts_the_folder` |

`python -m unittest tests.test_rando_items`: 13 tests OK (10 on made-up tables, 3 on the real tables; 40 seeds x 4
switch sets x 2 fixtures, and 12 real seeds x 3 switch sets, with every guard PASS). `tests.test_randomizer` still OK.

## 3. Numbers for one seed (i49a, defaults, on top of slice 1)

856 placement rows rewritten (122 different starting items changed, e.g. Kaze's Vulnerary -> Concoction, Charlotte's
Heal -> Bloom Festal). 31 Item rows changed in the two armories (own sides; the item shops' only band with room,
Concoction/Elixir, came out unchanged for this seed). 57 + 57 rewards changed. With `mixed`, seed i49m: 95 Item
rows, both item shops changed too. All guards PASS. Spoiler log: the mod folder's `spoiler.txt`, after slice 1's
part.

## 4. Robot check (round 49, one job, the robot's own test game only)

2026-11-20. The STOP file was checked before the start. One headless server at a time, below normal, no window.
Data folder, APPDATA and LOCALAPPDATA all under `build/rando49/items/server/`. Only memory reads. No writer, no
pokes, no new play.

- **Mod:** `python tools/randomizer/items.py make --seed i49a --out build/rando49/items/robot_mods` (slice 1 +
  items only), then `mods.py --mods-dir build/rando49/items/robot_mods --stage-dir build/rando49/items/stage
  --zakuro-dir build/rando49/items/zak install`. That is 2890 cells and 101 files; log `build/rando49/items/install.log`.
- **Job:** `python tools/randomizer/items.py robot --mod build/rando49/items/robot_mods/Rando-i49a`. Results in
  `build/rando49/items/robot.json`, pictures in `build/rando49/items/shots/` (not tracked).
- **Runs:** `mod`, then `mods.py uninstall` + `disable` (both rc 0, **0 files left**), then `off`. Each run: save
  bt-ch1-clear, the recorded bt-ch2 presses up to frame 5117, memory read at 4800, 5117 and 5300 (round 47's ch2
  frames). The Chapter 2 map, before the first move. About 18 s and 15 s.

| Check | mod | off |
|---|---|---|
| Item records in memory (found from the Person block plus the file offset; every record's number and name checked): the 12 stock bytes of all 355 items, plus the 160 reward rows' item | 515 checked, **0 mismatches** at all 3 reads, equal to the plan (31 changed items, 114 changed rewards) | 515 checked, **0 mismatches**, equal to the original |
| Units who join in Chapter 2: their five item slots (Unit +0x108) | Gunter (Sorcerer from slice 1) carries Ox Spirit; Felicia (slice 1's new class) carries Iron Club and Rat Spirit. Both equal the plan, **0 mismatches** | Gunter Iron Lance; Felicia Iron Dagger and Heal (the original) |
| Slice 1's 49 Person rows | 0 mismatches | 0 mismatches (original) |
| Whole-memory hash at frame 5300 | `3bf00458ef318071...` | `74eb98e65d597c4e...`. This is **the same** as round 47's no-mod run (rc-none ch2, same Zakuro 0.2.32), so **off = original** |

Said plainly: Jakob was not on the map at these frames, as in round 47. His items were checked in the table only.
Corrin's items come from the save, so they were not compared. Shop menus were not opened (no new play). The stock
was read from the Item records the shop code reads (shop::Data::UpdateStock reads Item +0x4C). Which route uses
which shop pair was not checked in the game. The guard keeps healing in all four shops, so every route is covered
either way.

## 5. Not done (said plainly)

- **Chests, villages, houses, story gifts.** These are in each chapter's event script, not in a table (docs/ROBOT.md
  notes a chapter's chest contents as strings in its script). Changing them needs a script codec. That is a separate step, and it needs
  your OK.
- **Enemy drops** belong to the enemy-gear track. **The castle's random-gain and lottery pools**
  (`Item.pool_rank`) are unchanged: their effect was not checked in a running game.
- **Route-join records.** The per-chapter Person files (`GameData/Person/*`, used when someone joins later on a
  route) are not read by slice 1 or by this track. That is why a weapon usable only through such a record keeps
  its type and rank.
- Shop goods per level keep the original counts. A band's cheapest unlimited good may become a limited one; the
  band keeps the same number of goods.

## 6. For the integrate step

`plan_items(facts, rng, opts) -> (edits, spoiler_lines)` with `rng = items.sub_rng(seed, "items", track_opts)`.
`opts` takes `inventories`, `shops`, `shop_sides`, `rewards`, `slice1_plan` (so starting items are chosen for the
new classes and over slice 1's weapon swaps), and `achieve` (`items.load_achieve()`). Edits are
`{"table", "file" (DisposUnit only), "index", "label", "cells"}`. This track writes all five item cells of a
placement, built on slice 1's values, so they replace slice 1's row for that placement. `check_items(facts, edits,
opts)` returns the guards. `edits_to_files(facts, edits, slice1_files)` is how this track's own robot mod was
written; rando.py may reuse it or merge its own way. Page wording for the switches: "Starting items", "Shops"
(own side / both sides), "Castle rewards".
