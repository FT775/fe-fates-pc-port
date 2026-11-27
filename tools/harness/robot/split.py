"""Look-ahead helper for the Conquest / Revelation chains (round 8, area "split"; docs/ROUTES_SPLIT.md).

It reuses the existing helpers (auto.segment, act.step / act.board / act.main) without changing them, with three
differences so that it can run beside the Birthright agent's look-aheads:

- savestates in build/harness/robot/states/split/ (game memory, build/ only), never the shared states/ folder;
- run names are the chain names (cq*, rv*), never the shared fixed names (look, lk, probe);
- the one-at-a-time lock is replaced by a small pool of OS-held locks of this area (SPLIT_SLOTS, default 2:
  one per chain), counted inside this area's FEF_ROBOT_JOBS share. Priority and APPDATA stay budget.py's.

usage:
  split.py base CHAIN SAVE END INPUT          run from a save zip to END (state at END-1), INPUT absolute frames
  split.py fork NEW SRC                       copy a chain (state, frame, inputs, save)
  split.py press CHAIN "BTN BTN W30 ..." [GAP] [WAIT]   press buttons GAP frames apart (W<n> = wait n frames)
  split.py auto CHAIN [--max N] [--seg F] [--stop CLASS ...]   answer talk / tutorial / movie screens
  split.py look CHAIN [-m] [-t]               board (units, cursor; -m terrain grid, -t dragon veins)
  split.py act CHAIN UX,UY DX,DY[;DX,DY] attack[:N]|wait|pair|show|menu:K [--dry]
  split.py endturn CHAIN X,Y                  cursor to an empty tile, system menu, End, autopilot
  split.py input CHAIN                        the stitched input of the chain (for a route)
"""
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import budget  # noqa: E402
import auto  # noqa: E402
import act  # noqa: E402

par = budget.par
STATES = os.path.join(budget.ROBOT, "states", "split")
os.makedirs(STATES, exist_ok=True)
SLOTS = max(1, min(6, int(os.environ.get("SPLIT_SLOTS", "2") or 2)))


class pool_slot:
    """One of SLOTS OS-held locks of this area (instead of budget's single shared probe.lock)."""

    def __init__(self, wait: float = 3600):
        self.wait = wait
        self.lock = None

    def __enter__(self):
        budget.enter()
        t0 = time.time()
        while True:
            for k in range(SLOTS):
                lk = par.OsLock(os.path.join(STATES, f"slot-{k}.lock"))
                if lk.try_acquire():
                    self.lock = lk
                    return self
            if time.time() - t0 > self.wait:
                sys.exit("split: no free slot")
            time.sleep(0.5)

    def __exit__(self, *exc):
        if self.lock is not None:
            self.lock.release()
            self.lock = None
        return False


budget.run_slot = pool_slot
auto.STATES = STATES


def save_of(chain):
    p = os.path.join(STATES, chain + ".save")
    return open(p).read().strip() if os.path.isfile(p) else "new-game-empty"


def use_save(chain):
    os.environ["AUTO_SAVE"] = save_of(chain)


def settle(chain, stops, max_=40, seg=60):
    """auto.py's loop, in this process (act.settle starts auto.py, which would use the shared folder and lock)."""
    use_save(chain)
    src = chain
    start = auto.state_frame(src)
    r = auto.segment(chain, src, start, start + 3, None)
    cur, cls = auto.current(r, start + 2)
    start += 2
    last = None
    stuck = 0
    log = os.path.join(STATES, chain + ".inputs")
    for _ in range(max_):
        if "TalkKeyWait" in cls and cur not in stops:
            cur = "TalkKeyWait"
        if cur in stops:
            break
        end = start + seg
        btn = auto.ANSWER.get(cur)
        if cur == "ProcTutorialViewer" and "BattleSeq" in cls:
            btn = None
        if cur in ("TalkKeyWait", "TalkUtil__ProcBind", "event__anonymous_namespace__ProcEvent"):
            btn = "A" if last == ("START", cur) else "START"
        if "BattleSeq" in cls and btn == "START":
            btn = "A"
        if cur == "ProcBattleInfo":
            stuck += 1
            if stuck >= 8:
                btn, stuck = "START", 0
        else:
            stuck = 0
        if cur == "map__anonymous_namespace__ProcSequence" and "ProcScene" in cls:
            btn = "A"
        last = (btn, cur)
        press = f"{start + 4}:{btn}" if btn else None
        r = auto.segment(chain, chain, start, end, press)
        if press:
            with open(log, "a") as fh:
                fh.write(press + "\n")
        print(f"  {start}: {cur} -> {btn or 'wait'}", flush=True)
        cur, cls = auto.current(r, end - 1)
        start = end - 1
    print(f"chain {chain} frame {auto.state_frame(chain)} current {cur}")
    return cur


act.settle = settle


def show(chain, flags=()):
    act.step(chain, [], wait=4)
    cur, cls = auto.current(__import__("json").load(open(os.path.join(auto.hl.RUNS, chain, "run.json"))),
                            auto.state_frame(chain))
    print("frame", auto.state_frame(chain), "current", cur)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    out = subprocess.run([sys.executable, os.path.join(HERE, "units.py"), chain, *flags], cwd=budget.ROOT,
                         capture_output=True, text=True, encoding="utf-8", errors="replace", env=env).stdout
    print("\n".join(ln for ln in out.splitlines() if not ln.startswith(("force3", "force4", "force5", "force6", "force7"))))


def backup(chain):
    for ext in (".bin", ".frame", ".inputs"):
        shutil.copyfile(os.path.join(STATES, chain + ext), os.path.join(STATES, chain + ".undo" + ext))


def restore(chain):
    for ext in (".bin", ".frame", ".inputs"):
        shutil.copyfile(os.path.join(STATES, chain + ".undo" + ext), os.path.join(STATES, chain + ext))


def main():
    a = sys.argv[1:]
    cmd = a[0]
    if cmd == "base":
        chain, save, end, inp = a[1], a[2], int(a[3]), a[4]
        with open(os.path.join(STATES, chain + ".save"), "w") as fh:
            fh.write(save)
        open(os.path.join(STATES, chain + ".inputs"), "w").write(inp + "\n")
        os.environ["AUTO_SAVE"] = save
        r = auto.segment(chain, None, 0, end, inp, shots=[end - 1])
        print(r.get("outcome"), "current", auto.current(r, end - 1)[0])
    elif cmd == "fork":
        new, src = a[1], a[2]
        for ext in (".bin", ".frame", ".inputs", ".save"):
            p = os.path.join(STATES, src + ext)
            if os.path.isfile(p):
                shutil.copyfile(p, os.path.join(STATES, new + ext))
        print("forked", new, "from", src, "frame", auto.state_frame(new))
    elif cmd == "press":
        chain, btns = a[1], a[2].split()
        gap = int(a[3]) if len(a) > 3 else 22
        wait = int(a[4]) if len(a) > 4 else 60
        use_save(chain)
        f = auto.state_frame(chain) + 10
        out = []
        for b in btns:
            if b.startswith("W"):
                f += int(b[1:])
                continue
            out.append(f"{f}:{b}")
            f += gap
        end = f + wait
        r = auto.segment(chain, chain, auto.state_frame(chain), end, ",".join(out) if out else None,
                         shots=sorted({int(x.split(":")[0]) + 12 for x in out} | {end - 1}),
                         dump="0x006D7000,16384", scale=int(os.environ.get("SPLIT_SCALE", "2")))
        if out:
            with open(os.path.join(STATES, chain + ".inputs"), "a") as fh:
                fh.write(",".join(out) + "\n")
        for fr, m in sorted(r.get("markers", {}).items(), key=lambda kv: int(kv[0])):
            print(fr, m.get("current"))
        print("sheet", r.get("shots"))
    elif cmd == "auto":
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("chain")
        ap.add_argument("--max", type=int, default=60)
        ap.add_argument("--seg", type=int, default=60)
        ap.add_argument("--stop", nargs="*", default=[act.HUMAN])
        o = ap.parse_args(a[1:])
        settle(o.chain, o.stop, o.max, o.seg)
    elif cmd == "look":
        use_save(a[1])
        show(a[1], a[2:])
    elif cmd == "act":  # a failed step (exit 2) puts the chain back as it was before the action
        use_save(a[1])
        backup(a[1])
        sys.argv = ["act.py"] + a[1:]
        try:
            act.main()
        except SystemExit as e:
            if e.code == 2:
                restore(a[1])
                print("act failed: chain restored to frame", auto.state_frame(a[1]))
            raise
    elif cmd == "endturn":
        chain = a[1]
        use_save(chain)
        t = tuple(int(v) for v in a[2].split(","))
        c, cls = act.step(chain, [], wait=4)
        if c != act.HUMAN:
            print("not player phase:", c)
            sys.exit(2)
        cur, units = act.board(chain)
        if any((u[1], u[2]) == t for u in units):
            print("tile occupied", t)
            sys.exit(2)
        c, cls = act.step(chain, act.moves(cur, t) + ["A"], wait=40)
        if c != "map__anonymous_namespace__SystemMenu":
            print("no system menu:", c)
            sys.exit(2)
        act.step(chain, ["UP", "A"], wait=60, dump=False)
        settle(chain, [act.HUMAN, "map__DialogYesNo", "ChapterFileMenu", "GameDialogYesNo"], 80, 90)
        show(chain)
    elif cmd == "input":
        lines = open(os.path.join(STATES, a[1] + ".inputs")).read().split()
        print(",".join(t for ln in lines for t in ln.split(",") if t))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
