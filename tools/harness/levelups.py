#!/usr/bin/env python3
"""Level-ups seen in marker runs (docs/ROBOT.md, round 4). Standard library only.

A marker run stores, at every shot frame, `state.levels` (markers.unit_levels: per person id the level, the
experience, the eight stat gains Unit+0xC8 and the raw stats). This tool compares consecutive shot frames of each
run and lists every unit whose level rose between them, with the stats before and after. It is the list the growth
batch (docs/tracks/BATCH_GROWTH.md) needs for its live compare: which routes contain a real level-up, and between
which frames.

    python tools/harness/levelups.py SESSION            a parallel.py session (build/parallel/SESSION/results/)
    python tools/harness/levelups.py RUN.json ...       run.json files (or parallel result files)
    python tools/harness/levelups.py --selftest

A level-up between two shots is only seen when both shots read the unit (a unit that joins, leaves the map or
falls in between is not compared). Units that level twice between two shots show the whole step.
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PARALLEL = os.path.join(ROOT, "build", "parallel")
STATS = ("hp", "str", "mag", "skl", "spd", "lck", "def", "res")


def load(path: str) -> tuple[str, dict]:
    """(route, markers) of a run.json or a parallel result file."""
    with open(path, encoding="utf-8") as fh:
        r = json.load(fh)
    r = r.get("run_json", r)
    return r.get("route", os.path.basename(path)), r.get("markers") or {}


def pid_key(k: str) -> tuple:
    """"6" < "6#2" < "10": person id, then the copy number markers.unit_levels gives a second unit of one id."""
    pid, _, n = k.partition("#")
    return (int(pid) if pid.isdigit() else 1 << 30, int(n) if n.isdigit() else 1, k)


def levelups(markers: dict) -> list[dict]:
    frames = sorted((int(f), m) for f, m in markers.items() if m)
    out = []
    for (f0, m0), (f1, m1) in zip(frames, frames[1:]):
        a = (m0.get("state") or {}).get("levels") or {}
        b = (m1.get("state") or {}).get("levels") or {}
        for pid in sorted(set(a) & set(b), key=pid_key):
            if b[pid]["lv"] > a[pid]["lv"]:
                up = {s: b[pid]["stats"][i] - a[pid]["stats"][i] for i, s in enumerate(STATS)
                      if b[pid]["stats"][i] != a[pid]["stats"][i]}
                out.append({"person": pid, "from": f0, "to": f1, "lv": [a[pid]["lv"], b[pid]["lv"]],
                            "exp": [a[pid]["exp"], b[pid]["exp"]], "stats_before": a[pid]["stats"],
                            "stats_after": b[pid]["stats"], "rose": up})
    return out


def report(paths: list[str]) -> dict:
    res = {}
    for p in paths:
        route, markers = load(p)
        has = any(((m or {}).get("state") or {}).get("levels") for m in markers.values())
        res[route] = {"levels_read": has, "levelups": levelups(markers)}
    return res


def selftest() -> int:
    def m(lv, exp, stats):
        return {"state": {"levels": {"6": {"lv": lv, "exp": exp, "gain": [0] * 8, "stats": stats}}}}
    mk = {"100": m(5, 89, [21, 8, 3, 6, 8, 5, 11, 3]), "200": m(5, 89, [21, 8, 3, 6, 8, 5, 11, 3]),
          "300": m(6, 26, [21, 8, 3, 7, 8, 5, 11, 3]), "400": {"state": {}}}
    got = levelups(mk)
    ok = (len(got) == 1 and got[0]["from"] == 200 and got[0]["to"] == 300 and got[0]["lv"] == [5, 6]
          and got[0]["rose"] == {"skl": 1})
    ok2 = levelups({"1": m(3, 0, [1] * 8)}) == []
    # round 6: two units with person id 6 ("6" and "6#2", markers.unit_levels); only the second levels up
    def two(lv_a, lv_b):
        return {"state": {"levels": {"6": {"lv": lv_a, "exp": 0, "gain": [0] * 8, "stats": [1] * 8},
                                     "6#2": {"lv": lv_b, "exp": 0, "gain": [0] * 8, "stats": [1] * 8},
                                     "10": {"lv": 1, "exp": 0, "gain": [0] * 8, "stats": [1] * 8}}}}
    got3 = levelups({"1": two(5, 7), "2": two(5, 8)})
    ok3 = [x["person"] for x in got3] == ["6#2"] and got3[0]["lv"] == [7, 8]
    print(f"levelups self-test: {int(ok) + int(ok2) + int(ok3)}/3 checks passed")
    return 0 if ok and ok2 and ok3 else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--selftest"]:
        sys.exit(selftest())
    if not args:
        print(__doc__)
        sys.exit(2)
    paths = []
    for a in args:
        if a.endswith(".json"):
            paths.append(a)
        else:
            paths += sorted(glob.glob(os.path.join(PARALLEL, a, "results", "*.json")))
    if not paths:
        print("levelups: no run files")
        sys.exit(3)
    print(json.dumps(report(paths), indent=1))
