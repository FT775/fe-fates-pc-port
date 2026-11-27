"""Run `rando.py make` subprocesses side by side (round 67, release part A).

Used by tools/release/fingerprints.py and by tests/test_rando_ingame.py's shared makes. Every make here is a fresh one:
the rando cache is OFF (FEF_RANDO_CACHE is taken out of the child's environment and no --cache is passed), the child
runs without a window at below-normal priority (subprocess flags, never `start /belownormal`), and its output folder is
the caller's (always under build/).

    import makes
    res = makes.make_many([("a", ["--seed", "1"], "build/x/a"), ...], jobs=4)
    res["a"].rc, res["a"].out, res["a"].patch, res["a"].mod_dir
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLI = os.path.join(ROOT, "tools", "randomizer", "rando.py")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BELOW_NORMAL = 0x00004000 if os.name == "nt" else 0


@dataclass
class Made:
    name: str
    args: list
    work: str           # the make's own folder: <work>/mods/Rando-<seed>/ and <work>/p.patch
    rc: int
    stdout: str
    stderr: str
    seconds: float

    @property
    def patch(self) -> str:
        return os.path.join(self.work, "p.patch")

    @property
    def mods(self) -> str:
        return os.path.join(self.work, "mods")

    def mod_dir(self) -> str | None:
        """the one Rando-<seed> folder the make wrote, or None"""
        if not os.path.isdir(self.mods):
            return None
        subs = sorted(d for d in os.listdir(self.mods) if os.path.isdir(os.path.join(self.mods, d)))
        return os.path.join(self.mods, subs[0]) if len(subs) == 1 else None


def clean_env() -> dict:
    """the child's environment: no rando cache, UTF-8 output"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env.pop("FEF_RANDO_CACHE", None)
    return env


def make(name: str, args: list, work: str, timeout: int = 900) -> Made:
    """one fresh `rando.py make ARGS --out <work>/mods --patch-out <work>/p.patch`"""
    os.makedirs(work, exist_ok=True)
    t0 = time.monotonic()
    cmd = [sys.executable, CLI, "make", *args, "--out", os.path.join(work, "mods"),
           "--patch-out", os.path.join(work, "p.patch")]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                           cwd=ROOT, env=clean_env(), creationflags=NO_WINDOW | BELOW_NORMAL)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, out, err = -9, (e.stdout or "") if isinstance(e.stdout, str) else "", f"timeout after {timeout} s"
    return Made(name, list(args), work, rc, out, err, round(time.monotonic() - t0, 2))


def make_many(specs: list[tuple[str, list, str]], jobs: int = 4, timeout: int = 900) -> dict[str, Made]:
    """specs = [(name, args, work)]; runs at most `jobs` makes at once; returns {name: Made}"""
    if not specs:
        return {}
    jobs = max(1, min(jobs, len(specs)))
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {n: ex.submit(make, n, a, w, timeout) for n, a, w in specs}
        return {n: f.result() for n, f in futs.items()}


def default_jobs() -> int:
    """side-by-side makes: FEF_MAKE_JOBS, else half the CPUs (2..6); the lanes of run_tests.py run beside these"""
    env = os.environ.get("FEF_MAKE_JOBS")
    if env and env.isdigit() and int(env) > 0:
        return int(env)
    return max(2, min(6, (os.cpu_count() or 4) // 2))
