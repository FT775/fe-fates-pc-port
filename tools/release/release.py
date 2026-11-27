#!/usr/bin/env python3
"""The one-command release (round 68, release part B; build/RELEASE_PLAN_2026-11-23.md; docs/RELEASE.md).

Double-click RELEASE.bat (no engine build) or 'RELEASE WITH ENGINE BUILD.bat' (adds --engine). Standard library only.

    python tools/release/release.py [run]          the release: checks, tests, smoke, package, record, local tag
    python tools/release/release.py status         where things stand (writes nothing)
    python tools/release/release.py undo rNN       put back what release rNN installed; drop its tag if never pushed
    python tools/release/release.py push rNN       OWNER ONLY: send rNN to the private GitHub repo (master -> its
                                                   main, plus the tag; asks you to type rNN back)
    python tools/release/release.py publish rNN    make the public one-commit snapshot of rNN from its Vanilla+ zip
                                                   only (build/publish/rNN/repo), run the hard stops of
                                                   docs/PUBLIC_RELEASE_PLAN.md section 6, print the push and gh
                                                   commands; NEVER pushes or uploads (round 85)
    python tools/release/release.py fixtures [--write]   check (or, inside a round commit, rewrite) the fixture shas
    python tools/release/release.py selftest       tests.test_release + test_package + test_install side by side
                                                   (temp folders and fakes only; check_all row release-selftest)

Options for run: --dry-run (print the plan, counted time per step and every build; writes nothing), --rehearse (all
but backup/install/tag; writes only under build/release/rehearse-<time>/; the clean-tree and on-master checks become
printed warnings, so a round can rehearse before its commit), --engine (build to a staging folder, smoke on it,
back up, install, verify), --full (FULL tests instead of the core), --tag rNN (default: the round after the newest
docs/REPORT_*.md), --yes (skip the 'press Enter' prompts and answer the FULL-due question with 'go on'; refused for
push and undo).

Step order (round-67 critique: safe steps first, the first failure stops everything):
  0 header  1 preflight  2 core (or FULL)  3 engine build to staging (--engine)  4 smoke  5 package + gates + notes
  6 backup + install + verify (--engine; else verify only)  7 record  8 local annotated tag  9 stage screen.
Step 5 runs package twice once config/release/editions.json and the Seal page hide (patch 0043) are in the tree
(round 84): the Seal edition first, then Vanilla+, each in its own folder under <out>/package/ (seal/, vanilla/);
the record keeps both, the tag message is the Seal edition's notes, the public snapshot takes vanilla/ only.
Step 4 then also runs the Seal edition's 2-job smoke set (config/seal/smoke_set.json) after the 6 Vanilla+ jobs.
Nothing here ever pushes on its own; 'push' is a separate command only the owner runs (refused when an agent's
environment is seen). 'publish' only prints the public push; no round or workflow ever runs that push (docs/RELEASE.md). Private strings (user name, home folder, repo path, git e-mail) are worked out at run time and
shown masked ('F***') in everything this tool prints or writes.

Exit codes: 0 done, 1 stopped (one plain line says why and what to do), 2 usage / refused, 3 build/STOP_ROUND.
Every outside effect goes through an Env object (runner, git, prompts, package, install, process list, disk, ROM
check), so tests/test_release.py runs the whole flow in a temp git repo with fakes.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BELOW_NORMAL = 0x00004000 if os.name == "nt" else 0
GB = 1 << 30

EXIT_OK, EXIT_STOP, EXIT_USAGE, EXIT_STOPROUND = 0, 1, 2, 3

# counted seconds per step (round 67 measurements: unit core in 4 lanes, check_all --core --jobs 4 38-48 s,
# smoke 103.9-137.0 s, run_tests --full 189.4 s; package from the round-67 probe: zip 1.3 s, bundle 0.8 s, gates ~30 s;
# smoke-seal: the 2-job Seal set, 53.0 s on 2 lanes at the round-84 gate, build/r84/gate/smoke_seal/results.json)
COUNTED = {
    "preflight": 20, "unit-core": 150, "check_all-core": 50, "unit-full": 190, "smoke": 140, "smoke-seal": 55,
    "package": 45,
    "install": 45, "verify": 5, "record": 2, "tag": 2,
}
LANES = 4
PROCESSES = ("zakuro.exe", "Fire Emblem Fates.exe", "boot-server.exe", "boot.exe")
FULL_PATHS = ("src/readable", "include/readable", "tools/readable", "patches/zakuro", "tools/harness/patches")
FULL_EVERY = 3
FREE_GB, FREE_ENGINE_GB = 20, 10
CAPTURE_LIB = os.path.join("build", "harness", "lib", "0004000000179800.dll")
FIXTURES = os.path.join("config", "release", "fixtures.json")
TAG_RX = re.compile(r"^r(\d+)([a-z]?)$")
AGENT_ENV = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "AI_AGENT")
STALE_STOPS = ("exe", "capture-library")
LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
PRIVATE_REFSPEC = "master:main"          # release.py push: local master -> the private repo's main (round 85 fix 1)

# release.py publish (round 85, docs/PUBLIC_RELEASE_PLAN.md sections 6 and 9 fix 5): the public one-commit snapshot
PUBLIC_URL = "https://github.com/FT775/fe-fates-pc-port.git"
PUBLIC_REPO = "FT775/fe-fates-pc-port"
PUBLIC_NAME, PUBLIC_EMAIL = "FT775", "322806047+FT775@users.noreply.github.com"
PUBLIC_FORBIDDEN_EXT = (".exe", ".dll", ".pdb", ".lib", ".obj", ".pyd", ".so", ".cci", ".3ds", ".cia", ".cxi", ".app",
                        ".romfs", ".bin", ".sav", ".bundle", ".zip", ".7z", ".rar")
PUBLIC_MAX_BYTES = 10 * 1024 * 1024
PUBLIC_CREDIT = ("Laz14", "gamebanana.com/mods/656034", "CC BY-NC-ND 4.0")

# what config/release/fixtures.json lists when rewritten with 'fixtures --write' (inside a round commit only)
DEFAULT_FIXTURES = [
    ("extracted/code.bin", "file", "the game's code: hygiene-leak and the decomp tests skip or pass blind without it"),
    ("extracted/text.bin", "file", "the game's text section: many table tests read it"),
    ("extracted/romfs", "listing", "the game's RomFS: most real-data tests skip without it"),
    ("play/seal-of-flames/data/mods", "listing", "the installed Seal mod copy: the Seal tests skip without it"),
    ("build/r62/check/runs", "tree", "round-62 page runs: the ids fingerprint and page tests"),
    ("build/r63/might/runs", "tree", "round-63 boss-might runs: test_rando_boss_might skips without them"),
]


class Stop(Exception):
    """A plain stop: one line saying what happened and what to do."""

    def __init__(self, msg: str, code: int = EXIT_STOP):
        super().__init__(msg)
        self.code = code


# ------------------------------------------------------------------------------------------------ small helpers
def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_sha(d: str) -> tuple[str, int]:
    """sha256 over every file below d: relative path ('/') and its own sha256, sorted (same as smoke.py)"""
    rows = []
    for top, _dirs, files in os.walk(d):
        for fn in files:
            p = os.path.join(top, fn)
            rows.append(f"{os.path.relpath(p, d).replace(os.sep, '/')}\0{sha256_file(p)}\n")
    rows.sort()
    return hashlib.sha256("".join(rows).encode("utf-8")).hexdigest(), len(rows)


def listing_sha(d: str) -> tuple[str, int]:
    """cheap: sha256 over every file's relative path and size (stat only; for the big RomFS and mod folders)"""
    rows = []
    for top, _dirs, files in os.walk(d):
        for fn in files:
            p = os.path.join(top, fn)
            rows.append(f"{os.path.relpath(p, d).replace(os.sep, '/')}\0{os.path.getsize(p)}\n")
    rows.sort()
    return hashlib.sha256("".join(rows).encode("utf-8")).hexdigest(), len(rows)


def fmt_s(s) -> str:
    if s is None:
        return "-"
    s = float(s)
    if s < 120:
        return f"{s:.0f} s"
    return f"{s / 60:.1f} min"


def ok_of(x) -> bool:
    if isinstance(x, dict):
        return bool(x.get("ok"))
    return bool(getattr(x, "ok", x))


def detail_of(x) -> str:
    if isinstance(x, dict):
        return str(x.get("detail") or x.get("why") or x.get("error") or "")
    return str(getattr(x, "detail", "") or "")


def mask_term(t: str) -> str:
    return (t[:1] or "?") + "***"


# ------------------------------------------------------------------------------------------------ real effects
def real_git(root: str):
    def git(args: list[str], timeout: float = 120) -> tuple[int, str, str]:
        try:
            p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, creationflags=NO_WINDOW)
            return p.returncode, p.stdout, p.stderr
        except (OSError, subprocess.SubprocessError) as e:
            return 99, "", f"{e.__class__.__name__}: {e}"
    return git


def real_git_at(cwd: str, args: list[str], extra_env: dict | None = None, timeout: float = 600) -> tuple[int, str, str]:
    """git in another folder (the public snapshot), hidden, with extra environment (author / committer)"""
    # never let a caller's git variables (a hook, an IDE task) point these commands at another repo
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR",
                        "GIT_NAMESPACE", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CEILING_DIRECTORIES")
           and not k.startswith("GIT_CONFIG")}
    env.update(extra_env or {})
    try:
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, creationflags=NO_WINDOW, env=env)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return 99, "", f"{e.__class__.__name__}: {e}"


def _kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, creationflags=NO_WINDOW)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def real_run(cmd: list[str], cwd: str, log: str, timeout: float, mask=lambda s: s) -> int:
    """run cmd hidden at below-normal priority (subprocess flags; never 'start /belownormal'); its output goes to
    log, masked line by line. Returns the exit code, or -9 after a timeout (the whole process tree is killed)."""
    os.makedirs(os.path.dirname(log), exist_ok=True)
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    with open(log, "w", encoding="utf-8") as out:
        out.write("$ " + mask(" ".join(cmd)) + "\n")
        out.flush()
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             text=True, encoding="utf-8", errors="replace", env=env,
                             creationflags=NO_WINDOW | BELOW_NORMAL)

        def pump():
            for line in p.stdout:
                out.write(mask(line))
                out.flush()
        t = threading.Thread(target=pump, daemon=True)
        t.start()
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(p.pid)
            p.wait()
            rc = -9
        t.join(10)
        p.stdout.close()
        out.write(f"\nEXIT {rc}\n")
    return rc


def real_processes() -> set[str]:
    """lower-case image names now running; raises Stop when Windows cannot say (fails closed)"""
    if os.name != "nt":
        return set()
    try:
        p = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=30,
                           creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as e:
        raise Stop(f"Could not list the running programs ({e.__class__.__name__}). Try again in a minute.")
    if p.returncode != 0:
        raise Stop(f"Could not list the running programs (tasklist exit {p.returncode}). Try again in a minute.")
    names = set()
    for ln in p.stdout.splitlines():
        if ln.startswith('"'):
            names.add(ln.split('","', 1)[0].strip('"').lower())
    return names


def real_ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def real_rom_check(root: str, cache: str | None):
    """(ok, detail): the ROM in roms/ is the clean dump config/game.json names (tools/paths.find_rom)"""
    sys.path.insert(0, os.path.join(root, "tools"))
    try:
        import paths as P  # noqa: WPS433
        kw = {"repo": pathlib.Path(root), "check": "full"}
        if cache:
            kw["cache"] = pathlib.Path(cache)
        rom = P.find_rom(**kw)
        return True, f"ROM checked: roms\\{os.path.basename(str(rom))} matches config/game.json"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def real_full_rows(root: str, engine: bool):
    """(row ids FULL runs, row ids left out and why, counted row-seconds) from tools/check_all.py and the recorded
    build/check_all_times.json. Without --engine the cargo rows and readable-verify are left out (they need builds)."""
    sys.path.insert(0, os.path.join(root, "tools"))
    import check_all as CA  # noqa: WPS433
    times = {}
    try:
        with open(os.path.join(root, "build", "check_all_times.json"), encoding="utf-8") as fh:
            times = json.load(fh).get("seconds", {})
    except (OSError, ValueError):
        pass
    needs_build = sorted({r.id for r in CA.ROWS if (r.cmd and r.cmd[0] == "cargo") or r.id == "readable-verify"})
    skip = [] if engine else needs_build
    _shown, reasons = CA.select_rows(CA.ROWS, None, skip, fast=False, slow=True, skip_unit_dupes=True)
    run = [r.id for r in CA.ROWS if r.id not in reasons]
    builds = [r for r in needs_build if r in run]
    return {"rows": run, "left_out": skip, "row_seconds": sum(float(times.get(r, 0) or 0) for r in run),
            "unknown_time": [r for r in run if r not in times], "builds": builds}


class _Mod:
    """tools/release/<name>.py, imported on first use; passes root= to functions that take it"""

    def __init__(self, name: str, root: str):
        self._name, self._root, self._mod = name, root, None

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        if self._mod is None:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            self._mod = importlib.import_module(self._name)
        fn = getattr(self._mod, attr)
        if not callable(fn):
            return fn
        try:
            params = inspect.signature(fn).parameters
        except (TypeError, ValueError):
            params = {}

        def call(*a, **k):
            if "root" in params and "root" not in k and len(a) < list(params).index("root") + 1:
                k["root"] = self._root
            return fn(*a, **k)
        return call


class Env:
    """every outside effect of a release; tests pass fakes"""

    def __init__(self, root: str = ROOT, *, run=None, git=None, ask=None, say=None, package=None, install=None,
                 processes=None, disk_free=None, rom_check=None, full_rows=None, environ=None, now=None,
                 clock=None, py: str = sys.executable, interactive: bool | None = None, git_at=None):
        self.root = os.path.abspath(root)
        self.run = run or real_run
        self.git = git or real_git(self.root)
        self.git_at = git_at or real_git_at
        self.ask = ask or real_ask
        self._say = say or (lambda s: print(s, flush=True))
        self.package = package or _Mod("package", self.root)
        self.install = install or _Mod("install", self.root)
        self.processes = processes or real_processes
        self.disk_free = disk_free or (lambda p: shutil.disk_usage(p).free)
        self.rom_check = rom_check or (lambda cache=None: real_rom_check(self.root, cache))
        self.full_rows = full_rows or (lambda engine: real_full_rows(self.root, engine))
        self.environ = os.environ if environ is None else environ
        self.now = now or (lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
        self.clock = clock or time.monotonic
        self.py = py
        self._terms = None

    # privacy: the private strings, worked out at run time only, never shown in clear
    def terms(self) -> list[str]:
        if self._terms is None:
            got = []
            try:
                got = list(self.package.privacy_terms() or [])
            except Exception:  # noqa: BLE001
                got = []
            if not got:
                got = own_privacy_terms(self)
            out = set()
            for t in got:
                if not t or len(t) < 3:
                    continue
                out.add(t)
                out.add(t.replace("\\", "/"))
                m = re.match(r"^([A-Za-z]):[\\/](.*)$", t)
                if m:
                    out.add("/" + m.group(1).lower() + "/" + m.group(2).replace("\\", "/"))
            self._terms = sorted(out, key=len, reverse=True)
        return self._terms

    def mask(self, s: str) -> str:
        for t in self.terms():
            s = re.sub(re.escape(t), mask_term(t), s, flags=re.IGNORECASE)
        return s

    def say(self, s: str = "") -> None:
        self._say(self.mask(s))

    def rel(self, p: str) -> str:
        try:
            r = os.path.relpath(p, self.root)
        except ValueError:
            return self.mask(p)
        return self.mask(p) if r.startswith("..") else r


def own_privacy_terms(env: Env) -> list[str]:
    """fallback when package.privacy_terms is not there: USERNAME, the home folder, the repo path, git user.email"""
    out = [env.environ.get("USERNAME") or env.environ.get("USER") or "", os.path.expanduser("~"), env.root]
    rc, mail, _ = env.git(["config", "user.email"])
    if rc == 0:
        out.append(mail.strip())
    return [t for t in out if t and t not in ("~",)]


# ------------------------------------------------------------------------------------------------ repo facts
def report_round(root: str) -> int | None:
    """the round number of the newest docs/REPORT_*.md (its first line says 'Round NN report')"""
    reps = sorted(f for f in os.listdir(os.path.join(root, "docs")) if re.match(r"REPORT_.*\.md$", f)) \
        if os.path.isdir(os.path.join(root, "docs")) else []
    for f in reversed(reps):
        try:
            with open(os.path.join(root, "docs", f), encoding="utf-8") as fh:
                head = fh.read(400)
        except OSError:
            continue
        m = re.search(r"Round\s+(\d+)", head)
        if m:
            return int(m.group(1))
    return None


def tag_key(t: str):
    m = TAG_RX.match(t)
    return (int(m.group(1)), m.group(2)) if m else None


def release_tags(env: Env) -> list[str]:
    rc, out, _ = env.git(["tag", "--list", "r*"])
    tags = [t.strip() for t in out.splitlines() if tag_key(t.strip())] if rc == 0 else []
    return sorted(tags, key=tag_key)


def next_tag(env: Env) -> str:
    n = report_round(env.root)
    if n is None:
        raise Stop("No docs/REPORT_*.md with a round number was found, so the tag is unknown. Give it: --tag rNN.",
                   EXIT_USAGE)
    return f"r{n + 1}"


def prev_tag(env: Env, tag: str) -> str | None:
    k = tag_key(tag)
    older = [t for t in release_tags(env) if tag_key(t) < k]
    return older[-1] if older else None


def tag_exists(env: Env, tag: str) -> bool:
    rc, _o, _e = env.git(["rev-parse", "-q", "--verify", f"refs/tags/{tag}"])
    return rc == 0


def origin_url(env: Env) -> str | None:
    rc, out, _ = env.git(["remote", "get-url", "origin"])
    return out.strip() if rc == 0 and out.strip() else None


def release_dir(env: Env, tag: str) -> str:
    return os.path.join(env.root, "build", "release", tag)


EDITIONS = os.path.join("config", "release", "editions.json")
EDITION_ORDER = ("seal", "vanilla")      # docs/SEAL_EDITION_PLAN.md section 6: seal first, then Vanilla+


def package_editions(env: Env) -> list[str]:
    """[] = one package run, today's (no editions file, or the Seal page hide not in the tree yet: no Vanilla+ zip
    while the page still shows Seal). ['seal', 'vanilla'] = two runs from the same commit, each in its own folder
    (round 84, Seal edition split B)."""
    try:
        with open(os.path.join(env.root, EDITIONS), encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return []
    eds = doc.get("editions") if isinstance(doc, dict) else None
    if not isinstance(eds, dict) or not all(e in eds for e in EDITION_ORDER):
        return []
    need = str(doc.get("vanilla_needs_patch") or "")
    if need:
        pz = os.path.join(env.root, "patches", "zakuro")
        try:
            have = any(n.startswith(need + "-") and n.endswith(".patch") for n in os.listdir(pz))
        except OSError:
            have = False
        if not have:
            return []
    return list(EDITION_ORDER)


SEAL_SMOKE_SET = os.path.join("config", "seal", "smoke_set.json")


def seal_smoke(env: Env) -> bool:
    """True = the smoke step also runs the Seal edition's 2-job set after the Vanilla+ set (plan section 9 call 5:
    the small Seal check runs before a Seal release): the Seal edition will be packaged and its set is there."""
    return bool(package_editions(env)) and os.path.isfile(os.path.join(env.root, SEAL_SMOKE_SET))


def read_record(env: Env, tag: str) -> dict | None:
    p = os.path.join(release_dir(env, tag), "release.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def all_records(env: Env) -> list[dict]:
    top = os.path.join(env.root, "build", "release")
    out = []
    if os.path.isdir(top):
        for d in os.listdir(top):
            if tag_key(d):
                r = read_record(env, d)
                if r:
                    out.append(r)
    return sorted(out, key=lambda r: tag_key(r.get("tag", "r0")) or (0, ""))


def was_pushed(env: Env, tag: str) -> tuple[bool, str]:
    """(pushed?, how we know). Fails closed: if GitHub is set up but cannot be asked, treat as pushed."""
    if os.path.isfile(os.path.join(release_dir(env, tag), "pushed.json")):
        return True, "the release record says it was pushed"
    rec = read_record(env, tag) or {}
    if rec.get("pushed"):
        return True, "the release record says it was pushed"
    if origin_url(env):
        rc, out, _ = env.git(["ls-remote", "--tags", "origin", f"refs/tags/{tag}"], timeout=60)
        if rc != 0:
            return True, "GitHub could not be asked, so the tag is treated as pushed"
        if out.strip():
            return True, "GitHub has this tag"
    return False, "never pushed"


def full_due(env: Env, tag: str) -> list[str]:
    """plain reasons FULL is due (empty: not due)"""
    why = []
    prev = prev_tag(env, tag)
    if prev is None:
        why.append("this is the first release (no earlier r-tag)")
    else:
        rc, out, _ = env.git(["diff", "--name-only", f"{prev}..HEAD", "--", *FULL_PATHS])
        files = [f for f in out.splitlines() if f.strip()] if rc == 0 else []
        if files:
            why.append(f"{len(files)} readable C / engine patch file(s) changed since {prev} (e.g. {files[0]})")
    try:
        with open(os.path.join(env.root, "config", "release", "seed_changes.json"), encoding="utf-8") as fh:
            ch = json.load(fh).get("changes") or []
        if ch:
            why.append(f"config/release/seed_changes.json announces {len(ch)} seed change(s)")
    except (OSError, ValueError):
        pass
    recs = [r for r in all_records(env) if r.get("ok") and not r.get("rehearse")]
    since = 0
    for r in reversed(recs):
        if r.get("full"):
            break
        since += 1
    if since >= FULL_EVERY:
        why.append(f"{since} releases since the last FULL one")
    return why


# ------------------------------------------------------------------------------------------------ fixtures
def fixture_entry(root: str, rel: str, kind: str, why: str) -> dict:
    p = os.path.join(root, rel)
    if kind == "file":
        return {"path": rel, "kind": kind, "sha256": sha256_file(p), "why": why}
    sha, n = (tree_sha if kind == "tree" else listing_sha)(p)
    return {"path": rel, "kind": kind, "sha256": sha, "files": n, "why": why}


def write_fixtures(env: Env) -> str:
    entries, missing = [], []
    for rel, kind, why in DEFAULT_FIXTURES:
        if os.path.exists(os.path.join(env.root, rel)):
            entries.append(fixture_entry(env.root, rel, kind, why))
        else:
            missing.append(rel)
    if missing:
        raise Stop("Cannot write the fixture list: missing " + ", ".join(missing))
    doc = {"about": "shas only (no game data): the inputs the core tests need. 'file' = sha256 of the file; "
                    "'tree' = smoke.py tree_sha (path + content sha of every file); 'listing' = sha256 of every "
                    "file's path and size (stat only, for big folders). smoke_set: its inputs are checked by "
                    "'smoke.py check'. Rewritten only inside a round commit (release.py fixtures --write).",
           "smoke_set": "config/harness/smoke_set.json", "files": entries}
    p = os.path.join(env.root, FIXTURES)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    return p


def check_fixtures(env: Env, log_dir: str | None) -> list[str]:
    """plain problems (empty = all inputs present with the right shas)"""
    p = os.path.join(env.root, FIXTURES)
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as e:
        return [f"{FIXTURES} is missing or unreadable ({e.__class__.__name__})"]
    probs = []
    for e in doc.get("files", []):
        f = os.path.join(env.root, e["path"])
        kind = e.get("kind", "file")
        if not (os.path.isfile(f) if kind == "file" else os.path.isdir(f)):
            probs.append(f"{e['path']} is missing ({e.get('why', '')})")
            continue
        got = sha256_file(f) if kind == "file" else (tree_sha if kind == "tree" else listing_sha)(f)[0]
        if got != e.get("sha256"):
            probs.append(f"{e['path']} differs from {FIXTURES} (expected {str(e.get('sha256'))[:12]}..., "
                         f"got {got[:12]}...)")
    if doc.get("smoke_set") and log_dir is not None:
        rc = env.run([env.py, os.path.join(env.root, "tools", "harness", "smoke.py"), "check"], env.root,
                     os.path.join(log_dir, "smoke-check.log"), 600, env.mask)
        if rc != 0:
            probs.append(f"the smoke inputs are not all there (smoke.py check exit {rc}; "
                         f"log {env.rel(os.path.join(log_dir, 'smoke-check.log'))}); "
                         "run 'python tools/harness/smoke.py fixtures'")
    if log_dir is not None and seal_smoke(env):
        # the Seal edition's 2-job set too, so missing or wrong Seal inputs stop step 1, not step 4
        log = os.path.join(log_dir, "smoke-check-seal.log")
        rc = env.run([env.py, os.path.join(env.root, "tools", "harness", "smoke.py"),
                      "--set", os.path.join(env.root, SEAL_SMOKE_SET), "check"], env.root, log, 600, env.mask)
        if rc != 0:
            probs.append(f"the Seal edition's smoke inputs are not all there (smoke.py --set "
                         f"{SEAL_SMOKE_SET.replace(os.sep, '/')} check exit {rc}; log {env.rel(log)}); "
                         "run 'python tools/harness/smoke.py --set config/seal/smoke_set.json fixtures'")
    return probs


# ------------------------------------------------------------------------------------------------ the plan
def split_stale(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """without --engine: (stale items that stop the release: the exe and the capture library, the ones the
    release ships or verifies; the rest, e.g. boot-server, which the smoke takes from its frozen copies: warnings)"""
    stops = [b for b in items if b.get("build") in STALE_STOPS]
    return stops, [b for b in items if b.get("build") not in STALE_STOPS]


class Opts:
    def __init__(self, **k):
        self.dry_run = k.get("dry_run", False)
        self.rehearse = k.get("rehearse", False)
        self.engine = k.get("engine", False)
        self.full = k.get("full", False)
        self.tag = k.get("tag")
        self.yes = k.get("yes", False)


def make_plan(env: Env, opts: Opts, builds: list[dict], full_info: dict | None) -> list[dict]:
    """[{key, title, counted_s}] in run order"""
    steps = [{"key": "preflight", "title": "Preflight (tree, nothing running, disk, ROM, fixtures, tag, FULL due)",
              "counted_s": COUNTED["preflight"]}]
    if opts.full:
        steps.append({"key": "unit-full", "title": "Unit tests, FULL (run_tests.py --full, 4 lanes)",
                      "counted_s": COUNTED["unit-full"]})
        steps.append({"key": "check_all-full",
                      "title": f"check_all --slow --skip-unit-dupes ({len(full_info['rows'])} rows, 4 lanes)",
                      "counted_s": round(full_info["row_seconds"] / LANES)})
    else:
        steps.append({"key": "unit-core", "title": "Unit tests, core (run_tests.py --core, 4 lanes)",
                      "counted_s": COUNTED["unit-core"]})
        steps.append({"key": "check_all-core", "title": "check_all --core --jobs 4",
                      "counted_s": COUNTED["check_all-core"]})
    if opts.engine:
        steps.append({"key": "engine-build", "title": "Engine build into a staging folder (never into play/)",
                      "counted_s": sum(int(b.get("counted_s") or 0) for b in builds)})
    where = "staged build" if opts.engine else "frozen installed copies"
    if seal_smoke(env):
        steps.append({"key": "smoke", "title": "Smoke: 6 Vanilla+ jobs, then 2 Seal edition jobs ("
                      + where + ")", "counted_s": COUNTED["smoke"] + COUNTED["smoke-seal"]})
    else:
        steps.append({"key": "smoke", "title": "Smoke: 6 robot jobs (the Vanilla+ set) + memory compare ("
                      + where + ")", "counted_s": COUNTED["smoke"]})
    eds = package_editions(env)
    if eds:
        steps.append({"key": "package", "title": "Package x2 (Seal edition, then Vanilla+): zips, notes, sums, "
                      "gates", "counted_s": COUNTED["package"] * len(eds)})
    else:
        steps.append({"key": "package", "title": "Package: zip, git bundle, SHA256SUMS, notes, gates",
                      "counted_s": COUNTED["package"]})
    if opts.engine and not opts.rehearse:
        steps.append({"key": "install", "title": "Back up, install, verify (automatic rollback on any failure)",
                      "counted_s": COUNTED["install"]})
    else:
        steps.append({"key": "verify", "title": "Verify the installed files against their build records",
                      "counted_s": COUNTED["verify"]})
    steps.append({"key": "record", "title": "Record: release.json, FINAL_SHA.txt, UNDO.txt",
                  "counted_s": COUNTED["record"]})
    if not opts.rehearse:
        steps.append({"key": "tag", "title": "Local annotated tag (never pushed here)", "counted_s": COUNTED["tag"]})
    return steps


def header(env: Env, opts: Opts, tag: str, prev: str | None, steps: list[dict], builds: list[dict],
           full_info: dict | None) -> None:
    mode = "DRY RUN (nothing is written)" if opts.dry_run else \
        "REHEARSAL (nothing installed, no tag)" if opts.rehearse else "RELEASE"
    env.say("=" * 78)
    env.say(f"FE Fates port: {mode} {tag}" + (f" (previous release {prev})" if prev else " (first release)"))
    env.say("=" * 78)
    env.say("Tests: " + ("FULL (every unit test and every check_all row)" if opts.full
                         else "CORE (about 10 minutes)"))
    if opts.engine:
        env.say("ENGINE BUILD: YES. These builds will run (going on is your OK for exactly these):")
        if not builds:
            env.say("  none: the installed program is already built from this code (it is reused, not rebuilt)")
        for b in builds:
            env.say(f"  - {b.get('build')}: {b.get('why', '')} (counted {fmt_s(b.get('counted_s'))})")
        if full_info and full_info.get("builds"):
            env.say("  - FULL check_all rows that build: " + ", ".join(full_info["builds"]))
    else:
        env.say("ENGINE BUILD: NO" + (f" (but {len(builds)} part(s) look out of date; see Preflight)" if builds else ""))
    if full_info:
        env.say(f"FULL check_all counted: {fmt_s(full_info['row_seconds'] / LANES)} ({fmt_s(full_info['row_seconds'])} of recorded row time / {LANES} lanes)"
                + (f"; left out (they need builds): {', '.join(full_info['left_out'])}" if full_info["left_out"]
                   else ""))
        if full_info.get("unknown_time"):
            env.say(f"  {len(full_info['unknown_time'])} row(s) have no recorded time and count as 0 s")
    env.say("")
    env.say(f"  {'#':>2}  {'step':<70} counted")
    for i, s in enumerate(steps, 1):
        env.say(f"  {i:>2}  {s['title']:<70} {fmt_s(s['counted_s'])}")
    total = sum(s["counted_s"] for s in steps)
    env.say(f"      {'total (counted)':<70} {fmt_s(total)}")
    env.say("")
    env.say("It never pushes. Pushing is a separate command only you run: RELEASE.bat push " + tag)


# ------------------------------------------------------------------------------------------------ steps
class Run:
    def __init__(self, env: Env, opts: Opts, tag: str, prev: str | None, out: str | None, steps: list[dict],
                 builds: list[dict]):
        self.env, self.opts, self.tag, self.prev, self.out, self.steps = env, opts, tag, prev, out, steps
        self.builds = builds
        self.head = None
        self.staged = None
        self.package = None
        self.packages = {}
        self.public_notes = ""
        self.backup = None
        self.install_result = None
        self.verify = None
        self.full_due = []
        self.skipped = []
        self.notes = ""
        self.started = env.now()
        self.ok = False
        self.failed_step = None
        self.tagged = False

    # ---- helpers
    def log(self, name: str) -> str:
        return os.path.join(self.out, "logs", name)

    def stop_round(self) -> None:
        if os.path.exists(os.path.join(self.env.root, "build", "STOP_ROUND")):
            raise Stop("build/STOP_ROUND exists, so the release stopped. Delete that file to run it again.",
                       EXIT_STOPROUND)

    def sub(self, name: str, cmd: list[str], timeout: float, what_to_do: str) -> None:
        log = self.log(name + ".log")
        shown = [os.path.basename(cmd[0])] + [self.env.rel(c) if os.path.isabs(c) else c for c in cmd[1:]]
        self.env.say(f"     running: {' '.join(shown)}")
        rc = self.env.run(cmd, self.env.root, log, timeout, self.env.mask)
        if rc == -9:
            raise Stop(f"{name} took longer than {fmt_s(timeout)} and was stopped (log {self.env.rel(log)}). "
                       + what_to_do)
        if rc != 0:
            raise Stop(f"{name} failed (exit {rc}; log {self.env.rel(log)}). " + what_to_do)

    # ---- 1 preflight
    def s_preflight(self) -> str:
        env, o = self.env, self.opts
        notes = []
        rc, branch, _ = env.git(["rev-parse", "--abbrev-ref", "HEAD"])
        branch = branch.strip()
        if rc != 0:
            raise Stop("This folder is not a git repository (git rev-parse failed).")
        if branch != "master":
            if not o.rehearse:
                raise Stop(f"You are on '{branch}', not master. Switch to master (git checkout master) and run again.")
            notes.append(f"WARNING (rehearse): on '{branch}', not master")
        rc, st, _ = env.git(["status", "--porcelain"])
        dirty = [ln for ln in st.splitlines() if ln.strip()]
        if rc != 0:
            raise Stop("git status failed. Run 'git status' to see why.")
        if dirty:
            if not o.rehearse:
                raise Stop(f"{len(dirty)} file(s) are changed or new and not committed (first: {dirty[0][3:]}). "
                           "Commit or remove them, then run again.")
            notes.append(f"WARNING (rehearse): {len(dirty)} uncommitted file(s); the package is made from the last "
                         "commit (HEAD), the tests run on the working files")
        self.stop_round()
        running = sorted(n for n in env.processes() if n in {p.lower() for p in PROCESSES})
        if running:
            raise Stop(f"{', '.join(running)} is running. Close the game, Zakuro and any robot run, then run again.")
        lib = os.path.join(env.root, CAPTURE_LIB)
        if os.path.isfile(lib):
            try:
                with open(lib, "r+b"):
                    pass
            except PermissionError:
                raise Stop("The capture library (build/harness/lib) is held by a running program. Wait for the "
                           "robot run to end, then run again.")
            except OSError:
                pass
        need = FREE_GB + (FREE_ENGINE_GB if o.engine else 0)
        free = env.disk_free(env.root)
        if free < need * GB:
            raise Stop(f"Only {free / GB:.1f} GB free on the repo's drive; the release needs {need} GB. "
                       "Free some space, then run again.")
        cache = None
        if self.out:
            cache = os.path.join(self.out, "rom_check.json")
            src = os.path.join(env.root, "build", "rom_check.json")
            if os.path.isfile(src) and not os.path.isfile(cache):
                shutil.copy2(src, cache)
        good, why = env.rom_check(cache)
        if not good:
            raise Stop(f"ROM check failed: {why}")
        probs = check_fixtures(env, os.path.join(self.out, "logs"))
        if probs:
            raise Stop(f"Test inputs: {probs[0]}" + (f" (and {len(probs) - 1} more)" if len(probs) > 1 else "")
                       + ". Without them the tests would skip without a word; put them back, then run again.")
        if tag_exists(env, self.tag):
            raise Stop(f"The tag {self.tag} already exists. Give another one (--tag), or undo it first "
                       f"(RELEASE.bat undo {self.tag}).")
        if not o.engine:
            stops, warns = split_stale(self.builds)
            for b in warns:
                notes.append(f"WARNING: {b.get('build')} looks out of date ({b.get('why', '')}); the smoke uses "
                             "the frozen copies, so this release goes on")
            if stops:
                msg = ("The installed program is out of date for this code ("
                       + "; ".join(f"{b.get('build')}: {b.get('why', '')}" for b in stops)
                       + "). Use 'RELEASE WITH ENGINE BUILD.bat'.")
                if not o.rehearse:
                    raise Stop(msg)
                notes.append("WARNING (rehearse): a real release would stop here: " + msg)
        rc, head, _ = env.git(["rev-parse", "HEAD"])
        self.head = head.strip()
        if not o.full:
            self.full_due = full_due(env, self.tag)
            if self.full_due:
                env.say("     FULL is due: " + "; ".join(self.full_due) + ".")
                if o.yes:
                    env.say("     --yes: going on with the CORE only (FULL stays due).")
                else:
                    ans = env.ask("     Go on with the CORE only? Type Y and Enter for yes, anything else stops: ")
                    if ans.strip().lower() not in ("y", "yes"):
                        raise Stop("Stopped so FULL can run. Run RELEASE.bat --full (it takes longer), or run "
                                   "again and answer Y.")
                self.skipped.append("FULL tests (due: " + "; ".join(self.full_due) + ")")
        for n in notes:
            env.say("     " + n)
        return f"HEAD {self.head[:12]} on {branch}" + (f"; {len(notes)} warning(s)" if notes else "")

    # ---- 2 core / full
    def s_unit(self, profile: str) -> str:
        cmd = [self.env.py, os.path.join(self.env.root, "tools", "release", "run_tests.py"), f"--{profile}",
               "--out", os.path.join(self.out, "tests")]
        self.sub(f"unit-{profile}", cmd, 1800, "Fix the failing test (the log names it), commit, and run again.")
        return f"run_tests.py --{profile} passed"

    def s_check_all(self, profile: str, full_info: dict | None) -> str:
        times = os.path.join(self.out, "check_all_times.json")
        src = os.path.join(self.env.root, "build", "check_all_times.json")
        if os.path.isfile(src) and not os.path.isfile(times):
            shutil.copy2(src, times)
        cmd = [self.env.py, os.path.join(self.env.root, "tools", "check_all.py")]
        if profile == "core":
            cmd += ["--core", "--jobs", str(LANES)]
            timeout = 1200
        else:
            cmd += ["--slow", "--skip-unit-dupes", "--jobs", str(LANES)]
            if full_info and full_info["left_out"]:
                cmd += ["--skip", ",".join(full_info["left_out"])]
            timeout = max(3600, 3 * (full_info or {}).get("row_seconds", 0) / LANES)
        cmd += ["--log-dir", os.path.join(self.out, "check_all"), "--json", os.path.join(self.out, "check_all.json"),
                "--times", times]
        self.sub(f"check_all-{profile}", cmd, timeout, "Fix the failing row (the log names it), commit, and run again.")
        return f"check_all --{'core' if profile == 'core' else 'slow'} passed"

    # ---- 3 engine build
    def s_engine(self) -> str:
        if not self.builds:
            self.staged = None
            return "nothing to build: the installed program matches this code and is reused"
        self.staged = self.env.install.stage_build(self.tag, os.path.join(self.out, "bin"))
        if not self.staged or not os.path.isdir(str(self.staged)):
            raise Stop("The engine build did not leave a staged folder. Read the build log in "
                       f"{self.env.rel(os.path.join(self.out, 'bin'))}; nothing was installed.")
        return f"staged in {self.env.rel(str(self.staged))}"

    # ---- 4 smoke
    def s_smoke(self) -> str:
        self.stop_round()
        cmd = [self.env.py, os.path.join(self.env.root, "tools", "harness", "smoke.py"), "run",
               "--lanes", "2", "--out", os.path.join(self.out, "smoke")]
        if self.staged:
            cmd += ["--bin", str(self.staged)]
        self.sub("smoke", cmd, 900, "Read the smoke log; it names the job and frame that differ. Nothing was "
                 "installed.")
        where = " on the staged build" if self.staged else " on the frozen installed copies"
        if not seal_smoke(self.env):
            return "smoke passed" + where
        # then the Seal edition's own 2 jobs, never at the same time as the Vanilla+ set (plan section 9 call 5)
        self.stop_round()
        cmd = [self.env.py, os.path.join(self.env.root, "tools", "harness", "smoke.py"),
               "--set", os.path.join(self.env.root, SEAL_SMOKE_SET), "run",
               "--lanes", "2", "--out", os.path.join(self.out, "smoke-seal")]
        if self.staged:
            cmd += ["--bin", str(self.staged)]
        self.sub("smoke-seal", cmd, 600, "The Seal edition's smoke failed (the Vanilla+ set passed). "
                 "Read the smoke-seal log; it names the job and frame that differ. Nothing was packaged or "
                 "installed.")
        return "smoke passed (6 Vanilla+ jobs, then 2 Seal edition jobs)" + where

    # ---- 5 package
    def s_package(self) -> str:
        base = os.path.join(self.out, "package")
        eds = package_editions(self.env)
        if not eds:                                  # today's single package
            self.package = self._one_package(base, None)
            self.notes = self._read_notes(self.package)
            gates = self.package.get("gates") or []
            return f"{len(gates)} gate(s) passed; zip {self.env.rel(str(self.package.get('zip')))}"
        # two editions from one commit, each in its own folder (<out>/package/seal, <out>/package/vanilla)
        for ed in eds:
            self.packages[ed] = self._one_package(base, ed)
        self.package = self.packages["seal"]          # the private repo's record, tag message and history checks
        self.notes = self._read_notes(self.package)
        self.public_notes = self._read_notes(self.packages["vanilla"])
        return "; ".join(f"{ed}: {len(p.get('gates') or [])} gate(s) passed, zip "
                         f"{self.env.rel(str(p.get('zip')))}" for ed, p in self.packages.items())

    def _one_package(self, base: str, edition: str | None) -> dict:
        if edition is None:
            res = self.env.package.build(self.env.root, self.tag, self.prev, base)
        else:
            self.env.say(f"     -- {edition} edition --")
            res = self.env.package.build(self.env.root, self.tag, self.prev, base, edition=edition)
        res = res if isinstance(res, dict) else dict(res)
        gates = res.get("gates") or []
        for g in gates:
            self.env.say(f"     {'PASS' if g.get('ok') else 'FAIL'}  {g.get('name')}: {g.get('detail', '')}")
        if not res.get("ok") or any(not g.get("ok") for g in gates):
            if edition:
                self.packages[edition] = res
            bad = next((g for g in gates if not g.get("ok")), {"name": "package", "detail": "not ok"})
            what = f" ({edition} edition)" if edition else ""
            raise Stop(f"Package check failed{what}: {bad.get('name')}: {bad.get('detail', '')}. Fix it, commit, and "
                       "run again. Nothing was installed or tagged.")
        return res

    @staticmethod
    def _read_notes(pk: dict | None) -> str:
        np = (pk or {}).get("notes_path")
        if np and os.path.isfile(np):
            with open(np, encoding="utf-8") as fh:
                return fh.read()
        return ""

    # ---- 6 backup + install + verify / verify only
    def s_install(self) -> str:
        env = self.env
        if not self.staged:
            self.verify = env.install.verify_installed()
            if not ok_of(self.verify):
                raise Stop(f"The installed files do not match their build records: {detail_of(self.verify)}. "
                           "Nothing was changed.")
            return "nothing new to install (the reused program is verified)"
        self.backup = env.install.backup(self.tag)
        if not ok_of(self.backup):
            raise Stop(f"Backup failed: {detail_of(self.backup)}. Nothing was installed.")
        self.save_record()            # so 'undo' finds the backup even if the next line dies
        self.install_result = env.install.install(self.staged, self.backup)
        if not ok_of(self.install_result):
            raise Stop(f"Install failed and was rolled back: {detail_of(self.install_result)}. The old files are "
                       "back in play/; the backups stay in build/backup.")
        self.verify = env.install.verify_installed()
        if not ok_of(self.verify):
            raise Stop(f"The new install does not match its build records: {detail_of(self.verify)}. Run "
                       f"RELEASE.bat undo {self.tag} to put the old files back.")
        return "backed up, installed and verified"

    def s_verify(self) -> str:
        self.verify = self.env.install.verify_installed()
        if not ok_of(self.verify):
            raise Stop(f"The installed files do not match their build records: {detail_of(self.verify)}. Nothing "
                       "was changed; ask for a round to rebuild or re-record them.")
        return "installed files match play/game and engine build records"

    # ---- 7 record
    def record(self) -> dict:
        return {
            "tag": self.tag, "prev_tag": self.prev, "rehearse": self.opts.rehearse, "engine": self.opts.engine,
            "full": self.opts.full, "head": self.head, "started": self.started, "finished": self.env.now(),
            "ok": self.ok, "failed_step": self.failed_step, "installed": bool(self.install_result
                                                                             and ok_of(self.install_result)),
            "builds": self.builds, "staged": self.env.rel(str(self.staged)) if self.staged else None,
            "steps": [{k: s.get(k) for k in ("key", "title", "counted_s", "actual_s", "ok", "detail")}
                      for s in self.steps],
            "full_due": self.full_due, "skipped": self.skipped,
            "package": _jsonable(self.env, self.package),
            "packages": {ed: _jsonable(self.env, p) for ed, p in self.packages.items()},
            "backup": _jsonable(self.env, self.backup),
            "install": _jsonable(self.env, self.install_result), "verify": _jsonable(self.env, self.verify),
            "tagged": self.tagged, "pushed": False,
        }

    def save_record(self) -> None:
        if not self.out:
            return
        os.makedirs(self.out, exist_ok=True)
        p = os.path.join(self.out, "release.json")
        txt = self.env.mask(json.dumps(self.record(), indent=1, default=str))
        with open(p + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(txt + "\n")
        os.replace(p + ".tmp", p)

    def s_record(self) -> str:
        self.save_record()
        lines = [f"release {self.tag}" + (" (REHEARSAL)" if self.opts.rehearse else ""), f"head {self.head}"]
        for ed, pk in (self.packages.items() if self.packages else [(None, self.package or {})]):
            for k in ("zip", "bundle", "sums", "notes_path"):
                f = pk.get(k)
                if f and os.path.isfile(str(f)):
                    lines.append((f"{ed} " if ed else "") + f"{k} {sha256_file(str(f))} {os.path.basename(str(f))}")
        v = self.verify if isinstance(self.verify, dict) else {}
        shas = v.get("shas") or v.get("installed") or {}
        if isinstance(shas, dict):
            for k in sorted(shas):
                lines.append(f"installed {k} {shas[k]}")
        with open(os.path.join(self.out, "FINAL_SHA.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.env.mask("\n".join(lines)) + "\n")
        with open(os.path.join(self.out, "UNDO.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.env.mask(undo_text(self)) + "\n")
        return f"wrote {self.env.rel(self.out)}\\release.json, FINAL_SHA.txt, UNDO.txt"

    # ---- 8 tag
    def s_tag(self) -> str:
        env = self.env
        rc, head, _ = env.git(["rev-parse", "HEAD"])
        if head.strip() != self.head:
            raise Stop("HEAD moved while the release ran (someone committed). Run the release again.")
        rc, st, _ = env.git(["status", "--porcelain"])
        if [ln for ln in st.splitlines() if ln.strip()]:
            raise Stop("Files changed while the release ran. Commit or remove them, then run again.")
        if tag_exists(env, self.tag):
            raise Stop(f"The tag {self.tag} appeared while the release ran. Run again with another --tag.")
        np = (self.package or {}).get("notes_path")
        if np and os.path.isfile(str(np)):
            args = ["tag", "-a", self.tag, "--cleanup=verbatim", "-F", str(np), self.head]
        else:
            args = ["tag", "-a", self.tag, "-m", f"Release {self.tag}", self.head]
        rc, _o, err = env.git(args)
        if rc != 0:
            raise Stop(f"git could not make the tag {self.tag}: {err.strip()[:200]}")
        self.tagged = True
        return f"local tag {self.tag} on {self.head[:12]} (not pushed)"


def _jsonable(env: Env, x):
    if x is None:
        return None
    try:
        return json.loads(env.mask(json.dumps(x, default=str)))
    except (TypeError, ValueError):
        return env.mask(str(x))


def undo_text(r: Run) -> str:
    t = r.tag
    if r.opts.rehearse:
        return (f"Rehearsal of {t}: nothing was installed and no tag was made, so there is nothing to undo. "
                "This folder can be deleted.")
    lines = [f"How to undo release {t}", "", "Open a command window in the repo folder and run:",
             f"    RELEASE.bat undo {t}", "", "It asks you to type the tag back first. Then:"]
    if r.install_result and ok_of(r.install_result):
        lines.append(f"  - it puts back the files saved in build/backup/*.<date>-pre-{t} and checks their shas;")
    else:
        lines.append("  - nothing was installed by this release, so no files are put back;")
    lines += [f"  - it deletes the local tag {t} only if it was never pushed;",
              "  - backups are never deleted."]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ commands
def cmd_run(env: Env, opts: Opts) -> int:
    tag = opts.tag or next_tag(env)
    if not tag_key(tag):
        raise Stop(f"'{tag}' is not a release tag; use r followed by the round number, e.g. r68.", EXIT_USAGE)
    prev = prev_tag(env, tag)
    try:
        # with --engine: what will be built (an exe whose sha equals its build record is reused, not rebuilt);
        # without: what is out of date (install.stale), which stops the release in preflight
        builds = list((env.install.plan(True) if opts.engine else env.install.stale()) or [])
    except Exception as e:  # noqa: BLE001
        raise Stop(f"Could not work out what needs building ({e.__class__.__name__}: {e}).")
    full_info = env.full_rows(opts.engine) if opts.full else None
    steps = make_plan(env, opts, builds, full_info)
    header(env, opts, tag, prev, steps, builds, full_info)
    if opts.dry_run:
        env.say("")
        env.say("Preflight would check: on master, nothing uncommitted, no build/STOP_ROUND, the game / Zakuro / "
                f"boot-server / robot not running, the capture library not held, {FREE_GB}"
                + (f"+{FREE_ENGINE_GB}" if opts.engine else "") + " GB free, the ROM, "
                f"{FIXTURES} and the smoke inputs, tag {tag} free.")
        env.say(f"Tag {tag}: " + ("ALREADY EXISTS (the release would stop)" if tag_exists(env, tag) else "free"))
        if not opts.full:
            why = full_due(env, tag)
            env.say("FULL due: " + ("; ".join(why) + " (you would be asked Y/N)" if why else "no"))
        if builds and not opts.engine:
            stops, warns = split_stale(builds)
            for b in warns:
                env.say(f"Warning only: {b.get('build')} looks out of date ({b.get('why', '')})")
            if stops:
                env.say("Would stop: out of date: " + "; ".join(f"{b.get('build')}: {b.get('why', '')}"
                                                                for b in stops))
        env.say("Dry run: nothing was written.")
        return EXIT_OK
    if not opts.yes:
        ans = env.ask(("Press Enter to start (this is your OK for the builds listed above)" if opts.engine
                       else "Press Enter to start") + ", or type N and Enter to stop: ")
        if ans.strip().lower() in ("n", "no", "q", "quit", "stop"):
            env.say("Not started. Nothing was written.")
            return EXIT_STOP
    if opts.rehearse:
        out = os.path.join(env.root, "build", "release", "rehearse-" + time.strftime("%Y%m%d-%H%M%S"))
    else:
        out = release_dir(env, tag)
        if os.path.isdir(out):
            old = read_record(env, tag) or {}
            if old.get("installed"):
                raise Stop(f"A release record for {tag} with an install already exists. Undo it first "
                           f"(RELEASE.bat undo {tag}).")
            os.replace(out, out + "-failed-" + time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(os.path.join(out, "logs"), exist_ok=True)
    r = Run(env, opts, tag, prev, out, steps, builds)
    funcs = {
        "preflight": r.s_preflight, "unit-core": lambda: r.s_unit("core"), "unit-full": lambda: r.s_unit("full"),
        "check_all-core": lambda: r.s_check_all("core", None),
        "check_all-full": lambda: r.s_check_all("full", full_info),
        "engine-build": r.s_engine, "smoke": r.s_smoke, "package": r.s_package, "install": r.s_install,
        "verify": r.s_verify, "record": r.s_record, "tag": r.s_tag,
    }
    if not opts.engine:
        r.skipped.append("engine build and install (no --engine)")
    if opts.rehearse:
        r.skipped.append("backup, install and tag (rehearsal)")
    r.skipped.append("push (rehearsal)" if opts.rehearse else "push (only you run it: RELEASE.bat push " + tag + ")")
    env.say("")
    for i, s in enumerate(steps, 1):
        try:
            r.stop_round()
            env.say(f"[{i}/{len(steps)}] {s['title']} (counted {fmt_s(s['counted_s'])})")
            t0 = env.clock()
            try:
                try:
                    s["detail"] = funcs[s["key"]]()
                except Stop:
                    raise
                except Exception as e:  # noqa: BLE001  (a tool raised: a plain stop, never a traceback)
                    raise Stop(f"{e.__class__.__name__}: {e}. Nothing after this step ran"
                               + (f"; if files were installed, RELEASE.bat undo {tag} puts the old ones back."
                                  if s["key"] == "install" else "."))
                s["ok"] = True
            finally:
                s["actual_s"] = round(env.clock() - t0, 1)
            env.say(f"     OK in {fmt_s(s['actual_s'])}: {s['detail']}")
            if s["key"] != "record":
                r.save_record()
        except Stop as e:
            s["ok"], s["detail"] = False, str(e)
            r.failed_step = s["key"]
            r.save_record()
            env.say("")
            env.say(f"STOPPED at step {i} ({s['title']}): {e}")
            env.say(f"Record: {env.rel(out)}\\release.json")
            return e.code
    r.ok = True
    r.save_record()
    stage_screen(env, r)
    return EXIT_OK


def stage_screen(env: Env, r: Run) -> None:
    env.say("")
    env.say("=" * 78)
    if r.opts.rehearse:
        env.say("Rehearsal done. " + ("FULL" if r.opts.full else "Core") + " passed. Nothing installed, no tag, "
                "not pushed.")
    else:
        env.say("Ready. Core passed. Not pushed." if not r.opts.full else "Ready. Core passed (FULL). Not pushed.")
    env.say("=" * 78)
    if r.notes:
        env.say("Release notes (check them; they go public when you push):" if not r.packages else
                "Release notes, Seal edition (the tag message; private repo):")
        for ln in r.notes.splitlines():
            env.say("  | " + ln)
        env.say("")
    if r.public_notes:
        env.say("Release notes, Vanilla+ (the public snapshot's notes; check them):")
        for ln in r.public_notes.splitlines():
            env.say("  | " + ln)
        env.say("")
    if r.skipped:
        env.say("Skipped: " + "; ".join(r.skipped) + ".")
    env.say("")
    env.say(f"  {'step':<44} {'counted':>9} {'actual':>9}")
    for s in r.steps:
        env.say(f"  {s['key']:<44} {fmt_s(s['counted_s']):>9} {fmt_s(s.get('actual_s')):>9}")
    env.say(f"  {'total':<44} {fmt_s(sum(s['counted_s'] for s in r.steps)):>9} "
            f"{fmt_s(sum(s.get('actual_s') or 0 for s in r.steps)):>9}")
    env.say("")
    env.say("Files:")
    env.say(f"  {env.rel(r.out)}\\release.json, FINAL_SHA.txt, UNDO.txt")
    for ed, pk in (r.packages.items() if r.packages else [(None, r.package or {})]):
        for k in ("zip", "bundle", "sums", "notes_path"):
            f = pk.get(k)
            if f:
                env.say(f"  {(ed + ' ') if ed else ''}{k}: {env.rel(str(f))}")
    if r.packages:
        env.say("  The public snapshot takes its files from the vanilla folder only; the Seal edition zip stays "
                "private (each upload needs your yes).")
    if r.opts.rehearse:
        return
    env.say("")
    env.say(f"Undo: RELEASE.bat undo {r.tag}")
    env.say(f"Push (only you, when you are ready): RELEASE.bat push {r.tag}")
    if r.packages:
        env.say(f"Public copy: RELEASE.bat publish {r.tag} makes and checks it from the Vanilla+ zip and prints the "
                "push commands (it sends nothing).")
    if not origin_url(env):
        env.say("")
        env.say("First time only, before the push: there is no GitHub link yet.")
        env.say("  1. On github.com, make a new EMPTY repository (no README, no licence, no .gitignore).")
        env.say("  2. Copy its address (https://github.com/<you>/<name>.git) and run, in this folder:")
        env.say("       git remote add origin <that address>")
        env.say(f"  3. Then: RELEASE.bat push {r.tag}  (it shows what goes public and asks you to type {r.tag}).")


def cmd_status(env: Env) -> int:
    rc, branch, _ = env.git(["rev-parse", "--abbrev-ref", "HEAD"])
    _rc, head, _ = env.git(["rev-parse", "--short=12", "HEAD"])
    _rc, st, _ = env.git(["status", "--porcelain"])
    dirty = [ln for ln in st.splitlines() if ln.strip()]
    env.say(f"Branch {branch.strip()}, HEAD {head.strip()}, " + (f"{len(dirty)} uncommitted file(s)" if dirty
                                                                  else "nothing uncommitted"))
    tags = release_tags(env)
    env.say("Release tags: " + (", ".join(tags) if tags else "none yet"))
    try:
        nt = next_tag(env)
        env.say(f"Next tag: {nt}" + (" (already exists!)" if tag_exists(env, nt) else ""))
    except Stop as e:
        nt = None
        env.say(str(e))
    recs = all_records(env)
    if recs:
        r = recs[-1]
        pushed, _how = was_pushed(env, r["tag"])
        env.say(f"Last release record: {r['tag']} ({'ok' if r.get('ok') else 'stopped at ' + str(r.get('failed_step'))}"
                f", {'FULL' if r.get('full') else 'core'}, {'engine' if r.get('engine') else 'no engine'}, "
                f"{'pushed' if pushed else 'not pushed'}, finished {r.get('finished')})")
    else:
        env.say("Last release record: none")
    if nt:
        why = full_due(env, nt)
        env.say("FULL due: " + ("; ".join(why) if why else "no"))
    url = origin_url(env)
    env.say("GitHub link: " + ("set" if url else "not set yet (see docs/RELEASE.md)"))
    if os.path.exists(os.path.join(env.root, "build", "STOP_ROUND")):
        env.say("build/STOP_ROUND exists: a release would stop at once.")
    try:
        v = env.install.verify_installed()
        env.say("Installed files: " + ("match their build records" if ok_of(v) else "DIFFER: " + detail_of(v)))
    except Exception as e:  # noqa: BLE001
        env.say(f"Installed files: could not check ({e.__class__.__name__}: {e})")
    return EXIT_OK


def cmd_undo(env: Env, tag: str | None, yes: bool) -> int:
    if yes:
        raise Stop("--yes is not allowed for undo: you type the tag yourself.", EXIT_USAGE)
    if not tag or not tag_key(tag):
        raise Stop("Say which release: RELEASE.bat undo r68", EXIT_USAGE)
    rec = read_record(env, tag)
    if rec is None:
        raise Stop(f"There is no release record for {tag} (build/release/{tag}/release.json), so nothing to undo.")
    installed = bool(rec.get("installed") or rec.get("backup"))
    has_tag = tag_exists(env, tag)
    pushed, how = was_pushed(env, tag) if has_tag else (False, "")
    env.say(f"Undo {tag}:")
    env.say(f"  - {'put back the files saved before ' + tag + ' (build/backup/*-pre-' + tag + ') and check them' if installed else 'nothing was installed by ' + tag + ' (no engine build), so no files change'}")
    if has_tag:
        env.say(f"  - the tag {tag}: " + ("STAYS, because " + how if pushed else "deleted (it was never pushed)"))
    env.say("  - backups are never deleted")
    ans = env.ask(f"Type {tag} and Enter to undo it (anything else stops): ")
    if ans.strip() != tag:
        raise Stop(f"Not undone: what you typed was not {tag}.")
    done = {"tag": tag, "when": env.now(), "restored": None, "tag_deleted": False}
    if installed:
        res = env.install.undo(tag)
        done["restored"] = _jsonable(env, res)
        if not ok_of(res):
            raise Stop(f"Undo could not put every file back: {detail_of(res)}. The backups are still in build/backup.")
        env.say("  Files put back and their shas checked.")
    else:
        env.say(f"  Nothing was installed by {tag}, so there were no files to put back.")
    if has_tag and not pushed:
        rc, _o, err = env.git(["tag", "-d", tag])
        if rc != 0:
            raise Stop(f"git could not delete the tag {tag}: {err.strip()[:200]}")
        done["tag_deleted"] = True
        env.say(f"  Local tag {tag} deleted.")
    elif has_tag:
        env.say(f"  The tag {tag} was pushed, so it stays (deleting it would not remove it from GitHub).")
    p = os.path.join(release_dir(env, tag), "undo.json")
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(env.mask(json.dumps(done, indent=1, default=str)) + "\n")
    env.say(f"Undone. Record: {env.rel(p)}")
    return EXIT_OK


def finding_line(f) -> str:
    """one masked line for a privacy finding (package.privacy_scan dicts: scope, where, line, kind, text)"""
    if not isinstance(f, dict):
        return str(f)
    if f.get("detail"):
        return str(f["detail"])
    where = f"{f.get('where', '?')}" + (f":{f['line']}" if f.get("line") else "")
    return (f"[{f.get('scope', '?')}] {where}: {f.get('kind', 'private string')}"
            + (f" x{f['count']}" if (f.get("count") or 1) > 1 else "") + (f" ({f['text']})" if f.get("text") else ""))


def cmd_push(env: Env, tag: str | None, yes: bool) -> int:
    if yes:
        raise Stop("--yes is not allowed for push: you type the tag yourself.", EXIT_USAGE)
    agent = [k for k in AGENT_ENV if env.environ.get(k)]
    if agent:
        raise Stop("push is for the owner only and is never run by an agent or a workflow. Double-click "
                   "RELEASE.bat yourself, or run 'RELEASE.bat push <tag>' in your own command window.", EXIT_USAGE)
    if not tag or not tag_key(tag):
        raise Stop("Say which release: RELEASE.bat push r68", EXIT_USAGE)
    if not tag_exists(env, tag):
        raise Stop(f"There is no local tag {tag}. Run RELEASE.bat first; it makes the tag.")
    rec = read_record(env, tag)
    if not rec or not rec.get("ok") or rec.get("rehearse"):
        raise Stop(f"There is no finished release record for {tag} (build/release/{tag}/release.json). "
                   "Run RELEASE.bat first.")
    eds = rec.get("packages") or {}
    if eds and not all(isinstance(p, dict) and p.get("ok") for p in eds.values()):
        raise Stop(f"The release record for {tag} has an edition whose package did not pass "
                   f"({', '.join(e for e, p in eds.items() if not (isinstance(p, dict) and p.get('ok')))}). "
                   "Run RELEASE.bat again.")
    url = origin_url(env)
    if not url:
        env.say("There is no GitHub link yet. First time only:")
        env.say("  1. On github.com, make a new EMPTY repository (no README, no licence, no .gitignore).")
        env.say("  2. In this folder run: git remote add origin https://github.com/<you>/<name>.git")
        env.say(f"  3. Then run RELEASE.bat push {tag} again.")
        raise Stop("Not pushed: no GitHub link (remote 'origin') yet.")
    pushed_tags = [r["tag"] for r in all_records(env) if r.get("pushed") or os.path.isfile(
        os.path.join(release_dir(env, r["tag"]), "pushed.json"))]
    last = pushed_tags[-1] if pushed_tags else None
    env.say(f"Push {tag} to GitHub. What goes public: "
            + (f"the commits since {last}" if last else "the WHOLE history (first push)") + ".")
    try:
        findings = list(env.package.privacy_scan([], history=True, repo=env.root, since=last) or [])
    except Exception as e:  # noqa: BLE001
        raise Stop(f"The privacy scan could not run ({e.__class__.__name__}: {e}). Not pushed.")
    if findings:
        env.say(f"Privacy: {len(findings)} private string(s) in that history (shown masked):")
        for f in findings[:30]:
            env.say("  - " + finding_line(f))
        if len(findings) > 30:
            env.say(f"  ... and {len(findings) - 30} more")
        env.say("They would become public. Cleaning old commits needs its own round (ask for it).")
    else:
        env.say("Privacy: nothing private found in that history.")
    lic = any(env.git(["cat-file", "-e", f"{tag}:{n}"])[0] == 0 for n in LICENSE_NAMES)
    if not lic:
        env.say("Licence: there is no LICENSE file, so on public GitHub the code would be 'all rights reserved'. "
                "Pick one before you make the repository public (MIT would match Zakuro).")
    # round 85 (docs/PUBLIC_RELEASE_PLAN.md section 9 fix 1): the private repo's branch is 'main'; local master goes
    # there (a plain 'push origin master' would make a second branch 'master' on GitHub)
    branch = PRIVATE_REFSPEC
    cmds = [["push", "-u", "origin", branch], ["push", "origin", f"refs/tags/{tag}"]]
    env.say("These commands will run: " + " ; ".join("git " + " ".join(c) for c in cmds))
    want = f"{tag} anyway" if findings else tag
    ans = env.ask(f"Type '{want}' and Enter to push (anything else stops): ")
    if ans.strip() != want:
        raise Stop(f"Not pushed: what you typed was not '{want}'.")
    for c in cmds:
        rc, out, err = env.git(c, timeout=600)
        if rc != 0:
            raise Stop(f"git {' '.join(c)} failed: {(err or out).strip()[:300]}")
    p = os.path.join(release_dir(env, tag), "pushed.json")
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"tag": tag, "when": env.now(), "branch": branch, "privacy_findings": len(findings),
                             "license": lic}, indent=1) + "\n")
    env.say(f"Pushed {tag}. Record: {env.rel(p)}")
    return EXIT_OK


# ------------------------------------------------------------------------------------------------ publish (round 85)
def _final_sha_line(path: str, key: str) -> str | None:
    """the sha on FINAL_SHA.txt's '<key> <sha> <name>' line (key e.g. 'vanilla zip'), or None"""
    try:
        with open(path, encoding="utf-8") as fh:
            for ln in fh:
                parts = ln.split()
                if len(parts) >= 3 and " ".join(parts[:-2]) == key:
                    return parts[-2]
    except OSError:
        return None
    return None


def _sums_of(path: str) -> dict:
    out = {}
    try:
        with open(path, encoding="ascii", errors="replace") as fh:
            for ln in fh:
                h, _, n = ln.rstrip("\r\n").partition("  ")
                if n:
                    out[n] = h
    except OSError:
        pass
    return out


def _seal_files_under(top: str) -> list[str]:
    """Seal edition zips and git bundles anywhere under top (they never go near the public step)"""
    hits = []
    for d, _dirs, files in os.walk(top):
        for f in files:
            low = f.lower()
            if low.endswith(".bundle") or (low.endswith(".zip") and "seal" in low):
                hits.append(os.path.join(d, f))
    return hits


def publish_commands(tag: str, last_public: str | None, notes: str, zipf: str, sums: str) -> tuple[list[str], list[str]]:
    """(the O5 commands in order, the separate r68-delete line(s)); paths relative to the project folder"""
    repo = f"build/publish/{tag}/repo"
    cmds = [
        "gh auth status",
        f"git -C {repo} push --force {PUBLIC_URL} main",
        f"git -C {repo} push {PUBLIC_URL} refs/tags/{tag}",
        f'gh release create {tag} --repo {PUBLIC_REPO} --verify-tag --title "FE Fates PC Port {tag} (Vanilla+, source '
        f'only)" --notes-file "{notes}" "{zipf}" "{sums}"',
    ]
    extra = []
    if last_public and last_public != tag:
        extra.append(f"gh release delete {last_public} --repo {PUBLIC_REPO} --cleanup-tag --yes")
    return cmds, extra


def cmd_publish(env: Env, tag: str | None) -> int:
    """Build the public one-commit snapshot of rNN from its Vanilla+ zip ONLY, run every hard stop of
    docs/PUBLIC_RELEASE_PLAN.md section 6 that can be checked here, and print the push and gh commands. It NEVER
    pushes or uploads: the public push is the owner's, or Claude's in chat right after the owner's yes for that one
    push (call B6). Writes only build/publish/rNN/ (an older repo folder there is moved aside, never deleted)."""
    if not tag or not tag_key(tag):
        raise Stop("Say which release: RELEASE.bat publish r86", EXIT_USAGE)
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": env.mask(detail)})
        env.say(f"  {'PASS' if ok else 'FAIL'}  {name}: {detail}")
        return bool(ok)

    rdir = release_dir(env, tag)
    vdir = os.path.join(rdir, "package", "vanilla")
    zipf = os.path.join(vdir, f"FE-Fates-port-{tag}.zip")
    notesf, sumsf = os.path.join(vdir, "RELEASE_NOTES.md"), os.path.join(vdir, "SHA256SUMS.txt")
    pub = os.path.join(env.root, "build", "publish", tag)
    repo = os.path.join(pub, "repo")
    rel = lambda p: os.path.relpath(p, env.root).replace(os.sep, "/")  # noqa: E731
    env.say(f"Public snapshot of {tag}: made from {rel(zipf)} only. Nothing is pushed or uploaded.")
    env.say("")
    env.say("The release record:")
    rec = read_record(env, tag)
    van = ((rec or {}).get("packages") or {}).get("vanilla")
    check("record", bool(rec) and rec.get("ok") and not rec.get("rehearse"),
          "build/release/{0}/release.json says ok, not a rehearse".format(tag) if rec and rec.get("ok")
          and not rec.get("rehearse") else ("no release record for " + tag if not rec else
                                             "the record is a rehearse or did not finish ok"))
    vgates = (van.get("gates") or []) if isinstance(van, dict) else None
    if not isinstance(van, dict):
        bad_gates = ["no Vanilla+ package in the record"]
    elif not isinstance(vgates, list) or not all(isinstance(g, dict) for g in vgates):
        bad_gates = ["the record's Vanilla+ gates are not a list of results"]
    else:
        bad_gates = [g.get("name") for g in vgates if not g.get("ok")]
    check("vanilla-package", isinstance(van, dict) and van.get("ok") and not bad_gates,
          "the Vanilla+ package and every one of its gates passed (no game bytes, no private strings, credits)"
          if isinstance(van, dict) and van.get("ok") and not bad_gates else f"not ok: {', '.join(map(str, bad_gates))}")
    have = all(os.path.isfile(p) for p in (zipf, notesf, sumsf))
    check("files", have, f"{rel(vdir)} holds the zip, RELEASE_NOTES.md and SHA256SUMS.txt" if have else
          f"missing in {rel(vdir)}: " + ", ".join(os.path.basename(p) for p in (zipf, notesf, sumsf)
                                                   if not os.path.isfile(p)))
    if have:
        zsha, nsha = sha256_file(zipf), sha256_file(notesf)
        final = _final_sha_line(os.path.join(rdir, "FINAL_SHA.txt"), "vanilla zip")
        sums = _sums_of(sumsf)
        check("zip-sha", zsha == final == sums.get(os.path.basename(zipf)) and sums.get("RELEASE_NOTES.md") == nsha,
              f"zip sha256 {zsha[:12]}... = FINAL_SHA.txt 'vanilla zip' = SHA256SUMS.txt; notes listed with their sha"
              if zsha == final == sums.get(os.path.basename(zipf)) and sums.get("RELEASE_NOTES.md") == nsha else
              f"zip {zsha[:12]}..., FINAL_SHA.txt {str(final)[:12]}..., SHA256SUMS.txt "
              f"{str(sums.get(os.path.basename(zipf)))[:12]}...; notes listed: {sums.get('RELEASE_NOTES.md') == nsha}")
    rc, tag_head, _ = env.git(["rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}"])
    check("tag", rc == 0 and rec is not None and tag_head.strip() == (rec or {}).get("head"),
          f"local tag {tag} points at the record's head {str((rec or {}).get('head'))[:12]}" if rc == 0 and rec
          and tag_head.strip() == rec.get("head") else f"local tag {tag} is missing or not on the record's head")
    seal_near = _seal_files_under(os.path.join(env.root, "build", "publish"))
    check("no-seal-files", not seal_near, "no Seal edition zip and no bundle under build/publish/" if not seal_near
          else "found: " + ", ".join(rel(p) for p in seal_near[:3]))
    if not all(c["ok"] for c in checks):
        _publish_record(env, pub, tag, checks, None)
        raise Stop("The release record is not clean, so no snapshot was made. Run the release again (O2) or ask "
                   "Claude; nothing was pushed.")

    # the snapshot: a fresh git init, the zip's FE-Fates-port-rNN/ contents, one commit, a lightweight tag
    env.say("")
    env.say("The snapshot:")
    os.makedirs(pub, exist_ok=True)
    if os.path.exists(repo):
        aside = os.path.join(pub, "repo-replaced-" + time.strftime("%Y%m%d-%H%M%S"))
        os.replace(repo, aside)
        env.say(f"  (an older {rel(repo)} was moved to {rel(aside)}; nothing deleted)")
    os.makedirs(repo)
    import zipfile                                       # noqa: WPS433 (only publish needs it)
    prefix = f"FE-Fates-port-{tag}/"
    zip_files = []
    with zipfile.ZipFile(zipf) as z:
        for zi in z.infolist():
            name = zi.filename
            if not name.startswith(prefix):
                raise Stop(f"The zip holds {name!r} outside {prefix}; no snapshot made.")
            sub = name[len(prefix):]
            if not sub or zi.is_dir():
                continue
            parts = sub.split("/")
            if sub.startswith("/") or "\\" in sub or ":" in sub or ".." in parts or ".git" in parts:
                raise Stop(f"The zip holds an unsafe path {sub!r}; no snapshot made.")
            dest = os.path.join(repo, *parts)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(z.read(zi))
            zip_files.append(sub)
    when = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime())
    ident = {"GIT_AUTHOR_NAME": PUBLIC_NAME, "GIT_AUTHOR_EMAIL": PUBLIC_EMAIL, "GIT_AUTHOR_DATE": when,
             "GIT_COMMITTER_NAME": PUBLIC_NAME, "GIT_COMMITTER_EMAIL": PUBLIC_EMAIL, "GIT_COMMITTER_DATE": when}
    message = f"FE Fates PC port {tag} (source only)"
    # gpgSign off: a signing setting in the PC's own git config must never put the owner's key on the public copy;
    # UTF-8 (no encoding header) and an empty hooks folder: no local setting or global hook changes the commit
    no_hooks = os.path.join(pub, "no-hooks").replace(os.sep, "/")
    os.makedirs(no_hooks, exist_ok=True)
    cfg = ["-c", "core.autocrlf=false", "-c", "core.safecrlf=false", "-c", f"user.name={PUBLIC_NAME}",
           "-c", f"user.email={PUBLIC_EMAIL}", "-c", "commit.gpgSign=false", "-c", "tag.gpgSign=false",
           "-c", "i18n.commitEncoding=UTF-8", "-c", f"core.hooksPath={no_hooks}"]
    for args in (["init", "-q", "-b", "main"], [*cfg, "add", "--all", "--force", "."],
                 [*cfg, "commit", "-q", "-m", message], [*cfg, "tag", tag]):
        rc, out, err = env.git_at(repo, args, ident)
        if rc != 0:
            what = next(a for a in args if a in ("init", "add", "commit", "tag"))
            raise Stop(f"git {what} in the snapshot failed: {(err or out).strip()[:200]}. Nothing was pushed.")
    g = lambda *a: env.git_at(repo, list(a), None)  # noqa: E731
    env.say(f"  {rel(repo)}: {len(zip_files)} files from the zip, one commit, tag {tag}")
    env.say("")
    env.say("Hard stops (docs/PUBLIC_RELEASE_PLAN.md section 6):")
    _rc, ls, _ = g("-c", "core.quotepath=false", "ls-files", "-z")
    tracked = sorted(p for p in ls.split("\0") if p)
    same = tracked == sorted(zip_files)
    check("file-list", same, f"{len(tracked)} tracked files = the zip's {len(zip_files)} files" if same else
          f"{len(set(zip_files) - set(tracked))} zip file(s) not tracked (e.g. "
          f"{', '.join(sorted(set(zip_files) - set(tracked))[:2])}), {len(set(tracked) - set(zip_files))} extra")
    _rc, n, _ = g("rev-list", "--all", "--count")
    _rc, parents, _ = g("rev-list", "--parents", "-n", "1", "HEAD")
    one = n.strip() == "1" and len(parents.split()) == 1
    check("one-commit", one, "exactly 1 commit, no parent" if one else f"{n.strip()} commit(s); parents: "
          f"{len(parents.split()) - 1}")
    _rc, heads, _ = g("for-each-ref", "--format=%(refname)", "refs/heads", "refs/tags")
    refs = sorted(heads.split())
    check("refs", refs == ["refs/heads/main", f"refs/tags/{tag}"], f"branch main and tag {tag} only" if refs ==
          ["refs/heads/main", f"refs/tags/{tag}"] else "refs: " + ", ".join(refs))
    _rc, who, _ = g("log", "-1", "--format=%an%x00%ae%x00%cn%x00%ce%x00%ai%x00%ci%x00%s")
    f = (who.rstrip("\n").split("\0") + [""] * 7)[:7]
    ok_who = (f[0], f[1], f[2], f[3]) == (PUBLIC_NAME, PUBLIC_EMAIL, PUBLIC_NAME, PUBLIC_EMAIL)
    ok_utc = f[4].endswith("+0000") and f[5].endswith("+0000")
    _rc, raw, _ = g("cat-file", "commit", "HEAD")
    head_part, _sep, body = raw.replace("\r\n", "\n").partition("\n\n")
    ok_msg = f[6] == message and body.rstrip("\n") == message      # the whole message: no extra lines or trailers
    extra = sum(1 for ln in body.splitlines() if ln.strip()) - 1
    check("identity", ok_who and ok_utc and ok_msg,
          f"author and committer {PUBLIC_NAME} <{PUBLIC_EMAIL}>, dates +0000, message '{message}' and nothing more"
          if ok_who and ok_utc and ok_msg else f"author {f[0]} <{f[1]}>, committer {f[2]} <{f[3]}>, "
          f"dates {f[4]} / {f[5]}, message '{f[6]}'" + (f" plus {extra} more line(s)" if f[6] == message
                                                         and not ok_msg else ""))
    sig = [ln.split(" ", 1)[0] for ln in head_part.split("\n") if ln.startswith(("gpgsig", "gpgsig-sha256"))]
    check("unsigned", bool(raw) and not sig, "the commit carries no signature (no key ID on the public copy)"
          if raw and not sig else ("the commit could not be read" if not raw else
                                   f"the commit is signed ({sig[0]} header): it would show the signer's key ID"))
    _rc, typ, _ = g("cat-file", "-t", tag)
    _rc, th, _ = g("rev-parse", tag)
    _rc, hh, _ = g("rev-parse", "HEAD")
    check("tag-lightweight", typ.strip() == "commit" and th.strip() == hh.strip(),
          f"tag {tag} is lightweight, on the one commit" if typ.strip() == "commit" and th.strip() == hh.strip()
          else f"tag {tag} is a '{typ.strip()}' object (it must be lightweight: no tagger identity)")
    big = [p for p in tracked if os.path.getsize(os.path.join(repo, *p.split("/"))) > PUBLIC_MAX_BYTES]
    ext = [p for p in tracked if os.path.splitext(p.lower())[1] in PUBLIC_FORBIDDEN_EXT]
    check("kinds-and-size", not big and not ext, "no program, game, archive or bundle file; none over 10 MB"
          if not big and not ext else "not allowed: " + ", ".join((ext + big)[:4]))
    ed_path = os.path.join(repo, "config", "release", "editions.json")
    try:
        with open(ed_path, encoding="utf-8") as fh:
            conf = env.package.edition_conf(json.load(fh), "vanilla")
        left = [p for p in tracked if env.package.is_left_out(p, conf["leave_out"]) or p.startswith("play/")]
        check("leave-out", not left, f"none of the {len(conf['leave_out'])} left-out paths of editions.json and "
              "nothing under play/" if not left else "present: " + ", ".join(left[:4]))
    except Exception as e:  # noqa: BLE001
        conf = {}
        check("leave-out", False, f"config/release/editions.json unreadable in the snapshot ({e.__class__.__name__})")
    try:
        ms = env.package.worktree_markers(repo)
        check("markers", not ms.get("bad"), f"markers in {ms.get('files')} file(s), {ms.get('allowed')} allowed, "
              f"{len(ms.get('info') or [])} info, 0 not allowed" if not ms.get("bad") else
              f"{len(ms['bad'])} not allowed (first: {ms['bad'][0]})")
    except Exception as e:  # noqa: BLE001
        check("markers", False, f"the marker check could not run ({e.__class__.__name__}: {e})")
    try:
        found = list(env.package.privacy_scan([], history=True, repo=repo) or [])
        found += list(env.package.privacy_scan([notesf, sumsf]) or [])
        priv = [x for x in found if not isinstance(x, dict) or x.get("severity", "private") == "private"]
        check("privacy", not priv, f"0 private findings in the snapshot's files and history and in the notes "
              f"({len(found)} info)" if not priv else f"{len(priv)} private finding(s), first: {finding_line(priv[0])}")
    except Exception as e:  # noqa: BLE001
        check("privacy", False, f"the privacy scan could not run ({e.__class__.__name__}: {e})")
    with open(notesf, encoding="utf-8", errors="replace") as fh:
        ntxt = fh.read()
    lacks = [s for s in PUBLIC_CREDIT if s not in ntxt]
    if not re.search(r"(?i)\b(?:not|never) included\b", ntxt):
        lacks.append("'not included'")
    try:
        nlines = int(env.package.notes_marker_lines(ntxt, conf.get("markers")))
    except Exception:  # noqa: BLE001
        nlines = 99
    check("notes-credit", not lacks and nlines <= 1, "the notes carry the full credit line (Laz14, "
          "gamebanana.com/mods/656034, CC BY-NC-ND 4.0, not included) and no other Seal line"
          if not lacks and nlines <= 1 else (f"the notes lack {', '.join(lacks)}" if lacks else
                                             f"the notes have {nlines} lines naming the mod (allowed 1)"))
    seal_near = _seal_files_under(os.path.join(env.root, "build", "publish"))
    check("no-seal-files-after", not seal_near, "still no Seal edition zip and no bundle under build/publish/"
          if not seal_near else "found: " + ", ".join(rel(p) for p in seal_near[:3]))
    failed = [c for c in checks if not c["ok"]]
    cmds, extra = publish_commands(tag, conf.get("last_public_tag"), rel(notesf), rel(zipf), rel(sumsf))
    _publish_record(env, pub, tag, checks, {"commands": cmds, "separate": extra} if not failed else None)
    env.say("")
    if failed:
        env.say(f"NOT READY: {len(failed)} hard stop(s) failed ({', '.join(c['name'] for c in failed)}). Nothing goes "
                "up until they are fixed. Nothing was pushed.")
        return EXIT_STOP
    env.say(f"READY. Every hard stop passed. Nothing was pushed. Record: {rel(os.path.join(pub, 'publish.json'))}")
    env.say("")
    env.say("Still to check by hand before the push: the repo description no longer names the mod (O4), and a read")
    env.say("of the notes and new docs for game text (no tool checks dialogue).")
    env.say("")
    env.say("The public push (O5). No round or workflow runs these: the project owner does, or Claude in chat right")
    env.say("after the owner's yes for this one push. Run them from the project folder, in this order; the first")
    env.say("must say account FT775:")
    for c in cmds:
        env.say("  " + c)
    if extra:
        env.say("")
        env.say(f"Separate, only if the owner chose to delete the {conf.get('last_public_tag')} release (call B4). It "
                "deletes that GitHub release and its tag, so the old copy is no longer reachable from the tags page:")
        for c in extra:
            env.say("  " + c)
    return EXIT_OK


def _publish_record(env: Env, pub: str, tag: str, checks: list[dict], commands: dict | None) -> None:
    os.makedirs(pub, exist_ok=True)
    doc = {"tag": tag, "when": env.now(), "ok": bool(checks) and all(c["ok"] for c in checks), "pushed": False,
           "checks": checks, "public_url": PUBLIC_URL, **(commands or {})}
    with open(os.path.join(pub, "publish.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(env.mask(json.dumps(doc, indent=1)) + "\n")
    if commands:
        with open(os.path.join(pub, "PUSH_COMMANDS.txt"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("Run from the project folder, only after the owner's yes for this push (call B6).\n"
                     + "\n".join(commands["commands"]) + "\n"
                     + ("\nSeparate, only if call B4 = delete:\n" + "\n".join(commands["separate"]) + "\n"
                        if commands.get("separate") else ""))


def cmd_fixtures(env: Env, write: bool) -> int:
    if write:
        p = write_fixtures(env)
        env.say(f"Wrote {env.rel(p)} (commit it in the round commit).")
        return EXIT_OK
    probs = check_fixtures(env, None)
    for pr in probs:
        env.say("FAIL: " + pr)
    env.say("fixtures OK (smoke inputs: run 'python tools/harness/smoke.py check')" if not probs
            else f"{len(probs)} problem(s)")
    return EXIT_OK if not probs else EXIT_STOP


SELFTEST_MODULES = ("tests.test_release", "tests.test_package", "tests.test_install")


def cmd_selftest(root: str = ROOT, timeout: int = 900) -> int:
    """The three release modules, each its own 'python -m unittest' child (below normal, no window), side by side.
    Prints one 'release selftest: N/N tests passed' line (check_all row release-selftest)."""
    procs = []
    for m in SELFTEST_MODULES:
        procs.append((m, subprocess.Popen([sys.executable, "-m", "unittest", m], cwd=root, stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                          creationflags=NO_WINDOW | BELOW_NORMAL)))
    total = bad = 0
    parts = []
    deadline = time.time() + timeout
    for m, p in procs:
        try:
            out, _ = p.communicate(timeout=max(1, deadline - time.time()))
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
            out += "\nTIMEOUT"
        ran = re.search(r"^Ran (\d+) tests? in ", out, re.M)
        n = int(ran.group(1)) if ran else 0
        fails = re.search(r"^FAILED \((.*)\)", out, re.M)
        nbad = sum(int(x) for x in re.findall(r"(?:failures|errors|unexpected successes)=(\d+)",
                                              fails.group(1))) if fails else 0
        ok = p.returncode == 0 and n > 0 and re.search(r"^OK\b", out, re.M) is not None
        if not ok:
            nbad = max(nbad, 1)
            tail = "\n".join(out.strip().splitlines()[-25:])
            print(f"--- {m} (exit {p.returncode}) ---\n{tail}")
        total += n
        bad += nbad
        parts.append(f"{m.split('.', 1)[1]} {n - nbad}/{n}")
    ok = bad == 0 and total > 0
    print(f"release selftest: {total - bad}/{total} tests passed ({', '.join(parts)})" + ("" if ok else " FAIL"))
    return EXIT_OK if ok else EXIT_STOP


# ------------------------------------------------------------------------------------------------ main
def parse(argv: list[str] | None):
    ap = argparse.ArgumentParser(prog="release.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "status", "undo", "push", "publish", "fixtures",
                                                              "selftest"])
    ap.add_argument("tagarg", nargs="?", default=None, help="the tag for undo / push / publish")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and counted times; write nothing")
    ap.add_argument("--rehearse", action="store_true", help="all but backup/install/tag; writes only "
                    "build/release/rehearse-<time>/")
    ap.add_argument("--engine", action="store_true", help="build to staging, smoke it, back up, install, verify")
    ap.add_argument("--full", action="store_true", help="FULL tests instead of the core")
    ap.add_argument("--tag", default=None, help="rNN (default: the round after the newest REPORT)")
    ap.add_argument("--yes", action="store_true", help="skip the press-Enter prompts (refused for push and undo)")
    ap.add_argument("--write", action="store_true", help="fixtures: rewrite config/release/fixtures.json")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None, env: Env | None = None) -> int:
    try:
        a = parse(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    env = env or Env()
    try:
        if a.cmd == "run":
            if a.tagarg:
                raise Stop(f"'run' takes no tag word; use --tag {a.tagarg}", EXIT_USAGE)
            if a.dry_run and a.rehearse:
                raise Stop("Use --dry-run or --rehearse, not both.", EXIT_USAGE)
            return cmd_run(env, Opts(dry_run=a.dry_run, rehearse=a.rehearse, engine=a.engine, full=a.full,
                                     tag=a.tag, yes=a.yes))
        if a.cmd == "status":
            return cmd_status(env)
        if a.cmd == "undo":
            return cmd_undo(env, a.tagarg or a.tag, a.yes)
        if a.cmd == "push":
            return cmd_push(env, a.tagarg or a.tag, a.yes)
        if a.cmd == "publish":
            return cmd_publish(env, a.tagarg or a.tag)
        if a.cmd == "fixtures":
            return cmd_fixtures(env, a.write)
        if a.cmd == "selftest":
            return cmd_selftest()
    except Stop as e:
        env.say(("REFUSED: " if e.code == EXIT_USAGE else "STOPPED: ") + str(e))
        return e.code
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
