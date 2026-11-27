#!/usr/bin/env python3
"""Engine half of the one-command release (round 68, release part B, goal 3; build/RELEASE_PLAN_2026-11-23.md).

What it does, in the release's order (tools/release/release.py calls it; nothing here runs by itself):

    plan(engine)            what would be built, why, and the counted seconds of each step (worked out from the build
                            records and `build.py --check-fresh`, before anything starts). An exe whose sha equals the
                            current play/game build-record and whose patches/Zakuro/3dsrecomp are unchanged is REUSED,
                            not rebuilt (it is left out of the list). Without --engine: [] (no build ever runs).
    stage_build(tag, dir)   only with --engine: builds what plan() lists into `dir` (never into play/):
                            engine.py apply + engine.py port --stage-only (exe, build-record.json, game-path.txt,
                            help.txt), build.py --server --stage-to (boot-server.exe + server_build.json, in its own
                            cargo target), build.py --out <dir>-work/harness (capture library + harness_build.json),
                            then the Zakuro cargo test rows of check_all. Writes dir/STAGED.json (every file's sha).
    backup(tag)             the pre-<tag> set -> build/backup/<name>.<date>-pre-<tag>, each copy sha-checked, plus
                            build/backup/pre-<tag>.json (the record undo reads). Never overwrites a backup.
    install(staged, rec)    refuses while the game / boot-server / Zakuro runs; checks the backup matches what is
                            installed now; copies every staged file next to its target, then renames them in; then the
                            checks (installed sha = staged sha, the installed exe's --help = the staged help.txt,
                            PLAY.bat --check, verify_installed). ANY failure puts the backup back automatically and
                            checks the shas again.
    verify_installed()      installed shas against play/game/build-record.json, server_build.json,
                            harness_build.json and engine/build-record.json (what is really installed; never a
                            last-release record).
    undo(tag)               puts the pre-<tag> set back and checks the shas. A release that installed nothing has
                            no backup record: 'nothing was installed'. Backups are never deleted; a file that did
                            not exist before the release is renamed aside, never deleted.

The backup set (the same names the rounds used by hand, build/backup/*.<date>-pre-<tag>):
    Fire Emblem Fates.exe      <- play/game/Fire Emblem Fates.exe
    build-record.json          <- play/game/build-record.json
    game-path.txt              <- play/game/game-path.txt
    engine-build-record.json   <- engine/build-record.json
    boot-server.exe            <- engine/target/zakuro-server/release/boot-server.exe
    server_build.json          <- engine/target/zakuro-server/server_build.json
    0004000000179800.dll       <- build/harness/lib/0004000000179800.dll   (the capture library: backed up too)
    harness_build.json         <- build/harness/lib/harness_build.json

Every function takes root= (the repo) and, where it runs programs, runner= (cmd, cwd, timeout) -> (rc, stdout,
stderr) and running= (names) -> [running names], so tests/test_install.py runs it in temp folders with fakes.
Programs run with no window and below-normal priority through subprocess flags (never 'start /belownormal').
Records hold repo-relative paths only. Python standard library only.

    python tools/release/install.py plan [--engine]     print what a release would build (writes nothing)
    python tools/release/install.py verify              installed files against their build records
    python tools/release/install.py selftest            tests/test_install.py (temp folders, fakes; builds nothing)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
try:
    from gamecfg import GAME  # noqa: E402  (config/game.json)
    PROGRAM = GAME.port.program_name
    TITLE_HEX = f"{GAME.title_id_int:016X}"
    PORT_DIR_REL = GAME.port.port_dir
except Exception:  # noqa: BLE001  (a broken config must not hide the release's own messages)
    PROGRAM, TITLE_HEX, PORT_DIR_REL = "Fire Emblem Fates", "0004000000179800", "build/port/fef"

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BELOW_NORMAL = 0x00004000 if os.name == "nt" else 0
EXE = f"{PROGRAM}.exe"
LIB = f"{TITLE_HEX}.dll"

# (key, backup/staged file name, installed path relative to the repo)
SET: list[tuple[str, str, str]] = [
    ("exe", EXE, f"play/game/{EXE}"),
    ("build-record", "build-record.json", "play/game/build-record.json"),
    ("game-path", "game-path.txt", "play/game/game-path.txt"),
    ("engine-build-record", "engine-build-record.json", "engine/build-record.json"),
    ("boot-server", "boot-server.exe", "engine/target/zakuro-server/release/boot-server.exe"),
    ("server-record", "server_build.json", "engine/target/zakuro-server/server_build.json"),
    ("capture-lib", LIB, f"build/harness/lib/{LIB}"),
    ("capture-record", "harness_build.json", "build/harness/lib/harness_build.json"),
]
NAME = {k: n for k, n, _r in SET}
INSTALLED = {k: r for k, _n, r in SET}
# what stage_build can produce and install() puts in (engine/build-record.json is backed up, never staged)
INSTALLABLE = ["exe", "build-record", "game-path", "boot-server", "server-record", "capture-lib", "capture-record"]
# a program never goes in without the record that describes it (and the other way round)
PAIRS = [("exe", "build-record"), ("boot-server", "server-record"), ("capture-lib", "capture-record")]
WATCH = (EXE, "boot-server.exe", "boot.exe", "zakuro.exe")
SERVER_SRC = ("tools/harness/patches/zakuro-server/Cargo.toml", "tools/harness/patches/zakuro-server/src/main.rs")
# the Zakuro cargo test rows of tools/check_all.py (tests/test_install.py keeps this list equal to check_all's)
CARGO_TEST_ROWS = ["rando-ingame-core", "rando-ingame-page", "game-picker-page", "engine-seal-person-name",
                   "engine-seal-person-order", "engine-nuzlocke-core", "engine-pagebot-hook"]
# counted seconds (F-027), each from a measurement (build/r67/design/map_build_install.json)
COUNTED = {
    "exe_cargo": 75,          # engine.py port, cargo only: 53-112 s over 16 backup build-records, usually 60-75
    "exe_recompile": 177,     # + the C recompile when 3dsrecomp or its inputs changed: 148-177 s
    "boot_server": 70,        # build.py --server: 66 s cargo, 'EXIT after 70 s' (r62 server.log)
    "boot_server_first": 300,  # first build in its own staging target folder: NOT measured yet (all crates compile)
    "capture_lib": 385,       # build.py: 385.4 s (harness_build.json)
    "apply": 5,               # engine.py apply (git am of the series)
    "cargo_row_unknown": 60,  # a cargo test row with no time in build/check_all_times.json
}


class InstallError(Exception):
    """a plain one-line reason; nothing half-done is left behind by the function that raises it"""


# ------------------------------------------------------------------------------------------------ small helpers
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


def rel(root: Path, p: Path) -> str:
    try:
        return Path(os.path.abspath(p)).relative_to(Path(os.path.abspath(root))).as_posix()
    except ValueError:
        return str(p)


def under(p: Path, top: Path) -> bool:
    p, top = Path(os.path.abspath(p)), Path(os.path.abspath(top))
    return p == top or top in p.parents


def copy_checked(src: Path, dst: Path, want: str | None = None) -> str:
    """copy src to dst through dst.tmp + rename; the copy's sha256 must equal src's (or want)"""
    want = want or sha256(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copy2(src, tmp)
    got = sha256(tmp)
    if got != want:
        tmp.unlink(missing_ok=True)
        raise InstallError(f"copy of {src.name} has sha256 {got[:12]}..., wanted {want[:12]}...")
    os.replace(tmp, dst)
    return got


def put_in_place(new: Path, dest: Path, stamp: str) -> str | None:
    """rename new over dest. A DLL a robot still holds cannot be overwritten but can be renamed: it goes aside to
    <dll>.old-<stamp> first (build.py swap_library's rule). Returns the aside name, if any."""
    try:
        os.replace(new, dest)
        return None
    except PermissionError:
        if dest.suffix.lower() != ".dll" or not dest.exists():
            raise
        aside = dest.with_name(f"{dest.name}.old-{stamp}")
        os.replace(dest, aside)
        os.replace(new, dest)
        return aside.name


def default_runner(cmd: list[str], cwd: str | Path | None = None, timeout: float = 3600) -> tuple[int, str, str]:
    """no window, below-normal priority (the class is inherited by every compiler a build starts)"""
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=NO_WINDOW | BELOW_NORMAL)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:.0f} s"
    except OSError as e:
        return 127, "", str(e)


def default_running(names=WATCH) -> list[str]:
    """which of names run now (Windows tasklist; elsewhere nothing is checked)"""
    if os.name != "nt":
        return []
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=60,
                             creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    have = {line.split('","')[0].strip('"').lower() for line in out.splitlines() if line.startswith('"')}
    return [n for n in names if n.lower() in have]


def stop_round(root: Path) -> None:
    if (root / "build" / "STOP_ROUND").exists():
        raise InstallError("build/STOP_ROUND exists: stopped before the next build step")


def git_head(root: Path, repo: Path, runner) -> str | None:
    if not (repo / ".git").exists():
        return None
    rc, out, _err = runner(["git", "-C", str(repo), "rev-parse", "HEAD"], root, 60)
    return out.strip() if rc == 0 and out.strip() else None


def patch_series(root: Path) -> list[str]:
    d = root / "patches" / "zakuro"
    return sorted(p.name for p in d.glob("[0-9][0-9][0-9][0-9]-*.patch")) if d.is_dir() else []


def check_all_seconds(root: Path) -> dict:
    data = read_json(root / "build" / "check_all_times.json") or {}
    return data.get("seconds") or {}


# ------------------------------------------------------------------------------------------------ plan
def freshness(*, root: str | Path = ROOT, runner=None) -> list[dict]:
    """every engine-side item with its state: action 'build' (stale), 'reuse' (fresh), 'test' (the cargo rows,
    which run only when something is built). Keys: build, why, counted_s, action."""
    root, runner = Path(root), runner or default_runner
    patches = patch_series(root)
    zakuro_head = git_head(root, root / "engine" / "zakuro", runner)
    recomp_head = git_head(root, root / "engine" / "3dsrecomp", runner)
    items = []

    # the game exe
    exe, rec = root / INSTALLED["exe"], read_json(root / INSTALLED["build-record"])
    why, recompile = [], False
    if not exe.is_file():
        why.append("no installed exe")
    elif rec is None:
        why.append("no play/game/build-record.json")
    else:
        if rec.get("sha256") != sha256(exe):
            why.append("the installed exe differs from its build-record")
        rp = rec.get("zakuro_patches")
        if isinstance(rp, list) and sorted(rp) != patches:
            why.append(f"patches/zakuro changed since the exe was built ({len(rp)} -> {len(patches)} patches)")
        if zakuro_head and rec.get("zakuro_head") and rec["zakuro_head"] != zakuro_head:
            why.append("engine/zakuro moved since the exe was built")
        if recomp_head and rec.get("3dsrecomp_head") and rec["3dsrecomp_head"] != recomp_head:
            why.append("3dsrecomp changed since the exe was built")
            recompile = True
    if why:
        inputs = read_json(root / PORT_DIR_REL / "port-inputs.json")
        if inputs is None or (recomp_head and inputs.get("3dsrecomp") != recomp_head):
            recompile = True
        cargo = COUNTED["exe_cargo"]
        if rec and isinstance(rec.get("seconds"), dict) and rec["seconds"].get("cargo_build"):
            cargo = max(cargo, int(round(rec["seconds"]["cargo_build"])))
        items.append({"build": "exe", "action": "build", "why": "; ".join(why) + (" (C recompile too)" if recompile else ""),
                      "counted_s": COUNTED["apply"] + cargo + (COUNTED["exe_recompile"] if recompile else 0)})
    else:
        items.append({"build": "exe", "action": "reuse", "counted_s": 0,
                      "why": f"reused: sha {rec['sha256'][:8]} equals play/game/build-record.json "
                             f"(built {rec.get('finished')}), same patches and engine heads"})

    # boot-server (links engine/zakuro by path: a Zakuro change makes it stale too)
    srv, srec = root / INSTALLED["boot-server"], read_json(root / INSTALLED["server-record"])
    why = []
    if not srv.is_file():
        why.append("no boot-server.exe")
    elif srec is None:
        why.append("no server_build.json")
    else:
        if srec.get("sha256") != sha256(srv):
            why.append("boot-server.exe differs from server_build.json")
        now = {Path(s).relative_to("tools/harness/patches/zakuro-server").as_posix(): sha256(root / s)
               for s in SERVER_SRC if (root / s).is_file()}
        if now and srec.get("source_sha256") != now:
            why.append("its tracked source changed")
        if "zakuro_head" not in srec:
            why.append("server_build.json predates zakuro_head (round 68), so a Zakuro change cannot be ruled out")
        elif zakuro_head and srec["zakuro_head"] != zakuro_head:
            why.append("engine/zakuro moved since boot-server was built")
        sp = srec.get("zakuro_patches")
        if isinstance(sp, list) and sorted(sp) != patches:
            why.append("patches/zakuro changed since boot-server was built")
    if why:
        first = not (root / "engine" / "target" / "zakuro-server-stage").is_dir()
        items.append({"build": "boot-server", "action": "build", "why": "; ".join(why),
                      "counted_s": COUNTED["boot_server_first" if first else "boot_server"]})
    else:
        items.append({"build": "boot-server", "action": "reuse", "counted_s": 0,
                      "why": f"reused: sha {srec['sha256'][:8]} equals server_build.json, same source and Zakuro"})

    # the capture library: build.py --check-fresh decides
    rc, out, err = runner([sys.executable, str(root / "tools" / "harness" / "build.py"), "--check-fresh"], root, 600)
    line = ((out or "") + (err or "")).strip().splitlines()
    line = line[-1] if line else f"exit {rc}"
    man = read_json(root / INSTALLED["capture-record"]) or {}
    if rc == 0:
        items.append({"build": "capture-library", "action": "reuse", "counted_s": 0, "why": f"reused: {line}"})
    else:
        items.append({"build": "capture-library", "action": "build", "why": line,
                      "counted_s": int(round(man.get("seconds") or COUNTED["capture_lib"]))})

    # the Zakuro cargo test rows (run only when something is built)
    times = check_all_seconds(root)
    secs = sum(int(round(times.get(r) or COUNTED["cargo_row_unknown"])) for r in CARGO_TEST_ROWS)
    known = sum(1 for r in CARGO_TEST_ROWS if times.get(r))
    items.append({"build": "zakuro-cargo-tests", "action": "test", "counted_s": secs,
                  "why": f"the {len(CARGO_TEST_ROWS)} Zakuro cargo test rows of check_all, serial "
                         f"({known} timed in build/check_all_times.json, the rest counted "
                         f"{COUNTED['cargo_row_unknown']} s each)"})
    return items


def plan(engine: bool, *, root: str | Path = ROOT, runner=None) -> list[dict]:
    """[{build, why, counted_s, action}] of what WILL run. Without engine: [] (no build ever runs). With engine:
    each stale item, plus the cargo test rows when anything is built; reused items are left out (nothing built
    means [] : the release then smokes and verifies the installed files)."""
    if not engine:
        return []
    items = freshness(root=root, runner=runner)
    builds = [i for i in items if i["action"] == "build"]
    if not builds:
        return []
    return builds + [i for i in items if i["action"] == "test"]


def stale(*, root: str | Path = ROOT, runner=None) -> list[dict]:
    """the stale items alone (for a release without --engine: a stale exe or library is a plain stop there)"""
    return [i for i in freshness(root=root, runner=runner) if i["action"] == "build"]


# ------------------------------------------------------------------------------------------------ stage
def stage_build(tag: str, out_dir: str | Path, *, root: str | Path = ROOT, runner=None, items=None,
                say=print) -> Path:
    """builds plan(True)'s items into out_dir (the staged bin folder; logs and the library build go to
    <out_dir>-work). Returns out_dir. Raises InstallError at the first failure (play/ is never touched)."""
    root, runner = Path(root), runner or default_runner
    bin_dir = Path(os.path.abspath(out_dir))
    if not under(bin_dir, root / "build") or under(bin_dir, root / "play"):
        raise InstallError(f"the staging folder must be under build/ (never play/): {bin_dir}")
    if bin_dir.exists() and any(bin_dir.iterdir()):
        raise InstallError(f"the staging folder {rel(root, bin_dir)} is not empty (one build per folder)")
    items = plan(True, root=root, runner=runner) if items is None else items
    names = {i["build"] for i in items if i.get("action", "build") in ("build", "test")}
    work = bin_dir.with_name(bin_dir.name + "-work")
    bin_dir.mkdir(parents=True, exist_ok=True)
    (work / "logs").mkdir(parents=True, exist_ok=True)
    py = sys.executable
    took: dict[str, float] = {}

    def step(name: str, cmd: list, timeout: float, fix: str) -> None:
        stop_round(root)
        say(f"  building {name} ...")
        t0 = time.time()
        rc, out, err = runner(cmd, root, timeout)
        took[name] = round(time.time() - t0, 1)
        with open(work / "logs" / f"{name}.log", "w", encoding="utf-8", newline="\n") as fh:
            fh.write(f"$ {subprocess.list2cmdline([str(c) for c in cmd])}\n{out}\n{err}\nEXIT {rc} after {took[name]} s\n")
        if rc != 0:
            raise InstallError(f"{name} failed (exit {rc}); log {rel(root, work / 'logs' / (name + '.log'))}. {fix}")

    if "exe" in names:
        step("engine-apply", [py, root / "tools" / "engine" / "engine.py", "apply"], 600,
             "engine/zakuro has hand edits or a patch does not apply: fix the patch, then run again.")
        step("exe", [py, root / "tools" / "engine" / "engine.py", "port", "--stage-only", bin_dir], 3600,
             "Nothing was installed.")
        for n in (EXE, "build-record.json", "game-path.txt"):
            if not (bin_dir / n).is_file():
                raise InstallError(f"engine.py port --stage-only left no {n} in {rel(root, bin_dir)}")
        rec = read_json(bin_dir / "build-record.json") or {}
        if rec.get("sha256") != sha256(bin_dir / EXE):
            raise InstallError("the staged exe is not the one its staged build-record describes")
    if "boot-server" in names:
        step("boot-server", [py, root / "tools" / "harness" / "build.py", "--server", "--stage-to", bin_dir], 3600,
             "Nothing was installed.")
        srec = read_json(bin_dir / "server_build.json") or {}
        if not (bin_dir / "boot-server.exe").is_file() or srec.get("sha256") != sha256(bin_dir / "boot-server.exe"):
            raise InstallError("the staged boot-server.exe is missing or not the one its server_build.json describes")
    if "capture-library" in names:
        step("capture-library", [py, root / "tools" / "harness" / "build.py", "--out", work / "harness"], 3600,
             "Nothing was installed.")
        lib_dir = work / "harness" / "lib"
        man = read_json(lib_dir / "harness_build.json") or {}
        if not (lib_dir / LIB).is_file() or man.get("library_sha256") != sha256(lib_dir / LIB):
            raise InstallError("the staged capture library is missing or not the one its manifest describes")
        copy_checked(lib_dir / LIB, bin_dir / LIB)
        copy_checked(lib_dir / "harness_build.json", bin_dir / "harness_build.json")
    if "zakuro-cargo-tests" in names:
        step("zakuro-cargo-tests", [py, root / "tools" / "check_all.py", "--only", ",".join(CARGO_TEST_ROWS),
                                    "--jobs", "1", "--priority", "below_normal",
                                    "--log-dir", work / "check_all"], 7200,
             "A Zakuro test failed: fix it (the log names the row), commit, and run again. Nothing was installed.")
    files = {p.name: sha256(p) for p in sorted(bin_dir.iterdir()) if p.is_file() and p.name != "STAGED.json"}
    if not files:
        raise InstallError("the engine build staged no file (plan listed nothing to build?)")
    write_json(bin_dir / "STAGED.json", {"tag": tag, "made": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": files,
                                         "builds": sorted(names), "seconds": took,
                                         "items": [{k: i.get(k) for k in ("build", "action", "why", "counted_s")}
                                                   for i in items]})
    return bin_dir


# ------------------------------------------------------------------------------------------------ backup
def backup_record_path(root: Path, tag: str) -> Path:
    return root / "build" / "backup" / f"pre-{tag}.json"


def backup(tag: str, *, root: str | Path = ROOT, date: str | None = None) -> dict:
    """copies the pre-<tag> set into build/backup (sha-checked) and writes build/backup/pre-<tag>.json.
    Returns the record (ok, detail, items). Never overwrites a backup: a second call for the same tag with the same
    installed files returns the same record; with other files it refuses."""
    root = Path(root)
    bdir = root / "build" / "backup"
    rec_path = backup_record_path(root, tag)
    old = read_json(rec_path)
    if old is not None:
        same = all(((root / it["installed"]).is_file() and sha256(root / it["installed"]) == it["sha256"])
                   if it.get("present") else not (root / it["installed"]).exists() for it in old.get("items", []))
        if same:
            old.update(ok=True, detail=f"the pre-{tag} backup exists already and matches the installed files")
            return old
        return {"ok": False, "detail": f"a pre-{tag} backup exists already ({rel(root, rec_path)}) for other files; "
                                       "pick another tag (backups are never overwritten)", "items": []}
    date = date or time.strftime("%Y-%m-%d")
    suffix = f".{date}-pre-{tag}"
    items = []
    try:
        for key, name, inst in SET:
            src = root / inst
            if not src.is_file():
                items.append({"key": key, "name": name, "installed": inst, "present": False})
                continue
            want = sha256(src)
            dst = bdir / (name + suffix)
            if dst.exists():
                if sha256(dst) != want:
                    raise InstallError(f"{rel(root, dst)} exists with other bytes; backups are never overwritten")
            else:
                copy_checked(src, dst, want)
            items.append({"key": key, "name": name, "installed": inst, "present": True, "backup": rel(root, dst),
                          "sha256": want, "size": src.stat().st_size})
    except (InstallError, OSError) as e:
        return {"ok": False, "detail": f"backup stopped: {e}", "items": items}
    record = {"ok": True, "tag": tag, "date": date, "made": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "detail": f"{sum(1 for i in items if i['present'])} file(s) backed up to build/backup/*{suffix}",
              "items": items}
    write_json(rec_path, record)
    return record


def _backup_items(record: dict) -> dict:
    return {it["key"]: it for it in (record or {}).get("items", [])}


def restore(record: dict, keys, *, root: Path, stamp: str, tag: str) -> list[str]:
    """puts the backed-up files of keys back (a file absent before goes aside, never deleted); returns problems
    after the sha re-check (empty = every file is back as it was)"""
    items = _backup_items(record)
    problems = []
    for key in keys:
        it = items.get(key)
        if it is None:
            problems.append(f"{key}: not in the backup record")
            continue
        dest = root / it["installed"]
        try:
            if it.get("present"):
                if dest.is_file() and sha256(dest) == it["sha256"]:
                    continue
                new = dest.with_name(f"{dest.name}.restore-{stamp}")
                copy_checked(root / it["backup"], new, it["sha256"])
                put_in_place(new, dest, stamp)
            elif dest.exists():
                os.replace(dest, dest.with_name(f"{dest.name}.after-{tag}-{stamp}"))
        except (InstallError, OSError) as e:
            problems.append(f"{it['installed']}: {e}")
    for key in keys:  # the re-check
        it = items.get(key)
        if not it:
            continue
        dest = root / it["installed"]
        if it.get("present"):
            if not dest.is_file() or sha256(dest) != it["sha256"]:
                problems.append(f"{it['installed']}: not the backed-up file after the restore")
        elif dest.exists():
            problems.append(f"{it['installed']}: still there (it did not exist before {tag})")
    return problems


# ------------------------------------------------------------------------------------------------ install
def _check_shas(ctx: dict) -> tuple[bool, str]:
    bad = [k for k in ctx["keys"] if sha256(ctx["root"] / INSTALLED[k]) != ctx["staged_shas"][NAME[k]]]
    return (not bad, "installed = staged" if not bad else "differs from the staged file: " + ", ".join(bad))


def _check_help(ctx: dict) -> tuple[bool, str]:
    if "exe" not in ctx["keys"]:
        return True, "no exe installed"
    rc, out, err = ctx["runner"]([str(ctx["root"] / INSTALLED["exe"]), "--help"], ctx["root"], 120)
    want = ctx["staged"] / "help.txt"
    if rc != 0:
        return False, f"--help exit {rc}: {(err or out).strip()[:120]}"
    if want.is_file() and out.replace("\r\n", "\n") != want.read_text(encoding="utf-8"):
        return False, "--help text differs from the staged build's"
    return True, "--help = the staged build's"


def _check_play(ctx: dict) -> tuple[bool, str]:
    if "exe" not in ctx["keys"]:
        return True, "no exe installed"
    rc, out, _err = ctx["runner"]([sys.executable, str(ctx["root"] / "tools" / "play" / "play.py"), "--check"],
                                  ctx["root"], 300)
    last = (out or "").strip().splitlines()
    return rc == 0, "PLAY.bat --check: " + (last[-1] if last else f"exit {rc}")


def _check_verify(ctx: dict) -> tuple[bool, str]:
    v = verify_installed(root=ctx["root"])
    return v["ok"], v["detail"]


DEFAULT_CHECKS = [("sha", _check_shas), ("help", _check_help), ("play-check", _check_play), ("records", _check_verify)]


def install(staged: str | Path, backup_record: dict, *, root: str | Path = ROOT, runner=None, running=None,
            checks=None, say=print) -> dict:
    """puts the staged files in. Result: ok, detail, installed, checks [{name, ok, detail}], rolled_back,
    rollback_ok. Nothing changes when a pre-check fails; any failure after the first rename rolls back."""
    root, runner = Path(root), runner or default_runner
    running = running or default_running
    staged = Path(os.path.abspath(staged))
    res = {"ok": False, "installed": [], "checks": [], "rolled_back": False, "rollback_ok": None}
    man = read_json(staged / "STAGED.json")
    if man is None:
        res["detail"] = f"no STAGED.json in {rel(root, staged)}: not a staged build"
        return res
    for name, want in man.get("files", {}).items():
        p = staged / name
        if not p.is_file() or sha256(p) != want:
            res["detail"] = f"staged {name} is missing or changed since it was built"
            return res
    keys = [k for k in INSTALLABLE if NAME[k] in man.get("files", {})]
    if not keys:
        res.update(ok=True, detail="nothing staged to install")
        return res
    for a, b in PAIRS:
        if (a in keys) != (b in keys):
            res["detail"] = f"staged {NAME[a] if a in keys else NAME[b]} without {NAME[b] if a in keys else NAME[a]}"
            return res
    busy = running(WATCH)
    if busy:
        res["detail"] = f"{', '.join(busy)} is running: close it, then run the release again (nothing was changed)"
        return res
    if not backup_record or not backup_record.get("ok", True):
        res["detail"] = "no good backup record: nothing was changed"
        return res
    items = _backup_items(backup_record)
    for k in keys:
        it, dest = items.get(k), root / INSTALLED[k]
        if it is None:
            res["detail"] = f"the backup has no entry for {INSTALLED[k]}: nothing was changed"
            return res
        if it.get("present"):
            b = root / it["backup"]
            if not b.is_file() or sha256(b) != it["sha256"]:
                res["detail"] = f"the backup copy {it['backup']} is missing or changed: nothing was changed"
                return res
            if not dest.is_file() or sha256(dest) != it["sha256"]:
                res["detail"] = f"{INSTALLED[k]} changed since the backup was made: back up again (nothing was changed)"
                return res
        elif dest.exists():
            res["detail"] = f"{INSTALLED[k]} appeared after the backup was made: back up again (nothing was changed)"
            return res
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tag = backup_record.get("tag", man.get("tag", "release"))
    news = []
    try:  # 1: every staged file is copied next to its target first (a full disk fails here, before any rename)
        for k in keys:
            dest = root / INSTALLED[k]
            new = dest.with_name(f"{dest.name}.new-{stamp}")
            copy_checked(staged / NAME[k], new, man["files"][NAME[k]])
            news.append((k, new, dest))
    except (InstallError, OSError) as e:
        for _k, new, _d in news:
            new.unlink(missing_ok=True)
        res["detail"] = f"could not copy the staged files next to their targets ({e}); nothing was changed"
        return res
    failure = None
    asides = []
    try:  # 2: rename them in
        for k, new, dest in news:
            aside = put_in_place(new, dest, stamp)
            if aside:
                asides.append(aside)
            res["installed"].append(INSTALLED[k])
    except OSError as e:
        failure = f"could not put {dest.name} in place ({e.__class__.__name__}: {e})"
    if failure is None:  # 3: the checks
        ctx = {"root": root, "staged": staged, "keys": keys, "staged_shas": man["files"], "runner": runner}
        for name, fn in (checks if checks is not None else DEFAULT_CHECKS):
            try:
                ok, detail = fn(ctx)
            except Exception as e:  # noqa: BLE001  (a crashing check is a failed check)
                ok, detail = False, f"{e.__class__.__name__}: {e}"
            res["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
            if not ok:
                failure = f"check {name} failed: {detail}"
                break
    for _k, new, _d in news:
        new.unlink(missing_ok=True)
    res["asides"] = asides
    if failure is None:
        res.update(ok=True, detail=f"installed {len(keys)} file(s); every check passed")
        return res
    problems = restore(backup_record, keys, root=root, stamp=stamp, tag=tag)
    res.update(rolled_back=True, rollback_ok=not problems,
               detail=failure + ("; rolled back, every file is the backed-up one again" if not problems else
                                 "; ROLLBACK INCOMPLETE: " + "; ".join(problems)))
    return res


# ------------------------------------------------------------------------------------------------ verify / undo
def verify_installed(*, root: str | Path = ROOT) -> dict:
    """installed shas against their build records. Result: ok, detail, items [{name, path, ok, detail}];
    ok None = not built here (information, not a failure)."""
    root = Path(root)
    out = []

    def pair(name: str, path_key: str, rec_key: str, field: str, needed: bool) -> None:
        p, r = root / INSTALLED[path_key], read_json(root / INSTALLED[rec_key])
        if not p.is_file() and r is None and not needed:
            out.append({"name": name, "path": INSTALLED[path_key], "ok": None, "detail": "not built here"})
            return
        if not p.is_file():
            out.append({"name": name, "path": INSTALLED[path_key], "ok": False, "detail": "missing"})
            return
        if r is None:
            out.append({"name": name, "path": INSTALLED[path_key], "ok": False,
                        "detail": f"no readable {INSTALLED[rec_key]}"})
            return
        got = sha256(p)
        ok = got == r.get(field)
        out.append({"name": name, "path": INSTALLED[path_key], "ok": ok, "sha256": got,
                    "detail": f"sha {got[:8]} = {INSTALLED[rec_key]}" if ok else
                              f"sha {got[:8]} but {INSTALLED[rec_key]} says {str(r.get(field))[:8]}"})

    pair("game exe", "exe", "build-record", "sha256", True)
    pair("boot-server", "boot-server", "server-record", "sha256", False)
    pair("capture library", "capture-lib", "capture-record", "library_sha256", False)
    erec = read_json(root / INSTALLED["engine-build-record"]) or {}
    for target, r in sorted(erec.items()):
        if not isinstance(r, dict) or not r.get("exe"):
            continue
        p = root / r["exe"].replace("\\", "/")
        if not p.is_file():
            out.append({"name": f"engine {target}", "path": rel(root, p), "ok": None, "detail": "not built here"})
            continue
        got = sha256(p)
        out.append({"name": f"engine {target}", "path": rel(root, p), "ok": got == r.get("sha256"), "sha256": got,
                    "detail": f"sha {got[:8]} " + ("= engine/build-record.json" if got == r.get("sha256") else
                                                   f"but engine/build-record.json says {str(r.get('sha256'))[:8]}")})
    bad = [i for i in out if i["ok"] is False]
    return {"ok": not bad, "items": out,
            "detail": ("; ".join(f"{i['name']}: {i['detail']}" for i in bad) if bad else
                       f"{sum(1 for i in out if i['ok'])} file(s) match their build records")}


def undo(tag: str, *, root: str | Path = ROOT, running=None) -> dict:
    """puts the pre-<tag> set back and checks the shas. No backup record = the release installed nothing."""
    root = Path(root)
    running = running or default_running
    rec = read_json(backup_record_path(root, tag))
    if rec is None:
        return {"ok": True, "nothing": True, "restored": [],
                "detail": f"nothing was installed by {tag} (no build/backup/pre-{tag}.json): nothing to put back"}
    busy = running(WATCH)
    if busy:
        return {"ok": False, "restored": [],
                "detail": f"{', '.join(busy)} is running: close it, then undo again (nothing was changed)"}
    items = _backup_items(rec)
    for it in items.values():
        if it.get("present"):
            b = root / it["backup"]
            if not b.is_file() or sha256(b) != it["sha256"]:
                return {"ok": False, "restored": [],
                        "detail": f"the backup copy {it['backup']} is missing or changed: nothing was changed"}
    changed = [k for k, it in items.items()
               if (it.get("present") and not ((root / it["installed"]).is_file()
                                              and sha256(root / it["installed"]) == it["sha256"]))
               or (not it.get("present") and (root / it["installed"]).exists())]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    problems = restore(rec, list(items), root=root, stamp=stamp, tag=tag)
    result = {"ok": not problems, "restored": [items[k]["installed"] for k in changed], "when": stamp,
              "detail": (f"put back {len(changed)} file(s) from build/backup/*-pre-{tag}; every sha checked"
                         if not problems else "; ".join(problems))}
    write_json(root / "build" / "backup" / f"pre-{tag}.undone-{stamp}.json", result)
    return result


# ------------------------------------------------------------------------------------------------ command line
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="install.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--engine", action="store_true")
    sub.add_parser("verify")
    sub.add_parser("selftest")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        items = freshness()
        will = plan(a.engine, root=ROOT) if a.engine else []
        print("ENGINE BUILD: " + ("NO (no --engine: nothing is built)" if not a.engine else
                                  ("none needed (everything is reused)" if not will else
                                   f"{len(will)} step(s), counted {sum(i['counted_s'] for i in will)} s")))
        for i in items:
            print(f"  {i['action']:6} {i['build']:20} {i['counted_s']:>5} s  {i['why']}")
        return 0
    if a.cmd == "verify":
        v = verify_installed()
        for i in v["items"]:
            print(f"  {'PASS' if i['ok'] else ('info' if i['ok'] is None else 'FAIL')}  {i['name']}: {i['detail']}")
        print("verify: " + ("OK" if v["ok"] else "FAIL") + f" ({v['detail']})")
        return 0 if v["ok"] else 1
    import unittest
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_install")
    r = unittest.TextTestRunner(verbosity=1).run(suite)
    n = r.testsRun
    bad = len(r.failures) + len(r.errors)
    print(f"install selftest: {n - bad}/{n} tests passed")
    return 0 if r.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
