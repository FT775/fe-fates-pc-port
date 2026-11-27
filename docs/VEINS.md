# Dragon veins: how they work, read from the code

**In plain words.** Some maps have dragon veins: marked tiles where certain units (the royals)
can use a map command, and something happens to the map: a river dries up, a path opens, a
wind blows. This note says how Fates does it, from the game's own code, and which parts now
have a readable C version (the third batch of the readable rewrite, plan step 9, after the
stances and the weapon triangle).

Status 2026-11-11: 7 readable overrides and 1 helper written, all **UNVERIFIED** in the
project's sense (tier 2 below is a smoke test, not a shadow run). They are all readers: nothing
here can fire a vein or change the ground. Every one of them gives the same answers as the
game's own ARM code on generated inputs (section 7: 3,200 and 12,000 cases, 0 mismatches), and
35 of 35 planted bugs were caught. Tier 2 on all 35 overrides: 0 mismatches. Nothing changes in the game.

Confidence tags: **[high]** read in the code and tested against it, **[med]** read in the code
but its meaning is an inference, **[low]** a guess. No chapter's vein list or effect is copied
here: which veins a chapter has is chapter data (its script), and a list would be a walkthrough.

---

## 1. Words

| In this note | In the game's code (symbol map) | What it is |
|---|---|---|
| gimmick | `map::trick::Data` (0x1C bytes) | one map gimmick: a vein, a region a vein changes, a cannon, a breakable wall ... |
| gimmick list | `map::Trick` (`G_Trick` 0x006D7FEC) | the current map's gimmicks, a linked list |
| gimmick type | `map::trick::Type` (`Data +0xC`) | 11 = dragon vein, 12 = a region a vein changes, 25..27 = cannons, ... |
| gimmick state | `Data +0x16` | bit 1 usable, bit 2 used (done), bit 4 ruined |
| vein command | `map::anonymous_namespace::TransformTerrain` | the map menu entry; its name message is the vein one |
| who may use one | `Unit::CanDragonVein` | a personal flag bit on the unit, its Person or its class |
| search | `map::trick::Enumerator` | "which gimmicks are at / reachable from this tile, of this type and state" |
| region list | `Data +0x18` (a string) | the regions a vein changes: "x,y,x,y..." or None / All / EnableAll / DoneAll / RuinAll |
| preview | `map::trick::Data::SetDeploy` | marks, on a 32x32 bitmap, the tiles a vein will change |

## 2. Where the veins of a chapter come from

[med for the meaning, high for the code path] When a map starts, `map::Trick::Regist(bool)`
0x003963BC builds the gimmick list from the chapter's script (the cmvm event script of that
chapter): it walks the script's functions of kind 21 (the tile events that `event::Poke`
triggers), then those of kind 22, and makes one `trick::Data` for each, with the position,
size, type and the region string from the function's arguments. So **a vein and its effect are
one script function**: the event declared on that tile with type 11. Using the vein runs that
event (section 4). There is no table of vein effects in the code.

The new gimmick's state is "usable", except in two cases read in `Regist`:

- when a game-mode bit is set (`GameUserData +0x28` bit 1, value 2), almost every gimmick type,
  **veins (11) and their regions (12) included**, is created already **done**; [med: which game
  mode sets that bit was not traced];
- in a versus map (`map::Situation::IsVersus`), a list of other types is created done (veins are
  not in it).

## 3. Who may use a vein, and where

**The unit** (`Unit::CanDragonVein` 0x0052DFE8) [high]: the unit's own personal-flag word, its
Person's and its class's (`Unit +0x0`, `Person +0x0`, `Job` flags) are ORed and tested against
one bit the game looks up by name once and caches (a `SPID_` flag named for dragon veins,
config/tables/PersonFlag.csv). So who may use a vein is data, not a formula. One more rule:
a unit whose state bit 28 (`Unit +0x8`, 0x10000000) is set may use a vein only if its Person
is also a download person (`Person::IsDownload` 0x0053DFEC: a second cached flag bit, or the
Person's number lies in a loaded Person block marked as a download block that is not the first,
resident block) [high for the code, low for what bit 28 means].

**The tile** [high]: a unit can use a vein when it stands in the vein's area. The area is the
gimmick's rectangle (`Data +0x8..+0xB`: x, y, width, height), not only one tile;
`trick::Data::IsAccess` 0x00526BA0 says which tiles reach which gimmick type:

| type | a unit on (x, y) reaches it when |
|---|---|
| 25..27 (cannons) | (x, y) is the one tile beside the cannon its side byte (`+0x15`: 1 left, 2 right, 4 below, 8 above) names |
| 1..8, **11 (veins)**, 13, 14, 23, 24 | (x, y) is in the rectangle |
| 9, 10 | (x, y) is in the rectangle grown by one tile on every side, without its four corners |
| 29 | (x, y) is in the rectangle and the map's current tile there can change (`TerrainTile.change_to[0]` not 0) |
| 0, **12 (vein regions)**, 15..22, 28, 30 and up | never |

**The command** (`TransformTerrain::BuildAttribute` 0x0037B138) [high]: shown (1) when the unit
being ordered (`map::Mind`) passes `CanDragonVein` **and** a usable (state bit 1) type-11
gimmick reaches its tile; otherwise not in the menu (4). The same two tests guard the command's
action (`TransformTerrain::ACall`), the script (`UnitCanDragonVein`: unit numbers 1..250, a unit
of force 9 is refused) and the AI: `AIThink::ActionMindTransform` lets enemy units with the flag
walk to a vein and use it [high for the call, med for "enemies": any AI-controlled unit].

**Once only** [high for the code]: there is no per-turn or per-unit "used a vein" flag. The only
record is the vein's own state byte. The command needs bit 1 (usable); `trick::Data::Done`
clears it and sets bit 2. The command's own code does not call `Done`: using the vein runs the
chapter's event (section 4), and the script switches the states (`TrickSet`), so "a vein works
once" is the script's doing [med]. The script can also test a state (`TrickTst`, rewritten:
with mask 2 it answers "has this vein been used").

## 4. What happens when a vein is used

1. `TransformTerrain::ACall` 0x0037B1B4: the first usable vein reaching the unit's tile gets
   `SetDeploy` (the preview marks, section 5), then the map goes to a target step and the
   human sequence's label 31.
2. `map::anonymous_namespace::ProcSequence::Transform` 0x00381594: for every usable vein
   reaching the tile, `event::Poke::Trigger(x, y, 11)`: the chapter's own event for that tile
   runs.
3. The event does the effect with script commands. Those found by name: `TrickSet` (enable /
   done / ruin a gimmick: `trick::Data::Enable/Done/Ruin`, which call `trick::Data::Mutation`,
   the writer that changes the ground and the 3D map), `TerrainAttributeSetTID` and friends
   (tile edits), `GimmickWindBlow` (a gust that pushes units), `GimmickMedicine` (a heal),
   `ChapterSetTrickDragon` (a number in `Situation +0x16` that `event::ProcMiracleTelop` reads:
   the vein banner) and `TrickSetDragonFocus` (`Situation +0x22/+0x23`). [high for the names
   and the stores, med for what each effect looks like]

**Chosen effect: the ground change** (regions of type 12). Why this one: it is the most common
effect (rivers, paths, bridges are all regions switching state), it is fully described by data
the code reads (the vein's region string, the regions' rectangles and states, the terrain
records' attribute bits), and the game already computes it read-only for its own preview. The
gust and the heal are scripted procedures with movement and animation; they are not a lookup.

## 5. The ground-change lookup (the game's own preview)

`trick::Data::SetDeploy` 0x00526D98 [high], called when the cursor rests on a gimmick
(`SequenceHuman` cursor ticks) and by the command, marks the tiles the vein will change, for the
blue preview on the map. For a vein (type 11):

1. **The region list** (`map::trick::PositionEnumerator` 0x0039A02C) from the vein's string:
   "None" gives none; "All" / "EnableAll" / "DoneAll" / "RuinAll" give the top-left corner of
   every region (type 12) in any state / usable / used / ruined; any other text is read as
   numbers separated by commas, taken as x, y pairs. Each comma ends a number, characters other
   than digits and commas are skipped, an empty number is -1, a number keeps only its low byte,
   and an odd last number is dropped.
2. For each named corner, the first region (type 12) whose corner is there. Its tiles are counted
   from the **named** corner (the two differ only for a name of -1, which matches any column or row).
3. For each tile of that region, the terrain record of the map's current tile (`MapImage +0x808`,
   `TerrainTile`) is marked when its attributes say it changes in the region's current state:
   bit 0x400 while usable, 0x800 while used, 0x1000 while ruined. A marked tile with bit 0x2000
   also marks its whole column of the play area, with 0x4000 its whole row.
4. A mark is bit (i & 7) of byte (i >> 3) of `MapDeploy +0x151C`, i = x | y << 5; SetDeploy
   returns 1 when it marked anything. A tile off the 32x32 map lands outside that bitmap (the
   game does not check).

Type 28 marks only the first listed position; cannons (25..27) ask `map::Deploy::Cannon`.

**For the `vein_highlight` option** (docs/tracks/OPTIONS_V1.md): `trick_at_access` (is there a
usable vein here), `unit_can_dragon_vein` (may this unit use it) and `trick_preview_marks` (which
tiles it changes) are all a highlight needs, and none of them writes. The game already draws a
vein note in the terrain window (`map::TerrainInfo::Draw` tail-calls `DrawTransformAccess` when
its mode byte `+0x14` is 1, with the chapter's vein help `Chapter::GetDragonVeinHelp`, a message
id from the chapter name and the route letter, falling back to the chapter name alone) [high
for the calls, med for when the mode byte is 1].

## 6. Cross-check against docs/tracks/rules/RULES.md

| RULES.md line | Code says | Verdict |
|---|---|---|
| One command; the unit stands on a marked tile and uses it | one map command (`TransformTerrain`); the unit must stand in the vein's area, which is a rectangle (often one tile, but the code allows more) | **confirmed** (with "tile" = any tile of the area) |
| The tile works once | the command needs the usable bit; using a vein runs the chapter's event, and the script marks it done; no per-turn or per-unit flag exists | **confirmed for the effect; the "once" is the script's doing**, not a rule of the command |
| The effect is chosen by that map, not by the route | the effect is the chapter script's event on that tile; the help text is looked up per chapter **and route letter** first | **confirmed** for the effect (each route's chapter has its own script); the help text may differ per route |
| Skirmishes do not offer the command; a map whose vein changed the ground is already in the changed state | with one game-mode bit set, every vein and region is created done: no command (the usable bit is off), regions in their done state | **consistent**, but which mode sets the bit was not traced |
| All three routes use the same command | one command class, one unit check; no route test in either | **confirmed** |
| Who may use it is a fixed set of units, data not a formula | one personal-flag bit on the unit, Person or class; plus the download-person rule for units with state bit 28 | **confirmed**, with one extra rule |
| (task question) a per-turn use flag | none found: not in the command, the unit check, the script check or the AI check | **refuted** (no such flag in the code read) |

Not this batch: `map::Situation::CalculateDoragonVein` 0x00527F98 is the **castle** dragon vein
points a finished map gives (10..300; 0 when the script calls `ChapterSetInvalidGainDragonVein`,
`Situation +0x4` bit 20), and `castle::DragonVeinSequence` / `ProcDragonVein` are the castle's
own vein; both are My Castle, not the map command.

## 7. What is rewritten, what waits

Readable C in `src/readable/map/` (`veins.h`, `vein_tricks.c`, `vein_units.c`, `vein_effect.c`;
registry: config/readable/functions.csv). No guest function is called; the two one-time caches
make the code give up while they are cold.

| Address | Game function | Readable | Kind | Host diff | Tier 2 (2026-11-11) |
|---|---|---|---|---|---|
| 0x00526BA0 | map::trick::Data::IsAccess(int,int) | trick_is_access | override | 0 mismatches | ABI-ONLY |
| 0x004CF5B4 | AIThink::GetTrickFromAccess (type 11: is this tile a vein) | trick_at_access | override | 0 mismatches | ABI-ONLY |
| 0x003B0A44 | TrickTst (script; mask 2: has this vein been used) | script_trick_test | override | 0 mismatches | ABI-ONLY |
| 0x0053DFEC | Person::IsDownload | person_is_download | override (cache: gives up while cold) | 0 mismatches | GAVE-UP (cold cache) |
| 0x0052DFE8 | Unit::CanDragonVein | unit_can_dragon_vein | override (cache) | 0 mismatches | GAVE-UP (cold cache) |
| 0x003ABD8C | UnitCanDragonVein (script) | script_unit_can_dragon_vein | override | 0 mismatches | ABI-ONLY |
| 0x0037B138 | TransformTerrain::BuildAttribute (the command shown or not) | vein_command_attribute | override | 0 mismatches | GAVE-UP (cold cache) |
| 0x00526D98 | map::trick::Data::SetDeploy (the preview) | trick_preview_marks | helper (writes nothing; returns the marks) | 0 mismatches | not run (helper) |

New layouts: `TrickData`, `Trick`, `MapImage`, `MapDeploy`, `MapMind`, `PersonBlockNode`,
`PersonBlock`, `UnitPool.units` and the Unit record size (0x140, from `UnitPool::Get`); globals
`G_Trick`, `G_MapImage`, `G_Deploy`, `G_MapMind`, `G_TerrainHeader`, `G_PersonBlocks`.

**Host differential test** (`python src/readable/map/tests/vein_diff.py`, `check_all` rows
`vein-diff` (with `--plant`) and the slow `vein-diff-long`): the stance test's method and ARM
interpreter. The game's code runs from extracted/text.bin with everything it calls (the
enumerator, `IsAccess`, `Terrain::Get`, `UnitPool::Get`, `Person::IsDownload`,
`PositionEnumerator` ...) except a few library routines answered in Python with the same
meaning (new[] / delete[], memory copy and clear, `strcmp`, and the cannon preview). For the
helper the whole of `SetDeploy` runs and every byte it leaves in a 3 KiB window around the
bitmap is compared. Inputs reach outside the usual ranges on purpose (the triangle review
found a test that drew only in-range values): coordinates -1, -128, 127, 255, 1000 and the
32-bit extremes, widths and heights 0, negative and 127, every type 0..31 and some above,
unit numbers 0, 251 and the extremes, texts with no digits, empty numbers, numbers over 255
and over 32 bits, more than 16 positions and more than 16 matches (the game's spill arrays),
off-map marks. Result: 8 functions x 400 cases (seed 20261111) and x 1500 cases (seed 7), **0
mismatches**; `--plant` makes 35 small wrong changes one at a time (a bound, a sign, a field, a
type list, a mask, a cache test, a parse rule, a mark position ...): **35 of 35 caught**.

**Waiting:**

- The writers: `SetDeploy` itself (the bitmap), `TransformTerrain::ACall`,
  `ProcSequence::Transform`, `trick::Data::Enable/Done/Ruin/Mutation`, `TrickSet`, the terrain
  script commands (project rule F-017: no readable writer until H6/H8 are green on Fates).
- `map::trick::Enumerator::Enumerate` as a whole override (it fills its own object and may
  allocate); the readable code repeats its search and stops at the first match.
- The other effects (`GimmickWindBlow`, `GimmickMedicine`), the AI's vein action, the cannons'
  preview, `Chapter::GetDragonVeinHelp`, the castle's vein points.

## 8. Tier 2 (3dsrecomp verify, 2026-11-11)

`python tools/readable/verify.py --rom "Fire Emblem Fates - Special Edition (USA).cci"` on all 35
overrides (whole-game library build 344 s): **0 mismatches**, `readable-verify: OK (22 ABI-ONLY,
4 CLEAN, 7 GAVE-UP, 2 UNSAMPLED)`. The seven vein overrides:

| Address | Readable | Verdict | Why |
|---|---|---|---|
| 0x00526BA0 | trick_is_access | ABI-ONLY | same r0; only r1, r2 and flags differ; shadow pass reads exactly what the original reads |
| 0x004CF5B4 | trick_at_access | ABI-ONLY | same r0; scratch registers, flags and dead stack differ (the game's enumerator lives on its stack) |
| 0x003B0A44 | script_trick_test | ABI-ONLY | the same |
| 0x003ABD8C | script_unit_can_dragon_vein | ABI-ONLY | same r0; flags and dead stack differ |
| 0x0052DFE8 | unit_can_dragon_vein | GAVE-UP | verify's memory has the one-time cache cold: only the fallback (the original) ran |
| 0x0053DFEC | person_is_download | GAVE-UP | the same (its own cache) |
| 0x0037B138 | vein_command_attribute | GAVE-UP | the same cache, through unit_can_dragon_vein |

The first run of the day gave 2 MISMATCH, both "shadow pass not invisible": verify counts every
read of unmapped memory, and the readable code read more than the game. `trick_is_access` read the
area before looking at the type (the game reads nothing more for a type that never reaches), and
`vein_command_attribute` read the ordered unit before giving up on the cold cache. Both now read
only what the game reads (the area only for the types that use it, the cannon fields per side; the
cache first); the second run above is clean. The host comparison does not see such reads, so
this is a real tier-2 catch. A smoke test, not a proof: one made-up state per function; the three
GAVE-UP functions stay covered by the host comparison (warm and cold caches). Registry statuses
were not changed (no `--update-status`).
