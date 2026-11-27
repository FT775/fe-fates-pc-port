# Randomizer track "recruit": the character shuffle, plan round 2 (host reads and the module)

**For the owner.** The character shuffle now exists as a tested module, `tools/randomizer/recruit.py`, but it is
**not on the page and not in PLAY RANDOMIZED yet**. That happens in plan round 3, together with the game-side part.
For now you can try it from the command line. It prints who goes into whose spot and checks every safety rule:

    python tools/randomizer/recruit.py plan --seed myseed --recruit route
    python tools/randomizer/recruit.py check --seeds 50

How it works: every join spot stays where it is in the story. If Saizo is put in Kaden's spot, Kaden's spot joins
in chapter 12 as Saizo would play: his class line, growths, stats levelled to the spot's level, skills and
weapons. With **keep the face** the spot still looks and sounds like Kaden. **Full identity** (Saizo's name,
portrait and model) is worked out as data here. It needs engine builds in plan rounds 4-6 before you can see it.
This round's code reading also found one gap in the randomizer we have today, and it changes plan round 3
(section 2, item 1): on Revelation, and for a few Birthright and Conquest joins, people arrive in their original
class even with Classes on. Nothing counts as done until you say ok (F-037).

Round 2 of the shuffle plan (docs/RANDOMIZER_RECRUIT.md section 8), 2026-11-20. Host only: no game run, no robot
run, no build. Files of this track: `tools/randomizer/recruit.py`, `tests/test_rando_recruit.py`, this page and
`docs/rando/RECRUIT_WIRE.md`. No shared file was edited (rando.py, randolib.py, gamedata.py, ingame.py,
rules.json, docs/RANDOMIZER.md, check_all).

## 1. What is built

- `plan_recruit(tables, rng, opts) -> (edits, spoiler_lines)`, `run_guards(tables, edits, opts)`,
  `shuffled_facts(facts, edits)`, `load_tables()`. These are the design's section 6 interfaces.
- Options: `recruit` off/route/any, `recruit_look` keep/full, `recruit_class` own/slot, `recruit_stats`
  autolevel/slot. **off is the default and makes no edits and no spoiler lines**, so existing seeds stay
  byte-identical. With off, `shuffled_facts` hands back the same object.
- Its own sub-seed: sha256 of (tool `rando-recruit-v1`, the seed, `recruit`), then one stream per purpose and per
  pool or placement. No other track's draws move. A test checks that slice 1's plan is unchanged after a recruit
  plan.
- **The tables come in as an object (F-047).** The pools, route groups, join chapters, route-variant rows and
  story people all come from the rows plus a rules block (`DEFAULT_RULES` in the module, overridable through a
  `recruit` block in rules.json or a story's own rules). Fixed people come from flags: the avatar flag, and the
  dragon-vein flag for the eight royals and Azura. The only names written in the module are the short lists in
  its rules block: Gunter fixed; Nyx and Shura held; the four castle joins; and the two ninja-door chapters. A
  Seal of Flames tables object can pass its own lists.
- Route groups are worked out from the placements: every placement of a spot's main id or route-variant rows in
  a route chapter, on any team, since talk recruits start on team 1 or 2. A test checks that they equal each
  person's own `support_route` mask in the Person row, and they do for all 29 pooled people who join in a chapter (the 4 castle joins are listed in the rules).
- Pools (route mode, this cartridge): Birthright+Revelation 8 women / 6 men, Conquest+Revelation 5 / 6,
  all-routes 1 / 3 (Felicia stays unless "any"), castle 1 / 3. "any" merges the chapter groups per sex.
  These match the design's section 3. The design counted Hayato among group 1's men and Nyx and Shura as held,
  so the module's 6 men in group 1 are Subaki, Saizo, Azama, Hayato, Hinata and Kaden.
- What a filler brings into a spot (keep the face): class line and Heart Seal list (own: the filler's line,
  moved to the spot's tier by swapping the line's two classes, `job`/`job_low`; slot: the spot's), weapon exp
  (it follows the class choice and is capped at the new class's limits), personal bases (autolevel: the filler's
  bases moved to the spot's level with the filler's growth plus the new class growth, levels counted +20 when
  promoted, inside the class floors and caps; slot: the spot's, capped), growths, stat caps (limit_mod), learned
  and personal skills, and the beast flag (own class only; it goes with the filler's class line). Growths always
  come from the filler: "stats: slot" only means the spot's starting numbers.
- Every route-variant HANDOVER row of a spot gets the same filler, levelled to the row's own level. Each
  route-variant placement also gets the new class in its `jid` cell, because the core can lay that today
  (section 2).
- Carried weapons the new class cannot use are swapped on every placement of the spot. They become ordinary shop
  weapons of a kind the class uses, at the old rank or the highest the new weapon exp allows. Beaststones are
  never sold, so beast fillers fall back to the stone the game itself hands to beast-class people (a Beaststone).
- Full identity, as data only: the Person cells `aid`, `mpid_name`, `mpid_help`, `body_type`, `voice` (main and
  route rows, tagged `"look": "full"`), plus a FaceData record (spot face id shows the filler's) and a Message
  record (spot name id shows the filler's) for the engine rounds.
- Every edit says who lays it: `core` (the in-game core today: GameData at New Game, GameData/Dispos/**),
  `person_hook` (the HANDOVER rows: needs the per-file hook extended to GameData/Person/**, an engine build) or
  `engine` (face and message: plan rounds 4-6).
- Spoiler lines: a "Character shuffle" section listing spot -> filler per pool, the fixed people with the reason,
  and the credit line for the public tools' list of breaks.
- Guards R1-R9 of the design plus "weapons usable". If a draw fails a guard, the module draws again (up to 60
  times, all from the sub-seed). In practice only R6 (a flier before the ninja door) ever fails, because Subaki's
  is the only flier spot that joins Revelation before chapter 11.

## 2. Host reads (the four questions the design left open)

All read-only from `asm/text` and `extracted/code.bin` on this machine. No game text copied.

1. **`Unit::Handover` (0x003D82F4): which row wins.** [high for the code; medium for the CreateImpl class source]
   It is called only from `Unit::CreateImpl2` (0x003D4490), when the placed row's `replace_index` (+0x28) is not 0.
   It swaps the unit's Person pointer (unit+0x9C) for the **main** row (`Person::Get(replace_index)`). It shifts
   the unit's stored stats by (route row bases - main row bases) so the totals do not jump. Then it merges the
   main person's set-aside unit (force 5), keeping the higher level, stats, weapon exp and skills. The unit's
   class (unit+0xA0) is **not** re-read from the main row. So the route-variant row (or the placement's `jid`)
   decides the **join class, level and starting stats**, and the main row decides everything after the join:
   growths, personal skill, name, face and model.
   - For the shuffle: in plan round 3, keep the face can ship **without** the GameData/Person/** hook for the class
     (the placement `jid` cell, already laid by the core) and for growths, skills and the personal skill (the main
     row). Without the hook, the route-variant joins (all of Revelation's, plus Birthright 7/8/11/22 and Conquest
     10/11/15/16) start with **the spot's own starting stats** at that level, as if "stats: slot". The hook
     extension fixes that and is the round 3 engine-build question for the owner.
   - **Gap in today's slice 1** (not this track's file; for the wiring round): slice 1 changes only the main row's
     class and the weapons on main-id placements. The route-variant placements have an empty `jid`, so those units
     are created in the route row's original class with their original weapons. That means: on Revelation, Silas,
     Hinoka, Sakura, Saizo, Orochi, Elise, Arthur, Effie, Hayato, Laslow, Peri, Odin, Niles, Azama, Setsuna and
     Scarlet; on Birthright, Silas, Hana, Subaki, Reina, Hayato and Shura; on Conquest, Selena, Beruka, Kaze, Gunter
     and Shura. All of them join in their **original class** even with Classes on, and keep it after the join.
     Their weapons still fit that class, so nothing breaks; the randomizer just does not reach them. The cheap fix
     is the same `jid` cell. RECRUIT_WIRE.md lists it.
2. **FaceData and AssetTable load moment.** [medium] `FaceDataManager::Initialize` is called from
   `MainSequence ... ProcSequence::InitializeB`. `AssetTable::Load` is called from `ContentsManager::LoadGlobal`,
   and `AssetTable::LoadROM` from `BattleGlobal::Initialize`. All of these load once at boot, before New Game, so
   full identity P1/P3 by file needs a resident patch at New Game (an engine build). The face lookup itself goes
   by the Person's `fid` (+0xC), which stays, as the design says.
3. **The `unit/Head/%s` source.** [high] `UnitIcon::SetIcon(const Job*, const Person*)` (0x004F5104) passes
   Person+0x10 (the `AID_` label, without "AID_") as the head name, or the Job's `JID_` when the person has none.
   `UnitIconObject::ReadSheet` (0x001D6F50) formats `unit/Head/%s/%s%s.bch.lz` from that name. So **P5 needs
   nothing of its own**: the `aid` cell (P3) also moves the map sprite.
4. **The message-fetch function.** [high for the name; medium that one hook covers dialogue]
   `Mess::Get(const char*)` (0x003D1CEC), about 1,590 call sites. `Mess::GetNoReplace` (0x003D16CC) is the variant
   without argument replacement. P4's whole-word name hook goes on `Mess::Get` (plan round 6).

## 3. Test results (host)

`python -m unittest tests.test_rando_recruit`: **14 tests, all pass** (94 s). Covered: R1-R9 plus weapons usable
for 50 seeds in each of the 16 option sets (route/any x keep/full x own/slot x autolevel/slot); off = no edits for
every combination; the same seed gives the same plan; seeds differ; the tables are never modified and slice 1's
plan does not move; `shuffled_facts` carries the filler; the autolevel identity (own class, own level = own
bases); the pools follow the rows (support_route cross-check); both of Revelation 9's Hayato placements get one
class and one filler; the flier guard catches a hand-made bad map and passes it with the spot's class; the
cross-sex, pool and fixed-person guards catch hand-made bad maps; the CLI runs and refuses a JSON path outside
build/. `recruit.py check --seeds 5` also passed every option set.

A sample plan (seed `abc`, route, keep, own, autolevel) gives about 2,000 edits: about 1,560 laid by the core
(mostly weapon swaps on the spot's placements in later chapters and paralogues) and about 430 for the
route-variant rows (person_hook).

## 4. How to wire it

See `docs/rando/RECRUIT_WIRE.md` for the exact flags, the rules.json keys and the `tracks.make_all` changes. In
short: recruit runs first, slice 1 and every track then plan on `shuffled_facts`. The recruit Person cells that
slice 1 does not write still have to reach the mod folder and the in-game patch. The page rows are added in plan
round 3, never earlier.

## 5. What needs the core later (owner OK at that round)

| Need | Why | Round |
|---|---|---|
| Per-file hook extended to `GameData/Person/**` | route-variant rows' level-matched stats (and slice 1's) | 3 (ask) |
| Resident FaceData / asset patch at New Game | full identity portraits and models (both tables load at boot) | 4 |
| Chapter Person copies | full identity in chapters that use their own copy of a person (not read here; the joins page found none of the 49 in them, the presentation page counted 285 copies: check in round 4) | 4 |
| `Mess::Get` name hook, voiced lines of swapped speakers silenced | names in dialogue | 6 |
| Missing-expression fallback | R9 checks only that a face id exists | 5 |

Not reached by recordings, as the design says: Revelation 8 Hayato, Conquest 16, the two ninja doors (cheat-poke
round, with the owner's yes).

## 6. Credit

The list of known breaks comes from the public Fates randomizers: Ignis and Paragon (thane98), lashoun's
upgraded-fefates-randomizer, the 2016 GBAtemp randomizer (GPL; facts only, no code). The spot-keeps-its-id method
follows our Sacred Stones port's Recruitment.
