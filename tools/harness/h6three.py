#!/usr/bin/env python3
"""Three bug-catcher numbers, kept apart (round 14 measure; Grok's STRATEGY_R14 section 1). READ-ONLY.

    python tools/harness/h6three.py                 # the three numbers, per file and per family
    python tools/harness/h6three.py --never         # + every planted bug on a line no recording reached
    python tools/harness/h6three.py --candidates    # + the equivalent candidates, by rule class, with ids
    python tools/harness/h6three.py --json OUT      # everything as one json file (the only thing it writes)

In plain words. H6 plants one small bug at a time in the readable code and replays the game's recordings. The one
H6 percent counts a bug on a line that no recording ever ran as a failure, and a bug that cannot change any answer
as a failure too. This command reads data that already exists and reports three separate numbers instead. It never
adds them into one percent, it never changes the H6 gate, and it never marks a planted bug "equivalent".

1. **Recordings, on reached lines.** The sampled H6 run (h6_sample.json and its mutants.csv files). A survivor whose
   line no recording ran is LISTED and left out of the count. "No recording ran it" is taken from the H5 run the
   sample used (all records, gcov over the whole file): a survivor the sample did not reach but H5 says some
   recording did reach stays in the count (a gap of the sample, not of the recordings). A survivor on a line H5
   holds no data for (a static helper outside every override's span) stays in the count too; the figure with
   those left out as well is shown beside it.
2. **Host test, on the same planted bugs.** The batches' host differential tests (*_diff.py, through
   tools/harness/h6host.py and h6host_stance.py), whose per-mutant verdicts sit in build/harness/h6host/<label>/.
   The newest verdict for a mutant wins; a verdict is used only when it is the same planted bug (same id, operator,
   old and new text, and the same source line and column, or the same line number where the run kept no
   mutants.csv). Files with no host test are listed with the reason; nothing is guessed for them.
3. **Live compare.** The round's integrate totals (offline replay of every route, the new chapter live, and the cheat
   routes apart), per family (bt, cq, rv, opt), with every kind of difference counted.

Also: the never-reached survivors grouped by reason (tools/harness/h6three_reasons.csv, written by a person from the
notes; a survivor no row covers is "not sorted yet"), and the equivalent candidates of rounds 11-13 (the survivors
the host tests missed after the sharper cases) grouped into rule classes a person could judge. The classes are
FOR THE OWNER TO DECIDE: a class says what kind of change it is, never that it is harmless.
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PLAY = os.path.join(ROOT, "build", "harness", "h56", "play")
HOST_DIR = os.path.join(ROOT, "build", "harness", "h6host")
MUTATE_DIRS = (os.path.join(ROOT, "build", "harness", "mutate"),
               os.path.join(ROOT, "build", "h6snap", "r10", "build", "harness", "mutate"))
REASONS = os.path.join(HERE, "h6three_reasons.csv")
# the owner's equivalence list (mutate.py reads it the same way; copied rules, this command never imports a tool that
# builds). A candidate it names is "cleared by the owner": it leaves the judgement pile; number 1 does not change.
EQUIV = os.path.join(HERE, "mutants_equivalent.csv")
EQUIV_KEY = ("function", "operator", "old", "new", "col", "source_line")
PIN_RX = re.compile(r"\[id ([A-Za-z_]\w*-\d+) line (\d+)\]\s*$")
# round 13's integrate (docs/REPORT_2026-11-18.md); --offline / --offline-cheat / --live take another round's files
R13_OFFLINE = "build/speed/replay/r13-off/offline.json"
R13_OFFLINE_CHEAT = "build/speed/replay/r13-offc/offline.json"
R13_LIVE = "build/parallel/r13-capn/summary.json"
# the host labels that made the 237 candidates (rounds 11-13); a later label's misses are "new, not yet sorted"
CANDIDATE_LABELS = r"^(r1[123]-|rv-r13|trial$)"
DIFF_KINDS = ("bad", "mismatch_r0", "mismatch_regs", "mismatch_mem", "mismatch_calls", "b_escaped", "unfaithful",
              "escaped", "damaged")
# batches as tools/harness/h6host.py knows them (copied, so this command never imports a tool that builds)
H6HOST_BATCHES = {"support": "support/tests/support_diff.py", "unit": "unit/tests/growth_diff.py",
                  "menu": "menu/tests/menu_diff.py", "skill": "skill/tests/skill_diff.py",
                  "battle": "battle/tests/formula_diff.py", "item": "item/tests/item_diff.py",
                  "sheet": "sheet/tests/sheet_diff.py", "move": "move/tests/move_diff.py",
                  "map": "map/tests/vein_diff.py"}
H6HOST_BATCH_FILES = {"battle": ("formula_forecast", "formula_unit", "formula_stats")}
H6HOST_REFUSED = {"ai_score": "owned by another workflow (h6host.py refuses ai_score)"}
# (ai and battle2 were refused until round 17; their files are now in H6HOST_FILE_BATCHES below)
STANCE_FILES = ("stance_gauge", "stance_bonus")  # h6host_stance.py: stance_diff.py, survivors only
# round 17 (host-tests): h6host.py's FILE_BATCHES (copied): one source file -> its diff script
H6HOST_FILE_BATCHES = {"ai_value": "ai/tests/ai_value_diff.py", "ai_think": "ai/tests/ai_value_diff.py",
                       "ai_area": "ai/tests/ai_perm_diff.py", "ai_items": "ai/tests/ai_perm_diff.py",
                       "ai_permission": "ai/tests/ai_perm_diff.py", "flags": "event/tests/flags_diff.py",
                       "forces": "unit/tests/forces_diff.py", "triangle_tables": "battle/tests/triangle_diff.py",
                       "battle2_bonus": "battle2/tests/battle2_diff.py", "battle2_calc": "battle2/tests/battle2_diff.py",
                       "battle2_rules": "battle2/tests/battle2_diff.py",
                       "class_change": "class_change/tests/class_change_diff.py",
                       "shop_price": "shop_price/tests/shop_price_diff.py"}


def rel(p: str) -> str:
    return os.path.relpath(p, ROOT).replace("\\", "/") if os.path.isabs(p) else p.replace("\\", "/")


def absp(p: str) -> str:
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def pct(a: int, b: int) -> float | None:
    return round(100.0 * a / b, 1) if b else None


def fmt_pct(a: int, b: int) -> str:
    return f"{a} / {b} ({100.0 * a / b:.1f}%)" if b else f"{a} / 0 (-)"


def read_csv(p: str) -> list[dict]:
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------ number 1: recordings on reached lines
def load_sample(sample_path: str) -> tuple[dict, list[dict]]:
    """(the sample json, every judged or stillborn mutant row of the functions it judged)."""
    with open(sample_path, encoding="utf-8") as fh:
        sample = json.load(fh)
    by_csv: dict[str, set] = collections.defaultdict(set)
    for name, v in sample["functions"].items():
        by_csv[v["mutants_csv"]].add(name)
    rows = []
    for p, names in sorted(by_csv.items()):
        for r in read_csv(absp(p)):
            if r["function"] in names:
                r["_csv"] = p
                rows.append(r)
    return sample, rows


def h5_line_map(h5_path: str | None) -> dict[str, dict[int, bool]]:
    """file -> {line: ran in some recording} over every override's span (H5's aggregate gcov)."""
    out: dict[str, dict[int, bool]] = collections.defaultdict(dict)
    if not h5_path or not os.path.exists(absp(h5_path)):
        return out
    with open(absp(h5_path), encoding="utf-8") as fh:
        h5 = json.load(fh)
    for o in h5.get("overrides", []):
        span = o.get("span")
        if not span or not o.get("source"):
            continue
        never = set(o.get("never_run_lines") or [])
        m = out[o["source"].replace("\\", "/")]
        for line in range(span[0], span[1] + 1):
            ran = line not in never and bool(o.get("met"))
            m[line] = m.get(line, False) or ran  # a line in two spans: ran if either says so
    return out


def h5_helpers(h5_path: str | None) -> dict[str, tuple[int, int]]:
    """override -> (lines of its static helpers, how many of them ran): H5's with_helpers minus its own counts.
    H5 keeps no per-line data for helper lines, only these counts."""
    out: dict[str, tuple[int, int]] = {}
    if not h5_path or not os.path.exists(absp(h5_path)):
        return out
    with open(absp(h5_path), encoding="utf-8") as fh:
        h5 = json.load(fh)
    for o in h5.get("overrides", []):
        wh = o.get("with_helpers") or {}
        if "lines" in wh and "lines" in o:
            out[o["name"]] = (int(wh["lines"]) - int(o["lines"]), int(wh.get("lines_run", 0)) - int(o.get("lines_run", 0)))
    return out


def reach_of(row: dict, lines: dict[str, dict[int, bool]], helpers: dict | None = None) -> str:
    """For a survivor: 'reached' (the sample ran it), 'never' (no recording ran it, H5 says so), 'sample-gap' (the
    sample did not, H5 says a recording did), 'no-line-data' (the sample did not; H5 has no data for the line).
    A helper line (outside every override's span) is settled by the helper counts when they leave no doubt: none of
    the override's helper lines ran (never), or all of them ran (sample-gap)."""
    if row.get("reached", "") != "not reached":
        return "reached"
    m = lines.get(row["file"].replace("\\", "/"), {})
    line = int(row["line"])
    if line in m:
        return "sample-gap" if m[line] else "never"
    total, ran = (helpers or {}).get(row["function"], (0, 0))
    if total > 0 and ran == 0:
        return "never"
    if total > 0 and ran == total:
        return "sample-gap"
    return "no-line-data"


def number1(rows: list[dict], lines: dict, helpers: dict | None = None) -> dict:
    files: dict[str, dict] = {}
    never_list = []
    for r in rows:
        f = files.setdefault(r["file"], dict(caught=0, judged=0, survived=0, stillborn=0, never=0, sample_gap=0,
                                             no_line_data=0, reached_survivors=0))
        if r["result"] == "stillborn":
            f["stillborn"] += 1
            continue
        if r["result"] not in ("caught", "survived"):
            continue
        f["judged"] += 1
        if r["result"] == "caught":
            f["caught"] += 1
            continue
        f["survived"] += 1
        k = reach_of(r, lines, helpers)
        r["_reach"] = k
        if k == "never":
            f["never"] += 1
            never_list.append(r)
        elif k == "sample-gap":
            f["sample_gap"] += 1
        elif k == "no-line-data":
            f["no_line_data"] += 1
            never_list.append(r)
        else:
            f["reached_survivors"] += 1
    tot = collections.Counter()
    for f in files.values():
        f["denominator"] = f["judged"] - f["never"]
        f["rate"] = pct(f["caught"], f["denominator"])
        f["denominator_strict"] = f["denominator"] - f["no_line_data"]
        f["rate_strict"] = pct(f["caught"], f["denominator_strict"])
        f["h6_rate"] = pct(f["caught"], f["judged"])
        tot.update({k: v for k, v in f.items() if isinstance(v, int)})
    total = dict(tot)
    total["rate"] = pct(total.get("caught", 0), total.get("denominator", 0))
    total["rate_strict"] = pct(total.get("caught", 0), total.get("denominator_strict", 0))
    total["h6_rate"] = pct(total.get("caught", 0), total.get("judged", 0))
    return dict(files=files, total=total, never=never_list)


# ------------------------------------------------------------------ number 2: host test on the same bugs
def _mutants_index(p: str, cache: dict) -> dict:
    if p not in cache:
        cache[p] = {r["id"]: r for r in read_csv(p)} if p and os.path.exists(p) else {}
    return cache[p]


def load_host(host_dir: str, label_rx: str | None = None) -> dict:
    """(stem, id, operator, old, new) -> the newest host row (with _label, _mtime, _src: the run's mutants row).
    label_rx: only the label folders it matches."""
    out: dict[tuple, dict] = {}
    cache: dict = {}
    rx = re.compile(label_rx) if label_rx else None
    paths = sorted(glob.glob(os.path.join(host_dir, "*", "*.csv")), key=lambda p: (os.path.getmtime(p), p))
    for p in paths:
        label = os.path.basename(os.path.dirname(p))
        if rx and not rx.search(label):
            continue
        stem = os.path.basename(p).split(".")[0]
        js = os.path.join(os.path.dirname(p), stem + ".json")
        src_rows = {}
        if os.path.exists(js) and ".shard" not in os.path.basename(p):
            try:
                with open(js, encoding="utf-8") as fh:
                    src_rows = _mutants_index(absp(json.load(fh).get("mutants_csv", "")), cache)
            except (ValueError, OSError):
                src_rows = {}
        mt = os.path.getmtime(p)
        for r in read_csv(p):
            r["_label"], r["_mtime"], r["_stem"] = label, mt, stem
            r["_src"] = src_rows.get(r["id"])
            out[(stem, r["id"], r["operator"], r["old"], r["new"])] = r
    return out


def host_for(row: dict, host: dict) -> dict | None:
    """The host verdict row for this H6 mutant, if it is the same planted bug."""
    stem = os.path.splitext(os.path.basename(row["file"]))[0]
    h = host.get((stem, row["id"], row["operator"], row["old"], row["new"]))
    if h is None:
        return None
    src = h.get("_src")
    if src is not None:
        same = (src.get("source_line"), str(src.get("col"))) == (row.get("source_line"), str(row.get("col")))
    else:
        same = str(h.get("line")) == str(row.get("line"))
    return h if same else None


def host_status(src_file: str, functions: set[str]) -> str:
    """'' when a host test covers this file, else why not."""
    parts = src_file.replace("\\", "/").split("/")
    batch, stem = parts[2], os.path.splitext(parts[-1])[0]
    if stem in STANCE_FILES:
        return ""
    if stem in H6HOST_FILE_BATCHES:
        diff = os.path.join(ROOT, "src", "readable", H6HOST_FILE_BATCHES[stem])
        if not os.path.exists(diff):
            return f"{rel(diff)} is missing"
        return ""
    if batch in H6HOST_REFUSED:
        return H6HOST_REFUSED[batch]
    if batch not in H6HOST_BATCHES:
        return f"no h6host adapter for the {batch} batch"
    if batch in H6HOST_BATCH_FILES and stem not in H6HOST_BATCH_FILES[batch]:
        return f"the {batch} adapter's diff script ({os.path.basename(H6HOST_BATCHES[batch])}) does not test this file"
    diff = os.path.join(ROOT, "src", "readable", H6HOST_BATCHES[batch])
    try:
        with open(diff, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return f"{rel(diff)} is missing"
    if functions and not any(re.search(r"\b" + re.escape(f) + r"\b", text) for f in functions):
        return f"{os.path.basename(diff)} never names this file's functions (no host test)"
    return ""


def number2(rows: list[dict], host: dict) -> dict:
    funcs: dict[str, set] = collections.defaultdict(set)
    for r in rows:
        funcs[r["file"]].add(r["function"])
    files = {}
    for r in rows:
        if r["result"] not in ("caught", "survived"):
            continue
        f = files.get(r["file"])
        if f is None:
            f = files[r["file"]] = dict(status=host_status(r["file"], funcs[r["file"]]), judged=0, h6_caught=0,
                                        known=0, host_caught=0, surv=0, surv_known=0, surv_host_caught=0,
                                        caught_known=0, caught_host_caught=0, unusable=0, labels=set())
        f["judged"] += 1
        surv = r["result"] == "survived"
        f["surv" if surv else "h6_caught"] += 1
        h = host_for(r, host) if not f["status"] else None
        r["_host"] = h["host"] if h else ""
        if h is None:
            continue
        if h["host"] not in ("caught", "survived"):
            f["unusable"] += 1  # stillborn or id-mismatch on the host side: no verdict
            continue
        f["labels"].add(h["_label"])
        f["known"] += 1
        c = h["host"] == "caught"
        f["host_caught"] += c
        if surv:
            f["surv_known"] += 1
            f["surv_host_caught"] += c
        else:
            f["caught_known"] += 1
            f["caught_host_caught"] += c
    tot = collections.Counter()
    for f in files.values():
        f["labels"] = sorted(f["labels"])
        f["host_complete"] = not f["status"] and f["known"] == f["judged"]
        f["survivors_complete"] = not f["status"] and f["surv_known"] == f["surv"]
        f["host_rate"] = pct(f["host_caught"], f["known"])
        f["either"] = f["h6_caught"] + f["surv_host_caught"]
        f["either_rate"] = pct(f["either"], f["judged"]) if f["survivors_complete"] else None
        f["records_only"] = f["caught_known"] - f["caught_host_caught"]  # the records catch it, the host test not
        if not f["status"]:
            tot.update({k: v for k, v in f.items() if isinstance(v, int) and not isinstance(v, bool)})
            tot["files_tested"] += 1
            tot["files_host_complete"] += f["host_complete"]
            tot["files_survivors_complete"] += f["survivors_complete"]
        else:
            tot["files_untested"] += 1
            tot["judged_untested"] += f["judged"]
    total = dict(tot)
    total["host_rate"] = pct(total.get("host_caught", 0), total.get("known", 0))
    total["either_rate"] = pct(total.get("either", 0), total.get("judged", 0))
    return dict(files=files, total=total)


# ------------------------------------------------------------------ number 3: live compare per family
def number3(offline: str | None, cheat: str | None, live: list[str]) -> dict:
    fam: dict[str, dict] = {}
    seen_files = []

    def add(route: str, cap: dict, is_cheat: bool):
        key = "cheat" if is_cheat else route.split("-")[0]
        F = fam.setdefault(key, dict(routes=set(), runs=0, records=0, match=0, gave_up=0, incomplete=0,
                                     differences=0, **{k: 0 for k in DIFF_KINDS}))
        F["routes"].add(route)
        F["runs"] += 1
        for k in ("records", "match", "gave_up", "incomplete") + DIFF_KINDS:
            F[k] += int(cap.get(k) or 0)
        F["differences"] += sum(int(cap.get(k) or 0) for k in DIFF_KINDS if k != "bad")

    for p, how in [(offline, "offline"), (cheat, "offline cheat")] + [(x, "live") for x in live]:
        if not p:
            continue
        if not os.path.exists(absp(p)):
            seen_files.append(dict(file=rel(p), how=how, missing=True))
            continue
        with open(absp(p), encoding="utf-8") as fh:
            d = json.load(fh)
        n = 0
        for r in d.get("runs", []):
            cap = r.get("capture") or {}
            if not cap:
                continue
            add(r["route"], cap, bool(r.get("cheat")) or r["route"].startswith("cheat-"))
            n += 1
        seen_files.append(dict(file=rel(p), how=how, runs=n, verdict=d.get("verdict")))
    tot = collections.Counter()
    routes = set()
    for k, F in fam.items():
        F["routes"] = sorted(F["routes"])
        if k != "cheat":
            routes |= set(F["routes"])
            tot.update({x: v for x, v in F.items() if isinstance(v, int)})
    total = dict(tot)
    total["routes"] = len(routes)
    return dict(families=fam, total=total, inputs=seen_files)


# ------------------------------------------------------------------ never-reached reasons
def load_reasons(path: str) -> list[dict]:
    if not path or not os.path.exists(path):
        return []
    out = []
    for r in read_csv(path):
        if not r.get("file") or r["file"].startswith("#"):
            continue
        spans = []
        for part in (r.get("lines") or "").split():
            a, _, b = part.partition("-")
            spans.append((int(a), int(b or a)))
        out.append(dict(file=r["file"].strip(), function=(r.get("function") or "").strip(), spans=spans,
                        reason=r["reason"].strip(), detail=(r.get("detail") or "").strip()))
    return out


def reason_of(row: dict, reasons: list[dict]) -> dict | None:
    """The most specific row: file + function + lines, then file + function, then file + lines, then file."""
    stem = os.path.basename(row["file"])
    line = int(row["line"])
    best, score = None, -1
    for r in reasons:
        if r["file"] not in (stem, row["file"]):
            continue
        if r["function"] and r["function"] != row["function"]:
            continue
        if r["spans"] and not any(a <= line <= b for a, b in r["spans"]):
            continue
        s = (2 if r["function"] else 0) + (1 if r["spans"] else 0)
        if s > score:
            best, score = r, s
    return best


def group_never(never: list[dict], reasons: list[dict]) -> dict:
    groups: dict[str, dict] = {}
    for r in never:
        m = reason_of(r, reasons)
        key = m["reason"] if m else "not sorted yet"
        g = groups.setdefault(key, dict(count=0, files=collections.Counter(), items=[]))
        g["count"] += 1
        g["files"][os.path.basename(r["file"])] += 1
        g["items"].append(dict(id=r["id"], file=r["file"], function=r["function"], line=int(r["line"]),
                               reach=r.get("_reach", ""), host=r.get("_host", ""),
                               detail=m["detail"] if m else "", source_line=r.get("source_line", "")))
    for g in groups.values():
        g["files"] = dict(g["files"].most_common())
    return dict(sorted(groups.items(), key=lambda kv: (kv[0] == "not sorted yet", -kv[1]["count"])))


# ------------------------------------------------------------------ equivalent candidates by rule class
CLASSES = [  # (key, plain words for a person). The order is the order of the tests in classify().
    ("give_up_only", "only makes the readable code give up more often (or later); the original then answers, so "
                     "no answer changes. Judge: is doing less of the work acceptable?"),
    ("no_arg_call_words", "an argument word of a call to a game function that takes no arguments, made 1 instead "
                          "of 0. Judge: does the callee really ignore its argument registers?"),
    ("zero_offset", "plus made minus in an address whose offset is a field at +0, so x + 0 and x - 0 are the "
                    "same address. Judge: is the offset really 0 in every build?"),
    ("swapped_arguments", "two arguments swapped in a call. Judge: does the callee only combine them in a way "
                          "where order does not matter (an add, a block+column sum)?"),
    ("boundary_compare", "a comparison moved by one at its boundary (< vs <=, > vs >=, x < 0 vs x < 1). Judge: "
                         "do both sides give the same value at exactly that boundary (a floor, a clamp, a value "
                         "divided afterwards)?"),
    ("clamp_limit", "a clamp's limit made one bigger (clamp(x, 0, 9) made clamp(x, 0, 10)). Judge: can the value "
                    "ever be past the old limit?"),
    ("impossible_value", "a constant compared against a value that never occurs (a pointer of 1, a 33-bit "
                         "number, a gimmick address of 1). Judge: can that value really never occur?"),
    ("return_after_give_up", "the value returned right after the readable code gave up (if (fe_gave_up(ctx)) "
                             "return 0;): the original answers instead, so the value is thrown away. Judge: is it "
                             "thrown away on every path?"),
    ("early_return_value", "the value returned on an early-exit path that is not a give-up (a guard the caller "
                           "may already exclude). Judge: can that path run with its result used?"),
    ("call_argument_constant", "a constant argument passed to another function made one bigger (a yes/no flag 1 "
                               "made 2, a mode 0 made 1). Judge: does the callee treat both values the same?"),
    ("start_value", "a starting value or flag value made one bigger (state = 0 made 1, forged = 1 made 2). Judge: "
                    "is it overwritten before use, or only tested as yes/no?"),
    ("named_constant", "a named constant made one bigger (a stat number, a flag bit, a search mode, a table size). "
                       "Judge: does the other value act the same here (for example a cache check that only "
                       "decides whether to give up)?"),
    ("other", "none of the rules above; a person reads each one"),
]
CLASS_TEXT = dict(CLASSES)
REL_PAIRS = {("<", "<="), ("<=", "<"), (">", ">="), (">=", ">")}
GIVEUP_TEST = re.compile(r"\bif\s*\(\s*fe_gave_up\s*\(")
DEFINE_RX = re.compile(r"^\s*#\s*define\s+([A-Z_][A-Z0-9_]*)\s+\(?\s*(0[xX][0-9a-fA-F]+|\d+)[uUlL]*\s*\)?\s*(?:/[*/].*)?$")
_DEFINES: dict[str, int] = {}


def defines() -> dict[str, int]:
    """Every plain integer #define of the readable sources (the names a mutant can touch)."""
    if not _DEFINES:
        for d in (os.path.join(ROOT, "src", "readable"), os.path.join(ROOT, "include", "readable")):
            for p in glob.glob(os.path.join(d, "**", "*.[ch]"), recursive=True):
                try:
                    with open(p, encoding="utf-8", errors="replace") as fh:
                        for line in fh:
                            m = DEFINE_RX.match(line)
                            if m:
                                _DEFINES.setdefault(m.group(1), int(m.group(2), 0))
                except OSError:
                    pass
    return _DEFINES


def squeeze(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def source_context(c: dict) -> tuple[str, str]:
    """(the changed line as it is in the file now, the code line just before it); empty when it is not found."""
    p = os.path.join(ROOT, c.get("file") or "")
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")
    except OSError:
        return "", ""
    want = squeeze(c.get("source_line") or "")
    n = int(c.get("line") or 0)
    for k in [n] + [n + d for d in range(-40, 41) if d]:
        if want and 1 <= k <= len(lines) and squeeze(lines[k - 1]) == want:
            before = [x for x in lines[max(0, k - 4):k - 1] if x.strip()]
            return lines[k - 1], (before[-1] if before else "")
    return "", ""


def classify(c: dict) -> str:
    """The rule class of one candidate (CLASSES). A grouping for a person, never a verdict."""
    op, old, new = c.get("operator", ""), c.get("old", ""), c.get("new", "")
    src = c.get("source_line") or ""
    why = c.get("h6_why") or ""
    extra = str(c.get("host_extra_giveups") or "").strip()
    if why.startswith("harmless") or op == "giveup" or (extra.lstrip("-").isdigit() and int(extra) != 0):
        return "give_up_only"
    if op == "const" and "guest_call" in src and re.search(r"\b0u\b", old) and re.search(r"(,\s*0u\s*){3,}\)", src):
        return "no_arg_call_words"
    full, before = source_context(c)
    if op == "arith" and old == "+" and new == "-":
        col = int(c["col"]) if str(c.get("col", "")).isdigit() else -1
        names = []
        if full and 0 <= col < len(full) and full[col] == "+":
            m = re.match(r"\s*\(?\s*([A-Z_][A-Z0-9_]*)\b", full[col + 1:])
            names = [m.group(1)] if m else []
        elif col < 0:
            names = re.findall(r"\+\s*([A-Z_][A-Z0-9_]*)", src)
        if any(defines().get(x) == 0 for x in names):
            return "zero_offset"
    if op == "swap":
        return "swapped_arguments"
    if op == "rel" and (old, new) in REL_PAIRS:
        return "boundary_compare"
    if op == "const":
        try:
            v_new = int(re.sub(r"[uUlL]+$", "", new), 0)
        except ValueError:
            v_new = None
        esc = re.escape(old)
        if v_new is not None and v_new > 0xFFFFFFFF:
            return "impossible_value"
        if re.search(r"\bclamp\s*\(.*,\s*" + esc + r"\s*\)", src):
            return "clamp_limit"
        if re.search(r"(<=?|>=?)\s*" + esc + r"\b|\b" + esc + r"\s*(<=?|>=?)", src) \
                and not re.search(r"[=!]=\s*" + esc + r"\b", src):
            return "boundary_compare"
        if re.search(r"[=!]=\s*" + esc + r"\b", src):
            return "impossible_value"
        if re.match(r"^\s*return\s+" + esc + r"\s*;", src):
            return "return_after_give_up" if GIVEUP_TEST.search(before) else "early_return_value"
        if re.match(r"^\s*(?:[A-Za-z_]\w*\s+)*[A-Za-z_]\w*\s*=\s*" + esc + r"\s*;", src):
            return "start_value"
        if re.search(r"\b[a-z_]\w*\s*\(", src) and re.search(r"[(,]\s*" + esc + r"\s*[,)]", src):
            return "call_argument_constant"
    if op == "named":
        return "named_constant"
    return "other"


def load_equiv(path: str) -> list[dict]:
    if not path or not os.path.isfile(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("function") and not r["function"].startswith("#")]


def cleared_by(c: dict, eq: list[dict]) -> str:
    """The `why` of the equivalence entry naming this candidate (same key as mutate.apply_equivalents, and the pinned
    id and line when the entry has "[id X line N]"), or ""."""
    for e in eq:
        if all(str(c.get(f, "")) == (e.get(f) or "") for f in EQUIV_KEY):
            m = PIN_RX.search(e.get("why") or "")
            if m is None or (str(c.get("id")) == m.group(1) and str(c.get("line")) == m.group(2)):
                return e.get("why") or ""
    return ""


def _find_src_row(stem: str, h: dict, cache: dict) -> dict | None:
    """The mutants.csv row of a host verdict whose run kept no mutants.csv path (stance shards)."""
    for d in MUTATE_DIRS:
        for p in sorted(glob.glob(os.path.join(d, f"game-h6play-*-{stem}", "mutants.csv")),
                        key=os.path.getmtime, reverse=True):
            r = _mutants_index(p, cache).get(h["id"])
            if r and (r["operator"], r["old"], r["new"], str(r["line"])) == (h["operator"], h["old"], h["new"],
                                                                            str(h["line"])):
                return r
    return None


def candidates(host_dir: str, host: dict, rows: list[dict], label_rx: str, equiv: str | None = None) -> dict:
    """The rounds 11-13 candidates: the misses of the host runs whose label matches label_rx (the newest verdict
    among those runs). For each: its verdict in today's sample and in the newest host run of any label. A miss of a
    later host run that is not one of them is "new, not sorted"."""
    today = {}
    for r in rows:
        today[(os.path.splitext(os.path.basename(r["file"]))[0], r["id"], r["operator"], r["old"], r["new"])] = r
    cache: dict = {}
    old = load_host(host_dir, label_rx)

    def cand(key, h):
        src = h.get("_src") or _find_src_row(key[0], h, cache) or {}
        c = dict(id=h["id"], file=src.get("file") or key[0], stem=key[0], function=h["function"], line=h["line"],
                 operator=h["operator"], old=h["old"], new=h["new"], source_line=src.get("source_line", ""),
                 col=src.get("col", ""), h6_why=h.get("h6_why", ""), h6_reached=h.get("h6_reached", ""),
                 host_extra_giveups=h.get("host_extra_giveups", ""), label=h["_label"])
        t = today.get(key)
        c["today"] = t["result"] if t else "not in today's sample"
        latest = host.get(key)
        c["newest_host"] = f"{latest['host']} ({latest['_label']})" if latest else ""
        c["class"] = classify(c)
        c["cleared"] = cleared_by(c, eq)
        return c

    eq = load_equiv(equiv)

    out = [cand(k, h) for k, h in sorted(old.items()) if h.get("h6") == "survived" and h.get("host") == "survived"]
    seen = {(c["stem"], c["id"], c["operator"], c["old"], c["new"]) for c in out}
    new = [cand(k, h) for k, h in sorted(host.items()) if h.get("h6") == "survived" and h.get("host") == "survived"
           and k not in seen]
    by = collections.OrderedDict((k, dict(count=0, text=CLASS_TEXT[k], files=collections.Counter(), items=[]))
                                 for k, _ in CLASSES)
    for c in out:
        g = by[c["class"]]
        g["count"] += 1
        g["files"][c["stem"]] += 1
        g["items"].append(c)
    for g in by.values():
        g["files"] = dict(g["files"].most_common())
    cleared = [c for c in out if c["cleared"]]
    cleared_new = [c for c in new if c["cleared"]]
    return dict(count=len(out), classes=by, new_not_sorted=new,
                cleared=len(cleared), cleared_new=len(cleared_new),
                cleared_by_class=collections.Counter(c["class"] for c in cleared + cleared_new),
                pile=len(out) - len(cleared), pile_new=len(new) - len(cleared_new),
                today=collections.Counter(c["today"] for c in out),
                newest_host=collections.Counter(c["newest_host"].split(" ")[0] for c in out))


# ------------------------------------------------------------------ report
def build(a) -> dict:
    latest_p = os.path.join(PLAY, "latest.json")
    sample_path = a.sample
    if not sample_path:
        sample_path = os.path.join(PLAY, "h6_sample.json")
    sample, rows = load_sample(absp(sample_path))
    h5 = a.h5 or sample["total"].get("h5_input")
    lines = h5_line_map(h5)
    n1 = number1(rows, lines, h5_helpers(h5))
    host = load_host(a.host_dir)
    n2 = number2(rows, host)
    n3 = number3(a.offline, a.offline_cheat, a.live)
    never = group_never(n1.pop("never"), load_reasons(a.reasons))
    cands = candidates(a.host_dir, host, rows, a.candidate_labels, a.equiv)
    t = sample["total"]
    check = dict(sample_caught=t.get("caught"), sample_judged=t.get("judged"),
                 csv_caught=n1["total"].get("caught"), csv_judged=n1["total"].get("judged"))
    check["agrees"] = (check["sample_caught"], check["sample_judged"]) == (check["csv_caught"], check["csv_judged"])
    latest = {}
    if os.path.exists(latest_p):
        with open(latest_p, encoding="utf-8") as fh:
            latest = json.load(fh).get("h6_sample", {})
    return dict(inputs=dict(sample=rel(absp(sample_path)), sample_run=t.get("run"), latest_h6_sample=latest.get("run"),
                            h5=rel(h5) if h5 else None, host_dir=rel(a.host_dir), reasons=rel(a.reasons)),
                check=check, number1=n1, number2=n2, number3=n3, never_by_reason=never, candidates=cands)


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, set):
        return sorted(x)
    if isinstance(x, collections.Counter):
        return dict(x)
    return x


def print_report(R: dict, show_never: bool, show_cands: bool, out=None) -> None:
    out = out or sys.stdout
    p = lambda *s: print(*s, file=out)  # noqa: E731
    i, c = R["inputs"], R["check"]
    p(f"h6three: sample {i['sample']} (run {i['sample_run']}), H5 {i['h5']}, host verdicts {i['host_dir']}")
    if not c["agrees"]:
        p(f"  WARNING: the mutants.csv files give {c['csv_caught']} / {c['csv_judged']}, the sample json says "
          f"{c['sample_caught']} / {c['sample_judged']}")
    n1 = R["number1"]
    T = n1["total"]
    p("")
    p("1. RECORDINGS, ON REACHED LINES (sampled H6; survivors on lines no recording ran are listed, not counted)")
    p(f"   one-percent H6 today: {fmt_pct(T['caught'], T['judged'])}")
    p(f"   reached lines only:   {fmt_pct(T['caught'], T['denominator'])}  ({T['never']} left out: H5 says no "
      f"recording ran the line)")
    p(f"   also leaving out the {T['no_line_data']} on helper lines H5 has no data for: "
      f"{fmt_pct(T['caught'], T['denominator_strict'])}")
    p(f"   kept in: {T['sample_gap']} survivors the sample did not reach but some recording did (sample gaps)")
    p(f"   {'file':<24} {'H6 today':>18} {'reached lines':>18} {'never':>6} {'gap':>5} {'nodata':>6}")
    for f, v in sorted(n1["files"].items(), key=lambda kv: (kv[1]["rate"] is None, kv[1]["rate"] or 0)):
        p(f"   {os.path.basename(f):<24} {fmt_pct(v['caught'], v['judged']):>18} "
          f"{fmt_pct(v['caught'], v['denominator']):>18} {v['never']:>6} {v['sample_gap']:>5} {v['no_line_data']:>6}")
    n2 = R["number2"]
    T2 = n2["total"]
    p("")
    p("2. HOST TEST, ON THE SAME PLANTED BUGS (the batches' *_diff.py; never added into H6)")
    p(f"   files with a host test: {T2.get('files_tested', 0)}; without: {T2.get('files_untested', 0)} "
      f"({T2.get('judged_untested', 0)} planted bugs, listed below, not guessed)")
    p(f"   host test alone, on every planted bug it has a verdict for: {fmt_pct(T2.get('host_caught', 0), T2.get('known', 0))}"
      f" ({T2.get('files_host_complete', 0)} files complete)")
    p(f"   H6 survivors the host test catches: {fmt_pct(T2.get('surv_host_caught', 0), T2.get('surv_known', 0))}")
    partial = T2.get("files_tested", 0) - T2.get("files_survivors_complete", 0)
    p(f"   records or host test (kept apart, on files with a host test): {fmt_pct(T2.get('either', 0), T2.get('judged', 0))}"
      + (f" ({partial} file(s) partial: a survivor without a host verdict counts as not caught)" if partial else ""))
    p(f"   caught by the records but not by the host test: {T2.get('records_only', 0)} "
      f"(of {T2.get('caught_known', 0)} record-caught bugs with a host verdict)")
    p(f"   {'file':<24} {'host alone':>20} {'survivors caught':>18} {'records or host':>18} {'rec only':>8}  note")
    for f, v in sorted(n2["files"].items(), key=lambda kv: (bool(kv[1]["status"]), kv[0])):
        if v["status"]:
            p(f"   {os.path.basename(f):<24} {'-':>20} {'-':>18} {'-':>18} {'-':>8}  NO HOST TEST: {v['status']}")
            continue
        note = []
        if not v["host_complete"]:
            note.append(f"host verdict for {v['known']} of {v['judged']}")
        if not v["survivors_complete"]:
            note.append(f"survivors without a verdict: {v['surv'] - v['surv_known']}")
        either = fmt_pct(v["either"], v["judged"]) if v["survivors_complete"] else "partial"
        p(f"   {os.path.basename(f):<24} {fmt_pct(v['host_caught'], v['known']):>20} "
          f"{fmt_pct(v['surv_host_caught'], v['surv_known']):>18} {either:>18} {v['records_only']:>8}  {'; '.join(note)}")
    n3 = R["number3"]
    p("")
    p("3. LIVE COMPARE (the round's integrate: offline replay of every route + the new chapter live; cheat apart)")
    for k, F in sorted(n3["families"].items(), key=lambda kv: (kv[0] == "cheat", kv[0])):
        p(f"   {k:<6} {len(F['routes']):>3} routes  {F['records']:>8} records  {F['match']:>8} match  "
          f"{F['gave_up']:>5} gave up  {F['incomplete']:>5} incomplete  bad {F['bad']}  other differences "
          f"{F['differences']}")
    T3 = n3["total"]
    p(f"   all (no cheat): {T3.get('routes', 0)} routes, {T3.get('records', 0)} records, bad {T3.get('bad', 0)}, "
      f"other differences {T3.get('differences', 0)}")
    for x in n3["inputs"]:
        p(f"   input: {x['file']} ({x['how']}{', MISSING' if x.get('missing') else ', ' + str(x.get('runs')) + ' runs, ' + str(x.get('verdict'))})")
    p("")
    p("NEVER REACHED, BY REASON (survivors left out of number 1, plus the helper lines H5 has no data for)")
    for k, g in R["never_by_reason"].items():
        p(f"   {g['count']:>4}  {k}  ({', '.join(f'{f} {n}' for f, n in g['files'].items())})")
        if show_never:
            for it in g["items"]:
                p(f"         {it['id']:<40} {os.path.basename(it['file'])}:{it['line']:<5} {it['reach']:<12} "
                  f"host={it['host'] or '-':<9} {it['source_line'][:70]}")
    C = R["candidates"]
    p("")
    p(f"EQUIVALENT CANDIDATES (rounds 11-13): {C['count']}, by rule class -- FOR THE OWNER TO DECIDE; "
      + (f"cleared by the owner: {C['cleared']} (+{C['cleared_new']} of the new)" if C["cleared"] + C["cleared_new"]
         else "none marked"))
    p(f"   judgement pile left: {C['pile']} of the {C['count']}, {C['pile_new']} of the {len(C['new_not_sorted'])} new"
      + (f"; cleared by class: {', '.join(f'{k} {n}' for k, n in sorted(C['cleared_by_class'].items()))}"
         if C["cleared_by_class"] else "")
      + " (cleared cases leave the pile; number 1 above is unchanged, F-026)")
    for k, g in C["classes"].items():
        if not g["count"]:
            continue
        p(f"   {g['count']:>4}  {k}: {g['text']}")
        p(f"         files: {', '.join(f'{f} {n}' for f, n in g['files'].items())}")
        for it in (g["items"] if show_cands else g["items"][:3]):
            p(f"         {it['id']:<40} {it['operator']} {it['old']!r} -> {it['new']!r}   {it['source_line'][:60]}"
              + ("   [owner ok]" if it.get("cleared") else ""))
    p(f"   in today's sample: {', '.join(f'{k} {v}' for k, v in sorted(C['today'].items()))}; "
      f"newest host verdict: {', '.join(f'{k} {v}' for k, v in sorted(C['newest_host'].items()))}")
    if C["new_not_sorted"]:
        nn = collections.Counter(c["stem"] for c in C["new_not_sorted"])
        p(f"   NEW (host runs after round 13, not part of the 237, not sorted by a person): {len(C['new_not_sorted'])} "
          f"({', '.join(f'{f} {n}' for f, n in nn.most_common())})")
        nc = collections.Counter(c["class"] for c in C["new_not_sorted"])
        p(f"         by rule class: {', '.join(f'{k} {n}' for k, n in nc.most_common())}")
        if show_cands:
            for it in C["new_not_sorted"]:
                p(f"         {it['id']:<40} {it['class']:<22} {it['operator']} {it['old']!r} -> {it['new']!r}   "
                  f"{it['source_line'][:50]}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", help="sampled H6 json (default build/harness/h56/play/h6_sample.json)")
    ap.add_argument("--h5", help="H5 json for the reach data (default: the one the sample used)")
    ap.add_argument("--host-dir", default=HOST_DIR)
    ap.add_argument("--offline", default=R13_OFFLINE)
    ap.add_argument("--offline-cheat", default=R13_OFFLINE_CHEAT)
    ap.add_argument("--live", action="append", help=f"live summary.json (repeatable; default {R13_LIVE})")
    ap.add_argument("--reasons", default=REASONS)
    ap.add_argument("--candidate-labels", default=CANDIDATE_LABELS,
                    help="regex of the host labels whose misses are the rounds 11-13 candidates")
    ap.add_argument("--equiv", default=EQUIV, help="the owner's equivalence list (default tools/harness/mutants_equivalent.csv)")
    ap.add_argument("--never", action="store_true", help="list every never-reached survivor")
    ap.add_argument("--candidates", action="store_true", help="list every candidate id")
    ap.add_argument("--json", help="write everything to this file (the only file this command writes)")
    a = ap.parse_args(argv)
    if a.live is None:
        a.live = [R13_LIVE]
    R = build(a)
    print_report(R, a.never, a.candidates)
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)) or ".", exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(_jsonable(R), fh, indent=1)
        print(f"h6three: wrote {a.json}")
    return 0 if R["check"]["agrees"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
