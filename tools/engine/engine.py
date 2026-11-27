"""Engine sources: fetch, patch, build and check Zakuro + 3dsrecomp at the pinned commits.

    python tools/engine/engine.py fetch                 clone/check engine/<repo> at the pins
    python tools/engine/engine.py apply [--force]       put patches/zakuro/NNNN-*.patch on Zakuro
    python tools/engine/engine.py build [TARGET ...]    cargo build (zakuro, 3dsrecomp,
                                                        3dsrecomp-verify; default: all three)
    python tools/engine/engine.py port [--rom ROM]      the standalone program: 3dsrecomp port
                                                        on your ROM + our patched Zakuro ->
                                                        play/game/Fire Emblem Fates.exe
    python tools/engine/engine.py port --stage-only DIR the same build, but the exe, its
                                                        build-record.json, game-path.txt and
                                                        the --help text go to DIR; play/game
                                                        is not touched (the release command's
                                                        staging step, round 68; below-normal
                                                        priority through subprocess flags)
    python tools/engine/engine.py status                what is cloned, patched and built
    python tools/engine/engine.py selftest              apply + port helpers on throwaway data

Pins and URLs: config/upstream.json. Sources: engine/zakuro, engine/3dsrecomp,
engine/fe-awakening-recomp (gitignored; reference only). Cargo output:
engine/target/<target> (outside the checkouts, so they stay clean). Build record:
engine/build-record.json.

`port` (docs/ENGINE.md section 8) writes game-derived files only: the generated C and the
Cargo project in build/port/fef/, the program in play/game/ (both gitignored; never share
them). It reads, never writes: the ROM, %APPDATA%\\3dsrecomp\\<TITLE ID>.hints (3dsrecomp
reads the hints Zakuro wrote) and %LOCALAPPDATA%\\zakuro\\tools (to find Zig).

Per-game constants (title id, names, folders, the default ROM) come from config/game.json
through tools/gamecfg.py; nothing here names a game except through it.

Rules (docs/ENGINE.md):
  * Zakuro (MIT) = the pin + our patch series, as commits on the local branch named in
    config/upstream.json ('fe14'). `apply`
    is idempotent: when the commits on top of the pin already match the series (by
    `git patch-id --verbatim`, whitespace counts) it does nothing; otherwise it resets the
    branch to the pin and
    re-applies every patch with `git am`. It refuses to throw away uncommitted edits
    unless --force.
  * 3dsrecomp has no licence file: it is built unmodified, at its pin, and never copied
    into tracked files. `fetch`/`build` refuse a 3dsrecomp checkout that is not exactly the pin
    with a clean tree.
  * fe-awakening-recomp (MIT) is reference only; nothing builds it.
  * Builds use the toolchain named in config/upstream.json through RUSTUP_TOOLCHAIN, which
    overrides the repos' rust-toolchain.toml (that file only adds rustfmt/clippy, which the
    build does not need) so rustup downloads nothing. `cargo --locked` keeps every crate
    at the version upstream's Cargo.lock names.

Python 3.11+ standard library only. Nothing here writes to %APPDATA% or %LOCALAPPDATA%.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from gamecfg import GAME  # noqa: E402  (config/game.json: every per-game constant)
import paths  # noqa: E402  (F-048: roms/ first, then the old root place for one release)

UPSTREAM = REPO / "config" / "upstream.json"
ENGINE = Path(os.environ.get(GAME.env("ENGINE_DIR")) or (REPO / "engine"))
TARGETS_DIR = ENGINE / "target"
RECORD = ENGINE / "build-record.json"

# identity for the commits `git am` makes on the local branch (never pushed)
GIT_IDENTITY = ["-c", f"user.name={GAME.key} engine.py", "-c", "user.email=engine@localhost"]
GIT_BASE = ["git", "-c", "core.autocrlf=false", "-c", "advice.detachedHead=false"]

# what `build` can build: repo, cargo arguments, executable produced
BUILDS: dict[str, dict] = {
    "zakuro": {
        "repo": "zakuro",
        "args": ["build", "--release", "--locked", "-p", "zakuro"],
        "exe": "release/zakuro.exe",
    },
    "3dsrecomp": {
        "repo": "3dsrecomp",
        "args": ["build", "--release", "--locked"],
        "exe": "release/3dsrecomp.exe",
    },
    "3dsrecomp-verify": {
        "repo": "3dsrecomp",
        "args": ["build", "--release", "--locked", "--features", "verify"],
        "exe": "release/3dsrecomp.exe",
    },
}


# what `port` makes (docs/ENGINE.md section 8). Everything it writes is game-derived and
# lives in gitignored folders: the Cargo project in build/, the program in play/.
TITLE_ID = GAME.title_id_int                    # 0x0004000000179800 for Fates SE USA
TITLE_HEX = f"{TITLE_ID:016X}"
GAME_NAME = GAME.game                           # "Fire Emblem Fates"
EDITION = GAME.edition                          # "Special Edition (USA)"
PROGRAM_NAME = GAME.port.program_name           # exe file name = window title (patch 0005)
PACKAGE = GAME.port.package                     # Cargo's name for it (no spaces allowed)
PORT_DIR = Path(os.environ.get(GAME.env("PORT_DIR")) or (REPO / GAME.port.port_dir))
GAME_DIR = Path(os.environ.get(GAME.env("GAME_DIR")) or (REPO / "play" / "game"))
PORT_OVERRIDES = REPO / "build" / "readable" / "port" / "overrides"
PLAY_CONFIG = REPO / "play" / "config.json"
DEFAULT_ROM = str(paths.roms_dir(REPO) / GAME.default_rom)   # shown in help only; tools/paths.py searches
# 3dsrecomp's bundled hints are keyed by title id + FNV-1a of the code; an update changes it
HINTS_SECTION = f"= {TITLE_HEX} {GAME.code_fnv1a}"
MSYS2_AR = Path(r"C:\msys64\ucrt64\bin\ar.exe")
# variables that must not reach cargo: crates with C parts would build them with the
# compiler meant for the generated code instead of MSVC's cl.exe
C_TOOL_VARS = ("CC", "CXX", "AR", "CFLAGS", "CXXFLAGS", "ARFLAGS")
PROFILE_MARK = "# added by tools/engine/engine.py port"
# port --stage-only: the 3dsrecomp port and cargo run at below-normal priority (the class is
# inherited by every compiler they start); never 'start /belownormal' (it pops dialogs from Git Bash)
BELOW_NORMAL = 0x00004000 if os.name == "nt" else 0


class EngineError(Exception):
    pass


# ----------------------------------------------------------------------------- helpers

def load_upstream() -> dict:
    return json.loads(UPSTREAM.read_text(encoding="utf-8"))


def git(repo: Path, *args: str, check: bool = True, input: bytes | None = None,
        identity: bool = False) -> subprocess.CompletedProcess:
    cmd = list(GIT_BASE) + (GIT_IDENTITY if identity else []) + ["-C", str(repo), *args]
    proc = subprocess.run(cmd, input=input, capture_output=True)
    if check and proc.returncode != 0:
        raise EngineError(f"git {' '.join(args)} failed in {repo}:\n"
                          + proc.stderr.decode(errors="replace").strip())
    return proc


def out(proc: subprocess.CompletedProcess) -> str:
    return proc.stdout.decode(errors="replace").strip()


def head(repo: Path) -> str:
    return out(git(repo, "rev-parse", "HEAD"))


def has_commit(repo: Path, sha: str) -> bool:
    return git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0


def dirty(repo: Path) -> list[str]:
    """Uncommitted changes, untracked files included (ignored files are not)."""
    return [line for line in out(git(repo, "status", "--porcelain")).splitlines() if line]


def patch_id(diff: bytes) -> str | None:
    # --verbatim (git 2.39+): whitespace counts, so a whitespace-only edit to a patch file
    # is seen as a change and re-applied (--stable would call it "unchanged").
    proc = subprocess.run(["git", "patch-id", "--verbatim"], input=diff, capture_output=True)
    text = proc.stdout.decode(errors="replace").split()
    return text[0] if text else None


def series(patch_dir: Path) -> list[Path]:
    """The patch series: NNNN-*.patch, in name order."""
    if not patch_dir.is_dir():
        return []
    return sorted(p for p in patch_dir.glob("*.patch")
                  if len(p.name) > 5 and p.name[:4].isdigit() and p.name[4] == "-")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------------------- fetch

def clone_at(dest: Path, url: str, sha: str) -> None:
    """A fresh checkout of url at sha in dest: only that commit is fetched (depth 1)."""
    dest.mkdir(parents=True)
    git(dest, "init", "-q")
    git(dest, "config", "core.autocrlf", "false")
    git(dest, "remote", "add", "origin", url)
    if git(dest, "fetch", "-q", "--depth", "1", "origin", sha, check=False).returncode != 0:
        print(f"  shallow fetch by commit refused, fetching all of {url}")
        git(dest, "fetch", "-q", "origin")
    if not has_commit(dest, sha):
        raise EngineError(f"{url} has no commit {sha}")


def fetch_repo(name: str, spec: dict) -> None:
    dest = ENGINE / name
    sha = spec["commit"]
    if not dest.exists():
        print(f"{name}: cloning {spec['url']} at {sha[:7]}")
        clone_at(dest, spec["url"], sha)
        if spec.get("branch"):
            git(dest, "checkout", "-q", "-B", spec["branch"], sha)
        else:
            git(dest, "checkout", "-q", "--detach", sha)
    else:
        url = out(git(dest, "remote", "get-url", "origin", check=False))
        if url.rstrip("/") != spec["url"].rstrip("/"):
            raise EngineError(f"{dest} points at {url!r}, not {spec['url']!r}")
        git(dest, "config", "core.autocrlf", "false")
        if not has_commit(dest, sha):
            print(f"{name}: fetching the pin {sha[:7]}")
            git(dest, "fetch", "-q", "--depth", "1", "origin", sha)
    check_repo(name, spec, fix=True)


def check_repo(name: str, spec: dict, fix: bool = False) -> None:
    """Refuse a checkout that is not at its pin (Zakuro: at the pin or patched on top)."""
    dest = ENGINE / name
    sha = spec["commit"]
    if not dest.exists():
        raise EngineError(f"{dest} is missing: run `engine.py fetch`")
    cur = head(dest)
    if spec.get("patches"):
        if git(dest, "merge-base", "--is-ancestor", sha, "HEAD", check=False).returncode != 0:
            raise EngineError(f"{name}: HEAD {cur[:7]} is not built on the pin {sha[:7]}")
        print(f"{name}: on the pin {sha[:7]} (+{len(commits_on_pin(dest, sha))} commits)")
        return
    if cur != sha:
        if fix and not dirty(dest):
            git(dest, "checkout", "-q", "--detach", sha)
            print(f"{name}: moved HEAD {cur[:7]} -> pin {sha[:7]}")
        else:
            raise EngineError(f"{name}: HEAD {cur[:7]} is not the pin {sha[:7]}")
    changes = dirty(dest)
    if changes:
        raise EngineError(f"{name}: the checkout has changes (it must stay unmodified):\n  "
                          + "\n  ".join(changes[:10]))
    print(f"{name}: at the pin {sha[:7]}, clean")


def cmd_fetch(args) -> int:
    up = load_upstream()
    ENGINE.mkdir(exist_ok=True)
    for name, spec in up["repos"].items():
        fetch_repo(name, spec)
    return 0


# ------------------------------------------------------------------------------- apply

def commits_on_pin(repo: Path, pin: str) -> list[str]:
    text = out(git(repo, "rev-list", "--reverse", "--first-parent", f"{pin}..HEAD"))
    return text.split() if text else []


def applied_ids(repo: Path, pin: str) -> list[str | None]:
    return [patch_id(git(repo, "show", "--format=", c).stdout) for c in commits_on_pin(repo, pin)]


def series_ids(patches: list[Path]) -> list[str | None]:
    return [patch_id(p.read_bytes()) for p in patches]


def apply_series(repo: Path, pin: str, branch: str, patches: list[Path],
                 force: bool = False) -> str:
    """Make `branch` = pin + patches. Returns 'unchanged' or 'applied N'."""
    want = series_ids(patches)
    bad = [p.name for p, i in zip(patches, want) if i is None]
    if bad:
        raise EngineError(f"not a patch (no diff found): {', '.join(bad)}")
    on_pin = git(repo, "merge-base", "--is-ancestor", pin, "HEAD", check=False).returncode == 0
    changes = dirty(repo)
    if on_pin and not changes and applied_ids(repo, pin) == want:
        cur_branch = out(git(repo, "rev-parse", "--abbrev-ref", "HEAD"))
        if cur_branch != branch:
            git(repo, "checkout", "-q", "-B", branch, "HEAD")
        return "unchanged"
    if changes and not force:
        raise EngineError(f"{repo} has uncommitted changes; commit them as a patch "
                          "(see patches/zakuro/README.md) or rerun with --force to drop them:\n  "
                          + "\n  ".join(changes[:10]))
    if (repo / ".git" / "rebase-apply").exists():
        git(repo, "am", "--quit", check=False, identity=True)
    git(repo, "checkout", "-q", "-f", "-B", branch, pin)
    git(repo, "clean", "-q", "-fd")
    for p in patches:
        proc = git(repo, "am", "-q", "--3way", "--keep-cr", "--committer-date-is-author-date",
                   str(p.resolve()), check=False, identity=True)
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout).decode(errors="replace").strip()
            # --quit drops the am session without moving HEAD; the checkout resets
            git(repo, "am", "--quit", check=False, identity=True)
            git(repo, "checkout", "-q", "-f", "-B", branch, pin)
            raise EngineError(f"{p.name} does not apply on {pin[:7]} (branch reset to the pin):\n{msg}")
    if applied_ids(repo, pin) != want:
        raise EngineError("after git am the commits do not match the series (patch-id check)")
    return f"applied {len(patches)}"


def cmd_apply(args) -> int:
    spec = load_upstream()["repos"]["zakuro"]
    repo = ENGINE / "zakuro"
    if not repo.exists():
        raise EngineError(f"{repo} is missing: run `engine.py fetch`")
    patches = series(REPO / spec["patches"])
    result = apply_series(repo, spec["commit"], spec["branch"], patches, force=args.force)
    print(f"zakuro: {result}; branch {spec['branch']} = {spec['commit'][:7]} + "
          f"{len(patches)} patch(es) from {spec['patches']}/")
    for p in patches:
        print(f"  {p.name}")
    return 0


def zakuro_patch_state(spec: dict) -> tuple[bool, int, int]:
    repo = ENGINE / "zakuro"
    patches = series(REPO / spec["patches"])
    want = series_ids(patches)
    have = applied_ids(repo, spec["commit"])
    return (have == want and not dirty(repo)), len(have), len(want)


# ------------------------------------------------------------------------------- build

def toolchain_info(toolchain: str) -> str:
    env = dict(os.environ, RUSTUP_TOOLCHAIN=toolchain)
    parts = []
    for tool in ("rustc", "cargo"):
        proc = subprocess.run([tool, "-V"], capture_output=True, text=True, env=env)
        parts.append(proc.stdout.strip() or proc.stderr.strip())
    return "; ".join(parts)


def load_record() -> dict:
    if RECORD.exists():
        return json.loads(RECORD.read_text(encoding="utf-8"))
    return {}


def cmd_build(args) -> int:
    up = load_upstream()
    toolchain = up["toolchain"]
    names = args.targets or list(BUILDS)
    unknown = [n for n in names if n not in BUILDS]
    if unknown:
        raise EngineError(f"unknown target(s) {unknown}; choose from {list(BUILDS)}")
    if shutil.which("cargo") is None:
        raise EngineError("cargo is not on PATH (rustup installs it in %USERPROFILE%\\.cargo\\bin)")
    # every source must be exactly what the pins and the series say
    for repo_name in sorted({BUILDS[n]["repo"] for n in names}):
        spec = up["repos"][repo_name]
        check_repo(repo_name, spec)
        if spec.get("patches"):
            ok, have, want = zakuro_patch_state(spec)
            if not ok:
                raise EngineError(f"zakuro carries {have} commit(s) on the pin but the series has "
                                  f"{want} (or the tree is dirty): run `engine.py apply` first")
    tools = toolchain_info(toolchain)
    print(f"toolchain: {tools}")
    record = load_record()
    env = dict(os.environ, RUSTUP_TOOLCHAIN=toolchain)
    for name in names:
        b = BUILDS[name]
        src = ENGINE / b["repo"]
        target_dir = TARGETS_DIR / name
        cmd = ["cargo", *b["args"], "--target-dir", str(target_dir)]
        print(f"\n== {name}: (cd {src.relative_to(REPO)}) RUSTUP_TOOLCHAIN={toolchain} "
              f"{' '.join(cmd)}", flush=True)
        start = time.monotonic()
        proc = subprocess.run(cmd, cwd=src, env=env)
        took = time.monotonic() - start
        if proc.returncode != 0:
            raise EngineError(f"{name}: cargo failed (exit {proc.returncode}) after {took:.0f} s")
        exe = target_dir / b["exe"]
        if not exe.exists():
            raise EngineError(f"{name}: cargo succeeded but {exe} is missing")
        spec = up["repos"][b["repo"]]
        entry = {
            "finished": _dt.datetime.now().isoformat(timespec="seconds"),
            "seconds": round(took, 1),
            "command": f"RUSTUP_TOOLCHAIN={toolchain} {' '.join(cmd)}",
            "cwd": str(src.relative_to(REPO)),
            "toolchain": tools,
            "pin": spec["commit"],
            "head": head(src),
            "patches": [p.name for p in series(REPO / spec["patches"])] if spec.get("patches") else [],
            "exe": str(exe.relative_to(REPO)),
            "size": exe.stat().st_size,
            "sha256": sha256(exe),
        }
        record[name] = entry
        RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"== {name}: built {entry['exe']} ({entry['size']:,} bytes) in {took:.0f} s")
    return 0


# -------------------------------------------------------------------------------- port

def rom_path(given: str | None) -> Path:
    """--rom, else "rom" in play/config.json (PLAY.bat's) when that file is there, else "rom" in
    play/launcher.json (the file PLAY's Getting ready window accepted outside roms/, round 77) when that file is
    there, else the .cci in roms/ (then the old repo-root place for one release): tools/paths.py."""
    try:
        return paths.resolve_rom(given, repo=REPO, check="header", use_env=False)
    except paths.PathError as e:
        raise EngineError(str(e)) from None


def check_rom(path: Path) -> dict:
    """The cartridge image config/game.json names: NCSD header with the title id, and the
    game partition's NCCH with the same program id and product code (read only, 1 KiB).
    Returns {"size": bytes}."""
    try:
        with path.open("rb") as f:
            header = f.read(0x200)
            ncch = b""
            if len(header) == 0x200 and header[0x100:0x104] == b"NCSD":
                f.seek(int.from_bytes(header[0x120:0x124], "little") * 0x200)
                ncch = f.read(0x200)
        size = path.stat().st_size
    except OSError as e:
        raise EngineError(f"cannot read the ROM {path} ({e}); pass --rom") from None
    if len(header) < 0x200 or header[0x100:0x104] != b"NCSD":
        raise EngineError(f"{path} is not a .cci/.3ds cartridge image")
    media = int.from_bytes(header[0x108:0x110], "little")
    if media != TITLE_ID:
        raise EngineError(f"{path} is title {media:016X}, not {GAME_NAME} {EDITION} ({TITLE_HEX})")
    if len(ncch) < 0x200 or ncch[0x100:0x104] != b"NCCH":
        raise EngineError(f"{path}: the game partition has no NCCH header (cut short or damaged?)")
    program = int.from_bytes(ncch[0x118:0x120], "little")
    product = ncch[0x150:0x160].split(b"\0", 1)[0].decode("ascii", "replace")
    if program != TITLE_ID or product != GAME.product_code:
        raise EngineError(f"{path}: program {program:016X} / product {product!r}, expected "
                          f"{TITLE_HEX} / {GAME.product_code}")
    return {"size": size}


def rom_digest(path: Path, use_cache: bool = True, state_path: Path | None = None) -> tuple[str, str]:
    """(sha256, where from). PLAY.bat's cached check (play/state.json, read only) is used
    when it names this very file (path, size, mtime); otherwise the file is hashed (2 GiB,
    about 10 s). An update or a patched dump changes the code, and with it the code hash
    3dsrecomp's bundled hints are keyed by, so only the known clean dump is ported."""
    st = path.stat()
    if use_cache:
        try:
            state = state_path or (PLAY_CONFIG.parent / "state.json")
            cached = json.loads(state.read_text(encoding="utf-8")).get("rom_check")
        except (OSError, ValueError, AttributeError):
            cached = None
        same_file = isinstance(cached, dict) and cached.get("path") == str(path.resolve()) \
            and cached.get("size") == st.st_size and cached.get("mtime_ns") == st.st_mtime_ns
        if same_file and cached.get("sha256"):
            return cached["sha256"], "PLAY's cached check"
    return sha256(path), "hashed now"


def bundled_hints(recomp_src: Path) -> tuple[str, int] | None:
    """3dsrecomp's own hints for this game: (file, number of addresses) for the section
    headed HINTS_SECTION ("= <title id> <code FNV-1a>") in any hints*.txt of the checkout,
    or None. Read only; nothing from 3dsrecomp is copied anywhere."""
    if not recomp_src.is_dir():
        return None
    for path in sorted(recomp_src.rglob("hints*.txt")):
        if ".git" in path.parts:
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if line.strip().upper() == HINTS_SECTION.upper():
                count = 0
                for nxt in lines[i + 1:]:
                    t = nxt.split("#", 1)[0].strip()
                    if t.startswith("="):
                        break
                    count += len(t.split()) if t else 0
                return str(path.relative_to(recomp_src)), count
    return None


def find_zig() -> Path | None:
    """The Zig Zakuro downloaded (%LOCALAPPDATA%\\zakuro\\tools\\zig-*\\zig.exe), newest."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    found = sorted((Path(base) / "zakuro" / "tools").glob("zig-*/zig.exe"))
    return found[-1] if found else None


def pick_cc(given: str | None) -> str:
    """CC for 3dsrecomp's generated C. It has to make MSVC-style objects, because the
    program is linked by Rust's MSVC toolchain (3dsrecomp docs/port.md): Zig's clang with
    an MSVC target, or LLVM clang. MinGW gcc makes the wrong kind of object."""
    if given:
        return given
    if os.environ.get("CC", "").strip():
        return os.environ["CC"].strip()
    zig = find_zig()
    if zig is not None:
        if " " in str(zig):
            raise EngineError(f"Zig is at a path with a space ({zig}); 3dsrecomp splits CC at "
                              "spaces. Pass --cc \"<zig without spaces> cc -target x86_64-windows-msvc\"")
        return f"{zig} cc -target x86_64-windows-msvc"
    if shutil.which("clang"):
        return "clang"
    raise EngineError("no C compiler for MSVC-style objects: start Zakuro's Recompile once (it "
                      "downloads Zig), install LLVM clang, or pass --cc")


def pick_ar(given: str | None) -> str:
    """AR: one program (3dsrecomp runs `AR rcs lib objects`). llvm-ar, else MSYS2's ar,
    whose archives of COFF objects MSVC's linker reads."""
    for value in (given, os.environ.get("AR", "").strip() or None):
        if value:
            return value
    for name in ("llvm-ar",):
        if shutil.which(name):
            return shutil.which(name)
    if MSYS2_AR.is_file():
        return str(MSYS2_AR)
    if shutil.which("ar"):
        return shutil.which("ar")
    raise EngineError("no archiver: install MSYS2 binutils or LLVM, or pass --ar")


def release_profile(zakuro_manifest: Path) -> str:
    """Zakuro's own [profile.release], so the program is optimised like zakuro.exe."""
    import tomllib
    profile = tomllib.loads(zakuro_manifest.read_text(encoding="utf-8")).get("profile", {}).get("release", {})
    lines = [PROFILE_MARK + ": Zakuro's [profile.release] (engine/zakuro/Cargo.toml)", "[profile.release]"]
    for key, value in profile.items():
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, (int, float)):
            text = str(value)
        elif isinstance(value, str):
            text = json.dumps(value)
        else:
            continue  # tables (per-package settings) are not needed for one program
        lines.append(f"{key} = {text}")
    return "\n".join(lines) + "\n"


def fix_manifest(text: str, zakuro_crate: Path, profile: str) -> str:
    """The generated Cargo.toml, pointed at our patched Zakuro and given its profile.

    `3dsrecomp port --zakuro DIR` writes the path inside a TOML "..." string, where the
    backslashes of a Windows path are escapes, so it is not used: port writes its GitHub
    dependency and this swaps that line for a '...' literal string with forward slashes."""
    path = zakuro_crate.resolve().as_posix()
    if "'" in path:
        raise EngineError(f"the Zakuro path has a quote in it: {path}")
    line = f"zakuro = {{ path = '{path}' }}"
    new, count = re.subn(r"(?m)^zakuro\s*=.*$", lambda _m: line, text)
    if count != 1:
        raise EngineError(f"the generated Cargo.toml has {count} zakuro dependency lines, expected 1")
    if PROFILE_MARK not in new:
        new = new.rstrip("\n") + "\n\n" + profile
    return new


def lock_versions(lock_text: str) -> dict[str, set[str]]:
    import tomllib
    versions: dict[str, set[str]] = {}
    for pkg in tomllib.loads(lock_text).get("package", []):
        versions.setdefault(pkg["name"], set()).add(pkg["version"])
    return versions


def lock_drift(reference: str, built: str) -> list[str]:
    """Crates whose versions in the program's Cargo.lock differ from Zakuro's."""
    ref, got = lock_versions(reference), lock_versions(built)
    return [f"{name}: zakuro {sorted(ref[name])}, program {sorted(got[name])}"
            for name in sorted(set(ref) & set(got)) if ref[name] != got[name]]


def usage_from_source(cli_rs: str) -> str:
    """The text `zakuro --help` prints: the USAGE string in crates/zakuro/src/cli.rs."""
    m = re.search(r'const USAGE: &str = "\\\n(.*?)";', cli_rs, re.S)
    if not m:
        raise EngineError("USAGE not found in cli.rs")
    return m.group(1).replace("\\\\", "\\").replace('\\"', '"')


def tree_digest(folder: Path) -> str | None:
    if not folder.is_dir():
        return None
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(folder).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def dir_size(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()) if folder.is_dir() else 0


def hints_file() -> Path | None:
    base = os.environ.get("APPDATA")
    return Path(base) / "3dsrecomp" / f"{TITLE_HEX}.hints" if base else None


def port_inputs(recomp_head: str, rom: Path, overrides: str | None, cc: str, ar: str) -> dict:
    """What the generated code depends on; the same inputs = no need to recompile."""
    st = rom.stat()
    hints = hints_file()
    hst = hints.stat() if hints and hints.is_file() else None
    return {"3dsrecomp": recomp_head, "rom": str(rom.resolve()), "rom_size": st.st_size,
            "rom_mtime_ns": st.st_mtime_ns, "overrides": overrides, "cc": cc, "ar": ar,
            "hints": [hst.st_size, hst.st_mtime_ns] if hst else None}


def project_problems(project: Path) -> list[str]:
    """What is missing or unexpected in the project 3dsrecomp port wrote."""
    problems = []
    for rel in ("Cargo.toml", "build.rs", "src/main.rs", "code/librecomp.a"):
        if not (project / rel).is_file():
            problems.append(f"{rel} missing")
    main_rs = project / "src" / "main.rs"
    if main_rs.is_file():
        text = main_rs.read_text(encoding="utf-8", errors="replace")
        if "zakuro::run(Some(" not in text:
            problems.append("src/main.rs does not hand linked code to zakuro::run")
        if f"0x{TITLE_HEX}" not in text:
            problems.append(f"src/main.rs is not for title {TITLE_HEX}")
    return problems


def stage_dir_problem(folder: Path) -> str | None:
    """Why `port --stage-only folder` is refused (None = fine): it must not be the play folder or
    inside it (that is what install is for), nor the port project or the engine sources."""
    target = Path(os.path.abspath(folder))
    for name, top in (("the game folder", GAME_DIR), ("the play folder", REPO / "play"),
                      ("the port project", PORT_DIR), ("the engine folder", ENGINE)):
        top = Path(os.path.abspath(top))
        if target == top or top in target.parents:
            return f"{target} is {name} or inside it ({top}); stage into a folder under build/ instead"
    if target.exists() and not target.is_dir():
        return f"{target} exists and is not a folder"
    return None


def install_exe(built: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".new")
    shutil.copy2(built, tmp)
    try:
        os.replace(tmp, dest)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        raise EngineError(f"{dest} is in use: close the game, then run port again") from None


GAME_README = """\
{name}, made on this PC by tools/engine/engine.py port.

  {name}.exe   the game's code (recompiled from YOUR copy) linked with our patched
               Zakuro. It is game-derived: personal use only, never share or upload it.
  game-path.txt   the ROM it starts when nothing else is given (PLAY.bat passes it anyway).
  build-record.json  how and when it was built.

It still reads everything but the code from your ROM, and keeps its data where Zakuro
does: saves in %APPDATA%\\zakuro\\user, mods in %APPDATA%\\zakuro\\mods, cheats in
%APPDATA%\\zakuro\\cheats, settings in %APPDATA%\\zakuro\\settings.toml. Esc opens the menu.
Start it with PLAY.bat (backs the save up first) or by double-clicking the exe.
Rebuild: python tools/engine/engine.py port. Delete this folder to go back to Zakuro.
"""


def cmd_port(args) -> int:
    stage_only = getattr(args, "stage_only", None)
    if stage_only:  # refused before anything is read or built
        why = stage_dir_problem(Path(stage_only))
        if why:
            raise EngineError(f"--stage-only: {why}")
    up = load_upstream()
    toolchain = up["toolchain"]
    zspec, rspec = up["repos"]["zakuro"], up["repos"]["3dsrecomp"]
    check_repo("zakuro", zspec)
    ok, have, want = zakuro_patch_state(zspec)
    if not ok:
        raise EngineError(f"zakuro carries {have} commit(s) on the pin but the series has {want} "
                          "(or the tree is dirty): run `engine.py apply` first")
    check_repo("3dsrecomp", rspec)
    rom = rom_path(args.rom)
    check_rom(rom)
    digest, digest_from = rom_digest(rom)
    if digest != GAME.rom_sha256 and not args.any_dump:
        raise EngineError(
            f"{rom} is {GAME_NAME} but not the known clean dump:\n  SHA-256 {digest} ({digest_from})\n"
            f"  expected {GAME.rom_sha256} (config/game.json)\n"
            "A patched, trimmed or updated copy has other code: 3dsrecomp's bundled hints and the\n"
            "project's addresses would not fit it. Use the clean dump (or --any-dump to port it anyway).")
    hints = bundled_hints(ENGINE / "3dsrecomp")
    cc, ar = pick_cc(args.cc), pick_ar(args.ar)
    recomp = TARGETS_DIR / "3dsrecomp" / BUILDS["3dsrecomp"]["exe"]
    rec = load_record().get("3dsrecomp") or {}
    recomp_head = head(ENGINE / "3dsrecomp")
    build_recomp = not recomp.is_file() or rec.get("head") != recomp_head
    # opt-in for Fates: the readable layer (src/readable, staged by tools/readable/stage.py,
    # which refuses any override that is not a Fates function start) has only a few
    # unverified overrides so far; nothing is compiled in unless asked (docs/ENGINE.md section 9)
    overrides_dir = PORT_OVERRIDES if args.readable else None
    zakuro_crate = ENGINE / "zakuro" / "crates" / "zakuro"
    built = PORT_DIR / "target" / "release" / f"{PACKAGE}.exe"
    out_dir = Path(os.path.abspath(stage_only)) if stage_only else GAME_DIR
    flags = BELOW_NORMAL if stage_only else 0   # 0 = exactly the old subprocess call
    dest = out_dir / f"{PROGRAM_NAME}.exe"
    user_hints = hints_file()
    print(f"game:       {GAME_NAME} {EDITION}, title {TITLE_HEX}, {GAME.product_code}")
    print(f"ROM:        {rom}")
    print(f"ROM SHA-256 {digest} ({digest_from}): "
          + ("the known clean dump" if digest == GAME.rom_sha256 else "NOT the known dump (--any-dump)"))
    print(f"hints:      3dsrecomp's own: " + (f"section '{HINTS_SECTION}' in {hints[0]} ({hints[1]} entries)"
                                               if hints else f"no section '{HINTS_SECTION}' (it still runs; "
                                               "fewer functions are known up front)"))
    print(f"            Zakuro's: {user_hints}" + (" (present)" if user_hints and user_hints.is_file() else
                                                    " (none yet; Zakuro writes it while the game runs)"))
    print(f"C compiler: CC={cc}")
    print(f"archiver:   AR={ar}")
    print(f"3dsrecomp:  {recomp.relative_to(REPO)}" + (" (will be built first)" if build_recomp else ""))
    print(f"Zakuro:     {zakuro_crate.relative_to(REPO)} (pin {zspec['commit'][:7]} + {want} patches)")
    print(f"readable:   " + ("left out (default for this game; --readable stages them)" if overrides_dir is None else
                             f"compiled in, OFF (default mode original; FE_READABLE=shadow|readable "
                             f"turns them on), staged in {PORT_OVERRIDES.relative_to(REPO)}"))
    print(f"project:    {PORT_DIR}")
    print(f"program:    {dest}" + ("  (staged only: play/game is not touched)" if stage_only else ""))
    if args.dry_run:
        print("[dry run] nothing built")
        return 0

    timings: dict[str, float] = {}
    if build_recomp:
        start = time.monotonic()
        cmd_build(argparse.Namespace(targets=["3dsrecomp"]))
        timings["3dsrecomp_build"] = round(time.monotonic() - start, 1)
    staged_digest = None
    if overrides_dir is not None:
        stage = REPO / "tools" / "readable" / "stage.py"
        proc = subprocess.run([sys.executable, str(stage), "--mode", "original", "--out", str(overrides_dir)])
        if proc.returncode != 0:
            raise EngineError("staging the readable overrides failed (see above); leave out --readable")
        staged_digest = tree_digest(overrides_dir)

    inputs = port_inputs(recomp_head, rom, staged_digest, cc, ar)
    inputs_file = PORT_DIR / "port-inputs.json"
    try:
        same = json.loads(inputs_file.read_text(encoding="utf-8")) == inputs
    except (OSError, ValueError):
        same = False
    if args.regen or not same or project_problems(PORT_DIR):
        cmd = [str(recomp), "port", str(rom), str(PORT_DIR), "--name", PACKAGE]
        if overrides_dir is not None:
            cmd += ["--overrides", str(overrides_dir)]
        env = dict(os.environ, CC=cc, AR=ar)
        print(f"\n== 3dsrecomp port (CC and AR set as above): {subprocess.list2cmdline(cmd)}", flush=True)
        inputs_file.unlink(missing_ok=True)
        start = time.monotonic()
        proc = subprocess.run(cmd, env=env, cwd=REPO, creationflags=flags)
        timings["recompile"] = round(time.monotonic() - start, 1)
        if proc.returncode != 0:
            raise EngineError(f"3dsrecomp port failed (exit {proc.returncode}) after {timings['recompile']:.0f} s")
        problems = project_problems(PORT_DIR)
        if problems:
            raise EngineError("3dsrecomp port finished but the project is not as expected: " + "; ".join(problems))
        inputs_file.write_text(json.dumps(inputs, indent=2) + "\n", encoding="utf-8")
    else:
        print("\n== generated code is up to date (same 3dsrecomp, ROM, hints, overrides, CC, AR); "
              "--regen recompiles anyway")

    manifest = PORT_DIR / "Cargo.toml"
    manifest.write_text(fix_manifest(manifest.read_text(encoding="utf-8"), zakuro_crate,
                                     release_profile(ENGINE / "zakuro" / "Cargo.toml")), encoding="utf-8")
    # start from Zakuro's own Cargo.lock, so every crate is the version zakuro.exe uses
    zakuro_lock = (ENGINE / "zakuro" / "Cargo.lock").read_text(encoding="utf-8")
    (PORT_DIR / "Cargo.lock").write_text(zakuro_lock, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k.upper() not in C_TOOL_VARS}
    env["RUSTUP_TOOLCHAIN"] = toolchain
    cargo = ["cargo", "build", "--release"]
    print(f"\n== (cd {PORT_DIR}) RUSTUP_TOOLCHAIN={toolchain} {' '.join(cargo)}", flush=True)
    start = time.monotonic()
    proc = subprocess.run(cargo, cwd=PORT_DIR, env=env, creationflags=flags)
    timings["cargo_build"] = round(time.monotonic() - start, 1)
    if proc.returncode != 0:
        raise EngineError(f"cargo failed (exit {proc.returncode}) after {timings['cargo_build']:.0f} s")
    if not built.is_file():
        raise EngineError(f"cargo succeeded but {built} is missing")
    drift = lock_drift(zakuro_lock, (PORT_DIR / "Cargo.lock").read_text(encoding="utf-8"))

    install_exe(built, dest)
    (out_dir / "game-path.txt").write_text(str(rom.resolve()) + "\n", encoding="utf-8")
    (out_dir / "README.txt").write_text(GAME_README.format(name=PROGRAM_NAME), encoding="utf-8")

    # the only run: --help, which prints and exits inside cli::parse, before any settings,
    # log or data folder is touched (lib.rs run_with)
    help_run = subprocess.run([str(dest), "--help"], capture_output=True, timeout=120)
    expected = usage_from_source((zakuro_crate / "src" / "cli.rs").read_text(encoding="utf-8"))
    got = help_run.stdout.decode("utf-8", "replace").replace("\r\n", "\n")
    help_ok = help_run.returncode == 0 and got == expected
    if stage_only:  # install compares the installed exe's --help with this text
        (out_dir / "help.txt").write_text(got, encoding="utf-8", newline="\n")

    entry = {
        "finished": _dt.datetime.now().isoformat(timespec="seconds"),
        "seconds": timings,
        "program": str(dest.relative_to(REPO)) if dest.is_relative_to(REPO) else str(dest),
        "size": dest.stat().st_size,
        "sha256": sha256(dest),
        "librecomp_size": (PORT_DIR / "code" / "librecomp.a").stat().st_size,
        "project_size": dir_size(PORT_DIR),
        "rom": str(rom.resolve()),
        "zakuro_head": head(ENGINE / "zakuro"),
        "zakuro_patches": [p.name for p in series(REPO / zspec["patches"])],
        "3dsrecomp_head": recomp_head,
        "readable": None if overrides_dir is None else {"mode": "original", "digest": staged_digest},
        "cc": cc,
        "ar": ar,
        "toolchain": toolchain_info(toolchain),
        "lock_drift": drift,
        "help_matches_source": help_ok,
    }
    if stage_only:
        # the record describes the exe as it will sit once installed (play/game/...), plus where it was staged
        installed = GAME_DIR / f"{PROGRAM_NAME}.exe"
        entry["program"] = str(installed.relative_to(REPO)) if installed.is_relative_to(REPO) else str(installed)
        entry["staged_in"] = str(dest.relative_to(REPO)) if dest.is_relative_to(REPO) else str(dest)
    (out_dir / "build-record.json").write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    print(f"\n== built {dest} ({entry['size']:,} bytes)"
          + (": STAGED ONLY, nothing installed (tools/release/install.py installs it)" if stage_only else ""))
    for k, v in timings.items():
        print(f"   {k}: {v:.0f} s")
    print(f"   project folder: {entry['project_size'] / 2**30:.1f} GiB in {PORT_DIR}")
    print("   Cargo.lock: same crate versions as Zakuro's" if not drift else
          "   Cargo.lock differs from Zakuro's: " + "; ".join(drift))
    print("   --help: same text as Zakuro's cli.rs" if help_ok else
          f"   --help: DIFFERENT (exit {help_run.returncode}); see build-record.json")
    return 0 if help_ok else 1


def port_status() -> list[str]:
    dest = GAME_DIR / f"{PROGRAM_NAME}.exe"
    if not dest.is_file():
        return [f"port                   not built (python tools/engine/engine.py port)"]
    line = f"port                   {dest} ({dest.stat().st_size:,} bytes)"
    try:
        rec = json.loads((GAME_DIR / "build-record.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [line + ", no build record"]
    line += f", built {rec.get('finished')}"
    zak = ENGINE / "zakuro"
    if zak.exists() and rec.get("zakuro_head") != head(zak):
        line += ", ZAKURO PATCHES CHANGED since (run port again)"
    if rec.get("sha256") != sha256(dest):
        line += ", exe differs from the record"
    return [line]


# ------------------------------------------------------------------------------ status

def cmd_status(args) -> int:
    up = load_upstream()
    record = load_record()
    problems = 0
    print(f"engine dir: {ENGINE}")
    for name, spec in up["repos"].items():
        dest = ENGINE / name
        if not dest.exists():
            print(f"{name:20} MISSING (run fetch)")
            problems += 1
            continue
        cur = head(dest)
        changes = dirty(dest)
        if spec.get("patches"):
            on_pin = git(dest, "merge-base", "--is-ancestor", spec["commit"], "HEAD",
                         check=False).returncode == 0
            ok, have, want = zakuro_patch_state(spec) if on_pin else (False, 0, 0)
            state = (f"pin {spec['commit'][:7]} + {have} commit(s), series {want}: "
                     + ("OK" if ok else "NEEDS apply") if on_pin else
                     f"HEAD {cur[:7]} NOT on the pin {spec['commit'][:7]}")
            problems += 0 if ok else 1
        else:
            ok = cur == spec["commit"] and not changes
            state = f"HEAD {cur[:7]} " + ("= pin, clean" if ok else
                                          f"!= pin {spec['commit'][:7]} or dirty")
            problems += 0 if ok else 1
        if changes:
            state += f"; {len(changes)} uncommitted change(s)"
        print(f"{name:20} {state}")
    for line in port_status():
        print(line)
    for name, b in BUILDS.items():
        exe = TARGETS_DIR / name / b["exe"]
        rec = record.get(name)
        if not exe.exists():
            print(f"build {name:16} not built")
            continue
        line = f"build {name:16} {exe.relative_to(REPO)} ({exe.stat().st_size:,} bytes)"
        if rec:
            src = ENGINE / b["repo"]
            stale = src.exists() and rec.get("head") != head(src)
            fresh = rec.get("sha256") == sha256(exe)
            line += (f", built {rec['finished']} in {rec['seconds']:.0f} s"
                     + (", SOURCE CHANGED since (rebuild)" if stale else "")
                     + ("" if fresh else ", exe differs from the record"))
        print(line)
    return 1 if problems else 0


# ---------------------------------------------------------------------------- selftest

def port_selftest(root: Path) -> list[tuple[str, bool]]:
    """The port helpers on made-up inputs (our own sample text, no generated files)."""
    import tomllib
    checks: list[tuple[str, bool]] = []
    crate = root / "My Zakuro (x)" / "crates" / "zakuro"
    crate.mkdir(parents=True)
    sample = ('# sample\n[package]\nname = "demo"\nversion = "0.1.0"\n\n[dependencies]\n'
              'zakuro = { git = "https://example.invalid/zakuro" }\n\n[workspace]\n')
    (root / "Z.toml").write_text('[profile.release]\nopt-level = 3\nlto = "thin"\npanic = "unwind"\n'
                                 'debug = 1\n[profile.release.package.x]\nopt-level = 1\n', encoding="utf-8")
    profile = release_profile(root / "Z.toml")
    fixed = fix_manifest(sample, crate, profile)
    parsed = tomllib.loads(fixed)
    checks.append(("port: manifest points at the local Zakuro (Windows path, spaces, parens)",
                   parsed["dependencies"]["zakuro"] == {"path": crate.resolve().as_posix()}))
    checks.append(("port: Zakuro's release profile copied, tables skipped",
                   parsed["profile"]["release"] == {"opt-level": 3, "lto": "thin", "panic": "unwind", "debug": 1}))
    checks.append(("port: fixing twice changes nothing", fix_manifest(fixed, crate, profile) == fixed))
    try:
        fix_manifest(sample.replace("zakuro = {", "other = {"), crate, profile)
        refused = False
    except EngineError:
        refused = True
    checks.append(("port: a manifest without the zakuro line is refused", refused))
    lock_a = ('version = 4\n[[package]]\nname = "a"\nversion = "1.0.0"\n'
              '[[package]]\nname = "b"\nversion = "2.0.0"\n')
    lock_b = lock_a + '[[package]]\nname = "demo"\nversion = "0.1.0"\n'
    checks.append(("port: lock drift none for the same versions", lock_drift(lock_a, lock_b) == []))
    checks.append(("port: lock drift names a changed crate",
                   lock_drift(lock_a, lock_b.replace('"2.0.0"', '"2.1.0"')) == ["b: zakuro ['2.0.0'], program ['2.1.0']"]))
    cli = 'x\nconst USAGE: &str = "\\\nline one\n  path %APPDATA%\\\\zakuro\n";\n'
    checks.append(("port: --help text read from cli.rs",
                   usage_from_source(cli) == "line one\n  path %APPDATA%\\zakuro\n"))
    project = root / "proj"
    (project / "src").mkdir(parents=True)
    (project / "code").mkdir()
    for rel in ("Cargo.toml", "build.rs", "code/librecomp.a"):
        (project / rel).write_text("x", encoding="utf-8")
    (project / "src" / "main.rs").write_text(f"fn main() {{ let id = 0x{TITLE_HEX}; zakuro::run(Some(id)); }}",
                                             encoding="utf-8")
    checks.append(("port: a complete project has no problems", project_problems(project) == []))
    (project / "src" / "main.rs").write_text("fn main() { zakuro::run(None); }", encoding="utf-8")
    checks.append(("port: a project for another title or without linked code is flagged",
                   len(project_problems(project)) == 2))
    rom = root / "rom.cci"

    def fake_rom(media: int = TITLE_ID, program: int = TITLE_ID, product: str = GAME.product_code) -> None:
        """a synthetic header (identifiers only): NCSD, then partition 0's NCCH at 0x200"""
        ncsd, ncch = bytearray(0x200), bytearray(0x200)
        ncsd[0x100:0x104] = b"NCSD"
        ncsd[0x108:0x110] = media.to_bytes(8, "little")
        ncsd[0x120:0x124] = (1).to_bytes(4, "little")
        ncch[0x100:0x104] = b"NCCH"
        ncch[0x118:0x120] = program.to_bytes(8, "little")
        ncch[0x150:0x150 + len(product)] = product.encode()
        rom.write_bytes(bytes(ncsd + ncch))

    def rom_accepted() -> bool:
        try:
            check_rom(rom)
            return True
        except EngineError:
            return False
    fake_rom()
    rom_ok = rom_accepted()
    fake_rom(media=TITLE_ID + 0x100)
    other_ok = rom_accepted()
    fake_rom(program=0x00040000000A0500)
    program_ok = rom_accepted()
    fake_rom(product="CTR-P-AFEE")
    product_ok = rom_accepted()
    rom.write_bytes(rom.read_bytes()[:0x200])      # NCSD only, cut short
    short_ok = rom_accepted()
    checks.append((f"port: ROM check takes {TITLE_HEX} / {GAME.product_code} and refuses another "
                   "media id, program id, product code or a cut-short file",
                   rom_ok and not (other_ok or program_ok or product_ok or short_ok)))
    # the ROM hash: PLAY's cache is used only for the very same file
    fake_rom()
    st = rom.stat()
    real = sha256(rom)
    state = root / "state.json"
    with_cache = {"rom_check": {"path": str(rom.resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns,
                                "sha256": "c" * 64}}
    state.write_text(json.dumps(with_cache), encoding="utf-8")
    cached = rom_digest(rom, state_path=state)
    with_cache["rom_check"]["size"] += 1
    state.write_text(json.dumps(with_cache), encoding="utf-8")
    stale = rom_digest(rom, state_path=state)
    checks.append(("port: ROM hash comes from PLAY's cache only for the same file",
                   cached == ("c" * 64, "PLAY's cached check") and stale == (real, "hashed now")))
    checks.append(("port: ROM hash without the cache is the file's SHA-256",
                   rom_digest(rom, use_cache=False) == (real, "hashed now")))
    # 3dsrecomp's bundled hints: the section headed "= <title> <code hash>", up to the next one
    src = root / "recomp"
    (src / "data").mkdir(parents=True)
    (src / "data" / "hints.txt").write_text(
        "# made-up sample\n= 0004000000000001 0000000000000000\n00100000 00100010\n"
        f"{HINTS_SECTION.lower()}\n00100000 00100004   # two\n00100008\n\n= 0004000000000002 1111\n00100000\n",
        encoding="utf-8")
    checks.append(("port: bundled hints section found and counted (case-insensitive, stops at the next)",
                   bundled_hints(src) == (str(Path("data") / "hints.txt"), 3)))
    (src / "data" / "hints.txt").write_text("= 0004000000000001 0\n00100000\n", encoding="utf-8")
    checks.append(("port: no section for this game = None", bundled_hints(src) is None))
    return checks


def cmd_selftest(args) -> int:
    """apply_series on a throwaway repo: fresh apply, no-op rerun, changed series, dirty tree."""
    checks: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix=f"{GAME.key}-engine-") as tmp:
        root = Path(tmp)
        BRANCH = load_upstream()["repos"]["zakuro"].get("branch") or GAME.key
        repo, pdir = root / "repo", root / "patches"
        repo.mkdir()
        pdir.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "core.autocrlf", "false")
        (repo / "a.txt").write_bytes(b"one\ntwo\nthree\n")
        git(repo, "add", "a.txt")
        git(repo, "commit", "-q", "-m", "pin", identity=True)
        pin = head(repo)
        # two patches made the way the README says: commit, then format-patch
        (repo / "a.txt").write_bytes(b"one\nTWO\nthree\n")
        git(repo, "commit", "-q", "-am", "first change", identity=True)
        (repo / "b.txt").write_bytes(b"new file\n")
        git(repo, "add", "b.txt")
        git(repo, "commit", "-q", "-m", "second change", identity=True)
        git(repo, "format-patch", "-q", "--zero-commit", "--no-signature", "-o", str(pdir), pin)
        git(repo, "checkout", "-q", "-B", BRANCH, pin)
        patches = series(pdir)
        checks.append(("format-patch names follow NNNN-*.patch", len(patches) == 2))
        checks.append(("fresh apply", apply_series(repo, pin, BRANCH, patches) == "applied 2"))
        checks.append(("files patched", (repo / "a.txt").read_bytes() == b"one\nTWO\nthree\n"
                       and (repo / "b.txt").exists()))
        first_head = head(repo)
        checks.append(("rerun is a no-op", apply_series(repo, pin, BRANCH, patches) == "unchanged"
                       and head(repo) == first_head))
        # drop the second patch: the branch is rebuilt with only the first
        patches[1].unlink()
        patches = series(pdir)
        checks.append(("shorter series re-applies", apply_series(repo, pin, BRANCH, patches) == "applied 1"
                       and not (repo / "b.txt").exists()))
        # a whitespace-only edit to a patch file is a change (patch-id --verbatim)
        original = patches[0].read_bytes()
        patches[0].write_bytes(original.replace(b"\n+TWO\n", b"\n+  TWO\n"))
        checks.append(("whitespace-only patch edit re-applies",
                       apply_series(repo, pin, BRANCH, patches) == "applied 1"
                       and (repo / "a.txt").read_bytes() == b"one\n  TWO\nthree\n"))
        patches[0].write_bytes(original)
        apply_series(repo, pin, BRANCH, patches)
        # an uncommitted edit is never thrown away without --force
        (repo / "a.txt").write_bytes(b"edited by hand\n")
        try:
            apply_series(repo, pin, BRANCH, patches)
            refused = False
        except EngineError:
            refused = True
        checks.append(("dirty tree refused", refused and (repo / "a.txt").read_bytes() == b"edited by hand\n"))
        checks.append(("--force resets", apply_series(repo, pin, BRANCH, patches, force=True) == "applied 1"
                       and (repo / "a.txt").read_bytes() == b"one\nTWO\nthree\n"))
        # a patch that no longer applies leaves the branch at the pin
        (pdir / "0002-broken.patch").write_bytes(
            "From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001\n"
            "From: x <x@x>\nDate: Mon, 1 Jan 2024 00:00:00 +0000\nSubject: [PATCH] broken\n\n---\n"
            " a.txt | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)\n\n"
            "diff --git a/a.txt b/a.txt\nindex 0000000..1111111 100644\n--- a/a.txt\n+++ b/a.txt\n"
            "@@ -1,3 +1,3 @@\n one\n-nothing like this\n+x\n three\n".encode())
        try:
            apply_series(repo, pin, BRANCH, series(pdir))
            failed = False
        except EngineError:
            failed = True
        checks.append(("bad patch fails, branch back at pin", failed and head(repo) == pin
                       and not (repo / ".git" / "rebase-apply").exists()))
        checks.append(("empty series = the pin", apply_series(repo, pin, BRANCH, []) in ("unchanged", "applied 0")
                       and head(repo) == pin))
        checks += port_selftest(root)
    passed = sum(ok for _, ok in checks)
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print(f"engine selftest: {passed}/{len(checks)}")
    return 0 if passed == len(checks) else 1


# -------------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="clone or check engine/<repo> at the pins")
    p = sub.add_parser("apply", help="apply patches/zakuro/ onto engine/zakuro (idempotent)")
    p.add_argument("--force", action="store_true", help="drop uncommitted edits in engine/zakuro")
    p = sub.add_parser("build", help="cargo build the engine targets")
    p.add_argument("targets", nargs="*", help=f"any of {', '.join(BUILDS)} (default: all)")
    p = sub.add_parser("port", help="the standalone program: 3dsrecomp port + patched Zakuro -> play/game/")
    p.add_argument("--rom", help=f"your {GAME_NAME} .cci (default: play/config.json's, else the one in roms/)")
    readable = p.add_mutually_exclusive_group()
    readable.add_argument("--readable", action="store_true",
                          help="stage and compile in the readable overrides (off for this game until stage.py is ported)")
    readable.add_argument("--no-readable", action="store_true", help="leave the readable overrides out (the default)")
    p.add_argument("--any-dump", action="store_true",
                   help="port a ROM whose SHA-256 is not config/game.json's (an update or patched copy)")
    p.add_argument("--regen", action="store_true", help="recompile the game's code even if nothing changed")
    p.add_argument("--cc", help="C compiler for the generated code (default: Zakuro's Zig, MSVC target)")
    p.add_argument("--ar", help="archiver (default: llvm-ar, else MSYS2 ar)")
    p.add_argument("--dry-run", action="store_true", help="check everything and print the plan, build nothing")
    p.add_argument("--stage-only", metavar="DIR",
                   help="build to DIR (exe, build-record.json, game-path.txt, help.txt); play/game untouched; "
                        "below-normal priority")
    sub.add_parser("status", help="what is cloned, patched and built")
    sub.add_parser("selftest", help="test the apply logic on a throwaway repo")
    args = ap.parse_args(argv)
    try:
        return {"fetch": cmd_fetch, "apply": cmd_apply, "build": cmd_build, "port": cmd_port,
                "status": cmd_status, "selftest": cmd_selftest}[args.cmd](args)
    except EngineError as e:
        print(f"STOP: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
