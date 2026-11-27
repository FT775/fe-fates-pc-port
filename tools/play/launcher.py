"""Getting ready: PLAY's built-in launcher (round 77, docs/LAUNCHER_PLAN.md parts L1-L4).

Before the game starts, it makes sure the player's own game file is found and is the right one, that a game
program is there, and offers the Randomizer's one-time preparation (and, in the Seal edition, its optional row:
tools/seal/launcher_seal.py, loaded only when that folder is there; round 84, F-072). It is the
console window PLAY.bat already opens; the only other window is the normal Windows "Open" window, opened
through PowerShell when the player presses 2 (Python's Tk is not used: the bundled Python of the download plan
has none).

    PLAY.bat              shows Getting ready only when something is missing or wrong (silent otherwise)
    PLAY.bat --setup      shows it every time (to point to a moved file, or change an optional choice)

play.py calls run() when PLAY.bat started it (PLAY.bat sets FEF_LAUNCHER=1) or with --setup; a plain
`python tools/play/play.py` never shows the window, so every older caller (tests, tools) works as before.

What it learns goes into play/launcher.json (git-ignored, never in a package): "rom" (the game file's path when
it is not in roms/), the Seal edition's "seal_zip" and "seal_skipped", "randomizer_prepared" and
"zakuro_dir". play/config.json is never rewritten (F-048). The fingerprint result stays in play/state.json, the
same cache play.py's check_rom uses. (A freshly unzipped folder's portable places are play.py's: play/appdata,
made on its first start.)

What it never does: copy, move or upload the game or the mod (it reads a file to fingerprint it and remembers
the path); download anything or open a browser; start a build (the program row only explains, and runs
`engine.py port --dry-run`, which builds nothing, after a Y); write anything itself outside play/ (the
Randomizer preparation into extracted/ by romfs.py, and the Seal edition's install, start only on the player's
key press; tools/seal/launcher_seal.py says what that one writes, and that --dry-run writes nothing).

"Look for it" (key 1) looks in roms/, Downloads, Desktop and Documents, at most 3 folders deep and at most 30
seconds. It reads names and sizes only, and opens a file only when its size is exactly the clean game's
(config/game.json rom_size), then only its first 512 header bytes. Links, junctions and every other reparse point
are skipped (also on Python 3.11, which has no DirEntry.is_junction), and so are cloud placeholders (OneDrive and
the like: offline or recall-on-open/-on-data-access files), which are never opened.

A game file that is the right game but not usable as it is (its fingerprint differs, a trimmed dump, or an update
.cia beside it) does not open the window by itself: PLAY then prints its STOP with the way out (a clean dump,
"check_rom": "header" in play/config.json, or PLAY.bat --anyway), as before round 77. When the window shows for
another reason (or with --setup), it prints the same way out under that file's sentence.

Every line the window prints is in WORDS below, so the wording can change in one place (round 77 part words,
with Grok: docs/collab/LAUNCHER_WORDS_GROK.md).
Python 3 standard library only. Nothing here holds Nintendo data: sizes, title id and SHA-256 are identifiers.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(REPO / "tools") not in sys.path:
    sys.path.insert(0, str(REPO / "tools"))
import paths  # noqa: E402  (F-048: roms/)

SEARCH_DEPTH = 3                 # folders below each place
SEARCH_SECONDS = 30.0
HEADER_BYTES = 0x200
ROMFS_GB = 1.8                   # extracted/romfs, about (docs/LAUNCHER_PLAN.md step 6)
ROMFS_NEED_FREE = int(2.5 * 2**30)
UPDATE_SUFFIXES = paths.UPDATE_SUFFIXES
# Windows file attributes (stat st_file_attributes): links/junctions, and cloud placeholders that must not be opened
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x40000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x400000
PLACEHOLDER_ATTRIBUTES = FILE_ATTRIBUTE_OFFLINE | FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS

# Every line the window prints. {names} are filled in; part words (round 77) may reword them.
WORDS = {
    "title": "Getting ready ({game} PC port)",
    "row_game": "Your copy of {game} {edition}, a .cci file",
    "row_program": "The game program",
    "row_rando": "The Randomizer (optional)",
    "game_missing": "not found yet",
    "game_ok": "found and checked: {path}",
    "game_bad": "found, but it cannot be used",
    "program_standalone": "ready, in play\\game\\{name}",
    "program_record_bad": "there, but it does not match its build record (PLAY explains)",
    "program_zakuro": "using Zakuro at {path}",
    "program_zakuro_not_recompiled": "Zakuro found at {path}, but it has not recompiled the game yet",
    "program_missing": "not built yet",
    # round 85: one plain line under the rows when Zakuro is there but the game was never recompiled
    "zakuro_recompile": "To fix the [!]: open Zakuro once, press Recompile next to {game} in its library, wait for it "
                        "(10-20 minutes), close Zakuro, then PLAY again.",
    "rando_ready": "prepared",
    "rando_not": "not prepared yet (press R once)",
    # finding the game file
    "find_head": "Find your copy of the game:",
    "find_1": "  1  Look in the usual folders (roms, Downloads, Desktop and Documents; up to 3 folders deep, at most 30 "
              "seconds)",
    "find_2": "  2  Choose the file (the Windows file window)",
    "find_3": "  3  Type or drag the path (drag the file onto this window, then press Enter)",
    "quit": "  Q  Quit",
    "ask": "Your choice: ",
    "ask_path": "Path of the file (Enter goes back): ",
    "ask_folder": "Folder that holds zakuro.exe (2 opens the Windows file window; Enter goes back): ",
    "ask_pick": "Number of the file to use (Enter goes back): ",
    "bad_key": "Please press one of the keys shown, then Enter.",
    "looking": "Looking for the game file (names and sizes only; at most {seconds:.0f} seconds) ...",
    "look_none": "No copy of the right size was found. Try 2 or 3.",
    "look_timeout": "Stopped looking after {seconds:.0f} seconds.",
    "look_many": "Found {count} possible game files:",
    "window_none": "The Windows file window is not available here; type or drag the path instead.",
    "window_cancel": "No file was chosen.",
    "window_title": "Choose your {game} file (.cci)",
    "checking": "Checking this file once (about 10 seconds)",
    "accepted": "This is the right file. Its place is remembered; the file stays where it is.",
    "accepted_roms": "This is the right file. It is already in the roms folder.",
    "config_wins": "Note: play\\config.json already names a game file ({path}). PLAY uses that one first.",
    # one sentence each when a file is not the game (nothing is written)
    "bad_missing": "There is no file at {path}.",
    "bad_folder": "{path} is a folder, not the game file; choose the .cci file itself.",
    "bad_update": "This is an update or add-on file, not the game; choose the .cci game file.",
    "bad_not_cci": "This is not a 3DS game file (.cci).",
    "bad_title": "This is a different game or edition (title {title}), not {game} {edition}.",
    "bad_product": "This is not the {edition} edition (product code {product}, expected {want}).",
    "bad_encrypted": "This is the right game, but still encrypted; make a decrypted dump of your own cartridge "
                     "(GodMode9 can).",
    "bad_trimmed": "This is the right game, but a trimmed dump ({size:,} bytes; the clean one is {want:,}), "
                   "so its fingerprint differs.",
    "bad_hash": "This is the right game, but not the clean copy: its fingerprint does not match.",
    "bad_cia": "An update file lies beside it ({names}); move it to another folder, then try again.",
    "bad_unreadable": "The file could not be read ({error}).",
    # the way out for the game file PLAY would use when it is the right game but not usable as is (PLAY's old STOP)
    "way_out_rom": "Use your clean dump, set \"check_rom\": \"header\" in play\\config.json, or start it once "
                   "with PLAY.bat --anyway (Q quits this window).",
    "way_out_cia": "Move it to another folder, or start with it once with PLAY.bat --anyway (Q quits this window).",
    "window_title_zakuro": "Choose zakuro.exe",
    # the program (docs/LAUNCHER_PLAN.md section 5)
    "prog_text": "The game program is not there yet. Two ways to get it:",
    "prog_z": "  Z  You already have Zakuro, and it has recompiled the game: point to the folder that holds zakuro.exe",
    "prog_cmd": "     Or make the one-game program once, with:   python tools\\engine\\engine.py port",
    "prog_time": "     (about 30-60 minutes the first time, a rough guess). This window never starts a build.",
    "prog_y": "  Y  Check what a build needs (engine.py port --dry-run: it only checks, it builds nothing)",
    "prog_y_checking": "Checking what a build needs (it builds nothing; it reads your whole game file, so allow a minute or two, an estimate) ...",
    # round 85: the check's own STOP line becomes one plain sentence with the command to run (never a raw "STOP:")
    "prog_y_fetch": "The build's source code is not on this PC yet: get it once with   python tools\\engine\\engine.py "
                    "fetch   then   python tools\\engine\\engine.py apply   then build with   "
                    "python tools\\engine\\engine.py port",
    "prog_y_apply": "Our changes are not added to the build's source code yet: add them once with   "
                    "python tools\\engine\\engine.py apply   then build with   python tools\\engine\\engine.py port",
    "prog_y_other": "A build cannot start yet ({reason}); after fixing that, check again with   "
                    "python tools\\engine\\engine.py port --dry-run",
    "prog_y_ok": "The check found everything a build needs. To build, run   python tools\\engine\\engine.py port   "
                 "in a command window (this window never starts a build).",
    "prog_y_failed": "The build check could not run ({reason}); try it yourself with   "
                     "python tools\\engine\\engine.py port --dry-run",
    "prog_bad_folder": "There is no zakuro.exe in {path}.",
    "prog_zakuro_ok": "Zakuro found. Remembered (nothing was copied).",
    # the Randomizer
    "rando_offer": "  R  Prepare the Randomizer once (it reads your game file and writes about {gb} GB into the "
                   "extracted folder here)",
    "rando_space": "Not enough free space for the Randomizer's files ({free:.1f} GB free; about {need:.1f} GB "
                   "needed). Nothing was written.",
    "rando_done": "The Randomizer is prepared.",
    "rando_failed": "The Randomizer's preparation stopped (exit {code}); the lines above say why.",
    "rando_dry": "[dry run] would run: {cmd}",
    # Ready
    "ready": "Ready. Press Enter to play.",
    "ready_dry": "Ready. Press Enter to go on (dry run: nothing starts).",
    "ready_change": "  1  2  3  Change the game file        Z  Zakuro folder",
    "quit_done": "Nothing was started.",
}

# Round 84 (Seal edition split B, F-072): the Seal edition's row, question and install live in tools/seal (the
# Vanilla+ zip leaves that folder out). Loaded only when it is there; its words join WORDS (its change line is
# "ready_change_seal"). Without it the window has no Seal row and never imports sof.
SEAL_DIR = REPO / "tools" / "seal"


def load_seal_part():
    """tools/seal/launcher_seal.py, or None when this folder is the Vanilla+ edition (or that file cannot load:
    the window then works as the Vanilla+ one)."""
    if not (SEAL_DIR / "launcher_seal.py").is_file():
        return None
    if str(SEAL_DIR) not in sys.path:
        sys.path.insert(0, str(SEAL_DIR))
    try:
        import launcher_seal  # noqa: PLC0415
    except Exception:  # noqa: BLE001  an optional edition's fault must never stop PLAY
        return None
    return launcher_seal


SEAL = load_seal_part()
if SEAL is not None:
    WORDS.update(SEAL.WORDS)


def say(key: str, out=print, **kw) -> None:
    out(WORDS[key].format(**kw))


# ---------------------------------------------------------------------------------------------- paths


def normalize_path(text: str | None) -> str | None:
    """A typed or dragged path: spaces and one pair of quotes around it removed (Explorer quotes a dragged path
    with spaces; PowerShell adds "& '...'"). None when nothing is left."""
    if text is None:
        return None
    s = text.strip().strip("﻿").strip()
    if s.startswith("& "):
        s = s[2:].strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    if s.lower().startswith("file:///"):
        s = urllib.parse.unquote(s[8:])          # a pasted address: %20 and the like back to letters
    return s or None


def home() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home())


def search_roots(rom_repo: Path) -> list[Path]:
    """roms/, Downloads, Desktop and Documents (those that exist), each once."""
    h = home()
    out: list[Path] = []
    for p in (Path(rom_repo) / "roms", h / "Downloads", h / "Desktop", h / "Documents"):
        try:
            key = p.resolve()
        except OSError:
            continue
        if p.is_dir() and all(key != q.resolve() for q in out):
            out.append(p)
    return out


def header_title(path: Path, opener=open) -> int | None:
    """The NCSD media id from the first 512 bytes, or None."""
    try:
        with opener(path, "rb") as f:
            head = f.read(HEADER_BYTES)
    except OSError:
        return None
    if len(head) < HEADER_BYTES or head[0x100:0x104] != b"NCSD":
        return None
    return struct.unpack_from("<Q", head, 0x108)[0]


def file_attributes(st) -> int:
    """Windows file attributes of an lstat result (0 elsewhere)."""
    return int(getattr(st, "st_file_attributes", 0) or 0)


def is_link(entry, st) -> bool:
    """A symbolic link, a junction or any other reparse point (st: the entry's own stat, links not followed).
    DirEntry.is_junction is new in Python 3.12; the attribute bit works on 3.11 too."""
    if entry.is_symlink():
        return True
    junction = getattr(entry, "is_junction", None)
    if junction is not None and junction():
        return True
    return bool(file_attributes(st) & FILE_ATTRIBUTE_REPARSE_POINT)


def look_for(roots, *, size: int, title: int, depth: int = SEARCH_DEPTH, seconds: float = SEARCH_SECONDS,
             clock=time.monotonic, opener=open) -> tuple[list[Path], bool]:
    """Files under roots (at most `depth` folders below each) whose size is exactly `size` and whose header has
    `title`. Only names and sizes are read (os.scandir); a file is opened only when its size matches, and then
    only its header. Links, junctions and other reparse points are not followed; cloud placeholders (offline,
    recall on open or on data access) are never opened. Returns (found, timed_out)."""
    start = clock()
    found: list[Path] = []
    stack: list[tuple[Path, int]] = [(Path(r), 0) for r in reversed(list(roots))]
    while stack:
        folder, level = stack.pop()
        try:
            entries = []
            with os.scandir(folder) as it:
                for entry in it:                         # a very large folder also stops at the time cap
                    if clock() - start > seconds:
                        return found, True
                    entries.append(entry)
            entries.sort(key=lambda e: e.name.lower())
        except OSError:
            continue
        subs = []
        for entry in entries:
            if clock() - start > seconds:
                return found, True
            try:
                st = entry.stat(follow_symlinks=False)
                if is_link(entry, st):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if level < depth:
                        subs.append(Path(entry.path))
                    continue
                if file_attributes(st) & PLACEHOLDER_ATTRIBUTES:        # in the cloud: opening it would download it
                    continue
                if entry.is_file(follow_symlinks=False) and st.st_size == size:
                    if header_title(Path(entry.path), opener) == title:
                        found.append(Path(entry.path))
            except OSError:
                continue
        stack.extend((s, level + 1) for s in reversed(subs))
    return found, False


def open_window_script(title: str) -> str:
    """The PowerShell lines that show the normal Windows Open window and print the chosen path (UTF-8)."""
    safe = title.replace("'", "''")
    return ("$ErrorActionPreference='Stop';"
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$o=New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
            "$d=New-Object System.Windows.Forms.OpenFileDialog;"
            f"$d.Title='{safe}';"
            "$d.Filter='Game file (*.cci;*.3ds)|*.cci;*.3ds|Zip (*.zip)|*.zip|zakuro.exe|zakuro.exe|All files (*.*)|*.*';"
            "$d.CheckFileExists=$true;"
            "if($d.ShowDialog($o) -eq [System.Windows.Forms.DialogResult]::OK){"
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;[Console]::Out.Write($d.FileName)}")


def open_window_command(title: str, which=shutil.which) -> list[str] | None:
    """The command for the Windows Open window, or None when PowerShell is not there (then: typing)."""
    exe = which("powershell") or which("pwsh")
    if not exe:
        return None
    return [exe, "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass", "-Command",
            open_window_script(title)]


# ------------------------------------------------------------------------------------------- the checks


def read_header(path: Path) -> dict | None:
    """NCSD + first NCCH header: media id, program id, product code, decrypted. None when not a cartridge image."""
    with Path(path).open("rb") as f:
        ncsd = f.read(0x200)
        if len(ncsd) < 0x200 or ncsd[0x100:0x104] != b"NCSD":
            return None
        media = struct.unpack_from("<Q", ncsd, 0x108)[0]
        f.seek(struct.unpack_from("<I", ncsd, 0x120)[0] * 0x200)
        ncch = f.read(0x200)
    if len(ncch) < 0x200 or ncch[0x100:0x104] != b"NCCH":
        return {"media": media, "program": None, "product": "", "decrypted": False}
    return {"media": media, "program": struct.unpack_from("<Q", ncch, 0x118)[0],
            "product": ncch[0x150:0x160].split(b"\0", 1)[0].decode("ascii", "replace"),
            "decrypted": bool(ncch[0x18F] & 0x04)}


def check_game_file(path, play, *, mode: str = "full", state: dict | None = None, out=print) -> tuple[bool, str, dict]:
    """(ok, one sentence, cache entry) for a candidate game file. Reads only; writes nothing. The fingerprint is
    taken from play/state.json's cache when the path, size and time match (play.check_rom's cache)."""
    p = Path(path)
    g = {"game": play.GAME, "edition": play.EDITION}
    if not p.exists():
        return False, WORDS["bad_missing"].format(path=p), {}
    if p.is_dir():
        return False, WORDS["bad_folder"].format(path=p), {}
    if p.suffix.lower() in UPDATE_SUFFIXES:
        return False, WORDS["bad_update"], {}
    try:
        head = read_header(p)
        st = p.stat()
    except OSError as error:
        return False, WORDS["bad_unreadable"].format(error=error), {}
    if head is None:
        return False, WORDS["bad_not_cci"], {}
    if head["media"] != play.TITLE_ID or head["program"] not in (None, play.TITLE_ID):
        return False, WORDS["bad_title"].format(title=f"{head['media']:016X}", **g), {}
    if head["program"] is None:
        return False, WORDS["bad_not_cci"], {}
    if head["product"] != play.PRODUCT_CODE:
        return False, WORDS["bad_product"].format(product=head["product"], want=play.PRODUCT_CODE, **g), {}
    if not head["decrypted"]:
        return False, WORDS["bad_encrypted"], {}
    stops, _dlc = play.classify_cias(p)
    if stops:
        return False, WORDS["bad_cia"].format(names=", ".join(stops)), {}
    if str(mode).lower() == "header":
        return True, "", {}
    if st.st_size != play.ROM_SIZE:
        return False, WORDS["bad_trimmed"].format(size=st.st_size, want=play.ROM_SIZE), {}
    key = {"path": str(p.resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    cached = (state or {}).get("rom_check")
    if isinstance(cached, dict) and all(cached.get(k) == v for k, v in key.items()) and cached.get("sha256"):
        digest = cached["sha256"]
    elif out is print:
        print(WORDS["checking"], end="", flush=True)
        digest = play.sha256_file(p, progress=True)
    else:
        out(WORDS["checking"])
        digest = play.sha256_file(p, progress=False)
    if digest != play.ROM_SHA256:
        return False, WORDS["bad_hash"], {}
    return True, "", dict(key, sha256=digest)


def current_rom(play, config: dict) -> tuple[Path | None, str]:
    """The game file PLAY would use now (config "rom", launcher.json "rom", roms/), or (None, why)."""
    try:
        return play.effective_rom(dict(config), []), ""
    except play.Stop as stop:
        text = str(stop).splitlines()[-1] if str(stop) else ""
        return None, ("" if text.startswith("No game file found") else text)


def in_roms(play, path: Path) -> bool:
    try:
        return Path(path).resolve().parent == (Path(play.ROM_REPO) / "roms").resolve()
    except OSError:
        return False


def needs_window(play, config: dict) -> list[str]:
    """Why the window must show ([] = PLAY goes on without it). Prints nothing except play.check_rom's own
    one-time fingerprint line, which PLAY would print next anyway (then it hits the cache).

    A game file that is the right game but not usable as it is (its fingerprint differs, a trimmed dump, an update
    .cia beside it) does not open the window: PLAY's own STOP then names the way out (a clean dump, "check_rom":
    "header" in play/config.json, or PLAY.bat --anyway), exactly as before round 77."""
    why: list[str] = []
    if program_status(play, config)["kind"] is None:
        why.append("program")
    rom, _ = current_rom(play, config)
    if rom is None:
        return why + ["game"]
    try:
        play.inspect_rom(rom)
        play.check_rom(dict(config), play.load_state(), False, [])      # fills the fingerprint cache only
    except play.Stop:
        return why + ["game"]
    return why


def program_status(play, config: dict) -> dict:
    exe = play.standalone_exe(config)
    if exe is not None:
        return {"kind": "standalone", "path": exe}
    try:
        return {"kind": "zakuro", "path": play.find_zakuro(config)}
    except play.Stop:
        return {"kind": None, "path": None}


def zakuro_recompiled(play, config: dict, exe: Path) -> bool:
    """False when PLAY would stop because Zakuro has not recompiled the game yet (round 85). It asks play.py's own
    check_recompiled (read only: Zakuro's settings.toml and the %APPDATA%\\3dsrecomp library are only looked at), so
    the row and PLAY never disagree; zakuro_args with --interpreter or --recompiled, or Zakuro's own "recompiled =
    false", count as known, as in PLAY."""
    blockers: list[str] = []
    try:
        play.check_recompiled(config, Path(exe), play.active_data_dir(config), [], blockers, False)
    except (play.Stop, OSError):
        return False
    return not blockers


def engine_stop(text: str) -> tuple[list[str], str]:
    """engine.py's output split into the lines before its "STOP: ..." and the STOP message itself ("" = none).
    engine.py prints its STOP last (stderr), so everything from that line on is the message."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("STOP:"):
            return lines[:i], "\n".join([line[len("STOP:"):].strip(), *lines[i + 1:]]).strip()
    return lines, ""


def engine_stop_sentence(message: str) -> str:
    """One plain sentence with the command to run, for engine.py port --dry-run's STOP message."""
    if "`engine.py fetch`" in message:
        return WORDS["prog_y_fetch"]
    if "`engine.py apply`" in message:
        return WORDS["prog_y_apply"]
    reason = (message.splitlines() or [""])[0].strip().rstrip(".:").replace("`", "")
    return WORDS["prog_y_other"].format(reason=reason or "no reason was given")


def record_ok(exe: Path, play) -> bool:
    """The program's SHA-256 equals its build-record.json's (no record or no sha in it: ok, as play.py)."""
    try:
        want = json.loads((Path(exe).parent / "build-record.json").read_text(encoding="utf-8")).get("sha256")
    except (OSError, ValueError, AttributeError):
        return True
    return not want or play.sha256_file(Path(exe), progress=False) == want


def extracted_dir(play) -> Path:
    return Path(os.environ.get(play.ENV("EXTRACTED")) or (REPO / "extracted"))


def randomizer_prepared(play) -> bool:
    top = extracted_dir(play)
    return (top / "romfs").is_dir() and (top / "assets" / "romfs_manifest.tsv").is_file()


# ---------------------------------------------------------------------------------------------- the window


class Window:
    """The Getting ready window: a loop of rows and one question. input_fn returns None at the end of input
    (which quits). runner runs romfs.py and engine.py port --dry-run; which finds PowerShell."""

    def __init__(self, play, config: dict, *, setup: bool, dry_run: bool, input_fn=None, out=print,
                 runner=subprocess.run, which=shutil.which):
        self.play, self.config, self.setup, self.dry = play, config, setup, dry_run
        self.input_fn = input_fn or self._input
        self.out, self.runner, self.which = out, runner, which
        self.lj = play.load_launcher()
        self.reason = ""                 # the last one-sentence answer about the game file
        self.way_out = ""                # WORDS key printed under it (the right game, not usable as is)
        self.game_ok_path: Path | None = None
        self.asked_engine = False
        self.seal_asked = False

    @staticmethod
    def _input(prompt: str) -> str | None:
        try:
            return input(prompt)
        except EOFError:
            return None

    def ask(self, key: str) -> str | None:
        answer = self.input_fn(WORDS[key])
        return None if answer is None else answer

    def remember(self, **values) -> None:
        self.lj = self.play.save_launcher(values)

    # -- rows

    def game_row(self) -> tuple[bool, str]:
        rom, why = current_rom(self.play, self.config)
        if rom is None:
            if why and not self.reason:
                self.reason = why
            return False, WORDS["game_missing"]
        ok, sentence, entry = check_game_file(rom, self.play, mode=self.config.get("check_rom", "full"),
                                              state=self.play.load_state(), out=self.out)
        if ok:
            self._cache(entry)
            self.game_ok_path = rom
            return True, WORDS["game_ok"].format(path=rom)
        if not self.reason:
            self.reason = sentence
            self.way_out = self.way_out_for(rom, sentence)
        return False, WORDS["game_bad"]

    def way_out_for(self, rom: Path, sentence: str) -> str:
        """PLAY's old STOP way out for the game file it would use: the right game, but not usable as is."""
        if sentence.startswith(WORDS["bad_cia"].split("{", 1)[0]):
            return "way_out_cia"
        try:
            trimmed = WORDS["bad_trimmed"].format(size=Path(rom).stat().st_size, want=self.play.ROM_SIZE)
        except OSError:
            trimmed = None
        return "way_out_rom" if sentence in (WORDS["bad_hash"], trimmed) else ""

    def _cache(self, entry: dict) -> None:
        if not entry:
            return
        state = self.play.load_state()
        if state.get("rom_check") != entry:
            state["rom_check"] = entry
            self.play.write_json(self.play.STATE_PATH, state)

    def show(self) -> dict:
        p, out = self.play, self.out
        game_ok, game_text = self.game_row()
        prog = program_status(p, self.config)
        seal = SEAL.status(p, self.lj, self.setup and not self.seal_asked) if SEAL is not None else None
        rando = randomizer_prepared(p)
        out("")
        say("title", out, game=p.GAME)
        g = {"game": p.GAME, "edition": p.EDITION}
        if prog["kind"] == "standalone":
            good = record_ok(prog["path"], p)
            prog_mark, prog_text = ("x" if good else "!"), (WORDS["program_standalone"].format(name=p.STANDALONE_NAME)
                                                            if good else WORDS["program_record_bad"])
        elif prog["kind"] == "zakuro" and not zakuro_recompiled(p, self.config, prog["path"]):
            prog_mark = "!"      # round 85: never a tick before the game was recompiled (PLAY would stop)
            prog_text = WORDS["program_zakuro_not_recompiled"].format(path=prog["path"].parent)
        elif prog["kind"] == "zakuro":
            prog_mark, prog_text = "x", WORDS["program_zakuro"].format(path=prog["path"].parent)
        else:
            prog_mark, prog_text = " ", WORDS["program_missing"]
        rows = [("x" if game_ok else " ", WORDS["row_game"].format(**g), game_text),
                *([SEAL.row(seal, WORDS)] if seal is not None else []),
                (prog_mark, WORDS["row_program"], prog_text),
                ("x" if rando else "-", WORDS["row_rando"], WORDS["rando_ready"] if rando else WORDS["rando_not"])]
        width = max(len(r[1]) for r in rows) + 3
        for mark, label, text in rows:
            out(f"  [{mark}] {label.ljust(width)}{text}")
        if prog["kind"] == "zakuro" and prog_mark == "!":
            say("zakuro_recompile", out, game=p.GAME)
        return {"game": game_ok, "program": prog["kind"] is not None, "seal": seal, "rando": rando}

    # -- the game file

    def game_question(self) -> str:
        out = self.out
        if self.reason:
            out("")
            out(self.reason)
            if self.way_out:
                say(self.way_out, out)
            self.reason = self.way_out = ""
        out("")
        say("find_head", out)
        for k in ("find_1", "find_2", "find_3", "quit"):
            say(k, out)
        answer = self.ask("ask")
        if answer is None:
            return "quit"
        a = answer.strip().lower()
        if a == "q":
            return "quit"
        if a == "":                       # just Enter: look again (after moving a file by hand)
            return "again"
        if a in ("1", "2", "3"):
            self.find(a)
            return "again"
        dragged = normalize_path(answer)
        if dragged and (os.sep in dragged or "/" in dragged):      # a path dragged straight onto the question
            self.try_game_file(Path(dragged))
            return "again"
        say("bad_key", out)
        return "again"

    def find(self, how: str) -> None:
        p = self.play
        if how == "1":
            say("looking", self.out, seconds=SEARCH_SECONDS)
            found, timed_out = look_for(search_roots(p.ROM_REPO), size=p.ROM_SIZE, title=p.TITLE_ID)
            if timed_out:
                say("look_timeout", self.out, seconds=SEARCH_SECONDS)
            if not found:
                say("look_none", self.out)
                return
            if len(found) > 1:
                say("look_many", self.out, count=len(found))
                for i, f in enumerate(found, 1):
                    self.out(f"  {i}  {f}")
                pick = self.ask("ask_pick")
                if not pick or not pick.strip().isdigit() or not 1 <= int(pick) <= len(found):
                    return
                found = [found[int(pick) - 1]]
            self.try_game_file(found[0])
        elif how == "2":
            chosen = self.choose(WORDS["window_title"].format(game=p.GAME))
            if chosen is False:
                how = "3"
            elif chosen:
                self.try_game_file(Path(chosen))
            else:
                say("window_cancel", self.out)
        if how == "3":
            typed = normalize_path(self.ask("ask_path"))
            if typed:
                self.try_game_file(Path(typed))

    def choose(self, title: str):
        """The Windows Open window: the chosen path, "" when cancelled, False when it is not available."""
        cmd = None if os.environ.get(self.play.ENV("LAUNCHER_NO_WINDOW")) == "1" else open_window_command(title, self.which)
        if cmd is None:
            say("window_none", self.out)
            return False
        try:
            run = self.runner(cmd, capture_output=True, timeout=900)
        except (OSError, subprocess.SubprocessError):
            say("window_none", self.out)
            return False
        raw = run.stdout or b""
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        return text.strip() if run.returncode == 0 else False

    def try_game_file(self, path: Path) -> bool:
        ok, sentence, entry = check_game_file(path, self.play, mode=self.config.get("check_rom", "full"),
                                              state=self.play.load_state(), out=self.out)
        if not ok:
            self.reason = sentence
            return False
        self._cache(entry)
        if in_roms(self.play, path) and self.lj.get("rom") in (None, ""):
            say("accepted_roms", self.out)
            return True
        self.remember(rom=str(Path(path)))
        given = str(self.config.get("rom") or "").strip()
        if given and not Path(given).is_file():
            self.config["rom"] = ""          # in memory only: PLAY then takes launcher.json (config is never edited)
        say("accepted", self.out)
        if given and Path(given).is_file() and Path(given).resolve() != Path(path).resolve():
            say("config_wins", self.out, path=given)
        return True

    # -- the program

    def program_question(self) -> str:
        out = self.out
        out("")
        for k in ("prog_text", "prog_z", "prog_cmd", "prog_time"):
            say(k, out)
        if not self.asked_engine:
            say("prog_y", out)
        say("quit", out)
        answer = self.ask("ask")
        if answer is None:
            return "quit"
        a = answer.strip().lower()
        if a == "q":
            return "quit"
        if a == "z":
            self.zakuro_folder()
        elif a == "y" and not self.asked_engine:
            self.asked_engine = True
            self.engine_check()
        else:
            say("bad_key", out)
        return "again"

    def engine_check(self) -> None:
        """Y: engine.py port --dry-run (it builds nothing). Its plan lines are shown as they are; its STOP line
        never is: it becomes one plain sentence with the command to run (round 85)."""
        out = self.out
        cmd = [sys.executable, str(REPO / "tools" / "engine" / "engine.py"), "port", "--dry-run"]
        say("prog_y_checking", out)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            run = self.runner(cmd, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, timeout=900)
        except (OSError, subprocess.SubprocessError) as error:   # TimeoutExpired is a SubprocessError
            say("prog_y_failed", out, reason=error.__class__.__name__)
            return
        stdout, stop_out = engine_stop(getattr(run, "stdout", "") or "")
        stderr, stop_err = engine_stop(getattr(run, "stderr", "") or "")
        for line in stdout + stderr:
            out(line)
        stop = stop_err or stop_out
        code = getattr(run, "returncode", None)
        if stop:
            out(engine_stop_sentence(stop))
        elif code == 0:
            say("prog_y_ok", out)
        elif code is not None:
            say("prog_y_failed", out, reason=f"exit {code}")

    def ask_path(self, key: str, title_key: str) -> str | None:
        """A typed or dragged path; "2" opens the Windows Open window instead (typing when it is not there)."""
        typed = normalize_path(self.ask(key))
        if typed == "2":
            chosen = self.choose(WORDS[title_key])
            if chosen is False:
                typed = normalize_path(self.ask(key))
                return None if typed == "2" else typed
            return chosen or None
        return typed

    def zakuro_folder(self) -> None:
        typed = self.ask_path("ask_folder", "window_title_zakuro")
        if not typed:
            return
        folder = Path(typed)
        if folder.is_file() and folder.name.lower() == "zakuro.exe":
            folder = folder.parent
        if not (folder / "zakuro.exe").is_file():
            say("prog_bad_folder", self.out, path=folder)
            return
        self.remember(zakuro_dir=str(folder))
        say("prog_zakuro_ok", self.out)

    # -- the Seal edition's question and install (tools/seal/launcher_seal.py; only called when SEAL is loaded)

    def seal_question(self, seal: dict) -> str:
        return SEAL.question(self, seal, say)

    def seal_install(self, seal: dict) -> None:
        SEAL.install(self, seal, say, WORDS)

    # -- the Randomizer

    def prepare_randomizer(self) -> None:
        rom = self.game_ok_path
        if rom is None:
            return
        top = extracted_dir(self.play)
        cmd = [sys.executable, str(REPO / "tools" / "assets" / "romfs.py"), str(rom)]
        if self.dry:
            say("rando_dry", self.out, cmd=subprocess.list2cmdline(cmd))
            return
        probe = top if top.exists() else top.parent
        free = shutil.disk_usage(probe).free
        if free < ROMFS_NEED_FREE:
            say("rando_space", self.out, free=free / 2**30, need=ROMFS_NEED_FREE / 2**30)
            return
        run = self.runner(cmd, cwd=str(REPO))
        code = getattr(run, "returncode", 1)
        if code == 0:
            self.remember(randomizer_prepared=True)
            say("rando_done", self.out)
        else:
            say("rando_failed", self.out, code=code)

    # -- Ready

    def ready_question(self, status: dict) -> str:
        out = self.out
        out("")
        say("ready_dry" if self.dry else "ready", out)
        if not status["rando"]:
            say("rando_offer", out, gb=ROMFS_GB)
        if self.setup:
            say("ready_change_seal" if SEAL is not None else "ready_change", out)
        say("quit", out)
        answer = self.ask("ask")
        if answer is None:
            return "quit"
        a = answer.strip().lower()
        if a == "":
            return "go"
        if a == "q":
            return "quit"
        if a == "r" and not status["rando"]:
            self.prepare_randomizer()
        elif self.setup and a in ("1", "2", "3"):
            self.find(a)
        elif self.setup and a == "p" and SEAL is not None:
            self.seal_install({"state": "missing", "zip": None})
        elif self.setup and a == "z":
            self.zakuro_folder()
        else:
            say("bad_key", out)
        return "again"

    def run(self) -> int:
        while True:
            status = self.show()
            if not status["game"]:
                step = self.game_question()
            elif not status["program"]:
                step = self.program_question()
            elif status["seal"] is not None and SEAL.wants_question(status["seal"]) and not self.seal_asked:
                step = self.seal_question(status["seal"])
            else:
                step = self.ready_question(status)
            if step == "quit":
                self.out("")
                say("quit_done", self.out)
                return 1
            if step == "go":
                return 0


def run(play, config: dict, *, setup: bool = False, dry_run: bool = False, **kw) -> int:
    """0: go on and start as PLAY does; 1: the player quit (nothing was started). Silent (and 0) when nothing is
    missing, unless setup."""
    if not setup and not needs_window(play, config):
        return 0
    return Window(play, config, setup=setup, dry_run=dry_run, **kw).run()
