"""split.py with the Revelation area's own state folder (round 8, area rv; docs/ROUTES_SPLIT.md, Revelation section).

Same commands as split.py (base, fork, press, auto, look, act, endturn, input); only the folder differs:
build/harness/robot/states/split-rv/ (savestates, chain inputs and the slot locks of this area), so it shares no
state file and no lock with the Conquest agent (states/split-cq/) or the round-8 split agent (states/split/).
split.py itself is unchanged; this sets its module-level STATES (read at call time) and auto.STATES.
usage: splitrv.py <split.py command> ...      (SPLIT_SLOTS, default 2, counts inside this area's FEF_ROBOT_JOBS)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import split  # noqa: E402

split.STATES = os.path.join(split.budget.ROBOT, "states", "split-rv")
os.makedirs(split.STATES, exist_ok=True)
split.auto.STATES = split.STATES

if __name__ == "__main__":
    split.main()
