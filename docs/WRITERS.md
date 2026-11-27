# Writers: the safety net, and the first writer (kept OFF)

**In plain words.** Most of the readable code only *reads* the game: it answers a question the
game asks and the game keeps its own answer until we have proved ours is the same. A *writer* is
different: it changes the game's memory (an option, a gauge, a save byte). A wrong writer can
spoil a save. So writers get a safety net before any of them may run:

1. **A switch per writer, off.** Every writer is built into the library and does nothing. It runs
   only when three things are all true: it is *armed* in the source (every writer ships unarmed),
   its name is listed in the environment variable `FE_WRITERS`, and the readable layer runs in
   `readable` mode. Shadow mode, capture mode and original mode never run a writer.
2. **An undo log.** Every byte a writer stores is written down first: where, how many bytes, the
   old value, the new value, which writer, which frame. If anything goes wrong the old bytes go
   back, exactly. A writer that has finished can also be undone later, but only if the game has
   not changed those bytes since (otherwise the undo refuses and changes nothing).
3. **Proof before a switch.** A writer is compared against the game's own code on the PC first
   (thousands of made-up cases, the exact list of stores and calls, planted bugs that must be
   caught). That is not enough to switch it on: the test robot's H6 and the owner's OK come first.

This is F-006 ("writers wait") and F-017 made into code. **Nothing is switched on.** No engine
build was made for this; it is tested on the PC against fakes and against the game's ARM code
run in a small interpreter.

---

## 1. The rules

| Rule | How it is enforced |
|---|---|
| Every writer is compiled in and OFF | `src/readable/core/writer.c`: the writer table's `armed` column is `0` for every writer, and the table is `const` in every library build (only the host tests, built with `-DFE_WRITER_TESTS`, can arm one). `writer_gate_test.py` fails if any `armed` is not 0 |
| A writer runs only when it is armed AND listed in `FE_WRITERS` AND the mode is `readable` | `fe_writer_switched_on`; `fe_writer_begin` refuses otherwise and counts the refusal |
| Shadow mode never runs a writer | `fe_writer_begin` refuses in shadow, capture and original mode (counted apart: `fe_writer_mode_refusals`); a session opened in readable mode refuses every store once the mode is not readable. Writers have no 3dsrecomp marker, so `FE_ENTRY` (and with it shadow mode and `verify`) never calls one. Tested both ways |
| A green report switches nothing on | the switch reads only the source constant, `FE_WRITERS` and `FE_READABLE`. It reads no file, no registry status, no harness report (`writer_gate_test.py` checks the source for it). A row going `shadow-clean` or `verified` changes nothing |
| Every store is logged and can be undone exactly | `fe_writer_store` (the writer's own stores) and `fe_writer_call` (a game function the writer calls: every store it makes is caught the way `undo.c` catches them) log `address, size, old, new, writer, frame, session` before the byte changes |
| A store that could not be undone is not made | a byte with no direct page pointer (device memory, or while `undo.c` or capture holds the page table), a size other than 1/2/4, an `svc` or an interpreter escape inside a called game function, a full log: the store is refused and the whole session is put back |
| Bounded memory | 8,192 log entries (about 200 KB, static). When the log is full the oldest *finished* sessions are dropped whole (they can no longer be undone; counted); a session still open is never cut: it fails and is put back |
| One writer at a time | one session, one Context, one host thread (an atomic flag) |
| A store outside a session does nothing | counted as a stray store |
| A writer is never an override (round 8) | registry kind `writer` (config/readable/functions.csv) and config/harness/targets.csv kind `writer`: `tools/readable/check.py` refuses an override marker at a writer's address ("a writer never has an override marker"), a writer row whose evidence does not start with WRITER, a row that says WRITER under another kind, and a writer source that does not go through the gate; `gen_stubs.py` never stubs a writer row and refuses a probe or override row on a writer's address. Planted-bug cases in both self-tests |
| "No writer stored anything" is read from every capture run (round 8) | the gate's run totals (`fe_writer_totals`, fe_writer.h `FE_WT_*`: log, stores, restored, sessions, refusals, mode refusals, stray, dropped) live in runtime.c; capture.c writes them as summary.tsv's `# writers:` line; `parallel.py` reads them into each run's capture totals and `summary.json` `writers` (verdict "no writer stored anything", or "WRITER STORED", which fails the run: the gate refuses in capture mode, so any store is a fault). A library built before round 8 has no line: "NOT REPORTED", never "clean" |

How a writer is shaped (`src/readable/menu/menu_config_writer.c` is the model): check the input
first (refuse before reading or storing anything), `fe_writer_begin`, the stores and calls in the
game's order, `fe_writer_end(keep)`, then put the guest registers back.

**Undo is exact or nothing.** `fe_writer_undo_last` takes the newest finished session. Every byte
it changed must still hold the value the session left there (for a byte stored twice, the later
value); if one does not, the game has stored since, and the undo returns `FE_WRITER_CONFLICT` and
changes nothing. Sessions are undone newest first.

**Not the same as `undo.c`.** `src/readable/core/undo.c` (H8 groundwork, still disabled) is a
rollback for a *readable function that gives up after storing*: it forgets everything once the
outermost frame commits. The writer log keeps finished sessions so an option can be taken back
later, and it records which writer, frame and value. They use the same trick for game functions
(a table of null page pointers so each store reaches a host callback). They do not nest: a writer
store while an `undo.c` frame is open is refused (safe: nothing is stored).

## 2. What must pass before a writer may be switched on

In this order, all of them, for that one writer:

1. **The host comparison** against the game's own code with 0 mismatches, the ordered list of
   stores and guest calls compared, and every planted bug caught (for the first writer:
   `writer_diff.py --plant`, section 3).
2. **The gate's own test** (`writer_gate_test.py --plant`) passes.
3. **Robot H6 on the writer**: the test robot's mutation step (Awakening harness H5/H6; Fates
   docs/HARNESS.md section 4 item 3) on game records of the writer and the game functions it
   calls. Round 8 built the plumbing, nothing is armed: docs/harness/HOOK_LIST.md lists the
   writer slots (O1 .. O5 the options block, D1 the danger-zone rebuild, W1 .. W3 the designed
   wiring) with the game function each stands for and its readable callees;
   `harness.py --mutate --writer-callees` lists those callees (5 today: the four `GetValue`
   readers and `force_is_allied`, which `Danger::Update` calls), and runs H6 on exactly them with
   `--run NAME` (a store-keep run) or `--fake` (the fakelib, a made-up hook list: the same code
   path); `h56.py h6 --writer-callees` does it on a session's kept records. What H6 on the writer's
   own C (`config_set_*`, `config_write_options`) still needs: records of the writer itself, i.e. a
   test build with the writer armed and a capture of its stores (OK A, docs/OPTIONS_WIRING.md
   section 10); the capture library records overrides and probes only, never a writer.
4. **A replay that shows the effect**: a route that changes the same option through the game's own
   screen, recorded, and the writer's stores compared with the game's on that route (docs/MENUS.md
   section 5 says which route each option needs).
5. **The owner's OK, in chat, for that writer.** Then, and only then, its `armed` value is set to
   1 in `writer.c` (a source change, reviewed), the library is rebuilt (an engine build: the
   owner's OK again, F-004), and the owner lists the writer in `FE_WRITERS` for a test run.

A green report at any step switches nothing on by itself.

## 3. The first writer: the game's own options block (kept OFF)

`config_write_options` (`src/readable/menu/menu_config_writer.c`, `menu_writer.h`) sets lines of
`GameConfigData` (the options block, `G_GameConfig`; docs/MENUS.md section 1):

| Line | Byte | Values | The game's setter | What else it does |
|---|---|---|---|---|
| battle animations | +0x8 | 0 .. 4 | `Battle::SetValue` 0x003BC36C | nothing |
| game speed | +0xC | 0 .. 2 | `GameSpeed::SetValue` 0x003BC968 | nothing |
| danger zone | +0xE | 0 .. 2 | `DangerPanel::SetValue` 0x003BAF00 | asks `Map::Get`; when a map exists, rebuilds the zone (`map::Image::Danger::Update` on MapImage +0x1008, itself a writer) |
| HP bars | +0x16 | 0 .. 1 | `HPGauge::SetValue` 0x003BC51C | nothing |

**How the game stores them** (read 2026-11-14 in the game's ARM code). The options screen's key
handler `ConfigItem::KeyCall` (0x003BA714) works out the new value from the left/right keys
(wrapping at the bound its class-table slot +0x78 gives; that this slot is `GetNum` is read from
the class layout [medium]; the four `GetNum` bodies return 5, 3, 3, 2 [high]), asks the line's
`GetValue` (slot +0x84), and only when the value differs calls the line's `SetValue(int)` (slot
+0x88); then it marks the menu for redraw and plays the cursor sound (screen work, not the
block). The writer does the same per line: the compare (through the readable
`GetValue` readers), then the setter; the screen work is not reproduced. A value past a line's
range is refused before anything is read or stored (the screen never stores one). The lines are
set in the block's byte order (battle, speed, danger, HP bars); the screen's own line order was
not traced and does not matter for the result (no setter reads another line's byte).

`Danger::Update` is called through `fe_writer_call`, so the zone it rebuilds is logged with the
line and undone with it.

**Status: UNVERIFIED, OFF.** Registry rows of kind `writer` (round 8; they were kind `helper` with
"WRITER, OFF" in the evidence before `check.py` knew the kind): `config_set_battle`,
`config_set_game_speed`, `config_set_danger`, `config_set_hp_gauge` at the four `SetValue` addresses,
and `config_write_options` at `ConfigItem::KeyCall` 0x003BA714 (the screen's store path it reproduces:
the compare, then `SetValue`; not a whole-function rewrite). The same five are `writer` rows of
`config/harness/targets.csv` (never stubbed, never a marker).

**Host comparison** `python src/readable/menu/tests/writer_diff.py --plant`: the game's
`GetValue` / `SetValue` code run in `arm_mini.py` against the writer through the real gate, on
made-up states (option bytes out of range, an unmapped options or map pointer, no map). Compared
per case: the result, one ordered list of every store (address, size, value) and every guest call
(with its argument), the bytes read, the block and the zone's flag word after, the undo log (old
values included, writer id, frame), and that `fe_writer_undo_last` then puts every byte back. A
store the game would make to unmapped memory must make the writer roll back with every byte back.
Modes: armed + listed + readable, and the OFF ones (not armed, not listed, shadow, capture,
original), refused values, and a setter called with no session: those must read nothing (the
stray setter: only the block pointer), store nothing and call nothing. Results: section 6.

## 4. Saves carry the options block (`keep_game_options`)

The options block is not only in memory: `GameUserData::Serialize` writes it into **every game
save**, and loading a save reads it back (docs/MENUS.md section 1). Consequences:

- Once this writer has set a line, **the next save the player makes stores that value.** A writer
  that sets options is therefore not a "display" switch in OPTIONS_V1's sense (a display switch
  never marks a save): its effect outlives the session in the player's own save files.
- Undoing the writer later (`fe_writer_undo_last`) puts the bytes in memory back; a save made in
  between keeps the new values. The undo cannot reach a save already written.
- Loading a save replaces the block with that save's values, so `keep_game_options` ("remember the
  options across saves") needs a writer that runs *after* a load. That is this writer, called with
  the remembered values; the remembered values themselves may come from a side file
  (`config_saved_record` reads the block, a reader). Grok's OPTIONS_V1/V2 and OPTION_HOOKS row
  "side file only, never the 3DS save" holds for where the port keeps its copy, but **not** for
  the effect: setting the block in memory is what the next game save writes. Checked against the
  code (GameUserData::Serialize calls GameConfigData::Serialize, docs/MENUS.md); the OPTIONS
  pages' "never the 3DS save" should be read as "the port never writes a save file itself".
- The robot's routes start from saves: a route recorded with one set of options and replayed with
  another moves every later input (game speed changes timing). A test of this writer must start
  from its own save and never from the owner's.

## 5. What is not done (and what it would need)

- **targets.csv rows: done in round 8** (kind `writer`, see section 1). A `probe` on each `SetValue`
  would make the capture library record the game's own calls (useful for step 2.4), but a writer's
  address may not carry a probe (`gen_stubs.py` refuses it) and a probe is not "off" (it runs in
  capture mode). The opt-* routes (docs/harness/OPT_ROUTES.md) record the game's own screen changing
  every option line instead, through the readers.
- **The header place.** `fe_writer.h` lives in `src/readable/core/` (this area's files); the
  menu header reaches it as `../core/fe_writer.h`. `stage.py` and the host tests resolve that.
  Integrate may move it to `include/readable/`.
- **Nothing calls the writer.** No hook, no options page. The Zakuro options page (tools/zakuro-
  options/DESIGN.md) is a design; wiring a writer to it is an engine change (owner's OK).
- **Builds that would be needed** (none made): the capture library with the writer compiled in
  happens anyway at the next `parallel.py build` (the writer is dead code there: no marker, never
  called, unarmed); a real test of the writer needs an armed build (`writer.c` edit + engine
  build) and a hook that calls it: both need the owner's OK.

## 6. Results (2026-11-14, this PC, host compiler only)

| Check | Result |
|---|---|
| `python src/readable/core/tests/writer_gate_test.py` | 244/244 checks, source checks clean (every writer unarmed; only FE_WRITERS read) |
| `python src/readable/core/tests/writer_gate_test.py --plant` | 17/17 planted bugs caught (restore order, the conflict check, the newest-byte rule, refusing a store without a page pointer, the log-room check (a hang, caught by the 60 s limit), dropping part of a session, sizes, svc and interpreter escapes, the mode check inside a session, one session at a time, the byte mask, the game's page table put back after a call, a failed session going on, the mode-refusal count, FE_WRITERS prefix matching, a writer armed in the source) |
| `python src/readable/menu/tests/writer_diff.py` | 600 cases, 0 mismatches (300 armed: 234 that stored, 77 that rebuilt the zone, 19 that had to roll back; 208 OFF; 38 refused; 54 stray setters) |
| `python src/readable/menu/tests/writer_diff.py --plant` | 25/25 planted bugs caught, 15 of them in the writer itself (list: docs/READABLE.md section 16) |
| `python tools/readable/check.py --selftest` | lint 138 rows 0 problems; 22/22 broken inputs, verify pipeline 28/28; 27 sources and 27 staged files compile; host 146/146, capture 565/565, undo 554/554 |
| round 8 (prep), the same checks after the writer kind and the run totals | `writer_gate_test.py` 307/307 checks, `--plant` 19/19 (two new: a store not counted in the totals, a total copied wrongly); `writer_diff.py` 600 cases 0 mismatches; `check.py --selftest` (run on a copy without another area's untracked src/readable/sheet/) lint 139 rows 0 problems, 27/27 broken inputs (new: unknown kind, a writer hidden as a helper, a writer without WRITER, a writer source that bypasses the gate, an override marker on a writer), capture 568/568 (the `# writers:` line), host 146/146, undo 554/554; `gen_stubs.py --selftest` 39/39, `--check` OK (110 overrides, 5 writers) |
