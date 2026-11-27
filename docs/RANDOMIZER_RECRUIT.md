# Randomizer: the character shuffle (who joins where), design and round plan

**For the owner.** The "Personal skills: shuffle" row never moved characters. It only swapped each person's
personal skill with someone else's, and the label made it look like more. That row is now called
**"Personal skills (shuffle = swap the skills between characters)"**. Its choices and its command-line flag did not
change. The real character shuffle was never built: F-043 #1 held it back "until the owner asks", and you asked on
2026-11-20. The other missing parts you asked for (children, promotions, music, Nuzlocke) were built in round 55 as
separate modules with their own tests, but **they are not on the page yet**. F-046 leaves the wiring to a later
round, which is why the page still says "Children (not built)".

How the shuffle works, the way the Sacred Stones port does it: each join spot stays where it is in the story, and
the person in it changes. If Subaki ends up in Hana's spot, he joins when Hana would have joined, at her level, and
the story still works because every scene only looks for "Hana's spot". There are two looks, as F-046 decided.
**Keep the face** leaves the spot looking and sounding like Hana while she plays as Subaki (his class line, growths,
stats and personal skill). **Full identity** shows Subaki everywhere the game lets us: his name in menus, his
portrait in scenes, his model and battle voice, and his name in the dialogue. Full identity needs new hooks in the
game core, so it needs engine builds, and the robot must pass it on the four known trouble chapters first.

The plan is **8 more counted rounds** after this one (9 in total, 11 if the cheat-poke checks or the
missing-expression case need a second pass). That is inside the 8 to 12 you were told. Keep the face is playable
from the page after round 3 of the plan. Full identity comes after round 6.

Status 2026-11-20, character shuffle design round (F-046, round 54; it ran next to round 53's game picker and did
not touch its files). Host only: no game run, no robot run, no build. Inputs: the four research pages
docs/rando/RECRUIT_JOINS.md, RECRUIT_SCRIPTS.md, RECRUIT_PRESENTATION.md and RECRUIT_PITFALLS.md, Grok's
docs/collab/RANDO_REST_GROK.md, F-043, F-044 and F-046, and the FE8 port's PLAYING.md "Recruitment" rows. The public
Fates randomizers (Ignis and Paragon by thane98, lashoun's upgraded-fefates-randomizer, the 2016 GBAtemp randomizer)
are GPL. This page uses **facts only** from them (their list of known breaks) and no code. They are credited here and
in the spoiler header of every shuffled seed.

## 1. The approach: swap who the spot is, never rewrite the story

There were three choices:

| Way | What changes | Cost | Verdict |
|---|---|---|---|
| **A. Swap who the spot is** (the FE8 port's way) | The Person row behind each spot's person id (`PID_`), plus that person's route-variant rows. For full identity, what the spot's face, name and model labels **show** | table cells, plus engine hooks for full identity | **chosen** |
| B. Move the ids (the public tools' way) | about 2,330 references in about 265 files: placements, handover rows, castle joins, and the event scripts, which reach their strings through byte offsets and would have to be rebuilt | very high; a single missed reference gives a duplicate or a scene that waits forever | rejected: this is where the public tools' breaks come from (RECRUIT_SCRIPTS.md section 2) |
| C. Mix (A for most people, B for a few) | the worst parts of both | | rejected |

Why A is safe. The event scripts name people **only** by `PID_` (RECRUIT_PRESENTATION.md section 1: no `AID_`,
`FID_`, face or voice label in any script). Every join, talk, transfer, scripted exit, death check and support
therefore keeps working, because each one still finds its spot. Each public break maps onto A like this:

- **Revelation 8, two Hayatos.** Hayato joins through his route-variant row `PID_C_ツクヨミ`, which Revelation 9
  places twice (two item variants, only one used per play). Way A gives every row of a spot the same filler, so
  there can be no duplicate (guard R3).
- **Conquest 9, the Nyx talk.** The talk stays Nyx's talk on Nyx's id. Nothing in the chapter is edited.
- **Conquest 16, the spare prompt.** No script is edited or removed, ever.
- **Revelation 13, invisible obstacles.** No table link was found. This one is a robot picture check.

The unit of the shuffle is the **spot = one main `PID_`** together with all its route-variant rows (the HANDOVER rows
`PID_A_*`, `PID_B_*`, `PID_C_*`, 27 rows: RECRUIT_JOINS.md section 1). A spot exists on the routes where that id is
placed or transferred. The swap is one permutation over ids and is decided at New Game. The route is chosen later,
in chapter 6, so the same permutation works for whichever route the player takes. Since it is a permutation, each
filler appears exactly once on every route where the spot exists.

## 2. The options (page rows and command-line flags)

| Row (page label) | Flag | Choices (default first) | "Everything on" | What it means |
|---|---|---|---|---|
| Character shuffle (who joins where) | `--recruit` | **off** / route / any | route | off = nobody moves. route = a person only takes the spot of someone from the same route group (section 3). any = any spot in the pool, any route group |
| &nbsp;&nbsp;Shuffled people look like (keep the face / full identity) | `--recruit-look` | **keep** / full | keep | keep = the spot keeps its own face, name, model and voice and plays as the filler. full = the filler is shown (section 5) |
| &nbsp;&nbsp;Recruit class (own / spot's) | `--recruit-class` | **own** / slot | own | own = the filler's own class line, promoted or unpromoted to match the spot's tier. slot = the class the spot had |
| &nbsp;&nbsp;Recruit stats (autolevel / spot's) | `--recruit-stats` | **autolevel** / slot | autolevel | autolevel = the filler's own bases, levelled up or down to the spot's join level with the filler's own growths, separately for the main row and each route-variant row. slot = the spot's stats |

Fixed in the first version and not offered as rows, said in the row's help text instead:

- **Lords and story people never move:** both Corrins, Azura, Gunter (his leaves and returns span chapters), and
  the eight royals (Ryoma, Takumi, Hinoka, Sakura, Xander, Leo, Camilla, Elise: vein flags, legendary weapons, and
  the chapters named after them; Grok pick 1: "lords fixed").
- **Children stay out** (F-043 #4). The children track (round 55) reads the parents' **spots**, so a shuffled parent
  passes on the filler's data. That is what the game itself does, and the spoiler says so.
- **Same sex only.** Bodies come from the class plus the female flag, dialogue pronouns are written in the text, and
  S-rank lists are per spot. Cross-sex is a later yes, as in the FE8 port.
- **Held out until their chapter passes the robot:** Nyx (Conquest 9) and Shura (Conquest 16, the spare prompt).
  Their spots keep them. The hold list lives in `config/randomizer/rules.json` (`recruit_hold`), so freeing them later
  is a one-line change with a test.
- **Out of the pool:** Mozu (her paralogue and special class), Anna (no join on the cartridge), download, amiibo and
  capture-only people, Kana, and every child.

Interplay with the slice 1 switches (shown in the page help):

- With **Classes on**, slice 1 deals a new class to the spot after the shuffle, so Recruit class matters only when
  Classes is off. Class trees "own" then means the filler's side, not the spot's.
- With **Growths** or **Join stats** on, slice 1 varies the filler's numbers, not the spot's old ones.
- So **keep the face with all three slice 1 switches on** changes very little you can see: the personal skill, the
  weapon ranks, and the starting point of the random stats. Keep the face shows most with Classes off. The help
  text says this plainly, so nobody thinks the shuffle failed.
- **Personal skills: shuffle** runs after the recruit shuffle, on the fillers. The two stack.

## 3. The pools (from RECRUIT_JOINS.md section 4)

"route" shuffles inside each group, by sex. "any" merges groups 1-3. The castle group always stays a pool of its own.

| Group | In the pool (after the fixed and held people) | Men / women |
|---|---|---|
| 1. Birthright + Revelation | Rinkah, Hana, Subaki, Saizo, Orochi, Azama, Setsuna, Hayato, Oboro, Hinata, Kagero, Reina, Kaden, Scarlet | 6 / 8 |
| 2. Conquest + Revelation | Arthur, Effie, Odin, Niles, Selena, Beruka, Laslow, Peri, Benny, Charlotte, Keaton | 6 / 5 |
| 3. All three routes | Felicia, Jakob, Kaze, Silas | 3 / 1 (Felicia has no partner of her sex here, so she stays unless "any") |
| 4. Castle joins | Izana, Fuga, Yukimura, Flora | 3 / 1 |

Beasts: Kaden and Keaton carry the beast flag `SPID_ラグズ`. Under "own" class the flag goes **with the filler** (it
belongs to the class line), so a beast can fill a human's spot and the other way round. Revelation 13, where both
join, is then the first robot check (section 7).

## 4. Guards (run at plan time on the host; a failed guard means no patch and the page refuses the seed)

| # | Guard | Why |
|---|---|---|
| R1 | the map is a permutation of each pool: every member exactly once, nobody lost, nobody twice | no duplicate, no missing recruit |
| R2 | fixed, held and out-of-pool people map to themselves | lords, story people, holds |
| R3 | every route-variant row of a spot gets the **same** filler as its main row, and both of Revelation 9's `PID_C_ツクヨミ` placements get the same filler | the Revelation 8 Hayato break |
| R4 | same female flag in each spot | bodies, pronouns, S ranks |
| R5 | slice 1's route guards run again on the **shuffled** rows: a staff user, a door opener (the lock skill moves with personal skills) and a vein user per route | these were per-person facts; after a swap they belong to the filler |
| R6 | **new: a flier per route** on Birthright before Birthright 10 and on Revelation before Revelation 11 (the ninja village door; same map). This also closes a gap slice 1 has today (RECRUIT_PITFALLS.md section 2 #5) | the door cannot be reached without one; map tiles are never moved |
| R7 | no edit to any `Scripts/` file, map tile or castle_join record; edits only to the allowed cells (section 6) | Conquest 16, and Way A's whole promise |
| R8 | Recruitment off: the mod folder and the in-game patch are byte-identical to the same seed without the recruit code (fixture seeds r50all, r50def, r50shops) | old seeds stay old seeds |
| R9 | full identity only: the filler's face package exists, and for every scene that asks the spot's person for an expression, B has it or the fallback chosen in plan round 5 applies | the missing-expression case (RECRUIT_PRESENTATION.md section 4) |

## 5. What full identity changes, and what stays wrong

Full identity remaps labels **once, as one permutation** (A's labels show B, B's show C, with no chains). This is the
cheapest correct way from RECRUIT_PRESENTATION.md section 3:

| Step | Edit | Follows the filler |
|---|---|---|
| P1 | FaceData records `FSID_ST_<A>` / `FSID_BU_<A>` take B's package, hair, colour, expressions, layout and name-plate `MPID_` | portraits on the status screen and in every conversation, name plates, chapter copies of A |
| P2 | Person `mpid_name` / `mpid_help` of A's spot, in the main row, the route-variant rows and the 285 chapter copies | menus, unit list, map window, help |
| P3 | Person `aid` of A's spot (or the `AID_` rows of asset ROM3/ROM4, decided by the load-moment read) | 3D battle model and own outfits, battle voice [medium] |
| P4 | names in dialogue: whole-word replacement through one hook where the game fetches a message (the FE8 port's way); the voiced scene lines of swapped speakers are silenced, not remapped (clip numbers do not match between people) | dialogue says B |
| P5 | map head: nothing if `unit/Head/%s` takes the `AID_`, else the same label remap | map sprite |

What stays wrong even with full identity, and the page help says so: the 55 pre-rendered movies; B speaks A's lines
and has A's supports, castle lines and story role (the same as in the FE8 port); My Room (Live2D) stays A's until its
lookup is read; the swapped person's voiced scene lines are silent.

## 6. How it plugs in

**Python (host, no build).** A new module `tools/randomizer/recruit.py`, written like the round 55 modules:

```
plan_recruit(tables, rng, opts) -> (edits, spoiler_lines)
run_guards(tables, edits, opts) -> {name: {"ok", "detail"}}
shuffled_facts(facts, edits) -> Facts      # a copy with each spot's Person (and route-variant) rows replaced
```

- `rng` is the run seed. The module derives its **own sub-seed** from `sha256(TOOL, seed, "recruit")`, with one stream
  per purpose and per spot (the children.py pattern), so no other track's draws move.
- In `tracks.make_all`, recruit runs **first**, before `R.make_plan`. Slice 1 and every track then plan on
  `shuffled_facts`. With Recruitment off, `make_all` never imports recruit.py and passes the untouched facts, which
  is R8.
- The recruit options live in their own `ropts` dict, not in `topts`, and are left out of `mod.json` and the spoiler
  when they are at their defaults. Adding keys to `topts` would otherwise change `mod.json` for old seeds that have a
  track on.
- `rando.py make` gets the four flags of section 2. `tools/play/rando.py` `OPTIONS` gets the four rows, so PLAY
  RANDOMIZED's menu and the in-game page (`ingame.schema()` reads the same list) both show them **without an engine
  build**. The rows are added in the round where the in-game apply works (plan round 3), never earlier: no
  half-built row. The "full" choice is offered only after plan round 6 (until then the row has one choice, like
  "Children (not built)").
- Spoiler: a "Character shuffle" section listing spot -> filler per group, with the credit line to the public tools
  for the list of breaks.

**Cells it edits.**

| File | Cells | Laid today by the in-game core? |
|---|---|---|
| GameData Person rows (main) | job and job line, growths, bases, level-matched stats, weapon ranks, personal skills, identity flags (beast); for full also `aid`, `mpid_name`, `mpid_help` (`fid` stays, so the face lookup still finds the spot; P1 changes what that face shows) | **yes** (GameData at New Game, round 51) |
| `GameData/Dispos/**` placements of the spot (team 0) | items (slice 1's weapon swap on the shuffled facts); `jid` of the 32 route-variant placements (all have an empty `jid` today, meaning "the row's own class") | **yes** (placement hook; `jid` is a label pointer the patcher already lays) |
| `GameData/Person/{A,B,C}_HANDOVER` route-variant rows | the same cells as the main row, at the row's own level | **no**: the core accepts only GameData and `GameData/Dispos/**`. Extending the per-file hook to `GameData/Person/**` is a small change in `fates_rando.rs`, but it is an **engine build** |
| chapter Person files (285 copies of main people) | full only: `aid`, `mpid_name`, `mpid_help` | no: the same hook extension |
| `face/FaceData.bin.lz`, `asset/ROM3/ROM4` | full only: P1 and P3 | no: needs the load-moment read, then either the same hook or a resident patch at New Game, which is an **engine build** |
| message text | full only: P4 | no: a new message-fetch hook, which is an **engine build** |

**Question to settle first, which may affect slice 1 today.** All 32 route-variant placements have an empty `jid`,
so the unit takes its class from the HANDOVER row. Slice 1 changes the main row's class and swaps items only on
placements of the **main** id. If `Unit::Handover` keeps the HANDOVER row as the unit's person, then today's
randomized Revelation joins (Silas, Hinoka, Hayato, the Conquest retainers and others) and the Birthright and
Conquest route-variant joins arrive **in their original class with their original weapons**. If it switches to the
main row (`replace_index`), they are fine. This was not tested. Our robot runs only reached Chapter 2. Plan round 2
reads `Unit::Handover` on the host first. If the main row wins, keep the face needs **no** engine build (GameData plus
the Dispos `jid` cells). If the HANDOVER row wins, plan round 3 includes the hook extension, which also fixes this
slice 1 gap.

**Engine builds: owner OK needed at that round.** F-046 says "any part that needs the game core gets its own engine
round", and the F-046 addendum asked for full identity now. The builds are: the per-file hook extended to
`GameData/Person/**` (only if the read says so; plan round 3), the face and asset tables (plan round 4), and the
message hook (plan round 6). Each one backs up the exe first and leaves Randomizer off byte-identical to the
original game, as in F-044. The OK is asked for when that round starts, not assumed here.

## 7. Test plan

**Unit tests** (`tests/test_rando_recruit.py`, host, no game):

- R1-R9 on the real tables, for 50 seeds in each of route/any × keep/full × own/slot × autolevel/slot.
- Same seed gives the same plan and the same files. Recruitment off gives files byte-identical to the fixture seeds.
- The sub-seed is independent: turning recruit on does not change the items, enemies, music or nuzlocke draws for
  spots that did not move.
- Autolevel: a filler levelled up then down returns to its own bases (within rounding), and route-variant levels come
  out per row.
- Made-up small tables: a pool of one stays put, an odd sex count leaves exactly the unmatched person in place, and a
  route without a flier fails R6.
- Schema: the new rows equal PLAY RANDOMIZED's lists, and the page answer gives the right flags (extends
  test_rando_ingame).

**Robot** (headless, F-042 rules: STOP_ROUND checked before every start, data folder and APPDATA/LOCALAPPDATA under
build/, self-exiting, one lane; recorded routes and saves only, no new play):

| Check | Route and save | Reached on recorded presses? |
|---|---|---|
| Chapter 2 unit list: the fillers present, no phantom unit | bt-ch2 (bt-ch1-clear) | yes |
| Revelation 9: Rinkah's spot joins at the start | rv-ch9 (rv-ch8-clear) | yes |
| Revelation 13: Kaden and Keaton's spots join, plus a turn 1 picture of the rubble | rv-ch13 (rv-ch12-clear) | yes |
| Conquest 9: the talk on turn 3, before the wall (once Nyx leaves the hold list: her spot's filler) | cq-ch9 (cq-ch8-clear); the chain was moved to C: in the 2026-11-17 archive and must be located first | probably, if turns 1-2 replay the same |
| full: a scene with a swapped speaker (face, name plate), a battle (model, voice key in the sound log), a scene asking for a missing expression | the earliest recorded scene where a pooled person speaks | yes, at chapter starts |
| Revelation 8 Hayato, Conquest 16 spare prompt, the two ninja doors | rv-ch8, cq-ch16, bt-ch10, rv-ch11 | **no**: these need new play or an F-030-style cheat poke, and the **owner's yes for that use** |
| Off = original: memory and saves equal to an unrandomized run | any of the above | yes |

Per F-046, full identity does not count as done until those four chapters pass "wherever recordings reach", and the
report names the ones they do not reach.

## 8. Round plan (counted rounds; each is one sitting with its own time box, F-027)

Status (round 59 check, 2026-11-21): the shuffle ("keep the face") is on the in-game page in play/game (patches 0016-0021). Strict robot pairs are valid on all four paths for both route and any (Birthright A004, Conquest B007, Revelation C007, Seal R002). A reviewer saw two of them: Rinkah at A004 and Felicia at Seal R002. Recolour changes the battle hair only. The HANDOVER chapters (Revelation 9/13, Conquest 9) are still not robot-checked. docs/REPORT_2027-01-02.md.

Status (round 59, engine round E1 = plan round 3, 2026-11-20): patch 0016 lets the core lay `GameData/Person/**`
(the route-variant HANDOVER rows and the chapter person files) in the game's own read, so "keep the face" is live on
the in-game page (rows Who joins where, class, level and stats; the look row stays grey at "the spot's person" until
E3/E4), Fates and the Seal edition. Smoke (headless, own boot-server, recorded Chapter 2 route): with seed e1smoke2
(recruit any) Felicia's spot joined as a Master Ninja with Kagero's stats (HP 27; off: Maid, HP 19); all 430
GameData cells, the 2 placement cells and the 3 chapter-person cells read back right; build/r59/e1/jobs/. 800
unpicked seeds (200 per route/any x autolevel/slot) all made, none refused (build/r59/e1/seeds_*.json). Not yet
robot-checked: Revelation 9 / 13, Conquest 9 (round 59 check step).

Status (round 58, wiring round W2, 2026-11-20): the shuffle is wired into `rando.py make` (`--recruit`,
`--recruit-look`, `--recruit-class`, `--recruit-stats`, kept as their own `ropts` dict) and PLAY RANDOMIZED, whose mod
folder lays every table cell including the route-variant rows (as `tables/PersonChapter.csv`). The four page rows stay
grey until plan round 3 (engine round E1). The slice-1 route-variant class fix is in (owner OK, F-046). The flier rule
for slice 1 itself is not switched on yet. docs/RANDOMIZER.md section 11.

| Plan round | Delivers | Engine build? | Robot |
|---|---|---|---|
| 1 (this one) | research (four pages), this design, the Personal skills label fix | no | no |
| 2 | host reads: `Unit::Handover` (which row), the FaceData and AssetTable load moment, the `unit/Head/%s` source, the message-fetch function. `recruit.py` (plan, guards, both looks as data), `rules.json` keys, `rando.py` flags, unit tests, spoiler. CLI only; nothing on the page | no | no |
| 3 | keep the face in the game: the cells laid by the core, the four page rows (full not offered), the flier guard switched on for slice 1 too. If round 2 says so: the hook extension to `GameData/Person/**` | maybe (owner OK) | Chapter 2, Revelation 9, Revelation 13, Conquest 9 where it fits; off = original |
| 4 | full identity P1-P3 (+P5): FaceData, asset or `aid`, names in menus, chapter copies | yes (owner OK) | swapped speaker scene, battle model |
| 5 | missing-expression behaviour, fallback, map sprite, fixes from round 4 | no (unless the fallback needs files) | the expression scene |
| 6 | full identity P4: the message hook (names in dialogue) and silenced voice lines; "full" offered on the page | yes (owner OK) | a scene line names the filler; voice silent |
| 7 | full identity robot pass on the guarded chapters recordings reach; the report says which do not | no | Revelation 13, Conquest 9, Chapter 2, Revelation 9 |
| 8 | (with the owner's yes for cheat pokes) Revelation 8, Conquest 16, the ninja doors; free Nyx and Shura if they pass | no | cheat-track runs |
| 9 | the owner's review: fixes, help text, docs/RANDOMIZER.md and PLAY RANDOMIZED notes | no | reruns only |

Slips to expect, said up front: the missing-expression case (round 5 may need the file way of the portrait look,
plus one round), and the Conquest 9 presses not fitting (then it moves to the cheat-poke round). Total: 9 counted
rounds, up to 11 with those two slips. Children, promotions, music and Nuzlocke are wired into the page in their own
F-046 round and are not counted here.

## 9. Credit

The list of known breaks (Conquest 9, Conquest 16, Revelation 8, Revelation 13, ninja maps needing a flier, fresh game
only, per-route spots) comes from the public Fates randomizers: Ignis and Paragon (thane98), lashoun's
upgraded-fefates-randomizer, and the 2016 GBAtemp Fates randomizer. Facts only; no code was read into this port.
The spot-keeps-its-id method and the option set follow our own Sacred Stones port's Recruitment.
