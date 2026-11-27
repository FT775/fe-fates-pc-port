# Round 62b: the randomizer page cleanup (F-049 addendum, F-050)

**For the owner.** The page now reads like a menu. Settings sit under seven headings (Basics, Characters, Classes,
Growths and stats, Items and shops, Enemies and bosses, Extras). Point at a setting and a help line under the list
says, in one sentence, what it changes in the game. On Seal of Flames the Children row is gone, not greyed.
Old leftovers ("slice1", growth min/max, the weapon-upgrade chance, the three boss rows) are off the page, but an
old seed still makes exactly the same game with the same run id. A **Spoiler log** switch (on by default) and a
**Randomize everything** button are new. The button turns on safe settings only: never Nuzlocke, Children or the
full identity swap, and it keeps your seed.

## What changed where

| Part | File | What |
|---|---|---|
| Rows | tools/randomizer/ingame.py `schema()` | `PAGE` (section, short label, one help sentence per visible row, Grok's order from docs/collab/RANDO_OPTIONS_GROK.md with the owner's corrections), `CHOICE_LABELS` (plain words for choice values: "slice1" shows as "Shuffle (same total)"), `SWITCH_CHOICES` (promotions, weapon stats drawn Off/On; the answer keeps "off"/"on"), `HIDDEN` (growth_min, growth_max, upgrade_rank, enemy_upgrade, boss_stats, boss_max_boost, boss_variance), `DRIVES` (the two page switches), `HIDE_FOR` (Children on Seal), `NOT_IN_EVERYTHING` |
| Command | ingame.py `make_args` | unchanged flags, in the round-62 order (`ARG_ORDER`); page-only rows have no flag |
| Page model (Python mirror) | ingame.py `page_restore`, `page_answers`, `page_everything`, `page_value`, `answer_text`, `run_id` | what the Rust page does, for host tests (run id = the core's `<seed>-<FNV-1a of the answer text>`) |
| Spoiler | tools/randomizer/rando.py `make --spoiler on|off` | off: no spoiler.txt; the plan, mod files and patch are the same (the page never passes it) |
| Page | engine patch 0030 (crates/zakuro/src/rando_page.rs) | reads the new fields, draws sections and the help line, hides hidden rows, Randomize everything, Spoiler log off removes the laid run's spoiler.txt |
| Robot | tools/harness/pagebot.py `resolve` | the agency scenario never picks a hidden, page-only, switch row, or a row hidden for the game |

## New schema fields (all optional; an old schema still reads)

| Field | Meaning |
|---|---|
| `section` | the header the row stands under; a header is drawn when it changes |
| `help` | one plain sentence; the help line shows `Label: help` for the row pointed at or focused |
| `hidden: true` | never drawn; still answered (its default, or the value restored from last.json) |
| `hide_for: {game: reason}` | not on that game's page at all; answered at its default (Children for `seal`) |
| `page_only: true` | never in the answer, so never in the run id or the make flags (Spoiler log, the two switches) |
| `drives: {key, off, on}` | an On/Off switch over a hidden row: on when that row is not `off`; turned on it sets `on` (an old value other than `off` is kept), off sets `off` |
| `choice_labels: {value: words}` | words shown for a choice value; the answer keeps the value |
| `switch: true` | a two-choice row ("off"/"on") drawn as Off/On |
| `grey_for` (round 62) | still read: fixed at default for that game, reason in the label (no row uses it now) |

## The two switches (exact mapping, the same answers give the same game)

| Page switch | Hidden row | Off | On (from off) | An old answer |
|---|---|---|---|---|
| Stronger enemy weapons | `enemy_upgrade` | 0 | 25 (round 62's Everything-on value) | 50 stays 50 |
| Tougher bosses | `boss_stats` | off | linear (round 62's Everything-on value) | ease stays ease |

How far an upgraded weapon goes and how much a boss gains comes from **Difficulty**, as round 62 already lays it
(Easy +1 forge, Normal next tier, Hard next tier +1; bosses +10% HP and +1 might per step). `upgrade_rank` stays
fixed at "same"; `boss_max_boost`, `boss_variance`, `growth_min`, `growth_max` keep their default or an old answer's
value (the growth floor 20-100 rules either way).

## Randomize everything

Every shown row to its `all` value, Randomizer on, the seed kept. `all` is round 62's suggested value except:
Children, Nuzlocke, the full swap look (fixed), Nuzlocke's "who counts" (fixed): their default. A row hidden for the
game (Children on Seal) stays at its default. The page's help line then lists the rows it turned on.

## Spoiler log

Default on. Off: the run just laid keeps no spoiler.txt (removed from `<data>/rando/<title>/runs/<id>/` and from the
work folder `build/rando-make/<id>/` before the game starts), and This run shows no spoiler button. The answer, the
run id and the laid game are the same either way. plan.json (the machine record `rando.py check` needs) is still
kept beside the run.

## Proofs (implement step, host only)

- tests/test_rando_page62b.py (21 tests): sections in order, label + one sentence on every shown row, no "slice1",
  hidden rows still flagged, defaults unchanged against the frozen round-62 schema (tests/test_rando_page_r62_schema.json),
  Children `hide_for` seal; for all 109 round-62 check runs (build/r62/check/runs, both games) plus off / defaults-on /
  three everything-on sets per game: the same answer text, the same run id, the same make flags as round 62's
  ingame.py (git 258da34); Randomize everything; spoiler never in the answer or the command.
- build/r62b/implement/remake.py: nine real makes through the new page's answer (Fates all1/all2/all3 and a
  boost-off-hard run, Seal all1/all2/all3 and a boost-off-hard run, two with Spoiler off): patch.txt and plan.json
  byte-identical to round 62's stored runs; Spoiler off wrote no spoiler.txt (remake.jsonl).
- Rust (patch 0030): the new fields read, an old schema still reads; old answers give the same text and run id on
  the new page (Fates and Seal); page-only rows never answered; switches drive their rows; Seal draws no Children
  control; Randomize everything; sections and the help line drawn, hidden rows not drawn; Spoiler off removes the
  laid run's spoiler only at the answer.

The build step owns: patches/zakuro/0030 (the patch file is build/r62b/engine/0030-*.patch), the frontend build,
play/game install, the before/after pagebot screenshots. Note for the "before" screenshots: the round-62 exe reads
the repo's schema, which now has page-only rows; take them with a copy of the round-62 tools (git 258da34).
