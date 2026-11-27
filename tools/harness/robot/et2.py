"""et2.py CHAIN X,Y : cursor to the empty tile X,Y, A (system menu checked), UP A (end turn), autopilot to the next stop."""
import sys, os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import act
chain = sys.argv[1]; t = tuple(int(v) for v in sys.argv[2].split(","))
c, cls = act.step(chain, [], wait=4)
if c != act.HUMAN: print("not player phase:", c); sys.exit(2)
cur, units = act.board(chain)
if any((u[1], u[2]) == t for u in units): print("tile occupied", t); sys.exit(2)
c, cls = act.step(chain, act.moves(cur, t) + ["A"], wait=40)
if c != "map__anonymous_namespace__SystemMenu": print("no system menu:", c); sys.exit(2)
c, cls = act.step(chain, ["UP", "A"], wait=60, dump=False)
p = subprocess.run([sys.executable, os.path.join(HERE, "auto.py"), chain, chain, "--max", "80", "--seg", "90", "--stop",
                    act.HUMAN, "map__DialogYesNo", "ChapterFileMenu", "GameDialogYesNo"], capture_output=True, text=True)
print(p.stdout.strip().splitlines()[-1])
