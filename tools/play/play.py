"""PLAY launcher: start Fire Emblem Fates (Special Edition, USA) straight into the game.

It starts the standalone program play/game/Fire Emblem Fates.exe when it has been built
(python tools/engine/engine.py port; docs/ENGINE.md section 8), else Zakuro. Both take the
same command line and keep saves, mods, cheats and settings in the same place.

    PLAY.bat                         (what the owner double-clicks; it runs this file)
    python tools/play/play.py [options] [-- extra zakuro options]

Options (each also works through PLAY.bat):
    --dry-run              do every check, print the command it would run, start nothing
    --check                check Zakuro, the ROM and the recompiled code, start nothing
    --where                print where everything lives (saves, mods, settings, logs)
    --backup               zip the save into play/backups (manual-*.zip, never pruned)
    --backup-seal          the Seal edition only (tools/seal): zip that edition's save
                           (play/seal-of-flames/data/user) into play/backups/manual-<time>-seal.zip;
                           only reads the save, never prunes, refuses while the game runs (round 73b)
    --migrate-saves to-portable|to-appdata
                           copy the save between %APPDATA%\\zakuro and play/data
                           (never overwrites, never deletes the source, backs up first)
    --portable on|off      switch "portable_saves" in play/config.json
    --make-shortcut        put a "PLAY Fire Emblem Fates" shortcut on the Desktop
    --force                with --make-shortcut: replace an existing shortcut
    --rehash               forget the cached ROM check and hash the ROM again
    --setup                open the Getting ready window (tools/play/launcher.py, round 77) even when
                           nothing is missing: point to a moved game file, Zakuro's folder, or
                           prepare the Randomizer (the Seal edition adds its zip). PLAY.bat shows it by itself
                           only when something is missing or wrong (it sets FEF_LAUNCHER=1);
                           a plain "python tools/play/play.py" never shows it.
    --anyway               start even when a check says stop (missing recompiled code,
                           save in the other place, Zakuro already running, ROM hash differs,
                           an update .cia beside the ROM)

Capture session (the Awakening port's docs/HARNESS.md 4.2; docs/PLAY.md here). For this game
it waits for a capture library, which tools/harness does not build yet: until then --capture
stops at "no capture library". It never touches your real save: it plays on a copy.
    --capture              start one recorded capture session in Zakuro (not the standalone
                           program): the capture library build/harness/lib (refused when
                           tools/harness/build.py --check-fresh says STALE), FE_READABLE=capture,
                           ZAKURO_RECORD=build/harness/sessions/<id>/input.rec, and --data
                           build/harness/sessions/<id>/data, a copy of a PLAY backup.
                           Prints the checklist, then asks you to type START.
    --session ID           the session's name (default cap-<date>-<time>; never reused)
    --capture-from NAME    the save to copy: a zip in play/backups (default: the newest one),
                           or "portable" for PLAY's portable save (play/data)
    --live a|ab            FE_CAPTURE_LIVE for the session (default a: the fidelity gate only;
                           the readable side runs headless afterwards, HARNESS.md 6)
    --go                   start without asking (no prompt); only the owner uses this

Everything the launcher learns about Zakuro comes from reading its source (v0.2.32):
  * `zakuro <rom>` loads that game at once, skipping the library.
  * `--data <dir>` moves saves (user/), mods/, cheats/, states/ and zakuro.log; settings
    stay in %APPDATA%\\zakuro\\settings.toml whatever --data says.
  * recompiled code is found at %APPDATA%\\3dsrecomp\\<TITLE ID>.dll.
  * there is no fullscreen flag (F11 in the game); --scale sets the window size.

The standalone program is Zakuro's own frontend with the recompiled code linked in (our patch
0005 names its window after the exe), so all of the above holds for it too; it needs no
%APPDATA%\\3dsrecomp DLL. "standalone": false in play/config.json always uses Zakuro.

Per-game constants (title id, product code, ROM size and SHA-256, names, the default ROM)
come from config/game.json through tools/gamecfg.py. Environment names start with the
game's prefix (FEF_PLAY_DIR, FEF_HARNESS_DIR; FEF_ASSUME_NOT_RUNNING=1 is for tests only).

Config: play/config.json (gitignored, written on first run). State (ROM hash cache):
play/state.json. Backups: play/backups/. Portable saves: play/data/ (off by default).
The launcher's choices: play/launcher.json (round 77; the game file, Zakuro folder and the Seal
edition's zip it was pointed to; read after config.json's own "rom" / "zakuro_dir", never written
into config.json). A freshly unzipped folder (no play/config.json and nothing else of PLAY's in
play/ before the first PLAY) is a portable folder: PLAY makes play/appdata then, and from that on
the standalone program gets APPDATA, LOCALAPPDATA and TEMP inside play/ (play/appdata,
play/localappdata, play/temp), so nothing of it lands in the PC's own Zakuro places. A folder that
already had play/config.json keeps today's places (no save is ever moved).
Python 3.13 standard library only. Nothing here holds Nintendo data: the title id,
product code and SHA-256 are identifiers (config/game.json).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from gamecfg import GAME as CFG  # noqa: E402  (config/game.json)
import paths  # noqa: E402  (F-048: roms/ first, then the old root place for one release)

TITLE_ID = CFG.title_id_int                     # 0x0004000000179800
TITLE_HEX = f"{TITLE_ID:016X}"
PRODUCT_CODE = CFG.product_code                 # CTR-P-BFZE
ROM_SIZE = CFG.rom_size                         # 2 GiB card image
ROM_SHA256 = CFG.rom_sha256                     # the owner's clean dump
GAME = CFG.game                                 # "Fire Emblem Fates"
EDITION = CFG.edition                           # "Special Edition (USA)"
SHORTCUT_NAME = CFG.port.shortcut_name + ".lnk"
# the exheader's extdata id is used; this one (config/game.json) only when it cannot be read
EXTDATA_FALLBACK = int(CFG.extdata_id, 16)
ENV = CFG.env                                   # ENV("PLAY_DIR") -> "FEF_PLAY_DIR"
# the options page's file path (tools/zakuro-options: FE_OPTIONS, else FEF_OPTIONS). PLAY does not set
# it for play yet (F-010); a capture session drops it (FE_OPTIONS goes with every FE_ variable).
OPTIONS_ENV = ENV("OPTIONS")                    # "FEF_OPTIONS"

PLAY_DIR = Path(os.environ.get(ENV("PLAY_DIR")) or (REPO / "play"))
STANDALONE_NAME = CFG.port.standalone_name      # tools/engine/engine.py port writes it
STANDALONE_DIR = PLAY_DIR / "game"
CONFIG_PATH = PLAY_DIR / "config.json"
# where roms/ (and the old root place) is searched when "rom" is empty or gone: the repo (tests: a temp folder)
ROM_REPO = Path(os.environ.get(ENV("ROM_REPO")) or REPO)
STATE_PATH = PLAY_DIR / "state.json"
BACKUP_DIR = PLAY_DIR / "backups"
# the Seal edition's own Zakuro data folder (the same place as tools/seal's data_dir(); tests check they agree).
# Kept in both editions with NOT_FRESH: a player's play/seal-of-flames is never treated as PLAY's to change.
SEAL_DATA_DIR = PLAY_DIR / "seal-of-flames" / "data"
# round 77 (docs/LAUNCHER_PLAN.md): the launcher's choices, and the switch PLAY.bat sets so the window may show
LAUNCHER_PATH = PLAY_DIR / "launcher.json"
LAUNCHER_ENV = ENV("LAUNCHER")                  # "FEF_LAUNCHER": "1" from PLAY.bat
PORTABLE_DIRS = {"APPDATA": "appdata", "LOCALAPPDATA": "localappdata", "TEMP": "temp", "TMP": "temp"}
# what makes play/ "not fresh": any of PLAY's own files (play/game, the built program, does not count)
NOT_FRESH = ("config.json", "state.json", "launcher.json", "backups", "data", "seal-of-flames", "randomizer",
             "appdata", "localappdata")

DEFAULT_CONFIG = {
    "_about": [
        "Settings for PLAY.bat. Edit with Notepad; keep the quotes and commas.",
        "Windows paths need doubled backslashes inside the quotes.",
        "zakuro_dir: the folder holding zakuro.exe (only needed when the standalone program is not built).",
        "rom: leave empty to use the .cci in the roms folder; or the full path of your own decrypted dump of "
        + GAME + " " + EDITION + " (.cci or .3ds).",
        "check_rom: 'full' (SHA-256, cached until the file changes) or 'header' (title id only).",
        "portable_saves: true keeps saves, mods and logs in play\\\\data (see Read Me First.txt).",
        "auto_backup: zip the save before each start; keep_backups: how many of those to keep.",
        "scale: window size as a whole number (null = Zakuro's own setting).",
        "zakuro_args: extra Zakuro options, for example [\"--mute\"].",
        "standalone: true starts play\\\\game\\\\" + STANDALONE_NAME + " when it is there; false always uses Zakuro.",
    ],
    "standalone": True,
    "zakuro_dir": "",                           # no machine-specific path by default (F-048)
    "rom": "",                                  # empty: roms/ (tools/paths.py find_rom); never written back
    "check_rom": "full",
    "portable_saves": False,
    "portable_data_dir": "data",
    "auto_backup": True,
    "keep_backups": 20,
    "scale": None,
    "zakuro_args": [],
}


class Stop(Exception):
    """A check failed; the message says what to do."""


# ---------------------------------------------------------------------------------------
# config and state


def load_config() -> tuple[dict, bool]:
    """The config, created with defaults on first run. Returns (config, created)."""
    if not CONFIG_PATH.exists():
        PLAY_DIR.mkdir(parents=True, exist_ok=True)
        write_json(CONFIG_PATH, DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG), True
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Stop(
            f"play\\config.json could not be read ({error}).\n"
            "Fix the line it names, or delete the file and PLAY again to get a fresh one."
        )
    if not isinstance(config, dict):
        raise Stop("play\\config.json must hold one { ... } object. Delete it and PLAY again.")
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return merged, False


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_launcher() -> dict:
    """play/launcher.json (round 77), or {} when it is missing or unreadable."""
    try:
        data = json.loads(LAUNCHER_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_launcher(values: dict) -> dict:
    """Merges values into play/launcher.json and returns the whole of it. Only the launcher's own keys."""
    data = load_launcher()
    data.setdefault("about", "PLAY's launcher (tools/play/launcher.py): paths you pointed to, your choices. "
                             "Delete this file to be asked again. play/config.json is never changed by it.")
    data.update(values)
    write_json(LAUNCHER_PATH, data)
    return data


def folder_is_fresh() -> bool:
    """A freshly unzipped folder: play/ holds none of PLAY's own files yet (config.json included)."""
    return not any((PLAY_DIR / name).exists() for name in NOT_FRESH)


def portable_folder_env(config: dict, base: dict | None = None) -> dict | None:
    """The program's whole environment for a portable folder (play/appdata is there: PLAY made it on the first
    start of a freshly unzipped folder; the standalone program built): APPDATA, LOCALAPPDATA, TEMP and TMP inside
    play/. None otherwise (today's places; Zakuro itself always keeps its own places)."""
    if not (PLAY_DIR / PORTABLE_DIRS["APPDATA"]).is_dir() or standalone_exe(config) is None:
        return None
    env = dict(os.environ if base is None else base)
    env.update({k: str(PLAY_DIR / v) for k, v in PORTABLE_DIRS.items()})
    return env


def make_portable_dirs(env: dict | None) -> None:
    """Right before a real start with a portable environment (portable_folder_env): make its folders inside play/,
    so the program never gets a TEMP or LOCALAPPDATA that does not exist (round 77 review). None = nothing."""
    if env is None:
        return
    for name in sorted(set(PORTABLE_DIRS.values())):
        (PLAY_DIR / name).mkdir(parents=True, exist_ok=True)


def load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------------------------------
# places


def appdata() -> Path:
    value = os.environ.get("APPDATA")
    if not value:
        raise Stop("The APPDATA environment variable is not set, so Zakuro's folders cannot be found.")
    return Path(value)


def appdata_data_dir() -> Path:
    return appdata() / "zakuro"


def portable_data_dir(config: dict) -> Path:
    path = Path(config.get("portable_data_dir") or "data")
    return path if path.is_absolute() else PLAY_DIR / path


def active_data_dir(config: dict) -> Path:
    return portable_data_dir(config) if config.get("portable_saves") else appdata_data_dir()


def recompiled_path() -> Path:
    return appdata() / "3dsrecomp" / f"{TITLE_HEX}.dll"


def settings_path() -> Path:
    return appdata() / "zakuro" / "settings.toml"


def mods_dir(data_dir: Path) -> Path:
    # Zakuro (zakuro-core/src/mods.rs) takes the upper-case folder unless only a
    # lower-case one exists.
    upper = data_dir / "mods" / TITLE_HEX
    lower = data_dir / "mods" / TITLE_HEX.lower()
    return lower if (not upper.exists() and lower.exists()) else upper


def save_items(data_dir: Path, extdata_id: int | None) -> list[Path]:
    """Every file or folder that makes up this game's save under a Zakuro data folder."""
    user = data_dir / "user"
    items = [user / "savedata" / TITLE_HEX, user / "savedata" / f"{TITLE_HEX}.format"]
    extdata = user / "extdata"
    if extdata_id and extdata.is_dir():
        for entry in sorted(extdata.iterdir()):
            stem = entry.name.removesuffix(".format")
            try:
                value = int(stem, 16)
            except ValueError:
                continue
            if value == extdata_id or (value & 0xFFFFFFFF) == extdata_id:
                items.append(entry)
    return items


def save_exists(data_dir: Path) -> bool:
    folder = data_dir / "user" / "savedata" / TITLE_HEX
    return folder.is_dir() and any(folder.iterdir())


# ---------------------------------------------------------------------------------------
# ROM checks


def inspect_rom(path: Path) -> dict:
    """Read the NCSD and first NCCH header. Raises Stop when it is not this game and edition."""
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            ncsd = f.read(0x200)
            if len(ncsd) < 0x200 or ncsd[0x100:0x104] != b"NCSD":
                raise Stop(f"{path.name} is not a 3DS cartridge image (.cci/.3ds): no NCSD header.")
            media_id = struct.unpack_from("<Q", ncsd, 0x108)[0]
            p0_offset = struct.unpack_from("<I", ncsd, 0x120)[0] * 0x200
            f.seek(p0_offset)
            ncch = f.read(0x200)
            if len(ncch) < 0x200 or ncch[0x100:0x104] != b"NCCH":
                raise Stop(f"{path.name}: the game partition has no NCCH header (cut short or damaged?).")
            program_id = struct.unpack_from("<Q", ncch, 0x118)[0]
            product = ncch[0x150:0x160].split(b"\0", 1)[0].decode("ascii", "replace")
            flags = ncch[0x188:0x190]
            no_crypto = bool(flags[7] & 0x04)
            exheader_size = struct.unpack_from("<I", ncch, 0x180)[0]
            extdata_id = None
            if no_crypto and exheader_size >= 0x400:
                exheader = f.read(0x400)
                if len(exheader) == 0x400:
                    extdata_id = struct.unpack_from("<Q", exheader, 0x230)[0] or None
    except OSError as error:
        raise Stop(f"Could not read the ROM ({error}).")
    if media_id != TITLE_ID or program_id != TITLE_ID:
        raise Stop(
            f"{path.name} is title {program_id:016X}, not {GAME} {EDITION} ({TITLE_HEX}).\n"
            "Point \"rom\" in play\\config.json at your own dump of that edition."
        )
    if product != PRODUCT_CODE:
        raise Stop(f"{path.name} has product code {product!r}, expected {PRODUCT_CODE}.")
    if not no_crypto:
        raise Stop(
            f"{path.name} is still encrypted. Zakuro needs a decrypted dump "
            "(GodMode9 can make one from your own cartridge)."
        )
    return {"size": size, "extdata_id": extdata_id or EXTDATA_FALLBACK,
            "extdata_from": "exheader" if extdata_id else "config/game.json"}


def sha256_file(path: Path, progress: bool = True) -> str:
    digest = hashlib.sha256()
    done = 0
    step = 256 * 1024 * 1024
    next_mark = step
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            digest.update(chunk)
            done += len(chunk)
            if progress and done >= next_mark:
                print(".", end="", flush=True)
                next_mark += step
    if progress:
        print()
    return digest.hexdigest()


def effective_rom(config: dict, notes: list[str]) -> Path:
    """The ROM to use: "rom" in play/config.json when it names a file that is there, else "rom" in
    play/launcher.json (the file the Getting ready window was pointed to, round 77) when it is there, else roms/
    (then the old root place, one release) through tools/paths.py. The title is checked there; the hash by check_rom
    (cached in play/state.json). play/config.json is never rewritten with the found path."""
    given = str(config.get("rom") or "").strip()
    if given and Path(given).is_file():
        return Path(given)
    chosen = str(load_launcher().get("rom") or "").strip()      # round 77: the file the launcher was pointed to
    if chosen and Path(chosen).is_file():
        if given:
            notes.append(f"Note: play\\config.json names a game file that is not there ({given}); using the one "
                         "the Getting ready window was pointed to.")
        return Path(chosen)
    if given:
        notes.append(f"Note: play\\config.json names a game file that is not there ({given}); using the roms folder.")
    try:
        return paths.find_rom(repo=ROM_REPO, check="header", notes=notes)
    except paths.PathError as error:
        raise Stop((notes[-1] + "\n" if given else "") + str(error))


def check_rom(config: dict, state: dict, rehash: bool, notes: list[str]) -> dict:
    rom = effective_rom(config, notes)
    config["rom"] = str(rom)                    # in memory only: the command line below uses it
    info = inspect_rom(rom)
    mode = str(config.get("check_rom", "full")).lower()
    if mode == "header":
        notes.append("ROM: header checked (title id, product code, decrypted); SHA-256 skipped by config.")
        return info
    st = rom.stat()
    key = {"path": str(rom.resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    cached = state.get("rom_check")
    if not rehash and isinstance(cached, dict) and all(cached.get(k) == v for k, v in key.items()):
        digest = cached.get("sha256", "")
    else:
        print(f"Checking your ROM once (SHA-256 of {st.st_size / 2**30:.1f} GiB, about 10 seconds)", end="", flush=True)
        digest = sha256_file(rom)
        state["rom_check"] = dict(key, sha256=digest)
        write_json(STATE_PATH, state)
    info["sha256"] = digest
    if digest != ROM_SHA256:
        info["hash_mismatch"] = True
        if st.st_size != ROM_SIZE:
            info["size_note"] = (f"  The file is {st.st_size:,} bytes; the clean card image is {ROM_SIZE:,}\n"
                                 "  (a trimmed dump is a different file, even when it plays).")
    else:
        notes.append(f"ROM: SHA-256 matches the known clean {GAME} dump.")
    return info


# ---------------------------------------------------------------------------------------
# Zakuro checks


def find_zakuro(config: dict) -> Path:
    setting = str(config.get("zakuro_dir") or "").strip()
    if not setting or not (Path(setting) / "zakuro.exe").is_file():
        chosen = str(load_launcher().get("zakuro_dir") or "").strip()   # round 77: the launcher's Zakuro folder
        if chosen and (Path(chosen) / "zakuro.exe").is_file():
            setting = chosen
    folder = Path(setting) if setting else None
    exe = folder / "zakuro.exe" if folder else None
    if exe is None or not exe.is_file():
        raise Stop(
            f"zakuro.exe was not found in:\n  {folder or '(no folder set)'}\n"
            "Put the folder that holds zakuro.exe in \"zakuro_dir\" in play\\config.json."
        )
    return exe


def standalone_exe(config: dict) -> Path | None:
    """play/game/<STANDALONE_NAME> when it is built and "standalone" is not false."""
    if config.get("standalone", True) is False:
        return None
    exe = STANDALONE_DIR / STANDALONE_NAME
    return exe if exe.is_file() else None


def find_program(config: dict) -> tuple[Path, bool]:
    """(exe, standalone): the standalone program when there is one, else Zakuro."""
    exe = standalone_exe(config)
    if exe is not None:
        return exe, True
    return find_zakuro(config), False


def zakuro_running() -> bool:
    """Zakuro or the standalone program (both use the same save) is running."""
    if os.name != "nt" or os.environ.get(ENV("ASSUME_NOT_RUNNING")) == "1":  # the latter: tests only
        return False
    # Fails closed (review 2026-11-11 #3): if Windows cannot tell us, do not guess "not running",
    # because two copies on one save can lose progress.
    for image in ("zakuro.exe", STANDALONE_NAME):
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise Stop(f"Could not check whether Zakuro or {STANDALONE_NAME} is already running "
                       f"({e.__class__.__name__}). Close any copy that is open, then try again.")
        if proc.returncode != 0:
            raise Stop(f"Could not check whether Zakuro or {STANDALONE_NAME} is already running "
                       f"(tasklist exit {proc.returncode}). Close any copy that is open, then try again.")
        out = proc.stdout
        if image.lower() in out.lower():
            return True
    return False


def read_settings() -> dict:
    try:
        return tomllib.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def code_mods_newer_than(data_dir: Path, when: float) -> list[Path]:
    mods = mods_dir(data_dir)
    code_files = [mods / n for n in ("code.bin", "code.ips", "code.bps", "exheader.bin")]
    code_files += [mods / "exefs" / n for n in ("code.bin", "code.ips", "code.bps")]
    return [p for p in code_files if p.is_file() and p.stat().st_mtime > when]


def check_standalone(exe: Path, data_dir: Path, notes: list[str], blockers: list[str] | None = None) -> None:
    built = exe.stat().st_mtime
    notes.append(f"Program: {exe.name} (standalone, recompiled code built in, "
                 f"made {_dt.datetime.fromtimestamp(built):%Y-%m-%d %H:%M}).")
    try:
        record = json.loads((exe.parent / "build-record.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = {}
    want = record.get("sha256")
    if want:  # round 68: the program must be the one its record describes (an install cut short, a hand copy)
        got = sha256_file(exe, progress=False)
        if got != want:
            (blockers if blockers is not None else notes).append(
                f"The program {exe.name} is not the one its build-record.json describes.\n"
                f"  program  sha256 {got}\n  record   sha256 {want}\n"
                "  It was replaced by hand or an install was cut short. Put the right one back\n"
                "  (RELEASE.bat undo <tag>, or python tools/engine/engine.py port), or start it once\n"
                "  with PLAY.bat --anyway.")
    patches = sorted(p.name for p in (REPO / "patches" / "zakuro").glob("[0-9][0-9][0-9][0-9]-*.patch"))
    if record.get("zakuro_patches") is not None and sorted(record["zakuro_patches"]) != patches:
        notes.append("Hint: our Zakuro patches changed since the program was built. Rebuild it with\n"
                     "  python tools/engine/engine.py port   (PLAY keeps working meanwhile).")
    in_use = code_mods_newer_than(data_dir, 0)
    if in_use:
        notes.append(
            "Note: a code mod is in use (" + ", ".join(p.name for p in in_use) + ").\n"
            "  The program is built from the game's own code, so the functions a code mod changes\n"
            "  run in the interpreter (slower); the rest stay recompiled. Data mods are not affected."
        )


def check_recompiled(config: dict, exe: Path, data_dir: Path, notes: list[str], blockers: list[str],
                     standalone: bool = False) -> None:
    args = [str(a) for a in config.get("zakuro_args") or []]
    if "--interpreter" in args:
        notes.append("Recompiled code: skipped, zakuro_args asks for --interpreter (slow).")
        return
    if "--recompiled" in args:
        notes.append("Recompiled code: zakuro_args names its own --recompiled library; not checked.")
        return
    settings = read_settings()
    own = (settings.get("per_game") or {}).get(TITLE_HEX) or {}
    use = own.get("recompiled", settings.get("recompiled", True))
    if use is False:
        notes.append(
            "Zakuro's settings say not to run recompiled code for this game "
            "(Esc > Settings for this game). It will run in the interpreter, below full speed."
        )
        return
    if standalone:
        check_standalone(exe, data_dir, notes, blockers)
        return
    dll = recompiled_path()
    if not dll.is_file():
        blockers.append(
            "The game has not been recompiled yet, so it would run slowly.\n"
            "  Once: open Zakuro (zakuro.exe in its folder), press Recompile next to\n"
            f"  {GAME} in the library, wait for it (10-20 minutes), close Zakuro,\n"
            "  then PLAY again. (PLAY.bat --anyway starts it slow, without recompiled code.)"
        )
        return
    dll_time = dll.stat().st_mtime
    notes.append(f"Recompiled code: found ({dll.name}, built {_dt.datetime.fromtimestamp(dll_time):%Y-%m-%d %H:%M}).")
    if exe.stat().st_mtime > dll_time:
        notes.append(
            "Hint: zakuro.exe is newer than the recompiled code. If Zakuro says the game was\n"
            "  recompiled by an older version, press \"Recompile outdated\" in its library once."
        )
    newer = code_mods_newer_than(data_dir, dll_time)
    if newer:
        notes.append(
            "Hint: a code mod is newer than the recompiled code (" + ", ".join(p.name for p in newer) + ").\n"
            "  Recompile once in Zakuro's library so the modded code runs at full speed."
        )


# ---------------------------------------------------------------------------------------
# backups and migration


def zip_save(data_dir: Path, extdata_id: int | None, dest: Path) -> Path | None:
    items = [p for p in save_items(data_dir, extdata_id) if p.exists()]
    if not items:
        return None
    user = data_dir / "user"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for item in items:
                files = [item] if item.is_file() else sorted(p for p in item.rglob("*") if p.is_file())
                for f in files:
                    z.write(f, f.relative_to(user).as_posix())
                if item.is_dir() and not files:
                    z.writestr(item.relative_to(user).as_posix() + "/", b"")
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)  # only our own half-written zip (round 73b review): no .zip.tmp is left behind
        raise
    return dest


def save_fingerprint(data_dir: Path, extdata_id: int | None) -> str:
    digest = hashlib.sha256()
    user = data_dir / "user"
    for item in save_items(data_dir, extdata_id):
        if not item.exists():
            continue
        files = [item] if item.is_file() else sorted(p for p in item.rglob("*") if p.is_file())
        for f in files:
            digest.update(f.relative_to(user).as_posix().encode() + b"\0")
            digest.update(f.read_bytes())
    return digest.hexdigest()


def timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def where_label(config: dict) -> str:
    return "portable" if config.get("portable_saves") else "appdata"


def auto_backup(config: dict, state: dict, data_dir: Path, extdata_id: int | None) -> str | None:
    if not config.get("auto_backup", True) or not save_exists(data_dir):
        return None
    fingerprint = save_fingerprint(data_dir, extdata_id)
    last = state.get("last_auto_backup") or {}
    if last.get("fingerprint") == fingerprint and last.get("data_dir") == str(data_dir) \
            and (BACKUP_DIR / str(last.get("file", ""))).is_file():
        return f"Save unchanged since backup {last.get('file')}; no new backup."
    name = f"auto-{timestamp()}-{where_label(config)}.zip"
    zip_save(data_dir, extdata_id, BACKUP_DIR / name)
    state["last_auto_backup"] = {"file": name, "fingerprint": fingerprint, "data_dir": str(data_dir)}
    write_json(STATE_PATH, state)
    keep = max(1, int(config.get("keep_backups") or 20))
    autos = sorted(BACKUP_DIR.glob("auto-*.zip"))
    for old in autos[:-keep]:
        old.unlink(missing_ok=True)
    return f"Backed up the save to play\\backups\\{name}."


class _ThisModule:
    """play.py itself, handed to tools/seal/play_seal.py (also a test's private copy, which is not in sys.modules)."""

    def __getattr__(self, name: str):
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(name) from None


def seal_part():
    """Round 84 (Seal edition split B, F-072): tools/seal/play_seal.py, or None in the Vanilla+ edition (no
    tools/seal) or when it cannot load. Imported lazily, so a Vanilla+ PLAY never imports sof."""
    path = REPO / "tools" / "seal" / "play_seal.py"
    if not path.is_file():
        return None
    mod = sys.modules.get("play_seal")
    if mod is not None and Path(getattr(mod, "__file__", "") or "").resolve() == path.resolve():
        return mod
    try:
        spec = importlib.util.spec_from_file_location("play_seal", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:  # noqa: BLE001  an optional edition's fault must never stop the normal game
        return None
    sys.modules["play_seal"] = mod
    return mod


def backup_seal(dry_run: bool = False) -> str:
    """PLAY.bat --backup-seal: the Seal edition's read-only save backup (tools/seal/play_seal.py, round 73b)."""
    part = seal_part()
    if part is None:
        raise Stop("--backup-seal belongs to the Seal edition, which is not in this folder (no tools/seal). "
                   "Nothing was backed up.")
    return part.backup_seal(_ThisModule(), dry_run)


def copy_item(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def migrate(config: dict, direction: str, extdata_id: int | None, dry_run: bool) -> list[str]:
    if direction == "to-portable":
        src, dst, src_label, dst_label = appdata_data_dir(), portable_data_dir(config), "appdata", "portable"
    elif direction == "to-appdata":
        src, dst, src_label, dst_label = portable_data_dir(config), appdata_data_dir(), "portable", "appdata"
    else:
        raise Stop("--migrate-saves needs to-portable or to-appdata.")
    if not save_exists(src):
        raise Stop(f"There is no {GAME} save to copy in:\n  {src}")
    sources = [p for p in save_items(src, extdata_id) if p.exists()]
    targets = [dst / p.relative_to(src) for p in sources]
    clash = [t for t in targets if t.exists()]
    if clash:
        raise Stop(
            "The destination already holds a save; nothing was copied (it is never overwritten):\n  "
            + "\n  ".join(str(c) for c in clash)
            + "\nBack it up (PLAY.bat --backup), move it away yourself, then try again."
        )
    if zakuro_running():
        raise Stop("Zakuro is running. Close it first, so the save is not half-written.")
    lines = []
    if dry_run:
        lines.append(f"[dry run] would back up the {src_label} save to play\\backups\\premigrate-*.zip")
        lines += [f"[dry run] would copy {s}\n            -> {t}" for s, t in zip(sources, targets)]
        return lines
    backup = zip_save(src, extdata_id, BACKUP_DIR / f"premigrate-{timestamp()}-{src_label}.zip")
    lines.append(f"Backed up the {src_label} save to {backup}.")
    for s, t in zip(sources, targets):
        copy_item(s, t)
        lines.append(f"Copied {s}\n    -> {t}")
    lines.append(f"The {src_label} copy was left as it was.")
    want = dst_label == "portable"
    if bool(config.get("portable_saves")) != want:
        lines.append(f"Now run: PLAY.bat --portable {'on' if want else 'off'}  (so PLAY uses the copied save)")
    return lines


def set_portable(value: str) -> str:
    config, _ = load_config()
    on = value.lower() in ("on", "true", "yes", "1")
    if value.lower() not in ("on", "off", "true", "false", "yes", "no", "1", "0"):
        raise Stop("--portable needs on or off.")
    config["portable_saves"] = on
    write_json(CONFIG_PATH, config)
    where = portable_data_dir(config) if on else appdata_data_dir()
    return f"portable_saves is now {'on' if on else 'off'}: saves, mods and logs in\n  {where}"


# ---------------------------------------------------------------------------------------
# shortcut


def make_shortcut(config: dict, force: bool, dry_run: bool) -> str:
    if os.name != "nt":
        raise Stop("Shortcuts are made on Windows only.")
    target = REPO / "PLAY.bat"
    icon = Path(config.get("zakuro_dir") or "") / "zakuro.exe"
    icon_spec = f"{icon},0" if icon.is_file() else f"{os.environ.get('SystemRoot', r'C:\Windows')}\\System32\\shell32.dll,137"
    script = (
        "$ErrorActionPreference='Stop';"
        "$desk=[Environment]::GetFolderPath('Desktop');"
        "$lnk=Join-Path $desk $env:FE_PLAY_LNK_NAME;"
        "if ($env:FE_PLAY_LNK_DRY -eq '1') { Write-Output $lnk; exit 0 };"
        "if ((Test-Path -LiteralPath $lnk) -and ($env:FE_PLAY_LNK_FORCE -ne '1')) { Write-Output ('EXISTS ' + $lnk); exit 3 };"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($lnk);"
        "$s.TargetPath=$env:FE_PLAY_LNK_TARGET;$s.WorkingDirectory=$env:FE_PLAY_LNK_WD;"
        "$s.IconLocation=$env:FE_PLAY_LNK_ICON;$s.Description=$env:FE_PLAY_LNK_DESC;"
        "$s.Save();Write-Output $lnk"
    )
    env = dict(os.environ, FE_PLAY_LNK_NAME=SHORTCUT_NAME, FE_PLAY_LNK_TARGET=str(target), FE_PLAY_LNK_WD=str(REPO),
               FE_PLAY_LNK_ICON=icon_spec, FE_PLAY_LNK_DESC=f"Start {GAME}", FE_PLAY_LNK_FORCE="1" if force else "0", FE_PLAY_LNK_DRY="1" if dry_run else "0")
    run = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, env=env, timeout=60)
    out = run.stdout.strip()
    if run.returncode == 3:
        raise Stop(f"A shortcut is already there:\n  {out[7:]}\nRun it again with --force to replace it.")
    if run.returncode != 0:
        raise Stop(f"Could not make the shortcut: {run.stderr.strip() or out}")
    if dry_run:
        return f"[dry run] would create {out}\n  -> {target} (icon {icon_spec})"
    return f"Made the shortcut:\n  {out}\n  -> {target}"


# ---------------------------------------------------------------------------------------
# launch


def build_command(config: dict, exe: Path, extra: list[str]) -> list[str]:
    cmd = [str(exe), str(Path(config["rom"]))]
    if config.get("portable_saves"):
        cmd += ["--data", str(portable_data_dir(config))]
    scale = config.get("scale")
    if scale not in (None, "", 0):
        cmd += ["--scale", str(int(scale))]
    cmd += [str(a) for a in config.get("zakuro_args") or []]
    cmd += extra
    return cmd


def seal_extras() -> tuple[list[str], object | None]:
    """The Seal edition's options for the standalone program and its sof module (tools/seal/play_seal.py, round 53);
    ([], None) in the Vanilla+ edition or when there is no Seal profile."""
    part = seal_part()
    return part.seal_extras(_ThisModule()) if part is not None else ([], None)


def launch(cmd: list[str], cwd: Path, env: dict | None = None) -> None:
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, cwd=str(cwd), creationflags=flags, close_fds=True, env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def find_program_label(config: dict) -> str:
    if standalone_exe(config) is not None:
        return f"standalone ({STANDALONE_NAME})"
    built = (STANDALONE_DIR / STANDALONE_NAME).is_file()
    return "Zakuro" + (" (\"standalone\": false in play\\config.json)" if built else " (no standalone program built)")


def where_rom(config: dict) -> str:
    try:
        return str(effective_rom(config, []))
    except Stop as stop:
        return f"not found ({stop})"


def print_where(config: dict) -> None:
    data = active_data_dir(config)
    rows = [
        ("Config", CONFIG_PATH),
        ("Program used", find_program_label(config)),
        ("Zakuro", Path(config.get("zakuro_dir") or "") / "zakuro.exe"),
        ("Standalone", STANDALONE_DIR / STANDALONE_NAME),
        ("ROM", where_rom(config)),
        ("Recompiled code", recompiled_path() if standalone_exe(config) is None else "built into the standalone program"),
        ("Zakuro settings", settings_path()),
        ("Saves in use", f"{data / 'user' / 'savedata' / TITLE_HEX}  ({where_label(config)})"),
        ("Save format file", data / "user" / "savedata" / f"{TITLE_HEX}.format"),
        ("Extra data", data / "user" / "extdata" / f"{EXTDATA_FALLBACK:016X}"),
        ("Mods", mods_dir(data)),
        ("Cheats", data / "cheats" / f"{TITLE_HEX}.txt"),
        ("Save states", data / "states" / TITLE_HEX),
        ("Zakuro log", data / "zakuro.log"),
        ("Backups", BACKUP_DIR),
        ("Other save place", (appdata_data_dir() if config.get("portable_saves") else portable_data_dir(config))
         / "user" / "savedata" / TITLE_HEX),
    ]
    width = max(len(k) for k, _ in rows)
    for k, v in rows:
        print(f"  {k.ljust(width)}  {v}")


# ---------------------------------------------------------------------------------------
# capture session (docs/HARNESS.md 4.2, milestone H4b)
#
# What Zakuro does with it, read from its source (engine/zakuro, v0.2.32, read only):
#   * the frontend writes every change of input to ZAKURO_RECORD, a text file: "clock <ms since
#     1900>", then one line per change, "<frame> <buttons hex> <circle x> <circle y> <touch x>
#     <touch y> <tilt x> <tilt y> <c-stick x> <c-stick y>" (crates/zakuro-core/src/replay.rs:20-48;
#     crates/zakuro/src/lib.rs:836-841 and 868-875 start it, lib.rs:1798-1799 writes each frame)
#   * with a recording the clock starts at the host's time, written on the first line
#     (lib.rs:837-841), so the headless replay (boot.exe, ZAKURO_REPLAY, boot.rs:69-77 and
#     269-270) runs from the same clock
#   * --recompiled names the library and --data the save folder (crates/zakuro/src/cli.rs:124-129);
#     the game's own "recompiled" setting off makes the frontend interpret instead (lib.rs:747-754),
#     so the capture library would never run: refused
#   * an update or DLC .cia beside the ROM is loaded with it (lib.rs:830-834, library.rs:195-220);
#     the capture library and the headless replay use the plain game: a STOP

HARNESS_DIR = Path(os.environ.get(ENV("HARNESS_DIR")) or (REPO / "build" / "harness"))
SESSIONS_DIR = HARNESS_DIR / "sessions"
CAPTURE_LIB = HARNESS_DIR / "lib" / f"{TITLE_HEX}.dll"
HARNESS_SAVES = HARNESS_DIR / "saves"   # saves packed by headless routes (headless.py --pack)
SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
LANGUAGE_CODES = {  # crates/zakuro/src/settings.rs:204-270, the names settings.toml uses
    "japanese": 0, "english": 1, "french": 2, "german": 3, "italian": 4, "spanish": 5,
    "chinese_simplified": 6, "korean": 7, "dutch": 8, "portuguese": 9, "russian": 10,
    "chinese_traditional": 11,
}

CAPTURE_CHECKLIST = """\
Owner checklist: one capture session of about 30-45 minutes (docs/PLAY.md, capture).
Your real save is NOT used and NOT changed: the session plays a copy, and progress
made in it stays in the copy.

  In the game (Continue the save), at normal speed. Start from a save at the start of
  a chapter (any route). A messy clear is fine; a game over (restart) is the only thing
  that wastes the session.
   [ ] do NOT skip the chapter's story scenes (they reach event code routes cannot)
   [ ] one battle: attack, heal, an Attack Stance and a Guard Stance pairing, a trade,
       then end the turn and let the whole enemy phase run; let a level-up finish if
       one happens (do not reset for one)
   [ ] after the chapter, open one My Castle menu that is there (shop, armory,
       convoy or a support list); if one is missing, do not go looking for it
   [ ] save in the game in a NEW slot, then stop
  Skip: class changes, children, the castle's 3D walk-around, amiibo, online,
  tutorials, support grinding.
  Press F5 two or three times at interesting moments (savestates).

  Please do NOT, during the session:
   - load a savestate (the recording cannot play a loaded state back)
   - change Zakuro settings, enhancements, cheats, the 3D (stereo / depth) or the top-screen extras
  Then close Zakuro normally and tell Claude the session name: {session}
  Everything it left is in {folder}"""


def check_fresh() -> tuple[bool, str]:
    """tools/harness/build.py --check-fresh: (fresh, its verdict line). Anything but FRESH refuses."""
    build = REPO / "tools" / "harness" / "build.py"
    if not build.is_file():
        return False, "tools/harness/build.py is missing"
    try:
        run = subprocess.run([sys.executable, str(build), "--check-fresh"], capture_output=True, text=True,
                             timeout=1800, cwd=str(REPO))
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"could not run build.py --check-fresh ({error})"
    lines = [ln.strip() for ln in (run.stdout + "\n" + run.stderr).splitlines() if ln.strip()]
    line = next((ln for ln in lines if ln.startswith("harness-build:")), lines[-1] if lines else "no output")
    return run.returncode == 0 and line.startswith("harness-build: FRESH"), line


def extdata_member_ok(name: str, extdata_id: int | None) -> bool:
    """extdata/<hex id>[.format][/...]: with the ROM's extdata id known only that id (as save_items
    picks it), otherwise any hex-named extdata folder."""
    parts = name.split("/")
    if len(parts) < 2 or parts[0] != "extdata" or not parts[1]:
        return False
    stem = parts[1].removesuffix(".format")
    try:
        value = int(stem, 16)
    except ValueError:
        return False
    return extdata_id is None or value == extdata_id or (value & 0xFFFFFFFF) == extdata_id


def check_save_zip(path: Path, extdata_id: int | None = None) -> list[str]:
    """The members of a PLAY save zip (paths relative to Zakuro's user folder). Only this game's
    savedata and hex-named extdata (with extdata_id: only that one) are accepted, never a path that
    leaves the folder."""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except (OSError, zipfile.BadZipFile) as error:
        raise Stop(f"{path.name} is not a readable zip ({error}).")
    for name in names:
        parts = name.split("/")
        if "\\" in name or name.startswith("/") or ":" in name or ".." in parts \
                or not (name.startswith(f"savedata/{TITLE_HEX}") or extdata_member_ok(name, extdata_id)):
            raise Stop(f"{path.name}: unexpected member {name!r} (not a PLAY save backup).")
    if not any(n.startswith(f"savedata/{TITLE_HEX}/") and not n.endswith("/") for n in names):
        raise Stop(f"{path.name} holds no {GAME} save files.")
    return names


def extract_save_zip(path: Path, user_dir: Path, extdata_id: int | None = None) -> list[str]:
    """Lays a checked PLAY save zip out under user_dir (a scratch Zakuro user folder)."""
    names = check_save_zip(path, extdata_id)
    user_dir = Path(user_dir).resolve()
    with zipfile.ZipFile(path) as z:
        for name in names:
            target = (user_dir / name).resolve()
            if user_dir not in target.parents:
                raise Stop(f"{path.name}: member {name!r} leaves the save folder.")
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return names


def within(path: Path, top: Path) -> bool:
    path, top = Path(path).resolve(), Path(top).resolve()
    return top in path.parents


def find_capture_save(config: dict, choice: str | None) -> tuple[str, Path]:
    """("backup", zip) or ("portable", data folder): where the session's copy comes from. Only
    PLAY's own backups (play/backups), saves the headless routes packed (build/harness/saves) or
    PLAY's portable data; never %APPDATA%\\zakuro\\user."""
    if choice and choice.lower() == "portable":
        folder = portable_data_dir(config)
        if not save_exists(folder):
            raise Stop(f"There is no {GAME} save in PLAY's portable folder:\n  {folder}")
        return "portable", folder
    if choice:
        for top in (BACKUP_DIR, HARNESS_SAVES):
            for name in (choice, choice + ".zip"):
                path = top / name
                if path.is_file() and within(path, top):
                    return "backup", path
        raise Stop(f"--capture-from {choice}: no such zip in play\\backups (or build\\harness\\saves).")
    zips = sorted((p for p in BACKUP_DIR.glob("*.zip") if not p.name.endswith("-seal.zip")),
                  key=lambda p: p.stat().st_mtime)    # a Seal edition save is never a Fates session's start
    if not zips:
        raise Stop("There is no save backup in play\\backups yet. Run PLAY.bat --backup once\n"
                   "(it zips your save), then PLAY.bat --capture again.")
    return "backup", zips[-1]


def copy_start_save(source: Path, session_dir: Path, extdata_id: int | None = None) -> Path:
    """Copies a checked save zip from play/backups or build/harness/saves to <session>/start-save.zip:
    the start every headless replay of the session lays out again (HARNESS.md 4.3)."""
    if not (within(source, BACKUP_DIR) or within(source, HARNESS_SAVES)):
        raise Stop(f"{source}: a session's save comes only from play\\backups or build\\harness\\saves.")
    check_save_zip(source, extdata_id)
    dest = Path(session_dir) / "start-save.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return dest


def capture_settings(settings: dict) -> dict:
    """What of Zakuro's settings reaches the game in the session, for the headless replay to match
    (crates/zakuro/src/lib.rs:746-771 builds the game's config from them)."""
    per_game = settings.get("per_game") or {}
    own = next((v for k, v in per_game.items() if str(k).upper() == TITLE_HEX and isinstance(v, dict)), {})
    language = str(own.get("language") or settings.get("language") or "english").lower()
    enhancements = settings.get("enhancements") or {}
    names = next((v for k, v in enhancements.items() if str(k).upper().lstrip("0") == TITLE_HEX.lstrip("0")), [])
    nickname = str(settings.get("nickname") or "").strip()

    def merged(key: str, default):
        value = own.get(key, settings.get(key, default))
        return default if value is None else value

    # the console's 3D slider reaches the game every frame (crates/zakuro/src/lib.rs:1282-1286 ->
    # zakuro-core set_slider_3d, the shared page); settings.rs:740-746: 0 while stereo is off, else
    # depth_3d/100. stereo and depth_3d may be global or per game (settings.rs:702-703).
    stereo = str(merged("stereo", "off")).lower()
    try:
        depth = max(0, min(100, int(merged("depth_3d", 50))))
    except (TypeError, ValueError):
        depth = 50
    slider = 0.0 if stereo == "off" else depth / 100.0
    battle_ui = str(own.get("battle_ui") or "off").lower()     # per game only (settings.rs:504-509)
    bottom_over, touch_pointer = bool(own.get("bottom_over", False)), bool(own.get("touch_pointer", False))
    return {
        "language": language,
        "language_code": LANGUAGE_CODES.get(language),
        # lib.rs nickname(): blank is "Player", at most 10 characters
        "nickname": nickname[:10] if nickname else "Player",
        "console_id": settings.get("console_id"),
        "enhancements": [str(n) for n in names] if isinstance(names, list) else [],
        "resolution": own.get("resolution", settings.get("resolution", 3)),
        "recompiled": own.get("recompiled", settings.get("recompiled", True)),
        "new3ds": False,
        "hardware_rasterizer": True,   # --rasterizer hardware, as every headless run (risk 20)
        "stereo": stereo,
        "depth_3d": depth,
        "slider_3d": slider,           # replayed as ZAKURO_3D (examples/boot.rs:57-59)
        # recorded, not replayed: frame interpolation and texture packs are drawing only (the session's
        # data folder has no mods/, so no pack loads); the top-screen extras rewrite the input before
        # the recorder writes it (lib.rs:1744-1799), so input.rec already holds what the game got
        "frame_interpolation": bool(merged("frame_interpolation", False)),
        "texture_packs": bool(merged("texture_packs", True)),
        "battle_ui": battle_ui,
        "bottom_over": bottom_over,
        "touch_pointer": touch_pointer,
        "top_screen_extras": battle_ui != "off" or bottom_over or touch_pointer,
    }


def cia_beside_rom(rom: Path) -> list[str]:
    try:
        return sorted(p.name for p in rom.parent.iterdir() if p.suffix.lower() == ".cia")
    except OSError:
        return []


# signature type -> bytes of signature + padding before a signed body (3DS TMD layout)
_SIG_SKIP = {0x10000: 0x240, 0x10001: 0x140, 0x10002: 0x7C, 0x10003: 0x240, 0x10004: 0x140, 0x10005: 0x7C}


def cia_title_id(path: Path) -> int | None:
    """The title id in a .cia's TMD (read only, a few KiB), or None when it cannot be read.
    CIA header: u32 header size, u16 type, u16 version, u32 cert chain, ticket, TMD sizes;
    each part starts on a 64-byte boundary; the TMD body holds the title id (big-endian)
    at 0x4C."""
    def up64(n: int) -> int:
        return (n + 63) & ~63
    try:
        with path.open("rb") as f:
            head = f.read(0x20)
            if len(head) < 0x14:
                return None
            hsize, _, _, certs, ticket, tmd_size = struct.unpack_from("<IHHIII", head, 0)
            if not (0x20 <= hsize <= 0x4000) or tmd_size < 0x200:
                return None
            f.seek(up64(hsize) + up64(certs) + up64(ticket))
            tmd = f.read(0x300)
        skip = _SIG_SKIP.get(struct.unpack_from(">I", tmd, 0)[0])
        if skip is None or len(tmd) < skip + 0x54:
            return None
        return struct.unpack_from(">Q", tmd, skip + 0x4C)[0]
    except (OSError, struct.error):
        return None


def classify_cias(rom: Path) -> tuple[list[str], list[str]]:
    """(stops, notes) for the .cia files beside the ROM, which Zakuro loads with the game.
    An update of this game (0004000E....) changes its code: a stop. DLC of this game
    (0004008C....) adds data only: a note. Anything unreadable or another game's: a stop,
    to be safe (Zakuro would try to load it with this game)."""
    stops, notes = [], []
    low = TITLE_ID & 0xFFFFFFFF
    for name in cia_beside_rom(rom):
        tid = cia_title_id(rom.parent / name)
        if tid is not None and tid & 0xFFFFFFFF == low and tid >> 32 == 0x0004008C:
            notes.append(name)
        else:
            stops.append(name + ("" if tid is None else f" (title {tid:016X})"))
    return stops, notes


def capture_env(base: dict, session_dir: Path, live: str) -> dict:
    """The session's environment: no inherited ZAKURO_ / FE_ setting survives (a stray ZAKURO_REPLAY
    or FE_CAPTURE_ONLY would change the session). The options file's path (FE_OPTIONS, or the game's
    own <prefix>_OPTIONS) never reaches a capture: options are off during capture (docs/OPTIONS_WIRING.md)."""
    env = {k: v for k, v in base.items() if not k.upper().startswith(("ZAKURO_", "FE_", "RUST_LOG"))
           and k.upper() != OPTIONS_ENV}
    env.update(ZAKURO_RECORD=str(session_dir / "input.rec"), FE_READABLE="capture",
               FE_CAPTURE_DIR=str(session_dir / "capture"), FE_CAPTURE_LIVE=live)
    return env


def capture_command(exe: Path, config: dict, session_dir: Path, mute: bool) -> list[str]:
    cmd = [str(exe), str(Path(config["rom"])), "--data", str(session_dir / "data"),
           "--recompiled", str(CAPTURE_LIB), "--rasterizer", "hardware"]
    scale = config.get("scale")
    if scale not in (None, "", 0):
        cmd += ["--scale", str(int(scale))]
    return cmd + (["--mute"] if mute else [])


def file_sha256(path: Path) -> str:
    return sha256_file(path, progress=False)


def prepare_session(session_dir: Path, kind: str, source: Path, extdata_id: int | None) -> dict:
    """Makes build/harness/sessions/<id>/: start-save.zip and data/user laid out from it, capture/."""
    if not within(session_dir, SESSIONS_DIR):
        raise Stop(f"{session_dir}: a session folder must be below {SESSIONS_DIR}")
    session_dir.mkdir(parents=True, exist_ok=False)
    start = session_dir / "start-save.zip"
    if kind == "portable":
        if zip_save(source, extdata_id, start) is None:   # PLAY's own backup logic
            raise Stop(f"No save files found in {source}.")
    else:
        copy_start_save(source, session_dir, extdata_id)
    members = extract_save_zip(start, session_dir / "data" / "user", extdata_id)
    (session_dir / "capture").mkdir()
    return {"start_save": "start-save.zip", "start_save_sha256": file_sha256(start),
            "start_save_bytes": start.stat().st_size, "members": members,
            "source": str(source), "source_kind": kind}


def library_manifest() -> dict:
    try:
        return json.loads((CAPTURE_LIB.parent / "harness_build.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def confirm_start() -> bool:
    if not sys.stdin or not sys.stdin.isatty():
        return False
    try:
        return input("Type START and press Enter to begin the session (anything else cancels): ").strip().upper() == "START"
    except EOFError:
        return False


def run_capture(opts: dict, extra: list[str]) -> int:
    """PLAY --capture: every check, the plan and the checklist; starts Zakuro only after START (or
    --go). Never the standalone program: it has the game's code built in, not the capture library."""
    config, created = load_config()
    if created:
        print(f"First run: wrote play\\config.json with the default paths ({CONFIG_PATH}).")
    if any(a != "--mute" for a in extra):
        raise Stop("With --capture only --mute may follow --: the session must match the headless replay.")
    exe = find_zakuro(config)
    state = load_state()
    notes: list[str] = []
    blockers: list[str] = []
    rom_info = check_rom(config, state, opts["rehash"], notes)
    extdata_id = rom_info.get("extdata_id")
    sid = opts["session"] or f"cap-{timestamp()}"
    if not SESSION_ID.fullmatch(sid):
        raise Stop(f"--session {sid}: letters, digits, _ . - only (up to 64), starting with a letter or digit.")
    session_dir = SESSIONS_DIR / sid
    if session_dir.exists():
        raise Stop(f"The session {sid} exists already ({session_dir}); a session is never reused.\n"
                   "Pick another name with --session, or leave it out.")
    if not CAPTURE_LIB.is_file():
        raise Stop(f"There is no capture library at\n  {CAPTURE_LIB}\n"
                   "It is built by the agents (python tools/harness/build.py).")
    fresh, line = check_fresh()
    if not fresh:
        raise Stop(f"The capture library is not built from today's sources:\n  {line}\n"
                   "It must be rebuilt first (python tools/harness/build.py, the agents do this).")
    kind, source = find_capture_save(config, opts["capture_from"])
    if kind == "backup":
        check_save_zip(source, extdata_id)
    snap = capture_settings(read_settings())
    if snap["recompiled"] is False:
        raise Stop("Zakuro's settings say not to run recompiled code for this game, so the capture\n"
                   "library would never run. Turn \"recompiled\" back on (Esc > Settings for this game).")
    if snap["language_code"] is None:
        blockers.append(f"Zakuro's language setting {snap['language']!r} is not one PLAY knows; the replay could not match it.")
    if rom_info.get("hash_mismatch"):
        blockers.append(f"The ROM's SHA-256 is not the known clean {GAME} dump's (see PLAY.bat --check).")
    cias = cia_beside_rom(Path(config["rom"]))
    if cias:
        blockers.append("These .cia files lie beside the ROM: " + ", ".join(cias) + ".\n"
                        "  Zakuro loads an update or DLC of the game from there, which the capture library\n"
                        "  and the headless replay do not use. Move them out for the session.")
    if zakuro_running():
        blockers.append(f"Zakuro or {STANDALONE_NAME} is already running: close it first.")

    live = opts["live"] or "a"
    env = capture_env(dict(os.environ), session_dir, live)
    cmd = capture_command(exe, config, session_dir, "--mute" in extra)
    for n in notes:
        print(n)
    when = _dt.datetime.fromtimestamp(source.stat().st_mtime)
    print(f"Capture session {sid}")
    print(f"  save copied from  {source} ({'PLAY portable save' if kind == 'portable' else f'backup of {when:%Y-%m-%d %H:%M}'})")
    print(f"  capture library   {CAPTURE_LIB} ({line})")
    print(f"  Zakuro settings   language {snap['language']}, nickname {snap['nickname']}, enhancements "
          f"{', '.join(snap['enhancements']) or 'none'}, resolution {snap['resolution']}, 3D slider "
          f"{snap['slider_3d']:g} (stereo {snap['stereo']}), top-screen extras "
          f"{'on' if snap['top_screen_extras'] else 'off'}")
    print(f"  session folder    {session_dir}")
    for key in ("ZAKURO_RECORD", "FE_READABLE", "FE_CAPTURE_DIR", "FE_CAPTURE_LIVE"):
        print(f"  {key}={env[key]}")
    print("  command (from the session folder):")
    print("    " + subprocess.list2cmdline(cmd))
    if blockers and not opts["anyway"]:
        for b in blockers:
            print("\nSTOP: " + b)
        return 1
    for b in blockers:
        print("Going on anyway (--anyway): " + b.splitlines()[0])
    print()
    print(CAPTURE_CHECKLIST.format(session=sid, folder=session_dir))
    print()
    if opts["dry_run"]:
        print(f"[dry run] would copy the save into {session_dir / 'data'} and start Zakuro as above. Nothing was made.")
        return 0
    if not (opts["go"] or confirm_start()):
        print("Not started (no START typed). Nothing was made.")
        return 1
    info = prepare_session(session_dir, kind, source, extdata_id)
    manifest = library_manifest()
    record = {
        "session": sid, "kind": "owner", "created": _dt.datetime.now().isoformat(timespec="seconds"),
        "about": "PLAY --capture (docs/HARNESS.md 4.2); replayed headless by tools/harness/recapture.py (4.3)",
        **info,
        "program": str(exe), "program_sha256": file_sha256(exe),
        "rom_sha256": rom_info.get("sha256"), "rom_check": config.get("check_rom"),
        "library": str(CAPTURE_LIB), "library_sha256": manifest.get("library_sha256"), "library_fresh": line,
        "settings": snap, "cia_beside_rom": cias,
        "env": {k: env[k] for k in ("ZAKURO_RECORD", "FE_READABLE", "FE_CAPTURE_DIR", "FE_CAPTURE_LIVE")},
        "command": cmd, "cwd": str(session_dir), "input": "input.rec", "frames": None,
    }
    write_json(session_dir / "session.json", record)
    launch(cmd, session_dir, env)
    print(f"Started the capture session {sid} in Zakuro. Play through the checklist, then close Zakuro.")
    return 0


def parse_args(argv: list[str]) -> tuple[dict, list[str]]:
    extra: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    opts = {"dry_run": False, "check": False, "where": False, "backup": False, "backup_seal": False, "migrate": None,
            "portable": None, "make_shortcut": False, "force": False, "rehash": False, "anyway": False,
            "setup": False, "capture": False, "go": False, "session": None, "capture_from": None, "live": None}
    valued = {"migrate_saves": "migrate", "portable": "portable", "session": "session",
              "capture_from": "capture_from", "live": "live"}
    it = iter(argv)
    for arg in it:
        key = arg.lstrip("-").replace("-", "_").lower()
        if arg in ("-h", "--help", "/?"):
            print(__doc__)
            sys.exit(0)
        if key in valued and arg.startswith("--"):
            value = next(it, None)
            if value is None:
                raise Stop(f"{arg} needs a value (see PLAY.bat --help).")
            opts[valued[key]] = value if key in ("session", "capture_from") else value.lower()
        elif key in opts and isinstance(opts[key], bool) and arg.startswith("--"):
            opts[key] = True
        else:
            raise Stop(f"Unknown option {arg!r}. PLAY.bat --help lists them; Zakuro's own go after --.")
    if opts["live"] not in (None, "a", "ab"):
        raise Stop("--live needs a or ab.")
    capture_only = [k for k in ("go", "session", "capture_from", "live") if opts[k] not in (None, False)]
    if capture_only and not opts["capture"]:
        raise Stop("--" + capture_only[0].replace("_", "-") + " belongs to --capture.")
    return opts, extra


def run_launcher(config: dict, opts: dict) -> int:
    """Round 77: the Getting ready window (tools/play/launcher.py) when something is missing, or with --setup.
    0 = go on as before; 1 = the player quit. A fault inside the launcher never stops PLAY: it goes on as before."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import launcher  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    try:
        return launcher.run(sys.modules[__name__], config, setup=opts["setup"], dry_run=opts["dry_run"])
    except Stop:
        raise
    except Exception as error:  # noqa: BLE001
        if opts["setup"]:
            raise
        print(f"Note: the Getting ready check could not run ({error.__class__.__name__}: {error}); going on as before.")
        return 0


def main(argv: list[str]) -> int:
    opts, extra = parse_args(argv)
    if opts["capture"]:
        return run_capture(opts, extra)
    if opts["backup_seal"]:                 # before load_config: it reads the Seal save and writes only the zip
        print(backup_seal(opts["dry_run"]))
        return 0
    if opts["portable"] is not None:
        print(set_portable(opts["portable"]))
        return 0
    fresh = not CONFIG_PATH.exists() and folder_is_fresh()
    config, created = load_config()
    if created:
        print(f"First run: wrote play\\config.json with the default paths ({CONFIG_PATH}).")
    if fresh:                                # round 77: a freshly unzipped folder keeps the program's places in play/
        (PLAY_DIR / PORTABLE_DIRS["APPDATA"]).mkdir(parents=True, exist_ok=True)
    real_appdata = os.environ.get("APPDATA")
    portable_env = None if opts["migrate"] else portable_folder_env(config)
    if portable_env is not None:             # every place below (settings, saves, backups) is then inside play/
        os.environ.update({k: portable_env[k] for k in PORTABLE_DIRS})
    if opts["where"]:
        print_where(config)
        return 0
    if opts["make_shortcut"]:
        print(make_shortcut(config, opts["force"], opts["dry_run"]))
        return 0
    if opts["setup"] or (os.environ.get(LAUNCHER_ENV) == "1" and not (
            opts["anyway"] or opts["check"] or opts["backup"] or opts["migrate"])):
        if run_launcher(config, opts):
            return 1
        if portable_env is None and not opts["migrate"]:
            portable_env = portable_folder_env(config)      # the window may have pointed to a program
            if portable_env is not None:
                os.environ.update({k: portable_env[k] for k in PORTABLE_DIRS})

    state = load_state()
    notes: list[str] = []
    blockers: list[str] = []
    exe, standalone = find_program(config)
    where_from = "the program's folder" if standalone else "Zakuro's folder"
    rom_info = check_rom(config, state, opts["rehash"], notes)
    extdata_id = rom_info.get("extdata_id")
    data_dir = active_data_dir(config)

    if opts["backup"]:
        if not save_exists(data_dir):
            raise Stop(f"No save to back up in:\n  {data_dir / 'user' / 'savedata' / TITLE_HEX}")
        dest = BACKUP_DIR / f"manual-{timestamp()}-{where_label(config)}.zip"
        if opts["dry_run"]:
            print(f"[dry run] would back up the save to {dest}")
        else:
            print(f"Backed up the save to {zip_save(data_dir, extdata_id, dest)}")
        return 0
    if opts["migrate"]:
        for line in migrate(config, opts["migrate"], extdata_id, opts["dry_run"]):
            print(line)
        return 0

    if rom_info.get("hash_mismatch"):
        blockers.append(
            f"The ROM's SHA-256 is not the known clean {GAME} dump's.\n"
            f"  got      {rom_info.get('sha256')}\n  expected {ROM_SHA256}\n"
            "  It is the right game (the header says so) but changed: a patched, trimmed or\n"
            "  differently dumped copy. Use your clean dump, set \"check_rom\": \"header\" in\n"
            "  play\\config.json, or start it once with PLAY.bat --anyway."
            + ("\n" + rom_info["size_note"] if rom_info.get("size_note") else "")
        )
    check_recompiled(config, exe, data_dir, notes, blockers, standalone)
    cia_stops, cia_notes = classify_cias(Path(config["rom"]))
    if cia_stops:
        blockers.append(
            "These .cia files lie beside the ROM: " + ", ".join(cia_stops) + ".\n"
            "  Zakuro loads a game update (or another .cia) from the ROM's folder. An update\n"
            "  changes the game's code, so the recompiled code (and the standalone program, built\n"
            "  from the clean dump) no longer fits it, and the project's mods are made for the\n"
            "  clean game. Move them to another folder (or PLAY.bat --anyway to start with them)."
        )
    if cia_notes:
        notes.append("DLC beside the ROM (Zakuro loads it with the game; data only): " + ", ".join(cia_notes))

    if portable_env is not None and real_appdata and not save_exists(data_dir) \
            and save_exists(Path(real_appdata) / "zakuro"):
        notes.append(f"Note: this folder keeps its own saves (in {data_dir}); a {GAME} save from another Zakuro is in\n"
                     f"  {Path(real_appdata) / 'zakuro'}. Nothing was copied. To use it here: PLAY.bat --migrate-saves "
                     "to-portable,\n  then PLAY.bat --portable on.")
    other = appdata_data_dir() if config.get("portable_saves") else portable_data_dir(config)
    if not save_exists(data_dir) and save_exists(other):
        to = "to-portable" if config.get("portable_saves") else "to-appdata"
        blockers.append(
            f"Your save is in the other place ({other}),\n"
            f"  not where PLAY looks now ({data_dir}).\n"
            f"  Copy it with PLAY.bat --migrate-saves {to}, or switch back with\n"
            f"  PLAY.bat --portable {'off' if config.get('portable_saves') else 'on'}."
            " (--anyway starts with a new, empty save there.)"
        )
    if zakuro_running():
        blockers.append(f"Zakuro or {STANDALONE_NAME} is already running. Two copies on one save can\n"
                        "  lose progress: close it first.")

    seal_args, sof = seal_extras() if standalone else ([], None)
    cmd = build_command(config, exe, seal_args + extra)
    for n in notes:
        print(n)
    if opts["check"]:
        for b in blockers:
            print("STOP: " + b)
        print("Check: " + ("would start." if not blockers else "would NOT start (see STOP lines)."))
        return 1 if blockers else 0
    if blockers and not opts["anyway"]:
        for b in blockers:
            print("\nSTOP: " + b)
        if opts["dry_run"]:
            print("\n[dry run] would not start. With --anyway it would run:")
            print("  cd /d " + subprocess.list2cmdline([str(exe.parent)]))
            print("  " + subprocess.list2cmdline(cmd))
        return 1
    for b in blockers:
        print("Going on anyway (--anyway): " + b.splitlines()[0])

    if opts["dry_run"]:
        if config.get("auto_backup", True) and save_exists(data_dir):
            print("[dry run] would back up the save to play\\backups (if it changed since the last backup)")
        if config.get("portable_saves"):
            print(f"[dry run] would create {data_dir} if missing")
        if portable_env is not None:
            print("[dry run] portable folder: the program gets " + ", ".join(
                f"{k}={portable_env[k]}" for k in ("APPDATA", "LOCALAPPDATA", "TEMP")))
        print(f"[dry run] would run, from {where_from}:")
        print("  cd /d " + subprocess.list2cmdline([str(exe.parent)]))
        print("  " + subprocess.list2cmdline(cmd))
        return 0

    try:
        message = auto_backup(config, state, data_dir, extdata_id)
    except OSError as error:
        message = f"Warning: the automatic backup failed ({error}); starting anyway."
    if message:
        print(message)
    if config.get("portable_saves"):
        data_dir.mkdir(parents=True, exist_ok=True)
    if sof is not None:
        # the game can be switched to the Seal edition's game in the window: its own save is backed up too
        try:
            seal_message = sof.backup_profile(extdata_id)
        except OSError as error:
            seal_message = f"Warning: the Seal edition save's backup failed ({error}); starting anyway."
        if seal_message:
            print(seal_message)
    if portable_env is not None:
        for name in sorted(set(PORTABLE_DIRS.values())):
            (PLAY_DIR / name).mkdir(parents=True, exist_ok=True)
        launch(cmd, exe.parent, env=dict(os.environ))
    else:
        launch(cmd, exe.parent)
    how = "(standalone program)" if standalone else "in Zakuro"
    print(f"Started {GAME} {how}. Saves: {data_dir / 'user' / 'savedata' / TITLE_HEX}")
    print("In the game: Esc opens the menu (Settings, Settings for this game), F11 switches full screen.")
    part = seal_part() if standalone else None
    if part is not None:
        print(part.START_LINE)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Stop as stop:
        print(f"\nSTOP: {stop}")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(1)
