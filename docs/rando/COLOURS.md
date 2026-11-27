# Recolour: a swapped character wears the new person's colours; own colours in new classes (round 59, track colour)

**For the owner.** In the "keep the face" shuffle, a swapped spot keeps its face but now shows the new person's
**hair colour**: in battle (a table number, exact), in the portrait and on the map (a picture recolour the port does
while the game reads the picture). A character in a class they never had already keeps their **own hair and skin**
in the game itself (their own model row wins over the class row); the outfit stays the class's army colour, which is
how you tell the side. Grok picked these rules (docs/collab/COLOUR_RULE_GROK.md). The planner, its guards and its
spoiler lines are built and pass 50 seeds on every path including Seal of Flames. **Not built yet:** the core hook
that lays the cells and recolours the pictures (assemble step, section 5), so **there is no in-game screenshot pair
yet**; the pictures below are host-side previews made with the same recolour maths.

Status 2026-11-20, round 59 phase A. Host only: no game run, no build, nothing written to play/ or the owner's
data. Facts come from our own code reads (symbol map, `asm/text`) and our own table dumps of the owner's files
(counts and field layouts only here, no game bytes tracked). Seal of Flames files are read locally from
`play/seal-of-flames/data/mods/0004000000179800/romfs/` and never committed.

## 1. Where a character's colours live (facts)

| Where it is drawn | What gives the colour | Keyed by | Evidence |
|---|---|---|---|
| Battle model hair | one `0xRRGGBB` number in the model table row (mask_hi bit 2) | the row's first condition: `AID_<person>` (person rows, ROM3/ROM4), `JID_<class>` (class rows, ROM2) | `BattleUnitResName::Import` 0x1F95A4 stores it at +0x724; `BattleUnit` reads ResName+0xFFC and calls `BattleUnit::SetMaterialHairColor` 0x16F638 (call at 0x171070) [high] |
| Battle model skin | the next number (mask_hi bit 3) | same | Import +0x728; `BattleUnit::SetMaterialSkinColor` call at 0x1710B0 [high] |
| Which row wins | rows are applied in table-priority order, later rows overwrite fields | header word high 16 bits: ROM0 1000, ROM1 2000, ROM2 3000, ROM3 4000, ROM4 5000, ROM5 6000, ROM6 8000 | `AssetTable::Load` 0x1697BC inserts sorted by that value; `BattleUnitResName::Construct` 0x1F996C walks from `AssetTable::Top` [high] |
| Avatar and children's battle hair | the unit's own hair colour (Unit+0x13C) replaces the row's | the unit has avatar data (+0xB0) or the person a parent (+0x2A) | `BattleUnitResName::PostProcess` 0x1F8A84 [high] |
| Unit hair colour (Unit+0x13C) | FaceData +0x1C (bytes R,G,B,A) of the person's `FID_`; a child takes the living parent's | `Person.fid` | `FaceDataManager::GetHairColorFromPerson` 0x1E0180, `Unit::UpdateHairColor` 0x3D609C [high] |
| Portrait | baked into the expression pictures (`face/face/<package>.arc`); a hair layer with tint exists only for the avatar and the children (118 of 452 records) | FaceData record by name | docs/ASSETS.md section 4; our dump [high] |
| Map sprite | baked pictures per army colour, `unit/Head/<AID minus "AID_">/<colour><n>.bch.lz` (青 player, 赤 enemy, 緑 ally, 紫 other); the avatar has 12 hair-colour folders | `Person.aid` | `UnitIcon::SetIcon` 0x4F5104; folder listing [high]. The map draw multiplies only by field lighting (`FieldWorld::GetUnitUpperColor`), no hair tint [high] |
| Outfit (body) | no colour number. Generic class bodies are baked army-colour textures `uBody_<sex>_<class>_cl0n_P/E/A`; a personal outfit is its own model in a row with `AID_` **and** `JID_` conditions | the class (+ person) | ROM2 rows, `bu/` file names; `ModifyForceTextureName` 0x1F9198 fills the `?` [high] |

The model table record format (our parser `colours.parse_asset`, checked to end exactly on the terminator in all
seven files of both games): `mask_lo`, then `mask_hi` when `mask_lo` bit 0 is set, then **one always-present first
condition**, then one 4-byte field per further set bit (lo bits 1..31, then hi bits 0..31); next record =
start + 4 x (popcount + 2) (`AssetFile::GetInfo` 0x4F83A0). Data region starts with the header word, rows from +4.

In memory: `BattleGlobal::Asset()` returns the static table object **0x006FFA60**; `+12` is the first list node,
`node+12` the next; each node is an archive like GameData's (`[[node+4]+112]+32` = the data start, whose first word
is the header that names the file, e.g. `0x0FA01111` = ROM3). The FaceData file: `FaceDataFile` array at
**0x007047F4**, 12 bytes each `{count, file object, records start}`; the global FaceData is entry 0, records start
= `*(0x007047F4+8)` (data start + 4). Both load once at boot and stay (docs/rando/RECRUIT.md item 2).

Counts (Fates): 176 model rows carry a hair number, 34 a skin number; 83 main persons have an own hair row (the
playable cast; the rest are generics, children and the avatar, whose hair comes from elsewhere). For most people
the portrait colour (FaceData) equals the model hair; 22 differ a little. Seal of Flames: same seven files (its
ROM2/ROM3 replaced), 456 FaceData records (4 new class faces, colour placeholder white), and about half of its
recruits are **generic class-named people** (`PID_Archer`, `PID_Paladin`, ...) with no `AID_` and a generic class
face: they share the class soldier's model and portrait.

## 2. The rule (Grok, docs/collab/COLOUR_RULE_GROK.md)

1. **Hair only** for a swap: battle hair number + hair pixels in portrait and map sprite. No outfit tint (it would
   fight the army colours that tell the side).
2. **Own colours in new classes = hair and skin**, which the game already keeps (own row beats class row). If the
   class has the person's personal outfit, that model is used; otherwise the army outfit stays. No edit.
3. **Leave enemy copies**: if the person's model row is shared with a boss on a route they never join (chapter 6
   on), do not change that hair number (option `boss_copies`, default `skip`; `follow` recolours anyway). In
   Fates this skips only the royals (never shuffled anyway) and Yukimura (Conquest 6 enemy); in Seal none.
   Story copies before a join (prologue to chapter 6, HANDOVER rows) follow the spot: they are the same story
   person.
4. **Same colour, no marker**: two silver-haired people stay alike (the spoiler line says "same hair colour").

Also: the **full identity** look shows the filler's own model, so no recolour is needed. A **generic** spot (Seal's
class-named recruits) is never recoloured: its model and portrait belong to every soldier of that class; the
spoiler line says so. As a filler, a generic person gives its class's soldier hair colour.

## 3. `tools/randomizer/colours.py`

`load_tables(game)` reads the seven model tables, FaceData, the map head folders, the chapter Person copies and the
route members (Seal: the mod's own files over the base RomFS). `plan_colours(tables, plan, opts)`; `plan` is
`{"look", "swaps": [[spot, filler]], "classes": {PID_: [JID_]}}`, made by `plan_from(merged_edits, facts, look)`
from the merged make (the shuffle's spot/filler pairs; every class from the final Person class cells and the
final Job promotion cells, so Classes, the shuffle, children and promotions all count).

Edits per swapped spot A <- B (colours always from the ORIGINAL tables, so a cycle A<-B<-C never chains):
- `AssetTable` cells: every row with first condition `AID_A` that has a hair number -> B's hair (laid_by
  `core_resident`);
- `FaceData` cells: `FSID_ST_A` and `FSID_BU_A` +0x1C -> B's colour, alpha kept (keeps A's children's hair and the
  unit hair colour consistent);
- `Picture` tints: A's `_st`, `_bu` (and `_ct`) portrait archives and every `unit/Head/<A>/*` map head, from A's
  hair colour to B's (laid_by `core_tint`).

Options `{"recolour": on|off, "own_colours": on|off, "boss_copies": skip|follow}`; off = no edits and no lines.
Guards: originals match the files; one writer per cell; every edited spot shows the filler's original colour;
only swapped spots, nothing with recolour off or the full look; no edited row shared with a boss (rule 3); every
person in a class they never had has an own hair row (or is hairless, or takes the unit hair as avatar/child).

Results (2026-11-20, 50 seeds each, recruit route and any, Fates and Seal of Flames): **0 guard failures**; about
24 swapped spots and 330 edits per Fates seed (24 hair cells, 48 FaceData cells, about 260 picture tints). Make
time about 0.1 s after the tables are loaded (the loads are about 0.8 s; the speed track's cache can hold them).
Tests: `python -m unittest tests.test_rando_colours` (14 tests: format, plan, chains, boss rule, off/full look,
guards, patch lines, recolour vectors, real tables over 5 seeds).

## 4. The picture recolour (host previews)

`recolour_rgb(rgb, src, dst)` (the reference the core must follow): a pixel is hair-like when, for coloured hair
(saturation >= 0.18), its hue is within 18 degrees of the hair's (none past 34) and its saturation at least about
a third of the hair's; for grey/white/black hair, when its own saturation is low. Skin-like pixels (hue 0-42,
saturation 0.12-0.65, value >= 0.25) never count unless the hair itself is skin-coloured and bright; pixels much
brighter than the hair (luminance ratio t > 1.3, none past 1.8) or much darker (t < 0.15) never count. A hair-like
pixel becomes `dst x t` (same shading), blended by the weight; alpha is kept.

Previews (`colours.py preview`, files under `build/r59/colour/preview/`, not tracked): `sheet_portraits.png` and
`sheet_map.png` (Luna <- Elfie, Silas <- Suzukaze, Kagero <- Crimson, Niles <- Harold). Honest look: red -> silver,
silver -> green and white -> blonde read clearly as the new person's hair. Limits: grey armour or white collars
shift with grey hair (no hair mask exists in the pictures); dark hair -> light hair also lifts some dark outfit
shading of the same hue (Kagero's top). Map heads are 16x16-ish pixel art: the change is visible but small.

## 5. The hooks the assemble step needs (e1 / core; exact)

**5.1 Patch file (tools/randomizer/ingame.py, e1's file).** After the existing `gamedata` / `dispos` files, append
`colours.patch_lines(edits)`: `file asset <romfs path> <header hex>` + `v <offset> <old 4 bytes> <new 4 bytes>`,
`file face face/FaceData.bin.lz` + `v ...`, and `tint <from RRGGBB> <to RRGGBB> <romfs path>`; every `v` and `tint`
line counts towards `end N`. Offsets count from the file's data region start (the in-memory data start). Call
order in `rando.py make`: after the shuffle and every class module, `plan = colours.plan_from(all_edits, facts,
look)`, then `plan_colours(load_tables(game, facts), plan, opts)`; guards into `plan["guards"]` with the prefix
`colour:`; spoiler lines after the shuffle's. Page rows (e1, rules.json / tools/play/rando.py): **Recolour**
(on/off, default on, grey when the shuffle is off or the look is full) and **Boss copies** (skip/follow, hidden or
advanced). `own_colours` needs no row (it only writes lines).

**5.2 Core: resident cells (zakuro-core `fates_rando.rs`).** New `Kind::Asset { header: u32 }` and `Kind::Face`.
Locate: Asset = walk `node = r32(0x006FFA60+12)`, `node = r32(node+12)` until 0; `start = archive_data_start(node)`
(the same `[[+4]+112]+32` chain); match `r32(start) == header`. Face = `start = r32(0x007047F4+8) - 4`, check
`r32(0x007047F4) == 452` (Fates) or the patch's own record count (Seal 456: write the count into the `file face`
line as a third word; ingame.py knows it). Apply with the existing all-or-nothing guard at the same moments as
GameData (Start game and save load), revert at the title like GameData. Both tables load once at boot, so after
apply they stay; `after_frame` should re-check cheaply (first cell) and re-apply if a reload ever puts the
originals back.

**5.3 Core: picture tint (zakuro-core `fates_rando_file.rs`, inside the game's own file read, like Dispos).** When a
run is active and the game reads a RomFS path listed in a `tint` line: decompress (LZ11/LZ13 as the file is),
for `.arc` walk the members (each an LZ BCH), for every texture of the BCH decode the level-0 pixels (ETC1/ETC1A4,
the formats `zakuro-gpu/src/texture.rs` already decodes), apply `recolour_rgb` per pixel (port the Python maths
1:1; the test vectors in `tests/test_rando_colours.py` `Recolour` are the contract), re-encode the level (and
regenerate its mips) and hand back the file. Cheapest correct re-encode: write the texture as the same format via
a simple ETC1 encoder, or switch the texture to RGBA8 / RGB565 in the BCH (the game takes any PICA format; docs/
ASSETS.md 3.3.1 shows the relocating writer's rules) and return the file stored, not compressed (an LZ stream of
literals is valid). The pictures are small and read per use (portraits when a face shows, map heads when a map
loads); cache the recoloured bytes per (path, from, to) for the session. The Python reference for the whole file is
`colours.recolour_file(raw, rel, src, dst)`.

**5.4 What the check must show (robot, after the build).** Same unit, same spot, same frame, recolour off vs on:
(1) battle: a swapped unit's hair (the battle hair cell), (2) its unit page portrait, (3) the map sprite; plus off =
original memory. A pair whose two images are byte-identical counts as failed. Seal: a named spot (not a generic
class person).

## 6. Open items

- In-game screenshot pairs: need 5.2/5.3 built (assemble step). Not done in this track.
- The map head and portrait recolour can catch same-colour outfit parts (section 4); if the owner finds it ugly,
  the fallback is battle hair only (cells, exact) with pictures unchanged.
- Seal of Flames' generic class-named recruits cannot be recoloured as spots (shared models); said in the spoiler.

## 7. Round 59 assemble step

Built: 5.1 (rando.py `_colours`: after the make, with the shuffle on and the keep look, the colour plan from the
shuffle's spot/filler pairs; guards as `colour: ...`; spoiler lines; `file asset` / `file face` lines appended to the
in-game patch) and 5.2 (patch 0019: `Kind::Asset`, `Kind::Face`, laid with GameData, all found and guarded first).
Not built: 5.3, the picture tint. The round-59 review found the per-pixel recolour bleaches line art and skin on
dark-to-light swaps (Kagero <- Crimson), so `colours.py` got a `pictures` option and the in-game make passes
"off": a swap changes the battle hair cell and the FaceData colour only; the spoiler says the portrait and map sprite
keep the spot's pictures. No page rows yet (Recolour / Boss copies): recolour is always on with the shuffle.
Headless runs laid the cells with their guards passing: Fates r59fa1 75 cells (ROM3 + FaceData, 452 records), Seal
r59sa1 53 cells (FaceData 456 records). No in-game screenshot pair of the hair yet (5.4 is the check step's).

## 8. Round 71: the Recolour row and "Easier to see" (A6, Python only)

The round-59 to 64 pictures showed the battle-hair recolour as faint (lavender to blue-grey seen only when zoomed;
pastel pairs nearly invisible under a hit effect; owner call G in docs/REVIEW_R59_R68.md). Round 71 gives Recolour
its own row on the New Game page (`tools/randomizer/ingame.py` RECOLOUR_ROW, section Characters, right under
"Their stats") with three choices:

| Choice (page words) | Value | What the game gets |
|---|---|---|
| Their own colour (default) | `on` | as before: the new person's hair colour in the battle hair cell and the face data |
| Easier to see | `clear` | the battle hair cell gets `colours.clear_hair(spot hair, new hair)`; the face data keeps the new person's own colour |
| Off | `off` | nothing: the spot keeps its own hair; the spoiler says "Recolour: off" |

It only matters with "Who joins where" on in the keep-the-face look (the full look shows the new person's own model).
Battle hair only (F-047 recolour scope): no portrait, map sprite or outfit is touched.

**The clearer colour** (`clear_hair`, pure, in CIE Lab / LCh; Grok's rules 1 and 4 and the round-71 consult):
the hue is always the new person's own. A coloured hair (chroma >= 12) gets 1.35 times the chroma and a lightness
inside 35..92 (darker vanishes in the battle shading), moved at most 25. Grey, white and black hair never gain a
colour; their lightness moves at most 15. If the result is still closer than Delta-E 40 (CIE76) to the spot's own
hair, the lightness moves away from it inside those limits until 40 is reached or a limit is hit; two silver heads
may stay alike (Grok: that is the honest result). Out of the sRGB range the chroma is lowered until it fits. Never
fainter: when the result would be closer to the spot's hair than the plain colour, the plain colour stays. The guard
"colour: filler's own colour" checks the value each choice wants.

**Old seeds do not change.** The row is left out of the page's answer, the run id and the make flags while it is at
its default (the new schema field `omit_default`, shared with the round-71 chest row), so every old answer gives the
same text, run id, flags and game; `tools/release/fingerprints.py check` is unchanged. "Randomize everything" keeps
it at "Their own colour" (Grok: picking "Easier to see" there would change an existing seed's patch). The Rust page
must leave an `omit_default` row out of its answer at its default the same way (rando_page.rs answers_with_seed),
else the in-game run id of a new game would gain `"recolour":"on"`. A run made away from the default says so in
plan.json (`"recolour": "clear"` or `"off"`; at the default the plan keeps its bytes).

**Commands:** `rando.py make ... --recolour on|clear|off`; `colours.py plan --seed S --recolour clear --swatch
build/r71/python/swatch.png` writes a picture with one row per swap (the spot's own hair, the new hair, the clearer
one) and a text file with the distances, for the review page (ROADMAP call 5). Seed r71col1: 26 swaps, 23 get a
clearer colour (Silas's spot: distance 18 to 40), 3 already differ clearly and keep the plain colour. Tests:
`tests/test_rando_recolour71.py`.
