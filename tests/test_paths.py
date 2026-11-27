"""tools/paths.py (F-048): roms/ first, the old root place for one release, plain refusals.
(The Seal edition's zip finder cases: tests/seal/test_paths_seal.py, round 84.)

Synthetic files only (a 1.5 KiB fake cartridge header, small zips); everything under build/f48/test_paths/.
    python -m unittest tests.test_paths -v
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
import paths  # noqa: E402
from gamecfg import GAME  # noqa: E402
from tests.test_play import fake_rom, fake_cia, OTHER_TITLE, load_play, ENV_PLAY  # noqa: E402

TEST_ROOT = ROOT / "build" / "f48" / "test_paths"
TID = GAME.title_id


def game_for(rom: Path) -> SimpleNamespace:
    """config/game.json's facts, with size and SHA-256 of the synthetic ROM (so a 'clean' fake exists)."""
    data = rom.read_bytes()
    return SimpleNamespace(game=GAME.game, edition=GAME.edition, title_id=GAME.title_id,
                           title_id_int=GAME.title_id_int, default_rom=GAME.default_rom,
                           rom_size=len(data), rom_sha256=hashlib.sha256(data).hexdigest())


class RomTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        self.repo = Path(self.tmp.name)
        self.roms = self.repo / "roms"
        self.roms.mkdir()
        (self.roms / "README.txt").write_text("note\n", encoding="utf-8")
        self.cache = self.repo / "build" / "rom_check.json"
        self.saved_env = os.environ.pop("FE_ROM", None)

    def tearDown(self) -> None:
        if self.saved_env is not None:
            os.environ["FE_ROM"] = self.saved_env
        self.tmp.cleanup()

    def put_rom(self, folder: Path, name: str = GAME.default_rom, **kw) -> Path:
        path = folder / name
        fake_rom(path, **kw)
        return path

    def test_rom_in_roms_is_found_and_hash_checked(self) -> None:
        rom = self.put_rom(self.roms)
        notes: list[str] = []
        self.assertEqual(paths.find_rom(repo=self.repo, notes=notes, game=game_for(rom)), rom)
        self.assertEqual(notes, [])
        self.assertTrue(self.cache.is_file())                  # the hash is remembered under build/
        self.assertEqual(paths.find_rom(repo=self.repo, notes=notes, game=game_for(rom)), rom)

    def test_any_cci_name_in_roms(self) -> None:
        rom = self.put_rom(self.roms, "my dump.cci")
        self.assertEqual(paths.find_rom(repo=self.repo, game=game_for(rom)), rom)

    def test_roms_wins_over_the_old_root_place(self) -> None:
        rom = self.put_rom(self.roms)
        self.put_rom(self.repo)
        notes: list[str] = []
        self.assertEqual(paths.find_rom(repo=self.repo, notes=notes, game=game_for(rom)), rom)
        self.assertEqual(notes, [])

    def test_old_root_place_found_with_a_note(self) -> None:
        rom = self.put_rom(self.repo)
        notes: list[str] = []
        self.assertEqual(paths.find_rom(repo=self.repo, notes=notes, game=game_for(rom)), rom)
        self.assertEqual(notes, [paths.MOVE_NOTE_ROM])
        self.assertIn("please move it to roms", notes[0])

    def test_no_roms_folder_still_finds_the_old_place(self) -> None:
        (self.roms / "README.txt").unlink()
        self.roms.rmdir()
        rom = self.put_rom(self.repo)
        self.assertEqual(paths.find_rom(repo=self.repo, notes=[], game=game_for(rom)), rom)

    def test_update_cia_is_refused_in_one_sentence(self) -> None:
        rom = self.put_rom(self.roms)
        fake_cia(self.roms / "update.cia", 0x0004000E00179800)
        with self.assertRaises(paths.PathError) as cm:
            paths.find_rom(repo=self.repo, game=game_for(rom))
        msg = str(cm.exception)
        self.assertIn("update.cia", msg)
        self.assertIn("update", msg)
        self.assertEqual(msg.count("\n"), 0)
        self.assertTrue(msg.endswith("."))

    def test_wrong_edition_is_refused(self) -> None:
        rom = self.put_rom(self.roms, title=OTHER_TITLE)
        with self.assertRaises(paths.PathError) as cm:
            paths.find_rom(repo=self.repo, game=game_for(rom))
        self.assertIn("different game or edition", str(cm.exception))
        self.assertNotIn("\n", str(cm.exception))

    def test_wrong_hash_is_refused(self) -> None:
        rom = self.put_rom(self.roms)
        good = game_for(rom)
        rom.write_bytes(rom.read_bytes()[:-1] + b"\x01")       # same size, same header, other bytes
        with self.assertRaises(paths.PathError) as cm:
            paths.find_rom(repo=self.repo, game=good)
        self.assertIn("SHA-256 differs", str(cm.exception))
        self.assertNotIn("\n", str(cm.exception))
        # the header-only check (PLAY's check_rom does its own hash with --anyway) accepts it
        self.assertEqual(paths.find_rom(repo=self.repo, check="header", game=good), rom)

    def test_wrong_size_is_refused_without_hashing(self) -> None:
        rom = self.put_rom(self.roms)
        good = game_for(rom)
        with rom.open("ab") as f:
            f.write(b"\0" * 16)
        with self.assertRaises(paths.PathError):
            paths.find_rom(repo=self.repo, game=good, cache=None)

    def test_two_game_files_are_refused(self) -> None:
        rom = self.put_rom(self.roms)
        self.put_rom(self.roms, "second.3ds")
        with self.assertRaises(paths.PathError) as cm:
            paths.find_rom(repo=self.repo, game=game_for(rom))
        self.assertIn("keep only", str(cm.exception))

    def test_nothing_found_says_where_to_put_it(self) -> None:
        with self.assertRaises(paths.PathError) as cm:
            paths.find_rom(repo=self.repo)
        self.assertIn("roms", str(cm.exception))

    def test_resolve_order(self) -> None:
        rom = self.put_rom(self.roms)
        other = self.put_rom(self.repo, "elsewhere.cci")
        g = game_for(rom)
        self.assertEqual(paths.resolve_rom(other, repo=self.repo, game=g), other)          # explicit
        os.environ["FE_ROM"] = str(other)
        try:
            self.assertEqual(paths.resolve_rom(repo=self.repo, game=g), other)            # FE_ROM
        finally:
            del os.environ["FE_ROM"]
        (self.repo / "play").mkdir()
        cfg = self.repo / "play" / "config.json"
        cfg.write_text(json.dumps({"rom": str(other), "zakuro_dir": "Z:\\keep"}), encoding="utf-8")
        self.assertEqual(paths.resolve_rom(repo=self.repo, game=g), other)                # config, file there
        before = cfg.read_bytes()
        cfg.write_text(json.dumps({"rom": str(self.repo / "moved away.cci"), "zakuro_dir": "Z:\\keep"}),
                       encoding="utf-8")
        before = cfg.read_bytes()
        notes: list[str] = []
        self.assertEqual(paths.resolve_rom(repo=self.repo, game=g, notes=notes), rom)     # moved: roms/
        self.assertTrue(any("not there" in n for n in notes))
        self.assertEqual(cfg.read_bytes(), before)                                        # config never edited
        self.assertIsNone(paths.try_resolve_rom(repo=self.repo / "nowhere", use_env=False))


class PlayLauncherTests(unittest.TestCase):
    """play.py: an owner's play/config.json whose "rom" is gone (moved to roms/) still works; Zakuro kept."""

    def test_config_rom_moved_falls_back_to_roms(self) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEST_ROOT) as td:
            repo = Path(td)
            (repo / "roms").mkdir()
            rom = repo / "roms" / GAME.default_rom
            fake_rom(rom)
            play_dir = repo / "play"
            play_dir.mkdir()
            cfg = {"rom": str(repo / GAME.default_rom), "zakuro_dir": "Z:\\Emu\\Zakuro", "check_rom": "header"}
            (play_dir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
            before = (play_dir / "config.json").read_bytes()
            m = load_play({ENV_PLAY: str(play_dir)})
            m.ROM_REPO = repo
            config, _ = m.load_config()
            notes: list[str] = []
            with redirect_stdout(io.StringIO()):
                info = m.check_rom(config, {}, False, notes)
            self.assertEqual(Path(config["rom"]), rom)
            self.assertEqual(config["zakuro_dir"], "Z:\\Emu\\Zakuro")
            self.assertIn("extdata_id", info)
            self.assertTrue(any("not there" in n for n in notes))
            self.assertEqual((play_dir / "config.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
