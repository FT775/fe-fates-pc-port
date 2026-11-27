# The full swap and the smaller page wishes: desk plan (round 70, track swap)

**For the owner, in plain words.** This page decides, before any engine build, how the rest of the full swap
and the small page wishes will be built. Nothing here changes the game.

- **A missing face expression** (a scene asks the new person for a face their picture set does not have): the
  game already handles it. Our read of its code shows it looks for the asked face, and if the file is missing it
  shows the person's normal face instead, or keeps the face already on screen. So the full swap needs **no**
  painted portraits and no picture files. A check before every seed makes sure each new person has a normal
  face. A small backstop hook is designed in case a robot picture shows something wrong.
- **Voices:** the swapped person's spoken scene lines go quiet. That is done in the same place that puts their
  name into the dialogue, so it rides in round 74's engine batch. Battle voices follow the new person.
- **The four trouble chapters** (Revelation 8 and 13, Conquest 9 and 16): if the full swap breaks one of them,
  either only the dialogue names stay old in that chapter, or the full swap stays off for the whole game. The
  page then says so in plain words. Nyx and Shura stay in their own spots either way.
- **Presets and a share code** come in **round 74** (2 h 10, an estimate). Grok's preset names: **Light** and **Wild**.
  The share code gets its own field with Copy and Paste, not the seed box.
- **Growths in Preparations:** on the **Y button** (keyboard: Zakuro's Y key, A by default). No Preparations
  menu of the game reads Y. Select and Tab stay the growth key on the battle map.
- **Esc menu, next New Game:** the same rows as the New Game page, under "This run". They are kept in the file
  the page already uses, and they never change the game you are playing. **The long help text** becomes one
  short line in a help area of fixed height, so the buttons never jump. Both are in round 71's batch.

Status 2026-11-24 (round 70, desk work only). No build, no game or robot run, no file written outside docs/ and
build/r70/swap/. Inputs: docs/RANDOMIZER_RECRUIT.md (sections 4-8, guard R9), docs/rando/RECRUIT_PRESENTATION.md,
docs/rando/WIRE_56.md section 7 (E3/E4), docs/ROADMAP.md, build/roadmap/ROADMAP_PLAN_2026-11-24.md, the engine
source (read only: `engine/zakuro/crates/zakuro/src/rando_page.rs`, `menus.rs`, `lib.rs`,
`crates/zakuro-core/src/fates_growth_view.rs`, `fates_rando_file.rs`) and the game's code, read in the local
regenerated `asm/` listing (gitignored, made from the owner's own code.bin). Only addresses, function names and
our own conclusions are written here. No game bytes or text are copied. Confidence: **[high]** read in code,
**[med]** strong evidence, **[low]** to be tested. Grok's answers: docs/collab/FULL_SWAP_R70_GROK.md (kept copy of
build/r70/swap/GROK_A_swap.out.txt and GROK_A2_swap.out.txt).

## 1. The missing-expression rule (guard R9)

### 1.1 What the game does today [high for the code, low for what it looks like]

A scene asks for an expression with `$E<name>,|`. `TcdiExpression::Dispose` (0x001D5770) reads the token and
calls `FaceInstance::ChangeExpression` (0x001AFA5C) or `FaceInstance::SetExpression` (0x001AF11C). The name goes
to the face instance at +324 (`FaceInstance::SetExpressionName` 0x001B0140: `strncpy(+324, name, 32)`). The picture
is then loaded by `FaceInstance::ReadNowExpression` (0x001B003C):

1. it builds `"<name>.bch.lz"` (format string at 0x00611E08) into the buffer at 0x00704FD4;
2. `PackageFile::IsExist(package, that name)`: if the face package has the file, it is read
   (`TexFile::ReadPackage`);
3. **if not**, and the texture slot already holds a picture (`[tex+4] != 0`), nothing changes: **the face on screen
   stays**;
4. **if not**, and the slot is empty, it builds the name from the default label at 0x006BDB98 (it points at
   0x006A6E44, the cp932 label for "normal") and reads that: **the normal face**.

So a missing expression already falls back cleanly in the game's own code: the face stays as it was, or it
shows the normal face. It never goes blank or stops, provided the package has a normal face. RECRUIT_PRESENTATION.md
section 4 marked this as "not known". This read answers it on paper. A robot picture must still confirm it
(section 1.4).

**Round 73b check (2026-11-25, desk read of the same listing; [high] for the code, not robot-proved).** Step 3
above cannot happen. `FaceInstance::ReadNowExpression` calls `FileBase::Free` on the texture slot at 0x001B0060,
**before** the `PackageFile::IsExist` test at 0x001B00C0, and `FileBase::Free` (0x0011CF84) always ends by storing
0 into the slot's +4 word (0x0011D064). So at 0x001B00EC `[tex+4]` is always 0 and the branch to "keep the face on
screen" is never taken: **a missing expression always shows the normal face** (step 4), provided the package has
the normal-face file. Two more details from the same read: the function does nothing at all while the face
package is still loading (`FileBase::IsDone` test at 0x001B0050); and when the face instance's flag word at +364
has both bit 0x400 and bit 0x2 set, the asked name is first decorated by a short prefix format (snprintf at
0x001B0088), so the existence test looks for the decorated name while the fallback reads the plain normal label
at 0x006BDB98. Consequences: the backstop hook in 1.2 has no case left to fix (a held odd face cannot occur), so
round 74 leaves it unbuilt by default and it stays first in the cut order; R9 (b) (the normal-face file exists)
is the one check that matters. Today `tools/randomizer/recruit.py` `run_guards` (the `R9_full_face_exists`
lines, about line 708) checks only that the filler has a face id; R9 (a)-(c) as written in 1.2 are not built.

### 1.2 The rule

- **Fallback through the game's own path, no files.** With P1 (A's FaceData records point at B's package),
  every expression A's scenes ask for is looked up in **B's** package. Missing ones show B's current or normal
  face (1.1). No portrait file is painted, copied or written. The "file way" of the old portrait look is
  dropped for good (the roadmap's stop list already has "painting portraits").
- **R9 at plan time (Python, recruit.py, no engine).** For "full" only, for every swapped spot A -> B:
  (a) B's FaceData record exists; (b) **B's package has the normal-face file**. Without it the fallback in 1.1
  step 4 would find nothing. If either fails, the seed is refused with a plain message, as R1-R8 do. (c) For
  the spoiler only, list the expressions A's scenes ask for that B lacks ("Kaze in Jakob's spot: 2 scene faces
  show his normal face"). The package file list comes from the owner's own files through the existing asset
  reader (docs/ASSETS.md section 4) at make time. Nothing is committed, only counts and labels in the run folder.
- **Backstop hook, only if the robot picture shows a wrong face.** That would be the "keeps the face already on
  screen" case looking odd, for example a shocked face held through a calm line. The fix is then one host hook at
  `FaceInstance::SetExpressionName` (0x001B0140), the only writer of +324. For a swapped FaceData, a name B's
  package lacks is replaced with the normal-face label before it is stored, so step 4's path is always taken.
  It needs no files and changes no memory outside the instance's own name field. It rides in round 74's message
  hook batch, because it is the same kind of hook (section 2.2). Default: **not built** unless the round-74
  picture asks for it.

### 1.3 What it costs

- R9 (a)(b)(c) in `tools/randomizer/recruit.py` with unit tests on made-up packages: 30 min (estimate),
  round 74.
- The backstop hook, if needed: 40 min (estimate), round 74. It is the first item to cut in that round.

### 1.4 Proof (round 74)

A recorded scene where a swapped speaker is asked for an expression B lacks. The plan's spoiler names one, and
the robot picks the earliest recorded scene from that list. Two pictures, SEEN: the face is B's (normal or held),
not blank and not A's. If no recorded scene has a missing expression for any seed the robot tries (it tries up
to 20 unpicked seeds on the host), the report says "not reached" and the backstop stays unbuilt.

## 2. Voice silencing in the message hook (rides in round 74)

### 2.1 Where names and voices are in the text [high]

A scene line is message text. The speaker is set by a command naming A (`$Ws<name>|`), the face by
`$Wm<name>|<pos>|`, and a spoken line by `$Svp` followed by `VOICE_<KEY>_EVT_nn` and `|`, where KEY is A's voice
key (RECRUIT_PRESENTATION.md section 1). Clip numbers mean different lines for different people, so a voice is
**removed, never remapped**.

### 2.2 The hook (one place for names and voices)

WIRE_56.md section 7 (E4) puts the names-in-dialogue hook on `Mess::Get` (0x003D1CEC). This round's read of
`Mess::Get` adds what the hook must respect [high]:

- `Mess::Get` finds the label in the message hash (`*0x006DCB44`, `IdentHash::GetIdent`). For a plain message it
  returns **a pointer into the loaded message file itself**. For a message with arguments (text starting `$a`)
  or with a prefix entry, it builds the text in the game's own message buffer (`0x006DCBDC`: +4 the buffer, +8
  its size; `Mess::GetBufferSize` 0x003D1974) and returns that. `Mess::GetNoReplace` (0x003D16CC) is the same
  without argument filling.
- So the changed text cannot be written over the file's own text (lengths change). It goes into a buffer: the
  game's message buffer (what `Mess::Get` already returns for argument messages, so callers accept it), as long
  as the new text plus its end mark fits the size at +8. A line that does not fit is left unchanged and logged.
- **Round 74's first check:** that no caller keeps two `Mess::Get` results at once (for example a name plate
  and a line). If one does, the hook uses its own small ring of buffers in guest memory instead. Finding a free
  region for it is then a named round-74 risk [low].
- **No function-entry hook exists in our Zakuro yet.** Today's hooks are after-frame, system call and the RomFS
  read. Round 74 adds the hook kind and counts it there. The alternative with no new hook kind is the roadmap
  draft's "while the game loads": message archives patched in the RomFS read, like the 0016 file kinds. Every
  patched file must still fit its stored size (fates_rando_file.rs step 5), so a file whose names grow too
  much would be served unchanged, with old names in that file. Pick: **the `Mess::Get` hook**. It works on
  only the lines actually shown, has no stored-size limit, and the voice pass sits in the same function. The
  read-path way is the fallback if the hook kind cannot be built in round 74.

**Round 73b check (2026-11-25, desk read; not robot-proved).**
- **The first check is answered: yes, callers keep two `Mess::Get` results at once [high].** A scan of the local
  listing (838 functions call `Mess::Get` or `Mess::GetNoReplace`, 1,593 call sites, 284 functions call it twice
  or more) found 36 places where the first result is kept in a saved register across a second call and used
  after it. Two were read by hand: `ProcFortune::Persistent` (calls at 0x001A0F18 and 0x001A0F24, then
  `castle::cut::DrawLowerShop` 0x00465994 gets both, r1 = the first) and `ProcMyRoom::CorePersistent` (0x0018C238
  and 0x0018C244, the same callee). Support talks (`RelianceTalkSequence::Create`, three calls at 0x00219110,
  0x00219130, 0x00219150) are among the multi-call functions and hold names. So **one shared return buffer is not
  safe**: the hook needs its own ring of buffers, and finding a guest memory region for it is round 74's named
  risk [low]. Whether any text pointer is held across frames (not just inside one function) is not known; talk
  lines go through `TalkCodeFactory::AddMess` (0x001E75A4) and `TalkExpander::ExpandMessage` (0x001C009C), which
  look like they parse the text at once [low].
- **"No function-entry hook exists in our Zakuro yet" is out of date.** Round 71's patch 0031 added a code trap
  (`crates/zakuro-core/src/fates_rando_chests.rs`: the first word of `ItemGain` 0x003B0768 replaced by the reserved
  `svc 0xFEC001`, the recompiled code re-checked so the interpreter runs that function, the host doing the replaced
  instruction). The same kind fits `Mess::Get`: all three of its return paths pass 0x003D1DA8 (`add sp, sp, #80`)
  with the text in r0 (the not-found path branches there from 0x003D1D18, the plain path from 0x003D1D90, the
  buffer paths fall into it from 0x003D1DA4). One trap there sees every result; the host points r0 at a ring buffer
  and does the `add` itself. The new part is only that it sits mid-function in a function called about 1,600 places
  (speed is a check, not a known cost).

**One pass, in this order, on the text `Mess::Get` returns (host side, from the run's plan):**

1. Split the text into commands (`$` up to the closing `|`) and plain text. **Commands are never touched by the
   name swap.** `$Ws` and `$Wm` name A on purpose: P1 already makes A's face show B, and the story needs A's label.
2. **Voice:** drop every `$Svp` command whose label starts with `VOICE_<KEY>_` for a KEY in the run's
   `silence` list. That list holds the voice key of every swapped spot A whose filler is not A, taken from A's
   FaceData record (+0x08) at plan time. Only play commands are dropped. A stop or fade command for the same
   clip is harmless with nothing playing. The Japanese voice option uses the same keys, so it gets the same
   treatment.
3. **Names:** whole-word replacement in the plain text with the permutation, all at once (A -> B and B -> C in
   one pass, never chained). Names joined to other words, possessives and nicknames are Grok's round-74
   question (ROADMAP_PLAN round 74).
4. Nothing changes when the run has no "full" look, when the chapter is on the run's `full_off_chapters` list
   (section 3), or when the text holds no swapped name and no silenced key. Fast path: the hook returns at once
   when the plan has no `names` and no `silence` list. That means randomizer off, keep the face, and every old
   seed.

**Battle voice** follows the filler through P3 (`aid` / asset row) with no text work [med]. **My Room** (Live2D)
and **castle lines** (CastlePerson by `PID_`) stay A's. The page help says so (docs/RANDOMIZER_RECRUIT.md section 5).

### 2.3 Plan data (Python, recruit.py, round 74)

The run's patch gets a `full` block, laid only by the engine, `laid_by: engine` as in RECRUIT_WIRE.md:
`names` (A's display name -> B's, from the message labels of both, per text language), `silence` (voice keys),
`faces` (for P1), `full_off_chapters` (section 3). The block is absent unless look = full, so every existing seed
fingerprint stays identical (R8).

### 2.4 What it costs (inside round 74's "about 8 h")

- Voice pass + tests on made-up lines (a speaker silenced, another kept, a command next to a name): 30 min
  (estimate) on top of the names hook.
- Proof: a recorded scene line with a swapped speaker. The sound log shows no `VOICE_<A's key>_EVT` clip while
  the line shows (the robot's sound log, as for music), and the line names B (picture, SEEN).

## 3. The four trouble chapters: the rule

The chapters are **Revelation 8** (two Hayatos in public tools), **Revelation 13** (invisible obstacles),
**Conquest 9** (the Nyx talk) and **Conquest 16** (the Shura spare prompt). In our chapter names they are
C008, C013, B009 and B016. Way A already closes two of the causes: one filler per spot (R3), and no script is
ever edited (R7). Nyx and Shura stay held (`recruit_hold`) whatever happens here.

**Rule (round 75 runs it; owner default "yes" for cheat pokes in rounds 72 and 75 covers C008 and B016):**

1. Each chapter runs with look = full and with look = keep, on the same seed and the same presses.
   C013 and B009 use recordings; C008 and B016 use the cheat track.
2. **Breaks with full but not with keep, and the break is in the dialogue** (a wrong or missing line, a voice
   cut that loses a prompt): the names and voice pass is turned off **in that chapter only**. The chapter goes
   on `recruit.full_off_chapters` in config/randomizer/rules.json. The plan copies the list into the run's `full`
   block, and the message hook passes text unchanged while that chapter is loaded. The core already learns the
   chapter from the chapter person file it serves (`Person::Load` 0x0044A808 builds `GameData/Person/<chapter>.bin.lz`;
   0016). The look row's help adds: "In Revelation 8 the dialogue keeps the old names."
3. **Breaks with full and the break is in faces, models or menu names** (P1-P3 are laid once for the whole game
   at New Game, so they cannot be switched off for one chapter): **"full" stays off everywhere**. The look row
   is fixed at "Keep the face" with the reason "Full swap breaks Conquest 16; it stays off until that is fixed".
   This uses the page's existing fixed-row mechanism (`PAGE_FIXED` / `PAGE_REASONS` in tools/randomizer/ingame.py),
   so it needs **no engine build**: a Python change of about 15 min plus a test.
4. **Breaks with keep too:** it is not a full-swap problem. It goes to the shuffle's own list (as Nyx and Shura
   did), and full follows keep.
5. **Not reached** (a recording or poke does not get there): not proven. Per F-046, "full" is offered on the
   page only when all four chapters passed or are listed under rule 2. Until then the row stays fixed with
   "Full swap waits for its chapter checks" (the reason wording already in ingame.py).

The rule needs no new engine work beyond the chapter check in the message hook: one comparison, part of
section 2.2's cost.

**Round 75 result (2026-11-25, robot on copies of the installed round-74 program, look = full only through A7's
test switch; F-060).** Each chapter ran with full and with keep on the same seed and the same presses.
- **Revelation 8 (C008), cheat track: PASS.** Seed r75c008a swaps three of its speakers (Saizo's spot = Azama,
  Orochi's = Scarlet, Kaze's = Jakob). Opening to the save question after STAGE COMPLETE (turn 1, boss Yukimura
  killed by `bosskill`), no fault, the same 150 lines per phase, every difference only the swapped portrait,
  plate or name, always agreeing (pictures SEEN; 46 of 150 lines identical by the pixel threshold, 43 by exact
  sha). Presses were in step up to the third battle; from the Yukimura battle on full was one poll (30 frames)
  ahead and keep needed one extra A in the ending (the drift below). No duplicate person (no "two Hayatos").
  Story wording about relationships stays (Jakob in Kaze's spot calls Azama in Saizo's spot "Brother"): expected
  full-swap behaviour, not a wrong line. The joined Kaze spot was not seen in a menu (the run ends at the save
  question).
- **Revelation 13 (C013), recording rv-ch13 plus a cheat end leg: NOT PROVEN (rule 5).** Every part reached
  passes: the opening scene (28 lines, same order, only names and portraits differ), turns 1-5 (Benny's face,
  name, class and map sprite; Sakura's rubble Grab and "Obstacle" equal; no invisible obstacle), and the closing
  scenes by `bosskill` (identical screen sequence). Turns 6-32 (the turn-17 dragon vein, the reinforcements, the
  moat crossing, any mid-chapter talk) were **not reached** under full: the recording leaves step at about frame
  43500 (and under keep at about 92000; it fits only the randomizer-off game). The voice silencing was not
  checked by sound here. One cosmetic case is put to the owner, not counted under rule 2: a stuttered name keeps
  the old first letter ("S-Hana" in full where keep has "S-Scarlet"); the line is there and the speaker right,
  it is a pattern of the names hook for the whole game, and switching one chapter off would not fix it.
- **Conquest 9 (B009), recording cq-ch9: NOT PROVEN for the whole chapter (rule 5).** The trouble point passes:
  the Nyx talk on turn 3 matches keep frame for frame and Nyx joins with her own PID, AID and MPID. OP2 names
  Jakob in Silas's spot; faces, menu names and battle models follow the person (SEEN); full equals keep at every
  checkpoint to frame 51600. Not reached: the OP4 scene (the swapped speaker's lines with 3 voice commands
  dropped; the recording skips it with Start in both looks) and turns 11-28 (seize, clear, ED). Keep itself leaves
  the original recording in the turn-10 enemy phase (support hit bonus; units differ from 49800): the shuffle's
  own replay matter, not the full swap.
- **Conquest 16 (B016), recording cq-ch16: PASS.** Seed r75b016a swaps five deployed people and two OP2 speakers.
  Both looks play all 21 turns: stage complete, the "Kill Shura?" prompt answered No (frames pixel-identical in
  both), the save menu (B017), the castle; Shura on the roster, Nyx and Shura in their own spots; 11 of 11
  recording checkpoints equal (screen, state, board), compared with the track's cmp.py (rcheck.judge_pair was not
  run: its shot records need fields these runs do not carry; cmp.py differs only by sorting the enemy pair list).
  Scope: recruit_class and recruit_stats at "slot" (the defaults would leave the recorded path). **Help-line
  correction:** the castle join scene before B016 showed the NEW person (Kaze's face and plate speaking Jakob's
  lines), so the planned help sentence must not say "castle lines keep the old person"; it should say movies and
  My Room keep the old person and castle join scenes show the new one.
- **Rules applied.** No rule-2 break (nothing goes on `recruit.full_off_chapters`, the list stays empty), no
  rule-3 break (faces, models and menu names follow the person everywhere they were seen), no rule-4 break. Rule 5
  holds for Revelation 13 and Conquest 9, so **the "How they look" row stays fixed** at "Keep the face" with the
  reason "Full swap waits: Revelation 13 and Conquest 9 not checked to the end" (ingame.py `LOOK_WAITS`, in
  `PAGE_FIXED` and `PAGE_REASONS`); it stays in `NOT_IN_EVERYTHING`. No page robot proof of the offered row was due.
- **The rv-ch9 drift (F-058) is found, not fixed.** Bisection on copies (same seed and presses, per-frame trace of
  the random generators) clears the names trap, the dropped voices, the face cells, the gender cells and file
  sizes; full minus the AID_ label pointers stays in step with keep for all 183000 frames. The AID_ pointer gives
  the swapped spot the filler's battle model and voice set; at the first hit on that unit (rv-ch9 frame 8244) the
  global generator 0x00752B7C makes one roll fewer, and a later random battle (about frame 16500) then plays out
  differently. That this roll comes from the sound or voice set is the likely way, not traced to the caller. It is
  the game's own behaviour with the filler's animation set, so a player sees no fault; only recordings made without
  the full swap stop fitting. C008 (30 frames from the third battle) and B009 (general random first differs at
  48750, a battle on the swapped Benny/Arthur spot) show the same kind. Not swapping AID would remove the full
  swap's battle look, so it is a design call, not a fix. **Round 76's matrix:** judge long full replays for
  dialogue, names, faces, menus and voices with the test-only "full minus AID" variant
  (build/r75/drift/tools/mkvariant.py noaid); judge the battle model and voice (AID) on short pieces from
  chapter-start saves through the first battle with a swapped unit; carry a per-frame generator trace against the
  keep twin (drift.py rng + rngcmp.py) and count anything after the first differing frame that depends on battle
  results as NOT REACHED; or use the cheat track for chapters whose story needs later turns. Revelation 13's
  turns 6-32 and Conquest 9's OP4 scene and end are the first jobs for that.
- **Missing faces (P3, R9 (c)):** not reached. No chapter run here reaches a place on its seed's
  `recruit.missing_faces` list (C008 cannot show one in this pool at all, by a host check of every possible filler).

**Round 76 result (2026-11-25, F-062; robot on copies of the installed round-74 program, boot-server b3ebe748 and
capture library 405f2bac sha-checked in every result; HEAD 1f266a4's randomizer; round 75's matrix: long replays with
the test-only "full minus AID" variant, AID on short pieces, a per-frame generator trace against the keep twin, and
anything after the first differing frame that depends on battle results NOT REACHED). Track full used no poke and no
chapter select; its seeds swap the people who speak but leave the spots whose people change battles unswapped.**
- **Revelation 13 (C013): PASS (rules 1-5).** Seed r76c13w30 (Hana's spot = Kagero and Oboro's = Orochi, both
  deployed; enemy speakers Peri = Selena, Laslow = Benny, Scarlet = Setsuna, Saizo = Azama, Kagero = Reina). The
  noaid long replay of rv-ch13 against keep, frames 0-232000: all 32 turns (the turn-17 vein, the reinforcements),
  stage complete, save, the C014 castle; no generator frame differs, boards equal at 464 of 464 checkpoints (and
  equal to round 75's randomizer-off run), final state equal, 0 faults, GameData 219 cells and the C013 person file
  12 cells with 0 wrong; 77 talk frames, the same lines in the same order. SEEN by the reviewer: Peri's quote as
  "I'm Selena..." with Selena's portrait, plate and battle model; Laslow's as Benny (portrait, plate, line); Orochi
  in Oboro's spot (level-up, forecast); Kagero in Hana's spot (unit page, Rally); ED3 with Setsuna's portrait and
  plate and "...Thank you, Setsuna." where keep says Scarlet. The voice is quieter only at Setsuna's ED3 lines (WAV
  level, robot). The AID piece (frames 0-80000) leaves keep's generator at frame 6690 (6709 global), so its battle
  results are NOT REACHED by rule, though boards stayed equal to frame 80000; Benny's battle model (78750) is robot,
  not opened by the reviewer. Not judged: battle quotes BT6-BT10 (Ryoma's side), which the recording does not show
  (gap). The first seed r76c13x109 left the recording at about frame 136000 in both looks: not counted.
- **Conquest 9 (B009): PASS (rules 1-5).** Seed r76b9b242 (Silas's spot = Jakob; Arthur, Odin, Niles and Effie stay).
  The noaid long replay of cq-ch9 against keep, frames 0-123500: all 28 turns, seize, ED, save, the B010 castle; no
  generator frame differs, boards 249 of 249, keep equals round 75's original-game run at 37 of 37 shared
  checkpoints, 0 faults, GameData 244 with 0 wrong. SEEN: Jakob's face, name and Cavalier unit page in Silas's spot
  with Silas's level, items and rating; "Felicia, Jakob, and Elise came to help me" where keep says Silas; the OP4
  scene with Jakob's portrait and plate on Silas's lines and Jakob in the sortie list (same lines, same order;
  voice quieter at Silas's lines, WAV, robot). In the OP4 talk job the generator first differs at frame 11988 inside
  the cutscene (the silenced voice; Elise's blink timing differs): boards equal, no battle judged after it,
  cosmetic. The AID piece (0-56000) equals keep, but no battle of the swapped Silas spot falls inside it, so the
  B009 AID battle look is a gap this round (round 75 saw it on its own seed).
- **Rules applied.** No rule-2 break (recruit.full_off_chapters stays empty), no rule-3 break, no rule-4 break, and
  with Revelation 8 and Conquest 16 PASS from round 75 no chapter is left under rule 5. **The page condition is met:
  "How they look" is offered on the Fire Emblem Fates page** with both choices ("Keep the face" stays the default and
  out of "Randomize everything"; recruit_look left PAGE_FIXED and PAGE_REASONS in tools/randomizer/ingame.py; the
  help line: "Full swap: a moved person comes as themselves (name, face, battle look), but movies and My Room keep
  the old person while castle join scenes show the new one."; no full_off chapter to name). The page robot (build/
  r76/integrate/pagebot/look-f, exe c49a0ab1) picked "Full swap" on the real page: the row took the value, the laid
  run r76look-21ab6036 carries full.txt, its patch.txt equals a fresh make, and patch.txt and full.txt are
  byte-identical to the same answer made through round 74's A7 switch with HEAD 1f266a4's ingame.py. Fingerprints
  unchanged (keep is the default; the help text is in no run id).
- **Seal of Flames: FAIL, the row stays grey there.** Track seal (seed r76s4, chapter select into R002 and R004, look
  = full through A7's switch, keep twin): scene portraits, names inside the lines, the unit list, unit page and map
  panel follow the new person (SEEN), the battle close-up is SEEN+poke (the head differs from keep; the forecast
  portrait is Kagero's), but **the scene name plate keeps the old Seal name** above the new face (for example the
  plate "Hiroki" above Drake's portrait while Corrin says "You're right, Drake."), in R002 and R004. Fates plates
  follow the person (C008, C013, B009). The cause (the plate name may come from a script command argument, which the
  trap copies unchanged) is a guess, not proven. Not fixed (the randomizer was frozen this round). The Seal page keeps
  "How they look" grey at "Keep the face" with the reason "Full swap waits on Seal of Flames: name plates in scenes
  keep the old name" (ingame.py GREY_FOR; a robot under A7's switch can still test it). The page robot (look-s,
  r76looks-d94d06a8) showed the Seal page's answer stays "keep" with no full.txt (it did not try to click "Full
  swap" there; the grey itself rests on the schema tests and the page's existing grey_for rule). Whether Seal needs a fix or its own full_off is round 77's question.
- **Birthright 14 (extra long replay, seed r76a14x0): no result.** That seed swaps seven deployed spots (against the
  track's seed rule); boards equal to 237 of 237 and GameData 201 with 0 wrong, but the generator differs from frame
  103740 and the recording leaves step in both looks, so battle results after 103740 and the closing scenes are NOT
  REACHED; its AID piece differs from frame 5869. Seen by the track (not opened by the reviewer): Saizo in Azama's
  spot, Kaze in Silas's, Setsuna in Hana's, Hayato's cut-in. The cq-ch10 and rv-ch10 replays were made but not
  started (cap).
- **Missing face (P3, R9 (c)): reached and SEEN.** Seed r76p3x3 (Kaden's spot = Azama) at C013 MID_C013_OP1_3_PCM1,
  expression 超笑 (big grin), line "I'd happily fight for its safety!": full shows Azama's normal face on the line, keep
  shows Kaden's grin; the line is there and nothing is blank (build/r76/full/p3_pictures.png; matched by the line,
  not the frame, because the AID look drifts the timing). The rule works as planned.
- **Still owner calls:** the stutter that keeps the old first letter ("S-Hana"), cosmetic; the AID drift that makes
  recordings made without the full swap stop fitting (a design call, not a fix).

## 4. Presets and the share code: round 74

**Where they live.** The page is drawn by the engine (`rando_page.rs`) from the rows Python prints
(`rando.py schema`). Rows alone cannot be preset buttons: a `drives` switch moves one row only. So the buttons and
the share code field are engine page code and need an engine batch. **Pick: round 74.** Round 71 is already
13 h with a cut order. The adopted roadmap (docs/ROADMAP.md) lists presets and the share code in round 74's
promise, and round 74's tests (the page robot) already run there.

**Design (Grok agreed, build/r70/swap/GROK_A_swap.out.txt):**

- **Presets** come from the schema: a new top-level `presets` list in `rando.py schema`, each with `name`, `help`
  and `values` (row key -> value). The page draws one button per preset in the Basics section. A press sets those
  values (through `RandoForm::set`, so fixed and grey rows keep their rule), keeps the seed, and writes one help
  line note. Contents are Grok's, owner's words on the buttons:
  - **Light:** classes, growths and join stats on. Royals and the face kept. Enemies, Nuzlocke and the full swap
    off.
  - **Wild:** Light plus enemy classes, enemy weapons, music and the within-route shuffle. Face still kept.
    Nuzlocke and the full swap still off.
- **Share code:** its own one-line field under the seed row, with **Copy** and **Paste**. It is not pasted into
  the seed box: a settings code there would be taken for a seed (Grok). The code is the schema version, the
  game (Fates or Seal), the seed and every row's value index, packed in a fixed key order, plus a 2-character
  check. Every answered row is included (hidden rows too), so the same code makes the same game and run id. A
  code from another schema version or with a bad check is refused in one plain sentence. The codec is a pure
  function in `rando_page.rs` (Rust, tests). Its twin goes in `tools/randomizer/ingame.py` (Python, PLAY
  RANDOMIZED and tests), and the two share one test-vector file under tests/.

**Counted (estimate, bottom-up), 2 h 10:** Python schema `presets` + twin codec + tests 1 h 05; engine buttons,
field and codec + tests 45 min; page-robot proof (press Light, then Wild; copy the code, paste it into a fresh
page, values equal; pictures SEEN) 20 min. Patch file: a new page patch in round 74's series (frontend only,
`rando_page.rs`, and `pagebot.rs` for the two new target kinds `btn:preset:<name>` and `row:share`).

**Round 73b check (2026-11-25, against today's `rando.py schema` and `rando_page.rs`).**
- Rows added since this section was written: **"Chest and village items"** (`chests`, Items and shops, default off,
  `omit_default`) and **"Recolour"** (`recolour`, Characters, on / clear / off, default on, `omit_default`). Grok
  (docs/collab/ROUND74_PRESETS_GROK.md): chests in **neither** preset (the owner has not said ok to it being on;
  it changes what a seed gives), Recolour at its **default** in both. Proposed default, owner's call.
- Light as written is "Randomizer on, every other row at its default" (classes, growths and join stats are already
  on by default; Royals keep class is on by default). Proposal: a preset press first puts every row at its default
  (`RandoForm::defaults`, `rando_page.rs` about line 340), then sets its rows through `RandoForm::set`, and keeps
  the seed, so Light after Wild gives exactly Light.
- **The share code must cover number rows**, which have no value index: 13 rows (8 shown, 5 hidden) are numbers
  with `min`/`max` in the schema (for example `growth_variance` 0-100, `base_variance` 1-10). They are packed as
  value minus min. Rows with `omit_default` (chests, recolour) are in the code at their value like every other row;
  the decoder then fills the form, and the answer leaves them out at their default as `answers_with_seed` does
  today (`rando_page.rs` about line 463), so the same code gives the same answer text and run id.
- Length, honestly: about 60 rows pack into roughly 30 characters, plus the seed (up to 32 characters), the schema
  version, the game and the 2-character check. A code with a long seed is about 70 characters, not "short".

## 5. Growths in Preparations: the free key is **Y**

**What the game reads there [high].** Every menu goes through `BasicMenu::Input` (0x004F9FB4). On a newly pressed
button it calls the selected item's handler and then the menu's: A -> `ACall`, B -> `BCall`, X (0x400) -> `XCall`,
**Y (0x800) -> `YCall`**, L -> `LCall`, R -> `RCall`, Start -> `StartCall`. Anything else, Select included, goes
to `CustomCall`. In the vtables of the Preparations menus:

| Menu (Preparations) | Item Y slot | Menu Y slot | Other keys the item takes |
|---|---|---|---|
| Pick Units, `sortie::UnitSelectMenu` (item vtable 0x0063F2DC, menu 0x0063F1C4) | `BasicMenuItem::YCall` 0x001C69FC = `return 0` (nothing) | `BasicMenu::YCall` 0x004FA878 (passes the item's 0 on) | A, B, X (sub menu), L (whole list), R, Start |
| Unit list from Preparations, `UnitListMenu::UnitListSortieMenu` (item 0x0069675C) | `BasicMenuItem::YCall` | `BasicMenu::YCall` | A, B, R, Start |
| Preparations top menu, `sortie::TopMenu` items | `BasicMenuItem::YCall` | default | B, L, R, Start |

In the whole game only two classes override `YCall`: `MIMassageName` and the debug menus. Neither is in
Preparations. A scan of the Preparations, unit-list and info functions for a test of the Y bit found none
(`UnitViewerCamera::Tick` tests 0x800 on an object's flags, not on the pad). The round-62 report says Select is
the game's own key there ("Start the battle?"). Our read did not find that handler in the menu classes (Select
reaches only the empty `CustomCall`), so it may sit in the Preparations sequence itself. Either way, **Y is the
clean choice**: nothing in Preparations reads it.

**The choice:** in Preparations, **Y** toggles the growth view (keyboard: the key bound to Y, Zakuro default `A`;
pad: the button bound to Y). The bottom-screen Growths button keeps working where the panel shows. On the
battle map nothing changes: Select / Tab / Back as in round 62. Grok agreed: "Y in Preparations, Select on the
map", said in the help line.

**Engine change (round 71, core + frontend, one patch):**

- `crates/zakuro-core/src/fates_growth_view.rs`: a new `prep_shown(g)`. It returns true when the Preparations
  sequence is alive (`sortie::Sequence::GetInstance` 0x004BCFD8 returns non-null; read the global it returns, no
  call) **and** the Pick Units or unit-list panel shows a unit (the existing `panel_unit` on `ProcGameInfo`,
  which these menus feed through `UnitMenu::SetGameInfo` / `UpdateGameInfo` in their vtables).
  `GrowthView::filter_input` takes Y the way it takes Select: one toggle per press, and Y is kept from the
  game only while `prep_shown`. The map rule is unchanged.
- **Where the numbers are painted:** the first round-71 step is one SEEN picture of Pick Units. The unit's stats
  may be drawn on the top screen there, not the bottom panel round 62 paints. In that case `paint` gets a
  second box list for that screen, with the same digits and the same pixel check of the frame it paints over.
  If the picture shows no stat numbers at all on Pick Units, the view shows the small eight-percent table
  (round 62's short-page way) over the portrait.
- `crates/zakuro/src/lib.rs`: nothing for the pad. The keyboard's Y key reaches the core as pad Y, so
  `filter_input` sees it. One help line in "Settings for this game" names the key.
- Tests: `y_switches_growths_only_in_preparations`, `y_reaches_the_game_everywhere_else`,
  `select_on_the_map_is_unchanged`.

**Proof (robot, round 71):** the recorded checkpoint `bt-ch9` frame 5875 is at the Preparations top menu
(markers.json). From a copy of that state, the robot presses A on Pick Units, takes a picture, presses Y, takes
another, presses Y again and takes a third. It must SEE percents on the second and the numbers back on the
third. The menu and marker state must be the same after the Y presses, and with no Y pressed the frames must be
identical to the round-62 exe. These are menu presses in the robot's own test copy (headless, F-042), not new play.

**Counted (estimate): 1 h 45** (detect 25, Y filter + tests 30, paint target from the picture 30, proof 20).
That matches the roadmap's "adds 1 h 45 to round 71". It is **first in the cut order**.

## 6. Esc menu "next New Game" and the help text: exact engine changes (round 71, one page patch)

Today the Esc menu's **Randomizer** button (`menus.rs`, Fates program, not `rando_blocked`) opens
`RandoPage::draw_this_run` (read only). The page's values live in `RandoPage::form`, the same object the New
Game page draws. `<data>/rando/last.json` is written only by `RandoPage::answered` and only when a randomized game
starts, and it is read once when the rows arrive (`RandoPage::poll` -> `RandoForm::restore`).

**Changes (file `crates/zakuro/src/rando_page.rs` unless named):**

1. `draw_this_run(&mut self, ctx, data: Option<&Path>)` (new parameter). `lib.rs` (line ~2600) passes
   `rando_data.as_deref()`, as `draw_new_game` already gets it.
2. Under "This run" and its separator, when `Rows::Ready`, a form exists and the New Game page is **not** open
   (`!self.new_game`), a **"Next New Game"** part:
   - at its top the grey line "These never change the game you are playing." (Grok: top, not bottom);
   - the **same rows and sections** as the New Game page (Grok: "a shorter list will hide a switch they set at the
     title"), drawn by the existing `rows()` inside `ui.push_id("next", ...)` and a `ScrollArea` with a max height,
     so the grid and combo-box ids never clash with the page's;
   - the same help line (change 5 below);
   - buttons **Keep for next New Game**, **Defaults**, **Randomize everything**, and no Start.
3. A new `pub fn keep_next(&mut self, data: Option<&Path>) -> Result<(), String>`. It writes `form.values` to
   `last_path(data)` through a new shared `write_last(data, &form)`, which `answered` also uses (same JSON, same
   folder). Unlike `answered`, it writes **even when Randomizer is off in the form**: Keep is the player's own
   choice, so "off next time" is remembered too. Then it sets `early_guess = false`, so the background guess
   (0020) follows the kept values, and it shows "Kept for the next New Game." in the part's note. Without a
   data folder (headless without `--data`) it says so and writes nothing.
4. Targets for the page robot get a `next:` prefix (`next:row:<key>`, `next:opt:<key>=<v>`, `next:btn:keep`, ...).
   `pagebot.rs` gets one script step that opens the Esc Randomizer window and draws `draw_this_run` with no
   window, as it does for the New Game page.
5. **Help line fit** (also used by the New Game page): `RandoForm::everything_on`'s note becomes one line,
   "Randomize everything turned on N settings. This run lists them after Start." (or "nothing more to turn on").
   The help line is drawn by a new `help_line(ui, text)`: an `egui::text::LayoutJob` with
   `wrap.max_rows = 2`, `break_anywhere = false`, `overflow_character = Some('…')`, inside a box of fixed
   two-line height (`allocate_ui` + `set_min_height`), with the full text on hover. Round 62b's list ran to four
   lines at 800x960 (docs/REPORT_2027-01-07.md). With this change the buttons sit at the same height whatever
   the help says. egui is 0.36.2 (Cargo.lock), which has these wrap fields.

`menus.rs` needs no change: the button exists and Seal of Flames already gets it.

**Tests (cargo, `rando_page.rs`):** `keep_next_writes_last_json_even_with_randomizer_off`,
`the_next_part_is_hidden_while_the_page_is_open`, `next_targets_are_named_apart`,
`the_everything_note_is_one_short_line`, `the_buttons_do_not_move_when_the_help_changes` (draw with a long and a
short help, compare the `btn:start` rectangle), and the round-62b test's note assertion updated.

**Proof (robot, round 71):** headless page robot in its own data folder. Open Esc Randomizer, set one row in
"Next New Game", press Keep. The job's `rando/last.json` holds the value. Then a New Game mode pick opens the page
with that value set (two pictures, SEEN). Separately: the New Game page before and after Randomize everything at
800x480 and 800x960, with the `btn:start` rectangle unchanged (two pictures, SEEN).

**Counted (estimate, bottom-up):** next New Game **2 h 00** (code 65, tests 30, page robot step + proof 25); help
line **30 min** (code 10, tests 10, proof 10; the roadmap counted 20, with the fixed-height box added here).

## 7. Summary for round 71's header (integrate)

| Item | Round | Patch (new, frontend/core) | Counted | Kind |
|---|---|---|---|---|
| Esc "next New Game" settings | 71 | page patch (`rando_page.rs`, `lib.rs`, `pagebot.rs`) | 2 h 00 | estimate, bottom-up |
| Help text fits (fixed 2-line help line, short note) | 71 | same page patch | 30 min | estimate |
| Growths in Preparations on Y | 71 | core + frontend patch (`fates_growth_view.rs`, help text) | 1 h 45 | estimate; **cut first** |
| Presets (Light, Wild) + share code field | 74 | page patch + `rando.py schema` / `ingame.py` | 2 h 10 | estimate |
| R9 normal-face guard + spoiler list | 74 | Python only (`recruit.py`) | 30 min | estimate |
| Expression backstop hook (only if the picture asks) | 74 | core | 40 min | estimate; cut first in 74 |
| Voice pass in the message hook | 74 | core (`Mess::Get` hook) | 30 min on top of the names hook | estimate |
| Four-chapter rule switch (`full_off_chapters`, fixed row) | 75 | Python only | 15 min | estimate |

None of these touches a save, a script, a text file or a portrait file. With the randomizer off and no new key
pressed, every one leaves the game's memory identical to today's program. That is the check each engine round
already runs.

**Round 73b check (2026-11-25): what of the full swap exists today, read in the code; nothing robot-proved.**

| Part | Python (tools/randomizer) | Engine (laid?) | Proven |
|---|---|---|---|
| P1 faces (FaceData records) | `recruit.py` `build_edits` (about line 532) writes one `{"table": "FaceData", "show": ..., "laid_by": "engine"}` record per swapped spot into plan.json only; no cell is made from it | the core has a resident FaceData file kind since round 59 (`fates_rando.rs` `Kind::Face`, `resident_start`, `apply_gamedata`), with plain and label-pointer cells; only plain cells (+0x1C hair colour, the recolour) were ever laid | no |
| P2 menu names (`mpid_name`, `mpid_help`) and P3 battle model (`aid`; the map head follows `aid`, `UnitIcon::SetIcon` 0x004F5104) | made as Person cells when look = full (`recruit_full_cells` in config/randomizer/rules.json: aid, mpid_name, mpid_help, body_type, voice), for the main row and the route-variant (HANDOVER) rows; **the chapter person copies are not edited** (`build_edits` takes the main row and the HANDOVER rows only) | main GameData row: label pointers are laid by the core today (`apply_file`). Person files (`GameData/Person/**`): **label pointers are not laid** (`fates_rando_session.rs` `make_placement`, about line 772: "label pointers are laid only in placement files"), and `ingame.py` `file_entries` (about line 515) refuses them except as a rename in place | no; the page keeps the look row fixed at "Keep the face" (`ingame.py` PAGE_FIXED, line 109), so no real game has laid them |
| P4 names in dialogue, voices quiet | nothing | nothing (the trap kind exists, see 2.2) | no |

So round 74's new work is: the FaceData cells (Python), label pointers in person files (a small core change, laid in
memory after the game stores the file, as placements are), the chapter copies (Python), the `Mess::Get` trap with
its buffer ring and the name and voice passes (core), R9 (a)-(c) (Python), and the proofs.
