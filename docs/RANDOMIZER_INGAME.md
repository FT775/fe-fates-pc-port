# The randomizer inside the game's New Game flow (F-044 and its addendum): design

**The Seal edition (F-047, round 58):** the page and the randomizer also work in the Seal edition (patch 0013); its notes moved to docs/seal/RANDOMIZER_SEAL.md in round 84. Round 58 also added patches 0014 (a randomized battle save loaded from the title is no longer taken for a New Game) and 0015 (placement files with class/item labels are laid in memory, so joiners keep their weapons); section 13.

**For the owner.** What you asked for: *"I need to be able to set all the randomizer settings within the settings
right after setting the new game to casual vs classic"*. Here is how it will work. You start a New Game as usual and pick
the difficulty. Right after you pick **Casual**, **Classic** (or Phoenix), the game stops for a moment and a
**Randomizer** page opens over it. It has every randomizer setting: Randomizer on/off (off at first), the seed (type one
or press Random), and every switch PLAY RANDOMIZED has, with the same names and defaults, plus "Everything on". Press
**Start game**. With Randomizer off, the game goes on exactly as the original (nothing is changed). With it on, the
randomizer makes the game from your seed (a few seconds) and the game goes on to the avatar screen. When you save, the
seed and settings are kept in a small file beside that save. Each time you load that save (Load, Continue, a battle
save), the same randomized game comes back. A save without that file loads as the original. Esc, **Randomizer** shows
what the current game was started with. PLAY.bat stays as it is; PLAY RANDOMIZED stays as a fallback. It needs Python
on the PC (the randomizer is our Python tool); without it the page says so and the game plays the original. **Size:
too big for one round.** This round (50) builds the Python part, the engine's apply-and-keep part and the tests that
prove it in the robot; round 51 builds the page you will see and the program you play (sections 8 and 9). Nothing
counts as done until you say ok (F-037).

**Round 50 build, 2026-11-20, in plain words.** Built and tested: the randomizer can now list every page setting
(`rando.py schema`) and write the "in-memory patch" the game will lay after you pick Casual/Classic (`make
--patch-out`). The engine has the part that finds the game's tables in memory, checks every cell first, writes the
patch (or nothing) and can put it back (patch 0007, not switched on yet). The robot, reading only, showed that the
game's copy of its tables in memory is exactly the file, and that every cell of an "everything on" patch sits where
the patch says. One finding changes the plan: the game makes a chapter's units **in the same frame** it loads that
chapter's placements, so laying placement changes "after the frame" is too late. Table changes (classes, growths,
bases, skills, shops, castle rewards) are fine; placement changes (the weapon swaps that go with new classes, starting
items, enemy gear and classes) need the more precise hook from section 3b first. Not built yet: the page you will see
and the program you play. No exe was built, and nothing in your game changed. Section 11 has the details.

**Round 51 build, 2026-11-20, in plain words: ready for your look.** The page is built and wired in, and the program
you play (`play/game/Fire Emblem Fates.exe`, Zakuro patches 0001-0010) was rebuilt with it. PLAY.bat starts it as
before. New Game, pick the difficulty, pick Casual or Classic: the Randomizer page opens; with Randomizer off the game
goes on as the original. The robot proved, headless and on recorded routes only: a randomized new game equals the same
seed installed as a mod (tables and the Prologue's 30 units, 0 differences); Randomizer off is the old program exactly
(same memory, same saves); a randomized save comes back randomized when loaded (a battle save too); an original save
loads as the original. It found two bugs, both fixed (patch 0010). Nobody has seen the page in a window yet: that is
your look (T7). Undo: put back the backup exe (section 12). Nothing counts as done until you say ok (F-037).

Status 2026-11-20 (round 50, design chapter, 60 min cap). Host only: no build, no game or robot run. Facts are from the
game's code (`asm/`, `config/functions.csv`, the game's own symbol names), the engine source that is actually built
(`engine/zakuro`, branch `fe14` = pin `c856685` + patches 0001-0006; `engine/fe-awakening-recomp/source/zakuro` is the
Awakening reference copy, not what `engine.py port` builds), docs/ROBOT.md, docs/TABLES.md, docs/OPTIONS_WIRING.md,
docs/RANDOMIZER.md, docs/RANDOMIZER_PAGE.md, tools/play/rando.py, tools/randomizer/rando.py, and the FE8 port's
PLAYING.md ("Randomizer", "This run"). Tags: **[high]** read in code, **[med]** good evidence, **[test]** to be proven by
the tests in section 7.

---

## 1. The real order of the New Game screens (from the code)

| Step | Screen | Code (game's own names) | Robot route `new-game` |
|---|---|---|---|
| 1 | Main menu (New Game / Extras) | `title::ProcTitle::CreateTopMenu` 0x00440F7C | 3000:A, screen at 3300 |
| 2 | **Difficulty** (Normal / Hard / Lunatic) | `title::ProcTitle::CreateDifficultyMenu` 0x00441DAC; `NormalItem/HardItem/LunaticItem::ACall` store 0/1/2 in ProcTitle+115 | list at 3600 |
| 3 | **Mode** (Casual / Classic / Phoenix) | `title::ProcTitle::CreateModeSelectMenu` 0x0044208C; `SelectModeCasualItem::ACall` 0x0043E208, `SelectModeClassicItem::ACall` 0x0043E55C, `SelectModePhoenixItem::ACall` 0x0043E674 | list at 3900, A at 4000 |
| 4 | the game is set up | `title::ProcTitle::JumpMyUnitEdit` 0x00441768 | (inside the frames after 4000) |
| 5 | Avatar creator | `title::ProcMyUnitEdit` (sequence 4) | 4590 |

So the mode is the **last** choice before the game starts [high]. Each mode's `ACall` does the same three things
[high, disassembly]: stores its mode (Casual 1, Classic 2, Phoenix 0; all three read) into the title's byte
ProcTitle+116, then `ProcInst::Jump(title, 8)`. Label 8 runs `JumpMyUnitEdit` (its address sits in ProcTitle's code
table at 0x006408E0): it copies difficulty (+115) into `GameUserData`+0x2D, calls `GameUserData::SetMode` with +116,
calls `GameConfigData::StartFromBeginning` (its **only** caller) and `MainSequence::Jump(4)` (the avatar creator;
`MainSequence` is the ProcInst at `*0x006D88D4`). **One moment covers all three modes:** the frame in which
`JumpMyUnitEdit` ran. That is where the page opens.

Why that moment is safe for the tables [high]: `GameData::Initialize` (0x004E6954, called once at boot from 0x001B6178)
loads `GameData/GameData.bin.lz` whole as one `ArchiveFile` (pointer at `*0x006D3868`) and gives each table only a
pointer into it (`Person::Initialize` gets header+0x8, `Job` +0xC, `Item` +0x2C, `AchieveBonus` +0x5C, ...). Units are
made from those rows much later (`Unit::CreateImpl` reads Person+0x2C class, +0x38 bases at creation) and stats,
growths and personal skills are read **live** from the rows (`Unit::GetStrImpl` etc. read Person+0x38.., `Unit::GetGrow`
Person+0x40, `Unit::IsEquipSkill` Person+0x74). So rows written before the avatar creator are the rows the whole game
uses, the same as if the file had been modded.

## 2. Decision 1: how the page is shown

**A Zakuro (egui) page, opened automatically at the end of the frame in which the mode was picked.** No game code is
changed and no game screen is drawn.

- Zakuro already pauses the game while any of its pages is open (`lib.rs`: `playing = ... && !menus.over_game()`), the
  same as the Esc menu. The new page joins `over_game()`. The game simply does not run a frame until **Start game**.
- How Zakuro sees the moment: after every frame it reads a few bytes (read only). The signal is "the title's
  `JumpMyUnitEdit` ran this frame". Candidates, all read-only: the `MainSequence` ProcInst's current label changing to 4,
  and the `GameConfigData` flag word (`*0x006DA0F8`+0x4) that only `StartFromBeginning` sets this way. The build round
  picks the one that flips exactly once, at frame 4000-4590 of the recorded `new-game` route, and on no other frame of
  `bt-prologue`, `bt-ch2` and the load routes [test T1].
- Rejected: **a page drawn by the game** (needs new game UI code: far bigger, and a game-code change in every run);
  **a readable hook on the `ACall`** (precise, but only in readable mode, which is not in your game yet and itself
  changed a save's clock byte in round 48; OK B is still open); **a code patch + new system call** (precise, but a
  game-code change that would have to be present in every run, so Randomizer off would no longer be byte-identical).
  Frame-end reading is enough here because nothing uses the changed rows between the pick and the avatar creator's
  first frame (section 1).
- Headless runs never wait: with `--headless` the page is answered at once from a test file (section 7, the test hook),
  or "Randomizer off" when there is none, so every existing robot or headless run behaves as today.

## 3. Decision 2: how the randomized data reaches the game

The randomizer stays our Python tool. Zakuro calls it; Python never runs inside the game.

### 3a. What Python makes

New, in `tools/randomizer/rando.py`:

- `rando.py schema` prints the page's rows as JSON: key, label, kind (on/off, choice list, number range), default, the
  "Everything on" values. It is built from `tools/play/rando.py` (`SWITCHES`, `SWITCH_LABELS`, `OPTIONS`, `SUGGESTED`,
  `SEED_RX`) plus the two `make` switches PLAY RANDOMIZED does not ask (`--trees own|any`, `--keep-royals on|off`) and
  Children (shown, grey, "off: not built"). So the page cannot drift from PLAY RANDOMIZED: one list, one place. A test
  compares the two.
- `rando.py make ... --patch-out FILE`: everything `make` does today (same plan, same guards, same spoiler; exit 2 when
  a guard fails), plus a **patch file**: for every cell the plan changes, where it is and what it was:
  - GameData cells: table (Person, Job, Item, AchieveBonusBattle, AchieveBonusVisit, ...), record index, field offset,
    size, **original bytes**, new bytes. Every cell the randomizer writes in GameData is a plain value (class and item
    numbers, s8 stats, u16 skill numbers; docs/TABLES.md), never a pointer [high].
  - Dispos cells, per file (route folder + file name, e.g. `A/A005`): unit index, the unit's `pid` text (identity check),
    field, original value, new value. `jid` and `item_N` are **string pointers** in Dispos files [high: TABLES.md
    DisposUnit +0x4, +0x14..], so for those the patch holds the label text (`JID_...`, `IID_...`); the forge/flag
    bytes are plain values.
  - the seed, the options, the randomizer's version (git hash of tools/randomizer + a format number), and the SHA-256 of
    the original tables it was made from.
- `--out` keeps writing the usual mod folder (plan.json, spoiler.txt) beside the patch, for the spoiler log and for
  `rando.py check`. No `--zakuro-dir`: nothing is installed, no GameData is rebuilt.

### 3b. What Zakuro writes (the writer, approved by the addendum)

New module `fates_rando` in `zakuro-core` (patch 0007), used by both the game program and the robot's `boot-server`
(so the robot tests the exact same code):

- **Find the tables in memory:** `*0x006D3868` (GameData's ArchiveFile) -> its buffer -> header (the same pointer chain
  `GameData::Initialize` walks: `[+4]`, `+112`, `+32`), then header+0x8 Person block, +0xC Job, +0x2C Item, +0x5C
  AchieveBonus... Record = block + header size + index x record size, as the robot already does for Person
  (`tools/randomizer/robot_check.py`).
- **Guard before any write:** every cell's current bytes must equal the patch's "original bytes", and the table counts
  must match. Any difference (another mod installed, a PLAY RANDOMIZED profile, a different game version) = **nothing
  is written**, the page says why, and the game goes on as loaded.
- **Apply** writes the new bytes. **Revert** writes the original bytes back (same guard the other way round).
- **Dispos (per chapter files):** the game reads a chapter's placements in `map::Dispos::Load` (0x0039ED9C) into one
  object (`*0x006D6DC8`: name[16] at +0, ArchiveFile at +16, data at +20) [high]. It is called by the chapter sequence
  (0x001DA824) and by `map::Dispos::Deserialize` when a battle save is loaded. After each frame `fates_rando` reads that
  object; when name or data pointer changed and a run is active, it patches that file's units in memory: plain bytes
  directly, `jid`/`item_N` by pointing them at the same label text in the resident GameData (the Job/Item record's own
  label string), which stays loaded the whole session. Same guard (each unit's pid text and original values must match).
  The open point is timing: units must not be made in the very frame the file was loaded. Test T3 measures it on every
  recorded chapter start before anything is built on it. **If any recorded chapter makes units in the load frame**, the
  fallback is a precise hook: `fates_rando` notes "Dispos file read" in Zakuro's file service (host side, inside the
  game's own read) and applies at the next system call of that thread once the data pointer is stored. That is still no
  game-code change; it costs about half a day more.
- **Off = original:** with no active run `fates_rando` only reads. Nothing in it writes unless a run is active, and a
  run becomes active only by Start game with Randomizer on, or by loading a save whose side file names a run.
- **On the title screen the tables are always the original's:** when the title's main menu comes back (soft reset, B
  from the avatar creator, quit to title), an active run is reverted. Every path from the title then starts clean, and a
  load re-applies its own run (section 4).

Why not Zakuro's mods layer: it is laid once at boot (`zakuro-core/src/loader.rs` -> `mods::lay`) into a new RomFS image,
and the game's own file code keeps the RomFS directory from boot; swapping the image later would not match what the
game already read. That is why PLAY RANDOMIZED needs a separate folder per seed and a restart. Not usable "right after
Casual/Classic" without restarting the game.

## 4. Decision 3: keeping the seed with the saves (as the FE8 port)

- **Where:** in the same data folder as the saves, never inside the 3DS save itself:
  `<data>/rando/0004000000179800/runs/<seed>-<8 hex of the options>/` (patch.json, plan.json, spoiler.txt,
  options.json) and `<data>/rando/0004000000179800/slots/<save file name>.json` (which run that save file belongs to,
  when it was written, the save's SHA-256 for the log). `<data>` is whatever `--data` / the default is: for you with
  PLAY.bat (portable_saves false) that is your normal Zakuro folder, so these files appear there only when **you** save a
  randomized game. Tests always use folders under `build/`.
- **When it is written:** Zakuro's file service knows each save file by name when the game writes it (`data:/Chapter0`
  ..2, the battle saves `ext:/Map0.bak`/`Map1.bak`, and any other file of `GameBackup::GetFileName`'s table at
  0x006DA080). A small callback in `services/fs.rs` (close after write, or rename onto that name) tells `fates_rando`:
  with an active run it writes `slots/<name>.json` (temp file + rename); with no run it removes that slot's file (so a
  slot overwritten by an original game loads as the original). The `Global` file is shared by all slots and is ignored.
- **When it is used:** the same callback on the first read of a save file: with a slot file, that run is applied before
  the game parses the save (the read is still inside the game's own call, so the tables are right before any unit is
  read back); without one, any active run is reverted (original tables). This covers title Load, Continue, the battle
  save (suspend) and Restart Chapter, because they all read one of these files [test T5].
- **Zakuro save states** (F-keys): a state holds the whole memory, tables included. Saving a state also writes
  `<state>.rando.json` (the active run). Loading a state sets the active run from it (none = original). No table
  write is needed: the memory is already right.
- A slot file whose run folder is missing: the save loads as the original and a notice says so (FE8 port rule: "the
  randomizing itself is kept only in the side file"). The save itself is never touched.

## 5. Decision 4: failure handling and limits

| Case | What happens |
|---|---|
| No Python (Zakuro tries `FEF_PYTHON`, then `py -3`, then `python`; `--version` and `rando.py schema` must answer within 5 s) | The page still opens after the mode pick, with Randomizer grey and the reason ("Python 3 was not found; the randomizer needs it"). Start game = the original game |
| `tools/randomizer` not found (the program looks next to itself: `play/game/../../tools/randomizer`, or `FEF_RANDO_TOOL`), or the game's tables not available (`gamedata.available()`) | same, with that reason |
| `make` fails or a guard fails (exit not 0), or takes over 120 s | message with the last lines of its output; buttons **Back to the settings** / **Play the original game**. Nothing was written |
| The in-memory guard fails (another mod or a PLAY RANDOMIZED profile is loaded) | nothing written; message; the game goes on as loaded. In a PLAY RANDOMIZED profile the row says "this game folder already has a randomizer mod" |
| A chapter's Dispos guard fails | that chapter keeps the original placements; a notice and a log line (`zakuro.log`); counted in the test reports as a failure |
| Game update installed (other build) | the guard fails at once (tables differ) -> greyed with "this randomizer is for the clean dump" |
| Owner's files | the program writes only `<data>/rando/...` and only for a randomized game. The page's last choices are kept in `<data>/rando/last.json`, never in `settings.toml` |

PLAY.bat: unchanged. PLAY RANDOMIZED: stays, works as today (its profiles have the mod laid at boot; the in-game page
sees the guard fail and says so, so the two never stack).

## 6. The page itself (rows)

Same names, defaults and "Everything on" as PLAY RANDOMIZED (from `rando.py schema`; FE8's rule: with Randomizer off
the rows are grey but can still be set):

| Row | Values (default first) |
|---|---|
| Randomizer | **Off** / On |
| Seed | text, 1-32 letters, digits, `-`, `_`; **Random** button; empty = a new one is made at Start game and shown afterwards |
| Classes, Growths, Join stats | **On** / Off (slice 1) |
| Class trees | **own** / any; Royals keep their classes **On** / Off; Children **off** (grey: not built) |
| Growths mode | **slice1** / redistribute / delta / full; Growth variance **30**, min **5**, max **80**, Adjust HP growths **Off** |
| Bases mode | **slice1** / redistribute / delta; Base variance **5**, Scale to join level **On** |
| Personal skills (shuffle = swap the skills between characters) | **keep** / shuffle / random; Skill slots **keep** / class / random |
| Starting items, Shops, Castle rewards | **Off** / On; Shop sides **own** / mixed |
| Enemy weapons, Enemy classes, Boss classes | **Off** / On; Enemy class trees **own** / any |
| Buttons | **Everything on** (the suggested values), **Defaults**, **Start game** |

Esc, **Randomizer** (F-044's page): **This run** (on/off, seed, the options that are not default, "Open spoiler log"),
read only; the next New Game's settings (the same form, kept in `last.json`). Changing them never changes a game
already started.

The form is a plain model (`RandoForm`: rows, values, validation, to command-line flags) separate from its egui drawing,
so it is unit-tested without a window.

## 7. Decision 5: tests without a visible window

Every run: check `build/STOP_ROUND` first; headless (`--headless N --mute`, or the robot's headless runner); data,
APPDATA and LOCALAPPDATA under `build/rando50/...`; below normal; at most 2 robot jobs; never `play/game/Fire Emblem
Fates.exe`. Recorded routes only (no new play).

**The hidden test hook** drives the same code as the page: `FEF_RANDO_ANSWER=<file.json>` (honoured only with
`--headless`, and by `boot-server`'s new command `rando-answer <file>`) holds the answer the page would give
(`{"randomizer": true, "seed": "...", options...}`). At the mode-pick moment `fates_rando` takes it instead of opening
the page, then runs exactly what **Start game** runs: Python `make --patch-out`, guard, apply.

| Test | How | Pass |
|---|---|---|
| U1 Python | `tests/test_rando_ingame.py`: `schema` = PLAY RANDOMIZED's lists; `--patch-out` applied to the original decompressed GameData.bin = the mods tool's rebuilt GameData.bin byte for byte (3 seeds x defaults/everything on); Dispos patches equal the mod's DisposUnit cells; same seed -> same patch | all pass |
| U2 Rust | `cargo test -p zakuro-core fates_rando` (fake memory): locate, guard, apply, revert, Dispos patch with label pointers, slot files written/removed/read, state sidecar; `cargo test -p zakuro` for `RandoForm` | all pass |
| T1 the moment | robot reads the candidate bytes every frame on `new-game` (0-4600) and `bt-prologue`, plus `bt-ch2` and the load routes | the signal fires once, between 4000 and 4590 of the new-game part, never elsewhere |
| T2 new game = mod | `bt-prologue` presses with the hook answering seed `r50all` (everything on): Person/Item/AchieveBonus rows at 4600 = the plan; then the same seed as an installed mod (round 47/49 way): the GameData buffer in memory byte-identical between the two runs; Prologue's units (class, items, stats) identical up to its first battle | 0 mismatches |
| T3 Dispos timing | per frame on every recorded chapter start (bt-prologue, bt-ch2 .. existing chain routes): the frame the Dispos object changes vs the first unit made from it | always at least 1 frame apart, else the precise hook (section 3b) |
| T4 off = original | the same routes with the new program and Randomizer off (and with no answer file): whole memory hash and save files = the old program's, as in round 47's rc-off vs rc-none | identical |
| T5 save and reload | seed `r50shops` with **only** Shops and Castle rewards on (they are not used in Prologue/Chapter 1, so the recorded `bt-prologue` presses still fit to its chapter save): the save writes `slots/Chapter0.json`; then `bt-ch2` from that save: the Item/AchieveBonus rows = the plan right after the load, Chapter 2's Dispos = the plan; a load of the original `bt-ch1-clear` save (no slot file) after it gives the original rows | 0 mismatches |
| T6 battle save | an existing chain route that loads a battle save (`Map0.bak`) with a slot file laid by the test for that file | rows and that chapter's Dispos = the plan after the load |
| T7 the page | no window is opened. The `RandoForm` unit tests cover the rows; you look at the page yourself (F-044: "the owner looks at the finished page himself") | owner |

Said plainly: the recorded presses only fit a randomized game until its first battle (round 47), so a full randomized
playthrough to a save is not tested; T5 uses a seed that cannot change the recorded play. Classic and Phoenix are not
recorded (the route picks Casual); all three go through the same `JumpMyUnitEdit` (section 1).

## 8. Size, honestly

| Piece | Work | Needs |
|---|---|---|
| P1 `rando.py schema` + test | 0.5 h | nothing |
| P2 `make --patch-out` + U1 | 1.5 h | nothing |
| R1 `fates_rando` in zakuro-core (locate, guard, apply/revert, Dispos patch, slot files, fs callbacks, state sidecar) + U2 | 3.5 h | patch 0007, `cargo test` (owner OK, F-044) |
| R2 boot-server commands (`rando-answer`, read helpers) | 1 h | boot-server build (own target) |
| T1, T3 (read-only robot) | 1 h | robot |
| T2, T4, T5, T6 | 2 h | robot + builds above |
| F1 the page (`RandoForm`, egui page, auto-open, Esc "Randomizer", Python in a thread, messages) + `run_headless` hook | 3 h | patch 0008 |
| F2 `engine.py apply` / `port`, backup of the current exe to `build/backup/` (the 2026-11-10 backup stays) | 0.5 h | owner OK (F-044) |
| docs, report | 0.5 h | |
| **Total** | **about 13 h** | |

This round's build slot is 150 min. It does not fit.

## 9. What each round builds

**Round 50 (this one, 150 min build + 25 review):**

1. T1 and T3 first (read-only robot on existing routes, 2 jobs): they decide the signal and whether frame-end Dispos
   patching is safe. If T3 fails, the rest of this round still builds; section 3b's fallback is planned into round 51.
2. P1 and P2 with U1.
3. R1 with U2 as patch 0007 (`engine.py apply`, `cargo test` for zakuro-core only). No exe build this round.
4. Integrate (30 + 10): docs/RANDOMIZER.md section 7, report, check_all row for U1.

**Round 51:** R2 + T2, T4, T5, T6 in the robot; F1 (patch 0008) and F2 (backup, `engine.py port`); the owner looks at the
page. Then nothing counts as done until the owner says ok.

## 10. Rules kept

No game-code change in any run; off = original (T4); the writer runs only for an active randomized run (new game with
Randomizer on, or a save whose slot file names one); no Nintendo data tracked (patch files and side files live in data
folders and `build/`, never in git); the owner's %APPDATA%, saves, Zakuro settings, cheats and mods are never touched by
tools or tests; PLAY.bat and PLAY RANDOMIZED unchanged; no children, no Nuzlocke, no join swaps (F-043).

---

## 11. Round 50 build results (2026-11-20)

Built what section 9 puts in round 50 (P1, P2, R1, T1, T3). Not built (round 51): the boot-server commands, T2/T4/T5/T6,
the egui page (patch 0008), the frame hook that calls `fates_rando`, the exe backup and `engine.py port`. **No exe was
built and `play/game/Fire Emblem Fates.exe` was not touched or started**: patch 0007 is not wired into any frame, so a
build now would change nothing you can see, and T3 (below) says the placement part needs the precise hook first. The
owner's look (T7) waits for the page.

### What was made

| Piece | Where | What |
|---|---|---|
| P1 | `tools/randomizer/ingame.py` `schema()`, `rando.py schema` | the page's 26 rows as JSON: Randomizer (off), Seed (PLAY RANDOMIZED's `SEED_RX`), its 3 switches and 18 options with their labels, defaults and "Everything on" values (read from `tools/play/rando.py`, loaded by path), plus `trees`, `keep_royals`, and Children (fixed off). `make_args(answer)` turns a page answer into `make` flags |
| P2 | `ingame.py` `make_patch()`, `rando.py make ... --patch-out FILE` | after the usual `make` (same plan, guards, spoiler; exit 2 on a failed guard, and then no patch), runs the mods tool's `compute()` on the made mod (nothing staged or installed) and compares each rebuilt file with the original **as the game holds it**: plain bytes outside pointer slots become `v` cells; pointer slots are compared by the label text they show, and a changed one becomes a `p` cell with the new label's place in GameData's string pool (`g`) or the file's own (`s`), plus the original pointer's file value for revert. Data pointers into the file's own data region must not change (checked). Any file other than GameData and `GameData/Dispos/**`, any whole-file or text change, or a data region that changes size: refused with the reason. Format: text, one cell per line (top of `ingame.py`) |
| R1 | `engine/zakuro/crates/zakuro-core/src/fates_rando.rs`, **patch 0007** (`patches/zakuro/0007-core-Fire-Emblem-Fates-randomizer-laid-in-memory-aft.patch`, README row; `engine.py apply`: "unchanged; fe14 = c856685 + 7 patches") | `Patch::parse` (refuses a cut or inconsistent file), `gamedata_start` / `dispos_now` (the chains below), `apply_file` (checks every cell: bytes, label text, and that each new label is where the patch says; then writes all or nothing; `revert` the other way), `Run` (GameData once; each placement file once per load; a failed placement guard keeps the original and leaves a notice), `NewGameWatch` (T1's signal), `slot_written` / `slot_run` (side files `<data>/rando/0004000000179800/slots/<save>.json`). No new crate dependencies |
| tests | `tests/test_rando_ingame.py`, check_all row `rando-ingame-tests` (+ its sample in `tests/test_check_all.py`); Rust unit tests in `fates_rando.rs` | below |
| robot | `tools/randomizer/robot_ingame.py` (read only: peeks, no pokes) | T1, T3 and a guard dry run, below |

The patch file holds game values, so it is written only under `build/` (tests) and later the data folder, never in
git. For the everything-on seed `r50all` it has 102 files, 578 value runs and 8,696 label pointers (9,274 cells).

### Tests

| Test | Command | Result |
|---|---|---|
| U1 Python | `python -m unittest tests.test_rando_ingame` | **8 passed** (42 s): schema = PLAY RANDOMIZED's lists (labels, defaults, "Everything on", choices, seed rule); `rando.py schema` prints the same JSON; page answer to flags (Children forced off); the patch reader refuses broken files; for seeds `r50all` (everything on), `r50def` (defaults) and `r50shops` (Shops + Castle rewards only, slice 1 off): the patch laid on memory images of the original files (pointers relocated to a fake load address) gives the mods tool's rebuilt files cell for cell (plain bytes byte for byte, labels by text, dropped pointers null); a second apply is refused and writes nothing; revert gives the original image back byte for byte; same seed, same patch. `r50shops` touches GameData only |
| U2 Rust | `cargo test -p zakuro-core --lib fates_rando` (target dir `engine/target/zakuro-core-test`, below normal, no window) | **11 passed**: parse, refusals, locate, apply then revert = original memory, guard refuses with 0 writes, placement guard keeps the original with a notice, a reload of the same file is laid again, an empty run writes nothing, the mode-pick watch fires on a new game and not on a load, side files written/removed/read, and the real `r50all` patch (via `FEF_RANDO_PATCH`, not kept in git) parses with all 9,274 cells |
| zakuro-core whole | `cargo test -p zakuro-core --lib` | **159 passed**, 0 warnings. The `zakuro` (frontend) crate was not changed this round, so its tests were not run |
| existing | `tests.test_play`, `test_rando_profile`, `test_randomizer` (79 passed); `test_rando_integrate`, `_items`, `_skills`, `_growth`, `_enemies` (61 passed); `tests.test_check_all` (95 passed, 1 skipped); `engine.py selftest` 24/24 | all pass. PLAY RANDOMIZED's command line is unchanged (`tools/play/rando.py` was not edited) |

### Robot (read only: headless boot-server below `build/rando50/server/`, data/APPDATA/LOCALAPPDATA there, below normal, at most 2 lanes, recorded routes only)

| Run | Route, frames | Found |
|---|---|---|
| GameData in memory | every run (bt-prologue 3950-47600, bt-ch2 0-20040) | `[[*0x006D3868 + 4] + 112] + 32` is GameData's data start; memory there = the original file: **0** plain byte and **0** pointer differences (4,708 pointer slots, labels compared as text). Dry guard of `r50all`'s 578 GameData cells: **0 would refuse** |
| Placements in memory | A000 (Prologue), A001, A002 (Chapter 2) | the name at +0 is the bare stem (`A000`); the data pointer at +20 = the same chain from the ArchiveFile at +16; memory = the file (A001, A002: 0 differences; A000 at its load frame 13449: 30 plain bytes from +0x164 already changed by the game itself, none of them a patch cell). Dry guard: A000 11 cells and A002 19 cells, **0 would refuse** |
| **T1** the moment | bt-prologue 3950-4700 every frame, 4700-47600 every 10; bt-ch2 0-20040 every 10 and 2830-2842 every frame | `GameConfigData` (`*0x006DA0F8`) word +4 changes **once, at frame 4019** (A on Casual at 4000) with byte +0xB staying 1; the `MainSequence` ProcInst changes in the same frame. On a save load (bt-ch2 frame 2839) the same word changes **and** +0xB goes to 0 in that frame. Later +0xB goes from 1 to 0 when the chapter starts (bt-prologue between frames 4700 and 12410). Signal used: "+4 changed, +0xB still 1" (`NewGameWatch`). Not proven frame by frame outside the scanned windows (10-frame steps), and Classic/Phoenix are not recorded |
| **T3** placement timing | every frame around each placement load: A000 13438-13452, A001 36738-36752, A002 4548-4562 | **fails**: the placement object and the unit list change **in the same frame** (13449, 36745, 4552). Units are made from the file in the frame it is loaded, so laying placements after that frame is too late |

Every server was the robot's headless boot-server (CREATE_NO_WINDOW); no window appeared and none was left running.

### What T3 means for round 51

- Table cells (GameData: classes, growths, bases, skills, shop stock, castle rewards) are safe: the mode pick is at
  frame 4019, the first placement file loads at 13449 (Prologue), and nothing between reads the changed rows
  (section 1).
- Placement cells (slice 1's weapon swaps for new classes, starting items, enemy weapons and classes) need the precise
  hook of section 3b: lay the cells inside the game's own load, before units are made. `Run::after_frame` stays as
  the place that would call it, but must not be relied on. Options to weigh in round 51: (1) a host-side note in the
  file service when a `GameData/Dispos` file is read, applied at the game's next system call once the data pointer is
  stored (needs a test that such a call comes before the first unit; about half a day); (2) a recompiled-code hook at
  the end of `map::Dispos::Load` 0x0039ED9C (precise, but a code hook, so it must be installed only while a run is
  active to keep "off = original"); (3) for a first version, the page offers only the table options and greys the
  placement ones, saying why. The owner picks.
- Also for round 51 (from the design review): the frame hook must sit in zakuro-core (`run_frame` or a shared
  after-frame hook), not only in the frontend, because `run_headless` and boot-server do not run the frontend's loop;
  Python must start with CREATE_NO_WINDOW and its output piped to `zakuro.log`; the save Load list may read every slot
  while browsing, so the side file must be applied on every open-for-read of a save (or at its parse), with a T5 case
  that browses first; `last.json` (the page's last choices) is written into the data folder even with Randomizer off
  (for the owner under PLAY.bat that is his own `%APPDATA%\zakuro`; tests keep it under `build/`); a check that a
  patched placement's class and items read back as the intended Job/Item after units are made.

---

## 12. Round 51 build results (2026-11-20)

Built what section 9 puts in round 51 (R2, F1, F2, T2, T4, T5, T6), with the four review fixes above. Nothing is
committed in the main repo; engine/zakuro branch `fe14` = `c856685` + patches 0001-0010 (`engine.py apply`: "fe14 =
c856685 + 10 patch(es)").

### What was made

| Piece | Where | What |
|---|---|---|
| Core wiring | patch 0008 (zakuro-core: new `fates_rando_session.rs`, `fates_rando_file.rs`; `fates_rando.rs`, `lib.rs`, `services/fs.rs`, `kernel/svc.rs`) | `System::run_frame` calls `fates_rando_session::after_frame` after each frame (read only; nothing for other games), so headless runs and boot-server have it too. At the mode pick: windowed, the page answers; headless, the answer comes from boot-server's `rando-answer FILE`, else `FEF_RANDO_ANSWER`, else Randomizer off. Then Python `make --patch-out` (works in `build/rando-make/<id>/`, copied to `<data>/rando/0004000000179800/runs/<seed>-<8hex>/`), the guard, all cells or none |
| Python hidden (fix 2) | `python_command`, `run_hidden` | `CREATE_NO_WINDOW` (0x08000000), stdin closed, output piped line by line to `zakuro.log` as `rando.py: ...`; killed past 120 s (`--version` probe 5 s). Python: `FEF_PYTHON`, `py -3`, `python`. Tool: `FEF_RANDO_TOOL`, else `tools/randomizer` up to 7 folders above the exe |
| Saves (fix 1) | `save_opened_for_read` in the file service | each open-for-read of a save (Chapter0..2, Map0.bak, Map1.bak) lays that save's run or puts the original tables back, only while GameConfigData+0xB is 1 (title, not inside a chapter); same run again = nothing written; missing run folder = original with a notice. A write+close or a rename onto a slot writes or removes `slots/<save>.json`. Save states: `<state>.rando.json` |
| Placement files (fix 4) | `read_file` overlay + `kernel::svc::dispatch` fallback | a patched copy is served inside the read when it fits the original stored size (r50all: 4 of 101 files); otherwise (97 of 101, size only, 0 guard failures) the cells are laid in memory at the first system call after the game stores the file. T2 and T6 show this comes before the units are made (A000 at frame 13445, A008 at 2843) |
| Page | patch 0009 (crates/zakuro: `rando_page.rs`, `rando_link.rs`, `menus.rs`, `lib.rs`, `settings.rs`; Cargo.toml + lock: `serde_json`) | `RandoForm` with every row of section 6; the page joins `Menus::over_game()` (game paused while it is open); "Making the game from seed X", then the core answers; on failure: Back to the settings / Play the original game. Esc menu: **Randomizer**, read-only **This run** (on/off, seed, options not at default, Open spoiler log, notices). Opens only with a window (`set_interactive`); headless never opens it and skips the schema probe. `last.json` is written only when a randomized game starts. Also: `--headless` now plays back `ZAKURO_REPLAY`; the old failing test `settings::a_first_run_has_the_fates_port_picks` (since 0006) is fixed |
| Boot reads, load vs new game | patch 0010 (core), found by the first T5 pass | (1) a slot read before GameData exists (the game reads its slots once at boot) does nothing, so no false "tables are not the original's" notice at every boot; (2) a mode-word change at most 2 frames after a save-slot read is a load, not a new game (a slot-1 save made right after the avatar screen used to be taken for a mode pick and put back to the original) |
| boot-server | `tools/harness/patches/zakuro-server/src/main.rs`, built with `build.py --server` | `rando-answer PATH`, `rando-status`, run-aware save/load slot and file. Old server kept in `build/rando51/old-server/` |
| Exe | `engine.py port`, below normal | `play/game/Fire Emblem Fates.exe` 143,967,744 bytes, sha256 b3b1f62a..., zakuro_head 3bd39dd, 10 patches. Backups in `build/backup/`: `*.2026-11-20-pre-rando` (the program before the randomizer, sha 2736a85d...), `*.2026-11-20-r51-d800dae`, `*.2026-11-20-r51-28e34d2`, and the 2026-11-10 one, each with its `build-record.json` |

### Tests

| Test | Result |
|---|---|
| U2 `cargo test -p zakuro-core --lib` | **174 passed**, 0 failed, 0 warnings (159 in round 50). New: Python window flag, page JSON, test hook = page, every save read lays its run or the original, another mod's tables refused, side files through saves and states, LZ11 and IS .bin round trips, placement patch on a buffer = the in-memory apply, boot read does nothing, a load is not a new game. check_all row `rando-ingame-core` (slow, weekly) |
| `cargo test -p zakuro --lib` | **79 passed**, 0 failed, 2 ignored (the sound test needing a ROM; the real-tool schema test, which passed with `--include-ignored`); 17 rando tests. check_all row `rando-ingame-page` (slow, weekly) |
| Headless frontend (`build/rando51/run_test.py`, a copy of the exe, `--headless N --mute`, data/APPDATA/LOCALAPPDATA/TMP under `build/rando51/`) | t-title: first-run defaults as in round 47, no randomizer activity. t-seed (`{"randomizer": true, "seed": "r51t"}`): mode pick at frame 4019, rando.py hidden (9 checks PASS), 255 cells laid, run folder with patch.txt, options.json, spoiler.txt, plan.json. t-off: answered off, no rando folder. Same again on the final exe |

### Robot (headless boot-server under `build/rando51/robot/`, 2 lanes, recorded routes only; `build/rando51/robot51.py`; results `t2t6.json`, `t4t5.json`, `t5full.json`, first pass `*-v1.json`)

| Test | Result |
|---|---|
| **T2** new game = mod (bt-prologue, seed r50all, everything on) | **PASS.** GameData in memory at frames 4600, 13460, 16992, 17460 = the installed mod's rebuilt GameData: 0 plain-byte and 0 pointer differences over 126,600 bytes, 578/578 cells new. The Prologue's 30 units (class, items and uses, skills, level, position, HP, bases, growths) identical to the installed-mod run at 13460, 16992, 17460. A000 laid at a system call (frame 13445), 11/11 cells, nothing else changed. The game's slot-1 save wrote `slots/Chapter0.json`. States: `.rando.json` names the run; loading an earlier state gives the original tables; loading back restores the run |
| **T4** off = original | **PASS.** Old boot-server (Nov 13), new with no answer, new with an explicit off: all memory sections equal at 4600, 13460, 17600, 47600 on bt-prologue (the `meta` section, build and server info, left out), save files byte-identical, no rando folder; the bt-ch2 load route equal too |
| **T5** save and reload | **PASS.** r50shops (Shops + Castle rewards only) to the slot-1 save at 47400: 155/155 cells, `Chapter0.json` names the run, saves and units = the original run. Randomized slot loaded after browsing the Load list: 155/155 cells at 3000 and 5117. Original slot loaded after a randomized slot was browsed: original tables, 0 differences. r50all's slot-1 save loaded from the title keeps the run, 578/578 ("a load, not a new game"; FAIL before patch 0010) |
| **T6** battle save (opt-ch8-set Map0.bak + a side file laid by the test, opt-ch8-reload presses) | **PASS.** GameData 578/578 from frame 1000; A008 laid after the load (frame 2843), 48/48 cells; the control run without a side file = original. The battle save's units keep their saved class and items; only their Person-row bases and growths follow the tables (by design) |
| **T7** the page | **owner.** No test opened it in a window |

Rules: `build/STOP_ROUND` checked before every build and run; every game start headless; `play/game` never started;
no window appeared; no new play, no cheat save; the owner's %APPDATA%\zakuro unchanged (settings.toml 2026-11-10, no
rando folder); every process started has exited.

### Still open

- T7: the owner's look at the page in a window (steps in docs/REPORT_2026-12-25.md). Nothing counts as done until he
  says ok.
- The Esc **Randomizer** window has only **This run**; section 6's "next New Game's settings" there is not built.
- The full-seed reload is checked right after the load; the recorded bt-ch2 presses do not fit a randomized game
  further on, so a placement load from that save was not reached (T6 covers a placement after a load).
- Classic and Phoenix are not recorded (the routes pick Casual); all three go through the same code.
- Installed-mod side (PLAY RANDOMIZED, not this page): in the mod run one label reads `033_MyCastleeeeeeee` in memory
  instead of `033_MyCastleDefense`; the rebuilt file is right, so the mods tool's LZ compressor and the game's
  decompressor disagree on one back-reference. Needs its own fix.
- Headless only: the first make of a seed runs Python inside a frame (up to 120 s); robot timeouts allow for it.

## 13. Round 58 results (2026-11-20)

- **Patch 0013** (the Seal edition): `fates_rando_game`; the page shows for Seal; the core activates Seal's tables
  before planning. Headless smoke: Seal everything-on laid at the mode pick, 81/81 guards, 2260 GameData cells.
- **Patch 0014**: during a battle-save load from the title, +0xB drops to 0 for one frame and the mode word
  changes as it returns to 1, which the new-game watch took for a New Game. The watch now needs +0xB at 1 in the
  frame before too. After the fix every reload keeps the run (0 of 1893 GameData cells wrong).
- **Patch 0015**: placement files with class/item label pointers always take the in-memory path. Re-checked at
  A004, X015, R019, X007: all placement cells laid, joiners armed.
- **Normal game unchanged:** randomizer off, 45 of 45 memory hashes equal to the pre-sofrando exe.
- **Builds and undo:** play/game exe now has 0001-0015 (sha 2b9b30ce...), boot-server 081cee93.... Backups in
  `build/backup/`: `*.2026-11-20-pre-sofrando` (before 0013), `*-pre-r58fix`, `*-r58-0014a`, `*-r58-0014`.
- **Grey rows** after round 58: character shuffle (and its rows), music, Nuzlocke, enemy levels, tougher bosses,
  one rank higher. Round 59 (E1, OK'd) turns on the shuffle's "keep the face" look and music; Nuzlocke waits for
  E2; one rank higher for its robot check (T1). Check results: docs/RANDOMIZER.md section 12.

## 14. Round 59 (2026-11-21)
- **Un-greyed rows:** character shuffle ("keep the face"), music, Enemy levels up and Tougher bosses (patches
  0016/0017).
- **Recolour:** battle hair and face-data colour with the shuffle (0019).
- **Background make and the owner's agency rule:** 0020. The page shows "Making your game... N%" while Start waits.
  The table cache is in build/rando-cache, never in the data folder.
- **The Seal edition's mod person files:** served under their own name (0018), padded to the mod's size (0021).
- **Still grey:** the full swap look (E3/E4), Nuzlocke (E2) and "one rank higher". The Recolour and Boss copies rows
  are not built.
- **Results:** docs/RANDOMIZER.md section 14 and docs/REPORT_2027-01-02.md.

## 15. Round 70 desk plan for the page (2026-11-24, track swap; no build)

The full plan, with the code reads behind it, is docs/rando/FULL_SWAP_PLAN.md. In short, for this page:

- **Esc menu, next New Game (round 71).** The Esc menu's Randomizer window keeps "This run" (read only) and gains a
  "Next New Game" part under it: the same rows and sections as the New Game page, the same help line, buttons
  **Keep for next New Game**, **Defaults** and **Randomize everything**, no Start, and at its top the grey line
  "These never change the game you are playing." (Grok: same rows, line at the top). It is hidden while the New
  Game page is open. Keep writes `<data>/rando/last.json` through a shared `write_last`, the same file and format
  `answered` writes. Unlike `answered`, it also writes when Randomizer is off. It then resets the early background
  guess. Code: `rando_page.rs` (`draw_this_run(ctx, data)`, `keep_next`, `write_last`, rows drawn under
  `push_id("next")`, robot targets prefixed `next:`), `lib.rs` (passes the data folder), `pagebot.rs` (one step
  that opens the window). `menus.rs` is unchanged. Counted 2 h 00 (estimate).
- **Help text fits (round 71).** "Randomize everything" writes one line ("turned on N settings. This run lists
  them after Start.") in place of the 4-line list of round 62b. The help line becomes a fixed two-line box (a
  `LayoutJob` with `max_rows = 2`, an ellipsis, and the full text on hover), so the buttons never move. Counted
  30 min (estimate).
- **Presets and share code (round 74, not 71).** The schema gets a `presets` list (Grok's **Light** and **Wild**).
  The page draws one button each in Basics. A **Share code** field with Copy and Paste sits under the seed row
  (not the seed box). Its codec is a pure function in `rando_page.rs` with a Python twin in `ingame.py` and one
  shared test-vector file. Counted 2 h 10 (estimate).
- **Growths in Preparations (round 71, cut first).** On the **Y** button. No Preparations menu reads Y: every
  `sortie` item uses the empty `BasicMenuItem::YCall`, and dispatch goes through `BasicMenu::Input` 0x004F9FB4.
  Select and Tab stay the growth key on the battle map. Code: `fates_growth_view.rs` (`prep_shown`,
  `filter_input` takes Y only there). Counted 1 h 45 (estimate).
- **Full swap look row.** It stays fixed at "Keep the face" until round 75's four-chapter rule passes (FULL_SWAP_PLAN.md
  section 3). If the full swap breaks faces, models or menu names in one of the four chapters, the row stays
  fixed with the reason named (Python only, `PAGE_FIXED` / `PAGE_REASONS`). If it breaks only the dialogue there,
  that chapter keeps the old names, and the row's help says so.

## 16. Round 81 side look R1 (2026-11-25, report only; F-066): Normal + Classic never opens the randomizer (fixed in round 81b, F-067)

**In plain words.** If you start a New Game on **Normal difficulty with Classic**, the randomizer (and the Nuzlocke
start, which hangs on the same moment) does not lay its game today: the port does not notice that New Game began.
Casual, Phoenix, and Hard with Casual are seen working (Hard with Classic was not tried). Nothing was fixed in round 81 (plan call 6); a fix is its own later
change, with your yes first.

- **Why** (build/r81/options/OPTIONS_TRACE.md section 6): `NewGameWatch` (fates_rando.rs, `after_frame`) fires when
  `GameConfigData` word +0x4 changes while no game is loaded. `StartFromBeginning` sets the Tutorial bit and clears
  0x80, 0x4000 and bits 29/30; after `Reset` (0x00011E5E) those are already so for Normal + Classic, so the word does
  not change.
- **Robot look** (build/r81/p45/recon-r1.json, staged boot-server 2db29775, a queued randomizer answer on both
  runs): route **bt-newgame-classic** (Normal + Classic): word +0x4 0x00011E5E at every frame from 3900 to 4590, no
  "New Game mode picked" line, no run laid (the answer was made in the background and never used). Control route
  **new-game** (Normal + Casual): "New Game mode picked at frame 4019", run laid 6 ms later, word +0x4 0x40015EDE.
  The round-81 P2 runs also saw word +0x4 unchanged at the Normal + Classic pick while the new Options writer, which
  traps `StartFromBeginning` itself, fired there once.
- **Other modes** (round-81 P2 A runs, randomizer off, build/r81/p2/A-*): "New Game mode picked at frame 4019" appears
  on Normal + Casual, Normal + Phoenix and Hard + Casual, and not on Normal + Classic. Hard + Classic was not run.
- **A possible fix later:** signal the pick from the same `StartFromBeginning` trap round 81 added (patch 0040)
  instead of the word change. Not built; the randomizer's output and every seed fingerprint are unchanged.

### 16.1 Round 81b: fixed (2026-11-26, patch 0041, F-067; installed)

**In plain words.** A New Game on **Classic** now starts the randomizer (and the Nuzlocke start) like Casual and
Phoenix do. The port now also listens to the game's own "start from the beginning" step, the same step round 81's New
Game defaults use. There is no new switch on the page. If the port ever cannot see a New Game, it says so on screen
once: "This New Game did not use your seed." (and, where Classic New Games cannot be seen at all: "Classic New Games
cannot start the randomizer in this setup; pick Casual or Phoenix."). The randomizer's output is unchanged: every seed
gives the same game as before.

- **The fix** (docs/ROUND81B_PLAN.md D1-D4, patches/zakuro/README.md row 0041): round 81's trap word over
  `StartFromBeginning` 0x001D0618 is now laid while a New Game row is set **or** the randomizer listens (Fire Emblem
  Fates with the randomizer on; the Seal edition did not listen, so Seal at the defaults laid no trap: that was the
  Seal + Classic gap round 82 found, fixed in round 82b, section 16.2). At the trap the
  same checks as round 81 run; when they hold, the randomizer takes the pick in that frame. A pick is the old watch
  firing **or** the step heard, at most one per frame; a watch within 2 frames after a heard pick is the same New Game.
- **Found on the way:** on Hard the mode list has only Casual / Classic and the cursor starts on Classic. So route
  `bt-newgame-hard` (no mode press) plays Hard + Classic, and `bt-newgame-hard-classic` plays Hard + Casual (its
  DOWN wraps to Casual). On Hard + Classic the word +0x4 does change (0x00011E5E to 0x00011E1E), so Hard + Classic
  was never broken; only **Normal + Classic** was. Round 81's "Hard + Casual" runs used `bt-newgame-hard`, so they
  were really Hard + Classic.
- **Proofs** (staged program c2791862, every game headless and self-exiting, own folders under build/r81b/; the
  owner's saves and settings.toml hashed read-only before and after each set: unchanged):
  - P1 smoke 8/8, memory compare equal, baseline equal; seed fingerprints all 6 the same.
  - P2 (build/r81b/p124): Normal + Classic (`bt-newgame-classic`): word +0x4 stays 0x00011E5E, the log says the step
    was heard at the trap, then exactly one "New Game mode picked at frame 4019", the run laid; the run id
    (r81bp2-12248cf4) and its 4 run files equal the same answer's on Normal + Casual. Hard + Classic
    (`bt-newgame-hard`, bytes GameUserData +0x28 = 01, +0x2D = 01) and Hard + Casual (`bt-newgame-hard-classic`,
    05 / 01): one pick each, same run id and files. Pictures SEEN: the Hard and Classic cursors and the avatar creator.
  - P3 (build/r81b/nodouble): Normal + Casual, Normal + Phoenix and `bt-newgame-hard` with one answer on the staged
    and on a copy of the round-81 program: one pick at 4019 on each, run r81b-73bdc732 with byte-equal run files on
    all 6 runs.
  - P4: a Nuzlocke answer on Normal + Classic: exactly one "Nuzlocke game ... started" line, its graveyard file made.
  - P5 (build/r81b/loads): a chapter save (bt-ch2) and a battle save (opt-ch8-reload) load with the randomizer on: no
    pick, no warning, memory equal to the round-81 program's at every point except the trap word, saves equal.
  - P6: Normal + Classic with all four New Game rows set and a randomizer answer: one writer line, one pick, the run
    laid.
  - P7 (Seal at the defaults): no trap; memory equal to the round-81 program's at every point, trap word included.
    The Seal row-set run was not repeated (round 81's P6 covers it; the writer is unchanged).
  - P8: the page robot (scenario quick) on Normal + Classic: the page opened at the pick, its answer was laid
    (verdict PASS, build/r81b/p8).
  - The two warning lines were not reached in a game (a headless refusal needs a memory poke); they are proven by the
    unit tests only.

### 16.2 Round 82b: the Seal edition + Classic fixed too (2026-11-26, patch 0042, F-069; installed)

Moved to docs/seal/RANDOMIZER_SEAL.md in round 84 (the Seal edition only).
