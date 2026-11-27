"""Scratch probe (build/ only, untracked): one headless original run of an ad-hoc route, without
writing config/harness/routes.json.
usage: probe.py NAME FRAMES INPUT SHOTS [--save ZIPNAME] [--load STATE] [--state-at F] [--markers]
                [--first F] [--scale N] [--dump 0xADDR,LEN]
SHOTS: 'step' (every step frames from --first) or a comma list. INPUT may be '@file' (one entry per line,
'#' comments). --load continues from a savestate in build/harness/robot/states/ (look-ahead only).
--state-at F keeps the savestate of frame F as states/NAME.bin.

Budget: robot/budget.py (priority from config/harness/resources.json, one look-ahead at a time, APPDATA
below build/)."""
import json, os, sys, shutil, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.append(os.path.join(ROOT, "tools", "harness"))
import headless as hl  # noqa
sys.path.append(HERE)
import budget  # noqa

ap = argparse.ArgumentParser()
ap.add_argument("name"); ap.add_argument("frames", type=int); ap.add_argument("input"); ap.add_argument("shots")
ap.add_argument("--save", default="new-game-empty"); ap.add_argument("--load"); ap.add_argument("--state-at", type=int)
ap.add_argument("--markers", action="store_true"); ap.add_argument("--first", type=int, default=0)
ap.add_argument("--scale", type=int, default=2); ap.add_argument("--dump")
a = ap.parse_args()
inp = a.input
if inp.startswith("@"):
    lines = open(inp[1:], encoding="utf-8").read().splitlines()
    inp = ",".join(t.strip() for ln in lines for t in ln.split("#")[0].split(",") if t.strip())
if "," in a.shots or a.shots.isdigit() and int(a.shots) > a.frames // 2:
    shots = [int(x) for x in a.shots.split(",") if x]
else:
    st = int(a.shots)
    shots = list(range(a.first + st, a.frames - 10, st)) + [a.frames - 10]
states = os.path.join(ROOT, "build", "harness", "robot", "states")  # below build/ only
os.makedirs(states, exist_ok=True)
save_at = a.state_at or (a.frames - 10)
route = {"frames": a.frames, "input": inp, "save_at": save_at, "shots": shots, "verified": False}
budget.enter()
orig_load = hl.load_routes
hl.load_routes = lambda path=hl.ROUTES: {**orig_load(path), "probe": route}
orig_env = hl.boot_env
def env(*args, **kw):
    e = orig_env(*args, **kw)
    budget.env_patch(e)  # APPDATA below build/, never the owner's %APPDATA%
    if a.load:
        e["ZAKURO_LOAD"] = os.path.join(states, a.load if a.load.endswith(".bin") else a.load + ".bin")
    return e
hl.boot_env = env
orig_sheet = hl.contact_sheet
hl.contact_sheet = lambda t, f, o, scale=2: orig_sheet(t, f, o, a.scale)
with budget.run_slot():
    r = hl.run(a.name, "probe", "original", save=a.save, keep_state=bool(a.state_at) or True, markers=a.markers,
           extra_dump=a.dump, timeout=3600)
st = os.path.join(hl.RUNS, a.name, "state.bin")
if os.path.isfile(st):
    shutil.move(st, os.path.join(states, a.name + ".bin"))
if a.markers and "markers" in r:
    for f, m in r["markers"].items():
        print(f, m.get("current"), [c for c in m.get("classes", []) if c not in ("ProcInst",)][:14])
print("sheet:", r.get("shots"))
