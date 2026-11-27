#!/usr/bin/env python3
"""H6 survivors of src/readable/battle/stance_gauge.c or stance_bonus.c against stance_diff.py (round 12,
h6-sharpen-2; stance_bonus.c added in round 13, h6-sharpen-3).

    python tools/harness/h6host_stance.py --mutants build/.../mutants.csv [--label r12-before] [--only]

In plain words: the same check as tools/harness/h6host.py, for the one file whose host test (stance_diff.py) has no
make_cases / compare split: each survivor of the H6 run is planted again exactly as mutate.py made it (same id;
operator, old, new and column checked), into a copy of src/readable/ (plus include/readable and
tools/readable/stub) under build/readable/h6host/<label>-stance/, and stance_diff.py's normal run (every function,
its default -n and --seed; --only: situation_can_dual only) runs on that copy. Caught = the run fails (a mismatch,
the driver fails, or it does not build). The unplanted copy must pass first. Warnings are not errors (as in
mutate.py). Results: build/harness/h6host/<label>/<file stem>.csv (never H6: kept apart).
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import importlib.util
import io
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import mutate  # noqa: E402

RELS = ("src/readable/battle/stance_gauge.c", "src/readable/battle/stance_bonus.c")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mutants", required=True)
    ap.add_argument("--label", default="r12")
    ap.add_argument("--only", action="store_true", help="stance_diff --only situation_can_dual (faster)")
    ap.add_argument("--ids", help="comma list of mutant ids (a subset)")
    ap.add_argument("--shard", help="K/N: only the survivors whose position modulo N is K (run N of these side by "
                    "side; each writes <stem>.shardK.csv)")
    a = ap.parse_args(argv)
    rows = [r for r in csv.DictReader(open(a.mutants, encoding="utf-8")) if r["result"] == "survived"]
    if a.ids:
        rows = [r for r in rows if r["id"] in set(a.ids.split(","))]
    tag = ""
    if a.shard:
        k, n = (int(x) for x in a.shard.split("/"))
        rows = [r for i, r in enumerate(rows) if i % n == k]
        tag = f".shard{k}"
    files = {r["file"].replace("\\", "/") for r in rows}
    if len(files) != 1 or not files <= set(RELS):
        print(f"h6host_stance: one of {RELS}, one at a time")
        return 2
    REL = files.pop()
    stem = os.path.splitext(os.path.basename(REL))[0]
    spec = importlib.util.spec_from_file_location(
        "h6host_stance_sd", os.path.join(ROOT, "src", "readable", "battle", "tests", "stance_diff.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    real = subprocess.run

    def run(cmd, *x, **k):  # warnings are not errors (a planted bug may leave a variable unused)
        if isinstance(cmd, list) and "-Werror" in cmd:
            cmd = [c for c in cmd if c not in ("-Werror", "-Wall", "-Wextra")]
            cmd.insert(1, "-w")
        return real(cmd, *x, **k)

    mod.subprocess = type(sys)("subprocess_h6host_stance")
    mod.subprocess.__dict__.update(subprocess.__dict__)
    mod.subprocess.run = run
    work = os.path.join(ROOT, "build", "readable", "h6host", a.label + "-" + stem + tag)
    src = os.path.join(ROOT, *REL.split("/"))
    remade = {}
    for fn in sorted({r["function"] for r in rows}):
        for m in mutate.make_mutants(src, fn, say=lambda *_: None):
            remade[m.mid] = m

    def judge(name: str, body: str | None) -> tuple[int, str]:
        r = os.path.join(work, name)
        shutil.rmtree(r, ignore_errors=True)
        shutil.copytree(os.path.join(ROOT, "src", "readable"), os.path.join(r, "src", "readable"),
                        ignore=shutil.ignore_patterns("tests", "*.parked"))
        if body is not None:
            with open(os.path.join(r, *REL.split("/")), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
        for d in (("include", "readable"), ("tools", "readable", "stub")):
            shutil.copytree(os.path.join(ROOT, *d), os.path.join(r, *d))
        mod.ROOT, mod.OUT = r, os.path.join(r, "out")
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = mod.main(["--only", "situation_can_dual"] if a.only else [])
        except SystemExit as e:  # the planted copy does not build
            rc, buf = 1, io.StringIO(str(e).splitlines()[0][:80])
        out = buf.getvalue().strip().splitlines()
        if body is not None:
            shutil.rmtree(r, ignore_errors=True)
        return rc, out[-1] if out else ""

    rc, last = judge("baseline", None)
    if rc:
        print(f"h6host_stance: baseline not clean ({last}); nothing judged")
        return 3
    print(f"h6host_stance: baseline clean ({last}); {len(rows)} survivor(s)")
    res = []
    for r in rows:
        m = remade.get(r["id"])
        o = dict(id=r["id"], function=r["function"], line=r["line"], operator=r["operator"], old=r["old"], new=r["new"],
                 h6=r["result"], h6_reached=r.get("reached", ""), host="", host_by="")
        if m is None or (m.op, m.old, m.new, str(m.col)) != (r["operator"], r["old"], r["new"], r["col"]):
            o["host"] = "id-mismatch"
        else:
            rc, last = judge(r["id"], m.text)
            o["host"], o["host_by"] = ("caught" if rc else "survived"), last
        print(f"  {o['id']}: {o['host']} {o['host_by']}")
        res.append(o)
    out_root = os.path.join(ROOT, "build", "harness", "h6host", a.label)
    os.makedirs(out_root, exist_ok=True)
    with open(os.path.join(out_root, stem + tag + ".csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, list(res[0].keys()) if res else ["id"])
        w.writeheader()
        w.writerows(res)
    print(f"h6host_stance: {sum(1 for o in res if o['host'] == 'caught')} of {len(res)} survivors caught by stance_diff")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
