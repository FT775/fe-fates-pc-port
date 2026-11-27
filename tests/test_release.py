"""tools/release/release.py (round 68, release part B, goal 1): the one-command release.

Everything runs in a synthetic temp git repo under build/ with fake core / smoke / package / install runners: no
game, no build, no install, no remote. The real repo is only read for the two .bat files (CRLF check).

    python -m unittest tests.test_release
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "release"))
import release as R  # noqa: E402
import package as PK  # noqa: E402

SCRATCH = os.path.join(ROOT, "build", "test-release")
# gpgSign off: the fake repos must not depend on (or sign with) any GPG setup of the PC that runs the tests
GIT_ID = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgSign=false",
          "-c", "tag.gpgSign=false"]


def git(root, *args):
    p = subprocess.run(["git", *GIT_ID, *args], cwd=root, capture_output=True, text=True,
                       creationflags=R.NO_WINDOW)
    if p.returncode != 0:
        raise AssertionError(f"git {args} failed: {p.stderr}")
    return p.stdout


def rmtree(p):
    """remove a temp repo (git leaves read-only object files on Windows)"""
    def fix(func, path, _exc):
        try:
            os.chmod(path, 0o700)
            func(path)
        except OSError:
            pass
    shutil.rmtree(p, onerror=fix)


def snapshot(root):
    out = {}
    for top, dirs, files in os.walk(root):
        if ".git" in dirs:
            dirs.remove(".git")
        for f in files:
            p = os.path.join(top, f)
            st = os.stat(p)
            out[os.path.relpath(p, root)] = (st.st_size, st.st_mtime_ns)
    return out


class FakeRunner:
    def __init__(self, rc=None):
        self.rc = rc or {}
        self.calls = []        # keys in order
        self.cmds = []

    @staticmethod
    def key(cmd):
        script = os.path.basename(cmd[1])
        if script == "run_tests.py":
            return "unit-" + cmd[2].lstrip("-")
        if script == "check_all.py":
            return "check_all-" + ("core" if "--core" in cmd else "full")
        if script == "smoke.py":
            args = list(cmd[2:])
            seal = False
            if args and args[0] == "--set":          # smoke.py --set <set> run ...: the Seal edition's set
                seal = args[1].replace("\\", "/").endswith("config/seal/smoke_set.json")
                args = args[2:]
            if args and args[0] == "check":
                return "smoke-check-seal" if seal else "smoke-check"
            return "smoke-seal" if seal else "smoke"
        return script

    def __call__(self, cmd, cwd, log, timeout, mask=lambda s: s):
        k = self.key(cmd)
        self.calls.append(k)
        self.cmds.append(cmd)
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(mask(" ".join(cmd)) + "\n")
        return self.rc.get(k, 0)


class FakePackage:
    def __init__(self, terms, gates_ok=True, findings=None):
        self.terms, self.gates_ok, self.findings = terms, gates_ok, findings or []
        self.failing_editions = set()
        self.calls = []

    def privacy_terms(self):
        return list(self.terms)

    def privacy_scan(self, paths_or_blobs, history=False, *, repo=None, since=None):
        self.calls.append(("privacy_scan", list(paths_or_blobs), history, since))
        return list(self.findings)

    def build(self, repo, tag, prev_tag, out_dir, edition=None):
        """like package.build: no edition = today's package in out_dir; an edition = out_dir/<edition>/"""
        self.calls.append(("build", tag, prev_tag) + ((edition,) if edition else ()))
        ok = self.gates_ok and edition not in self.failing_editions
        if edition:
            out_dir = os.path.join(out_dir, edition)
        os.makedirs(out_dir, exist_ok=True)
        z = os.path.join(out_dir, f"FE-Fates-port-{tag}" + ("-seal-edition" if edition == "seal" else "") + ".zip")
        with open(z, "wb") as fh:
            fh.write(b"PK fake " + (edition or "").encode())
        notes = os.path.join(out_dir, "RELEASE_NOTES.md")
        with open(notes, "w", encoding="utf-8") as fh:
            fh.write(f"# Release {tag}" + (f" ({edition})" if edition else "") + "\n\nShort version: fake notes.\n")
        sums = os.path.join(out_dir, "SHA256SUMS.txt")
        with open(sums, "w", encoding="ascii") as fh:
            fh.write(f"{R.sha256_file(z)}  {os.path.basename(z)}\n")
        gates = [{"name": "privacy", "ok": True, "detail": "nothing of SecretUser in HEAD"},
                 {"name": "credits", "ok": ok, "detail": "mod credit" + ("" if ok else " MISSING")}]
        return {"ok": ok, "zip": z, "bundle": None, "sums": sums, "notes_path": notes, "gates": gates,
                "edition": edition or "seal"}


class FakeInstall:
    def __init__(self, builds=None, install_ok=True, verify_ok=True):
        self.builds = builds or []
        self.install_ok, self.verify_ok = install_ok, verify_ok
        self.calls = []

    def plan(self, engine):
        self.calls.append("plan")
        return list(self.builds) if engine else []

    def stale(self):
        self.calls.append("stale")
        return list(self.builds)

    def stage_build(self, tag, out_dir):
        self.calls.append("stage_build")
        os.makedirs(out_dir, exist_ok=True)
        return out_dir

    def backup(self, tag):
        self.calls.append("backup")
        return {"ok": True, "files": [f"build/backup/x.exe.2026-11-23-pre-{tag}"]}

    def install(self, staged, backup_record):
        self.calls.append("install")
        return {"ok": self.install_ok, "detail": "" if self.install_ok else "sha check failed; rolled back"}

    def verify_installed(self):
        self.calls.append("verify_installed")
        return {"ok": self.verify_ok, "detail": "" if self.verify_ok else "exe differs",
                "shas": {"exe": "ab" * 32}}

    def undo(self, tag):
        self.calls.append("undo")
        return {"ok": True}


class Base(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.root = tempfile.mkdtemp(prefix="repo-", dir=SCRATCH)
        self.addCleanup(rmtree, self.root)
        w = self.write
        w("docs/REPORT_2027-01-12.md", "# Round 67 report: test\n\n**Short version:** fake.\n")
        w("config/release/seed_changes.json", '{"round": 67, "changes": []}\n')
        w("fixture/input.bin", "fixture bytes\n")
        w("src/readable/a.c", "int a;\n")
        w(".gitignore", "build/\n")
        w("config/release/fixtures.json", json.dumps({"smoke_set": "config/harness/smoke_set.json", "files": [
            {"path": "fixture/input.bin", "kind": "file", "sha256": R.sha256_file(os.path.join(self.root,
                                                                                             "fixture/input.bin"))}]}))
        subprocess.run(["git", "init", "-q", "-b", "master"], cwd=self.root, check=True, creationflags=R.NO_WINDOW)
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "user.email", "test@example.invalid")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "first")
        self.out = []
        self.answers = []
        self.prompts = []
        self.runner = FakeRunner()
        self.package = FakePackage(["SecretUser", self.root])
        self.install = FakeInstall()
        self.procs = set()
        self.free = 100 * R.GB
        self.environ = {}
        self.git_hook = None

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def ask(self, prompt):
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else ""

    def env(self):
        real = R.real_git(self.root)

        def g(args, timeout=120):
            if self.git_hook:
                r = self.git_hook(args)
                if r is not None:
                    return r
            return real(args, timeout)
        return R.Env(self.root, run=self.runner, git=g, ask=self.ask, say=self.out.append, package=self.package,
                     install=self.install, processes=lambda: set(self.procs), disk_free=lambda p: self.free,
                     rom_check=lambda cache=None: (True, "fake ROM ok"),
                     full_rows=lambda engine: {"rows": ["a", "b"], "left_out": [] if engine else ["cargo-x"],
                                               "row_seconds": 400.0, "unknown_time": [], "builds": []},
                     environ=self.environ)

    def main(self, *argv):
        return R.main(list(argv), self.env())

    def text(self):
        return "\n".join(self.out)

    def tags(self):
        return git(self.root, "tag", "--list").split()

    def record(self, tag="r68"):
        with open(os.path.join(self.root, "build", "release", tag, "release.json"), encoding="utf-8") as fh:
            return json.load(fh)


class Order(Base):
    def test_default_tag_is_the_round_after_the_newest_report(self):
        self.assertEqual(R.next_tag(self.env()), "r68")

    def test_core_release_runs_the_steps_in_order_and_tags(self):
        self.assertEqual(self.main("--yes"), 0, self.text())
        self.assertEqual(self.runner.calls, ["smoke-check", "unit-core", "check_all-core", "smoke"])
        self.assertEqual([c[0] for c in self.package.calls], ["build"])
        self.assertEqual(self.install.calls, ["stale", "verify_installed"])
        rec = self.record()
        self.assertTrue(rec["ok"])
        self.assertEqual([s["key"] for s in rec["steps"]],
                         ["preflight", "unit-core", "check_all-core", "smoke", "package", "verify", "record", "tag"])
        self.assertTrue(all(s["ok"] for s in rec["steps"]))
        self.assertTrue(all(s["actual_s"] is not None for s in rec["steps"]))
        self.assertIn("r68", self.tags())
        t = self.text()
        self.assertIn("ENGINE BUILD: NO", t)
        self.assertIn("Ready. Core passed. Not pushed.", t)
        self.assertIn("git remote add origin", t)            # first time: how to link GitHub
        self.assertIn("RELEASE.bat undo r68", t)
        for f in ("FINAL_SHA.txt", "UNDO.txt"):
            self.assertTrue(os.path.isfile(os.path.join(self.root, "build", "release", "r68", f)))
        msg = git(self.root, "cat-file", "-p", "r68")
        self.assertIn("# Release r68", msg)                  # notes are the tag message, '#' lines kept
        smoke = self.runner.cmds[self.runner.calls.index("smoke")]
        self.assertNotIn("--bin", smoke)

    def test_engine_release_builds_to_staging_smokes_it_then_backs_up_installs_verifies(self):
        self.install.builds = [{"build": "exe", "why": "patches changed", "counted_s": 70}]
        self.assertEqual(self.main("--engine", "--yes"), 0, self.text())
        self.assertEqual(self.install.calls, ["plan", "stage_build", "backup", "install", "verify_installed"])
        smoke = self.runner.cmds[self.runner.calls.index("smoke")]
        self.assertIn("--bin", smoke)
        rec = self.record()
        self.assertEqual([s["key"] for s in rec["steps"]],
                         ["preflight", "unit-core", "check_all-core", "engine-build", "smoke", "package", "install",
                          "record", "tag"])
        self.assertTrue(rec["installed"])
        self.assertIn("ENGINE BUILD: YES", self.text())
        self.assertIn("exe: patches changed", self.text())

    def test_engine_reuses_an_exe_that_matches_its_build_record(self):
        self.assertEqual(self.main("--engine", "--yes"), 0, self.text())
        self.assertNotIn("stage_build", self.install.calls)
        self.assertNotIn("backup", self.install.calls)
        self.assertNotIn("--bin", self.runner.cmds[self.runner.calls.index("smoke")])
        self.assertIn("reused", self.text())

    def test_full_runs_full_tests_and_skips_build_rows_without_engine(self):
        self.assertEqual(self.main("--full", "--yes"), 0, self.text())
        self.assertEqual(self.runner.calls, ["smoke-check", "unit-full", "check_all-full", "smoke"])
        ca = self.runner.cmds[self.runner.calls.index("check_all-full")]
        self.assertIn("--slow", ca)
        self.assertIn("--skip-unit-dupes", ca)
        self.assertIn("cargo-x", ca[ca.index("--skip") + 1])
        self.assertIn("FULL check_all counted: 100 s", self.text())
        self.assertTrue(self.record()["full"])

    def test_rehearse_goes_on_past_a_stale_library_with_a_warning(self):
        self.install.builds = [{"build": "capture-library", "why": "STALE"}]
        self.assertEqual(self.main("--rehearse", "--yes"), 0, self.text())
        self.assertIn("a real release would stop here", self.text())

    def test_stale_boot_server_without_engine_is_only_a_warning(self):
        self.install.builds = [{"build": "boot-server", "why": "server_build.json predates zakuro_head"}]
        self.assertEqual(self.main("--yes"), 0, self.text())
        self.assertIn("WARNING: boot-server looks out of date", self.text())

    def test_out_of_date_install_without_engine_stops_in_preflight(self):
        self.install.builds = [{"build": "exe", "why": "patch 0031 is newer", "counted_s": 70}]
        self.assertEqual(self.main("--yes"), 1)
        self.assertIn("RELEASE WITH ENGINE BUILD.bat", self.text())
        self.assertEqual(self.runner.calls, ["smoke-check"])


class StopOnFail(Base):
    def test_unit_core_failure_stops_everything(self):
        self.runner.rc["unit-core"] = 1
        self.assertEqual(self.main("--yes"), 1)
        self.assertEqual(self.runner.calls, ["smoke-check", "unit-core"])
        self.assertEqual(self.package.calls, [])
        self.assertNotIn("r68", self.tags())
        rec = self.record()
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["failed_step"], "unit-core")
        self.assertIn("STOPPED at step 2", self.text())

    def test_smoke_failure_stops_before_package(self):
        self.runner.rc["smoke"] = 1
        self.assertEqual(self.main("--yes"), 1)
        self.assertEqual(self.package.calls, [])
        self.assertNotIn("r68", self.tags())

    def test_package_gate_failure_stops_before_backup_and_install(self):
        self.install.builds = [{"build": "exe", "why": "x", "counted_s": 70}]
        self.package.gates_ok = False
        self.assertEqual(self.main("--engine", "--yes"), 1)
        self.assertEqual(self.install.calls, ["plan", "stage_build"])
        self.assertIn("Package check failed: credits", self.text())
        self.assertNotIn("r68", self.tags())

    def test_failed_install_stops_and_says_it_was_rolled_back(self):
        self.install.builds = [{"build": "exe", "why": "x", "counted_s": 70}]
        self.install.install_ok = False
        self.assertEqual(self.main("--engine", "--yes"), 1)
        self.assertIn("rolled back", self.text())
        self.assertNotIn("verify_installed", self.install.calls)
        self.assertNotIn("r68", self.tags())

    def test_failed_verify_without_engine_stops(self):
        self.install.verify_ok = False
        self.assertEqual(self.main("--yes"), 1)
        self.assertIn("do not match their build records", self.text())
        self.assertNotIn("r68", self.tags())

    def test_a_tool_that_raises_is_a_plain_stop(self):
        self.install.builds = [{"build": "exe", "why": "x", "counted_s": 70}]

        def boom(tag, out_dir):
            raise RuntimeError("cargo exit 101")
        self.install.stage_build = boom
        self.assertEqual(self.main("--engine", "--yes"), 1)
        self.assertIn("RuntimeError: cargo exit 101", self.text())
        self.assertNotIn("Traceback", self.text())
        self.assertEqual(self.package.calls, [])

    def test_stop_round_stops_at_once(self):
        self.write("build/STOP_ROUND", "")
        self.assertEqual(self.main("--yes"), 3)
        self.assertEqual(self.runner.calls, [])

    def test_running_game_refuses(self):
        self.procs = {"fire emblem fates.exe"}
        self.assertEqual(self.main("--yes"), 1)
        self.assertIn("is running", self.text())
        self.assertEqual(self.runner.calls, [])

    def test_low_disk_refuses_and_engine_needs_more(self):
        self.free = 25 * R.GB
        self.assertEqual(self.main("--engine", "--yes"), 1)
        self.assertIn("needs 30 GB", self.text())

    def test_wrong_fixture_sha_stops(self):
        self.write("fixture/input.bin", "changed\n")
        git(self.root, "commit", "-qam", "change fixture")
        self.assertEqual(self.main("--yes"), 1)
        self.assertIn("fixture/input.bin differs", self.text())
        self.assertEqual(self.runner.calls, ["smoke-check"])

    def test_smoke_inputs_missing_stops(self):
        self.runner.rc["smoke-check"] = 1
        self.assertEqual(self.main("--yes"), 1)
        self.assertIn("smoke inputs", self.text())

    def test_owner_says_no_at_the_start(self):
        self.answers = ["n"]
        self.assertEqual(self.main(), 1)
        self.assertEqual(self.runner.calls, [])
        self.assertFalse(os.path.exists(os.path.join(self.root, "build", "release", "r68")))


class Preflight(Base):
    def test_dirty_tree_refused(self):
        self.write("new.txt", "x\n")
        self.assertEqual(self.main("--yes"), 1)
        self.assertIn("not committed", self.text())
        self.assertEqual(self.runner.calls, [])

    def test_not_master_refused(self):
        git(self.root, "checkout", "-q", "-b", "side")
        self.assertEqual(self.main("--yes"), 1)
        self.assertIn("not master", self.text())

    def test_tag_must_be_free(self):
        git(self.root, "tag", "r68")
        self.assertEqual(self.main("--yes"), 1)
        self.assertIn("already exists", self.text())
        self.assertEqual(self.package.calls, [])

    def test_bad_tag_is_a_usage_error(self):
        self.assertEqual(self.main("--tag", "v1.0", "--yes"), 2)


class FullDue(Base):
    def _released(self):
        git(self.root, "tag", "-a", "r67", "-m", "r67")

    def test_first_release_asks_and_n_stops(self):
        self.answers = ["", "n"]      # Enter to start, then N to the FULL question
        self.assertEqual(self.main(), 1)
        self.assertTrue(any("CORE only" in p for p in self.prompts))
        self.assertIn("first release", self.text())
        self.assertIn("Stopped so FULL can run", self.text())
        self.assertEqual(self.runner.calls, ["smoke-check"])

    def test_y_goes_on_and_records_full_as_skipped(self):
        self.answers = ["", "y"]
        self.assertEqual(self.main(), 0, self.text())
        self.assertTrue(any(s.startswith("FULL tests") for s in self.record()["skipped"]))

    def test_not_due_asks_nothing(self):
        self._released()
        self.answers = [""]
        self.assertEqual(self.main(), 0, self.text())
        self.assertFalse(any("CORE only" in p for p in self.prompts))
        self.assertEqual(R.full_due(self.env(), "r68"), [])

    def test_readable_edit_since_last_tag_makes_it_due(self):
        self._released()
        self.write("src/readable/a.c", "int a, b;\n")
        git(self.root, "commit", "-qam", "readable edit")
        self.assertTrue(any("readable" in w for w in R.full_due(self.env(), "r68")))

    def test_announced_seed_change_makes_it_due(self):
        self._released()
        self.write("config/release/seed_changes.json", '{"round": 68, "changes": [{"key": "k", "reason": "r"}]}')
        git(self.root, "commit", "-qam", "seed change")
        self.assertTrue(any("seed" in w for w in R.full_due(self.env(), "r68")))

    def test_three_releases_since_the_last_full_one(self):
        self._released()
        for i, full in ((64, True), (65, False), (66, False), (67, False)):
            self.write(f"build/release/r{i}/release.json", json.dumps({"tag": f"r{i}", "ok": True, "full": full}))
        self.assertTrue(any("3 releases" in w for w in R.full_due(self.env(), "r68")))
        self.write("build/release/r67/release.json", json.dumps({"tag": "r67", "ok": True, "full": True}))
        self.assertEqual(R.full_due(self.env(), "r68"), [])


class DryRunRehearse(Base):
    def test_dry_run_writes_nothing_and_shows_the_header(self):
        before = snapshot(self.root)
        self.assertEqual(self.main("--dry-run"), 0, self.text())
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.package.calls, [])
        self.assertEqual(self.install.calls, ["stale"])
        self.assertEqual(self.prompts, [])
        t = self.text()
        self.assertIn("ENGINE BUILD: NO", t)
        self.assertIn("total (counted)", t)
        self.assertIn("Dry run: nothing was written.", t)
        self.assertNotIn("r68", self.tags())

    def test_engine_dry_run_lists_every_build(self):
        self.install.builds = [{"build": "exe", "why": "patch changed", "counted_s": 70},
                               {"build": "boot-server", "why": "zakuro_head changed", "counted_s": 66}]
        before = snapshot(self.root)
        self.assertEqual(self.main("--engine", "--dry-run"), 0)
        self.assertEqual(snapshot(self.root), before)
        t = self.text()
        self.assertIn("ENGINE BUILD: YES", t)
        self.assertIn("exe: patch changed", t)
        self.assertIn("boot-server: zakuro_head changed", t)
        self.assertNotIn("stage_build", self.install.calls)

    def test_rehearse_writes_only_its_folder_and_never_installs_or_tags(self):
        self.install.builds = []
        self.write("uncommitted.txt", "work in progress\n")   # rehearse warns, does not stop
        before = snapshot(self.root)
        self.assertEqual(self.main("--rehearse", "--yes"), 0, self.text())
        after = snapshot(self.root)
        new = [p for p in after if p not in before or after[p] != before[p]]
        self.assertTrue(new)
        for p in new:
            self.assertTrue(p.replace(os.sep, "/").startswith("build/release/rehearse-"), p)
        self.assertEqual(self.tags(), [])
        self.assertEqual(self.install.calls, ["stale", "verify_installed"])
        t = self.text()
        self.assertIn("WARNING (rehearse)", t)
        self.assertIn("Rehearsal done.", t)
        self.assertNotIn("RELEASE.bat push", t.split("Rehearsal done.")[1])
        # child tools are pointed into the rehearsal folder
        for cmd in self.runner.cmds:
            for flag in ("--out", "--log-dir", "--json", "--times"):
                if flag in cmd:
                    self.assertIn("rehearse-", cmd[cmd.index(flag) + 1])

    def test_rehearse_with_engine_stages_but_never_backs_up_or_installs(self):
        self.install.builds = [{"build": "exe", "why": "x", "counted_s": 70}]
        self.assertEqual(self.main("--rehearse", "--engine", "--yes"), 0, self.text())
        self.assertEqual(self.install.calls, ["plan", "stage_build", "verify_installed"])
        self.assertEqual(self.tags(), [])

    def test_dry_run_and_rehearse_together_refused(self):
        self.assertEqual(self.main("--dry-run", "--rehearse"), 2)


class PushUndo(Base):
    def _release(self, *extra):
        self.assertEqual(self.main("--yes", *extra), 0, self.text())
        self.out.clear()

    def test_yes_is_refused_for_push_and_undo(self):
        self._release()
        self.assertEqual(self.main("push", "r68", "--yes"), 2)
        self.assertEqual(self.main("undo", "r68", "--yes"), 2)
        self.assertIn("r68", self.tags())

    def test_push_refused_in_an_agent_environment(self):
        self._release()
        self.environ["CLAUDECODE"] = "1"
        self.answers = ["r68"]
        self.assertEqual(self.main("push", "r68"), 2)
        self.assertIn("owner only", self.text())
        self.assertEqual(self.prompts, [])

    def test_push_without_a_remote_explains_the_first_time_and_pushes_nothing(self):
        self._release()
        self.answers = ["r68"]
        self.assertEqual(self.main("push", "r68"), 1)
        self.assertIn("git remote add origin", self.text())
        self.assertFalse(os.path.exists(os.path.join(self.root, "build", "release", "r68", "pushed.json")))

    def _fake_remote(self):
        pushes = []

        def hook(args):
            if args[:3] == ["remote", "get-url", "origin"]:
                return 0, "https://example.invalid/fake.git\n", ""
            if args and args[0] == "ls-remote":
                return 0, "", ""
            if args and args[0] == "push":
                pushes.append(args)
                return 0, "", ""
            return None
        self.git_hook = hook
        return pushes

    def test_push_shows_findings_and_wants_the_tag_typed_back(self):
        self._release()
        pushes = self._fake_remote()
        self.package.findings = [{"detail": "commit 1234: docs/x.md: S*** (user name)"}]
        self.answers = ["r68"]                     # findings present: 'r68 anyway' is needed
        self.assertEqual(self.main("push", "r68"), 1)
        self.assertEqual(pushes, [])
        self.assertIn("WHOLE history", self.text())
        self.assertIn("no LICENSE", self.text())
        self.assertEqual(self.package.calls[-1], ("privacy_scan", [], True, None))   # first push: whole history
        self.answers = ["r68 anyway"]
        self.assertEqual(self.main("push", "r68"), 0, self.text())
        # round 85 fix 1: local master goes to the private repo's main (never a second branch 'master' there)
        self.assertEqual(pushes, [["push", "-u", "origin", "master:main"], ["push", "origin", "refs/tags/r68"]])
        self.assertIn("git push -u origin master:main", self.text())
        with open(os.path.join(self.root, "build", "release", "r68", "pushed.json"), encoding="utf-8") as fh:
            rec = json.load(fh)
        self.assertEqual(sorted(rec), ["branch", "license", "privacy_findings", "tag", "when"])
        self.assertEqual((rec["tag"], rec["branch"], rec["privacy_findings"]), ("r68", "master:main", 1))

    def test_second_push_scans_only_since_the_last_pushed_tag(self):
        self._release()
        self._fake_remote()
        self.answers = ["r68"]
        self.assertEqual(self.main("push", "r68"), 0, self.text())
        git(self.root, "commit", "-q", "--allow-empty", "-m", "next round")
        self.write("docs/REPORT_2027-01-13.md", "# Round 68 report\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "r68 report")
        self.answers = [""]
        self.assertEqual(self.main(), 0, self.text())
        self.assertIn("r69", self.tags())
        self.answers = ["r69"]
        self.assertEqual(self.main("push", "r69"), 0, self.text())
        self.assertEqual(self.package.calls[-1], ("privacy_scan", [], True, "r68"))
        self.assertIn("commits since r68", self.text())

    def test_push_with_no_findings_takes_the_plain_tag(self):
        self._release()
        pushes = self._fake_remote()
        self.answers = ["r68"]
        self.assertEqual(self.main("push", "r68"), 0, self.text())
        self.assertEqual(len(pushes), 2)

    def test_undo_of_a_pushed_tag_keeps_the_tag(self):
        self._release()
        with open(os.path.join(self.root, "build", "release", "r68", "pushed.json"), "w") as fh:
            fh.write("{}")
        self.answers = ["r68"]
        self.assertEqual(self.main("undo", "r68"), 0, self.text())
        self.assertIn("r68", self.tags())
        self.assertIn("STAYS", self.text())

    def test_undo_without_engine_says_nothing_was_installed_and_drops_the_tag(self):
        self._release()
        self.answers = ["r68"]
        self.assertEqual(self.main("undo", "r68"), 0, self.text())
        self.assertNotIn("r68", self.tags())
        self.assertIn("nothing was installed", self.text().lower())
        self.assertNotIn("undo", self.install.calls)

    def test_undo_of_an_engine_release_restores_then_drops_the_tag(self):
        self.install.builds = [{"build": "exe", "why": "x", "counted_s": 70}]
        self._release("--engine")
        self.answers = ["r68"]
        self.assertEqual(self.main("undo", "r68"), 0, self.text())
        self.assertEqual(self.install.calls[-1], "undo")
        self.assertNotIn("r68", self.tags())

    def test_undo_needs_the_tag_typed_back(self):
        self._release()
        self.answers = ["yes"]
        self.assertEqual(self.main("undo", "r68"), 1)
        self.assertIn("r68", self.tags())

    def test_undo_of_an_unknown_release(self):
        self.answers = ["r99"]
        self.assertEqual(self.main("undo", "r99"), 1)
        self.assertIn("no release record", self.text())


class Privacy(Base):
    def test_private_strings_are_masked_in_screen_and_record(self):
        self.assertEqual(self.main("--yes"), 0, self.text())
        t = self.text()
        self.assertNotIn("SecretUser", t)
        self.assertIn("S***", t)                       # the gate detail, masked
        with open(os.path.join(self.root, "build", "release", "r68", "release.json"), encoding="utf-8") as fh:
            raw = fh.read()
        self.assertNotIn("SecretUser", raw)
        self.assertNotIn(self.root, raw)
        self.assertNotIn(self.root.replace("\\", "/"), raw)

    def test_mask_handles_slash_and_git_bash_forms(self):
        e = self.env()
        self.package.terms = ["C:\\Users\\SecretUser"]
        e._terms = None
        self.assertEqual(e.mask("at C:/Users/SecretUser/x and /c/Users/SecretUser/y"), "at C***/x and /***/y")

    def test_status_writes_nothing(self):
        before = snapshot(self.root)
        self.assertEqual(self.main("status"), 0)
        self.assertEqual(snapshot(self.root), before)
        self.assertIn("Next tag: r68", self.text())
        self.assertIn("GitHub link: not set", self.text())


class Editions(Base):
    """Round 84 (Seal edition split B, docs/SEAL_EDITION_PLAN.md section 6 item 4): once editions.json and the Seal
    page hide (patch 0043) are in the tree, the release packages twice, seal first, then vanilla, each in its own
    folder; the record, FINAL_SHA and the stage screen carry both; without them it is today's single package."""

    EDITIONS = {"format": 1, "default": "seal", "vanilla_needs_patch": "0043",
                "editions": {"vanilla": {"leave_out": ["config/seal/"]}, "seal": {"leave_out": []}}}

    def add_editions(self, patch=True, seal_set=True):
        self.write("config/release/editions.json", json.dumps(self.EDITIONS))
        if patch:
            self.write("patches/zakuro/0043-page-hide.patch", "fake patch\n")
        if seal_set:
            self.write("config/seal/smoke_set.json", '{"jobs": []}\n')
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "editions")

    def test_two_editions_seal_first_each_in_its_own_folder(self):
        self.add_editions()
        self.assertEqual(R.package_editions(self.env()), ["seal", "vanilla"])
        self.assertEqual(self.main("--yes"), 0, self.text())
        self.assertEqual([c for c in self.package.calls if c[0] == "build"],
                         [("build", "r68", None, "seal"), ("build", "r68", None, "vanilla")])
        base = os.path.join(self.root, "build", "release", "r68", "package")
        for ed, zname in (("seal", "FE-Fates-port-r68-seal-edition.zip"), ("vanilla", "FE-Fates-port-r68.zip")):
            for f in (zname, "RELEASE_NOTES.md", "SHA256SUMS.txt"):      # side by side after both runs (risk 14)
                self.assertTrue(os.path.isfile(os.path.join(base, ed, f)), (ed, f))
        rec = self.record()
        self.assertTrue(rec["ok"])
        self.assertEqual(sorted(rec["packages"]), ["seal", "vanilla"])
        self.assertEqual(rec["package"]["edition"], "seal")           # the private record / tag follow the seal run
        with open(os.path.join(self.root, "build", "release", "r68", "FINAL_SHA.txt"), encoding="utf-8") as fh:
            final = fh.read()
        self.assertIn("seal zip ", final)
        self.assertIn("vanilla zip ", final)
        self.assertIn("vanilla sums ", final)
        msg = git(self.root, "cat-file", "-p", "r68")
        self.assertIn("# Release r68 (seal)", msg)
        t = self.text()
        self.assertIn("Package x2", t)
        self.assertIn("Release notes, Vanilla+", t)
        self.assertIn("# Release r68 (vanilla)", t)
        self.assertIn("vanilla folder only", t)

    def test_vanilla_gate_failure_stops_after_the_seal_run_with_no_tag(self):
        self.add_editions()
        self.package.failing_editions = {"vanilla"}
        self.assertEqual(self.main("--yes"), 1, self.text())
        self.assertEqual([c[-1] for c in self.package.calls if c[0] == "build"], ["seal", "vanilla"])
        self.assertIn("Package check failed (vanilla edition)", self.text())
        self.assertEqual(self.tags(), [])
        self.assertFalse(self.record()["ok"])
        self.assertFalse(self.record()["packages"]["vanilla"]["ok"])

    def test_seal_gate_failure_stops_before_the_vanilla_run(self):
        self.add_editions()
        self.package.failing_editions = {"seal"}
        self.assertEqual(self.main("--yes"), 1, self.text())
        self.assertEqual([c[-1] for c in self.package.calls if c[0] == "build"], ["seal"])
        self.assertIn("Package check failed (seal edition)", self.text())

    def test_no_patch_0043_means_todays_single_package(self):
        self.add_editions(patch=False)
        self.assertEqual(R.package_editions(self.env()), [])
        self.assertEqual(self.main("--yes"), 0, self.text())
        self.assertEqual([c for c in self.package.calls if c[0] == "build"], [("build", "r68", None)])
        self.assertEqual(self.record()["packages"], {})

    def test_no_editions_file_means_todays_single_package(self):
        self.assertEqual(R.package_editions(self.env()), [])
        self.write("config/release/editions.json", "{not json")
        self.assertEqual(R.package_editions(self.env()), [])

    # plan section 9 call 5: the small Seal check (its 2 smoke jobs) runs before a Seal release
    def test_seal_smoke_runs_after_the_vanilla_set(self):
        self.add_editions()
        self.assertTrue(R.seal_smoke(self.env()))
        self.assertEqual(self.main("--yes"), 0, self.text())
        self.assertEqual(self.runner.calls, ["smoke-check", "smoke-check-seal", "unit-core", "check_all-core", "smoke",
                                             "smoke-seal"])
        seal = self.runner.cmds[self.runner.calls.index("smoke-seal")]
        self.assertEqual(seal[2], "--set")
        self.assertTrue(seal[3].replace("\\", "/").endswith("config/seal/smoke_set.json"))
        self.assertEqual(seal[4], "run")
        self.assertEqual(seal[seal.index("--lanes") + 1], "2")
        self.assertTrue(seal[seal.index("--out") + 1].endswith("smoke-seal"))
        self.assertNotIn("--bin", seal)
        vanilla = self.runner.cmds[self.runner.calls.index("smoke")]
        self.assertNotIn("--set", vanilla)
        self.assertEqual([s["key"] for s in self.record()["steps"]].count("smoke"), 1)
        t = self.text()
        self.assertIn("Smoke: 6 Vanilla+ jobs, then 2 Seal edition jobs", t)
        self.assertNotIn("(the Vanilla+ set)", t)

    def test_seal_smoke_gets_the_staged_build_too(self):
        self.add_editions()
        self.install.builds = [{"build": "exe", "why": "patches changed", "counted_s": 70}]
        self.assertEqual(self.main("--engine", "--yes"), 0, self.text())
        self.assertIn("--bin", self.runner.cmds[self.runner.calls.index("smoke")])
        self.assertIn("--bin", self.runner.cmds[self.runner.calls.index("smoke-seal")])

    def test_no_config_seal_smoke_set_means_the_vanilla_set_only(self):
        self.add_editions(seal_set=False)
        self.assertFalse(R.seal_smoke(self.env()))
        self.assertEqual(self.main("--yes"), 0, self.text())
        self.assertEqual(self.runner.calls, ["smoke-check", "unit-core", "check_all-core", "smoke"])
        self.assertIn("Smoke: 6 robot jobs (the Vanilla+ set)", self.text())
        self.assertEqual([c[-1] for c in self.package.calls if c[0] == "build"], ["seal", "vanilla"])

    def test_no_seal_edition_means_no_seal_smoke_even_with_the_set(self):
        self.add_editions(patch=False)                 # the set is there, but only today's single package
        self.assertFalse(R.seal_smoke(self.env()))
        self.assertEqual(self.main("--yes"), 0, self.text())
        self.assertNotIn("smoke-seal", self.runner.calls)
        self.assertNotIn("smoke-check-seal", self.runner.calls)

    # round 84 review: missing or wrong Seal smoke inputs stop step 1 (preflight), not step 4
    def test_seal_smoke_inputs_are_checked_in_preflight(self):
        self.add_editions()
        self.assertEqual(self.main("--yes"), 0, self.text())
        chk = self.runner.cmds[self.runner.calls.index("smoke-check-seal")]
        self.assertEqual(chk[2], "--set")
        self.assertTrue(chk[3].replace("\\", "/").endswith("config/seal/smoke_set.json"))
        self.assertEqual(chk[4:], ["check"])
        self.assertTrue(os.path.isfile(os.path.join(self.root, "build", "release", "r68", "logs",
                                                    "smoke-check-seal.log")))

    def test_seal_smoke_inputs_missing_stops_preflight_naming_the_edition(self):
        self.add_editions()
        self.runner.rc["smoke-check-seal"] = 1
        self.assertEqual(self.main("--yes"), 1, self.text())
        self.assertEqual(self.runner.calls, ["smoke-check", "smoke-check-seal"])
        t = self.text()
        self.assertIn("Seal edition's smoke inputs", t)
        self.assertIn("config/seal/smoke_set.json", t)
        self.assertEqual(self.package.calls, [])
        self.assertEqual(self.tags(), [])

    def test_no_seal_edition_means_no_seal_input_check(self):
        self.add_editions(patch=False)                 # the set is there, but only today's single package
        self.runner.rc["smoke-check-seal"] = 1         # would stop if it ran
        self.assertEqual(self.main("--yes"), 0, self.text())
        self.assertEqual(self.runner.calls, ["smoke-check", "unit-core", "check_all-core", "smoke"])

    def test_seal_smoke_failure_stops_the_release_before_package(self):
        self.add_editions()
        self.runner.rc["smoke-seal"] = 1
        self.assertEqual(self.main("--yes"), 1, self.text())
        self.assertEqual(self.runner.calls, ["smoke-check", "smoke-check-seal", "unit-core", "check_all-core", "smoke",
                                             "smoke-seal"])
        self.assertEqual([c for c in self.package.calls if c[0] == "build"], [])
        self.assertIn("Seal edition's smoke failed", self.text())
        self.assertEqual(self.tags(), [])
        self.assertFalse(self.record()["ok"])

    def test_vanilla_smoke_failure_never_starts_the_seal_set(self):
        self.add_editions()
        self.runner.rc["smoke"] = 1
        self.assertEqual(self.main("--yes"), 1, self.text())
        self.assertNotIn("smoke-seal", self.runner.calls)
        self.assertEqual(self.package.calls, [])

    def test_push_refuses_a_record_with_a_failed_edition(self):
        self.add_editions()
        self.assertEqual(self.main("--yes"), 0, self.text())
        p = os.path.join(self.root, "build", "release", "r68", "release.json")
        rec = self.record()
        rec["packages"]["vanilla"]["ok"] = False
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        git(self.root, "remote", "add", "origin", os.path.join(self.root, "nowhere.git"))
        self.answers = ["r68"]
        self.assertEqual(self.main("push", "r68"), 1, self.text())
        self.assertIn("did not pass (vanilla)", self.text())


class HandPushRecord(Base):
    """Round 85, call B2 (a): a pushed.json written by hand for a tag pushed outside release.py (r68, 2026-11-24)
    in the push's own format makes the next push scan only the history after that tag."""

    def test_hand_written_pushed_json_moves_the_scan_start(self):
        self.assertEqual(self.main("--yes"), 0, self.text())
        with open(os.path.join(self.root, "build", "release", "r68", "pushed.json"), "w", encoding="utf-8") as fh:
            json.dump({"tag": "r68", "when": "2026-11-24 05:10:14", "branch": "master:main", "privacy_findings": 2,
                       "license": True}, fh, indent=1)
        self.write("docs/REPORT_2027-01-13.md", "# Round 68 report\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "r68 report")
        self.answers = [""]
        self.assertEqual(self.main(), 0, self.text())
        self.git_hook = lambda args: ((0, "https://example.invalid/fake.git\n", "") if args[:3] == ["remote", "get-url",
                                      "origin"] else (0, "", "") if args and args[0] in ("ls-remote", "push") else None)
        self.out.clear()
        self.answers = ["r69"]
        self.assertEqual(self.main("push", "r69"), 0, self.text())
        self.assertEqual(self.package.calls[-1], ("privacy_scan", [], True, "r68"))
        self.assertIn("the commits since r68", self.text())


class RealPackage:
    """the real tools/release/package.py, with made-up private terms only (no real user name or home folder)"""

    def __init__(self, extra=()):
        self.extra = list(extra)

    def __getattr__(self, attr):
        return getattr(PK, attr)

    def privacy_terms(self):
        return ["SecretUser"]

    def privacy_scan(self, items, history=False, *, repo=None, since=None):
        return PK.privacy_scan(items, history, repo=repo, since=since, terms=self.extra or None, env={})


class Publish(Base):
    """Round 85 (docs/PUBLIC_RELEASE_PLAN.md section 9 fix 5, section 6): release.py publish rNN builds the public
    one-commit snapshot from the Vanilla+ zip only, runs the hard stops, prints the push and gh commands, and never
    pushes. A fake small release folder in a temp repo; real git, no network."""

    EDS = {"format": 1, "default": "seal", "vanilla_needs_patch": "0043",
           "editions": {"vanilla": {"leave_out": ["config/seal/", "docs/old_stub.md"], "last_public_tag": "r67",
                                    "notes": "config/release/notes/{tag}-vanilla.md"},
                        "seal": {"leave_out": []}},
           "markers": list(PK.DEFAULT_MARKERS), "marker_allowed_lines": {"CREDITS.md": 1}}
    CREDIT = ("Seal of Flames by Laz14 (https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0) is a separate fan mod. "
              "It is not included.")

    def setUp(self):
        super().setUp()
        git(self.root, "tag", "-a", "r68", "-m", "r68")
        self.head = git(self.root, "rev-parse", "HEAD").strip()
        self.files = {"README.md": "# The port\nSource only.\n", "CREDITS.md": "# Thanks\n" + self.CREDIT + "\n",
                      "PLAY.bat": "@echo off\r\necho play\r\npause\r\n", "tools/hello.py": "print('hello')\n",
                      "config/release/editions.json": json.dumps(self.EDS, indent=1) + "\n"}
        self.notes = "# FE Fates PC port r68\n\n## What's new since r67\n- Things.\n\n## Credits\n" + self.CREDIT + "\n"
        self.git_calls = []
        self.git_envs = []
        self.tamper = None
        self.pkg = RealPackage()

    def env(self):
        e = super().env()
        e.package = self.pkg

        def git_at(cwd, args, extra_env=None, timeout=600):
            args = list(args)
            extra_env = dict(extra_env) if extra_env is not None else None
            if self.tamper:
                args, extra_env = self.tamper(args, extra_env)
            self.git_calls.append(list(args))
            self.git_envs.append((list(args), dict(extra_env) if extra_env is not None else None))
            return R.real_git_at(cwd, args, extra_env, timeout)
        e.git_at = git_at
        return e

    def make_release(self, files=None, notes=None, final_zip_sha=None, rec=None):
        d = os.path.join(self.root, "build", "release", "r68")
        v = os.path.join(d, "package", "vanilla")
        os.makedirs(v, exist_ok=True)
        z = os.path.join(v, "FE-Fates-port-r68.zip")
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, data in sorted((files or self.files).items()):
                zf.writestr("FE-Fates-port-r68/" + name, data.encode("utf-8") if isinstance(data, str) else data)
        n = os.path.join(v, "RELEASE_NOTES.md")
        with open(n, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.notes if notes is None else notes)
        with open(os.path.join(v, "SHA256SUMS.txt"), "w", encoding="ascii", newline="\n") as fh:
            fh.write(f"{R.sha256_file(z)}  FE-Fates-port-r68.zip\n{R.sha256_file(n)}  RELEASE_NOTES.md\n")
        with open(os.path.join(d, "FINAL_SHA.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"release r68\nhead {self.head}\nseal zip {'0' * 64} FE-Fates-port-r68-seal-edition.zip\n"
                     f"vanilla zip {final_zip_sha or R.sha256_file(z)} FE-Fates-port-r68.zip\n")
        record = {"tag": "r68", "ok": True, "rehearse": False, "head": self.head,
                  "packages": {"seal": {"ok": True, "gates": []},
                               "vanilla": {"ok": True, "gates": [{"name": "leak", "ok": True}]}}}
        record.update(rec or {})
        with open(os.path.join(d, "release.json"), "w", encoding="utf-8") as fh:
            json.dump(record, fh)

    def repo(self):
        return os.path.join(self.root, "build", "publish", "r68", "repo")

    def publish_record(self):
        with open(os.path.join(self.root, "build", "publish", "r68", "publish.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def failed(self):
        return [c["name"] for c in self.publish_record()["checks"] if not c["ok"]]

    def test_publish_builds_one_commit_checks_it_and_prints_the_commands_without_pushing(self):
        self.make_release()
        self.assertEqual(self.main("publish", "r68"), 0, self.text())
        t = self.text()
        self.assertIn("READY. Every hard stop passed. Nothing was pushed.", t)
        self.assertFalse([a for a in self.git_calls if "push" in a or "remote" in a or "fetch" in a])
        rec = self.publish_record()
        self.assertTrue(rec["ok"])
        self.assertFalse(rec["pushed"])
        self.assertEqual(self.failed(), [])
        self.assertEqual({c["name"] for c in rec["checks"]} >= {
            "record", "vanilla-package", "zip-sha", "tag", "no-seal-files", "file-list", "one-commit", "refs",
            "identity", "tag-lightweight", "kinds-and-size", "leave-out", "markers", "privacy", "notes-credit"}, True)
        repo = self.repo()
        self.assertEqual(git(repo, "rev-list", "--all", "--count").strip(), "1")
        self.assertEqual(len(git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()), 1)
        who = git(repo, "log", "-1", "--format=%an|%ae|%cn|%ce|%ai|%ci|%s").strip().split("|")
        self.assertEqual(who[:4], [R.PUBLIC_NAME, R.PUBLIC_EMAIL, R.PUBLIC_NAME, R.PUBLIC_EMAIL])
        self.assertTrue(who[4].endswith("+0000") and who[5].endswith("+0000"))
        self.assertEqual(who[6], "FE Fates PC port r68 (source only)")
        self.assertEqual(git(repo, "cat-file", "-t", "r68").strip(), "commit")          # lightweight
        self.assertEqual(sorted(git(repo, "ls-files").split("\n")[:-1]), sorted(self.files))
        self.assertEqual(git(repo, "branch", "--format=%(refname:short)").split(), ["main"])
        for c in (f"git -C build/publish/r68/repo push --force {R.PUBLIC_URL} main",
                  f"git -C build/publish/r68/repo push {R.PUBLIC_URL} refs/tags/r68",
                  "gh release create r68 --repo FT775/fe-fates-pc-port --verify-tag", "gh auth status",
                  '--notes-file "build/release/r68/package/vanilla/RELEASE_NOTES.md"',
                  '"build/release/r68/package/vanilla/FE-Fates-port-r68.zip"',
                  '"build/release/r68/package/vanilla/SHA256SUMS.txt"'):
            self.assertIn(c, t)
        self.assertNotIn("seal-edition", t.split("The public push (O5)")[1])
        self.assertNotIn(".bundle", t.split("The public push (O5)")[1])
        main_part, sep, delete_part = t.partition("Separate, only if the owner chose to delete the r67 release")
        self.assertTrue(sep)
        self.assertNotIn("gh release delete", main_part)
        self.assertIn("gh release delete r67 --repo FT775/fe-fates-pc-port --cleanup-tag --yes", delete_part)
        self.assertEqual(rec["commands"][1], f"git -C build/publish/r68/repo push --force {R.PUBLIC_URL} main")
        self.assertTrue(os.path.isfile(os.path.join(self.root, "build", "publish", "r68", "PUSH_COMMANDS.txt")))

    def test_a_rehearse_record_makes_no_snapshot(self):
        self.make_release(rec={"rehearse": True})
        self.assertEqual(self.main("publish", "r68"), 1, self.text())
        self.assertIn("record", self.failed())
        self.assertFalse(os.path.exists(self.repo()))
        self.assertIn("no snapshot was made", self.text())

    def test_zip_that_differs_from_final_sha_makes_no_snapshot(self):
        self.make_release(final_zip_sha="ab" * 32)
        self.assertEqual(self.main("publish", "r68"), 1, self.text())
        self.assertIn("zip-sha", self.failed())
        self.assertFalse(os.path.exists(self.repo()))

    def test_tag_not_on_the_record_head_makes_no_snapshot(self):
        self.make_release(rec={"head": "0" * 40})
        self.assertEqual(self.main("publish", "r68"), 1, self.text())
        self.assertIn("tag", self.failed())

    def test_a_seal_zip_under_build_publish_stops_it(self):
        self.make_release()
        os.makedirs(os.path.join(self.root, "build", "publish", "r68"), exist_ok=True)
        with open(os.path.join(self.root, "build", "publish", "r68", "FE-Fates-port-r68-seal-edition.zip"), "wb") as fh:
            fh.write(b"PK")
        self.assertEqual(self.main("publish", "r68"), 1, self.text())
        self.assertIn("no-seal-files", self.failed())

    def test_left_out_path_program_file_marker_and_private_string_each_stop_it(self):
        self.pkg = RealPackage(["PlantedSecret42"])
        files = dict(self.files, **{"config/seal/rules.json": '{"about": "ids"}\n', "tools/x.dll": "MZ fake\n",
                                    "docs/notes.md": "Ask PlantedSecret42.\n", "tools/run.py": "# runs sof.py\n"})
        self.make_release(files=files)
        self.assertEqual(self.main("publish", "r68"), 1, self.text())
        failed = self.failed()
        for name in ("leave-out", "kinds-and-size", "privacy", "markers"):
            self.assertIn(name, failed)
        for name in ("file-list", "one-commit", "identity", "tag-lightweight", "notes-credit"):
            self.assertNotIn(name, failed)
        t = self.text()
        self.assertIn("NOT READY", t)
        self.assertNotIn("gh release create", t)
        self.assertNotIn("PlantedSecret42", json.dumps(self.publish_record()))
        self.assertFalse(os.path.exists(os.path.join(self.root, "build", "publish", "r68", "PUSH_COMMANDS.txt")))

    def test_notes_without_the_full_credit_or_with_two_mod_lines_stop_it(self):
        self.make_release(notes="# FE Fates PC port r68\n\nSeal of Flames by Laz14 is credited.\n")
        self.assertEqual(self.main("publish", "r68"), 1, self.text())
        self.assertIn("notes-credit", self.failed())
        self.out.clear()
        self.make_release(notes=self.notes + "Get Seal of Flames from roms/seal.\n")
        self.assertEqual(self.main("publish", "r68"), 1, self.text())
        self.assertIn("notes-credit", self.failed())
        self.assertIn("lines naming the mod", self.text())

    def test_a_second_run_moves_the_older_snapshot_aside(self):
        self.make_release()
        self.assertEqual(self.main("publish", "r68"), 0, self.text())
        self.assertEqual(self.main("publish", "r68"), 0, self.text())
        pub = os.path.join(self.root, "build", "publish", "r68")
        self.assertTrue([d for d in os.listdir(pub) if d.startswith("repo-replaced-")])
        self.assertEqual(git(self.repo(), "rev-list", "--all", "--count").strip(), "1")

    def test_publish_needs_a_tag_word(self):
        self.assertEqual(self.main("publish"), 2)
        self.assertEqual(self.main("publish", "latest"), 2)

    # Round 85 follow-up (owner "Yes, add them"): permanent guards for the snapshot hard stops the round 85 probe
    # proved once. Each case spoils the snapshot in ONE way through the e.git_at wrapper (real git, no network).

    UNRELATED_CHECKS = ("file-list", "one-commit", "refs", "kinds-and-size", "leave-out", "markers", "privacy",
                        "notes-credit")

    @staticmethod
    def subcommand(args):
        """the git command word after any '-c key=value' pairs (so 'cat-file commit HEAD' is not a commit call)"""
        i = 0
        while i < len(args) and args[i] == "-c":
            i += 2
        return args[i] if i < len(args) else None

    @classmethod
    def is_commit_call(cls, args):
        return cls.subcommand(args) == "commit"

    @classmethod
    def is_tag_call(cls, args):
        return cls.subcommand(args) == "tag"

    @staticmethod
    def same_instant_minus_five(when):
        """'2026-11-27T15:04:05+0000' -> '2026-11-27T10:04:05-0500' (the same moment, another zone)"""
        dt = datetime.datetime.strptime(when, "%Y-%m-%dT%H:%M:%S+0000") - datetime.timedelta(hours=5)
        return dt.strftime("%Y-%m-%dT%H:%M:%S-0500")

    def run_spoiled_publish(self, tamper):
        self.out.clear()
        self.git_calls.clear()
        self.git_envs.clear()
        self.tamper = tamper
        # start each spoiled run from no snapshot folder: a second publish within the same wall-clock second would
        # aim at the same repo-replaced-YYYYmmdd-HHMMSS name and os.replace fails on Windows (no sleep needed)
        pub = os.path.join(self.root, "build", "publish", "r68")
        if os.path.isdir(pub):
            rmtree(pub)
        self.assertFalse(os.path.exists(pub), pub)
        try:
            return self.main("publish", "r68")
        finally:
            self.tamper = None

    def assert_refused_only_by(self, rc, check, also_ok=()):
        t = self.text()
        self.assertEqual(rc, 1, t)
        failed = self.failed()
        self.assertIn(check, failed, t)
        self.assertEqual(failed, [check], t)
        for name in self.UNRELATED_CHECKS + tuple(also_ok):
            self.assertNotIn(name, failed, t)
        self.assertIn("NOT READY", t)
        self.assertNotIn("READY. Every hard stop passed", t)
        self.assertNotIn("gh release create", t)
        self.assertFalse(os.path.exists(os.path.join(self.root, "build", "publish", "r68", "PUSH_COMMANDS.txt")))
        rec = self.publish_record()
        self.assertIs(rec["ok"], False)
        self.assertIs(rec["pushed"], False)
        self.assertNotIn("commands", rec)
        self.assertNotIn("separate", rec)
        self.assertTrue(self.git_calls, "the snapshot ran no git call through e.git_at")
        self.assertFalse([a for a in self.git_calls if "push" in a or "remote" in a or "fetch" in a])

    def test_publish_snapshot_commit_gets_exactly_the_public_identity_and_utc_dates_in_its_env(self):
        self.make_release()
        self.assertEqual(self.main("publish", "r68"), 0, self.text())
        commits = [env for args, env in self.git_envs if self.is_commit_call(args)]
        self.assertEqual(len(commits), 1, self.git_envs)
        env = commits[0]
        self.assertIsNotNone(env)
        self.assertEqual(env["GIT_AUTHOR_NAME"], R.PUBLIC_NAME)
        self.assertEqual(env["GIT_COMMITTER_NAME"], R.PUBLIC_NAME)
        self.assertEqual(env["GIT_AUTHOR_EMAIL"], R.PUBLIC_EMAIL)
        self.assertEqual(env["GIT_COMMITTER_EMAIL"], R.PUBLIC_EMAIL)
        # the +0000 guard only bites a local-time slip on a PC that is not on UTC (this PC: -0500); the identity
        # check itself is tested zone-free by the date test below
        for key in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
            self.assertRegex(env[key], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+0000$", key)
        self.assertEqual(env["GIT_AUTHOR_DATE"], env["GIT_COMMITTER_DATE"])
        self.assertEqual(sorted(k for k in env if k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_"))),
                         sorted(["GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE", "GIT_COMMITTER_NAME",
                                 "GIT_COMMITTER_EMAIL", "GIT_COMMITTER_DATE"]))
        tags = [args for args, _env in self.git_envs if self.is_tag_call(args)]
        self.assertEqual(len(tags), 1, self.git_envs)
        self.assertEqual(tags[0][tags[0].index("tag"):], ["tag", "r68"])                  # lightweight: no -a/-m/-s

    def test_a_wrong_author_or_committer_name_or_email_on_the_snapshot_commit_stops_it_at_identity(self):
        self.make_release()
        wrong = {"GIT_AUTHOR_NAME": "Someone Else", "GIT_AUTHOR_EMAIL": "someone.else@example.invalid",
                 "GIT_COMMITTER_NAME": "Someone Else", "GIT_COMMITTER_EMAIL": "someone.else@example.invalid"}
        for key, value in wrong.items():
            with self.subTest(key=key):
                def tamper(args, extra_env, key=key, value=value):
                    if self.is_commit_call(args):
                        extra_env = dict(extra_env, **{key: value})
                    return args, extra_env
                rc = self.run_spoiled_publish(tamper)
                self.assert_refused_only_by(rc, "identity", also_ok=("tag-lightweight",))
                who = git(self.repo(), "log", "-1", "--format=%an|%ae|%cn|%ce").strip().split("|")
                fields = ["GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"]
                expect = [R.PUBLIC_NAME, R.PUBLIC_EMAIL, R.PUBLIC_NAME, R.PUBLIC_EMAIL]
                expect[fields.index(key)] = value
                self.assertEqual(who, expect)                       # only the one field is wrong, the rest right

    def test_an_author_or_committer_date_outside_utc_stops_it_at_identity_even_for_the_same_instant(self):
        self.make_release()
        for key in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
            with self.subTest(key=key):
                def tamper(args, extra_env, key=key):
                    if self.is_commit_call(args):
                        extra_env = dict(extra_env, **{key: self.same_instant_minus_five(extra_env[key])})
                    return args, extra_env
                rc = self.run_spoiled_publish(tamper)
                self.assert_refused_only_by(rc, "identity", also_ok=("tag-lightweight",))
                ai, ci, at, ct = git(self.repo(), "log", "-1", "--format=%ai|%ci|%at|%ct").strip().split("|")
                self.assertEqual(at, ct)                            # the same moment in time ...
                bad, good = (ai, ci) if key == "GIT_AUTHOR_DATE" else (ci, ai)
                self.assertTrue(bad.endswith("-0500"), bad)         # ... shown in another zone: still refused
                self.assertTrue(good.endswith("+0000"), good)
                who = git(self.repo(), "log", "-1", "--format=%an|%ae|%cn|%ce").strip().split("|")
                self.assertEqual(who, [R.PUBLIC_NAME, R.PUBLIC_EMAIL, R.PUBLIC_NAME, R.PUBLIC_EMAIL])

    def test_a_wrong_snapshot_commit_message_stops_it_at_identity_even_with_the_right_names_and_dates(self):
        self.make_release()

        def tamper(args, extra_env):
            if self.is_commit_call(args):
                args = list(args)
                args[args.index("-m") + 1] = "FE Fates PC port r68"           # "(source only)" left off
            return args, extra_env
        rc = self.run_spoiled_publish(tamper)
        self.assert_refused_only_by(rc, "identity", also_ok=("tag-lightweight",))
        self.assertEqual(git(self.repo(), "log", "-1", "--format=%s").strip(), "FE Fates PC port r68")
        who = git(self.repo(), "log", "-1", "--format=%an|%ae|%cn|%ce").strip().split("|")
        self.assertEqual(who, [R.PUBLIC_NAME, R.PUBLIC_EMAIL, R.PUBLIC_NAME, R.PUBLIC_EMAIL])
        self.assertIn("message 'FE Fates PC port r68'", self.text())

    def test_an_annotated_snapshot_tag_stops_it_at_tag_lightweight_without_needing_gpg(self):
        self.make_release()

        def tamper(args, extra_env):
            if self.is_tag_call(args):
                i = args.index("tag")
                # tag.gpgSign=false: the case must not depend on any GPG setup of the PC that runs the tests
                args = args[:i] + ["-c", "tag.gpgSign=false", "tag", "-a", "-m", "annotated r68"] + args[i + 1:]
            return args, extra_env
        rc = self.run_spoiled_publish(tamper)
        self.assertTrue([a for a in self.git_calls if self.is_tag_call(a) and "-a" in a], self.git_calls)
        self.assert_refused_only_by(rc, "tag-lightweight", also_ok=("identity",))
        self.assertEqual(git(self.repo(), "cat-file", "-t", "r68").strip(), "tag")       # really annotated
        self.assertIn("is a 'tag' object", self.text())
        rec = self.publish_record()
        self.assertEqual([c["ok"] for c in rec["checks"] if c["name"] == "refs"], [True])  # same ref names


    # Owner "Yes, add the signing guard" (2026-11-27): the snapshot switches signing off, so a signing setting in the
    # PC's own git config can never put a key ID on the public copy; a signed commit or extra message lines stop it.

    def test_the_snapshot_commit_and_tag_switch_signing_off_and_the_unsigned_check_passes(self):
        self.make_release()
        self.assertEqual(self.main("publish", "r68"), 0, self.text())
        calls = [a for a, _env in self.git_envs if self.is_commit_call(a) or self.is_tag_call(a)]
        self.assertEqual(len(calls), 2, self.git_envs)
        for args in calls:
            pairs = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "-c"]
            self.assertIn("commit.gpgSign=false", pairs, args)
            self.assertIn("tag.gpgSign=false", pairs, args)
        self.assertIn("unsigned", [c["name"] for c in self.publish_record()["checks"]])
        self.assertNotIn("gpgsig", git(self.repo(), "cat-file", "commit", "HEAD"))

    def test_signing_turned_on_in_the_pcs_own_git_config_does_not_reach_the_snapshot(self):
        """a home .gitconfig that asks git to sign every commit and tag (with a signing program that does not exist:
        without the guard the commit would try to sign and fail, or sign with a real key), sets a local commit
        encoding and a global commit-msg hook that adds a trailer: none of it reaches the snapshot"""
        self.make_release()
        home = tempfile.mkdtemp(prefix="home-", dir=SCRATCH)
        self.addCleanup(rmtree, home)
        fwd = home.replace("\\", "/")
        with open(os.path.join(home, ".gitconfig"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"[commit]\n\tgpgSign = true\n[tag]\n\tgpgSign = true\n\tforceSignAnnotated = true\n"
                     f"[gpg]\n\tprogram = {fwd}/no-such-signer.exe\n[user]\n\tsigningKey = 0000000000000000\n"
                     f"[i18n]\n\tcommitEncoding = ISO-8859-1\n[core]\n\thooksPath = {fwd}/hooks\n")
        os.makedirs(os.path.join(home, "hooks"))
        with open(os.path.join(home, "hooks", "commit-msg"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write('#!/bin/sh\necho "Signed-off-by: Someone Else <someone.else@example.invalid>" >> "$1"\n')
        env = {"HOME": home, "XDG_CONFIG_HOME": os.path.join(home, ".config")}
        with unittest.mock.patch.dict(os.environ, env):
            _rc, out, _err = R.real_git_at(home, ["config", "--global", "--get", "commit.gpgSign"])
            self.assertEqual(out.strip(), "true", "the test home .gitconfig was not picked up")
            rc = self.main("publish", "r68")
        self.assertEqual(rc, 0, self.text())
        self.assertIn("READY. Every hard stop passed.", self.text())
        raw = git(self.repo(), "cat-file", "commit", "HEAD")
        self.assertNotIn("gpgsig", raw)
        self.assertNotIn("\nencoding ", raw.partition("\n\n")[0])          # no local encoding header
        self.assertNotIn("Signed-off-by", raw)                              # the global commit-msg hook never ran
        self.assertEqual(git(self.repo(), "cat-file", "-t", "r68").strip(), "commit")

    def test_a_signed_snapshot_commit_stops_it_at_unsigned(self):
        """the commit is swapped for the same commit plus a (fake) signature header just before the tag is made"""
        self.make_release()
        repo = self.repo()

        def tamper(args, extra_env):
            if self.is_tag_call(args):
                raw = git(repo, "cat-file", "commit", "HEAD")
                head, _sep, body = raw.partition("\n\n")
                fake = ("gpgsig -----BEGIN PGP SIGNATURE-----\n \n iQEzBAABCAAdFiEEfakefakefake\n"
                        " -----END PGP SIGNATURE-----")
                path = os.path.join(self.root, "signed-commit.txt")
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(head + "\n" + fake + "\n\n" + body)
                new = git(repo, "hash-object", "-t", "commit", "-w", "--literally", path).strip()
                git(repo, "update-ref", "refs/heads/main", new)
            return args, extra_env
        rc = self.run_spoiled_publish(tamper)
        self.assert_refused_only_by(rc, "unsigned", also_ok=("identity", "tag-lightweight"))
        self.assertIn("gpgsig", git(repo, "cat-file", "commit", "HEAD"))
        self.assertIn("the commit is signed (gpgsig header)", self.text())

    def test_an_extra_line_in_the_snapshot_message_stops_it_at_identity(self):
        """a trailer such as Signed-off-by would carry a name and e-mail the subject line check never sees"""
        self.make_release()

        def tamper(args, extra_env):
            if self.is_commit_call(args):
                args = list(args) + ["-m", "Signed-off-by: Someone Else <someone.else@example.invalid>"]
            return args, extra_env
        rc = self.run_spoiled_publish(tamper)
        self.assert_refused_only_by(rc, "identity", also_ok=("tag-lightweight", "unsigned"))
        self.assertEqual(git(self.repo(), "log", "-1", "--format=%s").strip(), "FE Fates PC port r68 (source only)")
        self.assertIn("plus 1 more line(s)", self.text())

class RealHelpers(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.d = tempfile.mkdtemp(prefix="run-", dir=SCRATCH)
        self.addCleanup(rmtree, self.d)

    def test_real_run_masks_the_log_and_returns_the_exit_code(self):
        log = os.path.join(self.d, "a.log")
        rc = R.real_run([sys.executable, "-c", "print('hello SecretUser'); raise SystemExit(3)"], self.d, log, 60,
                        lambda s: s.replace("SecretUser", "S***"))
        self.assertEqual(rc, 3)
        with open(log, encoding="utf-8") as fh:
            txt = fh.read()
        self.assertIn("hello S***", txt)
        self.assertNotIn("SecretUser", txt)

    def test_real_run_timeout_kills_and_returns_minus_9(self):
        log = os.path.join(self.d, "b.log")
        rc = R.real_run([sys.executable, "-c", "import time; time.sleep(30)"], self.d, log, 1)
        self.assertEqual(rc, -9)

    def test_listing_and_tree_shas_see_changes(self):
        p = os.path.join(self.d, "t")
        os.makedirs(p)
        with open(os.path.join(p, "f"), "w") as fh:
            fh.write("1")
        a, b = R.listing_sha(p), R.tree_sha(p)
        with open(os.path.join(p, "f"), "w") as fh:
            fh.write("2")
        self.assertEqual(R.listing_sha(p), a)      # same size: listing is stat-only by design
        self.assertNotEqual(R.tree_sha(p), b)
        with open(os.path.join(p, "f"), "w") as fh:
            fh.write("22")
        self.assertNotEqual(R.listing_sha(p), a)


class BatFiles(unittest.TestCase):
    def test_release_bat_files_are_crlf_and_pause(self):
        for name, engine in (("RELEASE.bat", False), ("RELEASE WITH ENGINE BUILD.bat", True)):
            with open(os.path.join(ROOT, name), "rb") as fh:
                data = fh.read()
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""), name)
            self.assertIn(b"tools\\release\\release.py", data)
            self.assertIn(b"pause", data)
            self.assertEqual(b"--engine" in data.split(b"release.py\"", 1)[1].split(b"\r\n", 1)[0], engine, name)
            self.assertNotIn(b"/belownormal", data.lower())
            second_line = data.split(b"\r\n")[1]           # round 85: the label sits in the first comment line
            self.assertIn(b"for the project owner", second_line, name)
            self.assertIn(b"echo This button is for the project owner", data, name)

    def test_fixture_list_holds_shas_only(self):
        with open(os.path.join(ROOT, "config", "release", "fixtures.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertTrue(doc["files"])
        for e in doc["files"]:
            self.assertFalse(os.path.isabs(e["path"]))
            self.assertEqual(len(e["sha256"]), 64)
            self.assertIn(e["kind"], ("file", "tree", "listing"))
            self.assertEqual(set(e) - {"path", "kind", "sha256", "files", "why"}, set())


if __name__ == "__main__":
    unittest.main()
