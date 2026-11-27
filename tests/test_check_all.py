"""Self-tests for tools/check_all.py (docs/CHECKS.md, "Self-tests").

    python -m unittest discover -s tests -t . -p "test_*.py"     (from the repo root)

They prove the runner's negative paths: a failing gate is FAIL, a crash or timeout is
FAIL (INCOMPLETE), never PASS; missing inputs are SKIP with the reason and the command
is not run; every row runs after a failure; KNOWN needs a recorded match; the exit code
follows the verdict. End-to-end tests run check_all.py from scratch copies of the repo
(no extracted/, a mutated config, a git repo with planted bytes from a dummy image).
Nothing outside temporary folders is written. Needs no ROM and no toolchain.
"""
from __future__ import annotations

import importlib.util
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import make_dummy_image  # noqa: E402


def load_check_all():
    spec = importlib.util.spec_from_file_location("check_all_under_test", ROOT / "tools" / "check_all.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


CA = load_check_all()
HAVE_GIT = shutil.which("git") is not None


def py(code: str) -> list[str]:
    return ["{py}", "-c", code]


class Engine(unittest.TestCase):
    """The runner on fake rows, in an empty temporary root."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ctx = CA.Ctx(root=self.root, log_dir=self.root / "logs")

    def tearDown(self):
        self.tmp.cleanup()

    def run_rows(self, rows, reasons=None, fail_on_skip=False):
        with open(os.devnull, "w") as quiet:
            res = CA.run_all(self.ctx, rows, reasons or {}, stream=quiet)
        v, rc, counts = CA.verdict(res, fail_on_skip)
        return {r["id"]: r for r in res}, v, rc

    def test_fail_then_every_row_still_runs(self):
        rows = [CA.Row("bad", "exits 3", cmd=py("import sys; sys.exit(3)")),
                CA.Row("good", "exits 0", cmd=py("print('fine')"))]
        res, v, rc = self.run_rows(rows)
        self.assertEqual(res["bad"]["status"], "FAIL")
        self.assertIn("exit 3", res["bad"]["note"])
        self.assertEqual(res["good"]["status"], "PASS")
        self.assertEqual((v, rc), ("FAIL", 1))

    def test_row_env_reaches_the_command(self):
        rows = [CA.Row("env", "reads an extra variable",
                       cmd=py("import os; print('got ' + os.environ.get('FEF_CHECK_ALL_T', 'none'))"),
                       env={"FEF_CHECK_ALL_T": "yes"}, require=(r"^got yes$",)),
                CA.Row("noenv", "the variable is not leaked to other rows",
                       cmd=py("import os; print('got ' + os.environ.get('FEF_CHECK_ALL_T', 'none'))"),
                       require=(r"^got none$",))]
        res, v, rc = self.run_rows(rows)
        self.assertEqual(res["env"]["status"], "PASS", res["env"]["note"])
        self.assertEqual(res["noenv"]["status"], "PASS", res["noenv"]["note"])

    def test_missing_required_line_fails(self):
        rows = [CA.Row("r", "exit 0, no verdict line", cmd=py("print('something else')"),
                       require=(r"^RESULT: PASS",))]
        res, v, rc = self.run_rows(rows)
        self.assertEqual(res["r"]["status"], "FAIL")
        self.assertIn("missing", res["r"]["note"])
        self.assertEqual(rc, 1)

    def test_traceback_with_exit_0_is_not_pass(self):
        code = ("import traceback\ntry:\n    1/0\nexcept Exception:\n    traceback.print_exc()\n"
                "print('RESULT: PASS')")
        rows = [CA.Row("r", "swallowed crash", cmd=py(code), require=(r"^RESULT: PASS",))]
        res, _, rc = self.run_rows(rows)
        self.assertEqual(res["r"]["status"], "FAIL")
        self.assertIn("Traceback", res["r"]["note"])
        self.assertEqual(rc, 1)

    def test_python_check_crash_is_incomplete_fail(self):
        def boom(ctx):
            raise RuntimeError("boom")
        rows = [CA.Row("r", "raises", func=boom), CA.Row("after", "runs anyway", func=lambda c: (True, "ok"))]
        res, _, rc = self.run_rows(rows)
        self.assertEqual(res["r"]["status"], "FAIL")
        self.assertIn("INCOMPLETE", res["r"]["note"])
        self.assertIn("boom", res["r"]["note"])
        self.assertEqual(res["after"]["status"], "PASS")
        self.assertEqual(rc, 1)

    def test_python_check_bad_return_is_fail(self):
        rows = [CA.Row("r", "returns None", func=lambda c: None),
                CA.Row("s", "returns a truthy non-bool", func=lambda c: ("yes", "x"))]
        res, _, rc = self.run_rows(rows)
        for rid in ("r", "s"):
            self.assertEqual(res[rid]["status"], "FAIL")
            self.assertIn("INCOMPLETE", res[rid]["note"])

    def test_command_timeout_is_incomplete_fail_and_tree_killed(self):
        marker = self.root / "grandchild_survived"
        # The child starts a grandchild that would write the marker after 3 s, then hangs.
        grand = self.root / "grand.py"
        grand.write_text(f"import time\ntime.sleep(3)\nopen({str(marker)!r}, 'w').write('x')\n")
        child = self.root / "child.py"
        child.write_text(f"import subprocess, sys, time\nsubprocess.Popen([sys.executable, {str(grand)!r}])\n"
                         "time.sleep(60)\n")
        rows = [CA.Row("hang", "sleeps past its timeout", cmd=["{py}", str(child)], timeout=1.5)]
        t0 = time.time()
        res, _, rc = self.run_rows(rows)
        self.assertLess(time.time() - t0, 30)
        self.assertEqual(res["hang"]["status"], "FAIL")
        self.assertIn("INCOMPLETE: timed out", res["hang"]["note"])
        self.assertEqual(rc, 1)
        time.sleep(4)
        self.assertFalse(marker.exists(), "the timed-out row's process tree was not killed")

    def test_python_check_timeout_is_incomplete_fail(self):
        rows = [CA.Row("slow", "sleeps", func=lambda c: (time.sleep(3), (True, "late"))[1], timeout=0.3)]
        res, _, _ = self.run_rows(rows)
        self.assertEqual(res["slow"]["status"], "FAIL")
        self.assertIn("INCOMPLETE: timed out", res["slow"]["note"])

    def test_missing_rom_skips_without_running(self):
        marker = self.root / "ran"
        rows = [CA.Row(n, n, needs=(n,), cmd=py(f"open(r'{marker}', 'w')"))
                for n in ("rom:code", "rom:parts", "rom:romfs", "toolchain", "armcc")]
        for r in rows:
            r.id = r.id.replace(":", "-")
        res, v, rc = self.run_rows(rows)
        for r in res.values():
            self.assertEqual(r["status"], "SKIP", r)
            self.assertTrue(r["note"])
        self.assertIn("extracted/code.bin", res["rom-code"]["note"])
        self.assertIn("toolchain", res["toolchain"]["note"])
        self.assertFalse(marker.exists(), "a row with missing inputs ran its command")
        # every row skipped: nothing was checked, so the run is not a pass
        self.assertEqual(rc, 1)
        self.assertIn("no row ran", v)
        rows.append(CA.Row("ok", "runs", cmd=py("print(1)")))
        res, v, rc = self.run_rows(rows)
        self.assertEqual((v, rc), ("PASS (5 skipped)", 0))

    def test_nothing_checked_is_not_pass(self):
        res, _, rc = self.run_rows([CA.Row("py-compile", "no Python files", func=CA.check_py_compile)])
        self.assertEqual(res["py-compile"]["status"], "FAIL")
        self.assertEqual(rc, 1)

    def test_run_where_no_row_runs_is_fail(self):
        rows = [CA.Row("a", "a", cmd=py("print(1)")), CA.Row("b", "b", cmd=py("print(1)"))]
        reasons = {"a": "not selected (--skip)", "b": "not selected (--skip)"}
        for fos in (False, True):
            res, v, rc = self.run_rows(rows, reasons, fail_on_skip=fos)
            self.assertEqual(rc, 1, v)
            self.assertTrue(v.startswith("FAIL"), v)
        self.assertEqual(CA.verdict([])[1], 1)

    def test_python_check_timeout_keeps_stdout(self):
        """A check thread abandoned after its timeout must not swallow the runner's later
        output (the table and the CHECK-ALL line)."""
        import io

        def chatty(ctx):
            time.sleep(1.5)
            print("ZOMBIE OUTPUT")
            return True, "late"

        real, cap = sys.stdout, io.StringIO()
        sys.stdout = cap
        try:
            rows = [CA.Row("slow", "sleeps", func=chatty, timeout=0.2),
                    CA.Row("next", "prints", func=lambda c: (print("row output") or True, "ok"))]
            res, v, rc = self.run_rows(rows)
            print("TABLE LINE")
            time.sleep(2)               # let the abandoned thread print
            print("AFTER ZOMBIE")
        finally:
            sys.stdout = real
        out = cap.getvalue()
        self.assertEqual(res["slow"]["status"], "FAIL")
        self.assertIn("timed out after 0.2s", res["slow"]["note"])
        self.assertEqual(res["next"]["status"], "PASS")
        self.assertIn("TABLE LINE", out)
        self.assertIn("AFTER ZOMBIE", out)
        self.assertNotIn("ZOMBIE OUTPUT", out)
        self.assertNotIn("row output", out)   # a row's output goes to its log only
        self.assertIn("row output", (self.root / "logs" / "next.log").read_text(encoding="utf-8"))
        self.assertEqual(rc, 1)

    def test_dummy_image_meets_rom_code(self):
        make_dummy_image.make(self.root, 0x4000)
        self.assertIsNone(CA.need_missing(self.ctx, "rom:code"))

    def test_after_dependency(self):
        rows = [CA.Row("a", "fails", cmd=py("import sys; sys.exit(1)")),
                CA.Row("b", "needs a", needs=("after:a",), cmd=py("print(1)"))]
        res, _, _ = self.run_rows(rows)
        self.assertEqual(res["b"]["status"], "SKIP")
        self.assertIn("needs a (FAIL)", res["b"]["note"])
        # a not selected in this run: b runs on what is on disk
        res, _, _ = self.run_rows(rows, reasons={"a": "not selected (--skip)"})
        self.assertEqual(res["b"]["status"], "PASS")

    def test_known_needs_a_recorded_match(self):
        k = [{"id": "K-T1", "match": r"^expected difference 42$", "note": "test limit"}]
        fail42 = py("print('expected difference 42'); import sys; sys.exit(1)")
        fail43 = py("print('expected difference 43'); import sys; sys.exit(1)")
        rows = [CA.Row("k", "known", cmd=fail42, known=k), CA.Row("u", "unknown", cmd=fail43, known=k),
                CA.Row("p", "passes", cmd=py("print(0)"), known=k)]
        res, v, rc = self.run_rows(rows)
        self.assertEqual(res["k"]["status"], "KNOWN")
        self.assertEqual(res["k"]["known"], ["K-T1"])
        self.assertEqual(res["u"]["status"], "FAIL")
        self.assertEqual(res["p"]["status"], "PASS")
        self.assertIn("not seen", res["p"]["note"])
        res, v, rc = self.run_rows(rows[:1])
        self.assertEqual((v, rc), ("PASS (1 known)", 0))

    def test_timeout_is_never_known(self):
        k = [{"id": "K-T2", "match": r".*", "note": "matches anything"}]
        rows = [CA.Row("t", "hangs", cmd=py("import time; time.sleep(30)"), timeout=1, known=k)]
        res, _, rc = self.run_rows(rows)
        self.assertEqual(res["t"]["status"], "FAIL")
        self.assertEqual(rc, 1)

    def test_fail_on_skip(self):
        rows = [CA.Row("p", "passes", cmd=py("print(0)")),
                CA.Row("s", "skips", needs=("rom:code",), cmd=py("print(0)"))]
        _, v, rc = self.run_rows(rows)
        self.assertEqual((v, rc), ("PASS (1 skipped)", 0))
        _, v, rc = self.run_rows(rows, fail_on_skip=True)
        self.assertEqual(rc, 1)
        self.assertTrue(v.startswith("FAIL"))
        # a row skipped only because it was not selected does not trip --fail-on-skip
        _, v, rc = self.run_rows(rows[:1] + [CA.Row("n", "unselected", cmd=py("print(0)"))],
                                 reasons={"n": "slow row"}, fail_on_skip=True)
        self.assertEqual(rc, 0)

    def test_row_registry(self):
        ids = [r.id for r in CA.ROWS]
        self.assertEqual(ids[0], "code-hash", "the first row must be the matching gate")
        self.assertEqual(len(ids), len(set(ids)))
        for r in CA.ROWS:
            self.assertTrue((r.cmd is None) != (r.func is None), r.id)
            self.assertIn(r.cost, ("fast", "medium", "slow"), r.id)
            for n in r.needs:
                self.assertTrue(n in ("rom:code", "rom:parts", "rom:romfs", "rom:cci", "toolchain", "armcc",
                                      "git", "host-cc", "engine:3dsrecomp-verify", "robot", "seal-edition")
                                or n.startswith(("after:", "file:")), (r.id, n))
                if not n.startswith("after:"):   # every need kind is one need_missing knows
                    why = CA.need_missing(self.ctx, n) or ""
                    self.assertFalse(why.startswith("unknown need"), (r.id, n, why))

    def test_engine_and_rom_image_needs(self):
        saved = {k: os.environ.pop(k, None) for k in ("FE_ROM", "FE_3DSRECOMP")}
        try:
            why = CA.need_missing(self.ctx, "rom:cci")
            self.assertIn("none configured", why)
            os.environ["FE_ROM"] = str(self.root / "missing.cci")
            self.assertIn("missing.cci", CA.need_missing(self.ctx, "rom:cci"))
            (self.root / "game.cci").write_bytes(b"")
            os.environ["FE_ROM"] = str(self.root / "game.cci")
            self.assertIsNone(CA.need_missing(self.ctx, "rom:cci"))
            del os.environ["FE_ROM"]
            (self.root / "play").mkdir()
            (self.root / "play" / "config.json").write_text(json.dumps({"rom": str(self.root / "game.cci")}))
            self.assertIsNone(CA.need_missing(self.ctx, "rom:cci"))
            why = CA.need_missing(self.ctx, "engine:3dsrecomp-verify")
            self.assertIn("engine.py build 3dsrecomp-verify", why)
            exe = self.root / "engine" / "target" / "3dsrecomp-verify" / "release" / f"3dsrecomp{CA.EXE}"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"")
            self.assertIsNone(CA.need_missing(self.ctx, "engine:3dsrecomp-verify"))
            # a row needing them is SKIP with the reason, its command not run
            marker = self.root / "ran"
            os.environ["FE_3DSRECOMP"] = str(self.root / "nope.exe")
            rows = [CA.Row("v", "needs the engine", needs=("engine:3dsrecomp-verify",),
                           cmd=py(f"open(r'{marker}', 'w').close()"))]
            res, _, _ = self.run_rows(rows)
            self.assertEqual(res["v"]["status"], "SKIP")
            self.assertIn("nope.exe", res["v"]["note"])
            self.assertFalse(marker.exists())
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_robot_need(self):
        """'robot': boot.exe, the capture library and the empty start save, each named when missing."""
        why = CA.need_missing(self.ctx, "robot")
        self.assertIn("boot", why)
        self.assertIn("build.py --boot", why)
        boot = CA.robot_boot_exe(self.root)
        boot.parent.mkdir(parents=True)
        boot.write_bytes(b"")
        why = CA.need_missing(self.ctx, "robot")
        self.assertIn("0004000000179800.dll", why)
        self.assertIn("parallel.py build", why)
        lib = CA.robot_library(self.root)
        lib.parent.mkdir(parents=True)
        lib.write_bytes(b"")
        self.assertIn("new-game-empty.zip", CA.need_missing(self.ctx, "robot"))
        save = self.root / "build" / "harness" / "saves" / "new-game-empty.zip"
        save.parent.mkdir(parents=True)
        save.write_bytes(b"")
        self.assertIsNone(CA.need_missing(self.ctx, "robot"))
        # the real smoke row is SKIP (never run) without them
        marker = self.root / "ran"
        rows = [CA.Row("s", "needs the robot", needs=("robot",), cmd=py(f"open(r'{marker}', 'w').close()"))]
        boot.unlink()
        res, _, _ = self.run_rows(rows)
        self.assertEqual(res["s"]["status"], "SKIP")
        self.assertFalse(marker.exists())

    def test_seal_edition_need(self):
        """round 84 (F-072): rows that need the Seal of Flames edition's tests or harness files SKIP with a plain
        reason in a folder without tests/seal and config/seal (the Vanilla+ zip), never FAIL"""
        why = CA.need_missing(self.ctx, "seal-edition")
        self.assertEqual(why, CA.SEAL_EDITION_MISSING)
        self.assertIn("not in this folder", why)
        marker = self.root / "ran"
        rows = [CA.Row("s", "needs the Seal edition", needs=("seal-edition",), edition="seal",
                       cmd=py(f"open(r'{marker}', 'w').close()")),
                CA.Row("ok", "a shared row", cmd=py("print('fine')"))]
        res, verdict, rc = self.run_rows(rows)
        self.assertEqual(res["s"]["status"], "SKIP")
        self.assertEqual(res["ok"]["status"], "PASS")
        self.assertIn("Vanilla+", res["s"]["note"])
        self.assertEqual(rc, 0)
        self.assertFalse(marker.exists())
        (self.root / "tests" / "seal").mkdir(parents=True)
        (self.root / "tests" / "seal" / "__init__.py").write_text("", encoding="utf-8")
        self.assertIsNotNone(CA.need_missing(self.ctx, "seal-edition"), "config/seal is needed too")
        (self.root / "config" / "seal").mkdir(parents=True)
        self.assertIsNone(CA.need_missing(self.ctx, "seal-edition"))
        self.assertEqual(CA.seal_edition_here(ROOT), (ROOT / "tests" / "seal" / "__init__.py").is_file()
                         and (ROOT / "config" / "seal").is_dir())

    def test_selection(self):
        rows, reasons = CA.select_rows(CA.ROWS, [], [], fast=True, slow=False)
        self.assertEqual(len(rows), len(CA.ROWS))
        for r in CA.ROWS:
            self.assertEqual(r.id in reasons, r.cost != "fast", r.id)
        rows, reasons = CA.select_rows(CA.ROWS, ["lint"], [], fast=True, slow=False)
        self.assertEqual([r.id for r in rows], ["lint"])
        self.assertEqual(reasons, {})
        with self.assertRaises(SystemExit):
            CA.select_rows(CA.ROWS, ["no-such-row"], [], False, False)


# round 67 (release plan part A): the 8 rows moved from fast to medium (613 of the old 746 s of --fast)
RETAGGED_R67 = ("volume-diff", "job-female-diff", "job-record-diff", "key-door-diff", "skill-record-diff",
                "person-record-diff", "parallel-tests", "w12-options")


def selected(**kw) -> list[str]:
    rows, reasons = CA.select_rows(CA.ROWS, kw.pop("only", []), kw.pop("skip", []),
                                   kw.pop("fast", False), kw.pop("slow", False), **kw)
    return [r.id for r in rows if r.id not in reasons]


def unittest_modules(row) -> tuple[str, ...]:
    """The test modules a `-m unittest` row runs (module names, or discover -p test_x.py)."""
    args = [a for a in row.cmd[3:]]
    if args[:1] == ["discover"]:
        pat = args[args.index("-p") + 1]
        self_check = "{root}/tests" == args[args.index("-s") + 1] and "*" not in pat and "?" not in pat
        return ("tests." + pat[:-3],) if self_check and pat.endswith(".py") else ("<discover " + pat + ">",)
    return tuple(args)


class Profiles(unittest.TestCase):
    """--fast / default / --slow / --core / --skip-unit-dupes selections and --list (round 67)."""

    def test_retagged_rows_are_medium_and_still_in_default_and_slow(self):
        rows = {r.id: r for r in CA.ROWS}
        for rid in RETAGGED_R67:
            self.assertIn(rid, rows)
            self.assertEqual(rows[rid].cost, "medium", rid)
        fast, default, slow = selected(fast=True), selected(), selected(slow=True)
        for rid in RETAGGED_R67:
            self.assertNotIn(rid, fast, rid)
            self.assertIn(rid, default, rid)
            self.assertIn(rid, slow, rid)
        self.assertEqual(slow, [r.id for r in CA.ROWS], "--slow keeps every row")
        self.assertEqual(default, [r.id for r in CA.ROWS if r.cost != "slow"], "default = fast + medium")

    def test_unit_dupes_are_pure_reruns_of_discovered_modules(self):
        rows = {r.id: r for r in CA.ROWS}
        self.assertEqual(len(CA.UNIT_DUPES), 17)
        mods = set()
        seal_here = (ROOT / "tests" / "seal" / "__init__.py").is_file()
        skipped = 0
        for rid, want in CA.UNIT_DUPES.items():
            r = rows[rid]
            self.assertIsNotNone(r.cmd, rid)
            self.assertEqual(r.cmd[:3], ["{py}", "-m", "unittest"], f"{rid} is not a pure unittest run")
            self.assertEqual(unittest_modules(r), want, rid)
            self.assertFalse(r.env, f"{rid}: extra environment means the unit suite does not run it the same way")
            for m in want:
                parts = m.split(".")
                self.assertEqual(parts[0], "tests", m)
                # round 83 (F-070): the Seal of Flames edition's modules are tests.seal.<file> (a package below tests)
                self.assertIn(len(parts), (2, 3), m)
                if len(parts) == 3:
                    self.assertEqual(parts[1], "seal", m)
                    self.assertIn("seal-edition", r.needs, f"{rid}: without tests/seal it must SKIP, not FAIL")
                    if not seal_here:       # round 84 (F-072): the Vanilla+ folder has no tests/seal
                        skipped += 1
                        mods.add(m)
                        continue
                name = parts[-1]
                self.assertTrue(name.startswith("test"), f"{m}: unittest discover (pattern test*.py) misses it")
                self.assertTrue(ROOT.joinpath(*parts[:-1], f"{name}.py").is_file(), m)
                mods.add(m)
        self.assertEqual(len(mods), 30, "the 17 rows cover 30 unit modules")
        if skipped:
            print(f"\n[test_check_all] the Seal of Flames edition is not here: {skipped} tests.seal module(s) not "
                  "checked on disk", file=sys.stderr)
        # every row that only runs unit modules is listed (else --core would run it twice)
        for r in CA.ROWS:
            if r.cmd and r.cmd[1:3] == ["-m", "unittest"]:
                self.assertIn(r.id, CA.UNIT_DUPES, f"{r.id} re-runs unit modules: add it to UNIT_DUPES")

    def test_core_profile(self):
        core = selected(core=True)
        ids = {r.id for r in CA.ROWS}
        for rid in CA.CORE_EXTRA:
            self.assertIn(rid, ids)
        self.assertEqual(CA.CORE_EXTRA, ("engine-selftest", "release-selftest"))
        want = [r.id for r in CA.ROWS if (r.cost == "fast" or r.id in CA.CORE_EXTRA) and r.id not in CA.UNIT_DUPES]
        self.assertEqual(core, want)
        self.assertIn("engine-selftest", core)
        self.assertIn("release-selftest", core)
        self.assertIn("code-hash", core)
        for rid in list(CA.UNIT_DUPES) + list(RETAGGED_R67):
            self.assertNotIn(rid, core, rid)
        self.assertTrue(all(r.cost != "slow" for r in CA.ROWS if r.id in core))
        _, reasons = CA.select_rows(CA.ROWS, [], [], False, False, core=True)
        self.assertIn("not in the --core profile", reasons["m1-tests"])
        self.assertIn("unit-suite duplicate", reasons["selftest"])
        self.assertIn("test_check_all", reasons["selftest"])
        # --skip still works inside the profile
        self.assertNotIn("lint", selected(core=True, skip=["lint"]))

    def test_skip_unit_dupes(self):
        for kw in ({}, {"slow": True}, {"fast": True}):
            plain = selected(**dict(kw))
            dropped = selected(skip_unit_dupes=True, **dict(kw))
            self.assertEqual(dropped, [rid for rid in plain if rid not in CA.UNIT_DUPES], kw)
        _, reasons = CA.select_rows(CA.ROWS, [], [], False, True, skip_unit_dupes=True)
        self.assertIn("test_rando_integrate", reasons["rando-tracks-tests"])
        self.assertIn("test_rando_enemies", reasons["rando-tracks-tests"])
        # the plain sets keep every duplicate row
        for rid in CA.UNIT_DUPES:
            self.assertIn(rid, selected(slow=True), rid)
        # explicit --only names still give way to --skip-unit-dupes (and so to --core)
        self.assertEqual(selected(only=["selftest", "lint"], skip_unit_dupes=True), ["lint"])
        self.assertEqual(selected(only=["selftest", "lint"]), ["lint", "selftest"])

    def test_list_follows_the_profile(self):
        rows, reasons = CA.select_rows(CA.ROWS, [], [], False, False, core=True)
        times = {"code-hash": 17.0, "engine-selftest": 21.0, "selftest": 65.0}
        with tempfile.TemporaryDirectory() as d:
            ctx = CA.Ctx(root=Path(d), log_dir=Path(d) / "logs")
            out = CA.list_rows(ctx, rows, reasons, times, "core")
            plain = CA.list_rows(ctx, rows)
        n = len(rows) - len(reasons)
        self.assertIn(f"profile core: {n} of {len(CA.ROWS)} rows run", out)
        self.assertIn("add up to 38.0 s", out, "only the selected rows' seconds count (not selftest's 65)")
        line = next(ln for ln in out.splitlines() if ln.startswith("selftest "))
        self.assertRegex(line, r"^selftest\s+medium\s+no\s+65\.00\s")
        self.assertRegex(next(ln for ln in out.splitlines() if ln.startswith("engine-selftest ")),
                         r"^engine-selftest\s+medium\s+yes\s+21\.00\s")
        self.assertNotIn(" rows run; ", plain)
        self.assertTrue(plain.startswith("Row                Cost    Needs"), "the plain list keeps its old columns")

    def test_list_and_profile_arguments(self):
        with tempfile.TemporaryDirectory() as d:
            times = Path(d) / "times.json"
            times.write_text(json.dumps({"seconds": {"engine-selftest": 21.08}}), encoding="utf-8")
            for args, want in ((["--core"], "profile core:"), (["--fast"], "profile fast:"),
                               (["--slow"], "profile slow:"), ([], "profile default:"),
                               (["--slow", "--skip-unit-dupes"], "profile slow+skip-unit-dupes:"),
                               (["--only", "lint"], "profile only:")):
                buf = []
                old = sys.stdout
                sys.stdout = type("W", (), {"write": lambda s, x: buf.append(x), "flush": lambda s: None})()
                try:
                    rc = CA.main(["--root", d, "--times", str(times), "--list"] + args)
                finally:
                    sys.stdout = old
                self.assertEqual(rc, 0, args)
                self.assertIn(want, "".join(buf), args)
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["times.json"], "--list writes nothing")
            for bad in (["--core", "--fast"], ["--core", "--slow"], ["--fast", "--slow"]):
                with open(os.devnull, "w") as quiet:
                    old = sys.stderr
                    sys.stderr = quiet
                    try:
                        with self.assertRaises(SystemExit) as cm:
                            CA.main(["--root", d, "--list"] + bad)
                    finally:
                        sys.stderr = old
                self.assertEqual(cm.exception.code, 2, bad)

    def test_save_times_drops_rows_that_no_longer_exist(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "times.json"
            p.write_text(json.dumps({"seconds": {"gone-row": 0.24, "a": 1.0}}), encoding="utf-8")
            CA.save_times(p, [{"id": "b", "status": "PASS", "seconds": 2.0}], keep={"a", "b"})
            self.assertEqual(CA.load_times([p]), {"a": 1.0, "b": 2.0})
            CA.save_times(p, [], keep=None)     # without keep nothing is dropped
            self.assertEqual(CA.load_times([p]), {"a": 1.0, "b": 2.0})

    @unittest.skipUnless((ROOT / "build" / "check_all_times.json").is_file(), "no local times file")
    def test_local_times_file_has_no_stale_rows(self):
        d = json.loads((ROOT / "build" / "check_all_times.json").read_text(encoding="utf-8"))
        stale = sorted(set(d.get("seconds", {})) - {r.id for r in CA.ROWS})
        self.assertEqual(stale, [], "times of rows that no longer exist (round 67 dropped rando-r66-rcheck-selftest)")

    def test_docstring_is_current(self):
        doc = CA.__doc__
        self.assertNotIn("~13 min", doc)
        for word in ("--core", "--skip-unit-dupes", "2026-11-23", "engine-selftest"):
            self.assertIn(word, doc)
        for rid in RETAGGED_R67:
            self.assertIn(rid, doc, "the retag is documented in the help")


# round 83 (Seal edition split A3, F-070; docs/SEAL_EDITION_PLAN.md section 5): the Seal of Flames edition rows
SEAL_ROWS = ("sof-path-tests", "rando-r64-seal-bosses", "rando-seal-tests", "engine-seal-person-name",
             "engine-seal-person-order", "seal-smoke")     # seal-smoke: round 84 (F-072)


class Editions(unittest.TestCase):
    """--edition all (default) / vanilla / seal and the rows' edition tags (round 83)."""

    def test_tags(self):
        rows = {r.id: r for r in CA.ROWS}
        self.assertEqual(sorted(r.id for r in CA.ROWS if r.edition == "seal"), sorted(SEAL_ROWS))
        self.assertEqual({r.edition for r in CA.ROWS}, {"shared", "seal"})
        for rid in SEAL_ROWS:
            self.assertIn(rid, rows)

    def test_all_is_the_default_and_changes_nothing(self):
        for kw in ({}, {"slow": True}, {"fast": True}, {"core": True}):
            self.assertEqual(selected(**dict(kw)), selected(edition="all", **dict(kw)), kw)
        self.assertEqual(selected(slow=True), [r.id for r in CA.ROWS])

    def test_vanilla_skips_only_the_seal_rows(self):
        slow = selected(slow=True)
        vanilla = selected(slow=True, edition="vanilla")
        self.assertEqual(vanilla, [rid for rid in slow if rid not in SEAL_ROWS])
        _, reasons = CA.select_rows(CA.ROWS, [], [], False, True, edition="vanilla")
        for rid in SEAL_ROWS:
            self.assertIn("--edition vanilla", reasons[rid], rid)
        # --only obeys the edition too
        self.assertEqual(selected(only=["sof-path-tests", "lint"], edition="vanilla"), ["lint"])

    def test_seal_runs_only_the_seal_rows(self):
        self.assertEqual(selected(slow=True, edition="seal"), [r.id for r in CA.ROWS if r.id in SEAL_ROWS])
        _, reasons = CA.select_rows(CA.ROWS, [], [], False, True, edition="seal")
        self.assertIn("--edition seal", reasons["lint"])
        # the default set has no slow rows: the 2 engine rows need --slow (or --only)
        self.assertEqual(selected(edition="seal"), ["sof-path-tests", "rando-r64-seal-bosses", "rando-seal-tests"])
        self.assertEqual(selected(only=["engine-seal-person-name", "lint"], edition="seal"),
                         ["engine-seal-person-name"])

    def test_unknown_edition_is_refused(self):
        with self.assertRaises(SystemExit):
            CA.select_rows(CA.ROWS, [], [], False, False, edition="classic")

    def test_install_gate_keeps_the_engine_seal_rows(self):
        """The install gate runs check_all --only with no --edition, so the 2 engine Seal rows guard shared engine
        code in both editions (plan section 5)."""
        spec = importlib.util.spec_from_file_location("install_for_editions", ROOT / "tools" / "release" / "install.py")
        I = importlib.util.module_from_spec(spec)  # noqa: N806
        spec.loader.exec_module(I)
        for rid in ("engine-seal-person-name", "engine-seal-person-order"):
            self.assertIn(rid, I.CARGO_TEST_ROWS)
            self.assertIn(rid, selected(only=list(I.CARGO_TEST_ROWS)))

    def test_list_names_the_edition(self):
        with tempfile.TemporaryDirectory() as d:
            for args, want in ((["--edition", "vanilla"], "profile edition-vanilla:"),
                               (["--core", "--edition", "seal"], "profile core+edition-seal:"),
                               (["--edition", "all"], "profile default:")):
                buf = []
                old = sys.stdout
                sys.stdout = type("W", (), {"write": lambda s, x: buf.append(x), "flush": lambda s: None})()
                try:
                    rc = CA.main(["--root", d, "--times", str(Path(d) / "none.json"), "--list"] + args)
                finally:
                    sys.stdout = old
                self.assertEqual(rc, 0, args)
                self.assertIn(want, "".join(buf), args)
            self.assertEqual(list(Path(d).iterdir()), [], "--list writes nothing")
        self.assertIn("--edition", CA.__doc__)

    def test_smoke_rows_split_6_and_2(self):
        """round 84 (F-072, plan section 5): the Vanilla+ smoke-set row wants 6/6 jobs and the memory compare; the
        Seal edition's seal-smoke row runs config/seal/smoke_set.json and wants 2/2; both at 2 lanes, both alone"""
        rows = {r.id: r for r in CA.ROWS}
        smoke, seal = rows["smoke-set"], rows["seal-smoke"]
        self.assertEqual(smoke.edition, "shared")
        self.assertEqual(seal.edition, "seal")
        self.assertIn("PASS: jobs 6/6, memory compare equal", smoke.require[0])
        self.assertIn("PASS: jobs 2/2, baseline equal", seal.require[0])
        self.assertEqual(smoke.cmd[-2:], ["--lanes", "2"])
        self.assertEqual(seal.cmd[-2:], ["--lanes", "2"])
        self.assertIn("{root}/config/seal/smoke_set.json", seal.cmd)
        self.assertNotIn("--set", smoke.cmd)
        self.assertIn("seal-edition", seal.needs)
        self.assertTrue({"smoke-set", "seal-smoke"} <= CA.PARALLEL_EXCLUSIVE)
        self.assertEqual(selected(slow=True, edition="vanilla").count("seal-smoke"), 0)

    def test_check_paths_per_edition(self):
        """round 84 (F-072, plan section 5, H13): the full check's path lists are tracked, one per edition, and never
        overlap; the Seal one is checked where the Seal edition is"""
        v = json.loads((ROOT / "config" / "harness" / "check_paths.json").read_text(encoding="utf-8"))
        self.assertEqual(v["edition"], "vanilla")
        self.assertEqual(list(v["paths"]), ["bt", "cq", "rv"])
        text = (ROOT / "config" / "harness" / "check_paths.json").read_text(encoding="utf-8")
        for marker in ("Seal of Flames", "Laz14", "656034"):
            self.assertNotIn(marker, text)
        seal_file = ROOT / "config" / "seal" / "check_paths.json"
        if not seal_file.is_file():
            self.skipTest("the Seal of Flames edition is not here (no config/seal)")
        s = json.loads(seal_file.read_text(encoding="utf-8"))
        self.assertEqual(s["edition"], "seal")
        self.assertEqual(list(s["paths"]), ["seal"])
        self.assertFalse(set(v["paths"]) & set(s["paths"]))

    def test_the_count_line_in_a_folder_without_the_seal_edition(self):
        """round 84 (F-072): check_all in a Vanilla+ folder prints how many selected rows skip for the missing Seal
        edition, and they SKIP, never FAIL (with only these rows selected nothing runs, which check_all itself calls
        a failed run: "nothing checked is not a pass")"""
        with tempfile.TemporaryDirectory() as d:
            buf = []
            old = sys.stdout
            sys.stdout = type("W", (), {"write": lambda s, x: buf.append(x), "flush": lambda s: None})()
            try:
                rc = CA.main(["--root", d, "--times", str(Path(d) / "none.json"),
                              "--only", "sof-path-tests,rando-seal-tests,seal-smoke"])
            finally:
                sys.stdout = old
            out = "".join(buf)
            self.assertIn(rc, (0, 1), out)
            self.assertIn(CA.SEAL_EDITION_MISSING + ": 3 selected row(s) skip", out)
            self.assertIn("no row ran", out)
            data = json.loads((Path(d) / "build" / "check_all.json").read_text(encoding="utf-8"))
            rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
            self.assertTrue(rows)
            self.assertEqual({r["status"] for r in rows}, {"SKIP"}, rows)


SHA = CA.EXPECTED_CODE_SHA1
# Per real row: output lines a passing run prints (shape as observed 2026-11-08), and
# variants a failing run would print. Each failing variant must be judged a problem,
# even with exit status 0: the negative test of every command row's verdict patterns.
ROW_SAMPLES = {
    "code-hash": (["text    OK  (0x359b88 bytes, want 0x359b88)", f"code.bin OK  sha1 {SHA}"],
                  [["text    FAIL  (0x359b88 bytes, want 0x359b88)", f"code.bin FAIL  sha1 {'0' * 40}"],
                   [f"code.bin OK  sha1 {'1' * 40}"],
                   ["lint: OK"]]),
    "lint": (["lint: OK"], [["lint: 2 problem(s)"], []]),
    "m1-tests": (["== summary: clean PASS, mutation PASS, shift PASS"],
                 [["== summary: clean PASS, mutation FAIL, shift PASS"], ["   mutation: PASS"]]),
    "diff-func": (["summary: 14/15 match; 0 matched row(s) failing; 0 nonmatching row(s) now match"],
                  [["summary: 13/15 match; 1 matched row(s) failing; 0 nonmatching row(s) now match"], []]),
    # Fates rows, shapes as printed 2026-11-10
    "symbols": (["Ran 16 tests in 20.670s", "", "OK"],
                [["Ran 16 tests in 20.670s", "", "FAILED (failures=1)"], ["Ran 16 tests in 20.670s"]]),
    "symbols-spotcheck": (["1. SVC wrappers: 24/24", "spotcheck: ok"],
                          [["spotcheck: 2 problem(s)"], ["1. SVC wrappers: 24/24"]]),
    "symbols-flow": (["flow selftest: 0 failures"], [["flow selftest: 2 failures"], []]),
    "tables-test": (["Ran 9 tests in 18.1s", "", "OK"], [["FAILED (errors=1)"], []]),
    "tables-gen": (["structs: compiles with arm-none-eabi-g++ (all offset/size static_asserts hold)",
                    "generated files up to date"],
                   [["docs/TABLES.md is stale: run python tools/tables/gen.py doc"], []]),
    "assets-bch": (["  PASS nonetc_mips: bu/Body.bch.lz texture 1 (HILO8, 512x512, mips 2, wrapper lz)",
                    "  PASS etc: GlobalMap/PointerSword.bch.lz texture 0 (ETC1A4, 64x128, mips 2, wrapper lz)",
                    "  PASS stored: field/x.bch.lz texture 0 (RGB565, 256x256, mips 6, wrapper stored)",
                    "  PASS resize doubled: a_st.arc 256x256 -> 512x512 (refused without --allow-resize: True)",
                    "  PASS resize halved: a_st.arc 256x256 -> 128x128 (refused without --allow-resize: True)",
                    "  PASS refuse non-power-of-two PNG: 00_tmp.png: 96x64 - both sides must be powers of two"],
                   [["  PASS nonetc_mips: a", "  FAIL etc: b", "  PASS stored: c"],
                    ["  PASS nonetc_mips: a", "  SKIP etc: no such texture", "  PASS stored: c"],
                    ["  PASS nonetc_mips: a", "  PASS stored: c"],
                    ["  PASS nonetc_mips: a", "  PASS etc: b", "  PASS stored: c"],
                    ["  PASS nonetc_mips: a", "  PASS etc: b", "  PASS stored: c", "  PASS resize doubled: x",
                     "  FAIL resize halved: y", "  PASS refuse non-power-of-two PNG: z"], []]),
    # shapes as printed 2026-11-11 by tools/assets/bchwrite.py selftest / test
    "assets-bchwrite": (["  PASS synthetic: texture 0 64x64 ETC1A4 -> 128x128 ETC1A4 mips 1, verified and restored",
                         "  PASS synthetic: two textures resized at once (one gains alpha)",
                         "  PASS synthetic: coverage scan notices removed relocations (7/7)",
                         "  PASS ROM GlobalMap/PointerSword.bch.lz: identity, coverage, 1/1 textures resized and restored"],
                        [["  PASS synthetic: two textures resized at once (one gains alpha)",
                          "  FAIL synthetic: coverage scan notices removed relocations (6/7)",
                          "  PASS ROM x: identity"],
                         ["  PASS synthetic: two textures resized at once (one gains alpha)",
                          "  PASS synthetic: coverage scan notices removed relocations (7/7)",
                          "  SKIP ROM samples: no extracted/romfs"],
                         ["  PASS synthetic: two textures resized at once (one gains alpha)",
                          "  PASS synthetic: coverage scan notices removed relocations (7/7)"], []]),
    "assets-bchwrite-all": (["BCH files: 13957 (RomFS files + .arc members)",
                             "  unedited rebuild through the relocating writer identical: 13957/13957",
                             "  relocation coverage scan clean (every non-zero GPU address word listed): 13957/13957",
                             "  textures resized (x2, or /2 when 1024 wide) + verified + restored identical: "
                             "11688/11688 (55 refused by the safety rules)",
                             "  mutation fuzz: removed relocations detected by the coverage scan: 5663/5663"],
                            [["  unedited rebuild through the relocating writer identical: 13956/13957",
                              "  relocation coverage scan clean (every non-zero GPU address word listed): 13957/13957",
                              "  textures resized (x2, or /2 when 1024 wide) + verified + restored identical: "
                              "11688/11688 (55 refused by the safety rules)"],
                             ["  unedited rebuild through the relocating writer identical: 13957/13957",
                              "  relocation coverage scan clean (every non-zero GPU address word listed): 13957/13957",
                              "  textures resized (x2, or /2 when 1024 wide) + verified + restored identical: "
                              "11687/11688 (55 refused by the safety rules)"],
                             ["  unedited rebuild through the relocating writer identical: 13957/13957",
                              "  relocation coverage scan clean (every non-zero GPU address word listed): 13957/13957",
                              "  textures resized (x2, or /2 when 1024 wide) + verified + restored identical: "
                              "11688/11688 (55 refused by the safety rules)", "  FAIL x.bch\tcoverage: y"], []]),
    "maps-test": (["Ran 16 tests in 5.1s", "", "OK"], [["FAILED (failures=1)"], ["Ran 16 tests in 5.1s"]]),
    "maps-roundtrip": (["Dispos: 185/185 byte-identical; Terrain: 109/109 byte-identical (decoded to the "
                        "spreadsheet form, read back and rebuilt in memory)"],
                       [["Dispos: 184/185 byte-identical; Terrain: 109/109 byte-identical"],
                        ["Dispos: 185/185 byte-identical; Terrain: 108/109 byte-identical"], []]),
    "assets-arc": ([".arc archives: 820/820 rebuild byte-identically from members (100.00%); 3412 members"],
                   [[".arc archives: 819/820 rebuild byte-identically from members (99.88%)"], []]),
    "assets-portrait": (["FaceData: 300 records; portrait files referenced: 800 of 887 under face/",
                         "portrait files exported to PNG and rebuilt byte-identically: 887/887 (3407 PNGs)"],
                        [["portrait files exported to PNG and rebuilt byte-identically: 886/887 (3407 PNGs)",
                          "  FAIL face/x.arc\tmismatch"],
                         ["portrait files exported to PNG and rebuilt byte-identically: 887/887 (3407 PNGs)",
                          "  FAIL edit test"], []]),
    # shapes as printed 2026-11-11 by tools/castle/test_castle.py (unittest)
    "castle-test": (["Ran 16 tests in 0.918s", "", "OK (skipped=1)"],
                    [["Ran 16 tests in 0.9s", "FAILED (failures=1)"], ["Ran 16 tests in 0.9s"], []]),
    "castle-all": (["Ran 1 test in 69.2s", "", "OK"],
                   [["Ran 1 test in 0.001s", "", "OK (skipped=1)"], ["Ran 0 tests in 0.000s", "", "OK"],
                    ["Ran 1 test in 69.2s", "FAILED (failures=1)"], []]),
    # shapes as printed 2026-11-11 by src/readable/battle/tests/
    "stance-armmini": (["arm_mini selftest: 9/9 checks passed"],
                       [["arm_mini selftest: 8/9 checks passed"], []]),
    "stance-diff": (["  stance_follow_up_damage        400 cases    0 mismatches",
                     "stance_diff: OK (5600 cases, 0 mismatches)"],
                    [["  MISMATCH stance_follow_up_damage case 3: original 5, readable 4",
                      "stance_diff: FAILED (5600 cases, 1 mismatches)"],
                     ["stance_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"],
                     ["stance_diff: OK (5600 cases, 0 mismatches)", "  MISMATCH x case 1: original 1, readable 2"],
                     []]),
    "stance-diff-long": (["stance_diff: OK (21000 cases, 0 mismatches)"],
                         [["stance_diff: FAILED (21000 cases, 2 mismatches)"],
                          ["stance_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    "triangle-diff": (["  triangle_attack_bonus          400 cases    0 mismatches",
                       "  planted bug 18 (triangle_battle.c: 'x'): caught, 61 mismatches in triangle_side_lookup",
                       "triangle_diff: planted bugs: 18/18 caught",
                       "triangle_diff: OK (5200 cases, 0 mismatches, 18/18 planted bugs caught)"],
                      [["  MISMATCH triangle_hit_bonus case 3: original [0, 1, 1, 5], readable [0, 1, 1, 4]",
                        "triangle_diff: FAILED (5200 cases, 1 mismatches, 18/18 planted bugs caught)"],
                       ["  planted bug  4 (triangle_tables.c: 'if (limit < floor)'): NOT CAUGHT",
                        "triangle_diff: planted bugs: 17/18 caught",
                        "triangle_diff: FAILED (5200 cases, 0 mismatches, 17/18 planted bugs caught)"],
                       ["triangle_diff: OK (5200 cases, 0 mismatches, 17/18 planted bugs caught)"],
                       ["triangle_diff: OK (5200 cases, 0 mismatches)"],
                       ["triangle_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"],
                       ["triangle_diff: OK (5200 cases, 0 mismatches, 18/18 planted bugs caught)",
                        "  MISMATCH x case 1: original [0, 1], readable [0, 2]"],
                       []]),
    "triangle-diff-long": (["triangle_diff: OK (19500 cases, 0 mismatches)"],
                           [["triangle_diff: FAILED (19500 cases, 2 mismatches)"],
                            ["triangle_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    "vein-diff": (["  trick_preview_marks            400 cases    0 mismatches",
                   "  planted bug 35 (vein_effect.c: 'x'): caught, 12 mismatches in trick_preview_marks",
                   "vein_diff: planted bugs: 35/35 caught",
                   "vein_diff: OK (3200 cases, 0 mismatches, 35/35 planted bugs caught)"],
                  [["  MISMATCH trick_is_access case 3: original [0, 1], readable [0, 0]",
                    "vein_diff: FAILED (3200 cases, 1 mismatches, 35/35 planted bugs caught)"],
                   ["  planted bug  5 (vein_tricks.c: 'return y != y0 - 1'): NOT CAUGHT",
                    "vein_diff: planted bugs: 34/35 caught",
                    "vein_diff: FAILED (3200 cases, 0 mismatches, 34/35 planted bugs caught)"],
                   ["vein_diff: OK (3200 cases, 0 mismatches, 34/35 planted bugs caught)"],
                   ["vein_diff: OK (3200 cases, 0 mismatches)"],
                   ["vein_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"],
                   ["vein_diff: OK (3200 cases, 0 mismatches, 35/35 planted bugs caught)",
                    "  MISMATCH x case 1: original [0, 1], readable [0, 2]"],
                   []]),
    "vein-diff-long": (["vein_diff: OK (12000 cases, 0 mismatches)"],
                       [["vein_diff: FAILED (12000 cases, 2 mismatches)"],
                        ["vein_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    "text-mods": (["Ran 26 tests in 21.7s", "", "OK"], [["FAILED (failures=2)"], []]),
    "play-tests": (["Ran 52 tests in 23.5s", "", "OK"], [["FAILED (failures=1)"], []]),
    "rando-page-tests": (["Ran 9 tests in 3.8s", "", "OK"],
                         [["Ran 9 tests in 3.8s", "", "FAILED (failures=1)"], ["Ran 0 tests in 0.000s", "", "OK"],
                          ["OK"], []]),
    "sof-path-tests": (["Ran 18 tests in 4.1s", "", "OK"],
                       [["Ran 18 tests in 4.1s", "", "FAILED (failures=1)"], ["Ran 0 tests in 0.000s", "", "OK"],
                        ["OK"], []]),
    "randomizer-tests": (["Ran 17 tests in 13.7s", "", "OK (skipped=4)"],
                         [["Ran 17 tests in 13.7s", "", "FAILED (errors=1)"], ["Ran 0 tests in 0.000s", "", "OK"],
                          ["OK"], []]),
    "rando-tracks-tests": (["Ran 87 tests in 120.0s", "", "OK"],
                           [["Ran 87 tests in 120.0s", "", "FAILED (failures=1)"], ["Ran 0 tests in 0.000s", "", "OK"],
                            ["OK"], []]),
    "rando-ingame-tests": (["Ran 8 tests in 42.4s", "", "OK"],
                           [["Ran 8 tests in 42.4s", "", "FAILED (errors=1)"], ["Ran 0 tests in 0.000s", "", "OK"],
                            ["OK"], []]),
    "rando-more-tracks-tests": (["Ran 82 tests in 30.5s", "", "OK"],
                                [["Ran 82 tests in 30.5s", "", "FAILED (failures=1)"],
                                 ["Ran 0 tests in 0.000s", "", "OK"], ["OK"], []]),
    "rando-r56-tracks-tests": (["Ran 62 tests in 60.1s", "", "OK"],
                               [["Ran 62 tests in 60.1s", "", "FAILED (errors=1)"],
                                ["Ran 0 tests in 0.000s", "", "OK"], ["OK"], []]),
    "rando-recruit-tests": (["Ran 14 tests in 91.2s", "", "OK"],
                            [["Ran 14 tests in 91.2s", "", "FAILED (failures=1)"],
                             ["Ran 0 tests in 0.000s", "", "OK"], ["OK"], []]),
    "rando-r62-tracks-tests": (["Ran 17 tests in 12.2s", "", "OK"],
                               [["Ran 17 tests in 12.2s", "", "FAILED (failures=1)"],
                                ["Ran 0 tests in 0.000s", "", "OK"], ["OK"], []]),
    "rando-r63-boss-might": (["Ran 9 tests in 4.1s", "", "OK"],
                             [["Ran 9 tests in 4.1s", "", "FAILED (failures=1)"],
                              ["Ran 0 tests in 0.000s", "", "OK"], ["OK"], []]),
    "rando-r64-seal-bosses": (["Ran 7 tests in 1.2s", "", "OK"],
                              [["Ran 7 tests in 1.2s", "", "FAILED (failures=1)"],
                               ["Ran 0 tests in 0.000s", "", "OK"], ["OK"], []]),
    "rando-seal-tests": (["Ran 11 tests in 140.7s", "", "OK"],
                         [["Ran 11 tests in 140.7s", "", "FAILED (failures=1)"],
                          ["Ran 0 tests in 0.000s", "", "OK"], ["OK"], []]),
    "rando-ingame-core": (["running 174 tests", "test result: ok. 174 passed; 0 failed; 0 ignored; 0 measured; "
                           "0 filtered out; finished in 3.21s"],
                          [["test result: FAILED. 173 passed; 1 failed; 0 ignored"],
                           ["test result: ok. 0 passed; 0 failed; 0 ignored"],
                           ["error[E0425]: cannot find value `x` in this scope",
                            "test result: ok. 174 passed; 0 failed; 0 ignored"], []]),
    "rando-ingame-page": (["running 17 tests", "test result: ok. 17 passed; 0 failed; 0 ignored; 0 measured; "
                           "64 filtered out; finished in 0.40s"],
                          [["test result: FAILED. 16 passed; 1 failed; 0 ignored"],
                           ["test result: ok. 0 passed; 0 failed; 0 ignored"], []]),
    "game-picker-page": (["running 9 tests", "test result: ok. 9 passed; 0 failed; 0 ignored; 0 measured; "
                          "81 filtered out; finished in 0.31s"],
                         [["test result: FAILED. 8 passed; 1 failed; 0 ignored"],
                          ["test result: ok. 0 passed; 0 failed; 0 ignored"],
                          ["error[E0599]: no method named `apply_choice` found",
                           "test result: ok. 9 passed; 0 failed; 0 ignored"], []]),
    "watchdog-tests": (["Ran 12 tests in 0.125s", "", "OK"],
                       [["Ran 12 tests in 0.125s", "", "FAILED (failures=1)"], ["Ran 0 tests in 0.000s", "", "OK"],
                        ["OK"], []]),
    "engine-selftest": (["  PASS  port: no section for this game = None", "engine selftest: 24/24"],
                        [["  FAIL  apply: 0003 refused", "engine selftest: 23/24"],
                         ["  FAIL  x", "engine selftest: 24/24"], []]),
    "gen-headers": (["problems: 0 (see report)", "RESULT: PASS"], [["problems: 3", "RESULT: FAIL"], []]),
    "rom-rebuild": (["regions: 48 match, 0 differ or missing (of 48 in the original)",
                     "VERDICT: BYTE-IDENTICAL (3s)"],
                    [["regions: 47 match, 1 differ or missing", "VERDICT: DIFFERENT"], []]),
    "rom-tests": (["  PASS  blz round trip", "3/3 checks passed"],
                  [["  FAIL  blz round trip", "2/3 checks passed"], ["  FAIL  x", "3/3 checks passed"],
                   ["2/3 checks passed"]]),
    "assets-quick": (["ASSETS QUICK: 104/104 sampled files identical through the chain (44 groups)"],
                     [["ASSETS QUICK: 103/104 sampled files identical through the chain (44 groups)"],
                      ["ASSETS QUICK: 104/1045 sampled files identical"], []]),
    "assets-full": (["ALL STAGES 100%"], [["  lz     LZ11 files recompress identically  856/857  99.88%"], []]),
    "tables-check": (["Person  63 file(s)  805 records: OK", "22/22 layouts pass (307 fields)",
                      "self-test: 72/72 mutated layouts rejected"],
                     [["21/22 layouts pass (307 fields)", "self-test: 72/72 mutated layouts rejected"],
                      ["22/22 layouts pass (307 fields)", "self-test: 71/72 mutated layouts rejected"],
                      ["22/22 layouts pass (307 fields)"], []]),
    "tables-rebuild": (["rebuilt 64 container file(s) from 84 table dumps: 64/64 byte-identical to the original RomFS files"],
                       [["rebuilt 64 container file(s) from 84 table dumps: 63/64 byte-identical to the original RomFS files"],
                        []]),
    "mods-selftest": (["  PASS  an unedited mod (all 22 tables) stages nothing  (22 tables copied, 0 file(s) staged)",
                       "mods selftest: 13/13 checks passed"],
                      [["  FAIL  conflicts: same cell in two mods is refused", "mods selftest: 12/13 checks passed"],
                       ["  FAIL  x", "mods selftest: 13/13 checks passed"],
                       ["mods selftest: 12/13 checks passed"], []]),
    "selftest": (["Ran 27 tests in 11.9s", "", "OK"], [["Ran 27 tests in 11.9s", "FAILED (failures=1)"], []]),
    # shape as printed 2026-11-09 by tools/readable/check.py --selftest
    # 79/79 since robot round 6 (2026-11-13: h4a fails on any bad live record, stage folders read)
    "harness-selftest": (["harness selftest: 79/79 checks passed"],
                         [["  FAIL  a damaged record (exit) is unfaithful", "harness selftest: 78/79 checks passed"],
                          ["  FAIL  h4a live gate finds every MISMATCH function", "harness selftest: 78/79 checks passed"],
                          ["  FAIL  x", "harness selftest: 79/79 checks passed"], []]),
    # shapes as printed 2026-11-12 by the robot's tools (tools/harness/)
    # 28/28 since robot round 6 (2026-11-13: forge ranks 2..63 with flag bits, repeated person ids "6", "6#2")
    # shapes as printed 2026-11-14 (round 9 fixes area's self-tests)
    "build-selftest": (["harness build self-test: 22/22 checks passed (fake 3dsrecomp)"],
                       [["  FAIL  --swap: old DLL renamed aside", "harness build self-test: 21/22 checks passed"],
                        ["harness build self-test: 21/22 checks passed (fake 3dsrecomp)"], []]),
    "fastlook-selftest": (["  ok   judge: no copy finished -> DIFFERENT", "fastlook selftest: 32/32 ok"],
                          [["  FAIL judge: copies equal but not the clean line -> DIFFERENT", "fastlook selftest: 31/32 ok"],
                           ["  FAIL x", "fastlook selftest: 32/32 ok"], []]),
    "splitcfg-selftest": (["splitcfg selftest: 10/10 ok"],
                          [["  FAIL refused: the section not an object", "splitcfg selftest: 9/10 ok"], []]),
    "offline-selftest": (["offline selftest: OK"],
                         [["FAIL: compare exit code", "offline selftest: OK"], ["offline selftest: 2 failure(s)"], []]),
    "h6cache-selftest": (["h6cache self-test: 15/15 checks passed"],
                         [["h6cache self-test: 14/15 checks passed"],
                          ["Traceback (most recent call last):", "h6cache self-test: 15/15 checks passed"], []]),
    # shape as printed 2026-11-15 by tools/harness/h6sample.py --selftest (H6 sampled mode, F-024)
    "h6sample-selftest": (["h6sample self-test: 15/15 checks passed"],
                          [["  FAIL  greedy cover takes the widest path first", "h6sample self-test: 14/15 checks passed"],
                           ["  FAIL  x", "h6sample self-test: 15/15 checks passed"],
                           ["Traceback (most recent call last):", "h6sample self-test: 15/15 checks passed"], []]),
    "testcache-selftest": (["  ok   a FAIL is never stored", "testcache selftest: 8/8 ok"],
                           [["  FAIL a FAIL is never stored", "testcache selftest: 7/8 ok"], []]),
    "markers-selftest": (["markers self-test: 28/28 checks passed"],
                         [["  FAIL  gold read", "markers self-test: 17/18 checks passed"],
                          ["  FAIL  levels: person 6 lv", "markers self-test: 23/24 checks passed"],
                          ["  FAIL  forged: kind 8 is not a weapon", "markers self-test: 24/25 checks passed"],
                          ["  FAIL  forged: rank 63 with flag bits", "markers self-test: 27/28 checks passed"],
                          ["  FAIL  x", "markers self-test: 28/28 checks passed"], []]),
    # shape as printed 2026-11-13 by tools/harness/levelups.py --selftest
    "harness-levelups": (["levelups self-test: 3/3 checks passed"],
                         [["  FAIL  level-up found", "levelups self-test: 1/2 checks passed"],
                          ["  FAIL  x", "levelups self-test: 2/2 checks passed"],
                          ["  FAIL  repeated person id kept apart", "levelups self-test: 2/3 checks passed"],
                          ["Traceback (most recent call last):", "levelups self-test: 3/3 checks passed"], []]),
    # shapes as printed 2026-11-13 by tools/harness/cheats.py (robot round 6)
    "cheats-selftest": (["cheats self-test: 23/23 checks passed"],
                        [["  FAIL  stage plan (x)", "cheats self-test: 22/23 checks passed"],
                         ["  FAIL  x", "cheats self-test: 23/23 checks passed"],
                         ["Traceback (most recent call last):", "cheats self-test: 23/23 checks passed"], []]),
    "rando-colours-tests": (["Ran 14 tests in 3.2s", "", "OK"],
                            [["Ran 14 tests in 3.2s", "", "FAILED (failures=1)"], ["Ran 0 tests in 0.000s", "", "OK"],
                             ["OK"], []]),
    "rando-cache-tests": (["Ran 9 tests in 238.0s", "", "OK"],
                          [["Ran 9 tests in 238.0s", "", "FAILED (errors=1)"], ["Ran 0 tests in 0.000s", "", "OK"],
                           ["OK"], []]),
    "engine-seal-person-name": (["test result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 182 filtered out"],
                                [["test result: FAILED. 1 passed; 1 failed; 0 ignored"],
                                 ["error[E0425]: cannot find function", "test result: ok. 2 passed; 0 failed"],
                                 ["test result: ok. 0 passed; 0 failed"], []]),
    "engine-seal-person-order": (["test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 191 filtered out"],
                                 [["test result: FAILED. 2 passed; 1 failed; 0 ignored"],
                                  ["error[E0425]: cannot find function", "test result: ok. 3 passed; 0 failed"],
                                  ["test result: ok. 2 passed; 0 failed"], []]),
    "engine-nuzlocke-core": (["test result: ok. 9 passed; 0 failed; 0 ignored; 0 measured; 188 filtered out"],
                             [["test result: FAILED. 8 passed; 1 failed; 0 ignored"],
                              ["error[E0425]: cannot find function", "test result: ok. 9 passed; 0 failed"],
                              ["test result: ok. 6 passed; 0 failed"], ["test result: ok. 0 passed; 0 failed"], []]),
    # shapes as printed 2026-11-21 (round 61 assemble: cargo test, audioproof.py selftest)
    "engine-pagebot-hook": (["test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 92 filtered out"],
                            [["test result: FAILED. 0 passed; 1 failed; 0 ignored"],
                             ["error[E0425]: cannot find function", "test result: ok. 1 passed; 0 failed"],
                             ["test result: ok. 0 passed; 0 failed"], []]),
    "audioproof-selftest": (["audioproof selftest: same 0.999 other -0.036 OK"],
                            [["audioproof selftest: same 0.512 other -0.036 FAIL"],
                             ["Traceback (most recent call last):", "audioproof selftest: same 0.999 other -0.036 OK"],
                             ["audioproof selftest: same 0.999 other 0.950 FAIL"], []]),
    # round 67 integrate: the smoke tool's synthetic selftest (fast, in --core) and the live set (slow)
    "smoke-selftest": (["...................", "Ran 19 tests in 4.774s", "", "OK", "smoke selftest: 19/19 ok"],
                       [["Ran 19 tests in 4.8s", "FAILED (failures=1)", "smoke selftest: 18/19 ok FAIL"],
                        ["FAIL: test_window (tests.test_smoke.Pool.test_window)", "smoke selftest: 19/19 ok"],
                        ["ERROR: test_exit_codes (tests.test_smoke.Judge.test_exit_codes)", "smoke selftest: 19/19 ok"],
                        ["Ran 0 tests in 0.000s", "OK", "smoke selftest: 0/0 ok FAIL"],
                        ["smoke selftest: 18/19 ok"], []]),
    # round 68 integrate: the release tool's selftest (three unit modules side by side; medium, in --core)
    "release-selftest": (["release selftest: 111/111 tests passed (test_release 54/54, test_package 21/21, "
                          "test_install 36/36)"],
                         [["--- tests.test_package (exit 1) ---", "FAILED (failures=1)",
                           "release selftest: 110/111 tests passed (test_release 54/54, test_package 20/21, "
                           "test_install 36/36) FAIL"],
                          ["Traceback (most recent call last):",
                           "release selftest: 111/111 tests passed (test_release 54/54, test_package 21/21, "
                           "test_install 36/36)"],
                          ["release selftest: 0/0 tests passed () FAIL"],
                          ["release selftest: 0/0 tests passed ()"],
                          ["release selftest: 110/111 tests passed"], []]),
    "smoke-set": (["smoke: 8 tasks, 2 lanes, output build/smoke/20261126-120000",
                   "| bt-A011-off | PASS | 42.7 | build/smoke/20261126-120000/jobs/bt-A011-off/result.json |",
                   "PASS: jobs 6/6, memory compare equal, baseline equal (103.9 s)"],
                  [["MISMATCH: job rv-C012-off: verdict FAIL, baseline PASS",
                    "FAIL: jobs 5/6 PASS; 1 baseline mismatch(es) (110.2 s)"],
                   ["MISMATCH: memory mem-off: frame_end frame 4600: range 1 differs",
                    "PASS: jobs 6/6, memory compare equal, baseline equal (103.9 s)"],
                   ["PASS: jobs 8/8, memory compare equal, baseline equal (103.9 s)"],
                   ["FAIL: 9 input problem(s)"],
                   ["FAIL: no baseline (config/harness/smoke_baseline.json): take one with --write-baseline"],
                   ["PARTIAL (--only bt-A011-off; not the whole set): PASS: jobs 1/1, memory compare equal, "
                    "baseline equal (40.0 s)"],
                   ["STOPPED (build/STOP_ROUND) (12.0 s)"],
                   ["PASS: jobs 7/7, memory compare equal, baseline equal (90.0 s)"], []]),
    "seal-smoke": (["smoke: 3 tasks, 2 lanes, output build/smoke/20261126-130000",
                    "| seal-R011-off | PASS | 44.1 | build/smoke/20261126-130000/jobs/seal-R011-off/result.json |",
                    "PASS: jobs 2/2, baseline equal (no memory compare in this set) (61.0 s)"],
                   [["MISMATCH: job seal-R011-off: verdict FAIL, baseline PASS",
                     "FAIL: jobs 1/2 PASS; 1 baseline mismatch(es) (60.2 s)"],
                    ["FAIL: no baseline (config/seal/smoke_baseline.json): take one with --write-baseline"],
                    ["PARTIAL (--only seal-R011-off; not the whole set): PASS: jobs 1/1, baseline equal (no memory "
                     "compare in this set) (40.0 s)"],
                    ["PASS: jobs 6/6, memory compare equal, baseline equal (103.9 s)"],
                    ["STOPPED (build/STOP_ROUND) (12.0 s)"], []]),
    "pagebot-selftest": (["pagebot selftest: 9/9"],
                         [["pagebot selftest: 8/9", "FAIL no hook refused"],
                          ["FAIL x", "pagebot selftest: 9/9"],
                          ["Traceback (most recent call last):", "pagebot selftest: 9/9"], []]),
    "rcheck-selftest": (["rcheck selftest: 18/18"],
                        [["rcheck selftest: 17/18", "  FAIL pair (x)"],
                         ["  FAIL x", "rcheck selftest: 18/18"],
                         ["Traceback (most recent call last):", "rcheck selftest: 18/18"], []]),
    "chapsel-selftest": (["chapsel selftest: 26/26"],
                         [["chapsel selftest: 25/26", "  FAIL plan A015 (x)"],
                          ["  FAIL x", "chapsel selftest: 26/26"],
                          ["Traceback (most recent call last):", "chapsel selftest: 26/26"], []]),
    "cheat-routes": (["cheat-forge-katana: from bt-ch8-clear, 1 poke(s): frame 3500 x = 1",
                      "cheat-katana-reload: from cheat-castle-katana, 0 poke(s): ",
                      "real-play start saves: 14 packed one(s) checked, none carries cheat state",
                      "cheats: 4 cheat route(s), rules OK"],
                     [["cheats: route title: start save x is a cheat save (named cheat-*)"],
                      ["cheats: route cheat-x: a cheat route without pokes must start from a cheat save"],
                      ["Traceback (most recent call last):", "cheats: 4 cheat route(s), rules OK"],
                      ["cheats: route title: start save x is a cheat save (named cheat-*)",
                       "cheats: 4 cheat route(s), rules OK"], []]),
    "headless-selftest": (["headless self-test: 60/60 checks passed"],
                          [["  FAIL  headless: lz4 long zero run", "headless self-test: 59/60 checks passed"],
                           ["  FAIL  x", "headless self-test: 60/60 checks passed"], []]),
    # 34 tests since robot round 6 (2026-11-13: capture verdicts, the OS lock, LaunderTests x4)
    "parallel-tests": ([".................................", "Ran 34 tests in 30.9s", "", "OK"],
                       [["Ran 24 tests in 3.2s", "", "FAILED (failures=1)"],
                        ["Ran 0 tests in 0.000s", "", "OK"], ["OK"], []]),
    "parallel-smoke": (["Ran 24 tests in 3.2s", "", "OK",
                        "smoke: determinism --route title --copies 3 --jobs 3 --serial-too --session smoke-title",
                        "smoke: PASS: side by side 9.1 s, one after another 17.5 s (x1.92); peaks [690, 688, 701] MB; "
                        "memory c3cbbe48a0d1e2f3"],
                       [["Ran 24 tests in 3.2s", "", "OK", "smoke: FAIL (no summary: [Errno 2] x)"],
                        ["Ran 24 tests in 3.2s", "", "OK", "smoke: FAIL: side by side 9.1 s, one after another 17.5 s"],
                        ["Ran 24 tests in 3.2s", "", "FAILED (errors=1)"],
                        ["Ran 24 tests in 3.2s", "", "OK"], []]),
    "formula-diff": (["  unit_attack                        300 cases    0 mismatches  (15 early give-ups)",
                      "  planted bug 30 (formula_forecast.c: 'x'): caught, 7 mismatches in forecast_hit",
                      "formula_diff: planted bugs: 30/30 caught",
                      "formula_diff: OK (6900 cases, 0 mismatches, 30/30 planted bugs caught)"],
                     [["  MISMATCH unit_hit case 3: original [1], readable [2]",
                       "formula_diff: FAILED (6900 cases, 1 mismatches, 30/30 planted bugs caught)"],
                      ["  planted bug  4 (formula_unit.c: 'x'): NOT CAUGHT",
                       "formula_diff: planted bugs: 29/30 caught",
                       "formula_diff: FAILED (6900 cases, 0 mismatches, 29/30 planted bugs caught)"],
                      ["formula_diff: OK (6900 cases, 0 mismatches, 29/30 planted bugs caught)"],
                      ["formula_diff: OK (6900 cases, 0 mismatches)"],
                      ["  unit_hit                             3 cases the ARM interpreter could not run (counted as failures)",
                       "formula_diff: OK (6900 cases, 0 mismatches, 30/30 planted bugs caught)"],
                      ["  unit_crit_avoid                    300 cases    0 mismatches  (300 early give-ups)",
                       "formula_diff: OK (6900 cases, 0 mismatches, 30/30 planted bugs caught)"],
                      ["  forecast_strikes                   300 cases    0 mismatches  "
                       "(4 cold: both reached / gave up at the cache; 92 early give-ups)",
                       "formula_diff: OK (6900 cases, 0 mismatches, 30/30 planted bugs caught)"],
                      ["formula_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    "formula-diff-long": (["  unit_attack                       1000 cases    0 mismatches  (299 early give-ups)",
                           "  unit_hit                          1000 cases    0 mismatches  (4 cold: both reached / "
                           "gave up at the cache; 51 early give-ups)",
                           "formula_diff: OK (23000 cases, 0 mismatches)"],
                          [["formula_diff: FAILED (23000 cases, 2 mismatches)"],
                           ["  unit_crit_avoid                   1000 cases    0 mismatches  (1000 early give-ups)",
                            "formula_diff: OK (23000 cases, 0 mismatches)"],
                           ["  unit_attack                       1000 cases    0 mismatches  (300 early give-ups)",
                            "formula_diff: OK (23000 cases, 0 mismatches)"],
                           ["formula_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    # shapes as printed 2026-11-12 by src/readable/unit/tests/growth_diff.py (37 planted bugs since 2026-11-13:
    # review 4, a nested give-up is a mismatch)
    "growth-diff": (["growth_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261112",
                     "  unit_grow                          300 cases    0 mismatches  (12 early give-ups)",
                     "  planted bug 37 (growth_exp.c: 'x'): caught, 12 mismatches in unit_dual_exp_damage",
                     "growth_diff: planted bugs: 37/37 caught",
                     "growth_diff: OK (7800 cases, 0 mismatches, 37/37 planted bugs caught)"],
                    [["  MISMATCH unit_exp_damage case 3: original [0, 12], readable [0, 13]; ov:x 0x1",
                      "growth_diff: FAILED (7800 cases, 1 mismatches, 36/36 planted bugs caught)"],
                     ["  planted bug  4 (growth_rates.c: 'x'): NOT CAUGHT",
                      "growth_diff: planted bugs: 35/36 caught",
                      "growth_diff: FAILED (7800 cases, 0 mismatches, 35/36 planted bugs caught)"],
                     ["growth_diff: OK (7800 cases, 0 mismatches, 35/36 planted bugs caught)"],
                     ["growth_diff: OK (7800 cases, 0 mismatches)"],
                     ["  unit_grow                            3 cases the ARM interpreter could not run (counted as failures)",
                      "growth_diff: OK (7800 cases, 0 mismatches, 36/36 planted bugs caught)"],
                     ["  unit_exp_rod                       300 cases    0 mismatches  (90 early give-ups)",
                      "growth_diff: OK (7800 cases, 0 mismatches, 36/36 planted bugs caught)"],
                     ["growth_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"],
                     ["growth_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    "growth-diff-long": (["  unit_grow                         1500 cases    0 mismatches  (449 early give-ups)",
                          "growth_diff: OK (39000 cases, 0 mismatches)"],
                         [["growth_diff: FAILED (39000 cases, 2 mismatches)"],
                          ["  unit_grow                         1500 cases    0 mismatches  (450 early give-ups)",
                           "growth_diff: OK (39000 cases, 0 mismatches)"],
                          ["  unit_grow                         1500 cases    0 mismatches  (1500 early give-ups)",
                           "growth_diff: OK (39000 cases, 0 mismatches)"],
                          ["growth_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    # shapes as printed 2026-11-13 by src/readable/skill/tests/skill_diff.py
    "skill-diff": (["skill_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261113",
                    "  battle_attack_skill_pick           300 cases    0 mismatches  "
                    "(28 cold: both reached / gave up at the cache; 30 early give-ups)",
                    "  battle_attack_skill_pick             1 distinct results, 0 not 0, 46 with a skill activated, 10 draws",
                    "  planted bug 34 (skill_battle.c: 'x'): caught, 5 mismatches in battle_attack_skill_pick",
                    "skill_diff: planted bugs: 34/34 caught",
                    "skill_diff: OK (5100 cases, 0 mismatches, 34/34 planted bugs caught)"],
                   [["  MISMATCH unit_has_skill case 3: original [1], readable [0]; x",
                     "skill_diff: FAILED (5100 cases, 1 mismatches, 32/32 planted bugs caught)"],
                    ["  planted bug  4 (skill_has.c: 'x'): NOT CAUGHT",
                     "skill_diff: planted bugs: 31/32 caught",
                     "skill_diff: FAILED (5100 cases, 0 mismatches, 31/32 planted bugs caught)"],
                    ["skill_diff: OK (5100 cases, 0 mismatches, 31/32 planted bugs caught)"],
                    ["skill_diff: OK (5100 cases, 0 mismatches)"],
                    ["  unit_skill_chance                    3 cases the ARM interpreter could not run (counted as failures)",
                     "skill_diff: OK (5100 cases, 0 mismatches, 32/32 planted bugs caught)"],
                    ["  battle_attack_skill_pick           300 cases    0 mismatches  "
                     "(28 cold: both reached / gave up at the cache; 90 early give-ups)",
                     "skill_diff: OK (5100 cases, 0 mismatches, 32/32 planted bugs caught)"],
                    ["skill_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"],
                    ["skill_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    "skill-diff-long": (["  battle_attack_skill_pick          1500 cases    0 mismatches  (144 early give-ups)",
                         "skill_diff: OK (25500 cases, 0 mismatches)"],
                        [["skill_diff: FAILED (25500 cases, 2 mismatches)"],
                         ["  battle_attack_skill_pick          1500 cases    0 mismatches  (450 early give-ups)",
                          "skill_diff: OK (25500 cases, 0 mismatches)"],
                         ["  unit_has_skill                    1500 cases    0 mismatches  (1500 early give-ups)",
                          "skill_diff: OK (25500 cases, 0 mismatches)"],
                         ["skill_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    # shapes as printed 2026-11-14 by src/readable/menu/tests/menu_diff.py (menus batch)
    "menu-diff": (["menu_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261114",
                   "  battle_picture_choice              300 cases    0 mismatches  (38 early give-ups)",
                   "  planted bug 41 (menu_danger.c: 'x'): caught, 12 mismatches in danger_tile_kind",
                   "menu_diff: planted bugs: 41/41 caught",
                   "menu_diff: OK (6600 cases, 0 mismatches, 41/41 planted bugs caught)"],
                  [["  MISMATCH config_danger_value case 3: original [1], readable [0]; x",
                    "menu_diff: FAILED (6600 cases, 1 mismatches, 41/41 planted bugs caught)"],
                   ["  planted bug  4 (menu_config.c: 'x'): NOT CAUGHT",
                    "menu_diff: planted bugs: 40/41 caught",
                    "menu_diff: FAILED (6600 cases, 0 mismatches, 40/41 planted bugs caught)"],
                   ["menu_diff: OK (6600 cases, 0 mismatches, 40/41 planted bugs caught)"],
                   ["menu_diff: OK (6600 cases, 0 mismatches)"],
                   ["  config_item_value                    3 cases the ARM interpreter could not run (counted as failures)",
                    "menu_diff: OK (6600 cases, 0 mismatches, 41/41 planted bugs caught)"],
                   ["  battle_picture_choice              300 cases    0 mismatches  (90 early give-ups)",
                    "menu_diff: OK (6600 cases, 0 mismatches, 41/41 planted bugs caught)"],
                   ["menu_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"],
                   ["menu_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    "menu-diff-long": (["  battle_picture_choice             1500 cases    0 mismatches  (183 early give-ups)",
                        "menu_diff: OK (33000 cases, 0 mismatches)"],
                       [["menu_diff: FAILED (33000 cases, 2 mismatches)"],
                        ["  battle_picture_choice             1500 cases    0 mismatches  (450 early give-ups)",
                         "menu_diff: OK (33000 cases, 0 mismatches)"],
                        ["  danger_tile_kind                  1500 cases    0 mismatches  (1500 early give-ups)",
                         "menu_diff: OK (33000 cases, 0 mismatches)"],
                        ["menu_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    # shapes as printed 2026-11-13 by the writers stage's tests (round 7)
    "writer-gate": (["gate test: 244/244 checks passed",
                     "  planted bug 17 ('x'): caught (gate test: 243/244 checks passed)",
                     "writer_gate_test: planted bugs: 17/17 caught",
                     "writer_gate_test: OK (source checks clean, 17/17 planted bugs caught)"],
                    [["  FAIL line 120: fe_writer_log_count() == 0", "gate test: 243/244 checks passed",
                      "writer_gate_test: OK (source checks clean, 17/17 planted bugs caught)"],
                     ["gate test: 244/244 checks passed", "  planted bug  5 ('x'): NOT CAUGHT",
                      "writer_gate_test: FAILED (source checks clean, 16/17 planted bugs caught)"],
                     ["gate test: 244/244 checks passed",
                      "writer_gate_test: OK (source checks clean, 16/17 planted bugs caught)"],
                     ["gate test: 244/244 checks passed", "writer_gate_test: OK (source checks clean)"],
                     ["  planted bug  3: does not build (fix the plant): x", "gate test: 244/244 checks passed",
                      "writer_gate_test: OK (source checks clean, 17/17 planted bugs caught)"],
                     ["  writer config_options is armed (armed=1) in writer.c",
                      "writer_gate_test: SKIPPED the C part (no host C compiler; set FE_HOST_CC)"],
                     ["writer_gate_test: OK (source checks clean, 17/17 planted bugs caught)"], []]),
    "writer-diff": (["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against "
                     "config_write_options through the writer gate, seed 20261114",
                     "  on           300 cases    0 mismatches",
                     "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone (a callee's store "
                     "logged and undone), 19 that had to roll back",
                     "  planted bug 25 (writer.c: 'x'): caught, 3 mismatches in on",
                     "writer_diff: planted bugs: 25/25 caught",
                     "writer_diff: OK (600 cases, 0 mismatches, 25/25 planted bugs caught)"],
                    [["  MISMATCH case 12 (on):", "writer_diff: exercised: 234 cases that stored, 77 that rebuilt "
                      "the zone", "writer_diff: FAILED (600 cases, 1 mismatches, 25/25 planted bugs caught)"],
                     ["writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                      "  planted bug  2 (menu_config_writer.c: 'x'): NOT CAUGHT",
                      "writer_diff: OK (600 cases, 0 mismatches, 24/25 planted bugs caught)"],
                     ["writer_diff: exercised: 0 cases that stored, 0 that rebuilt the zone",
                      "writer_diff: OK (600 cases, 0 mismatches, 25/25 planted bugs caught)"],
                     ["writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                      "writer_diff: OK (600 cases, 0 mismatches)"],
                     ["writer_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    "writer-diff-long": (["writer_diff: exercised: 1202 cases that stored, 350 that rebuilt the zone (a callee's "
                          "store logged and undone), 101 that had to roll back",
                          "writer_diff: OK (3000 cases, 0 mismatches)"],
                         [["writer_diff: exercised: 1202 cases that stored, 350 that rebuilt the zone",
                           "writer_diff: FAILED (3000 cases, 2 mismatches)"],
                          ["writer_diff: OK (3000 cases, 0 mismatches)"],
                          ["writer_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    "oka-host-seed1": (["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against config_write_options through the writer gate, seed 1",
                        "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                        "writer_diff: planted bugs: 25/25 caught",
                        "writer_diff: OK (600 cases, 0 mismatches, 25/25 planted bugs caught)"],
                       [["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against config_write_options through the writer gate, seed 2",
                         "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                         "writer_diff: OK (600 cases, 0 mismatches, 25/25 planted bugs caught)"],
                        ["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against config_write_options through the writer gate, seed 1", "  MISMATCH case 3 (on):",
                         "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                         "writer_diff: FAILED (600 cases, 1 mismatches, 25/25 planted bugs caught)"],
                        ["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against config_write_options through the writer gate, seed 1", "  planted bug  7 (writer.c: 'x'): NOT CAUGHT",
                         "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                         "writer_diff: OK (600 cases, 0 mismatches, 24/25 planted bugs caught)"],
                        ["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against config_write_options through the writer gate, seed 1", "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                         "writer_diff: OK (600 cases, 0 mismatches)"],
                        ["writer_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    "oka-host-seed2": (["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against config_write_options through the writer gate, seed 2",
                        "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                        "writer_diff: planted bugs: 25/25 caught",
                        "writer_diff: OK (600 cases, 0 mismatches, 25/25 planted bugs caught)"],
                       [["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against config_write_options through the writer gate, seed 1",
                         "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                         "writer_diff: OK (600 cases, 0 mismatches, 25/25 planted bugs caught)"],
                        ["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against config_write_options through the writer gate, seed 2", "  MISMATCH case 3 (on):",
                         "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                         "writer_diff: FAILED (600 cases, 1 mismatches, 25/25 planted bugs caught)"],
                        ["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against config_write_options through the writer gate, seed 2", "  planted bug  7 (writer.c: 'x'): NOT CAUGHT",
                         "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                         "writer_diff: OK (600 cases, 0 mismatches, 24/25 planted bugs caught)"],
                        ["writer_diff: the game's GetValue / SetValue (arm_mini.py on extracted/text.bin) against config_write_options through the writer gate, seed 2", "writer_diff: exercised: 234 cases that stored, 77 that rebuilt the zone",
                         "writer_diff: OK (600 cases, 0 mismatches)"],
                        ["writer_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # shapes as printed 2026-11-18 by src/readable/menu/tests/w12_diff.py (round 35, F-034)
    "w12-host-seed1": (["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118",
                        'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize',
                        "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)",
                        "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model",
                        "w12_diff: planted bugs: 34/34 caught",
                        'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                       [["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", "  MISMATCH case 3 (on):", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model",
                         "w12_diff: FAILED (300 scenarios, 1 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)"],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", "  options MISMATCH x: expected 1, the reader gave 0", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", "  CLEAN-SAVE MISMATCH case 4: a save differs from the game's own with no options file", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", "  planted bug 7 (menu_options_hook.c: 'x'): NOT CAUGHT", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model",
                         "w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 33/34 planted bugs caught)"],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", "w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 0 where W2 could not and restored, 96 with a Deserialize inside a Serialize", "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 2 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 1 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", "w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0)"],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model",
                         "w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 26/26 planted bugs caught)"],   # round 38: the plant list shrank below the floor (34 since round 40)
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", 'w12_diff: exercised: 84 scenarios where W1 stored, 74 where W2 wrote a save itself, 10 where W2 could not and restored, 84 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model",
                         "w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 32/32 planted bugs caught)"],   # round 40: round 38's 32-plant list (no apply plants) no longer passes
                        ["w12_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    "w12-host-seed2": (["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2",
                        'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize',
                        "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)",
                        "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model",
                        "w12_diff: planted bugs: 34/34 caught",
                        'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                       [["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 20261118", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", "  MISMATCH case 3 (on):", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model",
                         "w12_diff: FAILED (300 scenarios, 1 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)"],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", "  options MISMATCH x: expected 1, the reader gave 0", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", "  CLEAN-SAVE MISMATCH case 4: a save differs from the game's own with no options file", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", "  planted bug 7 (menu_options_hook.c: 'x'): NOT CAUGHT", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model",
                         "w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 33/34 planted bugs caught)"],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", "w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 0 where W2 could not and restored, 96 with a Deserialize inside a Serialize", "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 2 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 1 differ from the game's own saves with no options file, 0 differ from section 4's model", 'w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 34/34 planted bugs caught)'],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model", "w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0)"],
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", 'w12_diff: exercised: 166 scenarios where W1 stored, 75 where W2 wrote a save itself, 10 where W2 could not and restored, 96 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model",
                         "w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 26/26 planted bugs caught)"],   # round 38: the plant list shrank below the floor (34 since round 40)
                        ["w12_diff: the game's Reset / Deserialize / Serialize / SetValue (arm_mini.py on extracted/text.bin) composed by OPTIONS_WIRING section 4, against W1/W2 through the writer gate, seed 2", 'w12_diff: exercised: 84 scenarios where W1 stored, 74 where W2 wrote a save itself, 10 where W2 could not and restored, 84 with a Deserialize inside a Serialize', "w12_diff: unarmed table (no -DFE_WRITER_TESTS, FE_WRITERS lists all three, readable mode): 300 scenarios, 0 mismatches (nothing stored, no session, the game's saves)", "w12_diff: clean saves: 150 scenarios (150 with an apply, 261 suspend saves, each followed by a game save): 0 differ from the game's own saves with no options file, 0 differ from section 4's model",
                         "w12_diff: OK (300 scenarios, 0 mismatches; unarmed 0; options 0; clean saves 0; 32/32 planted bugs caught)"],   # round 40: round 38's 32-plant list (no apply plants) no longer passes
                        ["w12_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    "w12-options": (['w12_diff: options file: 2027 files (the shared test lines, 2,000 made-up, the 64 KB limit, %APPDATA% refused), 0 mismatches'],
                    [["w12_diff: options file: 2027 files (the shared test lines, 2,000 made-up, the 64 KB limit, %APPDATA% refused), 3 mismatches"],
                     ["  options MISMATCH x: expected 1, the reader gave 0", 'w12_diff: options file: 2027 files (the shared test lines, 2,000 made-up, the 64 KB limit, %APPDATA% refused), 0 mismatches'],
                     ["w12_diff: options file: 0 files (x), 0 mismatches"],
                     ["w12_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    # shapes as printed 2026-11-18 by tools/harness/options_track.py (round 35, F-034)
    "options-track-selftest": (["options track self-test: 23/23 checks passed"],
                               [["  FAIL  an options save never starts a real-play route", "options track self-test: 22/23 checks passed"],
                                ["  FAIL  x", "options track self-test: 23/23 checks passed"], []]),
    "options-track-routes": (["opt-t2-hp-file: from bt-ch8-support, options {'hp_bars': 2}",
                              "options_track: 24 options route(s), rules OK"],
                             [["options_track: 24 options route(s), 1 problem(s)"],
                              ["bt-ch9: start save opt-x carries the options mark (harness-options.json)",
                               "options_track: 24 options route(s), rules OK"], []]),
    # shapes as printed 2026-11-13 by tools/harness/h56.py (robot round 7)
    "h56-selftest": (["h56 self-test: 15/15 checks passed"],
                     [["  FAIL  mixed real-play and cheat folders refused", "h56 self-test: 14/15 checks passed"],
                      ["  FAIL  x", "h56 self-test: 15/15 checks passed"],
                      ["Traceback (most recent call last):", "h56 self-test: 15/15 checks passed"], []]),
    "h56-h5": (["  bt-ch8-options      866 record(s): original vs original clean; readable gave_up 11, match 847",
                "h5 (check): 100 of 110 overrides met, 17818 records (17394 match, 293 gave up, 0 bad; offline != "
                "live: 0); lines run 561/641, branches taken 330/549 (60.1%)"],
               [["h5 (check): 100 of 110 overrides met, 17818 records (17393 match, 293 gave up, 1 bad; offline != "
                 "live: 1); lines run 561/641"],
                ["  bt-ch8-options      866 record(s): original vs original NOT CLEAN; readable match 866",
                 "h5 (check): 100 of 110 overrides met, 17818 records (17394 match, 293 gave up, 0 bad; offline != "
                 "live: 0)"],
                ["h5 (check): 100 of 110 overrides met, 17818 records (17394 match, 293 gave up, 0 bad; offline != "
                 "live: 0)", "  HARNESS PROBLEM: build/parallel/r8-cap/records/r8-cap-1: original side mismatch"],
                ["h56: SETUP: no record folders in build/parallel/r8-cap/records"],
                ["h5 (check): 0 of 110 overrides met, 0 records (0 match, 0 gave up, 0 bad; offline != live: 0)"],
                []]),
    # shape as printed 2026-11-13 by tools/extras/usa_extras.py verify (Fates' native map)
    "extras-verify": (["[yes] wide          0x004DB6D4 1 word(s), the stereo case's perspective call: x",
                       "51 words in 4 extras: all check out"],
                      [["[ NO] wide          0x004DB6D4 1 word(s), x: original bytes: SHA-1 differs",
                        "51 words in 4 extras: SOME FAIL"],
                       ["[ NO] fps60         0x00610440 13 word(s), x", "51 words in 4 extras: all check out"],
                       ["0 words in 0 extras: all check out"],
                       ["Traceback (most recent call last):", "51 words in 4 extras: all check out"], []]),
    "readable": (["lint: 13 registry row(s), 0 problem(s)", "host test: 80/80 checks passed (0 faults)",
                  "self-test: 13/13 broken inputs rejected, 15 verify-log samples, 7 verdict combinations",
                  "verify pipeline self-test: 22/22 checks passed (fake 3dsrecomp)", "readable: OK"],
                 [["host test: 79/80 checks passed (0 faults)", "readable: 1 problem(s)"],
                  ["verify pipeline self-test: 22/22 checks passed (fake 3dsrecomp)",
                   "readable: OK (compile SKIPPED: no host C compiler (set FE_HOST_CC))"],
                  ["verify pipeline self-test: 21/22 checks passed (fake 3dsrecomp)", "readable: OK"],
                  ["readable: OK"], []]),
    # shape from tools/readable/verify.py (its self-test drives the same code with a fake 3dsrecomp)
    "readable-verify": (["  ABI-ONLY 0x002C4D88 unit_crit: r1 00000001 against 00000002, memory at 0FFFEFF0 (dead stack)",
                         "  GAVE-UP  0x002C48F8 unit_stat_cap: readable code gave up, the original ran",
                         "verify-logs: 9 ABI-ONLY, 1 GAVE-UP", "readable-verify: OK (9 ABI-ONLY, 1 GAVE-UP)"],
                        [["  MISMATCH 0x002C4D88 unit_crit: r0 00000005 against 00000006",
                          "verify-logs: 1 MISMATCH, 9 ABI-ONLY", "readable-verify: 1 problem(s) (1 MISMATCH, 9 ABI-ONLY)"],
                         ["  NOT-RUN  0x002C4D88 unit_crit: stuck", "readable-verify: OK (10 ABI-ONLY)"],
                         ["readable-verify: SETUP MISSING: no 3dsrecomp at engine/target/3dsrecomp-verify/release/3dsrecomp.exe"],
                         ["readable-verify: 1 problem(s) (the build failed or wrote no 0004000000179800.dll)"],
                         []]),
    # shapes as printed 2026-11-14 by round 8's tools (prep, readers, evidence)
    "gen-stubs-selftest": (["gen_stubs self-test: 39/39 checks passed"],
                           [["  FAIL  a writer row was stubbed", "gen_stubs self-test: 38/39 checks passed"],
                            ["  FAIL  x", "gen_stubs self-test: 39/39 checks passed"],
                            ["Traceback (most recent call last):", "gen_stubs self-test: 39/39 checks passed"], []]),
    "gen-stubs-check": (["targets: OK (129 override(s), 34 of them guard users, 0 probe(s), 5 writer(s), never stubbed)"],
                        [["targets: 0x0052A000 unit_defense: guard tag missing (code.bin has a call to 0x00302C6C)",
                          "targets: 1 problem(s)"],
                         ["targets: 1 problem(s)",
                          "targets: OK (129 override(s), 34 of them guard users, 0 probe(s), 5 writer(s), never stubbed)"],
                         ["targets: OK (129 override(s))"], []]),
    "sheet-diff": (["sheet_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261113",
                    "  unit_defense                   300 cases    0 mismatches  (40 cold: both reached / gave up at the cache)",
                    "  planted bug  1 (sheet_stats.c: 'x'): caught, 3 mismatches in unit_defense",
                    "sheet_diff: planted bugs: 40/40 caught",
                    "sheet_diff: OK (5700 cases, 0 mismatches, 40/40 planted bugs caught)"],
                   [["  MISMATCH unit_move case 3: x", "sheet_diff: FAILED (5700 cases, 1 mismatches, 40/40 planted bugs caught)"],
                    ["  planted bug  4 (sheet_unit.c: 'x'): NOT CAUGHT",
                     "sheet_diff: OK (5700 cases, 0 mismatches, 39/40 planted bugs caught)"],
                    ["sheet_diff: OK (5700 cases, 0 mismatches)"],
                    ["  unit_move                      300 cases    0 mismatches  (90 early give-ups)",
                     "sheet_diff: OK (5700 cases, 0 mismatches, 40/40 planted bugs caught)"],
                    ["  unit_move                        3 cases the ARM interpreter could not run (counted as failures)",
                     "sheet_diff: OK (5700 cases, 0 mismatches, 40/40 planted bugs caught)"],
                    ["sheet_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []]),
    "sheet-diff-long": (["  unit_defense                  1500 cases    0 mismatches  (180 cold: both reached / gave up at the cache)",
                         "sheet_diff: OK (28500 cases, 0 mismatches)"],
                        [["sheet_diff: FAILED (28500 cases, 2 mismatches)"],
                         ["  unit_move                     1500 cases    0 mismatches  (450 early give-ups)",
                          "sheet_diff: OK (28500 cases, 0 mismatches)"],
                         ["sheet_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    **{f"{k.replace('_', '-')}-diff": ([f"{k}_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261114",
                      f"  {fn:28s}   300 cases    0 mismatches  (12 cold: both reached / gave up at the cache; 3 early give-ups)",
                      f"  planted bug  1 ({k}_x.c: 'x'): caught, 3 mismatches in {fn}",
                      f"{k}_diff: planted bugs: {p}/{p} caught",
                      f"{k}_diff: OK ({c} cases, 0 mismatches, {p}/{p} planted bugs caught)"],
                     [[f"  MISMATCH {fn} case 3: x", f"{k}_diff: FAILED ({c} cases, 1 mismatches, {p}/{p} planted bugs caught)"],
                      [f"  planted bug  4 ({k}_x.c: 'x'): NOT CAUGHT",
                       f"{k}_diff: OK ({c} cases, 0 mismatches, {p - 1}/{p} planted bugs caught)"],
                      [f"{k}_diff: OK ({c} cases, 0 mismatches)"],
                      [f"  {fn:28s}   300 cases    0 mismatches  (90 early give-ups)",
                       f"{k}_diff: OK ({c} cases, 0 mismatches, {p}/{p} planted bugs caught)"],
                      [f"  {fn:28s}     3 cases the ARM interpreter could not run (counted as failures)",
                       f"{k}_diff: OK ({c} cases, 0 mismatches, {p}/{p} planted bugs caught)"],
                      ["Traceback (most recent call last):", f"{k}_diff: OK ({c} cases, 0 mismatches, {p}/{p} planted bugs caught)"],
                      [f"{k}_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"], []])
       for k, fn, c, p in (("item", "item_is_magic", 7500, 52), ("move", "route_cost", 7200, 48),
                           ("support", "unit_support_level", 7700, 56),
                           # round 11 batches (docs/AI.md, docs/BATTLE2.md), shapes as printed 2026-11-15
                           ("ai_perm", "ai_has_heal_rod", 5400, 48), ("battle2", "forecast_damage", 4800, 39),
                           # round 12 batches (docs/CLASS_CHANGE.md, docs/WEAPON_RANK.md), shapes as printed 2026-11-16
                           ("class_change", "battle_seal_effect", 1500, 28),
                           ("weapon_rank", "script_unit_weapon_rank", 900, 23),
                           # round 13 batches (docs/SHOP_PRICE.md, docs/CASTLE_JOIN.md), shapes as printed 2026-11-16
                           ("shop_price", "shop_buy_price", 600, 22),
                           ("castle_join", "castle_join_offer", 300, 20),
                           # round 14 batches (docs/EQUIP_USE.md, docs/STAFF_RANGE.md), shapes as printed 2026-11-16
                           ("equip_use", "unit_can_equip_item", 300, 39),
                           ("staff_range", "unit_rod_heal_power", 900, 36),
                           # round 15 batch (docs/CAPABILITY.md), shape as printed 2026-11-16
                           ("capability", "unit_capability", 900, 35),
                           # round 16 batch (docs/SHOP_GREY.md), shape as printed 2026-11-16
                           ("shop_grey", "shop_stock", 900, 37),
                           # round 17 host tests (ai_value + ai_think, event/flags, unit/forces), shapes as printed 2026-11-17
                           ("ai_value", "ai_unit_value", 2400, 18), ("flags", "event_flag_get", 300, 7),
                           ("forces", "force_get_unit", 900, 14),
                           # round 18 batch (docs/WEAPON_LEVEL_VIEW.md), shape as printed 2026-11-17
                           ("weapon_level_view", "weapon_level_view_kind", 300, 22),
                           # round 21 batch (docs/STRIKE.md), shape as printed 2026-11-17
                           ("strike", "strike_power", 300, 35))},
    **{f"{k.replace('_', '-')}-diff-long": ([f"  {fn:28s}  1500 cases    0 mismatches  (60 cold: both reached / gave up at the cache)",
                           f"{k}_diff: OK ({c} cases, 0 mismatches)"],
                          [[f"{k}_diff: FAILED ({c} cases, 2 mismatches)"],
                           [f"  {fn:28s}  1500 cases    0 mismatches  (450 early give-ups)", f"{k}_diff: OK ({c} cases, 0 mismatches)"],
                           [f"  MISMATCH {fn} case 9: x", f"{k}_diff: OK ({c} cases, 0 mismatches)"],
                           [f"{k}_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []])
       for k, fn, c in (("item", "item_is_magic", 37500), ("move", "route_cost", 36000),
                        ("support", "unit_support_level", 37500), ("ai_perm", "ai_has_heal_rod", 27000),
                        ("battle2", "forecast_damage", 24000), ("class_change", "battle_seal_effect", 7500),
                        ("weapon_rank", "script_unit_weapon_rank", 4500),
                        ("shop_price", "shop_buy_price", 3000), ("castle_join", "castle_join_offer", 1500),
                        ("capability", "unit_capability", 4500),
                        ("shop_grey", "shop_stock", 4500),
                        ("ai_value", "ai_unit_value", 12000), ("flags", "event_flag_get", 1500),
                        ("forces", "force_get_unit", 4500),
                        ("weapon_level_view", "weapon_level_view_kind", 1500),
                        ("strike", "strike_power", 1500),
                        ("staff_range", "unit_rod_heal_power", 4500))},
    # round 21: the class weapon sub-kind test (docs/WHO_HOLDS.md); no early give-up is allowed at all
    "who-holds-diff": (["who_holds_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261117",
                        "  who_holds_can_equip_subkind      300 cases    0 mismatches  (51 cold: both gave up at entry)",
                        "who_holds_diff: planted bugs: 24/24 caught",
                        "who_holds_diff: OK (300 cases, 0 mismatches, 24/24 planted bugs caught)"],
                       [["  MISMATCH who_holds_can_equip_subkind case 3: x",
                         "who_holds_diff: FAILED (300 cases, 1 mismatches, 24/24 planted bugs caught)"],
                        ["  planted bug  4 (who_holds.c: 'x'): NOT CAUGHT",
                         "who_holds_diff: OK (300 cases, 0 mismatches, 23/24 planted bugs caught)"],
                        ["who_holds_diff: OK (300 cases, 0 mismatches, 23/24 planted bugs caught)"],
                        ["  who_holds_can_equip_subkind      300 cases    0 mismatches  (51 cold: both gave up at entry; 1 early give-ups)",
                         "who_holds_diff: OK (300 cases, 0 mismatches, 24/24 planted bugs caught)"],
                        ["  who_holds_can_equip_subkind          3 cases the ARM interpreter could not run (counted as failures)",
                         "who_holds_diff: OK (300 cases, 0 mismatches, 24/24 planted bugs caught)"],
                        ["Traceback (most recent call last):",
                         "who_holds_diff: OK (300 cases, 0 mismatches, 24/24 planted bugs caught)"],
                        ["who_holds_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"],
                        ["who_holds_diff: OK (300 cases, 0 mismatches)"], []]),
    "who-holds-diff-long": (["  who_holds_can_equip_subkind     1500 cases    0 mismatches  (222 cold: both gave up at entry)",
                             "who_holds_diff: OK (1500 cases, 0 mismatches)"],
                            [["who_holds_diff: FAILED (1500 cases, 2 mismatches)"],
                             ["  who_holds_can_equip_subkind     1500 cases    0 mismatches  (2 early give-ups)",
                              "who_holds_diff: OK (1500 cases, 0 mismatches)"],
                             ["  MISMATCH who_holds_can_equip_subkind case 9: x", "who_holds_diff: OK (1500 cases, 0 mismatches)"],
                             ["who_holds_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # round 22: the female and staff target tests (docs/FEMALE.md, docs/ROD_TARGET.md), shapes as printed 2026-11-17;
    # no early give-up is allowed at all (a cold cache gives up at entry on both sides, counted apart as "cold")
    **{f"{k.replace('_', '-')}-diff": ([f"{k}_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261117",
                                        f"  {fn:30s}   300 cases    0 mismatches  (27 cold: both gave up at entry)",
                                        f"{k}_diff: planted bugs: {p}/{p} caught",
                                        f"{k}_diff: OK ({c} cases, 0 mismatches, {p}/{p} planted bugs caught)"],
                                       [[f"  MISMATCH {fn} case 3: x",
                                         f"{k}_diff: FAILED ({c} cases, 1 mismatches, {p}/{p} planted bugs caught)"],
                                        [f"  planted bug  4 ({k}.c: 'x'): NOT CAUGHT",
                                         f"{k}_diff: OK ({c} cases, 0 mismatches, {p - 1}/{p} planted bugs caught)"],
                                        [f"{k}_diff: OK ({c} cases, 0 mismatches, {p - 1}/{p} planted bugs caught)"],
                                        [f"  {fn:30s}   300 cases    0 mismatches  (27 cold: both gave up at entry; 1 early give-ups)",
                                         f"{k}_diff: OK ({c} cases, 0 mismatches, {p}/{p} planted bugs caught)"],
                                        [f"  {fn:30s}       3 cases the ARM interpreter could not run (counted as failures)",
                                         f"{k}_diff: OK ({c} cases, 0 mismatches, {p}/{p} planted bugs caught)"],
                                        ["Traceback (most recent call last):",
                                         f"{k}_diff: OK ({c} cases, 0 mismatches, {p}/{p} planted bugs caught)"],
                                        [f"{k}_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"],
                                        [f"{k}_diff: OK ({c} cases, 0 mismatches)"], []])
       for k, fn, c, p in (("female", "female_unit_is_female", 600, 19),
                           ("rod_target", "rod_can_use_target", 300, 42))},
    **{f"{k.replace('_', '-')}-diff-long": ([f"  {fn:30s}  1500 cases    0 mismatches  (134 cold: both gave up at entry)",
                                             f"{k}_diff: OK ({c} cases, 0 mismatches)"],
                                            [[f"{k}_diff: FAILED ({c} cases, 2 mismatches)"],
                                             [f"  {fn:30s}  1500 cases    0 mismatches  (2 early give-ups)",
                                              f"{k}_diff: OK ({c} cases, 0 mismatches)"],
                                             [f"  MISMATCH {fn} case 9: x", f"{k}_diff: OK ({c} cases, 0 mismatches)"],
                                             [f"{k}_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []])
       for k, fn, c in (("female", "female_unit_is_female", 3000), ("rod_target", "rod_can_use_target", 1500))},
    # round 23: the item bonus-while-carried test (docs/ITEM_ENHANCE.md), shape as printed 2026-11-17; early give-ups
    # are allowed here (a CanItemEquip cache cold before the tail branch), so a line with them still passes
    "item-enhance-diff": (["item_enhance_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261117",
                           "  unit_item_enhance_have           300 cases    0 mismatches  (45 cold: both gave up; 33 early give-ups (a CanItemEquip cache cold, tail not reached; safe))",
                           "item_enhance_diff: guards made cold alone: 16/16 own, 30/30 CanItemEquip's",
                           "item_enhance_diff: planted bugs: 29/29 caught",
                           "item_enhance_diff: OK (300 cases, 0 mismatches, 29/29 planted bugs caught)"],
                          [["  MISMATCH unit_item_enhance_have case 3: x",
                            "item_enhance_diff: FAILED (300 cases, 1 mismatches, 29/29 planted bugs caught)"],
                           ["  planted bug  4 (item_enhance.c: 'x'): NOT CAUGHT",
                            "item_enhance_diff: OK (300 cases, 0 mismatches, 28/29 planted bugs caught)"],
                           ["item_enhance_diff: OK (300 cases, 0 mismatches, 28/29 planted bugs caught)"],
                           ["  unit_item_enhance_have               3 cases the ARM interpreter could not run (counted as failures)",
                            "item_enhance_diff: OK (300 cases, 0 mismatches, 29/29 planted bugs caught)"],
                           ["Traceback (most recent call last):",
                            "item_enhance_diff: OK (300 cases, 0 mismatches, 29/29 planted bugs caught)"],
                           ["item_enhance_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"],
                           ["item_enhance_diff: OK (300 cases, 0 mismatches)"], []]),
    "item-enhance-diff-long": (["  unit_item_enhance_have          1500 cases    0 mismatches  (230 cold: both gave up; 170 early give-ups (a CanItemEquip cache cold, tail not reached; safe))",
                                "item_enhance_diff: OK (1500 cases, 0 mismatches)"],
                               [["item_enhance_diff: FAILED (1500 cases, 2 mismatches)"],
                                ["  MISMATCH unit_item_enhance_have case 9: x", "item_enhance_diff: OK (1500 cases, 0 mismatches)"],
                                ["item_enhance_diff: OK (300 cases, 0 mismatches)"],
                                ["item_enhance_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # round 23: the four volume readers (docs/VOLUME.md); no cache, so no give-up of any kind is allowed
    "volume-diff": (["volume_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261117",
                     "  volume_bgm_value                 300 cases    0 mismatches",
                     "  volume_voice_value               300 cases    0 mismatches",
                     "volume_diff: planted bugs: 19/19 caught",
                     "volume_diff: OK (1200 cases, 0 mismatches, 19/19 planted bugs caught)"],
                    [["  MISMATCH volume_se_value case 3: x",
                      "volume_diff: FAILED (1200 cases, 1 mismatches, 19/19 planted bugs caught)"],
                     ["  planted bug  4 (volume.c: 'x'): NOT CAUGHT",
                      "volume_diff: OK (1200 cases, 0 mismatches, 18/19 planted bugs caught)"],
                     ["volume_diff: OK (1200 cases, 0 mismatches, 18/19 planted bugs caught)"],
                     ["  volume_bgm_value                 300 cases    0 mismatches  (2 cold: both gave up at entry)",
                      "volume_diff: OK (1200 cases, 0 mismatches, 19/19 planted bugs caught)"],
                     ["  volume_bgm_value                   3 cases the ARM interpreter could not run (counted as failures)",
                      "volume_diff: OK (1200 cases, 0 mismatches, 19/19 planted bugs caught)"],
                     ["Traceback (most recent call last):",
                      "volume_diff: OK (1200 cases, 0 mismatches, 19/19 planted bugs caught)"],
                     ["volume_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"],
                     ["volume_diff: OK (1200 cases, 0 mismatches)"], []]),
    "volume-diff-long": (["  volume_bgm_value                1500 cases    0 mismatches",
                          "volume_diff: OK (6000 cases, 0 mismatches)"],
                         [["volume_diff: FAILED (6000 cases, 2 mismatches)"],
                          ["  volume_bgm_value                1500 cases    0 mismatches  (4 cold: both gave up at entry)",
                           "volume_diff: OK (6000 cases, 0 mismatches)"],
                          ["  MISMATCH volume_bgm_value case 9: x", "volume_diff: OK (6000 cases, 0 mismatches)"],
                          ["volume_diff: OK (1200 cases, 0 mismatches)"],
                          ["volume_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # round 25: the class female reader (docs/JOB_FEMALE.md); cold-cache give-ups at entry are allowed
    "job-female-diff": (["job_female_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261117",
                         "  job_female_is_female             300 cases    0 mismatches  (24 cold: both gave up at entry)",
                         "job_female_diff: planted bugs: 13/13 caught",
                         "job_female_diff: OK (300 cases, 0 mismatches, 13/13 planted bugs caught)"],
                        [["  MISMATCH job_female_is_female case 3: x",
                          "job_female_diff: FAILED (300 cases, 1 mismatches, 13/13 planted bugs caught)"],
                         ["  planted bug  4 (job_female.c: 'x'): NOT CAUGHT",
                          "job_female_diff: OK (300 cases, 0 mismatches, 12/13 planted bugs caught)"],
                         ["job_female_diff: OK (300 cases, 0 mismatches, 12/13 planted bugs caught)"],
                         ["  job_female_is_female               3 cases the ARM interpreter could not run (counted as failures)",
                          "job_female_diff: OK (300 cases, 0 mismatches, 13/13 planted bugs caught)"],
                         ["Traceback (most recent call last):",
                          "job_female_diff: OK (300 cases, 0 mismatches, 13/13 planted bugs caught)"],
                         ["job_female_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"],
                         ["job_female_diff: OK (300 cases, 0 mismatches)"], []]),
    "job-female-diff-long": (["  job_female_is_female            1500 cases    0 mismatches  (131 cold: both gave up at entry)",
                              "job_female_diff: OK (1500 cases, 0 mismatches)"],
                             [["job_female_diff: FAILED (1500 cases, 2 mismatches)"],
                              ["  MISMATCH job_female_is_female case 9: x", "job_female_diff: OK (1500 cases, 0 mismatches)"],
                              ["job_female_diff: OK (300 cases, 0 mismatches)"],
                              ["job_female_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # round 25: the class record lookup helper (docs/JOB_RECORD.md); no cache, so no give-up of any kind is allowed
    "job-record-diff": (["job_record_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261117",
                         "  job_record_get                   300 cases    0 mismatches",
                         "job_record_diff: planted bugs: 18/18 caught",
                         "job_record_diff: OK (300 cases, 0 mismatches, 18/18 planted bugs caught)"],
                        [["  MISMATCH job_record_get case 3: x",
                          "job_record_diff: FAILED (300 cases, 1 mismatches, 18/18 planted bugs caught)"],
                         ["  planted bug  4 (job_record.c: 'x'): NOT CAUGHT",
                          "job_record_diff: OK (300 cases, 0 mismatches, 17/18 planted bugs caught)"],
                         ["job_record_diff: OK (300 cases, 0 mismatches, 17/18 planted bugs caught)"],
                         ["  job_record_get                   300 cases    0 mismatches  (2 cold: both gave up at entry)",
                          "job_record_diff: OK (300 cases, 0 mismatches, 18/18 planted bugs caught)"],
                         ["Traceback (most recent call last):",
                          "job_record_diff: OK (300 cases, 0 mismatches, 18/18 planted bugs caught)"],
                         ["job_record_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"],
                         ["job_record_diff: OK (300 cases, 0 mismatches)"], []]),
    "job-record-diff-long": (["  job_record_get                  1500 cases    0 mismatches",
                              "job_record_diff: OK (1500 cases, 0 mismatches)"],
                             [["job_record_diff: FAILED (1500 cases, 2 mismatches)"],
                              ["  job_record_get                  1500 cases    0 mismatches  (4 early give-ups)",
                               "job_record_diff: OK (1500 cases, 0 mismatches)"],
                              ["  MISMATCH job_record_get case 9: x", "job_record_diff: OK (1500 cases, 0 mismatches)"],
                              ["job_record_diff: OK (300 cases, 0 mismatches)"],
                              ["job_record_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # round 26: the door key reader (docs/KEY_DOOR.md); cold-cache give-ups at entry are allowed
    "key-door-diff": (["key_door_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261117",
                         "  key_door_unit_can_open           300 cases    0 mismatches  (34 cold: both gave up at entry)",
                         "key_door_diff: planted bugs: 18/18 caught",
                         "key_door_diff: OK (300 cases, 0 mismatches, 18/18 planted bugs caught)"],
                        [["  MISMATCH key_door_unit_can_open case 3: x",
                          "key_door_diff: FAILED (300 cases, 1 mismatches, 18/18 planted bugs caught)"],
                         ["  planted bug  4 (key_door.c: 'x'): NOT CAUGHT",
                          "key_door_diff: OK (300 cases, 0 mismatches, 17/18 planted bugs caught)"],
                         ["key_door_diff: OK (300 cases, 0 mismatches, 17/18 planted bugs caught)"],
                         ["  key_door_unit_can_open               3 cases the ARM interpreter could not run (counted as failures)",
                          "key_door_diff: OK (300 cases, 0 mismatches, 18/18 planted bugs caught)"],
                         ["Traceback (most recent call last):",
                          "key_door_diff: OK (300 cases, 0 mismatches, 18/18 planted bugs caught)"],
                         ["key_door_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"],
                         ["key_door_diff: OK (300 cases, 0 mismatches)"], []]),
    "key-door-diff-long": (["  key_door_unit_can_open          1500 cases    0 mismatches  (170 cold: both gave up at entry)",
                              "key_door_diff: OK (1500 cases, 0 mismatches)"],
                             [["key_door_diff: FAILED (1500 cases, 2 mismatches)"],
                              ["  MISMATCH key_door_unit_can_open case 9: x", "key_door_diff: OK (1500 cases, 0 mismatches)"],
                              ["key_door_diff: OK (300 cases, 0 mismatches)"],
                              ["key_door_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # round 26: the skill record by label (docs/SKILL_RECORD.md); no cache, so no give-up of any kind is allowed
    "skill-record-diff": (["skill_record_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261117",
                         "  skill_record_by_name             300 cases    0 mismatches",
                         "skill_record_diff: planted bugs: 20/20 caught",
                         "skill_record_diff: OK (300 cases, 0 mismatches, 20/20 planted bugs caught)"],
                        [["  MISMATCH skill_record_by_name case 3: x",
                          "skill_record_diff: FAILED (300 cases, 1 mismatches, 20/20 planted bugs caught)"],
                         ["  planted bug  4 (skill_record.c: 'x'): NOT CAUGHT",
                          "skill_record_diff: OK (300 cases, 0 mismatches, 19/20 planted bugs caught)"],
                         ["skill_record_diff: OK (300 cases, 0 mismatches, 19/20 planted bugs caught)"],
                         ["  skill_record_by_name             300 cases    0 mismatches  (2 cold: both gave up at entry)",
                          "skill_record_diff: OK (300 cases, 0 mismatches, 20/20 planted bugs caught)"],
                         ["  skill_record_by_name               3 cases the ARM interpreter could not run (counted as failures)",
                          "skill_record_diff: OK (300 cases, 0 mismatches, 20/20 planted bugs caught)"],
                         ["Traceback (most recent call last):",
                          "skill_record_diff: OK (300 cases, 0 mismatches, 20/20 planted bugs caught)"],
                         ["skill_record_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"],
                         ["skill_record_diff: OK (300 cases, 0 mismatches)"], []]),
    "skill-record-diff-long": (["  skill_record_by_name            1500 cases    0 mismatches",
                              "skill_record_diff: OK (1500 cases, 0 mismatches)"],
                             [["skill_record_diff: FAILED (1500 cases, 2 mismatches)"],
                              ["  skill_record_by_name            1500 cases    0 mismatches  (4 cold: both gave up at entry)",
                               "skill_record_diff: OK (1500 cases, 0 mismatches)"],
                              ["  MISMATCH skill_record_by_name case 9: x", "skill_record_diff: OK (1500 cases, 0 mismatches)"],
                              ["skill_record_diff: OK (300 cases, 0 mismatches)"],
                              ["skill_record_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # round 27: the person record (docs/PERSON_RECORD.md): two functions, no give-up allowed; "drawn again" is fine
    "person-record-diff": (["  person_record_by_name: a made-up state read the game's code as data (4 data bytes read from the game's code); drawn again",
                           "person_record_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 20261117",
                           "  person_record_by_name            300 cases    0 mismatches",
                           "  person_record_get                300 cases    0 mismatches",
                           "  person_record_by_name              1 made-up states drawn again (a data read landed in the game's code)",
                           "person_record_diff: planted bugs: 38/38 caught",
                           "person_record_diff: OK (600 cases, 0 mismatches, 38/38 planted bugs caught)"],
                          [["  MISMATCH person_record_get case 3: x",
                            "person_record_diff: FAILED (600 cases, 1 mismatches, 38/38 planted bugs caught)"],
                           ["  planted bug  4 (person_record.c: 'x'): NOT CAUGHT",
                            "person_record_diff: OK (600 cases, 0 mismatches, 37/38 planted bugs caught)"],
                           ["person_record_diff: OK (600 cases, 0 mismatches, 37/38 planted bugs caught)"],
                           ["  person_record_by_name            300 cases    0 mismatches  (2 cold: both gave up at entry)",
                            "person_record_diff: OK (600 cases, 0 mismatches, 38/38 planted bugs caught)"],
                           ["  person_record_get                  3 cases the ARM interpreter could not run (counted as failures)",
                            "person_record_diff: OK (600 cases, 0 mismatches, 38/38 planted bugs caught)"],
                           ["Traceback (most recent call last):",
                            "person_record_diff: OK (600 cases, 0 mismatches, 38/38 planted bugs caught)"],
                           ["person_record_diff: SKIPPED (extracted/text.bin is missing; extract the ROM first)"],
                           ["person_record_diff: OK (600 cases, 0 mismatches)"], []]),
    "person-record-diff-long": (["  person_record_by_name           1500 cases    0 mismatches",
                                "  person_record_get               1500 cases    0 mismatches",
                                "person_record_diff: OK (3000 cases, 0 mismatches)"],
                               [["person_record_diff: FAILED (3000 cases, 2 mismatches)"],
                                ["  person_record_get               1500 cases    0 mismatches  (4 cold: both gave up at entry)",
                                 "person_record_diff: OK (3000 cases, 0 mismatches)"],
                                ["  MISMATCH person_record_by_name case 9: x", "person_record_diff: OK (3000 cases, 0 mismatches)"],
                                ["person_record_diff: OK (1500 cases, 0 mismatches)"],
                                ["person_record_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # round 14: the equip test on the seed-7 case set (same plants, same build folder as equip-use-diff)
    "equip-use-diff-s7": (["equip_use_diff: original ARM code (arm_mini.py on extracted/text.bin) against the readable C, seed 8",
                           "  unit_can_equip_item            300 cases    0 mismatches  (73 gave up on both sides; 18 early give-ups)",
                           "equip_use_diff: cold guards: each of the 21 own cold in 3..10 cases, each of the 9 callee in 2",
                           "equip_use_diff: planted bugs: 39/39 caught",
                           "equip_use_diff: OK (300 cases, 0 mismatches, 39/39 planted bugs caught)"],
                          [["equip_use_diff: FAILED (300 cases, 1 mismatches, 39/39 planted bugs caught)"],
                           ["  planted bug 12 (equip_use.c: 'x'): NOT CAUGHT",
                            "equip_use_diff: OK (300 cases, 0 mismatches, 38/39 planted bugs caught)"],
                           ["equip_use_diff: a guard was never cold (raise -n)",
                            "equip_use_diff: OK (300 cases, 0 mismatches, 39/39 planted bugs caught)"],
                           ["  unit_can_equip_item            300 cases    0 mismatches  (95 early give-ups)",
                            "equip_use_diff: OK (300 cases, 0 mismatches, 39/39 planted bugs caught)"],
                           ["equip_use_diff: OK (300 cases, 0 mismatches)"],
                           ["equip_use_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # round 15 (include/readable/fe_guest.h guest_call6), shape as printed 2026-11-16
    "guest-call6-test": (["  planted bug 10 (stores although a give-up is pending): caught, 16 failed checks: x",
                          "guest_call6_test --plant: 10/10 planted bugs caught"],
                         [["  planted bug 4 (x): NOT CAUGHT", "guest_call6_test --plant: 9/10 planted bugs caught"],
                          ["guest_call6_test --plant: 9/10 planted bugs caught"],
                          ["Traceback (most recent call last):", "guest_call6_test --plant: 10/10 planted bugs caught"],
                          []]),
    # round 15 stats step (docs/LOOK_STEP4.md), shape of tools/mods/look_step4.py check
    "look-step4": (["  built 2 file(s): GameData.bin.lz, DiningData.bin.lz",
                    "  uninstall back byte-identical: OK (3 file(s) before, 3 after)", "CHECK PASS"],
                   [["  built 2 file(s): GameData.bin.lz, DiningData.bin.lz", "CHECK FAIL: Item #1 might 4"],
                    ["  build error: x", "CHECK PASS"],
                    ["  uninstall back byte-identical: BAD (3 file(s) before, 4 after)", "CHECK PASS"],
                    ["ERROR: no romfs"], ["Traceback (most recent call last):", "CHECK PASS"], []]),
    # round 16 looks step (docs/LOOK_TEXT.md, docs/LOOK_PORTRAIT.md), shapes of tools/mods/look_text.py and
    # look_portrait.py check as printed 2026-11-16
    "look-text": (["  built 1 file(s): m/@E/GameData.bin.lz",
                   "  uninstall back byte-identical: OK (1 file(s) before, 1 after)", "CHECK PASS"],
                  [["  built 1 file(s): m/@E/GameData.bin.lz", "CHECK FAIL: label says 'Jakob', not 'Jacques'"],
                   ["  build error: x", "CHECK PASS"],
                   ["  uninstall back byte-identical: BAD (1 file(s) before, 2 after)", "CHECK PASS"],
                   ["CHECK PASS"],
                   ["ERROR: no romfs"], ["Traceback (most recent call last):", "CHECK PASS"], []]),
    "look-portrait": (["  built 2 file(s): face/face/a_bu.arc, face/face/a_st.arc",
                       "  uninstall back byte-identical: OK (1 file(s) before, 1 after)", "CHECK PASS"],
                      [["  built 2 file(s): face/face/a_bu.arc, face/face/a_st.arc",
                        "CHECK FAIL: a_st.arc expression 3 is not Felicia's"],
                       ["  build error: x", "CHECK PASS"],
                       ["  uninstall back byte-identical: BAD (1 file(s) before, 3 after)", "CHECK PASS"],
                       ["CHECK PASS"],
                       ["ERROR: no romfs"], ["Traceback (most recent call last):", "CHECK PASS"], []]),
    # round 18 test-tools step: the flags case maker on round 17's false-mismatch seed
    "flags-diff-s424242": (["  event_flag_get                 400 cases    0 mismatches",
                            "flags_diff: OK (400 cases, 0 mismatches)"],
                           [["flags_diff: FAILED (400 cases, 1 mismatches)"],
                            ["  MISMATCH event_flag_get case 17: x", "flags_diff: OK (400 cases, 0 mismatches)"],
                            ["  event_flag_get                 400 cases    0 mismatches  (120 early give-ups)",
                             "flags_diff: OK (400 cases, 0 mismatches)"],
                            ["flags_diff: SKIPPED (no host C compiler; set FE_HOST_CC)"], []]),
    # round 18 test-tools step (tools/harness/test_h6host.py): 4 tests as printed 2026-11-17
    "h6host-test": (["....", "----------------------------------------------------------------------",
                     "Ran 4 tests in 4.012s", "", "OK"],
                    [["Ran 4 tests in 4.0s", "", "FAILED (failures=2)"],
                     ["Ran 4 tests in 4.0s", "", "OK (skipped=1)"],
                     ["Ran 0 tests in 0.000s", "", "OK"], ["OK"], []]),
    # round 14 measure step (docs/harness/H6_THREE.md): 15 tests as printed 2026-11-16
    "h6three-tests": (["...............", "----------------------------------------------------------------------",
                       "Ran 15 tests in 0.175s", "", "OK"],
                      [["Ran 15 tests in 0.2s", "", "FAILED (failures=1)"],
                       ["Ran 0 tests in 0.000s", "", "OK"], ["OK"], []]),
    # shape as printed 2026-11-15 by src/readable/battle2/tests/shadow_count.py
    "battle2-shadow-count": (["shadow_count: GetEnhanceHave in verify's made-up state, r0 = 0x00100000, r1 = 0",
                              "  predicted: A = 310; B = 310 (original) + 66 (x) + 64 (y) + 0 (z) = 440",
                              "shadow_count: OK (tier 2 shadow pass: 310 faults against 440; predicted 310 against 440)"],
                             [["shadow_count: DIFFERENT (tier 2 shadow pass: 310 faults against 441; predicted 310 against 440)"],
                              ["shadow_count: OK (tier 2 shadow pass: 310 faults against 441; predicted 310 against 440)"],
                              ["shadow_count: no tier-2 shadow output to compare with (prediction only)"],
                              ["shadow_count: SKIPPED (extracted/ is missing)"], []]),
    "mutate-writer-fake": (["mutate: writer H6 (fake): 3 callee(s) of the made-up writer slots: fake_heal, fake_clampst, fake_count",
                            "  fake_heal                           10/ 10 caught (100.0%; 0 via a caller's record, 0 by crash/timeout)",
                            "mutate: 26/26 caught (100.0%; equivalent mutants left out: 6, stillborn: 0); x"],
                           [["mutate: writer H6 (fake): 3 callee(s) of the made-up writer slots: x",
                             "mutate: 25/26 caught (96.2%; equivalent mutants left out: 6, stillborn: 0); x"],
                            ["mutate: writer H6 (fake): 0 callee(s) of the made-up writer slots",
                             "mutate: 26/26 caught (100.0%; x)"],
                            ["mutate: 26/26 caught (100.0%; x)"],
                            ["Traceback (most recent call last):", "mutate: writer H6 (fake): 3 callee(s)",
                             "mutate: 26/26 caught (100.0%; x)"], []]),
    "evidence-selftest": (["evidence self-test: 15/15 checks passed"],
                          [["  FAIL clean deleted a kept session", "evidence self-test: 14/15 checks passed"],
                           ["Traceback (most recent call last):", "evidence self-test: 15/15 checks passed"], []]),
}


class RowPatterns(unittest.TestCase):
    def test_every_command_row_has_samples(self):
        cmd_rows = {r.id for r in CA.ROWS if r.cmd is not None}
        self.assertEqual(cmd_rows, set(ROW_SAMPLES), "add pass/fail samples for new command rows")

    def test_pass_samples_pass_and_fail_samples_fail(self):
        rows = {r.id: r for r in CA.ROWS}
        for rid, (good, bads) in ROW_SAMPLES.items():
            self.assertEqual(CA.judge_lines(rows[rid], good), [], rid)
            for bad in bads:
                self.assertTrue(CA.judge_lines(rows[rid], bad), (rid, bad))
            self.assertTrue(CA.judge_lines(rows[rid], good + ["Traceback (most recent call last):"]), rid)


class LeakScan(unittest.TestCase):
    def test_raw_hex_and_word_dumps_found(self):
        code = make_dummy_image.stream("leak-test", 1 << 14)
        keys, _ = CA.leak_keys(code)
        run = code[1000:1000 + 64]
        self.assertTrue(CA.scan_leaks(keys, b"xx" + run + b"yy"))
        dump = ", ".join(f"0x{b:02X}" for b in run).encode()
        self.assertTrue(any(CA.scan_leaks(keys, s) for s in CA.hex_streams(dump)))
        words = " ".join(f"{int.from_bytes(run[i:i + 4], 'little'):08X}" for i in range(0, 64, 4)).encode()
        self.assertTrue(any(CA.scan_leaks(keys, s) for s in CA.hex_streams(words)))
        self.assertFalse(CA.scan_leaks(keys, make_dummy_image.stream("other", 4096)))

    def test_text_formats_found(self):
        """code.bin bytes written in the project's own asm format and in common dump formats
        (the verifier's misses: .word, .byte, xxd, hexdump -C) are all found."""
        code = make_dummy_image.stream("leak-fmt", 1 << 14)
        keys, _ = CA.leak_keys(code)
        base = 0x2000
        run = code[base:base + 256]
        u32 = [int.from_bytes(run[i:i + 4], "little") for i in range(0, len(run), 4)]
        u16 = [int.from_bytes(run[i:i + 2], "little") for i in range(0, len(run), 2)]
        asc = lambda ch: "".join(chr(b) if 32 <= b < 127 else "." for b in ch)  # noqa: E731
        fmts = {
            "gen_asm .word with address comments and labels": "\n".join(
                (f"D_{0x45A000 + i:08X}:\n" if i % 32 == 0 else "")
                + f"\t.word 0x{w:08X} @ {0x45A000 + i:08X}" for i, w in zip(range(0, 256, 4), u32)),
            ".word, symbols named by address": "\n".join(
                f"\t.word {'func' if i % 3 else 'D'}_{w:08X}" for i, w in enumerate(u32)),
            ".byte 16 per line": "\n".join("    .byte " + ", ".join(f"0x{b:02x}" for b in run[i:i + 16])
                                          for i in range(0, 256, 16)),
            ".byte decimal": "\n".join("    .byte " + ", ".join(str(b) for b in run[i:i + 16])
                                       for i in range(0, 256, 16)),
            ".hword": "\n".join(f"  .hword 0x{h:04x}" for h in u16),
            ".4byte list": "  .4byte " + ", ".join(f"0x{w:08x}" for w in u32),
            "xxd": "\n".join(f"{0x1000 + i:08x}: " + " ".join(run[i + j:i + j + 2].hex() for j in range(0, 16, 2))
                             + "  " + asc(run[i:i + 16]) for i in range(0, 256, 16)),
            "xxd, ASCII column that looks like hex": "\n".join(
                f"{0x1000 + i:08x}: " + " ".join(run[i + j:i + j + 2].hex() for j in range(0, 16, 2))
                + "  deadbeefcafe0123" for i in range(0, 256, 16)),
            "hexdump -C": "\n".join(f"{i:08x}  " + " ".join(f"{b:02x}" for b in run[i:i + 8]) + "  "
                                    + " ".join(f"{b:02x}" for b in run[i + 8:i + 16])
                                    + f"  |{asc(run[i:i + 16])}|" for i in range(0, 256, 16)),
            "hexdump (16-bit words)": "\n".join(f"{i:07x} " + " ".join(f"{h:04x}" for h in u16[i // 2:i // 2 + 8])
                                                for i in range(0, 256, 16)),
            "objdump -d": "\n".join(f"  {0x100000 + 4 * i:x}:\t{w:08x} \tldr\tr0, [pc, #0x1c]\t; 0x10"
                                    for i, w in enumerate(u32)),
            "C array over lines": "static const u8 x[] = {\n" + "\n".join(
                "    " + ", ".join(f"0x{b:02X}" for b in run[i:i + 12]) + "," for i in range(0, 256, 12)) + "\n};",
            "C array, decimal": "{" + ", ".join(str(b) for b in run) + "}",
            "u16 array": "{" + ", ".join(f"0x{h:04x}" for h in u16) + "}",
            "python bytes literal": "data = b'" + "".join(f"\\x{b:02x}" for b in run) + "'",
            "python bytes over lines": "data = (\n" + "\n".join(
                "    b'" + "".join(f"\\x{b:02x}" for b in run[i:i + 16]) + "'" for i in range(0, 256, 16)) + "\n)",
            ".ascii with escapes": '  .ascii "' + "".join(f"\\{b:03o}" for b in run) + '"',
            "contiguous hex": run.hex(),
            "xxd -p": "\n".join(run[i:i + 30].hex() for i in range(0, 256, 30)),
            "dump inside # comments": "x = 1\n" + "\n".join(
                f"# {0x1000 + i:08x}: " + " ".join(run[i + j:i + j + 2].hex() for j in range(0, 16, 2))
                for i in range(0, 256, 16)),
            "dump inside // comments": "\n".join("// " + " ".join(f"{b:02X}" for b in run[i:i + 16])
                                                 for i in range(0, 256, 16)),
        }
        # second verifier's misses: quoted hex, one-line decimal arrays, hex lists whose
        # lines start with a byte that spells a nasm directive (db, dd ...)
        fmts.update({
            "JSON hex string": '{"blob": "' + run.hex() + '"}',
            "bytes.fromhex": 'data = bytes.fromhex("' + run.hex().upper() + '")',
            "hex string, odd offset": 'x = "f' + run.hex() + '"',
            "C decimal array, declaration on the line": "const unsigned char t[] = {" + ", ".join(str(b) for b in run) + "};",
            "python decimal list": "data = [" + ", ".join(str(b) for b in run) + "]",
        })
        o = next(i for i in range(0x100, len(code) - 300) if code[i] == 0xDB)
        dbrun = code[o:o + 256]
        fmts["hex list, lines start with db"] = "\n".join(
            " ".join(f"{b:02x}" for b in dbrun[i:i + 16]) for i in range(0, 256, 16))
        for name, text in fmts.items():
            hits = sum(len(CA.scan_leaks(keys, s)) for s in CA.decoded_streams(text.encode()))
            self.assertGreater(hits, 0, name)

    def test_text_without_code_bytes_is_clean(self):
        code = make_dummy_image.stream("leak-fmt", 1 << 14)
        keys, _ = CA.leak_keys(code)
        other = make_dummy_image.stream("unrelated", 512)
        texts = ["\n".join(f"\t.word 0x{int.from_bytes(other[i:i + 4], 'little'):08X} @ {i:08X}"
                           for i in range(0, 512, 4)),
                 (ROOT / "tools" / "check_all.py").read_text(encoding="utf-8"),
                 "Prose with be a cafe face added 12 34 56 numbers.\n" * 50,
                 "-1, -200, 300, 1e5, \u00b2, 0x, .byte -1, 999, .word -5\n.space 0x10, 0xAB\n"
                 ".space bad\n.ascii \"\\777\"\n x = '\\x4'\n" * 20]
        for t in texts:
            self.assertEqual(sum(len(CA.scan_leaks(keys, s)) for s in CA.decoded_streams(t.encode())), 0)

    def test_decoder_never_crashes(self):
        """A decoder crash would make hygiene-leak FAIL (INCOMPLETE) on any odd file: feed it
        a fixed-seed soup of directives, numbers, escapes, comment marks and raw bytes."""
        import random
        bs = chr(92)
        toks = [".byte", ".word", ".hword", ".space", ".zero", ".ascii", ".asciz", ".quad", "DCB", "dd",
                "0x", "0x1", "0xFFFFFFFFFFFF", "-1", "-0x5", "255", "256", "00000000:", "0045A000", "|ab|",
                "  |", "@", "#", "//", "/*", ";", "'", '"', bs, bs + "x", bs + "x4", bs + "777",
                "func_001F5C38", "{", "}", ",", "b'", "é", "１", "-", "*", "be", "1e5"]
        rng = random.Random(7)
        for _ in range(3000):
            line = "".join(rng.choice(toks) + rng.choice(["", " ", ", ", "  ", "\n"])
                           for _ in range(rng.randint(0, 14)))
            CA.decoded_streams(line.encode("utf-8"))
        for _ in range(300):
            CA.decoded_streams(bytes(rng.randrange(256) for _ in range(rng.randint(0, 200))))

    def test_low_information_windows(self):
        self.assertTrue(CA.is_progression(bytes(range(9, 41))))
        self.assertTrue(CA.is_progression(b"".join(i.to_bytes(2, "little") for i in range(100, 116))))
        self.assertTrue(CA.is_progression(b"".join(i.to_bytes(4, "little") for i in range(7, 15))))
        self.assertFalse(CA.is_progression(make_dummy_image.stream("p", 32)))
        code_len = 0x400000
        ptrs = b"".join(v.to_bytes(4, "little") for v in
                        (0, 0x00484F3C, 0x002FB330, 0x003DBDDC, 0x003DBDD0, 0x003DBDCC, 0xFFFFFFF8, 0x0045A000))
        self.assertTrue(CA.is_pointer_window(ptrs, code_len))
        self.assertFalse(CA.is_pointer_window(ptrs[:28] + b"\x41\x42\x43\x44", code_len))
        self.assertFalse(CA.is_pointer_window(make_dummy_image.stream("q", 32), code_len))

    def test_short_runs_and_identifiers(self):
        code = make_dummy_image.stream("leak-test", 1 << 14)
        keys, _ = CA.leak_keys(code)
        self.assertFalse(CA.scan_leaks(keys, code[1000:1000 + CA.LEAK_WINDOW - 1]))
        self.assertEqual(CA.window_kind(b"N3app10ProcInstE_GLOBAL__N__13_x"), "ident")
        self.assertEqual(CA.window_kind(b"nn::pia::inet::NatTraverser::Com"), "ident")
        self.assertEqual(CA.window_kind(b"Allocator<nn::nex::DataStoreRati"), "ident")
        self.assertEqual(CA.window_kind(b"nn::pia Allocator<nn::nex::Data>"), "text")
        self.assertEqual(CA.window_kind(b"Hello, world! This is a string."), "text")
        self.assertEqual(CA.window_kind(bytes(range(32))), "binary")


def copy_repo_subset(dst: Path):
    """What lint and the ROM-free rows read: tools/*.py, config/, src/, include/, README."""
    (dst / "tools").mkdir(parents=True)
    for p in (ROOT / "tools").glob("*.py"):
        shutil.copy2(p, dst / "tools" / p.name)
    for d in ("config", "src", "include"):
        if (ROOT / d).is_dir():
            shutil.copytree(ROOT / d, dst / d, ignore=shutil.ignore_patterns("__pycache__"))
    if (ROOT / "README.md").is_file():
        shutil.copy2(ROOT / "README.md", dst / "README.md")


def run_check_all(root: Path, *args: str) -> tuple[int, dict, str]:
    out = root / "out.json"
    p = subprocess.run([sys.executable, str(root / "tools" / "check_all.py"), "--json", str(out), *args],
                       cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=600)
    data = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    return p.returncode, {r["id"]: r for r in data.get("rows", [])}, p.stdout + p.stderr


class EndToEnd(unittest.TestCase):
    """check_all.py run as a program from scratch copies of the repository."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        copy_repo_subset(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_rom_no_toolchain_skips_with_reasons(self):
        rows = "code-hash,m1-tests,diff-func,gen-headers,rom-rebuild,assets-quick,lint,py-compile"
        rc, res, out = run_check_all(self.root, "--only", rows)
        self.assertEqual(rc, 0, out)
        self.assertEqual(res["lint"]["status"], "PASS", out)
        self.assertEqual(res["py-compile"]["status"], "PASS", out)
        for rid in ("code-hash", "m1-tests", "diff-func", "rom-rebuild", "assets-quick"):
            self.assertEqual(res[rid]["status"], "SKIP", res[rid])
            self.assertIn("extracted/", res[rid]["note"])
        self.assertEqual(res["gen-headers"]["status"], "SKIP")
        self.assertIn("toolchain", res["gen-headers"]["note"])
        self.assertIn("CHECK-ALL: PASS (6 skipped)", out)
        rc, _, out = run_check_all(self.root, "--only", rows, "--fail-on-skip")
        self.assertEqual(rc, 1, out)

    def test_mutated_config_fails_lint_and_other_rows_still_run(self):
        p = self.root / "config" / "src_map.csv"
        if not p.is_file():
            # no C++ yet (Fates): one row naming the first registry function and a source
            with (self.root / "config" / "functions.csv").open(encoding="utf-8") as fh:
                first = fh.read().splitlines()[1].split(",")
            p.write_text("addr,name,symbol,source,status,compiler\n"
                         f"{first[0]},{first[3]},{first[3]},src/game/x.cpp,nonmatching,gcc-standin\n",
                         encoding="utf-8")
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        cols = lines[1].split(",")
        cols[1] = cols[1] + "_mutated"          # name no longer matches config/functions.csv
        lines[1] = ",".join(cols)
        p.write_text("".join(lines), encoding="utf-8")
        rc, res, out = run_check_all(self.root, "--only", "lint,py-compile")
        self.assertEqual(rc, 1, out)
        self.assertEqual(res["lint"]["status"], "FAIL", out)
        self.assertEqual(res["py-compile"]["status"], "PASS", out)

    def test_crashing_tool_is_never_pass(self):
        # build.py replaced by one that prints a traceback and the success line, exit 0
        (self.root / "tools" / "build.py").write_text(
            "import traceback\ntry:\n    raise RuntimeError('boom')\nexcept Exception:\n"
            "    traceback.print_exc()\nprint('lint: OK')\n", encoding="utf-8")
        rc, res, out = run_check_all(self.root, "--only", "lint")
        self.assertEqual(res["lint"]["status"], "FAIL", out)
        self.assertEqual(rc, 1)
        (self.root / "tools" / "build.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        rc, res, out = run_check_all(self.root, "--only", "lint")
        self.assertEqual(res["lint"]["status"], "FAIL", out)   # exit 0 without "lint: OK"

    def test_syntax_error_fails_py_compile(self):
        (self.root / "tools" / "broken.py").write_text("def f(:\n", encoding="utf-8")
        rc, res, out = run_check_all(self.root, "--only", "py-compile")
        self.assertEqual(res["py-compile"]["status"], "FAIL", out)
        self.assertEqual(rc, 1)

    def test_usage_error(self):
        rc, _, out = run_check_all(self.root, "--only", "no-such-row")
        self.assertEqual(rc, 2, out)


@unittest.skipUnless(HAVE_GIT, "git not on PATH")
class Hygiene(unittest.TestCase):
    """hygiene-paths / hygiene-leak on a scratch git repo with a dummy image."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # a timed-out row may still hold the dir (Windows)
        self.root = Path(self.tmp.name) / "repo"
        (self.root / "tools").mkdir(parents=True)
        shutil.copy2(ROOT / "tools" / "check_all.py", self.root / "tools" / "check_all.py")
        self.git("init", "-q")
        make_dummy_image.make(self.root, 1 << 16, "hygiene")
        (self.root / ".gitignore").write_text("extracted/\nbuild/\nout.json\n", encoding="utf-8")
        (self.root / "README.md").write_text("clean text\n", encoding="utf-8")
        self.git("add", ".gitignore", "README.md", "tools/check_all.py")
        self.code = (self.root / "extracted" / "code.bin").read_bytes()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def test_clean_tree_passes(self):
        rc, res, out = run_check_all(self.root, "--only", "hygiene-paths,hygiene-leak")
        self.assertEqual(res["hygiene-paths"]["status"], "PASS", out)
        self.assertEqual(res["hygiene-leak"]["status"], "PASS", out)
        self.assertEqual(rc, 0)

    def test_planted_bytes_fail(self):
        run = self.code[5000:5000 + 80]
        (self.root / "notes.txt").write_bytes(b"header\n" + run + b"\ntrailer\n")
        (self.root / "dump.md").write_text(
            "bytes: " + " ".join(f"{b:02x}" for b in self.code[9000:9000 + 64]) + "\n", encoding="utf-8")
        self.git("add", "notes.txt", "dump.md")
        rc, res, out = run_check_all(self.root, "--only", "hygiene-leak")
        self.assertEqual(res["hygiene-leak"]["status"], "FAIL", out)
        self.assertIn("2 file(s) with code.bin bytes", res["hygiene-leak"]["note"])
        self.assertEqual(rc, 1)

    def test_untracked_files_are_scanned(self):
        """A new file not yet added (and not ignored) is what the next commit adds: scanned too.
        An ignored file (build/) is not."""
        (self.root / "new_notes.txt").write_bytes(b"header\n" + self.code[7000:7000 + 80] + b"\n")
        (self.root / "build").mkdir()
        (self.root / "build" / "scratch.bin").write_bytes(self.code[:4096])
        rc, res, out = run_check_all(self.root, "--only", "hygiene-leak")
        self.assertEqual(res["hygiene-leak"]["status"], "FAIL", out)
        self.assertIn("1 file(s) with code.bin bytes: new_notes.txt", res["hygiene-leak"]["note"])
        self.assertIn("+ 1 untracked files", res["hygiene-leak"]["note"])
        self.assertEqual(rc, 1)

    def test_bytes_in_asm_and_dump_formats_fail(self):
        """The verifier's attack: code.bin bytes as gen_asm-style .word lines (address
        comments, labels, symbols named by address), xxd and hexdump -C dumps."""
        c = self.code
        words = [int.from_bytes(c[i:i + 4], "little") for i in range(0x3000, 0x3100, 4)]
        (self.root / "src").mkdir()
        (self.root / "src" / "data.s").write_text("".join(
            (f"D_{0x400000 + 4 * n:08X}:\n" if n % 16 == 0 else "")
            + f"\t.word 0x{w:08X} @ {0x400000 + 4 * n:08X}\n" for n, w in enumerate(words)), encoding="utf-8")
        (self.root / "notes.md").write_text("```\n" + "".join(
            f"{i:08x}: " + " ".join(c[i + j:i + j + 2].hex() for j in range(0, 16, 2)) + "  ................\n"
            for i in range(0x5000, 0x5080, 16)) + "```\n", encoding="utf-8")
        (self.root / "dump.txt").write_text("".join(
            f"{i:08x}  " + " ".join(f"{b:02x}" for b in c[i:i + 16]) + "  |................|\n"
            for i in range(0x7000, 0x7080, 16)), encoding="utf-8")
        self.git("add", "src/data.s", "notes.md", "dump.txt")
        rc, res, out = run_check_all(self.root, "--only", "hygiene-paths,hygiene-leak")
        self.assertEqual(res["hygiene-paths"]["status"], "PASS", out)
        self.assertEqual(res["hygiene-leak"]["status"], "FAIL", out)
        self.assertIn("3 file(s) with code.bin bytes", res["hygiene-leak"]["note"])
        self.assertEqual(rc, 1)

    def test_gen_asm_output_fails_without_rom(self):
        shutil.rmtree(self.root / "extracted")
        (self.root / "src").mkdir()
        mark = "@ GENERATED by tools/" + "gen_asm.py from the user's code.bin. Do not edit or commit.\n"
        (self.root / "src" / "copied.s").write_text(mark + ".syntax unified\n", encoding="utf-8")
        (self.root / "src" / "mentions.py").write_text(
            'HEADER = ["' + mark.strip() + '"]\n', encoding="utf-8")   # a quoted mention is fine
        self.git("add", "src/copied.s", "src/mentions.py")
        rc, res, out = run_check_all(self.root, "--only", "hygiene-paths,hygiene-leak")
        self.assertEqual(res["hygiene-paths"]["status"], "FAIL", out)
        self.assertIn("src/copied.s: output of tools/gen_asm.py", res["hygiene-paths"]["note"])
        self.assertIn("1 problem(s)", res["hygiene-paths"]["note"])
        self.assertEqual(res["hygiene-leak"]["status"], "SKIP", out)
        self.assertEqual(rc, 1)

    def test_in_process_timeout_still_prints_table(self):
        rc, res, out = run_check_all(self.root, "--only", "hygiene-paths", "--timeout-scale", "0.00001")
        self.assertEqual(res["hygiene-paths"]["status"], "FAIL", out)
        self.assertIn("INCOMPLETE: timed out", res["hygiene-paths"]["note"])
        self.assertIn("CHECK-ALL: FAIL", out)
        self.assertEqual(rc, 1)

    def test_forbidden_paths_and_extensions_fail(self):
        for rel in ("build/report.txt", "asset.lz", "tools/config.local.json"):
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text("x\n", encoding="utf-8")
            self.git("add", "-f", rel)
        rc, res, out = run_check_all(self.root, "--only", "hygiene-paths")
        self.assertEqual(res["hygiene-paths"]["status"], "FAIL", out)
        self.assertIn("3 problem(s)", res["hygiene-paths"]["note"])
        self.assertEqual(rc, 1)

    def test_untracked_files_get_path_checks(self):
        """A new file not yet added (and not ignored) gets the same checks as a tracked one;
        an ignored one (build/) does not."""
        (self.root / "blob.txt").write_bytes(b"abc\0def")
        (self.root / "build").mkdir()
        (self.root / "build" / "scratch.bin").write_bytes(b"\0" * 16)
        rc, res, out = run_check_all(self.root, "--only", "hygiene-paths")
        self.assertEqual(res["hygiene-paths"]["status"], "FAIL", out)
        self.assertIn("blob.txt: binary content", res["hygiene-paths"]["note"])
        self.assertIn("1 problem(s)", res["hygiene-paths"]["note"])
        self.assertIn("+ 1 untracked files", res["hygiene-paths"]["note"])

    def test_untracked_python_is_compiled(self):
        (self.root / "tools" / "new_tool.py").write_text("def f(:\n", encoding="utf-8")
        rc, res, out = run_check_all(self.root, "--only", "py-compile")
        self.assertEqual(res["py-compile"]["status"], "FAIL", out)
        self.assertIn("tools/new_tool.py", res["py-compile"]["note"])
        (self.root / "tools" / "new_tool.py").write_text("X = 1\n", encoding="utf-8")
        rc, res, out = run_check_all(self.root, "--only", "py-compile")
        self.assertEqual(res["py-compile"]["status"], "PASS", out)

    def test_binary_content_fails(self):
        (self.root / "blob.txt").write_bytes(b"abc\0def")
        self.git("add", "blob.txt")
        rc, res, out = run_check_all(self.root, "--only", "hygiene-paths")
        self.assertEqual(res["hygiene-paths"]["status"], "FAIL", out)
        self.assertIn("binary", res["hygiene-paths"]["note"])

    def test_empty_code_bin_is_not_pass(self):
        (self.root / "extracted" / "code.bin").write_bytes(b"")
        rc, res, out = run_check_all(self.root, "--only", "hygiene-leak")
        self.assertEqual(res["hygiene-leak"]["status"], "FAIL", out)
        self.assertIn("nothing was checked", res["hygiene-leak"]["note"])
        self.assertEqual(rc, 1)

    def test_missing_extracted_skips_leak_scan(self):
        shutil.rmtree(self.root / "extracted")
        rc, res, out = run_check_all(self.root, "--only", "hygiene-paths,hygiene-leak")
        self.assertEqual(res["hygiene-paths"]["status"], "PASS", out)
        self.assertEqual(res["hygiene-leak"]["status"], "SKIP", out)
        self.assertIn("extracted/code.bin", res["hygiene-leak"]["note"])
        self.assertEqual(rc, 0)


# ------------------------------------------------------------------ --jobs and the row-result cache
sys.path.insert(0, str(ROOT / "tools"))
import testcache as TC  # noqa: E402


def stamp_row(rid: str, seconds: float, out: Path, lines: str = "ok", rc: int = 0, **kw) -> "CA.Row":
    """A row that records when it ran (start/end in out/<rid>.t) and prints `lines`."""
    code = (f"import time, sys; t0 = time.time(); time.sleep({seconds}); "
            f"open(r'{out / (rid + '.t')}', 'w').write(f'{{t0}} {{time.time()}}'); "
            f"print({lines!r}); sys.exit({rc})")
    return CA.Row(rid, f"stamp {rid}", cmd=py(code), **kw)


def span(out: Path, rid: str) -> tuple[float, float]:
    a, b = (out / f"{rid}.t").read_text().split()
    return float(a), float(b)


class KnownFailures(unittest.TestCase):
    """Round 10: the readable-verify KNOWN entries are strict. Round 22 added rod_can_use_target: exactly these
    two NOT-RUN (item_sell_price and rod_can_use_target), 2 problems in all, and no MISMATCH."""
    LOG = ("  NOT-RUN  0x0034AC30 rod_can_use_target: no executable function was tested (VERIFY_ONLY address not found?); "
           "0 functions in both passes and the build's entry table shows no holder for this address: nothing explains it\n"
           "  NOT-RUN  0x0053AE8C item_sell_price: no executable function was tested (VERIFY_ONLY address not found?); "
           "0 functions in both passes and the build's entry table shows no holder for this address: nothing explains it\n"
           "verify-logs: 108 ABI-ONLY, 14 CLEAN, 73 GAVE-UP, 2 NOT-RUN, 9 UNSAMPLED\n"
           "readable-verify: 2 problem(s) (108 ABI-ONLY, 14 CLEAN, 73 GAVE-UP, 2 NOT-RUN, 9 UNSAMPLED)\n")

    def match(self, text):
        return all(re.search(k["match"], text, re.M) for k in CA.KNOWN["readable-verify"])

    def test_the_known_log_matches(self):
        self.assertTrue(self.match(self.LOG))

    def test_anything_more_is_not_known(self):
        for bad in (self.LOG.replace("2 problem(s) (108", "3 problem(s) (1 MISMATCH, 108"),
                    self.LOG.replace("2 problem(s) (108", "2 problem(s) (1 MISMATCH, 108"),
                    self.LOG.replace("0x0053AE8C item_sell_price", "0x0053AAAA item_other"),
                    self.LOG.replace("0x0034AC30 rod_can_use_target", "0x0034AAAA rod_other"),
                    self.LOG.replace("2 NOT-RUN, 9", "3 NOT-RUN, 9").replace("2 problem(s)", "3 problem(s)"),
                    # the round 10 log alone (only item_sell_price) is no longer the known shape either
                    self.LOG.split("\n", 1)[1].replace("2 NOT-RUN", "1 NOT-RUN").replace("2 problem(s)", "1 problem(s)")):
            self.assertFalse(self.match(bad), bad)


class RobotRoutes(unittest.TestCase):
    """check_robot_routes (round 8, F-022) on a made-up routes.json / markers.json."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config" / "harness").mkdir(parents=True)
        self.routes = {"bt-ch5": {"save": "bt-ch4-clear", "verified": True},
                       "cq-ch6": {"save": "bt-ch5-clear", "verified": True},
                       "rv-ch6": {"save": "bt-ch5-clear", "verified": True},
                       "cq-ch7": {"save": "cq-ch6-clear", "verified": False},
                       "cheat-x": {"save": "bt-ch5-clear", "verified": True}}
        self.cps = {"bt-ch5": {"100": {"what": "x"}},
                    "cq-ch6": {"100": {"state": {"route": 1}}},
                    "rv-ch6": {"100": {"state": {"route": 2}}}}

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, saves=None):
        (self.root / "config/harness/routes.json").write_text(json.dumps({"routes": self.routes}), encoding="utf-8")
        (self.root / "config/harness/markers.json").write_text(json.dumps({"checkpoints": self.cps}), encoding="utf-8")
        if saves is not None:
            d = self.root / "build/harness/saves"
            d.mkdir(parents=True, exist_ok=True)
            for z in saves:
                (d / f"{z}.zip").write_bytes(b"PK")
        ctx = CA.Ctx(root=self.root, log_dir=self.root / "logs")
        return CA.check_robot_routes(ctx)

    def test_good_tree_passes_without_build(self):
        ok, note = self.run_check()
        self.assertTrue(ok, note)
        self.assertIn("3 verified real-play route(s)", note)

    def test_options_routes_are_not_real_play(self):
        # the options track (opt-* with "options", F-032/F-034) is scored apart: never counted as real play
        self.routes["opt-t9"] = {"save": "bt-ch5-clear", "verified": True, "options": {"hp_bars": 2}}
        ok, note = self.run_check()
        self.assertTrue(ok, note)
        self.assertIn("3 verified real-play route(s)", note)
        self.routes["opt-real"] = {"save": "bt-ch5-clear", "verified": True}
        ok, note = self.run_check()
        self.assertFalse(ok, note)   # a real-play opt-* route still needs checkpoints

    def test_good_tree_passes_with_saves(self):
        ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + list(CA.ROUND8_PACKS))
        self.assertTrue(ok, note)

    def test_round10_packs_are_required(self):
        # round 10 (fresh helper per chapter): bt-ch13..17, rv-ch10..14 and integrate's cq-ch8 pack of round 9
        want = {f"bt-ch{n}-clear" for n in range(13, 18)} | {f"rv-ch{n}-clear" for n in range(10, 15)} | {"cq-ch8-clear", "cq-ch9-clear"}
        self.assertLessEqual(want, set(CA.ROUND8_PACKS))
        for z in sorted(want):
            self.tearDown(); self.setUp()   # a fresh tree: run_check leaves its save files behind
            ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + [p for p in CA.ROUND8_PACKS if p != z])
            self.assertFalse(ok, z)
            self.assertIn(f"{z}.zip is missing", note)

    def test_round11_packs_are_required_and_paused_keys_left_out(self):
        # round 11: bt-ch18..23, cq-ch10..12, rv-ch15..17; cq-ch13 / rv-ch18 paused unverified (F-025)
        want = ({f"bt-ch{n}-clear" for n in range(18, 24)} | {f"cq-ch{n}-clear" for n in range(10, 13)}
                | {f"rv-ch{n}-clear" for n in range(15, 18)})
        self.assertLessEqual(want, set(CA.ROUND8_PACKS))
        self.routes["cq-ch13"] = {"save": "cq-ch12-clear", "verified": False}   # no checkpoints, no pack: still fine
        ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + list(CA.ROUND8_PACKS))
        self.assertTrue(ok, note)
        self.assertIn("unverified cq-/rv- key(s) left out: cq-ch13, cq-ch7", note)
        self.tearDown(); self.setUp()
        ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + [p for p in CA.ROUND8_PACKS if p != "bt-ch23-clear"])
        self.assertFalse(ok)
        self.assertIn("bt-ch23-clear.zip is missing", note)

    def test_round12_pack_is_required(self):
        # round 12: Birthright only (F-025), bt-ch24 proven as its own step; cq-ch13 / rv-ch18 still paused
        self.assertIn("bt-ch24-clear", CA.ROUND8_PACKS)
        ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + [p for p in CA.ROUND8_PACKS if p != "bt-ch24-clear"])
        self.assertFalse(ok)
        self.assertIn("bt-ch24-clear.zip is missing", note)

    def test_round13_pack_is_required(self):
        # round 13: Birthright only (F-025), bt-ch25 proven as its own step; cq-ch13 / rv-ch18 still paused
        self.assertIn("bt-ch25-clear", CA.ROUND8_PACKS)
        ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + [p for p in CA.ROUND8_PACKS if p != "bt-ch25-clear"])
        self.assertFalse(ok)
        self.assertIn("bt-ch25-clear.zip is missing", note)

    def test_round14_pack_is_required(self):
        # round 14: Birthright only (F-025), bt-ch26 proven as its own step; cq-ch13 / rv-ch18 still paused
        self.assertIn("bt-ch26-clear", CA.ROUND8_PACKS)
        ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + [p for p in CA.ROUND8_PACKS if p != "bt-ch26-clear"])
        self.assertFalse(ok)
        self.assertIn("bt-ch26-clear.zip is missing", note)

    def test_round15_no_clear_save_after_bt_ch27(self):
        # round 15: bt-ch27 is verified, but the game makes no save after chapter 27 (straight to the Endgame
        # Preparations), so bt-ch27-clear is never required and a copy equal to bt-ch26-clear is refused
        self.assertNotIn("bt-ch27-clear", CA.ROUND8_PACKS)
        self.assertEqual(CA.NO_CLEAR_SAVE, {"bt-ch27": "bt-ch26-clear"})
        base = ["bt-ch4-clear", "bt-ch5-clear"] + list(CA.ROUND8_PACKS)
        ok, note = self.run_check(base)
        self.assertTrue(ok, note)
        self.assertIn("no clear save by design: bt-ch27", note)
        ok, note = self.run_check(base + ["bt-ch27-clear"])          # every test zip holds b"PK": a copy of bt-ch26
        self.assertFalse(ok)
        self.assertIn("bt-ch27-clear.zip is byte-identical to bt-ch26-clear.zip", note)
        (self.root / "build/harness/saves/bt-ch27-clear.zip").write_bytes(b"PK other")
        ok, note = CA.check_robot_routes(CA.Ctx(root=self.root, log_dir=self.root / "logs"))
        self.assertTrue(ok, note)

    def test_round20_packs_are_required_and_unproven_keys_left_out(self):
        # round 20 (F-031): Conquest 13-15 and Revelation 18-20 proven per chapter with their packed clear saves;
        # an unproven next chain (verified false, no checkpoints, no pack) stays out and is named
        want = {"cq-ch13-clear", "cq-ch14-clear", "cq-ch15-clear", "rv-ch18-clear", "rv-ch19-clear", "rv-ch20-clear"}
        self.assertLessEqual(want, set(CA.ROUND8_PACKS))
        self.assertFalse({"cq-ch17-clear", "rv-ch27-clear"} & set(CA.ROUND8_PACKS))
        self.routes["cq-ch7"]["verified"] = True
        self.cps["cq-ch7"] = {"100": {"state": {"route": 1}}}
        self.routes["rv-ch27"] = {"save": "rv-ch26-clear", "verified": False}
        ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + list(CA.ROUND8_PACKS))
        self.assertTrue(ok, note)
        self.assertIn("unverified cq-/rv- key(s) left out: rv-ch27", note)
        self.assertNotIn("cq-ch7,", note)
        for z in sorted(want):
            self.tearDown(); self.setUp()
            ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + [p for p in CA.ROUND8_PACKS if p != z])
            self.assertFalse(ok, z)
            self.assertIn(f"{z}.zip is missing", note)

    def test_round31_packs_are_required(self):
        # round 31 (F-031): Revelation 25 and 26 proven per chapter with their packed clear saves;
        # rv-ch27 was not cleared (no key, no pack) and is not required
        want = {"rv-ch25-clear", "rv-ch26-clear"}
        self.assertLessEqual(want, set(CA.ROUND8_PACKS))
        self.assertNotIn("rv-ch27-clear", CA.ROUND8_PACKS)
        for z in sorted(want):
            self.tearDown(); self.setUp()
            ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + [p for p in CA.ROUND8_PACKS if p != z])
            self.assertFalse(ok, z)
            self.assertIn(f"{z}.zip is missing", note)

    def test_round24_packs_are_required(self):
        # round 24 (F-031): Conquest 16 and Revelation 21-24 proven per chapter with their packed clear saves;
        # cq-ch17 was not cleared (no key, no pack) and is not required
        want = {"cq-ch16-clear", "rv-ch21-clear", "rv-ch22-clear", "rv-ch23-clear", "rv-ch24-clear"}
        self.assertLessEqual(want, set(CA.ROUND8_PACKS))
        self.assertNotIn("cq-ch17-clear", CA.ROUND8_PACKS)
        for z in sorted(want):
            self.tearDown(); self.setUp()
            ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"] + [p for p in CA.ROUND8_PACKS if p != z])
            self.assertFalse(ok, z)
            self.assertIn(f"{z}.zip is missing", note)

    def test_planted_problems_fail(self):
        for change in (lambda: self.cps["cq-ch6"]["100"]["state"].update(route=2),     # wrong route byte
                       lambda: self.cps["rv-ch6"]["100"].pop("state"),                 # route byte never read
                       lambda: self.cps.pop("bt-ch5"),                                 # no checkpoints
                       lambda: self.cps["bt-ch5"].update({"5": {"state": {"route": 1}}}),
                       lambda: self.routes["rv-ch6"].update(save="rv-ch5-clear"),       # not the branch save
                       lambda: self.routes.pop("cq-ch6")):
            self.setUp()
            change()
            ok, note = self.run_check()
            self.assertFalse(ok, note)
            self.tearDown()
        self.setUp()

    def test_missing_pack_fails_only_when_build_exists(self):
        ok, note = self.run_check(["bt-ch4-clear", "bt-ch5-clear"])
        self.assertFalse(ok)
        self.assertIn("cq-ch6-clear.zip is missing", note)


class CheatEndgame(unittest.TestCase):
    """check_cheat_endgame (round 19, F-030) on a made-up routes.json / markers.json."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config" / "harness").mkdir(parents=True)
        self.routes = {"cheat-bt-endgame": {"cheat": True, "save": "bt-ch26-clear", "frames": 100, "save_at": 90,
                                            "pokes": [{"frame": 10, "path": "unit:31232 +0xF3", "size": 1,
                                                       "value": 1, "expect": 78}], "verified": False},
                       "bt-ch27": {"save": "bt-ch26-clear", "verified": True}}
        self.cps = {"cheat-bt-endgame": {"10": {"state": {"units": [16, 1, 0]}}}}
        self.table = dict(CA.CHEAT_NO_CLEAR_SAVE)
        CA.CHEAT_NO_CLEAR_SAVE.clear()
        CA.CHEAT_NO_CLEAR_SAVE["cheat-bt-endgame"] = "bt-ch26-clear"

    def tearDown(self):
        CA.CHEAT_NO_CLEAR_SAVE.clear()
        CA.CHEAT_NO_CLEAR_SAVE.update(self.table)
        self.tmp.cleanup()

    def test_cq_ch27_from_cheat_save_without_pokes(self):
        """round 37: cheat-cq-ch27 starts from the Conquest cheat save cheat-cq-ch26-clear and may declare no pokes
        of its own; from a real-play save the same route fails; a packed cheat-cq-ch27-clear.zip is refused."""
        packs = dict(CA.CHEAT_CQ_PACKS)
        try:
            CA.CHEAT_CQ_PACKS.setdefault("cheat-cq-ch26", "cheat-cq-ch25-clear")
            CA.CHEAT_NO_CLEAR_SAVE["cheat-cq-ch27"] = "cheat-cq-ch26-clear"
            self.routes["cheat-cq-ch27"] = {"cheat": True, "save": "cheat-cq-ch26-clear", "verified": True,
                                            "pokes": []}
            self.cps["cheat-cq-ch27"] = {"5": {"state": {"route": 1}}}
            ok, note = self.run_check(["bt-ch26-clear", "cheat-cq-ch26-clear"])
            self.assertTrue(ok, note)
            self.assertIn("verified: cheat-cq-ch27", note)
            ok, note = self.run_check(["cheat-cq-ch27-clear"])
            self.assertFalse(ok)
            self.assertIn("cheat-cq-ch27-clear.zip exists", note)
            (self.root / "build/harness/saves/cheat-cq-ch27-clear.zip").unlink()
            del CA.CHEAT_CQ_PACKS["cheat-cq-ch26"]
            ok, note = self.run_check()
            self.assertFalse(ok)
            self.assertIn("cheat-cq-ch27: declares no pokes", note)
        finally:
            CA.CHEAT_CQ_PACKS.clear()
            CA.CHEAT_CQ_PACKS.update(packs)

    def test_rv_ch27_clear_zip_is_refused(self):
        """round 36: cheat-rv-ch27 ends before any save; a packed cheat-rv-ch27-clear.zip is a mislabelled rv-ch26."""
        CA.CHEAT_NO_CLEAR_SAVE["cheat-rv-ch27"] = "rv-ch26-clear"
        self.routes["cheat-rv-ch27"] = {"cheat": True, "save": "rv-ch26-clear", "verified": True,
                                        "pokes": [{"frame": 5, "path": "unit:1 +0x12C", "size": 1, "value": 30,
                                                   "expect": 0}]}
        self.cps["cheat-rv-ch27"] = {"5": {"state": {"route": 2}}}
        ok, note = self.run_check(["bt-ch26-clear", "rv-ch26-clear"])
        self.assertTrue(ok, note)
        self.assertIn("verified: cheat-rv-ch27", note)
        ok, note = self.run_check(["cheat-rv-ch27-clear"])
        self.assertFalse(ok)
        self.assertIn("cheat-rv-ch27-clear.zip exists", note)

    def run_check(self, saves=None):
        (self.root / "config/harness/routes.json").write_text(json.dumps({"routes": self.routes}))
        (self.root / "config/harness/markers.json").write_text(json.dumps({"checkpoints": self.cps}))
        if saves is not None:
            d = self.root / "build/harness/saves"
            d.mkdir(parents=True, exist_ok=True)
            for s in saves:
                (d / f"{s}.zip").write_bytes(b"PK")
        return CA.check_cheat_endgame(CA.Ctx(root=self.root, log_dir=self.root / "logs"))

    def test_table_and_row(self):
        self.assertEqual(self.table, {"cheat-bt-endgame": "bt-ch26-clear",
                                                 "cheat-rv-ch27": "rv-ch26-clear",
                                                 "cheat-rv-endgame": "rv-ch26-clear",
                                                 "cheat-cq-ch27": "cheat-cq-ch26-clear",
                                                 "cheat-cq-endgame": "cheat-cq-ch26-clear"})
        self.assertIn("cheat-endgame", [r.id for r in CA.ROWS])
        self.assertFalse({"cq-ch13", "rv-ch18"} & set(self.table))

    def test_good_unverified_and_verified(self):
        ok, note = self.run_check(["bt-ch26-clear"])
        self.assertTrue(ok, note)
        self.assertIn("not yet verified: cheat-bt-endgame", note)
        self.assertIn("real-play bt-endgame unwritten (F-030)", note)
        self.routes["cheat-bt-endgame"]["verified"] = True
        ok, note = self.run_check()
        self.assertTrue(ok, note)
        self.assertIn("verified: cheat-bt-endgame", note)

    def test_clear_save_is_refused(self):
        ok, note = self.run_check(["bt-ch26-clear", "cheat-bt-endgame-clear"])
        self.assertFalse(ok)
        self.assertIn("cheat-bt-endgame-clear.zip exists", note)

    def test_planted_problems_fail(self):
        for change in (lambda: self.routes["cheat-bt-endgame"].pop("cheat"),
                       lambda: self.routes["cheat-bt-endgame"].update(pokes=[]),
                       lambda: self.routes["cheat-bt-endgame"].update(save="bt-ch27-clear"),
                       lambda: self.cps.pop("cheat-bt-endgame"),
                       lambda: self.routes.pop("cheat-bt-endgame")):
            self.tearDown(); self.setUp()
            change()
            ok, note = self.run_check()
            self.assertFalse(ok, note)


class CheatConquest(unittest.TestCase):
    """check_cheat_conquest (round 29, F-033) on a made-up routes.json / markers.json / saves."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config" / "harness").mkdir(parents=True)
        self.routes = {"cheat-cq-ch17": {"cheat": True, "save": "cq-ch16-clear", "frames": 100, "save_at": 90,
                                         "pokes": [{"frame": 10, "path": "unit:1 +0x12C", "size": 1,
                                                    "value": 20, "expect": 0}], "verified": True},
                       "cheat-cq-ch18": {"cheat": True, "save": "cheat-cq-ch17-clear", "verified": False}}
        self.cps = {"cheat-cq-ch17": {"10": {"state": {"route": 1}}}}
        self.mark = True
        self.packs = dict(CA.CHEAT_CQ_PACKS)
        CA.CHEAT_CQ_PACKS.clear()
        CA.CHEAT_CQ_PACKS["cheat-cq-ch17"] = "cq-ch16-clear"

    def tearDown(self):
        CA.CHEAT_CQ_PACKS.clear()
        CA.CHEAT_CQ_PACKS.update(self.packs)
        self.tmp.cleanup()

    def run_check(self, saves=True):
        import zipfile
        (self.root / "config/harness/routes.json").write_text(json.dumps({"routes": self.routes}))
        (self.root / "config/harness/markers.json").write_text(json.dumps({"checkpoints": self.cps}))
        if saves:
            d = self.root / "build/harness/saves"
            d.mkdir(parents=True, exist_ok=True)
            for name in CA.CHEAT_CQ_PACKS:
                with zipfile.ZipFile(d / f"{name}-clear.zip", "w") as zf:
                    zf.writestr("save/x.bin", b"x")
                    if self.mark:
                        zf.writestr(CA.CHEAT_MARK, "{}")
        return CA.check_cheat_conquest(CA.Ctx(root=self.root, log_dir=self.root / "logs"))

    def test_table_and_row(self):
        self.assertEqual(self.packs, {"cheat-cq-ch17": "cq-ch16-clear",
                                      "cheat-cq-ch18": "cheat-cq-ch17-clear",
                                      "cheat-cq-ch19": "cheat-cq-ch18-clear",
                                      "cheat-cq-ch20": "cheat-cq-ch19-clear",
                                      "cheat-cq-ch21": "cheat-cq-ch20-clear",
                                      "cheat-cq-ch22": "cheat-cq-ch21-clear",
                                      "cheat-cq-ch23": "cheat-cq-ch22-clear",
                                      "cheat-cq-ch24": "cheat-cq-ch23-clear",
                                      "cheat-cq-ch25": "cheat-cq-ch24-clear",
                                      "cheat-cq-ch26": "cheat-cq-ch25-clear"})   # the real table (setUp trims it)
        self.assertIn("cheat-conquest", [r.id for r in CA.ROWS])
        self.assertNotIn("cq-ch17-clear", CA.ROUND8_PACKS)

    def test_good(self):
        ok, note = self.run_check()
        self.assertTrue(ok, note)
        self.assertIn("cheat-cq-ch17", note)
        self.assertIn("not listed (not proven): cheat-cq-ch18", note)
        import shutil
        shutil.rmtree(self.root / "build")
        ok, note = self.run_check(saves=False)
        self.assertTrue(ok, note)
        self.assertIn("clear saves not checked", note)

    def test_unmarked_or_missing_save_fails(self):
        self.mark = False
        ok, note = self.run_check()
        self.assertFalse(ok)
        self.assertIn("carries no harness-cheat.json", note)
        (self.root / "build/harness/saves/cheat-cq-ch17-clear.zip").unlink()
        (self.root / "build/harness/saves/other.zip").write_bytes(b"PK")
        ok, note = CA.check_cheat_conquest(CA.Ctx(root=self.root, log_dir=self.root / "logs"))
        self.assertFalse(ok)
        self.assertIn("cheat-cq-ch17-clear.zip is missing", note)

    def test_planted_problems_fail(self):
        for change in (lambda: self.routes["cheat-cq-ch17"].pop("cheat"),
                       lambda: self.routes["cheat-cq-ch17"].update(pokes=[]),
                       lambda: self.routes["cheat-cq-ch17"].update(save="cq-ch17-clear"),
                       lambda: self.routes["cheat-cq-ch17"].update(verified=False),
                       lambda: self.cps.pop("cheat-cq-ch17"),
                       lambda: self.routes.pop("cheat-cq-ch17")):
            self.tearDown(); self.setUp()
            change()
            ok, note = self.run_check()
            self.assertFalse(ok, note)


    def chain(self):
        """Round 32: cheat-cq-ch18 and cheat-cq-ch19 listed, each from the one before's cheat clear save, no
        pokes of their own."""
        CA.CHEAT_CQ_PACKS.update({"cheat-cq-ch18": "cheat-cq-ch17-clear", "cheat-cq-ch19": "cheat-cq-ch18-clear"})
        for name, start in (("cheat-cq-ch18", "cheat-cq-ch17-clear"), ("cheat-cq-ch19", "cheat-cq-ch18-clear")):
            self.routes[name] = {"cheat": True, "save": start, "frames": 100, "save_at": 90, "pokes": [],
                                 "verified": True}
            self.cps[name] = {"10": {"state": {"route": 1}}}

    def test_round32_chain_without_pokes_passes(self):
        self.chain()
        self.routes["cheat-cq-ch20"] = {"cheat": True, "save": "cheat-cq-ch19-clear", "verified": False}
        ok, note = self.run_check()
        self.assertTrue(ok, note)
        self.assertIn("3 proven Conquest cheat route(s)", note)
        self.assertIn("not listed (not proven): cheat-cq-ch20", note)

    def test_round32_chain_problems_fail(self):
        for change in (lambda: self.routes["cheat-cq-ch19"].update(save="cq-ch18-clear"),   # real-play save, no poke
                       lambda: self.routes["cheat-cq-ch18"].update(verified=False),
                       lambda: self.routes["cheat-cq-ch19"].pop("cheat"),
                       lambda: self.cps.pop("cheat-cq-ch18"),
                       lambda: (self.root / "build/harness/saves/cheat-cq-ch19-clear.zip").unlink()):
            self.tearDown(); self.setUp()
            self.chain()
            if change.__code__.co_names and "unlink" in change.__code__.co_names:
                self.run_check()
            change()
            ok, note = (CA.check_cheat_conquest(CA.Ctx(root=self.root, log_dir=self.root / "logs"))
                        if "unlink" in change.__code__.co_names else self.run_check())
            self.assertFalse(ok, note)


class AiScoreParked(unittest.TestCase):
    """check_ai_score_parked (F-025) on a made-up tree."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config" / "harness").mkdir(parents=True)
        (self.root / "config" / "readable").mkdir(parents=True)
        d = self.root / "src" / "readable" / "ai_score"
        d.mkdir(parents=True)
        (d / "ai_score.h").write_text("#include \"fe.h\"\n")
        (d / "ai_score_sim.c.parked").write_text("int x;\n")
        (self.root / "config/readable/functions.csv").write_text("address,name,file\n0x1,a,src/readable/ai/ai_items.c\n")
        (self.root / "config/harness/targets.csv").write_text("address,kind,source\n0x1,override,ai/ai_items.c\n")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self):
        return CA.check_ai_score_parked(CA.Ctx(root=self.root, log_dir=self.root / "logs"))

    def test_parked_tree_passes(self):
        ok, note = self.check()
        self.assertTrue(ok, note)
        self.assertIn("1 .c.parked file(s)", note)

    def test_unparked_body_fails(self):
        (self.root / "src/readable/ai_score/ai_score_sim.c").write_text("int x;\n")
        ok, note = self.check()
        self.assertFalse(ok)
        self.assertIn("ai_score_sim.c is a .c file", note)

    def test_registry_rows_fail(self):
        for rel, line in (("config/readable/functions.csv", "0x2,b,src/readable/ai_score/ai_score_rod.c"),
                          ("config/harness/targets.csv", "0x2,override,ai_score\\ai_score_rod.c")):
            self.setUp()
            with open(self.root / rel, "a") as fh:
                fh.write(line + "\n")
            ok, note = self.check()
            self.assertFalse(ok, rel)
            self.assertIn("names src/readable/ai_score/", note)
            self.tearDown()
        self.setUp()


class Parallel(unittest.TestCase):
    """--jobs: rows side by side, the same verdicts and notes as a serial run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config" / "harness").mkdir(parents=True)
        (self.root / "config" / "harness" / "resources.json").write_text('{"max_parallel_runs": 6}')
        self.out = self.root / "stamps"
        self.out.mkdir()
        self.saved = (dict(CA.PARALLEL_LOCKS), set(CA.PARALLEL_EXCLUSIVE), dict(CA.PARALLEL_WEIGHT))
        # round 13: an integrate shell may export FEF_CHECK_ALL_SLOTS=12; these tests set their own budget
        self.slots_env = os.environ.pop("FEF_CHECK_ALL_SLOTS", None)

    def tearDown(self):
        os.environ.pop("FEF_CHECK_ALL_SLOTS", None)
        if self.slots_env is not None:
            os.environ["FEF_CHECK_ALL_SLOTS"] = self.slots_env
        CA.PARALLEL_LOCKS.clear()
        CA.PARALLEL_LOCKS.update(self.saved[0])
        CA.PARALLEL_EXCLUSIVE = frozenset(self.saved[1])
        CA.PARALLEL_WEIGHT.clear()
        CA.PARALLEL_WEIGHT.update(self.saved[2])
        self.tmp.cleanup()

    def ctx(self, name):
        return CA.Ctx(root=self.root, log_dir=self.root / name)

    def both(self, rows, reasons=None, jobs=3, times=None):
        reasons = reasons or {}
        with open(os.devnull, "w") as quiet:
            ser = CA.run_all(self.ctx("serial"), rows, reasons, stream=quiet)
            par = CA.run_parallel(self.ctx("par"), rows, reasons, jobs, stream=quiet, times=times,
                                  counter=lambda: 0)
        return ser, par

    def test_same_verdicts_and_notes_as_serial(self):
        known = [{"id": "K-1", "match": r"expected difference 42", "note": "named"}]
        rows = [stamp_row("p1", 0.2, self.out, "lint: OK", require=(r"^lint: OK",), note_rx=(r"^(lint: .*)$",)),
                stamp_row("f1", 0.1, self.out, "nope", rc=3),
                stamp_row("k1", 0.1, self.out, "expected difference 42", rc=1, known=known),
                stamp_row("dep", 0.1, self.out, "x", needs=("after:f1",)),
                stamp_row("dep2", 0.1, self.out, "x", needs=("after:p1",)),
                CA.Row("fn", "in process", func=lambda c: (print("hi") or True, "func note")),
                stamp_row("sk", 0.1, self.out),
                stamp_row("miss", 0.1, self.out, "something else", require=(r"^wanted$",))]
        ser, par = self.both(rows, {"sk": "not selected (--skip)"})
        self.assertEqual([r["id"] for r in ser], [r["id"] for r in par], "row order")
        for a, b in zip(ser, par):
            self.assertEqual((a["status"], a["note"], a["selected"]), (b["status"], b["note"], b["selected"]), a["id"])
        self.assertEqual(CA.verdict(ser), CA.verdict(par))
        st = {r["id"]: r["status"] for r in par}
        self.assertEqual(st, {"p1": "PASS", "f1": "FAIL", "k1": "KNOWN", "dep": "SKIP", "dep2": "PASS",
                              "fn": "PASS", "sk": "SKIP", "miss": "FAIL"})

    def test_lane_count_runs_outside_the_lock(self):
        """Round 9: a slow tasklist (the counter) must not hold back a row that finishes meanwhile."""
        rows = [stamp_row("long", 8.0, self.out), stamp_row("short", 5.5, self.out),
                stamp_row("after", 0.1, self.out, needs=("after:short",))]
        ctx = self.ctx("lk")
        seen, calls = [], [0]

        def counter():
            calls[0] += 1
            if calls[0] > 1 and not seen:
                time.sleep(2.0)              # the count is slow; "short" finishes during it
                seen.append("short" in ctx.results)
            return 0
        with open(os.devnull, "w") as quiet:
            par = CA.run_parallel(ctx, rows, {}, None, stream=quiet, counter=counter)
        self.assertTrue(all(r["status"] == "PASS" for r in par), par)
        self.assertEqual(seen, [True], "a row finishing during the lane count waited for the lock")

    def test_rows_overlap_but_locked_rows_never_do(self):
        CA.PARALLEL_LOCKS.update({"l1": ("build:x",), "l2": ("build:x",)})
        rows = [stamp_row("a", 2.0, self.out), stamp_row("b", 2.0, self.out),
                stamp_row("l1", 0.6, self.out), stamp_row("l2", 0.6, self.out)]
        _, par = self.both(rows, jobs=4)
        self.assertTrue(all(r["status"] == "PASS" for r in par), par)
        a, b = span(self.out, "a"), span(self.out, "b")
        self.assertLess(max(a[0], b[0]), min(a[1], b[1]), "free rows run side by side")
        l1, l2 = span(self.out, "l1"), span(self.out, "l2")
        self.assertTrue(l1[1] <= l2[0] or l2[1] <= l1[0], "rows sharing a folder never overlap")

    def test_exclusive_rows_run_alone_after_the_others(self):
        seen = {}

        def check(ctx):
            seen["t"] = time.time()
            return True, "alone"
        rows = [CA.Row("fn", "in process", func=check), stamp_row("a", 0.5, self.out), stamp_row("b", 0.5, self.out)]
        _, par = self.both(rows)
        self.assertGreaterEqual(seen["t"], max(span(self.out, "a")[1], span(self.out, "b")[1]))
        self.assertEqual([r["id"] for r in par], ["fn", "a", "b"])

    def test_longest_first_and_one_lane(self):
        import io
        rows = [stamp_row("short", 0.1, self.out), stamp_row("long", 0.1, self.out)]
        buf = io.StringIO()
        CA.run_parallel(self.ctx("p"), rows, {}, 1, stream=buf, times={"short": 1, "long": 500}, counter=lambda: 0)
        starts = [l.split(":")[0] for l in buf.getvalue().splitlines() if l.endswith(")") and "..." in l]
        self.assertEqual(starts, ["[check-all] long", "[check-all] short"])
        s, l = span(self.out, "short"), span(self.out, "long")
        self.assertLessEqual(l[1], s[0], "one lane: one row at a time")

    def test_lanes_never_take_robot_slots(self):
        r = self.root
        self.assertEqual(CA.lanes_now(r, None, lambda: 0)[0], 6)
        self.assertEqual(CA.lanes_now(r, None, lambda: 2)[0], 4)
        self.assertEqual(CA.lanes_now(r, None, lambda: 6)[0], 1)
        self.assertEqual(CA.lanes_now(r, None, lambda: 12)[0], 1, "a 12-run session leaves one lane")
        self.assertEqual(CA.lanes_now(r, 3, lambda: 1)[0], 3)
        self.assertEqual(CA.lanes_now(r, 8, lambda: 1)[0], 5, "--jobs N is capped by the free slots")
        self.assertEqual(CA.lanes_now(r, None, lambda: None)[0], 1, "uncounted robots: one lane")
        os.environ["FEF_CHECK_ALL_SLOTS"] = "12"
        try:
            self.assertEqual(CA.lanes_now(r, None, lambda: 0)[0], 12)
        finally:
            del os.environ["FEF_CHECK_ALL_SLOTS"]

    def test_slots_env_is_honoured_and_named(self):
        """Round 13: FEF_CHECK_ALL_SLOTS replaces resources.json (up or down), the lane line names the source,
        and an unusable value is ignored out loud, never silently."""
        r = self.root
        self.assertEqual(CA.slot_budget_from(r, {}), (6, "resources.json max_parallel_runs"))
        self.assertEqual(CA.slot_budget_from(r, {"FEF_CHECK_ALL_SLOTS": "12"}), (12, "FEF_CHECK_ALL_SLOTS"))
        self.assertEqual(CA.slot_budget_from(r, {"FEF_CHECK_ALL_SLOTS": " 3 "}), (3, "FEF_CHECK_ALL_SLOTS"))
        for bad in ("0", "-2", "twelve", "1.5"):
            n, src = CA.slot_budget_from(r, {"FEF_CHECK_ALL_SLOTS": bad})
            self.assertEqual(n, 6, bad)
            self.assertIn("ignored", src, bad)
        self.assertEqual(CA.slot_budget_from(r, {"FEF_CHECK_ALL_SLOTS": ""})[1], "resources.json max_parallel_runs")
        os.environ["FEF_CHECK_ALL_SLOTS"] = "12"
        n, why = CA.lanes_now(r, 8, lambda: 1)
        self.assertEqual(n, 8, "--jobs 8 under a 12-slot budget with 1 robot run")
        self.assertIn("budget 12 (FEF_CHECK_ALL_SLOTS)", why)
        os.environ["FEF_CHECK_ALL_SLOTS"] = "2"
        self.assertEqual(CA.lanes_now(r, None, lambda: 0)[0], 2, "the env lowers the budget too")
        self.assertEqual(CA.slot_budget(r), 2)
        self.assertIn("FEF_CHECK_ALL_SLOTS", CA.__doc__, "documented in check_all's help")

    def test_weighted_row_takes_two_lanes(self):
        CA.PARALLEL_WEIGHT["heavy"] = 2
        rows = [stamp_row("heavy", 0.6, self.out), stamp_row("a", 0.6, self.out)]
        _, par = self.both(rows, jobs=2, times={"heavy": 9, "a": 1})
        h, a = span(self.out, "heavy"), span(self.out, "a")
        self.assertLessEqual(h[1], a[0], "a two-lane row fills two lanes")

    def test_times_file_merges_and_feeds_the_order(self):
        p = self.root / "times.json"
        CA.save_times(p, [{"id": "a", "status": "PASS", "seconds": 12.5},
                          {"id": "b", "status": "SKIP", "seconds": 0.0},
                          {"id": "c", "status": "PASS", "seconds": 0.01, "cached": True}])
        CA.save_times(p, [{"id": "d", "status": "FAIL", "seconds": 3.0}])
        self.assertEqual(CA.load_times([p]), {"a": 12.5, "d": 3.0})

    def test_jobs_argument(self):
        with open(os.devnull, "w") as quiet:
            old = sys.stdout
            sys.stdout = quiet
            try:
                rc = CA.main(["--root", str(self.root), "--only", "lint", "--jobs", "many",
                              "--json", str(self.root / "o.json")])
            finally:
                sys.stdout = old
        self.assertEqual(rc, 2)


class RowCache(unittest.TestCase):
    """--cache / --no-cache on a made-up host test: hits, misses on any input change, refusals."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cc = CA.find_host_cc()
        x = self.root / "src" / "readable" / "x"
        (x / "tests").mkdir(parents=True)
        (x / "t.c").write_text('#include "t.h"\nint f(void) { return T; }\n')
        (x / "t.h").write_text("#define T 1\n")
        self.script = x / "tests" / "x_diff.py"
        self.script.write_text(
            "import os\nROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))\n"
            "p = os.path.join(ROOT, 'build', 'count')\nos.makedirs(os.path.dirname(p), exist_ok=True)\n"
            "n = int(open(p).read()) + 1 if os.path.exists(p) else 1\nopen(p, 'w').write(str(n))\n"
            "print('x_diff: OK (10 cases, 0 mismatches, 3/3 planted bugs caught)')\n")
        self.row = CA.Row("x-diff", "made up", cmd=["{py}", "{root}/src/readable/x/tests/x_diff.py"],
                          require=(r"^x_diff: OK",), note_rx=(r"^x_diff: (OK .*)$",))
        self.spec = {"files": ["src/readable/**"], "py": ["src/readable/x/tests/x_diff.py"],
                     "c_dirs": ["src/readable"] if self.cc else [], "include": [], "host_cc": bool(self.cc)}
        CA.CACHE_SPECS["x-diff"] = self.spec
        self.cache_dir = self.root / "cache"

    def tearDown(self):
        CA.CACHE_SPECS.pop("x-diff", None)
        self.tmp.cleanup()

    def count(self) -> int:
        p = self.root / "build" / "count"
        return int(p.read_text()) if p.exists() else 0

    def run_once(self, mode, now=None, row=None):
        ctx = CA.Ctx(root=self.root, log_dir=self.root / "logs")
        ctx.cache, ctx.cache_mode = TC.Cache(self.cache_dir, now=now), mode
        with open(os.devnull, "w") as quiet:
            res = CA.run_all(ctx, [row or self.row], {}, stream=quiet)
        return res[0]

    def test_hit_then_header_change_misses(self):
        r = self.run_once("use")
        self.assertEqual((r["status"], r["cache"]["state"]), ("PASS", "stored"))
        self.assertIn("no clean run", r["cache"]["why"])
        r = self.run_once("clean")
        self.assertEqual((r["status"], self.count()), ("PASS", 2))
        r = self.run_once("use")
        self.assertEqual(r["status"], "PASS")
        self.assertTrue(r.get("cached"), r)
        self.assertTrue(r["note"].startswith("CACHED key=" + r["cache"]["key"]), r["note"])
        self.assertIn("OK (10 cases", r["note"])
        self.assertEqual(self.count(), 2, "a hit runs nothing")
        self.assertIn("CACHED key=", (self.root / "logs" / "x-diff.log").read_text())
        if not self.cc:
            self.skipTest("no host C compiler: the header half needs the preprocessor")
        # the planted change: a header the row's C file includes
        (self.root / "src" / "readable" / "x" / "t.h").write_text("#define T 2\n")
        r = self.run_once("use")
        self.assertFalse(r.get("cached"), r)
        self.assertEqual((r["cache"]["state"], r["cache"]["why"], self.count()), ("stored", "no entry for this key", 3))
        r = self.run_once("use")
        self.assertTrue(r.get("cached"))

    def test_any_declared_input_changes_the_key(self):
        c = TC.Cache(self.cache_dir)
        k0, info, probs = c.key_for(self.root, CA.row_definition(self.row), self.spec, self.cc)
        self.assertEqual(probs, [])
        self.script.write_text(self.script.read_text() + "# changed\n")
        k1 = c.key_for(self.root, CA.row_definition(self.row), self.spec, self.cc)[0]
        changed_row = CA.Row("x-diff", "made up", cmd=self.row.cmd, require=(r"^x_diff: OK \(",))
        k2 = c.key_for(self.root, CA.row_definition(changed_row), self.spec, self.cc)[0]
        os.environ["FE_TESTCACHE_PROBE"] = "1"
        try:
            k3 = c.key_for(self.root, CA.row_definition(self.row), self.spec, self.cc)[0]
        finally:
            del os.environ["FE_TESTCACHE_PROBE"]
        self.assertEqual(len({k0, k1, k2, k3}), 4)

    def test_week_old_clean_run_and_harness_change_refuse_hits(self):
        self.run_once("clean")
        week = time.time() + 8 * 24 * 3600
        r = self.run_once("use", now=week)
        self.assertFalse(r.get("cached"))
        self.assertIn("weekly clean run due", r["cache"]["why"])
        real = TC.harness_digest
        TC.harness_digest = lambda extra=(): "0" * 64
        try:
            r = self.run_once("use")
        finally:
            TC.harness_digest = real
        self.assertFalse(r.get("cached"))
        self.assertIn("harness changed", r["cache"]["why"])

    def test_fail_is_never_stored(self):
        self.run_once("clean")
        self.script.write_text("print('x_diff: FAILED')\n")
        for _ in range(2):
            r = self.run_once("use")
            self.assertEqual(r["status"], "FAIL")
            self.assertFalse(r.get("cached"))
        self.assertEqual(list(self.cache_dir.glob("entries/x-diff/*.json")).__len__(), 1)

    def test_incomplete_declaration_is_never_cached(self):
        self.script.write_text(self.script.read_text()
                               + "CFG = os.path.join(ROOT, 'config', 'x.json')\nprint(CFG)\n")
        for mode in ("clean", "use", "use"):
            r = self.run_once(mode)
            self.assertEqual(r["cache"]["state"], "uncacheable")
            self.assertIn("config/x.json", " ".join(r["cache"]["why"]))
        self.assertEqual(self.count(), 3)

    def test_header_outside_the_declaration_is_never_cached(self):
        if not self.cc:
            self.skipTest("no host C compiler")
        (self.root / "other").mkdir()
        (self.root / "other" / "o.h").write_text("#define O 1\n")
        (self.root / "src" / "readable" / "x" / "t.c").write_text('#include "../../../other/o.h"\nint g;\n')
        probs = TC.Cache(self.cache_dir).key_for(self.root, CA.row_definition(self.row), self.spec, self.cc)[2]
        self.assertTrue(any("other/o.h" in p for p in probs), probs)

    def test_only_reachable_library_code_counts(self):
        lib = self.root / "src" / "readable" / "x" / "tests" / "lib.py"
        lib.write_text("import os\nROOT = '.'\nCFG = os.path.join(ROOT, 'config', 'c.json')\n"
                       "def clean():\n    return 1\n"
                       "def dirty():\n    return open(CFG).read()\n")
        spec = dict(self.spec, c_dirs=[])
        for use, bad in (("clean", False), ("dirty", True)):
            self.script.write_text(f"import lib\nlib.{use}()\n")
            probs = TC.completeness(self.root, spec, TC.expand(self.root, spec["files"]), None)
            self.assertEqual(any("config/c.json" in p for p in probs), bad, (use, probs))
        self.script.write_text("import json_not_declared_anywhere_xyz\n")
        probs = TC.completeness(self.root, spec, TC.expand(self.root, spec["files"]), None)
        self.assertTrue(any("json_not_declared_anywhere_xyz" in p for p in probs), probs)

    def test_real_cache_specs_are_complete(self):
        """Every cached row of check_all declares a complete input list in this repository. An
        incomplete one is only reported (skip): at run time it is never cached, so it is safe."""
        if not (ROOT / "extracted" / "text.bin").is_file() or not self.cc:
            self.skipTest("needs extracted/ and a host C compiler")
        c = TC.Cache(self.cache_dir)
        rows = {r.id: r for r in CA.ROWS}
        gaps = {}
        for rid, spec in CA.CACHE_SPECS.items():
            if rid == "x-diff":
                continue
            self.assertIn(rid, rows)
            _, _, probs = c.key_for(ROOT, CA.row_definition(rows[rid]), spec, self.cc)
            if probs:
                gaps[rid] = probs[:2]
        if gaps:
            self.skipTest(f"uncacheable until CACHE_SPECS is extended (they always run): {gaps}")


def _make_dir_link(link: Path, target: Path) -> str | None:
    """A directory junction (Windows, mklink /J: no admin right needed) or a symlink; None, else why not."""
    try:
        if os.name == "nt":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True,
                               text=True, timeout=60)
            if r.returncode != 0:
                return f"mklink /J failed: {(r.stdout + r.stderr).strip()}"
        else:
            os.symlink(target, link, target_is_directory=True)
    except (OSError, subprocess.SubprocessError) as e:
        return f"no directory link here: {e}"
    return None


def _remove_dir_link(link: Path) -> None:
    """Remove the link itself, never what it points at (cmd rmdir without /s on Windows: no recursive delete)."""
    if not os.path.lexists(link):
        return
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "rmdir", str(link)], capture_output=True, timeout=60)
    else:
        os.unlink(link)


class CacheLinks(unittest.TestCase):
    """Round 85 (docs/PUBLIC_RELEASE_PLAN.md section 4 item 4): a declared folder that is a junction or a symlink
    (extracted/ pointing at another drive) keeps its repository path in testcache.expand(). Before, the glob branch
    resolved the link and relative_to(root) raised ValueError (check_all --cache crashed)."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="tc-links-"))
        self.root = self.base / "repo"
        self.target = self.base / "elsewhere"
        (self.root / "tests").mkdir(parents=True)
        (self.target / "sub").mkdir(parents=True)
        (self.target / "text.bin").write_bytes(b"\x01\x02\x03")
        (self.target / "sub" / "a.bin").write_bytes(b"a")
        self.link = self.root / "extracted"
        why = _make_dir_link(self.link, self.target)
        if why:
            shutil.rmtree(self.base)
            self.skipTest(why)

    def tearDown(self):
        _remove_dir_link(self.link)
        if os.path.lexists(self.link):      # the link is still there: never delete through it
            print(f"\nleft in place (link not removed): {self.link}")
            return
        shutil.rmtree(self.base, ignore_errors=True)

    def test_link_is_real_and_the_old_way_breaks(self):
        self.assertNotEqual(self.link.resolve(), self.link.absolute())
        p = self.link / "text.bin"
        with self.assertRaises(ValueError):
            p.resolve().relative_to(self.root.resolve())

    def test_globs_and_trees_through_the_link_keep_the_repo_path(self):
        self.assertEqual(TC.expand(self.root, ["extracted/text.bin"]), ["extracted/text.bin"])
        self.assertEqual(TC.expand(self.root, ["extracted/*.bin"]), ["extracted/text.bin"])
        self.assertEqual(TC.expand(self.root, ["extracted/**"]), ["extracted/sub/a.bin", "extracted/text.bin"])
        # a relative root (how a caller in the repository folder may pass it) gives the same answer
        here = os.getcwd()
        try:
            os.chdir(self.base)
            self.assertEqual(TC.expand(Path("repo"), ["extracted/*.bin"]), ["extracted/text.bin"])
        finally:
            os.chdir(here)

    def test_the_key_hashes_the_linked_bytes(self):
        files = TC.expand(self.root, ["extracted/text.bin"])
        self.assertEqual(TC.sha256_file(self.root / files[0]), TC.sha256_file(self.target / "text.bin"))
        c = TC.Cache(self.base / "cache")
        spec = {"files": ["extracted/text.bin"], "py": [], "c_dirs": [], "include": [], "host_cc": False}
        k1, info, _probs = c.key_for(self.root, {"id": "t"}, spec, None)
        self.assertEqual(info["files"], 1)
        (self.target / "text.bin").write_bytes(b"\x09")
        k2 = TC.Cache(self.base / "cache").key_for(self.root, {"id": "t"}, spec, None)[0]
        self.assertNotEqual(k1, k2)

    def test_a_path_outside_the_root_is_kept_safely(self):
        got = TC.expand(self.root, ["../elsewhere/text.bin"])
        self.assertEqual(got, ["../elsewhere/text.bin"])
        self.assertTrue((self.root / got[0]).is_file())


if __name__ == "__main__":
    unittest.main()
