# Round 74: the counted header (for your OK before any engine build)

Written in round 73b (2026-11-25, a desk round on your "keep building"; no build, no game run). Sources: the roadmap
(docs/ROADMAP.md row 74, build/roadmap/ROADMAP_PLAN_2026-11-24.md "Round 74"), docs/rando/FULL_SWAP_PLAN.md
(sections 1, 2 and 4, with this round's "Round 73b check" corrections), docs/RANDOMIZER_RECRUIT.md (sections 4-8),
docs/rando/RECRUIT_PRESENTATION.md, docs/rando/WIRE_56.md section 7, round 71's plan and real times
(docs/ROUND71_PLAN.md, docs/REPORT_2027-01-16.md). Grok's preset answer: docs/collab/ROUND74_PRESETS_GROK.md.
Nothing in this file has been built.

## In plain words

**What you will see after round 74.** Each item is shown to you as a picture to look at, unless it says otherwise.
Nothing counts until you say ok (F-037).

1. **A moved character shows their own face in talks.** In a recorded scene, the person standing in someone
   else's spot shows their own portrait and their own name plate.
2. **Their own name in the menus:** the unit list and the map window. In the Revelation and Conquest chapters that
   use the route copies of a person, this name follows too.
3. **Their own battle model** in a battle close-up. The small map figure comes from the same table cell.
4. **Their own name inside the dialogue lines.** Their voiced scene lines go quiet. The quiet part is checked in the
   robot's sound log, not in a picture: no voice clip of the old person plays while the line shows.
5. **A face they do not have** (a scene asks for a shocked face their picture set lacks) shows their normal face,
   never a blank. If no recorded scene asks for a missing face on any of 20 tried seeds, the report says
   "not reached".
6. **Two preset buttons, Light and Wild, and a Share code field** on the New Game page. These come with
   **no picture**, because the page draws only in a real window and the robot runs without one (as in rounds 71-72).
   The robot proves the values (press Light, then Wild; copy the code, paste it into a fresh page, every value
   equal). Please look once yourself.
7. **The Esc Randomizer window fits a short game window** (small fix, see code answer (e)): the "This run" list
   gets its own scroll bar, so Keep never falls off the bottom. No picture, for the same reason as item 6.

**What you will not see yet:** the full swap is **not offered on your New Game page** after round 74. The row
"How they look" stays fixed at "Keep the face" until round 75 has run the four trouble chapters (Revelation 8 and
13, Conquest 9 and 16). That is the F-046 rule in FULL_SWAP_PLAN.md section 3. Round 74 shows the full swap in the
robot's own test game only.

**How long:** counted **13 h 10** in two sittings: 8 h 05 code and unit tests, then 5 h 05 for builds, proofs,
checks and the report. Most parts are estimates written on the slow side. Round 71's plan counted 14 h 40; after
its cuts the report re-counted it at 8 h 45 (REPORT_2027-01-16), and it took about 2 h 30. By round 71's real
speed this round would take about 4 h, but round 74 is harder in four named
places (below), so the count stays the time box. Hard stop: 12 h 10 for sitting 1 and 7 h 40 for sitting 2.
If it runs long, things are cut in this order: the expression backstop (recommended: cut before the start), then
the share code, then the Seal of Flames proof leg, then the menu names in the route and chapter copies. With all
four cut: **9 h 45**.

**What needs your OK:**

- **One line from you, "Yes, start round 74", is the OK for every build listed in sitting 2:**
  - the game program, staged with `engine.py port --stage-only`;
  - at most one repair build;
  - boot-server, in its own target folder;
  - the capture library, only if `build.py` says STALE;
  - the cargo tests, in their own target folder. They may also run once in the gate, so a compile error shows up
    before the game build.
- **Backups first:** play\game exe, build-record, game-path.txt, boot-server and the capture library go to
  `build/backup/*.<date>-pre-r74`.
- **Install last:** `tools/release/install.py` installs, only after checks C1 and C2 pass. Your saves and Zakuro
  settings are never written.
- **The calls below all have defaults.** Silence means the default (F-051(4)).

## Your calls (silence = the default)

| # | Call | Default |
|---|---|---|
| 1 | The full swap on your page after round 74 | **No**: the row stays fixed until round 75's four chapters pass (F-046) |
| 2 | Preset contents (Grok, docs/collab/ROUND74_PRESETS_GROK.md) | **Light** = Randomizer on, every other row at its default (classes, growths, join stats on; royals keep class; face kept). **Wild** = Light + enemy classes, enemy weapons, Music "maps", "Who joins where" = within this story. **Both:** Chest and village items off, Recolour "Their own colour", Nuzlocke off, full swap off. A press first resets every row to its default, then sets these, and keeps the seed |
| 3 | Help lines | Light: "Different classes and growths. Enemies, chests, and the face stay." Wild: "Light, plus enemy classes and weapons, music, and who joins. Face stays." (Grok's line with "classes" added; Grok's own line left them out.) Share code: "Copy or paste this. The same code makes the same game." |
| 4 | The expression backstop hook | **Not built.** The code shows the case it was meant for cannot happen (code answer (c)) |
| 5 | If no free guest memory is found for the name buffers in A4's first 30 min | **Fall back to the "while the game loads" way** (FULL_SWAP_PLAN 2.2): message files are patched in the read. A file whose names grow past its stored size keeps its old names, and the report lists those files |
| 6 | Esc "Next New Game" + Keep keeps the seed of the game you are playing (code answer (e)) | **Keep as is.** To get a new seed, clear the seed box before Keep. The help line says so (one line, inside A9) |

## Settled by reading the code (round 73b; none of it robot-proved)

Confidence words: **high** = read in the code; **med** = strong evidence; **low** = to be tested.

**(a) Does any caller keep two `Mess::Get` results at once? Yes. [high]**
A scan of the local regenerated listing found these numbers:
- 838 functions call `Mess::Get` or `Mess::GetNoReplace`, at 1,593 call sites;
- 284 functions call it twice or more;
- in 36 places, the first result stays in a saved register across a second call and is used after it.

Two of those were read by hand. Both pass the two texts together to `castle::cut::DrawLowerShop` (0x00465994):
- `ProcFortune::Persistent`: calls at 0x001A0F18 and 0x001A0F24;
- `ProcMyRoom::CorePersistent`: calls at 0x0018C238 and 0x0018C244.

Support talks (`RelianceTalkSequence::Create`, 0x00219110 / 0x00219130 / 0x00219150) also make several calls, and
they hold names. So the game's one shared message buffer (0x006DCBDC +4) is **not** safe for our changed text. The
hook needs its own ring of buffers in guest memory. Finding that memory is the named risk (call 5).

The hook place itself is settled. All three return paths of `Mess::Get` pass 0x003D1DA8 (`add sp, sp, #80`) with
the text in r0. They come from 0x003D1D18 (label not found), 0x003D1D90 (plain text) and 0x003D1DA4 (built text).
Round 71's svc trap (patch 0031, `fates_rando_chests.rs`) is the same kind of hook, so FULL_SWAP_PLAN 2.2's "no
function-entry hook exists yet" was out of date.

**(b) Which parts of the full swap exist already? [high for the code]**

| Part | Python | Engine | Laid in a real game / proven |
|---|---|---|---|
| P1 faces | `recruit.py` `build_edits` (about line 532) writes a FaceData record into plan.json only (`laid_by: engine`). No cell is made from it | The core has a resident FaceData file kind since round 59 (`fates_rando.rs` `Kind::Face`, `resident_start`, `apply_gamedata`). It takes plain and label-pointer cells, but only plain cells (the recolour's hair colour at +0x1C) were ever laid | no / no |
| P2 menu names, P3 battle model | Made as Person cells when look = full (`recruit_full_cells`: aid, mpid_name, mpid_help, body_type, voice), for the main row and the route (HANDOVER) rows. The **285 chapter copies are not edited** | Main GameData row: label pointers are laid today (`apply_file`). Person files: label pointers are **kept original** (`fates_rando_session.rs` `make_placement`, about line 772: "label pointers are laid only in placement files"), and `ingame.py` `file_entries` (about line 515) refuses them | no: the page keeps the look row fixed (`ingame.py` line 109) / no |
| P4 names in dialogue, voices quiet | nothing | nothing (only the trap kind exists) | no / no |

New in round 74: A1 to A5 below. Nothing of P1-P4 has ever been proven.

**(c) Is the R9 missing-expression rule still true as written? Yes for the rule, but one step of the reasoning was
wrong. [high for the code]**
`FaceInstance::ReadNowExpression` (0x001B003C) frees the texture slot (`FileBase::Free`, called at 0x001B0060)
*before* it checks whether the asked face exists. `FileBase::Free` (0x0011CF84) always stores 0 into the slot
(0x0011D064). So the branch "keep the face already on screen" (0x001B00EC) is never taken: **a missing face always
shows the normal face**, as long as the face package has its normal-face file.

What follows:
- R9 (b), "the normal-face file exists", is the check that matters.
- The backstop hook has nothing left to fix (call 4).
- Today `recruit.py` `run_guards` (`R9_full_face_exists`, about line 708) checks only that the person has a face
  id. R9 (a)-(c) are new work in A2.

**(d) Presets and share code against today's page. [high]**
- Since round 70, two rows are new: "Chest and village items" (`chests`, default off) and "Recolour" (`recolour`,
  default on). Both carry `omit_default`.
- Grok: chests in neither preset, Recolour at its default in both. That is call 2.
- Light as written equals "Randomizer on, every other row at its default".
- The share code must also carry the **13 number rows** (8 shown, 5 hidden), packed as value minus min, because
  they have no choice index.
- Rows with `omit_default` go into the code at their value. The decoded answer leaves them out at their default,
  as `answers_with_seed` does today (`rando_page.rs` about line 463), so the same code gives the same run id.
- Honest length: about 30 characters for the rows, plus the seed (up to 32 characters), the version, the game and
  a 2-character check. With a long seed the code is about 70 characters.
- Written into FULL_SWAP_PLAN section 4 as a "Round 73b check" paragraph.

**(e) Two open items from rounds 71-72. [high for the seed, med for the window]**
- *Esc "Next New Game" + Keep with no seed typed:* **it keeps the current game's seed.**
  1. At Start game with an empty seed box, the page puts the proposed seed into the form (`rando_page.rs` about
     line 1168).
  2. `answered` then writes those values, seed included, to `rando/last.json` (about line 1001).
  3. The Esc draft is a copy of that form (`draw_this_run`, about line 1270), so its seed box already shows the
     current seed.
  4. Keep (`keep_next_in`, about line 1239) writes it again.

  The next New Game page (`poll`, about line 804) restores it. The New Game page from the title did the same even
  before round 71.
- *Can the Esc window cut off Keep?* **Yes, in a short window. [med]**
  - Only the "Next New Game" rows have a scroll bar: `ScrollArea`, max height 35% of the window, at least 100
    points (about line 1312).
  - The "This run" list above it has no scroll bar and gets one line per changed setting. "Randomize everything"
    changes 22 shown rows.
  - The window itself (`egui::Window` "rando this run", about line 1276) has no scroll bar.
  - At 800x480 the parts add up to roughly 750 points of height, so the bottom, with Keep, is cut off.

  Fix A9 puts the "This run" list in its own capped scroll area.

## The parts, counted

"Counted" = a time measured before (the round is named). "Estimate" = never measured, written on the slow side.
Every part has a cap of its count plus half, rounded up to 5 min.

### Sitting 1: code and unit tests (no build, no game run): 8 h 05

| # | Part | Time | Cap | Kind | Patch / files |
|---|---|---|---|---|---|
| A1 | **Faces and copies (Python).** `ingame.make_patch` turns each FaceData record into cells of `face/FaceData.bin.lz`: the fields that differ between A's and B's records (package name, hair, colour, expression layout, name-plate MPID), with labels from that file's own pool. `recruit.py` adds `aid`, `mpid_name` and `mpid_help` of the 285 chapter copies for look = full. Tests on made-up tables | 1 h 00 | 1 h 30 | estimate | Python only |
| A2 | **R9 (a)(b)(c)** in `recruit.py`: face record exists, normal-face file in B's package (owner's files via the asset reader, at make time), spoiler list of missing faces; tests on made-up packages | 30 min | 45 min | estimate (FULL_SWAP 1.3) | Python only |
| A3 | **Label pointers in person files (core):** a `GameData/Person/**` file with pointer cells is laid in memory after the game stores it, the way placement files are (`make_placement`); `ingame.py` lets Person files carry pointer cells (map settings still refuse); tests | 45 min | 1 h 10 | estimate | new `0034-core-...-person-file-label-pointers.patch` |
| A4 | **The `Mess::Get` trap (core):** svc trap at 0x003D1DA8; a ring of buffers in guest memory (the first 30 min look for a free region, else call 5); one pass per text: commands untouched, voice commands of silenced keys dropped, whole-word names, `full_off_chapters` (empty in round 74), fast path when the run has no `full` block; tests on made-up lines | 2 h 00 | 3 h 00 | estimate (names 1 h 30 + voice 30, FULL_SWAP 2.4) | new `0035-core-...-names-and-voices-in-messages.patch` |
| A5 | **The `full` block (Python):** names per text language from both people's message labels, the silence list (voice key from FaceData +0x08), faces, `full_off_chapters`; written only when look = full, so every existing seed fingerprint stays the same (R8). One Grok consult on joined names and nicknames (5 min, inside) | 45 min | 1 h 10 | estimate | Python only |
| A6 | **Presets and share code:** schema `presets`, Python twin codec and a shared test-vector file under tests/ (1 h 05); page buttons in Basics, the share field with Copy / Paste, Rust codec, `pagebot.rs` targets `btn:preset:<name>` and `row:share` (45 min) | 1 h 50 | 2 h 45 | estimate (FULL_SWAP 4) | new `0036-page-...-presets-and-share-code.patch` |
| A7 | **The robot's way to lay look = full** while your page keeps the row fixed: a test-only switch read only in the robot's own data folder | 15 min | 25 min | estimate | Python (+ page test) |
| A8 | **Expression backstop hook:** recommended cut before start (call 4) | 40 min | 1 h 00 | estimate | would join 0035 |
| A9 | **Esc window fits** a short window: "This run" list in a capped scroll area; the one help line of call 6; one test | 15 min | 25 min | estimate | joins 0036 |
| G | Gate: `run_tests.py --core` + seed fingerprints (every seed unchanged; look = full is in no fingerprinted seed) | 5 min | 10 min | counted (round 71: 158 s + 24 s) | none |

Sitting 1: 60 + 30 + 45 + 120 + 45 + 110 + 15 + 40 + 15 + 5 = **485 min = 8 h 05**.
If a fingerprint changes, sitting 1 stops there and says which seed.

### Sitting 2: backups, builds, proofs, checks, report: 5 h 05

| # | Part | Time | Cap | Kind | Builds |
|---|---|---|---|---|---|
| B0 | build/STOP_ROUND absent; D: free measured (stop below 30 GB free after the need below); backups to `build/backup/*.<date>-pre-r74` | 5 min | 10 min | counted (rounds 59-62, 71) | none |
| B1 | `engine.py port --stage-only` with 0034-0036 (0037 only if A8 is kept), staged with `install.stage_build("r74", ...)` | 30 min | 45 min | counted (round 71: build phase 10 min in all, exe 86.7 s) | **game exe (staged)** |
| B2 | At most one repair build, only if B1 or a proof fails on our code; more likely than in round 71 (a trap in a hot function) | 45 min | 1 h 10 | counted allowance (roadmap) | game exe again, at most once |
| B3 | boot-server (own target, `build.py --server --stage-to`), the capture library only if `build.py` says STALE (expected FRESH: no menu or capture file changes), cargo tests in their own target folder | 15 min | 25 min | counted (round 71: boot-server 76.7 s, 7 cargo rows) | **boot-server**, capture library if stale |
| P1 | **Faces, menu names, model** (robot, headless, existing recordings only): a recorded scene with a swapped speaker (portrait + name plate), the unit list, one battle close-up; on Revelation (a route-copy chapter) and Seal of Flames; off = original on the same presses | 1 h 00 | 1 h 30 | estimate | none |
| P2 | **Dialogue names and quiet voices:** a recorded line names B (picture); the robot's sound log shows no `VOICE_<A's key>_EVT` clip while it shows | 40 min | 1 h 00 | estimate | none |
| P3 | **Missing face:** the earliest recorded scene from A2's spoiler list, up to 20 seeds tried on the host; two pictures or "not reached" | 20 min | 30 min | estimate (FULL_SWAP 1.4) | none |
| P4 | **Presets and share code** by the page robot (values, no picture); the Esc window's targets at 800x480 with "This run" full (Keep reachable) | 20 min | 30 min | estimate (FULL_SWAP 4) | none |
| C1 | CORE: `run_tests.py --core`, `check_all.py --core --jobs 4`, `smoke.py run --bin` on the staged exe (8/8, randomizer-off memory equal) | 15 min | 25 min | counted (round 71: 158 + 82 + 110 s) | none |
| C2 | **FULL place:** `run_tests.py --full` on the staged exe (an engine patch makes FULL due, F-052). The F-051 full matrix with the full swap on is round 76 | 15 min | 25 min | counted (round 71: 233 s) | none |
| C3 | Install with `tools/release/install.py` after C1 and C2 pass (automatic rollback), memory compare of the installed exe | 10 min | 15 min | counted (round 71 C3) | none |
| R | Report with the pictures, the sound-log lines and the undo steps | 30 min | 45 min | counted (roadmap) | none |

Sitting 2: 5 + 30 + 45 + 15 + 60 + 40 + 20 + 20 + 15 + 15 + 10 + 30 = **305 min = 5 h 05**.

### Totals

| | Time |
|---|---|
| Sitting 1 | 8 h 05 |
| Sitting 2 | 5 h 05 |
| **Counted total** (B2 included, as the slow side) | **13 h 10** |
| Without the repair build | 12 h 25 |
| With the backstop cut before start (call 4) | 12 h 30 (11 h 45 without B2) |
| By round 71's real speed (code at 23% of its count, builds 9%, proofs 71%, checks 25%) | about 4 h 00 (485 x 0.23 + 95 x 0.09 + 140 x 0.71 + 70 x 0.25 = 237 min), **not** assumed (see below) |

**Hard stop:** 1.5 times each sitting's count: **12 h 10** for sitting 1 and **7 h 40** for sitting 2. At a cap, the
part stops and the report says what is left.

**Where round 74 is harder than round 71:**
1. **A new hook place.** Round 71's trap sat at the entry of a function the game calls rarely and needed no guest
   memory. This one sits inside `Mess::Get`, which about 1,600 places call, and it needs a buffer ring in guest
   memory.
2. **Faces were never laid.** FaceData label pointers have never been written. Whether a face instance copies its
   record when it is made (and so would miss a later change) is not known [low]. The cells are laid at New Game,
   before any scene, so this is expected to be fine.
3. **The proofs are pictures of scenes and a sound log, not memory reads.** Round 71's chest proof read memory
   (judge_chest). So the proofs are counted at their full estimate, not at round 71's 71%.
4. **Pointers in person files laid in memory are a new path.** Round 58 found placement pointers wrong when they
   were laid in the read. That is why A3 lays them after the game stores the file.

### Cut order (if a sitting runs past its count)

1. **The expression backstop** (A8, 40 min). Recommended: cut before the start (call 4).
2. **The share code** (about 1 h 10 of A6 + 10 min of P4 = 1 h 20). The preset buttons stay.
3. **The Seal of Flames proof leg** of P1/P2 (20 min). It moves to round 76's full check.
4. **Menu names in the route and chapter copies** (A3 45 min + A1's chapter-copy part 20 min = 1 h 05). The main
   unit list and the faces still follow. In the route-copy chapters (Revelation 9 and 13, Conquest 9) and in
   the chapter copies, menu names stay the old person's until round 75. Patch 0034 is then not made.
   (Not a typo: the trouble chapters are Revelation 8 and 13, but the route copies sit in Revelation 9's files;
   Revelation 9's PID_C_ placements are what break Revelation 8.)

With all four cut: **9 h 45** (13 h 10 minus 3 h 25: 40 + 80 + 20 + 65 min).

## Not in round 74 (on purpose)

- **The four trouble chapters** with the full swap (Revelation 8 and 13, Conquest 9 and 16): round 75, which also
  decides whether the full swap is offered on your page (call 1). No cheat pokes in round 74 (they are OK'd for
  rounds 72 and 75 only).
- **The F-051 full matrix with the full swap on:** round 76.
- **Movies, My Room and castle lines** stay the old person's. The page help already says so.
- **Chest and village items in "Randomize everything"** wait for your call (report 16, item 6).
- **Port mode and the download:** not here (round 77, and only after 3dsrecomp's author answers).
- No push, no release tag, no delete, no download.

## New patch numbers

The series is **0001-0033** today (`patches/zakuro/`: 33 patches plus NOTICE.md and README.md; 0031 chests, 0032
page, 0033 growths). Round 74 adds **0034** (core: label pointers in person files), **0035** (core: names and voices
in `Mess::Get`), **0036** (page: presets, share code, Esc window fit). There is **0037** only if the backstop is
kept. The numbers are fixed in the order the patches are made.

## Where the tests run

- Sitting 1's gate G: CORE unit tests and fingerprints, no game.
- C1: CORE + check_all core + smoke on the **staged** exe.
- C2: **FULL** (`run_tests.py --full`) on the staged exe, inside round 74, because engine patches make FULL due
  (F-052).
- The F-051 full matrix (every chapter, all settings) with the full swap on: **round 76**. The four trouble
  chapters: **round 75**.

## Disk

| Need | Size | Kind |
|---|---|---|
| Engine build output (port build objects and staged exe) | up to 4 GB | estimate (round 71) |
| Backups (exe, boot-server, capture library) | about 1 GB | estimate |
| Robot proofs (scene pictures, sound logs, 20-seed face search) | about 3 GB | estimate |
| **Total** | **about 8 GB** | estimate |

D: had **83 GB free** at 03:24 on 2026-11-25 (measured by Claude in round 73b), so about 75 GB would stay free.
Stop rule: B0 measures again, and the round stops if D: would fall below 30 GB free.

## Hard rules in round 74 (as in every round)

- build/STOP_ROUND is checked before every game or robot start.
- Every start is headless and exits by itself, with its data folder and APPDATA/LOCALAPPDATA under build/.
- At most 6 robot jobs at once. A run is never relaunched more than once. A visible window counts as a failed run.
- play\game\Fire Emblem Fates.exe is never started.
- No Nintendo or Seal of Flames bytes go into git. Names and face labels stay in the run folder only.
- Your saves, Zakuro settings, cheats and mods are never touched.
- Every process started is listed and killed before the round returns.
