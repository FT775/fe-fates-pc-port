# Round 79: guarantees inside the randomizer (desk plan, counted, for your OK)

**Moved to round 75b** (owner, 2026-11-25, "Yes, move it up"): it runs after round 75 and before round 76's full check, so that check covers the new seeds. Round 74 changed tools/randomizer/recruit.py, ingame.py, rando.py and tracks.py after this plan was read; round 75b re-reads them before counting starts.

Written 2026-11-25 by a side session while round 74 (an engine round) runs in the main folder. Desk work only: no
build, no game, no robot, no test suite was run. Facts were read from our own code and docs, from the game's own
scripts and maps (read only, nothing copied here but counts and chapter ids), and from the robot results round 72
already left on disk. Grok's answer: docs/collab/SEED_GUARANTEES_GROK.md. Nothing in this file has been built.

Confidence: **[high]** read or counted directly, **[medium]** inferred from counts and context, **[low]** a guess to
check. "Counted" = a time measured in an earlier round (named). "Estimate" = never measured, written on the slow side.

## In plain words

**What changes for you.** Today a randomized game only promises that each story has a healer, a door opener and a
dragon-vein user *somewhere*. Nothing says *when* they join. After round 79 the randomizer itself makes sure each
needed helper is in your army **by the first chapter that needs them**:

- a **door and chest opener** (a thief or anyone with the lock-opening skill) before the first map with chests or
  locked doors;
- a **healer who is holding a staff** by chapter 7 on every story;
- a **flier** before the two maps known to need one (Birthright 10 and Revelation 11);
- a **dragon-vein user**: Corrin always has it and is on every map, so this is already true.

It is always on. There is no page switch. If a seed's roll already meets every rule, the seed's classes stay
exactly as they are today. If not, the randomizer gives **one** person who is in your army at that chapter a class
with the missing skill, the same way it already does per story today. A small check at the end looks again and
refuses a seed that still misses a rule (that would be our bug, not bad luck).

**Never stricter than the original game.** In the original Revelation, nobody who can open chests is there for the
chests of chapters 7 and 8. The rule does not force one in. It asks for an opener by chapter 9, which is when the
original game gives you one. (Grok agrees: docs/collab/SEED_GUARANTEES_GROK.md.)

**How often it matters today.** We measured 200 seeds with the page's default settings (classes, growths, join
stats). **163 of 200 seeds miss at least one rule today.** The misses are healers (Revelation 96, Conquest 87,
Birthright 65 of 200) and fliers (Revelation 49, Birthright 33 of 200). Door openers never miss today,
because the thieves keep their own lock-opening skill whatever class they get.

**Your current game is safe.** A saved game remembers its own run folder. The play-evening seed (`hoshido73`, run `hoshido73-6ab5ad56`) keeps
loading the tables it was made with. Only a **new** game made after round 79 uses the new rules, and it gets a new
run id, so the two never mix. Old share codes (round 74) are refused with "This code was made by another version of
the randomizer", because they would make a different game now.

**What needs your OK:**
1. **Every seed's result changes** (an announced seed change). The seed fingerprints are re-recorded, the guarded
   boss seed `r63fboss1` included. That one needs your yes by name (section 7).
2. The open calls in section 10. Each has a default; silence means the default (F-051(4)).

**No engine build, no program install.** The game runs the randomizer from the project's `tools/randomizer` folder
(docs/RANDOMIZER_INGAME.md section 5), so the change is live as soon as the round's commit is in the main folder.

**How long:** counted **7 h 50** in two sittings (5 h 25 code and tests, then 2 h 25 proofs, checks and report). Hard
stop at 1.5 times each sitting. With the cut order used in full: **6 h 05**. Section 9. (15 min of it is the
"no repeated class" rule you added on 2026-11-25: a guarantee picks a class nobody else in your army has yet,
whenever one with the needed skill exists.)

## 1. What exists today (read 2026-11-25)

| Part | Where | What it does | Timing? |
|---|---|---|---|
| Route roles in the class pass | `randolib.make_plan` step 2 (`role_ok`, `route_members`) | per route (A/B/C, each with the shared chapters A000-A005): if nobody is a staff user or door opener, one changed person of that route is given a class with the role (`forced`) | no |
| Route-role guards | `randolib.run_guards` (`staff_user_per_route`, `door_opener_per_route`, `vein_user_per_route`); test `tests/test_randomizer.py` `test_route_roles_kept` | the same, re-checked from the plan | no |
| Even spread keeps roles | `misc.assign_evenly` (`ROLES`, `_roles_ok`) | the even pass gives a route's staff user / opener back slice 1's class if it took the role away | no |
| Shuffle guards | `recruit.py` `run_guards` R5 (staff, door, vein per route), **R6 flier before A010 and C011** (`recruit_flier_before`) | only when the character shuffle is on; R6 is the one timing rule that exists, and it only checks, it never repairs (the shuffle re-rolls up to 60 times) | R6 only |
| Lock skill never moved | `skills.py`, `children.py` guards | the skills and children tracks never take the lock-opening skill away | n/a |
| Keys never moved | `chests.STORY_ITEMS` | the chest track never moves door or chest keys | n/a |
| No map table | docs/RANDOMIZER.md section 3, "Not checked" | which maps need a vein, opener or flier was never written down | no |

Who counts for a role (unchanged): **door opener** = the lock-opening skill in the person's own skill list or in the
class's skill list (keys in shops are not counted); **staff user** = a class with a staff rank; **flier** = a class
in the flying category; **vein** = the person flag (Corrin and the royals; slice 1 never edits flags).

## 2. The needs table (the hand-made list)

### How it was built

1. **Which chapter has chests and locked doors** [high]. Every chapter script's map tile events were read with the
   read-only reader of round 70 (`chests.read_cmb`). Kind 10 = chest and kind 1 = village were settled in round 71
   (every one stands on a chest or village tile). This plan did the same for **kind 9: all 56 kind-9 tile events
   in Fates' story and paralogue scripts stand on a door tile** (the five door terrains), so kind 9 = a locked door
   [high]. (Gates and castle gates are other kinds and need no opener.)
2. **Who is really in the army at that chapter** [high for the male avatar]. Round 72's break check loaded a story
   save before every chapter and wrote the army it found (`build/r72/check/jobs/<path>-<chapter>-off/result.json`,
   key `army`: person and class of every unit, read from memory). Those saves were made by playing the story
   (recordings), so the lists are the real army, including people who leave (Kaze leaves Birthright after chapter
   14; Rinkah and Sakura are never in the Conquest army; on Revelation only Corrin, Azura, Felicia and Gunter are
   there for chapters 7 and 8). "Joined somewhere before" would have been wrong in all of these.
3. **Today's misses**: `randolib.make_plan` (slice 1 only, default switches) for seeds `g79s0`..`g79s199`, each rule
   checked against step 2's army list. Plan only, nothing written (35 s).

Two notes on step 2:

- The robot's saves for chapter 7 are "after chapter 7" (`bt-ch7-clear`, `cq-ch7-clear`, `rv-ch7-clear`), so the
  chapter-7 lists include chapter 7's own joiners. That is one chapter generous for the chapter-7 rules [medium]. It
  changes no rule below: every role counted at chapter 7 was already there before it, except Elise (Conquest
  staff), who joins in chapter 7 itself. Part G1 reads `cq-ch6-clear`'s army once to settle it.
- The robot always played a **male** Corrin. With a male Corrin, Felicia stays and Jakob comes back later (chapter
  16-17). The placements put both of them in chapters 2-3 and Conquest 6-8, so with a female Corrin it is very likely
  the other way round [medium]. The rule therefore treats them as **one retainer slot**: a need is met through that
  slot only if Felicia **and** Jakob both have the role (call 5).

### The table

| Story | Role | Needed by | Why that chapter (facts) | Who can count there (army roll; pool = may get a new class) | Original game meets it | Misses today (200 default seeds) | Confidence |
|---|---|---|---|---|---|---|---|
| Birthright | door / chest opener | **A007** | first chests: 2 chest events in A007; first locked doors: 3 in A009 | after ch. 7: Kaze, Saizo | yes | 0 | [high] chapters; [medium] roll (one chapter generous) |
| Birthright | healer with a staff | **A007** | the owner's "a healer early"; the first chapter after the split | after ch. 7: Sakura, the retainer slot | yes | 65 | [high] roll; the chapter is call 2 |
| Birthright | flier | **A010** | a locked door on the ninja-village map (1 door event in A010); public randomizers list it as a map that breaks without a flier | after ch. 9: Subaki | yes | 33 | [medium]: the need comes from public tools' known-break list (facts only), not from our own map reading |
| Birthright | dragon vein | every chapter | vein tile events in most chapters | Corrin (kept class, flag; in every army list) | yes | 0 | [high] |
| Conquest | door / chest opener | **B009** | first chests: 4 in B009; first locked doors: 4 in B012 | after ch. 8: Niles | yes | 0 | [high] |
| Conquest | healer with a staff | **B007** | first chapter after the split | after ch. 7: the retainer slot, Elise | yes | 87 | [high] roll (Elise: see the note); the chapter is call 2 |
| Conquest | flier | none | no known Conquest map needs one | | | | [low]: not looked for beyond the public list |
| Conquest | dragon vein | every chapter | | Corrin | yes | 0 | [high] |
| Revelation | door / chest opener | **C009** | chests in C007 (6) and C008 (2), but the original game's first opener (Kaze) is only there after chapter 8; "never stricter" moves the need to the next chest map, C009 (3 chests); first locked door C011 | after ch. 8: Kaze | yes (C009) / **no** (C007) | 0 | [high] |
| Revelation | healer with a staff | **C007** | first chapter after the split | after ch. 7: **the retainer slot only** (Corrin, Azura and Gunter never change class) | yes | 96 | [high] |
| Revelation | flier | **C011** | the same ninja-village map as A010 (1 door event in C011) | after ch. 10: Subaki | yes | 49 | [medium], as A010 |
| Revelation | dragon vein | every chapter | | Corrin | yes | 0 | [high] |

163 of the 200 seeds miss at least one row (staff or flier). With the character shuffle on, door openers can move to
a later join spot, so the door rows can miss too (not measured; part G6 measures it).

**Consequence to know (Revelation healer).** In Revelation chapter 7 the only person who may change class is the
retainer (Felicia with a male Corrin, Jakob with a female one). So on every seed the retainer pair gets a class
that can use staves. With "classes from their own side" (the default) that is a short list (the Nohr promoted staff
classes). This is the price of "a healer by chapter 7" on Revelation. Call 2 has the looser choice.

**Not needed-by chapters:** paralogues (X001-X022). Four of them have locked doors (X004, X009, X016, X022), but
they are optional and open late, when every story already has its openers. The backstop reports them as
information only.

### Where the table lives

`config/randomizer/guarantees.json` (new; IDs only, like `rules.json`): per story, a list of
`{role, by, why, confidence, army: [PID_...]}` with the retainer slot written as one entry holding both ids. No game
values. A read-only command `python tools/randomizer/guarantees.py facts` re-derives the door and chest chapters
from the scripts (kinds 9 and 10) and, when round 72's results are on disk, the army lists, and exits non-zero if the
file disagrees. A test runs it when the RomFS is there (as `chests.py kinds` does today).

## 3. How it is enforced (generation time)

**Where.** One new module, `tools/randomizer/guarantees.py`, plus small hooks in code we already own:

| File | Change | Size |
|---|---|---|
| `tools/randomizer/guarantees.py` (new) | `needs(rules)` (the table for the active game), `met(facts, jobs, need)` (who covers it), `repair(facts, plan, seed, sw)` (the pass below), `check(...)` (the backstop) | new |
| `tools/randomizer/randolib.py` | `make_plan` step 2b: after today's route pass, call `guarantees.repair`; its lines go to `plan["forced"]` and a new `plan["guarantees"]` block | ~15 lines |
| `tools/randomizer/misc.py` | `assign_evenly`: the "roles stay" step asks `guarantees.met` instead of route membership | ~10 lines |
| `tools/randomizer/tracks.py` | the backstop cross guard after every class-changing track; a "Guarantees" section in the spoiler | ~20 lines |
| `tools/randomizer/ingame.py`, `rando.py` | the version marker (section 5) | ~15 lines |
| `config/randomizer/guarantees.json`, `seal_rules.json` | the tables (Seal: rebuilt, section 4) | data |

Not touched: `recruit.py` (its R5/R6 guards stay as they are and stay green, because the timing rules are stricter
than both), `chests.py`, the engine, the page code.

**The repair pass (deterministic per seed).**

1. Order the needs by (story position of the chapter, story letter, role): the same order every run.
2. For each need: if anyone in its army roll covers it (with the classes slice 1 drew), nothing happens.
3. Otherwise pick **one** person: from the roll, only pool people (not kept, not held: never Corrin, Azura, Gunter,
   the four royals with legendary weapons, Nyx or Shura); first those whose drawn class already changed, then the
   others; inside that, the earliest joiner, then table order. Draw their class from their legal classes that have
   the role, with its own random stream `rng_for(seed, switches, "guarantee", role, chapter, pid)`. The retainer
   slot repairs Felicia and Jakob together (each their own stream).
   **No repeated class (owner, 2026-11-25: "Yes, add it"):** the draw first keeps only the role classes that nobody
   else in that chapter's army has (counting class pairs as one class, as "Spread classes" does); only if none is
   left does it draw from all the role classes. So a guarantee never adds a repeat when it can avoid one, whether
   "Spread classes" is on or off. Part G2b.
4. Re-check every earlier need (a new class can take a role away: a flier made a healer). A person who is the only
   cover for an earlier need is skipped. At most 3 passes.
5. If a need still cannot be met, the next attempt draws again with an attempt counter in the stream (as the
   shuffle does). Expected never on Fates (G6 measures it on 1,000 seeds); if it happens, the backstop refuses the
   seed with the page's plain "this seed failed a check".

**"Healer with a staff."** A repaired healer's join placement must carry a staff of a rank their class can use.
Slice 1 already swaps carried weapons a new class cannot use; the repair asks that swap, for this one person, to
pick a staff for one slot when none is carried (the cheapest staff of the lowest rank, never a story item). Cells:
the placement's `item_1..5`, which slice 1 already writes.

**Fewest changes.** Other people's draws use their own streams, so they never move. A seed whose roll already
meets every rule keeps every table byte (only `plan.json`, the spoiler and the run id change, section 5). Each
repair changes one person's class (and its knock-ons: weapon exp, carried weapons, join stats fitted to the class,
exactly as for any drawn class).

## 4. How it meets the other parts

| Part | What happens |
|---|---|
| **Character shuffle** (recruit, way A) | The shuffle runs first and every later step plans on the shuffled rows (`tracks.make_all` step 1). Join spots keep their person id, so the army rolls (spot ids) still say who is there when; the repair then gives a class to the person now standing in that spot. The shuffle's own R5/R6 and its 60 re-rolls stay. Held people (Nyx, Shura, castle joiners) are never picked. |
| **Full swap** (look = full, round 74/75) | Only names, faces and voices follow the person; classes are cells like any other. Nothing extra. |
| **Even spread** (misc) | Its "roles stay" step uses `guarantees.met`, so it never undoes a repair. |
| **Promotions, skills** | Promotions change `job_low` and Seal targets, not the join class. Skills never move the lock skill (existing guard). The backstop runs after both. |
| **Children** | Out of the table: children are never counted and never repaired (they join in optional paralogues, after every need). The children track is unchanged. |
| **Nuzlocke** | The guarantee is about who **joins**. A fallen opener is the player's run, not a bad seed (Grok). The Nuzlocke help line gets one sentence: "Keep your first healer and lock opener alive." Call 6 asks whether Nuzlocke should want two of each. |
| **The four trouble chapters** (Conquest 9 and 16, Revelation 8 and 13) | No new kind of edit: the repair writes the same Person class cells and placement class/item cells slice 1 writes today, and the guarded chapters' rules (`scope.guarded`, `recruit_hold`) are kept. Revelation 8's double Hayato placement keeps one class (shuffle guard R3; slice 1's route-variant rule). |
| **Chest and village items** (round 71) | Keys never move (`chests.STORY_ITEMS`), so no key ends up behind its own door. G6 adds that as a test. |
| **Seal of Flames** (docs/rando/SEAL.md) | Its rules are rebuilt from the mod's tables (`sources.py rules`). Round 79 adds a `guarantees` block there: the first Seal-path chapter with chest or door events (kinds 10 and 9, read from the layered scripts at rule-build time) and the army rolls from the placements (`seal.first_join`). Only chapter ids and person ids are written; nothing of the mod is committed. Confidence [medium]: no Seal story save exists (round 72's Seal break check started from a Fates save), so the rolls cannot leave out people who leave. Door and healer only; no Seal flier need is known (`recruit_flier_before` is empty there). Cut item 2 in section 9. |

## 5. Seed versioning: telling old and new seeds apart

**What changes.** Every seed's `plan.json` gains the `guarantees` block, so every seed fingerprint changes; seeds
that needed a repair also change their tables. The slice-1 random streams keep their key (`TOOL_VERSION` stays
`rando-slice1-v1`), so a seed stays recognizably the same seed; only the repaired people differ.

**The risk this answers.** The game re-uses a run folder when `runs/<run id>/patch.txt` already exists
(`fates_rando_session`: "if !run_dir(..).join("patch.txt").is_file() { make(..) }"). The run id is the seed plus a
hash of the page's answer. If nothing in the answer changed, a new game with an old seed and old settings would
silently lay the old, unguaranteed tables.

**The plan (no engine build):**

1. **A hidden page row `rando_version`** in `ingame.schema()`: one choice, `"2"`, default `"2"`, fixed, hidden, not
   in "Randomize everything", no command-line flag. Hidden rows are answered at their value
   (`ingame.page_answers`), so every answer text gains `"rando_version":"2"`, every run id changes, and a new game
   always makes a fresh folder. A restored old answer (Esc "Next New Game", round 71) gets the current value,
   because a value that does not fit its row falls back to the default. The next version that changes seeds sets
   the only choice to `"3"`.
2. **Old saves:** a save names its run in `slots/<save>.json`, and that folder is still there, so it loads the
   tables it was made with. Nothing is re-made. The owner's current game (`hoshido73-6ab5ad56`) is untouched.
3. **Share codes (round 74):** the code's layout is a hash of every share row's key and kind
   (docs/rando/FULL_BLOCK.md section 7). Adding `rando_version` changes the layout, so a code made before round 79 is
   refused with the existing sentence "This code was made by another version of the randomizer." The row has one
   choice, so it packs to 0 bits; a test vector for a one-choice row goes into `tests/rando_sharecode_vectors.json`
   (both codecs must accept width 0).
4. **`plan.json` and the spoiler** carry `"guarantees": {"version": 1, ...}` and `"rando_version": 2`.
   `rando.py check <folder>` on a folder without them says plainly "made by randomizer 1 (before round 79); this
   tool makes randomizer 2, so a remake would differ" and exits 3 (not a guard failure). No frozen copy of the old
   maker is kept (call 10).
5. **PLAY RANDOMIZED** mod folders (`Rando-<seed>`) carry the same block in `mod.json`'s `randomizer` entry.

**Round 74 status, said plainly.** Round 74 is not merged yet. Read for this plan: `docs/rando/FULL_SWAP_PLAN.md`
section 4 (in git) and `docs/rando/FULL_BLOCK.md` (an **untracked** working file in the main folder, read
2026-11-25 while round 74 was running; section 7 is the share code). Part G4 re-reads both after round 74 is merged and adjusts point 3
if the share code changed. If round 74's share code is cut, point 3 falls away and the rest stands.

**Re-baselining the fingerprints (needs your OK).** In the round's commit, after the gate shows only announced
changes:

- `config/release/seed_changes.json` = `{"round": 79, "changes": [...]}` listing all six keys
  (`fates/default/1`, `fates/everything-on/1`, `seal/default/1`, `seal/everything-on/1`, `ids/r62-page` (every page
  run id changes) and `fates/boss-classes/r63fboss1`), each with the reason "round 79 guarantees".
- **The guarded key `r63fboss1`** cannot be announced away (F-052): its patch and plan hashes are written in
  `tools/release/fingerprints.py` (`GUARDED`) and in docs/tests/STORY_BOSSES.md. Before changing them, the round
  shows a cell diff of the old and new patch: **every boss and enemy cell equal**, only player Person and player
  placement cells differ. With your yes, `GUARDED` and STORY_BOSSES.md get the new hashes and run id.
- Then `fingerprints.py update --round 79` rewrites the listed keys only.
- The round-62 schema copy (`tests/test_rando_page_r62_schema.json`) gains the row, and
  `tests/test_rando_page62b.py`'s "same answer, same run id" test changes its promise to "an old answer keeps its
  run folder; a new answer gets a version-2 run id".
- The smoke set re-makes its everything-on runs with today's code, so it follows by itself; F-052 makes FULL due
  (an announced seed change), so C2 runs it.

## 6. The backstop (the small after-check)

`guarantees.check` runs in `tracks.make_all` after every track that can change a class or a skill (slice 1, even
spread, promotions, skills, children), on the final rows. For each need it lists who covers it and whether a repair
was made. It is a cross guard (`guarantees: timing`): a miss fails the make, and the page shows its existing
"this seed failed a check" with Back / Play the original. A miss there is our bug, never a seed's bad luck.

It also writes the spoiler's **Guarantees** section (one line a need: "Revelation 7, healer: Felicia (Maid)",
"repaired: Felicia Bow Knight -> Strategist") and the paralogue lines as information. These numbers are what the
easy / fair / harsh label will read later.

## 7. Tests, and which robot data proves the timing

**Unit tests (host, made-up tables)**, in a new `tests/test_rando_guarantees.py`:

| Test | What |
|---|---|
| `test_met_seed_unchanged` | a made-up seed that already meets every need: tables byte-identical to slice 1 without the pass |
| `test_repair_one_person` | a need with no cover: exactly one pool person changes, with a role class; deterministic over 60 seeds |
| `test_never_kept_or_held` | Corrin, Azura, Gunter, royals, Nyx, Shura never repaired |
| `test_retainer_slot` | both retainers get the role together |
| `test_leaver_not_counted` | a person absent from a chapter's roll does not cover it |
| `test_earlier_need_kept` | a repair never takes away the only cover of an earlier need |
| `test_healer_holds_staff` | a repaired healer's join placement carries a usable staff |
| `test_never_stricter` | a made-up chapter where the original has no cover is not a need |
| `test_version_row` | the hidden row is answered, changes the run id, is not in "everything", has no flag; a restored old answer gets `"2"` |
| `test_check_refuses_v1_folder` | `rando.py check` exit 3 with the plain sentence |
| `test_keys_never_behind_doors` | chests on: no key placed anywhere |
| `test_seal_rules_block` | the Seal block equals what the made-up mod tables give |

**Real data (when the RomFS is there):** `guarantees.py facts` agrees with the table; 1,000 seeds with page defaults,
200 with "Randomize everything", 200 with the shuffle (within story and across stories): **0 misses** after the
pass; the number of seeds whose tables did not change is reported. `test_route_roles_kept` stays (the route rules
are still true).

**Robot data that proves the timing (already on disk, no new run):** round 72's break check, the `army` of every
randomizer-off job (`build/r72/check/jobs/*-off/result.json`; Birthright A007-A028, Conquest B007-B028, Revelation
C007-C028), read from memory on saves made by playing the story. That is where every army roll in section 2 comes
from, and G1's `facts` command re-reads it. Not covered: a female Corrin (no such save exists) and Seal of Flames
(its break check used a Fates save).

**New robot work in round 79 (small):**

- **P1, page and old save.** The page robot's existing scenario: the page shows no new row; the answer carries
  `rando_version`; the run id for `hoshido73` with round 73's settings differs from `hoshido73-6ab5ad56`; then a
  headless save load of a copy of a round-73 test save still lays its old run folder. All in the robot's own data
  folder, never the owner's.
- **P2, a repaired healer in a real game** (cut first). A seed where the pass repaired Felicia: new game through the
  existing recordings `bt-prologue` and `bt-ch2` to the Chapter 2 map (round 47's method, frame 5117), Felicia's
  class read from memory is the planned staff class and her inventory holds a staff.

## 8. What is not in round 79

- The easy / fair / harsh label (later, as the owner said; Grok: still worth it).
- A "no safety net" switch (only if the owner asks; call 8).
- Flier needs other than A010 and C011, mounted units, archers, "a unit that can hurt armour" (Grok: comfort, not a
  stuck map).
- A female-Corrin robot read (call 5's default covers it).
- docs/ROADMAP.md row 79 still says "seed doctor"; the round updates it (this desk session may only edit this file
  and the Grok file).

## 9. The parts, counted

Every part has a cap of its count plus half, rounded up to 5 min. All parts are estimates unless marked counted.

### Sitting 1: code and unit tests (no builds at all)

| # | Part | Time | Cap | Kind | Files |
|---|---|---|---|---|---|
| G1 | **Needs table:** `config/randomizer/guarantees.json` from section 2; `guarantees.py facts` (scripts kinds 9/10, round 72 armies); read `cq-ch6-clear`'s army for the Elise note (from an existing break-check job's base, else a one-save chapsel army read, headless) | 45 min | 1 h 10 | estimate | new json, new module |
| G2 | **The repair pass** (section 3) in `guarantees.py`; hooks in `randolib.make_plan` and `misc.assign_evenly`; the staff-in-hand rule | 1 h 15 | 1 h 55 | estimate | Python only |
| G2b | **No repeated class** in the repair draw (section 3, step 3), with a unit test: a made-up army where one role class is free and one is taken picks the free one, and one where all are taken still repairs | 15 min | 25 min | estimate | Python only |
| G3 | **Seal of Flames block** in `sources.build_seal_rules` + rebuilt `seal_rules.json` (ids only) | 40 min | 1 h 00 | estimate | Python + rules |
| G4 | **Version marker** (section 5): re-read FULL_BLOCK.md / FULL_SWAP_PLAN.md 4 after round 74 is merged; hidden row, `plan.json` / `mod.json` block, `rando.py check` refusal, share-code test vector | 40 min | 1 h 00 | estimate | Python + one test file |
| G5 | **Backstop** cross guard and the spoiler section in `tracks.make_all` | 30 min | 45 min | estimate | Python only |
| G6 | **Tests** of section 7 (unit + real data: 1,000 + 200 + 200 seeds); update `test_route_roles_kept` wording, the r62 schema copy, `test_rando_page62b` | 1 h 15 | 1 h 55 | estimate | tests |
| G7 | Gate: `run_tests.py --core` + `fingerprints.py check` (all six keys changed and listed) | 5 min | 10 min | counted (round 71: 158 s + 24 s) | none |

### Sitting 2: proofs, checks, report

| # | Part | Time | Cap | Kind | Builds |
|---|---|---|---|---|---|
| F1 | **Fingerprints** (after your OK): the r63fboss1 boss-cell diff, `GUARDED` + STORY_BOSSES.md, `seed_changes.json`, `update --round 79` | 20 min | 30 min | estimate (the fingerprint run itself: counted 24 s, round 71) | none |
| P1 | Page robot + old-save load (section 7) | 30 min | 45 min | estimate | none |
| P2 | Repaired healer in a real game to Chapter 2 (cut first) | 35 min | 55 min | counted (round 47: 3 jobs on these recordings, about 30 min) + 5 min | none |
| C1 | CORE: `run_tests.py --core`, `check_all.py --core --jobs 4`, `smoke.py run` (8/8) | 15 min | 25 min | counted (round 71: 158 + 82 + 110 s) | none |
| C2 | FULL: `run_tests.py --full` (due: an announced seed change, F-052) | 15 min | 25 min | counted (round 71: 233 s) | none |
| R | Report and docs (RANDOMIZER.md section 3, ROADMAP row 79, DECISIONS) | 30 min | 45 min | counted (roadmap) | none |

### Totals

| | Time |
|---|---|
| Sitting 1 | 5 h 25 |
| Sitting 2 | 2 h 25 |
| **Counted total** | **7 h 50** |
| By round 71's real speed (code at 23 % of its count, proofs 71 %, checks 25 %) | about 2 h 45 (320 x 0.23 + 65 x 0.71 + 55 x 0.25 + report 30 = 164 min), **not** assumed: this round's code is new logic with real-data tests, not wiring |

**Hard stop:** 1.5 times each sitting's count: **8 h 10** for sitting 1 and **3 h 40** for sitting 2. At a cap, the
part stops, is written up as far as it got, and the cut order below decides what goes.

### Cut order (if a sitting runs past its count)

1. **P2**, the repaired healer in a real game (35 min). The tables are already proven to lay (rounds 47 and 72);
   this only shows one more case.
2. **G3**, Seal of Flames (40 min). Seal then keeps today's per-route roles; the backstop reports its timing as
   information only.
3. **The staff-in-hand rule** inside G2 (20 min). A repaired healer could then join without a staff (the spoiler
   says so).
4. **The `rando.py check` sentence** inside G4 (10 min). An old folder then fails `check` as a plain guard failure.

With all four cut: **6 h 05** (7 h 50 minus 1 h 45).

**Space:** no builds. The robot proofs write under `build/r79/`, about 1 GB (estimate). Stop if D: falls below 30 GB
free.

## 10. Open calls (each with a default; silence = the default)

| # | Call | Default |
|---|---|---|
| 1 | Never stricter than the original game | **Yes.** Revelation's chest opener is needed by chapter 9, not 7 (the original has none for chapters 7-8). Grok agrees |
| 2 | When the healer is needed | **By chapter 7 on every story** (the first chapter after the split). Price: on Revelation the retainer always gets a staff class (section 2). The looser choice: by chapter 9 (Revelation then has Sakura in the roll too) |
| 3 | The healer must hold a staff when joining | **Yes** (Grok: "a staff user with no staff does not count") |
| 4 | Flier needs | **Only Birthright 10 and Revelation 11** (the known breaks). No other map is guaranteed a flier |
| 5 | Felicia / Jakob (which one stays depends on Corrin's sex, not known when the seed is made) | **Both must meet a need they cover** (one retainer slot). Alternative: one female-Corrin robot run first (not planned) |
| 6 | Nuzlocke | **One of each, as without Nuzlocke**, plus one help sentence. Alternative: two of each role under Nuzlocke |
| 7 | Paralogues | **Not needed-by chapters**; reported only |
| 8 | A "no safety net" switch | **Not built** (only if you ask later; Grok: if built, off by default) |
| 9 | Re-record every seed fingerprint, the guarded boss seed `r63fboss1` included | **Yes**, after the round shows every boss and enemy cell unchanged (section 5). **Needs your yes by name** |
| 10 | Old run folders and remakes | **No frozen copy of the old maker.** Old saves keep working (their folder is kept); `rando.py check` on an old folder says it was made before round 79 |
| 11 | Seal of Flames in round 79 | **Yes, door and healer**, from the placements [medium]; cut item 2 if the round runs long |
| 12 | The easy / fair / harsh label | **Later round**, reading the backstop's numbers (you said later; Grok: keep it) |
