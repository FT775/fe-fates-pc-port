"""tools/release/install.py (round 68, release part B, goal 3) on a fake repo in a temp folder.

No build, no install, no game: every program call goes to a fake runner that writes small files, 'running' is a fake
too. Cases: plan (no --engine = nothing; a fresh exe is reused, not rebuilt; stale exe / patches / boot-server /
library), backup (sha-checked, never overwritten, absent files recorded), install (atomic, every check, a failed check
or a failed rename rolls back and the shas are checked again, a running game refuses, a changed staged file or an old
backup refuses), verify_installed against the build records, undo (restores, re-checks, a never-installed release
says so), stage_build (order, STAGED.json, play/ refused, a failing step stops), and the engine-side pieces
(engine.py port --stage-only refuses play/, build.py's server record keys)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "release"))
import install as I  # noqa: E402

PATCHES = ["0001-a.patch", "0002-b.patch"]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wj(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def wb(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def make_repo(root: Path, *, server_head: str | None = "z1", lib: bool = True) -> None:
    """a repo whose installed files all match their records (zakuro head z1, 3dsrecomp head r1)"""
    for n in PATCHES:
        wb(root / "patches" / "zakuro" / n, n.encode())
    wb(root / I.INSTALLED["exe"], b"old exe")
    wj(root / I.INSTALLED["build-record"], {"sha256": sha(b"old exe"), "zakuro_patches": PATCHES, "zakuro_head": "z1",
                                            "3dsrecomp_head": "r1", "finished": "2026-11-22T00:35:20",
                                            "seconds": {"cargo_build": 64.2}})
    wb(root / I.INSTALLED["game-path"], b"roms/game.cci\n")
    wb(root / "engine" / "target" / "3dsrecomp" / "release" / "3dsrecomp.exe", b"recomp")
    wj(root / I.INSTALLED["engine-build-record"],
       {"3dsrecomp": {"exe": "engine\\target\\3dsrecomp\\release\\3dsrecomp.exe", "sha256": sha(b"recomp")},
        "3dsrecomp-verify": {"exe": "engine\\target\\3dsrecomp-verify\\release\\3dsrecomp.exe", "sha256": "x"}})
    (root / "engine" / "zakuro" / ".git").mkdir(parents=True)
    (root / "engine" / "3dsrecomp" / ".git").mkdir(parents=True)
    src = root / "tools" / "harness" / "patches" / "zakuro-server"
    wb(src / "Cargo.toml", b"[package]\n")
    wb(src / "src" / "main.rs", b"fn main() {}\n")
    wb(root / I.INSTALLED["boot-server"], b"old server")
    srec = {"sha256": sha(b"old server"),
            "source_sha256": {"Cargo.toml": sha(b"[package]\n"), "src/main.rs": sha(b"fn main() {}\n")}}
    if server_head:
        srec.update(zakuro_head=server_head, zakuro_patches=PATCHES)
    wj(root / I.INSTALLED["server-record"], srec)
    if lib:
        wb(root / I.INSTALLED["capture-lib"], b"old lib")
        wj(root / I.INSTALLED["capture-record"], {"library_sha256": sha(b"old lib"), "seconds": 385.4})
    wj(root / I.PORT_DIR_REL / "port-inputs.json", {"3dsrecomp": "r1"})


class Fake:
    """the runner: git heads, build.py --check-fresh, the three staging builds, --help, PLAY --check, check_all"""

    def __init__(self, heads=None, fresh=True, help_text="usage: game\n", play_rc=0, fail=None, new_help=None):
        self.heads = heads or {"zakuro": "z1", "3dsrecomp": "r1"}
        self.fresh, self.help_text, self.play_rc, self.fail = fresh, help_text, play_rc, fail
        self.new_help = new_help
        self.calls: list[list[str]] = []

    def __call__(self, cmd, cwd=None, timeout=0):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        joined = " ".join(cmd)
        if self.fail and self.fail in joined:
            return 1, "", "boom"
        if cmd[0] == "git":
            return 0, self.heads.get(Path(cmd[2]).name, "") + "\n", ""
        if "--check-fresh" in cmd:
            return (0, "harness-build: FRESH: ok\n", "") if self.fresh else (1, "harness-build: STALE: a.c changed\n", "")
        if cmd[-1] == "--help":
            return 0, self.help_text, ""
        if cmd[-1] == "--check" and "play.py" in joined:
            return self.play_rc, "Check: would start.\n", ""
        if "engine.py" in joined and "--stage-only" in cmd:
            out = Path(cmd[cmd.index("--stage-only") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / I.EXE).write_bytes(b"new exe")
            wj(out / "build-record.json", {"sha256": sha(b"new exe"), "zakuro_patches": PATCHES, "zakuro_head": "z2"})
            (out / "game-path.txt").write_bytes(b"roms/game.cci\n")
            (out / "help.txt").write_text(self.new_help or self.help_text, encoding="utf-8", newline="\n")
            (out / "README.txt").write_bytes(b"readme")
            return 0, "built\n", ""
        if "--server" in cmd:
            out = Path(cmd[cmd.index("--stage-to") + 1])
            (out / "boot-server.exe").write_bytes(b"new server")
            wj(out / "server_build.json", {"sha256": sha(b"new server"), "zakuro_head": "z2", "zakuro_patches": PATCHES})
            return 0, "", ""
        if "build.py" in joined and "--out" in cmd:
            lib = Path(cmd[cmd.index("--out") + 1]) / "lib"
            wb(lib / I.LIB, b"new lib")
            wj(lib / "harness_build.json", {"library_sha256": sha(b"new lib")})
            return 0, "", ""
        return 0, "", ""


def nobody(_names):
    return []


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="install_test_"))
        make_repo(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def stage(self, files: dict[str, bytes], help_text: str | None = None) -> Path:
        d = self.root / "build" / "release" / "r68" / "bin"
        d.mkdir(parents=True, exist_ok=True)
        for n, b in files.items():
            (d / n).write_bytes(b)
        if help_text is not None:
            (d / "help.txt").write_text(help_text, encoding="utf-8", newline="\n")
        I.write_json(d / "STAGED.json", {"tag": "r68", "files": {p.name: I.sha256(p) for p in d.iterdir()
                                                                 if p.name != "STAGED.json"}})
        return d

    def exe_stage(self, help_text="usage: game\n") -> Path:
        return self.stage({I.EXE: b"new exe", "build-record.json": json.dumps({"sha256": sha(b"new exe")}).encode(),
                           "game-path.txt": b"roms/game.cci\n"}, help_text)

    def installed(self, key: str) -> bytes:
        return (self.root / I.INSTALLED[key]).read_bytes()


class Plan(Base):
    def test_no_engine_builds_nothing_and_runs_nothing(self):
        fake = Fake()
        self.assertEqual(I.plan(False, root=self.root, runner=fake), [])
        self.assertEqual(fake.calls, [])

    def test_everything_fresh_is_reused_not_rebuilt(self):
        self.assertEqual(I.plan(True, root=self.root, runner=Fake()), [])
        items = {i["build"]: i for i in I.freshness(root=self.root, runner=Fake())}
        self.assertEqual(items["exe"]["action"], "reuse")
        self.assertIn("equals play/game/build-record.json", items["exe"]["why"])
        self.assertEqual(items["boot-server"]["action"], "reuse")
        self.assertEqual(items["capture-library"]["action"], "reuse")

    def test_exe_differs_from_record_is_rebuilt(self):
        wb(self.root / I.INSTALLED["exe"], b"hand copy")
        p = {i["build"]: i for i in I.plan(True, root=self.root, runner=Fake())}
        self.assertIn("differs from its build-record", p["exe"]["why"])
        self.assertEqual(p["exe"]["counted_s"], I.COUNTED["apply"] + I.COUNTED["exe_cargo"])
        self.assertIn("zakuro-cargo-tests", p)  # the cargo rows come with any build

    def test_patch_change_and_recompile_counted(self):
        wb(self.root / "patches" / "zakuro" / "0003-c.patch", b"c")
        (self.root / I.PORT_DIR_REL / "port-inputs.json").unlink()
        p = {i["build"]: i for i in I.plan(True, root=self.root, runner=Fake(heads={"zakuro": "z1", "3dsrecomp": "r1"}))}
        self.assertIn("patches/zakuro changed", p["exe"]["why"])
        self.assertEqual(p["exe"]["counted_s"], I.COUNTED["apply"] + I.COUNTED["exe_cargo"] + I.COUNTED["exe_recompile"])
        self.assertIn("patches/zakuro changed since boot-server", p["boot-server"]["why"])

    def test_zakuro_moved_makes_exe_and_boot_server_stale(self):
        p = {i["build"]: i for i in I.plan(True, root=self.root, runner=Fake(heads={"zakuro": "z9", "3dsrecomp": "r1"}))}
        self.assertIn("engine/zakuro moved", p["exe"]["why"])
        self.assertIn("engine/zakuro moved", p["boot-server"]["why"])

    def test_old_server_record_without_zakuro_head_still_reads_and_is_stale(self):
        shutil.rmtree(self.root)
        make_repo(self.root, server_head=None)
        items = {i["build"]: i for i in I.freshness(root=self.root, runner=Fake())}
        self.assertEqual(items["boot-server"]["action"], "build")
        self.assertIn("predates zakuro_head", items["boot-server"]["why"])
        self.assertEqual(items["boot-server"]["counted_s"], I.COUNTED["boot_server_first"])

    def test_stale_library(self):
        p = {i["build"]: i for i in I.plan(True, root=self.root, runner=Fake(fresh=False))}
        self.assertEqual(p["capture-library"]["counted_s"], 385)
        self.assertIn("STALE", p["capture-library"]["why"])
        self.assertEqual([i["build"] for i in I.stale(root=self.root, runner=Fake(fresh=False))], ["capture-library"])

    def test_cargo_rows_equal_check_all(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import check_all
        rows = [r.id for r in check_all.ROWS if r.cmd and r.cmd[0] == "cargo" and "test" in r.cmd]
        self.assertEqual(sorted(rows), sorted(I.CARGO_TEST_ROWS))


class Backup(Base):
    def test_backup_copies_every_file_sha_checked(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        self.assertTrue(rec["ok"], rec)
        for it in rec["items"]:
            self.assertTrue(it["present"], it)
            b = self.root / it["backup"]
            self.assertTrue(b.name.endswith(".2026-11-23-pre-r68"), b.name)
            self.assertEqual(I.sha256(b), I.sha256(self.root / it["installed"]))
        names = sorted(Path(it["backup"]).name.split(".2026")[0] for it in rec["items"])
        self.assertEqual(names, sorted(n for _k, n, _r in I.SET))
        self.assertTrue((self.root / "build" / "backup" / "pre-r68.json").is_file())
        text = (self.root / "build" / "backup" / "pre-r68.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), text)  # repo-relative paths only

    def test_second_backup_same_files_is_the_same_record(self):
        a = I.backup("r68", root=self.root, date="2026-11-23")
        b = I.backup("r68", root=self.root, date="2026-11-24")
        self.assertTrue(b["ok"])
        self.assertEqual(a["items"], b["items"])

    def test_backup_never_overwritten(self):
        I.backup("r68", root=self.root, date="2026-11-23")
        wb(self.root / I.INSTALLED["exe"], b"changed since")
        again = I.backup("r68", root=self.root, date="2026-11-23")
        self.assertFalse(again["ok"])
        self.assertIn("never overwritten", again["detail"])
        b = self.root / "build" / "backup" / f"{I.EXE}.2026-11-23-pre-r68"
        self.assertEqual(b.read_bytes(), b"old exe")

    def test_existing_backup_file_with_other_bytes_refused(self):
        wb(self.root / "build" / "backup" / f"{I.EXE}.2026-11-23-pre-r69", b"something else")
        rec = I.backup("r69", root=self.root, date="2026-11-23")
        self.assertFalse(rec["ok"])
        self.assertEqual((self.root / "build" / "backup" / f"{I.EXE}.2026-11-23-pre-r69").read_bytes(), b"something else")
        self.assertFalse((self.root / "build" / "backup" / "pre-r69.json").exists())

    def test_absent_file_is_recorded(self):
        shutil.rmtree(self.root)
        make_repo(self.root, lib=False)
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        items = {it["key"]: it for it in rec["items"]}
        self.assertFalse(items["capture-lib"]["present"])


class Install(Base):
    def test_install_happy_path(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        staged = self.exe_stage()
        fake = Fake()
        res = I.install(staged, rec, root=self.root, runner=fake, running=nobody)
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.installed("exe"), b"new exe")
        self.assertEqual([c["name"] for c in res["checks"]], ["sha", "help", "play-check", "records"])
        self.assertTrue(all(c["ok"] for c in res["checks"]))
        self.assertTrue(I.verify_installed(root=self.root)["ok"])
        self.assertEqual(self.installed("boot-server"), b"old server")  # not staged: untouched
        self.assertFalse(list((self.root / "play" / "game").glob("*.new-*")))
        self.assertTrue(any(c[-1] == "--help" for c in fake.calls))

    def test_failed_check_rolls_back_and_rechecks(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        res = I.install(self.exe_stage(), rec, root=self.root, runner=Fake(play_rc=1), running=nobody)
        self.assertFalse(res["ok"])
        self.assertTrue(res["rolled_back"])
        self.assertTrue(res["rollback_ok"], res)
        self.assertIn("play-check", res["detail"])
        self.assertEqual(self.installed("exe"), b"old exe")
        self.assertEqual(json.loads(self.installed("build-record"))["sha256"], sha(b"old exe"))
        self.assertTrue(I.verify_installed(root=self.root)["ok"])

    def test_help_text_differs_rolls_back(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        res = I.install(self.exe_stage(help_text="usage: other\n"), rec, root=self.root, runner=Fake(), running=nobody)
        self.assertFalse(res["ok"])
        self.assertIn("--help text differs", res["detail"])
        self.assertEqual(self.installed("exe"), b"old exe")

    def test_rename_failure_midway_rolls_back(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        staged = self.exe_stage()
        real = I.put_in_place
        calls = []

        def flaky(new, dest, stamp):
            calls.append(dest.name)
            if len(calls) == 2:
                raise PermissionError("in use")
            return real(new, dest, stamp)
        with mock.patch.object(I, "put_in_place", flaky):
            res = I.install(staged, rec, root=self.root, runner=Fake(), running=nobody)
        self.assertFalse(res["ok"])
        self.assertTrue(res["rollback_ok"], res)
        self.assertEqual(self.installed("exe"), b"old exe")
        self.assertFalse(list((self.root / "play" / "game").glob("*.new-*")))

    def test_running_game_refuses_and_changes_nothing(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        res = I.install(self.exe_stage(), rec, root=self.root, runner=Fake(), running=lambda n: [I.EXE])
        self.assertFalse(res["ok"])
        self.assertIn("is running", res["detail"])
        self.assertFalse(res["rolled_back"])
        self.assertEqual(self.installed("exe"), b"old exe")

    def test_changed_staged_file_refuses(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        staged = self.exe_stage()
        (staged / I.EXE).write_bytes(b"tampered")
        res = I.install(staged, rec, root=self.root, runner=Fake(), running=nobody)
        self.assertFalse(res["ok"])
        self.assertIn("changed since it was built", res["detail"])
        self.assertEqual(self.installed("exe"), b"old exe")

    def test_backup_older_than_installed_refuses(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        wb(self.root / I.INSTALLED["exe"], b"rebuilt after the backup")
        res = I.install(self.exe_stage(), rec, root=self.root, runner=Fake(), running=nobody)
        self.assertFalse(res["ok"])
        self.assertIn("back up again", res["detail"])
        self.assertEqual(self.installed("exe"), b"rebuilt after the backup")

    def test_exe_without_its_record_refuses(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        staged = self.stage({I.EXE: b"new exe"})
        res = I.install(staged, rec, root=self.root, runner=Fake(), running=nobody)
        self.assertFalse(res["ok"])
        self.assertIn("without build-record.json", res["detail"])

    def test_all_three_programs(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        staged = self.stage({I.EXE: b"new exe", "build-record.json": json.dumps({"sha256": sha(b"new exe")}).encode(),
                             "game-path.txt": b"g\n", "boot-server.exe": b"new server",
                             "server_build.json": json.dumps({"sha256": sha(b"new server")}).encode(),
                             I.LIB: b"new lib", "harness_build.json": json.dumps({"library_sha256": sha(b"new lib")}).encode()},
                            "usage: game\n")
        res = I.install(staged, rec, root=self.root, runner=Fake(), running=nobody)
        self.assertTrue(res["ok"], res)
        self.assertEqual((self.installed("boot-server"), self.installed("capture-lib")), (b"new server", b"new lib"))


class VerifyAndUndo(Base):
    def test_verify_against_records(self):
        v = I.verify_installed(root=self.root)
        self.assertTrue(v["ok"], v)
        info = [i for i in v["items"] if i["ok"] is None]
        self.assertEqual([i["name"] for i in info], ["engine 3dsrecomp-verify"])  # not built here = information
        wb(self.root / I.INSTALLED["boot-server"], b"other server")
        v = I.verify_installed(root=self.root)
        self.assertFalse(v["ok"])
        self.assertIn("boot-server", v["detail"])

    def test_missing_exe_fails_verify(self):
        (self.root / I.INSTALLED["exe"]).unlink()
        self.assertFalse(I.verify_installed(root=self.root)["ok"])

    def test_undo_restores_and_rechecks(self):
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        self.assertTrue(I.install(self.exe_stage(), rec, root=self.root, runner=Fake(), running=nobody)["ok"])
        res = I.undo("r68", root=self.root, running=nobody)
        self.assertTrue(res["ok"], res)
        self.assertEqual(sorted(res["restored"]), sorted([I.INSTALLED["exe"], I.INSTALLED["build-record"]]))
        self.assertEqual(self.installed("exe"), b"old exe")
        self.assertTrue(I.verify_installed(root=self.root)["ok"])
        self.assertTrue((self.root / "build" / "backup" / f"{I.EXE}.2026-11-23-pre-r68").is_file())  # kept

    def test_undo_without_install_says_nothing_was_installed(self):
        res = I.undo("r70", root=self.root, running=nobody)
        self.assertTrue(res["ok"])
        self.assertTrue(res["nothing"])
        self.assertIn("nothing was installed", res["detail"])

    def test_undo_refuses_while_running(self):
        I.backup("r68", root=self.root, date="2026-11-23")
        res = I.undo("r68", root=self.root, running=lambda n: ["boot-server.exe"])
        self.assertFalse(res["ok"])
        self.assertIn("is running", res["detail"])

    def test_undo_moves_a_new_file_aside_never_deletes(self):
        shutil.rmtree(self.root)
        make_repo(self.root, lib=False)
        I.backup("r68", root=self.root, date="2026-11-23")
        wb(self.root / I.INSTALLED["capture-lib"], b"lib that came later")
        res = I.undo("r68", root=self.root, running=nobody)
        self.assertTrue(res["ok"], res)
        self.assertFalse((self.root / I.INSTALLED["capture-lib"]).exists())
        aside = list((self.root / "build" / "harness" / "lib").glob(f"{I.LIB}.after-r68-*"))
        self.assertEqual(len(aside), 1)
        self.assertEqual(aside[0].read_bytes(), b"lib that came later")


class Stage(Base):
    def test_stage_builds_in_order_and_lists_shas(self):
        fake = Fake(fresh=False, heads={"zakuro": "z2", "3dsrecomp": "r1"})
        out = self.root / "build" / "release" / "r68" / "bin"
        got = I.stage_build("r68", out, root=self.root, runner=fake, say=lambda *_: None)
        self.assertEqual(got, Path(os.path.abspath(out)))
        steps = [c for c in fake.calls if c[0] != "git" and "--check-fresh" not in c]
        kinds = [("apply" if "apply" in c else "port" if "--stage-only" in c else "server" if "--server" in c
                  else "lib" if "--out" in c else "cargo" if "check_all.py" in " ".join(c) else "?") for c in steps]
        self.assertEqual(kinds, ["apply", "port", "server", "lib", "cargo"])
        man = json.loads((out / "STAGED.json").read_text(encoding="utf-8"))
        for n in (I.EXE, "build-record.json", "boot-server.exe", "server_build.json", I.LIB, "harness_build.json"):
            self.assertEqual(man["files"][n], I.sha256(out / n), n)
        self.assertEqual(self.installed("exe"), b"old exe")  # nothing installed
        self.assertEqual(self.installed("boot-server"), b"old server")
        cargo = steps[-1]
        self.assertEqual(cargo[cargo.index("--only") + 1].split(","), I.CARGO_TEST_ROWS)

    def test_stage_then_install_then_undo(self):
        fake = Fake(fresh=False, heads={"zakuro": "z2", "3dsrecomp": "r1"})
        out = I.stage_build("r68", self.root / "build" / "release" / "r68" / "bin", root=self.root, runner=fake,
                            say=lambda *_: None)
        rec = I.backup("r68", root=self.root, date="2026-11-23")
        res = I.install(out, rec, root=self.root, runner=fake, running=nobody)
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.installed("capture-lib"), b"new lib")
        self.assertTrue(I.undo("r68", root=self.root, running=nobody)["ok"])
        self.assertEqual((self.installed("exe"), self.installed("boot-server"), self.installed("capture-lib")),
                         (b"old exe", b"old server", b"old lib"))

    def test_play_folder_refused(self):
        for d in (self.root / "play" / "game", self.root / "elsewhere"):
            with self.assertRaises(I.InstallError):
                I.stage_build("r68", d, root=self.root, runner=Fake(fresh=False), say=lambda *_: None)

    def test_failing_step_stops_and_installs_nothing(self):
        fake = Fake(fresh=False, heads={"zakuro": "z2", "3dsrecomp": "r1"}, fail="--server")
        with self.assertRaises(I.InstallError) as e:
            I.stage_build("r68", self.root / "build" / "release" / "r68" / "bin", root=self.root, runner=fake,
                          say=lambda *_: None)
        self.assertIn("boot-server failed", str(e.exception))
        self.assertFalse(any("--out" in c for c in fake.calls))  # nothing after the failed step
        self.assertEqual(self.installed("boot-server"), b"old server")

    def test_stop_round_stops_before_a_step(self):
        wb(self.root / "build" / "STOP_ROUND", b"")
        with self.assertRaises(I.InstallError) as e:
            I.stage_build("r68", self.root / "build" / "release" / "r68" / "bin", root=self.root,
                          runner=Fake(fresh=False), say=lambda *_: None)
        self.assertIn("STOP_ROUND", str(e.exception))


class EngineSide(unittest.TestCase):
    """the small engine-side changes: engine.py port --stage-only, build.py's server record"""

    def test_stage_dir_problem(self):
        sys.path.insert(0, str(ROOT / "tools" / "engine"))
        import engine as E
        for bad in (E.GAME_DIR, E.GAME_DIR / "sub", ROOT / "play", E.PORT_DIR, E.ENGINE / "target"):
            self.assertIsNotNone(E.stage_dir_problem(bad), bad)
        self.assertIsNone(E.stage_dir_problem(ROOT / "build" / "release" / "r68" / "bin"))

    def test_port_stage_only_into_play_refused_before_anything(self):
        sys.path.insert(0, str(ROOT / "tools" / "engine"))
        import engine as E
        import contextlib
        import io
        err = io.StringIO()
        with mock.patch.object(E, "load_upstream", side_effect=AssertionError("read something")), \
                contextlib.redirect_stderr(err):
            rc = E.main(["port", "--stage-only", str(E.GAME_DIR), "--dry-run"])
        self.assertEqual(rc, 2)
        self.assertIn("--stage-only", err.getvalue())

    def test_server_record_keys_and_default_target_unchanged(self):
        # load tools/harness/build.py by its path: a bare 'import build' can get tools/build.py or
        # tools/tables/build.py when an earlier test module in the same process imported one of those
        import importlib.util
        hdir = str(ROOT / "tools" / "harness")
        if hdir not in sys.path:
            sys.path.insert(0, hdir)
        spec = importlib.util.spec_from_file_location("_harness_build_for_test_install", ROOT / "tools" / "harness" / "build.py")
        B = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(B)
        cmd, _env, _cwd = B.server_command()
        self.assertEqual(cmd[cmd.index("--target-dir") + 1], B.SERVER_TARGET)
        cmd, _env, _cwd = B.server_command(target=B.SERVER_STAGE_TARGET)
        self.assertEqual(cmd[cmd.index("--target-dir") + 1], B.SERVER_STAGE_TARGET)
        facts = B.zakuro_facts()
        self.assertEqual(sorted(facts), ["zakuro_head", "zakuro_patches"])
        self.assertTrue(all(p.endswith(".patch") for p in facts["zakuro_patches"]))


if __name__ == "__main__":
    unittest.main()
