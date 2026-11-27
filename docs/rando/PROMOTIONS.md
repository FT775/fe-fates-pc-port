# Randomizer track: random promotions (round 55)

**For the owner.** With "Random promotions" on, every normal base class gets two new promoted classes to choose
from when a Master Seal is used: a Knight might become a Wyvern Lord or a Master of Arms, an Archer a Sniper or an
Adventurer. Male and female rows of a class get the same pair. Each new class can always use the weapon the base
class used, at least as high a rank, so nobody ends up with weapons they cannot swing (healers always promote
into a class with staves). Every promoted class stays reachable from at least one base class. A second switch,
"Heart Seal classes", gives each playable person new Heart Seal (reclass) classes. A Heart Seal class is never the
person's own class line (after the class shuffle too), and a person keeps how many they have. The Fates menu
shows **two** promotion choices. A third choice like the FE8 port's cannot be done with table edits alone. It
needs a change to the game code later, in its own engine round, with your OK then (section 5). Status
2026-11-20: module and tests done, not wired into the page yet (the integrate round does that). No robot or game
check yet. Nothing counts as done until you say ok (F-037). This is our own code. The public Fates randomizers
(GPL) were read for facts only. The idea comes from the FE8 port's "Random promotions" (our sister project). No
code was copied.

## 1. How it is called

`tools/randomizer/promotions.py` (this track's only module):

```
plan_promotions(tables, rng, opts) -> (edits, spoiler_lines)
    tables  randolib.Facts (gamedata.load_facts())
    rng     the run seed text (or a random.Random); the track makes its own sub-seed from it + "promotions"
    opts    {"promotions": off|on, "choices": "2", "reclass": keep|random, "sides": any|own,
             "base_plan": slice-1 plan (optional)}
    edits   [{"table": "Job"|"Person", "index", "label", "cell", "old", "new"}]
run_guards(tables, edits, opts) -> {guard: {"ok", "detail"}}
files_with_edits(facts, slice1_files, edits)   tables/Job.csv (new) + the Person cells merged into Person.csv
apply_edits(plan, edits, opts)                 records the track in plan["tracks"]["promotions"]
make_folder(seed, opts, out_top)               slice 1 + this track as one mod folder (below build/ only)
```

Default opts are off / 2 / keep / any. They make **no edits**, so existing seeds stay byte-identical. Suggested
page rows: "Random promotions: Off / On", "Heart Seal classes: Keep / Random", "Promotion sides: Any / Own
side". `choices` is not a page row yet. "3" is refused with the reason from section 5.

`python tools/randomizer/promotions.py make --seed S [--reclass random] [--sides own] --out build/...` writes a
test folder: `promotions.json` (edits + guards), the track's lines at the end of `spoiler.txt`, and
`tables/Job.csv`.

Randomness: the track key is SHA-256 of (tool version, seed, "promotions"). There is one stream each for the
promotion draw (per attempt), the Heart Seal draw (per person) and job_low (per person). Other tracks never move
these results. The opts text is part of each stream, so turning on Heart Seal classes also gives a different
promotion draw for the same seed.

## 2. Facts (from our own table layouts and the symbol map; docs/TABLES.md)

| Fact | Where |
|---|---|
| A class's Master Seal choices are `Job.promotion (1, 2)`, two u16 class numbers at Job+0x64 | `Unit::ClassChange` 003D40C8 and `ClassChangeEnumerator::AddSlideLow` read Job+0x64 (high) |
| The next cell, `Job.base_class (1, 2)` at +0x68, has **no reader** in the game code | evidence scan of the class-change and inherit code (low); it is unused data |
| The class-change menu is built by `ClassChangeEnumerator`: `Enumerate(const Item*)` (by seal), `Add`, `AddSlideLow`, `EnumerateParallel` (Job.parallel_class +0x72), `EnumerateBuddy` / `EnumerateMarrige` (Friendship / Partner Seal) | config/functions.csv names; bodies not read |
| Heart Seal classes per person: `Person.reclass (1, 2)` at +0x7C, Job numbers, 0 = none | data + Paragon reclass_1/2 (fact, medium) |
| `Person.job_low` at +0x2E: for a promoted class, the base class used for reclassing (`Person::GetLowJobIndex`); for a base class the data always holds one of its promotions | TABLES.md (high); every playable row follows this pattern |
| Each class has a male and a female row; `Job.gender_pair` (+0x70) links them (`IsInheritJobIndex` reads it) | data; Monk ↔ Shrine Maiden, Great Master ↔ Priestess, Butler ↔ Maid are pairs too |
| Every normal base class uses exactly one weapon kind | data (Job.max_weapon_exp) |
| Class counts (your tables): 36 promotion sources (17 base class lines × 2 genders + Villager × 2), 54 normal promoted target rows, 34 normal base rows for Heart Seal classes | `PromoFacts`; the real-data test asserts 36 |

Special lines:

| Line | What this track does |
|---|---|
| Corrin's Nohr Prince(ss) → Nohr / Hoshido Noble | never touched (the avatar's own line) |
| Songstress | has no promotion; never touched; never a target |
| Kitsune → Nine-Tails, Wolfskin → Wolfssegner | kept: each has one promotion, there is one promoted beast class per line, and the beast people's stones and transformations depend on it |
| Villager (Mozu) | its two promotions are drawn like the others (lance kept). It is never a target, a Heart Seal class or anyone's job_low |
| The eight downloadable classes, enemy-only classes, dragons, Lancer | never a source or target |

## 3. What is built

**Master Seal choices** (`promotions: on`). Lines are drawn on the male row and copied to the female row
through the gender pairs, when the paired class is legal for her (a line that would end up short is drawn per
row). A target must be all of these:

- a normal promoted player class (not enemy-only, DLC, avatar or singer, not a beast class);
- the same gender row;
- able to use the base class's weapon kind at the same or a higher limit (so the unit's weapon exp and weapons
  stay usable). This also keeps healers in staff classes (the FE8 port's "magic into magic" rule, done here
  through weapons);
- not twice in one menu. Every source keeps its number of filled cells (no dead ends).

The draw goes most-constrained-first, up to 64 tries, so that **every promoted class stays reachable** from a
normal line (not only through the Villager). With `sides: own`, Hoshido base classes promote into Hoshido
classes and Nohr into Nohr. A line with too few classes on its own side draws from both, and the spoiler says
so. On your tables, every seed tried (15 seeds × every option in the tests, 40 × 2 by hand) reached every class
with no fallback.

**job_low follows** (with `promotions: on`). A playable person's `job_low` is redrawn when it no longer fits the
game's pattern under the new promotions. A base class person gets one of the new promotions. A promoted person
gets a normal base class that now promotes into their class, same side first. With `base_plan` given, "old" is
slice 1's value, because slice 1 picks job_low from the original promotions.

**Heart Seal classes** (`reclass: random`). Each playable person (not Corrin, not Azura) gets new classes in the
slots that already hold one. They must be normal base classes of their gender, never their original or new class
line, and never two the same. With `sides: own`, they come from the person's (new) class side when possible. This
also fixes the slice-1 note "a person may be offered their new class again".

**Guards** (`run_guards`, all tested):

- only base classes' promotion cells and playable people's reclass / job_low cells;
- legal targets;
- counts kept (no dead ends);
- no repeats in a menu;
- promoted / beast / avatar / singer / DLC rows untouched;
- every promoted class a playable person starts in (after slice 1) stays reachable;
- job_low matches;
- Heart Seal rules;
- Corrin's and the singer's cells untouched.

**Tests** (`python -m unittest tests.test_rando_promotions`, 19 tests, all pass):

- made-up tables: off = no edits; "3" refused with the reason; same seed gives the same edits; 60 seeds × every
  option pass every guard; no dead ends and every class reachable; special rows untouched; weapon kind kept;
  gender rows mirrored; sides own, plus the fallback; Heart Seal rules; Heart Seal avoids slice 1's new class;
  job_low follows; each guard catches a planted bad edit; CSV merge;
- your own RomFS: 15 seeds × every option with a slice-1 plan pass all guards and keep every class reachable;
  off = no edits; the mods tool accepts the test folder (`tables/Job.csv` included).

## 4. Not done yet / for the integrate round

- Wiring: `rando.py`, `tracks.py`, `ingame.py`, `rules.json`, the page and `check_all` were not edited (file
  ownership this round). The integrate round has to do four things:
  - call `plan_promotions` with `base_plan`;
  - write `tables/Job.csv` and the Person cells (`files_with_edits` shows how; slice 1's Person.csv `job_low`
    column is overwritten for the people listed);
  - give the **skills track** the new promotions: `skills.SkillFacts.line()/old_place()` look up "classes that
    promote into X" in the original Job rows;
  - show the spoiler lines.
- **Children** (the children track): child rows are outside this track's scope. Their `job_low` follows the
  pattern too, and their inherited classes come from the parents' class and Heart Seal classes through
  `gender_pair` / `parallel_class`, which this track never edits. The children track can call
  `PromoFacts` / `_promotions_after` to keep child job_low consistent.
- **Friendship / Partner Seals** offer a partner's classes (EnumerateBuddy / EnumerateMarrige). With Heart Seal
  classes random, what a friend passes on changes with them. That is intended, but no robot has seen it yet.
- **Robot check** (no lanes this round): the next robot round should load a test folder and read the Job rows'
  +0x64 cells and the Person rows' +0x7C / +0x2E cells from memory, as the skills robot reads Person rows. A
  Master Seal in a test save, reading the menu's class list, would be the real proof. That step needs an
  existing route or replay with a seal; no new play.
- Enemies: whether anything in enemy creation reads Job+0x64 was not traced. The enemy tables name their classes
  directly.

## 5. What needs the game core later (engine round, owner OK then)

**A third promotion choice (FE8 port style).** It is not possible from tables. The Job row has exactly two
promotion cells. The Master Seal menu comes from `ClassChangeEnumerator::Enumerate` / `Add`, which read only
those two. The plan for that later round:

- **Engine:** a small patch in `ClassChangeEnumerator::Enumerate` (0x0021B148) that also adds the class named
  in a third cell. The unused `Job.base_class.1` cell (+0x68, no reader found) can hold that class, so no new
  table is needed.
- **Tables:** this module would then draw a third target under the same guards, and `choices: 3` would be
  allowed.

**The engine work must also cover:** the menu having room for a third row, `Unit::ClassChange` accepting a class
from the third cell, and the class-change preview showing the third class. None of this is built.
