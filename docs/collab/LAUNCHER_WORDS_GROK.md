# Grok (Hermes) on the Getting ready window's words (round 77, part words)

Asked 2026-11-25 by the round-77 words step, one consult, facts only (no game data, no private details). The
answer is used in `tools/play/launcher.py` (`WORDS`), `Read Me First.txt` (First start) and docs/PLAY.md 6e.
Grok's answer is kept as given; Claude's notes follow it.

## The question (as sent)

Round 77 of the Fire Emblem Fates PC port: please word the lines of a small console window short and plain. Facts only; no game data is involved.

What the window is: when a player double-clicks PLAY.bat in a freshly unzipped port folder, a console window titled "Getting ready" checks four rows before the game starts: (1) their own game file (a decrypted .cci dump of Fire Emblem Fates Special Edition (USA), which they must supply), (2) Seal of Flames by Laz14, an optional fan mod they may have downloaded themselves as a zip, (3) the game program (either a one-game program they build once with a Python command that takes roughly 30-60 minutes, or an existing Zakuro emulator folder that has recompiled the game), (4) the Randomizer, which needs a one-time preparation that reads the game file and writes about 1.8 GB. When nothing is missing the window never appears. Keys are typed then Enter (it is a plain console). The window never downloads anything, never builds anything, never copies the game file (it remembers the path).

Ways to find the game file: 1 Look for it (searches roms, Downloads, Desktop and Documents, at most 3 folders deep and 30 seconds, reads names and sizes only), 2 Choose the file (opens the normal Windows Open window), 3 Type or drag the path (drag the file from Explorer onto the console window, then Enter). A wrong file gets exactly one sentence saying why, and nothing is saved.

Below are the current lines, one per key, as key = "text". Please return a reworded version of each line you would change, in the same key = "text" form, plus a one-line reason only where it is not obvious. Rules:
- keep every {placeholder} exactly (for example {path}, {game}, {edition}, {gb}, {free:.1f}, {size:,}); the program fills them in;
- keep the word "Getting ready" in title, and keep rando_dry starting with "[dry run] would run";
- keep each refusal (keys bad_*) one sentence, and keep the facts (3 folders, 30 seconds, 1.8 GB, 30-60 minutes as a rough guess, the gamebanana address, never downloads, never builds);
- the leading spaces and the key letters (1, 2, 3, Q, S, P, Z, Y, R) stay as they are; prompts end with ": ";
- plain English for a non-technical player; short; no exclamation marks; no jokes.

Also, separately: suggest 6-10 short plain lines for a "First start" section of the port's Read Me First.txt (a plain-text note), telling a new player what the Getting ready window will ask and that PLAY.bat --setup opens it again.

Current lines:
title = "Getting ready ({game} PC port)"
row_game = "Your game file ({game} {edition}, .cci)"
row_seal = "Seal of Flames by Laz14 (optional)"
row_program = "The game program"
row_rando = "The Randomizer (optional)"
game_missing = "not found yet"
game_ok = "found and checked: {path}"
game_bad = "not usable yet"
seal_missing = "not found (that is fine)"
seal_found = "found, not installed yet: {path}"
seal_installed = "installed"
seal_broken = "installed, but needs repair (P installs it again)"
seal_skipped = "skipped (PLAY.bat --setup asks again)"
program_standalone = "ready: play\\game\\{name}"
program_record_bad = "there, but not the one its build record describes (PLAY says more)"
program_zakuro = "Zakuro: {path}"
program_missing = "not built yet"
rando_ready = "prepared"
rando_not = "not prepared (R does it once)"
find_head = "Find your game file:"
find_1 = "  1  Look for it (roms, Downloads, Desktop and Documents; up to 3 folders deep, at most 30 seconds)"
find_2 = "  2  Choose the file (the Windows Open window)"
find_3 = "  3  Type or drag the path (drag the file onto this window, then press Enter)"
quit = "  Q  Quit"
ask = "Your choice: "
ask_path = "Path of the file (or just Enter to go back): "
ask_folder = "Folder that holds zakuro.exe (2 opens the Windows Open window; just Enter goes back): "
ask_pick = "Number of the file to use (or just Enter to go back): "
bad_key = "Please press one of the keys shown, then Enter."
looking = "Looking for the game file (names and sizes only; at most {seconds:.0f} seconds) ..."
look_none = "No game file of the right size was found there. Try 2 or 3."
look_timeout = "Stopped looking after {seconds:.0f} seconds."
look_many = "Found {count} possible game files:"
window_none = "The Windows Open window is not available here; type or drag the path instead."
window_cancel = "No file was chosen."
window_title = "Choose your {game} game file (.cci)"
checking = "Checking the file's fingerprint once (about 10 seconds)"
accepted = "This is your game file. Remembered (the file stays where it is)."
accepted_roms = "This is your game file (in the roms folder)."
config_wins = "Note: play\\config.json names a game file by hand ({path}); PLAY uses that one first."
bad_missing = "There is no file at {path}."
bad_folder = "{path} is a folder, not the game file; choose the .cci file itself."
bad_update = "This is an update or add-on file, not the game; choose the .cci game file."
bad_not_cci = "This is not a 3DS game file (.cci)."
bad_title = "This is a different game or edition (title {title}), not {game} {edition}."
bad_product = "This is not the {edition} edition (product code {product}, expected {want})."
bad_encrypted = "This is the right game, but still encrypted; make a decrypted dump of your own cartridge (GodMode9 can)."
bad_trimmed = "This is the right game, but a trimmed dump ({size:,} bytes; the clean one is {want:,}), so its fingerprint differs."
bad_hash = "This is the right game, but not the clean dump: its fingerprint differs."
bad_cia = "An update file lies beside it ({names}); move it to another folder, then try again."
bad_unreadable = "The file could not be read ({error})."
seal_text = "Seal of Flames by Laz14 is a fan mod, not part of this port. It is optional."
seal_where = "You can get it yourself at {address} (this window never downloads anything)."
seal_ask = "  S  Skip it        P  Point to the zip you downloaded"
seal_ask_found = "  S  Skip it        P  Install it from the zip found above"
seal_ask_path = "Path of the Seal of Flames zip (2 opens the Windows Open window; just Enter goes back): "
window_title_seal = "Choose the Seal of Flames zip you downloaded"
window_title_zakuro = "Choose zakuro.exe"
seal_refused = "That zip was not installed and is not remembered."
seal_remembered = "Remembered where the zip is (it stays there, unchanged)."
seal_dry = "[dry run] the zip passed its check; nothing was installed."
prog_text = "The game program is not there yet. Two ways to get it:"
prog_z = "  Z  You have Zakuro and it has recompiled the game: point to the folder that holds zakuro.exe"
prog_cmd = "     Or make the one-game program once with:   python tools\\engine\\engine.py port"
prog_time = "     (about 30-60 minutes the first time, a rough guess). This window never starts a build."
prog_y = "  Y  Check what it needs now (engine.py port --dry-run: it only checks, it builds nothing)"
prog_bad_folder = "There is no zakuro.exe in {path}."
prog_zakuro_ok = "Zakuro found. Remembered (nothing was copied)."
rando_offer = "  R  Prepare the Randomizer once (it reads your game file and writes about {gb} GB into the extracted folder here)"
rando_space = "Not enough free space for the Randomizer's files ({free:.1f} GB free; about {need:.1f} GB needed). Nothing was written."
rando_done = "The Randomizer is prepared."
rando_failed = "The Randomizer's preparation stopped (exit {code}); the lines above say why."
rando_dry = "[dry run] would run: {cmd}"
ready = "Ready. Press Enter to play."
ready_dry = "Ready. Press Enter to go on (dry run: nothing starts)."
ready_change = "  1  2  3  Change the game file        P  Seal of Flames zip        Z  Zakuro folder"
quit_done = "Nothing was started."

## Grok's answer

title = "Getting ready ({game} PC port)"
row_game = "Your copy of {game} {edition} (a .cci file)"
game_bad = "found, but it cannot be used"
seal_broken = "installed, but damaged (press P to install it again)"
program_standalone = "ready, in play\\game\\{name}"
program_record_bad = "there, but it does not match its build note (PLAY explains)"
program_zakuro = "using Zakuro at {path}"
rando_not = "not prepared yet (press R once)"
find_head = "Find your copy of the game:"
find_1 = "  1  Look in the usual folders (roms, Downloads, Desktop and Documents; up to 3 folders deep, at most 30 seconds)"
find_2 = "  2  Choose the file (the Windows file window)"
ask_folder = "Folder that holds zakuro.exe (2 opens the Windows file window; Enter goes back): "
look_none = "No copy of the right size was found. Try 2 or 3."
window_title = "Choose your {game} file (.cci)"
checking = "Checking this file once (about 10 seconds)"
accepted = "This is the right file. Its place is remembered. The file stays where it is."
accepted_roms = "This is the right file. It is already in the roms folder."
config_wins = "Note: play\\config.json already names a game file ({path}). PLAY uses that one first."
bad_encrypted = "This is the right game, but it is still encrypted; make a decrypted copy of your own cartridge (GodMode9 can do that)."
bad_hash = "This is the right game, but it is not the clean copy: its check does not match."
prog_z = "  Z  You already have Zakuro, and it has rebuilt the game: point to the folder that holds zakuro.exe"
prog_cmd = "     Or make the one-game program once, with:   python tools\\engine\\engine.py port"
prog_y = "  Y  Check what a build needs (engine.py port --dry-run: it only checks, it builds nothing)"

The word "fingerprint" is the one a new player will not know. "Check" says the same thing. "Found, but it cannot be used" is clearer than "not usable yet" when the file was found.

First start, for Read Me First.txt:

Double-click PLAY.bat.
If everything is already in place, the game starts and this window does not appear.
If something is missing, a window titled Getting ready opens.
It asks for your own copy of the game. This port does not include that file.
It can look in roms, Downloads, Desktop and Documents, or you can choose the file yourself.
Seal of Flames is optional. The window never downloads it.
The game program is built once, or you point at a Zakuro folder that has already rebuilt the game. The window never starts that build.
The Randomizer is optional. Preparing it once reads your game file and needs about 1.8 GB of free space.
Nothing is copied. The window only remembers where your file is.
To see these questions again, double-click is not required: run PLAY.bat --setup.

## Claude's notes (what was taken)

Taken into `tools/play/launcher.py` `WORDS` (tests unchanged and passing: they read `WORDS`):

- Taken as given: `game_bad`, `seal_broken`, `program_standalone`, `program_zakuro`, `rando_not`, `find_head`,
  `find_1`, `find_2`, `ask_folder`, `look_none`, `window_title`, `checking`, `accepted_roms`, `config_wins`,
  `prog_cmd`, `prog_y`.
- Taken with a small change:
  - `row_game`: "Your copy of {game} {edition}, a .cci file" (a comma instead of the brackets, because the edition
    already ends in "(USA)").
  - `program_record_bad`: Grok's shape, but "build record" kept (PLAY's own stop lines and the file
    `build-record.json` use that name).
  - `accepted`: Grok's three short sentences joined as two ("Its place is remembered; the file stays where it is.").
  - `prog_z`: "recompiled" kept instead of "rebuilt", because Zakuro's own button is called Recompile.
  - `bad_hash`: "not the clean copy" taken, "fingerprint" kept ("its fingerprint does not match"): `bad_trimmed`
    and Read Me First already use the word and explain it, and "its check does not match" said less.
  - `bad_encrypted`: not taken; the current line is already one sentence of the same length.
- Made to match Grok's choices: "the Windows file window" also in `window_none` and `seal_ask_path`; "Enter goes
  back" also in `ask_path`, `ask_pick` and `seal_ask_path`.
- Unchanged (Grok left them as they were): the title, every other row and status, the Seal, Randomizer and Ready
  lines, and every other refusal.
- The first-start lines went into `Read Me First.txt` ("First start: the Getting ready window") in the note's own
  style, with the keys listed; Grok's last line ("double-click is not required") was not used as written.
