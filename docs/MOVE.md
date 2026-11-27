# Movement and terrain (Fates): what a tile is, what a step costs, who stands where, read from the code

**In plain words.** Every time a unit is selected the game works out where it may go: which tiles
it can enter, what each step costs it, which tiles are taken by other units, and where a route
ends. The cursor's terrain window, the AI's choice of a good tile and the chapter scripts ask the
same questions about the map. This batch rewrites 24 of those small questions as readable C: the
terrain record of a tile, the movement cost of a terrain for a unit, whether a unit ignores
terrain costs, the cost and end point of a route, whether the move-range fill may spread through
a tile, the unit standing on a tile, the map's playable area, whether a class flies or rides, and
how much the AI likes a tile's terrain.

All 24 are **readers**: they store nothing (F-017, F-018, F-021: no writer, nothing armed). They
are a round-10 rewrite batch, written while the robot runs, with host builds only.

Status 2026-11-14: 24 readable overrides (`src/readable/move/`), all **UNVERIFIED** in the
project's sense. Every one gives the same answers as the game's own ARM code on made-up cases,
with the same guest calls in the same order and the same unmapped reads (section 7); every bug
planted on purpose was caught. Not yet in a live compare: the round-10 integrate rebuilds the
capture library with these rows. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-14) [high unless marked]. No table values or game text are copied here; flag, skill and
class names are the game's ID labels (`SPID_`, `SEID_`, `ISID_`, `JCID_`, `JID_`) given in
English [med for the English].

---

## 1. Where the terrain lives

- The **map image** (the global at 0x006D73E8, `MapImage` in config/readable/structs) holds the
  map's width and height (bytes 0 and 1), its playable area (bytes 2..5: first column, first row,
  column after the last, row after the last) and several 32 x 32 grids, one byte per tile, tile
  number `x | y << 5`: the pool number of the unit on the tile (+0x8), the tile kind (+0x408) and
  the tile's movement-cost column (+0xC08). The game never checks the coordinates before it forms
  the tile number; neither does the readable code.
- **`Terrain::Get(int)`** (0x004E0AFC, `terrain_record`): the tile kind's record in the loaded
  chapter's terrain file: the tile table + kind x 0x28. A record (TerrainTile, docs/TABLES.md)
  gives the movement-cost column, defence, avoid and heal bonuses (signed bytes) and attribute
  bits. Attribute bit 3 is the one the movement code tests: such a tile is never part of a move
  range [high for the effect, med for "blocked" as the meaning].
- **`map::Cursor::GetTerrain(int,int)`** (0x0039B7E4, `cursor_terrain`): the terrain record of
  the tile under the cursor (the cursor object itself is not read; the game passes the tile kind
  on to `Terrain::Get`).
- **`Map::Get`** (0x00342574, `map_get`): the loaded map, 0 while none is. The script commands
  below answer "nothing" without a map.

## 2. Map size, playable area, terrain bonuses

- **Script `TerrainGetW` / `TerrainGetH`** (0x003A7BD0 / 0x003A7BAC): the map's width and height,
  0 without a map.
- **Script `TerrainIsOutOfPlayArea`** (0x003AE294): 1 when the tile is outside the playable area
  (or no map is loaded). The four bounds are signed compares, read one at a time, each only when
  the ones before passed.
- **Script `TerrainAttributeIsFlag`** (0x003AE12C): 1 when the tile is inside the playable area
  and its terrain has any of the given attribute bits.
- **`map::Camera::GetPlayAreaW` / `GetPlayAreaH`** (0x005270FC / 0x005270DC): the playable area's
  width and height (end minus first, kept to a byte).
- **`AIThink::GetTerrainScore(Unit*,int,int)`** (0x004CB124, `ai_terrain_score`): how much the AI
  likes a tile's terrain, 0 .. 63:

  ```
  score = 5 + avoid + defence / 5 + heal / 10      (divisions toward zero), then kept to 0 .. 63
  ```

  A unit of the class category "flying" (`JCID_` flying, via `Unit::GetCategory`) scores 0: terrain
  does nothing for it. On a tile with attribute bit 8 a unit with the skill labelled "lockpick"
  counts negative avoid, defence and heal as 0 [low for what that pairing means in play].
  This is the only place in this batch where the terrain's avoid / defence / heal numbers are
  read; the battle forecast gets them through `map::BattleInfo::Side` code that stores into the
  fight side (writers in this project's sense, section 6).

## 3. What a step costs

- The **TerrainCost table** (GameData) has one row per movement class (the class's
  `move_cost_class`, Job +0x5C) and one signed byte per terrain cost column; rows are padded to a
  multiple of 4 bytes. A negative cost means the class cannot enter.
- **`TerrainCost::Get(int)`** (0x001A67EC, `terrain_cost_row`): the address of a class's row.
- **`TerrainCost::GetCostFromUnit(const Unit*,int)`** (0x001A6708, `terrain_cost_for_unit`): the
  cost of a column for the unit's class. When that is negative and the unit, its Person or its
  class has the PersonFlag bit labelled "own terrain cost" (`SPID_`), the cost of movement class 0
  is used instead (which may be negative too) [high for the rule; med for the label's English].
- **`Unit::IsCostFree`** (0x0052AB90, `unit_is_cost_free`): the unit pays at most 1 for every
  passable tile when it is in the class category "shooter" (ballista classes) and has the skill
  labelled "amphibious", or when one of its five items carries the item-skill flag labelled
  "Fujin Yumi" (`ISID_`) and `Unit::IsItemEnhanceHave` says that item's bonus applies to it. The
  category is asked once; the items are asked slot by slot.

## 4. Routes

A route is a list of step bytes ending with 0x80: bit 0 = one tile left, bit 1 = right, bit 3 =
up, bit 2 = down (bit 0 wins over bit 1 and bit 3 over bit 2).

- **`map::Route::GetRouteCost(Unit*,int,int,const unsigned char*)`** (0x00394BC0, `route_cost`):
  the cost of walking the route from a start tile: for every tile entered, the unit's cost for
  that tile's cost column (+0xC08 grid); a cost above 1 counts 1 when the unit is cost-free (asked
  only then), a negative cost counts 0. This routine ends only on the exact byte 0x80; a byte with
  bit 7 and other bits set is a step here.
- **`map::Route::GetGoalX` / `GetGoalY`** (0x00395B50 / 0x00395B88, `route_goal_x/y`): where the
  route ends. These two stop at any byte with bit 7 set.
- **`map::Route::GetCross(int,int) const`** (0x0052650C, `route_cross`): the step number at which
  the stored route (its step count at +0x80, start at +0x81/+0x82) stands on a tile, or -1. The
  start is step 0; the tile reached by the last step is never compared, so asking for the route's
  end gives -1.

## 5. Who stands where, and the move-range fill

- `UnitPool::Get(int)` (0x004F6174, a guest call here, not rewritten, section 6): the unit of a
  pool number (1 and up; 0 gives no unit; no range check).
- **`map::Image::Unit::GetUnit(int,int) const`** (0x00526424, `image_unit_at`): the unit standing
  on a tile of a unit grid (the pool number at the tile, then `UnitPool::Get`).
- **Script `UnitGetByPosition`** (0x003ABE80, `script_unit_at`): the pool number of the unit on a
  tile (Unit +0xF0), 0 when nobody stands there or no map is loaded.
- **`map::Deploy::MoveImage::Get(int,int) const`** (0x005278A0, `move_image_get`): a move image's
  value of a tile (below 0 = not reached), but -1 on a tile whose terrain has attribute bit 3.
- **`map::Deploy::IsFill(int,int) const`** (0x00527734, `deploy_is_fill`): may the move-range fill
  spread through this tile?

  | Tile | Answer |
  |---|---|
  | terrain attribute bit 3, or not reached in the deploy's move image (below 0) | no |
  | the start (move image 0), or nobody stands there | yes |
  | someone stands there, deploy mode bit 2 | no |
  | mode bit 4, and the unit (or its Person or class) has the PersonFlag bit labelled "may not move", or bit 8 of Unit +0x54 | no |
  | mode bit 14, and the unit's force is not allied with the deploy's force (`Force::IsAllied`) | no |
  | otherwise | yes |

## 6. Flying and riding; not this batch

- **`Job::IsFlyer` / `Job::IsRider`** (0x00524980 / 0x00524A7C): the class is in the category
  "flying" / "mounted" (`JCID_`). In real play `IsFlyer` is asked by the map's route animation and
  `IsRider` by the arena; the move getters use `Unit::GetCategory` instead.
- **`Terrain::IsCastleUnitDispos`** (0x00545324): a castle unit may stand on a terrain with a cost
  column, without attribute bit 3, where the class labelled "armour knight (male)" (`JID_`) pays
  more than 0.

Not here, and why:

- `Unit::GetAttackForTerrain(int)` 0x005309A0 and `(const unit::Item*)` 0x00534180 (the attack
  against a breakable terrain object): already readable overrides of the battle-formula batch
  (`unit_attack_for_terrain_of_slot`, `unit_attack_for_terrain` in
  src/readable/battle/formula_unit.c, with their host diff there). Not duplicated.
- `Unit::GetMovePower` (the move stat) is the sheet batch's `unit_move`; `map::trick::Data::IsAccess`
  and the dragon-vein readers are the vein batch's. Not duplicated.
- `map::Actor::GetTerrain` 0x0052633C (the terrain under a unit's map figure): it converts the
  figure's float position with VFP instructions and leaves the converted values in s0/s1. Readable
  C does not touch VFP registers, so tier 2 would show "vfp state" as a MISMATCH that is no
  difference in results. Left out until the classifier owner decides on that shape.
- `map::Deploy::Move`, `FillRod`, `UnitMove`, `RangeAround` and the other range builders: they
  fill the move images (writers). `map::BattleInfo::Side::ComplementConditions`,
  `CalculateDetailAvoid`, `CalculateDetailDefense` (where the forecast adds terrain avoid and
  defence): they store into the fight side.
- `UnitPool::Get` 0x004F6174: written, host-diffed, and then taken out again. `map::Mind::GetTradeUnit`
  (0x004F616C, two instructions) falls through into it, so 3dsrecomp's verify cannot pick the address
  on its own (tier 2 said NOT-RUN with no holder in the build's entry table). The vein batch's
  helper of the same name does the computation inline; the readers here call it through the guest.
- `AIThink::GetMovePowerSlow` and the script's `UnitGetMovePower`: thin wrappers around the move
  stat with a difficulty or unit-number test; a later batch can take them with the AI readers.

## 7. Checks

**Host differential test** `python src/readable/move/tests/move_diff.py` (the sheet test's method
and ARM interpreter, with tail branches listed as calls and USAT added in the test's own CPU
subclass): made-up maps, terrain tables, cost tables, units, routes and deploys with values outside
the game's ranges on purpose (coordinates off the map and far off it, tile kinds past the table,
cost columns past the row, padded and huge column counts, route bytes with bit 7 and other bits
set, negative terrain numbers, unmapped units and records). For each override it compares r0, the
unmapped reads and the list of guest calls with their argument registers in order; a nested
give-up is a mismatch. `Unit::GetCategory` runs as ARM code on one side and as the sheet batch's
override on the other; this batch's own callees (`Terrain::Get`, `Map::Get`,
`Image::Unit::GetUnit`, `GetCostFromUnit`, `IsCostFree`) likewise.

Results 2026-11-14:

| Run | Cases | Mismatches | Planted bugs |
|---|---|---|---|
| default (`--plant`, seed 20261114, 300 per function) | 7,200 | 0 | 47/47 caught |
| long (`-n 1500 --seed 7`) | 36,000 | 0 | - |

What the test found while it was written: the first `route_cost` asked only its own caches; when
`GetCostFromUnit`'s or `IsCostFree`'s cache was cold the inner override would have given up inside
it (a nested give-up). Every reader that calls an override with caches now asks those caches in
its opening test (as the sheet batch's move getter does for `GetCategory`), so a cold cache gives
up before anything is read.

**Tier 2**: section 8.

## 8. Tier 2 and where these will be met

**Tier 2** (2026-11-14, `python tools/readable/verify.py --only <the 24 addresses> --out
build/readable/verify_move`, below-normal priority, library build 531 s): **`readable-verify: OK`:
1 CLEAN, 15 ABI-ONLY, 7 GAVE-UP, 1 UNSAMPLED, 0 MISMATCH, 0 NOT-RUN.** No classifier change.

- CLEAN / ABI-ONLY (`map_get`; `terrain_record`, `terrain_cost_row`, `cursor_terrain`, the four
  script readers, both camera readers, `route_goal_x/y`, `route_cross`, `image_unit_at`,
  `script_unit_at`, `move_image_get`): differences only in r1-r3, r12, lr, flags and dead stack.
  The shadow passes' unmapped-read surpluses are the shapes the classifier already accepts (exactly
  twice the count; or the readable code of the nested `terrain_record` with its shadow match logged).
- GAVE-UP (`terrain_cost_for_unit`, `unit_is_cost_free`, `ai_terrain_score`, `job_is_flyer`,
  `job_is_rider`, `deploy_is_fill`, `terrain_is_castle_unit_dispos`): verify's made-up memory has
  every one-time cache cold, so the readable code gave up and the original ran, as in every earlier
  batch. Proves nothing either way; the host test and the live compare cover them.
- UNSAMPLED (`route_cost`): in verify's made-up state the route never reaches its 0x80 end byte,
  so the game's own code runs past verify's instruction limit in both passes; nothing compared.
- A first run with 25 functions had one NOT-RUN, `UnitPool::Get`, now taken out (section 6).

Expected in real play [med, not yet run]: `terrain_cost_for_unit`, `unit_is_cost_free`,
`route_cost`, `deploy_is_fill`, `move_image_get` and `image_unit_at` every
time a unit is selected and moved (the move range, the route, `ProcSequence::UnitMove`);
`cursor_terrain` and `terrain_record` with the terrain window; `ai_terrain_score` on every enemy
phase; the script readers in chapters whose scripts ask them; `job_is_flyer` in the route
animation. None was run in a live compare in this batch (no robot runs: round 10 uses all 12).

## 9. Live compare, round 10 integrate (2026-11-15) [high]

The first live compare of this batch (session r10-cap, all 37 verified real-play routes, library with all 203
overrides) found **one fault: `cursor_terrain`**. Every one of its sampled records (20 to 29 per route, 866 in all)
was a `mismatch_calls`: the readable code listed a guest call to `Terrain::Get` that the original does not make.
Results, memory and every other override were equal (every route's memory hash as before, all checkpoints met).

Why: `map::Cursor::GetTerrain` ends with a plain branch (`b Terrain__Get_004E0AFC`), not a call. 3dsrecomp keeps
the target's code inside the caller's generated function (the library's `f_0039B7E4` dispatches `0x004E0AFC` to
its own label), so in the library the original never enters the `terrain_record` override from there. The support
batch met the same thing in tier 2 and runs the C of such targets directly (docs/SUPPORT.md); this batch's tier 2
did not show it (`cursor_terrain` was ABI-ONLY there). The host test listed the tail branch as a call, so it agreed
with the wrong version.

Fix: `cursor_terrain` now returns `terrain_record(ctx, tile_kind(ctx, x, y))` (no guest call), and move_diff.py
runs a tail branch to an override on as ARM code, unlisted (a tail branch to a stubbed guest function is still
listed: `image_unit_at`'s branch to `UnitPool::Get` matched live, 891 records, as did the support batch's tail calls
to guest functions). The planted bug for that line now swaps x and y in the new line. A search of every round-10
override's code for tail branches found no other one whose target is an override.

**An assumption to re-check in every batch (round 11, tools-fixes) [high that it is an assumption].** move_diff.py's
`ListingCpu.step` (and support_diff.py's, which does the same) treats EVERY tail branch (`B`, no link) to an override
as inlined: it runs the target on as ARM code and lists no call. That is what 3dsrecomp did for the three cases seen
(`f_0039B7E4` -> `0x004E0AFC`, and `f_0052F518` -> the three level getters, docs/SUPPORT.md 7), but it is the
recompiler's choice per caller, not a rule of the game: a target the recompiler does NOT pull into the caller is
entered through the dispatch, so its override runs and the live compare lists the call. If that happens, the host
test (no call listed) and the readable code (no guest call) agree with each other and are both wrong, and only the
live compare shows it, as it did for `cursor_terrain`. So for each new batch, before trusting the host test on a
tail branch to an override: look the caller up in the tier-2 build's `lib/entries.c` and generated code. Inlined
means the target's internal labels are listed under the caller (`{0x004E0B..u, f_0039B7E4}`) and the caller's
code reaches the target with a plain `goto L_<target>`; a `target = 0x...; goto dispatch` (or no such labels)
means the override is entered, and the readable code must make the guest call and the test must list it. A tail
branch to a stubbed guest function (no override) is always listed and called; that part does not depend on this.
