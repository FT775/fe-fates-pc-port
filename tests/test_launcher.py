"""Self-tests for PLAY's Getting ready window (tools/play/launcher.py, round 77, docs/LAUNCHER_PLAN.md section 6).

    python -m unittest tests.test_launcher          (from the repo root)

T1-T13 of the plan. Everything runs in a fresh folder under build/launcher77/ (never %TEMP%): a synthetic
cartridge header (tests/test_play.py fake_rom: identifiers only, no game bytes) with a test copy of
config/game.json whose rom_size and rom_sha256 are the fake file's (FE_GAME_CONFIG), so the full check passes on
it (the Seal edition's row and zip cases: tests/seal/test_launcher_seal.py, round 84); a fake
APPDATA, LOCALAPPDATA and USERPROFILE (Downloads, Desktop, Documents); an empty standalone program that is never
started (the start is recorded by replacing play.launch, or --dry-run is used).
Safety: no test opens a window (FEF_LAUNCHER_NO_WINDOW=1 everywhere, and the Windows Open window's PowerShell
command is only built, or handed to a fake runner, never run), starts the game, Zakuro, a build or anything from
the network, or reads the real game file. Every answer comes through a pipe (stdin never inherited).
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
PLAY = ROOT / "tools" / "play" / "play.py"
TOOLS_PLAY = ROOT / "tools" / "play"
sys.path.insert(0, str(ROOT))
from tests.test_play import fake_rom, fake_cia, TID, STANDALONE, ENV_PLAY, ENV_NOT_RUNNING  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
from gamecfg import GAME  # noqa: E402
sys.path.insert(0, str(TOOLS_PLAY))
import launcher as L  # noqa: E402  (the module under test; pure functions only in-process)

TEST_ROOT = ROOT / "build" / "launcher77"
OTHER_TITLE = 0x00040000000A0500
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def snapshot(top: Path, skip: tuple[Path, ...] = ()) -> dict:
    """name -> (size, mtime_ns, sha256) of every file below top (folders as 'dir'), skipping the given trees."""
    out = {}
    if top.exists():
        for p in sorted(top.rglob("*")):
            if any(p == s or s in p.parents for s in skip):
                continue
            rel = p.relative_to(top).as_posix()
            if p.is_file():
                st = p.stat()
                out[rel] = (st.st_size, st.st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
            else:
                out[rel] = "dir"
    return out


class Base(unittest.TestCase):
    def setUp(self) -> None:
        TEST_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=TEST_ROOT)
        b = self.base = Path(self.tmp.name)
        self.appdata, self.localappdata, self.home = b / "AppData", b / "LocalAppData", b / "home"
        self.play, self.build, self.roms = b / "play", b / "build", b / "roms"
        for d in (self.home / "Downloads", self.home / "Desktop", self.home / "Documents", self.roms):
            d.mkdir(parents=True)
        normal = self.appdata / "zakuro"                       # a stranger's own Zakuro: never written
        (normal / "user" / "savedata" / TID).mkdir(parents=True)
        (normal / "user" / "savedata" / TID / "Global").write_bytes(b"normal save")
        (normal / "settings.toml").write_text("resolution = 4\n", encoding="utf-8")
        self.localappdata.mkdir()
        (self.localappdata / "keep.txt").write_text("local", encoding="utf-8")
        self.source = b / "rom-source.cci"                    # the synthetic game file, copied where a test wants it
        fake_rom(self.source)
        data = self.source.read_bytes()
        cfg = json.loads((ROOT / "config" / "game.json").read_text(encoding="utf-8"))
        cfg["rom_size"], cfg["rom_sha256"] = len(data), hashlib.sha256(data).hexdigest()
        self.game_json = b / "game.json"
        self.game_json.write_text(json.dumps(cfg), encoding="utf-8")
        self.rec = b / "launch.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # -- helpers

    def rom_at(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.source, path)
        return path

    def program(self) -> Path:
        exe = self.play / "game" / STANDALONE
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"test program, never started")
        (exe.parent / "build-record.json").write_text(json.dumps(
            {"sha256": hashlib.sha256(exe.read_bytes()).hexdigest()}), encoding="utf-8")
        return exe

    def env(self, launcher: bool = True, **more) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("FEF_", "ZAKURO_", "FE_"))}
        env.update({"APPDATA": str(self.appdata), "LOCALAPPDATA": str(self.localappdata),
                    "USERPROFILE": str(self.home), "HOME": str(self.home), ENV_PLAY: str(self.play),
                    ENV_NOT_RUNNING: "1", GAME.env("ROM_REPO"): str(self.base), GAME.env("SOF_BUILD"): str(self.build),
                    GAME.env("EXTRACTED"): str(self.base / "extracted"), GAME.env("LAUNCHER_NO_WINDOW"): "1",
                    "FE_GAME_CONFIG": str(self.game_json), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        if launcher:
            env[GAME.env("LAUNCHER")] = "1"
        env.update(more)
        return env

    def run_play(self, *args: str, answers: str = "", launcher: bool = True, **more) -> subprocess.CompletedProcess:
        """play.py as PLAY.bat runs it (FEF_LAUNCHER=1), the answers through a pipe."""
        return subprocess.run([sys.executable, "-I", "-X", "utf8", str(PLAY), *args], input=answers, capture_output=True, text=True,
                              encoding="utf-8", env=self.env(launcher, **more), timeout=120, creationflags=NO_WINDOW)

    def run_main(self, *args: str, answers: str = "", launcher: bool = True) -> tuple[subprocess.CompletedProcess, dict | None]:
        """play.main with play.launch replaced by a recorder: nothing is ever started."""
        code = ("import sys, json; sys.path.insert(0, %r); import play\n"
                "def rec(cmd, cwd, env=None):\n"
                "    json.dump({'cmd': cmd, 'cwd': str(cwd), 'env': None if env is None else dict(env)},"
                " open(%r, 'w', encoding='utf-8'))\n"
                "play.launch = rec\n"
                "try:\n    sys.exit(play.main(%r))\n"
                "except play.Stop as e:\n    print('STOP: ' + str(e)); sys.exit(1)\n"
                % (str(TOOLS_PLAY), str(self.rec), list(args)))
        out = subprocess.run([sys.executable, "-I", "-X", "utf8", "-c", code], input=answers, capture_output=True, text=True,
                             encoding="utf-8", env=self.env(launcher), timeout=120, creationflags=NO_WINDOW)
        data = json.loads(self.rec.read_text(encoding="utf-8")) if self.rec.is_file() else None
        self.rec.unlink(missing_ok=True)
        return out, data

    def launcher_json(self) -> dict | None:
        p = self.play / "launcher.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def config(self, **over) -> Path:
        self.play.mkdir(parents=True, exist_ok=True)
        cfg = {"rom": "", "check_rom": "full", "zakuro_dir": ""}
        cfg.update(over)
        p = self.play / "config.json"
        p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        return p

    def load_play(self, **over):
        """A private copy of play.py whose folders are this test's (in-process; gamecfg is the real one)."""
        env = {ENV_PLAY: str(self.play), GAME.env("ROM_REPO"): str(self.base), "APPDATA": str(self.appdata)}
        env.update(over)
        with mock.patch.dict(os.environ, env):
            spec = importlib.util.spec_from_file_location("play_for_launcher_test", PLAY)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        module.ROM_SIZE = self.source.stat().st_size            # the synthetic file is "the clean dump" here
        module.ROM_SHA256 = hashlib.sha256(self.source.read_bytes()).hexdigest()
        return module


class LauncherTests(Base):
    # T1 ---------------------------------------------------------------------------------------------------
    def test_t01_file_in_roms_no_questions(self) -> None:
        rom = self.rom_at(self.roms / "Fire Emblem Fates.cci")
        self.program()
        out = self.run_play("--dry-run")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("Getting ready", out.stdout)
        self.assertNotIn(L.WORDS["ask"], out.stdout)
        self.assertIn("[dry run] would run", out.stdout)
        self.assertIn(f'"{rom}"', out.stdout)
        self.assertIsNone(self.launcher_json(), "launcher.json was written")

    # T2 ---------------------------------------------------------------------------------------------------
    def test_t02_no_file_typed_path_is_remembered_and_used(self) -> None:
        rom = self.rom_at(self.base / "elsewhere" / "fates.cci")
        self.program()
        out = self.run_play("--dry-run", answers=f"3\n{rom}\ns\n\n")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("Getting ready", out.stdout)
        self.assertIn(L.WORDS["accepted"], out.stdout)
        self.assertEqual(self.launcher_json()["rom"], str(rom))
        again = self.run_play("--dry-run", launcher=False)          # the next PLAY, even without the window
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn(f'"{rom}"', again.stdout)
        self.assertNotIn("Getting ready", again.stdout)
        cfg = json.loads((self.play / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["rom"], "")                             # F-048: config.json never gets the path

    # T3 ---------------------------------------------------------------------------------------------------
    def test_t03_dragged_path_quotes_spaces_and_letters(self) -> None:
        rom = self.rom_at(self.base / "Mes jeux \u00e9t\u00e9 \u00fc \u30b2\u30fc\u30e0" / "Fire Emblem (my copy).cci")
        self.assertEqual(L.normalize_path(f'  "{rom}"  '), str(rom))
        self.assertEqual(L.normalize_path(f"& '{rom}'"), str(rom))
        self.assertEqual(L.normalize_path(f"'{rom}'\r"), str(rom))
        self.assertEqual(L.normalize_path(str(rom)), str(rom))
        self.assertIsNone(L.normalize_path('  ""  '))
        self.assertEqual(L.normalize_path("file:///D:/My%20Games/x%C3%A9.cci"), "D:/My Games/xé.cci")
        self.program()
        for answers in (f'"{rom}"\ns\n\n', f'3\n   "{rom}"   \ns\n\n'):     # dragged on the question, and after 3
            (self.play / "launcher.json").unlink(missing_ok=True)
            out = self.run_play("--dry-run", answers=answers)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertEqual(self.launcher_json()["rom"], str(rom))

    # T4 ---------------------------------------------------------------------------------------------------
    def test_t04_wrong_files_one_sentence_each_nothing_written(self) -> None:
        play = self.load_play()
        g = {"game": play.GAME, "edition": play.EDITION}
        d = self.base / "wrong"
        d.mkdir()
        update = self.base / "update only" / "update.cia"            # alone in its folder
        update.parent.mkdir()
        fake_cia(update, 0x0004000E00179800)
        other = d / "other.cci"
        fake_rom(other, title=OTHER_TITLE)
        enc = d / "encrypted.cci"
        fake_rom(enc, decrypted=False)
        trimmed = d / "trimmed.cci"
        trimmed.write_bytes(self.source.read_bytes() + b"\0" * 16)
        changed = d / "changed.cci"
        changed.write_bytes(self.source.read_bytes()[:-1] + b"\x01")
        notcci = d / "notes.cci"
        notcci.write_bytes(b"x" * 0x400)
        side = self.base / "with-update" / "fates.cci"
        self.rom_at(side)
        fake_cia(side.parent / "update.cia", 0x0004000E00179800)
        want = {
            update: L.WORDS["bad_update"],
            other: L.WORDS["bad_title"].format(title=f"{OTHER_TITLE:016X}", **g),
            enc: L.WORDS["bad_encrypted"],
            trimmed: L.WORDS["bad_trimmed"].format(size=trimmed.stat().st_size, want=play.ROM_SIZE),
            changed: L.WORDS["bad_hash"],
            notcci: L.WORDS["bad_not_cci"],
            d: L.WORDS["bad_folder"].format(path=d),
            d / "missing.cci": L.WORDS["bad_missing"].format(path=d / "missing.cci"),
            side: L.WORDS["bad_cia"].format(names=f"update.cia (title {0x0004000E00179800:016X})"),
        }
        for path, sentence in want.items():
            ok, got, entry = L.check_game_file(path, play, state={}, out=lambda *_a, **_k: None)
            self.assertFalse(ok, path)
            self.assertEqual(got, sentence, path)
            self.assertEqual(entry, {})
            self.assertNotIn(". ", got, f"one sentence: {got}")
        ok, got, entry = L.check_game_file(self.source, play, state={}, out=lambda *_a, **_k: None)
        self.assertTrue(ok, got)
        self.assertEqual(entry["sha256"], play.ROM_SHA256)
        # through the window: every wrong file answered, nothing remembered, nothing started
        self.program()
        answers = "".join(f"3\n{p}\n" for p in (update, other, enc, trimmed, changed, d, d / "missing.cci")) + "q\n"
        out = self.run_play("--dry-run", answers=answers)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        for path in (update, other, enc, trimmed, changed, d, d / "missing.cci"):
            self.assertIn(want[path], out.stdout)
        self.assertIn(L.WORDS["quit_done"], out.stdout)
        self.assertIsNone(self.launcher_json())
        self.assertFalse((self.play / "state.json").exists(), "a wrong file's fingerprint was cached")

    # T5 ---------------------------------------------------------------------------------------------------
    def test_t05_look_for_it_caps_and_reads_headers_only_of_the_right_size(self) -> None:
        size = self.source.stat().st_size
        dl = self.home / "Downloads"
        right = self.rom_at(dl / "a" / "b" / "fates.cci")                 # 2 folders deep: found
        deep = self.rom_at(dl / "a" / "b" / "c" / "d" / "fates deep.cci")  # 4 folders deep: beyond the cap
        three = self.rom_at(self.home / "Desktop" / "x" / "y" / "z" / "copy.3ds")   # 3 deep: found
        wrong_title = dl / "other game.cci"
        fake_rom(wrong_title, title=OTHER_TITLE)                           # same size, other title: opened, refused
        wrong_size = dl / "fates (trimmed).cci"
        wrong_size.write_bytes(self.source.read_bytes() + b"\0")           # wrong size: never opened
        (dl / "notes.txt").write_text("x" * size, encoding="utf-8")        # the right size but not a game: opened, refused
        opened = []

        def spy(path, mode="r"):
            opened.append(Path(path))
            return open(path, mode)
        with mock.patch.dict(os.environ, {"USERPROFILE": str(self.home)}):      # never the real Downloads
            roots = L.search_roots(self.base)
        self.assertEqual(roots, [self.roms, dl, self.home / "Desktop", self.home / "Documents"])
        found, timed_out = L.look_for(roots, size=size, title=GAME.title_id_int, opener=spy)
        self.assertFalse(timed_out)
        self.assertEqual(sorted(found), sorted([right, three]))
        self.assertNotIn(deep, found)
        self.assertNotIn(wrong_size, opened)
        self.assertTrue(all(p.stat().st_size == size for p in opened), opened)
        self.assertEqual(sorted(opened), sorted([right, three, wrong_title, dl / "notes.txt"]))
        # the time cap, on a fake clock that moves one second per look
        ticks = iter(range(10_000))
        found, timed_out = L.look_for(roots, size=size, title=GAME.title_id_int, seconds=3, clock=lambda: next(ticks))
        self.assertTrue(timed_out)
        self.assertEqual(L.SEARCH_DEPTH, 3)
        self.assertEqual(L.SEARCH_SECONDS, 30.0)
        # through the window: 1 finds the one right file
        shutil.rmtree(self.home / "Desktop" / "x")
        self.program()
        out = self.run_play("--dry-run", answers="1\ns\n\n")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.launcher_json()["rom"], str(right))

    # T14 (round 84, F-072) -----------------------------------------------------------------------------------
    def test_t14_without_the_seal_edition_no_row_no_question_no_sof(self) -> None:
        """The Vanilla+ window: with no Seal part (no tools/seal) there is no Seal row, no S / P question and no P
        key, and sof is never imported. (The Vanilla+ folder proof runs the same window with tools/seal absent.)"""
        self.rom_at(self.roms / "fates.cci")
        self.program()
        self.config()
        play = self.load_play()
        printed: list[str] = []
        answers = iter(["p", ""])
        with mock.patch.object(L, "SEAL", None), mock.patch.dict(sys.modules, {"sof": None}):
            w = L.Window(play, {"check_rom": "full"}, setup=True, dry_run=True, input_fn=lambda p: next(answers, None),
                         out=printed.append, which=lambda n: None)
            self.assertEqual(w.run(), 0)
            status = w.show()
        text = chr(10).join(printed)
        self.assertIsNone(status["seal"])
        for marker in ("Seal", "Laz14", "656034", "sof"):
            self.assertNotIn(marker, text)
        self.assertIn(L.WORDS["ready_change"], printed)
        self.assertIn(L.WORDS["bad_key"], printed)                      # P means nothing here
        self.assertEqual(L.load_seal_part() is None, not (ROOT / "tools" / "seal" / "launcher_seal.py").is_file())

    # T7 ---------------------------------------------------------------------------------------------------
    def test_t07_writes_only_inside_play(self) -> None:
        rom = self.rom_at(self.home / "Downloads" / "fates.cci")
        self.program()
        before = snapshot(self.base, skip=(self.play, self.build))
        out, rec = self.run_main(answers=f"3\n{rom}\ns\n\n")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIsNotNone(rec, "the start was not recorded")
        self.assertEqual(snapshot(self.base, skip=(self.play, self.build)), before,
                         "something outside play\\ (and build\\) changed")
        self.assertTrue(any(k.startswith("AppData/") for k in before) and any(k.startswith("LocalAppData/") for k in before))
        self.assertTrue((self.play / "launcher.json").is_file())

    # T8 ---------------------------------------------------------------------------------------------------
    def test_t08_a_folder_like_yours_stays_silent_and_byte_for_byte(self) -> None:
        self.rom_at(self.roms / "Fire Emblem Fates.cci")
        self.program()
        cfg = self.config()
        cfg_bytes = cfg.read_bytes()
        first_plain = self.run_play("--dry-run", launcher=False)       # hashes once, as today
        second_plain = self.run_play("--dry-run", launcher=False)      # from the cache
        with_launcher = self.run_play("--dry-run")
        self.assertEqual(with_launcher.returncode, 0, with_launcher.stdout + with_launcher.stderr)
        self.assertEqual(with_launcher.stdout, second_plain.stdout)
        (self.play / "state.json").unlink()
        first_launcher = self.run_play("--dry-run")
        self.assertEqual(first_launcher.stdout, first_plain.stdout)
        self.assertIn("Checking your ROM once", first_launcher.stdout)
        out, rec = self.run_main()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIsNone(rec["env"], "the start got another environment")
        self.assertNotIn("Getting ready", out.stdout + with_launcher.stdout)
        self.assertEqual(cfg.read_bytes(), cfg_bytes)
        self.assertIsNone(self.launcher_json())
        self.assertFalse((self.play / "appdata").exists())
        self.assertNotIn("portable folder", with_launcher.stdout)

    # T9 ---------------------------------------------------------------------------------------------------
    def test_t09_fresh_folder_is_portable_and_copies_nothing(self) -> None:
        self.rom_at(self.roms / "fates.cci")
        self.program()                                                    # play\game only: still a fresh folder
        before = snapshot(self.appdata)
        dry = self.run_play("--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stdout + dry.stderr)
        self.assertIn(f"APPDATA={self.play / 'appdata'}", dry.stdout)
        out, rec = self.run_main()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        env = rec["env"]
        self.assertEqual(env["APPDATA"], str(self.play / "appdata"))
        self.assertEqual(env["LOCALAPPDATA"], str(self.play / "localappdata"))
        self.assertEqual(env["TEMP"], str(self.play / "temp"))
        self.assertEqual(env["TMP"], str(self.play / "temp"))
        self.assertIn("Nothing was copied", out.stdout)
        self.assertIn("PLAY.bat --migrate-saves to-portable", out.stdout)
        self.assertEqual(out.stdout.count("Nothing was copied"), 1)
        self.assertFalse((self.play / "appdata" / "zakuro").exists(), "a save was copied")
        self.assertEqual(snapshot(self.appdata), before)
        self.assertIn(str(self.play / "appdata" / "zakuro"), out.stdout)   # the saves the program will use

    def test_t09b_a_folder_that_had_config_keeps_todays_places(self) -> None:
        self.rom_at(self.roms / "fates.cci")
        self.program()
        (self.play / "state.json").write_text("{}", encoding="utf-8")    # PLAY ran here before
        out, rec = self.run_main()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIsNone(rec["env"])
        self.assertFalse((self.play / "appdata").exists())

    # T10 --------------------------------------------------------------------------------------------------
    def test_t10_windows_open_window_command_and_typing_fallback(self) -> None:
        exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        cmd = L.open_window_command("Choose your Fire Emblem Fates game file (it's .cci)", which=lambda n: exe if n == "powershell" else None)
        self.assertEqual(cmd[:7], [exe, "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass", "-Command"])
        script = cmd[7]
        for part in ("System.Windows.Forms", "OpenFileDialog", "ShowDialog", "TopMost", "UTF8", "*.cci;*.3ds",
                     "$d.Title='Choose your Fire Emblem Fates game file (it''s .cci)'"):
            self.assertIn(part, script)
        self.assertIsNone(L.open_window_command("x", which=lambda n: None))
        play = self.load_play()
        rom = self.rom_at(self.base / "picked" / "fates.cci")
        calls = []

        def fake_runner(c, **kw):
            calls.append(c)
            return subprocess.CompletedProcess(c, 0, stdout=str(rom).encode("utf-8"), stderr=b"")
        printed = []
        env_no_switch = {k: v for k, v in os.environ.items() if k != GAME.env("LAUNCHER_NO_WINDOW")}
        with mock.patch.dict(os.environ, env_no_switch, clear=True):
            w = L.Window(play, {"check_rom": "full"}, setup=True, dry_run=True, input_fn=lambda p: None,
                         out=printed.append, runner=fake_runner, which=lambda n: exe if n == "powershell" else None)
            w.find("2")
        self.assertEqual(calls, [L.open_window_command(L.WORDS["window_title"].format(game=GAME.game),
                                                       which=lambda n: exe)])
        self.assertEqual(self.launcher_json()["rom"], str(rom))
        # no PowerShell: the window falls back to typing; the runner is never called
        (self.play / "launcher.json").unlink()
        typed, calls2 = iter([str(rom)]), []
        w = L.Window(play, {"check_rom": "full"}, setup=True, dry_run=True, input_fn=lambda p: next(typed, None),
                     out=printed.append, runner=lambda *a, **k: calls2.append(a), which=lambda n: None)
        w.find("2")
        self.assertEqual(calls2, [])
        self.assertIn(L.WORDS["window_none"], printed)
        self.assertEqual(self.launcher_json()["rom"], str(rom))
        # the Zakuro question: "2" opens the same window (no PowerShell here: typing instead; the Seal edition's zip
        # question is checked in tests/seal/test_launcher_seal.py)
        typed = iter(["2", f'"{rom}"'])
        w = L.Window(play, {"check_rom": "full"}, setup=True, dry_run=True, input_fn=lambda p: next(typed, None),
                     out=printed.append, runner=lambda *a, **k: calls2.append(a), which=lambda n: None)
        self.assertEqual(w.ask_path("ask_folder", "window_title_zakuro"), str(rom))
        self.assertEqual(calls2, [])

    # T11 --------------------------------------------------------------------------------------------------
    def test_t11_missing_program_explains_and_never_builds(self) -> None:
        self.rom_at(self.roms / "fates.cci")
        play = self.load_play()
        zak = self.base / "Zakuro 0.2"
        zak.mkdir()
        (zak / "zakuro.exe").write_bytes(b"")
        empty = self.base / "not zakuro"
        empty.mkdir()
        answers = iter(["", "y", "y", "z", str(empty), "z", f'"{zak / "zakuro.exe"}"', "s", ""])
        calls, printed = [], []
        w = L.Window(play, {"check_rom": "full"}, setup=False, dry_run=False, input_fn=lambda p: next(answers, None),
                     out=printed.append, runner=lambda c, **k: calls.append(c), which=lambda n: None)
        self.assertEqual(w.run(), 0)
        text = "\n".join(printed)
        for key in ("prog_text", "prog_z", "prog_cmd", "prog_time", "prog_y"):
            self.assertIn(L.WORDS[key], text)
        self.assertEqual(calls, [[sys.executable, str(ROOT / "tools" / "engine" / "engine.py"), "port", "--dry-run"]])
        self.assertIn(L.WORDS["prog_bad_folder"].format(path=empty), text)
        self.assertEqual(self.launcher_json()["zakuro_dir"], str(zak))
        self.assertIn(L.WORDS["bad_key"], text)                          # the second y: asked once only
        # through PLAY: quit without pressing Y runs nothing and starts nothing
        out = self.run_play("--dry-run", answers="q\n")
        self.assertNotIn("Getting ready", out.stdout)                   # the Zakuro folder above is remembered
        self.assertIn(str(zak / "zakuro.exe"), out.stdout)
        (self.play / "launcher.json").unlink()
        out = self.run_play("--dry-run", answers="q\n")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn(L.WORDS["prog_text"], out.stdout)
        self.assertNotIn("[dry run] nothing built", out.stdout)

    # T12 --------------------------------------------------------------------------------------------------
    @unittest.skipUnless(os.name == "nt", "Windows batch file")
    def test_t12_play_bat_exit_codes(self) -> None:
        self.rom_at(self.roms / "fates.cci")
        self.program()
        # PLAY.bat sets FEF_LAUNCHER itself. The real LOCALAPPDATA stays: the Microsoft Store Python that "py -3" may
        # start cannot run without it (play.py never writes there; T7 checks that with a fake one).
        env = self.env(launcher=False, PLAY_NO_PAUSE="1", LOCALAPPDATA=os.environ.get("LOCALAPPDATA", ""))
        ready = subprocess.run(["cmd", "/c", str(ROOT / "PLAY.bat"), "--setup", "--dry-run"], input="s\n\n",
                               capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
                               creationflags=NO_WINDOW)
        self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
        self.assertIn("Getting ready", ready.stdout)
        self.assertIn("[dry run] would run", ready.stdout)
        for p in self.roms.iterdir():
            p.unlink()
        quit_ = subprocess.run(["cmd", "/c", str(ROOT / "PLAY.bat"), "--dry-run"], input="q\n", capture_output=True,
                               text=True, encoding="utf-8", env=env, timeout=120, creationflags=NO_WINDOW)
        self.assertEqual(quit_.returncode, 1, quit_.stdout + quit_.stderr)
        self.assertIn(L.WORDS["quit_done"], quit_.stdout)
        self.assertIn("was not started", quit_.stdout)

    # T13 --------------------------------------------------------------------------------------------------
    def test_t13_release_package_holds_no_play_file(self) -> None:
        rc = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "play/launcher.json"],
                            capture_output=True, creationflags=NO_WINDOW).returncode
        self.assertEqual(rc, 0, "play/launcher.json is not git-ignored in this repository")
        from tests import test_package as TP
        PK = TP.PK

        class Pkg(TP.PackageTestBase):
            def runTest(self):  # noqa: N802
                pass
        case = Pkg()
        with mock.patch.object(tempfile, "tempdir", str(self.base)):
            case.setUp()
        try:
            case.commit({".gitignore": "/play/\n", "tools/play/launcher.py": "print('launcher')\n"}, "launcher")
            case.write({"play/launcher.json": json.dumps({"rom": TP.FAKE_HOME + r"\Downloads\fates.cci"}),
                        "play/config.json": "{}"})
            res = case.build()
            self.assertTrue(res["ok"], [(g["name"], g["detail"]) for g in res["gates"] if not g["ok"]])
            self.assertTrue(case.gate(res, "archive")["ok"])
            with zipfile.ZipFile(res["zip"]) as z:
                names = z.namelist()
            self.assertIn("FE-Fates-port-r1/tools/play/launcher.py", names)
            self.assertEqual([n for n in names if n.split("/", 1)[-1].startswith("play/")], [])
            self.assertEqual([n for n in names if n.endswith("launcher.json")], [])
            self.assertNotIn("archive", [g["name"] for g in res["gates"] if not g["ok"]])
            self.assertIn("archive", PK.GATES)
        finally:
            case.tearDown()


class ReviewFixTests(Base):
    """Round 77's review findings (1)-(6)."""

    # (1) ---------------------------------------------------------------------------------------------------
    def lay_out(self, case: str) -> dict:
        """One 'right game, not usable as is' file; returns the play/config.json overrides it needs."""
        for p in list(self.roms.iterdir()):
            p.unlink()
        if case == "changed":
            (self.roms / "fates.cci").write_bytes(self.source.read_bytes()[:-1] + b"\x01")
            return {}
        if case == "trimmed":
            (self.roms / "fates.cci").write_bytes(self.source.read_bytes() + b"\0" * 16)
            return {}
        side = self.base / "with-update" / "fates.cci"
        if not side.is_file():
            self.rom_at(side)
            fake_cia(side.parent / "update.cia", 0x0004000E00179800)
        return {"rom": str(side)}

    def test_r1_right_game_not_usable_prints_the_old_stop_not_the_window(self) -> None:
        self.program()
        for case in ("changed", "trimmed", "cia"):
            with self.subTest(case=case):
                self.config(**self.lay_out(case))
                (self.play / "state.json").unlink(missing_ok=True)
                plain = self.run_play("--dry-run", launcher=False)            # as at HEAD 5300858
                (self.play / "state.json").unlink(missing_ok=True)
                bat = self.run_play("--dry-run", answers="q\n")               # as PLAY.bat runs it
                self.assertEqual(bat.returncode, 1, bat.stdout + bat.stderr)
                self.assertEqual(bat.stdout, plain.stdout)
                self.assertNotIn("Getting ready", bat.stdout)
                self.assertNotIn(L.WORDS["quit_done"], bat.stdout)
                self.assertIn("\nSTOP: ", bat.stdout)
                self.assertIn("PLAY.bat --anyway", bat.stdout)
                if case == "cia":
                    self.assertIn("These .cia files lie beside the ROM", bat.stdout)
                    self.assertIn("Move them to another folder", bat.stdout)
                else:
                    self.assertIn("The ROM's SHA-256 is not the known clean", bat.stdout)
                    self.assertIn('set "check_rom": "header" in\n  play\\config.json', bat.stdout)
                    self.assertIn("Use your clean dump", bat.stdout)
                anyway = self.run_play("--dry-run", "--anyway", answers="q\n")
                self.assertEqual(anyway.returncode, 0, anyway.stdout + anyway.stderr)
                self.assertNotIn("Getting ready", anyway.stdout)
                self.assertIn("Going on anyway (--anyway)", anyway.stdout)
                self.assertIn("[dry run] would run", anyway.stdout)
        self.assertIsNone(self.launcher_json())

    def test_r1b_the_window_shows_the_same_way_out(self) -> None:
        self.program()
        for case, key in (("changed", "way_out_rom"), ("trimmed", "way_out_rom"), ("cia", "way_out_cia")):
            with self.subTest(case=case):
                over = self.lay_out(case)
                play = self.load_play()
                printed = []
                w = L.Window(play, {"check_rom": "full", **over}, setup=True, dry_run=True, input_fn=lambda p: "q",
                             out=printed.append, runner=lambda *a, **k: self.fail("ran something"), which=lambda n: None)
                self.assertEqual(w.run(), 1)
                text = "\n".join(printed)
                self.assertIn(L.WORDS[key], text)
                self.assertIn("PLAY.bat --anyway", text)
                if key == "way_out_rom":
                    self.assertIn('"check_rom": "header" in play\\config.json', text)
                self.assertLess(text.index(L.WORDS["game_bad"]), text.index(L.WORDS[key]))
        # a typed wrong file is not given the way out (it is not the file PLAY would use)
        for p in list(self.roms.iterdir()):
            p.unlink()
        play = self.load_play()
        typed = self.base / "typed" / "changed.cci"
        typed.parent.mkdir()
        typed.write_bytes(self.source.read_bytes()[:-1] + b"\x01")
        answers, printed = iter(["3", str(typed), "q"]), []
        w = L.Window(play, {"check_rom": "full"}, setup=False, dry_run=True, input_fn=lambda p: next(answers, None),
                     out=printed.append, which=lambda n: None)
        self.assertEqual(w.run(), 1)
        self.assertIn(L.WORDS["bad_hash"], printed)
        self.assertNotIn(L.WORDS["way_out_rom"], printed)

    @unittest.skipUnless(os.name == "nt", "Windows batch file")
    def test_r1c_play_bat_prints_the_old_stop_and_anyway_skips_the_window(self) -> None:
        self.program()
        self.config(**self.lay_out("changed"))
        env = self.env(launcher=False, PLAY_NO_PAUSE="1", LOCALAPPDATA=os.environ.get("LOCALAPPDATA", ""))
        stop = subprocess.run(["cmd", "/c", str(ROOT / "PLAY.bat"), "--dry-run"], input="q\n", capture_output=True,
                              text=True, encoding="utf-8", env=env, timeout=120, creationflags=NO_WINDOW)
        self.assertEqual(stop.returncode, 1, stop.stdout + stop.stderr)
        self.assertNotIn("Getting ready", stop.stdout)
        self.assertIn("STOP: The ROM's SHA-256 is not the known clean", stop.stdout)
        self.assertIn('set "check_rom": "header" in', stop.stdout)
        self.assertIn("start it once with PLAY.bat --anyway", stop.stdout)
        self.assertIn("was not started", stop.stdout)
        anyway = subprocess.run(["cmd", "/c", str(ROOT / "PLAY.bat"), "--anyway", "--dry-run"], input="q\n",
                                capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
                                creationflags=NO_WINDOW)
        self.assertEqual(anyway.returncode, 0, anyway.stdout + anyway.stderr)
        self.assertNotIn("Getting ready", anyway.stdout)
        self.assertIn("Going on anyway (--anyway)", anyway.stdout)

    # (2) ---------------------------------------------------------------------------------------------------
    def test_r2_engine_finds_the_file_the_window_accepted(self) -> None:
        import paths as P  # noqa: PLC0415  (tools/ is on sys.path above)
        repo = self.base / "fake-repo"
        (repo / "roms").mkdir(parents=True)
        (repo / "play").mkdir()
        in_roms = self.rom_at(repo / "roms" / "fates.cci")
        accepted = self.rom_at(self.base / "my games" / "fates.cci")
        given = self.rom_at(self.base / "given" / "fates.cci")
        configured = self.rom_at(self.base / "configured" / "fates.cci")
        lj, cfg = repo / "play" / "launcher.json", repo / "play" / "config.json"

        def resolve(arg=None, **kw):
            return P.resolve_rom(arg, repo=repo, check="header", use_env=False, **kw)
        self.assertEqual(resolve(), in_roms)                                        # nothing chosen: roms\
        lj.write_text(json.dumps({"rom": str(accepted)}), encoding="utf-8")
        self.assertEqual(resolve(), accepted)                                       # launcher.json before roms\
        self.assertEqual(resolve(str(given)), given)                                # --rom first
        cfg.write_text(json.dumps({"rom": str(configured)}), encoding="utf-8")
        self.assertEqual(resolve(), configured)                                     # config.json before launcher.json
        cfg.write_text(json.dumps({"rom": str(self.base / "gone.cci")}), encoding="utf-8")
        notes: list[str] = []
        self.assertEqual(resolve(notes=notes), accepted)                            # config's file gone: launcher.json
        self.assertTrue(any("launcher.json" in n for n in notes), notes)
        lj.write_text(json.dumps({"rom": str(self.base / "moved.cci")}), encoding="utf-8")
        self.assertEqual(resolve(notes=[]), in_roms)                                # launcher's file gone: roms\
        lj.write_text(json.dumps({"rom": str(accepted)}), encoding="utf-8")
        self.assertEqual(resolve(use_config=False), in_roms)                        # check_all's roms-only look
        # engine.py port and port --dry-run take it through rom_path (called directly: nothing is built)
        spec = importlib.util.spec_from_file_location("engine_for_launcher_test", ROOT / "tools" / "engine" / "engine.py")
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        cfg.unlink()
        with mock.patch.object(engine, "REPO", repo), mock.patch.dict(os.environ, {"FE_ROM": str(given)}):
            self.assertEqual(engine.rom_path(None), accepted)                       # FE_ROM is not engine's
            self.assertEqual(engine.rom_path(str(given)), given)
            cfg.write_text(json.dumps({"rom": str(configured)}), encoding="utf-8")
            self.assertEqual(engine.rom_path(None), configured)

    # (3) ---------------------------------------------------------------------------------------------------
    def run_rando(self, seed: str) -> tuple[subprocess.CompletedProcess, dict | None]:
        code = ("import sys, json; sys.path.insert(0, %r); import rando\n"
                "def rec(cmd, cwd, env=None):\n"
                "    json.dump({'env': None if env is None else dict(env)}, open(%r, 'w', encoding='utf-8'))\n"
                "rando.play.launch = rec\n"
                "try:\n    sys.exit(rando.main(['new', '--seed', %r]))\n"
                "except rando.Stop as e:\n    print('STOP: ' + str(e)); sys.exit(1)\n"
                % (str(TOOLS_PLAY), str(self.rec), seed))
        env = self.env(False, **{GAME.env("RANDOMIZER_DIR"): str(self.base / "no-rando")})
        out = subprocess.run([sys.executable, "-I", "-X", "utf8", "-c", code], capture_output=True, text=True,
                             encoding="utf-8", env=env, timeout=120, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        data = json.loads(self.rec.read_text(encoding="utf-8")) if self.rec.is_file() else None
        self.rec.unlink(missing_ok=True)
        return out, data

    def test_r3_play_randomized_gets_the_portable_places(self) -> None:
        self.rom_at(self.roms / "fates.cci")
        self.program()
        (self.play / "appdata").mkdir(parents=True)                          # a portable folder (PLAY made it)
        out, rec = self.run_rando("PORT77")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        env = rec["env"]
        self.assertEqual(env["APPDATA"], str(self.play / "appdata"))
        self.assertEqual(env["LOCALAPPDATA"], str(self.play / "localappdata"))
        self.assertEqual(env["TEMP"], str(self.play / "temp"))
        self.assertEqual(env["TMP"], str(self.play / "temp"))
        self.assertEqual(env["ZAKURO_DATA"], str(self.play / "randomizer" / "PORT77" / "data"))
        for name in ("localappdata", "temp"):                                 # made before the start (review)
            self.assertTrue((self.play / name).is_dir(), name)
        shutil.rmtree(self.play / "appdata")                                 # not a portable folder: today's places
        out, rec = self.run_rando("NORM77")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        env = rec["env"]
        self.assertEqual(env["APPDATA"], str(self.appdata))
        self.assertEqual(env["LOCALAPPDATA"], str(self.localappdata))
        self.assertEqual(env["ZAKURO_DATA"], str(self.play / "randomizer" / "NORM77" / "data"))
        self.assertFalse((self.play / "appdata").exists())

    # (4) ---------------------------------------------------------------------------------------------------
    @unittest.skipUnless(os.name == "nt", "Windows junctions")
    def test_r4_junctions_are_skipped_also_without_is_junction(self) -> None:
        import _winapi  # noqa: PLC0415
        size = self.source.stat().st_size
        target = self.base / "outside"
        rom = self.rom_at(target / "fates.cci")
        root = self.base / "root"
        root.mkdir()
        link = root / "joined"
        _winapi.CreateJunction(str(target), str(link))
        try:
            self.assertEqual(L.look_for([target], size=size, title=GAME.title_id_int)[0], [rom])   # it is findable
            self.assertEqual(L.look_for([root], size=size, title=GAME.title_id_int), ([], False))
            real = os.scandir

            class Hidden:                                                    # a DirEntry as Python 3.11 has it
                def __init__(self, entry):
                    self._entry = entry

                def __getattr__(self, name):
                    if name == "is_junction":
                        raise AttributeError(name)
                    return getattr(self._entry, name)

            class Scan:
                def __init__(self, path):
                    self._it = real(path)

                def __enter__(self):
                    return (Hidden(e) for e in self._it.__enter__())

                def __exit__(self, *exc):
                    return self._it.__exit__(*exc)
            seen = []
            with real(root) as it:
                for e in it:
                    h = Hidden(e)
                    seen.append((h.is_dir(follow_symlinks=False), h.is_symlink(), hasattr(h, "is_junction")))
            self.assertEqual(seen, [(True, False, False)])                  # only the attribute bit can tell
            with mock.patch.object(L.os, "scandir", Scan):
                self.assertEqual(L.look_for([root], size=size, title=GAME.title_id_int), ([], False))
        finally:
            os.rmdir(link)                                                   # the junction only; target stays
        self.assertTrue(rom.is_file())

    # (6) ---------------------------------------------------------------------------------------------------
    def test_r6_cloud_placeholders_are_never_opened(self) -> None:
        size = self.source.stat().st_size
        root = self.base / "cloud"

        class FakeStat:
            def __init__(self, attrs):
                self.st_size, self.st_file_attributes = size, attrs

        class FakeEntry:
            def __init__(self, name, attrs):
                self.name, self.path, self._attrs = name, str(root / name), attrs

            def is_symlink(self):
                return False

            def is_junction(self):
                return False

            def is_dir(self, follow_symlinks=True):
                return False

            def is_file(self, follow_symlinks=True):
                return True

            def stat(self, follow_symlinks=True):
                return FakeStat(self._attrs)
        entries = [FakeEntry("local.cci", 0x20), FakeEntry("offline.cci", L.FILE_ATTRIBUTE_OFFLINE | 0x20),
                   FakeEntry("recall-open.cci", L.FILE_ATTRIBUTE_RECALL_ON_OPEN),
                   FakeEntry("recall-data.cci", L.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | 0x20),
                   FakeEntry("reparse.cci", L.FILE_ATTRIBUTE_REPARSE_POINT)]

        @contextlib.contextmanager
        def fake_scandir(path):
            self.assertEqual(Path(path), root)
            yield iter(entries)
        opened = []

        def spy(path, mode="r"):
            opened.append(Path(path).name)
            return open(self.source, mode)                                   # a right header, for the local one
        with mock.patch.object(L.os, "scandir", fake_scandir):
            found, timed_out = L.look_for([root], size=size, title=GAME.title_id_int, opener=spy)
        self.assertFalse(timed_out)
        self.assertEqual(found, [root / "local.cci"])
        self.assertEqual(opened, ["local.cci"])
        self.assertEqual(L.PLACEHOLDER_ATTRIBUTES, 0x1000 | 0x40000 | 0x400000)


class Round85Tests(Base):
    """Release plan section 4 items 2 and 3 (round 85): the Zakuro row never ticks before the game was recompiled,
    and the Y answer never prints a raw STOP line. In-process with fakes: nothing is built or started."""

    def zakuro(self) -> Path:
        zak = self.base / "Zakuro"
        zak.mkdir(exist_ok=True)
        (zak / "zakuro.exe").write_bytes(b"test zakuro, never started")
        return zak

    def window_text(self, play, config: dict, answers: list[str], runner=None) -> tuple[str, list]:
        it, printed, calls = iter(answers), [], []

        def fake_runner(cmd, **kw):
            calls.append((cmd, kw))
            return runner(cmd, **kw) if runner else None
        w = L.Window(play, config, setup=True, dry_run=True, input_fn=lambda p: next(it, None),
                     out=printed.append, runner=fake_runner, which=lambda n: None)
        with mock.patch.dict(os.environ, {"APPDATA": str(self.appdata)}):     # the test's own Zakuro places
            w.run()
        return "\n".join(str(x) for x in printed), calls

    def test_zakuro_row_waits_for_the_recompiled_game(self) -> None:
        self.rom_at(self.roms / "fates.cci")
        play = self.load_play()
        zak = self.zakuro()
        config = {"check_rom": "full", "zakuro_dir": str(zak)}
        text, calls = self.window_text(play, config, ["q"])
        row = [ln for ln in text.splitlines() if L.WORDS["row_program"] in ln]
        self.assertEqual(len(row), 1, text)
        self.assertTrue(row[0].strip().startswith("[!]"), row[0])
        self.assertIn(L.WORDS["program_zakuro_not_recompiled"].format(path=zak), row[0])
        self.assertIn(L.WORDS["zakuro_recompile"].format(game=play.GAME), text)
        self.assertEqual(calls, [])
        # Zakuro has recompiled it (the library file PLAY looks for): a tick and no extra line
        dll = self.appdata / "3dsrecomp" / f"{TID}.dll"
        dll.parent.mkdir(parents=True)
        dll.write_bytes(b"test library")
        text, _ = self.window_text(play, config, ["q"])
        row = [ln for ln in text.splitlines() if L.WORDS["row_program"] in ln]
        self.assertTrue(row[0].strip().startswith("[x]"), row[0])
        self.assertIn(L.WORDS["program_zakuro"].format(path=zak), row[0])
        self.assertNotIn(L.WORDS["zakuro_recompile"].format(game=play.GAME), text)
        # zakuro_args with --interpreter: PLAY does not stop, so neither does the row
        dll.unlink()
        text, _ = self.window_text(play, dict(config, zakuro_args=["--interpreter"]), ["q"])
        self.assertNotIn("[!]", text)

    def test_the_row_agrees_with_plays_own_stop(self) -> None:
        self.rom_at(self.roms / "fates.cci")
        zak = self.zakuro()
        self.config(zakuro_dir=str(zak))
        out = self.run_play("--setup", "--dry-run", answers="s\n\n")       # s skips the Seal row where it is
        self.assertIn(L.WORDS["zakuro_recompile"].format(game=self.load_play().GAME), out.stdout)
        self.assertIn("[!] " + L.WORDS["row_program"], out.stdout)
        self.assertIn("has not been recompiled yet", out.stdout + out.stderr)   # PLAY's STOP after Ready says so too
        self.assertNotIn("[dry run] would run", out.stdout)

    def test_y_turns_a_stop_into_one_plain_sentence(self) -> None:
        self.rom_at(self.roms / "fates.cci")
        play = self.load_play()
        cases = [
            ("STOP: X:\\p\\engine\\zakuro is missing: run `engine.py fetch`\n", L.WORDS["prog_y_fetch"]),
            ("STOP: zakuro carries 0 commit(s) on the pin but the series has 43 (or the tree is dirty): run "
             "`engine.py apply` first\n", L.WORDS["prog_y_apply"]),
            ("STOP: no archiver: install MSYS2 binutils or LLVM, or pass --ar\n",
             L.WORDS["prog_y_other"].format(reason="no archiver: install MSYS2 binutils or LLVM, or pass --ar")),
            ("STOP: X:\\fates.cci is the game but not the known clean dump:\n  SHA-256 00\nUse the clean dump.\n",
             L.WORDS["prog_y_other"].format(reason="X:\\fates.cci is the game but not the known clean dump")),
        ]
        for stderr, want in cases:
            with self.subTest(stop=stderr.splitlines()[0][:40]):
                text, calls = self.window_text(
                    play, {"check_rom": "full"}, ["y", "q"],
                    runner=lambda c, **k: subprocess.CompletedProcess(c, 2, "game:       plan line\n", stderr))
                self.assertEqual(len(calls), 1)
                cmd, kw = calls[0]
                self.assertEqual(cmd, [sys.executable, str(ROOT / "tools" / "engine" / "engine.py"), "port", "--dry-run"])
                self.assertTrue(kw.get("capture_output"))
                self.assertIn(want, text)
                self.assertIn("game:       plan line", text)
                self.assertFalse([ln for ln in text.splitlines() if "STOP" in ln], text)
                self.assertNotIn("SHA-256 00", text)                    # the rest of the STOP message is not shown raw
        # a check that passes, a check that ends without a STOP line, a check that cannot start
        text, _ = self.window_text(play, {"check_rom": "full"}, ["y", "q"],
                                   runner=lambda c, **k: subprocess.CompletedProcess(c, 0, "[dry run] nothing built\n", ""))
        self.assertIn(L.WORDS["prog_y_ok"], text)
        text, _ = self.window_text(play, {"check_rom": "full"}, ["y", "q"],
                                   runner=lambda c, **k: subprocess.CompletedProcess(c, 1, "", "Traceback\n"))
        self.assertIn(L.WORDS["prog_y_failed"].format(reason="exit 1"), text)

        def broken(c, **k):
            raise OSError("no python")
        text, _ = self.window_text(play, {"check_rom": "full"}, ["y", "q"], runner=broken)
        self.assertIn(L.WORDS["prog_y_failed"].format(reason="OSError"), text)

    def test_engine_stop_helpers(self) -> None:
        self.assertEqual(L.engine_stop("a\nb\n"), (["a", "b"], ""))
        self.assertEqual(L.engine_stop("a\nSTOP: x\n  y\n"), (["a"], "x\n  y"))
        for key in ("prog_y_fetch", "prog_y_apply", "prog_y_other", "prog_y_ok", "prog_y_failed", "zakuro_recompile"):
            self.assertNotIn("STOP", L.WORDS[key])
            self.assertEqual(len(L.WORDS[key].splitlines()), 1, key)       # one line each


if __name__ == "__main__":
    unittest.main()
