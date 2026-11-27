"""Scratch autopilot (build/ only): from a savestate, advance in short segments and answer the screens
that need no decision (talk, tutorial, movie), stop when the player phase (map__SequenceHuman current)
or an unknown screen is up. Every input is absolute-frame, appended to states/<chain>.inputs so the
whole chain can be replayed from frame 0 later.
usage: auto.py CHAIN FROM_STATE [--max N] [--seg F] [--stop CLASS ...] [--press 'F:BTN,...' --to F]
"""
import os, sys, json, shutil, argparse, re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.append(os.path.join(ROOT, "tools", "harness"))
import headless as hl  # noqa
sys.path.append(HERE)
import budget  # noqa: priority, one look-ahead at a time, APPDATA below build/

STATES = os.path.join(ROOT, "build", "harness", "robot", "states")  # below build/ only (savestates hold game memory)
ANSWER = {  # current class -> button
    "TalkKeyWait": "A", "TalkUtil__ProcBind": "A", "ProcTutorialViewer": "START", "ProcMovie": "START",
    "GameMessage": "A", "event__anonymous_namespace__ProcEvent": "A",
    "map__SequenceCompleteEffect__anonymous_namespace__ProcSequence": "A",
    "anonymous_namespace__EventDialog@00626DB0": None,
}


def state_frame(name):
    with open(os.path.join(STATES, name + ".frame")) as fh:
        return int(fh.read())


def segment(name, src, start, end, inputs, markers=True, shots=None, scale=2, dump=None):
    """Runs from state src (frame start) to end; saves state name at end-1. inputs: 'F:BTN,...'."""
    shots = shots or [end - 1]
    route = {"frames": end, "input": inputs or f"{end + 100}:A", "save_at": end - 1, "shots": shots, "verified": False}
    orig = hl.load_routes.__wrapped__ if hasattr(hl.load_routes, "__wrapped__") else hl.load_routes
    f = lambda path=hl.ROUTES: {**orig(path), "probe": route}
    f.__wrapped__ = orig
    hl.load_routes = f
    oenv = hl.boot_env.__wrapped__ if hasattr(hl.boot_env, "__wrapped__") else hl.boot_env
    def env(*a, **k):
        e = budget.env_patch(oenv(*a, **k))
        if src:
            e["ZAKURO_LOAD"] = os.path.join(STATES, src + ".bin")
        return e
    env.__wrapped__ = oenv
    hl.boot_env = env
    osheet = hl.contact_sheet.__wrapped__ if hasattr(hl.contact_sheet, "__wrapped__") else hl.contact_sheet
    cs = lambda t, fr, o, scale_=2: osheet(t, fr, o, scale)
    cs.__wrapped__ = osheet
    hl.contact_sheet = cs
    with budget.run_slot():
        r = hl.run(name, "probe", "original", save=os.environ.get("AUTO_SAVE", "new-game-empty"), keep_state=True, markers=markers, extra_dump=dump,
               timeout=3600, say=lambda *a: None)
    st = os.path.join(hl.RUNS, name, "state.bin")
    shutil.move(st, os.path.join(STATES, name + ".bin"))
    with open(os.path.join(STATES, name + ".frame"), "w") as fh:
        fh.write(str(end - 1))
    return r


def current(r, frame):
    m = r.get("markers", {}).get(str(frame), {})
    return m.get("current"), m.get("classes", [])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("chain"); ap.add_argument("src")
    ap.add_argument("--max", type=int, default=60); ap.add_argument("--seg", type=int, default=60)
    ap.add_argument("--stop", nargs="*", default=["map__SequenceHuman__anonymous_namespace__ProcSequence"])
    ap.add_argument("--press"); ap.add_argument("--to", type=int)
    a = ap.parse_args()
    log = os.path.join(STATES, a.chain + ".inputs")
    src = a.src
    start = state_frame(src)
    if a.press:  # one planned segment
        end = a.to
        r = segment(a.chain, src, start, end, a.press, shots=sorted({int(x.split(':')[0]) + 30 for x in a.press.split(',')} | {end - 1}))
        with open(log, "a") as fh:
            fh.write(a.press + "\n")
        for fr, m in r.get("markers", {}).items():
            print(fr, m.get("current"))
        print("sheet", r.get("shots"))
        sys.exit(0)
    r = segment(a.chain, src, start, start + 3, None)
    cur, cls = current(r, start + 2)
    src, start = a.chain, start + 2
    last = None
    for i in range(a.max):
        if cur in a.stop:
            print(f"stop at {start}: {cur}")
            break
        end = start + a.seg
        btn = ANSWER.get(cur)
        if cur == "ProcTutorialViewer" and "BattleSeq" in cls:
            btn = None
        if "TalkKeyWait" in cls and cur not in a.stop:
            cur = "TalkKeyWait"
        if cur in ("TalkKeyWait", "TalkUtil__ProcBind", "event__anonymous_namespace__ProcEvent"):
            btn = "A" if last == ("START", cur) else "START"
        if "BattleSeq" in cls and btn == "START":
            btn = "A"  # START pauses a battle
        if cur == "ProcBattleInfo":
            stuck = stuck + 1 if 'stuck' in dir() else 1
            if stuck >= 8:
                btn, stuck = "START", 0  # resume a paused battle
        else:
            stuck = 0
        if cur == "map__anonymous_namespace__ProcSequence" and "ProcScene" in cls:
            btn = "A"  # chapter objective screen
        last = (btn, cur)
        press = f"{start + 4}:{btn}" if btn else None
        r = segment(a.chain, src, start, end, press)
        if press:
            with open(log, "a") as fh:
                fh.write(press + chr(10))
        print(f"{start}: {cur} -> {btn or 'wait'}", flush=True)
        cur, cls = current(r, end - 1)
        src, start = a.chain, end - 1
    print("chain state", a.chain, "frame", state_frame(a.chain), "current", cur)
