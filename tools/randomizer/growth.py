#!/usr/bin/env python3
"""Randomizer track "growth" (F-043 #2; docs/rando/GROWTH.md): the three growth modes and two bases modes on top
of slice 1, with the same option shapes as our FE8 port's randomizer (Growths Redistribute / Delta / Full, Growth
variance 30%, Growth min 5%, Growth max 80%, Adjust HP growths; Bases Redistribute / Delta, Base variance 5).

    plan_growth(tables, rng, opts) -> (edits, spoiler_lines)

tables  a randolib.Facts (the original rows)
rng     the run seed (text, as given to rando.py) or a random.Random; this track derives its OWN sub-seed from it
        and the track name, then one stream per (purpose, person), so no other track's draws are disturbed
opts    DEFAULT_OPTS keys, plus optional "base_plan": the slice-1 plan (randolib.make_plan) the edits go on top of
        (its classes give the stat caps for the bases; its values are the "old" side of each edit)

edits   [{"table": "Person", "index": 12, "label": "PID_...", "cell": "growth.hp", "old": "45", "new": "50"}, ...]
        only cells whose value differs from the base plan (or the original rows when there is no base plan)

Default opts ("slice1" for both) give NO edits, so a default run stays byte-identical to slice 1.
Our own code: the algorithms follow our own FE8 port (port/reforged/reforged_rando.c, a sister project); public
Fates randomizers (GPL) were read for facts only (growth / base totals per person, scaled to the join level).

    python tools/randomizer/growth.py make --seed S [--growths MODE] [--growth-variance N] [--growth-min N]
        [--growth-max N] [--adjust-hp on|off] [--bases MODE] [--base-variance N] [--scale-to-level on|off] --out DIR
    python tools/randomizer/growth.py robot ...      (the track's one headless robot check; see main())
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "growth"
TOOL = "rando-growth-v1"
STEP = 5                       # every growth this track writes is a multiple of 5 (as all of the game's own are)
GROWTH_MODES = ("slice1", "redistribute", "delta", "full")
BASE_MODES = ("slice1", "redistribute", "delta")
DEFAULT_OPTS = {"growths": "slice1", "growth_variance": 30, "growth_min": 5, "growth_max": 80, "adjust_hp": False,
                "bases": "slice1", "base_variance": 5, "scale_to_level": True}
GROWTH_TOP = 125               # the Person growth cell is a signed byte; slice 1's guard allows 0..127
PROMOTED_LEVELS = 20           # a promoted joiner with no internal level counts as 20 levels more


# ------------------------------------------------------------------ options and random streams
def check_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS)
    o.update({k: v for k, v in (opts or {}).items() if k in DEFAULT_OPTS})
    if o["growths"] not in GROWTH_MODES:
        raise R.RandoError(f"growths: one of {', '.join(GROWTH_MODES)}")
    if o["bases"] not in BASE_MODES:
        raise R.RandoError(f"bases: one of {', '.join(BASE_MODES)}")
    for k, lo, hi in (("growth_variance", 0, 100), ("growth_min", 0, 100), ("growth_max", 0, GROWTH_TOP),
                      ("base_variance", 1, 10)):
        v = o[k]
        if isinstance(v, str):
            v = v.strip().rstrip("%")
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise R.RandoError(f"{k}: a whole number {lo}-{hi}") from None
        if not lo <= v <= hi:
            raise R.RandoError(f"{k}: {v} is outside {lo}-{hi}")
        o[k] = v
    o["adjust_hp"] = bool(o["adjust_hp"])
    o["scale_to_level"] = bool(o["scale_to_level"])
    if o["growths"] != "slice1" and growth_bounds(o)[0] > growth_bounds(o)[1]:
        raise R.RandoError(f"growth min {o['growth_min']} and max {o['growth_max']} leave no multiple of 5 between them")
    return o


def growth_bounds(o: dict) -> tuple[int, int]:
    """Growth min/max moved inward to multiples of 5 (min up, max down)."""
    return -(-o["growth_min"] // STEP) * STEP, o["growth_max"] // STEP * STEP


def opts_text(o: dict, part: str) -> str:
    on = lambda b: "on" if b else "off"  # noqa: E731
    if part == "growths":
        if o["growths"] == "slice1":
            return "growths=slice1"
        t = f"growths={o['growths']}"
        if o["growths"] != "full":
            t += f" variance={o['growth_variance']}"
        return t + f" min={o['growth_min']} max={o['growth_max']} adjust-hp={on(o['adjust_hp'])}"
    if o["bases"] == "slice1":
        return "bases=slice1"
    return f"bases={o['bases']} variance={o['base_variance']} scale-to-level={on(o['scale_to_level'])}"


def track_key(rng) -> str:
    """This track's sub-seed: from the run seed text and the track name (or 256 bits of a given Random)."""
    if isinstance(rng, random.Random):
        base = "random:" + format(rng.getrandbits(256), "064x")
    else:
        base = "seed:" + R.check_seed(str(rng))
    return hashlib.sha256("\x1f".join([TOOL, base, TRACK]).encode("utf-8")).hexdigest()


def stream(key: str, purpose: str, text: str, pid: str) -> random.Random:
    h = hashlib.sha256("\x1f".join([key, purpose, text, pid]).encode("utf-8")).digest()
    return random.Random(int.from_bytes(h, "big"))


# ------------------------------------------------------------------ growth modes (8 stats, HP first)
def growths_redistribute(r: random.Random, v: list[int], lo: int, hi: int, var: int, adj: bool) -> list[int]:
    """The total moves by up to var (in steps of 5), then is shared out again in chunks of 5, each stat between
    lo and hi; HP is the fall-through pick (2 of 9 picks, 4 of 11 with adjust-HP)."""
    total = sum(v)
    total -= total % STEP
    move = STEP * r.randint(0, var // STEP)
    total = total + move if r.randrange(2) == 0 else total - move
    n = len(v)
    out = [lo] * n
    left = total - n * lo
    if left >= n * (hi - lo):
        return [hi] * n
    picks = 11 if adj else 9
    guard = 0
    while left > 0 and guard < 4096:
        guard += 1
        pick = r.randrange(picks)
        s = pick if 1 <= pick <= n - 1 else 0
        if out[s] + STEP <= hi:
            out[s] += STEP
            left -= STEP
    for s in range(n):           # a stream that kept hitting full stats ends in order
        while left > 0 and out[s] + STEP <= hi:
            out[s] += STEP
            left -= STEP
    return out


def growths_delta(r: random.Random, v: list[int], lo: int, hi: int, d: int, adj: bool) -> list[int]:
    """Each growth moves up or down by up to d (in steps of 5), kept between lo and hi; with adjust-HP, HP never
    goes down."""
    out = []
    steps = d // STEP
    for s, g in enumerate(v):
        g = int(round(g / STEP)) * STEP
        up = r.randrange(2) == 0
        if s == 0 and adj:
            up = True
        if up and g < hi:
            g += STEP * r.randint(0, min(steps, max(0, (hi - g) // STEP)))
        elif g > lo:
            g -= STEP * r.randint(0, min(steps, max(0, (g - lo) // STEP)))
        out.append(min(max(g, lo), hi))
    return out


def growths_full(r: random.Random, n: int, lo: int, hi: int, adj: bool) -> list[int]:
    """Each growth new, between lo and hi (multiples of 5); with adjust-HP an HP growth in the lower half is
    raised by half the range."""
    k = (hi - lo) // STEP
    out = [lo + STEP * r.randint(0, k) for _ in range(n)]
    half = STEP * (k // 2)
    if adj and out[0] < lo + half:
        out[0] = min(out[0] + half, hi)
    return out


# ------------------------------------------------------------------ bases modes
def join_level(facts: R.Facts, p: dict) -> int:
    """The person's join level counted from a base class's level 1: level + internal level, or + 20 for a promoted
    class with no internal level given."""
    lvl, il = R.ival(p.get("level", 1)), R.ival(p.get("internal_level", -1))
    if il >= 0:
        return lvl + il
    j = facts.jobs.get(p["job"])
    return lvl + (PROMOTED_LEVELS if j and facts.promoted(j) else 0)


def base_variance_for(o: dict, level: int) -> int:
    """Base variance scaled to the join level: var at level 1, about 1.5x var at level 11, 2x at level 21."""
    if not o["scale_to_level"]:
        return o["base_variance"]
    return max(1, (o["base_variance"] * (19 + max(level, 1)) + 10) // 20)


def base_bounds(facts: R.Facts, p: dict, jid: str) -> tuple[list[int], list[int]]:
    """Personal base bounds so that class base + personal stays within 0 (HP 1) and the class cap (Job.max + the
    person's limit modifier): the same caps slice 1 uses."""
    j = facts.jobs[jid]
    lo, hi = [], []
    for s in R.STATS:
        jb = R.ival(j[f"base.{s}"])
        a = (1 if s == "hp" else 0) - jb
        b = R.ival(j[f"max.{s}"]) + R.ival(p[f"limit_mod.{s}"]) - jb
        lo.append(a)
        hi.append(max(a, b))
    return lo, hi


def bases_redistribute(r: random.Random, v: list[int], lo: list[int], hi: list[int], var: int) -> list[int]:
    """The total moves by up to var, then is shared out again 1-3 points at a time (HP 2 of 9 picks), every stat
    starting at 0 (or its floor) and kept within its bounds."""
    total = sum(v)
    move = r.randint(0, var)
    total = total + move if r.randrange(2) == 0 else total - move
    n = len(v)
    out = [min(max(0, lo[s]), hi[s]) for s in range(n)]
    left = max(0, total - sum(out))
    guard = 0
    while left > 0 and guard < 2048:
        guard += 1
        pick = r.randrange(9)
        s = pick if 1 <= pick <= n - 1 else 0
        amt = min(r.randint(1, 3), left, hi[s] - out[s])
        if amt <= 0:
            if all(out[i] >= hi[i] for i in range(n)):
                break
            continue
        out[s] += amt
        left -= amt
    return out


def bases_delta(r: random.Random, v: list[int], lo: list[int], hi: list[int], d: int) -> list[int]:
    out = []
    for s, b in enumerate(v):
        m = r.randint(0, d)
        b = b + m if r.randrange(2) == 0 else b - m
        out.append(min(max(b, lo[s]), hi[s]))
    return out


# ------------------------------------------------------------------ the plan
def plan_growth(tables: R.Facts, rng, opts: dict | None = None) -> tuple[list[dict], list[str]]:
    facts = tables
    o = check_opts(opts)
    base_plan = (opts or {}).get("base_plan")
    if o["growths"] == "slice1" and o["bases"] == "slice1":
        return [], []
    key = track_key(rng)
    bp = {e["pid"]: e for e in base_plan["persons"]} if base_plan else {}
    lo_g, hi_g = growth_bounds(o)
    gtext, btext = opts_text(o, "growths"), opts_text(o, "bases")
    edits: list[dict] = []
    lines = [f"Growth track ({TOOL}): {gtext}; {btext}"]
    for p in facts.persons:
        if not facts.in_scope(p):
            continue
        pid = p["label"]
        e = bp.get(pid)
        jid = e["job"] if e else p["job"]
        orig_g = [R.ival(p[f"growth.{s}"]) for s in R.STATS]
        orig_b = [R.ival(p[f"base.{s}"]) for s in R.STATS]
        cur_g = list(e["growth"]) if e else orig_g
        cur_b = list(e["base"]) if e else orig_b
        name = e["name"] if e else facts.pname(p)
        new_g, new_b = cur_g, cur_b
        if o["growths"] != "slice1":
            r = stream(key, "growths", gtext, pid)
            if o["growths"] == "redistribute":
                new_g = growths_redistribute(r, orig_g, lo_g, hi_g, o["growth_variance"], o["adjust_hp"])
            elif o["growths"] == "delta":
                new_g = growths_delta(r, orig_g, lo_g, hi_g, o["growth_variance"], o["adjust_hp"])
            else:
                new_g = growths_full(r, len(R.STATS), lo_g, hi_g, o["adjust_hp"])
            lines.append(f"{name} [{pid}] growths: {' '.join(map(str, orig_g))} (total {sum(orig_g)})  ->  "
                         f"{' '.join(map(str, new_g))} (total {sum(new_g)})")
        if o["bases"] != "slice1":
            lo_b, hi_b = base_bounds(facts, p, jid)
            lvl = join_level(facts, p)
            var = base_variance_for(o, lvl)
            r = stream(key, "bases", btext, pid)
            if o["bases"] == "redistribute":
                new_b = bases_redistribute(r, orig_b, lo_b, hi_b, var)
            else:
                new_b = bases_delta(r, orig_b, lo_b, hi_b, var)
            lines.append(f"{name} [{pid}] bases (join level {lvl}, variance {var}): {' '.join(map(str, orig_b))} "
                         f"(total {sum(orig_b)})  ->  {' '.join(map(str, new_b))} (total {sum(new_b)})")
        for kind, cur, new in (("growth", cur_g, new_g), ("base", cur_b, new_b)):
            for n, s in enumerate(R.STATS):
                if new[n] != cur[n]:
                    edits.append({"table": "Person", "index": R.ival(p["index"]), "label": pid,
                                  "cell": f"{kind}.{s}", "old": str(cur[n]), "new": str(new[n])})
    return edits, lines


def apply_edits(plan: dict, edits: list[dict], opts: dict | None = None) -> dict:
    """A copy of a slice-1 plan with this track's edits in its persons' growth/base lists (so randolib.render
    writes them). Nothing is added when there are no edits (default opts: byte-identical to slice 1)."""
    if not edits:
        return plan
    out = copy.deepcopy(plan)
    by = {e["pid"]: e for e in out["persons"]}
    for ed in edits:
        kind, s = ed["cell"].split(".", 1)
        by[ed["label"]][kind][R.STATS.index(s)] = int(ed["new"])
    o = check_opts(opts)
    out.setdefault("tracks", {})[TRACK] = {"tool": TOOL, "opts": o}
    return out


def _clamp(x: int, lo: int, hi: int) -> int:
    return min(max(x, lo), hi)


def check_bounds(facts: R.Facts, plan: dict, opts: dict) -> list[str]:
    """This track's own guard, recomputed from the plan and the original rows: every growth / base the modes
    wrote is within its bounds and moved no further than the variance allows. [] = all good."""
    o = check_opts(opts)
    lo_g, hi_g = growth_bounds(o)
    gv = o["growth_variance"]
    bad = []
    for e in plan["persons"]:
        p = facts.by_pid[e["pid"]]
        og = [R.ival(p[f"growth.{s}"]) for s in R.STATS]
        ob = [R.ival(p[f"base.{s}"]) for s in R.STATS]
        g, b = e["growth"], e["base"]
        n8 = len(R.STATS)
        if o["growths"] != "slice1":
            if any(x % STEP or x < lo_g or x > hi_g for x in g):
                bad.append(f"{e['pid']}: growth outside {lo_g}-{hi_g} or not a multiple of 5: {g}")
            if o["growths"] == "redistribute":
                t = sum(og) - sum(og) % STEP
                lo_t, hi_t = _clamp(t - gv, n8 * lo_g, n8 * hi_g), _clamp(t + gv, n8 * lo_g, n8 * hi_g)
                if not lo_t <= sum(g) <= hi_t:
                    bad.append(f"{e['pid']}: growth total {sum(g)} outside {lo_t}-{hi_t}")
            if o["growths"] == "delta":
                for n in range(n8):
                    r5 = int(round(og[n] / STEP)) * STEP
                    if not _clamp(r5 - gv, lo_g, hi_g) <= g[n] <= _clamp(r5 + gv, lo_g, hi_g):
                        bad.append(f"{e['pid']}: growth {R.STATS[n]} moved {og[n]} -> {g[n]} (variance {gv})")
                if o["adjust_hp"] and g[0] < _clamp(int(round(og[0] / STEP)) * STEP, lo_g, hi_g):
                    bad.append(f"{e['pid']}: HP growth went down with adjust-HP on")
        if o["bases"] != "slice1":
            lo_b, hi_b = base_bounds(facts, p, e["job"])
            var = base_variance_for(o, join_level(facts, p))
            if any(not lo_b[n] <= b[n] <= hi_b[n] for n in range(n8)):
                bad.append(f"{e['pid']}: base outside the class caps: {b}")
            if o["bases"] == "redistribute":
                s0 = sum(_clamp(0, lo_b[n], hi_b[n]) for n in range(n8))
                lo_t, hi_t = _clamp(sum(ob) - var, s0, sum(hi_b)), _clamp(sum(ob) + var, s0, sum(hi_b))
                if not lo_t <= sum(b) <= hi_t:
                    bad.append(f"{e['pid']}: base total {sum(b)} outside {lo_t}-{hi_t} (variance {var})")
            if o["bases"] == "delta":
                for n in range(n8):
                    if not _clamp(ob[n] - var, lo_b[n], hi_b[n]) <= b[n] <= _clamp(ob[n] + var, lo_b[n], hi_b[n]):
                        bad.append(f"{e['pid']}: base {R.STATS[n]} moved {ob[n]} -> {b[n]} (variance {var})")
    return bad


# ------------------------------------------------------------------ command line (host tool + robot check)
def build_files(facts: R.Facts, seed: str, opts: dict, switches: dict | None = None) -> tuple[dict, dict, list]:
    """Slice 1 (default switches) + this track only: (files, plan, spoiler lines)."""
    base = R.make_plan(facts, seed, switches)
    edits, lines = plan_growth(facts, seed, dict(opts, base_plan=base))
    plan = apply_edits(base, edits, opts)
    files = R.render(facts, plan)
    if lines:
        files["spoiler.txt"] = files["spoiler.txt"] + ("\n" + "\n".join(lines) + "\n").encode("utf-8")
    return files, plan, lines



# ------------------------------------------------------------------ round 62: the growth floor (F-049 + addendum)
# The owner: every randomized stat's TOTAL growth (personal + class) is at least 20 and at most 100, always, also
# for stats that were 0 ("Yes, min 20 always"). Move is no growth and is not touched. The floor works on the files a
# run lays (tables/Person.csv over the original rows, tables/Job.csv over the original classes), as the very last
# step, so every track before it (slice 1, growth modes, class growths, children, promotions) is seen as laid.
FLOOR_LO, FLOOR_HI = 20, 100


def floor_on(switches: dict, o: dict) -> bool:
    """The floor runs whenever growths are randomized: slice 1's Growths switch, a growth mode, class growths or
    the children (their growths)."""
    s = dict(R.DEFAULT_SWITCHES, **(switches or {}))
    return bool(s.get("growths") or o.get("growth_mode", "slice1") != "slice1"
                or o.get("class_growths", "off") != "off" or o.get("children"))


def _csv_rows(data: bytes | None) -> tuple[list[str], list[list[str]]]:
    import csv
    import io
    if not data:
        return [], []
    rows = list(csv.reader(io.StringIO(data.decode("utf-8").lstrip(chr(0xFEFF)))))
    return (rows[0], rows[1:]) if rows else ([], [])


def final_rows(facts: R.Facts, files: dict) -> tuple[dict, dict]:
    """({pid: Person row}, {jid: Job row}) as the run lays them: the original rows with the CSVs' cells on top."""
    persons = {p["label"]: dict(p) for p in facts.persons}
    jobs = {j["label"]: dict(j) for j in facts.job_list}
    head, body = _csv_rows(files.get("tables/Person.csv"))
    for r in body:
        d = dict(zip(head, r))
        if d.get("label") in persons:
            persons[d["label"]].update({k: v for k, v in d.items() if k not in ("index", "label")})
    head, body = _csv_rows(files.get("tables/Job.csv"))
    for r in body:
        d = dict(zip(head, r))
        if d.get("label") in jobs:
            jobs[d["label"]].update({k: v for k, v in d.items() if k not in ("index", "label")})
    return persons, jobs


def floor_people(facts: R.Facts) -> list[str]:
    """Whose growths the floor keeps: the army (slice 1's scope) and the children, in Person index order."""
    out = [p["label"] for p in facts.persons if facts.in_scope(p)]
    try:
        import children as C
        out += [c["label"] for c in C.children(facts) if c["label"] not in out]
    except Exception:  # noqa: BLE001  (a game without children: the army only)
        pass
    return sorted(set(out), key=lambda x: R.ival(facts.by_pid[x]["index"]))


def floor_classes(jobs: dict, jid: str, facts: R.Facts | None = None) -> list[str]:
    """The person's class and, for a base class, the classes its Master Seal can make of it (the final promotion
    cells; a promoted class's cells are not Master Seal targets)."""
    out = [jid]
    j = jobs.get(jid) or {}
    if facts is not None and facts.promoted(j):
        return out
    for c in ("promotion.1", "promotion.2"):
        t = j.get(c, "")
        if t and t in jobs and t not in out:
            out.append(t)
    return out


def _r5_up(v: int) -> int:
    return -(-v // STEP) * STEP


def _r5_down(v: int) -> int:
    return (v // STEP) * STEP


def plan_floor(facts: R.Facts, files: dict) -> tuple[dict, list[str], list[str]]:
    """({pid: {growth.stat: new}}, spoiler lines, problems). A personal growth moves only as far as needed so that
    personal + class lands in 20..100 for the person's class, and for its promotions too when one personal value
    can satisfy them all (else the class they join as wins). Steps of 5, never below 0."""
    persons, jobs = final_rows(facts, files)
    cells: dict[str, dict] = {}
    lines, bad = [], []
    for pid in floor_people(facts):
        p = persons[pid]
        jid = p.get("job", "")
        if jid not in jobs:
            continue
        cls = floor_classes(jobs, jid, facts)
        bits = []
        for s in R.STATS:
            gs = [R.ival(jobs[c].get(f"growth.{s}", 0)) for c in cls]
            cur = R.ival(p.get(f"growth.{s}", 0))
            lo = max(FLOOR_LO - g for g in gs)
            hi = min(FLOOR_HI - g for g in gs)
            if lo > hi:                                   # the class they join as wins
                lo, hi = FLOOR_LO - gs[0], FLOOR_HI - gs[0]
            lo, hi = max(0, _r5_up(lo)), _r5_down(hi)
            if hi < lo:
                bad.append(f"{pid} {s}: class growth {gs[0]} leaves no personal growth for a total of 20..100")
                continue
            new = min(max(cur, lo), hi)
            if new != cur:
                cells.setdefault(pid, {})[f"growth.{s}"] = str(new)
                bits.append(f"{s} {cur}->{new} (total {cur + gs[0]}->{new + gs[0]})")
        if bits:
            lines.append(f"  {facts.pname(facts.by_pid[pid])} [{pid}] ({facts.jname(jid)}): " + ", ".join(bits))
    return cells, lines, bad


def floor_report(facts: R.Facts, files: dict) -> tuple[list[str], list[str]]:
    """(the final growth table: personal + class = total per person and stat, as laid; problems: a total outside
    20..100 for the class a person joins as)."""
    persons, jobs = final_rows(facts, files)
    out, bad = ["Final growths as laid (personal + class of the class they join as = total; hp str mag skl spd lck "
                "def res). The game adds a child's parent and the avatar's boon/bane on top while playing:"], []
    for pid in floor_people(facts):
        p = persons[pid]
        jid = p.get("job", "")
        if jid not in jobs:
            continue
        pers = [R.ival(p.get(f"growth.{s}", 0)) for s in R.STATS]
        cl = [R.ival(jobs[jid].get(f"growth.{s}", 0)) for s in R.STATS]
        tot = [a + b for a, b in zip(pers, cl)]
        out.append(f"  {facts.pname(facts.by_pid[pid])} [{pid}] {facts.jname(jid)}: "
                   + " ".join(f"{a}+{b}={c}" for a, b, c in zip(pers, cl, tot)))
        for s, v in zip(R.STATS, tot):
            if not FLOOR_LO <= v <= FLOOR_HI:
                bad.append(f"{pid} {s}: total {v}")
    return out, bad


def apply_floor(facts: R.Facts, files: dict, plan: dict) -> tuple[dict, list[str]]:
    """files with the floor laid into tables/Person.csv (cells the CSV already has are replaced), plan["guards"]
    "growth: floor 20-100" (recomputed from the files alone) and plan["floor"] (the cells), plan.json rewritten
    with them. Returns (files, spoiler lines)."""
    import tracks as TR
    cells, lines, bad = plan_floor(facts, files)
    files = dict(files)
    if cells:
        files["tables/Person.csv"] = TR._overlay_person(facts, files.get("tables/Person.csv"), cells, csv_wins=False)
    table, bad2 = floor_report(facts, files)
    plan["guards"]["growth: floor 20-100"] = {"ok": not (bad or bad2), "detail": (bad + bad2)[:50]
                                               + [f"{sum(len(v) for v in cells.values())} personal growths moved"]}
    plan["floor"] = {pid: dict(sorted(v.items())) for pid, v in sorted(cells.items())}
    files["plan.json"] = (json.dumps(plan, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    head = [f"Every randomized total growth (personal + class) is kept between {FLOOR_LO} and {FLOOR_HI}, also for "
            "stats that were 0; Move is not a growth. Personal growths moved by the floor (they replace the numbers "
            "above):"] + (lines or ["  none"])
    return files, head + [""] + table


def _onoff(v: str) -> bool:
    import rando
    return rando.onoff(v)


def main(argv=None) -> int:
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make", help="slice 1 + this track for one seed, as a mod folder (host only)")
    p.add_argument("--seed", required=True)
    p.add_argument("--growths", choices=GROWTH_MODES, default="slice1")
    p.add_argument("--growth-variance", type=int, default=30)
    p.add_argument("--growth-min", type=int, default=5)
    p.add_argument("--growth-max", type=int, default=80)
    p.add_argument("--adjust-hp", type=_onoff, default=False)
    p.add_argument("--bases", choices=BASE_MODES, default="slice1")
    p.add_argument("--base-variance", type=int, default=5)
    p.add_argument("--scale-to-level", type=_onoff, default=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("robot", help="one robot job: mod runs, then the same runs with the mod uninstalled")
    p.add_argument("job")
    p.add_argument("top", help="the track's own folder below build/ (results, servers)")
    p.add_argument("plan")
    p.add_argument("--mod-zak", required=True)
    p.add_argument("--off-zak", required=True)
    p.add_argument("runs", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "make":
        import gamedata as GD
        opts = {"growths": a.growths, "growth_variance": a.growth_variance, "growth_min": a.growth_min,
                "growth_max": a.growth_max, "adjust_hp": a.adjust_hp, "bases": a.bases,
                "base_variance": a.base_variance, "scale_to_level": a.scale_to_level}
        try:
            facts = GD.load_facts()
            files, plan, lines = build_files(facts, a.seed, opts)
        except R.RandoError as e:
            print(f"ERROR: {e}")
            return 1
        folder = R.write_mod(files, os.path.join(os.path.abspath(a.out), R.mod_name(plan["seed"])))
        bad = check_bounds(facts, plan, opts)
        guards = R.run_guards(facts, plan)
        print(f"made {folder}; {len(lines) - 1 if lines else 0} spoiler lines from the growth track")
        for k, v in guards.items():
            print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}" + ("" if v["ok"] else f"  {v['detail'][:3]}"))
        print(f"  {'PASS' if not bad else 'FAIL'} growth_track_bounds" + (f"  {bad[:3]}" if bad else ""))
        return 0 if not bad else 2
    # robot: the slice-1 driver with its folders moved under this track's own top folder
    top = os.path.abspath(a.top)
    if not os.path.normcase(top).startswith(os.path.normcase(os.path.join(ROOT, "build")) + os.sep):
        print("ERROR: the robot folder must be below build/")
        return 1
    if os.path.exists(os.path.join(ROOT, "build", "STOP_ROUND")):
        print("STOP_ROUND exists: not started")
        return 3
    import robot_check as RC
    import gamedata as GD
    RC.TOP = top
    facts = GD.load_facts(names=False)
    res = {"job": a.job, "plan": a.plan, "mod_zak": a.mod_zak, "off_zak": a.off_zak, "runs": []}
    os.makedirs(os.path.join(top, "robot"), exist_ok=True)
    path = os.path.join(top, "robot", f"{a.job}.json")
    for label, zak, exp in (("mod", a.mod_zak, RC.expected(a.plan, facts)), ("off", a.off_zak, RC.expected("vanilla", facts))):
        for spec in a.runs:
            if os.path.exists(os.path.join(ROOT, "build", "STOP_ROUND")):
                res["stopped"] = "STOP_ROUND appeared"
                break
            parts = spec.split(":")
            parts[0] = f"{label}-{parts[0]}"
            r = RC.run_one(a.job, zak, exp, ":".join(parts))
            res["runs"].append(r)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(res, fh, indent=1, ensure_ascii=False)
    for r in res["runs"]:
        print(r["run"], "frame", r.get("frame"), "memory", r.get("digest", {}).get("memory", "")[:16], "mods",
              len(r.get("mods_in_data", [])), "seconds", r.get("seconds"))
        for e in r["reads"]:
            pc = e.get("persons") or {}
            print("  read", e["frame"], "units", len(e.get("units", [])), "persons checked", pc.get("checked"),
                  "mismatches", len(pc.get("mismatches", [])), e.get("error", ""))
    print("result:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
