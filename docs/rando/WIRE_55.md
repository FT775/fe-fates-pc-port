# Wiring the round-55 tracks (children, promotions, music, Nuzlocke)

Round 55, F-046, 2026-11-20. This is the plan for the **integrate round**, which runs after rounds 53 and 54. Nothing here is wired
yet. Round 55 wrote only `tools/randomizer/{children,promotions,music,nuzlocke}.py`, their tests and
`docs/rando/{CHILDREN,PROMOTIONS,MUSIC,NUZLOCKE}.md`. Nothing counts as done until the owner says ok (F-037).

Facts below were read from the four modules, `tools/randomizer/tracks.py`, `tools/randomizer/rando.py`,
`tools/randomizer/ingame.py`, `tools/play/rando.py`, `config/randomizer/rules.json`, `tools/check_all.py` and
`engine/zakuro/crates/zakuro/src/rando_page.rs` (read only).

## 0. Rules that hold for every track

- **Off means byte-identical.** Every new option defaults to "changes nothing". `tracks.active()` must stay false
  when all new options are at their defaults, so `make_all` still returns `R.render(facts, plan)` unchanged.
  Test: seed `r50def` and seed `r50all` (the round-50 samples, with the new options at default) give the same files
  byte for byte as before the wiring.
- **Sub-seeds.** Each track derives its own key from the run seed **text**:
  `sha256(TOOL \x1f "seed:"+seed \x1f TRACK)`. The key functions are `children.sub_seed`, `promotions.track_key` and
  `music.track_key`. Nuzlocke draws nothing. Always pass the seed text (`seed`), never a shared `random.Random`.
  That way PLAY RANDOMIZED and the in-game page give the same result, and turning one track on never moves another.
  The TOOL strings are `rando-children-v1`, `rando-promotions-v1`, `rando-music-v1` and `rando-nuzlocke-v1`.
  Changing one changes every seed of that track; bump it only on purpose.
- **Guards with the same opts.** Call each `run_guards(tables, edits, opts)` with **exactly** the opts the plan
  used. The round-55 review found that children's `legal_class` fails falsely when `trees=any` is left out.
  Put every track's guards in `plan["guards"]` under a `<track>.` prefix, as round 49 does. A failed guard means
  exit 2 and no mod and no patch, as today.
- **Spoiler.** Each track's lines go into its own `_section(...)` in `spoiler.txt`, and the option goes into
  `mod.json` `randomizer.topts` / `randomizer.tracks`, as for the round-49 tracks.

## 1. Option names, defaults and flags

Add these to `tracks.DEFAULT_TOPTS` / `CHOICES` / `BOOLS`. Add the same names to `tools/play/rando.py OPTIONS` (the label,
the kind and the default) and to `SUGGESTED` (the "Everything on" value). Add a matching flag to
`rando.py make` (argparse, `default=D[...]`). `ingame.schema()` then picks them up by itself, because it reads
`PR.OPTIONS`.

| topts key | flag | choices | default | "Everything on" | page label (suggested) | track opts it maps to |
|---|---|---|---|---|---|---|
| `children` | `--children` (exists) | on/off | off | on | Children | children `{"children": True, ...}` |
| `promotions` | `--promotions` | off / on | off | on | Random promotions (Master Seal) | promotions `promotions` |
| `promotion_sides` | `--promotion-sides` | any / own | any | any | `  Promotion sides (own = own side)` | promotions `sides` |
| `reclass` | `--reclass` | keep / random | keep | random | Heart Seal classes | promotions `reclass` |
| `music` | `--music` | off / maps / maps+battles | off | maps+battles | Music | music `music` |
| `nuzlocke` | `--nuzlocke` | on/off | off | off (never in "Everything on") | Nuzlocke (Classic only) | nuzlocke `nuzlocke` |
| `recruits` | `--recruits` | all / first | all | all | `  Recruits (first = only the first per chapter)` | nuzlocke `recruits` |

Promotions `choices` is **not** a row and not a flag. It stays `"2"`. `"3"` is refused (two promotion cells per Job
row, see section 7).

New mapping helpers in `tracks.py`, in the style of `growth_opts()`:

```
children_opts(sw, o)  = {"children": sw["children"], "classes": sw["classes"], "growths": sw["growths"],
                         "join_stats": sw["join_stats"], "trees": sw["trees"],
                         + growth_mode, growth_variance, growth_min, growth_max, adjust_hp,
                           bases_mode, base_variance, scale_to_level, personal_skills,
                           skill_slots (children accepts keep|class only: map "random" -> "class" and
                           say so in the spoiler, or refuse children+random until the track learns it)}
promotions_opts(o)    = {"promotions": o["promotions"], "choices": "2", "reclass": o["reclass"],
                         "sides": o["promotion_sides"], "base_plan": plan}
music_opts(o)         = {"music": o["music"]}
nuzlocke_opts(o)      = {"nuzlocke": o["nuzlocke"], "recruits": o["recruits"]}
active(): + "children": sw["children"], "promotions": o["promotions"] != "off" or o["reclass"] != "keep",
            "music": o["music"] != "off", "nuzlocke": o["nuzlocke"]
```

**Children and slice 1.** `randolib.make_plan` raises `children: not built in slice 1`. Keep slice 1 seeing
`children=False`: strip the switch before `R.make_plan` and route it to `plan_children` only. In
`tools/play/rando.py`, remove the `for flag in ("--children",)` override that always sends `off`. In
`ingame.schema()`, drop `"fixed": True` and the "(not built)" label, so the row becomes a normal on/off row.
`ingame.make_args` already passes it on.

## 2. Order inside `tracks.make_all`

The order matters only where tracks share cells or facts. Each track still has its own sub-seed, so the order
never moves a draw.

1. slice 1 plan (`R.make_plan`, children stripped)
2. growth track (unchanged)
3. **promotions, Job part**: `plan_promotions(facts, seed, promotions_opts)`. Then
   `promo_after = promotions._promotions_after(PromoFacts(facts), edits)`.
4. skills track. With promotions on, `skills.SkillFacts.line()/old_place()` must use `promo_after` for the
   "classes that promote into X" lookup (PROMOTIONS.md section 4). Add an optional `promotions=` argument to
   `SkillFacts`. Without it, the behaviour is today's.
5. **children**: `plan_children(facts, seed, children_opts | {"base_plan": plan, "skill_rows": skill_rows,
   "taken_personal": <adults' personal skills after step 4>})`.
6. items, then enemies (unchanged)
7. **music**: `plan_music(music_tables, seed, music_opts)`. `MusicTables` comes from `music.load_tables()`, read
   only. Load it only when music is on, so default runs do not read map/config.
8. **nuzlocke**: `plan_nuzlocke(...)` returns `([], lines)`. It makes no table edits ever. With Nuzlocke on, also
   write `nuzlocke.json` = `make_rules(facts, nuzlocke_opts)` into the mod folder, next to `plan.json`. The in-game
   core copies it into the run folder (section 7).

### Cross-track job_low gap (found while writing this; must be fixed in the integrate round)

The promotions track redraws `job_low` for the people in its scope, and the children are outside that scope. A
host check with promotions on (seeds w55a/w55b/w55c, children off) found that **14, 16 and 15 of the 22 child rows**
keep a `job_low` that is not one of their class's new promotions. Example (seed w55a): Dwyer is a Troubadour with job_low Butler, but the Troubadour's new promotions are
Adventurer and Great Master. The children
track's own guard `promotion_line_legal` reads the *original* Job rows, so it does not see this either.
The wiring:

- the promotions Person pass (job_low + Heart Seal) also covers the child rows (extend its scope; the Heart Seal
  part may keep children out, because their reclass comes from the parents at join);
- with children on, `plan_children` gets `promo_after` (a new opt `job_promotions`), so the child's new class gets
  a job_low drawn from the new promotions, and the children track writes that cell. The promotions pass then skips
  the child rows, so no cell is written twice;
- a new **cross guard** in `tracks.py`: `job_low_fits_final_promotions`. For every Person row of the player's army,
  children included, a non-empty `job_low` is one of the final promotions of the final `job`. Run it on the final
  edits of all tracks.

### Writing the files

- children: `children.files_with_edits(facts, files, c_edits)`, after skills and before items. It refuses a row that
  another track already wrote. The children's DisposUnit item cells and the items track's cells must not meet: the
  items track starts from slice 1's values for **team 0 placements in scope**, and the child placements are outside
  that scope. Keep the refusal; do not merge.
- promotions: `promotions.files_with_edits(facts, files, p_edits)` writes `tables/Job.csv` (new) and merges the Person
  cells (`job_low`, `reclass.1/2`) into `tables/Person.csv`. Call `promotions.apply_edits(plan, p_edits, opts)` so
  `plan["tracks"]["promotions"]` is recorded.
- music: `music.edits_to_files(mt, m_edits)` writes `romfs/map/config/<CID>.bin` (whole files, rebuilt from the
  game's own bytes) and `tables/PersonChapter.csv`. No other track writes PersonChapter today. If one ever does,
  merge by `(file, index)` and refuse a cell that two tracks write.
- nuzlocke: `nuzlocke.json` (rules) only.

## 3. The in-game page (`ingame.py`) and what the core can lay

The page is **schema-driven**: `rando_page.rs` builds its rows from `rando.py schema` (the kinds onoff, choice and
number, and `fixed`). New rows therefore need **no engine build**. They appear as soon as `tools/play/rando.py
OPTIONS` has them.

The in-memory patch (`ingame.make_patch`, core `fates_rando.rs`) knows only two kinds of file: `gamedata`
(`GameData/GameData.bin.lz`) and `dispos` (`GameData/Dispos/**`). It refuses everything else.

| Track | Files it changes | In-game page now? | PLAY RANDOMIZED (mod folder) now? |
|---|---|---|---|
| children | Person (GameData), DisposUnit (Dispos) | **yes** | yes |
| promotions | Job and Person (GameData) | **yes** | yes |
| music | `romfs/map/config/*.bin` (whole files) + `GameData/Person/**` (PersonChapter) | **no**: `make_patch` refuses these files | yes |
| nuzlocke | none (a rules file plus runtime hooks) | **no**: needs core hooks C1-C6 | **no**: needs the same core hooks |

So in the integrate round, on the in-game page:

- `music` row: `"fixed": True`, default off, label "Music (PLAY RANDOMIZED only for now)". A `make --patch-out` with
  music on must refuse cleanly with that reason, so a half-made patch can never happen.
- `nuzlocke` and `recruits` rows: `"fixed": True`, off, label "Nuzlocke (needs the next engine round)". The same
  applies on PLAY RANDOMIZED: grey, or refused with that reason.
- "This run" (Esc): no change until the engine round.

## 4. `config/randomizer/rules.json`

The minimum change: under `tracks.modules`, add `"children": "tools/randomizer/children.py"`,
`"promotions": "tools/randomizer/promotions.py"`, `"music": "tools/randomizer/music.py"` and
`"nuzlocke": "tools/randomizer/nuzlocke.py"`. Update `tracks.about` to round 55 / F-046. `defaults_in` stays
`tracks.py DEFAULT_TOPTS`.

Optional (IDs only, no game values). These are constants the modules hold today. Move them only if the modules
read them back, and add a test that module and rules agree:

```
"children":   {"inherit_banned_job_flag": "SPID_継承禁止", "support_inherit_banned_job_flag": "SPID_支援継承禁止"},
"promotions": {"extra_source_prefixes": ["JID_村人"], "attempts": 64},
"music":      {"map_dir": "map/config", "map_prefix": "STRM_MAP_", "battle_prefix": "STRM_BOSS_",
               "kept_prefixes": ["STRM_MAPEX_"], "never": ["STRM_EVT_", "STRM_SYS_", "STRM_VO_", "jingles/fanfares"]},
"nuzlocke":   {"never_sortie_bit": 2048, "classic_only": true}
```

## 5. `tools/check_all.py`

Two rows change and one row is new, all in the same style as the existing rows (`require` `^Ran [1-9]\d* tests? in ` /
`^OK\b`, `reject` Traceback / FAILED, `note_rx` the Ran / OK (skipped) lines):

| Row | Command | Cost / timeout | Notes |
|---|---|---|---|
| **new** `rando-more-tracks-tests` | `{py} -m unittest tests.test_rando_children tests.test_rando_promotions tests.test_rando_music tests.test_rando_nuzlocke` | medium / 1800 | 17 + 19 + 21 + 21 = 78 tests today. Real-data tests skip without the extracted tables |
| `rando-tracks-tests` (extend) | add to `tests.test_rando_integrate`: defaults byte-identical with the new options present; everything on incl. children+promotions+music passes every guard + the cross guard; parts independent (music on/off does not move any other cell; promotions on/off does not move the children's classes) | as today | |
| `rando-ingame-tests` (extend) | `tests.test_rando_ingame`: schema has the new rows with the defaults above; music/nuzlocke rows `fixed`; `--patch-out` with children+promotions on equals the mods tool's rebuilt GameData/Dispos cell for cell; `--patch-out` with music on is refused with the reason | as today | |

**Samples** (fixed seeds for those tests and for the robot rounds; host commands, they write under `build/` only):

| Sample | Command | Expected now |
|---|---|---|
| children, 3 sets | `python tools/randomizer/children.py check --seeds 50` / `--trees any --personal-skills random` / `--growth-mode redistribute --bases-mode delta --personal-skills shuffle --skill-slots class` | 0 guard failures (19702 / 23441 / 23706 cells) |
| promotions | `python tools/randomizer/promotions.py` make with seed `w55a`, promotions on, reclass random, sides own | all guards pass, mods tool accepts `tables/Job.csv` |
| music | `python tools/randomizer/music.py make --seed demo55 --music maps+battles` | 252 cells (100 map, 152 boss), 7 guards PASS |
| nuzlocke | `python tools/randomizer/nuzlocke.py rules --recruits first` | 5 never-benched rows (Corrin x2, Azura, Kana x2) |
| integrate | `rando.py make --seed r55all` with everything on (children, promotions on, reclass random, music maps+battles), and `r55def` (all defaults) | r55all: every guard incl. `job_low_fits_final_promotions`; r55def = slice 1 byte for byte |

## 6. Robot checks each track needs (later robot round; headless, own data folder and APPDATA under build/, existing recordings only)

| Track | Check | Can it run? |
|---|---|---|
| children | a seed with children on: one paralogue join read back from memory (class, job_low, items usable) | **blocked**: no recording reaches a child paralogue, and F-025 says do not marry for coverage. Until then the host guards are the check |
| promotions | (1) load seed `w55a` via the in-game patch on an existing route, then read Job +0x64 (the two promotion cells) and Person +0x7C/+0x2E from memory = the patch; (2) the real proof: a Master Seal menu on an existing route or replay that has a seal, with the menu's class list read | (1) yes; (2) only if such a recording exists |
| music | PLAY RANDOMIZED mod folder for seed `demo55`: start a chapter with a changed song and read `map::sound`'s current song name (the name slots at the object `D_006D7F38`+8 points to); one boss fight's song; trace whether hearing a song unlocks it in the Sound Room / jukebox (`Museum.bin`, `castle::JukeBox::Update`) | yes, through the mod-folder path |
| nuzlocke | after the engine round: a battle death written once; Restart / battle save / older save / state load bring the unit back dead; Corrin's death not written; a second join in a chapter benched and not deployable; off = byte-identical memory and saves (as round 51's T4) | no, until C1-C6 exist |
| all | with every new option off: memory and saves byte-identical to today (the round-51 T4 check, re-run) | yes |

## 7. What needs a later engine build (owner OK then; not in the integrate round)

| Need | Why | Size |
|---|---|---|
| **Nuzlocke core hooks C1-C6** (NUZLOCKE.md section 4): page start + rules file, the death hook at `Unit::Transfer` 0x003D8C00 force 4, the join hook, the load hook after `UnitPool::Deserialize` 0x004F5BE8, the My Castle mode lock, "This run" | no table cell serves any rule; everything happens at run time | about 1 engine round + 1 robot round. Before it: settle the 0x800 bench bit on forced deploys, and the `on_join(forced=True)` entry that stays `fielded=False` (round-55 review) |
| **Music in the in-game page**: a third file kind (`mapconfig`) in `fates_rando.rs` + `make_patch`, and `GameData/Person/**` as a placement-like kind. Or one `TSound::SetName(name, type)` swap-table hook, which also covers the castle-invasion boss songs that the code picks | the core lays only GameData and Dispos in memory | about 1 engine round + the music robot check |
| **A third promotion choice** (FE8-style "three choices") | the Job row has two promotion cells. Patch `ClassChangeEnumerator::Enumerate` 0x0021B148 to read the unused Job +0x68 cell | about 1 engine round + 1 robot round, optional |
| **Children: inherited class / parent bonuses** | `GetInheritJobIndex` 0x003C5C30 and `Unit::Inherit2` decide at join, from the parents' live units | engine work, only if the owner wants it. Not planned |

Nothing in the integrate round itself needs an engine or Zakuro build: the page rows come from the schema.
