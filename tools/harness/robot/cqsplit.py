"""split.py for the Conquest chain only (round 8, area cq; docs/ROUTES_SPLIT.md section 7).

The same commands as split.py (base, fork, press, auto, look, act, endturn, input), unchanged, with this area's
own folder build/harness/robot/states/split-cq/ (states, inputs, and its own SPLIT_SLOTS lock pool), so it never
shares a lock or a state file with the Revelation chain or the Birthright agent. Chain names start with "q"
(run folders build/harness/runs/q*), never the shared fixed names.
usage: cqsplit.py <split.py command and arguments>
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import split  # noqa: E402
import auto  # noqa: E402

split.STATES = os.path.join(split.budget.ROBOT, "states", "split-cq")
os.makedirs(split.STATES, exist_ok=True)
auto.STATES = split.STATES
_segment = auto.segment


def _segment_full(*a, **k):
    """Contact sheets at full size by default (CQ_SCALE, default 1): the forecast numbers are readable."""
    k.setdefault("scale", int(os.environ.get("CQ_SCALE", "1")))
    return _segment(*a, **k)


auto.segment = _segment_full

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] in ("base", "press", "auto", "look", "act", "endturn") \
            and not sys.argv[2].startswith("q"):
        sys.exit("cqsplit: chain names of this area start with q")
    split.main()
