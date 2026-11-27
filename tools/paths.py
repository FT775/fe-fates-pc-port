#!/usr/bin/env python3
"""Where the player's own files live (F-048, docs/collab/FOLDER_LAYOUT_GROK.md). Every tool asks here.

    roms/                 the game: Fire Emblem Fates Special Edition (USA) .cci. Nothing else.
    roms/seal/            optional: the Seal of Flames download zip (kept zipped, never edited)

    from paths import find_rom, resolve_rom, find_seal_zip     # (tools/ on sys.path)

find_rom()       roms/ first: the one .cci/.3ds there must have this game's title id (config/game.json)
                 and, with check="full", its rom_sha256 (cached in build/rom_check.json until the file
                 changes). An update .cia (or any .cia) in roms/, a wrong edition or a changed dump stops
                 with one plain sentence (PathError). For one release the old place, the repo root
                 (config/game.json "default_rom"), is still found, with a one-line "please move it" note.
resolve_rom()    what a tool uses: an explicit path, else FE_ROM, else "rom" in play/config.json when
                 that file exists, else "rom" in play/launcher.json (the file PLAY's Getting ready window
                 accepted outside roms/, round 77) when that file exists, else find_rom(). A "rom" that is
                 no longer there (the file was moved to roms/) falls back with a note; neither file is edited.
find_seal_zip()  roms/seal/ at any depth: the mod's zip (0004000000179800.zip) or the GameBanana
                 download zip that holds it. For one release the old root folder "Seal of Flames v6".
seal_mod_zip()   the mod's zip itself: when find_seal_zip() gave the download zip, its inner mod zip is
                 copied (read-only stream, never unpacked into the repo root) to build/sof-extract/download/.

Python 3 standard library only. Nothing here holds Nintendo data: title id and SHA-256 are identifiers.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from gamecfg import GAME  # noqa: E402

REPO = HERE.parent
ROMS = "roms"
SEAL = "seal"
LEGACY_SEAL_FOLDER = "Seal of Flames v6"           # the old unzipped download in the repo root
ROM_SUFFIXES = (".cci", ".3ds")
UPDATE_SUFFIXES = (".cia", ".cxi", ".cfa")
MOVE_NOTE_ROM = "Note: the game file is in the old place (the main folder); please move it to roms\\."
MOVE_NOTE_SEAL = "Note: Seal of Flames is in the old place (the main folder); please move its zip to roms\\seal\\."


class PathError(Exception):
    """A file is missing or wrong; the message is one plain sentence saying what to do."""


def _say(note: str, notes: list[str] | None) -> None:
    if notes is not None:
        notes.append(note)
    else:
        print(note, file=sys.stderr)


def roms_dir(repo: Path = REPO) -> Path:
    return Path(repo) / ROMS


def seal_dir(repo: Path = REPO) -> Path:
    return Path(repo) / ROMS / SEAL


def legacy_rom(repo: Path = REPO, game=GAME) -> Path:
    return Path(repo) / game.default_rom


def legacy_seal_dir(repo: Path = REPO) -> Path:
    return Path(repo) / LEGACY_SEAL_FOLDER


# ------------------------------------------------------------------------------------------------ ROM

def rom_title(path: Path) -> int | None:
    """The NCSD media id (title id) of a cartridge image, or None when it is not one (reads 512 bytes)."""
    try:
        with Path(path).open("rb") as f:
            head = f.read(0x200)
    except OSError:
        return None
    if len(head) < 0x200 or head[0x100:0x104] != b"NCSD":
        return None
    return struct.unpack_from("<Q", head, 0x108)[0]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(8 << 20):
            h.update(chunk)
    return h.hexdigest()


def rom_sha256(path: Path, cache: Path | None) -> str:
    """SHA-256 of the file, remembered in `cache` (JSON) by path, size and modification time."""
    path = Path(path)
    st = path.stat()
    key = {"path": str(path.resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    data: dict = {}
    if cache is not None:
        try:
            data = json.loads(Path(cache).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        hit = data.get(key["path"]) if isinstance(data, dict) else None
        if isinstance(hit, dict) and hit.get("size") == st.st_size and hit.get("mtime_ns") == st.st_mtime_ns:
            return hit.get("sha256", "")
    digest = _sha256(path)
    if cache is not None:
        try:
            data = data if isinstance(data, dict) else {}
            data[key["path"]] = dict(key, sha256=digest)
            Path(cache).parent.mkdir(parents=True, exist_ok=True)
            tmp = Path(str(cache) + ".tmp")
            tmp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
            os.replace(tmp, cache)
        except OSError:
            pass
    return digest


def check_rom_file(path: Path, *, check: str = "full", game=GAME, cache: Path | None = None) -> Path:
    """Raises PathError (one sentence) unless `path` is this game's cartridge image (and, with check="full",
    the clean dump config/game.json names)."""
    path = Path(path)
    where = f"{path.parent.name}\\{path.name}" if path.parent.name else path.name
    if path.suffix.lower() in UPDATE_SUFFIXES:
        raise PathError(f"{where} is an update or add-on file, not the game; this port needs only the "
                        f"{game.game} {game.edition} .cci, so please move {path.name} out of that folder.")
    title = rom_title(path)
    if title is None:
        raise PathError(f"{where} is not a 3DS cartridge image (.cci); put your {game.game} {game.edition} "
                        "dump there instead.")
    if title != game.title_id_int:
        raise PathError(f"{where} is a different game or edition (title {title:016X}), not {game.game} "
                        f"{game.edition} ({game.title_id}); only that edition works.")
    if check == "full":
        size = path.stat().st_size
        if size != game.rom_size or rom_sha256(path, cache) != game.rom_sha256:
            raise PathError(f"{where} is {game.game} but not the clean {game.edition} dump this port checks "
                            "(its SHA-256 differs); use your own unmodified full dump.")
    return path


def find_rom(*, repo: Path = REPO, check: str = "full", notes: list[str] | None = None, game=GAME,
             cache: Path | None = None) -> Path:
    """roms/ first, then (one release) the repo root. See the module text."""
    repo = Path(repo)
    if cache is None:
        cache = repo / "build" / "rom_check.json"
    folder = roms_dir(repo)
    if folder.is_dir():
        files = sorted(p for p in folder.iterdir() if p.is_file())
        updates = [p for p in files if p.suffix.lower() in UPDATE_SUFFIXES]
        if updates:
            check_rom_file(updates[0], check="header", game=game)      # raises: an update file is never used
        roms = [p for p in files if p.suffix.lower() in ROM_SUFFIXES]
        if len(roms) > 1:
            raise PathError(f"roms\\ holds {len(roms)} game files ({', '.join(p.name for p in roms)}); "
                            f"keep only your {game.game} {game.edition} .cci there.")
        if roms:
            return check_rom_file(roms[0], check=check, game=game, cache=cache)
    old = legacy_rom(repo, game)
    if old.is_file():
        check_rom_file(old, check=check, game=game, cache=cache)
        _say(MOVE_NOTE_ROM, notes)
        return old
    raise PathError(f"No game file found: put your {game.game} {game.edition} .cci in the roms folder "
                    f"({folder}).")


def play_config_rom(repo: Path = REPO) -> str | None:
    """"rom" from play/config.json, or None (missing file, unreadable, empty)."""
    p = Path(repo) / "play" / "config.json"
    try:
        value = json.loads(p.read_text(encoding="utf-8")).get("rom") if p.is_file() else None
    except (OSError, ValueError, AttributeError):
        return None
    return value or None


def launcher_rom(repo: Path = REPO) -> str | None:
    """"rom" from play/launcher.json (the game file PLAY's Getting ready window accepted, round 77), or None."""
    p = Path(repo) / "play" / "launcher.json"
    try:
        value = json.loads(p.read_text(encoding="utf-8")).get("rom") if p.is_file() else None
    except (OSError, ValueError, AttributeError):
        return None
    return (str(value).strip() or None) if value else None


def resolve_rom(given: str | os.PathLike | None = None, *, repo: Path = REPO, check: str = "full",
                notes: list[str] | None = None, use_env: bool = True, use_config: bool = True,
                use_launcher: bool | None = None, game=GAME) -> Path:
    """An explicit path (not checked here), else FE_ROM, else play/config.json's "rom" when that file is
    there, else play/launcher.json's "rom" when that file is there (use_launcher; by default as use_config),
    else find_rom(). Raises PathError when nothing is found."""
    if given:
        return Path(given)
    if use_env and os.environ.get("FE_ROM"):
        return Path(os.environ["FE_ROM"])
    rom = None
    if use_config:
        rom = play_config_rom(repo)
        if rom and Path(rom).is_file():
            return Path(rom)
    if use_config if use_launcher is None else use_launcher:
        chosen = launcher_rom(repo)
        if chosen and Path(chosen).is_file():
            if rom:
                _say(f"Note: play\\config.json names a game file that is not there ({rom}); using the one the "
                     "Getting ready window was pointed to (play\\launcher.json).", notes)
            return Path(chosen)
    if rom:
        _say(f"Note: play\\config.json names a game file that is not there ({rom}); looking in roms\\.", notes)
    return find_rom(repo=repo, check=check, notes=notes, game=game)


def try_resolve_rom(given=None, **kw) -> Path | None:
    """resolve_rom(), or None instead of PathError (quiet: notes are dropped)."""
    kw.setdefault("notes", [])
    try:
        return resolve_rom(given, **kw)
    except PathError:
        return None


# ------------------------------------------------------------------------------------- Seal of Flames

def mod_zip_name(game=GAME) -> str:
    return f"{game.title_id}.zip"


def _zip_kind(path: Path, game=GAME) -> str | None:
    """'mod' (the mod's own zip: <title>/romfs/...), 'download' (a zip holding <title>.zip), or None."""
    name = mod_zip_name(game).lower()
    if path.name.lower() == name:
        return "mod"
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except (OSError, zipfile.BadZipFile):
        return None
    if any(n.replace("\\", "/").rsplit("/", 1)[-1].lower() == name for n in names):
        return "download"
    if any(n.replace("\\", "/").lower().startswith(game.title_id.lower() + "/") for n in names):
        return "mod"
    return None


def find_seal_zip(*, repo: Path = REPO, notes: list[str] | None = None, game=GAME) -> Path | None:
    """The Seal of Flames zip: roms/seal/ at any depth (the mod's zip preferred over a download zip), else
    (one release) the old root folder. None when there is none (Seal of Flames is optional)."""
    repo = Path(repo)
    folder = seal_dir(repo)
    if folder.is_dir():
        zips = sorted((p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".zip"),
                      key=lambda p: (len(p.relative_to(folder).parts), str(p).lower()))
        kinds = [(p, _zip_kind(p, game)) for p in zips]
        for want in ("mod", "download"):
            for p, kind in kinds:
                if kind == want:
                    return p
    old = legacy_seal_dir(repo) / mod_zip_name(game)
    if old.is_file():
        _say(MOVE_NOTE_SEAL, notes)
        return old
    return None


def seal_zip_kind(path: Path, game=GAME) -> str | None:
    return _zip_kind(Path(path), game)


def seal_mod_zip(path: Path, work: Path, game=GAME) -> Path:
    """The mod's zip for `path`: itself when it is the mod's zip; for the GameBanana download zip, its inner
    <title>.zip copied once to work/download/<size>-<name> (the download is only read; nothing goes to the root)."""
    path = Path(path)
    if _zip_kind(path, game) != "download":
        return path
    name = mod_zip_name(game).lower()
    with zipfile.ZipFile(path) as zf:
        members = [i for i in zf.infolist()
                   if not i.is_dir() and i.filename.replace("\\", "/").rsplit("/", 1)[-1].lower() == name]
        if len(members) != 1:
            raise PathError(f"{path.name} holds {len(members)} copies of {mod_zip_name(game)}; "
                            "put the Seal of Flames download zip itself in roms\\seal\\.")
        info = members[0]
        out = Path(work) / "download" / f"{info.file_size}-{info.CRC:08x}-{mod_zip_name(game)}"
        if out.is_file() and out.stat().st_size == info.file_size:
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".part")
        with zf.open(info) as src, tmp.open("wb") as dst:
            shutil.copyfileobj(src, dst, 8 << 20)
        os.replace(tmp, out)
        return out


if __name__ == "__main__":
    notes: list[str] = []
    try:
        print("ROM:  ", resolve_rom(notes=notes, check=(sys.argv[1] if len(sys.argv) > 1 else "header")))
    except PathError as e:
        print("ROM:   STOP:", e)
    print("Seal: ", find_seal_zip(notes=notes) or "none (optional)")
    for n in notes:
        print(n)
