#!/usr/bin/env python3
"""H6 survivors against the batch's host differential test (round 11, F-025 "sharper tests").

    python tools/harness/h6host.py --mutants build/.../mutants.csv [--all] [--jobs 6] [--label NAME]

In plain words: H6 (tools/harness/h56.py h6) plants one small bug at a time in the readable code and replays
the game records; a bug the records do not notice is a "survivor". This tool takes the survivors of one source
file (the mutants.csv of an H6 run), plants each one again, exactly as mutate.py made it, and runs the batch's
host differential test (src/readable/<batch>/tests/<x>_diff.py: the game's own ARM code in arm_mini.py against
the readable C on made-up states, the cases of its normal run: default -n and --seed) on the planted copy.
A planted bug is "caught by the host test" when any case then mismatches, or the C driver crashes or runs away.

This is NOT the H6 number. H6 counts game records only; this tool reports, per survivor, whether the host test
would notice it too, so the two together say which planted bugs no test of ours notices at all. Results are
kept apart: build/harness/h6host/<label>/<file stem>.csv / .json (the H6 run's own files are only read).

Each mutant is re-made with mutate.make_mutants (same operators, same id) and must agree with the csv row
(operator, old, new, column and the squeezed source line; the line number may move when comments changed),
else it is skipped as `id-mismatch`. The batch's baseline (no planted bug) must give 0 mismatches first.

Batches: support, unit (growth_diff), menu, skill; round 12: battle (formula_diff: formula_*.c only), item, sheet,
move; round 13: map (vein_diff). Round 17: per source file (FILE_BATCHES): the ai and battle2 files, triangle_tables,
class_change, shop_price, flags and forces. The batch ai_score is refused (another workflow owns it).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import mutate  # noqa: E402

BATCHES = {  # folder under src/readable -> (diff script, its SRC_* constant, build_driver takes strict=)
    "support": ("support/tests/support_diff.py", "SRC_SUPPORT", True),
    "unit": ("unit/tests/growth_diff.py", "SRC_UNIT", False),
    "menu": ("menu/tests/menu_diff.py", "SRC_MENU", False),
    "skill": ("skill/tests/skill_diff.py", "SRC_SKILL", False),
    # round 12 (h6-sharpen-2): battle (formula_*.c only), item, sheet, move
    "battle": ("battle/tests/formula_diff.py", "SRC_BATTLE", False),
    "item": ("item/tests/item_diff.py", "SRC_ITEM", True),
    "sheet": ("sheet/tests/sheet_diff.py", "SRC_SHEET", True),
    "move": ("move/tests/move_diff.py", "SRC_MOVE", True),
    # round 13 (h6-sharpen-3): map (vein_diff: vein_tricks.c and vein_units.c)
    "map": ("map/tests/vein_diff.py", "SRC_MAP", False),
}
# a batch folder whose diff script covers only some of its files: the stems it covers
BATCH_FILES = {"battle": ("formula_forecast", "formula_unit", "formula_stats")}
# round 17 (host-tests): one source file -> its diff script, wherever the folder's own adapter points (the 13
# files that had no host verdict: the three new small tests and the five batch tests h6host had no adapter for)
FILE_BATCHES = {
    "ai_value": ("ai/tests/ai_value_diff.py", "SRC_AI", True),
    "ai_think": ("ai/tests/ai_value_diff.py", "SRC_AI", True),
    "ai_area": ("ai/tests/ai_perm_diff.py", "SRC_AI", True),
    "ai_items": ("ai/tests/ai_perm_diff.py", "SRC_AI", True),
    "ai_permission": ("ai/tests/ai_perm_diff.py", "SRC_AI", True),
    "flags": ("event/tests/flags_diff.py", "SRC_EVENT", True),
    "forces": ("unit/tests/forces_diff.py", "SRC_UNIT", True),
    "triangle_tables": ("battle/tests/triangle_diff.py", "SRC_BATTLE", False),
    "battle2_bonus": ("battle2/tests/battle2_diff.py", "SRC_B2", True),
    "battle2_calc": ("battle2/tests/battle2_diff.py", "SRC_B2", True),
    "battle2_rules": ("battle2/tests/battle2_diff.py", "SRC_B2", True),
    "class_change": ("class_change/tests/class_change_diff.py", "SRC_CC", True),
    "shop_price": ("shop_price/tests/shop_price_diff.py", "SRC_SP", True),
}
REFUSED = {"ai_score"}  # (ai and battle2: refused until round 17; only their files above are handled)
DRIVER_TIMEOUT = 300  # seconds for one run of the C driver over every case (the baseline takes a few)

_real_run = subprocess.run
_local = threading.local()


_OBJ: dict[str, str] = {}  # readable source outside the batch folder -> its object, compiled once per run
_OBJ_DIR: list[str] = []


def _run(cmd, *a, **kw):
    """subprocess.run for the diff module: warnings are not errors (a planted bug may leave a variable unused:
    still valid C, as in mutate.py's builds), the driver gets a time limit (a planted bug may loop), and the
    readable sources outside the planted batch folder are compiled once (the first build, the baseline) and
    linked as objects afterwards (same compiler, same flags; only the batch folder and the driver recompile)."""
    if isinstance(cmd, list) and "-c" in cmd:
        pass  # a diff script that compiles one file at a time keeps its own object cache (shop_price_diff.py)
    elif isinstance(cmd, list) and len(cmd) > 2 and "-o" in cmd and any(x.endswith(".c") for x in cmd):
        cmd = [x for x in cmd if x not in ("-Werror", "-Wall", "-Wextra")]
        if "-w" not in cmd:
            cmd.insert(1, "-w")
        if _OBJ_DIR:
            batch_dir = os.path.normcase(os.path.abspath(_OBJ_DIR[1]))
            flags = [x for x in cmd[1:] if not x.endswith(".c")]
            o = flags.index("-o")
            flags = flags[:o] + flags[o + 2:]
            out = []
            for x in cmd:
                ax = os.path.normcase(os.path.abspath(x)) if x.endswith(".c") else ""
                if ax and ax.startswith(os.path.join(os.path.normcase(ROOT), "src", "readable"))                         and not ax.startswith(batch_dir):
                    if ax not in _OBJ:
                        obj = os.path.join(_OBJ_DIR[0], f"{len(_OBJ):04d}_{os.path.basename(x)[:-2]}.o")
                        r = _real_run([cmd[0], "-c"] + flags + [x, "-o", obj], capture_output=True, text=True,
                                      env=kw.get("env"))
                        if r.returncode:
                            return r
                        _OBJ[ax] = obj
                    out.append(_OBJ[ax])
                else:
                    out.append(x)
            cmd = out
    elif isinstance(cmd, list) and len(cmd) == 1 and "timeout" not in kw:
        kw["timeout"] = DRIVER_TIMEOUT
    return _real_run(cmd, *a, **kw)


def _shim():
    """A stand-in for the subprocess module whose run is _run (everything else is the real module's)."""
    m = type(sys)("subprocess_h6host")
    m.__dict__.update(subprocess.__dict__)
    m.run = _run
    return m


def patch_helpers(roots: tuple[str, ...] | None = None) -> list[str]:
    """Round 18: give _run to every module already imported from under `roots` (default: src/readable) that
    still holds the real subprocess module. A diff script often borrows code from another one (ai_perm_diff
    calls move_diff.compare; flags_diff and forces_diff run leaf_diff's build and compare), and that code calls
    its own module's subprocess.run: before this, its driver had no time limit (round 17: two runaway planted
    bugs hung for 15 minutes). Returns the names of the modules patched (for the test)."""
    roots = tuple(os.path.normcase(os.path.abspath(r)) + os.sep
                  for r in (roots or (os.path.join(ROOT, "src", "readable"),)))
    done = []
    for name, m in list(sys.modules.items()):
        f = getattr(m, "__file__", None)
        if not f or getattr(m, "subprocess", None) is not subprocess:
            continue
        if os.path.normcase(os.path.abspath(f)).startswith(roots):
            m.subprocess = _shim()
            done.append(name)
    return done


def load(batch: str, stem: str = ""):
    script, src_const, strict = FILE_BATCHES.get(stem) or BATCHES[batch]
    path = os.path.join(ROOT, "src", "readable", script)
    spec = importlib.util.spec_from_file_location(f"h6host_{batch}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.subprocess = _shim()
    patch_helpers()  # the modules it borrowed code from (a later import inside a function: see patch_helpers)
    return mod, getattr(mod, src_const), strict


def judge(mod, cc, lines, expected, exe) -> tuple[str, str, int | None]:
    """(caught | survived, by what, early give-ups). The third value (round 13, report only: it never changes
    the verdict) is the number of cases where the readable code gave up early although the original answered
    (the 4th count of the diff scripts that keep one; None for the others). A planted bug that only raises it is
    a "give-up only" bug: never a wrong answer, but the readable code does less of the work."""
    patch_helpers()  # a module imported late (inside a build function) gets the time limit too
    try:
        per = mod.compare(exe, cc, lines, expected, 0, quiet=True)
    except subprocess.TimeoutExpired:
        return "caught", "runaway", None
    except SystemExit as e:
        return "caught", "driver failed: " + str(e).splitlines()[0][:80], None
    early = sum(v[3] for v in per.values()) if per and all(len(v) >= 4 for v in per.values()) else None
    hit = [k for k, v in per.items() if v[1]]
    if hit:
        return "caught", " ".join(f"{k}:{per[k][1]}" for k in hit), early
    return "survived", "", early


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mutants", required=True, help="an H6 run's mutants.csv (one source file)")
    ap.add_argument("--all", action="store_true", help="every judged mutant, not only the survivors")
    ap.add_argument("--ids", help="comma list of mutant ids (a subset)")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--label", default="r11")
    ap.add_argument("-n", type=int, help="cases per function (default: the diff script's normal run)")
    ap.add_argument("--seed", type=int, help="(default: the diff script's normal run)")
    a = ap.parse_args(argv)

    rows = list(csv.DictReader(open(a.mutants, encoding="utf-8")))
    files = {r["file"] for r in rows}
    if len(files) != 1:
        print(f"h6host: the csv holds {len(files)} source files; one at a time")
        return 2
    rel = files.pop().replace("\\", "/")
    batch = rel.split("/")[2]
    stem = os.path.splitext(os.path.basename(rel))[0]
    if stem not in FILE_BATCHES and (batch in REFUSED or batch not in BATCHES):
        print(f"h6host: batch {batch!r} is not handled here ({'owned by another workflow' if batch in REFUSED else 'no adapter'})")
        return 2
    if stem not in FILE_BATCHES and batch in BATCH_FILES and stem not in BATCH_FILES[batch]:
        print(f"h6host: {rel}: the {batch} adapter's diff script does not test this file")
        return 2
    src_path = os.path.join(ROOT, rel)
    want = [r for r in rows if r["result"] in (("survived", "caught") if a.all else ("survived",))]
    if a.ids:
        ids = set(a.ids.split(","))
        want = [r for r in want if r["id"] in ids]

    mod, src_dir, strict = load(batch, stem)
    text_bin = open(mod.TEXT, "rb").read()
    if hasattr(mod, "find_cc"):
        cc = mod.find_cc()
    else:  # formula_diff.py takes the compiler search of tools/readable/check.py too (through triangle_diff)
        sys.path.insert(0, os.path.join(ROOT, "tools", "readable"))
        import check as _check
        cc = _check.find_cc()
    if not cc:
        print("h6host: no host C compiler")
        return 2
    import re
    script_text = open(mod.__file__, encoding="utf-8").read()
    d_n = re.search(r'add_argument\("-n", type=int, default=(\d+)', script_text)
    d_seed = re.search(r'add_argument\("--seed", type=int, default=(\d+)', script_text)
    n = a.n if a.n else int(d_n.group(1))  # the diff script's normal run
    seed = a.seed if a.seed is not None else int(d_seed.group(1))
    t0 = time.time()
    made = mod.make_cases(text_bin, n, seed, None)
    lines, expected, unsupported = made if len(made) == 3 else (made[0], made[1], {})  # vein_diff: no unsupported
    t_cases = time.time() - t0
    out_root = os.path.join(ROOT, "build", "harness", "h6host", a.label)
    work = os.path.join(ROOT, "build", "readable", "h6host", a.label, stem)
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(out_root, exist_ok=True)

    def build(name: str, body: str | None):
        d = os.path.join(work, name, "src")
        shutil.copytree(src_dir, d, ignore=shutil.ignore_patterns("tests"))
        if body is not None:
            with open(os.path.join(d, os.path.basename(rel)), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
        kw = {"strict": False} if strict else {}
        return mod.build_driver(cc, os.path.join(work, name), d, **kw)

    _OBJ_DIR[:] = [os.path.join(work, "objects"), src_dir]
    os.makedirs(_OBJ_DIR[0], exist_ok=True)
    base_exe = build("baseline", None)
    res, by, base_early = judge(mod, cc, lines, expected, base_exe)
    if res != "survived" or unsupported:
        print(f"h6host: baseline not clean ({by or unsupported}); nothing judged")
        return 3
    print(f"h6host: {rel}: baseline clean, {len(expected)} cases ({t_cases:.0f} s to make); "
          f"{len(want)} mutant(s) to judge, {a.jobs} at once")

    remade: dict[str, mutate.Mutant] = {}
    for fn in sorted({r["function"] for r in want}):
        for m in mutate.make_mutants(src_path, fn, say=lambda *_: None):
            remade[m.mid] = m

    def one(r: dict) -> dict:
        m = remade.get(r["id"])
        out = dict(id=r["id"], function=r["function"], line=r["line"], operator=r["operator"], old=r["old"],
                   new=r["new"], h6=r["result"], h6_reached=r.get("reached", ""), h6_why=r.get("why", "")[:40],
                   host="", host_by="", host_extra_giveups="")
        if m is None or (m.op, m.old, m.new, str(m.col), m.src_line) != (r["operator"], r["old"], r["new"], r["col"],
                                                                         r["source_line"]):
            out["host"] = "id-mismatch"
            return out
        try:
            exe = build(r["id"], m.text)
        except SystemExit as e:
            out["host"], out["host_by"] = "stillborn", str(e).splitlines()[-1][:80]
            return out
        out["host"], out["host_by"], early = judge(mod, cc, lines, expected, exe)
        if early is not None and base_early is not None:
            out["host_extra_giveups"] = early - base_early  # report only (a give-up counter, not armed)
        shutil.rmtree(os.path.join(work, r["id"]), ignore_errors=True)
        return out

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for k, o in enumerate(ex.map(one, want), 1):
            results.append(o)
            if k % 25 == 0:
                print(f"  ... {k}/{len(want)}", flush=True)
    cols = list(results[0].keys()) if results else ["id"]
    with open(os.path.join(out_root, stem + ".csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        w.writerows(results)
    judged_h6 = sum(1 for r in rows if r["result"] in ("caught", "survived"))
    caught_h6 = sum(1 for r in rows if r["result"] == "caught")
    surv = [o for o in results if o["h6"] == "survived"]
    host_caught = [o for o in surv if o["host"] == "caught"]
    summary = dict(file=rel, mutants_csv=os.path.relpath(a.mutants, ROOT).replace("\\", "/"), cases=len(expected),
                   n=n, seed=seed, h6_judged=judged_h6, h6_caught=caught_h6,
                   h6_rate=round(100 * caught_h6 / max(judged_h6, 1), 1), survivors_judged=len(surv),
                   survivors_caught_by_host=len(host_caught),
                   survivors_not_reached=sum(1 for o in surv if o["h6_reached"] == "not reached"),
                   not_reached_caught_by_host=sum(1 for o in host_caught if o["h6_reached"] == "not reached"),
                   host_stillborn=sum(1 for o in surv if o["host"] == "stillborn"),
                   id_mismatch=sum(1 for o in results if o["host"] == "id-mismatch"),
                   either_caught=caught_h6 + len(host_caught),
                   host_survivors_giving_up_more=sum(1 for o in surv if o["host"] == "survived"
                                                     and isinstance(o["host_extra_giveups"], int)
                                                     and o["host_extra_giveups"] > 0),
                   either_rate=round(100 * (caught_h6 + len(host_caught)) / max(judged_h6, 1), 1),
                   seconds=round(time.time() - t0))
    with open(os.path.join(out_root, stem + ".json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print("h6host: " + json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
