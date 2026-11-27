# The page robot (tools/harness/pagebot.py), round 60, hook built round 61

**In plain words.** The owner's rule for the Randomizer page: while you look at the page the game is made in the
background, any change to a row throws that guess away, and Start game uses exactly the page's values; nothing is
laid before Start game. Round 59 tested this only headless with a test hook, never on the real page. This robot
drives the real page. It also times Start game to the avatar screen.

## Why it needs one more engine piece
The page is drawn only with a window, and a window is not allowed (F-042). In a headless run there is no page: the
core answers the mode pick by itself. So the robot needs a small frontend hook, `FEF_PAGEBOT`
(plan: build/r60/screens/plans/PAGEBOT_HOOK.md). With it, a headless run keeps the mode pick waiting for the page,
draws the real page every frame into a context with no window, and clicks with real pointer events on the
rectangles the page's own controls report. The screens track may not build the engine, so the hook is a plan for
the assemble step. **Until an exe has the hook the robot refuses** ("REFUSED: this exe has no FEF_PAGEBOT hook").

## What one run does (scenario `agency`)
1. A COPY of the exe below build/ (never play/game's own exe), `--headless N --mute`, `--data`, APPDATA,
   LOCALAPPDATA and TMP under build/r60/pagebot/<name>/, below normal, no console window, the recorded new-game
   replay, kept to real speed (`FEF_HEADLESS_PACE=60`). STOP_ROUND checked every second; a visible window = failed.
2. The page opens at the mode pick. The robot clicks Everything on and waits until the background make of those
   values has FINISHED.
3. It changes two rows on the page (the first choice row to its next choice, the first on/off row flipped; read from
   `rando.py schema`), then presses Start game at once.
4. Checks (all must hold): the finished guess was thrown away and its folder is gone; only the laid run is left;
   the answer and the lay came after the Start game click; the answer text equals the page's values at the click;
   the laid patch.txt is byte-identical to a fresh `rando.py make --patch-out` of that text (no cache, empty folder).
5. Timing: ms from the click to "laid", and to the avatar creator (laid + the calibrated frames).

## Calibration (done, no hook needed)
`python tools/harness/pagebot.py calibrate` on the frozen boot-server copy (build/r60/screens/bin, sha e71515c5...),
the recorded new-game route: the core saw the mode pick at frame 4019; the avatar creator (title__ProcMyUnitEdit)
shows by frame 4045 (looked at every 5 frames), so at most 26 frames (0.43 s at 60 fps) after the answer.
Result: build/r60/pagebot/calibrate.json.

## Use
```bash
python tools/harness/pagebot.py selftest                  # 10/10: the verdict rules on invented logs
python tools/harness/pagebot.py calibrate
python tools/harness/pagebot.py run --exe "build/r61/hooks/bin/Fire Emblem Fates.exe" --name agency
python tools/harness/pagebot.py run --exe ... --name agency-seal --seal
python tools/harness/pagebot.py run ... --scenario quick     # timing: Everything on, wait for the make, Start game
python tools/harness/pagebot.py judge --name agency [--seal] # the verdict again for a finished job (no game start)
```

## Round 61: the hook is built and the robot ran (2026-11-21)
**In plain words.** The hook now exists in a test build (track hooks, its own engine copy). The robot drove the real
page headless, with no window, on Fire Emblem Fates and in the Seal edition. The owner's rule holds: rows changed after
a finished background make win, the stale guess is thrown away and its folder removed, and the laid game is
byte-for-byte a fresh make of the page's final values. Start game to the avatar screen takes about half a second when
the background make already finished; when rows were changed just before Start game, the game waits for the new make
(about 5 s Fates, 11 s Seal).

- Hook: patch build/r61/hooks/patches/0026-page-Fire-Emblem-Fates-randomizer-the-page-robot-hoo.patch (number after
  the nuz track's patches; the assemble step renumbers). Frontend only (rando_page.rs reports its control rectangles
  and thrown guesses; new pagebot.rs; lib.rs run_headless/rando()). Frontend tests 91 passed (new:
  the_page_reports_its_controls). Without FEF_PAGEBOT nothing changes: a randomizer-off headless run of the test exe
  has the same memory hashes as the round-60 exe at frames 0, 3000, 4600 and 5200 (build/r61/hooks/smoke/off-hooks).
- Test exe build/r61/hooks/bin/Fire Emblem Fates.exe, sha256 7bf3e6af... (jobs build/r61/pagebot/<name>/).
- agency (Fates, agency2): PASS. Everything on, make finished, then Recruits changed to "any" and Classes turned
  off on the page; the finished guess was discarded and its folder is gone, only the laid run is left, the answer is
  the page's values at the click, and the laid patch.txt equals a fresh make of that text (exact).
  Start game to laid 4852 ms, to the avatar screen 5295 ms.
- agency-seal1 (Seal edition): PASS, laid patch = fresh make (b973139a...). Start game to laid 10892 ms, to the
  avatar screen 11332 ms. (The first judge failed outside the game: the fresh make rebuilt the shared
  build/sources/seal layer while another track used it. The robot now builds its own layer in build/r61/pagebot/
  _sources and the verdict was taken again from the same finished run.)
- Timing, scenario quick (the guess finished, Start game with the same values), 3 tries each, all PASS:
  Fates 480, 482, 500 ms to the avatar screen (35-39 ms to laid); Seal 594, 590, 568 ms (127-151 ms to laid).
- Limits: the avatar moment is the lay plus the 26 game frames calibrated in round 60 (pick 4019 to the avatar
  creator by 4045, frozen boot-server copy), run at real speed (FEF_HEADLESS_PACE=60); the hook does not read the
  screen. The first agency run (agency1) clicked a choice list's entry in its first frame (a sizing pass, not
  clickable): the hook now clicks only a rectangle that stayed the same for two frames.


## Round 61 check on the final exe (ff85e43d, build/r61/check/pagebot)
- agency-f (Fates): PASS, laid patch = fresh make (07eb0eff on both); Start game to the avatar screen 5921 ms.
- agency-s (Seal): PASS, laid = fresh (b06b73d6); 7295 ms.
- quick-f / quick-s (guess already finished): 573 / 659 ms.
- **Plainly: the two agency runs FAIL the robot's own 2-second check (`under_2s: false`).** The verdict says PASS only
  because `under_2s` is not part of the verdict. When a row changes after the background make, Start game waits for a
  fresh make: about 6 s on Fates and 7-11 s on Seal (11.3 s in the track's run, 7.3-7.4 s at assemble and check). The
  check-step times were measured with up to 5 other robot jobs running. Only the quick runs are under 2 s.

## Round 72: the Esc window's own check list (scenario `esc`, `judge_esc`)
**In plain words.** Round 71's Esc run was judged by the New Game page's three checks (guess, stale, exact), so it
said FAIL even though the Esc part worked. The Esc Randomizer window's "Next New Game" part now has its own
scenario and its own check list, and it passes on Fire Emblem Fates and in the Seal edition, on a copy of the
installed program (game exe 853e713a).

The scenario: start a randomized game (Randomizer on, every other row at its default, spoiler log off), then over
the game: open Esc > Randomizer, change a row and close WITHOUT Keep; open it again; Keep with no change; change
Difficulty to Hard and Keep; let the background guess for the next New Game finish; close.

| Check | What must hold |
|---|---|
| game_laid_first | a randomized game was laid (a run id) before the window first opened |
| next_shown | every opening showed the Next New Game part |
| steps_known | the hook knew every step and the script ran to its end |
| game_untouched | no answer and no lay after the window opened: the game playing never changes |
| laid_run_kept | the laid run's patch.txt is still there at the end and equals a fresh make of the Start game answer |
| unkept_thrown | the change closed without Keep is not in last.json when the window opens again |
| keep_same_equal | Keep with no change writes exactly what Start game wrote (the thrown change did not come back) |
| keep_changed_one_row | Keep after one change writes last.json that differs from Start game's in that row only |
| kept_note | the part then says "Kept for the next New Game." |
| disk_last | last.json on disk at the end equals what the hook read after the last Keep |
| next_guess | the background guess started after the last Keep is of the kept values and finished |
| runs_left_ok | the runs folder holds the laid run and otherwise only guesses started after the window opened |
| expects_ok | every expect_last step was ok |

```bash
python tools/harness/pagebot.py selftest                          # 27/27 (11 of them the round-72 Esc rules)
python tools/harness/pagebot.py run --exe ... --name esc --scenario esc [--seal]
```

Results (build/r72/esc/<job>/result.json; exe copy build/r72/esc/bin, sha 853e713a...):
- esc-fates2 (Fates): **PASS**, all 13 checks; 74 s. Laid run 93ub8n2j-d4ce5de4, its patch = a fresh make
  (c6c02b9d... both); kept last.json differs from Start game's in `difficulty`
  only; the next New Game's guess 93ub8n2j-5f77c32e finished.
- esc-seal (Seal edition): **PASS**, all 13 checks; 82 s. Laid run d92d46uz-c06dfe9a, patch = a fresh make (23494095... both), guess d92d46uz-6f790374.
- esc-fates (first try, Everything on before Start game): FAIL, a robot limit, not a game fault. The hook draws
  the page into an 800 x 480 screen (pagebot.rs), half the default window (stacked layout at scale 2 is
  800 x 960). After Everything on, This run lists every changed row, so the Next New Game part starts below
  y 480 (the unkept change at y 601, Keep at y 697, Difficulty at y 646): Keep did nothing (no "Kept" note) and
  the run stopped at the hook's 10-minute page limit (675 s, exit 0, killed nothing).
  **For the owner:** in a window only 480 high (for example side by side at scale 2), the Esc window of a game
  made with Everything on would also run past the bottom edge, because This run's list has no scroll bar. This is
  read from the robot's coordinates only; no picture shows it.
- Observation (not judged): with no seed typed, the next New Game's background guess uses this game's seed
  (both 93ub8n2j on Fates, d92d46uz on Seal), so an unchanged Keep makes the same game again unless the New Game
  page picks a new seed when it opens.
- No picture of the Esc part or the help line: the hook draws with no window, and starting the game on a hidden
  Windows desktop (CreateDesktop, never switched to) gave no picture (build/r72/esc/hidden/hidden.py, 3 tries,
  about 6 minutes): the game does not get past reading the cartridge there (Vulkan and OpenGL), and PrintWindow
  with PW_RENDERFULLCONTENT returns a white client area. A plain window-DC capture returned pixels of the owner's
  own screen instead of the game; those two pictures were deleted at once and that way is refused in the script.
  The owner must look once.

## Round 74: presets, the share code and the Esc window's fit (scenarios `presets`, `escfit`, `p4`; `judge_p4`)
**In plain words.** Round 74 (patch 0036) adds two preset buttons, Light and Wild, and a Share code field to the New
Game page, and gives the Esc window's "This run" list its own scroll bar. The page draws no picture without a
window, so the robot proves these by values. Made by track page in round 74; **not run yet** (the prove step P4
runs it on the staged program). `p4` runs both parts in one job (the plan's one P4 lane).

The page part (`presets`): press Light, Wild, Light (each checked); press Wild and Copy the share code; press Light
and Random (other values, another seed); paste the copied code into the field (every value and the seed must come
back); Defaults; paste a code made by tools/randomizer/sharecode.py (Wild plus Difficulty Hard, Enemy levels 3,
growth step 45, chests on, Recolour "Easier to see", seed `p4share-74`); paste that code with a typo (nothing may
change). The Esc part (`escfit`): Randomize everything, Start game, open Esc > Randomizer with This run full (about
22 rows, spoiler button on), check Keep is drawn wholly on the hook's 800 x 480 screen, click it, check last.json.

| Check | What must hold |
|---|---|
| steps_known | the hook knew every step (no unknown_step) and ran the whole script |
| expects_ok | every expect step was ok in the run (the keys it names) |
| light_values / wild_values | after the press, the whole answer but the seed is the preset's (ingame.page_preset) |
| light_after_wild | Light after Wild gives exactly the first Light's answer text |
| copy_is_the_values | the copied text is the field's code, and sharecode.py reads it back as exactly the values at Copy (Rust encoder against the Python decoder) |
| paste_copied_equal | after other values and another seed, the pasted copy gives the values at Copy again (same text, seed too) and the help line says it was used |
| made_code_equal | a sharecode.py code pasted gives exactly the answer sharecode.py reads from it (Python encoder against the Rust decoder) |
| typo_refused | the typo code changes nothing and the help line says "This code has a typo." |
| game_laid_first | (Esc part) a randomized game was laid before the window opened |
| this_run_full | (Esc part) This run listed as many rows as the laid answer changes, at least 15 |
| keep_on_screen | (Esc part) Keep is drawn wholly on the 800 x 480 screen |
| keep_clicked | (Esc part) the click on Keep landed: the expect_last after it is ok |

New hook steps (pagebot.rs, patch 0036): `{"paste": text}`, `{"paste_copied": true}`, `{"expect_target": target}`;
a `copied` event from egui's copy command (no real clipboard is touched in a headless run); click events carry the
field's code, expect events the help line's note.

```bash
python tools/harness/pagebot.py selftest                          # 75/75 (48 of them the round-74 P4 rules)
python tools/harness/pagebot.py run --exe <staged copy> --name p4 --scenario p4 [--seal] --top build/r74/p4
```

## Round 80: the Helpers rows save (scenario `helpers`, `judge_helpers`; patch 0037)
**In plain words.** Round 80 put a Helpers heading in the Esc window (True hit Off / On). The robot starts the
original game, opens Esc over it, clicks True hit On, and reads the job's OWN settings.toml (its APPDATA is below the
job folder) to see the click saved. The owner's real `%APPDATA%\zakuro\settings.toml` is only hashed, before and after.

New hook steps (pagebot.rs, patch 0037): `{"esc": "paused"}` opens the Paused window over the game (targets
`helpers:section`, `helpers:opt:true_hit=<off|on>`; a change runs `apply_settings`) and `{"esc": "close"}` closes it;
`{"expect_settings": {...}}` reads the program's settings file (`settings::path()`) and compares the named keys.

| Check | What must hold |
|---|---|
| hook / steps_known | the exe has the hook and knew every step |
| game_first | the original game was laid before the Esc window opened |
| opened / closed / ended | Esc opened, closed, and the run ended by itself |
| before_default / no_table_at_defaults | before the click the file reads normal / off with no `[fates_helpers]` table |
| clicked / changed_once | one click on True hit On, and it changed the row once |
| after_saved / table_written | the file then holds `true_hit = true` (`enemy_phase = "normal"`) in `[fates_helpers]` |
| own_settings_file | every file read is the job's own, never the owner's |
| on_screen | True hit's On is drawn wholly on the 800 x 480 screen |
| real_settings_unchanged | the owner's settings.toml hashed the same before and after |

Result: **PASS** on the round-80 repair program (build/r80/repair/s1/run.log); real settings.toml ed6d9057 before
and after.

## Round 81: the New Game defaults rows save (scenario `newgame`, `judge_newgame`; patch 0039)
**In plain words.** Round 81 added a collapsing "New Game defaults" line under Helpers with four rows (Battle
animations, Map speed, Enemy turn skip, HP bars), each starting on Game's choice. The robot opens Esc over the original
game, opens the line, clicks Battle animations Off and Enemy turn skip All, then puts Battle animations back to Game's
choice. The job's own settings.toml must end with exactly `enemy_skip = "all"` among the four New Game keys (a row at
Game's choice is not written). Targets: `helpers:newgame:section` and, while the line is open,
`helpers:opt:<key>=<word>` (keys `battle_animations`, `map_speed`, `enemy_skip`, `hp_bars`; words `game`, `off`, `on`,
`normal`, `fast`, `fast_while_a`, `move`, `all`). In `expect_settings` an expected `"game"` matches an absent key.

| Check | What must hold |
|---|---|
| hook / steps_known / game_first / opened / closed / ended | as in `helpers` |
| before_default / no_table_at_defaults | before any click: no New Game key, True hit off, no `[fates_helpers]` table |
| section_opened | the line was clicked after "before" and before any row click |
| row_clicks | exactly the three row clicks, in order, each after the line was opened |
| changed_three_times | opening the line saved nothing; each row click saved once |
| set_saved / back_saved | after the two set rows, and after the put-back, the file holds exactly those rows |
| table_written / file_rows_exact / file_others_kept | at the end: the table, exactly `enemy_skip = "all"` among the four keys, True hit off and enemy phase normal |
| own_settings_file | every file read is the job's own |
| on_screen | the lowest row's last choice (HP bars On) is drawn wholly on the 800 x 480 screen |
| real_settings_unchanged | the owner's settings.toml hashed the same before and after |

Results: **PASS, 19/19** on the round-81 B1 program (aac1b576, build/r81/s1/newgame, 69.1 s) and again on the repair
program that was installed (293b066b, build/r81/repair/s1/newgame, 69.1 s); real settings.toml ed6d9057 before and
after both. The Esc window itself draws no picture headless: the owner looks once (ok list).

```bash
python tools/harness/pagebot.py selftest                          # 129/129 (round 81)
python tools/harness/pagebot.py run --exe <staged copy> --top build/r81/s1 --name newgame --scenario newgame
```
