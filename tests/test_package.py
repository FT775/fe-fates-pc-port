"""Tests for tools/release/package.py (round 68, release part B, goal 2).

Every test builds a small synthetic git repo in a temporary folder, with a made-up code.bin and made-up reference
files, and runs package.build / privacy_scan / notes / redact on it. Nothing outside the temporary folders is written;
no game data, no ROM and no network are needed. The private strings are made up (a fake USERNAME/USERPROFILE and a
planted term), so the real ones are never part of a test.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "release"))
import package as PK  # noqa: E402

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
FAKE_USER = "Zorblax"
FAKE_HOME = r"C:\Users\Zorblax"
SECRET = "PlantedSecret42"
ENV = {"USERNAME": FAKE_USER, "USERPROFILE": FAKE_HOME}

BASE_FILES = {
    ".gitattributes": "* text=auto eol=lf\n*.bat text eol=crlf\n*.bin binary\n",
    "CREDITS.md": "# Thanks\nSeal of Flames by Laz14, https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0, not included.\n",
    "roms/README.txt": "Put your own dump here.\n",
    "roms/seal/README.txt": "Seal of Flames is by Laz14, GameBanana 656034, CC BY-NC-ND 4.0, not included.\n",
    "mods/README.md": "Mods are made on your PC.\n",
    "PLAY.bat": "@echo off\necho hello\npause\n",
    "patches/zakuro/NOTICE.md": "MIT notice of Zakuro.\n",
    "config/seal/seal_bosses.json": json.dumps({"about": "ids only", "bosses": ["A001", "B002"],
                                                "order": {"A001": 0.25, "B002": 1.0}}) + "\n",
    "docs/REPORT_2027-01-01.md": "# Round 1 report: first steps\n\nTime: counted 1 h.\n\n**Short version:** Things "
                                 "work. Smoke 8/8. Nothing counts as done until you say ok.\n\n## More\nDetails.\n",
    "tools/hello.py": "print('hello')\n",
}


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, creationflags=NO_WINDOW)
    if check and r.returncode:
        raise AssertionError(f"git {args}: {r.stderr.decode(errors='replace')}")
    return r.stdout.decode("utf-8", "replace")


class PackageTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pkgtest_"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "checkout", "-q", "-b", "master")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "test@localhost")
        git(self.repo, "config", "core.autocrlf", "false")
        rnd = random.Random(68)
        self.code = bytes(rnd.getrandbits(8) for _ in range(64 * 1024))
        self.code_bin = self.tmp / "code.bin"
        self.code_bin.write_bytes(self.code)
        self.refs = self.tmp / "refs"
        (self.refs / "rom").mkdir(parents=True)
        (self.refs / "rom" / "table.bin").write_bytes(bytes(rnd.getrandbits(8) for _ in range(500)))
        self.commit(BASE_FILES, "base")

    def tearDown(self):
        def unlock(fn, path, _exc):  # git object files are read-only on Windows: make writable, try again
            try:
                os.chmod(path, 0o700)
                fn(path)
            except OSError:
                pass
        shutil.rmtree(self.tmp, **({"onexc": unlock} if sys.version_info >= (3, 12) else {"onerror": unlock}))

    def write(self, files):
        for p, data in files.items():
            fp = self.repo / p
            if data is None:
                fp.unlink()
                continue
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))

    def commit(self, files, msg):
        self.write(files)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)

    def build(self, tag="r1", prev=None, **kw):
        kw.setdefault("env", ENV)
        kw.setdefault("terms", [SECRET])
        kw.setdefault("email", "")
        kw.setdefault("ref_dirs", [self.refs])
        kw.setdefault("code_bin", self.code_bin)
        kw.setdefault("lanes", 1)
        return PK.build(self.repo, tag, prev, self.tmp / "out" / tag, **kw)

    def specs(self):
        return PK.term_specs(self.repo, ENV, extra=[SECRET], email="")

    def gate(self, res, name):
        return next(g for g in res["gates"] if g["name"] == name)

    def assert_no_clear(self, res):
        blob = json.dumps(res)
        for s in (FAKE_USER, SECRET):
            self.assertNotIn(s, blob)
        rec = (Path(res["zip"]).parent / PK.RESULT_NAME).read_text(encoding="utf-8")
        for s in (FAKE_USER, SECRET):
            self.assertNotIn(s, rec)


class CleanPackage(PackageTestBase):
    def test_clean_package_passes_every_gate(self):
        res = self.build()
        bad = [(g["name"], g["detail"]) for g in res["gates"] if not g["ok"]]
        self.assertEqual(bad, [])
        self.assertTrue(res["ok"])
        self.assertEqual({g["name"] for g in res["gates"]}, set(PK.GATES))
        with zipfile.ZipFile(res["zip"]) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
            self.assertTrue(all(n.startswith("FE-Fates-port-r1/") for n in names))
            self.assertIn("FE-Fates-port-r1/CREDITS.md", names)
            self.assertIn(b"\r\n", z.read("FE-Fates-port-r1/PLAY.bat"))
        out = Path(res["zip"]).parent
        for line in (out / PK.SUMS_NAME).read_text().splitlines():
            h, _, n = line.partition("  ")
            self.assertEqual(hashlib.sha256((out / n).read_bytes()).hexdigest(), h)
        rc = subprocess.run(["git", "-C", str(self.repo), "bundle", "verify", res["bundle"]], capture_output=True,
                            creationflags=NO_WINDOW).returncode
        self.assertEqual(rc, 0)
        self.assertFalse(self.gate(res, "privacy-history")["push_blocked"])

    def test_notes_mark_owner_ok_and_carry_credits(self):
        res = self.build()
        text = Path(res["notes_path"]).read_text(encoding="utf-8")
        self.assertIn("Round 1 report: first steps", text)
        self.assertIn("Things work. Smoke 8/8.", text)
        self.assertIn("waiting for the owner's ok", text)
        self.assertNotIn("Nothing counts as done", text)
        for s in ("Laz14", "https://gamebanana.com/mods/656034", "CC BY-NC-ND 4.0", "Not included", "What you need"):
            self.assertIn(s, text)

    def test_bad_tag_is_refused(self):
        with self.assertRaises(PK.PackageError):
            self.build(tag="r1; rm -rf")


class Privacy(PackageTestBase):
    def test_private_string_in_head_fails_masked(self):
        self.commit({"docs/notes.md": f"Logs are in {FAKE_HOME}\\AppData\\x and {SECRET} said hi.\n"}, "add notes")
        res = self.build()
        g = self.gate(res, "privacy-head")
        self.assertFalse(g["ok"])
        self.assertFalse(res["ok"])
        kinds = {(f["where"], f["kind"]) for f in g["findings"] if f["severity"] == "private"}
        self.assertIn(("docs/notes.md", "home"), kinds)
        self.assertIn(("docs/notes.md", "term"), kinds)
        texts = " ".join(f["text"] for f in g["findings"])
        self.assertIn("C***", texts)
        self.assertIn("P***", texts)
        self.assert_no_clear(res)
        self.assertTrue(res["privacy"]["push_blocked"])

    def test_private_string_only_in_history_blocks_push_only(self):
        self.commit({"docs/old.md": f"user {FAKE_USER} was here\n"}, "oops")
        self.commit({"docs/old.md": None}, "remove it")
        res = self.build()
        self.assertTrue(res["ok"], [(g["name"], g["detail"]) for g in res["gates"] if not g["ok"]])
        g = self.gate(res, "privacy-history")
        self.assertTrue(g["ok"])
        self.assertTrue(g["push_blocked"])
        priv = [f for f in g["findings"] if f["severity"] == "private"]
        self.assertEqual(len(priv), 1)
        self.assertEqual(priv[0]["kind"], "user")
        self.assertEqual(len(priv[0]["commits"]), 2)         # the commit that added it and the one that removed it
        self.assertIn("Z***", priv[0]["text"])
        self.assert_no_clear(res)

    def test_commit_message_is_scanned(self):
        self.commit({"docs/x.md": "x\n"}, f"note from {SECRET}")
        res = self.build()
        g = self.gate(res, "privacy-history")
        self.assertTrue(g["push_blocked"])
        self.assertTrue(any(f["where"].startswith("commit ") for f in g["findings"]))

    def test_privacy_scan_history_and_since(self):
        self.commit({"docs/old.md": f"{SECRET}\n"}, "oops")
        self.commit({"docs/old.md": None}, "remove it")
        git(self.repo, "tag", "-a", "r1", "-m", "r1")
        found = PK.privacy_scan([], history=True, repo=self.repo, specs=self.specs())
        self.assertTrue(any(f["scope"] == "history" and f["severity"] == "private" for f in found))
        self.commit({"docs/new.md": "clean\n"}, "after the tag")
        since = PK.privacy_scan([], history=True, repo=self.repo, since="r1", specs=self.specs())
        self.assertFalse([f for f in since if f["severity"] == "private"])
        items = PK.privacy_scan([("blob.txt", f"hi {FAKE_USER}".encode())], specs=self.specs())
        self.assertEqual([(f["scope"], f["kind"]) for f in items], [("file", "user")])
        self.assertNotIn(FAKE_USER, json.dumps(items))

    def test_terms_come_from_the_environment(self):
        specs = PK.term_specs(self.repo, ENV, email="me@localhost")
        kinds = {t.kind: t for t in specs}
        self.assertEqual(kinds["user"].clear, FAKE_USER)
        self.assertEqual(kinds["home"].clear, FAKE_HOME)
        self.assertNotIn("email", kinds)                     # a placeholder address names no one
        self.assertEqual(kinds["user"].masked, "Z***")
        self.assertEqual(kinds["repo"].severity, "info")
        specs = PK.term_specs(self.repo, {"USERNAME": "ab"}, email="real.person@mail.test")
        kinds = {t.kind for t in specs}
        self.assertNotIn("user", kinds)                      # too short to scan for
        self.assertIn("email", kinds)
        terms = PK.privacy_terms(self.repo, ENV)
        self.assertIn(FAKE_USER, terms)
        self.assertIn(FAKE_HOME, terms)
        # every written form of a path is caught: forward slashes, JSON-escaped, msys, URL-encoded, mangled
        s = self.specs()
        for form in ("C:/Users/Zorblax/x", "C:\\\\Users\\\\Zorblax\\\\x", "/c/Users/Zorblax/x", "C--Users-Zorblax-x",
                     "c:\\users\\zorblax"):
            masked = PK.mask_text(form, s)
            self.assertNotIn("orblax", masked.lower(), form)
        self.assertEqual(PK.mask_text("Quentin and Zorblaxes", s), "Quentin and Zorblaxes")

    def test_redact_current_files(self):
        repo_path = str(self.repo.resolve())
        self.commit({"docs/where.md": f"Home {FAKE_HOME}\\x, repo {repo_path}\\build\n",
                     "tools/run.sh": f'cd "{repo_path}"\n'}, "paths")
        specs = self.specs()
        found = PK.redact(self.repo, write=False, specs=specs)
        self.assertTrue(any(f["kind"] == "home" and f["path"] == "docs/where.md" for f in found))
        self.assertTrue(any(f.get("kept") and f["path"] == "tools/run.sh" for f in found))
        self.assertEqual((self.repo / "docs/where.md").read_text().count(FAKE_USER), 1)    # dry: unchanged
        PK.redact(self.repo, write=True, specs=specs)
        text = (self.repo / "docs/where.md").read_text()
        self.assertNotIn(FAKE_USER, text)
        self.assertIn("<home>\\x", text)
        self.assertIn("<repo>\\build", text)
        self.assertIn(repo_path, (self.repo / "tools/run.sh").read_text())               # a tool keeps its path


class ContentGates(PackageTestBase):
    def test_long_byte_run_fails(self):
        run = self.code[4096:4096 + 64]
        arr = ", ".join(f"0x{b:02x}" for b in run)
        self.commit({"src/leak.c": f"static const unsigned char t[] = {{ {arr} }};\n"}, "leak")
        res = self.build()
        g = self.gate(res, "leak")
        self.assertFalse(g["ok"])
        self.assertIn("zip:src/leak.c", g["detail"])
        self.assertFalse(res["ok"])

    def test_long_byte_run_in_history_only_fails(self):
        arr = ", ".join(f"0x{b:02x}" for b in self.code[8192:8192 + 64])
        self.commit({"src/leak.c": f"unsigned char t[] = {{ {arr} }};\n"}, "leak")
        self.commit({"src/leak.c": None}, "remove leak")
        res = self.build()
        g = self.gate(res, "leak")
        self.assertFalse(g["ok"])                            # the bundle carries the old blob
        self.assertIn("history:src/leak.c", g["detail"])

    def test_missing_code_bin_fails(self):
        res = self.build(code_bin=self.tmp / "nope.bin")
        g = self.gate(res, "leak")
        self.assertFalse(g["ok"])
        self.assertIn("nothing could be checked", g["detail"])

    def test_same_file_as_reference_fails(self):
        data = (self.refs / "rom" / "table.bin").read_bytes().hex()[:200].encode()
        (self.refs / "rom" / "text.txt").write_bytes(data)
        with zipfile.ZipFile(self.refs / "mod.zip", "w") as z:
            z.writestr("inner/readme_of_mod.txt", b"mod text " * 20)
        self.commit({"docs/copy.txt": data, "docs/mod.txt": b"mod text " * 20}, "copies")
        res = self.build()
        g = self.gate(res, "same-file")
        self.assertFalse(g["ok"])
        self.assertTrue(any("zip:docs/copy.txt" in p for p in g["problems"]))
        self.assertTrue(any("zip:docs/mod.txt" in p and "!inner/readme_of_mod.txt" in p for p in g["problems"]))

    def test_no_reference_folder_fails(self):
        res = self.build(ref_dirs=[self.tmp / "missing"])
        self.assertFalse(self.gate(res, "same-file")["ok"])

    def test_seal_numbers_fail(self):
        self.commit({"config/randomizer/seal_rules.json": json.dumps({"units": {"A": {"hp": 20, "str": 5, "mag": 1}},
                                                                     "growth": [40, 35, 10]})}, "seal stats")
        res = self.build()
        g = self.gate(res, "seal-ids")
        self.assertFalse(g["ok"])
        self.assertEqual(len(g["problems"]), 2)

    def test_seal_numbers_fail_in_config_seal(self):
        """Round 83 (F-070, plan risk 1): after the move to config/seal/ the seal-ids gate still reads the rules file."""
        self.commit({"config/seal/seal_rules.json": json.dumps({"units": {"A": {"hp": 20, "str": 5, "mag": 1}},
                                                               "growth": [40, 35, 10]})}, "seal stats, new place")
        res = self.build()
        g = self.gate(res, "seal-ids")
        self.assertFalse(g["ok"])
        self.assertIn("seal_rules.json", g["detail"])

    def test_credits_missing_fails(self):
        self.commit({"CREDITS.md": "# Thanks\nNobody.\n"}, "lost credits")
        res = self.build()
        g = self.gate(res, "credits")
        self.assertFalse(g["ok"])
        self.assertIn("CREDITS.md lacks 'Laz14'", g["detail"])


class SealDataRule(unittest.TestCase):
    """Round 83 (Seal edition split A2, F-070; docs/SEAL_EDITION_PLAN.md risk 1): the seal-ids rule is NOT changed by
    the split. The two Seal rules files still match it at their new place (config/seal/, same names); the harness
    files planned for config/seal/ never do (they hold plain numbers: run overlays, memory frames)."""

    def test_rule_unchanged(self):
        self.assertEqual(PK.SEAL_DATA.pattern, r"^config/(?:[^/]+/)*seal[^/]*\.(json|csv|tsv)$")

    def test_rules_files_match_old_and_new_place(self):
        for p in ("config/seal/seal_rules.json", "config/seal/seal_bosses.json",
                  "config/randomizer/seal_rules.json", "config/randomizer/seal_bosses.json"):
            self.assertTrue(PK.SEAL_DATA.match(p), p)

    def test_harness_files_do_not_match(self):
        for p in ("config/seal/smoke_set.json", "config/seal/smoke_baseline.json", "config/seal/check_paths.json",
                  "config/harness/smoke_set.json", "config/harness/check_paths.json"):
            self.assertIsNone(PK.SEAL_DATA.match(p), p)


EDITIONS = {
    "format": 1, "default": "seal", "vanilla_needs_patch": "0043",
    "editions": {
        "vanilla": {"zip": "FE-Fates-port-{tag}.zip", "bundle": False,
                    "leave_out": ["PLAY SEAL OF FLAMES.bat", "roms/seal/", "config/seal/", "tools/seal/", "tests/seal/",
                                  "docs/seal/", "tools/play/sof.py"],
                    "credit_files": {"CREDITS.md": ["Laz14", "gamebanana.com/mods/656034", "CC BY-NC-ND", "included"]}},
        "seal": {"zip": "FE-Fates-port-{tag}-seal-edition.zip", "bundle": True, "leave_out": [],
                 "credit_files": {"CREDITS.md": ["Laz14", "gamebanana.com/mods/656034", "CC BY-NC-ND"],
                                  "roms/seal/README.txt": ["Laz14", "656034", "CC BY-NC-ND"]}}},
    "markers": ["Seal of Flames", "Laz14", "656034", "seal_rules", "seal_bosses", "roms/seal", "--game seal", "sof.py"],
    "marker_allowed_lines": {"CREDITS.md": 1, "README.md": 1},
    "marker_allowed_paths": ["docs/REPORT_*.md", "docs/collab/*"],
    "marker_shared_by_design": [],
}

EDITION_FILES = {
    "config/release/editions.json": json.dumps(EDITIONS, indent=1) + "\n",
    "patches/zakuro/0043-page-picker-hide.patch": "the page only when the mod is installed\n",
    "PLAY SEAL OF FLAMES.bat": "@echo off\r\necho seal\r\n",
    "tools/seal/sof.py": "print('installer')\n",
    "tests/seal/__init__.py": "",
    "docs/seal/README.md": "Seal of Flames by Laz14, https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0.\n",
    "tools/play/sof.py": "# stub: runs tools/seal/sof.py\n",
    "README.md": "# The port\nFates with the port's extras. Seal of Flames edition: see docs/seal/README.md.\n",
}


class Editions(PackageTestBase):
    """Round 84 (Seal edition split B, docs/SEAL_EDITION_PLAN.md section 6): package --edition vanilla|seal."""

    def setUp(self):
        super().setUp()
        self.commit(EDITION_FILES, "editions")

    def zipnames(self, res):
        with zipfile.ZipFile(res["zip"]) as z:
            return z.namelist()

    def test_vanilla_passes_its_gate_set_and_leaves_the_seal_folders_out(self):
        res = self.build(edition="vanilla")
        bad = [(g["name"], g["detail"]) for g in res["gates"] if not g["ok"]]
        self.assertEqual(bad, [])
        self.assertTrue(res["ok"])
        self.assertEqual([g["name"] for g in res["gates"]], PK.gate_set("vanilla"))
        self.assertEqual(set(PK.gate_set("vanilla")), set(PK.GATES) | {"edition"})
        self.assertEqual(res["edition"], "vanilla")
        out = self.tmp / "out" / "r1" / "vanilla"
        self.assertEqual(Path(res["zip"]), out / "FE-Fates-port-r1.zip")
        self.assertIsNone(res["bundle"])
        self.assertFalse(list(out.glob("*.bundle")))
        names = self.zipnames(res)
        self.assertTrue(all(n.startswith("FE-Fates-port-r1/") for n in names))
        rel = [n[len("FE-Fates-port-r1/"):] for n in names]
        for p in ("PLAY SEAL OF FLAMES.bat", "tools/seal/sof.py", "tools/play/sof.py", "docs/seal/README.md",
                  "config/seal/seal_bosses.json", "roms/seal/README.txt", "tests/seal/__init__.py"):
            self.assertNotIn(p, rel)
        self.assertFalse([n for n in rel if n.startswith(("roms/seal", "config/seal", "docs/seal", "tools/seal"))])
        for p in ("CREDITS.md", "roms/README.txt", "tools/hello.py", "PLAY.bat"):
            self.assertIn(p, rel)
        g = self.gate(res, "archive")
        self.assertIn("7 tracked file(s) left out on purpose", g["detail"])
        self.assertEqual(g["left_out"], 7)
        for name in ("bundle-verify", "history-paths", "privacy-history"):
            self.assertTrue(self.gate(res, name)["ok"])
            self.assertTrue(self.gate(res, name)["detail"].startswith("not applicable"), name)
        self.assertIn("0 Seal-derived file(s)", self.gate(res, "seal-ids")["detail"])
        self.assertIn("(vanilla edition)", self.gate(res, "credits")["detail"])
        self.assertNotIn("roms/seal/README.txt", self.gate(res, "credits")["detail"])
        e = self.gate(res, "edition")
        self.assertIn("7 tracked file(s) on the leave-out list, 0 of them in the zip", e["detail"])
        self.assertIn("patch 0043 in the commit", e["detail"])
        sums = (out / PK.SUMS_NAME).read_text().splitlines()
        self.assertEqual(sorted(ln.split("  ")[1] for ln in sums), ["FE-Fates-port-r1.zip", PK.NOTES_NAME])
        self.assert_no_clear(res)

    def test_seal_edition_is_todays_zip_in_its_own_folder(self):
        res = self.build(edition="seal")
        self.assertTrue(res["ok"], [(g["name"], g["detail"]) for g in res["gates"] if not g["ok"]])
        self.assertEqual({g["name"] for g in res["gates"]}, set(PK.GATES))
        out = self.tmp / "out" / "r1" / "seal"
        self.assertEqual(Path(res["zip"]), out / "FE-Fates-port-r1-seal-edition.zip")
        self.assertTrue(Path(res["bundle"]).is_file())
        rel = [n.split("/", 1)[1] for n in self.zipnames(res) if not n.endswith("/")]
        tracked = git(self.repo, "ls-files").splitlines()
        self.assertEqual(sorted(rel), sorted(tracked))                  # nothing left out
        self.assertIn("roms/seal/README.txt", self.gate(res, "credits")["detail"])

    def test_both_runs_sit_side_by_side(self):
        """plan risk 14: each run deletes only its own files, so both folders keep notes and sums."""
        a = self.build(edition="seal")
        b = self.build(edition="vanilla")
        self.assertTrue(a["ok"] and b["ok"])
        base = self.tmp / "out" / "r1"
        for ed in ("seal", "vanilla"):
            for f in (PK.NOTES_NAME, PK.SUMS_NAME, PK.RESULT_NAME):
                self.assertTrue((base / ed / f).is_file(), (ed, f))
            for line in (base / ed / PK.SUMS_NAME).read_text().splitlines():
                h, _, n = line.partition("  ")
                self.assertEqual(hashlib.sha256((base / ed / n).read_bytes()).hexdigest(), h)
        self.assertTrue((base / "seal" / "FE-Fates-port-r1-seal-edition.zip").is_file())
        self.assertTrue((base / "vanilla" / "FE-Fates-port-r1.zip").is_file())
        self.assertFalse((base / PK.NOTES_NAME).exists())                # nothing in the shared out folder itself
        again = self.build(edition="vanilla")                           # a rerun replaces only its own folder
        self.assertTrue(again["ok"])
        self.assertTrue((base / "seal" / "fe-fates-r1.bundle").is_file())

    def test_no_flag_is_todays_package(self):
        res = self.build()
        self.assertEqual(Path(res["zip"]), self.tmp / "out" / "r1" / "FE-Fates-port-r1.zip")
        self.assertEqual(res["edition"], "seal")
        self.assertIsNone(res["edition_flag"])
        self.assertEqual({g["name"] for g in res["gates"]}, set(PK.GATES))
        self.assertTrue(res["ok"], [(g["name"], g["detail"]) for g in res["gates"] if not g["ok"]])

    def test_marker_outside_the_allowed_lines_fails(self):
        self.commit({"tools/run.py": "# runs tools/play/sof.py\n",
                     "docs/REPORT_2027-01-02.md": "# Round 2 report\n\n**Short version:** Seal of Flames work.\n",
                     "docs/collab/GROK.md": "Laz14 chat\n"}, "markers")
        res = self.build(edition="vanilla")
        g = self.gate(res, "edition")
        self.assertFalse(g["ok"])
        self.assertFalse(res["ok"])
        self.assertTrue(any(p.startswith("marker: tools/run.py:1 'sof.py'") for p in g["problems"]), g["problems"])
        self.assertFalse([p for p in g["problems"] if "REPORT_" in p or "collab" in p])  # frozen history: allowed

    def test_two_marker_lines_in_readme_fail_one_passes(self):
        self.commit({"README.md": "# Port\nSeal of Flames edition: docs/seal.\nPut it in roms\\seal\\.\n"}, "two")
        g = self.gate(self.build(edition="vanilla"), "edition")
        self.assertFalse(g["ok"])
        self.assertIn("README.md: 2 lines hold a Seal marker (allowed 1", g["detail"])

    def test_shared_by_design_is_info_not_a_failure(self):
        ed = json.loads(json.dumps(EDITIONS))
        ed["marker_shared_by_design"] = ["patches/zakuro/*"]
        self.commit({"config/release/editions.json": json.dumps(ed),
                     "patches/zakuro/0042-x.patch": "Seal of Flames New Game hook\n"}, "shared")
        res = self.build(edition="vanilla")
        g = self.gate(res, "edition")
        self.assertTrue(g["ok"], g["detail"])
        self.assertTrue(any("0042-x.patch" in i and "shared by design" in i for i in g["marker_info"]))

    def test_the_bare_word_seal_is_not_a_marker(self):
        rx = PK.marker_rx(EDITIONS["markers"])
        for s in ("Master Seal", "Heart Seal", "battle_seal_effect", "a sealed throne room", "offspring_seal_level",
                  "roms/sealed", "xsof.py", "Laz140", "game sealx"):
            self.assertIsNone(rx.search(s), s)
        for s in ("roms\\seal", "roms\\\\seal\\\\x", "ROMS/SEAL", "seal of flames", "run --game seal now",
                  "tools/play/sof.py", "SEAL_BOSSES.md", "gamebanana 656034"):
            self.assertIsNotNone(rx.search(s), s)

    def test_gate_r84_other_spellings_and_one_folder_globs(self):
        """round 84 gate (review of B6): the marker words also match written as one identifier or with '=', a
        '*' in a path pattern stays inside one folder, and a config/seal* folder is caught by its own name"""
        rx = PK.marker_rx(EDITIONS["markers"])
        for s in ("docs/SEAL_OF_FLAMES_PATH.md", "SealOfFlames", "--game=seal"):
            self.assertIsNotNone(rx.search(s), s)
        for s in ("play/seal-of-flames", "--game sealx"):
            self.assertIsNone(rx.search(s), s)
        self.assertTrue(PK._glob_hit("tools/randomizer/sources.py", ["tools/randomizer/*"]))
        self.assertFalse(PK._glob_hit("tools/randomizer/deep/q.py", ["tools/randomizer/*"]))
        self.assertTrue(PK._glob_hit("docs/collab/reviews/x.md", ["docs/collab/**"]))
        self.assertTrue(PK.SEAL_NAMED_CONFIG.match("config/seal/smoke_set.json"))
        self.assertIsNone(PK.SEAL_NAMED_CONFIG.match("config/harness/smoke_set.json"))
        real = json.loads((ROOT / "config" / "release" / "editions.json").read_text(encoding="utf-8"))
        wide = [p for p in real["marker_shared_by_design"] if "*" in p and p != "patches/zakuro/*.patch"]
        self.assertEqual(wide, [], "shared-by-design entries are exact paths")

    def test_worktree_markers_sees_new_untracked_files(self):
        """round 84 repair: package.py markers also scans the new files git does not ignore (a commit would hold
        them), not only the tracked ones; ignored files stay out"""
        self.write({"tests/_helper_new.py": "RULES = 'config/seal/seal_rules.json'\n",
                    ".gitignore": "ignored_dir/\n", "ignored_dir/x.py": "seal_rules\n"})
        res = PK.worktree_markers(self.repo)
        self.assertTrue(any(b.startswith("tests/_helper_new.py") for b in res["bad"]), res["bad"])
        self.assertFalse(any("ignored_dir" in b for b in res["bad"] + res["info"]))

    def test_seal_named_config_file_fails(self):
        self.commit({"config/harness/seal_jobs.json": json.dumps({"about": "ids", "jobs": ["A"]})}, "seal config")
        g = self.gate(self.build(edition="vanilla"), "edition")
        self.assertFalse(g["ok"])
        self.assertIn("config/harness/seal_jobs.json: a config/**/seal* file", g["detail"])

    def test_vanilla_needs_the_page_hide_patch(self):
        self.commit({"patches/zakuro/0043-page-picker-hide.patch": None}, "no 0043")
        g = self.gate(self.build(edition="vanilla"), "edition")
        self.assertFalse(g["ok"])
        self.assertIn("patch 0043 (the Seal page hide) is not in this commit", g["detail"])

    def test_archive_gate_wants_exactly_the_leave_out_list_missing(self):
        self.commit({".gitattributes": BASE_FILES[".gitattributes"] + "tools/hello.py export-ignore\n"}, "ignore")
        g = self.gate(self.build(edition="vanilla"), "archive")
        self.assertFalse(g["ok"])
        self.assertIn("1 tracked files missing (export-ignore?): tools/hello.py", g["detail"])

    def test_vanilla_credits_need_the_one_line_and_not_roms_seal(self):
        self.commit({"CREDITS.md": "# Thanks\nSeal of Flames by Laz14 (https://gamebanana.com/mods/656034, "
                                   "CC BY-NC-ND 4.0) is a separate fan mod.\n"}, "no 'included'")
        g = self.gate(self.build(edition="vanilla"), "credits")
        self.assertFalse(g["ok"])
        self.assertIn("CREDITS.md lacks 'included'", g["detail"])

    def test_vanilla_without_editions_file_refuses(self):
        self.commit({"config/release/editions.json": None}, "no editions")
        with self.assertRaises(PK.PackageError):
            self.build(edition="vanilla")
        self.assertTrue(self.build(edition="seal")["ok"])                # seal falls back to today's credits
        with self.assertRaises(PK.PackageError):
            self.build(edition="deluxe")

    def test_leave_out_rule(self):
        lo = EDITIONS["editions"]["vanilla"]["leave_out"]
        for p in ("docs/seal/README.md", "docs/seal/", "roms/seal/README.txt", "PLAY SEAL OF FLAMES.bat",
                  "tools/play/sof.py"):
            self.assertTrue(PK.is_left_out(p, lo), p)
        for p in ("docs/sealx/a.md", "docs/SEAL_EDITION_PLAN.md", "tools/play/sof.pyc", "PLAY.bat", "roms/README.txt",
                  "tools/play/launcher.py"):
            self.assertFalse(PK.is_left_out(p, lo), p)
        with self.assertRaises(PK.PackageError):
            PK.edition_conf({"editions": {"vanilla": {"leave_out": ["../x"]}}}, "vanilla")


class EditionNotes(PackageTestBase):
    def setUp(self):
        super().setUp()
        self.commit(dict(EDITION_FILES, **{
            "docs/REPORT_2027-01-02.md": "# Round 2 report: Seal edition split B\n\n**Short version:** The Seal of "
                                         "Flames files moved to tools/seal. Smoke 6/6. The page robot passed.\n",
            "docs/REPORT_2027-01-03.md": "# Round 3 report: Seal of Flames only\n\n**Short version:** Only Laz14's "
                                         "mod work; roms/seal checked.\n"}), "reports")
        git(self.repo, "tag", "-a", "r1", "-m", "r1")

    def test_vanilla_notes_drop_seal_sentences_and_keep_one_credit_line(self):
        text = PK.notes(self.repo, None, "r2", specs=self.specs(), edition="vanilla")
        rx = PK.marker_rx(EDITIONS["markers"])
        self.assertEqual(len([ln for ln in text.splitlines() if rx.search(ln)]), 1)
        self.assertIn(PK.VANILLA_SEAL_LINE, text)
        self.assertIn("the built-in randomizer", text)
        self.assertIn("### Round 3 report\nSeal edition work is in that edition's notes.", text)
        self.assertNotIn("roms/seal", text)

    def test_vanilla_notes_since_tag(self):
        self.commit({"docs/REPORT_2027-01-04.md": "# Round 4 report: Seal edition split C\n\n**Short version:** "
                                                  "The Seal of Flames files moved. Smoke 6/6. Nothing counts as done "
                                                  "until you say ok.\n"}, "r4")
        text = PK.notes(self.repo, "r1", "r4", specs=self.specs(), edition="vanilla")
        self.assertIn("### Round 4 report\n", text)                    # the title loses its Seal part
        self.assertIn("Smoke 6/6.", text)
        self.assertNotIn("moved", text.split("## Not included")[0])
        self.assertIn("waiting for the owner's ok", text)
        only = "# Round 5 report: x\n\n**Short version:** Only Laz14's mod work.\n"
        self.commit({"docs/REPORT_2027-01-05.md": only}, "r5")
        text = PK.notes(self.repo, "r1", "r5", specs=self.specs(), edition="vanilla")
        self.assertIn("### Round 5 report: x\nSeal edition work is in that edition's notes.", text)

    def test_seal_notes_lead_with_the_credit(self):
        text = PK.notes(self.repo, "r1", "r2", specs=self.specs(), edition="seal")
        self.assertTrue(text.startswith("# FE Fates PC port r2, Seal of Flames edition\n"))
        lead = text.index("## Seal of Flames")
        self.assertLess(lead, text.index("## What changed"))
        for s in ("Laz14", "https://gamebanana.com/mods/656034", "CC BY-NC-ND 4.0", "Not included",
                  "not affiliated", "Bugs in the port go to us"):
            self.assertIn(s, text[lead:text.index("## What changed")])

    def test_real_editions_file_matches_the_plan(self):
        """config/release/editions.json of THIS repo: the Vanilla+ leave-out list of docs/SEAL_EDITION_PLAN.md
        section 6, folders as folders, the markers of section 7."""
        doc = json.loads((ROOT / PK.EDITIONS_PATH).read_text(encoding="utf-8"))
        v = PK.edition_conf(doc, "vanilla")
        for e in ("PLAY SEAL OF FLAMES.bat", "roms/seal/", "config/seal/", "tools/seal/", "tests/seal/", "docs/seal/",
                  "tools/play/sof.py"):
            self.assertIn(e, v["leave_out"])
        self.assertEqual(v["zip"], "FE-Fates-port-{tag}.zip")
        self.assertFalse(v["bundle"])
        s = PK.edition_conf(doc, "seal")
        self.assertEqual(s["leave_out"], [])
        self.assertEqual(s["zip"], "FE-Fates-port-{tag}-seal-edition.zip")
        self.assertEqual(sorted(v["markers"]), sorted(PK.DEFAULT_MARKERS))
        self.assertEqual(doc["default"], PK.DEFAULT_EDITION)
        self.assertNotIn("seal", [m.lower() for m in v["markers"]])
        for p in v["marker_shared_by_design"]:
            self.assertIn(p, doc.get("marker_shared_why", {}), p)
        # round 85 (docs/PUBLIC_RELEASE_PLAN.md sections 4, 5 and 9): more Vanilla+ leave-outs, the notes file, r68
        for e in ("docs/PUBLIC_RELEASE_PLAN.md", "docs/GAME_PICKER.md", "docs/collab/LICENCE_REQUEST_3DSRECOMP.md",
                  "docs/SEAL_OF_FLAMES_PATH.md", "docs/rando/SEAL.md", "docs/rando/SEAL_BOSSES.md",
                  "docs/tests/SEAL_SAVE.md", "tools/harness/robot/endturn.sh", "tools/harness/robot/lb.sh",
                  "tools/harness/robot/lk.sh", "tools/harness/robot/st.sh"):
            self.assertIn(e, v["leave_out"])
        self.assertNotIn("docs/GAME_PICKER.md", v["marker_shared_by_design"])
        self.assertEqual(v["notes"], "config/release/notes/{tag}-vanilla.md")
        self.assertEqual(v["last_public_tag"], "r68")
        self.assertEqual(v["marker_allowed_lines"].get("config/release/notes/*-vanilla.md"), 1)
        self.assertIsNone(s["notes"])


NOTES_CREDIT = ("Seal of Flames by Laz14 (https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0) is a separate fan mod. "
                "It is not included.")
FIXTURE_NOTES = ("# FE Fates PC port r1 (source only)\n\n## What's new since r0\n- A first public copy.\n\n"
                 "## Credits\n" + NOTES_CREDIT + "\n")


class CommittedNotes(PackageTestBase):
    """Round 85 (docs/PUBLIC_RELEASE_PLAN.md section 9 fix 4): a committed notes file config/release/notes/<tag>-
    vanilla.md is the Vanilla+ RELEASE_NOTES.md word for word, still read by the credit, marker, leak and privacy
    gates and listed in SHA256SUMS; without it the notes are made from the reports as before."""

    def setUp(self):
        super().setUp()
        ed = json.loads(json.dumps(EDITIONS))
        ed["editions"]["vanilla"]["notes"] = "config/release/notes/{tag}-vanilla.md"
        ed["editions"]["vanilla"]["last_public_tag"] = "r0"
        ed["marker_allowed_lines"]["config/release/notes/*-vanilla.md"] = 1
        self.commit(dict(EDITION_FILES, **{"config/release/editions.json": json.dumps(ed, indent=1) + "\n",
                                           "config/release/notes/r1-vanilla.md": FIXTURE_NOTES}), "notes")

    def test_the_notes_file_is_used_word_for_word_and_listed_in_the_sums(self):
        res = self.build(edition="vanilla")
        self.assertTrue(res["ok"], [(g["name"], g["detail"]) for g in res["gates"] if not g["ok"]])
        self.assertEqual(res["notes_source"], "config/release/notes/r1-vanilla.md")
        self.assertEqual(Path(res["notes_path"]).read_bytes(), FIXTURE_NOTES.encode("utf-8"))
        out = Path(res["zip"]).parent
        sums = dict(reversed(ln.split("  ")) for ln in (out / PK.SUMS_NAME).read_text().splitlines())
        self.assertEqual(sums[PK.NOTES_NAME], hashlib.sha256(FIXTURE_NOTES.encode("utf-8")).hexdigest())
        self.assertIn("notes (config/release/notes/r1-vanilla.md) 1 marker line(s)", self.gate(res, "edition")["detail"])

    def test_another_tag_or_the_seal_edition_keeps_the_report_notes(self):
        res = self.build(tag="r2", edition="vanilla")
        self.assertEqual(res["notes_source"], "reports")
        self.assertIn("## What changed", Path(res["notes_path"]).read_text(encoding="utf-8"))
        seal = self.build(edition="seal")
        self.assertEqual(seal["notes_source"], "reports")
        self.assertTrue(Path(seal["notes_path"]).read_text(encoding="utf-8").startswith(
            "# FE Fates PC port r1, Seal of Flames edition"))

    def test_gates_read_the_notes_file(self):
        self.commit({"config/release/notes/r1-vanilla.md": "# r1\n\nWhat's new since r0. Thanks to everyone.\n"},
                    "no credit")
        self.assertFalse(self.gate(self.build(edition="vanilla"), "credits")["ok"])
        self.commit({"config/release/notes/r1-vanilla.md": FIXTURE_NOTES + f"Ask {SECRET}.\n"}, "private")
        res = self.build(edition="vanilla")
        self.assertFalse(self.gate(res, "privacy-head")["ok"])
        self.assert_no_clear(res)
        self.commit({"config/release/notes/r1-vanilla.md": FIXTURE_NOTES + "Put the mod in roms/seal.\n"}, "two")
        g = self.gate(self.build(edition="vanilla"), "edition")
        self.assertFalse(g["ok"])
        self.assertTrue(any("lines hold a Seal marker" in p for p in g["problems"]), g["problems"])
        self.commit({"config/release/notes/r1-vanilla.md": FIXTURE_NOTES.replace("since r0", "lately")}, "no tag")
        g = self.gate(self.build(edition="vanilla"), "edition")
        self.assertFalse(g["ok"])
        self.assertTrue(any("never names r0" in p for p in g["problems"]), g["problems"])

    def test_marker_allowed_lines_takes_a_path_pattern(self):
        self.assertEqual(PK._allowed_lines_key("config/release/notes/r9-vanilla.md",
                                               {"config/release/notes/*-vanilla.md": 1}),
                         "config/release/notes/*-vanilla.md")
        self.assertIsNone(PK._allowed_lines_key("config/release/notes/sub/r9-vanilla.md",
                                                {"config/release/notes/*-vanilla.md": 1}))
        self.assertEqual(PK._allowed_lines_key("CREDITS.md", {"CREDITS.md": 1}), "CREDITS.md")
        self.assertEqual(PK.notes_marker_lines(FIXTURE_NOTES), 1)


class BundleRefs(PackageTestBase):
    """Round 85 (plan section 9 fix 3): the Seal bundle and the history scans carry HEAD, master and the tags, never
    the other branches (the helper branches)."""

    def test_helper_branch_stays_out_of_bundle_and_scans(self):
        git(self.repo, "checkout", "-q", "-b", "claude/helper")
        self.commit({"docs/helper.md": f"made by {FAKE_USER}\n"}, f"helper work {SECRET}")
        helper = git(self.repo, "rev-parse", "HEAD").strip()
        git(self.repo, "checkout", "-q", "master")
        git(self.repo, "tag", "-a", "r1", "-m", "r1")
        self.assertEqual(PK._history_refs(self.repo), ["HEAD", "master", "--tags"])
        res = self.build(edition="seal")
        self.assertTrue(res["ok"], [(g["name"], g["detail"]) for g in res["gates"] if not g["ok"]])
        self.assertFalse(self.gate(res, "privacy-history")["push_blocked"])
        heads = git(self.repo, "bundle", "list-heads", res["bundle"])
        self.assertNotIn("claude/helper", heads)
        self.assertNotIn(helper, heads)
        self.assertIn("refs/heads/master", heads)
        self.assertIn("refs/tags/r1", heads)
        found = PK.privacy_scan([], history=True, repo=self.repo, specs=self.specs())
        self.assertFalse([f for f in found if f["severity"] == "private"])

    def test_a_repo_without_master_scans_head_and_tags(self):
        git(self.repo, "branch", "-m", "master", "main")
        self.assertEqual(PK._history_refs(self.repo), ["HEAD", "--tags"])
        self.commit({"docs/x.md": f"{SECRET}\n"}, "x")
        found = PK.privacy_scan([], history=True, repo=self.repo, specs=self.specs())
        self.assertTrue([f for f in found if f["severity"] == "private"])


class WhatYouNeed(unittest.TestCase):
    def test_road_a_and_road_b_in_plain_words_without_mod_markers(self):
        t = PK.WHAT_YOU_NEED
        for s in ("Road A (no build)", "Road B (build it)", "Special Edition (USA)", "decrypted", "PLAY.bat",
                  "docs/BUILD.md", "never share it", "Neither road has been tried on a clean PC"):
            self.assertIn(s, t)
        self.assertIsNone(PK.marker_rx(PK.DEFAULT_MARKERS).search(t))


class ZipReopen(PackageTestBase):
    def test_lf_batch_file_fails(self):
        self.commit({".gitattributes": "* text=auto eol=lf\n*.bat -text\n", "PLAY.bat": "@echo off\necho lf\n"}, "lf")
        res = self.build()
        g = self.gate(res, "zip-reopen")
        self.assertFalse(g["ok"])
        self.assertIn("PLAY.bat: not CRLF", g["detail"])

    def test_extra_file_in_roms_and_binary_fail(self):
        self.commit({"roms/notes.txt": "hi\n", "mods/Thing/table.csv": "a,b\n",
                     "docs/blob.dat": b"abc\0def"}, "junk")
        res = self.build()
        probs = " ".join(self.gate(res, "zip-reopen")["problems"])
        self.assertIn("roms/notes.txt: roms/ may hold only README files", probs)
        self.assertIn("mods/Thing/table.csv", probs)
        self.assertIn("docs/blob.dat: binary content", probs)

    def test_forbidden_path_in_history_fails(self):
        self.commit({"extracted/thing.txt": "x\n"}, "oops")
        self.commit({"extracted/thing.txt": None}, "gone")
        res = self.build()
        g = self.gate(res, "history-paths")
        self.assertFalse(g["ok"])
        self.assertIn("extracted/thing.txt", g["detail"])


class Notes(PackageTestBase):
    def test_notes_since_previous_tag_and_masking(self):
        git(self.repo, "tag", "-a", "r1", "-m", "r1")
        self.commit({"docs/REPORT_2027-01-02.md": f"# Round 2 report: second\n\n**Short version:** Logs in "
                                                  f"{FAKE_HOME}\\AppData by {SECRET}. Done.\n"}, "round 2")
        text = PK.notes(self.repo, "r1", "r2", specs=self.specs())
        self.assertIn("Round 2 report: second", text)
        self.assertNotIn("Round 1 report", text)
        self.assertIn("<home>\\AppData", text)
        self.assertIn("<private>", text)
        self.assertNotIn(FAKE_USER, text)
        self.assertNotIn(SECRET, text)
        self.assertNotIn("waiting for the owner's ok", text)
        first = PK.notes(self.repo, None, "r2", specs=self.specs())
        self.assertIn("Round 2 report", first)
        self.assertNotIn("Round 1 report", first)            # first release: the newest round only
        self.assertIn("first release", first)

    def test_report_without_short_version(self):
        entry = PK._report_entry("docs/REPORT_x.md", "# Round 9 report: odd\n\nTime: 1 h.\n\nIt went fine.\n")
        self.assertIn("Round 9 report: odd", entry)
        self.assertIn("It went fine.", entry)


if __name__ == "__main__":
    unittest.main()
