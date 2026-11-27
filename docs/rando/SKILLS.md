# Randomizer track: skills (round 49, F-043 #1)

**For the owner.** This track gives the 49 playable people new skills without adding anything new to the game.
Two switches. **Personal skills** (each person's own skill, like Felicia's Devoted Partner): keep, shuffle them
among the people, or draw each person a random personal skill (no two people get the same one). **Skill
slots** (the up to three skills a person joins with, like Gunter's Elbow Room and Shelter): keep, follow the new
class (a skill the old class taught becomes the skill the new class teaches at the same level), or random
skills that normal classes teach. A slot that is empty stays empty, and a person keeps the same number of
skills. Corrin and Azura are never changed. Status 2026-11-20: module, tests and one robot check done; nothing
counts as done until the owner says ok (F-037). Our own code; the public Fates randomizers (GPL) were read for
facts only.

## 1. How it is called

`tools/randomizer/skills.py` (this track's only module):

```
plan_skills(tables, rng, opts) -> (edits, spoiler_lines)
    tables  randolib.Facts, with the Skill rows in tables.skills (or opts["skill_rows"]; load_skill_rows())
    rng     the run seed text (or a random.Random); the track makes its own sub-seed from it + "skills"
    opts    {"personal": keep|shuffle|random, "slots": keep|class|random, "base_plan": slice-1 plan}
    edits   [{"table": "Person", "index", "label", "cell", "old", "new"}]
run_guards(tables, edits) -> {guard: {"ok", "detail"}}
person_csv_with_edits(facts, slice1_person_csv, edits)   adds the skill columns to slice 1's Person.csv
```

Default opts are keep / keep: no edits, so a default run is byte-identical to slice 1. Suggested page values:
personal = shuffle, slots = class. `rando.py`, `randolib.py`, `gamedata.py`, `rules.json` and the page are not
edited (the integrate step wires the switches; until then `randolib.render` writes only slice 1's columns, and
`person_csv_with_edits` shows how the skill columns go in).

`python tools/randomizer/skills.py make --seed S [--personal M] [--slots M] --out DIR` writes slice 1 (default
switches) + this track as one mod folder (below `build/` only), with `skills.json` (the edits and guards) and
the skills lines at the end of `spoiler.txt`. `... robot` is the robot check below.

Randomness: the track key is SHA-256 of (tool version, seed, "skills"); each use is its own stream (personal
shuffle, personal random, and one per person for the slots), so the other tracks never move these results.

## 2. Cells written

Person rows of the 49 people only (the slice-1 scope: player army, no children, bond, capture-only,
downloadable or enemy-only rows):

| Cell | What | Rule |
|---|---|---|
| `skill.1` .. `skill.5` | the skills the person joins with equipped (Unit::CreateImpl gives each one whose `skill_mask` bit is set; all 49 have 0x7FFF) | only a slot that already holds a skill; never `skill_mask` |
| `personal_skill.normal/.hard/.lunatic` | the personal skill per difficulty | all three get the same new skill (they are equal today for all 49) |

**Round 61: the route-variant rows (GameData/Person/{A,B,C}_HANDOVER, laid as tables/PersonChapter.csv).** A
route-variant join (Revelation's Elise, Arthur, Effie in chapter 14, Hayato at the end of chapter 9, Sakura at the
end of chapter 8, and the others in the HANDOVER files) is created from its HANDOVER row and copies that row's slot
skills, so those rows follow their main person: every skill the two rows share becomes what the main row's skill
became; a skill only the route row holds follows the main rows' rule (class mode: the class the join gets, slice 1's
make_plan step 5 rule; random mode: a fresh draw from the same pool), with the same guards (legal ids, class-taught,
filled slots unchanged in number and place, the lock skill kept, no repeats) plus "route-variant rows follow their
main row". The personal skill cells of a route row follow the main row when both held the same skill. Off/keep =
no edits (byte-identical). Before round 61 these rows were left out (the same gap items.py had until round 60).

Map placements (DisposUnit `skill_1..5`) are not touched: none of the 1497 placements of these 49 people holds a
skill except one on the test map Z000 (Elise, Locktouch).

## 3. Which skills may go where (read from the tables)

| Family | How it is found | Count | May go into |
|---|---|---|---|
| Personal | Skill.flags_2 bit 3 (the 69 rows with no sort order) | 69 | personal cells only |
| Enemy-only | flags_2 bit 0 without bit 3 (Unit::CreateImpl skips them for a player unit): Dragonskin, Divine Shield, Hit/Avo +10/+20, Resist/Immune Status, Void Curse, Self-Destruct, Staff Savant, Immobilize, Inevitable End, Brynhildr | 12 | nowhere |
| DLC-only | kind 4, no dictionary price, not personal: the eight downloadable classes' skills (Dread Fighter, Dark Falcon, Ballistician, Witch, Lodestar, Vanguard, Great Lord, Grandmaster) and the other DLC rewards (Galeforce, the stance/shield skills, the "-taker" skills, Paragon...) | 41 | nowhere |
| Song | kind 1: Inspiring Song (changes only the singer's Sing) | 1 | nowhere |
| Class-taught | Job.skill.1-4 of every class slice 1 may hand out (not excluded, not enemy-only) | 94 | slots (random mode draws from these, minus Locktouch: 93) |
| Not in any pool | Corrin's lines (Nobility, Dragon Fang, Draconic Hex, Nohrian Trust, Dragon Ward, Hoshidan Unity), the Songstress's (Luck +4, Voice of Peace, Foreign Princess), the Villager's (Aptitude, Underdog), Locktouch | 13 | stay where they are |

The personal pool for random mode is the personal family as held by player-army people who are not
downloadable or enemy-only (children's skills allowed), minus the kept ones below: 62 skills for 41 people.

## 4. Guards (each has a test in tests/test_rando_skills.py)

| Guard | How | Test |
|---|---|---|
| Same seed and opts, same edits; other tracks do not disturb | track key + one stream per use | `test_same_seed_same_output_and_seed_matters`, `test_other_tracks_do_not_disturb`, real data `test_every_mode_many_seeds` |
| Only legal skill ids, of the right family | slot values from the class-taught pool (or the new class line); personal values from the personal pool | `test_only_legal_ids_and_families`, guard `each cell keeps its family` |
| Slot count and place unchanged | only filled slots are rewritten | `test_slot_counts_unchanged`, guard `filled slots unchanged in number and place` |
| No skill twice in a person's slots; no personal skill for two people | draws without repeats | guards |
| Corrin and the singer untouched | rows with the avatar flag or a class with the sing command are skipped | `test_kept_rows_lock_and_story_skills` |
| Door openers kept | Locktouch is never taken from a slot and never drawn at random (slice 1's door-opener guard counts it); a person whose new class line teaches it in class mode may gain it | `test_kept_rows_lock_and_story_skills`, guard |
| Story / command / asset personal skills kept | see the list below | same |
| Class skills follow the new class | the old slot skill's place in the old class line (base class lv 1 / 10, promoted lv 5 / 15; the base class is looked up in `job_low` and then in every class that promotes into the person's class, because Gunter's skills do not match his `job_low`) becomes the new line's skill at that place; if that place is empty (a base class has no promoted half) or it would repeat, another skill of the new line, else one from the class-taught pool, and the spoiler says so | `test_class_skills_follow_new_class`, `test_class_mode_no_base_plan_is_no_slot_change` |
| Bad edits are caught | made-up wrong edits fail four guards | `test_guard_catches_bad_edits` |
| The mods tool accepts the folder | real data | `test_mods_tool_accepts_the_folder` |

Results: `python -m unittest tests.test_rando_skills`: 15 tests OK (12 seeds x 8 modes on the real tables, every
guard PASS).

**Kept with their owner (and why).** Found by searching every RomFS file (LZ unpacked) and the code for SEID_
labels: event scripts name only one skill, Self-Destruct (an enemy's, Scripts/B/B028.cmb); no scene tests a
playable person's skill by name.

| Skill | Owner | Why |
|---|---|---|
| Supportive | Corrin | the avatar's row is never edited |
| Healing Descant | Azura | the singer's row is never edited |
| Capture | Orochi | gives the Capture command |
| Kidnap | Niles | gives the Capture command |
| Fiery Blood, Icy Blood, Wind Disciple | Rinkah, Flora, Fuga | the model/asset table asset/ROM5.lz names these three as conditions next to model entries; what it does there was not traced, so they are not moved |

**Could not be checked:** whether any scene checks a skill indirectly (through a flag or a script command that
does not name the skill); what the ROM5 asset entries do; the learned-skill pool (a unit's unequipped learned
skills): this track writes only the equipped slots, and whether the pool also gets them was not read; Hard and
Lunatic were not played (the robot used the Normal save; all three personal cells are written the same).

## 5. Robot check (one headless job, 2026-11-20)

In the robot's own test game only. Data folders below `build/rando49/skills/` (not tracked); APPDATA and
LOCALAPPDATA of each run pointed into its own server folder by the harness. Not touched: %APPDATA%, the owner's
saves, Zakuro settings, cheats, `mods/`, build/oka, routes.json, markers.json.

1. `skills.py make --seed r49skills --personal shuffle --slots class --out build/rando49/skills/mods`:
   slice 1 (default switches) + this track only; 166 skill cells (39 people's personal skill, 49 slot cells of
   33 people), every slice-1 and skills guard PASS.
2. `mods.py --mods-dir build/rando49/skills/mods --stage-dir build/rando49/skills/stage --zakuro-dir
   build/rando49/skills/zak install` (build OK, 2597 cells, 101 files; log `install.log`); the installed
   folder was copied to `zak_on`, then `uninstall` + `disable` on `zak` (0 files left; `uninstall.log`).
3. Runs (each `boot-server` headless, below normal, exits by itself): start save `bt-ch1-clear`, recorded route
   `bt-ch2` presses up to frame 5117 (the Chapter 2 map, before the first move), reads at 4800 / 5117 / 5300.
   Memory was only read. Results `build/rando49/skills/robot/r49sk.json` (off) and `r49sk-mod.json` (on).

| Check | Result |
|---|---|
| All 49 Person rows in memory: class, class line, five slots, three personal skills = the plan | **PASS, 0 mismatches** at every read |
| Gunter on the map (Great Knight -> Paladin) | equipped Shelter + Elbow Room (his Cavalier skills: Paladin's base line is the same, so unchanged); personal **Optimistic** (was Forceful Partner) |
| Felicia on the map (Maid -> Berserker) | equipped **HP +5 + Gamble** (was Resistance +2 + Demoiselle: her Troubadour skills became the Fighter's at the same levels); personal **Vow of Friendship** (was Devoted Partner) |
| Corrin on the map | Nobility, Supportive: unchanged, as planned |
| Each unit's equipped skills (Unit +0xFE) = its row's slots | 0 mismatches (the game keeps them sorted by skill number: Gunter's unit lists Shelter before Elbow Room in both runs) |
| **Off = original** | after uninstall: 0 mod files in the run's data folder, the 49 rows equal the original tables (0 mismatches), and the whole-memory hash at frame 5300 is `74eb98e65d597c4e...`, the same as round 47's no-mod run (rc-none ch2) |

Said plainly: the first robot start ran only the "off" run, because of a bug in my own driver (it skipped the
first run spec); after the fix the "on" run was started once more (the one allowed retry). Gunter and Felicia
join in Chapter 2, so their units were made from the modded rows; Corrin was made in the original game (the
save), and his row is not edited anyway. No battle was played, so no skill was seen firing; only that the right
skills are on the right people.
