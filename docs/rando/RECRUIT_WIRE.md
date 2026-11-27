# Wiring the character shuffle (for the wiring round; recruit track, plan round 2)

**Status 2026-11-21 (round 59):** done. Round 58 (W2) wired the shuffle into the tools, and round 59 (E1) added the page rows and the game side ("keep the face" only; the full look waits for E3/E4). docs/RANDOMIZER_RECRUIT.md.

**For the owner.** This is the to-do list for the round that puts the character shuffle into the randomizer
tools. That round is allowed to edit the shared files this track may not touch. Nothing on this page has been done
yet. The four page rows go in during plan round 3, together with the game-side part, never earlier.

The module is `tools/randomizer/recruit.py` (docs/rando/RECRUIT.md). With `recruit off`, nothing below may change
any output: R8, and the fixture seeds r50all, r50def and r50shops must stay byte-identical.

## 1. `tools/randomizer/rando.py make` (and `check`): four flags

```
p.add_argument("--recruit",        choices=("off", "route", "any"),  default="off")
p.add_argument("--recruit-look",   choices=("keep", "full"),         default="keep", dest="recruit_look")
p.add_argument("--recruit-class",  choices=("own", "slot"),          default="own",  dest="recruit_class")
p.add_argument("--recruit-stats",  choices=("autolevel", "slot"),    default="autolevel", dest="recruit_stats")
```

They become a separate `ropts` dict (the keys of `recruit.DEFAULT_OPTS`), **not** keys of `topts`. Adding them to
`topts` would change `mod.json` for old seeds that have a track on. `ropts` goes into `mod.json`, the plan and
the spoiler header only when `ropts["recruit"] != "off"`. `cmd_check` passes the saved `ropts` back into
`make_all`.

## 2. `config/randomizer/rules.json`: one new block

Copy `recruit.DEFAULT_RULES` in as `"recruit": { ... }`. `RecruitTables` reads `facts.rules["recruit"]` key by key
over its defaults, so the block can also be left out. Keys:

| Key | Value today | Meaning |
|---|---|---|
| `recruit_fixed` | `["PID_ギュンター"]` | story people who never move, besides the avatar flag and the dragon-vein flag |
| `recruit_hold` | `["PID_ニュクス", "PID_アシュラ"]` | held in their spot until Conquest 9 / Conquest 16 pass the robot; freeing one is a one-line change |
| `recruit_castle` | Izana, Fuga, Yukimura, Flora | castle_join records 2-5; a pool of their own |
| `recruit_flier_before` | `{"A": "A010", "C": "C011"}` | R6: a flier must have joined before this chapter |
| `flier_job_category` | `"JCID_飛行"` | which classes fly |
| `recruit_keep_cells` | (list in the module) | the Person cells that follow the filler |
| `recruit_full_cells` | `aid, mpid_name, mpid_help, body_type, voice` | the cells full identity adds |

A Seal of Flames rules file (F-047) gives its own `recruit` block: other castle joins, holds, chapters.

## 3. `tools/randomizer/tracks.py make_all`

```
def make_all(facts, seed, switches=None, topts=None, ropts=None):
    r_edits, r_lines = [], []
    if ropts and ropts.get("recruit", "off") != "off":
        import recruit as RC                      # never imported when off (R8)
        rt = RC.load_tables(facts=facts)          # reads only the HANDOVER rows in addition
        r_edits, r_lines = RC.plan_recruit(rt, seed, ropts)
        g = RC.run_guards(rt, r_edits, ropts)
        refuse the seed if any guard fails (the page shows "this seed failed a check")
        facts = RC.shuffled_facts(facts, r_edits)
    plan = R.make_plan(facts, seed, switches)     # slice 1 and every track plan on the shuffled facts
    ...
```

Output (the part that is easy to miss): `R.render` writes only slice 1's Person columns, starting from the facts
it was given. The recruit cells slice 1 does not write still have to reach the files: skills, personal skills,
limit_mod, reclass and the beast flag, and with Classes/Growths/Join stats off also job, bases, growths and weapon
exp. Write the recruit `Person` edits for `GameData/GameData.bin.lz` into the Person CSV first, then lay slice 1's
values over them (slice 1 wins where both write).

- `DisposUnit` recruit edits (`jid`, `item_N`) go into the same Dispos CSV as items/enemies. Recruit runs first,
  so a later track's item edit on the same cell wins. The items and enemies tracks plan on `shuffled_facts`,
  which already contains the recruit item swaps.
- `Person` edits with `file` = `GameData/Person/{A,B,C}_HANDOVER.bin.lz` (`laid_by: person_hook`): write them to
  the mod folder as their own Person CSVs (the table tools take a file argument). They reach the in-game patch only
  after the core accepts `GameData/Person/**` (plan round 3, engine build, owner OK). Until then `ingame.py` must
  skip them **and say so in the spoiler** ("route-variant joins keep the spot's starting stats").
- `FaceData` / `Message` records (`laid_by: engine`): go into the plan JSON only, for plan rounds 4-6. Do not offer
  "full" on the page before round 6.
- Spoiler: `_section("Character shuffle", r_lines)` before slice 1's section.

## 4. Slice 1 fix that comes with it (the gap found in this round's Handover read)

Route-variant placements (pid `PID_A_*`, `PID_B_*`, `PID_C_*`, all with an empty `jid`) create the unit in the
route row's class. `Unit::Handover` then switches the person to the main row but **keeps the unit's class**. So
with Classes on today, those joins stay in their original class (docs/rando/RECRUIT.md section 2). Fix in
`randolib.make_plan` / `render`: for every placement whose pid is a HANDOVER row of a person whose class changed,
write the new class into `jid` and run the same weapon check on its items. This is the same cell recruit uses, and
the core already lays it. It changes the output of seeds with Classes on (the route-variant placements gain a
`jid`), so it needs the owner's OK as a slice-1 change, with the fixture seeds updated in the same round. The
slice-1 flier rule (R6 of the design, "a flier per route before the ninja doors") should be switched on in the
same round.

## 5. Page rows (`tools/play/rando.py OPTIONS`, read by `ingame.schema()`), plan round 3

```
"recruit":       ("Character shuffle (who joins where)", ("off", "route", "any"), "off"),
"recruit_look":  ("  Shuffled people look like", ("keep",), "keep"),          # "full" added in plan round 6
"recruit_class": ("  Recruit class (own / spot's)", ("own", "slot"), "own"),
"recruit_stats": ("  Recruit stats (autolevel / spot's)", ("autolevel", "slot"), "autolevel"),
```

"Everything on" sets route / keep / own / autolevel. Help text (design section 2): lords, royals, Azura, Gunter
and children never move; same sex only; Nyx and Shura held; with Classes on, keep the face mostly shows as the
personal skill and the weapon ranks.

## 6. Tests to extend in the wiring round

- `tests/test_rando_ingame.py`: the four rows equal PLAY RANDOMIZED's list, and the page answer gives the right
  flags.
- `tests/test_randomizer.py` (or the integrate test): `make_all(..., ropts={"recruit": "off"})` equals
  `make_all(...)` byte for byte on the fixture seeds; with recruit on, the mod folder holds the recruit cells and
  `check` reproduces it.
- Track independence: with recruit on, the items, enemies, music and nuzlocke draws for spots that did not move
  are unchanged.
