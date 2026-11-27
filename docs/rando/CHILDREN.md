# Randomizer track "children": the child units (owner 2026-11-20, "build the other missing parts too")

**For the owner.** The greyed "Children" row on the randomizer page now has a module behind it. With it on, the
22 child units (the two Kana rows and the 20 children who join in a paralogue) get the same randomizing as
everyone else: a new class, shuffled growths and join stats, and, if you pick them, the growth modes and the
skill options. What a table edit cannot change, the game still decides when the child joins: the extra class a
child inherits from its parents for the Heart Seal, and the stat and skill bonuses it takes from its parents.
Guards keep each paralogue winnable: a child that starts as a healer stays a healer, a child that starts with a
weapon keeps a class that can attack and a weapon it can use in every map it appears in, and a child with the
lock-opening skill keeps it. With the row off (the default) nothing changes, and every seed made before gives
exactly the same files. The row is not wired into the page or rando.py yet: the integrate round after rounds 53
and 54 does that. Nothing counts as done until you say ok (F-037).

Module `tools/randomizer/children.py`, tests `tests/test_rando_children.py` (14 on made-up tables, 3 on your
own tables when they are there). Our own code; it reuses slice 1 (`randolib.py`), the growth track and the
skills track. The Sacred Stones port has no children, so there is nothing to borrow from it here. Public Fates
tools (GPL) were used for facts only (they ban children by default, docs/collab/FATES_RANDO_RESEARCH_GROK.md).

## 1. Who the children are (from the Person table)

A child is a Person row of the player's army with a `child_id` (Person +0x82) other than 0xFFFF; slice 1
already used that test to leave them out (`Facts.is_child`). On your tables there are 22:

| Rows | Join chapter (Dispos file) | Notes |
|---|---|---|
| Kana (male row, female row) | X002 | dragon (SPID_マムクート): class kept, like Corrin; only one row joins, by the avatar's gender |
| Shigure, Dwyer, Sophie, Midori | X003-X006 | all routes; Shigure, Sophie and Midori are also placed in Z000 (a chapter no route lists) |
| Shiro, Kiragi, Asugi, Selkie, Hisame, Mitama, Caeldori, Rhajat | X007-X014 | Birthright and Revelation |
| Siegbert, Forrest, Ignatius, Velouria, Percy, Ophelia, Soleil, Nina | X015-X022 | Conquest and Revelation |

`family_index` (Person +0x2A) names each child's **fixed parent** (the row index: Shigure -> Azura, Dwyer ->
Jakob, Kana -> the avatar of the other gender, and so on). The other parent is whoever the player paired.
In the paralogue a child is placed one to three times: as the player's unit (team 0), as an AI ally (team 2) or
as an enemy to talk to (team 1: Rhajat, Percy, Nina). Every placement leaves the class cell empty, so the class
comes from the Person row.

## 2. What a table edit can change, and what it cannot (facts)

| Thing | Who decides | Table edit? |
|---|---|---|
| The child's class at join | Person.job / job_low (Unit::CreateImpl reads Person +0x2C) | **yes** (this track) |
| Personal growths | Person.growth, then **averaged with one parent's** at every level-up (unit::Family::GetGrow, docs/GROWTH.md section 2; the class growth is added after) | **yes**, half of the effect; the parent half follows the parent's row (which slice 1 may have changed) |
| Personal join stats, weapon exp | Person.base, Person.weapon_exp | **yes** |
| Stat caps | Job.max + Person.limit_mod + both parents' limit terms + 1 (unit::Family::GetLimit) | not edited; our cap check uses Job.max + limit_mod only, which is stricter |
| Starting skills, personal skill | Person.skill.1-5, personal_skill (Unit::CreateImpl, Unit::IsEquipSkill) | **yes** (skill options) |
| The class inherited from the parents (an extra Heart Seal class) | `anonymous_namespace::GetInheritJobIndex` 0x003C5C30 at join | **no**: the game picks it from the parents' Person rows (below) |
| Stats and equipped skills taken from the parents at join | `Unit::Inherit2` 0x003D8700: it looks up the parents' live units (`UnitPool::GetFromPerson`), reads their stats (`unit::Edit::GetCapability`) and growth (`Unit::GetGrow`), and calls `Unit::InheritEquipSkill` twice | **no**: runtime, from the parents as played (call list read; the exact formula is not read yet) |
| Join level | Person.level 10 with autolevel_rank 10: extra level-ups by scenario progress (docs/TABLES.md Person +0x35) | not edited |

**The inherited class, as the code picks it** (read from the disassembly of 0x003C5C30 and 0x003C59F4):

1. the parent's base class (`Person::GetLowJobIndex`: Person.job, or job_low when the class is promoted);
2. else the parent's first Heart Seal class (Person.reclass.1, +0x7C);
3. else, when the parent has a fixed parent itself (family_index), what that grandparent passes on;
4. else the parallel class (Job.parallel_class, +0x72) of the parent's base class, then of its reclass.1.

A candidate is refused (`IsInheritJobIndex`) when it is empty, when the genders differ and the class has no
other-gender twin (Job.gender_pair, +0x70; the twin is used when there is one), when it is the child's own base
class, when it is promoted, when the class has the flag `SPID_継承禁止` (only the singer's class), or, through
a support pairing, `SPID_支援継承禁止` (Nohr Prince(ss), Wolfskin, Kitsune, Villager). A list of excluded classes
passed in by the caller is also checked; this track does not know that list.

So the table edits **do** move the inherited class, but only indirectly: slice 1's new class for the parent is
what step 1 reads, and the child's new class changes which candidate counts as "its own" (then the next step is
used). The spoiler log shows, per child, what the rule gives from the fixed parent with this seed's tables
(the slice-1 plan is passed in as `base_plan`). For Kana the fixed parent is the avatar; the game has a separate
`GetInheritJobIndexFromPlayer` for that case, not read yet, so the log says so instead of guessing.

## 3. What is built

`plan_children(tables, rng, opts) -> (edits, spoiler_lines)`, the same shape as the other tracks. Options (the
names the adults' options already use in rando.py / tracks.py):

| Option | Values (default in bold) | What it does for the children |
|---|---|---|
| children | on / **off** | off: no edits, no lines (byte-identical seeds) |
| classes, growths, join_stats, trees | slice 1's switches (**on, on, on, own**) | slice 1's class pick, growth shuffle and join-stat shuffle, on the children |
| growth_mode, growth_variance, growth_min, growth_max, adjust_hp | the growth track's (**slice1**, 30, 5, 80, off) | the growth modes on top |
| bases_mode, base_variance, scale_to_level | the growth track's (**slice1**, 5, on) | the bases modes on top |
| personal_skills | **keep** / shuffle / random | shuffle: the children's personal skills dealt out again among the children; random: each draws a personal-family skill, no two children the same (and none in `taken_personal`, the adults' new ones, when the integrate round passes them) |
| skill_slots | **keep** / class | class: a starting skill the old class line teaches becomes the skill the new class line teaches at the same place (the skills track's rule) |

The track has its own sub-seed (from the run seed and the track name), so the adults' plan and every other
track's draws never move. It runs slice 1's own code on a view of the tables whose "scope" is the children, so
the class pick, the class line (job_low), weapon exp and the weapon swap are exactly slice 1's.

Edits: Person cells of the 22 child rows (job, job_low, bases, growths, weapon exp, and with the skill options
skill.1-5 and the three personal-skill cells) and the item cells of the children's own placements. Nothing else.
`files_with_edits(facts, files, edits)` adds them to a mod folder's tables/Person.csv and tables/DisposUnit.csv
(and refuses a row another track already wrote). Host commands (no game start):

    python tools/randomizer/children.py check --seeds 50 [--trees any] [--growth-mode M] [--personal-skills M] ...
    python tools/randomizer/children.py make --seed S [...] --out build/<folder>

**Guards** (`run_guards(tables, edits, opts)`, recomputed from the edits and the original rows):

| Guard | What it checks |
|---|---|
| off_means_no_edits | with the row off there are no edits |
| only_children / only_allowed_cells | only the 22 rows and their own placements; only the cells above; no cell "changed" to its own value |
| legal_class | same gender row, same tier, a normal player class, beasts stay beasts (Selkie, Velouria), trees=own keeps the side |
| story_classes_kept | the dragon Kana rows keep their class |
| healer_and_attack_roles_kept | a child that starts in a staff class stays in one (Dwyer, Mitama, Forrest); every other child gets a class that can attack |
| promotion_line_legal | job_low is one of the new class's promotions |
| items_usable | every item in every placement of the child is usable with its new class and weapon exp |
| attack_weapon_at_join | a placement that held a usable weapon still holds one (slice 1's swap may hand a staff to a class with a staff and a weapon; this track turns that swap into a weapon of the same rank) |
| stats_within_caps | personal + class base within 0 (HP 1) and Job.max + limit_mod; growths 0-127 |
| lock_skill_kept | a child holding the lock-opening skill (Asugi, Nina) keeps it in the same cell (door opener) |
| personal_skills_unique | the three personal cells agree; no personal skill held by more children than before (the two Kana rows share one) |

The adults' route guards (a staff user, a door opener and a vein user per route) already cover the army the
player brings to a paralogue; the children add no vein flag change (flags are never edited).

**Test results (2026-11-20, host only):** `python -m unittest tests.test_rando_children`: 17 tests OK (14 on
made-up tables: off = no edits, guards over 50 seeds for 7 option sets, explicit legal-class checks, healers and
fighters, only children's cells, same seed = same edits, lock skill, personal skills, the inherited-class rule,
the files; 3 on your tables: 22 children, all guards over 50 + 20 + 20 seeds, off = empty). The neighbouring
suites (test_randomizer, test_rando_growth, test_rando_skills) still pass (42 tests). `children.py check --seeds
50` on your tables: 0 guard failures with the defaults, with trees=any + random personal skills, and with
growth/bases modes + shuffle + class skills. No game was started; no robot run.

**What the guards mean in practice** (on your tables, trees=own / any): most children have 7-8 legal classes
(15 with trees=any). The three healers have only their own class with trees=own (no other unpromoted staff
class of their gender on their side) and two with trees=any; the two beasts likewise. The Kana rows never
change class.

## 4. What needs the game core later (engine build, owner OK then)

- **Randomizing the inherited class itself** (e.g. a random extra Heart Seal class per child): the pick is
  code (GetInheritJobIndex at join). A table-only trick would be to change parents' reclass.1 or
  Job.parallel_class, which also changes the adults' own Heart Seal lists, so it is not done.
- **The parent bonuses at join** (Unit::Inherit2) and the inherited equipped skill (Unit::InheritEquipSkill):
  runtime, from the parents as played. Changing or turning them off needs the core.
- **The avatar's case for Kana** (GetInheritJobIndexFromPlayer): not read yet; reading it is host work only.
- **Swapping which child joins in which paralogue** belongs to the character-shuffle work (round 54's
  docs/RANDOMIZER_RECRUIT.md), not here.
- **A robot check** (a seed with children on, one paralogue's join read back from memory) needs a recording that
  reaches a child paralogue; none exists (docs/ROBOT.md: children are never met in real play, F-025 says do not
  marry for coverage). Until then the check is the host guards above plus the table reader.

Not done in this round on purpose (file ownership): rando.py's `--children` switch still refuses "on", the page
row stays grey, tracks.py does not call the module, and docs/RANDOMIZER.md is not changed. The integrate round
wires `plan_children` in after the growth and skills tracks (passing `base_plan` and the adults' new personal
skills as `taken_personal`), then `files_with_edits`.
