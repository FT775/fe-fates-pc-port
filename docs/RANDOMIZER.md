# The randomizer: slice 1 (class, growths, join stats), the round-49 tracks and the round-W1 modules

**For the owner.** Pick a seed. The tool gives every playable person a new class they are allowed to be,
new growth rates and new join stats, and writes that as an ordinary mod folder (the same kind the mods tool
builds). The same seed always gives exactly the same folder, so you can send someone the seed. Children are
off. Nobody new is added. The game's hidden dice are never touched. Delete the folder (or uninstall it) and the
game is the original again. Status 2026-11-19, round 47 (F-041 #4-5). Our own code; public randomizers
(Paragon, the upgraded Fates randomizer) were read for facts only, no code copied.

**The Seal edition (F-047, round 58):** the same randomizer also runs on the Seal edition's mod tables. Its notes moved to docs/seal/RANDOMIZER_SEAL.md in round 84.

**The in-game page since round 62b (F-050):** settings under seven headings with a one-sentence help line, Children not on the Seal page, leftover rows (slice1, growth min/max, upgrade chance and rank, the three boss rows) off the page but still answered (old seeds make the same game and run id), the switches Stronger enemy weapons and Tougher bosses (amount from Difficulty), a Spoiler log switch and a Randomize everything button (safe rows only). docs/rando/R62B_PAGE.md.

**Round 49 (F-043, 2026-11-20):** four more parts can be switched on with the same seed: growth and base modes
(FE8-port style), skills, starting items / shops / castle rewards, and enemy weapons / classes. All of them are
**off by default**, and with them off the tool writes exactly the same files as before (old seeds unchanged).
Section 6 below. Nothing counts as done until the owner says ok (F-037).

**Round 50 (F-044 and its addendum, 2026-11-20): the randomizer inside the game.** The planned main way to play a
randomized game is a **Randomizer** page that opens inside the game right after you pick Casual / Classic (or Phoenix)
in a New Game, with every row of section 6, the seed kept beside each save. PLAY RANDOMIZED.bat (docs/RANDOMIZER_PAGE.md)
stays as the fallback. **Status: not playable yet.** Round 50 built the parts under the page (section 7); the page
itself and the program you play come in round 51. Until then PLAY RANDOMIZED.bat is the way to play a randomized game.
Design and results: docs/RANDOMIZER_INGAME.md.

**Round 51 (2026-11-20): the in-game page is built, waiting for the owner's look.** The program PLAY.bat starts now has
the Randomizer page (Zakuro patches 0008-0010). The robot checks T2, T4, T5 and T6 pass (section 8). Nobody has seen the
page in a window yet (T7, the owner). PLAY RANDOMIZED.bat stays as the fallback. Nothing counts as done until the
owner says ok (F-037).

**Round 54 (2026-11-20): the character shuffle is designed, not built.** The row the owner read as a character shuffle,
"Personal skills: shuffle", only ever swapped personal skills between people. It is now labelled **"Personal skills
(shuffle = swap the skills between characters)"** (same choices, same `--personal-skills` flag). The real character
shuffle (who joins in which join spot, the FE8 port's Recruitment) has a design and a counted 9-round plan in
docs/RANDOMIZER_RECRUIT.md; no code yet. Section 9 lists every row of the FE8 port's Randomizer screen as built / built
but not on the page / not built / not possible in Fates.

**Round W1 (F-046 / F-047, 2026-11-20): five more parts wired.** Children, random promotions (Master Seal and Heart
Seal classes), class and enemy stats (class growths and bases, enemy growths and levels, tougher bosses), weapons
(weapon stats, special powers, stronger enemy weapons) and misc (enemy drops, class movement, spread classes evenly)
now work through `rando.py make`, PLAY RANDOMIZED.bat and the in-game page. Every new row is **off by default**; with
them off the tool writes exactly the same files as before (proven on the seeds r50def, r50all, r50shops and a fourth
seed, byte for byte, mod folders and in-memory patches). Two rows are grey on the in-game page until the next engine
round: **Enemy levels up** and **Tougher bosses** (they change the chapter person files, which the in-game page cannot
lay yet; PLAY RANDOMIZED can). Music, Nuzlocke and the character shuffle are shown grey with their reason; they come in
round W2 and the engine rounds. Section 10. Nothing counts as done until the owner says ok (F-037).

## 1. How to run it

```
python tools/randomizer/rando.py make --seed MYSEED
#   -> build/rando/out/Rando-MYSEED/   (mod.json, tables/Person.csv, tables/DisposUnit.csv, spoiler.txt, plan.json)
python tools/randomizer/rando.py check build/rando/out/Rando-MYSEED     # remake from plan.json + every guard
```

Switches (all `on|off` unless said): `--classes`, `--growths`, `--join-stats`, `--trees own|any` (own: a person
only gets classes of the same side, Hoshido or Nohr, as the class they start in; any: both sides),
`--keep-royals` (on: Ryoma, Xander, Takumi and Leo keep their classes because their personal legendary weapons
need them), `--children off` (on is refused: not built). Seeds are 1-40 letters, digits, `-` or `_`.

To play it, the folder goes into **its own** data folder, never your normal one:

- From the randomizer page (`PLAY RANDOMIZED.bat`, `tools/play/rando.py`, docs/RANDOMIZER_PAGE.md): the page
  calls `rando.py make --seed S ... --zakuro-dir <profile>/data --out <profile>/mod`. The tool writes the folder,
  builds it with the mods tool and installs it into that profile's data folder only.
- By hand: `python tools/mods/mods.py --mods-dir build/rando/out --stage-dir build/rando/stage --zakuro-dir
  <a separate data folder> install`. `uninstall` with the same folders takes it out again.

`rando.py` refuses to write into %APPDATA%, %LOCALAPPDATA% or the repository's `mods/` folder.

## 2. What slice 1 changes

Only rows that already exist; only these cells:

| Table | Cells | What it means in game |
|---|---|---|
| Person (the main cast, `GameData/GameData.bin.lz`) | `job` | the class the person joins in |
| | `job_low` | for a promoted class: a base class that promotes into it (used for reclassing); for a base class: one of its two promotions (the game's own pattern) |
| | `growth.*` | personal growth rates (the class growth is added by the game) |
| | `base.*` | personal join stats (added to the class's own base stats) |
| | `weapon_exp.*` | starting weapon experience, moved onto the new class's weapon types |
| DisposUnit (map placements of those people) | `item_1..5` | a carried weapon the new class cannot use is swapped |

Who is in scope: the player's army in the main cast table, minus children, logbook (bond) units, capture-only
generic units, downloadable and enemy-only people: 49 people (Corrin's two rows included).

- **Class:** a random pick from the person's legal classes: the same gender row, the same tier (base or
  promoted), a normal player class (no enemy-only, downloadable, Villager, Lancer, dragon form, Corrin's own
  line or the Songstress), beasts stay beasts and nobody else becomes one, and with `--trees own` the same side.
- **Growths:** the person's total growth is shared out again over the eight stats in steps of 5 (HP at least
  10, no stat above 80). The total stays the same.
- **Join stats:** the person's total personal base is shared out again (HP weighted double), each stat kept so
  that personal + class base stays within the class's cap (Job.max + the person's limit modifier).
- **Weapon exp:** the old weapon types' exp, largest first, onto the new class's types in a random order, cut to
  the new class's limit. A weapon the person could use at the start before stays usable (the exp is raised to
  its rank, never above the class limit).
- **Carried weapons:** on every map placement of a changed person (any side), a weapon or staff the new class
  cannot use is swapped for an ordinary shop weapon of the same rank of a type the class can use (same side's
  style first: katana for Hoshido classes). If no ordinary weapon of that rank exists, the nearest rank is taken
  and the spoiler log says so. Items (Vulnerary, seals) are never touched.

## 3. The guards (each one has a test in tests/test_randomizer.py)

| Guard | How it is kept | Test |
|---|---|---|
| Same seed, byte-identical output | one random stream per (seed, switches, purpose, person), from SHA-256; no clock, no dict order | `test_same_seed_byte_identical`, real data `test_byte_identical_and_differs` |
| Different seed, different output | | `test_different_seed_differs` |
| No illegal class | `legal_classes`; re-checked by the `legal_class` guard | `test_no_illegal_class` (60 seeds x 3 switch sets), real data 25 seeds x 3 |
| Weapons still usable | swap + exp raise; `weapons_usable` guard over every placement item | `test_weapons_still_usable_and_swaps_said`, `test_class_only_item_is_swapped` |
| Per route: a staff user, a door opener, a dragon-vein user | if a route (Birthright A, Conquest B, Revelation C, each with the shared opening chapters) has nobody, a changed person of that route is given a class with the role | `test_route_roles_kept` (a made-up route whose only healer would lose staves) |
| Story-critical people keep their class | Corrin (lord, dragonstone), Azura (singer), the four royals with personal legendary weapons (`--keep-royals`, default on), anyone starting in a special class (Mozu's Villager) | `test_story_people_keep_class` |
| Children off, no new people | out of scope; no row is added; `--children on` refused | `test_children_and_outsiders_never_edited`, `test_no_new_people_and_only_allowed_cells`, `test_bad_seed_and_children_refused` |
| Hidden dice untouched | only the cells in section 2 are written; no table of the random generator is in the output | `test_rng_untouched`, real data `test_mods_tool_accepts_the_folder` (the mods tool sees only Person and DisposUnit changes) |
| Stats within class caps | see "Join stats"; growths in steps of 5 | `test_stats_within_caps_and_totals` |

What the role guards can and cannot see: **door opener** = the lock-opening skill in the person's own skill list
(unchanged by slice 1, so Kaze, Saizo, Niles and the other thieves keep opening doors whatever their class) or in
the new class's skills; keys bought in shops are not counted. **Staff user** = a class with staff rank. **Dragon
veins** = the person flag the game checks (royals and Corrin); slice 1 never edits flags, so this cannot change.
**Not checked:** items given by story scenes instead of map placements.

**Seed guarantees (round 75b, docs/SEED_GUARANTEES_PLAN.md, F-061).** Since round 75b the randomizer also knows which
maps need a role, and by when. config/randomizer/guarantees.json (ids only) lists per story: a door opener by
Birthright 7, Conquest 9 and Revelation 9 (never stricter than the original game, which has no opener for Revelation
7-8); a healer by chapter 7 on every story; a flier by Birthright 10 and Revelation 11 (the known breaks, among them the
two ninja-map doors); the dragon vein is always met by Corrin. Felicia and Jakob count as one retainer slot: both must
cover a need for the slot to count, because which one stays depends on Corrin's sex. The Seal edition's own
guarantees: docs/seal/RANDOMIZER_SEAL.md.
How it is kept: after the route pass, `guarantees.repair` (randolib.make_plan step 2b) gives one pool person per unmet
need a class with the role, from its own random stream, so nobody else's draw moves; it prefers a role class nobody
else in that chapter's army has (no repeated class; class pairs count as one) and never breaks an earlier need. Kept
and held people are never repaired; the one exception is the last resort, which may re-class Gunter (rules.json
recruit_fixed) when nobody else in that army can take the role (13 of 200 shuffle-'any' seeds, none elsewhere). A
repaired healer joins holding a staff (step 4b). The even spread keeps a guarantee (misc's roles-stay step asks
`guarantees.met`). The backstop guard `guarantees: timing` re-checks every need after each class- or skill-changing
track and refuses the seed if one is not met. The spoiler has a Guarantees section; plan.json, the spoiler and the
PLAY RANDOMIZED mod.json carry the block and `rando_version` 2. A hidden one-choice page row `rando_version` ("2") makes
every run id new and refuses old share codes (layout CE); `rando.py check` on a folder made before round 75b says so
and exits 3. Paralogues are not needed-by chapters (their doors are listed as information). Under Nuzlocke the
guarantee is about who joins; the help line says to keep the first healer and lock opener alive. Tests:
tests/test_rando_guarantees.py; `python tools/randomizer/guarantees.py facts` re-checks the table against the scripts and
round 72's robot armies.

## 4. What is not done yet

- The page before a new game is the separate `tools/play/rando.py` (another helper's work); it calls this tool.
- Skills, items, shops, castle rewards and enemies: round 49's parts (section 6). Heart Seal (reclass) options
  are unchanged, so a person may be offered their new class again.
- Capture-only and downloadable people, children, supports, chests/villages (chapter scripts) and maps are not
  randomized.
- Join spots and join levels are not moved. The character shuffle that would move them is designed in
  docs/RANDOMIZER_RECRUIT.md (round 54), not built (section 9).
- Only Normal-difficulty numbers were looked at in the robot check (the tables are the same on every difficulty;
  Hard/Lunatic only add their own difficulty columns, which slice 1 does not touch).

## 5. Robot check (round 47)

2026-11-19, ~23:35-00:05, in the robot's **own** test game only. Nothing counts as done until the owner says ok
(F-037).

**Where the mod went.** `rando.py make --seed r47robot --out build/rando/robot_mods` (37 new classes, 187
weapon swaps, 835 map placements, every guard PASS), then `mods.py --mods-dir build/rando/robot_mods --stage-dir
build/rando/stage --zakuro-dir build/rando/zak install` (2620 changed cells; log build/rando/install_r47robot.log).
Each run copied that folder's `mods/` into its own server data folder below `build/rando/server/`. Not touched:
%APPDATA%, the owner's saves, Zakuro settings, cheats, `mods/`, play/, build/oka, routes.json, markers.json.
Real recorded presses only; memory was only read. Driver: `tools/randomizer/robot_check.py` (3 jobs, below
normal, one after another except the first two side by side). Results: `build/rando/robot/rc-*.json`; pictures
`build/rando/robot/shots/`, side by side `build/rando/cmp_rando.png` (not tracked: game pictures).

| Run | Start | Presses | Mod |
|---|---|---|---|
| ch1 | new-game-empty | bt-prologue up to frame 38810 (Chapter 1 map, cursor on Corrin); reads at 38810 and 39000 | |
| ch2 | bt-ch1-clear | bt-ch2 up to 5117 (Chapter 2 map, before the first move); reads at 4800, 5117, 5300 | |
| rc-mod | | both | Rando-r47robot installed |
| rc-none | | both | no mod at all |
| rc-off | | both | the same robot folder after `mods.py uninstall` + `disable` (0 files left) |

| Check | Result | Evidence |
|---|---|---|
| All 49 people's Person rows in memory (class, class line, 8 bases, 8 growths, 8 weapon exp) equal the plan | **PASS, 0 mismatches** at every read, both runs | rc-mod.json `persons.mismatches` (49 checked each read) |
| Corrin on the Chapter 1 map | class Nohr Prince (kept), person + class base 21 8 4 6 6 3 6 2 = the plan; the panel shows HP 24/24 instead of 22/22 (the plan's +2 HP) | rc-mod.json, cmp_rando.png row 1 |
| Gunter on the Chapter 2 map | class **Strategist** (spoiler: Great Knight -> Strategist), base 23 2 9 8 9 10 3 8 = the plan; drawn as a mounted Strategist | rc-mod.json ch2, cmp_rando.png rows 2-3 |
| Felicia on the Chapter 2 map | class **Bow Knight** (spoiler: Maid -> Bow Knight), base 26 9 2 11 10 4 7 8 = the plan; drawn as a Bow Knight | same |
| Presses still fit | yes up to the last read (5300): the same screens, Corrin's panel in the same place; the recorded battle at 10392 was not tried (it would very likely go another way with new classes) | cmp_rando.png |
| No mod = original tables | rc-none: the 49 rows equal the original tables, 0 mismatches | rc-none.json |
| **Off = original** | rc-off's whole-memory hash equals rc-none's: ch1 `5b0b47b2040be226...`, ch2 `74eb98e65d597c4e...`; every memory section the same; only the metadata section differs by 2 bytes (the run folder name, rc-off vs rc-none) | rc-off.json, rc-none.json |

Said plainly: Jakob was not among the units read on the Chapter 2 map at these frames (he is in that chapter's
placement list; he was not in the unit lists at 4800-5300), so his class was checked in the Person table only
(Butler -> Berserker, 0 mismatches). The Chapter 2 save (bt-ch1-clear) was made in the original game, so
Corrin's level-2 gains in it come from the original growths; his join stats and the newly joining Gunter and
Felicia come from the mod.

## 6. Round 49: the four tracks put together (F-043)

`rando.py make` takes these options on top of slice 1's switches. The defaults (first) change nothing. Each part
is its own module with its own write-up; `tools/randomizer/tracks.py` puts them together into the ONE mod folder.

| Part (write-up) | Options (default first) | What it changes |
|---|---|---|
| Stats (docs/rando/GROWTH.md) | `--growth-mode slice1/redistribute/delta/full`, `--growth-variance 30`, `--growth-min 5`, `--growth-max 80`, `--adjust-hp off/on`, `--bases-mode slice1/redistribute/delta`, `--base-variance 5`, `--scale-to-level on/off` | the FE8 port's Growths / Bases rows. `slice1` = slice 1's own Growths / Join stats switches decide. A mode replaces slice 1's growths (or join stats) for everyone and starts from the person's original numbers. Steps of 5; max 125 |
| Skills (docs/rando/SKILLS.md) | `--personal-skills keep/shuffle/random`, `--skill-slots keep/class/random` | personal skills and the skills people join with (Person skill cells). `shuffle` swaps personal **skills** between people; it never moves people (page label since round 54: "Personal skills (shuffle = swap the skills between characters)") |
| Items (docs/rando/ITEMS.md) | `--starting-items off/on`, `--shops off/on`, `--shop-sides own/mixed`, `--rewards off/on` | starting items of the player's map placements, the four castle shops' stock (prices stay), castle battle/visit rewards. Chests and villages are in chapter scripts: not changed |
| Enemies (docs/rando/ENEMIES.md) | `--enemy-weapons off/on`, `--enemy-classes off/on`, `--boss-classes off/on`, `--enemy-trees own/any` | enemy weapons and classes in the map placements (team 1); story units and Conquest 9/16, Revelation 8/13 untouched; the "no stuck enemies" terrain rule |

Example with everything on (one line):

```
python tools/randomizer/rando.py make --seed r49all --growth-mode full --adjust-hp on --bases-mode redistribute
    --personal-skills shuffle --skill-slots class --starting-items on --shops on --shop-sides mixed --rewards on
    --enemy-weapons on --enemy-classes on --boss-classes on --out build/rando49/all/mods
python tools/randomizer/rando.py check build/rando49/all/mods/Rando-r49all      (remakes it: byte-identical)
```

How they fit together: slice 1's plan first; then growth (written into the plan's people), skills (Person skill
columns), items (team-0 placements' items on top of slice 1's weapon swaps, Item stock, AchieveBonus rows),
enemies (team-1 placements' class and items). Each part draws from its own random stream (SHA-256 of the seed,
its own name and its own options), so switching one part on or off never changes another part's result (tested).
Files written: mod.json, tables/Person.csv, tables/DisposUnit.csv, tables/Item.csv, tables/AchieveBonusBattle.csv,
tables/AchieveBonusVisit.csv (only those a part changed), spoiler.txt (slice 1's log, then one section per part:
"Growths and bases", "Skills", "Items, shops and castle rewards", "Enemies"), plan.json (with `topts` and
`tracks`, so `check` can remake it).

Guards: slice 1's nine (re-run after the growth part), plus each part's own, listed in the spoiler log and in
`make`'s output with the part's name in front (29 with everything on). One change to slice 1: with a bases mode
on, the line "personal base total grew" gives way to the growth part's own bound (the total may move by up to the
base variance, the FE8 port's meaning).

Tests: `tests.test_rando_integrate` (12: defaults = slice 1 byte for byte, everything on for 3 seeds with every
guard PASS and the same files twice, parts independent, the bases-mode guard, the mods tool accepts the folder and
`check` remakes it, and the PLAY RANDOMIZED options), plus each part's own tests (`tests.test_rando_growth`,
`_skills`, `_items`, `_enemies`) and `tests.test_randomizer`. check_all row `rando-tracks-tests`.

Robot check (2026-11-20, one job, `tools/randomizer/robot_all.py`, everything under build/rando49/all/, headless,
below normal, its own data/APPDATA/LOCALAPPDATA folders): seed r49all with every option on (9903 changed cells,
103 files installed). Start save bt-ch1-clear and the recorded bt-ch2 presses to frame 5117 (no new play); memory
read at 4800 and 5117 on the Chapter 2 map. With the mod: the 49 Person rows (class, class line, bases, growths,
weapon exp, 5 skill slots, 3 personal skills) = the plan, 0 mismatches; the shop stock of all 355 items and the
160 castle reward rows (515 values) = the plan, 0 mismatches; Gunter's and Felicia's items and equipped skills =
the plan; the 4 enemies matched their rows, 2 of them changed (a Spear Fighter with a Brass Naginata, a Diviner
with a Rat Spirit), class and items = the plan, and every enemy can use its weapons. Then uninstall (0 files left)
and the same run without the mod: everything = the original tables, 0 mismatches. Results
build/rando49/all/robot/all49.json. Not seen: a battle with the new skills or enemies, a shop menu (the stock was
read from the Item rows the shop reads), Hard/Lunatic, later chapters.

## 7. Round 50: the in-game page's parts (F-044 addendum, docs/RANDOMIZER_INGAME.md)

Two new subcommands feed the in-game page. Neither changes `make`'s own output (old seeds unchanged).

- `python tools/randomizer/rando.py schema` prints the page's rows as JSON (26 rows: every row of section 6 plus
  slice 1's switches, `--trees`, `--keep-royals`, and Children shown greyed out, always off). It reads the same lists
  PLAY RANDOMIZED uses, so the two cannot drift apart (code: tools/randomizer/ingame.py).
- `python tools/randomizer/rando.py make --seed S ... --patch-out FILE` runs the usual `make`, then the mods tool's
  compute step (nothing is installed), and writes a text patch: every changed cell with its original value, so the
  engine can check the original before writing and can put it back. Seed r50all with everything on: 102 files,
  9,274 cells.
- The engine side is patch 0007 (patches/zakuro/0007-...): a module `fates_rando` in zakuro-core that finds GameData
  and the current chapter's placement file in memory, checks every cell, writes all or nothing, and reverts. **Nothing
  calls it yet**, so the game runs exactly as before.

Tests: `tests.test_rando_ingame` (8: schema = PLAY RANDOMIZED's lists; the patch laid on memory images of the original
files = the mods tool's rebuilt files for 3 seeds; a second apply is refused; revert = original byte for byte),
check_all row `rando-ingame-tests`; `cargo test -p zakuro-core --lib fates_rando` (11). Robot, read only: GameData in
memory = the file (0 differences); the r50all patch's dry check refuses 0 cells. One finding blocks part of the plan:
the game makes a chapter's units in the same frame it loads that chapter's placements, so the placement rows (the
weapon swaps that go with new classes, starting items, enemy weapons and classes) need a more precise hook before
the page can offer them (owner's choice, round 51).


## 8. Round 51: the in-game page built and robot-tested (F-044, docs/RANDOMIZER_INGAME.md section 12)

- Zakuro patches 0008 (core wiring: frame watcher, test hook, Python hidden, save and state side files, placement
  files), 0009 (the page and the Esc menu's "This run"), 0010 (no false notice at boot; a load is not a new game).
  `play/game/Fire Emblem Fates.exe` rebuilt (zakuro_head 3bd39dd); the earlier program is in
  `build/backup/Fire Emblem Fates.exe.2026-11-20-pre-rando`.
- The placement rows are offered: placement files are laid in the game's read when the patched copy fits, else at the
  first system call after the game stores the file, which the robot showed comes before the units are made.
- Robot (headless, recorded routes): **T2** a randomized new game (r50all, everything on) = the same seed as an
  installed mod, tables and the Prologue's 30 units, 0 differences; **T4** Randomizer off = the old program (memory and
  saves); **T5** saves keep their seed through the Load list and loads, original saves stay original; **T6** a battle
  save comes back randomized, with its chapter's placements. All pass.
- Tests: `cargo test -p zakuro-core --lib` 174 passed (check_all row `rando-ingame-core`), `cargo test -p zakuro --lib`
  79 passed (row `rando-ingame-page`); both rows are slow (cargo builds), run weekly.
- Not done: the owner's look at the page (T7); the next New Game's settings in the Esc window; Classic and Phoenix are
  not recorded.

## 9. Built / not built, row by row against the FE8 port's Randomizer screen (status 2026-11-20, round 58 W2)

Words used: **on the page** = built, tested, and offered on the in-game Randomizer page and in PLAY RANDOMIZED
(robot-checked in rounds 49-51, still waiting for the owner's look, F-037). **PLAY RANDOMIZED only** = wired into
`rando.py` and PLAY RANDOMIZED (the mod folder lays it), shown grey on the in-game page until its engine round.
**Module only** = round 55 wrote the code
and its unit tests, but it is not wired into `rando.py`, the page or the game yet (docs/rando/WIRE_55.md is the wiring
plan). **Designed** = a written design, no code. **Not built** = nothing yet. **Not in Fates** = the FE8 row has no
meaning in this game. The FE8 rows are from the FE8 port's docs/port/PLAYING.md, "Randomizer".

| FE8 port row | Fates status | Where / note |
|---|---|---|
| Randomizer, Seed | on the page | seed is text, kept beside each save (section 8) |
| Growths (Redistribute / Delta / Full), Growth variance / min / max, Adjust HP growths | on the page | `--growth-mode` etc. (section 6); plus slice 1's own Growths switch |
| Bases (Redistribute / Delta), Base variance | on the page | `--bases-mode`, `--base-variance`, `--scale-to-level`; plus slice 1's Join stats switch |
| Class movement | on the page (round W1) | `--class-move off/small/wide` (docs/rando/MISC.md). Grok's pick (W1): keep the no-stuck rule, so it mostly makes classes faster; label says so |
| Constitution | not in Fates | Fates has no Con stat |
| Affinity | not in Fates | Fates has no support affinities |
| Player classes | on the page | slice 1 Classes switch, `--trees own/any` |
| Include lords | on the page (inverted) | `--keep-royals` (default on: the four royals with legendary weapons keep their class); Corrin never changes |
| Include thieves | not needed | thieves keep their lock-opening skill in any class; no thief exclusion row |
| Include dancer | not built (fixed) | Azura always keeps the Songstress class (story-critical); no row |
| Monster classes | not in Fates | beasts (Kitsune / Wolfskin) stay beasts and nobody else becomes one; no row |
| Assign evenly | on the page (round W1) | `--assign-evenly` (docs/rando/MISC.md): slice 1 again with the even classes, before every other part |
| Match gender | on (fixed) | always on: every class pick uses the person's gender row; no row |
| Class growths (Keep / Transfer), Class bases (Final / Personal) | not needed as such | Fates adds class growth and base itself; slice 1 already behaves like Keep / Final. Round W1 adds the class rows themselves: `--class-growths delta`, `--class-bases delta` (docs/rando/STATS.md) |
| Random promotions | on the page (round W1) | `--promotions`, `--promotion-sides`, `--reclass` (docs/rando/PROMOTIONS.md): two random Master Seal choices per class, plus "Heart Seal classes: Keep / Random"; everyone's job_low (children too) follows the new promotions |
| Every promotion has three choices | later (engine) | the Fates menu shows two; a third needs a game-code change (owner OK at that round) |
| Monster promos | not in Fates | no monster classes |
| FE7/FE6 classes, Keep colours | not in Fates | FE8-only (other GBA ROMs; GBA palettes) |
| **Recruitment** (who joins where), Recruit class (Own / Slot), Recruit stats (Autolevel / Slot), Cross-gender | **PLAY RANDOMIZED only (round W2)** | `--recruit off/route/any`, `--recruit-look keep/full`, `--recruit-class own/slot`, `--recruit-stats autolevel/slot` (docs/RANDOMIZER_RECRUIT.md, docs/rando/RECRUIT.md); same-sex only. The mod folder lays every table cell, the route-variant rows included; full swap's portraits and names inside dialogue wait for engine rounds E3/E4. On the in-game page since engine round E1 (round 59, section 13; the look row stays at "keep the face" until E3/E4). Smoke-checked at Chapter 2 (section 13) |
| Boss classes, Enemy classes | on the page | `--boss-classes`, `--enemy-classes`, `--enemy-trees`, the "no stuck enemies" terrain rule (docs/rando/ENEMIES.md) |
| Enemy growths, Enemy buff | on the page (round W1) | `--enemy-growths off/flat/scaling`, `--enemy-buff` (docs/rando/STATS.md); `--enemy-levels` is PLAY RANDOMIZED only until the next engine round |
| Boss stats, Boss max boost | PLAY RANDOMIZED only (round W1) | `--boss-stats off/linear/ease`, `--boss-max-boost`, `--boss-variance`; on the in-game page since engine round E1 (round 59, chapter person files laid in the read) |
| Better enemy weapons | on the page | `--enemy-weapons` shuffles them (same kind); round W1 adds the FE8 port's chance: `--enemy-upgrade 0-100` (never loses an "effective against" bonus, Grok's pick); `--upgrade-rank next` waits for its robot check |
| Tower & Ruins | not in Fates | (closest: the paralogue / castle invasion maps; not randomized) |
| Weapon might / hit / weight / uses | on the page (round W1) | `--weapon-stats` (might, hit, crit, avoid, staff uses; docs/rando/WEAPONS.md) |
| Weapon traits | on the page (round W1) | `--weapon-traits 0-100`, `--wild-traits` (shown only in the spoiler; the in-game help text stays) |
| Rewards | on the page, partly | `--rewards`: castle battle / visit rewards. Chests and villages live in chapter scripts: not changed |
| Enemy drops | on the page (round W1) | `--enemy-drops 0-100` in steps of 5 (the page rounds to 5s); drops the game had stay (docs/rando/MISC.md) |
| Shops | on the page | `--shops`, `--shop-sides` (the four castle shops; prices stay) |
| Master Seals only | not needed | Fates' Master Seal already promotes every class; the seal supply stays the original (docs/rando/ITEMS.md) |
| Random music | PLAY RANDOMIZED only (round W2) | `--music off/maps/maps+battles` (docs/rando/MUSIC.md): map themes in `romfs/map/config/*.bin`, battle themes in PersonChapter; on the in-game page since engine round E1 (round 59); a new name is never longer than the old one (FITS rule, docs/rando/MUSIC.md guard 8). Chapter 2's map settings file was patched in the game's read in the smoke; the song heard is not checked yet |
| Nuzlocke | page row live (round 60, engine round E2: patch 0024; round 61: patch 0025, in play/game since the round-61 assemble: the gate is the player army, not the camera-angle byte GameConfigData +0xB that kept the round-60 core off on Birthright's bt-ch9-clear, robot smoke passes there on the final build; section 15 is the round-60 history) | `--nuzlocke on` writes `nuzlocke.json` beside the patch; the core keeps a graveyard beside the save, puts the fallen back among the fallen after any save or state load, and locks Classic; `--recruits first` is grey (Grok: a story ally cannot be told from a recruit); PLAY RANDOMIZED accepts `--nuzlocke on` since round 61 (profile run `profile-nuzlocke`; recruits first still refused) (docs/rando/NUZLOCKE.md) |
| (Fates only) Personal skills, Skill slots | on the page | `--personal-skills keep/shuffle/random` (swaps skills, not people), `--skill-slots` |
| (Fates only) Starting items | on the page | `--starting-items` |
| (Fates only) Children | on the page (round W1) | `--children` (docs/rando/CHILDREN.md): class, growths, one skill; the parents stay; a live child paralogue join is not robot-checked yet (no recording reaches one) |

Next steps: docs/rando/WIRE_56.md section 8: the robot round T1 (section 6's "yes" checks, music through the mod
folder), then the engine rounds E1 (the shuffle and music on the page), E2 (Nuzlocke), E3/E4 (full swap). Section 11
below is round W2. The check_all rows of round W1: `rando-more-tracks-tests`
(children, promotions, music, Nuzlocke), `rando-r56-tracks-tests` (weapons, stats, misc), `rando-recruit-tests`
(slow, weekly), and the extended `rando-tracks-tests` / `rando-ingame-tests`.

## 10. Round W1: children, promotions, stats, weapons and misc wired (F-046 / F-047, docs/rando/WIRE_56.md)

Every option below is **off** (or 0) by default and then changes nothing. A seed made with only the older options gives
the same files as before W1 (the new options are written into mod.json / plan.json only when not at their default, and
the cross guards run only with a W1 part on). `rando.py make --help` lists the flags.

| Row on the page (PLAY RANDOMIZED shows the same) | Flag | Values (default first) | Everything on |
|---|---|---|---|
| Spread classes evenly (fewer repeats) | `--assign-evenly` | off / on | on |
| Random promotions (Master Seal choices) | `--promotions` | off / on | on |
| Promotions stay on own side | `--promotion-sides` | any / own | any |
| Heart Seal classes | `--reclass` | keep / random | random |
| Children (class, growths, one skill; parents stay) | `--children` | off / on | on |
| Class growth rates / How much (in 5s) | `--class-growths`, `--class-growth-variance` | off / delta; 10 (0-50) | delta, 10 |
| Class base stats / How much | `--class-bases`, `--class-base-variance` | off / delta; 2 (1-5) | delta, 2 |
| Class movement | `--class-move` | off / small (1) / wide (2) | small |
| Weapon stats (might, hit, crit, avoid, staff uses) | `--weapon-stats` | off / on | on |
| Weapon special powers (chance per weapon) / Wild powers too | `--weapon-traits`, `--wild-traits` | 0 (0-100); off | 25, off |
| Stronger enemy weapons (chance) | `--enemy-upgrade` | 0 (0-100) | 25 |
| Stronger weapons may be one rank higher | `--upgrade-rank` | same / next | same (grey on the page: "next" after its robot check) |
| Enemies grow faster / Extra growth % | `--enemy-growths`, `--enemy-buff` | off / flat / scaling; 10 | flat, 10 |
| Enemy levels up | `--enemy-levels` | 0 (0-5) | 0 (on the page since engine round E1) |
| Tougher bosses / Most extra points / Random spread | `--boss-stats`, `--boss-max-boost`, `--boss-variance` | off / linear / ease; 5; 0 | linear (on the page since engine round E1) |
| Enemies drop items (chance per enemy) | `--enemy-drops` | 0, or 5-100 in steps of 5 | 10 |

The old switch name `--children` now feeds the children part (slice 1 itself never randomizes children).

**Order** (each part has its own sub-seed from the seed text, so the order never moves a draw; it matters only where
parts share cells): slice 1 -> spread classes evenly (slice 1 again with the even classes, `randolib.make_plan(...,
classes=...)`) -> growth -> promotions (job_low follows the new promotions, for the children too when the children part
is off) -> skills -> children (with the final promotions) -> items -> enemies -> stats -> enemy drops (on the final
enemy items) -> weapons (a drop is never upgraded) -> class movement (on the final enemy classes) -> cross guards.

**Cross guards** (in `plan["guards"]` as `cross: ...`, and in the spoiler): `job_low_fits_final_promotions` (every army
row, children included, has a job_low among the final promotions of its class; closes the round-55 gap where 14-16 of 22
child rows did not), `no_stuck_final` (every enemy with a new class or Move still reaches 3/4 of its old tiles in 3
turns), `weapons_usable_final` (every enemy weapon a part touched is usable by the final class), `one_writer_per_cell`
(no cell written by two parts with different values, except slice 1 -> items, enemies -> weapons and slice 1 ->
promotions, which must chain). Any failed guard: exit 2, no install, no patch.

**Files**: `tables/Job.csv` (one row per class: promotion cells, class growths / bases / enemy growths, Move),
`tables/PersonChapter.csv` (enemy levels, boss bases; GameData/Person files), `tables/Item.csv` (shop stock and weapon
stats by column), `tables/DisposUnit.csv` (plus `item_N_flags` for drops), `tables/Person.csv` (job_low, Heart Seal
classes, the children's rows). The spoiler has one section per part.

**Module fixes made in W1** (WIRE_56 section 2c): Monk / Shrine Maiden, Great Master / Priestess and Butler / Maid now
count as one class each in class movement and assign evenly (from `rules.json` `scope.job_pairs`, else the Job rows'
own gender pairs); the class-movement guard checks the upper bound for promoted classes too; stronger enemy weapons
never swap an effective weapon (e.g. a dragon-slaying sword) for one without that bonus (Grok's pick (a)); the stats
guard that could never fail (`bosses_beatable`) is replaced by `boss_gain_follows_story` (each boss stat gains at most
its chapter's story-position buff plus the variance); the enemy scope rules (story chapter files, guarded chapters)
come from the tables object (`rules.json` `scope`, F-047). Grok's pick for class movement: keep the no-stuck rule
(mostly faster, the label says so).

**In-game page**: the rows come from `rando.py schema` (no engine build), in WIRE_56 section 3's order. Grey with a
reason: Who joins where and its three rows, Music, Nuzlocke and its row (not wired yet), Enemy levels up and Tougher
bosses (next engine round), and "one rank higher" (robot check). `make --patch-out` refuses the grey options with the
reason, so a half-made patch cannot happen.

**Help line for the page** (one sentence each): who never moves in the shuffle (Corrin, Azura, the royals, Gunter, the
children; Nyx and Shura held until their chapters pass); weapon special powers show only in the spoiler; enemy growths
also speed up allied NPCs; music never touches scenes, the title or songs a character sings.

**Results (round W1, host, 2026-11-20):** old seeds byte for byte the same (r50def, r50all, r50shops, a fourth seed:
mod folders and patches); every `tests/test_rando_*.py` plus `tests.test_randomizer` and `tests.test_check_all` pass
(356 tests, 1 skipped); a sweep of 24 seeds over six option sets (everything on at the extremes: trees any, royals
free, wild powers, rank next, enemy levels 5, boss boost 20, drops 50, wide Move) passes every guard after one fix the
sweep found (children with random personal skills: when the adults hold most skills, a child left without a free
skill could keep one another child drew; now it cannot). One headless robot smoke run (the in-game answer path, seed
r56w1, every row that is not grey at its Everything-on value): the game made the seed through `rando.py` (81 guards
pass, 0 fail) and laid 1853 GameData cells at the New Game mode pick, exited by itself, no window.

**Not checked in a game yet** (robot round T1, WIRE_56 section 6): promotions in memory and a Master Seal menu, a boss
and a generic enemy with the planned stats, an upgraded enemy attacking with its new weapon, a marked enemy dropping its
item, a class moving its new Move, a child paralogue join.

## 11. Round W2: the character shuffle, music and the Nuzlocke rules file wired; route-variant joins fixed (round 58)

Host only, no game started. Every new option is off by default and then changes nothing: with the shuffle off,
`recruit.py` is not even imported (the R8 rule) and the facts stay the same object; music and Nuzlocke are kept out of
mod.json / plan.json while at their default. The check (HEAD's code against this round's, eight cases): every seed with
Classes off gives the same files byte for byte; seeds with Classes on change only in `tables/DisposUnit.csv`,
`plan.json` and `spoiler.txt` (the route-variant fix below; `tables/Person.csv` is unchanged).

| Row (PLAY RANDOMIZED; grey on the in-game page) | Flag | Values (default first) | Everything on |
|---|---|---|---|
| Who joins where (character shuffle) | `--recruit` | off / route / any | route |
| Shuffled people look like | `--recruit-look` | keep (the spot's person) / full (themselves) | keep |
| Shuffled people's class | `--recruit-class` | own / slot | own |
| Shuffled people's level and stats | `--recruit-stats` | autolevel / slot | autolevel |
| Music | `--music` | off / maps / maps+battles | maps+battles |
| Nuzlocke (shown, "not yet" in PLAY RANDOMIZED) | `--nuzlocke` | off / on | never |
| Only the first new ally per chapter (with Nuzlocke) | `--recruits` | all / first | all |

**The shuffle's options are their own dict** (`ropts`, `tracks.RECRUIT_DEFAULTS` = `recruit.DEFAULT_OPTS`), not part of
the track options, so old seeds' mod.json never changes; `ropts` goes into mod.json, plan.json and the spoiler header
only when the shuffle is on, and `rando.py check` passes it back.

**Order**: the shuffle runs first (`recruit.plan_recruit` on the tables object, its guards R1-R7 and weapons_usable as
`recruit: ...`, then `recruit.shuffled_facts`): slice 1 and every later part plan on the shuffled army. Music runs after
class movement, Nuzlocke last (no table edits), then the cross guards, which now also run with the shuffle or music on.
`one_writer_per_cell` lets any later part build on a shuffle cell (all of them start from the shuffled facts).

**Files**: the shuffle's GameData cells that no later part wrote are added to `tables/Person.csv` (a later part's value
wins where both write); its placement cells (`jid`, items) to `tables/DisposUnit.csv`; its route-variant rows
(GameData/Person/{A,B,C}_HANDOVER, which are PersonChapter-layout rows) to `tables/PersonChapter.csv`. Music writes
whole `romfs/map/config/<chapter>.bin` files (rebuilt from the game's own bytes) and its `combat_music` cells into
`tables/PersonChapter.csv`. With more than one part writing PersonChapter (stats, music, the shuffle) the CSV is merged by
row and column (one part alone keeps its own CSV byte for byte). Nuzlocke writes `nuzlocke.json` (the rules file the
core will read in engine round E2). Full swap's portrait / name records go into `plan.json` only (`recruit_engine`).

**In-game page**: the seven rows come from PLAY RANDOMIZED's list now, still grey and at their default, and still
without a flag, so the page's command line is the same as in round W1. `make --patch-out` refuses the shuffle, music and
Nuzlocke with the reason (engine round E1 / E2); the mod folder is still written.

**Route-variant joins (owner OK, F-046)**: `gamedata.load_facts` now also reads the HANDOVER rows (`Facts.handover`,
`Facts.variant_of`). Slice 1's new step 5: for every placement that names a route-variant row of a person whose class
changed, the new class goes into the placement's `jid` (a cell the in-game core lays), and carried weapons that class
cannot use with the route row's own weapon exp are swapped (own random keys, so no other draw moves). `weapons_usable`
and `only_allowed_cells` cover these placements; the spoiler lists each one ("route-variant join ... joins as ...").
On the game's data: 32 such placements (27 rows), all in the same tier as the main row; seed hv1 gives 26 jid writes.

**Slice-1 fix found with the shuffle on**: a filler moved to an early spot can get a negative personal base total from
"fit the spot's level"; slice 1's Join stats then raised every stat to 0 (seed w2a, Kaze's spot: +30 points, the guard
"personal base total grew" failed). Now, only when the total is below the floors (no row of the game is), the negative
bases are kept, cut so no stat of the new class drops below 0 (HP below 1). Old seeds do not change.

**Results (round W2, host, 2026-11-20):** every `tests/test_rando_*.py` suite plus `tests.test_randomizer` passes
(271 tests: integrate 26, ingame 12, recruit 14, slice 1 18, children/promotions/music/nuzlocke 81,
weapons/stats/misc/profile 71, growth/skills/items/enemies 49). New tests: route-variant joins (made-up tables and the
game's data), W2 defaults change nothing (and recruit / music / nuzlocke are not imported), everything on with the
shuffle and music (every guard, mods tool accepts, `check` remakes byte for byte), every shuffle cell reaches the
files, parts do not disturb each other, PLAY RANDOMIZED refuses Nuzlocke ("not yet"), `--patch-out` refuses the
shuffle / music / Nuzlocke. Samples: w2a (everything + shuffle route + music + Nuzlocke), w2b (shuffle any, full swap),
w2c (shuffle only, slot / slot, Classes off), w2d (music maps), w2e (CLI: shuffle any full, music, Nuzlocke, boss stats,
enemy levels, children, promotions): all guards pass; w2e `check` byte-identical, mods tool 0 errors.

**Not checked in a game yet**: the shuffle, music and the route-variant jid in memory (robot round T1 for music and
the jid through the mod folder; engine round E1 for the shuffle on the page).

## 12. Round 58: the everything-on check on all four paths (F-047)

Owner's rule: both halves are needed, "make sure things don't break, AS WELL as making sure each setting is visibly
working". Plain report: docs/REPORT_2027-01-01.md. Contact sheet: `build/r58/sheet/index.html` (650 PNGs; numbers
in `build/r58/sheet/verdicts.json` and `build/r58/check/half1.json`). Nothing counts as done until the owner says
ok (F-037).

**How:** each seed was made on the host as the game makes it, laid into a copy of a packed clear save, and driven
by chapter select (docs/tests/CHAPSEL.md) in headless boot-servers: preparations, unit page, inventory, map, enemy
phase, battle save, reload in a second server, memory read at the map and after the reload. 553 jobs, at most 4 at
once.

**Bugs found and fixed:** (1) `randolib.stats_within_caps` refused every Seal seed with Join stats off (the mod's
own Faceless has luck -1); a stat below 0 now counts only when the plan made it lower than the game's own data.
(2) Patch 0014: a randomized battle save loaded from the title was taken for a New Game (answered off, original
tables back, HP cut). (3) Patch 0015: placement files patched during the read had wrong class/item labels in
memory (Rinkah and Kaze joined with no weapon at A004). From the assemble step: the shuffle guard allows the buff
its own floors force (owner OK, F-046 addendum), and `rando.py make|check --game fates|seal`.

**Half 1 (nothing breaks):** 0 panic or guest-fault lines in 553 jobs; every reached map had all its cells right,
before and after the reload, on the final engine. Birthright 34 full passes (A002-A006 at map start through their
recorded routes; not reached: A007, A016, A017, X009, X010, X012, X014), Conquest 28 of 30, Revelation 19 of 22,
Seal 35 of 41 to the enemy phase, but Seal save/reload fails there with the randomizer off too.

**Half 2 (visibly working):** table in docs/REPORT_2027-01-01.md. The review withdrew robot PASSes whose OFF and ON
shots were not at the same spot or showed no change (A016 x5, Seal R010 drops, S002 and C014 classes, C014 skill
slots). Only 7 pairs are confirmed by eye; the other PASS cells are robot pixel-diff claims still to be looked at.

## 13. Round 59: engine round E1, the shuffle, music, enemy levels and tougher bosses on the in-game page

**In plain words.** The in-game page can now lay four more things: the character shuffle ("keep the face": the
person in a join spot plays as someone else, with that person's class, stats, growths and skills), random music
(map and battle themes), Enemy levels up and Tougher bosses. These were PLAY RANDOMIZED only. Fates and Seal of
Flames both. Still grey: the full swap look (engine rounds E3/E4), Nuzlocke (E2), and "one rank higher" for
stronger weapons (its robot check). Nothing counts as done until the owner says ok (F-037).

**How.** Engine patch 0016 (patches/zakuro/README.md) adds two file kinds to the in-memory patch: `person`
(`GameData/Person/**`: the chapter person files and the route-variant HANDOVER files) and `mapconfig`
(`map/config/<chapter>.bin`, the map theme names). Both are patched only inside the game's own read, as the
placement files are. Song names are written over the old ones in the file's own string pool, never longer
(Grok's pick A, docs/collab/E1_MUSIC_GROK.md), so these files keep their size and need no label pointers.
`ingame.make_patch` refuses anything else in these files, so a half-made patch cannot happen. `make --patch-out`
now refuses only the full swap look and Nuzlocke.

**Music change (all paths):** a new song name is never longer than the old one (docs/rando/MUSIC.md guard 8). The
reversed prologue song stays on the Prologue; the four amiibo boss songs only replace each other. Music seeds made
before round 59 give different music now.

**The shuffle buff (F-046 addendum):** the guard allows a personal base total to grow by exactly what the floors
force (round 58 assemble step). Proof over unpicked seeds: build/r59/e1/seeds_def_pre.json (seeds u0-u199 in each
of route/any x autolevel/slot, default rows: 800 made, 0 refused) and seeds_all*.json (the same with every row on).

**Smoke (headless, e1's own boot-server, recorded Chapter 2 route, build/r59/e1/jobs/):** seed e1smoke2 (shuffle
any, music maps and battles, enemy levels 3, bosses linear; classes, growths and join stats off). Felicia's spot
joined as a Master Ninja with Kagero's stats (HP 27, bases from Kagero levelled to the spot); with the randomizer
off she is a Maid, HP 19. The two Samurai are level 5 (off: 2). Memory readback: all 430 GameData cells, the 2
Chapter 2 placement cells and the 3 chapter-person cells hold their new values (off: their old values). The core's
log: `GameData/Person/A002.bin.lz patched in the read (3 cells)`, `map/config/A002.bin patched in the read (1
cells)`. No fault.

**The Seal edition's smoke** (round 58, chapter select S002): moved to docs/seal/RANDOMIZER_SEAL.md in round 84.

**A fault found and fixed (patch 0017):** the first Seal smoke read the boss's song name back as other bytes. The
game decompresses these files in place, and its own LZ13 outer size is exactly what that needs (checked on all 302
person and placement files). Our patched files kept the original size field, so the end of the file (the string
pool, where labels and song names live) was overwritten while it was decoded. This is also the cause of round 58's
wrong placement labels (patch 0015 had routed around it). Fixed: the core writes the outer size its own stream
needs; after it, Seal S002 and Fates A002 read back right in every cell.


## 14. Round 59 results: assemble and the everything-on check (2026-11-21)

**In plain words.** The final build is in play/game. It has patches 0001-0021: 0018 is the Seal save fix, 0019 the
recolour, 0020 the background make, and 0021 the size fix to 0018. Nothing counts as done until the owner says ok
(F-037).

**Start.** The page makes the game in the background, and any change throws the guess away. Start game lays
exactly the page's values, and nothing is laid before it. With the make already finished, the mode pick to "laid"
took 9-16 ms (Fates) and 110-141 ms (Seal). If rows change right before Start, the wait is 2-8 s. These are
headless log times; no real-page robot timed it. docs/rando/SPEED.md section 7.

**Recolour.** Only the battle hair and the face-data colour change. The portrait and map-sprite recolour was not
built, because it damaged portraits. docs/rando/COLOURS.md section 7.

**Break check** (build/r59/check/break.json, break2.json): every chapter, off plus all1-3.

| Path | Result | Failures |
|---|---|---|
| Birthright | 41/41 | none; A004 all2 passes now |
| Conquest | 30/30 | none |
| Revelation | 22/22 off and all1 | C026 all2 and C012 all3: the enemy phase did not return; cause unknown |

The Seal edition's row of this check: docs/seal/RANDOMIZER_SEAL.md (moved in round 84).

**Pairs** (build/r59/check/pairs-verdicts.json, sheet build/r59/sheet/index.html): the per-setting table is in
docs/REPORT_2027-01-02.md. Still FAIL on every path: class growths, castle rewards, stronger enemy weapons (the
dice move) and music (cannot be seen).

## 15. Round 60 results (2026-11-21, report docs/REPORT_2027-01-03.md)

Final build (build/r60/FINAL_SHA.txt): play/game exe 09740aa7, boot-server a3f0bc67, capture library 610f791d,
engine pin c856685 + patches 0001-0024. Backups: build/backup/*.2026-11-21-pre-r60.
- Break check 536/536 on the final build (4 paths x off/all1/all2/all3): Seal R021/R023/Y004 reload with equal units
  (patch 0022), Seal R013/R023 take the patched person file (patch 0023), so every Seal chapter gets the randomizer.
- Per-setting table after the check reviewer's review (build/r60/integrate/table_reviewed.json): 116 cells, 56 SEEN,
  41 robot-only, 10 memory-only (music x4, castle rewards x4, shops Revelation/Seal), 9 FAIL (boss classes x4, Seal
  recolour, Conquest class growths, Revelation skill slots, Seal children, Birthright stronger enemy weapons).
- Fixed this round: starting items for route-variant joins (items.py, track screens). Not fixed: the same bug in
  skills.py (plan build/r60/screens/plans/SKILLS_VARIANTS.md).
- Nuzlocke (patch 0024): passes on Conquest, Revelation and Seal; **fails on Birthright** (save bt-ch9-clear: the core's
  gate byte GameConfigData +0xB stays 1, so the fallen stay in the army; at A010 they stay on the map). The graveyard
  entries have turn 0 and an empty name (the core does not read them yet).
- Not run: the real-page robot (pagebot.py needs the FEF_PAGEBOT exe hook, plan build/r60/screens/plans/PAGEBOT_HOOK.md)
  and the music audio fingerprint (needs a boot-server audio command, plan build/r60/screens/plans/SERVER_AUDIO.md).

## 16. Round 61 results (2026-11-21, report docs/REPORT_2027-01-04.md)

Final build (build/r61/FINAL_SHA.txt): play/game exe ff85e43d, boot-server 4d0b60c9 (with the audio command), capture
library 610f791d, engine pin c856685 + patches 0001-0026. Backups: build/backup/*.2026-11-21-pre-r61.
- Nuzlocke (patch 0025): the gate is the player army, not the camera byte; passes on all 4 paths on the final build,
  Birthright included. PLAY RANDOMIZED accepts Nuzlocke.
- Page robot hook (patch 0026) built; the real page lays exactly what a fresh make of the final values gives (Fates
  and Seal). Start game to the avatar screen: about 0.6 s with the guess finished, 6-7 s when rows changed after it
  (fails the robot's 2 s check).
- Music proven by sound on all 4 paths (boot-server `audio` command, tools/harness/audioproof.py).
- skills.py: route-variant HANDOVER rows follow their main row; enemies.py: boss classes no longer moves the enemy key.
- Break check: 534/536 (Seal Y006 all1/all2: robot could not open the map menu for the save step).
- Table after review (build/r61/integrate/table_reviewed.json): 116 cells, 66 SEEN, 43 robot, 6 mem, 1 FAIL (Seal
  Children, owner call).

## Round 62 (F-049)

Growth floor (every total growth 20-100), one-step stronger enemy weapons by a new Difficulty row, tier-matched boss classes for story bosses (robot-proven list), tougher bosses scaled by the difficulty (Conquest chapter-only army bosses included), Children greyed for the Seal edition: docs/rando/R62.md (core page change: docs/rando/R62_CORE_PAGE.md, applied as patch 0029). Final check: docs/REPORT_2027-01-06.md. Open: the tougher-boss weapon part is one might point short on Normal and Hard (a forge level shows +1 on screen), and most story bosses are not yet shown past their scenes in the new class (only Revelation C017).

## Rounds 63-64 (F-049, F-051, lean)

Round 63: tougher bosses show +1 / +2 / +3 weapon might (docs/rando/BOSS_MIGHT.md); 13 more story/generic bosses proven past their scenes. Round 64: 10 of the 11 bosses round 63 could not fight are proven too (24 of 25; A023 Arthur not fought, stays changing; docs/tests/STORY_BOSSES.md); the Seal edition's boss might and its own Boss classes list: docs/seal/ (its boss page); Conquest recolour SEEN (docs/tests/RECOLOUR_CQ.md); item flag 0x8000 proven to be the drop, the forge rule stays (docs/rando/DROP_FLAG.md). Not built: a separate Recolour on/off row (F-047 asks only for an on/off picture pair; recolour follows the shuffle's keep-the-face look, so the check's OFF side is a test-only run with the colour lines taken out).
