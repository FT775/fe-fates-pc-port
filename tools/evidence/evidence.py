#!/usr/bin/env python3
"""Evidence packs and build-folder cleanup (owner OK 2026-11-13).

ELI5: after a round, keep the small text proof (result tables, run details, memory fingerprints,
logs) of every check session, and throw away the bulky leftovers (game snapshots, the robot's
scratch savestates, old session folders). Everything stays inside build/ (gitignored); a short
digest line per session goes to docs/evidence/INDEX.md (text only, no game data).

    python tools/evidence/evidence.py pack [SESSION ...]     # default: every session in build/parallel
    python tools/evidence/evidence.py clean                  # dry run: shows what would go
    python tools/evidence/evidence.py clean --yes            # really delete
    python tools/evidence/evidence.py --selftest

Clean rules (only inside build/, never saves/libraries/ports/ROM copies):
  * build/parallel/<session>: deleted only when it is packed (manifest matches) and is not one of the
    newest --keep-sessions (default 3) sessions.
  * build/harness/robot/states/*.bin (scratch savestates): all but the newest --keep-states (default
    10) are deleted. The .frame/.inputs files (the robot's button history) are always kept, so any
    state can be replayed again.
  * --keep SESSION (repeatable) protects a session whatever its age (kept H5/H6 records).
  * Refuses to run while a boot.exe is running (a round is using these files) unless --force.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "build"
PARALLEL = BUILD / "parallel"
EVIDENCE = BUILD / "evidence"
STATES = BUILD / "harness" / "robot" / "states"
INDEX = REPO / "docs" / "evidence" / "INDEX.md"

# Small text files that prove a result. Everything else (saves, savestates, pictures, pipelines,
# appdata copies, zips) is left out.
KEEP_NAMES = {"run.json", "summary.tsv", "callbacks.tsv", "boot.log", "result.json", "spec.json",
              "worker.log", "summary.json", "routes.json"}
KEEP_SUFFIXES = {".json", ".tsv", ".log", ".txt"}
SKIP_DIRS = {"appdata", "localappdata", "data", "saves", "shots", "tmp"}
MAX_FILE = 8 * 1024 * 1024  # a text file bigger than this is cut to its last 1 MB (logs)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inside_build(p: Path) -> Path:
    p = p.resolve()
    if BUILD.resolve() not in p.parents:
        raise SystemExit(f"refusing: {p} is not inside {BUILD}")
    return p


def evidence_files(session_dir: Path):
    for root, dirs, files in os.walk(session_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            p = Path(root) / f
            if f in KEEP_NAMES or p.suffix.lower() in KEEP_SUFFIXES:
                yield p


def pack(session_dir: Path, out_root: Path | None = None) -> dict:
    session_dir = inside_build(session_dir)
    out = (out_root or EVIDENCE) / session_dir.name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    files = {}
    for p in sorted(evidence_files(session_dir)):
        rel = p.relative_to(session_dir)
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if p.stat().st_size > MAX_FILE:
            with open(p, "rb") as src, open(dst, "wb") as fh:
                src.seek(-(1 << 20), os.SEEK_END)
                fh.write(b"[... cut by evidence.py: only the last 1 MB kept ...]\n" + src.read())
        else:
            shutil.copy2(p, dst)
        files[rel.as_posix()] = {"sha256": sha256(p), "size": p.stat().st_size}
    digest = summarize(session_dir)
    manifest = {"session": session_dir.name, "source": str(session_dir), "files": files,
                "total_bytes": sum(f["size"] for f in files.values()), "digest": digest}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def summarize(session_dir: Path) -> dict:
    """Per-session totals from summary.json (parallel.py) if present, else from summary.tsv files."""
    d = {"runs": 0, "pass": 0, "fail": 0, "mem": []}
    sj = session_dir / "summary.json"
    if sj.exists():
        try:
            data = json.loads(sj.read_text(encoding="utf-8"))
            rows = data.get("runs") or []
            for r in rows if isinstance(rows, list) else []:
                d["runs"] += 1
                d["pass" if r.get("ok") else "fail"] += 1
                h = r.get("memory")
                if h:
                    d["mem"].append(f"{r.get('route', '?')}={str(h)[:8]}")
        except (ValueError, OSError):
            pass
    return d


def is_packed(session_dir: Path) -> bool:
    m = EVIDENCE / session_dir.name / "manifest.json"
    if not m.exists():
        return False
    try:
        files = json.loads(m.read_text(encoding="utf-8"))["files"]
    except (ValueError, KeyError):
        return False
    for rel, info in files.items():
        p = session_dir / rel
        if not p.exists() or p.stat().st_size != info["size"]:
            return False
    return True


def boot_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq boot.exe"], capture_output=True,
                             text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "boot.exe" in out.lower()


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def plan_clean(keep_sessions: int, keep_states: int, parallel=PARALLEL, states=STATES, keep=()):
    victims = []
    if parallel.is_dir():
        sessions = sorted((d for d in parallel.iterdir() if d.is_dir()),
                          key=lambda d: d.stat().st_mtime, reverse=True)
        for d in sessions[keep_sessions:]:
            if d.name in keep:
                continue
            if is_packed(d) or not any(evidence_files(d)):
                victims.append(d)
    if states.is_dir():
        bins = sorted(states.glob("*.bin"), key=lambda f: f.stat().st_mtime, reverse=True)
        victims += bins[keep_states:]
    return victims


def update_index(manifests):
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    lines = INDEX.read_text(encoding="utf-8").splitlines() if INDEX.exists() else [
        "# Evidence index", "",
        "One line per packed check session. The packs themselves live in build/evidence/ (not in git);",
        "each has a manifest.json with the sha256 of every kept file. Written by tools/evidence/evidence.py.",
        "", "| Session | Files | Bytes | Runs | Pass | Fail |", "|---|---:|---:|---:|---:|---:|"]
    have = {l.split("|")[1].strip() for l in lines if l.startswith("| ") and not l.startswith("| Session")}
    for m in manifests:
        if m["session"] in have:
            lines = [l for l in lines if not l.startswith(f"| {m['session']} |")]
        dg = m["digest"]
        lines.append(f"| {m['session']} | {len(m['files'])} | {m['total_bytes']} | {dg['runs']} | "
                     f"{dg['pass']} | {dg['fail']} |")
    INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")


def selftest() -> int:
    global BUILD, EVIDENCE
    ok = total = 0

    def check(name, cond):
        nonlocal ok, total
        total += 1
        ok += bool(cond)
        if not cond:
            print("FAIL:", name)

    old = (BUILD, EVIDENCE)
    with tempfile.TemporaryDirectory() as t:
        BUILD = Path(t) / "build"
        EVIDENCE = BUILD / "evidence"
        par, st = BUILD / "parallel", BUILD / "states"
        for i, name in enumerate(["s-old", "s-mid", "s-new", "s-newest"]):
            s = par / name
            (s / "jobs" / "j1" / "runs" / "r1").mkdir(parents=True)
            (s / "jobs" / "j1" / "runs" / "r1" / "summary.tsv").write_text("x\t1\n")
            (s / "jobs" / "j1" / "runs" / "r1" / "run.json").write_text("{}")
            (s / "jobs" / "j1" / "data").mkdir()
            (s / "jobs" / "j1" / "data" / "Chapter0").write_bytes(b"\0" * 100)
            (s / "jobs" / "j1" / "shots").mkdir()
            (s / "jobs" / "j1" / "shots" / "a.png").write_bytes(b"png")
            os.utime(s, (1000 + i, 1000 + i))
        st.mkdir()
        for i in range(5):
            (st / f"s{i}.bin").write_bytes(b"s")
            (st / f"s{i}.inputs").write_text("in")
            os.utime(st / f"s{i}.bin", (2000 + i, 2000 + i))
        m = pack(par / "s-old")
        check("pack keeps summary.tsv", "jobs/j1/runs/r1/summary.tsv" in m["files"])
        check("pack keeps run.json", "jobs/j1/runs/r1/run.json" in m["files"])
        check("pack drops saves", not any("Chapter0" in k for k in m["files"]))
        check("pack drops pictures", not any(k.endswith(".png") for k in m["files"]))
        check("manifest written", (EVIDENCE / "s-old" / "manifest.json").exists())
        check("packed detected", is_packed(par / "s-old"))
        check("unpacked not detected", not is_packed(par / "s-mid"))
        v = plan_clean(2, 2, par, st)
        names = {p.name for p in v}
        check("old packed session goes", "s-old" in names)
        check("old unpacked session stays", "s-mid" not in names)
        check("--keep session stays", "s-old" not in {p.name for p in plan_clean(2, 2, par, st, keep={"s-old"})})
        check("newest sessions stay", not names & {"s-new", "s-newest"})
        check("old states go", {"s0.bin", "s1.bin", "s2.bin"} <= names)
        check("newest states stay", not names & {"s3.bin", "s4.bin"})
        check("inputs never go", not any(n.endswith(".inputs") for n in names))
        try:
            inside_build(Path(t) / "elsewhere")
            check("outside build refused", False)
        except SystemExit:
            check("outside build refused", True)
    BUILD, EVIDENCE = old
    print(f"evidence self-test: {ok}/{total} checks passed")
    return 0 if ok == total else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("pack")
    p.add_argument("sessions", nargs="*")
    c = sub.add_parser("clean")
    c.add_argument("--yes", action="store_true", help="really delete (default: dry run)")
    c.add_argument("--keep-sessions", type=int, default=3)
    c.add_argument("--keep-states", type=int, default=10)
    c.add_argument("--keep", action="append", default=[], metavar="SESSION",
                   help="never delete this session (repeatable), e.g. kept H5/H6 records")
    c.add_argument("--force", action="store_true", help="run even while boot.exe is running")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.cmd == "pack":
        dirs = [PARALLEL / s for s in a.sessions] if a.sessions else sorted(
            d for d in PARALLEL.iterdir() if d.is_dir())
        ms = []
        for d in dirs:
            if not d.is_dir():
                print("no such session:", d.name)
                continue
            m = pack(d)
            ms.append(m)
            print(f"packed {d.name}: {len(m['files'])} files, {m['total_bytes'] / 1e6:.1f} MB")
        update_index(ms)
        print(f"evidence total: {dir_size(EVIDENCE) / 1e6:.1f} MB in {EVIDENCE}")
        return 0
    if a.cmd == "clean":
        if boot_running() and not a.force:
            print("refusing: boot.exe is running (a round is using these files); try later or --force")
            return 2
        victims = plan_clean(a.keep_sessions, a.keep_states, keep=set(a.keep))
        freed = 0
        for v in victims:
            v = inside_build(v)
            size = dir_size(v) if v.is_dir() else v.stat().st_size
            freed += size
            print(("delete " if a.yes else "would delete ") + f"{v.relative_to(REPO)}  ({size / 1e6:.0f} MB)")
            if a.yes:
                shutil.rmtree(v) if v.is_dir() else v.unlink()
        print(f"{'freed' if a.yes else 'would free'}: {freed / 1e9:.2f} GB ({len(victims)} items)")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
