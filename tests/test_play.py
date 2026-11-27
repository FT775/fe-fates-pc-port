"""Self-tests for the PLAY launcher (tools/play/play.py, PLAY.bat).

    python -m unittest tests.test_play          (from the repo root)

Everything runs in temporary folders: a fake APPDATA, a fake Zakuro folder (an empty
zakuro.exe that is never started: only --dry-run, --check, --where, --backup and
--migrate-saves are exercised) and a synthetic cartridge header of a few KiB with the
title id and product code the launcher expects (identifiers only, no game bytes).
Needs no ROM, no Zakuro and no network.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAY = ROOT / "tools" / "play" / "play.py"
sys.path.insert(0, str(ROOT / "tools"))
from gamecfg import GAME  # noqa: E402  (config/game.json: the game under test)

TITLE = GAME.title_id_int
TID = f"{TITLE:016X}"
PRODUCT = GAME.product_code.encode()
OTHER_TITLE = 0x00040000000A0500      # another game (Fire Emblem Awakening USA): always refused
OTHER_TID = f"{OTHER_TITLE:016X}"
EXTDATA_TEST_ID = 0x1234  # a made-up extdata id for the synthetic header
STANDALONE = GAME.port.standalone_name
ENV_PLAY, ENV_HARNESS, ENV_NOT_RUNNING = GAME.env("PLAY_DIR"), GAME.env("HARNESS_DIR"), GAME.env("ASSUME_NOT_RUNNING")
ROM_NAME = GAME.default_rom


def fake_rom(path: Path, *, title: int = TITLE, product: bytes = PRODUCT, decrypted: bool = True,
             exheader: bool = True) -> None:
    ncsd = bytearray(0x200)
    ncsd[0x100:0x104] = b"NCSD"
    struct.pack_into("<Q", ncsd, 0x108, title)
    struct.pack_into("<II", ncsd, 0x120, 1, 8)          # partition 0 at 0x200
    ncch = bytearray(0x200)
    ncch[0x100:0x104] = b"NCCH"
    struct.pack_into("<Q", ncch, 0x118, title)
    ncch[0x150:0x150 + len(product)] = product
    struct.pack_into("<I", ncch, 0x180, 0x400)
    ncch[0x18F] = 0x04 if decrypted else 0x00
    ext = bytearray(0x400)
    struct.pack_into("<Q", ext, 0x230, EXTDATA_TEST_ID if exheader else 0)
    path.write_bytes(bytes(ncsd + ncch + ext))


def fake_cia(path: Path, title_id: int, sig: int = 0x10004) -> None:
    """A synthetic .cia head (identifiers only): header, empty cert chain and ticket, then a
    TMD whose body holds title_id; sizes laid out on 64-byte boundaries as in a real one."""
    skip = {0x10000: 0x240, 0x10001: 0x140, 0x10002: 0x7C, 0x10003: 0x240, 0x10004: 0x140, 0x10005: 0x7C}.get(sig, 0x140)
    header = bytearray(0x2040)                       # 0x2020 rounded up to 64
    struct.pack_into("<IHHIII", header, 0, 0x2020, 0, 0, 0, 0, 0x208 + skip)
    tmd = bytearray(skip + 0xC4)
    struct.pack_into(">I", tmd, 0, sig)
    struct.pack_into(">Q", tmd, skip + 0x4C, title_id)
    path.write_bytes(bytes(header + tmd))


def load_play(env: dict):
    """A private copy of play.py whose folders come from env (<prefix>_PLAY_DIR, <prefix>_HARNESS_DIR)."""
    from unittest import mock
    import importlib.util
    with mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location("play_under_test", PLAY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class PlayBase(unittest.TestCase):
    """The sandbox and helpers (no tests): PlayTests here, the Seal edition's tests/seal/test_play_seal.py."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.appdata = base / "AppData"
        self.play = base / "play"
        self.zakuro = base / "Zakuro (test)"
        self.zakuro.mkdir()
        (self.zakuro / "zakuro.exe").write_bytes(b"")
        self.rom = base / "games" / ROM_NAME
        self.rom.parent.mkdir()
        fake_rom(self.rom)
        self.play.mkdir()
        self.write_config()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_config(self, **over) -> None:
        config = {"zakuro_dir": str(self.zakuro), "rom": str(self.rom), "check_rom": "header"}
        config.update(over)
        (self.play / "config.json").write_text(json.dumps(config), encoding="utf-8")

    def run_play(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, APPDATA=str(self.appdata), **{ENV_PLAY: str(self.play), ENV_NOT_RUNNING: "1",
                                                             GAME.env("ROM_REPO"): str(self.play.parent)})
        return subprocess.run([sys.executable, str(PLAY), *args], capture_output=True, text=True, env=env, timeout=120)

    def make_dll(self) -> None:
        dll = self.appdata / "3dsrecomp" / f"{TID}.dll"
        dll.parent.mkdir(parents=True, exist_ok=True)
        dll.write_bytes(b"")

    def make_save(self, data_dir: Path, content: bytes = b"save") -> None:
        folder = data_dir / "user" / "savedata" / TID
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "Global").write_bytes(content)
        (data_dir / "user" / "savedata" / f"{TID}.format").write_bytes(b"fmt")
        ext = data_dir / "user" / "extdata" / f"{EXTDATA_TEST_ID:016X}"
        ext.mkdir(parents=True, exist_ok=True)
        (ext / "Cache").write_bytes(b"ext")


    # -- a synthetic play/seal-of-flames save folder (round 73b; zip_save and the capture rule use it here) --

    def make_seal_save(self) -> Path:
        data = self.play / "seal-of-flames" / "data"
        folder = data / "user" / "savedata" / TID
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "Chapter0").write_bytes(b"seal-chapter")
        (folder / "Global").write_bytes(b"seal-global")
        (data / "user" / "savedata" / f"{TID}.format").write_bytes(b"fmt")
        ext_id = int(GAME.extdata_id, 16)
        ext = data / "user" / "extdata" / f"{ext_id:016X}"
        ext.mkdir(parents=True, exist_ok=True)
        (ext / "Map0.bak").write_bytes(b"seal-ext")
        (data / "user" / "extdata" / f"{ext_id:016X}.format").write_bytes(b"efmt")
        other = data / "user" / "extdata" / f"{EXTDATA_TEST_ID:016X}"   # another title's extdata: left out
        other.mkdir(parents=True, exist_ok=True)
        (other / "x").write_bytes(b"other")
        (data / "mods" / TID / "romfs").mkdir(parents=True, exist_ok=True)
        (data / "zakuro.log").write_bytes(b"log")
        return data

    def snapshot(self) -> dict:
        base = Path(self.tmp.name)
        return {str(p.relative_to(base)): (p.stat().st_mtime_ns, p.stat().st_size, p.read_bytes())
                for p in base.rglob("*") if p.is_file()}


class PlayTests(PlayBase):
    # -- launching ------------------------------------------------------------------------

    def test_dry_run_prints_command_with_rom(self) -> None:
        self.make_dll()
        out = self.run_play("--dry-run", "--", "--mute")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("[dry run] would run", out.stdout)
        self.assertIn(f'"{self.zakuro / "zakuro.exe"}" "{self.rom}" --mute', out.stdout)
        self.assertNotIn("--data", out.stdout)

    def make_standalone(self) -> Path:
        exe = self.play / "game" / STANDALONE   # empty, never started
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"")
        return exe

    def test_standalone_is_preferred_and_needs_no_dll(self) -> None:
        exe = self.make_standalone()
        out = self.run_play("--dry-run", "--", "--mute")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("standalone", out.stdout)
        self.assertIn(f'"{exe}" "{self.rom}" --mute', out.stdout)
        self.assertIn("from the program's folder", out.stdout)
        self.assertNotIn("press Recompile", out.stdout)

    def test_standalone_exe_sha_must_equal_build_record(self) -> None:
        """round 68: --check (the install proof) compares the program's sha256 with its build-record.json"""
        import hashlib
        exe = self.make_standalone()
        exe.write_bytes(b"program v2")
        record = exe.parent / "build-record.json"
        record.write_text(json.dumps({"sha256": hashlib.sha256(b"program v2").hexdigest()}), encoding="utf-8")
        same = self.run_play("--check")
        self.assertEqual(same.returncode, 0, same.stdout + same.stderr)
        self.assertNotIn("not the one its build-record.json describes", same.stdout)
        record.write_text(json.dumps({"sha256": hashlib.sha256(b"program v1").hexdigest()}), encoding="utf-8")
        other = self.run_play("--check")
        self.assertEqual(other.returncode, 1, other.stdout + other.stderr)
        self.assertIn("not the one its build-record.json describes", other.stdout)
        self.assertIn("would NOT start", other.stdout)
        anyway = self.run_play("--dry-run", "--anyway")
        self.assertEqual(anyway.returncode, 0, anyway.stdout + anyway.stderr)
        record.write_text(json.dumps({"finished": "old record without a sha"}), encoding="utf-8")
        old = self.run_play("--check")
        self.assertEqual(old.returncode, 0, old.stdout + old.stderr)

    def test_standalone_works_without_zakuro(self) -> None:
        exe = self.make_standalone()
        self.write_config(zakuro_dir=str(self.zakuro / "nowhere"))
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(f'"{exe}" "{self.rom}"', out.stdout)

    def test_standalone_false_uses_zakuro(self) -> None:
        self.make_standalone()
        self.make_dll()
        self.write_config(standalone=False)
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(f'"{self.zakuro / "zakuro.exe"}" "{self.rom}"', out.stdout)
        where = self.run_play("--where")
        self.assertIn('"standalone": false', where.stdout)

    def test_standalone_keeps_save_checks_and_backups(self) -> None:
        self.make_standalone()
        self.make_save(self.appdata / "zakuro")
        out = self.run_play("--backup")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(len(list((self.play / "backups").glob("manual-*.zip"))), 1)
        where = self.run_play("--where")
        self.assertIn(f"standalone ({STANDALONE})", where.stdout)
        self.assertIn(str(self.appdata / "zakuro" / "user" / "savedata" / TID), where.stdout)

    def test_first_run_writes_config_with_defaults(self) -> None:
        (self.play / "config.json").unlink()
        out = self.run_play("--where")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        config = json.loads((self.play / "config.json").read_text(encoding="utf-8"))
        self.assertFalse(config["portable_saves"])
        self.assertEqual(config["zakuro_dir"], "")            # F-048: no machine-specific path by default
        self.assertIn("First run", out.stdout)

    def test_missing_recompiled_code_stops(self) -> None:
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 1)
        self.assertIn("press Recompile", out.stdout)
        self.assertIn("would not start", out.stdout)
        out = self.run_play("--dry-run", "--anyway")
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_recompiled_off_in_settings_is_a_note_not_a_stop(self) -> None:
        settings = self.appdata / "zakuro" / "settings.toml"
        settings.parent.mkdir(parents=True)
        settings.write_text(f'recompiled = true\n[per_game.{TID}]\nrecompiled = false\n', encoding="utf-8")
        out = self.run_play("--check")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("interpreter", out.stdout)

    def test_missing_zakuro_and_rom_stop(self) -> None:
        self.write_config(zakuro_dir=str(self.zakuro / "nowhere"))
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 1)
        self.assertIn("zakuro.exe was not found", out.stdout)
        self.write_config(rom=str(self.rom) + ".missing")
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 1)
        self.assertIn("names a game file that is not there", out.stdout)
        self.assertIn("No game file found", out.stdout)       # tools/paths.py: nothing in roms/ either

    def test_wrong_game_encrypted_and_bad_header_stop(self) -> None:
        self.make_dll()
        fake_rom(self.rom, title=OTHER_TITLE)
        self.assertIn(f"not {GAME.game}", self.run_play("--dry-run").stdout)
        fake_rom(self.rom, product=b"CTR-P-AFEE")
        self.assertIn("product code", self.run_play("--dry-run").stdout)
        fake_rom(self.rom, decrypted=False)
        self.assertIn("still encrypted", self.run_play("--dry-run").stdout)
        self.rom.write_bytes(b"\0" * 0x400)
        self.assertIn("no NCSD header", self.run_play("--dry-run").stdout)

    def test_full_hash_mismatch_stops_and_is_cached(self) -> None:
        self.make_dll()
        self.write_config(check_rom="full")
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 1)
        self.assertIn("SHA-256 is not the known clean", out.stdout)
        state = json.loads((self.play / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["rom_check"]["size"], self.rom.stat().st_size)
        out = self.run_play("--dry-run")
        self.assertNotIn("Checking your ROM", out.stdout)       # cached
        out = self.run_play("--dry-run", "--rehash")
        self.assertIn("Checking your ROM", out.stdout)

    def test_full_hash_mismatch_names_a_trimmed_size(self) -> None:
        self.make_dll()
        self.write_config(check_rom="full")
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 1)
        self.assertIn(f"{GAME.rom_size:,}", out.stdout)          # the synthetic file is a few KiB
        self.assertIn(GAME.rom_sha256, out.stdout)

    # -- this game's constants (config/game.json) ------------------------------------------

    def test_constants_come_from_game_json(self) -> None:
        m = load_play({ENV_PLAY: str(self.play)})
        self.assertEqual((m.TITLE_ID, m.PRODUCT_CODE, m.ROM_SIZE, m.ROM_SHA256),
                         (GAME.title_id_int, GAME.product_code, GAME.rom_size, GAME.rom_sha256))
        self.assertEqual(m.TITLE_HEX, "0004000000179800")
        self.assertEqual(m.STANDALONE_NAME, "Fire Emblem Fates.exe")
        self.assertEqual(m.SHORTCUT_NAME, "PLAY Fire Emblem Fates.lnk")
        self.assertEqual(m.EXTDATA_FALLBACK, 0x1794)
        self.assertEqual(m.DEFAULT_CONFIG["rom"], "")          # F-048: empty = roms/ (tools/paths.py)
        self.assertEqual(m.DEFAULT_CONFIG["zakuro_dir"], "")   # no machine-specific path by default
        self.assertEqual(m.PLAY_DIR, self.play)

    def test_first_run_config_has_no_machine_path(self) -> None:
        (self.play / "config.json").unlink()
        self.run_play("--where")
        config = json.loads((self.play / "config.json").read_text(encoding="utf-8"))
        self.assertEqual((config["rom"], config["zakuro_dir"]), ("", ""))   # F-048: roms/ is searched instead

    def test_extdata_falls_back_to_game_json_without_an_exheader_id(self) -> None:
        fake_rom(self.rom, exheader=False)
        data = self.appdata / "zakuro"
        self.make_save(data)
        ext = data / "user" / "extdata" / f"{0x1794:016X}"
        ext.mkdir(parents=True)
        (ext / "Global").write_bytes(b"ext")
        out = self.run_play("--backup")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        (backup,) = (self.play / "backups").glob("manual-*.zip")
        names = set(zipfile.ZipFile(backup).namelist())
        self.assertIn(f"extdata/{0x1794:016X}/Global", names)
        self.assertNotIn(f"extdata/{EXTDATA_TEST_ID:016X}/Cache", names)   # not this game's

    def test_update_cia_beside_the_rom_stops_dlc_is_a_note(self) -> None:
        self.make_dll()
        low = TITLE & 0xFFFFFFFF
        fake_cia(self.rom.parent / "Fates DLC.cia", (0x0004008C << 32) | low)
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("DLC beside the ROM", out.stdout)
        fake_cia(self.rom.parent / "Fates Update.cia", (0x0004000E << 32) | low, sig=0x10000)
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn(f"Fates Update.cia (title 0004000E{low:08X})", out.stdout)
        self.assertNotIn("Fates DLC.cia (", out.stdout)
        (self.rom.parent / "Fates Update.cia").write_bytes(b"not a cia")
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 1, out.stdout)       # unreadable: stop, to be safe
        self.assertIn("Fates Update.cia", out.stdout)
        self.assertEqual(self.run_play("--dry-run", "--anyway").returncode, 0)

    def test_cia_title_id_reader(self) -> None:
        m = load_play({ENV_PLAY: str(self.play)})
        for sig in (0x10000, 0x10001, 0x10002, 0x10003, 0x10004, 0x10005):
            path = Path(self.tmp.name) / f"t{sig:x}.cia"
            fake_cia(path, 0x0004000E00179800, sig=sig)
            self.assertEqual(m.cia_title_id(path), 0x0004000E00179800, hex(sig))
        path = Path(self.tmp.name) / "bad.cia"
        fake_cia(path, 1, sig=0x12345)
        self.assertIsNone(m.cia_title_id(path))
        path.write_bytes(b"")
        self.assertIsNone(m.cia_title_id(path))

    # -- portable saves -------------------------------------------------------------------

    def test_portable_adds_data_flag_and_guards_the_old_save(self) -> None:
        self.make_dll()
        self.make_save(self.appdata / "zakuro")
        self.assertEqual(self.run_play("--portable", "on").returncode, 0)
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 1)
        self.assertIn("--migrate-saves to-portable", out.stdout)
        out = self.run_play("--migrate-saves", "to-portable")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        portable = self.play / "data" / "user"
        self.assertEqual((portable / "savedata" / TID / "Global").read_bytes(), b"save")
        self.assertTrue((portable / "savedata" / f"{TID}.format").is_file())
        self.assertTrue((portable / "extdata" / f"{EXTDATA_TEST_ID:016X}" / "Cache").is_file())
        self.assertTrue((self.appdata / "zakuro" / "user" / "savedata" / TID / "Global").is_file(), "source kept")
        self.assertEqual(len(list((self.play / "backups").glob("premigrate-*.zip"))), 1)
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 0, out.stdout)
        command = out.stdout.strip().splitlines()[-1]
        self.assertIn(subprocess.list2cmdline(["--data", str(self.play / "data")]), command)

    def test_migrate_never_overwrites(self) -> None:
        self.make_save(self.appdata / "zakuro", b"old")
        self.make_save(self.play / "data", b"new")
        out = self.run_play("--migrate-saves", "to-portable")
        self.assertEqual(out.returncode, 1)
        self.assertIn("never overwritten", out.stdout)
        self.assertEqual((self.play / "data" / "user" / "savedata" / TID / "Global").read_bytes(), b"new")

    # -- backups and shortcut -------------------------------------------------------------

    def test_backup_zip_holds_the_save(self) -> None:
        self.make_save(self.appdata / "zakuro")
        out = self.run_play("--backup")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        (backup,) = (self.play / "backups").glob("manual-*.zip")
        names = set(zipfile.ZipFile(backup).namelist())
        self.assertIn(f"savedata/{TID}/Global", names)
        self.assertIn(f"savedata/{TID}.format", names)
        self.assertIn(f"extdata/{EXTDATA_TEST_ID:016X}/Cache", names)

    def test_backup_seal_without_the_seal_edition_says_so(self) -> None:
        """Round 84 (F-072): in a folder without tools/seal (the Vanilla+ edition), --backup-seal stops with a plain
        reason and writes nothing; seal_extras gives nothing, so the command never names the Seal edition."""
        self.make_seal_save()
        module = load_play({ENV_PLAY: str(self.play), "APPDATA": str(self.appdata)})
        module.seal_part = lambda: None
        with self.assertRaises(module.Stop) as stop:
            module.backup_seal()
        self.assertIn("not in this folder", str(stop.exception))
        self.assertEqual(module.seal_extras(), ([], None))
        self.assertFalse((self.play / "backups").exists())

    def test_zip_save_leaves_no_tmp_when_it_fails(self) -> None:
        """Round 73b review: a zip that fails half-way must not leave a .zip.tmp behind (backup_seal would then
        refuse to run until someone removed it)."""
        import types
        data = self.make_seal_save()
        module = load_play({ENV_PLAY: str(self.play), "APPDATA": str(self.appdata)})

        class Boom(zipfile.ZipFile):
            def write(self, *a, **k):
                super().write(*a, **k)
                raise OSError("disk full (made up)")
        module.zipfile = types.SimpleNamespace(ZipFile=Boom, ZIP_DEFLATED=zipfile.ZIP_DEFLATED)
        dest = self.play / "backups" / "manual-20990101-000000-seal.zip"
        with self.assertRaises(OSError):
            module.zip_save(data, module.EXTDATA_FALLBACK, dest)
        self.assertEqual(list((self.play / "backups").iterdir()), [], "no zip and no .zip.tmp left")

    def test_capture_never_starts_from_a_seal_backup(self) -> None:
        # (the Seal edition's half, sof.data_dir() == play.SEAL_DATA_DIR, is in tests/seal/test_play_seal.py)
        module = load_play({ENV_PLAY: str(self.play), "APPDATA": str(self.appdata)})
        b = self.play / "backups"
        b.mkdir()
        (b / "manual-20990101-000000-appdata.zip").write_bytes(b"a")
        seal = b / "manual-20990102-000000-seal.zip"
        seal.write_bytes(b"s")
        os.utime(seal, (4102444800, 4102444800))                  # the newest file
        self.assertEqual(module.find_capture_save({}, None)[1].name, "manual-20990101-000000-appdata.zip")

    def test_auto_backup_skips_unchanged_and_prunes(self) -> None:
        sys.path.insert(0, str(PLAY.parent))
        old = dict(os.environ)
        try:
            os.environ.update({"APPDATA": str(self.appdata), ENV_PLAY: str(self.play)})
            import importlib
            import play as module
            module = importlib.reload(module)
            data = self.appdata / "zakuro"
            self.make_save(data, b"1")
            config = dict(module.DEFAULT_CONFIG, keep_backups=2)
            state: dict = {}
            self.assertIn("Backed up", module.auto_backup(config, state, data, EXTDATA_TEST_ID))
            self.assertIn("unchanged", module.auto_backup(config, state, data, EXTDATA_TEST_ID))
            for i in range(3):  # three changed saves; only the newest keep_backups stay
                self.make_save(data, bytes([50 + i]))
                module.timestamp = lambda i=i: f"2099010{i}-000000"
                self.assertIn("Backed up", module.auto_backup(config, state, data, EXTDATA_TEST_ID))
            self.assertEqual(len(list((self.play / "backups").glob("auto-*.zip"))), 2)
        finally:
            os.environ.clear()
            os.environ.update(old)
            sys.path.remove(str(PLAY.parent))

    @unittest.skipUnless(os.name == "nt", "Windows shortcut")
    def test_shortcut_dry_run_creates_nothing(self) -> None:
        out = self.run_play("--make-shortcut", "--dry-run")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("[dry run] would create", out.stdout)
        self.assertIn("PLAY.bat", out.stdout)

    @unittest.skipUnless(os.name == "nt", "Windows batch file")
    def test_play_bat_passes_options_and_exit_code(self) -> None:
        self.make_dll()
        env = dict(os.environ, APPDATA=str(self.appdata), PLAY_NO_PAUSE="1",
                   **{ENV_PLAY: str(self.play), ENV_NOT_RUNNING: "1"})
        ok = subprocess.run(["cmd", "/c", str(ROOT / "PLAY.bat"), "--dry-run"], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("[dry run] would run", ok.stdout)
        bad = subprocess.run(["cmd", "/c", str(ROOT / "PLAY.bat"), "--nonsense"], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("was not started", bad.stdout)



# -- PLAY --capture and tools/harness/recapture.py (docs/HARNESS.md 4.2, 4.3; milestone H4b) ----------
# In-process, with fakes only: the freshness check, the launcher and boot.exe are replaced, so no
# game, no Zakuro and no 3dsrecomp ever runs. Every folder is a temporary one.

import contextlib  # noqa: E402
import hashlib  # noqa: E402
import importlib.util  # noqa: E402
import io  # noqa: E402
from unittest import mock  # noqa: E402

HARNESS = ROOT / "tools" / "harness"


def load_play(env: dict):
    """A private copy of play.py whose folders come from env (<prefix>_PLAY_DIR, <prefix>_HARNESS_DIR)."""
    with mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location("play_under_test", PLAY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def save_zip(path: Path, members: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, body in members.items():
            z.writestr(name, body)
    return path


GOOD_SAVE = {f"savedata/{TID}/Global": b"backup-save", f"savedata/{TID}.format": b"fmt",
             f"extdata/{EXTDATA_TEST_ID:016X}/Cache": b"ext"}


class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.appdata, self.play, self.harness = base / "AppData", base / "play", base / "build" / "harness"
        self.zakuro = base / "Zakuro (test)"
        self.zakuro.mkdir()
        (self.zakuro / "zakuro.exe").write_bytes(b"")
        self.rom = base / "games" / ROM_NAME
        self.rom.parent.mkdir()
        fake_rom(self.rom)
        self.play.mkdir()
        (self.play / "config.json").write_text(json.dumps(
            {"zakuro_dir": str(self.zakuro), "rom": str(self.rom), "check_rom": "header"}), encoding="utf-8")
        self.lib = self.harness / "lib" / f"{TID}.dll"
        self.lib.parent.mkdir(parents=True)
        self.lib.write_bytes(b"not a library")
        self.backup = save_zip(self.play / "backups" / "manual-20990101-000000-appdata.zip", GOOD_SAVE)
        env = {"APPDATA": str(self.appdata), ENV_PLAY: str(self.play), ENV_HARNESS: str(self.harness),
               ENV_NOT_RUNNING: "1", "ZAKURO_LOAD": "stray.bin", "FE_CAPTURE_ONLY": "0x1"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.m = load_play(env)
        self.m.check_fresh = lambda: (True, "harness-build: FRESH: test")
        self.launched: list = []
        self.m.launch = lambda cmd, cwd, env=None: self.launched.append((cmd, cwd, env))

    def capture(self, *args: str, stdin: str | None = None) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(sys, "stdin", io.StringIO(stdin or "")):
            try:
                rc = self.m.main(["--capture", *args])
            except self.m.Stop as stop:
                rc = f"STOP {stop}"
        return rc, out.getvalue()

    def sessions(self) -> list:
        folder = self.harness / "sessions"
        return sorted(folder.iterdir()) if folder.is_dir() else []

    def settings(self, text: str) -> None:
        path = self.appdata / "zakuro" / "settings.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_dry_run_prints_plan_and_checklist_and_makes_nothing(self) -> None:
        exe = self.play / "game" / STANDALONE   # a standalone program is never used here
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
        rc, out = self.capture("--dry-run", "--session", "s1")
        self.assertEqual(rc, 0, out)
        session = self.harness / "sessions" / "s1"
        self.assertIn(subprocess.list2cmdline([str(self.zakuro / "zakuro.exe"), str(self.rom), "--data",
                                               str(session / "data"), "--recompiled", str(self.lib),
                                               "--rasterizer", "hardware"]), out)
        self.assertNotIn(str(exe), out)
        self.assertIn(f"ZAKURO_RECORD={session / 'input.rec'}", out)
        self.assertIn("FE_READABLE=capture", out)
        self.assertIn("FE_CAPTURE_LIVE=a", out)
        self.assertIn("Attack Stance", out)
        self.assertIn("load a savestate", out)
        self.assertIn(str(self.backup), out)
        self.assertEqual(self.sessions(), [])
        self.assertEqual(self.launched, [])

    def test_stale_or_missing_library_refuses_even_with_anyway(self) -> None:
        self.m.check_fresh = lambda: (False, "harness-build: STALE: a staged file changed")
        rc, out = self.capture("--dry-run", "--anyway")
        self.assertTrue(str(rc).startswith("STOP") and "STALE" in str(rc), (rc, out))
        self.lib.unlink()
        rc, out = self.capture("--go", "--anyway")
        self.assertTrue(str(rc).startswith("STOP") and "no capture library" in str(rc), (rc, out))
        self.assertEqual((self.sessions(), self.launched), ([], []))

    def test_go_copies_the_backup_and_starts_with_the_capture_environment(self) -> None:
        self.settings(f'language = "english"\nnickname = ""\nconsole_id = 77\n[per_game.{TID}]\nlanguage = "german"\n'
                      f'[enhancements]\n"{TID}" = ["60 FPS"]\n')
        real = self.appdata / "zakuro" / "user" / "savedata" / TID
        real.mkdir(parents=True)
        (real / "Global").write_bytes(b"REAL SAVE, never read")
        rc, out = self.capture("--go", "--session", "s2", "--", "--mute")
        self.assertEqual(rc, 0, out)
        session = self.harness / "sessions" / "s2"
        self.assertEqual((session / "start-save.zip").read_bytes(), self.backup.read_bytes())
        self.assertEqual((session / "data" / "user" / "savedata" / TID / "Global").read_bytes(), b"backup-save")
        self.assertTrue((session / "data" / "user" / "extdata" / f"{EXTDATA_TEST_ID:016X}" / "Cache").is_file())
        self.assertTrue((session / "capture").is_dir())
        (cmd, cwd, env), = self.launched
        self.assertEqual(Path(cwd), session)
        self.assertEqual(cmd[-1], "--mute")
        self.assertEqual(env["ZAKURO_RECORD"], str(session / "input.rec"))
        self.assertEqual((env["FE_READABLE"], env["FE_CAPTURE_LIVE"]), ("capture", "a"))
        self.assertEqual(env["FE_CAPTURE_DIR"], str(session / "capture"))
        self.assertNotIn("ZAKURO_LOAD", env)
        self.assertNotIn("FE_CAPTURE_ONLY", env)
        meta = json.loads((session / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["settings"]["language_code"], 3)
        self.assertEqual(meta["settings"]["nickname"], "Player")
        self.assertEqual(meta["settings"]["enhancements"], ["60 FPS"])
        self.assertEqual(meta["settings"]["console_id"], 77)
        self.assertEqual(meta["start_save_sha256"], hashlib.sha256(self.backup.read_bytes()).hexdigest())
        self.assertEqual(meta["command"], cmd)

    def test_the_options_file_path_never_reaches_a_capture(self) -> None:
        """Options are off during capture (docs/OPTIONS_WIRING.md): neither FE_OPTIONS nor the game's
        own <prefix>_OPTIONS survives into the session, in any letter case; other prefixed settings do."""
        options_env = GAME.env("OPTIONS")
        self.assertEqual(self.m.OPTIONS_ENV, options_env)
        stray = {"FE_OPTIONS": "x.txt", options_env: "y.txt", options_env.lower(): "z.txt", ENV_PLAY: str(self.play)}
        env = self.m.capture_env(stray, self.harness / "sessions" / "s9", "a")
        for key in ("FE_OPTIONS", options_env, options_env.lower()):
            self.assertNotIn(key, env)
        self.assertEqual(env[ENV_PLAY], str(self.play))
        with mock.patch.dict(os.environ, {"FE_OPTIONS": "x.txt", options_env: "y.txt"}):
            rc, out = self.capture("--go", "--session", "s3")
        self.assertEqual(rc, 0, out)
        (_cmd, _cwd, launched_env), = self.launched
        self.assertNotIn("FE_OPTIONS", launched_env)
        self.assertNotIn(options_env, launched_env)
        self.assertEqual(launched_env["FE_READABLE"], "capture")

    def test_without_start_or_go_nothing_is_made(self) -> None:
        rc, out = self.capture(stdin="START\n")   # not a console: never asks, never starts
        self.assertEqual(rc, 1, out)
        self.assertIn("Not started", out)
        self.assertEqual((self.sessions(), self.launched), ([], []))

    def test_bad_zip_member_is_refused_and_nothing_is_written_outside(self) -> None:
        save_zip(self.play / "backups" / "zz-evil.zip", {f"savedata/{TID}/Global": b"x", "../../evil.txt": b"x"})
        rc, _ = self.capture("--go", "--capture-from", "zz-evil")
        self.assertTrue(str(rc).startswith("STOP") and "unexpected member" in str(rc), rc)
        save_zip(self.play / "backups" / "zz-other.zip", {f"savedata/{OTHER_TID}/Global": b"x"})
        rc, _ = self.capture("--go", "--capture-from", "zz-other.zip")
        self.assertTrue(str(rc).startswith("STOP"), rc)
        save_zip(self.play / "backups" / "zz-extra.zip", {f"savedata/{TID}/Global": b"x", "cheats/x.txt": b"x"})
        rc, _ = self.capture("--go", "--capture-from", "zz-extra")
        self.assertTrue(str(rc).startswith("STOP") and "cheats/x.txt" in str(rc), rc)   # saves only
        self.assertFalse((Path(self.tmp.name) / "evil.txt").exists())
        self.assertEqual((self.sessions(), self.launched), ([], []))

    def test_recompiled_off_unknown_language_and_cia_beside_rom_stop(self) -> None:
        self.settings(f'[per_game.{TID}]\nrecompiled = false\n')
        rc, _ = self.capture("--dry-run", "--anyway")
        self.assertTrue(str(rc).startswith("STOP") and "recompiled" in str(rc), rc)
        self.settings('language = "klingon"\n')
        rc, out = self.capture("--dry-run")
        self.assertEqual(rc, 1)
        self.assertIn("klingon", out)
        self.settings("")
        (self.rom.parent / "Fire Emblem Fates Update.CIA").write_bytes(b"")
        rc, out = self.capture("--dry-run")
        self.assertEqual(rc, 1)
        self.assertIn("Fire Emblem Fates Update.CIA", out)
        self.assertEqual(self.launched, [])

    def test_portable_save_is_zipped_by_plays_own_logic(self) -> None:
        folder = self.play / "data" / "user" / "savedata" / TID
        folder.mkdir(parents=True)
        (folder / "Global").write_bytes(b"portable-save")
        rc, out = self.capture("--go", "--session", "p1", "--capture-from", "portable")
        self.assertEqual(rc, 0, out)
        session = self.harness / "sessions" / "p1"
        self.assertIn(f"savedata/{TID}/Global", zipfile.ZipFile(session / "start-save.zip").namelist())
        self.assertEqual((session / "data" / "user" / "savedata" / TID / "Global").read_bytes(), b"portable-save")

    def test_session_names_args_and_options_are_checked(self) -> None:
        self.assertEqual(self.capture("--go", "--session", "again")[0], 0)
        rc, _ = self.capture("--go", "--session", "again")
        self.assertTrue(str(rc).startswith("STOP") and "never reused" in str(rc), rc)
        for bad in ("../up", ".hidden", "a b"):
            rc, _ = self.capture("--dry-run", "--session", bad)
            self.assertTrue(str(rc).startswith("STOP"), (bad, rc))
        rc, _ = self.capture("--dry-run", "--", "--interpreter")
        self.assertTrue(str(rc).startswith("STOP") and "--mute" in str(rc), rc)
        for argv in (["--go"], ["--live", "a"], ["--capture", "--live", "b"]):
            with self.assertRaises(self.m.Stop):
                self.m.parse_args(argv)
        self.assertEqual(len(self.launched), 1)


def fake_runner(calls: list, diverge_after: int | None = None, state: bool = True, nondeterministic: bool = False):
    """Stands in for boot.exe: checks what it is given, writes a log and an invented savestate (no
    game bytes) whose guest memory depends on the mode and the frame."""
    import headless as hl

    def leb(n: int) -> bytes:
        out = bytearray()
        while True:
            b, n = n & 0x7F, n >> 7
            out.append(b | (0x80 if n else 0))
            if not n:
                return bytes(out)

    def run(cmd, env, cwd, log_path, timeout):
        frames = int(cmd[2])
        at, path = env["ZAKURO_SAVE_AT"].split(":", 1)
        at, mode = int(at), env["FE_READABLE"]
        laid = Path(env["ZAKURO_DATA"]) / "user" / "savedata" / TID / "Global"
        calls.append({"mode": mode, "at": at, "frames": frames, "env": env, "laid": laid.is_file(),
                      "replay": os.path.isfile(env["ZAKURO_REPLAY"]), "cwd": cwd})
        Path(log_path).write_text(f"outcome: Completed after {frames} frames\ninstructions: 99\n", encoding="utf-8")
        if state:
            memory = [hashlib.sha256(f"section {k} frame {at}".encode()).digest() * 3 for k in range(4)]
            if diverge_after is not None and mode == "capture" and at > diverge_after:
                memory[1] = b"X" + memory[1][1:]
            if nondeterministic and mode == "original" and sum(c["mode"] == "original" for c in calls) == 2:
                memory[3] = b"Y" + memory[3][1:]
            own = (env["ZAKURO_DATA"] + "/user").encode()
            Path(path).write_bytes(hl.fake_state(b"\x05Mutex" + leb(len(own)) + own + b"\x02FS", memory))
        return 0
    return run


class RecaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        sys.path.insert(0, str(HARNESS))
        self.addCleanup(sys.path.remove, str(HARNESS))
        spec = importlib.util.spec_from_file_location("recapture_under_test", HARNESS / "recapture.py")
        self.r = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.r)
        base = Path(self.tmp.name)
        self.build = base / "build" / "harness"
        self.build.mkdir(parents=True)
        for attr, value in (("BACKUP_DIR", base / "play" / "backups"), ("HARNESS_SAVES", self.build / "saves")):
            patcher = mock.patch.object(self.r.play, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.boot, self.lib = base / "boot.exe", base / "lib.dll"
        self.boot.write_bytes(b"")
        self.lib.write_bytes(b"")
        self.kw = dict(rom=str(base / "game.cci"), boot=str(self.boot), lib=str(self.lib), build=str(self.build),
                       fresh=lambda: (True, "harness-build: FRESH: test"), say=lambda *_: None)

    def make_session(self, sid: str = "s1", settings: dict | None = None, rec: str | None = None) -> Path:
        folder = self.build / "sessions" / sid
        folder.mkdir(parents=True)
        save_zip(folder / "start-save.zip", GOOD_SAVE)
        (folder / "input.rec").write_text(rec or self.r.route_to_rec("100:A,200:START", 300, 7), encoding="utf-8")
        (folder / "session.json").write_text(json.dumps({"session": sid, "settings": settings or {}}), encoding="utf-8")
        return folder

    def test_route_input_becomes_a_recording_boot_reads_alike(self) -> None:
        text = self.r.route_to_rec("10:A,12:B,30:CUP+@100x50,40:BOGUS,50:A+@1y2", 60, 7)
        self.assertEqual(text.splitlines(), [
            "clock 7",
            "0 0 0.0 0.0 -1 -1 0.0 0.0 0.0 0.0",
            "10 1 0.0 0.0 -1 -1 0.0 0.0 0.0 0.0",
            "12 3 0.0 0.0 -1 -1 0.0 0.0 0.0 0.0",     # A held 10..15 and B from 12: OR'ed
            "16 2 0.0 0.0 -1 -1 0.0 0.0 0.0 0.0",
            "18 0 0.0 0.0 -1 -1 0.0 0.0 0.0 0.0",
            "30 40000000 0.0 1.0 100 50 0.0 0.0 0.0 0.0",   # circle up pushes the pad all the way
            "36 0 0.0 0.0 -1 -1 0.0 0.0 0.0 0.0",            # entries with unknown names are dropped
        ])
        rec = self.r.parse_rec(text)
        self.assertEqual((rec["clock"], rec["last_frame"], len(rec["changes"])), (7, 36, 7))
        self.assertEqual(self.r.parse_rec("clock 5\n2 1 0.0 0.0 -1 -1\n3 0 0.0 0.0 -1 -1 0.5 -0.5\n")["changes"], [2, 3])
        for bad in ("", "frame 1\n", "clock 1\n1 1 0.0\n", "clock 1\n1 zz 0.0 0.0 -1 -1\n",
                    "clock 1\n5 1 0 0 -1 -1\n4 0 0 0 -1 -1\n"):
            with self.assertRaises(self.r.Stop, msg=bad):
                self.r.parse_rec(bad)

    def test_same_states_give_same_and_leave_only_summaries(self) -> None:
        self.make_session(settings={"language_code": 1, "nickname": "Player", "enhancements": ["60 FPS"], "resolution": 3})
        calls: list = []
        with mock.patch.dict(os.environ, {"ZAKURO_INPUT": "1:A", "FE_CAPTURE_ONLY": "0x1"}):
            report = self.r.recapture("s1", runner=fake_runner(calls), **self.kw)
        self.assertEqual(report["verdict"], "SAME", report)
        self.assertEqual((report["frames"], report["save_at"]), (206 + self.r.TAIL, 206 + self.r.TAIL - 10))  # last change: START let go at 206
        self.assertEqual([c["mode"] for c in calls], ["original", "capture"])
        for c in calls:
            self.assertTrue(c["laid"] and c["replay"])
            self.assertNotIn("ZAKURO_INPUT", c["env"])
            self.assertNotIn("FE_CAPTURE_ONLY", c["env"])
            self.assertEqual((c["env"]["ZAKURO_RASTERIZER"], c["env"]["ZAKURO_LANGUAGE"], c["env"]["ZAKURO_NICK"],
                              c["env"]["ZAKURO_ENHANCE"], c["env"]["ZAKURO_RESOLUTION"]),
                             ("hardware", "1", "Player", "60 FPS", "3"))
        cap = calls[1]["env"]
        self.assertEqual((cap["FE_CAPTURE_LIVE"], cap["FE_CAPTURE_DIR"]), ("ab", str(self.build / "runs" / "s1-cap")))
        self.assertNotIn("FE_CAPTURE_DIR", calls[0]["env"])
        for name in ("s1-orig", "s1-cap"):
            self.assertTrue((self.build / "runs" / name / "run.json").is_file())
            meta = json.loads((self.build / "runs" / name / "run.json").read_text(encoding="utf-8"))
            self.assertEqual((meta["source"], meta["session_kind"]), ("replay", None))  # plain report counts it
            self.assertFalse((self.build / "tmp" / name).exists())
            self.assertFalse((self.build / "data" / name).exists())
        self.assertEqual(list(self.build.rglob("state.bin")), [])
        self.assertTrue((self.build / "recapture" / "s1.json").is_file())

    def test_diverged_gives_a_plan_and_bisect_finds_the_frame(self) -> None:
        self.make_session(rec=self.r.route_to_rec("100:A", 6000, 7))
        report = self.r.recapture("s1", save_at=5590, frames=5600, runner=fake_runner([], diverge_after=1234), **self.kw)
        self.assertEqual(report["verdict"], "DIVERGED")
        self.assertIn("guest memory DIFFERS (vram)", report["compare"])
        plan = report["bisection"]
        self.assertEqual((plan["lo"], plan["hi"], plan["first_probe"]), (0, 5590, 2795))
        self.assertIn("recapture.py bisect s1 --lo 0 --hi 5590", plan["auto"])
        calls: list = []
        found = self.r.bisect("s1", 5590, runner=fake_runner(calls, diverge_after=1234), **self.kw)
        self.assertEqual((found["verdict"], found["lo"], found["hi"]), ("BISECTED", 1234, 1235))
        self.assertLessEqual(len(found["probes"]), plan["probes_max"])
        self.assertTrue(all(c["frames"] == c["at"] + 1 for c in calls))

    def test_failed_nondeterministic_and_stale_library(self) -> None:
        self.make_session()
        self.assertEqual(self.r.recapture("s1", runner=fake_runner([], state=False), **self.kw)["verdict"], "FAILED")
        report = self.r.recapture("s1", determinism=True, runner=fake_runner([], nondeterministic=True), **self.kw)
        self.assertEqual(report["verdict"], "NOT-DETERMINISTIC")
        calls: list = []
        kw = dict(self.kw, fresh=lambda: (False, "harness-build: STALE: x"))
        with self.assertRaises(self.r.Stop):
            self.r.recapture("s1", runner=fake_runner(calls), **kw)
        self.assertEqual(calls, [])

    def test_folders_and_sessions_are_checked(self) -> None:
        for bad in ("../x", "", "a/b"):
            with self.assertRaises(self.r.Stop):
                self.r.load_session(bad, str(self.build))
        with self.assertRaises(self.r.Stop):
            self.r.load_session("missing", str(self.build))
        with self.assertRaises(self.r.Stop):
            self.r.replay_env({}, str(Path(self.tmp.name) / "outside"), str(self.build / "t"), str(self.build / "r"),
                              "original", "ab", "rec", "lib", "s", 10, str(self.build))
        folder = self.make_session("evil")
        save_zip(folder / "start-save.zip", {"../x": b"1"})
        with self.assertRaises(Exception):
            self.r.load_session("evil", str(self.build))

    def test_synth_session_from_a_route_run_and_expected_state(self) -> None:
        zip_path = save_zip(self.build / "saves" / "ch1.zip", GOOD_SAVE)
        run_dir = self.build / "runs" / "pu"
        run_dir.mkdir(parents=True)
        routes = {"pairup": {"frames": 400, "input": "100:A,200:B", "save_at": 390, "shots": []}}
        (run_dir / "run.json").write_text(json.dumps({"route": "pairup", "input": "100:A,200:B", "state_frame": 390,
                                                      "save_backup": str(zip_path)}), encoding="utf-8")
        meta = self.r.synth("pu", "syn", str(self.build), routes)
        folder = self.build / "sessions" / "syn"
        self.assertEqual((folder / "start-save.zip").read_bytes(), zip_path.read_bytes())
        self.assertEqual(self.r.parse_rec((folder / "input.rec").read_text(encoding="utf-8"))["changes"],
                         [0, 100, 106, 200, 206])
        self.assertEqual((meta["frames"], meta["save_at"], meta["expect_run"]), (400, 390, "pu"))
        with self.assertRaises(self.r.Stop):
            self.r.synth("pu", "syn", str(self.build), routes)   # never reused
        outside = save_zip(Path(self.tmp.name) / "elsewhere.zip", GOOD_SAVE)
        (run_dir / "run.json").write_text(json.dumps({"route": "pairup", "input": "1:A", "state_frame": 390,
                                                      "save_backup": str(outside)}), encoding="utf-8")
        with self.assertRaises(Exception):
            self.r.synth("pu", "syn2", str(self.build), routes)
        self.assertFalse((self.build / "sessions" / "syn2").exists())
        # the replay is compared with the run's own state digest
        (run_dir / "run.json").write_text(json.dumps({"state_frame": 390}), encoding="utf-8")
        report = self.r.recapture("syn", runner=fake_runner([]), expect_run="pu", **self.kw)
        self.assertEqual(report["verdict"], "SAME")
        self.assertEqual(report["expect_run"]["verdict"], "NOT-COMPARABLE")   # the fake run kept no state
        orig = json.loads((self.build / "runs" / "syn-orig" / "run.json").read_text(encoding="utf-8"))
        (run_dir / "run.json").write_text(json.dumps({"state_frame": 390, "state": orig["state"]}), encoding="utf-8")
        report = self.r.recapture("syn", runner=fake_runner([]), expect_run="pu", **self.kw)
        self.assertEqual(report["expect_run"]["verdict"], "SCRIPT-EQUIVALENT", report["expect_run"])
        changed = dict(orig["state"], memory="0" * 64, sections=dict(orig["state"]["sections"], fcram="0" * 64))
        (run_dir / "run.json").write_text(json.dumps({"state_frame": 390, "state": changed}), encoding="utf-8")
        report = self.r.recapture("syn", runner=fake_runner([]), expect_run="pu", **self.kw)
        self.assertEqual(report["expect_run"]["verdict"], "SCRIPT-DIFFERS")


class CaptureGateTests(unittest.TestCase):
    """The owner-facing gates of PLAY --capture with their real code (review findings 6-9)."""
    setUp, capture, sessions, settings = (CaptureTests.setUp, CaptureTests.capture, CaptureTests.sessions,
                                          CaptureTests.settings)

    def test_check_fresh_reads_build_py_verdict_and_exit_code(self) -> None:
        real = load_play({ENV_PLAY: str(self.play), ENV_HARNESS: str(self.harness)}).check_fresh
        cases = [
            ("harness-build: FRESH: library matches\n", "", 0, True),
            ("noise\nharness-build: FRESH: x\n", "", 0, True),
            ("harness-build: STALE: a staged file changed\n", "", 1, False),
            ("harness-build: STALE: x\n", "", 0, False),
            ("harness-build: FRESH: x\n", "", 1, False),       # FRESH but a failing exit code
            ("FRESH\n", "", 0, False),                          # no verdict line
            ("", "Traceback ...\n", 2, False),
            ("", "", 0, False),
        ]
        for out, err, rc, want in cases:
            done = subprocess.CompletedProcess([], rc, stdout=out, stderr=err)
            with mock.patch.object(subprocess, "run", return_value=done):
                self.assertEqual(real()[0], want, (out, err, rc))
        with mock.patch.object(subprocess, "run", side_effect=OSError("no python")):
            ok, line = real()
        self.assertFalse(ok)
        self.assertIn("could not run", line)
        with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 1)):
            self.assertFalse(real()[0])

    def test_console_start_prompt_needs_exactly_start(self) -> None:
        class Console(io.StringIO):
            def isatty(self) -> bool:
                return True
        for answer, want in (("START", True), ("start", True), ("  START  ", True), ("yes", False), ("y", False),
                             ("", False), ("STARTX", False), ("go", False)):
            with mock.patch.object(sys, "stdin", Console()), mock.patch("builtins.input", return_value=answer):
                self.assertEqual(self.m.confirm_start(), want, answer)
        with mock.patch.object(sys, "stdin", Console()), mock.patch("builtins.input", side_effect=EOFError):
            self.assertFalse(self.m.confirm_start())
        with mock.patch.object(sys, "stdin", io.StringIO("START\n")):     # not a console
            self.assertFalse(self.m.confirm_start())
        # the whole flow: a console answer other than START makes nothing
        with mock.patch.object(sys, "stdin", Console()), mock.patch("builtins.input", return_value="yes"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.m.main(["--capture", "--session", "c1"]), 1)
        self.assertEqual((self.sessions(), self.launched), ([], []))
        with mock.patch.object(sys, "stdin", Console()), mock.patch("builtins.input", return_value="START"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.m.main(["--capture", "--session", "c2"]), 0)
        self.assertEqual(len(self.launched), 1)

    def test_zakuro_running_and_rom_hash_mismatch_stop(self) -> None:
        self.m.zakuro_running = lambda: True
        rc, out = self.capture("--go", "--session", "r1")
        self.assertEqual(rc, 1, out)
        self.assertIn("already running", out)
        self.m.zakuro_running = lambda: False
        real_check = self.m.check_rom

        def mismatch(*a, **k):
            info = real_check(*a, **k)
            return dict(info, hash_mismatch=True)
        self.m.check_rom = mismatch
        rc, out = self.capture("--go", "--session", "r2")
        self.assertEqual(rc, 1, out)
        self.assertIn("SHA-256", out)
        self.assertEqual((self.sessions(), self.launched), ([], []))

    def test_zip_paths_that_pass_the_prefix_still_cannot_leave(self) -> None:
        for name in (f"savedata/{TID}/../../../evil", f"savedata/{TID}/a/../../../../evil",
                     f"extdata/{EXTDATA_TEST_ID:016X}/../../evil", f"savedata/{TID}\\..\\evil",
                     f"savedata/{TID}/C:evil", f"/savedata/{TID}/x"):
            path = save_zip(Path(self.tmp.name) / "z" / "bad.zip", {f"savedata/{TID}/Global": b"x", name: b"x"})
            with self.assertRaises(self.m.Stop, msg=name):
                self.m.check_save_zip(path)
        # the resolve check on its own, behind a check that let everything through
        path = save_zip(Path(self.tmp.name) / "z" / "raw.zip", {f"savedata/{TID}/../../../evil": b"x"})
        user = Path(self.tmp.name) / "z" / "deep" / "user"
        with mock.patch.object(self.m, "check_save_zip", lambda p, e=None: [f"savedata/{TID}/../../../evil"]):
            with self.assertRaises(self.m.Stop):
                self.m.extract_save_zip(path, user)
        self.assertFalse((Path(self.tmp.name) / "z" / "evil").exists())
        self.assertFalse((Path(self.tmp.name) / "evil").exists())

    def test_extdata_must_be_this_games(self) -> None:
        own = f"extdata/{EXTDATA_TEST_ID:016X}/Cache"
        other = "extdata/0000000000099999/Cache"
        good = save_zip(Path(self.tmp.name) / "z" / "own.zip", {f"savedata/{TID}/Global": b"x", own: b"x"})
        self.assertIn(own, self.m.check_save_zip(good, EXTDATA_TEST_ID))
        bad = save_zip(Path(self.tmp.name) / "z" / "other.zip", {f"savedata/{TID}/Global": b"x", other: b"x"})
        with self.assertRaises(self.m.Stop):
            self.m.check_save_zip(bad, EXTDATA_TEST_ID)
        self.m.check_save_zip(bad)   # without the id: any hex-named extdata folder
        junk = save_zip(Path(self.tmp.name) / "z" / "junk.zip", {f"savedata/{TID}/Global": b"x", "extdata/notes/x": b"x"})
        with self.assertRaises(self.m.Stop):
            self.m.check_save_zip(junk)
        save_zip(self.play / "backups" / "zz-other-ext.zip", {f"savedata/{TID}/Global": b"x", other: b"x"})
        rc, _ = self.capture("--go", "--capture-from", "zz-other-ext")
        self.assertTrue(str(rc).startswith("STOP") and other in str(rc), rc)
        self.assertEqual((self.sessions(), self.launched), ([], []))

    def test_session_folder_must_be_below_sessions(self) -> None:
        with self.assertRaises(self.m.Stop):
            self.m.prepare_session(Path(self.tmp.name) / "elsewhere", "backup", self.backup, EXTDATA_TEST_ID)
        with self.assertRaises(self.m.Stop):
            self.m.prepare_session(self.harness / "sessions" / ".." / "escaped", "backup", self.backup, None)
        self.assertFalse((Path(self.tmp.name) / "elsewhere").exists())
        self.assertFalse((self.harness / "escaped").exists())

    def test_3d_slider_and_screen_extras_are_kept(self) -> None:
        self.settings(f'stereo = "anaglyph"\ndepth_3d = 80\n[per_game.{TID}]\ndepth_3d = 40\nbattle_ui = "panels"\n')
        rc, out = self.capture("--go", "--session", "d3")
        self.assertEqual(rc, 0, out)
        self.assertIn("3D slider 0.4 (stereo anaglyph)", out)
        snap = json.loads((self.harness / "sessions" / "d3" / "session.json").read_text(encoding="utf-8"))["settings"]
        self.assertEqual((snap["stereo"], snap["depth_3d"], snap["slider_3d"]), ("anaglyph", 40, 0.4))
        self.assertEqual((snap["battle_ui"], snap["top_screen_extras"]), ("panels", True))
        self.settings('depth_3d = 70\n')     # stereo off: the slider is down whatever the depth
        snap = self.m.capture_settings(self.m.read_settings())
        self.assertEqual((snap["stereo"], snap["slider_3d"], snap["top_screen_extras"]), ("off", 0.0, False))


class RecaptureReviewTests(unittest.TestCase):
    """Environment, comparison, bisection and storage details of recapture.py (review findings 1, 3, 6, 10)."""
    setUp, make_session = RecaptureTests.setUp, RecaptureTests.make_session

    def test_capture_env_late_new3ds_dump_and_3d(self) -> None:
        self.make_session(settings={"slider_3d": 0.4})
        calls: list = []
        report = self.r.recapture("s1", runner=fake_runner(calls), **self.kw)
        self.assertEqual(report["verdict"], "SAME")
        orig, cap = calls[0]["env"], calls[1]["env"]
        self.assertEqual((cap["FE_CAPTURE_LATE"], cap["FE_READABLE"]), ("1", "capture"))
        self.assertNotIn("FE_CAPTURE_LATE", orig)
        for env in (orig, cap):
            self.assertNotIn("ZAKURO_NEW3DS", env)
            self.assertEqual(env["ZAKURO_DUMP_AT"], str(report["save_at"]))
            self.assertEqual(env["ZAKURO_3D"], "0.4")
        env = self.r.replay_env({"slider_3d": 0.0, "new3ds": False}, str(self.build / "d"), str(self.build / "t"),
                                str(self.build / "r"), "original", "ab", "rec", "lib", "s", 10, str(self.build))
        self.assertNotIn("ZAKURO_3D", env)
        self.assertNotIn("ZAKURO_NEW3DS", env)
        with self.assertRaises(self.r.Stop):
            self.r.replay_env({}, str(self.build / "d"), str(self.build / "t"), str(self.build / "r"),
                              "both", "ab", "rec", "lib", "s", 10, str(self.build))

    def test_compare_runs_uses_the_metadata_too(self) -> None:
        seen: list = []
        with mock.patch.object(self.r.hl, "compare_digests", lambda *a: seen.append(a) or (True, "same")):
            self.r.compare_runs({"state": "A", "_meta": "MA"}, {"state": "B", "_meta": "MB"})
        self.assertEqual(seen, [("A", "B", "MA", "MB")])

    def test_run_one_checks_save_at_before_running(self) -> None:
        self.make_session()
        session = self.r.load_session("s1", str(self.build))
        calls: list = []
        kw = {k: v for k, v in self.kw.items() if k != "fresh"}
        for save_at, frames in ((0, 100), (100, 100), (150, 100), (-1, 100)):
            with self.assertRaises(self.r.Stop, msg=(save_at, frames)):
                self.r.run_one(session, "x", "original", frames, save_at, runner=fake_runner(calls), **kw)
        self.assertEqual(calls, [])

    def test_bisect_reaches_a_one_frame_gap_for_every_divergence(self) -> None:
        self.make_session()
        for d in range(0, 20):
            found = self.r.bisect("s1", 20, runner=fake_runner([], diverge_after=d), **self.kw)
            self.assertEqual((found["verdict"], found["lo"], found["hi"]), ("BISECTED", d, d + 1), d)
        found = self.r.bisect("s1", 64, min_gap=8, runner=fake_runner([], diverge_after=37), **self.kw)
        self.assertLessEqual(found["hi"] - found["lo"], 8)
        self.assertTrue(found["lo"] <= 37 < found["hi"], found)

    def test_bisect_checks_endpoints_stops_on_failure_and_cleans_up(self) -> None:
        self.make_session()
        calls: list = []
        found = self.r.bisect("s1", 100, runner=fake_runner(calls, diverge_after=500), **self.kw)
        self.assertEqual(found["verdict"], "NO-DIVERGENCE-AT-HI")
        self.assertEqual(len(calls), 2)                       # only the hi probe ran
        found = self.r.bisect("s1", 100, lo=40, runner=fake_runner([], diverge_after=10), **self.kw)
        self.assertEqual(found["verdict"], "DIVERGED-BEFORE-LO")
        calls = []
        base = fake_runner(calls, diverge_after=30)

        def failing(cmd, env, cwd, log_path, timeout):
            rc = base(cmd, env, cwd, log_path, timeout)
            if calls[-1]["at"] == 50:                         # the first middle probe dies
                os.remove(env["ZAKURO_SAVE_AT"].split(":", 1)[1])
            return rc
        found = self.r.bisect("s1", 100, runner=failing, **self.kw)
        self.assertEqual(found["verdict"], "FAILED")
        self.assertEqual([c["at"] for c in calls], [100, 100, 50, 50])   # no probe after the failure
        for c in calls:
            self.assertNotIn("ZAKURO_DUMP_AT", c["env"])       # probes make no PPMs, no sheets
        self.assertEqual([p.name for p in (self.build / "runs").iterdir()] if (self.build / "runs").exists() else [], [])
        self.assertFalse((self.build / "shots").exists() and any((self.build / "shots").iterdir()))
        self.assertTrue((self.build / "recapture" / "s1-bisect.json").is_file())

    def test_expected_needs_the_same_frame(self) -> None:
        self.make_session()
        report = self.r.recapture("s1", runner=fake_runner([]), **self.kw)
        orig = json.loads((self.build / "runs" / "s1-orig" / "run.json").read_text(encoding="utf-8"))
        run_dir = self.build / "runs" / "pu"
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").write_text(json.dumps({"state_frame": report["save_at"] - 1, "state": orig["state"]}),
                                          encoding="utf-8")
        self.assertEqual(self.r.expected("pu", orig, report["save_at"], str(self.build))["verdict"], "NOT-COMPARABLE")
        (run_dir / "run.json").write_text(json.dumps({"state_frame": report["save_at"], "state": orig["state"]}),
                                          encoding="utf-8")
        self.assertEqual(self.r.expected("pu", orig, report["save_at"], str(self.build))["verdict"], "SCRIPT-EQUIVALENT")

    def test_the_first_held_touch_wins_as_in_boot(self) -> None:
        lines = self.r.route_to_rec("10:@1x2,12:@3x4", 30, 7).splitlines()
        self.assertEqual(lines[1:], [
            "0 0 0.0 0.0 -1 -1 0.0 0.0 0.0 0.0",
            "10 0 0.0 0.0 1 2 0.0 0.0 0.0 0.0",      # 12..15: both held, the first entry's touch
            "16 0 0.0 0.0 3 4 0.0 0.0 0.0 0.0",
            "18 0 0.0 0.0 -1 -1 0.0 0.0 0.0 0.0",
        ])

    def test_owner_session_saves_are_compared_with_the_replay(self) -> None:
        folder = self.make_session()
        report = self.r.recapture("s1", runner=fake_runner([]), **self.kw)
        self.assertEqual(report["session_fidelity"]["verdict"], "NOT-CHECKED")
        user = folder / "data" / "user"
        with zipfile.ZipFile(folder / "start-save.zip") as z:
            z.extractall(user)
        report = self.r.recapture("s1", runner=fake_runner([]), **self.kw)
        self.assertEqual(report["session_fidelity"]["verdict"], "SAVES-EQUAL", report["session_fidelity"])
        (user / "savedata" / TID / "Global").write_bytes(b"the owner saved in the game")
        report = self.r.recapture("s1", runner=fake_runner([]), **self.kw)
        fid = report["session_fidelity"]
        self.assertEqual((fid["verdict"], fid["differ"]), ("SAVES-DIFFER", [f"savedata/{TID}/Global"]))
        self.assertEqual(report["verdict"], "SAME")      # fidelity never changes the A/B verdict


# -- the PLAY .bat buttons catch every non-zero exit code (round 85, release plan section 4 item 1) ----------
# "if errorlevel 1" is false for a NEGATIVE code, e.g. -1073741515 when Python itself cannot start (a missing
# DLL), so the button said nothing and ended with 0. Every PLAY-style button now keeps the code in RC and compares
# it with 0, as RELEASE.bat does. The buttons are found by their "goto failed" line, so an edition's extra
# button is checked too when it is in this folder.

def play_buttons() -> list[Path]:
    found = []
    for folder in (ROOT, ROOT / "tools" / "play"):
        for bat in sorted(folder.glob("*.bat")):
            if b"goto failed" in bat.read_bytes():
                found.append(bat)
    return found


class BatExitCodeTests(unittest.TestCase):
    NEEDED = ("PLAY.bat", "PLAY RANDOMIZED.bat", "Make Desktop Shortcut.bat")

    def test_every_play_button_compares_the_code_with_zero(self) -> None:
        bats = play_buttons()
        names = [b.name for b in bats]
        for need in self.NEEDED:
            self.assertIn(need, names)
        for bat in bats:
            with self.subTest(bat=bat.name):
                data = bat.read_bytes()
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""), "not CRLF")
                self.assertNotIn(b"errorlevel 1", data.lower())
                lines = data.decode("ascii").split("\r\n")
                run = [i for i, ln in enumerate(lines) if ln.startswith("%PY% ")]
                self.assertEqual(len(run), 1, "one Python line")
                self.assertEqual(lines[run[0] + 1], 'set "RC=%ERRORLEVEL%"')
                self.assertEqual(lines[run[0] + 2], 'if not "%RC%"=="0" goto failed')
                failed = lines.index(":failed")
                self.assertTrue(any(ln.startswith("if %RC% LSS 0 echo Python stopped with a Windows error")
                                    for ln in lines[failed:failed + 3]))
                self.assertIn("exit /b 1", lines[failed:])

    @unittest.skipUnless(os.name == "nt", "Windows batch file")
    def test_a_negative_code_is_caught(self) -> None:
        # a copy of each button whose Python line is replaced by a process that only ends with the code;
        # nothing else starts (no Python, no game)
        env = dict(os.environ, PLAY_NO_PAUSE="1")
        with tempfile.TemporaryDirectory() as tmp:
            for bat in play_buttons():
                data = bat.read_bytes().decode("ascii").split("\r\n")
                for code, want in (("-1073741515", 1), ("9009", 1), ("0", 0)):
                    with self.subTest(bat=bat.name, code=code):
                        lines = ["cmd /c exit " + code if ln.startswith("%PY% ") else ln for ln in data]
                        copy = Path(tmp) / ("copy_" + bat.name.replace(" ", "_"))
                        copy.write_bytes("\r\n".join(lines).encode("ascii"))
                        out = subprocess.run(["cmd", "/c", str(copy)], capture_output=True, text=True, env=env,
                                             timeout=60)
                        self.assertEqual(out.returncode, want, out.stdout + out.stderr)
                        self.assertEqual("Python stopped with a Windows error" in out.stdout, code.startswith("-"))


if __name__ == "__main__":
    unittest.main()
