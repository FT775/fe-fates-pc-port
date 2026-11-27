"""Self-tests for the randomized-game profiles (tools/play/rando.py, PLAY RANDOMIZED.bat; F-041 #4).

    python -m unittest tests.test_rando_profile          (from the repo root)

Everything runs in temporary folders: a fake APPDATA holding a fake NORMAL save and normal mods, a fake
play folder (FEF_PLAY_DIR), a fake standalone program (an empty file that is never started: the start is
recorded by replacing play.launch), a synthetic cartridge header (identifiers only, tests/test_play.py), and
either no randomizer (stub) or a tiny fake randomizer command line (FEF_RANDOMIZER_DIR). Checks: the profile
folder layout, that the normal data folder (fake %APPDATA%\\zakuro and play\\data) is byte-for-byte the same
before and after, the command and ZAKURO_DATA point at the profile, seeds are checked, a seed is never reused,
continue lists by seed. Needs no ROM, no Zakuro, no network.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANDO = ROOT / "tools" / "play" / "rando.py"
sys.path.insert(0, str(ROOT))
from tests.test_play import fake_rom, TID, STANDALONE, ENV_PLAY, ENV_NOT_RUNNING, ROM_NAME, EXTDATA_TEST_ID  # noqa: E402
sys.path.insert(0, str(ROOT / "tools"))
from gamecfg import GAME  # noqa: E402

ENV_RANDO = GAME.env("RANDOMIZER_DIR")

FAKE_CLI = r'''
import argparse, os, sys, json
p = argparse.ArgumentParser(description="fake randomizer for tests")
p.add_argument("--seed", required=True)
p.add_argument("--classes", default="on"); p.add_argument("--growths", default="on")
p.add_argument("--join-stats", default="on"); p.add_argument("--children", default="off")
p.add_argument("--zakuro-dir", required=True)
a = p.parse_args()
if a.seed == "FAILME":
    sys.exit(3)
mods = os.path.join(a.zakuro_dir, "mods", "%s", "romfs", "GameData")
os.makedirs(mods, exist_ok=True)
open(os.path.join(mods, "GameData.bin.lz"), "wb").write(b"fake " + a.seed.encode())
print(json.dumps(vars(a)))
'''


def tree_digest(top: Path) -> dict:
    out = {}
    if top.exists():
        for p in sorted(top.rglob("*")):
            rel = p.relative_to(top).as_posix()
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir"
    return out


FAKE_CLI_SUB = r'''
import argparse, os, sys
p = argparse.ArgumentParser(description="fake randomizer with subcommands, as tools/randomizer/rando.py has")
sub = p.add_subparsers(dest="cmd")
m = sub.add_parser("make"); sub.add_parser("check")
m.add_argument("--seed"); m.add_argument("--classes"); m.add_argument("--growths"); m.add_argument("--join-stats")
m.add_argument("--children"); m.add_argument("--out"); m.add_argument("--zakuro-dir")
p.epilog = "make flags: --seed S --classes on|off --growths on|off --join-stats on|off --children off --out DIR --zakuro-dir DATA"
p.formatter_class = argparse.RawDescriptionHelpFormatter
a = p.parse_args()
assert a.cmd == "make", a.cmd
os.makedirs(os.path.join(a.out, "Rando-" + a.seed), exist_ok=True)
open(os.path.join(a.out, "Rando-" + a.seed, "plan.json"), "w").write("{}")
os.makedirs(os.path.join(a.zakuro_dir, "mods", "%s", "romfs"), exist_ok=True)
'''


class RandoProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.appdata = base / "AppData"
        self.play = base / "play"
        self.rom = base / "games" / ROM_NAME
        self.rom.parent.mkdir()
        fake_rom(self.rom)
        (self.play / "game").mkdir(parents=True)
        (self.play / "game" / STANDALONE).write_bytes(b"")
        (self.play / "config.json").write_text(json.dumps(
            {"rom": str(self.rom), "check_rom": "header", "zakuro_dir": str(base / "nozakuro"),
             "zakuro_args": ["--data", str(self.appdata / "zakuro"), "--mute"]}), encoding="utf-8")
        # the owner's NORMAL data folder: a save and a mod that must never change
        normal = self.appdata / "zakuro"
        (normal / "user" / "savedata" / TID).mkdir(parents=True)
        (normal / "user" / "savedata" / TID / "Global").write_bytes(b"normal save")
        (normal / "mods" / TID / "romfs").mkdir(parents=True)
        (normal / "mods" / TID / "romfs" / "owner_mod.bin").write_bytes(b"owner mod")
        (normal / "settings.toml").write_text("scale = 2\n", encoding="utf-8")
        (self.play / "data" / "user").mkdir(parents=True)
        (self.play / "data" / "user" / "portable.bin").write_bytes(b"portable save")
        self.nocli = base / "no-randomizer"
        self.cli = base / "randomizer"
        self.cli.mkdir()
        (self.cli / "randomizer.py").write_text(FAKE_CLI % TID, encoding="utf-8")
        self.before = (tree_digest(normal), tree_digest(self.play / "data"))

    def tearDown(self) -> None:
        after = (tree_digest(self.appdata / "zakuro"), tree_digest(self.play / "data"))
        try:
            self.assertEqual(self.before, after, "the normal data folder changed")
        finally:
            self.tmp.cleanup()

    def env(self, cli: bool) -> dict:
        return dict(os.environ, APPDATA=str(self.appdata),
                    **{ENV_PLAY: str(self.play), ENV_NOT_RUNNING: "1", ENV_RANDO: str(self.cli if cli else self.nocli)})

    def run_rando(self, *args: str, cli: bool = True, stdin: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(RANDO), *args], capture_output=True, text=True,
                              env=self.env(cli), timeout=120, input=stdin)

    def run_start(self, *args: str, cli: bool = True) -> tuple[subprocess.CompletedProcess, dict | None]:
        """rando.main with play.launch replaced by a recorder (nothing is started)."""
        rec = Path(self.tmp.name) / "launch.json"
        code = ("import sys, json; sys.path.insert(0, %r); import rando\n"
                "def rec(cmd, cwd, env=None):\n"
                "    json.dump({'cmd': cmd, 'cwd': str(cwd), 'zakuro_data': (env or {}).get('ZAKURO_DATA')}, open(%r, 'w'))\n"
                "rando.play.launch = rec\n"
                "try:\n    sys.exit(rando.main(%r))\n"
                "except rando.Stop as e:\n    print('STOP: ' + str(e)); sys.exit(1)\n"
                % (str(RANDO.parent), str(rec), list(args)))
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=self.env(cli), timeout=120)
        return out, (json.loads(rec.read_text()) if rec.is_file() else None)

    # -------------------------------------------------------------------------------------

    def test_new_with_randomizer_layout_and_start(self) -> None:
        out, launch = self.run_start("new", "--seed", "TEST42", "--growths", "off")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        prof_dir = self.play / "randomizer" / "TEST42"
        data = prof_dir / "data"
        for sub in ("user", f"mods/{TID}", "cheats", "backups"):
            self.assertTrue((data / sub).is_dir() if sub != "backups" else (prof_dir / sub).is_dir(), sub)
        prof = json.loads((prof_dir / "profile.json").read_text(encoding="utf-8"))
        self.assertEqual(prof["seed"], "TEST42")
        self.assertEqual(prof["switches"], {"classes": True, "growths": False, "join_stats": True})
        self.assertFalse(prof["children"])
        self.assertFalse(prof["mod"]["stub"])
        cmd = prof["mod"]["command"]
        self.assertEqual(cmd[cmd.index("--zakuro-dir") + 1], str(data))
        self.assertEqual(cmd[cmd.index("--growths") + 1], "off")
        self.assertNotIn("--children", cmd)       # round W1: children is an option, passed only when on
        self.assertEqual((data / "mods" / TID / "romfs" / "GameData" / "GameData.bin.lz").read_bytes(), b"fake TEST42")
        self.assertFalse((data / "mods" / TID / "romfs" / "owner_mod.bin").exists())   # never the owner's mods
        self.assertFalse(any(p.name.startswith(".") for p in (self.play / "randomizer").iterdir()))
        self.assertIsNotNone(launch)
        self.assertEqual(launch["zakuro_data"], str(data))
        c = launch["cmd"]
        self.assertEqual(c[:4], [str(self.play / "game" / STANDALONE), str(self.rom), "--data", str(data)])
        self.assertEqual(c.count("--data"), 1)            # the owner's own --data in zakuro_args is dropped
        self.assertIn("--mute", c)
        self.assertIn("randomizer.log", os.listdir(prof_dir))

    def test_new_without_randomizer_is_a_stub_and_says_so(self) -> None:
        out = self.run_rando("new", "--seed", "STUB1", "--no-start", cli=False)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("STUB", out.stdout)
        prof = json.loads((self.play / "randomizer" / "STUB1" / "profile.json").read_text(encoding="utf-8"))
        self.assertTrue(prof["mod"]["stub"])
        files = [p.name for p in (self.play / "randomizer" / "STUB1" / "data" / "mods" / TID).iterdir()]
        self.assertEqual(files, ["RANDOMIZER-STUB.txt"])
        out = self.run_rando("continue", "STUB1", "--dry-run", cli=False)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("STUB", out.stdout)
        self.assertIn("ZAKURO_DATA=" + str(self.play / "randomizer" / "STUB1" / "data"), out.stdout)

    def test_made_seed_and_list_and_continue_menu(self) -> None:
        out = self.run_rando("new", "--no-start")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        seeds = [p.name for p in (self.play / "randomizer").iterdir()]
        self.assertEqual(len(seeds), 1)
        self.assertRegex(seeds[0], r"^[2-9A-HJ-NP-Z]{10}$")
        self.assertEqual(self.run_rando("new", "--seed", "B2", "--no-start").returncode, 0)
        out = self.run_rando("list")
        self.assertIn(seeds[0], out.stdout)
        self.assertIn("B2", out.stdout)
        out, launch = self.run_start("continue", "B2")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(launch["zakuro_data"], str(self.play / "randomizer" / "B2" / "data"))
        # the menu: 2 = continue, then the seed typed in
        out = self.run_rando("--dry-run", stdin="2\nb2\n")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("[dry run] would run", out.stdout)
        # the menu: 1 = new, seed typed, three switches
        out = self.run_rando("--no-start", stdin="1\nMENU7\ny\nn\ny\n")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        prof = json.loads((self.play / "randomizer" / "MENU7" / "profile.json").read_text(encoding="utf-8"))
        self.assertEqual(prof["switches"], {"classes": True, "growths": False, "join_stats": True})

    def test_subcommand_cli_gets_make_and_out(self) -> None:
        (self.cli / "randomizer.py").write_text(FAKE_CLI_SUB % TID, encoding="utf-8")
        out = self.run_rando("new", "--seed", "SUB1", "--no-start")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        prof_dir = self.play / "randomizer" / "SUB1"
        cmd = json.loads((prof_dir / "profile.json").read_text(encoding="utf-8"))["mod"]["command"]
        self.assertEqual(cmd[2], "make")
        self.assertEqual(cmd[cmd.index("--out") + 1], str(prof_dir / "mod"))
        self.assertTrue((prof_dir / "mod" / "Rando-SUB1" / "plan.json").is_file())
        self.assertNotIn(".SUB1.making", (prof_dir / "randomizer.log").read_text(encoding="utf-8"))

    def test_seed_rules(self) -> None:
        for bad in ("..", "a/b", "x" * 33, "-lead", "has space"):
            out = self.run_rando("new", "--seed", bad, "--no-start")
            self.assertEqual(out.returncode, 1, bad)
        self.assertFalse((self.play / "randomizer").exists() and any((self.play / "randomizer").iterdir()))
        self.assertEqual(self.run_rando("new", "--seed", "SAME", "--no-start").returncode, 0)
        out = self.run_rando("new", "--seed", "SAME", "--no-start")
        self.assertEqual(out.returncode, 1)
        self.assertIn("already exists", out.stdout)
        out = self.run_rando("continue", "NOPE")
        self.assertEqual(out.returncode, 1)

    def test_failed_randomizer_leaves_no_profile(self) -> None:
        out = self.run_rando("new", "--seed", "FAILME", "--no-start")
        self.assertEqual(out.returncode, 1)
        self.assertFalse((self.play / "randomizer" / "FAILME").exists())
        self.assertEqual([p.name for p in (self.play / "randomizer").iterdir()], [])

    def test_backup_of_profile_save_only(self) -> None:
        self.assertEqual(self.run_rando("new", "--seed", "BK", "--no-start").returncode, 0)
        save = self.play / "randomizer" / "BK" / "data" / "user" / "savedata" / TID
        save.mkdir(parents=True)
        (save / "Global").write_bytes(b"rando save")
        out, launch = self.run_start("continue", "BK")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        zips = list((self.play / "randomizer" / "BK" / "backups").glob("auto-*.zip"))
        self.assertEqual(len(zips), 1)
        self.assertFalse((self.play / "backups").exists())   # PLAY's normal backups are not used

    def test_guard_refuses_normal_place(self) -> None:
        code = ("import sys; sys.path.insert(0, %r); import rando; from pathlib import Path\n"
                "cfg = {'portable_data_dir': 'data'}\n"
                "for p in (rando.play.portable_data_dir(cfg), rando.play.appdata_data_dir(), rando.RANDO_DIR):\n"
                "    try:\n        rando.guard_profile(p, cfg); print('ALLOWED', p)\n"
                "    except rando.Stop:\n        print('refused')\n" % str(RANDO.parent))
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=self.env(True), timeout=60)
        self.assertEqual(out.stdout.split(), ["refused"] * 3, out.stdout + out.stderr)

    def test_normal_play_unchanged(self) -> None:
        """PLAY.bat's dry run still uses no --data and no profile."""
        out = subprocess.run([sys.executable, str(ROOT / "tools" / "play" / "play.py"), "--dry-run"],
                             capture_output=True, text=True, env=self.env(True), timeout=120)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("randomizer", out.stdout)


if __name__ == "__main__":
    unittest.main()
