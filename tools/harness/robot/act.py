"""Scratch: one unit action on the chain's state, step by step with checks.
usage: act.py CHAIN UX,UY DX,DY [attack[:N] | wait | pair | menu:K] [--save ZIP]
attack:N presses RIGHT N times on the target choice before confirming.
Prints the board after. Stops (exit 2) when a step lands on an unexpected screen."""
import os, sys, struct, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import auto  # noqa
RUNS = auto.hl.RUNS
HUMAN = "map__SequenceHuman__anonymous_namespace__ProcSequence"
CMD = "map__anonymous_namespace__UnitCommand"
FORE = "map__anonymous_namespace__ProcSequence"
log = None


def board(run):
    d = os.path.join(RUNS, run)
    heap = open(os.path.join(d, "zakuro-dump-0x30000000.bin"), "rb").read()
    g = open(os.path.join(d, "zakuro-dump-0x006D7000.bin"), "rb").read()
    rd = lambda a, n: heap[a - 0x30000000:a - 0x30000000 + n] if 0 <= a - 0x30000000 < len(heap) - n else None
    pool = struct.unpack_from("<II", g, 0x2F40)
    cp = struct.unpack_from("<I", g, 0x198)[0]
    cur = struct.unpack("<ii", rd(cp, 8)) if rd(cp, 8) else None
    units = []
    for f in range(3):
        fb = rd(pool[1] + f * 12, 12)
        u = struct.unpack("<I", fb[:4])[0] if fb else 0
        while u:
            ub = rd(u, 0x140)
            units.append((f, ub[0xF4], ub[0xF5], ub[0xF3], struct.unpack_from("<I", ub, 8)[0]))
            u = struct.unpack("<I", ub[0x14:0x18])[0]
    return cur, units


def step(chain, presses, wait=60, dump=True):
    """presses: list of buttons, 20 frames apart, from the state's frame + 10."""
    f = auto.state_frame(chain)
    t = f + 10
    out = []
    for b in presses:
        out.append(f"{t}:{b}")
        t += 22
    end = t + wait
    r = auto.segment(chain, chain, f, end, ",".join(out) if out else None, dump="0x006D7000,16384" if dump else None)
    if out:
        with open(os.path.join(auto.STATES, chain + ".inputs"), "a") as fh:
            fh.write(",".join(out) + "\n")
    cur, cls = auto.current(r, end - 1)
    if "TalkKeyWait" in cls:
        cur = "TalkKeyWait"
    return cur, cls


def settle(chain, stops, max_=40):
    """auto.py loop until one of stops."""
    p = subprocess.run([sys.executable, os.path.join(HERE, "auto.py"), chain, chain, "--max", str(max_), "--seg", "60",
                        "--stop", *stops, "map__DialogYesNo"], capture_output=True, text=True, env=os.environ)
    last = p.stdout.strip().splitlines()[-1]
    return last.split("current ")[-1] if "current" in last else last


def moves(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    return ["RIGHT" if dx > 0 else "LEFT"] * abs(dx) + ["DOWN" if dy > 0 else "UP"] * abs(dy)


def show(chain):
    cur, units = board(chain)
    print("cursor", cur)
    for u in units:
        print("  ", "PEA"[u[0]], (u[1], u[2]), "hp", u[3], f"{u[4]:x}")
    return cur, units


def main():
    chain, us, ds, what = sys.argv[1], sys.argv[2], sys.argv[3], (sys.argv[4] if len(sys.argv) > 4 else "wait")
    u = tuple(int(x) for x in us.split(","))
    cands = [tuple(int(x) for x in c.split(",")) for c in ds.split(";")]
    d = cands[0]
    c, cls = step(chain, [], wait=4)
    cur, units = board(chain)
    if c != HUMAN:
        print("not in player phase:", c); sys.exit(2)
    # select
    c, cls = step(chain, moves(cur, u) + ["A"], wait=50)
    if c in ("TalkKeyWait", "ProcTutorialViewer", "TalkUtil__ProcBind"):
        c = settle(chain, [HUMAN, CMD])
    if c != HUMAN:
        print("after select:", c); sys.exit(2)
    # move
    prev = u
    for d in cands:
        c, cls = step(chain, moves(prev, d) + ["A"], wait=70)
        if c in ("TalkKeyWait", "ProcTutorialViewer", "TalkUtil__ProcBind", "map__ProcMoveRoute"):
            c = settle(chain, [CMD, HUMAN])
        if c == CMD:
            print("moved to", d)
            break
        prev = d
    if c != CMD:
        print("after move:", c); sys.exit(2)
    if what == "show":  # stop at the command menu (no input appended past it)
        os.system(f'cp "{os.path.join(auto.hl.BUILD, "shots", chain, "checkpoints.png")}" "{os.path.join(auto.hl.BUILD, "robot", "cmd.png")}"')
        print("command menu up"); return
    if what.startswith("attack"):
        n = int(what.split(":")[1]) if ":" in what else 0
        c, cls = step(chain, ["A"], wait=70)
        if c in ("TalkKeyWait", "ProcTutorialViewer", "TalkUtil__ProcBind"):
            c = settle(chain, [FORE, HUMAN])
        if c != FORE:
            print("after attack:", c); sys.exit(2)
        c, cls = step(chain, ["RIGHT"] * n, wait=40)
        os.system(f'cp "{os.path.join(auto.hl.BUILD, "shots", chain, "checkpoints.png")}" "{os.path.join(auto.hl.BUILD, "robot", "fore.png")}"')
        if "--dry" in sys.argv:
            print("forecast up (dry)"); return
        c, cls = step(chain, ["A"], wait=20, dump=False)
    elif what.startswith("menu:"):
        k = int(what.split(":")[1])
        c, cls = step(chain, ["DOWN"] * k + ["A"], wait=60)
        print("menu pick ->", c)
        return
    else:  # wait: last item
        c, cls = step(chain, ["UP", "A"], wait=30, dump=False)
    c = settle(chain, [HUMAN, "ChapterFileMenu", "GameDialogYesNo", CMD], 60)
    print("now:", c)
    step(chain, [], wait=4)
    show(chain)


if __name__ == "__main__":
    main()
