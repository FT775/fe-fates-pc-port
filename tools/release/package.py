"""Release package and its gates (round 68, release part B, goal 2).

    python tools/release/package.py build --tag r68 [--prev r67] [--out DIR] [--repo DIR] [--lanes 4] [--edition E]
    python tools/release/package.py markers [--repo DIR]               strong Seal markers the Vanilla+ zip would carry
    python tools/release/package.py notes --tag r68 [--prev r67] [--repo DIR]
    python tools/release/package.py scan [--history] [--since TAG] [--repo DIR] [PATH ...]
    python tools/release/package.py redact [--write] [--repo DIR]     private terms in the CURRENT tracked files
    python tools/release/package.py terms                              which kinds of private terms were found (masked)

What `build` makes in its out folder (default build/release/<tag>/package):
  FE-Fates-port-<tag>.zip   `git archive --format=zip --prefix=FE-Fates-port-<tag>/ HEAD`: tracked files only
  fe-fates-<tag>.bundle     a git bundle of the history (HEAD, master and the tags), checked with `git bundle verify`
  RELEASE_NOTES.md          notes(): the 'Short version' of each report since the previous tag, plus a fixed block;
                            Vanilla+ (round 85): the committed notes file editions.json names for the tag
                            (config/release/notes/<tag>-vanilla.md) word for word when the commit has it
  SHA256SUMS.txt            sha256 of the three files above
  package.json              the result: gates, counts and privacy findings, MASKED (never a private string in clear)

Editions (round 84, Seal edition split B; docs/SEAL_EDITION_PLAN.md section 6; config/release/editions.json):
  no --edition      today's package, unchanged: the full zip (everything tracked) straight in the out folder
  --edition seal    the Seal of Flames edition: the same full zip, named FE-Fates-port-<tag>-seal-edition.zip, with
                    the bundle, in <out>/seal/ with its own notes, SHA256SUMS and package.json (today's 11 gates)
  --edition vanilla Vanilla+ ("the FE Fates PC port"): `git archive` of HEAD leaving out the paths editions.json lists
                    (Seal folders, PLAY SEAL OF FLAMES.bat, the sof.py stub), in <out>/vanilla/; no bundle (the
                    three history gates say "not applicable"); the archive gate wants the missing tracked files to
                    be exactly the left-out ones; plus the edition gate (no left-out path, no config/**/seal* file,
                    no strong Seal marker outside the frozen history docs and the one credit line, patch 0043 in
                    the commit) and its own credits gate (CREDITS.md's one line; roms/seal/README.txt is left out)
Each edition writes and deletes only in its own folder, so the two runs sit side by side (plan risk 14).

Gates (every one runs; the package is ok only when every gate is ok; GATES below says what each one catches). The
scanned set is EVERY blob that leaves this PC with the package: each file in the zip, each blob of the bundle's
history that is not in HEAD's tree (HEAD's own blobs are the zip's files), and the notes.

Privacy (privacy_terms / privacy_scan): the private strings are worked out at RUN TIME only, from os.environ
(USERNAME, USERPROFILE), the repo's absolute path (and the main worktree's), the top folder above it, and
`git config user.email` (a placeholder such as name@localhost names no one and is left out). They are never written
to a file or a log in clear: every finding and log line shows them masked ('F***'). Kinds: user, home, email are
'private'; repo and layout (D: folder paths) are 'info'. A private finding in HEAD's tree or the notes FAILS the
package; one only in older history is reported (masked) and blocks only the push (release.py push); info findings
are listed, never fail.

Every git call is a child process with no window at below-normal priority. Every function takes an injectable
runner (and roots) so the tests run in temporary repos.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BELOW_NORMAL = 0x00004000 if os.name == "nt" else 0
FORMAT = 1

PREFIX = "FE-Fates-port-{tag}/"
ZIP_NAME = "FE-Fates-port-{tag}.zip"
BUNDLE_NAME = "fe-fates-{tag}.bundle"
NOTES_NAME = "RELEASE_NOTES.md"
SUMS_NAME = "SHA256SUMS.txt"
RESULT_NAME = "package.json"
TAG_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

MAX_BLOB = 50 * 1024 * 1024        # GitHub warns at 50 MB and refuses 100 MB
SAME_FILE_MIN = 64                 # tinier files (empty, "{}") match anything by chance and carry no data
SEAL_LINK = "gamebanana.com/mods/656034"
SEAL_LICENCE = "CC BY-NC-ND"
CREDIT_FILES = {"CREDITS.md": ("Laz14", SEAL_LINK, SEAL_LICENCE),
                "roms/seal/README.txt": ("Laz14", "656034", SEAL_LICENCE)}
ROMS_ALLOWED = re.compile(r"^roms/(?:[^/]+/)*README(?:\.txt|\.md)?$")
SEAL_DATA = re.compile(r"^config/(?:[^/]+/)*seal[^/]*\.(json|csv|tsv)$", re.I)
OWNER_OK = re.compile(r"(?i)\s*\bnothing counts as done until you say ok\.?|\s*\bwaiting for (?:your|the owner's) ok\.?"
                      r"|\s*\bneeds your ok\.?")
GENERIC_USERS = {"user", "users", "admin", "administrator", "owner", "guest", "runner", "root", "default", "public"}
GENERIC_TOP = {"users", "home", "src", "source", "repos", "repo", "projects", "git", "code", "dev", "work",
               "documents", "temp", "tmp", "workspace", "workspaces", "github"}
PLACEHOLDER_EMAIL = re.compile(r"(?i)@(localhost|example\.(com|org|net)|invalid)$")

GATES = {
    "archive": "git archive of HEAD made a zip: tracked files only (never play/, extracted/, roms, mods, build/)",
    "bundle-verify": "the git bundle of the history is complete and `git bundle verify` accepts it",
    "zip-reopen": "the zip reopened: no ROM/asset/program extension, no NUL byte (binary) in any file, .bat/.cmd "
                  "files CRLF, roms/ holds README files only, mods/ only README.md/.gitkeep, nothing under a "
                  "never-tracked path, no file over 50 MB",
    "history-paths": "the same path, extension, binary and size rules for every older blob the bundle carries",
    "leak": "hygiene-leak's long-byte-run check (32-byte windows every 16 bytes) against extracted/code.bin, raw "
            "and decoded from hex/arrays/asm, on every zip file, history blob and the notes",
    "same-file": "no packed blob is byte-identical (sha256) to a file in extracted/ (the ROM's files), play/ "
                 "(the installed game and the installed Seal of Flames mod) or roms/ (incl. members of zips there)",
    "seal-ids": "files made from Seal of Flames data (config/**/seal*.json) hold ids only: no number lists, no "
                "objects with 3+ integers (a stat row), fractions only in [0, 1]",
    "credits": "CREDITS.md and roms/seal/README.txt still credit Laz14 with the link and CC BY-NC-ND, every tracked "
               "NOTICE.md is packed, and the notes carry the credit block",
    "privacy-head": "no private term (Windows user name, home folder, git e-mail) in HEAD's files or the notes "
                    "(FAIL); D: folder paths are listed as info",
    "privacy-history": "private terms in older history: listed masked, never fail the package, block only the push",
    "sums": "SHA256SUMS.txt written and read back: every listed file has the listed sha256",
}
EDITION_GATE = {
    "edition": "Vanilla+ only: no left-out path (config/release/editions.json) and no config/**/seal* file in the zip; "
               "no strong Seal marker (Seal of Flames, Laz14, 656034, seal_rules, seal_bosses, roms/seal, "
               "--game seal, sof.py; never the bare word) outside the frozen history docs and the one credit line "
               "of CREDITS.md / README.md / the notes; the Seal page hide (patch 0043) is in the commit",
}
ALL_GATES = {**GATES, **EDITION_GATE}

EDITIONS_PATH = "config/release/editions.json"
EDITION_NAMES = ("vanilla", "seal")
DEFAULT_EDITION = "seal"
NOT_APPLICABLE = "not applicable: no bundle; the Seal-edition run from the same commit checks the history"
# the edition gate's own files must name the markers it looks for: reported as info, never a failure
# (round 85: release.py publish checks the public notes' credit line, so it and its test name the markers too)
GATE_OWN_FILES = ("config/release/editions.json", "tools/release/package.py", "tests/test_package.py",
                  "tools/release/release.py", "tests/test_release.py")
DEFAULT_MARKERS = ("Seal of Flames", "Laz14", "656034", "seal_rules", "seal_bosses", "roms/seal", "--game seal",
                   "sof.py")
SEAL_NAMED_CONFIG = re.compile(r"^config/(?:[^/]+/)*seal[^/]*(?:/|$)", re.I)  # a seal* file or folder
SEAL_EDITION_WORDS = re.compile(r"(?i)\bseal[- ]edition\b")
DEFAULT_ZIPS = {"vanilla": "FE-Fates-port-{tag}.zip", "seal": "FE-Fates-port-{tag}-seal-edition.zip"}


def gate_set(edition=None) -> list[str]:
    """The gates one run makes, in run order: today's 11 (no edition, or seal); Vanilla+ adds the edition gate
    (before sums)."""
    names = list(GATES)
    if edition == "vanilla":
        names.insert(names.index("sums"), "edition")
    return names


# --------------------------------------------------------------------------- processes
def default_runner(argv, cwd=None, input=None, timeout=1800):
    """Run a child with no window at below-normal priority: (returncode, stdout bytes, stderr bytes)."""
    r = subprocess.run(argv, cwd=None if cwd is None else str(cwd), input=input, capture_output=True,
                       timeout=timeout, creationflags=NO_WINDOW | BELOW_NORMAL)
    return r.returncode, r.stdout, r.stderr


class PackageError(Exception):
    pass


def _git(repo, args, runner=None, input=None, check=True) -> bytes:
    runner = runner or default_runner
    rc, out, err = runner(["git", "-C", str(repo), *args], input=input)
    if check and rc:
        raise PackageError(f"git {args[0]} failed: {err.decode('utf-8', 'replace').strip()[:300]}")
    return out


def _main_root(repo, runner=None) -> Path:
    """The main worktree of repo (for a temporary `git worktree` this is the real repo, where extracted/ lives)."""
    try:
        common = _git(repo, ["rev-parse", "--path-format=absolute", "--git-common-dir"], runner).decode().strip()
        p = Path(common)
        if p.name == ".git":
            return p.parent.resolve()
    except (PackageError, OSError):
        pass
    return Path(repo).resolve()


# --------------------------------------------------------------------------- privacy terms
@dataclass
class Term:
    kind: str        # user | home | email | repo | layout | term
    severity: str    # private | info
    clear: str       # the string itself: in memory only, never written
    rx: re.Pattern
    neutral: str     # the neutral word used when redacting

    @property
    def masked(self) -> str:
        return (self.clear[:1] or "?") + "***"


def _path_variants(p: str) -> list[str]:
    p = p.rstrip("\\/")
    back = p.replace("/", "\\")
    fwd = back.replace("\\", "/")
    out = {back, fwd, back.replace("\\", "\\\\"), fwd.replace(" ", "%20"),
           urllib.parse.quote(fwd, safe=":/"), re.sub(r"[^A-Za-z0-9]", "-", back)}
    m = re.match(r"^([A-Za-z]):(/.*)$", fwd)
    if m:
        msys = "/" + m.group(1).lower() + m.group(2)
        out |= {msys, "/mnt" + msys, msys.replace(" ", "\\ ")}
    return sorted((v for v in out if len(v) >= 4), key=len, reverse=True)


def _rx(variants, word=False) -> re.Pattern:
    alt = "|".join(re.escape(v) for v in sorted(set(variants), key=len, reverse=True))
    return re.compile(r"(?i)(?<![A-Za-z0-9])(?:" + alt + r")(?![A-Za-z0-9])")


def term_specs(repo=None, env=None, runner=None, extra=None, email=None) -> list[Term]:
    """The private terms of THIS run (see the module doc). extra: more strings to treat as private (tests).
    email: override `git config user.email` (tests); "" skips it."""
    env = os.environ if env is None else env
    specs: list[Term] = []
    home = env.get("USERPROFILE") or env.get("HOME") or ""
    if home and len(home.rstrip("\\/")) > 3:
        specs.append(Term("home", "private", home.rstrip("\\/"), _rx(_path_variants(home)), "<home>"))
    repos = []
    for r in ([repo] if repo else []) + ([_main_root(repo, runner)] if repo else []) + [ROOT]:
        s = str(Path(r).resolve())
        if s.lower() not in {x.lower() for x in repos}:
            repos.append(s)
    for s in repos:
        specs.append(Term("repo", "info", s, _rx(_path_variants(s)), "<repo>"))
    tops = []
    for s in repos:
        parts = Path(s).parts                      # ('D:\\', 'Steam and VR Games (Arrrgh)', 'PC ports', 'FE Fates')
        if len(parts) >= 3 and parts[1].lower() not in GENERIC_TOP:
            top = str(Path(parts[0]) / parts[1])
            if top.lower() not in {t.lower() for t in tops} and not top.lower().startswith(home.lower() or "\0"):
                tops.append(top)
    for t in tops:
        specs.append(Term("layout", "info", t, _rx(_path_variants(t)), "<folder>"))
    if email is None and repo is not None:
        try:
            email = _git(repo, ["config", "user.email"], runner, check=False).decode().strip()
        except OSError:
            email = ""
    if email and "@" in email and not PLACEHOLDER_EMAIL.search(email):
        specs.append(Term("email", "private", email, _rx([email]), "<email>"))
    user = env.get("USERNAME") or env.get("USER") or ""
    if len(user) >= 3 and user.lower() not in GENERIC_USERS:
        specs.append(Term("user", "private", user, _rx([user]), "<user>"))
    for x in extra or ():
        if x:
            specs.append(Term("term", "private", x, _rx([x]), "<private>"))
    return specs


def privacy_terms(repo=None, env=None, runner=None) -> list[str]:
    """The private strings of this run, in memory only (user name, home folder, repo paths, e-mail)."""
    return [t.clear for t in term_specs(repo if repo is not None else ROOT, env, runner)]


def mask_text(text: str, specs, neutral: bool = False) -> str:
    """Every term replaced by its mask ('F***') or, with neutral=True, its neutral word ('<user>')."""
    for t in specs:
        text = t.rx.sub(t.neutral if neutral else t.masked, text)
    return text


def masked_terms(specs) -> list[dict]:
    return [{"kind": t.kind, "severity": t.severity, "masked": t.masked} for t in specs]


def _scan_text(label: str, text: str, scope: str, specs, any_rx) -> list[dict]:
    out = []
    if not any_rx.search(text):
        return out
    for n, line in enumerate(text.splitlines(), 1):
        if not any_rx.search(line):
            continue
        work, hits = line, []
        for t in specs:
            k = len(t.rx.findall(work))
            if k:
                hits.append((t, k))
                work = t.rx.sub(t.masked, work)
        rest = mask_text(work, specs)
        for t, k in hits:
            out.append({"scope": scope, "where": mask_text(label, specs), "line": n, "kind": t.kind,
                        "severity": t.severity, "count": k, "text": rest.strip()[:200]})
    return out


def _any_rx(specs) -> re.Pattern:
    return re.compile("|".join(f"(?:{t.rx.pattern[4:]})" for t in specs) or r"(?!x)x", re.I)


def privacy_scan(paths_or_blobs, history: bool = False, *, repo=None, since=None, specs=None, terms=None,
                 runner=None, env=None) -> list[dict]:
    """Findings (masked) for each item: a path (str/Path) or a (label, bytes) pair; scope 'file'.
    history=True also scans what a push of repo carries: every blob of HEAD's tree (scope 'head') and every older
    blob plus every commit's author, committer and message (scope 'history'), over HEAD, master and the tags,
    or only what is new since the tag `since`. terms: extra private strings (tests)."""
    if specs is None:
        specs = term_specs(repo, env, runner, extra=terms)
    any_rx = _any_rx(specs)
    found: list[dict] = []
    base = Path(repo).resolve() if repo else None
    for item in paths_or_blobs or ():
        if isinstance(item, tuple):
            label, data = item
        else:
            p = Path(item)
            data = p.read_bytes()
            try:
                label = p.resolve().relative_to(base).as_posix() if base else p.name
            except ValueError:
                label = p.name
        found += _scan_text(label, data.decode("utf-8", "replace"), "file", specs, any_rx)
    if history:
        if repo is None:
            raise PackageError("privacy_scan(history=True) needs repo")
        found += _history_privacy(repo, since, specs, any_rx, runner)
    return found


# --------------------------------------------------------------------------- git objects
def _history_refs(repo=None, runner=None) -> list[str]:
    """What the Seal bundle and a push of the private repo carry: HEAD, master (when the repo has that branch) and
    the tags, never the other branches (round 85, docs/PUBLIC_RELEASE_PLAN.md section 9 fix 3: helper branches stay
    out of the bundle, and the history-paths, privacy-history and push scans look at exactly what the bundle holds).
    A repo without master (the public snapshot's 'main') gets HEAD and the tags."""
    refs = ["HEAD"]
    if repo is not None:
        rc, _o, _e = (runner or default_runner)(["git", "-C", str(repo), "rev-parse", "-q", "--verify",
                                                 "refs/heads/master"])
        if rc == 0:
            refs.append("master")
    return refs + ["--tags"]


def _refs_args(since=None, repo=None, runner=None) -> list[str]:
    return _history_refs(repo, runner) + ([f"^{since}"] if since else [])


def _head_blobs(repo, runner=None, rev="HEAD") -> dict[str, str]:
    """blob sha -> path for HEAD's tree."""
    out = _git(repo, ["ls-tree", "-r", "-z", rev], runner)
    res = {}
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, _, path = rec.partition(b"\t")
        mode, typ, sha = meta.split()
        if typ == b"blob":
            res.setdefault(sha.decode(), path.decode("utf-8", "surrogateescape"))
    return res


def _history_objects(repo, runner=None, since=None) -> tuple[dict[str, str], list[str]]:
    """(blob sha -> first path, commit shas) reachable from HEAD, master and the tags (minus `since`)."""
    out = _git(repo, ["rev-list", "--objects", *_refs_args(since, repo, runner)], runner)
    shas, names = [], {}
    for line in out.decode("utf-8", "surrogateescape").splitlines():
        sha, _, name = line.partition(" ")
        if sha:
            shas.append(sha)
            names[sha] = name
    if not shas:
        return {}, []
    chk = _git(repo, ["cat-file", "--batch-check=%(objecttype) %(objectname)"], runner,
               input=("\n".join(shas) + "\n").encode())
    blobs, commits = {}, []
    for line in chk.decode().splitlines():
        typ, _, sha = line.partition(" ")
        if typ == "blob":
            blobs[sha] = names.get(sha, "")
        elif typ == "commit":
            commits.append(sha)
    return blobs, commits


def _cat_batch(repo, shas, runner=None, chunk=256):
    """Yield (sha, type, bytes) via `git cat-file --batch`, in chunks."""
    shas = list(shas)
    for i in range(0, len(shas), chunk):
        part = shas[i:i + chunk]
        out = _git(repo, ["cat-file", "--batch"], runner, input=("\n".join(part) + "\n").encode())
        pos = 0
        for _ in part:
            nl = out.index(b"\n", pos)
            head = out[pos:nl].decode().split()
            if len(head) < 3:                       # "<sha> missing"
                pos = nl + 1
                continue
            size = int(head[2])
            data = out[nl + 1:nl + 1 + size]
            yield head[0], head[1], data
            pos = nl + 1 + size + 1


def _history_privacy(repo, since, specs, any_rx, runner=None) -> list[dict]:
    head = _head_blobs(repo, runner)
    blobs, commits = _history_objects(repo, runner, since)
    found = []
    for sha, typ, data in _cat_batch(repo, list(blobs), runner):
        scope = "head" if sha in head else "history"
        label = (head.get(sha) or blobs.get(sha) or "?") + ("" if scope == "head" else f" @blob {sha[:8]}")
        for f in _scan_text(label, data.decode("utf-8", "replace"), scope, specs, any_rx):
            if scope == "history":
                f["blob"] = sha
            found.append(f)
    for sha, typ, data in _cat_batch(repo, commits, runner):
        for f in _scan_text(f"commit {sha[:8]}", data.decode("utf-8", "replace"), "history", specs, any_rx):
            f["commits"] = [sha[:8]]
            found.append(f)
    looked = 0
    for f in found:                                  # which commits carry a private history blob (first 20)
        if f.get("blob") and f["severity"] == "private" and looked < 20:
            looked += 1
            out = _git(repo, ["log", "--format=%h", f"--find-object={f['blob']}", *_refs_args(since, repo, runner)],
                       runner, check=False)
            f["commits"] = out.decode().split()[:10]
    for f in found:
        f.pop("blob", None)
    return found


# --------------------------------------------------------------------------- check_all helpers (hygiene)
_CA = None


def _check_all():
    """tools/check_all.py of THIS tool's repo (its hygiene-leak code and path rules are reused, not copied)."""
    global _CA
    if _CA is None:
        spec = importlib.util.spec_from_file_location("check_all_for_release", ROOT / "tools" / "check_all.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["check_all_for_release"] = mod
        spec.loader.exec_module(mod)
        _CA = mod
    return _CA


def _path_problems(p: str, CA) -> str | None:
    low = p.lower()
    if any(low.startswith(d) for d in CA.FORBIDDEN_DIRS) or p in CA.FORBIDDEN_FILES:
        return "under a never-tracked path"
    if low.startswith("mods/") and p not in CA.MODS_TRACKED:
        return "mods/ may hold only README.md and .gitkeep"
    if low.startswith("roms/") and not ROMS_ALLOWED.match(p):
        return "roms/ may hold only README files"
    if p in CA.ALLOWED_TRACKED:
        return None
    ext = os.path.splitext(low)[1]
    if ext in CA.SUSPICIOUS_EXT:
        return f"ROM/asset/program extension {ext}"
    return None


def _leak_serious(keys, code: bytes, data: bytes, CA) -> list[str]:
    """The serious windows of one blob, exactly as check_hygiene_leak judges them (identifier-only raw runs and
    address-only decoded runs are allowed, D-006)."""
    found = [(f"raw @+{i:#x}", o, k) for i, o, k in CA.scan_leaks(keys, data)]
    if not CA.is_binary(data):
        for n, s in enumerate(CA.decoded_streams(data)):
            for i, o, _ in CA.scan_leaks(keys, s):
                kind = "pointers" if CA.is_pointer_window(code[o:o + CA.LEAK_WINDOW], len(code)) else "decoded"
                found.append((f"decoded stream {n} @+{i:#x}", o, kind))
    return [f"{w} = code.bin+{o:#x} ({k})" for w, o, k in found if k not in ("ident", "pointers")]


_W: dict = {}


def _leak_init(code_path: str):
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), BELOW_NORMAL)
        except Exception:
            pass
    CA = _check_all()
    code = Path(code_path).read_bytes()
    keys, _ = CA.leak_keys(code)
    _W.update(CA=CA, code=code, keys=keys)


def _leak_batch(items):
    return [(label, _leak_serious(_W["keys"], _W["code"], data, _W["CA"])) for label, data in items]


def _leak_scan(items, code_path: Path, lanes: int = 4) -> tuple[list[tuple[str, list[str]]], int, str]:
    """(label, serious windows) for every item with any; the number of keys; how it ran (serial / N lanes)."""
    CA = _check_all()
    code = code_path.read_bytes()
    keys, _ = CA.leak_keys(code)
    if not keys:
        raise PackageError(f"{code_path.name} gives no keys (empty or truncated): nothing could be checked")
    total = sum(len(d) for _, d in items)
    mode = "serial"
    if lanes <= 1 or total < 8 * 1024 * 1024:
        res = [(lb, _leak_serious(keys, code, d, CA)) for lb, d in items]
    else:
        mode = f"{lanes} lanes"
        batches, cur, size = [], [], 0
        for it in sorted(items, key=lambda x: -len(x[1])):
            cur.append(it)
            size += len(it[1])
            if size >= 2 * 1024 * 1024:
                batches.append(cur)
                cur, size = [], 0
        if cur:
            batches.append(cur)
        res = []
        try:
            with concurrent.futures.ProcessPoolExecutor(max_workers=lanes, initializer=_leak_init,
                                                        initargs=(str(code_path),)) as ex:
                for part in ex.map(_leak_batch, batches):
                    res += part
        except Exception as e:                      # module not importable in a child (loaded by path): serial
            mode = f"serial (lanes failed: {e.__class__.__name__})"
            res = [(lb, _leak_serious(keys, code, d, CA)) for lb, d in items]
    return [(lb, hits) for lb, hits in res if hits], len(keys), mode


# --------------------------------------------------------------------------- same-file index
def _ref_index(ref_dirs, skip=frozenset()) -> tuple[dict[int, list], list[str], int]:
    """size -> [file path | (zip path, member)], the dirs found, file count. skip: normalised paths of the repo's own
    tracked files (roms/README.txt is tracked AND inside roms/: it is ours, not a reference)."""
    idx: dict[int, list] = {}
    present, n = [], 0
    for d in ref_dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        present.append(d.name)
        stack = [d]
        while stack:
            cur = stack.pop()
            try:
                with os.scandir(cur) as it:
                    for e in it:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            if os.path.normcase(os.path.abspath(e.path)) in skip:
                                continue
                            n += 1
                            size = e.stat().st_size
                            idx.setdefault(size, []).append(e.path)
                            if e.name.lower().endswith(".zip"):
                                try:
                                    with zipfile.ZipFile(e.path) as z:
                                        for zi in z.infolist():
                                            if not zi.is_dir():
                                                n += 1
                                                idx.setdefault(zi.file_size, []).append((e.path, zi.filename))
                                except (zipfile.BadZipFile, OSError):
                                    pass
            except OSError:
                continue
    return idx, present, n


def _ref_sha(ref, cache) -> str:
    if ref in cache:
        return cache[ref]
    h = hashlib.sha256()
    if isinstance(ref, tuple):
        with zipfile.ZipFile(ref[0]) as z, z.open(ref[1]) as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
    else:
        with open(ref, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
    cache[ref] = h.hexdigest()
    return cache[ref]


def _same_file(items, ref_dirs, base: Path, skip=frozenset()) -> tuple[list[str], str]:
    idx, present, n = _ref_index(ref_dirs, skip)
    if not present:
        return ["no reference folder found (extracted/, play/, roms/): nothing could be compared"], "0 reference files"
    cache, hits = {}, []
    for label, data in items:
        if len(data) < SAME_FILE_MIN or len(data) not in idx:
            continue
        sha = hashlib.sha256(data).hexdigest()
        for ref in idx[len(data)]:
            try:
                if _ref_sha(ref, cache) == sha:
                    where = ref if isinstance(ref, str) else f"{ref[0]}!{ref[1]}"
                    try:
                        where = Path(where.split("!")[0]).resolve().relative_to(base).as_posix() + (
                            "!" + ref[1] if isinstance(ref, tuple) else "")
                    except ValueError:
                        pass
                    hits.append(f"{label} = {where}")
                    break
            except (OSError, zipfile.BadZipFile, KeyError):
                continue
    return hits, f"{n:,} reference files in {', '.join(present)}; {len(cache)} hashed (same size)"


# --------------------------------------------------------------------------- Seal ids-only
def _seal_problems(path: str, data: bytes) -> list[str]:
    if not path.lower().endswith(".json"):
        return [f"{path}: Seal of Flames data must be ids-only JSON (a table file is not allowed)"]
    try:
        doc = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        return [f"{path}: not readable JSON ({e.__class__.__name__})"]
    bad = []

    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    def walk(x, where):
        if len(bad) >= 5:
            return
        if isinstance(x, dict):
            ints = [k for k, v in x.items() if isinstance(v, int) and not isinstance(v, bool)]
            if len(ints) >= 3:
                bad.append(f"{path}: {where or '/'} holds {len(ints)} integers ({', '.join(ints[:4])}...): a stat row?")
            for k, v in x.items():
                walk(v, f"{where}/{k}")
        elif isinstance(x, list):
            if any(num(v) for v in x):
                bad.append(f"{path}: {where} is a list holding numbers (game values?)")
            for v in x:
                walk(v, where + "[]")
        elif isinstance(x, float) and not 0.0 <= x <= 1.0:
            bad.append(f"{path}: {where} = a number outside [0, 1]")
    walk(doc, "")
    return bad


# --------------------------------------------------------------------------- editions
def load_editions(repo, runner=None, rev="HEAD") -> dict | None:
    """config/release/editions.json as committed at rev (the zip and its leave-out list come from the same commit);
    None when the commit has none (an older commit: only today's package and the seal edition can be made)."""
    rc, out, _err = (runner or default_runner)(["git", "-C", str(repo), "show", f"{rev}:{EDITIONS_PATH}"])
    if rc:
        return None
    try:
        doc = json.loads(out.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise PackageError(f"{EDITIONS_PATH} at {rev} is not readable JSON ({e.__class__.__name__})")
    if not isinstance(doc, dict) or not isinstance(doc.get("editions"), dict):
        raise PackageError(f"{EDITIONS_PATH} at {rev} has no 'editions' table")
    return doc


def edition_conf(editions: dict | None, edition: str) -> dict:
    """One edition's settings, with the defaults filled in (seal works without editions.json; vanilla does not)."""
    if edition not in EDITION_NAMES:
        raise PackageError(f"unknown edition {edition!r}: use one of {', '.join(EDITION_NAMES)}")
    conf = dict(((editions or {}).get("editions") or {}).get(edition) or {})
    if edition == "vanilla" and not conf:
        raise PackageError(f"{EDITIONS_PATH} is missing from the commit (or has no 'vanilla' entry): the Vanilla+ zip "
                           "cannot know what to leave out")
    conf.setdefault("zip", DEFAULT_ZIPS[edition])
    conf.setdefault("bundle", edition == "seal")
    conf.setdefault("leave_out", [])
    conf.setdefault("credit_files", {f: list(n) for f, n in CREDIT_FILES.items()})
    conf.setdefault("marker_gate", edition == "vanilla")
    conf.setdefault("notes", None)                   # round 85: the committed public notes file, '{tag}' in its name
    conf.setdefault("last_public_tag", None)         # round 85: the newest tag on the public repo (r68)
    for k in ("markers", "marker_allowed_lines", "marker_allowed_paths", "marker_shared_by_design",
              "vanilla_needs_patch"):
        conf.setdefault(k, (editions or {}).get(k))
    conf["markers"] = list(conf["markers"] or DEFAULT_MARKERS)
    conf["marker_allowed_lines"] = dict(conf["marker_allowed_lines"] or {})
    conf["marker_allowed_paths"] = list(conf["marker_allowed_paths"] or [])
    conf["marker_shared_by_design"] = list(conf["marker_shared_by_design"] or [])
    for e in conf["leave_out"]:
        if not isinstance(e, str) or not e or e.startswith("/") or "\\" in e or ".." in e.split("/"):
            raise PackageError(f"{EDITIONS_PATH}: {e!r} is not a usable git path (forward slashes, relative)")
    return conf


def is_left_out(path: str, leave_out) -> bool:
    """A folder entry ('docs/seal/') leaves out everything under it; any other entry is one exact file."""
    return any(path == e or (e.endswith("/") and (path.startswith(e) or path + "/" == e)) for e in leave_out)


def marker_rx(markers) -> re.Pattern:
    """The strong Seal markers, case-insensitive, whole words; '/' also matches '\\' and '\\\\' (Windows paths);
    a space also matches '_', '=' or nothing (SEAL_OF_FLAMES, SealOfFlames, --game=seal; not '-': the profile
    folder play/seal-of-flames is shared by design)."""
    alts = []
    for m in sorted(set(markers), key=len, reverse=True):
        body = "".join(r"[/\\]{1,2}" if ch == "/" else r"[ _=]?" if ch == " " else re.escape(ch) for ch in m)
        if m[:1].isalnum():
            body = r"(?<![A-Za-z0-9_])" + body
        if m[-1:].isalnum():
            # a many-word marker also counts when an identifier goes on after it (SEAL_OF_FLAMES_PATH)
            body += r"(?![A-Za-z0-9])" if " " in m else r"(?![A-Za-z0-9_])"
        alts.append(body)
    return re.compile("(?i)" + "|".join(alts) if alts else r"(?!x)x")


def _glob_rx(pattern: str) -> re.Pattern:
    """A path pattern: '**' crosses folders, '*' and '?' stay inside one folder name (round 84 gate: a '*' that
    crossed '/' let tools/randomizer/* cover every subfolder too)."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _glob_hit(path: str, patterns) -> bool:
    return any(_glob_rx(p).match(path) for p in patterns)


def _allowed_lines_key(path: str, allowed: dict):
    """The marker_allowed_lines key for path: the exact path first, else the first pattern that matches (round 85:
    'config/release/notes/*-vanilla.md', the committed public notes, each with its one credit line); None if none."""
    if path in allowed:
        return path
    return next((k for k in allowed if any(c in k for c in "*?") and _glob_rx(k).match(path)), None)


def notes_marker_lines(text: str, markers=None) -> int:
    """How many lines of a notes text hold a strong Seal marker (the public notes may hold 1: the credit line)."""
    rx = marker_rx(markers or DEFAULT_MARKERS)
    return sum(1 for ln in text.splitlines() if rx.search(ln))


def marker_scan(entries: dict, conf: dict) -> dict:
    """Strong Seal markers in the files of one zip (path -> bytes). Returns dict(bad=[...], info=[...], allowed=n,
    files=n): bad = a marker outside the frozen history docs, the allowed credit lines and the gate's own files."""
    rx = marker_rx(conf["markers"])
    bad, info, allowed, files = [], [], 0, 0
    for p in sorted(entries):
        d = entries[p]
        if b"\0" in d:
            continue
        hits = [(n, m.group(0)) for n, line in enumerate(d.decode("utf-8", "replace").splitlines(), 1)
                for m in [rx.search(line)] if m]
        if not hits:
            continue
        files += 1
        first = f"{p}:{hits[0][0]} '{hits[0][1]}'" + (f" (+{len(hits) - 1} more line(s))" if len(hits) > 1 else "")
        if p in GATE_OWN_FILES:
            info.append(f"{first} [the edition gate's own file]")
        elif _glob_hit(p, conf["marker_allowed_paths"]):
            allowed += 1
        elif _allowed_lines_key(p, conf["marker_allowed_lines"]) is not None:
            n = int(conf["marker_allowed_lines"][_allowed_lines_key(p, conf["marker_allowed_lines"])])
            if len(hits) <= n:
                allowed += 1
            else:
                bad.append(f"{p}: {len(hits)} lines hold a Seal marker (allowed {n}; first {first})")
        elif _glob_hit(p, conf["marker_shared_by_design"]):
            info.append(f"{first} [shared by design, {EDITIONS_PATH}]")
        else:
            bad.append(first)
    return {"bad": bad, "info": info, "allowed": allowed, "files": files}


def worktree_markers(repo=None, runner=None) -> dict:
    """The marker scan the Vanilla+ zip would get, run on the CURRENT files a commit would hold: the tracked files plus
    the new files git does not ignore (working tree, editions.json from the working tree), so a lane can see its
    markers before a commit. Round 84 repair: new untracked files count too (tests/_edition.py slipped past this check
    while it was untracked, then failed the practice zip's edition gate). Writes nothing."""
    repo = Path(repo or ROOT).resolve()
    ep = repo / EDITIONS_PATH
    editions = json.loads(ep.read_text(encoding="utf-8")) if ep.is_file() else None
    conf = edition_conf(editions, "vanilla")
    out = _git(repo, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"], runner)
    files = sorted({p for p in out.decode("utf-8", "surrogateescape").split("\0") if p})
    entries = {}
    for p in files:
        fp = repo / p
        if not is_left_out(p, conf["leave_out"]) and fp.is_file():
            entries[p] = fp.read_bytes()
    res = marker_scan(entries, conf)
    res["left_out"] = sum(is_left_out(p, conf["leave_out"]) for p in files)
    return res


def _short_without_seal(short: str, markers) -> str:
    """Grok (build/r84/release/grok_release.txt): the public Vanilla+ notes drop the sentences that are only about
    Seal of Flames; a round that was only Seal work becomes one line."""
    rx = marker_rx(markers)
    parts = re.split(r"(?<=[.!?;])\s+(?=[A-Z(\"'*`])", short)
    keep = [s for s in parts if not rx.search(s) and not SEAL_EDITION_WORDS.search(s)]
    if not keep:
        return "Seal edition work is in that edition's notes."
    return " ".join(keep)


# --------------------------------------------------------------------------- notes
NOT_INCLUDED = """## Not included
- The game. Use your own clean dump of Fire Emblem Fates (Special Edition, USA); its SHA-256 is checked against
  `config/game.json`. It is never shared.
- Seal of Flames by Laz14 (https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0). Download it from GameBanana
  yourself and put the zip, still zipped, in `roms/seal/`. No file of the mod is in this release.
- Any program file: no .exe, no .dll, no game bytes. The standalone game program is built on your own PC.
"""

WHAT_YOU_NEED = """## What you need
- Windows 11, Python 3.13 (standard library only) and Git for Windows.
- Your own decrypted copy of Fire Emblem Fates, Special Edition (USA), as a .cci file in `roms/` (see
  `roms/README.txt`). Start with `Read Me First.txt` and `README.md`.
- Then pick a road. Neither road has been tried on a clean PC yet.
  - **Road A (no build):** install Zakuro (https://github.com/fearkov/zakuro) and let it recompile the game once,
    then double-click `PLAY.bat`. You get the plain game. The in-game Randomizer page, True hit, the New Game
    defaults and built-in 60 fps / 16:9 come from our Zakuro patches, so they need Road B.
  - **Road B (build it):** install Rust and the Visual Studio C++ Build Tools, then build our patched Zakuro on
    your own PC (`docs/BUILD.md`). You get everything. The program you build is for you only: never share it.
"""

CREDITS_BLOCK = """## Credits
Full list: `CREDITS.md`. Zakuro by fearkov (MIT; our patches in `patches/zakuro/`, notices in
`patches/zakuro/NOTICE.md`); 3dsrecomp by fearkov; fe-awakening-recomp by Zelkin1 (MIT); Seal of Flames by Laz14
(https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0, not included); facts from Paragon and mila by thane98 (GPL,
read for facts only, never copied), the fefates-tools wiki, SPICA, 3dbrew, Serenes Forest and the Fire Emblem Wiki.
Grok (xAI) is the project's creative lead.
"""

# Vanilla+ (docs/SEAL_EDITION_PLAN.md section 6): one Seal line only, in the credits, no install steps
VANILLA_SEAL_LINE = ("Seal of Flames by Laz14 (https://gamebanana.com/mods/656034, CC BY-NC-ND 4.0) is a separate fan "
                     "mod. The mod is never included.")

NOT_INCLUDED_VANILLA = """## Not included
- The game. Use your own clean dump of Fire Emblem Fates (Special Edition, USA); its SHA-256 is checked against
  `config/game.json`. It is never shared.
- Any program file: no .exe, no .dll, no game bytes. The standalone game program is built on your own PC.
"""

CREDITS_BLOCK_VANILLA = """## Credits
Full list: `CREDITS.md`. Zakuro by fearkov (MIT; our patches in `patches/zakuro/`, notices in
`patches/zakuro/NOTICE.md`); 3dsrecomp by fearkov; fe-awakening-recomp by Zelkin1 (MIT); facts from Paragon and mila
by thane98 (GPL, read for facts only, never copied), the fefates-tools wiki, SPICA, 3dbrew, Serenes Forest and the
Fire Emblem Wiki. Grok (xAI) is the project's creative lead.
""" + VANILLA_SEAL_LINE + "\n"

# the Seal of Flames edition leads with the credit (section 6; Grok: fans expect it above "What changed")
SEAL_CREDIT_LEAD = """## Seal of Flames
Seal of Flames by Laz14 (https://gamebanana.com/mods/656034), CC BY-NC-ND 4.0. Not included: download it yourself
from GameBanana and put the zip, still zipped, in `roms/seal/`. This port is not affiliated with or endorsed by Laz14.
Bugs in the port go to us, not to Laz14. We never share the mod. Get it from Laz14's page. Do not share a changed
copy, and do not sell it.
"""

INTRO = ("Source-only release of the Fire Emblem Fates (Special Edition, USA) PC port: tools, readable code, "
         "patches, tests and docs. Not pushed by any tool: only the owner pushes.\n")
INTRO_EDITION = ("Source-only release of the Fire Emblem Fates (Special Edition, USA) PC port: tools, the built-in "
                 "randomizer, readable code, patches, tests and docs. There is no program in the zip. Not pushed by "
                 "any tool: only the owner pushes.\n")


def _report_entry(path: str, text: str) -> str:
    lines = text.splitlines()
    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), Path(path).stem)
    m = re.search(r"\*\*Short version:\*\*\s*(.+?)(?:\n\s*\n|\Z)", text, re.S)
    if m:
        short = " ".join(m.group(1).split())
    else:                                           # first paragraph after the title that is not a Time: line
        paras = [p for p in re.split(r"\n\s*\n", text) if p.strip() and not p.lstrip().startswith(("#", "Time:"))]
        short = " ".join(paras[0].split()) if paras else "(no short version)"
    waiting = bool(OWNER_OK.search(short))
    short = OWNER_OK.sub("", short).strip()
    out = f"### {title}\n{short}\n"
    if waiting:
        out += "\n*Status: waiting for the owner's ok.*\n"
    return out


def _reports_at(repo, rev, runner=None) -> list[str]:
    out = _git(repo, ["ls-tree", "--name-only", rev, "docs/"], runner, check=False)
    return sorted(p for p in out.decode("utf-8", "replace").splitlines() if re.match(r"^docs/REPORT_.*\.md$", p))


def notes(repo, prev_tag, tag, *, runner=None, specs=None, env=None, edition=None, markers=None) -> str:
    """Release notes: each docs/REPORT_*.md new since prev_tag (the newest one when there is no previous tag),
    read from HEAD, its 'Short version', items still waiting for the owner's ok marked, then the fixed blocks.
    Every private or folder term is replaced by a neutral word (<user>, <home>, <repo>, <folder>).
    edition None: today's notes. 'seal': titled for the Seal of Flames edition, the credit first. 'vanilla': the
    sentences only about Seal of Flames dropped, one Seal line (the credit) only."""
    if specs is None:
        specs = term_specs(repo, env, runner)
    if edition is not None and edition not in EDITION_NAMES:
        raise PackageError(f"unknown edition {edition!r}")
    now = _reports_at(repo, "HEAD", runner)
    if prev_tag:
        before = set(_reports_at(repo, prev_tag, runner))
        new = [p for p in now if p not in before]
        since = f"since {prev_tag}"
    else:
        new = now[-1:]
        since = "first release: the newest round only; earlier rounds are in docs/REPORT_*.md"
    if edition is None:
        parts = [f"# FE Fates PC port {tag}\n", INTRO]
    elif edition == "seal":
        parts = [f"# FE Fates PC port {tag}, Seal of Flames edition\n", INTRO_EDITION, SEAL_CREDIT_LEAD]
    else:
        parts = [f"# FE Fates PC port {tag}\n", INTRO_EDITION]
    parts.append(f"## What changed ({since})\n")
    if not new:
        parts.append("No new round report since the previous release.\n")
    for p in new:
        text = _git(repo, ["show", f"HEAD:{p}"], runner).decode("utf-8", "replace")
        entry = _report_entry(p, text)
        if edition == "vanilla":
            mk = markers or DEFAULT_MARKERS
            head, _, rest = entry.partition("\n")
            body, sep, status = rest.partition("\n\n*Status:")
            if marker_rx(mk).search(head) or SEAL_EDITION_WORDS.search(head):
                head = head.split(":")[0]           # "### Round 84 report: Seal edition split B" -> "### Round 84 report"
                if marker_rx(mk).search(head) or SEAL_EDITION_WORDS.search(head):
                    head = "### A round report"
            entry = head + "\n" + _short_without_seal(body.strip(), mk) + "\n" + ("\n*Status:" + status if sep else "")
        parts.append(entry)
    if edition == "vanilla":
        parts += [NOT_INCLUDED_VANILLA, WHAT_YOU_NEED, CREDITS_BLOCK_VANILLA]
    else:
        parts += [NOT_INCLUDED, WHAT_YOU_NEED, CREDITS_BLOCK]
    return mask_text("\n".join(parts), specs, neutral=True)


def committed_notes(repo, tag, conf, runner=None, rev="HEAD"):
    """(git path, bytes) of the committed public notes for tag (round 85, docs/PUBLIC_RELEASE_PLAN.md section 9 fix
    4: conf['notes'], e.g. config/release/notes/{tag}-vanilla.md, as committed at rev), or None when the edition names
    no notes file or the commit has none for this tag (then the notes are made from the reports, as before)."""
    pattern = (conf or {}).get("notes")
    if not pattern:
        return None
    rel = str(pattern).format(tag=tag)
    if rel.startswith("/") or "\\" in rel or ".." in rel.split("/"):
        raise PackageError(f"{EDITIONS_PATH}: notes path {rel!r} is not a usable git path")
    rc, out, _err = (runner or default_runner)(["git", "-C", str(repo), "show", f"{rev}:{rel}"])
    if rc:
        return None
    try:
        out.decode("utf-8")
    except UnicodeDecodeError as e:
        raise PackageError(f"{rel} is not UTF-8 text ({e.reason})")
    return rel, out


# --------------------------------------------------------------------------- build
def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _gate(gates, name, ok, detail, t0, **extra):
    g = {"name": name, "ok": bool(ok), "detail": detail, "what": ALL_GATES.get(name, ""),
         "secs": round(time.time() - t0, 1)}
    g.update(extra)
    gates.append(g)
    return g


def build(repo, tag, prev_tag, out_dir, *, runner=None, env=None, terms=None, email=None, ref_dirs=None,
          code_bin=None, lanes=4, log=None, edition=None, editions=None) -> dict:
    """Make the zip, bundle, notes and sums for HEAD of repo and run every gate (module doc).
    Returns dict(ok, zip, bundle, sums, notes_path, gates=[{name, ok, detail, what, secs}], counts, privacy).
    edition None: today's package in out_dir. 'seal' / 'vanilla': that edition in out_dir/<edition>/ (module doc).
    editions: the editions table (tests); default config/release/editions.json as committed at HEAD."""
    log = log or (lambda s: None)
    runner = runner or default_runner
    repo = Path(repo).resolve()
    if not TAG_RX.match(tag or ""):
        raise PackageError(f"not a usable tag name: {tag!r}")
    if edition is not None and edition not in EDITION_NAMES:
        raise PackageError(f"unknown edition {edition!r}: use one of {', '.join(EDITION_NAMES)}")
    conf = None
    if edition is not None:
        if editions is None:
            editions = load_editions(repo, runner)
        conf = edition_conf(editions, edition)
    vanilla = edition == "vanilla"
    with_bundle = conf is None or bool(conf["bundle"])
    out = Path(out_dir).resolve() / (edition or "")  # absolute: git runs with -C repo
    out.mkdir(parents=True, exist_ok=True)
    main = _main_root(repo, runner)
    specs = term_specs(repo, env, runner, extra=terms, email=email)
    any_rx = _any_rx(specs)
    ref_dirs = ref_dirs if ref_dirs is not None else [main / "extracted", main / "play", main / "roms"]
    code_bin = Path(code_bin) if code_bin else main / "extracted" / "code.bin"
    CA = _check_all()
    gates: list[dict] = []
    t_all = time.time()
    zip_name = ZIP_NAME.format(tag=tag) if conf is None else conf["zip"].format(tag=tag)
    if conf is not None and not TAG_RX.match(zip_name[:-4] if zip_name.lower().endswith(".zip") else ""):
        raise PackageError(f"{EDITIONS_PATH}: zip name {conf and conf['zip']!r} is not usable")
    zpath, bpath = out / zip_name, out / BUNDLE_NAME.format(tag=tag)
    npath, spath = out / NOTES_NAME, out / SUMS_NAME
    prefix = PREFIX.format(tag=tag) if conf is None else zip_name[:-4] + "/"
    leave_out = list(conf["leave_out"]) if vanilla else []
    head = _git(repo, ["rev-parse", "HEAD"], runner).decode().strip()

    # archive
    t0 = time.time()
    for p in (zpath, bpath, npath, spath, out / RESULT_NAME):
        if p.exists():
            p.unlink()
    spec = ["--", ".", *(f":(exclude,literal){e.rstrip('/')}" for e in leave_out)] if leave_out else []
    _git(repo, ["archive", "--format=zip", f"--prefix={prefix}", "-o", str(zpath), "HEAD", *spec], runner)
    entries: dict[str, bytes] = {}
    outside, names = [], []
    with zipfile.ZipFile(zpath) as z:
        for zi in z.infolist():
            if not zi.filename.startswith(prefix):
                outside.append(zi.filename)
                continue
            names.append(zi.filename[len(prefix):])
            if zi.is_dir():
                continue
            entries[zi.filename[len(prefix):]] = z.read(zi)
    tracked = [p for p in _git(repo, ["ls-files", "-z"], runner).decode("utf-8", "surrogateescape").split("\0") if p]
    missing = sorted(set(tracked) - set(entries))
    meant = sorted(p for p in tracked if is_left_out(p, leave_out))
    surprise = sorted(set(missing) - set(meant))        # missing but not on the leave-out list
    kept = sorted(set(meant) - set(missing))            # on the leave-out list but still in the zip
    _gate(gates, "archive", entries and not outside and not surprise and not kept,
          f"{len(entries)} files, {zpath.stat().st_size:,} bytes zipped, {sum(map(len, entries.values())):,} unpacked"
          + (f"; {len(meant) - len(kept)} tracked file(s) left out on purpose ({EDITIONS_PATH})" if vanilla else "")
          + (f"; {len(outside)} entries outside {prefix}" if outside else "")
          + (f"; {len(surprise)} tracked files missing (export-ignore?): {', '.join(surprise[:3])}" if surprise else "")
          + (f"; {len(kept)} left-out file(s) still in the zip: {', '.join(kept[:3])}" if kept else ""),
          t0, left_out=len(meant) - len(kept) if vanilla else 0)
    log(f"archive: {gates[-1]['detail']}")

    # bundle
    t0 = time.time()
    branch_refs = _history_refs(repo, runner)        # HEAD master --tags (round 85 fix 3; helper branches stay out)
    if with_bundle:
        rc, o, e = runner(["git", "-C", str(repo), "bundle", "create", str(bpath), *branch_refs])
        vrc, vo, ve = (1, b"", e) if rc else runner(["git", "-C", str(repo), "bundle", "verify", str(bpath)])
        _gate(gates, "bundle-verify", rc == 0 and vrc == 0,
              (f"{bpath.stat().st_size:,} bytes; verify ok" if rc == 0 and vrc == 0 else
               "bundle failed: " + (ve or e).decode("utf-8", "replace").strip()[:200]), t0)
    else:
        _gate(gates, "bundle-verify", True, NOT_APPLICABLE, t0, applicable=False)
    log(f"bundle: {gates[-1]['detail']}")

    # notes: the committed public notes file word for word when the commit has one for this tag (Vanilla+, round 85),
    # else made from the reports; either way the credit, marker, leak and privacy gates below read them
    fixed = committed_notes(repo, tag, conf, runner) if vanilla else None
    if fixed:
        notes_source = fixed[0]
        npath.write_bytes(fixed[1])
        log(f"notes: {notes_source} word for word")
    else:
        notes_source = "reports"
        text = notes(repo, prev_tag, tag, runner=runner, specs=specs, edition=edition,
                     markers=conf["markers"] if conf else None)
        npath.write_text(text, encoding="utf-8", newline="\n")
    notes_bytes = npath.read_bytes()

    # history blobs not in HEAD's tree (only a package with the bundle carries them)
    if with_bundle:
        head_blobs = _head_blobs(repo, runner)
        hist_blobs, commits = _history_objects(repo, runner)
        older = {s: p for s, p in hist_blobs.items() if s not in head_blobs}
        older_data = [(f"{p} @blob {s[:8]}", p, d) for s, typ, d in _cat_batch(repo, list(older), runner)
                      for p in [older[s]]]
    else:
        older, older_data, commits = {}, [], []

    # zip-reopen
    t0 = time.time()
    bad = [f"{n}: outside {prefix}" for n in outside]
    for p, d in sorted(entries.items()):
        why = _path_problems(p, CA)
        if why:
            bad.append(f"{p}: {why}")
        if b"\0" in d:
            bad.append(f"{p}: binary content (NUL bytes)")
        if len(d) > MAX_BLOB:
            bad.append(f"{p}: {len(d):,} bytes (over 50 MB)")
        if p.lower().endswith((".bat", ".cmd")):
            if not d or re.search(rb"(?<!\r)\n", d):
                bad.append(f"{p}: not CRLF (cmd.exe misreads LF-only batch files)")
    nbat = sum(p.lower().endswith((".bat", ".cmd")) for p in entries)
    if bad:
        detail = f"{len(entries)} files reopened; {len(bad)} problem(s): " + "; ".join(bad[:4])
    else:
        detail = f"{len(entries)} files reopened, {nbat} batch files CRLF; roms/ and mods/ hold READMEs only"
    _gate(gates, "zip-reopen", not bad, detail, t0, problems=bad[:50])
    log(f"zip-reopen: {gates[-1]['detail']}")

    # history-paths
    t0 = time.time()
    bad = []
    for label, p, d in older_data:
        why = _path_problems(p, CA)
        if why:
            bad.append(f"{label}: {why}")
        if b"\0" in d:
            bad.append(f"{label}: binary content (NUL bytes)")
        if len(d) > MAX_BLOB:
            bad.append(f"{label}: {len(d):,} bytes (over 50 MB)")
    if with_bundle:
        _gate(gates, "history-paths", not bad,
              f"{len(older_data)} older blobs in {len(commits)} commits; {len(bad)} problem(s)"
              + (": " + "; ".join(bad[:4]) if bad else ""), t0, problems=bad[:50])
    else:
        _gate(gates, "history-paths", True, NOT_APPLICABLE, t0, applicable=False)
    log(f"history-paths: {gates[-1]['detail']}")

    scan_items = ([(f"zip:{p}", d) for p, d in entries.items()]
                  + [(f"history:{lb}", d) for lb, _, d in older_data] + [("notes", notes_bytes)])
    scan_bytes = sum(len(d) for _, d in scan_items)

    # leak
    t0 = time.time()
    if not code_bin.is_file():
        _gate(gates, "leak", False, f"{code_bin.name} not found (extract the ROM first: python tools\\extract_rom.py):"
                                    " nothing could be checked", t0)
    else:
        try:
            hits, nkeys, mode = _leak_scan(scan_items, code_bin, lanes)
            _gate(gates, "leak", not hits,
                  f"{len(scan_items)} blobs ({scan_bytes:,} bytes) vs {nkeys:,} code.bin keys; "
                  f"{len(hits)} with code.bin bytes ({mode})"
                  + (": " + "; ".join(f"{lb} ({len(h)} window(s), first {h[0]})" for lb, h in hits[:3]) if hits else ""),
                  t0, problems=[f"{lb}: {h[0]}" for lb, h in hits[:50]])
        except PackageError as e:
            _gate(gates, "leak", False, str(e), t0)
    log(f"leak: {gates[-1]['detail']}")

    # same-file
    t0 = time.time()
    own = [p for p in _git(main, ["ls-files", "-z"], runner).decode("utf-8", "surrogateescape").split("\0") if p]
    skip = frozenset(os.path.normcase(os.path.abspath(main / p)) for p in own)
    hits, info = _same_file(scan_items, ref_dirs, main, skip)
    _gate(gates, "same-file", not hits,
          f"{len(scan_items)} blobs vs {info}; {len(hits)} identical" + (": " + "; ".join(hits[:3]) if hits else ""),
          t0, problems=hits[:50])
    log(f"same-file: {gates[-1]['detail']}")

    # seal-ids
    t0 = time.time()
    seal = sorted(p for p in entries if SEAL_DATA.match(p))
    bad = [b for p in seal for b in _seal_problems(p, entries[p])]
    _gate(gates, "seal-ids", not bad,
          f"{len(seal)} Seal-derived file(s) ({', '.join(Path(p).name for p in seal) or 'none'}); "
          f"{len(bad)} problem(s)" + (": " + "; ".join(bad[:3]) if bad else ": ids only"), t0, problems=bad[:50])
    log(f"seal-ids: {gates[-1]['detail']}")

    # credits
    t0 = time.time()
    bad = []
    credit_files = CREDIT_FILES if conf is None else conf["credit_files"]
    for f, needles in credit_files.items():
        if f not in entries:
            bad.append(f"{f} missing")
            continue
        txt = entries[f].decode("utf-8", "replace")
        bad += [f"{f} lacks '{n}'" for n in needles if n.lower() not in txt.lower()]
    notices = [p for p in tracked if Path(p).name.upper() == "NOTICE.MD" and not is_left_out(p, leave_out)]
    bad += [f"{p} not packed or empty" for p in notices if not entries.get(p, b"").strip()]
    ntxt = notes_bytes.decode("utf-8", "replace")
    bad += [f"notes lack '{n}'" for n in ("Laz14", SEAL_LINK, SEAL_LICENCE) if n not in ntxt]
    if conf is not None:                            # both editions say "not included" in the notes, every time
        bad += [] if re.search(r"(?i)\b(?:not|never) included\b", ntxt) else ["notes lack 'not included'"]
    _gate(gates, "credits", not bad,
          (f"Laz14 + {SEAL_LINK} + {SEAL_LICENCE} in {', '.join(credit_files)} and the notes"
           + (f" ({edition} edition)" if edition else "") + f"; {len(notices)} NOTICE.md packed")
          if not bad else "; ".join(bad[:5]), t0, problems=bad)
    log(f"credits: {gates[-1]['detail']}")

    # privacy-head (zip files + notes)
    t0 = time.time()
    head_found = []
    for p, d in entries.items():
        head_found += _scan_text(p, d.decode("utf-8", "replace"), "head", specs, any_rx)
    head_found += _scan_text("RELEASE_NOTES.md", ntxt, "notes", specs, any_rx)
    priv = [f for f in head_found if f["severity"] == "private"]
    info = [f for f in head_found if f["severity"] == "info"]
    _gate(gates, "privacy-head", not priv,
          f"{len(priv)} private finding(s) in HEAD/notes" + (
              " (" + ", ".join(sorted({f"{f['where']}:{f['line']} {f['kind']}" for f in priv})[:4]) + ")" if priv else "")
          + f"; {len(info)} info (folder paths: " + (", ".join(sorted({f['where'] for f in info})[:6]) or "none") + ")",
          t0, findings=head_found[:200])
    log(f"privacy-head: {gates[-1]['detail']}")

    # privacy-history (older blobs + commits): never fails, blocks the push
    t0 = time.time()
    hist_found = []
    for label, p, d in older_data:
        hist_found += _scan_text(label, d.decode("utf-8", "replace"), "history", specs, any_rx)
    for sha, typ, d in _cat_batch(repo, commits, runner):
        for f in _scan_text(f"commit {sha[:8]}", d.decode("utf-8", "replace"), "history", specs, any_rx):
            f["commits"] = [sha[:8]]
            hist_found.append(f)
    hpriv = [f for f in hist_found if f["severity"] == "private"]
    if hpriv:                                       # which commits carry each private blob
        blob_of = {f"{older[s]} @blob {s[:8]}": s for s in older}
        for f in hpriv[:20]:
            s = blob_of.get(f["where"])
            if s and "commits" not in f:
                o2 = _git(repo, ["log", "--format=%h", f"--find-object={s}", *branch_refs], runner, check=False)
                f["commits"] = o2.decode().split()[:10]
    ncommits = len({c for f in hpriv for c in f.get("commits", [])})
    if with_bundle:
        _gate(gates, "privacy-history", True,
              f"{len(hpriv)} private finding(s) in older history" + (f" ({ncommits} commit(s); blocks the push only)"
                                                                     if hpriv else "")
              + f"; {len(hist_found) - len(hpriv)} info", t0, push_blocked=bool(hpriv), findings=hist_found[:200])
    else:
        _gate(gates, "privacy-history", True, NOT_APPLICABLE, t0, applicable=False, push_blocked=False, findings=[])
    log(f"privacy-history: {gates[-1]['detail']}")

    # edition (Vanilla+ only)
    if vanilla:
        t0 = time.time()
        bad = [f"{n}: left out by {EDITIONS_PATH} but in the zip" for n in names if is_left_out(n, leave_out)]
        bad += [f"{p}: a config/**/seal* file in the Vanilla+ zip" for p in entries if SEAL_NAMED_CONFIG.match(p)]
        ms = marker_scan(entries, conf)
        bad += [f"marker: {b}" for b in ms["bad"]]
        nhits = [ln for ln in ntxt.splitlines() if marker_rx(conf["markers"]).search(ln)]
        if len(nhits) > 1:
            bad.append(f"notes: {len(nhits)} lines hold a Seal marker (allowed 1, the credit line)")
        last = conf.get("last_public_tag")
        if fixed and last and not re.search(rf"(?<![A-Za-z0-9]){re.escape(str(last))}(?![0-9])", ntxt):
            bad.append(f"notes: {notes_source} never names {last}, the last public release (strangers last saw {last}: "
                       f"say what changed since it)")
        need = conf.get("vanilla_needs_patch")
        if need:
            pz = _git(repo, ["ls-tree", "--name-only", "HEAD", "patches/zakuro/"], runner, check=False)
            have = [ln for ln in pz.decode("utf-8", "replace").splitlines()
                    if Path(ln).name.startswith(f"{need}-") and ln.endswith(".patch")]
            if not have:
                bad.append(f"patch {need} (the Seal page hide) is not in this commit: no Vanilla+ zip while the page "
                           "still shows Seal")
        detail = (f"{len(meant)} tracked file(s) on the leave-out list, {len(kept)} of them in the zip; strong Seal "
                  f"markers in {ms['files']} file(s): {ms['allowed']} allowed (frozen history / credit line), "
                  f"{len(ms['info'])} info, {len(ms['bad'])} not allowed; notes ({notes_source}) {len(nhits)} marker "
                  f"line(s)"
                  + (f"; patch {need} in the commit" if need and not any(b.startswith("patch ") for b in bad) else ""))
        if bad:
            detail += f"; {len(bad)} problem(s): " + "; ".join(bad[:4])
        _gate(gates, "edition", not bad, detail, t0, problems=bad[:200], marker_info=ms["info"][:50],
              marker_files=ms["files"], marker_allowed=ms["allowed"], notes_marker_lines=len(nhits))
        log(f"edition: {detail}")

    # sums
    t0 = time.time()
    files = [p for p in (zpath, bpath if with_bundle else None, npath) if p is not None and p.exists()]
    sums = {p.name: _sha256_file(p) for p in files}
    spath.write_text("".join(f"{h}  {n}\n" for n, h in sums.items()), encoding="ascii", newline="\n")
    back = {}
    for line in spath.read_text(encoding="ascii").splitlines():
        h, _, n = line.partition("  ")
        back[n] = h
    bad = [n for n in sums if back.get(n) != _sha256_file(out / n)]
    _gate(gates, "sums", files and not bad and len(back) == len(files),
          f"{len(files)} files listed and re-checked" + (f"; mismatch: {', '.join(bad)}" if bad else ""), t0)

    missing_gates = [n for n in gate_set(edition) if n not in {g["name"] for g in gates}]
    ok = all(g["ok"] for g in gates) and not missing_gates
    result = {
        "format": FORMAT, "ok": ok, "tag": tag, "prev_tag": prev_tag, "head": head,
        "edition": edition or DEFAULT_EDITION, "edition_flag": edition, "gate_set": gate_set(edition),
        "zip": str(zpath), "bundle": str(bpath) if with_bundle else None, "sums": str(spath), "notes_path": str(npath),
        "notes_source": notes_source,
        "gates": gates,
        "counts": {"zip_files": len(entries), "zip_bytes": zpath.stat().st_size,
                   "left_out": len(meant) - len(kept) if vanilla else 0,
                   "bundle_bytes": bpath.stat().st_size if with_bundle and bpath.exists() else 0,
                   "older_blobs": len(older_data), "commits": len(commits), "scanned_bytes": scan_bytes},
        "privacy": {"terms": masked_terms(specs), "head_private": len(priv), "head_info": len(info),
                    "history_private": len(hpriv), "history_info": len(hist_found) - len(hpriv),
                    "push_blocked": bool(hpriv) or bool(priv)},
        "secs": round(time.time() - t_all, 1),
    }
    # the record never holds a private string: mask everything once more before writing (paths included)
    blob = mask_text(json.dumps(result, indent=1), [t for t in specs if t.severity == "private"])
    (out / RESULT_NAME).write_text(blob, encoding="utf-8", newline="\n")
    return json.loads(blob)


# --------------------------------------------------------------------------- redaction of current files
def redact(repo=None, write=False, *, specs=None, runner=None, env=None, info_under=("docs/",)) -> list[dict]:
    """Private terms in the CURRENT tracked files (working tree): [{path (masked), kind, count}]. With write=True each
    is replaced by its neutral word (<user>, <home>); folder paths (info) only under info_under (tools that need a
    path keep it). History is never rewritten."""
    repo = Path(repo or ROOT).resolve()
    specs = specs if specs is not None else term_specs(repo, env, runner)
    any_rx = _any_rx(specs)
    files = [p for p in _git(repo, ["ls-files", "-z"], runner).decode("utf-8", "surrogateescape").split("\0") if p]
    out = []
    for p in files:
        fp = repo / p
        if not fp.is_file():
            continue
        raw = fp.read_bytes()
        if b"\0" in raw:
            continue
        text = raw.decode("utf-8", "surrogateescape")
        if not any_rx.search(text):
            continue
        use = [t for t in specs if t.severity == "private" or p.startswith(tuple(info_under))]
        new = text
        for t in use:
            k = len(t.rx.findall(new))
            if k:
                out.append({"path": mask_text(p, specs), "kind": t.kind, "severity": t.severity, "count": k})
                new = t.rx.sub(t.neutral, new)
        work = new
        for t in specs:
            k = 0 if t in use else len(t.rx.findall(work))
            if k:
                out.append({"path": mask_text(p, specs), "kind": t.kind, "severity": t.severity,
                            "count": k, "kept": "a tool needs this path"})
                work = t.rx.sub(t.neutral, work)
        if write and new != text:
            fp.write_bytes(new.encode("utf-8", "surrogateescape"))
    return out


# --------------------------------------------------------------------------- CLI
def _print_findings(found, limit=40):
    for f in found[:limit]:
        extra = f" commits {','.join(f['commits'])}" if f.get("commits") else ""
        print(f"  [{f['severity']}] {f['scope']} {f['where']}:{f['line']} {f['kind']} x{f['count']}{extra}: {f['text']}")
    if len(found) > limit:
        print(f"  ... and {len(found) - limit} more")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--tag", required=True)
    b.add_argument("--prev", default=None)
    b.add_argument("--out", default=None)
    b.add_argument("--repo", default=str(ROOT))
    b.add_argument("--lanes", type=int, default=4)
    b.add_argument("--edition", choices=EDITION_NAMES, default=None,
                   help="vanilla or seal: that edition in <out>/<edition>/; no flag = today's package in <out>")
    n = sub.add_parser("notes")
    n.add_argument("--tag", required=True)
    n.add_argument("--prev", default=None)
    n.add_argument("--repo", default=str(ROOT))
    n.add_argument("--edition", choices=EDITION_NAMES, default=None)
    m = sub.add_parser("markers")
    m.add_argument("--repo", default=str(ROOT))
    s = sub.add_parser("scan")
    s.add_argument("paths", nargs="*")
    s.add_argument("--history", action="store_true")
    s.add_argument("--since", default=None)
    s.add_argument("--repo", default=str(ROOT))
    r = sub.add_parser("redact")
    r.add_argument("--write", action="store_true")
    r.add_argument("--repo", default=str(ROOT))
    sub.add_parser("terms")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.cmd == "terms":
        for t in masked_terms(term_specs(ROOT)):
            print(f"  {t['kind']:<7} {t['severity']:<8} {t['masked']}")
        return 0
    if a.cmd == "notes":
        if a.edition == "vanilla":                  # the committed public notes file, when HEAD has one for the tag
            fixed = committed_notes(a.repo, a.tag, edition_conf(load_editions(a.repo), "vanilla"))
            if fixed:
                print(f"({fixed[0]}, word for word)")
                print(fixed[1].decode("utf-8"))
                return 0
        print(notes(a.repo, a.prev, a.tag, edition=a.edition))
        return 0
    if a.cmd == "markers":
        res = worktree_markers(a.repo)
        print(f"Vanilla+ marker check on the current tracked and new (not ignored) files ({res['left_out']} left out by {EDITIONS_PATH}): "
              f"markers in {res['files']} file(s), {res['allowed']} allowed, {len(res['info'])} info, "
              f"{len(res['bad'])} not allowed")
        for b in res["bad"]:
            print(f"  NOT ALLOWED  {b}")
        for i in res["info"]:
            print(f"  info         {i}")
        return 1 if res["bad"] else 0
    if a.cmd == "scan":
        found = privacy_scan(a.paths, a.history, repo=a.repo, since=a.since)
        priv = [f for f in found if f["severity"] == "private"]
        print(f"{len(found)} finding(s), {len(priv)} private (masked):")
        _print_findings(found)
        return 1 if any(f["scope"] in ("head", "file") for f in priv) else 0
    if a.cmd == "redact":
        found = redact(a.repo, a.write)
        for f in found:
            print(f"  {'kept' if f.get('kept') else ('redacted' if a.write else 'would redact')}: {f['path']} "
                  f"{f['kind']} x{f['count']}")
        print(f"{len(found)} item(s)")
        return 0
    out = a.out or str(ROOT / "build" / "release" / a.tag / "package")
    res = build(a.repo, a.tag, a.prev, out, lanes=a.lanes, log=lambda s: print(s, flush=True), edition=a.edition)
    print()
    for g in res["gates"]:
        print(f"  {'PASS' if g['ok'] else 'FAIL'}  {g['name']:<16} {g['secs']:>6.1f} s  {g['detail']}")
    fh = [f for g in res["gates"] if g["name"].startswith("privacy") for f in g.get("findings", [])]
    if fh:
        print("privacy findings (masked):")
        _print_findings(fh)
    print(f"\n{'PACKAGE OK' if res['ok'] else 'PACKAGE FAILED'} in {res['secs']} s: {res['zip']}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
