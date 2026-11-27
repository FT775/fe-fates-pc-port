# Randomizer start delay (round 59, track speed; F-047 "start delay" and "the owner's rule")

**For the owner.** When you pressed Start game with the randomizer on, the game froze for about 10 seconds
before it went on. That time was all spent in the Python randomizer making your game, and most of it was not
randomizing at all: it was reading the same game tables again and again. This round's speed track measured
where the time goes, made the host side 5 to 10 times faster with the very same output, byte for byte, and wrote
the exact plan for the game side: the game makes your run in the background while the page is open, throws a
guess away the moment you change anything, and Start game always uses exactly what the page shows. Nothing in
the engine was changed by this track; the engine part is done in the assemble step. Nothing counts as done until
you say ok (F-037).

Status 2026-11-20 (track speed, phase A):

| | done | where |
|---|---|---|
| where the time goes, Fates and Seal of Flames | measured (section 1) | build/r59/speed/ |
| table cache per game, invalidated by game files and code | built and tested | tools/randomizer/cache.py, tests/test_rando_cache.py |
| two slow searches in enemies.py / misc.py | exact patch, tested on a copy | section 6 (appendix) |
| fast in-memory-patch path (in-game only) | built (cache.py fast_patch) | cache.py |
| progress line source ("Making your game... N%") | built (cache.py progress_lines) | cache.py |
| background make, throw-away, Start uses the page's values | exact plan | section 4 |
| host make under 1.5 s | **not reached**: 2.1 s page defaults, 4.5-6.5 s everything on, warm (section 2) | |
| Start game to avatar screen under 2 s | reachable with section 4 (Start finds the make done: 0.2 s lay) | assemble step measures it |

## 1. Where the ~10 s went

**On the game side** (round 58's own headless logs, no new runs): from the mode pick to "randomized game laid"
took 39.1 s for Fates with everything on (`build/r58/assemble/r58fix3-fates-all/data/zakuro.log`: picked 14.12 s,
Python started 14.36 s, Python done 53.07 s, laid 53.23 s) and 41.9 s for Seal of Flames
(`r58fix2-seal-all`). So: finding Python (`py -3 --version`, every make) 0.2-0.9 s, the Python make 38.7 s, laying
the patch in memory 0.16 s. The game itself costs nothing worth fixing; the whole delay is the make.

**On the host** (the core's own make script, `rando.py make --patch-out`, run on a frozen copy of the code,
build/r59/speed/snap = HEAD + cache.py; machine shared with four other tracks, so absolute times wobble):

| answer | before | after, empty cache | after, warm cache | output |
|---|---|---|---|---|
| Fates, page defaults (Randomizer on, nothing else) | 10.4 s alone; 12.3 s under load | 3.5 s | **2.1 s** | identical |
| Fates, everything on | 33-35 s alone; 43.5 s under load | 8.1 s | **4.5 s** | identical |
| Fates, everything on, other values (trees any, full growths, ...; seed zz9) | 57 s under load | 9.7 s | 6.5 s | identical |
| Seal of Flames, page defaults | 21 s under load | 6.8 s | 4.4 s | identical |
| Seal of Flames, everything on (two seeds) | 49-51 s under load | 11-13 s | 6.5-8.1 s | identical |

Medians of 2-3 runs (final code: build/r59/speed/bench/fates-def2.json, fates-all2.json, fates-all-b.json,
seal-def.json, seal-all.json, seal-all-c.json; the Seal default/all rows were measured before the last two memo
changes, so they are a little pessimistic). ("everything on" = every row the page can lay today, at its "Everything on" value. "identical" = every file of the
mod folder and the patch, SHA-256, against the first "before" run.) The owner's ~10 s is the page-defaults row.

What the time was, before (profile of the everything-on make, build/r59/speed/prof1.out):

1. **Terrain lookups (about 45%).** `EnemyTables.tile_col` parsed the chapter's whole terrain grid from its hex
   text again for every single tile it looked at: 7.9 million times per make, from the no-stuck searches of the
   enemy classes (enemies.py) and of the Move changes (misc.py, tracks.cross_guards).
2. **Table file lists (about 5 s on its own).** `tablelib.TableDef.files()` lists and stats a whole folder of
   chapter files on every call, and the mods tool calls it thousands of times per make (131 820 `isfile` calls).
3. **Tables read again.** `gamedata._load` decoded the same tables 22 times per make (DisposUnit, 700+ files, 0.6 s
   each time), mods.vanilla() decoded every table once more, and every original file was LZ-decompressed again.
4. **The mods tool's LZ compressor** (the game's slow greedy matcher) recompressed ~100 rebuilt files, only for the
   patch maker to decompress them again a moment later.
5. **Seed-independent answers worked out per unit**: which classes an enemy may get, which items a class can
   hold, how far a class reaches from a tile (13 000 searches).
6. Smaller: starting Python through the `py` launcher and probing it every make (0.5-0.9 s), recompiling changed
   modules every make because the core sets PYTHONDONTWRITEBYTECODE=1, Seal's layer check (walks 4 601 files, 0.5 s).
   Module imports are only ~0.1 s in all: tracks.py already imports a module only when its option is on, so "lazy
   imports" has almost nothing left to give.

## 2. What is built (host side)

**tools/randomizer/cache.py** (new, standard library only). `cache.install(cache_dir, fast_patch=..., progress_lines=...)`
puts a cache under the table readers; it changes no output byte:

1. table file lists remembered per (RomFS folder, pattern) for the process;
2. `gamedata._load`, `gamedata.load_handover`, `enemies.script_pids`, `mods.vanilla()` kept on disk per game
   (`<cache>/fates/`, `<cache>/seal/`); each call gets a fresh copy (a caller may change its rows);
3. LZ decompression of the game's own files kept on disk by the SHA-256 of the compressed bytes (made files are
   never stored: only bytes whose hash is one of the game files' hashes);
4. the reach answers (tiles reachable from a tile, by move-cost class and Move) kept on disk; they depend only on
   the terrain tables;
5. `fast_patch=True`, the in-game path only (`--patch-out` without `--zakuro-dir`): the rebuilt files are
   LZ-encoded as plain literals (valid LZ, decompresses to the same bytes) instead of with the slow matcher; the
   patch maker only reads the decompressed bytes, so the patch is identical. Never used for PLAY RANDOMIZED
   installs, whose files go into a data folder;
6. `progress_lines=True`: `progress 5 started`, `progress 70 planned`, `progress 92 files rebuilt`,
   `progress 99 patch made` on stdout, flushed, for the page's progress line.

Invalidation: an entry is used only when nothing it depends on changed. The key holds (a) the SHA-256 of the
readers' code: tools/randomizer/{cache,gamedata,enemies,sources}.py, tools/{tables,mods,assets}/*.py and the
table layouts config/tables/** (other randomizer modules only use the tables, so editing them keeps the cache);
(b) the SHA-256 of every game file the randomizer reads (GameData, Scripts, m, map/config, talk, exalt in the
active RomFS folder, Fates' own or the Seal layer); a small index (size and time -> hash) skips re-hashing
unchanged files, `FEF_RANDO_CACHE_STRICT=1` re-hashes all; (c) the RomFS folder and the call's arguments. Any
change is a miss: the original reader runs and the entry is rewritten (written whole, then renamed). Cache size:
about 12 MB per game. `python tools/randomizer/cache.py status|warm|clear [--cache-dir DIR] [--game fates|seal]`.

**Proof** (tests/test_rando_cache.py, 9 tests, all pass, 4 min): cache hit = byte-identical output (the real
`rando.py make --patch-out`: no cache vs empty cache vs warm cache vs cache without fast_patch: every file the
same); the warm make reads no table and no original LZ file itself; any input change is a miss (a game file's
bytes, in strict mode even with the old size and time; a file added; the readers' code; a table layout; the RomFS
folder; the arguments); a module that only uses the tables does not invalidate; each call gets its own copy; the
literal LZ decompresses to its input in all three formats; the F-047 agency host half (section 5). The
enemies/misc patch passes tests/test_rando_enemies, test_rando_misc, test_rando_integrate and test_randomizer (81
tests) on the copy.

**Still slow, honestly.** With everything built here the warm host make is 2.1 s (page defaults, Fates), 4.4 s
(page defaults, Seal) and 4.5-8 s (everything on), not 1.5 s. What is left is real work: the mods tool's rebuild and its own checks (decode-back of
every rebuilt table, check.py; ~1.3 s), the plan itself (~1-4 s with the enemy options), the patch maker (0.3 s),
Python's own start (0.5 s on this PC, its Python is the Microsoft Store one). Next steps if the owner wants the
make itself faster (not needed for the 2 s start target once section 4 is in): an index by person in randolib's
`placements` / `variant_placements` (O(people x placements) scans, ~0.3 s) and a cached `replacement_items`
(~0.5 s), both e1's file; `os.scandir` in sources.py's layer check (Seal, ~0.3 s); a keep-alive Python worker
started with the page (saves the 0.5 s start; measured: a second make in the same process is identical byte for
byte, build/r59/speed/reentry.py). The 2 s target is met by section 4, not by a faster make.

## 3. Python changes for the assemble step (exact)

**3.1 enemies.py and misc.py** (not owned by any track this round): apply the patch in section 6
(`git apply build/r59/speed/patches/enemies.diff build/r59/speed/patches/misc.diff`; it applies to HEAD). It
precomputes each chapter's tile columns once (no more hex parsing per tile), remembers per-class answers that
depend only on the tables (`kept_job`, `can_hold`, `class_candidates`), and replaces both reach searches by one
shared `EnemyTables.reach_tiles(ch, x, y, mcc, mov)` over a precomputed passable-cost map, kept in
`self._reach_memo` (cache.py fills that from disk). The tiles counted are exactly the old ones (any shortest-path
search gives the same set within the budget); all outputs identical on every seed tried.

**3.2 rando.py** (e1's file). In `main()`'s `make` parser:

    p.add_argument("--cache", help="keep parsed tables in this folder (tools/randomizer/cache.py; default "
                                   "FEF_RANDO_CACHE, none = no cache)")
    p.add_argument("--progress", action="store_true", help="print 'progress N stage' lines (the in-game page)")

and at the top of `cmd_make`, right after `game = _activate(a.game, a.seal_romfs)`:

    cdir = a.cache or os.environ.get("FEF_RANDO_CACHE")
    if cdir:
        import cache as CA
        CA.install(cdir, fast_patch=bool(a.patch_out) and not a.zakuro_dir, progress_lines=a.progress)

(`--progress` only means something together with a cache folder; the core always passes both.) Nothing else
changes; without `--cache` the make is exactly as before.

**3.3 The core's MAKE_SCRIPT** (zakuro-core `fates_rando_session.rs`). The argument list gets the cache folder
after `options`, before the optional game:

    tool, answer, out, patch, seed, options, cache = sys.argv[1:8]
    ...
    if len(sys.argv) > 9 and sys.argv[8] != 'fates':
        import sources
        sources.activate(sys.argv[8], sys.argv[9] or None)
    sys.exit(rando.main(['make'] + ingame.make_args(a) + ['--out', out, '--patch-out', patch,
                                                          '--cache', cache, '--progress']))

with `cache = <data>/rando/cache` (F-047: "under the data folder", one folder per game inside it, made by
cache.py). If the assemble step prefers that Python never writes inside the data folder (it lives in %APPDATA% for
the owner; the make's work folder is already kept in the repo's build/rando-make/ for that reason), use
`<repo>/build/rando-cache` instead; nothing else depends on where it is.

## 4. The game side: background make, the owner's rule (exact plan)

The rule (F-047, 2026-11-20): a background make is only a guess. It is thrown away the moment any row or the
seed changes, and a new one starts with the new values. Start game always uses exactly what is on the page when
it is pressed. If the matching make is not finished, Start game waits for it (with the progress line) or makes it
then. Nothing is applied to the game before Start game.

This needs no change in how the core lays a run: `Session::answer` already skips the make when
`<data>/rando/<title>/runs/<id>/patch.txt` exists, `id = run_id(seed, answer text)`, and the patch is written
whole and renamed last. So a background make is just `make_run_for` for the exact answer text Start game would
send; Start game then finds the patch and only lays it (0.16 s).

**4.1 Core (zakuro-core, fates_rando_session.rs)**

1. `find_python()` once per program run (a `OnceLock`), and the real interpreter's path asked once
   (`<py> -c "import sys; print(sys.executable)"`) and used directly afterwards: no launcher, no probe per make
   (0.5-1 s per make on this PC).
2. Child environment: drop `PYTHONDONTWRITEBYTECODE=1`, set `PYTHONPYCACHEPREFIX=<data>/rando/pycache` instead
   (compiled modules kept outside the repo; a changed module is no longer recompiled on every make).
3. `pub fn run_id_for(answer: &str, game: Option<&str>) -> Result<(String, String), String>`: the (seed, id)
   `answer` would use, from `answer_for(answer, game)`; the answer must carry its seed (the page always fills it,
   4.2.2). The same `run_id` function as `answer`, so the ids agree by construction.
4. `pub fn make_run_cancellable(data, id, seed, answer, game, cancel: &AtomicBool, progress: &AtomicU8)`: today's
   `make_run_for` body, with `run_hidden` polling `cancel` every 50 ms (kill the child, remove
   `build/rando-make/<id>/` and the run folder if it has no patch.txt, return `Err("cancelled")`) and the output
   pump storing N from lines `progress N ...` into `progress`. `make_run_for` = this with a never-set flag, so
   headless runs and boot-server keep their exact behaviour (they have no page; their make stays synchronous in
   `after_frame`).

**4.2 Page (zakuro, rando_page.rs + lib.rs; a small `Prebuild` struct)**

    struct Prebuild { text: String, id: String, cancel: Arc<AtomicBool>, progress: Arc<AtomicU8>,
                      done: Receiver<Result<PathBuf, String>>, result: Option<Result<PathBuf, String>> }

1. **When it starts.** `open_new_game()` (and every time the page's values change, after 300 ms with no further
   change, so typing a seed does not start one make per key): if the Randomizer row is on, compute
   `text = form.answers_preview()` (4.2.2); if no prebuild has this `text`, cancel the current one and start one:
   a thread running `make_run_cancellable` for `text` (the child at normal priority: the game is paused on the
   page). Randomizer off: cancel, nothing runs.
2. **The seed.** `answers()` today puts a new random seed into the form at Start game when none is typed. Instead
   the page makes that random seed when it opens (and again whenever the seed row is emptied) and keeps it as
   `proposed_seed`, shown as the hint ("new one at Start game" -> "random: r5e1f..."); both `answers_preview()`
   and `answers()` use the typed seed, else `proposed_seed`. A blank seed still means "a random seed"; the
   background make and Start game simply use the same random one. Both build the JSON through the same function,
   so the text (and so the id) is byte-identical.
3. **Thrown away.** A prebuild whose `text` is no longer the page's is cancelled at once and its id goes on a
   `discarded` list. When its thread has ended, `<data>/rando/<title>/runs/<id>/` and `build/rando-make/<id>/` are
   removed (a guess never laid is never referenced by a save; a later return to the same values simply makes it
   again, byte-identical by determinism).
4. **Start game.** `text = form.answers()`. If the prebuild has this `text` and is done with Ok: send
   `PageAction::Answer(text)` now (the core finds patch.txt and lays it). If it is still running: the page shows
   **"Making your game... N%"** (N from `progress`, 0 before the first line) with the rows locked and Back to the
   settings still offered (Back cancels the wait, nothing laid); each frame it polls, and sends the answer the
   frame the make is done. If it failed, or no prebuild has this `text`: start one now (the same thread code) and
   wait the same way. The answer is never sent before the make of exactly `text` is done, so `answer` never runs
   Python on the frame thread; if it still had to (a race, a deleted folder), it is the same function as today.
5. **Nothing applied before Start game.** A prebuild writes only `build/rando-make/<id>/`,
   `<data>/rando/<title>/runs/<id>/` (complete only with patch.txt) and the cache. Game memory is touched only by
   `answer`, which only Start game calls. The frame thread never waits on Python: the game stays paused on the
   page while it is open, as today.
6. **After Start.** On Ok, delete every discarded and every other guessed run folder of this page session except
   the laid id. On Play the original game, delete all of them.
7. **First make warm.** In `RandoPage::ask()`'s thread, after `find()`: start, hidden and at below-normal priority,
   `python tools/randomizer/cache.py warm --cache-dir <cache> --game <fates|seal> [--seal-romfs <mod_romfs(data)>]`
   once, so the cache is filled before the page is even opened (it exits by itself; 2-6 s once per change of the
   game files or the reader code).

**4.3 Timing this gives.** Start game pressed after the make finished: lay only, 0.16 s, plus the game's own
step to the avatar screen (the same as with the randomizer off). Pressed right after a change: the rest of a
2-4.5 s make (defaults) or 4.5-8 s (everything on) with the progress line, instead of 10-40 s of frozen window.

## 5. The agency test (byte-identical)

**Host half, done** (`RealMake.test_hit_is_byte_identical_and_changes_miss`): a make of rows A finishes and fills
the cache; then the rows change (other seed, two rows changed) and the make of the final rows B runs on the same
cache. Its mod folder and patch are byte-identical to a fresh make of B with no cache and nothing made before, and
differ from A's. The progress lines come in order (5, 70, 92, 99).

**Game half, for the assemble step:**

1. Rust unit test of `Prebuild` with a fake maker (records calls, finishes on command): open with A -> make(A)
   starts; finish A; change a row to B -> A discarded and its folder removed, make(B) starts; Start game while B
   runs -> no answer sent yet, status shows the progress; finish B -> exactly one answer, whose `run_id_for` is B's
   id; A is never laid, and nothing is laid before Start.
2. Robot, headless page driver (copies only, own data folder and APPDATA/LOCALAPPDATA under build/): open the page,
   wait for the background make of A to finish (its runs/<idA>/patch.txt appears), change two rows and the seed,
   press Start game. Pass when the laid run's `runs/<id>/patch.txt` equals, byte for byte, the patch of a fresh
   `rando.py make --patch-out` of the final values in an empty folder with no cache, and `runs/<idA>/` is gone.
3. Timing: zakuro.log time of the Start game press to "randomized game ... laid" (target well under 2 s when the
   background make had finished), plus the frames to the avatar screen compared with the same run with the
   randomizer off (the game's own part).

## 6. Appendix: the enemies.py / misc.py patch

The exact files: `build/r59/speed/patches/enemies.diff` and `misc.diff` (made against HEAD 24280f8; `git apply
--check` passes). Summary of the enemies.py hunks:

- `EnemyTables._tile_cols(k)`: `{(x, y): move cost column}` of every playable tile of chapter k, made once
  (the grid's hex text parsed once, not per lookup); `tile_col` reads it. Out-of-area tiles give None as before.
- `step_cost`: the class's TerrainCost row remembered per class.
- `kept_job` -> memo over `_kept_job` (the old body); `can_hold` -> memo over `_can_hold` (the old body);
  `class_candidates` -> memo over `_class_candidates` (the old body), keyed by (class, trees, boss, the unit's five
  item cells), returning a copy.
- `reach` = `reach_tiles(ch, x, y, move_cost_class, mov)`, which counts the tiles within `mov * REACH_TURNS` over
  `_cost_map(k, mcc)` (`{(x, y): cost}` of the tiles that class may enter), memo in `self._reach_memo`.

misc.py, `_reach`:

    @@ def _reach(t, ch: str, x: int, y: int, mcc: int, mov: int, cache: dict) -> int:
         key = (ch[:4], x, y, mcc, mov)
         if key in cache:
             return cache[key]
    +    if hasattr(t, "reach_tiles"):           # the enemies track's shared, faster search (the same tiles; SPEED.md)
    +        cache[key] = t.reach_tiles(ch, x, y, mcc, mov)
    +        return cache[key]
         row = t.cost.get(mcc)

Bench and profiles: build/r59/speed/bench.py (base / cold / warm on the frozen copy, every output file hashed),
build/r59/speed/bench/*.json, prof*.out. Children ran hidden at below-normal priority; no game was started by this
track.

## 7. Round 59 assemble step: what was built and measured

Built into play/game (patch 0020) and tools/randomizer: enemies.diff + misc.diff applied; `rando.py make --cache
--progress`; the core finds Python once and calls the real interpreter; `PYTHONPYCACHEPREFIX=build/rando-pycache`;
the cache lives in `<repo>/build/rando-cache` (never inside the data folder, which is %APPDATA% for the owner);
`make_run_cancellable`, `run_id_for`, `discard_run`. Page (4.2): the background make of exactly Start game's text, a
first guess of the restored last values as soon as the rows are known (before the page opens), 300 ms settle,
cancel + delete on any change (never a run the page did not make), "Making your game... N%" while Start game waits,
guesses removed after Start. Not built: 4.2.7 (a separate `cache.py warm` run; the first guess fills the cache).

Headless (no page): an answer known before the mode pick is made in the background; the test hook
`FEF_RANDO_GUESS` + `FEF_RANDO_GUESS_UNTIL` stands for the page's values before the player changed rows;
`FEF_HEADLESS_PACE=60` keeps a run to the clock. Measured (build/r59/assemble/smoke, new-game replay, mode pick at
frame 4019, everything on incl. the shuffle, music maps+battles, enemy levels +3, tougher bosses):

| run | mode pick -> laid |
|---|---|
| Fates r59fa1 / r59fa2 / r59fa3 (paced 60 fps) | 16 / 11 / 9 ms |
| Seal r59sa1 / r59sa2 / r59sa3 (paced 60 fps) | 120 / 141 / 110 ms |
| unpaced (the pick 8 s after boot, make not finished; Fates warm, Seal cold cache) | 1161 ms / 8275 ms |

The game's own frames from the pick to the avatar screen are the same replay frames as with the randomizer off.
If Start game is pressed before the background make is done, the wait is the rest of that make (2-8 s warm).

Owner's rule test (5.2, headless half): guess A (r59agA) made and finished, then the answer changed (seed, trees,
enemy levels) to B at frame 2500: A's run and work folders were removed; the laid `runs/r59agB-99450ef5/patch.txt`
is byte-identical (sha256 a8f22d2d...) to a fresh `rando.py make --patch-out` of B with no cache in an empty folder.
The Rust page test `the_background_make_text_is_start_games_text` covers the text identity; a page robot driver was
not run.
