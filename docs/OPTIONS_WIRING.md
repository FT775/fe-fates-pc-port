# Options wiring: how a switch on the PC options page would reach the game

**In plain words.** The PC options page (Esc, then **FE options**) only writes a small text file
today. Nothing in the game reads that file yet. Four of the switches are settings the game already
has on its own options screen: the danger zone, the HP bars on the map, the battle animations and
the map movement speed. Those four need no new game code. They need one small piece that copies
your choice into the game's own settings each time you **load a save** (and when the game resets
for a new start), and a second small piece that makes sure your **saves keep the game's own
setting**, suspend saves included, so turning a PC switch off later leaves your saves exactly as
the game made them.

- Leaving a switch at **"The game's choice"** (the default) means nothing is written, ever.
- If the file is missing, damaged or unreadable, nothing is written. The game behaves as it does
  today.
- If you change one of these four on the game's own options screen while playing, your change
  wins until the next load, and that is what your save keeps.
- Anything that is not one of the game's own settings (growth numbers, forecasts, vein marks, the
  run switches) needs new code that draws or changes something. Those switches wait, as before.

Nothing here has been built. Turning it on needs three engine builds, each with your OK. The list
is at the end (section 10), in order, with how to undo each one.

Status 2026-11-13 (wiring stage, daytime; revised after review: the versus copy and the boot
`Reset`, sections 1, 3, 4). Design only. No Zakuro, cargo or `engine.py` build was
run and no patch was applied to the real engine. Facts are from docs/MENUS.md (the game's code, read
only); Grok's OPTIONS_V1, OPTIONS_V2 and OPTION_HOOKS were checked against it (section 9). Tags:
**[high]** read in the game's code or checked by a script, **[med]** good evidence, **[low]** a
guess, **[not read]** a name only.

---

## 1. The facts this rests on (docs/MENUS.md)

- The game keeps its options in one block, `GameConfigData`; the global `G_GameConfig`
  (0x006DA0F8) holds a pointer to it [high].
- The four lines that matter here are one byte each [high]:

  | Byte | Line | Values (what the game's code does with them) | Game's reset value |
  |---|---|---|---|
  | +0x8 | battle animations | 0 = every fight on the map; 1 = the battle picture; 2, 3, 4 = the picture only for some armies or units (which ones is not traced) | 1 |
  | +0xC | game speed | 0 = map movement never fast; 1 = always fast; 2 = fast while A is held | 2 |
  | +0xD | enemy-phase skip | read by the map sequence's AI steps; what each value does is not read | 0 |
  | +0xE | danger zone | **every value draws** (corrected round 38, OK A T3): `Danger::Add` picks its move-search flags from it (0 -> 0x50000, 2 -> 0x30000, else 0x10000) and `Panel::Danger::SetVertex` draws for 0 and 2 with one loop and colour pair, for 1 with a second loop (0x00391704) and another colour pair; no value hides the zone, and T3 saw 1 draw the same picture as 0 on its map. What the three values change on screen is not traced | 0 |
  | +0x16 | HP bars on the map | 0 = hidden; not 0 = shown | 1 |

- The block is written into **every game save** (`GameUserData::Serialize` calls
  `GameConfigData::Serialize`, 20 bytes: a version byte, the word +0x4, then +0x8 .. +0x16) and read
  back on every load (`GameConfigData::Deserialize`) [high]. Loading a save loads its options.
- The game asks the block at the moment it needs it: the battle-picture choice once per fight in
  the battle sequence's constructor (and the L button still flips it, and a unit's "always" or
  "never" flag still wins); the movement speed every time something moves (`IsSpeedFast`); the HP
  bar every tick (`map::Actor::Tick`); the danger zone when the zone is rebuilt or redrawn [high].
- **The battle-animation byte +0x8 has two readers, not one** [high, docs/MENUS.md sections 2 and 3]:
  `IsDetailBattle` for a fight, and `IsDetailSupport` for a support or a dance (the battle sequence's
  constructor asks `IsDetailSupport` instead when its flags bit 2 is set; `map::SequenceDance::Create`
  asks it too). `IsDetailSupport` uses the same per-unit rule on +0x8, but a unit counts only when
  option bit 1 (support pictures allowed, word +0x4) is also on, and a unit with the "no support
  picture" flag turns it off. So `animation_skip` changes supports and dances as well as fights:
  byte 0 puts all three on the map; byte 1 asks for the picture, and a support or dance then shows it
  only when bit 1 is on (the PC page never touches bit 1). Grok review 5 #2.
- Changing a line on the game's own screen goes through the line's `SetValue`; the danger-zone
  line's `SetValue` also rebuilds the zone (`Danger::Update`, a writer) [high].
- **The block is not the only `GameConfigData`.** The versus data (`versus::Data`) holds its own
  copy at +0x12AC (docs/MENUS.md: "the versus mode keeps its own copy"). Every direct call to the
  three functions the wiring overrides, found by a scan of `code.bin` for `bl` to them and read
  2026-11-14 [high]:

  | Function | Caller (call site) | On which block |
  |---|---|---|
  | `Reset` 0x001D06DC | `GameConfigData::GameConfigData` (ctor, 0x001D0790) | `this` (any new block) |
  | | `GameConfig::Initialize` (0x00179FD0), boot | the newly allocated global block, **before** its pointer is stored in `G_GameConfig` (0x00179FE4) |
  | | `MainSequence` `ProcSequence::GameReset` (0x001B6CF0) | `*G_GameConfig` |
  | | `versus::Data::Data` (ctor 0x001D0778 call at 0x004C5214, then 0x004C5240) | the copy |
  | | `versus::Data::FromGame` (0x004C5134) | the copy |
  | `Deserialize` 0x001D0374 | `GameUserData::Deserialize` (0x001B3A1C), save load | `*G_GameConfig` |
  | | `versus::Data::FromGame` (0x004C51BC) | the copy, from a stream the **global** block's `Serialize` just wrote (0x004C51A4) |
  | | `versus::Data::Deserialize` (0x004C50DC) | the copy |
  | | `versus::Data::ConfigToGame` (0x00543D0C) | `*G_GameConfig`, from the copy's `Serialize` (0x00543CF0) |
  | `Serialize` 0x0050AEA0 | `GameUserData::Serialize` (0x005098B4), game save | `*G_GameConfig` |
  | | `versus::Data::FromGame` (0x004C51A4) | `*G_GameConfig`, into a memory stream |
  | | `versus::Data::ConfigToGame` (0x00543CF0) | the copy |
  | | `versus::Data::Serialize` (0x0050AE5C, falls through into `GameConfigData::Serialize` with `this` = the copy) | the copy |

  `GameBackup::Serialize` (0x00179A5C) builds a `versus::Data` on its stack
  (0x00179ECC), calls `FromGame` (0x00179ED8) and `versus::Data::Serialize` (0x00179EE4). **Corrected
  round 38:** it does that only for backup type 7, the Versus files (`data:/Versus0` .. `Versus4`,
  `GameBackup::GetFileName`'s table at 0x006DA080); `GameBackup::Serialize` switches on the type
  byte (+0x4, nine cases, 0x00179A84). The battle save on the map (type 4, `ext:/Map0.bak` /
  `Map1.bak`) and the chapter save (type 3, `data:/Chapter0` ..) take other cases; OK A T5 saw the
  battle save run one `Serialize` on the global block and nothing on a copy. So a Versus file write
  runs `Reset` three times, `Serialize` twice and `Deserialize` once, not every suspend save. `StartFromBeginning` (0x001D0618) calls none of them and touches only the flag word +0x4, not
  the four lines [high]. Who calls `ConfigToGame` is [not read].

## 2. The path, end to end

```
Esc > FE options (Zakuro page, tools/zakuro-options)
   |  writes only when you change something; temp file, then rename
   v
fe14-options.txt   (config/game.json port.options_file; path given by FE_OPTIONS, else FEF_OPTIONS)
   |  read by the readable library (inside the game's process), never written by it
   v
apply hook W1, after the game's own Deserialize / Reset          (section 3, 4)
   |  hands the lines you set to the writers stage's writer config_write_options
   |  (gate name "config_options"), which sets them the way the game's own screen does;
   |  nothing for "the game's choice"
   v
the game's own code reads its own block: picture or map, speed, bars, danger tiles
   |
   v
save guard W2 = the game's Serialize, writing the game's own value for the lines you set (section 5)
```

The page and the library never talk to each other directly: the file is the only link. A change
on the page is picked up at the next apply point (section 3). The library reads the file at each
apply point (a few times per play session, a file of a few hundred bytes), so no restart is
needed and nothing is rebuilt.

**Why this way, and not another.** Three ways were weighed:

| Way | What it does | Verdict |
|---|---|---|
| A. Apply into the block (this design) | after a load or game reset on the global block, store the chosen byte into the game's own block; the game's own code does the rest | **chosen**. One writer of 1-byte stores, at two rare moments, with a known end state ("the same as if you had picked that line on the game's screen"), which the robot can check against the game doing it itself |
| R. Change the readers' answers | override `IsSpeedFast`, `IsDetailBattle` and so on to answer from the file, never storing | rejected as the main way. It covers only speed and battle pictures: the HP bar and the danger zone read the byte inside functions that also write (`Actor::Tick`, `Danger::Add`, `SetVertex`). The game's own screen would then show one value while another is used, and every live compare (F-018) would report these readers as mismatches whenever a switch is on |
| Z. Zakuro writes the byte | Zakuro's per-frame overlay hook (patch series 0004, `GameOverlay::frame` gets the game's memory) or a cheat line pokes the byte every frame | rejected. It cannot tell a load from any other frame, so it would fight the game's own screen every frame; it sits outside the undo log, the gate and the capture rules; a cheat line would mean the owner's real cheat file, which is never touched; and nothing keeps the saves clean |

## 3. When a value is applied

| Moment | Applied? | How |
|---|---|---|
| **Save load** | yes | W1 runs right after the game's own `GameConfigData::Deserialize` (0x001D0374) has filled **the global block** from the save (`GameUserData::Deserialize`, 0x001B3A1C; and pushed the volumes to the sound system, which W1 never touches). `versus::Data::ConfigToGame` (0x00543D0C) also deserializes into the global block, from the versus copy: W1 treats it as a load too, so `own[]` then comes from that copy [med: its caller is not read] |
| **Game reset** | yes | W1 runs right after `GameConfigData::Reset` (0x001D06DC) when `Reset` is called on the global block: `MainSequence` `ProcSequence::GameReset` (0x001B6CF0) [high]. Round 38 (T4 trace with the caller): the game runs `GameReset` **twice before the title** on every boot (both W1 applies of a new game, and the first two of every load route, have lr 0x001B6CF4); a save load adds one apply from `GameUserData::Deserialize` (lr 0x001B3A20). W1 applies once per call, as designed |
| **New game** | through `Reset` or a load only | `StartFromBeginning` (0x001D0618) calls neither `Reset` nor `Deserialize` and writes only the flag word +0x4, so it neither applies nor undoes anything [high]. If a new game passes through `GameReset`, W1 applies there; if not, the first apply is the first save load. T4 shows which |
| **Boot** | **no**, by design | `GameConfig::Initialize` (0x00179F9C) allocates the block, calls `Reset` on it (0x00179FD0) and only then stores the pointer in `G_GameConfig` (0x00179FE4) [high]. During that `Reset` the block is not yet `*G_GameConfig`, so W1's block check (section 4, step 0) runs the game's `Reset` only and applies nothing: fail closed. Nothing on the title screen uses these four lines, so the first load or game reset is soon enough |
| **Inside a save** | **never** | writing a Versus file (backup type 7; round 38: not the map's battle save, type 4) calls `Reset`, `Serialize` and `Deserialize` on the versus copy (section 1). W1 and W2 act only on the global block (step 0), and W1 never applies while any `GameConfigData::Serialize` is running (step 0). A save never changes what the game is using |
| **After the game's own options screen** | **no** | your change on the game's screen wins until the next load or game reset, and it is what the save keeps (section 5). Re-applying the PC value when that screen closes (the menu's destructor `ProcGameConfigMenu::~ProcGameConfigMenu`, 0x003BBFE8, is the candidate) would make the game's own line seem stuck. It stays a possible later choice for the owner ("PC page always wins"), not part of the first build |
| **You change the PC page while playing** | at the next load or game reset | the page's text says so (patch 0002). Applying at any other moment would need a hook that runs while a map is up, where the danger zone and a fight may already have read the old value |

Only the lines you set are touched, and each exactly as the game's own screen stores it: the
writers stage's `config_write_options` (src/readable/menu/menu_config_writer.c, read 2026-11-14 by
that stage in the game's code) compares with the line's `GetValue` first and stores only a value
that differs, and for the danger zone it also rebuilds the zone (`Danger::Update`, through the
gate's logged guest call) when a map exists, as `DangerPanel::SetValue` does. **Round 40: W1 does
not use that rebuild.** W1 applies through `config_apply_options`: the same compare-then-store and
value range, but the danger line stores its byte only. A battle save's map already exists while
`Deserialize` runs (the trace: `Map::Get` answers, `G_MapImage` is set), and a rebuild there, in the
middle of the load, changed what the map start then allocated (2,554 heap bytes laid out differently,
section 15). The game rebuilds the zone itself right after the load, twice (`Danger::Update` from
lr 0x001DA1B8 and 0x00397104, in runs with and without the file alike), with the stored byte already
in place; so a battle save loaded straight onto a map still gets its zone built with the new setting
(T3).

## 4. The writers and the safety net

The writers stage (this round) built the gate and the first writer, both OFF:
`src/readable/core/fe_writer.h` / `writer.c` (the gate and its log) and
`src/readable/menu/menu_config_writer.c` (`config_write_options`, gate name `config_options`: sets
any of the four lines the way each line's `SetValue` does, refuses a value past the line's last one
before it reads or stores anything). The options wiring adds two pieces around it.

**Status 2026-11-18 (F-034): written, unarmed.** W1 and W2 are in
`src/readable/menu/menu_options_hook.c` (`config_options_hook`, `config_serialize_guard`; declarations
in `menu_writer.h`), the options file reader in `src/readable/core/options.c` (`fe_options.h`). Each
has a gate entry in writer.c's table, **armed 0** in git: `config_options_hook` (W1) and
`config_save_guard` (W2), next to `config_options`. W1 first asks its own entry, so with the
tracked table it runs the game's `Reset` / `Deserialize` and nothing else (it does not read the block
pointer or the file); W2, with no line set, runs the game's `Serialize`. Neither is an override in
git: no override marker, no registry or targets.csv row, so the shared capture library and every
library built from git have no override on these three functions and behave exactly as before. The
three override bodies that wire them are kept as text in
`src/readable/menu/options_hooks_overrides.txt`, for the OK A test tree only (section 10 item 1;
the tree also needs their three registry rows and a targets.csv refresh, and arms the three entries
there). Host test: `src/readable/menu/tests/w12_diff.py` (section 7, "host tests"). The text below
is the design the code follows; where the code had to choose, the choice is noted in the code's
header comment (the mode check comes from the gate: W1's own entry is switched on only in readable
mode; W1's record of the last apply is cleared at every apply point, so a load with no line set
leaves nothing for W2 to change).

**W1, the apply hook `config_options_hook`** (an override of `GameConfigData::Deserialize` and of
`GameConfigData::Reset`; the gate's writers are never overrides themselves, so the hook is the
override that calls one).

0. **Only the global block, never inside a save.** W1 overrides every caller of `Deserialize` and
   `Reset`, but `config_write_options` always writes the global block (`guest_ptr(ctx,
   G_GameConfig)`). So W1 first checks two things, and if either fails it runs the game's own
   function and returns, touching nothing (not the file, not `own[]`, not the gate):
   - `this` (r0) equals `*G_GameConfig` and is not 0. This rules out the versus copy (every
     Versus file write, GameBackup type 7, runs `Reset` on it three times and `Deserialize` once, section 1) and the boot
     `Reset`, which runs before the pointer is stored (section 3).
   - no `GameConfigData::Serialize` is running: W2 (which overrides it for every caller, the
     copy included) keeps a depth count around every call it passes through, and W1 refuses while
     it is above 0. Nothing read today deserializes inside a `Serialize`; the rule keeps a later
     find from changing what the game uses in the middle of a save.

   Without step 0, writing a Versus file (backup type 7, the only save that builds the versus copy;
   round 38) would run W1 on the copy: `own[]` would be recorded from the
   global block, which already holds the PC values, and the next game save written by W2 would
   carry the PC value. That is exactly the leak W2 exists to stop. Host test and T5 check it
   (section 7).
1. Runs the game's own function first (`RECOMP_ORIGINAL`, fe_guest.h) and keeps its result.
2. Reads the options file (host code, a new `src/readable/core/options.c`): only `danger_zone`,
   `hp_bars`, `animation_skip`, `anim_speed`, parsed by exactly the page's rules (patch 0002's
   `parse`: a bad or out-of-range value is 0, an unknown line is ignored, the last of two equal
   keys wins). The page and the library share one list of test lines, so they cannot disagree.
3. If all four are 0: returns. **Nothing is read from the game, nothing is stored, the gate is not
   even asked.** This is the path of every robot run and of every player without the file.
4. Remembers the game's own value of each line it is about to set (`own[line]`, in the library's
   memory, never the game's), then calls `config_apply_options` with those lines (the
   `ConfigOptionsWanted` bits and values from the table below; round 40: `config_write_options`'
   gate session and rules, but the danger byte without the zone rebuild, section 3). It keeps what
   was stored (`applied[line]`).

   | Page value | `danger_zone` (+0xE) | `hp_bars` (+0x16) | `animation_skip` (+0x8) | `anim_speed` (+0xC) |
   |---|---|---|---|---|
   | 0 | not touched | not touched | not touched | not touched |
   | 1 | 0 (drawn) | 1 (shown) | 0 (every fight on the map) | 1 (always fast) |
   | 2 | not touched (round 38: no game value hides the zone; was "1 (not drawn)") | 0 (hidden) | 1 (the picture, by the game's rule: L flips, unit flags win, supports and dances also need option bit 1) | 2 (fast while A held) |
   | 3 | (past the list: 0) | (past the list: 0) | (past the list: 0) | 0 (never fast) |

   Not offered: danger values 1 and 2 (their effect on screen is not traced; neither hides the zone) and
   battle values 2 .. 4 (their meaning is not traced), and the
   enemy-phase byte +0xD (its effect is not read). The writer itself would accept them; the page
   and the hook never ask for them.

**W2, the save guard `config_serialize_guard`** (replaces `GameConfigData::Serialize`, 0x0050AEA0;
a second gate writer, e.g. `config_save_guard`, because it writes the save stream).

- **Only the global block.** If `this` is not `*G_GameConfig` (the versus copy, written by
  `versus::Data::Serialize` in every Versus file write and by `ConfigToGame`), W2 runs the game's own
  `Serialize` untouched. It still counts the call in the depth count W1 checks (step 0).
- On the global block, it writes the same 20 bytes in the same order as the game's own `Serialize` (the readable helper
  `config_saved_record` already reproduces that order and is checked against the whole function,
  docs/MENUS.md section 6), through the same guest stream calls (inside the gate, so each store is
  logged), except: for a line W1 set, if the block still holds `applied[line]`, it writes
  `own[line]`. If the block holds anything else, you changed that line on the game's screen: it
  writes the block's value and makes that the new `own[line]`.
- With no line set by W1 it does not open a gate session at all and runs the game's own
  `Serialize`: byte for byte the game's save (T1, T5).
- If it cannot run (the gate refuses, a stream call fails), it first sets `own[line]` back into the
  block for every line W1 set (through `config_restore_options`, a gate session of its own: the same
  compare-then-store as `config_write_options`, any byte value, but the danger line stores its byte
  **without** the zone rebuild; round 38, T6), then lets the game's own `Serialize` run. The save is then clean and the PC choice is dropped for the rest of
  the session (fail closed: the game's own options win). If even that restore is refused, the save
  carries the PC value: the one residual case, made by a gate failure, and tested (T6).
- The writers stage's note in menu_config_writer.c says it plainly: once the block is set, the next
  save holds those values. W2 exists for that sentence; **the hook W1 may not be switched on without
  W2** (section "The gate" below).

**The undo log.** Every store of W1 and W2 goes through the gate (`fe_writer_store`,
`fe_writer_call`): logged with its old value first, and the whole session put back, newest first,
on any failure (a byte without a direct page pointer, a full log, an svc or interpreter escape inside
a logged guest call, a guest call that stopped). `fe_writer_undo_last` can also undo the newest
apply exactly, but only while every byte still holds what was stored (otherwise it changes nothing
and answers `FE_WRITER_CONFLICT`): that is the tool for T6 and for a future "undo the last apply"
button, not something the player needs. The older undo.c frames (H8 groundwork) are the model the
gate's log was built on; under a capture neither can commit.

**The gate.** As built by the writers stage, a writer runs only when all three hold: it is armed in
writer.c's table (`armed` = 1: a source edit, then a library build; the table is `const` in every
library build), its name is in `FE_WRITERS`, and the readable layer runs in readable mode
(`FE_READABLE=readable`). Shadow, capture and original mode never run a writer. What the options
wiring needs on top, for the integrate stage and the writers stage to decide:

- W1's hook must refuse to call the writer unless W2's writer is armed and listed too (W1 alone would
  let the PC value leak into saves);
- `FE_READABLE=readable` is one mode for every override today: in a play build it would also switch
  the 110 reader overrides from the game's answer to the readable answer. A play build (OK C) either
  stages only the options hooks and writers, or the gate gets a "writers only" mode. Until one of
  those exists, OK C cannot be asked for;
- arming needs its proofs first: T1 .. T7 below, the planted-bug rows in `check_all` (integrate adds
  them; the writers stage's `writer_diff.py` is the first), and the owner's OK for the build that
  carries the armed table.

## 5. Saves, the game's own options screen, and `keep_game_options`

- **Saves stay the game's.** With W2, a save made while a PC switch is on holds the value the game
  itself would have written: the save's own value from the last load, or the value you picked on the
  game's screen since. Turning every PC switch back to "The game's choice" therefore gives exactly
  the game's own behaviour on every save, old or new. This is OPTIONS_V1's rule "a display switch
  never marks a save" kept for the four built-in lines.
- **Versus files stay the game's too** (round 38: this is backup type 7 only, not the map's battle
  save, section 1). `GameBackup::Serialize` makes the versus copy by running
  the global block's `Serialize` into a memory stream (`FromGame`, 0x004C51A4) and reading it back
  into the copy (0x004C51BC). W2 runs on that first call (global block) and writes `own[]`, so the
  copy, and the Versus file written from it, hold the game's own values. The copy's `Reset`,
  `Deserialize` and `Serialize` run the game's code untouched (step 0 and W2's block check), and
  `own[]` is not changed by the save. A chapter save made after a Versus file is therefore still
  clean (the host test's made-up order checks it; no robot route writes a Versus file. T5's
  robot route is a battle save, type 4, then a chapter save: `opt-t5-chain2-base` / `-file`).
- **The game's own options screen** keeps working. It shows the value in use (the PC value after a
  load). A change there wins until the next load or game reset and is what the next save keeps.
- **Known limit: Zakuro save states [med].** A Zakuro save state holds the game's memory (the block
  with the PC value) but not the library's `own[]`. After loading a save state, W2 uses the `own[]`
  of the last real load, which may come from another save; the next game save could then carry that
  value for a line you set (an option value, nothing else). Fix, if wanted: Zakuro tells the library
  when a save state is loaded and W2 then writes the game's reset value or the block as it is (a
  Zakuro change, part of build B). Until then the page's help line says: "After loading a save
  state, load a save once before saving." (in patch 0002 since round 8, under "The game's own
  options"; it was promised here in round 7 but missing from the patch text). T6 checks the
  behaviour either way.
- **Known limit: W2 cannot tell a PC-applied value from the same value chosen in-game.** W2 decides
  per line by comparing the block with `applied[line]`: when they are equal it writes `own[line]`.
  If you pick, on the game's own screen, exactly the value the PC page applied (for example the PC
  page skips battle pictures, you open the game's screen, set the line to another value and back to
  "skipped"), the block again holds `applied[line]` and W2 still writes `own[line]` into the save:
  your in-game choice of that same value is not kept in the save, the save's earlier value is. The
  game in memory is unaffected (it uses the block), and the next load applies the PC value again
  anyway while the switch is on. Telling the two apart would need a hook on the line's `SetValue`
  (the game's screen) to mark the line as chosen in-game; not designed. T2/T5 must not count this
  case as a W2 failure; the page text does not mention it (it changes nothing a player sees while the
  PC switch is on).
- **The robot's save states** are made by the robot's own runs with no options file, so W1 never
  stored anything in them.
- **`keep_game_options`** (OPTIONS_V1: "remember the rows of the game's own screen across new
  games", default 0). The game already keeps options per save. This key, when added, would reuse
  both writers: W2 already sees the values the player picked in-game, so at each save the library
  would also write them to a side file next to `fe14-options.txt` (host file, never the 3DS save);
  at a game reset (W1 after `Reset` on the global block) those values would be applied the way PC values are, lower in
  priority than a line set on the page. Not on the page yet; it needs the T4 new-game route first.

## 6. Fail-closed rules

Every doubt ends in "write nothing, the game's own value stands".

| Case | What happens |
|---|---|
| `FE_OPTIONS` and `FEF_OPTIONS` unset or empty | no file: W1 stores nothing |
| file missing, unreadable, not UTF-8, or larger than 64 KB | treated as empty: nothing stored |
| a line without `=`, an unknown key, a value that is not a number or out of range | that line is 0 ("the game's choice") |
| the page is writing the file at that moment | the page writes a temp file and renames it, so the library sees the old or the new file, never half of one |
| `Reset` / `Deserialize` / `Serialize` called on another block (the versus copy in every Versus file write, `ConfigToGame`'s source) | W1 and W2 run the game's own function untouched; `own[]` is not changed |
| the boot `Reset` (`GameConfig::Initialize`, the pointer not stored yet) | `this` is not `*G_GameConfig`: the game's own `Reset` only, nothing applied; the first apply is the first load or game reset |
| a `Deserialize` or `Reset` of the global block while a `Serialize` is running | W1 runs the game's function only (depth count, step 0) |
| `G_GameConfig` is null, or the block is not in mapped memory | W1 does nothing (step 0); a store that still fails rolls the gate session back, nothing stays stored |
| the gate refuses (not armed, not in `FE_WRITERS`, not readable mode, another session open) | `config_write_options` answers `FE_WRITER_OFF`: nothing stored |
| a store or a logged guest call fails inside the session | the session rolls back, newest first: the block (and the danger tiles) as the game left them |
| a capture is recording, or `FE_READABLE` is shadow, capture or original | the gate never runs a writer in those modes: the game's own functions run |
| W2 cannot run | it restores `own[]` into the block (bytes only: no `Danger::Update` inside a save, and the save's own byte even when the screen would not offer it), then the game's own `Serialize` runs: clean save, PC choice dropped for the session; the zone keeps the tiles it was built with until the game next rebuilds it (display only) |
| W2's writer is not armed and listed | W1 does not call the writer at all (section 4, the gate) |
| the default: nothing armed (writer.c's table is `const`, every entry 0) | the game's own functions run; the page's values are stored in the file only |
| the robot, a capture session, a recapture | **no options file reaches them**: PLAY's capture session drops `FE_OPTIONS` and `FEF_OPTIONS` (done this stage, below); the harness does the same since round 8: `headless.py` `child_env` (every boot.exe of a robot run, the cheat track's stages included), `recapture.py` `replay_env` and `parallel.py`'s worker drop both names in any case (tests: headless self-test, test_parallel `OptionsEnvTests`, each with a planted removal that must be seen) |

**Done this stage (tools/play):** `capture_env` already dropped every `FE_` variable, so a stray
`FE_OPTIONS` never reached a capture; `FEF_OPTIONS` (the game's own prefix) did. It is now dropped
too (`play.py` `OPTIONS_ENV`, test `test_the_options_file_path_never_reaches_a_capture` in
tests/test_play.py: 53 tests OK). PLAY still does not set the options path for normal play (F-010).

## 7. What the robot must replay before the gate may open

All on the robot's own test game, below build/, with the owner's saves never touched. Runs that
apply an option are a separate track, like the cheat track (F-019): named `opt-*`, with
`"options": {...}` in config/harness/routes.json, scored apart, and a save they make never starts a
real-play route (the save gets a mark, as cheat saves do). A route whose options change the timing
(battle pictures, movement speed) must be recorded with those options; the 14 Birthright routes are
recorded with the saves' own options and cannot be replayed with a different speed or picture
setting, because the robot feeds inputs by frame.

| Test | What it shows | Needs |
|---|---|---|
| T0 options-screen look | the game's screen opens and closes, the eight `GetValue` readers are met live (0 mismatch, F-018), and the choice order on the screen matches the values in section 1 (so the page's words are right) | a real-play route that opens the screen and changes nothing (being recorded this round); capture library already OK'd |
| T1 off is the original | W1/W2 compiled in, armed and listed, **no options file**: (a) every Birthright route ends with the same memory hash as **the same library in readable mode without the writers listed** (byte for byte), (b) every save the routes make is byte-identical to original mode's, and (c) every byte where readable mode differs from original mode lies in dead stack below the saved stack pointer. Corrected round 38: readable mode alone differs from original mode (451 bytes on bt-ch8-pair), all of it guest stack below sp left by the original functions that readable overrides do not run (section 13, round 38). **Corrected round 40 (section 13b; not yet seen by the owner):** readable overrides spend no guest instructions, so the game's clock (`nn::fnd::DateTime::GetNow`, driven by Zakuro's tick = executed guest cycles) reads up to a millisecond earlier, and on long routes that reaches saves and memory. T1 is now: (a) unchanged; (b) every save byte-identical to original mode's after Huffman decoding, **except** bytes of a field the game stored from a `DateTime::GetNow` value, shown with the GetNow log (same number of calls, same callers, only the values differ, by at most 1 ms per call); any other differing byte FAILS; (c) a **shadow-mode** run of the same library (readers run and are compared, the game keeps the original's state and timing) ends with memory equal to original mode's except bytes below the main thread's saved stack pointer, saves byte-identical, 0 mismatches. Readable-vs-original memory is no longer compared byte for byte: clock-driven state cannot be bounded that way | a library build with W1/W2 armed (a test build, never the play build) and `FE_READABLE=readable`; owner OK A |
| T2 same as the game's own screen | for each line and value: route X sets the value on the game's screen; route Y loads the same save with the PC value. After the load and after one fight / one move / one map frame, the memory is the same except the bytes the game's screen itself writes (its cursor, sounds). **HP bars, corrected round 38:** the file hides the bars from the load, before the map's first frame, which the screen cannot do; the bars' draw buffers are then never built (section 13, round 38). For that line T2 asks: the block equal to X's, W1's store the same as `HPGauge::SetValue`'s (host test), and every other differing byte one that only drawing the bars writes (in Y still the heap's never-written fill, or heap memory those buffers would hold). **Danger zone, corrected round 40 (section 15; not yet seen by the owner):** the screen run shows the save's value on the options screen until the press, the file run shows the PC value from the screen's first frame; the line's label and help text are drawn differently, which no ordering of presses can avoid. For that line T2 asks: (a) the block equal to X's at every shot after X's press, and every save file equal; (b) from the first shot after the load (W1's apply) until the options screen draws the danger line, Y's whole 58 MB linear heap equal to the no-file run's except the option byte +0xE (W1 stored that byte and nothing else; the game's own map start with that byte changes nothing else); (c) every other byte where Y differs from X and X does not differ from the no-file run first differs after the options screen opened (never before it, never not at all), and lies in the screen's 2-D vertex pools (0x31A8xxxx / 0x31B4xxxx) or the options menu's heap objects (0x327E .. 0x3289xxxx); VRAM, DSP RAM and AXI WRAM no such byte. Anything else FAILS | `opt-*` routes; OK A |
| T3 danger zone | X turns the whole zone on, with a marker on `DangerImage.flags` and the `_b` maps: drawn with page value 1, and **page value 2 stores nothing** (round 38: no game value hides the zone; the page no longer offers "Not drawn"); a battle save loaded onto a map with a game value other than 0 (round 40: W1 stores the byte only; the game's own two `Danger::Update` calls after the load build the zone with it, section 3) | a route with X; OK A for the applied runs |
| T4 new game | the calls are read (section 1): boot `Reset` runs before the pointer is stored, `StartFromBeginning` touches only +0x4. T4 records **when** `ProcSequence::GameReset` runs (title return, new game) and shows W1 applied exactly once per `GameReset` call and once per load of the global block, never at the boot `Reset` (round 38: two `GameReset` calls before the title, so two applies there are right) | the `new-game-empty` start, a trace with the caller, and a call count |
| T5 saves stay clean | load, apply, save: the save files are byte-identical to the same route with no options file, for every save kind the robot makes. **Must include a route that makes a battle save (the map's Save, GameBackup type 4, `Map0.bak`) and then a chapter save in the same session**: both files must match the no-options route, and `own[]` / the global block must be unchanged across the battle save (round 38: `opt-t5-chain2-base` / `-file`). The versus-copy order (section 1) runs only when a Versus file is written (type 7); no route writes one, so it is covered by the host test's made-up order only, and T5 says so | `opt-*` routes; OK A |
| T6 give-ups | a planted give-up in W1 (after one store) and in W2: the block is as the game left it, the save is clean | the planted-bug build of the capture library; OK A |
| T7 picture and dice | the same fight with the picture and on the map: does the fight's result (dice, damage, experience) differ? (not traced, docs/MENUS.md section 5) | two `opt-*` routes. If the results differ, `animation_skip` is not "display only" and the page must say so |
| host tests | W1 and W2 against the game's own `Serialize` / `Deserialize` / `Reset` on made-up states (menu_diff's method), with planted bugs (wrong byte, wrong mapping, a store when the value is 0, W2's own/applied swap, a store outside a gate session, W1 without W2, **the block check removed from W1 or W2**, **the Serialize depth check removed**), and a made-up suspend save: the `GameBackup::Serialize` call order on a versus copy (ctor `Reset`, `Reset`, `FromGame`'s `Reset` / global `Serialize` / copy `Deserialize`, copy `Serialize`) followed by a game save, both outputs equal to the game's with no options | no build; offline (`check_all` rows by integrate) |

H5 and H6 of the Awakening harness (live verdicts for every override, then planted bugs caught at
90% or more) and H7/H8 (writers offline, then live under the undo log) are the reference order;
W1 and W2 are the first writers that would go through H7 and H8 on Fates.

## 8. Every OPTIONS_V2 switch

Key: **in game** = the game already has the switch; **new** = needs new code. **Build** = the
engine build each needs before it can reach the game (letters from section 10: A capture-library
run with a writer on, B Zakuro page, C play build with the readable library, D new drawing code in
that play build). Every switch also needs the page (B) to be set at all.

| Key | In game? | Readers (exist, read only) | Writer | Robot replay required | Engine build |
|---|---|---|---|---|---|
| `danger_zone` | **in game**: byte +0xE (every value draws; round 38); X toggles the whole zone. Only page value 1 (game value 0, the reset style) does anything; page value 2 is ignored | `config_danger_value`, `danger_tile_kind`, `danger_panel_is_hide` | W1 (+0xE) and W2 | T0, T1, T2, T3, T5, T6 | **Y**: B, C. "Show only while a button is held" (V1's wording) would be **new** (D) and is not offered |
| `hp_bars` | **in game**: byte +0x16; the chapter can still hide all bars | `config_hp_gauge_value`, `actor_hp_bar_shown` | W1 (+0x16) and W2 | T0, T1, T2 (one map frame, actor draw bit 4), T5, T6 | **Y**: B, C. V1's low-HP warning is **new** (D) |
| `animation_skip` | **in game**: byte +0x8 (0 .. 4), read for fights (`IsDetailBattle`) **and** for supports and dances (`IsDetailSupport`, flags bit 2; also needs option bit 1); L still flips per fight; unit flags still win | `config_battle_value`, `config_is_detail_battle`, `config_is_detail_support`, `battle_picture_choice` | W1 (+0x8, values 0 and 1 only) and W2 | T0, T1, T2 (one fight each way **and one support or dance each way**), T5, T6, **T7** | **Y**: B, C |
| `anim_speed` | **in game**, but it is the **map movement** speed (byte +0xC), not V1's "battle picture speed" | `config_game_speed_value`, `config_is_speed_fast` | W1 (+0xC) and W2 | T0, T1, T2, T5, T6; routes recorded with the speed fixed | **Y**: B, C. A faster battle picture is **new** (D); no game switch was found for it |
| `enemy_phase` | **in game**: byte +0xD (`AISkip`), the game's own Options line 6. Round 80 read its effect (1 Move: no camera glide or wait, units placed at once during any AI sequence; 2 All: the dark skip) and saw it in a robot run (MENUS.md line 52; Off 728 / Move 543 / All 418 frames for one enemy turn) | `config_ai_skip_value` | would be W1 (+0xD) and W2; not written by the port | round 80 E1 done (no writer). The port's own 2x / 4x pacing was cut in round 80 (it reached only 0.88x / 0.82x of normal time, F-065): the Helpers heading shows a help line pointing at line 6 and the Start key instead; `enemy_phase` stays in `[fates_helpers]` and nothing reads it | writing +0xD stays **Y** later: B, C |
| `keep_game_options` | the game ties options to each save already | `config_saved_record`, the `GetValue` readers | W1 and W2 plus a host side file (never the 3DS save) | T0, T4, T5, plus: change a line, save, load another save, marker before and after | **Y**: B, C |
| `growth_display` | **new** (a draw) | `Unit::GetGrow` | none (a draw only) | the status screen (no route opens it) | **Y**: B, C, D |
| `stance_forecast` | **new** | `Unit::GetDualSupport`, `Unit::GetDoubleCapability`, the gauge helper | none; must not call `CalculateDual` | one replayed pair (done: bt-ch8-pair) | **Y**: B, C, D |
| `vein_highlight` | **new** | `Unit::CanDragonVein`, the `SetDeploy` helper | none; must not call `SetDeploy`, `Done` or the vein event | one vein seen (done) | **Y**: B, C, D |
| `support_preview` | **new** | `Unit::GetRelianceLevel` | none; must not call `UpdateReliance` | one C support (done: bt-ch8-support) | **Y**: B, C, D |
| `forecast_hit` | **new** | `Side::GetSimpleHit`, the crit helper | none | one replayed forecast (done) | **Y**: B, C, D |
| `forecast_strikes` | **new** | `Side::GetSimpleTimes` | none | the same forecast | **Y**: B, C, D |
| `triangle_hint` | **new** | the triangle helpers | none; must not store the cell | the same forecast | **Y**: B, C, D |
| `vein_who` | **new** | `Unit::CanDragonVein` | none | one vein seen (done) | **Y**: B, C, D |
| `gauge_display` | **new** | the gauge helpers | none; must not call `CalculateDual` | one replayed pair (done) | **Y**: B, C, D |
| `skill_banners` | **new** | `SkillIndexProvider::GetSkillEffectName`, `HasBattleSkill` | none; must not call `ProcSkillEffect::Tick` | one skill activation in **real play** (today only on the cheat track, cheat-skill-proc, which does not count, F-019) | **Y**: B, C, D |
| `growth_mode` | **new** (changes results) | `Unit::GetGrow` | the level-up roll (`Unit::LevelUp`) | level-ups (bt-ch8), the two gates (replay-clean with planted bugs, undo log) | **Y**: B, C, D, and its own writer proofs |
| `casual_mode` | **in game as a save flag**, but its writer is not named | `DifficultyIsCasual` | the flag writer (candidate `GameUserData::SetMode`, not confirmed) | the flag writer on both save kinds, the two gates | **Y**: B, C, D |
| `death_rule` | same flag; Phoenix revives | `DifficultyIsPhoenix` | the same flag writer; `SequencePhoenix::Create` | the same, plus a reading of the revive value | **Y**: B, C, D |
| `dual_strike` | **new** (changes results) | `Unit::GetDualSupport` (bonus only) | inside `CalculateAttackSingle` | a follow-up (done), the two gates | **Y**: B, C, D |
| `dual_guard` | **new** (changes results) | `Unit::GetDoubleCapability` (bonus only) | inside `CalculateAttackSingle` | a pair (done), the two gates | **Y**: B, C, D |
| `exp_rate` | **new** (changes results) | the four `GetExp*`, `GetDualExpDamage` | `GrowSequence::Calculate`, `Unit::ExpNormalize` or `ExpSequence::Create` (not `GainExp`) | the two gates | **Y**: B, C, D |
| `gold_rate` | **new** (changes results) | none general | the general gold writer is not named | stays off | **Y**: B, C, D, after the writer is found |
| `support_rate` | **new** (changes results) | `Unit::GetRelianceLevel` | `GameProfile::UpdateReliance` | the two gates | **Y**: B, C, D |

The run switches (`growth_mode` and below) keep OPTIONS_V1's rules: a per-slot mark, the two
gates, off during capture. W1 and W2 do not change that.

## 9. Grok's notes checked

| Note | Verdict |
|---|---|
| OPTIONS_V2 "`animation_skip`: none", "`anim_speed`: none", "`hp_bars`: bar draw unnamed" | out of date: docs/MENUS.md found all three in the game's own block (section 1) |
| OPTIONS_V1 `anim_speed` = "faster battle picture" | the game's switch of that name is **map movement** speed; a faster battle picture has no game switch found. The page's label now says "Map movement speed" |
| OPTIONS_V1 `danger_zone` "1 show while a button is held" | the game draws the zone after X toggles it; "while held" would be new code. The page now offers the game's two choices |
| OPTIONS_V1 `keep_game_options` "never the 3DS save" | kept, and extended: with W2, no PC switch changes what a save holds |
| OPTIONS_V2 "a display switch never marks a save" | holds for the four built-in lines only because of W2; without W2 the block (and so the save) would carry the PC value. That is why the gate refuses W1 without W2 |
| OPTION_HOOKS "a poke of the game byte that is not restored sticks" | right, and worse than "sticks": it would land in the next save. W2 answers it |
| OPTIONS_V2 "Off is still the original game" | kept: value 0 is "the game's choice" and stores nothing; T1 checks it on all 14 routes |

## 10. Owner OKs needed, in order

Each one is a separate yes. Saying no to a later one leaves the earlier ones harmless.

1. **A: let the robot run W1/W2 switched on in its own test game.** Builds: one test library with
   W1, W2 and `config_write_options` **armed** (a source edit of writer.c's table, kept out of git
   or on a test branch, and a library build through `parallel.py build`, one at a time, below
   normal), then `opt-*` robot runs in readable mode with an options file below build/ only. A
   capture cannot run a writer (the gate refuses), so these runs are judged by memory hashes, save
   bytes and markers, not by capture records. Why: T1 .. T7 are the only proof that the writers do
   what this page says and that saves stay clean; F-017 keeps writers off until such a replay can
   catch them, so turning one on even in the robot's game is your call. Undo: rebuild the library
   from the unarmed table (`parallel.py build`, as every round does), delete the `opt-*` runs and
   saves under build/; your saves, Zakuro and the real game are never touched.
2. **B: build Zakuro with the options page** (patches 0001 and 0002 from
   tools/zakuro-options/patches; `cargo build` of Zakuro, one build, below normal, at a time you
   choose) and let PLAY set `FEF_OPTIONS` to `play/fe14-options.txt` (F-010). Why: without the page
   there is no place to set a switch. Harmless on its own: until C, the file is written and nothing
   reads it. Undo: keep the current Zakuro folder as a copy before the build and put it back, or
   reverse the two patches (`git apply -R`) and build again; PLAY's setting is one line to remove.
3. **C: the play build with the readable library** (`tools/engine/engine.py port --readable`,
   compiling 3dsrecomp's output with the options hooks and the two writers armed, `FE_WRITERS` set by
   PLAY to those two only). It can only be asked for once the 110 reader overrides can stay on the
   game's own answers while the writers run (section 4, the gate: a writers-only mode or a staging
   with only these pieces). Why: this is what makes the four built-in switches reach your game.
   Before it: A's tests all pass and the integrate stage's `check_all` rows pass. Undo: PLAY back to
   the previous standalone (keep `play/game` as a copy first), or PLAY stops setting `FE_WRITERS`
   (the gate then refuses and the game's own functions run); your saves stay the game's at every
   point (W2), and PLAY takes a save backup on start anyway.
4. **Your five-minute look** (after C): back up your save folder, use a spare slot, set "Battle
   pictures: skipped" on the PC page, load the spare save, fight once, save, set it back to "The
   game's choice", load again: the game's own setting is back.
5. **D, later and per switch: new drawing code** (growth numbers, forecasts, vein marks, banners)
   in the same play build as C, each after its own robot replay. Not needed for the four built-in
   switches.

## 11. Status 2026-12-03 (round 28, OK A): the host test could not run, so OK A waits

The owner said "Yes, OK A" (F-032, 2026-11-18 ~01:00). Round 28 started the test at 01:10 and stopped
at the first step, as section 10 item 1 and the OK A checklist require.

- **Why it stopped.** W1 (`config_options_hook`) and W2 (`config_serialize_guard`) are not written.
  Section 4 says "Neither is written yet"; F-021 calls them design only. There is no
  `src/readable/core/options.c` (the options file reader) and writer.c's table has only
  `config_options` (armed 0). With no code, there is nothing to plant the section 7 bugs into and no
  hook to run the made-up suspend save order through. The round was not allowed to write writer code.
- **What did run.** The host test of the one writer that exists, `config_write_options`
  (`writer_diff.py --plant`, host gcc, below normal): seed 1 and seed 2, each 600 cases, 0 mismatches,
  25/25 planted bugs caught. These are now check_all rows `oka-host-seed1` and `oka-host-seed2`. They
  cover `config_write_options` only, not W1 or W2.
- **Results, plainly.** Host test for W1/W2: NOT RUN (no code). T1-T7: NOT RUN. Nothing was armed or
  built (build/oka does not exist), no `opt-*` route with `"options"` was added, the tracked writer.c
  table is unarmed (git diff empty), build/harness/lib was not touched, %APPDATA% unchanged.
- **OK A's checklist is not green.** The checklist (docs/collab/OK_A_CHECKLIST_GROK.md, "What a yes
  switches on") speaks of "the options writer that is already written and switched off". That is true
  of `config_write_options` only; W1 and W2 are not written. The owner gave OK A on that wording.
- **Next.** Someone writes W1, W2 and options.c exactly as section 4 says, plus their host test with
  every section 7 plant and the suspend save order. That is new writer code and needs the owner's own
  decision (who and when). Only then: the host step, the armed build in its own tree, T1-T7.

## 12. Status 2026-11-18 (round 35, F-034): W1, W2 and the options file reader written, unarmed, host-tested

The owner said "ok, yes go ahead" (F-034, ~10:10). This step wrote the three missing pieces and their host
test. Nothing was armed, no library was built, no robot game was run for this step.

- **Written** (section 4 status): `src/readable/core/options.c` + `fe_options.h` (the page's parse, the 64 KB limit,
  never a path inside %APPDATA% / %LOCALAPPDATA%), `src/readable/menu/menu_options_hook.c` (W1
  `config_options_hook`, W2 `config_serialize_guard`), writer.c table entries `config_options_hook` and
  `config_save_guard`, **armed 0**. No override marker and no registry or targets.csv row: the three override
  bodies are text in `src/readable/menu/options_hooks_overrides.txt`, for the OK A tree only.
- **Host test** `src/readable/menu/tests/w12_diff.py` (host gcc, below normal). The game's own `Reset`,
  `Deserialize`, `Serialize` and the four `GetValue` / `SetValue` (arm_mini.py on text.bin), composed by section 4's
  rules, against the C W1/W2 through the real gate, on made-up scenarios: the boot `Reset` before the pointer is
  stored, loads, a change on the game's screen, the made-up suspend save (ctor `Reset`, `Reset`, `FromGame`'s
  `Reset`, global `Serialize` into a memory stream, copy `Deserialize`, copy `Serialize`) followed by a game save,
  a game reset, a `Deserialize` inside a `Serialize`, a save W2 cannot write (it restores and the game's
  `Serialize` runs), the file changed between steps, and every gate setting.
  - seed 20261118: 300 scenarios, 0 mismatches (W1 stored in 85, W2 wrote 77 saves itself, 9 restores, 97 nested);
    **26/26 planted bugs caught**: section 7's list (wrong byte, wrong mapping x2, a store for value 0, the
    own/applied swap x2, a store outside a gate session x2, W1 without W2, the block check removed from W1 and from
    W2, the depth check removed, W2 not counting) and more (record not cleared at a load, own[] not following the
    game's screen, no restore, choice kept after a give-up, record order, a byte left out, W1 before the game's
    function, four parse bugs, the %APPDATA% refusal removed, the gate's armed check removed);
  - seed 2: 300 scenarios, 0 mismatches (82 / 75 / 10 / 96);
  - the options file: the shared test lines `src/readable/core/tests/options_cases.json` (patch 0002's own vectors
    and more), 2,000 made-up files against a Python copy of the page's Rust parse, the 64 KB limit, %APPDATA% and
    %LOCALAPPDATA% (fake folders below build/): 2,027 files, 0 mismatches;
  - **the unarmed table**: the driver built without `-DFE_WRITER_TESTS` (the table `const`, every entry 0, as in
    every library), `FE_WRITERS` listing all three, readable mode: 300 scenarios, 0 mismatches, no gate session,
    nothing stored, every save the game's.
- **Still green**: `writer_diff.py --plant` 600 cases, 0 mismatches, 25/25; `writer_gate_test.py` 307/307, source
  checks clean; `tools/readable/check.py --selftest` readable: OK; `gen_stubs.py --check` OK (266 overrides,
  5 writers, unchanged).
- **opt-* harness rules** (section 7): `tools/harness/options_track.py` (self-test 23/23): the route rules, the
  save mark `harness-options.json` and the name `opts-*`, the refusal of an options save for any route without
  `"options"`, options runs kept out of the real-play totals; `headless.run` refuses options routes until the OK A
  library exists. docs/harness/OPT_ROUTES.md has the details.
- **Not done here** (next steps of OK A, each with its own cap): the OK A tree below build/oka/ (copy, the
  marker file, three registry rows, targets refresh, the three entries armed), its library build, the options
  file plumbing into an armed run, T1-T7.

## 13. Status 2026-12-10 (round 35, OK A side by side): not green; W1/W2 stay off

OK A ran in the robot's test game only (F-032, F-034), on two armed test libraries built in their own trees below
build/oka/ (never build/harness/lib, never git). Only `config_options`, `config_options_hook` and
`config_save_guard` were armed there. The tracked writer.c table is unchanged: every entry 0.

| Test | Result |
|---|---|
| Host test W1/W2, seed 20261118 and seed 2 | PASS: 300 scenarios each, 0 mismatches, unarmed 0, options file 2,027 files 0, clean saves 150 scenarios 0, 26/26 planted bugs caught. Gap: the "block is mapped" check is never exercised (a reviewer's plant that drops it was missed) |
| T1 off is the original | FAIL on bt-ch8-pair (stopped there; 13 routes not run): readable mode alone ends at a different memory hash from original mode (451 FCRAM bytes in 9 ranges, 0x037CACD0..0x037CBE38). Armed + writers listed = armed without writers = shared library in readable mode, byte for byte: the writers added 0 bytes |
| T2 the file does what the screen does | FAIL on HP bars: 14,787 FCRAM bytes the screen run did not write (from 0x4F80, spread up to 0x3A22028). Battle animations, game speed, danger zone: every difference is a byte the screen's own presses wrote. Map frames and cursor only, no fight |
| T3 danger zone | FAIL: `danger_zone = 2` (game byte 1) still draws the X zone, picture identical to `= 1`. The writer stores what section 5 says; the reading "byte 1 = not drawn" is wrong. Suspend-save rebuild NOT RUN |
| T4 once per reset | NOT PASSED: the boot Reset is never applied (pointer still 0); a new game applies twice before the title, +1 per load; the caller of the two is not known |
| T5 saves never carry the file's values | NOT PASSED: Map0.bak, Chapter0 and every other save byte-identical with and without the file; the versus-copy suspend path was never reached and the chain route lost its chapter save |
| T6 give-up mid-way | W1 PASS (3 plants, 3 rollbacks, memory and saves = no file). W2 FAIL: the block is restored but Map0.bak differs in 252 bytes; that save was thrown out, never loaded or packed |
| T7 animation_skip display-only | answered for two chapter 8 fights (same exp, level-up, stats and enemy count); not a proof for every fight |
| OK A checklist fully green | **NO** |

The writer gate (F-026), three numbers kept apart: (1) recordings: 0, no capture of W1/W2 was made (lines reached
in armed runs: W1's apply at loads and new game, W2's save at the battle save and its give-up under a plant; never
reached: the boot apply, the versus-copy suspend, a chapter save after a suspend); (2) host test 26/26 on both
seeds; (3) armed compare: T1 FAIL, T2 FAIL, T5 not passed, T6 FAIL (W2). **W1 and W2 stay off; W2 must not be armed
anywhere until T6 is fixed and rerun.** The page must not offer "Danger zone: not drawn" until a real-play route
sets that line to 1 on the game's own screen. headless.py still refuses options routes; the T-runs used wrappers
below build/oka/ that patch only inside their own process. Full results: docs/harness/OPT_ROUTES.md,
build/oka/results/, docs/REPORT_2026-12-10.md.

### 13a. Round 38 (2026-11-18, chapter oka-write, F-034): what was wrong, what changed

Each round-35 finding was explained, then fixed or its test corrected with the reason below. Diagnosis ran only on
test trees below build/oka/ (tree3: the fixes plus a trace with the caller and a T1 bisect switch; tree4: tree3 plus
one switch that brings back round 35's danger mapping, to replay round 35's T6 exactly), each built in its own
folder, never swapped into build/harness/lib, never in git. The tracked writer.c table is still 0 for every entry. No
OK A test was rerun as a whole here; the rerun is the next step.

| Finding | What it was | What changed |
|---|---|---|
| T1: readable mode alone ends 451 bytes from original mode | **Dead guest stack, a known harmless effect.** Every differing byte lies at 0x0E004CD0 .. 0x0E005E38 (FCRAM 0x037CACD0 .. 0x037CBE38), below the main thread's saved stack pointer (0x0E005F60 / 0x0E005F98 in the savestate, stack top 0x0E005FE0): memory the game always writes before it reads it. In original mode the overridden functions run and leave their frames there; readable overrides answer in host code and leave other leftovers. Bisect by override address on tree3: the lower half of the overrides adds 0 bytes, the upper half all 451; 14 of 16 groups of ~16 overrides each add some, 2 add none; in all 19 bisect runs every differing byte is in that dead stack (build/oka/r38/t1/deadstack.txt). Many overrides contribute, as expected for stack leftovers, so the bisect stopped at groups | **The test was wrong; T1 corrected** (section 7): armed vs the same library in readable mode without writers (byte for byte; round 35 already saw them equal), saves vs original mode byte for byte, and every byte that differs from original mode below the saved stack pointer. No code change |
| T2: HP bars via the file leave 14,787 bytes the screen does not | **History, not W1.** The file hides the bars at the load, before the map's first frame; the screen route showed them first. 4,751 of the bytes (all of FCRAM 0x4F80 .. 0x5A00, the bars' vertex data) are still the heap's never-written fill 0xCD in the file run: the bars were never drawn, so their buffers were never built. The other 10,036 are heap memory nearby (0x273B35 .., 0x370000 ..) that holds other objects when those buffers do not exist. W1's store is the byte `HPGauge::SetValue` stores (writer host test) | **The test was wrong for this line; T2 corrected** (section 7). No code change |
| T3: danger zone value 2 (game byte 1) still draws | **The design misread the byte.** `SetVertex` draws for every value (0 and 2 one loop, 1 a second loop at 0x00391704 with another colour pair); `Danger::Add` uses the byte only to pick the move-search flags. No value hides the zone | W1's mapping: page value 2 is **not touched** (`MN_NOT_OFFERED`; a file that sets only it stores nothing and asks no gate); section 1, 4 and 8 corrected; the page patch's label now says "No effect (the game cannot hide the zone)" (patch text only, no Zakuro build); `menus.h` comment on `danger_tile_kind` corrected |
| T4: no startup apply; a new game applies twice before the title | **Both as designed.** The trace with the caller: the boot `Reset` (lr 0x00179FD4, `GameConfig::Initialize`) runs before the pointer is stored, so W1 skips it; the two applies before the title both come from `ProcSequence::GameReset` (lr 0x001B6CF4), which the game calls twice there; a save load adds one from `GameUserData::Deserialize` (lr 0x001B3A20) | Design text corrected (section 3, T4 in section 7): once per `GameReset` call and once per load. No code change |
| T5: the suspend path was never reached | **The design misread the suspend save.** `GameBackup::Serialize` builds the versus copy only for backup type 7, the Versus files; the map's battle save is type 4 (`Map0.bak`) and runs one `Serialize` on the global block | Sections 1, 4, 5, 6, 7 corrected. New routes `opt-t5-chain2-base` / `opt-t5-chain2-file` (opt-* rules, from bt-ch8-support, real presses, no pokes): round 35's chain to the battle save at 74190, then the last action re-found by look-ahead (the unit at (8,6) attacks the last enemy in place), stage complete, "Save your progress?" Yes: a chapter save at 79289 in the same session. Replayed from frame 0 on tree3 in readable mode with the writers listed: both runs reach the chapter save; Map0.bak and Chapter0 (and every other save file) byte-identical with and without the file; W2 wrote both saves itself, `own[]` and the block unchanged across the battle save. The Versus-file path stays covered by the host test only (no route writes a Versus file) |
| T6: W2's give-up left Map0.bak 252 bytes different | **W2's restore rebuilt the danger zone inside the save.** Restoring the danger line through `config_write_options` calls `Danger::Update` (as the screen's `SetValue` does), which the game never runs inside a save; it changed what the rest of the battle save holds (the file is compressed, so the change spread to its last 252 bytes and its header). Proof on tree2: the same give-up with every line but the danger line gave a clean save; the danger line alone did not | New `config_restore_options` (menu_config_writer.c): the same compare-then-store, but the danger line stores its byte only, and it takes the save's own byte whatever it is (the host test then found that a save byte the screen never offers, e.g. HP bars 0x38, made the restore refuse and the next save carry the PC value). W2 uses it. Replayed on tree4 with round 35's mapping and planted give-up: Map0.bak equal to the no-file save (e229f979...); on tree3 (new mapping) W1 and W2 give-ups and the plain file run also equal. The one failed diagnosis save (tree2, danger line only) was deleted, never loaded or packed (sha256 in build/oka/r38/) |
| Host-test gap: "block in mapped memory" never exercised | the scenarios never pointed `G_GameConfig` at a block that is not wholly mapped | w12_diff.py: a step that points it at a block whose +0x10 .. +0x16 lie on an unmapped page, then a reset, load or save on it; the reviewer's plant (the mapped check removed) is now caught |

**Host tests** (w12_diff.py, host gcc, below normal): seed 20261118 and seed 2, 300 scenarios each, 0 mismatches,
unarmed table 0, options reader 2,027 files 0, clean saves 0; **32 of 32 planted bugs caught** on each (round 35's 26,
two of them re-anchored to the changed text, plus six new: danger page value 2 stored, the restore rebuilding the zone
(from W2 and from the writer), the restore refusing the save's own byte, the block-mapped check removed, the gate asked
when nothing is offered). Still green: writer_diff.py --plant 600 cases, 0 mismatches, 25/25 (two plants
re-anchored to the shared range table); writer_gate_test.py 307/307, source checks clean; tools/readable/check.py OK;
gen_stubs.py --check OK (266 overrides, 5 writers); options_track.py self-test 23/23 and --check OK (26 options routes).
**Not done here:** the OK A rerun (T1-T7 on a fresh armed tree with these fixes) is the next step; T3's X-button
route and T2's per-line reruns with the corrected rules belong to it. W1 and W2 stay off.

### 13b. Round 40 (2026-11-18, chapter oka-t1-cause): why readable mode alone changes Chapter0

No writer was involved. Everything ran in two diagnosis trees below build/oka/: tree3 (round 38's, with the bisect
switch) and **tree8t1**. tree8t1 is `git archive` of HEAD 5db2f29, so its writer table is unarmed. It adds the round-38
switch `FE_DIAG_LO/HI` and `oka_time_probe.c`, two overrides that run the game's own
`nn::fnd::DateTime::GetNow` (0x00244458) and `GetNowTime` (0x001644E8) unchanged and log what they return. Neither
tree was ever swapped into build/harness/lib or put in git. tree8t1's own library has sha fcb77b44... and
120,515,350 bytes. The shared library was 14c19839... at the start. At 18:11 another round rebuilt it from the main
tree (610f791d..., 120,500,497 bytes, harness_build.json dated 18:04:44). That rebuild was not from this round's
trees. Runs are named
`opt-r40-t1-*`. Their tools and logs are in build/oka/r40/ (t1_run.py, t1_bisect.py, t1_edge.py, savedec.py, t1/).

- **The bytes.** Chapter0 is a 0xC0-byte header, then `PMOC`, then a Nintendo Huffman (0x28) stream. Decoded
  (r40/savedec.py), the original and readable bodies differ in **exactly one byte**: bt-castle-shop body 0x143B
  (0x1E becomes 0x1D), bt-ch8-support body 0x1B98 (0x32 becomes 0x31). That byte is the low byte of a u64
  **clock time in milliseconds since 2000-01-01**: 0xAD4D50441E, 48.158 s after the robot's fixed ZAKURO_CLOCK.
  In memory it is the `GameRealElapse` object at FCRAM 0x2670678 (vtable 0x0068F62C), field +0x10, at FCRAM
  0x2670688. `GameRealElapse::Update` (0x001D16D4) stores it from `DateTime::GetNow`, and `GameRealElapse::Serialize`
  (0x0050B068) writes it into the save. The header and every other body byte are equal. bt-ch3 has the same
  Chapter0 in both modes.
- **The clock log.** Original, readable and partial-readable runs make the same `GetNow` calls, from the same callers,
  in the same order: 33 calls on bt-castle-shop, 58 on bt-ch8-support, 48 on bt-ch3. Only the values differ, and
  only around the save. On bt-castle-shop, calls 27 to 31 read 1 ms less. Call 29 (lr 0x001D16E8, `Update`) reads
  0x...441E in original mode and 0x...441D in readable mode: exactly the two saved values. On bt-ch8-support, calls 31
  to 37 read 1 ms less: `Update` reads 0x...4432 and 0x...4431, again the two saved values. On bt-ch3 every value is
  equal.
- **Why.** Zakuro's `svcGetSystemTick` returns `cpu.cycles` (zakuro-core kernel/svc.rs), and the shared page's
  clock is extrapolated from the same tick (memory/config.rs `update_datetime`). Cycles advance only for guest
  instructions the recompiled code runs (its `BLOCK_TO` budget). A readable override answers in host code
  (`FE_ENTRY`, include/readable/fe_guest.h) and spends none of that budget, so a clock read later in the same frame
  happens a few ticks earlier. Around the save on these two routes, the savings push one read across a millisecond
  boundary.
- **The bisect agrees: no override is at fault on its own.** On bt-castle-shop, scored by Chapter0:
  - Each sixth of the 269 overrides, run readable alone, gives the original Chapter0.
  - Edge search (t1_edge.py): `[0, 0x005337F1)` differs and `[0, 0x005334F1)` does not; `[0x001A80D4, 0x005337F1)`
    differs and `[0x001D0374, 0x005337F1)` does not.
  - So the change needs every override from `weapon_level_record` (WeaponLevel::Get, one load) up to
    `unit_stat_limit` together. Dropping either end removes it. That is a cumulative cycle threshold, not a wrong
    answer.
  - The prefix run `[0, 0x005337F0)` shows the threshold directly: calls 27 and 28 read 1 ms less, but call 29
    (`Update`) reads the original value, so the save is the original.
- **Readers change nothing when timing is equal.** In shadow mode the readers run and are compared, while the game
  keeps the original's results and the original's guest cycles. On tree8t1, all 9 routes round 38 ran
  (bt-castle-shop, bt-ch8-support, bt-ch3, bt-castle-forge, bt-ch2, bt-ch4, bt-ch5, bt-ch6-castle, bt-ch8-pair)
  gave:
  - every save file byte-identical to original mode's;
  - 0 mismatch lines;
  - memory hash equal to original mode's on 7 routes. On bt-ch6-castle 9 bytes differ and on bt-ch8-pair 4 bytes,
    all at FCRAM 0x37CB474 .. 0x37CB597, in the main thread's dead stack below the saved sp (FCRAM 0x37CBF60),
    left there by readable code's guest-helper calls.
- **bt-ch3's 3 bytes** (FCRAM 0x3983BDC .. 0x3983BDE) are not a clock value. In original mode they hold 0x004F63BC,
  the return address that `UnitPool::GetPlayer` pushes when it calls `Unit::IsUnique` (0x00533A80). That function
  is overridden by `unit_is_unique`, so readable mode pushes nothing and the word stays 0. It is a stale stack
  word, the same kind as round 38's. That thread's sp was not decoded, so "dead" rests on how the word got there,
  not on an sp check.
- **The clock matters to the game.** `Random::InitializeAll` (lr 0x0044AC4C) and `unit::Identifier::SetIdentifier`
  (lr 0x00418B4C) also read `GetNow`. In a control run (original mode, ZAKURO_CLOCK 1 ms earlier), bt-castle-shop's
  Chapter0 body differed in 21 bytes. On the 9 routes, readable mode never moved one of those reads. If it ever
  moves an RNG-seed read, readable mode will play differently from the recording. That would be a timing effect,
  not a reader answer, but it would break a replay.
- **The large readable-vs-original memory differences** (1.66 M bytes on bt-castle-shop, round 38's "8 routes far
  from the stack") are not explained byte by byte. Shadow mode shows they do not come from reader answers or reader
  writes. The rest of the readable-vs-original gap is guest work the overrides skip: cycles (the clock) and the
  original bodies' own stores. A partial readable run on bt-castle-shop leaves 51,526 bytes, all inside the full
  run's 1,656,950.

**Verdict: no reader is wrong. Nothing in src/readable was changed and no host-test plant was added.** T1(b) and
T1(c) were asking for something readable mode cannot give on a clock-driven game. They are corrected in section 7:
the save rule allows clock fields proven with the GetNow log, and the memory rule moves to a shadow-mode run. The
owner has not yet seen this rule change. A real fix, if one is wanted, would be readable mode charging the guest
budget the original would have spent. That is an engine and runtime design question, not done here.

## 14. Status 2026-12-13 (round 38, OK A rerun with the round-38 fixes): not green; W1/W2 stay off

What ran (2026-11-18, 13:35 to about 17:10; owner "ok, yes go ahead", F-034; report docs/REPORT_2026-12-13.md):
the round-38 fixes (section 13a), the host tests, one clean armed test library (build/oka/tree5, sha 0f731460...,
only `config_options`, `config_options_hook` and `config_save_guard` armed) plus one plant/trace copy
(build/oka/tree6, sha f930b72d..., for T4 and T6), each built in its own folder and never swapped into
build/harness/lib (sha 14c19839... before and after every step). The tracked writer.c table is 0 for every entry.
All runs are opt-* runs in readable mode below build/; no save was packed; no %APPDATA% / owner file touched.

| Test | Result |
|---|---|
| host tests (w12_diff seeds 20261118 and 2; writer_diff seeds 20261114 and 2) | **PASS**: 300 scenarios each, 0 mismatches, unarmed 0, options 2,027 files 0, clean saves 0, 32/32 plants; writer_diff 600 cases 0 mismatches, 25/25 |
| T1 off is the original | **FAIL**. 9 of 14 routes run (x4 timeouts; the first batch timed out under rounds 36/37's load). (a) armed = readable without writers on 9/9 (the writers add 0 bytes); (b) saves equal to original mode on 7/9: **Chapter0 differs on bt-castle-shop and bt-ch8-support**; (c) "only dead stack" holds on bt-ch8-pair only: 8 routes leave FCRAM differences far from the stack. A control run on the shared library in readable mode with no writers gives the same memory and saves as the armed run on 3/3 routes, so **readable mode (the reader overrides) causes it, not W1/W2** |
| T2 same as the screen | **FAIL on danger zone 2 to 0 from the file** (new opt-t2-dz0-*, from opt-ch8-set): 4,795 FCRAM bytes the screen run did not write (0xFF0000 .., 0x1A80000, 0x1B40000); block and saves equal. Likely W1 rebuilding the zone at the load where the screen rebuilds it later (not proven). Battle animations, game speed 0 and 1, danger page value 2 (stores nothing), every line at the save's value: PASS. HP bars: passes the corrected rule only by judgement against section 13a's diagnosis (not re-proven byte by byte) |
| T3 danger zone | **PASS under the round-38 rule** (page value 2 stores nothing; value 1 draws; the zone is rebuilt at a battle-save load, shown by the DangerImage redraw flag, not a call trace). The checklist's old "not drawn with 2" cannot pass by design: the owner has not yet seen the changed rule |
| T4 new game | **PASS**: boot Reset skipped (lr 0x00179FD4), one apply per `GameReset` (2, lr 0x001B6CF4), one per load (lr 0x001B3A20), none at boot |
| T5 saves stay clean | **PASS** for every save kind the robot makes: battle save, chapter save, and battle save then chapter save in one session (opt-t5-chain2-*): every save file byte-identical with and without the file; `own[]` and the block unchanged across the battle save. The Versus-file copy path (type 7) is host-test only |
| T6 give-ups | **PASS** for W1 and W2 (tree6 plants): block back to the game's, Map0.bak e229f979 and every save byte-identical to the no-file save. No undo failed, no save thrown out |
| T7 picture and dice | **answered for two chapter 8 fights**: no difference in exp, level-up, stats or unit counts; raw dice word not compared |
| OK A checklist fully green | **NO** (T1, T2) |

The gate (F-026), for W1/W2, three numbers never added together: (1) recordings on lines a recording reached: 0 (no
capture of W1/W2 was made; lines reached in armed runs: W1 at loads and at `GameReset`, W2's battle and chapter saves
and its give-up; never reached, not failures: the Versus-file copy path, a danger byte other than 0 stored on the T5
routes); (2) host test: 32/32 and 25/25 plants caught on both seeds, 0 mismatches; (3) armed compare: T1 FAIL
(readable mode, not the writers), T2 FAIL (danger zone line), T5 PASS, T6 PASS. W1/W2 are not at the gate and stay
off.

Next (owner's calls): T1 needs either the reader override that changes Chapter0 on bt-castle-shop / bt-ch8-support
found (bisect by override address; bt-ch3 has only 3 differing bytes) or a writers-only mode (readers on original
answers, section 10 item 3); T2's danger line needs a diagnosis of the 4,795 bytes (or a rule like HP bars', with
the owner's yes); T3's changed rule needs the owner's look. check_all: `w12-host-seed1/2` now also require at least
32 plants (all caught); the `opt-t5-chain2-*` route inputs no longer hold newline characters.

Commit state (checked 17:13 onward): round 36's commit e9d2950 took in round 38's integrate edits to
tools/check_all.py (W12_PLANT_FLOOR), tests/test_check_all.py, the routes.json opt-t5-chain2-* fix and the round-38
notes in PORT_PLAN.md, CHECK_ALL.md and ROBOT.md. The files they depend on are still uncommitted: w12_diff.py (HEAD
has round 35's 26 plants, so HEAD alone fails `w12-host-seed1/2` against the floor of 32), writer_diff.py, the menu
sources (menu_config_writer.c, menu_options_hook.c, menu_writer.h, menus.h), this file, OPT_ROUTES.md, the Zakuro
page patch and DESIGN.md, and docs/REPORT_2026-12-13.md (not yet written to disk). The next integration commit must
take all of them together.

## 15. Round 40 (2026-11-18, chapter oka-t2-danger): T2's danger line 2 -> 0 explained; W1 fixed; rule corrected

Round 38's T2 left 4,795 FCRAM bytes on the danger line (save value 2, file `danger_zone = 1` = game byte 0) that
the screen run (RIGHT on line 7 at 3650) did not write. Everything below ran on the robot's test game only, in
readable mode with the three entries armed, on diagnosis and test trees below build/oka/ that were never swapped
into build/harness/lib and never put in git: **t40d** (tree6 + trace overrides on `Danger::Tick` / `Update` /
`Add` / `SetVertex` and a trace line in `config_set_danger`), **t40e** (tree6 + a switch that makes W1's danger
store skip the rebuild), **t40f** (tree5, the clean armed tree, + this round's fix; library sha 7ab7da2b...). The
tracked writer.c table is unchanged (every entry 0, sha 7457c6b8...). Tools and results: build/oka/r40/
(oka_dump.py keeps the per-frame memory dumps, t2_danger_rule.py, t2_danger_rule.json, an_f.py). Note: tree7
(this round's first diagnosis tree) was overwritten by another round at 17:47 and is not used
(tree7/WARNING_SOURCES_OVERWRITTEN.txt). The shared library changed from 14c19839... to 610f791d... at about
18:11 by another round's rebuild from the main tree, not by this one.

**What the 4,795 bytes were (frame-by-frame dumps of the whole 58 MB linear heap, file run vs no-file run):**

- Up to 2840 the two runs are byte-identical. The load happens between 2840 and 2844. From 2844 to 2860 they
  differ in **one byte**, +0xE (2 vs 0), except one passing frame (2852, 705 bytes, gone at 2856).
- **2,554 bytes appear at 2864 .. 2880, when the map starts**: in the file run a 0x20-byte heap block sits where the
  no-file run has a 0x4320-byte block, so the map's `BCH` texture (the same 0x4300 bytes but one) is
  loaded 0x100 bytes later, and the bytes around it differ. Cause, shown by the trace (t40d) and a switch run
  (t40e): **W1's apply rebuilt the zone inside the load.** During the battle save's `Deserialize` the map already
  exists (`Map::Get` = 0x31CABC80, `G_MapImage` = 0x32826910), so `config_set_danger` called `Danger::Update`
  (flags 0 -> 2, no unit added). The game then calls `Danger::Update` itself twice (lr 0x001DA1B8 and
  0x00397104) in both runs, with no file too; the extra call in the middle of the load changed what the map start
  allocated. With the switch (byte stored, no rebuild) those 2,554 bytes are gone (file run with vs without the
  rebuild: exactly 2,554 FCRAM bytes apart; end memory ecc8176a...).
- **2,241 bytes appear when the options screen draws the danger line** (first at 3590, when the cursor reaches the
  row above line 7; 16 more at 3600, 32 at 3620; 76 at 3710 and 9 at 3900, after B closes the screen): 2,132 in the
  screen's two 2-D vertex pools (0x31A8CA69.., 0x31B4CA71..: label and help-text quads; the file run draws
  "Attacks/Traps" / "Display enemy attack ranges and traps." from the first frame, the screen run "All" / "...
  attack/staff ranges..." until its press at 3650) and 109 in the options menu's heap objects (0x327E58E8 ..
  0x3289198E, 0x31800056..). In the screen run nothing differs from the no-file run before 3650.

**Fix (W1, source; nothing armed):** new `config_apply_options` (menu_config_writer.c, declared in menu_writer.h):
`config_write_options`' gate session, compare-then-store and value range, but the danger line stores its byte
**without** `Map::Get` / `Danger::Update`. W1 (menu_options_hook.c) now applies through it. The game's own two
`Danger::Update` calls after the load build the zone with the stored byte (T3's rule still holds). The screen's
writer `config_write_options` (with the rebuild, as `DangerPanel::SetValue`) and W2's restore are unchanged.

**T2's rule for the danger line corrected** (section 7, T2; **not yet seen by the owner**): the remaining 2,241
bytes are the options screen showing the value in use, which differs between "set at the load" and "set with a
press on that screen" whatever W1 does. The rule now asks (a) block and saves equal, (b) the whole heap equal to the
no-file run except +0xE from after the load until the options screen opens, (c) every other differing byte first
differing after the screen opened, in its vertex pools or menu heap objects.

| Check (t40f, readable, three armed, opt-* runs) | Result |
|---|---|
| T2 danger 2 -> 0, round 38's rule | 2,241 bytes "not the screen's" (was 4,795): FAIL under that rule |
| T2 danger 2 -> 0, corrected rule (t2_danger_rule.py) | **PASS**: block equal at every shot after the press, every save file equal; heap = no-file run except +0xE at 2844, 2860, 2880, 3000, 3300, 3340 (and 3580); the 2,241 bytes first differ at 3590 .. 3900, all in the vertex pools (2,132) and menu heap objects (109); VRAM / DSP / AXI none |
| the other T2 lines, T2 page value 2, every line at the save's value, T5 (battle save, chapter save, chain2), T7 | memory hash of every run **identical to round 38's** (21 of 22 runs); only the danger file run changed (ba53938f... -> ecc8176a...). T5: every save file byte-identical with and without the file; T2 battle animations, game speed 0 and 1, page value 2, save values: PASS; HP bars: the round-38 rule as before |
| host tests, fixed sources | w12_diff seed 20261118 and seed 2: 300 scenarios each, 0 mismatches, unarmed 0, options 0, clean saves 0, **34/34 plants caught** (round 38's 32 plus "apply rebuilds the zone" from the hook and from the writer); writer_diff seed 1 and seed 2: 600 cases each, 0 mismatches, 25/25; writer_gate_test.py --plant: source checks clean, 19/19 |
| source checks | gen_stubs.py --check OK (266 overrides, 5 writers); tools/readable/check.py: readable OK; options_track.py --check OK (31 options routes) |

W1 and W2 stay off; nothing was armed outside build/oka/; no save was packed; no options file outside build/.
T1 is a separate area (section 13b). The OK A checklist is still not fully green: T1 and the two rule changes
(T3 round 38, T2 danger round 40) wait for the owner.

## 16. Status 2026-12-14 (round 40, integrate): what ran and the results; not green; W1/W2 stay off

**In plain words.** Round 40 found what was behind round 38's two FAILs, fixed W1 for part of T2, and reran T1 and
T2 on a fresh armed tree (build/oka/t41, library sha 3b79f36b..., never swapped in). Every check that ran passes
**under the corrected rules**, but those rules (T1 here and section 13b, T2 danger section 15, T3 section 13a) have
**not been seen by the owner**, so OK A is **not green**. No writer is on for the owner.

- **T1** (section 13b): no reader is wrong. Readable overrides answer in host code and spend no guest cycles, so a
  later clock read (GetNow) comes about 1 ms earlier; on bt-castle-shop and bt-ch8-support that changes one byte of
  GameRealElapse's saved time in Chapter0. Shadow mode: saves equal original 12/12, 0 mismatch lines; memory equal on
  10, 9 / 4 dead-stack bytes on bt-ch6-castle / bt-ch8-pair. On t41: **PASS (corrected rule) on 12 routes**;
  **bt-ch9 and bt-ch9-ore NOT RUN** (cap). The clock exception cites round 40's GetNow log from tree8t1 (unarmed
  HEAD library), not a log on t41. Risk kept open: a moved RNG-seed clock read would change play in readable mode.
- **T2**: battle animations, game speed 0 and 1, danger page value 2, every line at the save's value **PASS**.
  Danger 2 -> 0 from the file: 2,554 of round 38's 4,795 bytes were W1 rebuilding the zone in the middle of the
  load; **fixed** (`config_apply_options` stores the byte, no rebuild; menu_config_writer.c, menu_writer.h,
  menu_options_hook.c). The other 2,241 bytes are the options screen drawing the row's value; **PASS under the
  corrected rule, FAIL under round 38's rule**. HP bars: block and saves equal; 10,036 of 14,787 bytes not proven
  byte by byte, **passes by judgement only**.
- **T3-T6**: last PASS in rounds 38/40 (tree5, tree6, t40f); **not rerun on t41**. **T7**: answered for two fights
  (round 38).
- **Host tests on the fixed sources** (this round): w12_diff seed 20261118 and seed 2, 300 scenarios each, 0
  mismatches, **34/34** plants (two new: "apply rebuilds the zone" from the hook and from the writer); options
  reader 2,027 files, 0 mismatches; writer_diff seeds 1 and 2, 25/25; writer_gate_test 19/19.
- **Writer gate (F-026), W1/W2 only, kept apart**: (1) recordings: 0 (no writer line reached by a recording;
  lines never reached are listed, not failures); (2) host test 34/34 on both seeds; (3) armed compare T1 PASS*
  (12 of 14 routes, corrected rule), T2 PASS* (corrected rule; HP bars by judgement), T5 PASS, T6 PASS (round 38/40).
  *= rule not yet seen by the owner. **Not at the gate.**
- **Safety checked**: tracked writer.c unchanged (every entry 0); build/harness/lib 610f791d... (another round's
  18:11 rebuild), never the armed library; %APPDATA% / %LOCALAPPDATA% zakuro: 0 files changed; no commit.
- **Incident**: build/oka/tree7 was overwritten at ~17:47 by the T1 agent; its 17:47:57 build must not be used
  (WARNING_SOURCES_OVERWRITTEN.txt). Round 40 used t40d/t40e/t40f/t41 instead.

- **Recheck 2026-11-19** (integrate rerun, 17:51 to 18:14): check_all rows touched 5 pass, fast 50 pass,
  w12-host-seed1/2 pass (34/34 each), unittest 95 OK; tracked writer.c has no diff; build/harness/lib still
  610f791d...; t41's armed library 3b79f36b... stays in build/oka/t41 only; %APPDATA% / %LOCALAPPDATA% zakuro: 0 files
  newer than 2026-11-18 17:00. Nothing new ran in the game; the results above are unchanged. Owner report:
  docs/REPORT_2026-12-14.md.

## 17. Round 81 (2026-11-25, F-066): a core writer replaces W1/W2 for four lines, once per New Game

**In plain words.** Four of the game's own Options lines (battle animations, map speed, enemy turn skip, HP bars)
can now be set once for every New Game from Esc > Helpers > **New Game defaults**. The port writes them at the one
moment a New Game begins (right after Casual, Classic or Phoenix is picked), as if you had changed them on the game's
Options screen before the Prologue. Loads, saves and a game already going are never written, so the save guard
(W2) and the write-at-every-load (W1) of sections 4-16 are not needed for these four lines. Every row starts on
**Game's choice**; with all four there, the program is round 80's program (memory compare equal, no trap word laid).

- **What replaced what.** W1 (copy the choice into the block at every load and reset) and W2 (make saves keep the
  game's own value) stay unbuilt and off; the C writer sources and their gate (sections 12-16) are history. The
  round-81 writer is Zakuro core code (patch 0040, `fates_options.rs`), not the readable library: a reserved svc
  0xEFFEC003 over the first word of `GameConfigData::StartFromBeginning` 0x001D0618 (original 0xE92D4070), laid
  only for the Fates title (Seal too) and only while a row is not Game's choice. At the svc it checks lr ==
  0x00441794, r0 == `*G_GameConfig` (0x006DA0F8) non-zero and readable, no player army, no map, does the replaced
  push and records "pending"; at the end of that frame (after the randomizer's `after_frame`) it checks again and
  stores each set row's byte only if it differs: +0x8 (0/1), +0xC (0/1/2), +0xD (0/1/2), +0x16 (0/1). Never word
  +0x4, never +0xE (danger zone), never the versus copy (`versus::Data` +0x12AC), no game function call. One log
  line `fates_options: New Game: ...`. Fail-closed: any doubt, no write.
- **Settings.** Zakuro's settings.toml `[fates_helpers]`: `battle_animations` (off / on), `map_speed` (normal /
  fast / fast_while_a), `enemy_skip` (off / move / all), `hp_bars` (off / on); a key is written only when it is not
  Game's choice, and each key is read on its own (a bad value resets only that key). The page words follow the
  game's own screen (V's R13 look): Map speed byte 2 reads "Manual", Enemy turn skip byte 1 "Movement".
- **What the robot proved (round 81, build/r81/).** P1: no keys, and an explicit all-"game" table: smoke 8/8,
  memory equal to the round-80 baseline, no `fates_options` line, 6 functions in the interpreter (as round 80). P2
  check one on Normal + Casual, Normal + Classic, Normal + Phoenix and Hard + Casual: one write line in B, none in
  A; before the pick only the trap word differs; from the pick through the character creator and past the first
  chapter save (frame 13050) memory equal except the trap word and exactly the four bytes; both random generators
  equal through 17460, GameUserData equal throughout. P3: chapter save (bt-ch2) and battle save (opt-ch8-reload)
  loads with rows set write nothing (0 lines, memory equal less the trap word, saves byte-identical); the written
  bytes equal the bytes the game's own screen stores for the same choices (opt-t2-*-set routes). P4: the randomizer
  and Nuzlocke starts with rows set make the same run id and run files. P6: one Seal New Game wrote once.
- **NOT REACHED in round 81.** P2 check two (B vs a run C that sets the same lines on the game's screen before the
  pick): the game's Options screen first opens on the Prologue map, after the pick, so run C cannot exist as
  written; P3's block-vs-screen match and V's pictures stand in for it. A game-over retry (no recorded route), the
  save-state run (the headless game exe has no save-state hook), and a New Game -> Options screen -> save -> load
  chain (no route) are also not robot-proven; unit tests cover the word rule and "a load never writes".
