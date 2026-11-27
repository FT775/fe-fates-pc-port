#!/usr/bin/env python3
"""Several headless game runs at once, as an add-on to headless.py (docs/harness/PARALLEL.md).
Standard library only (psutil is used for memory readings when it happens to be installed and the
Windows job-object calls are not available).

It does not change headless.py or harness.py. Each run is a child process (`parallel.py --worker`)
that imports headless.py, points its folder constants at the run's own folder below build/parallel/
and calls headless.run() exactly as `harness.py headless` does. So a run here is the same run, with
the same boot.exe settings, the same run.json and the same exit rule (0: exit 0 and a savestate,
1: the run failed, 3: a setup problem).

    python tools/harness/parallel.py runs --route title --route new-game          # a list of routes
    python tools/harness/parallel.py runs --route title --copies 4 --markers      # K copies of one route
    python tools/harness/parallel.py determinism --route title --copies 3 [--serial-too]
    python tools/harness/parallel.py search --route new-game --target title__ProcMyUnitEdit \\
        --variant a=+4300:A --variant b=+4300:B --shots 4400,4600,4800 --frames 5000
    python tools/harness/parallel.py build -- --boot     # build.py, one at a time, below-normal priority
    python tools/harness/parallel.py clean               # remove build/parallel/
    python tools/harness/parallel.py limits              # what the budget allows right now
    python tools/harness/parallel.py pack SESSION RUN NAME   # a --keep run's in-game save -> saves/NAME.zip
    python tools/harness/parallel.py runs --route bt-ch2 --mode capture --only all --store-keep   # keep game records
    python tools/harness/parallel.py keep-empty SESSION   # round 13: records/<run>/ of its 0-record runs (no game)
    python tools/harness/parallel.py runs --route bt-ch8 --mode capture --lib build/speed/x/lib/T.dll   # another library
    python tools/harness/parallel.py runs --route a --route b --mode capture --longest-first --capture-jobs 10

Round 9 (docs/harness/PARALLEL.md 6): --mem-per-run-gb defaults to the measured peak of the same route and mode
(+15%, from earlier summary.json files; 1.5 GB when a route was never measured), so two determinism copies of a
0.72 GB route fit side by side in a 2.7 GB budget. --longest-first starts the routes that took longest last time
first; --capture-jobs N (capture only) raises the run cap to N (at most resources.json night.max_parallel_runs)
only while no other boot.exe holds the slots: never below the normal cap, never above the memory budget.

Budget (config/harness/resources.json, the owner's): at most max_parallel_runs runs at once, at
`priority`, in max_total_memory_gb of memory all together; builds one at a time. The owner turns it
down (or up) per shell with FEF_ROBOT_JOBS, FEF_ROBOT_PRIORITY (idle | below_normal | normal),
FEF_ROBOT_MEM_GB. `--jobs` may only lower FEF_ROBOT_JOBS / max_parallel_runs, never raise them.

How the limits are kept (Windows): every child is started with BELOW_NORMAL_PRIORITY_CLASS (or the
chosen class) and CREATE_NO_WINDOW, and put in its own job object before it starts work (it waits
for a "go" line): the job forces the priority class on boot.exe too, measures the run's peak
committed memory (PeakJobMemoryUsed), holds a hard memory ceiling, and kills the whole process tree
when parallel.py stops or is killed (KILL_ON_JOB_CLOSE). A new run starts only when the runs going
plus one more fit in the memory budget (each counted at its own peak, or at the estimate if higher)
and free physical memory stays above a reserve. The estimate starts at --mem-per-run-gb and becomes
the largest peak seen (+15%) once a run has finished, so the pool widens or narrows to what runs
really use. A run that pushes the total over the budget while others run is stopped and queued again.

Folders (all below build/parallel/<session>/; build/harness/ is only read):

    bin/, lib/          copies of boot.exe and the capture library (so a rebuild elsewhere is never
                        blocked by a file this tool holds open); deleted at the end
    jobs/<run>/         the run's own build root: data/ tmp/ runs/ shots/ saves/ localappdata/
                        appdata/ (APPDATA for the child), routes.json, spec.json, worker.log;
                        deleted at the end unless --keep
    results/<run>.json  run.json plus the pool's numbers (wall time, peak memory, kill reason)
    shots/<run>.png     the contact sheet; logs/<run>.boot.log for failed runs only
    summary.json        everything above in one file, the verdict, the %APPDATA% check
    records/<run>/      (--store-keep, round 7) the run's kept capture records (records.fecap, pages/,
                        summary.tsv, callbacks.tsv, run.json) for the offline replay (tools/harness/h56.py);
                        kept after the job folder goes; game memory: build/ only. Round 13: a run that kept 0
                        records (no records.fecap) still leaves run.json and summary.tsv, and every run.json
                        here carries capture_targets_sha256 / capture_manifest_library_sha256 (the library's
                        build manifest), capture_git_head and capture_records_fecap (offline.py plan)

Never written: %APPDATA%\\zakuro, %APPDATA%\\3dsrecomp (each child's APPDATA points into its job
folder, and the summary proves it with before/after modification times), the saves in
build/harness/saves/ and play/backups/ (copied, never opened for writing; only the explicit `pack`
command adds a new zip there, through headless.pack_save), the ROM.

Determinism uses the h4a comparison by import (headless.compare_digests and compare_meta on the
stripped metadata each run kept, plus equal instruction counts): every copy against the first.

`python tools/harness/test_parallel.py` checks the pool with fake child commands; `--smoke` adds
the one real run (title x3, determinism, against one-after-another).
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "build", "parallel")
RESOURCES = os.path.join(ROOT, "config", "harness", "resources.json")
HARNESS_BUILD = os.path.join(ROOT, "build", "harness")  # read only from here
SELF = os.path.abspath(__file__)
NAME_RX = r"[A-Za-z0-9_.-]+"

GB = 1 << 30
MB = 1 << 20
PRIORITY = {"idle": 0x00000040, "below_normal": 0x00004000, "normal": 0x00000020}
CREATE_NO_WINDOW = 0x08000000
ENV_JOBS, ENV_PRIORITY, ENV_MEM = "FEF_ROBOT_JOBS", "FEF_ROBOT_PRIORITY", "FEF_ROBOT_MEM_GB"


class Stop(Exception):
    """A setup problem: printed, nothing is run (exit 3)."""


def rel(p: str) -> str:
    try:
        return os.path.relpath(p, ROOT).replace("\\", "/")
    except ValueError:
        return p


def below(p: str, top: str) -> bool:
    p, top = os.path.abspath(p), os.path.abspath(top)
    return p.startswith(top + os.sep) and ".." not in p.split(os.sep)


def rmtree_own(path: str) -> None:
    """Deletes a folder of this tool's own scratch; refuses anything outside build/parallel/."""
    if not below(path, OUT):
        raise Stop(f"refusing to delete {path}: not below {rel(OUT)}")
    shutil.rmtree(path, ignore_errors=True)


# ------------------------------------------------------------------ budget
class Limits:
    def __init__(self, jobs: int, priority: str, mem_gb: float, build_jobs: int = 1,
                 build_priority: str = "below_normal", notes: list[str] | None = None):
        self.jobs, self.priority, self.mem_gb = jobs, priority, mem_gb
        self.build_jobs, self.build_priority = build_jobs, build_priority
        self.notes = notes or []

    def as_dict(self) -> dict:
        return {"jobs": self.jobs, "priority": self.priority, "mem_gb": self.mem_gb,
                "build_jobs": self.build_jobs, "build_priority": self.build_priority, "notes": self.notes}


def load_limits(path: str = RESOURCES, env: dict | None = None, cli_jobs: int | None = None) -> Limits:
    """The owner's budget, then the env overrides; a bad override is ignored with a note (never raises
    the budget by accident); --jobs can only lower the result."""
    env = os.environ if env is None else env
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        cfg = {}
    notes = []
    jobs = int(cfg.get("max_parallel_runs", 1) or 1)
    prio = str(cfg.get("priority", "below_normal"))
    mem = float(cfg.get("max_total_memory_gb", 4) or 4)
    builds = cfg.get("builds") or {}
    bjobs, bprio = int(builds.get("parallel", 1) or 1), str(builds.get("priority", "below_normal"))
    if not cfg:
        notes.append(f"{rel(path)} unreadable: defaults 1 run, below_normal, 4 GB")
    if env.get(ENV_JOBS):
        try:
            v = int(env[ENV_JOBS])
            if v < 1:
                raise ValueError
            jobs = v
            notes.append(f"{ENV_JOBS}={v}")
        except ValueError:
            notes.append(f"{ENV_JOBS}={env[ENV_JOBS]!r} ignored (a whole number >= 1)")
    if env.get(ENV_PRIORITY):
        v = env[ENV_PRIORITY].strip().lower().replace("-", "_")
        if v in PRIORITY:
            prio = bprio = v
            notes.append(f"{ENV_PRIORITY}={v} (runs and builds)")
        else:
            notes.append(f"{ENV_PRIORITY}={env[ENV_PRIORITY]!r} ignored ({' | '.join(PRIORITY)})")
    if env.get(ENV_MEM):
        try:
            v = float(env[ENV_MEM])
            if v <= 0:
                raise ValueError
            mem = v
            notes.append(f"{ENV_MEM}={v:g}")
        except ValueError:
            notes.append(f"{ENV_MEM}={env[ENV_MEM]!r} ignored (a number of GB > 0)")
    if prio not in PRIORITY:
        notes.append(f"priority {prio!r} unknown: below_normal")
        prio = "below_normal"
    if bprio not in PRIORITY:
        bprio = "below_normal"
    if cli_jobs is not None:
        if cli_jobs < 1:
            raise Stop("--jobs must be >= 1")
        if cli_jobs > jobs:
            notes.append(f"--jobs {cli_jobs} is above the budget: {jobs}")
        else:
            jobs = cli_jobs
    return Limits(jobs, prio, mem, bjobs, bprio, notes)


# ------------------------------------------------------------------ Windows calls (ctypes)
WIN = os.name == "nt"
if WIN:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    HANDLE = wintypes.HANDLE

    class _IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class _BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _EXT(ctypes.Structure):
        _fields_ = [("Basic", _BASIC), ("IoInfo", _IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _PIDS(ctypes.Structure):
        _fields_ = [("Assigned", wintypes.DWORD), ("InList", wintypes.DWORD), ("Ids", ctypes.c_size_t * 256)]

    class _PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + \
                   [(n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                  "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                                  "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                                                  "PrivateUsage")]

    class _MEMSTAT(ctypes.Structure):
        _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD)] + \
                   [(n, ctypes.c_ulonglong) for n in ("TotalPhys", "AvailPhys", "TotalPageFile", "AvailPageFile",
                                                     "TotalVirtual", "AvailVirtual", "AvailExtendedVirtual")]

    for _n, _a, _r in (("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], HANDLE),
                       ("SetInformationJobObject", [HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
                       ("QueryInformationJobObject", [HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                                      ctypes.c_void_p], wintypes.BOOL),
                       ("AssignProcessToJobObject", [HANDLE, HANDLE], wintypes.BOOL),
                       ("TerminateJobObject", [HANDLE, wintypes.UINT], wintypes.BOOL),
                       ("CloseHandle", [HANDLE], wintypes.BOOL),
                       ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], HANDLE),
                       ("GetPriorityClass", [HANDLE], wintypes.DWORD),
                       ("GetCurrentProcess", [], HANDLE),
                       ("WaitForSingleObject", [HANDLE, wintypes.DWORD], wintypes.DWORD),
                       ("K32GetProcessMemoryInfo", [HANDLE, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
                       ("GlobalMemoryStatusEx", [ctypes.c_void_p], wintypes.BOOL)):
        _f = getattr(_k32, _n)
        _f.argtypes, _f.restype = _a, _r

    JOB_EXT_INFO, JOB_PID_LIST = 9, 3
    LIMIT_PRIORITY, LIMIT_JOB_MEMORY, LIMIT_KILL_ON_CLOSE = 0x20, 0x200, 0x2000
    PROCESS_QUERY_LIMITED, SYNCHRONIZE = 0x1000, 0x00100000

try:
    import psutil  # optional; only used where the job object is not available
except ImportError:
    psutil = None


def free_memory() -> int:
    """Available physical memory in bytes (GlobalMemoryStatusEx, else psutil, else /proc)."""
    if WIN:
        st = _MEMSTAT()
        st.dwLength = ctypes.sizeof(st)
        if _k32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return int(st.AvailPhys)
    if psutil:
        return int(psutil.virtual_memory().available)
    try:
        with open("/proc/meminfo") as fh:
            for ln in fh:
                if ln.startswith("MemAvailable:"):
                    return int(ln.split()[1]) * 1024
    except OSError:
        pass
    return 64 * GB


def priority_of(pid: int) -> int | None:
    """The priority class of a running process (Windows), for the checks."""
    if not WIN:
        return None
    h = _k32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not h:
        return None
    try:
        return int(_k32.GetPriorityClass(h)) or None
    finally:
        _k32.CloseHandle(h)


def pid_alive(pid: int) -> bool:
    if WIN:
        h = _k32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED, False, pid)
        if not h:
            return False
        try:
            return _k32.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT: still running
        finally:
            _k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class TreeJob:
    """One Windows job object around one child: priority class for the whole tree, peak memory,
    a hard memory ceiling, kill-the-tree. Elsewhere: psutil (if any) and plain kill."""

    def __init__(self, name: str, priority: str, hard_bytes: int | None):
        self.handle = None
        self.note = None
        if not WIN:
            return
        h = _k32.CreateJobObjectW(None, None)
        if not h:
            self.note = f"CreateJobObject failed ({ctypes.get_last_error()})"
            return
        info = _EXT()
        info.Basic.LimitFlags = LIMIT_KILL_ON_CLOSE | LIMIT_PRIORITY
        info.Basic.PriorityClass = PRIORITY[priority]
        if hard_bytes:
            info.Basic.LimitFlags |= LIMIT_JOB_MEMORY
            info.JobMemoryLimit = hard_bytes
        if not _k32.SetInformationJobObject(h, JOB_EXT_INFO, ctypes.byref(info), ctypes.sizeof(info)):
            self.note = f"SetInformationJobObject failed ({ctypes.get_last_error()})"
            _k32.CloseHandle(h)
            return
        self.handle = h

    def assign(self, proc: subprocess.Popen) -> bool:
        if not self.handle:
            return False
        if not _k32.AssignProcessToJobObject(self.handle, int(proc._handle)):
            self.note = f"AssignProcessToJobObject failed ({ctypes.get_last_error()})"
            _k32.CloseHandle(self.handle)
            self.handle = None
            return False
        return True

    def peak(self) -> int:
        if not self.handle:
            return 0
        info = _EXT()
        if _k32.QueryInformationJobObject(self.handle, JOB_EXT_INFO, ctypes.byref(info), ctypes.sizeof(info), None):
            return int(info.PeakJobMemoryUsed)
        return 0

    def pids(self) -> list[int]:
        if not self.handle:
            return []
        lst = _PIDS()
        if not _k32.QueryInformationJobObject(self.handle, JOB_PID_LIST, ctypes.byref(lst), ctypes.sizeof(lst), None):
            return []
        return [int(lst.Ids[i]) for i in range(min(lst.InList, 256))]

    def current(self, proc: subprocess.Popen) -> int:
        """Committed (private) bytes of every process in the tree right now."""
        if WIN and self.handle:
            total = 0
            for pid in self.pids():
                h = _k32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
                if not h:
                    continue
                try:
                    pmc = _PMC()
                    pmc.cb = ctypes.sizeof(pmc)
                    if _k32.K32GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
                        total += int(pmc.PrivateUsage)
                finally:
                    _k32.CloseHandle(h)
            return total
        if psutil:
            try:
                p = psutil.Process(proc.pid)
                return sum(int(x.memory_info().rss) for x in [p] + p.children(recursive=True))
            except psutil.Error:
                return 0
        return 0

    def kill(self, proc: subprocess.Popen) -> None:
        if self.handle:
            _k32.TerminateJobObject(self.handle, 1)
        else:
            if WIN:  # no job: the whole tree by taskkill
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            try:
                proc.kill()
            except OSError:
                pass

    def close(self) -> None:
        if self.handle:
            _k32.CloseHandle(self.handle)  # KILL_ON_JOB_CLOSE: anything left dies here
            self.handle = None


# ------------------------------------------------------------------ the pool
class Job:
    """One child command. result_file: JSON the child writes (read back into the result)."""

    def __init__(self, name: str, cmd: list[str], cwd: str | None = None, env: dict | None = None,
                 log_file: str | None = None, result_file: str | None = None, timeout: float = 1200,
                 info: dict | None = None):
        self.name, self.cmd, self.cwd, self.env = name, cmd, cwd, env
        self.log_file, self.result_file, self.timeout = log_file, result_file, timeout
        self.info = info or {}
        self.requeued = 0


class Running:
    def __init__(self, job: Job, proc: subprocess.Popen, tree: TreeJob, log):
        self.job, self.proc, self.tree, self.log = job, proc, tree, log
        self.started = time.time()
        self.peak = 0
        self.now = 0
        self.killed: str | None = None


class Pool:
    """Runs Jobs as below-normal children within the run, memory and free-memory limits.

    mem_per_run_gb: the first estimate of one run's memory (then the largest peak seen, +15%).
    run_cap_gb: one run is stopped above this (default: the whole budget); the job object's hard
    ceiling is 1.5 times it. reserve_gb: free physical memory kept for everything else."""

    def __init__(self, limits: Limits, mem_per_run_gb: float = 1.5, run_cap_gb: float | None = None,
                 reserve_gb: float = 2.0, priority: str | None = None, say=print, tick: float = 0.2,
                 free_mem=free_memory, on_tick=None, max_requeue: int = 2, adapt: bool = True,
                 others=None, floor_jobs: int | None = None):
        self.limits = limits
        # round 9 (--capture-jobs): others() counts game runs outside this pool (another session's boot.exe, a
        # look-ahead); the cap is then max(floor_jobs, limits.jobs - others()). None: the cap is limits.jobs (as before)
        self.others, self.floor_jobs = others, floor_jobs
        self.priority = priority or limits.priority
        self.budget = int(limits.mem_gb * GB)
        self.est = int(mem_per_run_gb * GB)
        self.first_est = self.est
        self.run_cap = int((run_cap_gb if run_cap_gb is not None else limits.mem_gb) * GB)
        self.reserve = int(reserve_gb * GB)
        self.say, self.tick, self.free_mem, self.on_tick = say, tick, free_mem, on_tick
        self.max_requeue = max_requeue
        self.adapt = adapt
        self.running: dict[str, Running] = {}
        self.max_running = 0
        self.peaks: list[int] = []
        self.events: list[str] = []
        self.waits = {"jobs": 0, "budget": 0, "free_memory": 0}

    def creationflags(self) -> int:
        if not WIN:
            return 0
        return CREATE_NO_WINDOW | PRIORITY[self.priority]

    def job_cap(self) -> int:
        if self.others is None:
            return self.limits.jobs
        try:
            busy = max(0, int(self.others(self)))
        except Exception:  # cannot count: behave as the normal budget
            busy = self.limits.jobs
        return max(self.floor_jobs or 1, min(self.limits.jobs, self.limits.jobs - busy))

    def can_start(self) -> bool:
        n = len(self.running)
        if n >= self.job_cap():
            self.waits["jobs"] += 1
            return False
        if n == 0:
            return True  # always make progress; the job object still caps the run
        held = sum(max(r.peak, r.now, self.est) for r in self.running.values())
        if held + self.est > self.budget:
            self.waits["budget"] += 1
            return False
        if self.free_mem() - self.est < self.reserve:
            self.waits["free_memory"] += 1
            return False
        return True

    def start(self, job: Job) -> None:
        log = open(job.log_file, "w", encoding="utf-8", errors="replace") if job.log_file else subprocess.DEVNULL
        tree = TreeJob(job.name, self.priority, int(self.run_cap * 1.5) if self.run_cap else None)
        kw = {}
        if not WIN and self.priority != "normal":
            kw["preexec_fn"] = lambda: os.nice(10 if self.priority == "below_normal" else 19)
        proc = subprocess.Popen(job.cmd, cwd=job.cwd, env=job.env, stdin=subprocess.PIPE, stdout=log,
                                stderr=subprocess.STDOUT, creationflags=self.creationflags(), **kw)
        tree.assign(proc)
        if tree.note:
            self.events.append(f"{job.name}: {tree.note} (priority from creationflags only)")
        try:  # the child may start its real work now (a --worker waits for this line)
            proc.stdin.write(b"go\n")
            proc.stdin.close()
        except OSError:
            pass
        self.running[job.name] = Running(job, proc, tree, log)
        self.max_running = max(self.max_running, len(self.running))

    def finish(self, r: Running, results: list[dict]) -> None:
        r.peak = max(r.peak, r.tree.peak())
        rc = r.proc.wait()
        r.tree.close()
        if r.log is not subprocess.DEVNULL:
            r.log.close()
        del self.running[r.job.name]
        if r.killed == "requeued":
            return
        res = None
        if r.job.result_file and os.path.isfile(r.job.result_file):
            try:
                with open(r.job.result_file, encoding="utf-8") as fh:
                    res = json.load(fh)
            except (OSError, ValueError):
                res = None
        if rc == 0 and not r.killed and r.peak:
            self.peaks.append(r.peak)
        if self.adapt and self.peaks:
            self.est = max(64 * MB, int(max(self.peaks) * 1.15))  # adapt to what runs really use
        results.append({"name": r.job.name, "exit_code": rc, "killed": r.killed,
                        "wall_seconds": round(time.time() - r.started, 2), "peak_mem_mb": round(r.peak / MB, 1),
                        "requeued": r.job.requeued, "info": r.job.info, "result": res})
        self.say(f"[pool] {r.job.name}: exit {rc}{' (' + r.killed + ')' if r.killed else ''}, "
                 f"{results[-1]['wall_seconds']} s, peak {results[-1]['peak_mem_mb']} MB")

    def kill(self, r: Running, why: str) -> None:
        if r.killed:
            return
        r.killed = why
        r.tree.kill(r.proc)

    def kill_all(self, why: str) -> None:
        for r in list(self.running.values()):
            self.kill(r, why)
        for r in list(self.running.values()):
            try:
                r.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            r.tree.close()
            if r.log is not subprocess.DEVNULL:
                r.log.close()
        self.running.clear()

    def run(self, jobs: list[Job]) -> list[dict]:
        pending = collections.deque(jobs)
        results: list[dict] = []
        try:
            while pending or self.running:
                for r in list(self.running.values()):
                    r.now = r.tree.current(r.proc)
                    r.peak = max(r.peak, r.now, r.tree.peak())
                    if r.proc.poll() is not None:
                        self.finish(r, results)
                        continue
                    if time.time() - r.started > r.job.timeout:
                        self.kill(r, "timeout")
                    elif self.run_cap and r.now > self.run_cap:
                        self.kill(r, "memory cap")
                        self.events.append(f"{r.job.name}: stopped at {r.now // MB} MB (cap {self.run_cap // MB} MB)")
                total = sum(r.now for r in self.running.values() if not r.killed)
                live = [r for r in self.running.values() if not r.killed]
                if total > self.budget and len(live) > 1:  # over the budget: the newest goes back in the queue
                    newest = max(live, key=lambda x: x.started)
                    if newest.job.requeued < self.max_requeue:
                        newest.job.requeued += 1
                        self.est = max(self.est, max(r.now for r in live))
                        self.events.append(f"{newest.job.name}: requeued (total {total // MB} MB > budget "
                                           f"{self.budget // MB} MB)")
                        self.kill(newest, "requeued")
                        pending.appendleft(newest.job)
                    else:
                        self.kill(newest, "memory budget")
                while pending and self.can_start():
                    self.start(pending.popleft())
                if self.on_tick:
                    self.on_tick(self)
                time.sleep(self.tick)
        except KeyboardInterrupt:
            self.say("[pool] interrupted: stopping every child")
            self.kill_all("interrupted")
            raise
        finally:
            for r in list(self.running.values()):
                r.tree.close()
        return results

    def stats(self) -> dict:
        return {"max_running": self.max_running, "estimate_first_mb": self.first_est // MB,
                "estimate_last_mb": self.est // MB, "peaks_mb": [p // MB for p in self.peaks],
                "budget_mb": self.budget // MB, "run_cap_mb": self.run_cap // MB, "priority": self.priority,
                "waits": self.waits, "events": self.events}


# ------------------------------------------------------------------ round 9: measured peaks, last wall times, slots
EVIDENCE = os.path.join(ROOT, "build", "evidence")
MEM_MARGIN = 1.15  # the same margin the pool adds to a measured peak


def past_runs(roots: tuple[str, ...] = (OUT, EVIDENCE)) -> list[dict]:
    """Every finished run row of earlier sessions (*/summary.json below build/parallel/ and build/evidence/), with
    the session file's time; unreadable or half-written files are skipped (never raises)."""
    rows = []
    for root in roots:
        for p in glob.glob(os.path.join(root, "*", "summary.json")):
            try:
                with open(p, encoding="utf-8") as fh:
                    s = json.load(fh)
                when = os.path.getmtime(p)
            except (OSError, ValueError):
                continue
            for r in (s.get("runs") or []) if isinstance(s, dict) else []:
                if isinstance(r, dict) and r.get("route"):
                    rows.append(dict(r, _when=when, _session=s.get("session")))
    return rows


def route_family(route: str) -> str:
    """The kind of route a peak stands for: "bt" for bt-ch12 / bt-ch12-clear-tail, "cq", "rv", else the first word."""
    m = re.match(r"([A-Za-z]+)-ch\d+", route or "")
    return m.group(1) if m else (route or "").split("-")[0]


def measured_peak_mb(routes: list[str], mode: str, past: list[dict] | None = None) -> tuple[float | None, str]:
    """The largest peak_mem_mb of a passed earlier run of each route in this mode, the largest over the routes. Round
    10: a route never run before takes the largest peak of the passed runs of its family (route_family: round 9's
    first bt-ch12 copies ran one after the other on the 1.5 GB guess while bt routes peak at 366-722 MB). None when
    a route has neither (then the old 1.5 GB first estimate stays); the pool still adapts after the first run."""
    past = past_runs() if past is None else past
    ok = [x for x in past if (x.get("mode") or "original") == mode and x.get("ok") and x.get("peak_mem_mb")]
    worst, which, notes = 0.0, "", []
    for r in sorted(set(routes)):
        peaks = [float(x["peak_mem_mb"]) for x in ok if x.get("route") == r]
        src = r
        if not peaks:
            fam = route_family(r)
            like = [x for x in ok if x.get("route") != r and route_family(x.get("route")) == fam]
            if not like:
                return None, f"no measured peak of {r} or another {fam} route ({mode})"
            top = max(like, key=lambda x: float(x["peak_mem_mb"]))
            peaks, src = [float(top["peak_mem_mb"])], f"{r} (like {top['route']})"
            notes.append(src)
        if max(peaks) > worst:
            worst, which = max(peaks), src
    return worst, f"measured peak {worst:.0f} MB of {which} ({mode})" + (
        f"; unmeasured routes estimated from their family: {', '.join(notes)}" if notes else "")


def last_wall(route: str, mode: str, past: list[dict]) -> float | None:
    """wall_seconds of the newest passed earlier run of the route in this mode."""
    xs = [x for x in past if x.get("route") == route and (x.get("mode") or "original") == mode and x.get("ok")
          and x.get("wall_seconds")]
    return float(max(xs, key=lambda x: x["_when"])["wall_seconds"]) if xs else None


def longest_first(jobs: list, past: list[dict], routes: dict) -> list:
    """Jobs ordered by the last wall time of their route, longest first; a route never run before is ordered by
    its frames at 200 frames a second (capture runs measured 150-260), so a long new route still goes early."""
    def key(j):
        r = j.info.get("route")
        w = last_wall(r, j.info.get("mode") or "original", past)
        return -(w if w is not None else float((routes.get(r) or {}).get("frames") or 0) / 200.0)
    return sorted(jobs, key=key)  # stable: equal keys keep the given order


def process_names() -> dict[int, str]:
    """pid -> executable name of every process (Toolhelp32 on Windows, /proc elsewhere); {} when unavailable."""
    out: dict[int, str] = {}
    if WIN:
        class _PE(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateToolhelp32Snapshot.restype = HANDLE
        k.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k.Process32FirstW.argtypes = k.Process32NextW.argtypes = [HANDLE, ctypes.c_void_p]
        snap = k.CreateToolhelp32Snapshot(0x2, 0)
        if not snap or snap == HANDLE(-1).value:
            return out
        try:
            e = _PE()
            e.dwSize = ctypes.sizeof(_PE)
            ok = k.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                out[int(e.th32ProcessID)] = e.szExeFile
                ok = k.Process32NextW(snap, ctypes.byref(e))
        finally:
            _k32.CloseHandle(snap)
        return out
    for d in glob.glob("/proc/[0-9]*/comm"):
        try:
            with open(d, encoding="utf-8") as fh:
                out[int(d.split("/")[2])] = fh.read().strip()
        except (OSError, ValueError):
            pass
    return out


def other_game_runs(pool, names=process_names, exe: str = "boot.exe") -> int:
    """boot.exe processes on this machine that are not this pool's own runs (another session, a look-ahead)."""
    mine = set()
    for r in list(pool.running.values()):
        try:
            mine.update(r.tree.pids())
        except Exception:
            pass
        mine.add(r.proc.pid)
    return sum(1 for pid, n in names().items() if n.lower() == exe and pid not in mine)


def capture_jobs_cap(want: int, path: str = RESOURCES) -> int:
    """--capture-jobs N is held to the owner's largest run count (resources.json night.max_parallel_runs, else
    max_parallel_runs)."""
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        cfg = {}
    top = int((cfg.get("night") or {}).get("max_parallel_runs") or cfg.get("max_parallel_runs") or 1)
    return max(1, min(int(want), top))


# ------------------------------------------------------------------ %APPDATA% guard
def appdata_dirs() -> list[str]:
    base = os.environ.get("APPDATA")
    return [os.path.join(base, n) for n in ("zakuro", "3dsrecomp")] if base else []


def snapshot(dirs: list[str], cap: int = 50000) -> dict:
    """{path: [mtime_ns, size]} of every file and folder below dirs (and the dirs themselves)."""
    out: dict[str, list] = {}
    for d in dirs:
        if not os.path.exists(d):
            out[d] = None
            continue
        for root, subdirs, files in os.walk(d):
            for n in [root] + [os.path.join(root, f) for f in files]:
                try:
                    st = os.stat(n)
                    out[n] = [st.st_mtime_ns, st.st_size if n != root else 0]
                except OSError:
                    out[n] = "unreadable"
                if len(out) >= cap:
                    return out
    return out


def snapshot_diff(before: dict, after: dict) -> list[str]:
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


# ------------------------------------------------------------------ runs (headless.py wrapped)
def headless_module():
    sys.path.insert(0, HERE)
    try:
        import headless  # noqa: E402  (same folder; the other tools import it the same way)
    finally:
        sys.path.remove(HERE)
    return headless


DEFAULT_SAVE = "new-game-empty"  # the robot's empty save (build/harness/saves/)


# ------------------------------------------------------------------ kept records (round 7; round 13: 0-record runs)
# Where capture libraries' build manifests (harness_build.json: library_sha256, targets_sha256) are found again for a
# run that did not stamp its run.json (sessions before round 13): only read.
MANIFEST_DIRS = ("build/harness/lib", "build/harness/*/lib", "build/evidence/*/lib", "build/speed/replay/*/lib",
                 "build/speed/replay/trees/*/build/harness/lib", "build/parallel/*/lib", "build/extras/robot/*/lib")


def git_head() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout.strip() or None) if r.returncode == 0 else None


def capture_stamp(manifest_path: str | None) -> dict:
    """Round 13: what offline.py plan needs to tell which targets.csv a run's records ran: the library build
    manifest's targets_sha256 and library_sha256 (harness_build.json beside the library; left out when there is
    none) and the commit checked out when the session started (a hint only: targets.csv may have been edited)."""
    st: dict = {"capture_git_head": git_head()}
    try:
        with open(manifest_path or "", encoding="utf-8") as fh:
            m = json.load(fh)
        if isinstance(m, dict) and m.get("targets_sha256") and m.get("library_sha256"):
            st["capture_targets_sha256"] = m["targets_sha256"]
            st["capture_manifest_library_sha256"] = m["library_sha256"]
    except (OSError, ValueError):
        pass
    return st


def find_manifest(lib_sha: str | None, root: str = ROOT) -> dict | None:
    """The build manifest of the capture library with this sha256, from the places manifests are kept (MANIFEST_DIRS)."""
    if not lib_sha:
        return None
    for pat in MANIFEST_DIRS:
        for p in sorted(glob.glob(os.path.join(root, pat, "harness_build.json"))):
            try:
                with open(p, encoding="utf-8") as fh:
                    m = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(m, dict) and m.get("library_sha256") == lib_sha and m.get("targets_sha256"):
                return dict(m, _path=rel(p))
    return None


def write_run_json(rj: dict, dst: str, extra: dict, mtime: float) -> None:
    """records/<run>/run.json: the run's run.json plus the round-13 capture stamp, with the run's own time (offline.py
    plan compares that time with later route and save changes)."""
    out = dict(rj)
    out.update(extra)
    tmp = dst + f".tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1)
    os.replace(tmp, dst)
    os.utime(dst, (mtime, mtime))


def keep_records(kept: str, run: str, records_root: str, stamp: dict) -> list[str]:
    """records/<run>[.stage<k>]/ from the run folder runs/<run>/ (a cheat route's earlier stages keep theirs in
    runs/<run>/stage<k>/). Round 13: a run that kept 0 records (capture.c writes no records.fecap when nothing it
    watched was called) still leaves run.json (its watched `only` list, the library hash) and summary.tsv, so
    offline.py plan counts its overrides as "watched, never called" instead of NEW. Returns the folders written."""
    stages = [(kept, run)] + [(d, f"{run}.{os.path.basename(d)}") for d in
                              sorted(glob.glob(os.path.join(kept, "stage*"))) if os.path.isdir(d)]
    src_rj = os.path.join(kept, "run.json")  # the whole run's (cheat marks included)
    out = []
    for src_dir, dst_name in stages:
        fecap = os.path.isfile(os.path.join(src_dir, "records.fecap"))
        if not fecap and (not os.path.isfile(src_rj)
                          or (src_dir != kept and not os.path.isfile(os.path.join(src_dir, "summary.tsv")))):
            continue
        dst = os.path.join(records_root, dst_name)
        os.makedirs(dst, exist_ok=True)
        for name in ("records.fecap", "summary.tsv", "callbacks.tsv", "boot.log"):
            if os.path.isfile(os.path.join(src_dir, name)):
                shutil.copy2(os.path.join(src_dir, name), os.path.join(dst, name))
        if os.path.isfile(src_rj):
            try:
                with open(src_rj, encoding="utf-8") as fh:
                    rj = json.load(fh)
            except (OSError, ValueError):
                rj = None
            if isinstance(rj, dict):
                write_run_json(rj, os.path.join(dst, "run.json"), dict(stamp, capture_records_fecap=fecap),
                               os.path.getmtime(src_rj))
            else:
                shutil.copy2(src_rj, os.path.join(dst, "run.json"))
        if os.path.isdir(os.path.join(src_dir, "pages")):
            shutil.copytree(os.path.join(src_dir, "pages"), os.path.join(dst, "pages"), dirs_exist_ok=True)
        out.append(dst)
    return out


def tsv_records(path: str) -> int | None:
    """Total of the records column of a capture summary.tsv (None: no such column)."""
    with open(path, encoding="utf-8") as fh:
        lines = [ln.rstrip("\n") for ln in fh if not ln.startswith("#") and ln.strip()]
    if not lines or "records" not in lines[0].split("\t"):
        return None
    i = lines[0].split("\t").index("records")
    return sum(int(ln.split("\t")[i] or 0) for ln in lines[1:])


def keep_empty(session: str, root: str = OUT, say=print) -> list[str]:
    """Round 13 backfill (`parallel.py keep-empty SESSION`): for a finished `--store-keep` capture session, the
    records/<run>[.stage<k>]/ folders that keep_records now writes for runs that kept 0 records, made from
    results/<run>.json (its run_json: `only`, library hash, route, input, outcome) and results/<run>[.stage<k>]
    .summary.tsv. No game runs. A folder that exists is never touched; a run whose summary.tsv counts records but has
    no records/ folder is reported, not backfilled (its records are gone: it must be captured again). run.json gets
    the targets.csv hash from the library's build manifest when one is still found (find_manifest), and the time of
    its summary.tsv (written during the run, before run.json)."""
    if not re.fullmatch(NAME_RX, session) or ".." in session:
        raise Stop(f"keep-empty: session {session!r}: letters, digits, _ . - only")
    sdir = os.path.join(root, session)
    if not os.path.isdir(os.path.join(sdir, "results")):
        raise Stop(f"keep-empty: no {rel(os.path.join(sdir, 'results'))}")
    made, manifests = [], {}
    for rj_path in sorted(glob.glob(os.path.join(sdir, "results", "*.json"))):
        run = os.path.basename(rj_path)[:-len(".json")]
        try:
            with open(rj_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        rj, row = data.get("run_json") or {}, data.get("row") or {}
        if row.get("mode") != "capture" or rj.get("store") != "keep" or not rj.get("only"):
            continue
        tsvs = [(run, os.path.join(sdir, "results", f"{run}.summary.tsv"))]
        for p in sorted(glob.glob(os.path.join(sdir, "results", f"{glob.escape(run)}.stage*.summary.tsv"))):
            tag = os.path.basename(p)[len(run):-len(".summary.tsv")]
            if re.fullmatch(r"\.stage\d+", tag):
                tsvs.append((run + tag, p))
        for dst_name, tsv in tsvs:
            dst = os.path.join(sdir, "records", dst_name)
            if os.path.exists(dst) or not os.path.isfile(tsv):
                continue
            n = tsv_records(tsv)
            if n != 0:
                say(f"keep-empty: {dst_name}: summary.tsv counts {n} record(s) but no records/ folder was kept: "
                    "not backfilled (capture it again)")
                continue
            lib = rj.get("library_sha256")
            if lib not in manifests:
                manifests[lib] = find_manifest(lib)
            m = manifests[lib]
            stamp = {"capture_records_fecap": False, "capture_backfilled_from": rel(rj_path)}
            if m:
                stamp.update(capture_targets_sha256=m["targets_sha256"], capture_manifest_library_sha256=lib,
                             capture_manifest=m["_path"])
            os.makedirs(dst)
            shutil.copy2(tsv, os.path.join(dst, "summary.tsv"))
            write_run_json(rj, os.path.join(dst, "run.json"), stamp, min(os.path.getmtime(tsv), os.path.getmtime(rj_path)))
            made.append(dst)
    say(f"keep-empty {session}: {len(made)} 0-record folder(s) written below {rel(os.path.join(sdir, 'records'))}")
    return made


class Session:
    """build/parallel/<name>/: shared copies, one job folder per run, results."""

    def __init__(self, name: str, save: str | None, keep: bool = False, say=print, lib: str | None = None):
        if not re.fullmatch(NAME_RX, name):
            raise Stop(f"session {name}: letters, digits, _ . - only")
        self.name, self.keep, self.say = name, keep, say
        self.dir = os.path.join(OUT, name)
        self.hl = headless_module()
        # --save, if given, is every run's start save; else each route's own "save" (a bt-* route starts
        # from the packed in-game save of the piece before it), else the empty save. Before 2026-11-11
        # round 3 the default new-game-empty overrode the route's save: bt-* runs started empty.
        self.save_src = self.find_save(save) if save else None
        self.saves_used: set[str] = set()
        self.routes = self.hl.load_routes()  # read only, validated by headless
        self.lib_src = os.path.abspath(lib) if lib else None  # round 9 --lib: None = build/harness/lib (as before)

    def find_save(self, save: str) -> str:
        hl = headless_module()
        try:
            return hl.find_backup(save)  # build/harness/saves/<name>.zip or a PLAY backup: only read
        except hl.Stop as e:
            raise Stop(str(e)) from None

    def stage(self) -> None:
        hl = self.hl
        lib_src = self.lib_src or hl.LIB
        for p, what in ((hl.BOOT, "boot.exe (tools/harness/build.py --boot)"), (lib_src, "the capture library (build.py)")):
            if not os.path.isfile(p):
                raise Stop(f"no {rel(p)}: {what}")
        if os.path.isdir(self.dir):
            rmtree_own(self.dir)
        for d in ("bin", "lib", "jobs", "results", "shots", "logs"):
            os.makedirs(os.path.join(self.dir, d))
        self.boot = os.path.join(self.dir, "bin", os.path.basename(hl.BOOT))
        shutil.copy2(hl.BOOT, self.boot)
        self.lib = os.path.join(self.dir, "lib", os.path.basename(lib_src))
        shutil.copy2(lib_src, self.lib)
        manifest = os.path.join(os.path.dirname(lib_src), "harness_build.json")
        if os.path.isfile(manifest):
            shutil.copy2(manifest, os.path.join(self.dir, "lib", "harness_build.json"))
        self.stamp = capture_stamp(manifest)  # round 13: written into every records/<run>/run.json

    def job(self, run: str, route_name: str, route: dict, mode: str = "original", markers: bool = False,
            keep_meta: bool = False, timeout: float | None = None, info: dict | None = None, only: str | None = None,
            store: bool | str = False) -> Job:
        """timeout: boot.exe's own limit for the run (headless.run); None = run_timeout(route, mode, 1), the same
        rule as the commands (round 10: was a flat 900 s here). The pool kills the worker 120 s after that (the
        worker's start, the copy of results and the clean-up), so a run's wall limit is timeout + 120 s."""
        if timeout is None:
            timeout = run_timeout(route, mode, 1)
        if not re.fullmatch(NAME_RX, run):
            raise Stop(f"run name {run}: letters, digits, _ . - only")
        root = os.path.join(self.dir, "jobs", run)
        os.makedirs(os.path.join(root, "saves"))
        routes = os.path.join(root, "routes.json")
        with open(routes, "w", encoding="utf-8") as fh:
            json.dump({"routes": {route_name: route}}, fh, indent=1)
        try:
            self.hl.load_routes(routes)  # headless's own route rules, before anything starts
        except self.hl.Stop as e:
            raise Stop(f"{run}: {e}") from None
        src = self.save_src or self.find_save(route.get("save") or DEFAULT_SAVE)
        # docs/CHEATS.md rule 3 before anything starts (headless.run checks it again): a cheat save, named by the
        # route or by --save, under any name, never starts a real-play run
        start_cheat = self.hl.save_is_cheat(src)
        if start_cheat and not route.get("cheat"):
            raise Stop(f"{run}: route {route_name} is real play, but its start save {rel(src)} is a cheat save "
                       f"({start_cheat}); cheat state never starts a real-play run")
        start_options = self.hl.save_is_options(src) if hasattr(self.hl, "save_is_options") else None
        if start_options and "options" not in route:  # tools/harness/options_track.py rule 3
            raise Stop(f"{run}: route {route_name} has no \"options\", but its start save {rel(src)} is an options "
                       f"save ({start_options}); options-track state never starts a real-play or cheat run")
        self.saves_used.add(rel(src))
        save = os.path.join(root, "saves", os.path.basename(src))
        shutil.copy2(src, save)
        seed = os.path.join(HARNESS_BUILD, "localappdata")  # the pipeline cache: a copy per run
        lad = os.path.join(root, "localappdata")
        if os.path.isdir(seed):
            shutil.copytree(seed, lad)
        else:
            os.makedirs(lad)
        os.makedirs(os.path.join(root, "appdata"))
        spec = {"run": run, "route": route_name, "routes": routes, "mode": mode, "markers": markers,
                "keep_meta": keep_meta, "timeout": timeout, "root": root, "boot": self.boot, "lib": self.lib,
                "save": save, "result": os.path.join(root, "result.json"), "only": only, "store": store}
        spec_path = os.path.join(root, "spec.json")
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, indent=1)
        hl = headless_module()  # the worker never sees the options file's path (FE_OPTIONS / FEF_OPTIONS)
        env = {k: v for k, v in os.environ.items() if k.upper() not in hl.OPTIONS_ENVS}
        env.update(APPDATA=os.path.join(root, "appdata"), PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
        return Job(run, [sys.executable, SELF, "--worker", spec_path], cwd=root, env=env,
                   log_file=os.path.join(root, "worker.log"), result_file=spec["result"], timeout=timeout + 120,
                   info=dict(info or {}, route=route_name, mode=mode, store=store,
                             cheat=bool(route.get("cheat")) or bool(start_cheat),
                             options="options" in route or bool(start_options)))

    def meta(self, run: str) -> bytes | None:
        """The stripped metadata a run kept (headless keep_meta), read before the job folder goes."""
        try:
            with open(os.path.join(self.dir, "jobs", run, "runs", run, "meta.bin.z"), "rb") as fh:
                return zlib.decompress(fh.read())
        except (OSError, zlib.error):
            return None

    def collect(self, results: list[dict]) -> list[dict]:
        """results/<run>.json, shots/<run>.png, logs/<run>.boot.log (failed runs); a short row each."""
        rows = []
        for r in results:
            run = r["name"]
            root = os.path.join(self.dir, "jobs", run)
            res = r.get("result") or {}
            rj = res.get("run_json") or {}
            png = os.path.join(root, "shots", run, "checkpoints.png")
            if os.path.isfile(png):
                shutil.copy2(png, os.path.join(self.dir, "shots", f"{run}.png"))
            ok = r["exit_code"] == 0 and not r["killed"]
            cap = None
            if r["info"].get("mode") == "capture":  # the live compare's verdict: summary.tsv, never the boot.log
                found = sorted(glob.glob(os.path.join(root, "runs", run, "**", "summary.tsv"), recursive=True))
                for src in found:  # a cheat run's earlier stages keep theirs in runs/<run>/stage<k>/
                    sub = os.path.basename(os.path.dirname(src))
                    tag = f".{sub}" if re.fullmatch(r"stage\d+", sub) else ""
                    shutil.copy2(src, os.path.join(self.dir, "results", f"{run}{tag}.summary.tsv"))
                cap = capture_totals(found)
                cap["problem"] = capture_problem(cap)
                if cap["problem"]:
                    ok = False
            if r["info"].get("store") == "keep":  # round 7: the kept records outlive the job folder (h56.py)
                keep_records(os.path.join(root, "runs", run), run, os.path.join(self.dir, "records"),
                             getattr(self, "stamp", None) or {})
            cps = rj.get("checkpoints")
            if isinstance(cps, list):  # search may shoot other frames: a checkpoint frame never shot is not a miss
                shot = set((rj.get("markers") or {}).keys())
                cps = [c for c in cps if not (c.endswith(": no markers") and c.split()[1].rstrip(":") not in shot)]
                rj["checkpoints"] = cps or "all met (of the frames shot)"
            if not ok:
                for src, dst in ((os.path.join(root, "runs", run, "boot.log"), f"{run}.boot.log"),
                                 (os.path.join(root, "worker.log"), f"{run}.worker.log")):
                    if os.path.isfile(src):
                        shutil.copy2(src, os.path.join(self.dir, "logs", dst))
            row = {"run": run, "ok": ok, "exit_code": r["exit_code"], "killed": r["killed"],
                   "wall_seconds": r["wall_seconds"], "peak_mem_mb": r["peak_mem_mb"], "requeued": r["requeued"],
                   "route": r["info"].get("route"), "variant": r["info"].get("variant"), "mode": r["info"].get("mode"),
                   "boot_exit": rj.get("exit_code"), "outcome": rj.get("outcome"), "frames": rj.get("frames"),
                   "boot_seconds": rj.get("seconds"), "instructions": rj.get("instructions"),
                   "memory": (rj.get("state") or {}).get("memory"), "checkpoints": rj.get("checkpoints"),
                   "current": {f: (m or {}).get("current") for f, m in (rj.get("markers") or {}).items()} or None,
                   "shots": rel(os.path.join(self.dir, "shots", f"{run}.png")) if os.path.isfile(png) else None,
                   "setup_error": res.get("setup_error"), "capture": cap, "cheat": bool(r["info"].get("cheat")) or bool(rj.get("cheat")),
                   "options": bool(r["info"].get("options")) or bool(rj.get("options_run")) or bool(rj.get("start_save_options")),
                   "pokes": rj.get("pokes")}
            with open(os.path.join(self.dir, "results", f"{run}.json"), "w", encoding="utf-8") as fh:
                json.dump({"row": row, "pool": {k: r[k] for k in ("exit_code", "killed", "wall_seconds", "peak_mem_mb",
                                                                  "requeued")}, "run_json": rj}, fh, indent=1)
            rows.append(row)
        return rows

    def cleanup(self) -> None:
        for d in ("bin", "lib") + (() if self.keep else ("jobs",)):
            p = os.path.join(self.dir, d)
            if os.path.isdir(p):
                rmtree_own(p)


def worker(spec_path: str) -> int:
    """One run in its own folders: headless.run() with headless's folder constants pointed at the
    job root (build/parallel/<session>/jobs/<run>/), the session's boot.exe and library copies, the
    job's own routes.json. Waits for the pool's "go" first (it is in its job object by then)."""
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    sys.stdin.readline()
    root = spec["root"]
    if not below(root, OUT):
        print(f"worker: {root} is not below {rel(OUT)}")
        return 3
    hl = headless_module()
    hl.BUILD = root
    hl.RUNS = os.path.join(root, "runs")
    hl.SAVES = os.path.join(root, "saves")
    hl.LOCALAPPDATA = os.path.join(root, "localappdata")
    hl.BOOT = spec["boot"]
    own_routes, base_load = spec["routes"], hl.load_routes
    hl.load_routes = lambda path=None: base_load(path or own_routes)
    out = {"spec": spec}
    try:
        r = hl.run(spec["run"], spec["route"], spec["mode"], save=spec["save"], lib=spec["lib"],
                   keep_meta=spec["keep_meta"], markers=spec["markers"], timeout=spec["timeout"],
                   only=spec.get("only"), store=spec.get("store") or False)
        out["run_json"] = r
        rc = 0 if r["exit_code"] == 0 and "state" in r else 1
    except hl.Stop as e:
        print(f"headless: SETUP: {e}")
        out["setup_error"] = str(e)
        rc = 3
    with open(spec["result"], "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return rc


# ------------------------------------------------------------------ capture records (round 6)
# A capture-mode run is a live shadow compare (docs/HARNESS.md): its verdict is in summary.tsv, not in the boot.log
# (the log's [fe-capture] lines are capped and a run with mismatch records can print none). Review round 5 planted a
# wrong unit_has_skill: 52 mismatch_r0 records, and both runs still printed PASS. Now any of these record kinds in
# any summary.tsv of a capture run makes the run FAIL.
CAPTURE_BAD = ("mismatch_r0", "mismatch_regs", "mismatch_mem", "mismatch_calls", "b_escaped", "unfaithful",
               "escaped", "damaged")
CAPTURE_SHOWN = ("match", "gave_up", "incomplete") + CAPTURE_BAD


WRITER_KEYS = ("log", "stores", "restored", "sessions", "refusals", "mode_refusals", "stray", "dropped")


def parse_writers_line(line: str) -> dict | None:
    """capture.c's "# writers: log 0; stores 0; ..." line (the writer gate's run totals, src/readable/core/fe_writer.h
    FE_WT_*) -> {key: count}; None when the line is not that line or a count is not a number."""
    if not line.startswith("# writers:"):
        return None
    out = {}
    for part in line[len("# writers:"):].split(";"):
        k, _, v = part.strip().rpartition(" ")
        if not k or not v.isdigit():
            return None
        out[k] = int(v)
    return out if all(k in out for k in WRITER_KEYS) else None


def writers_problem(w: dict | None) -> str | None:
    """A capture never runs a writer (the gate refuses in capture mode): any store, log entry or session in a capture
    run's totals is a failure. No line at all (a library built before round 8) is not a failure, only unreported."""
    if not w:
        return None
    if w.get("stores") or w.get("log") or w.get("sessions"):
        return (f"the writer gate stored in a capture run (stores {w.get('stores')}, log {w.get('log')}, sessions "
                f"{w.get('sessions')}): no writer may run in capture mode")
    return None


def read_capture_summary(path: str) -> dict:
    """One summary.tsv (capture.c fe_cap_write_summary): {"functions": rows with records > 0, "records",
    each verdict column summed, "bad": the sum of the CAPTURE_BAD columns, "bad_functions": [address, ...],
    "writers": the writer gate's run totals from the "# writers:" line, or None when the library wrote none}."""
    out: dict = {"functions": 0, "records": 0, "bad": 0, "bad_functions": [], "met": [], "writers": None}
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = [ln.rstrip("\n") for ln in fh]
    for ln in raw:
        w = parse_writers_line(ln)
        if w is not None:
            out["writers"] = w
    lines = [ln for ln in raw if ln.strip() and not ln.startswith("#")]
    if not lines:
        return out
    head = lines[0].split("\t")
    for ln in lines[1:]:
        cells = dict(zip(head, ln.split("\t")))

        def num(k: str) -> int:
            v = (cells.get(k) or "0").strip()
            return int(v) if v.isdigit() else 0
        recs = num("records")
        out["records"] += recs
        out["functions"] += 1 if recs else 0
        if recs:
            out["met"].append(cells.get("address"))
        bad = 0
        for k in head:
            if k in CAPTURE_SHOWN:
                out[k] = out.get(k, 0) + num(k)
                bad += num(k) if k in CAPTURE_BAD else 0
        out["bad"] += bad
        if bad:
            out["bad_functions"].append(cells.get("address"))
    return out


def capture_totals(paths: list[str]) -> dict:
    """Every summary.tsv of one run (a cheat run in stages writes one per stage), added up; "functions" counts
    each function with records once (a function met in two stages is one function)."""
    tot: dict = {"summary_files": len(paths), "functions": 0, "records": 0, "bad": 0, "bad_functions": [], "met": [],
                 "writers": None}
    for p in paths:
        one = read_capture_summary(p)
        for k, v in one.items():
            if k in ("bad_functions", "met"):
                tot[k] += [a for a in v if a not in tot[k]]
            elif k == "writers":
                if v is not None:  # stages of a cheat run: each is its own process, the totals add
                    tot[k] = {w: (tot[k] or {}).get(w, 0) + v.get(w, 0) for w in WRITER_KEYS}
            elif k != "functions":
                tot[k] = tot.get(k, 0) + v
    tot["functions"] = len(tot["met"])
    return tot


def capture_problem(cap: dict | None) -> str | None:
    """Why a capture run is not a pass (None: it is): no summary.tsv at all, or any bad record."""
    if cap is None:
        return None
    if not cap["summary_files"]:
        return "no summary.tsv (capture wrote nothing)"
    wp = writers_problem(cap.get("writers"))
    if wp:
        return wp
    if cap["bad"]:
        kinds = ", ".join(f"{cap[k]} {k}" for k in CAPTURE_BAD if cap.get(k))
        return (f"{cap['bad']} bad capture record(s): {kinds} in {len(cap['bad_functions'])} function(s) "
                f"{cap['bad_functions'][:6]}")
    return None


def capture_table(rows: list[dict], title: str, say=print) -> dict | None:
    """The per-session table of capture records, one line per run and a total; returns the total."""
    rows = [r for r in rows if r.get("capture") is not None]
    if not rows:
        return None
    cols = ("functions", "records") + CAPTURE_SHOWN
    short = {"functions": "fns", "records": "records", "match": "match", "gave_up": "gave_up",
             "incomplete": "incompl", "mismatch_r0": "mm_r0", "mismatch_regs": "mm_regs", "mismatch_mem": "mm_mem",
             "mismatch_calls": "mm_calls", "b_escaped": "b_esc", "unfaithful": "unfaith", "escaped": "escaped",
             "damaged": "damaged"}
    total = {c: 0 for c in cols}
    say(f"  capture records, {title}:")
    say("    " + f"{'run':<28} {'route':<22} " + " ".join(f"{short[c]:>8}" for c in cols) + "  verdict")
    for r in rows:
        cap = r["capture"]
        for c in cols:
            total[c] += cap.get(c, 0)
        say("    " + f"{r['run'][:28]:<28} {str(r.get('route'))[:22]:<22} "
            + " ".join(f"{cap.get(c, 0):>8}" for c in cols) + f"  {'PASS' if r['ok'] else 'FAIL'}")
    total["bad"] = sum(total[c] for c in CAPTURE_BAD)
    total["writers"] = writers_total(rows)
    say("    " + writers_line(total["writers"]))
    total["runs"], total["failed_runs"] = len(rows), sum(1 for r in rows if not r["ok"])
    total["verdict"] = "PASS" if not total["bad"] and not total["failed_runs"] else "FAIL"
    say("    " + f"{'TOTAL':<28} {str(len(rows)) + ' run(s)':<22} " + " ".join(f"{total[c]:>8}" for c in cols)
        + f"  {total['verdict']}")
    return total


def writers_total(rows: list[dict]) -> dict:
    """The writer gate's totals over a table's capture runs, and the plain verdict read from them."""
    got = [r["capture"].get("writers") for r in rows if r.get("capture") is not None]
    rep_ = [w for w in got if w]
    tot = {k: sum(w.get(k, 0) for w in rep_) for k in WRITER_KEYS}
    tot["reported_runs"], tot["runs"] = len(rep_), len(got)
    if not rep_:
        tot["verdict"] = "NOT REPORTED (library built before the writer totals, round 8)"
    elif tot["stores"] or tot["log"] or tot["sessions"]:
        tot["verdict"] = "WRITER STORED"
    elif len(rep_) < len(got):
        tot["verdict"] = f"no writer stored anything in the {len(rep_)} run(s) that report it ({len(got) - len(rep_)} do not)"
    else:
        tot["verdict"] = "no writer stored anything"
    return tot


def writers_line(t: dict) -> str:
    return (f"writers: {t['verdict']} (stores {t['stores']}, log {t['log']}, sessions {t['sessions']}, refusals "
            f"{t['refusals']} of them {t['mode_refusals']} for the mode, stray {t['stray']}; {t['reported_runs']}/"
            f"{t['runs']} run(s) report it)")


# ------------------------------------------------------------------ verdicts
def determinism_verdict(rows: list[dict], digests: list[dict], metas: list[bytes | None]) -> dict:
    """h4a step 1 for K runs: each against the first, by headless.compare_digests (compare_meta on
    the stripped metadata when both kept it) and equal instruction counts."""
    hl = headless_module()
    if len(rows) < 2:
        return {"verdict": "NOT CHECKED", "pairs": [], "why": "fewer than 2 runs finished"}
    pairs, same_all = [], True
    for i in range(1, len(rows)):
        if not digests[0] or not digests[i]:
            pairs.append({"a": rows[0]["run"], "b": rows[i]["run"], "same": False, "line": "a savestate is missing"})
            same_all = False
            continue
        same, line = hl.compare_digests(digests[0], digests[i], metas[0], metas[i])
        ia, ib = rows[0].get("instructions"), rows[i].get("instructions")
        same = same and ia is not None and ia == ib
        pairs.append({"a": rows[0]["run"], "b": rows[i]["run"], "same": same,
                      "line": f"{line}; instructions {ia} vs {ib}"})
        same_all = same_all and same
    return {"verdict": "DETERMINISTIC" if same_all else "DIVERGED", "pairs": pairs}


def first_hit(markers: dict | None, target: str, current_only: bool = False) -> int | None:
    """The earliest shot frame whose memory markers show target (the current screen, or any live
    process class unless current_only)."""
    best = None
    for f, m in (markers or {}).items():
        if not m:
            continue
        hit = m.get("current") == target or (not current_only and target in (m.get("classes") or []))
        if hit and (best is None or int(f) < best):
            best = int(f)
    return best


def rank_search(rows: list[dict], marker_sets: list[dict | None], target: str, current_only: bool) -> list[dict]:
    """Variants that reached the target, earliest frame first (then fewer inputs, then name); then
    the runs that finished without reaching it, then the failed runs."""
    out = []
    for row, mk in zip(rows, marker_sets):
        hit = first_hit(mk, target, current_only) if row["ok"] else None
        out.append({"run": row["run"], "variant": row.get("variant"), "first_frame": hit, "ok": row["ok"],
                    "inputs": row.get("inputs_count", 0)})
    out.sort(key=lambda x: (x["first_frame"] is None, not x["ok"], x["first_frame"] or 0, x["inputs"], x["run"]))
    return out


# ------------------------------------------------------------------ commands
def print_rows(rows: list[dict], say=print) -> None:
    for r in rows:
        mem = (r.get("memory") or "")[:16] or "-"
        cp = r.get("checkpoints")
        cp = "" if cp is None else f", checkpoints {cp if isinstance(cp, str) else str(len(cp)) + ' missed'}"
        cap = r.get("capture") or {}
        say(f"  {'PASS' if r['ok'] else 'FAIL'}  {r['run']}: {r.get('route')}{' [CHEAT]' if r.get('cheat') else ''}"
            f"{' [' + r['variant'] + ']' if r.get('variant') else ''}"
            f" exit {r['exit_code']}{' (' + r['killed'] + ')' if r.get('killed') else ''}, {r.get('outcome')} after "
            f"{r.get('frames')} frames, boot {r.get('boot_seconds')} s / wall {r['wall_seconds']} s, peak "
            f"{r['peak_mem_mb']} MB, memory {mem}{cp}{', ' + r['setup_error'] if r.get('setup_error') else ''}"
            f"{', CAPTURE FAIL: ' + cap['problem'] if cap.get('problem') else ''}")


def execute(sess: Session, jobs: list[Job], limits: Limits, a, after=None) -> tuple[dict, int]:
    """Stages, runs the pool, collects, checks %APPDATA%, cleans up. after(rows) -> (extra, ok)."""
    before = snapshot(appdata_dirs())
    started = time.time()
    est_gb, est_note = getattr(a, "mem_per_run_gb", None), "given"
    past = None
    if est_gb is None:  # round 9: the measured peak of these routes (+15%), else the old first estimate
        past = past_runs()
        mb, est_note = measured_peak_mb([j.info.get("route") for j in jobs if j.info.get("route")],
                                        (jobs[0].info.get("mode") if jobs else None) or "original", past)
        est_gb = round(mb * MEM_MARGIN / 1024, 3) if mb else 1.5
        est_note += f" -> first estimate {est_gb:g} GB" if mb else " -> first estimate 1.5 GB"
    if getattr(a, "longest_first", False):
        past = past_runs() if past is None else past
        jobs = longest_first(jobs, past, sess.routes)
        sess.say(f"[{sess.name}] longest first: " + ", ".join(j.name for j in jobs))
    run_limits, others, floor = limits, None, None
    cj = getattr(a, "capture_jobs", None)
    if cj:
        top = capture_jobs_cap(cj)
        if top > limits.jobs:
            run_limits = Limits(top, limits.priority, limits.mem_gb, limits.build_jobs, limits.build_priority,
                                limits.notes + [f"--capture-jobs {cj}: up to {top} while no other boot.exe holds the slots"])
            others, floor = other_game_runs, limits.jobs
    pool = Pool(run_limits, mem_per_run_gb=est_gb, reserve_gb=a.reserve_gb, say=sess.say, others=others,
                floor_jobs=floor)
    limits = run_limits
    sess.say(f"[{sess.name}] {len(jobs)} run(s), up to {limits.jobs} at once, {limits.priority}, budget "
             f"{limits.mem_gb:g} GB{' (' + '; '.join(limits.notes) + ')' if limits.notes else ''}; memory {est_note}")
    interrupted = False
    results = []
    try:
        results = pool.run(jobs)
    except KeyboardInterrupt:
        interrupted = True
    wall = round(time.time() - started, 1)
    rows = sess.collect(results)
    extra, ok = after(rows) if (after and not interrupted) else ({}, True)
    sess.cleanup()
    changed = snapshot_diff(before, snapshot(appdata_dirs()))
    honest = [r for r in rows if not r.get("cheat") and not r.get("options")]
    cheat = [r for r in rows if r.get("cheat")]
    opts = [r for r in rows if r.get("options") and not r.get("cheat")]  # tools/harness/options_track.py rule 4
    summary = {"session": sess.name, "command": a.command, "wall_seconds": wall, "limits": limits.as_dict(),
               "pool": pool.stats(), "runs": rows, "interrupted": interrupted, "memory_estimate": est_note,
               "order": [j.name for j in jobs],
               "cheat_runs": [r["run"] for r in cheat],
               "options_runs": [r["run"] for r in opts],
               "appdata": {"checked": appdata_dirs(), "entries": len(before), "unchanged": not changed,
                           "changed": changed[:20]},
               "save_source": rel(sess.save_src) if sess.save_src else sorted(sess.saves_used), **extra}
    # real play and cheat runs (routes with "cheat": true, docs/CHEATS.md) are listed and added up apart, so the
    # real-play numbers stay honest-play only
    if honest:
        if cheat or opts:
            sess.say("  real-play runs:")
        print_rows(honest, sess.say)
    if cheat:
        sess.say("  CHEAT runs (memory poked by the route, docs/CHEATS.md; scored separately):")
        print_rows(cheat, sess.say)
    if opts:
        sess.say("  OPTIONS-track runs (writers armed with an options file, OPTIONS_WIRING section 7; scored separately):")
        print_rows(opts, sess.say)
    totals = {"honest": capture_table(honest, "real-play runs", sess.say),
              "cheat": capture_table(cheat, "CHEAT runs (scored separately)", sess.say)}
    if opts:
        totals["options"] = capture_table(opts, "OPTIONS-track runs (scored separately)", sess.say)
    if any(totals.values()):
        summary["capture_totals"] = totals
        # "no writer stored anything", read directly (docs/WRITERS.md): every capture run of the session, both tracks
        summary["writers"] = writers_total([r for r in rows if r.get("capture") is not None])
    with open(os.path.join(sess.dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    for r in rows:
        if (r.get("capture") or {}).get("problem"):
            sess.say(f"[{sess.name}] CAPTURE FAIL {r['run']} ({r.get('route')}): {r['capture']['problem']}")
    sess.say(f"[{sess.name}] wall {wall} s, at most {pool.max_running} at once, peak per run "
             f"{max([r['peak_mem_mb'] for r in rows] or [0])} MB; %APPDATA% (zakuro, 3dsrecomp) "
             f"{'unchanged' if not changed else 'CHANGED: ' + ', '.join(changed[:3])}; summary {rel(os.path.join(sess.dir, 'summary.json'))}")
    if interrupted:
        return summary, 130
    good = ok and all(r["ok"] for r in rows) and not changed and len(rows) == len(jobs)
    if any(r.get("setup_error") for r in rows) and not any(r["ok"] for r in rows):
        return summary, 3
    return summary, 0 if good else 1


def session_name(a, tag: str) -> str:
    return a.session or f"{tag}-{time.strftime('%Y%m%d-%H%M%S')}"


def only_addresses(spec: str | None) -> str | None:
    """--only: "all" (every override of config/readable/functions.csv) or a comma list of override names or
    addresses -> the FE_CAPTURE_ONLY list (addresses, Thumb bit cleared as capture.c keys them)."""
    if not spec:
        return None
    sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
    import check as rcheck  # noqa: E402  (the readable registry)
    reg = [r for r in rcheck.registry() if r["kind"].strip() == "override"]
    by_name = {r["name"]: r for r in reg}
    by_addr = {int(r["address"], 16) & ~1: r for r in reg}
    if spec == "all":
        picked = list(reg)
    else:
        picked = []
        for item in spec.split(","):
            item = item.strip()
            r = by_name.get(item) or (by_addr.get(int(item, 16) & ~1) if re.fullmatch(r"0x[0-9A-Fa-f]{1,8}", item) else None)
            if r is None:
                raise Stop(f"--only: {item} is not a readable override (config/readable/functions.csv)")
            picked.append(r)
    return ",".join(f"0x{int(r['address'], 16) & ~1:08X}" for r in picked)


# round 9: the default run timeout grows with the route's length and with how many runs share the PC (round 8: the
# six longest routes, 78,900-162,800 frames, hit the old flat 900 s with 12 capture runs at once; at 6 at once with
# --timeout 3600 they passed in up to 1,309 s wall). Seconds per frame at 6 runs at once, measured-plus-margin:
TIMEOUT_FLOOR, TIMEOUT_CAP, TIMEOUT_BASE = 900.0, 4 * 3600.0, 120.0
TIMEOUT_PER_FRAME = {"capture": 0.012, "original": 0.006}
TIMEOUT_REF_JOBS = 6


def run_timeout(route: dict, mode: str, at_once: int, given: float | None = None) -> float:
    """--timeout when given (a positive number); else 120 s + frames x seconds-per-frame(mode), times at_once / 6 when
    more than 6 runs share the PC, never below 900 s or above 4 h. This is boot.exe's limit inside the worker; the
    pool's wall limit for the worker is this + 120 s (Session.job)."""
    if given:
        return float(given)
    frames = int(route.get("frames") or 0)
    per = TIMEOUT_PER_FRAME.get(mode, TIMEOUT_PER_FRAME["capture"])
    load = max(1.0, at_once / TIMEOUT_REF_JOBS)
    return float(min(TIMEOUT_CAP, max(TIMEOUT_FLOOR, TIMEOUT_BASE + frames * per * load)))


def at_once_for(a, limits: Limits, n_jobs: int) -> int:
    cj = getattr(a, "capture_jobs", None)
    top = max(limits.jobs, capture_jobs_cap(cj)) if cj else limits.jobs
    return max(1, min(top, n_jobs))


def cmd_runs(a, limits: Limits) -> int:
    sess = Session(session_name(a, "runs"), a.save, a.keep, lib=getattr(a, "lib", None))
    names = a.route or ["title"]
    for n in names:
        if n not in sess.routes:
            raise Stop(f"no route {n} in config/harness/routes.json")
    if getattr(a, "capture_jobs", None) and a.mode != "capture":
        raise Stop("--capture-jobs is for --mode capture")
    if a.store_keep and (a.mode != "capture" or not a.only):
        raise Stop("--store-keep needs --mode capture and --only (capture.c stores only a named working set)")
    only = only_addresses(a.only) if a.mode == "capture" else None
    if a.only and a.mode != "capture":
        raise Stop("--only is for --mode capture")
    sess.stage()
    jobs, i = [], 0
    at_once = at_once_for(a, limits, len(names) * a.copies)
    for n in names:
        for k in range(a.copies):
            i += 1
            jobs.append(sess.job(f"{sess.name}-{i}", n, sess.routes[n], a.mode, a.markers,
                                 timeout=run_timeout(sess.routes[n], a.mode, at_once, a.timeout),
                                 info={"copy": k + 1}, only=only, store="keep" if a.store_keep else False))
    return execute(sess, jobs, limits, a)[1]


def cmd_determinism(a, limits: Limits) -> int:
    if a.copies < 2:
        raise Stop("determinism: --copies 2 or more")
    route = a.route[0] if a.route else "title"
    rc_all, summaries = 0, []
    for tag, lim in (("par", limits), ("ser", Limits(1, limits.priority, limits.mem_gb, notes=["one after another"]))) \
            if a.serial_too else (("par", limits),):
        sess = Session(session_name(a, "det") + ("-" + tag if a.serial_too else ""), a.save, a.keep,
                       lib=getattr(a, "lib", None))
        if route not in sess.routes:
            raise Stop(f"no route {route} in config/harness/routes.json")
        sess.stage()
        jobs = [sess.job(f"{sess.name}-{k + 1}", route, sess.routes[route], a.mode, keep_meta=True,
                         timeout=run_timeout(sess.routes[route], a.mode, min(lim.jobs, a.copies), a.timeout))
                for k in range(a.copies)]

        def after(rows, sess=sess):
            done = [r for r in rows if r["ok"]]
            digests = []
            for r in done:
                with open(os.path.join(sess.dir, "results", f"{r['run']}.json"), encoding="utf-8") as fh:
                    digests.append(json.load(fh)["run_json"].get("state"))
            v = determinism_verdict(done, digests, [sess.meta(r["run"]) for r in done])
            if len(done) != len(rows):
                v = dict(v, verdict="NOT CHECKED" if len(done) < 2 else v["verdict"],
                         failed=[r["run"] for r in rows if not r["ok"]])
            for p in v["pairs"]:
                sess.say(f"  {p['a']} vs {p['b']}: {p['line']}: {'same' if p['same'] else 'DIFFERENT'}")
            sess.say(f"[{sess.name}] determinism ({len(done)} x {route}, {a.mode}): {v['verdict']}")
            return {"route": route, "determinism": v}, v["verdict"] == "DETERMINISTIC" and len(done) == len(rows)

        summary, rc = execute(sess, jobs, lim, a, after)
        summaries.append(summary)
        rc_all = rc_all or rc
        if rc == 130:
            return rc
    if a.serial_too and len(summaries) == 2:
        par, ser = summaries
        mem = {r.get("memory") for s in summaries for r in s["runs"]}
        speed = round(ser["wall_seconds"] / par["wall_seconds"], 2) if par["wall_seconds"] else None
        line = (f"side by side {par['wall_seconds']} s vs one after another {ser['wall_seconds']} s: x{speed}; "
                f"memory hash {'the same in all ' + str(2 * a.copies) + ' runs' if len(mem) == 1 else 'NOT the same: ' + str(len(mem)) + ' values'}")
        print(f"[speedup] {line}")
        with open(os.path.join(OUT, summaries[0]["session"], "summary.json"), "r+", encoding="utf-8") as fh:
            s = json.load(fh)
            s["speedup"] = {"parallel_s": par["wall_seconds"], "serial_s": ser["wall_seconds"], "factor": speed,
                            "serial_session": ser["session"], "one_memory_hash": len(mem) == 1}
            fh.seek(0)
            json.dump(s, fh, indent=1)
            fh.truncate()
        if len(mem) != 1:
            rc_all = rc_all or 1
    return rc_all


def parse_variants(a, base: dict) -> list[tuple[str, str]]:
    out = []
    items = list(a.variant or [])
    if a.variants:
        with open(a.variants, encoding="utf-8") as fh:
            data = json.load(fh)
        items += [f"{k}={v}" for k, v in (data.items() if isinstance(data, dict) else enumerate(data, 1))]
    for k, item in enumerate(items, 1):
        name, _, inp = item.partition("=") if "=" in item and not re.match(r"^\d+:", item) else (f"v{k}", "", item)
        inp = inp.strip()
        if inp.startswith("+"):
            inp = base["input"] + "," + inp[1:].strip().lstrip(",")
        if not re.fullmatch(NAME_RX, name):
            raise Stop(f"variant name {name}: letters, digits, _ . - only")
        out.append((name, inp))
    if len({n for n, _ in out}) != len(out):
        raise Stop("variant names must differ")
    if not out:
        raise Stop("search: give --variant NAME=INPUT (INPUT starting with + is added to the route's input)")
    return out


def cmd_search(a, limits: Limits) -> int:
    sess = Session(session_name(a, "search"), a.save, a.keep)
    rname = a.route[0] if a.route else None
    if rname not in sess.routes:
        raise Stop(f"search: --route must name a route of config/harness/routes.json (got {rname})")
    base = sess.routes[rname]
    variants = parse_variants(a, base)
    frames = a.frames or int(base["frames"])
    shots = [int(s) for s in a.shots.split(",")] if a.shots else list(base["shots"])
    if len(shots) > a.max_shots:
        raise Stop(f"search: {len(shots)} shots; each marker dump is about 56 MiB of scratch per run (cap "
                   f"--max-shots {a.max_shots})")
    sess.stage()
    jobs, counts = [], {}
    for name, inp in variants:
        route = {k: v for k, v in base.items() if k not in ("verified",)}
        route.update(input=inp, frames=frames, shots=shots,
                     save_at=int(base["save_at"]) if int(base["save_at"]) < frames else frames - 10,
                     about=f"parallel search variant {name} of {rname}")
        run = f"{sess.name}-{name}"
        counts[run] = len(inp.split(","))
        jobs.append(sess.job(run, rname, route, a.mode, markers=True,
                             timeout=run_timeout(route, a.mode, max(1, min(limits.jobs, len(variants))), a.timeout),
                             info={"variant": name, "input": inp}))

    def after(rows):
        sets = []
        for r in rows:
            r["inputs_count"] = counts.get(r["run"], 0)
            with open(os.path.join(sess.dir, "results", f"{r['run']}.json"), encoding="utf-8") as fh:
                sets.append(json.load(fh)["run_json"].get("markers"))
        ranked = rank_search(rows, sets, a.target, a.current_only)
        for i, x in enumerate(ranked):
            where = f"frame {x['first_frame']}" if x["first_frame"] is not None else "not reached"
            sess.say(f"  {i + 1}. {x['variant']}: {where}{'' if x['ok'] else ' (run failed)'}")
        win = ranked[0] if ranked and ranked[0]["first_frame"] is not None else None
        sess.say(f"[{sess.name}] target {a.target}: " + (f"first reached by {win['variant']} at frame "
                                                        f"{win['first_frame']}" if win else "reached by no variant"))
        return {"target": a.target, "current_only": a.current_only, "shots": shots, "frames": frames,
                "ranking": ranked, "winner": win and win["variant"],
                "inputs": {n: i for n, i in variants}}, win is not None

    summary, rc = execute(sess, jobs, limits, a, after)
    if rc == 1 and summary.get("winner"):
        rc = 0  # a variant that misses the target, or fails, is an answer of the search, not a failure
    return rc


class OsLock:
    """An exclusive lock held by the operating system for this process (round 6; review: an O_CREAT|O_EXCL lock
    file is empty between its creation and the pid write, and a waiter that read it then took it for a dead
    holder's and removed it, so two holders could overlap). The lock is a byte range far past the pid text
    (msvcrt.locking on Windows, fcntl.flock elsewhere): the OS frees it when the holder closes the file or dies,
    so there is no stale lock to take over and no window between creating the file and owning it. The pid
    written at offset 0 is only for messages. After the lock is taken, the path must still name the file this
    process locked (another holder may have removed it and a third made a new one): else it tries again."""

    REGION = 1 << 20  # the locked byte: past the pid text, so others can still read who holds it

    def __init__(self, path: str):
        self.path, self.fd = path, None

    def try_acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        while True:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
            try:
                os.lseek(fd, self.REGION, 0)
                if WIN:
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                return False
            try:
                same = os.path.samestat(os.fstat(fd), os.stat(self.path))
            except OSError:
                same = False
            if not same:  # removed (and maybe made again) between our open and our lock: take the new one
                self._unlock(fd)
                continue
            os.lseek(fd, 0, 0)
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode())
            self.fd = fd
            return True

    def holder(self) -> int:
        try:
            with open(self.path, "rb") as fh:
                return int(fh.read(32).decode("ascii", "replace").strip() or 0)
        except (OSError, ValueError):
            return 0

    def _unlock(self, fd: int) -> None:
        try:
            os.lseek(fd, self.REGION, 0)
            if WIN:
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)

    def release(self, remove: bool = True) -> None:
        """Frees the lock; removes the file when nobody else has it open (Windows refuses to remove an open
        file, so a waiter's handle keeps it; elsewhere it is unlinked while still locked, before closing)."""
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        if remove and not WIN:
            try:
                os.remove(self.path)
            except OSError:
                pass
        self._unlock(fd)
        if remove and WIN:
            try:
                os.remove(self.path)
            except OSError:
                pass


def acquire_build_lock(lock: str, say=print, wait: float = 3600) -> OsLock:
    """One build at a time (an OsLock: freed by the OS if the holder dies, so a stale file is simply free)."""
    held = OsLock(lock)
    started, told = time.time(), -1
    while not held.try_acquire():
        if time.time() - started > wait:
            raise Stop(f"another build (process {held.holder()}) holds {rel(lock)}")
        if int(time.time() - started) // 30 != told:
            told = int(time.time() - started) // 30
            say(f"[build] waiting for build process {held.holder()} (builds run one at a time)")
        time.sleep(0.5)
    return held


def run_build(args: list[str], limits: Limits, cmd: list[str] | None = None, say=print,
              lock: str | None = None, log: str | None = None) -> int:
    """tools/harness/build.py (or cmd) as one below-normal child in a job object, one build at a time
    (a lock file shared by every parallel.py). Builds the engine only when asked: the owner's OK first."""
    lock = lock or os.path.join(OUT, "build.lock")
    held = acquire_build_lock(lock, say)
    try:
        os.makedirs(OUT, exist_ok=True)
        log = log or os.path.join(OUT, f"build-{time.strftime('%Y%m%d-%H%M%S')}.log")
        job = Job("build", cmd or [sys.executable, os.path.join(HERE, "build.py"), *args], cwd=ROOT,
                  log_file=log, timeout=3 * 3600)
        lim = Limits(limits.build_jobs, limits.build_priority, max(limits.mem_gb, 16))
        pool = Pool(lim, mem_per_run_gb=1, run_cap_gb=0, priority=limits.build_priority, say=say, tick=0.5)
        res = pool.run([job])
        say(f"[build] log {rel(log)}")
        return res[0]["exit_code"] if res else 1
    finally:
        held.release()


FAKE_CHILD = """import os, subprocess, sys, time
pids, secs = sys.argv[1], float(sys.argv[2])
if len(sys.argv) == 3:  # the child: start one grandchild, record both pids, sleep
    g = subprocess.Popen([sys.executable, __file__, pids, "120", "grandchild"])
os.makedirs(pids, exist_ok=True)  # one file per process: appends from several processes can lose lines
open(os.path.join(pids, str(os.getpid())), "w").close()
time.sleep(secs)
"""


def cmd_fake(a, limits: Limits) -> int:
    """For test_parallel.py only: N fake children (sleep, record pid files in --pids DIR) in a session folder, so the
    Ctrl-C cleanup can be tested on the real command line."""
    sdir = os.path.join(OUT, a.session or "fake")
    if os.path.isdir(sdir):
        rmtree_own(sdir)
    os.makedirs(os.path.join(sdir, "jobs"))
    script = os.path.join(sdir, "fake_child.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(FAKE_CHILD)
    jobs = []
    for k in range(a.copies):
        jd = os.path.join(sdir, "jobs", f"f{k}")
        os.makedirs(jd)
        jobs.append(Job(f"f{k}", [sys.executable, script, os.path.abspath(a.pids), str(a.sleep)], cwd=jd,
                        log_file=os.path.join(jd, "log.txt")))
    try:
        Pool(limits, mem_per_run_gb=0.05, reserve_gb=0).run(jobs)
    except KeyboardInterrupt:
        rmtree_own(sdir)
        print("[fake] interrupted: children stopped, scratch removed")
        return 130
    rmtree_own(sdir)
    return 0


def cmd_pack(rest: list[str], saves: str | None = None) -> dict:
    """pack SESSION RUN NAME: the in-game save a finished --keep run left in its job folder, packed by
    headless.pack_save (the same checks: a Completed run, save files newer than nothing after run.json, the
    size cap) into build/harness/saves/NAME.zip, as `headless.py --pack` does for build/harness/ runs."""
    extdata = rest[3:] == ["extdata"]  # pack SESSION RUN NAME extdata: also the game's extra data (a battle save)
    if len(rest) != 3 and not extdata:
        raise Stop("pack: give SESSION RUN NAME [extdata] (a run kept with --keep)")
    session, run, name = rest[:3]
    for part in (session, run):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", part):
            raise Stop(f"pack: {part}: letters, digits, _ . - only")
    job = os.path.join(OUT, session, "jobs", run)
    if not os.path.isdir(os.path.join(job, "data", run)):
        raise Stop(f"pack: {rel(job)}: no kept job folder (run with --keep)")
    hl = headless_module()  # the job folder is the run's build root, as in worker()
    old = (hl.BUILD, hl.RUNS, hl.SAVES)
    try:
        hl.BUILD, hl.RUNS = job, os.path.join(job, "runs")
        if saves:
            hl.SAVES = saves
        return hl.pack_save(os.path.join(job, "data", run), name, extdata=extdata)
    except hl.Stop as e:
        raise Stop(f"pack: {e}")
    finally:
        hl.BUILD, hl.RUNS, hl.SAVES = old


def main(argv: list[str]) -> int:
    if argv[:1] == ["--worker"] and len(argv) == 2:
        return worker(argv[1])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["runs", "determinism", "search", "build", "clean", "limits", "pack",
                                       "keep-empty", "_fake"])
    ap.add_argument("rest", nargs="*", help="build: arguments for build.py (after --)")
    ap.add_argument("--route", action="append", help="a route of config/harness/routes.json (repeatable)")
    ap.add_argument("--copies", type=int, default=1, help="runs per route (determinism: K copies, default 3)")
    ap.add_argument("--mode", default="original", choices=["original", "capture"])
    ap.add_argument("--markers", action="store_true", help="runs: memory markers and checkpoint hits")
    ap.add_argument("--save", default=None,
                    help=f"start save for every run (headless --save rules; only read); default: each route's "
                         f"own \"save\", else {DEFAULT_SAVE}")
    ap.add_argument("--jobs", type=int, help="at most this many at once (only lowers the budget)")
    ap.add_argument("--session", help="folder name below build/parallel/ (default: command + time)")
    ap.add_argument("--keep", action="store_true", help="keep the job folders (default: deleted)")
    ap.add_argument("--only", help="runs --mode capture: capture only these overrides (names or addresses, comma "
                                   "list, or 'all')")
    ap.add_argument("--store-keep", action="store_true",
                    help="runs --mode capture --only ...: keep every record (FE_CAPTURE_STORE=keep) in records/<run>/")
    ap.add_argument("--timeout", type=float, default=None,
                    help="seconds per run (boot.exe); default scaled by the route's frames and the runs at once "
                         "(run_timeout: 120 s + frames x 0.012 s capture / 0.006 s original, x runs/6 above 6; "
                         "900 s to 4 h); the worker itself is killed 120 s after this")
    ap.add_argument("--mem-per-run-gb", type=float, default=None,
                    help="first estimate of one run's memory (default: the measured peak of the same route and mode "
                         "+15%%, from earlier summary.json files; 1.5 when never measured)")
    ap.add_argument("--lib", help="runs/determinism: this capture library instead of build/harness/lib (copied first)")
    ap.add_argument("--longest-first", action="store_true",
                    help="runs: start the routes that took longest last time first (default: the given order)")
    ap.add_argument("--capture-jobs", type=int,
                    help="runs --mode capture: up to N at once (at most resources.json night.max_parallel_runs) while "
                         "no other boot.exe holds the slots; never below the normal cap")
    ap.add_argument("--reserve-gb", type=float, default=2.0, help="free physical memory left alone")
    ap.add_argument("--serial-too", action="store_true", help="determinism: also run them one after another, "
                                                              "compare wall times")
    ap.add_argument("--variant", action="append", help="search: NAME=INPUT (+INPUT: added to the route's input)")
    ap.add_argument("--variants", help="search: a JSON file {name: input}")
    ap.add_argument("--target", help="search: the process class to reach (config/harness/markers.json names)")
    ap.add_argument("--current-only", action="store_true", help="search: the target must be the current screen")
    ap.add_argument("--shots", help="search: shot frames (comma list) where markers are read")
    ap.add_argument("--frames", type=int, help="search: run length")
    ap.add_argument("--max-shots", type=int, default=12)
    ap.add_argument("--pids", help=argparse.SUPPRESS)
    ap.add_argument("--sleep", type=float, default=60, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if WIN:  # Ctrl-Break (and a console close) stops the children like Ctrl-C does
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    try:
        limits = load_limits(cli_jobs=a.jobs)
        if a.command == "limits":
            print(json.dumps(dict(limits.as_dict(), free_memory_gb=round(free_memory() / GB, 1),
                                  appdata_checked=appdata_dirs()), indent=1))
            return 0
        if a.command == "clean":
            if os.path.isdir(OUT):
                probe = OsLock(os.path.join(OUT, "build.lock"))
                if os.path.exists(probe.path) and not probe.try_acquire():
                    raise Stop("a build is running (build/parallel/build.lock)")
                probe.release()
                shutil.rmtree(OUT)
            print(f"removed {rel(OUT)}")
            return 0
        if a.command == "build":
            return run_build(a.rest, limits)
        if a.command == "pack":
            print(json.dumps(cmd_pack(a.rest), indent=1))
            return 0
        if a.command == "keep-empty":
            if len(a.rest) != 1:
                raise Stop("keep-empty SESSION")
            keep_empty(a.rest[0])
            return 0
        if a.command == "_fake":
            return cmd_fake(a, limits)
        if a.command == "determinism":
            a.copies = a.copies if a.copies > 1 else 3
            return cmd_determinism(a, limits)
        if a.command == "search":
            if not a.target:
                raise Stop("search: give --target CLASS")
            return cmd_search(a, limits)
        return cmd_runs(a, limits)
    except Stop as e:
        print(f"parallel: SETUP: {e}")
        return 3
    except KeyboardInterrupt:
        print("parallel: interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
