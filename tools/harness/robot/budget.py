"""The owner's budget for the look-ahead helpers (round 5, review 4: bd.sh started probe.py outside parallel.py).

A look-ahead step loads the savestate the step before it kept, so a chain is one run at a time by nature, and
parallel.py's pool cannot run it (its runs start from a save zip, not a savestate: no ZAKURO_LOAD). So the
helpers stay outside the pool, and every game run they make (probe.py, auto.py; the shell helpers and act.py /
et2.py call those two) goes through enter() here first:

- priority: the class of config/harness/resources.json, FEF_ROBOT_PRIORITY honoured (parallel.load_limits, read
  only); set on this Python process, and boot.exe inherits a below-normal or idle class;
- one at a time: build/harness/robot/probe.lock, an OS-held lock (parallel.OsLock, round 6: the OS frees it when
  the holder dies, so there is no stale lock to take over; the old O_CREAT|O_EXCL file was empty for a moment
  after its creation, and a waiter that read it then removed it as a dead holder's and both ran), held only
  around one game run (`with budget.run_slot():` around headless.run), so two look-aheads never overlap and a
  helper that starts another helper between its runs (act.py -> auto.py) never waits on itself. A look-ahead is one more run beside a parallel.py session, which does not count
  it: keep such a session one job under the cap (FEF_ROBOT_JOBS) while looking ahead;
- APPDATA: boot_env() gets APPDATA = build/harness/robot/appdata, never the owner's %APPDATA% (headless.py
  already points LOCALAPPDATA below build/).
"""
import atexit
import ctypes
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.append(os.path.join(ROOT, "tools", "harness"))
import parallel as par  # noqa: E402  (load_limits, PRIORITY, pid_alive; nothing written)

ROBOT = os.path.join(ROOT, "build", "harness", "robot")
LOCK = os.path.join(ROBOT, "probe.lock")
APPDATA = os.path.join(ROBOT, "appdata")
_held = False
_lock: "par.OsLock | None" = None


def _release() -> None:
    global _lock
    if _lock is not None:
        _lock.release()
        _lock = None


def enter() -> par.Limits:
    """Priority class and the APPDATA folder (once per process is enough; calling it again is harmless)."""
    limits = par.load_limits()
    if os.name == "nt":
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p  # the pseudo-handle -1: as a C int it is refused on 64-bit
        k32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        if not k32.SetPriorityClass(k32.GetCurrentProcess(), par.PRIORITY.get(limits.priority, par.PRIORITY["below_normal"])):
            print("robot: could not lower the priority class", file=sys.stderr)
    os.makedirs(APPDATA, exist_ok=True)
    return limits


class run_slot:
    """The one-at-a-time lock around one game run."""

    def __init__(self, wait: float = 3600):
        self.wait = wait

    def __enter__(self):
        global _held, _lock
        enter()
        t0 = time.time()
        lock = par.OsLock(LOCK)
        while not lock.try_acquire():
            if time.time() - t0 > self.wait:
                sys.exit(f"robot: {LOCK} held by pid {lock.holder()} for {self.wait:.0f} s")
            time.sleep(0.5)
        _lock = lock
        if not _held:
            atexit.register(_release)  # a run stopped by an exception still frees it (the OS does too)
            _held = True
        return self

    def __exit__(self, *exc):
        _release()
        return False


def env_patch(env: dict) -> dict:
    """boot.exe's environment: APPDATA below build/."""
    env["APPDATA"] = APPDATA
    return env
