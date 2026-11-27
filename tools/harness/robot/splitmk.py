"""Print the marker reads of a parallel.py session's runs (area split, round 8): frame, current screen, route byte,
unit counts per force, paired units, and stage-complete / save classes. usage: splitmk.py SESSION [RUN]"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
ses = sys.argv[1]
res = os.path.join(ROOT, "build", "parallel", ses, "results")
for fn in sorted(os.listdir(res)):
    if not fn.endswith(".json") or (len(sys.argv) > 2 and sys.argv[2] not in fn):
        continue
    r = json.load(open(os.path.join(res, fn), encoding="utf-8"))["run_json"]
    print("==", fn, r.get("route"), "memory", r.get("state", {}).get("memory", "")[:16], "checkpoints", r.get("checkpoints"))
    for f, m in sorted((r.get("markers") or {}).items(), key=lambda kv: int(kv[0])):
        st = m.get("state", {})
        extra = [c for c in m.get("classes", []) if "Complete" in c or "ChapterFile" in c]
        print(f, m.get("current"), "route", st.get("route"), "units", st.get("units"), "paired", st.get("paired_player"),
              "gold", st.get("gold"), extra)
