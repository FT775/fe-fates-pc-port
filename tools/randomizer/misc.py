#!/usr/bin/env python3
"""Fire Emblem Fates randomizer, track "misc" (round 56, F-046 'build the other missing parts too';
docs/rando/MISC.md). Three rows of the FE8 port's Randomizer screen that Fates did not have yet:

    Enemy drops      a chance (5-100 %) that an enemy carries an item it drops when defeated
    Assign evenly    the classes plan spreads the classes, so no class repeats much inside one route
    Class movement   each class's Move (Job.mov) moves a little, inside sensible bounds

Our own code. The FE8 port (our sister project) gave the ideas; public Fates tools were read for facts only.
Wired in round W1 (tools/randomizer/tracks.py, docs/rando/WIRE_56.md): assign evenly runs right after slice 1
(randolib.make_plan(..., classes=...)), enemy drops on the enemies track's final rows, class movement on the final
enemy classes. Every option defaults to "changes nothing" (no edits at all).

    python tools/randomizer/misc.py make --seed S [--enemy-drops 0|5..100] [--class-move off|small|wide]
                                         [--assign-evenly on|off]       (host only: prints counts, writes nothing)

Interface for the integrate step (every table comes in through a passed-in object, F-047):

    plan_drops(tables, seed, opts)            -> (edits, lines)   tables: enemies.EnemyTables
    run_drop_guards(tables, edits, opts)      -> {name: {"ok", "detail"}}
    plan_movement(tables, seed, opts)         -> (edits, lines)   tables: enemies.EnemyTables
    run_move_guards(tables, edits, opts)      -> {name: {"ok", "detail"}}
    assign_evenly(facts, plan, seed, opts)    -> (classes, lines) facts: randolib.Facts, plan: slice 1's plan
    make_plan_even(facts, seed, sw, opts)     -> (plan, lines)    slice 1 again with the even classes
    run_even_guards(facts, before, after)     -> {name: {"ok", "detail"}}
    job_csv_with_edits / dispos_csv_with_edits  merge this track's cells into the mod folder's CSV files

edits: [{"table": "DisposUnit", "file", "index", "label", "column": "item_N_flags", "old", "new"}] and
       [{"table": "Job", "index", "label", "column": "mov", "old", "new"}], in a fixed order.

Facts this track rests on (read from the code, docs/TABLES.md and the user's own tables; no game values here):
- DisposUnit item_N_flags bit 0 is the drop mark. Unit::SetDisposItem 003D8C38 turns it into unit::Item+0x2
  bit 15 (0x8000), unless the item is ISID_敵専用 without ISID_即換金 (enemy-only gear never drops; gold does).
  map::SequenceBattle ProcSequence::ItemDrop 0035C548 tests that bit on the loser's items, and
  UnitItemClearDrop 003AC058 clears it. In the original tables every marked slot belongs to team 1.
- A forged slot with the mark is split by SetDisposItem into the forged weapon (kept) and a plain copy (the
  drop), which needs a free slot: this track never marks a forged slot, nor one with level bits (bits 1-4).
- Job.mov (+0x5D; Unit::GetMovePower 0052D5E4 reads it) is the class's Move; the no-stuck rule of the enemies track
  (3 turns over the chapter's own terrain, at least 3/4 of the tiles, TerrainCost row = Job.move_cost_class)
  is re-checked for every enemy whose class loses Move.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import io
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "misc"
TOOL = "rando-misc-v1"
DEFAULT_OPTS = {"enemy_drops": 0, "class_move": "off", "assign_evenly": False}
DROP_CHOICES = (0,) + tuple(range(5, 101, 5))
MOVE_CHOICES = ("off", "small", "wide")
MOVE_SPREAD = {"off": 0, "small": 1, "wide": 2}
ITEM_SLOTS = range(1, 6)
DROP_BIT = 1
LEVEL_BITS = 0x1E
ENEMY_ONLY = "ISID_敵専用"
CASH = "ISID_即換金"
FLIER_CAT = "JCID_飛行"
ARMOR_CAT = "JCID_アーマー"
MOUNT_CAT = "JCID_騎乗"
# Move bounds by kind of class (min, max). The original value is always allowed, even outside these.
MOVE_BOUNDS = {"armor": (3, 5), "foot": (4, 7), "mounted": (5, 8), "flier": (5, 8), "beast": (5, 8)}
REACH_TURNS = 3
REACH_RATIO = 0.75
ROLES = ("staff", "door")


# ------------------------------------------------------------------ options and seeds
def check_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS, **{k: v for k, v in (opts or {}).items() if k in DEFAULT_OPTS})
    d = o["enemy_drops"]
    if isinstance(d, str):
        d = 0 if d.strip().lower() in ("off", "") else int(d.strip().rstrip("%"))
    if d not in DROP_CHOICES:
        raise R.RandoError("enemy drops: off (0) or 5-100 in steps of 5")
    o["enemy_drops"] = int(d)
    if o["class_move"] not in MOVE_CHOICES:
        raise R.RandoError("class movement: off, small (+-1) or wide (+-2)")
    o["assign_evenly"] = bool(o["assign_evenly"]) if not isinstance(o["assign_evenly"], str) \
        else o["assign_evenly"].lower() in ("on", "1", "true", "yes")
    return o


def opts_text(o: dict) -> str:
    o = check_opts(o)
    return (f"enemy-drops={o['enemy_drops'] or 'off'}{'%' if o['enemy_drops'] else ''} "
            f"class-move={o['class_move']} assign-evenly={'on' if o['assign_evenly'] else 'off'}")


def active(opts: dict | None) -> bool:
    o = check_opts(opts)
    return bool(o["enemy_drops"]) or o["class_move"] != "off" or o["assign_evenly"]


def track_key(seed: str) -> str:
    """This track's sub-seed from the run seed text (never a shared Random), as the round-55 tracks do."""
    return hashlib.sha256("\x1f".join([TOOL, "seed:" + R.check_seed(str(seed)), TRACK]).encode("utf-8")).hexdigest()


def stream(key: str, purpose: str, who: str) -> random.Random:
    h = hashlib.sha256("\x1f".join([key, purpose, who]).encode("utf-8")).digest()
    return random.Random(int.from_bytes(h, "big"))


def ival(cell) -> int:
    return R.ival(cell)


def _strip(jid: str) -> str:
    return jid[:-1] if jid.endswith(("男", "女")) else jid


def job_pairs(tables) -> dict[str, str]:
    """{class: the family name it shares with its other-gender row} for the pairs whose labels differ by more than
    the 男/女 ending (Monk / Shrine Maiden, Great Master / Priestess, Butler / Maid in Fates). From the tables object
    (F-047): rules["scope"]["job_pairs"] ({male: female}) when the rules carry it, else the Job rows' own mutual
    gender_pair cells. Cached on the tables object."""
    got = getattr(tables, "_misc_job_pairs", None)
    if got is not None:
        return got
    rules = getattr(tables, "rules", None) or {}
    facts = tables.f if hasattr(tables, "f") and hasattr(tables.f, "jobs") else tables
    jobs = getattr(facts, "jobs", None) or {}
    pairs: dict[str, str] = {}
    explicit = (rules.get("scope") or {}).get("job_pairs")
    if explicit is not None:
        for m, w in explicit.items():
            pairs[m] = pairs[w] = _strip(m)
    else:
        for jid, j in jobs.items():
            g = j.get("gender_pair", "")
            if g and g != jid and g in jobs and jobs[g].get("gender_pair") == jid and _strip(g) != _strip(jid):
                male = jid if jid.endswith("男") else g
                pairs[jid] = pairs[g] = _strip(male)
    try:
        tables._misc_job_pairs = pairs
    except AttributeError:
        pass
    return pairs


def family(jid: str, tables=None) -> str:
    """A class without its gender ending: the male and female rows of one class count as one class. With the
    tables object, the pairs whose labels differ (job_pairs) count as one class too."""
    if tables is not None:
        f = job_pairs(tables).get(jid)
        if f:
            return f
    return _strip(jid)


# ------------------------------------------------------------------ 1. enemy drops
def _chapter(d: dict) -> str:
    return d["file"].replace("\\", "/").rsplit("/", 1)[-1].split(".", 1)[0]


def _drop_item_ok(t, d: dict, s: int) -> str | None:
    """None when slot s of placement d may get the drop mark, else why not."""
    iid = d.get(f"item_{s}", "")
    if not iid:
        return "empty"
    it = t.f.items.get(iid)
    if it is None:
        return "unknown item"
    itf = R.flags(it["flags"])
    if itf & set(t.rules["replacement_refuse_item_flags"]) or any("専用" in x for x in itf):
        return "story, personal, enemy-only or precious item"
    fl = ival(d.get(f"item_{s}_flags", 0))
    if fl & DROP_BIT:
        return "already a drop"
    if fl & LEVEL_BITS:
        return "given only at some levels"
    forge = [d.get(f"item_{s}_forge.{x}", "0") for x in ("normal", "hard", "lunatic")]
    if any(ival(v) != 0 for v in forge):
        return "forged or not given on every difficulty"
    return None


def drop_scope(t, d: dict) -> str | None:
    """None when this placement may get a drop; else why not."""
    why = t.out_of_scope(d) or t.scripted(d)
    if why:
        return why
    if any(d.get(f"item_{s}") and ival(d.get(f"item_{s}_flags", 0)) & DROP_BIT for s in ITEM_SLOTS):
        return "already drops an item"
    return None


def plan_drops(t, seed: str, opts: dict | None = None):
    """Each unscripted enemy of a story chapter that drops nothing gets, with the chance given, the drop mark on
    one of its own items (an ordinary item first: vulnerary, seal, gold; else an ordinary weapon). Never a story
    key item, never a personal or enemy-only one, never a forged slot. Existing drops are never removed."""
    o = check_opts(opts)
    chance = o["enemy_drops"]
    if not chance:
        return [], []
    key = track_key(seed)
    edits, spoil = [], []
    n_scope = 0
    for d in t.dispos:
        if drop_scope(t, d):
            continue
        n_scope += 1
        who = f"{d['file']}#{ival(d['index'])}"
        r = stream(key, "drop", who)
        if r.randrange(100) >= chance:
            continue
        ok = [s for s in ITEM_SLOTS if _drop_item_ok(t, d, s) is None]
        if not ok:
            continue
        plain = [s for s in ok if t.f.item_kind(d[f"item_{s}"]) is None]
        s = r.choice(plain or ok)
        old = str(d.get(f"item_{s}_flags", "0"))
        edits.append({"table": "DisposUnit", "file": d["file"], "index": ival(d["index"]),
                      "label": d.get("label", ""), "column": f"item_{s}_flags", "old": old,
                      "new": str(ival(old) | DROP_BIT)})
        p = t.pc.get(d["pid"]) or {}
        spoil.append(f"{_chapter(d)} unit {ival(d['index'])} "
                     f"({t.f.name(p.get('mpid_name', '')) if p else d['pid']} at {d.get('pos.x')},{d.get('pos.y')}): "
                     f"drops {t.f.iname(d[f'item_{s}'])}")
    head = [f"Enemy drops ({chance}%): {n_scope} enemies could get one, {len(edits)} now drop an item. "
            "Drops the game already had are kept."]
    return edits, head + spoil


def run_drop_guards(t, edits: list[dict], opts: dict | None = None) -> dict:
    o = check_opts(opts)
    by = {(d["file"], ival(d["index"])): d for d in t.dispos}
    out: dict[str, dict] = {}

    def g(name, bad):
        out[name] = {"ok": not bad, "detail": bad[:50]}

    bad, per_unit = [], {}
    for e in edits:
        if e.get("table") != "DisposUnit":
            continue
        k = (e["file"], e["index"])
        d = by.get(k)
        col = e["column"]
        if d is None or not col.startswith("item_") or not col.endswith("_flags"):
            bad.append(f"{k}: {col} is not a drop cell")
            continue
        s = int(col.split("_")[1])
        if str(d.get(col, "0")) != str(e["old"]):
            bad.append(f"{k}: old value differs")
        if ival(e["new"]) != ival(e["old"]) | DROP_BIT or ival(e["new"]) == ival(e["old"]):
            bad.append(f"{k}: {col} changed more than the drop bit")
        why = drop_scope(t, d) or _drop_item_ok(t, d, s)
        if why:
            bad.append(f"{k} slot {s}: {why}")
        per_unit[k] = per_unit.get(k, 0) + 1
    g("drops_only_on_ordinary_items_of_unscripted_enemies", bad)
    g("at_most_one_new_drop_per_enemy", [f"{k}: {n}" for k, n in per_unit.items() if n > 1])
    g("drops_off_no_edits", [] if o["enemy_drops"] or not per_unit else [f"{len(per_unit)} drop edits with drops off"])
    return out


# ------------------------------------------------------------------ 2. class movement
def move_kind(t, j: dict) -> str:
    cat = R.flags(j.get("category", ""))
    if FLIER_CAT in cat:
        return "flier"
    if t.rules["beast_job_category"] in cat:
        return "beast"
    if ARMOR_CAT in cat:
        return "armor"
    if MOUNT_CAT in cat:
        return "mounted"
    return "foot"


def movable_jobs(t) -> list[dict]:
    """The classes whose Move may change: normal player classes of a side (Hoshido / Nohr). Story classes,
    enemy-only, monsters, dragons, downloadable and special classes keep their Move."""
    out = []
    for j in t.f.job_list:
        jid = j["label"]
        if t.f.excluded_job(jid) or ival(j.get("origin", 0)) not in (1, 2) or not any(t.f.wexp_max(j)):
            continue
        out.append(j)
    return out


def _reach(t, ch: str, x: int, y: int, mcc: int, mov: int, cache: dict) -> int:
    key = (ch[:4], x, y, mcc, mov)
    if key in cache:
        return cache[key]
    if hasattr(t, "reach_tiles"):           # the enemies track's shared, faster search (the same tiles; SPEED.md)
        cache[key] = t.reach_tiles(ch, x, y, mcc, mov)
        return cache[key]
    row = t.cost.get(mcc)
    budget = mov * REACH_TURNS
    best = {(x, y): 0}
    q = [(0, x, y)]
    while q:
        c, cx, cy = heapq.heappop(q)
        if c > best.get((cx, cy), 1 << 30):
            continue
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            col = t.tile_col(ch, nx, ny)
            if col is None or row is None or col >= len(row) or row[col] < 0:
                continue
            nc = c + row[col]
            if nc <= budget and nc < best.get((nx, ny), 1 << 30):
                best[(nx, ny)] = nc
                heapq.heappush(q, (nc, nx, ny))
    cache[key] = len(best)
    return len(best)


def _units_by_family(t) -> dict[str, list[tuple]]:
    """family -> [(chapter, x, y, jid, unit key)] of every enemy or other-army unit standing on a known tile."""
    out: dict[str, list[tuple]] = {}
    for d in t.dispos:
        if str(d.get("team")) not in ("1", "2") or not d.get("pid"):
            continue
        jid = t.unit_job(d)
        if not jid or jid not in t.f.jobs:
            continue
        ch = _chapter(d)
        x, y = ival(d.get("pos.x", -1)), ival(d.get("pos.y", -1))
        if t.tile_col(ch, x, y) is None:
            continue
        out.setdefault(family(jid, t), []).append((ch, x, y, jid, f"{d['file']}#{ival(d['index'])}"))
    return out


def stuck_units(t, fam_units: list[tuple], new_mov: dict[str, int], cache: dict) -> list[str]:
    """Units of these classes that would reach less than 3/4 of their tiles in 3 turns with the new Move."""
    bad = []
    for ch, x, y, jid, who in fam_units:
        j = t.f.jobs[jid]
        old, new = ival(j["mov"]), new_mov.get(jid, ival(j["mov"]))
        if new >= old:
            continue
        mcc = ival(j["move_cost_class"])
        ro, rn = _reach(t, ch, x, y, mcc, old, cache), _reach(t, ch, x, y, mcc, new, cache)
        if rn < REACH_RATIO * ro:
            bad.append(f"{who} ({jid}): reaches {rn} tiles in {REACH_TURNS} turns instead of {ro}")
    return bad


def move_range(t, j: dict, spread: int) -> tuple[int, int]:
    old = ival(j["mov"])
    lo, hi = MOVE_BOUNDS[move_kind(t, j)]
    return min(old, max(lo, old - spread)), max(old, min(hi, old + spread))


def plan_movement(t, seed: str, opts: dict | None = None):
    """New Move for every normal class: within +-1 (small) or +-2 (wide) of its own, inside the bounds of its
    kind (armor 3-5, foot 4-7, mounted / flier / beast 5-8; the original value always allowed). Male and female
    rows of a class move together. Base classes first; a promoted class never has less Move than a class that
    promotes into it. A class that would lose Move keeps the smallest loss (or none) under which no enemy of it
    gets stuck (the enemies track's no-stuck rule on every chapter where one stands)."""
    o = check_opts(opts)
    spread = MOVE_SPREAD[o["class_move"]]
    if not spread:
        return [], []
    key = track_key(seed)
    jobs = movable_jobs(t)
    fams: dict[str, list[dict]] = {}
    for j in jobs:
        fams.setdefault(family(j["label"], t), []).append(j)
    units = _units_by_family(t)
    cache: dict = {}
    new_mov: dict[str, int] = {}
    held: list[str] = []
    feeders: dict[str, set] = {}       # promoted family -> base families that promote into it
    for j in jobs:
        if not t.f.promoted(j):
            for c in ("promotion.1", "promotion.2"):
                if j.get(c) in t.f.jobs:
                    feeders.setdefault(family(j[c], t), set()).add(family(j["label"], t))
    order = sorted(fams, key=lambda f: (any(t.f.promoted(j) for j in fams[f]), min(ival(j["index"]) for j in fams[f])))
    for f in order:
        rows = fams[f]
        lo, hi = None, None
        for j in rows:                  # the family's range: the intersection of its rows' ranges
            a, b = move_range(t, j, spread)
            lo, hi = (a, b) if lo is None else (max(lo, a), min(hi, b))
        olds = {ival(j["mov"]) for j in rows}
        if len(olds) != 1 or lo > hi:
            continue                    # the rows disagree already: leave the class alone
        old = olds.pop()
        if any(t.f.promoted(j) for j in rows):
            floor = max([new_mov.get(x["label"], ival(x["mov"])) for bf in feeders.get(f, ()) for x in fams.get(bf, [])]
                        or [lo])
            lo = max(lo, floor)
            hi = max(hi, lo)
        pick = stream(key, "move", f).randint(lo, hi)
        if pick < old:                  # the no-stuck rule: raise the loss until no enemy of the class is stuck
            for v in range(pick, old + 1):
                trial = {j["label"]: v for j in rows}
                if not stuck_units(t, units.get(f, []), trial, cache):
                    break
            if v != pick:
                held.append(f"{t.f.jname(rows[0]['label'])}: Move {pick} would leave enemies stuck; {v} used")
            pick = v
        for j in rows:
            new_mov[j["label"]] = pick
    # a raised base class (no-stuck) may now outrun its promoted class: lift the promoted ones once more
    for f in order:
        rows = fams[f]
        if not any(t.f.promoted(j) for j in rows) or rows[0]["label"] not in new_mov:
            continue
        floor = max([new_mov.get(x["label"], ival(x["mov"])) for bf in feeders.get(f, ()) for x in fams.get(bf, [])]
                    or [0])
        if new_mov[rows[0]["label"]] < floor:
            for j in rows:
                new_mov[j["label"]] = floor
    edits, spoil = [], []
    for j in t.f.job_list:
        jid = j["label"]
        if jid in new_mov and new_mov[jid] != ival(j["mov"]):
            edits.append({"table": "Job", "index": ival(j["index"]), "label": jid, "column": "mov",
                          "old": str(j["mov"]), "new": str(new_mov[jid])})
            spoil.append(f"{t.f.jname(jid)}: Move {j['mov']} -> {new_mov[jid]}")
    up = sum(1 for e in edits if ival(e["new"]) > ival(e["old"]))
    head = [f"Class movement ({o['class_move']}): {len(edits)} class rows changed ({up} up, {len(edits) - up} down); "
            f"{len(held)} losses made smaller so no enemy gets stuck."] + held
    return edits, head + spoil


def run_move_guards(t, edits: list[dict], opts: dict | None = None) -> dict:
    o = check_opts(opts)
    spread = MOVE_SPREAD[o["class_move"]]
    out: dict[str, dict] = {}

    def g(name, bad):
        out[name] = {"ok": not bad, "detail": bad[:50]}

    movable = {j["label"] for j in movable_jobs(t)}
    new = {}
    bad = []
    for e in edits:
        if e.get("table") != "Job":
            continue
        j = t.f.jobs.get(e["label"])
        if j is None or e["column"] != "mov" or str(j["mov"]) != str(e["old"]):
            bad.append(f"{e['label']}: not a Job.mov cell with the right old value")
            continue
        if e["label"] not in movable:
            bad.append(f"{e['label']}: a story / special class changed")
        new[e["label"]] = ival(e["new"])
    g("only_mov_of_normal_classes", bad)
    g("movement_off_no_edits", [] if spread or not new else [f"{len(new)} Move edits with the option off"])
    mv = lambda jid: new.get(jid, ival(t.f.jobs[jid]["mov"]))  # noqa: E731
    by_fam: dict[str, list[str]] = {}
    for jid in movable:
        by_fam.setdefault(family(jid, t), []).append(jid)
    feeders: dict[str, set] = {}            # promoted family -> the base classes that promote into it
    for j in t.f.job_list:
        if not t.f.promoted(j) and j["label"] in movable:
            for c in ("promotion.1", "promotion.2"):
                if j.get(c) in t.f.jobs:
                    feeders.setdefault(family(j[c], t), set()).add(j["label"])
    bad = []
    for jid, v in new.items():
        j = t.f.jobs[jid]
        lo, hi = move_range(t, j, spread)
        if not t.f.promoted(j):
            if not lo <= v <= hi:
                bad.append(f"{jid}: Move {v} outside {lo}-{hi}")
            continue
        # a promoted class may sit above its own range only to stay as fast as a (raised) base class of its line
        top = max([hi] + [mv(b) for b in feeders.get(family(jid, t), ())])
        if v < lo:
            bad.append(f"{jid}: Move {v} below {lo}")
        if v > top:
            bad.append(f"{jid}: Move {v} above {top} (its range or its fastest base class)")
    g("move_within_bounds", bad)
    bad = []
    for j in t.f.job_list:
        if t.f.promoted(j) or j["label"] not in movable:
            continue
        for c in ("promotion.1", "promotion.2"):
            up = j.get(c)
            if up in movable and mv(up) < mv(j["label"]) and (up in new or j["label"] in new):
                bad.append(f"{up} ({mv(up)}) has less Move than {j['label']} ({mv(j['label'])})")
    g("promoted_never_slower_than_its_base", bad)
    bad = []
    for jid in new:
        for other in by_fam.get(family(jid, t), []):
            if other != jid and mv(other) != mv(jid):
                bad.append(f"{jid} and {other} differ")
    g("male_and_female_rows_move_together", bad)
    units = _units_by_family(t)
    cache: dict = {}
    bad = []
    for f in {family(j, t) for j in new}:
        bad += stuck_units(t, units.get(f, []), new, cache)
    g("no_stuck_enemies", bad)
    return out


# ------------------------------------------------------------------ 3. assign evenly (a post-pass over slice 1)
def _job_of(facts, plan_jobs: dict, pid: str) -> str:
    return plan_jobs.get(pid) or facts.by_pid[pid]["job"]


def route_counts(facts, plan_jobs: dict, routes: dict) -> dict[str, dict[str, int]]:
    out = {}
    for letter, mem in routes.items():
        c: dict[str, int] = {}
        for pid in mem:
            if pid in facts.by_pid:
                f = family(_job_of(facts, plan_jobs, pid), facts)
                c[f] = c.get(f, 0) + 1
        out[letter] = c
    return out


def spread_text(counts: dict[str, dict[str, int]]) -> str:
    return ", ".join(f"route {k}: most-used class x{max(v.values()) if v else 0}" for k, v in sorted(counts.items()))


def _roles_ok(facts, plan_jobs: dict, mem: list[str], role: str) -> bool:
    for pid in mem:
        if pid not in facts.by_pid:
            continue
        p = facts.by_pid[pid]
        jid = _job_of(facts, plan_jobs, pid)
        if role == "door" and facts.rules["lock_skill"] in ([p.get(f"skill.{i}") for i in range(1, 6)]
                                                            + [p.get("personal_skill.normal")]):
            return True
        if R.role_ok_job(facts, p, jid, role):
            return True
    return False


def _guarantees_stay(facts, s1: dict, jobs: dict, legal: dict) -> list[str]:
    """Round 75b: a guarantee slice 1's plan met (its repair included) stays met: the roles-stay step asks
    guarantees.met, and gives a covering person (or the whole retainer slot) slice 1's class back. Changes jobs."""
    import guarantees as GU
    lines = []
    for n in GU.needs(facts.rules):
        if not GU.applies(facts, n)[0] or not GU.met(facts, s1, n) or GU.met(facts, jobs, n):
            continue
        for e in GU.met(facts, s1, n):
            ms = [pid for pid in GU.members(e) if pid in facts.by_pid]
            if not all(pid in legal or jobs.get(pid) == s1.get(pid) for pid in ms):
                continue
            for pid in ms:
                if jobs.get(pid) != s1.get(pid):
                    jobs[pid] = s1[pid]
                    lines.append(f"{GU.where(n)}: {facts.pname(facts.by_pid[pid])} keeps slice 1's class "
                                 f"{facts.jname(s1[pid])} (the {GU.ROLE_WORDS[n['role']]} guarantee)")
            break
    return lines


def assign_evenly(facts, plan: dict, seed: str, opts: dict | None = None):
    """{pid: class} for every person slice 1 gave a new class, spread so that inside each route a class (the
    male and female rows counted as one) is used again only when the person has no less-used legal class left.
    The people with the fewest legal classes choose first; slice 1's pick is kept whenever it is among the
    least used; ties are drawn from this track's own stream. Story-fixed people count but never move. A route
    that had a staff user or a lock opener in slice 1's plan keeps one (slice 1's pick comes back if needed)."""
    o = check_opts(opts)
    if not o["assign_evenly"] or not plan["switches"].get("classes", True):
        return {}, []
    key = track_key(seed)
    sw = plan["switches"]
    routes = plan.get("routes") or facts.route_members()
    s1 = {e["pid"]: e["job"] for e in plan["persons"]}
    movers = [e for e in plan["persons"] if not e.get("kept")]
    legal = {e["pid"]: facts.legal_classes(facts.by_pid[e["pid"]], sw) for e in movers}
    in_routes = {e["pid"]: [k for k, mem in routes.items() if e["pid"] in mem] for e in movers}
    jobs = {pid: j for pid, j in s1.items() if pid not in legal}      # fixed people keep their class
    counts = {k: {} for k in routes}
    for k, mem in routes.items():
        for pid in mem:
            if pid in facts.by_pid and pid not in legal:
                f = family(_job_of(facts, jobs, pid), facts)
                counts[k][f] = counts[k].get(f, 0) + 1
    order = sorted(movers, key=lambda e: (len(legal[e["pid"]]), e["index"]))
    for e in order:
        pid = e["pid"]
        cands = legal[pid] or [s1[pid]]
        score = {c: max([counts[k].get(family(c, facts), 0) for k in in_routes[pid]] or [0]) for c in cands}
        low = min(score.values())
        best = [c for c in cands if score[c] == low]
        pick = s1[pid] if s1[pid] in best else stream(key, "even", pid).choice(best)
        jobs[pid] = pick
        for k in in_routes[pid]:
            counts[k][family(pick, facts)] = counts[k].get(family(pick, facts), 0) + 1
    lines = []
    for letter, mem in routes.items():                # roles slice 1 had in a route stay
        for role in ROLES:
            if not _roles_ok(facts, s1, mem, role) or _roles_ok(facts, jobs, mem, role):
                continue
            for pid in mem:
                if pid in legal and jobs[pid] != s1[pid] and R.role_ok_job(facts, facts.by_pid[pid], s1[pid], role):
                    jobs[pid] = s1[pid]
                    lines.append(f"route {letter}: {facts.pname(facts.by_pid[pid])} keeps slice 1's class "
                                 f"{facts.jname(s1[pid])} (the route's {role} user)")
                    break
    lines += _guarantees_stay(facts, s1, jobs, legal)
    before, after = route_counts(facts, s1, routes), route_counts(facts, jobs, routes)
    worse = [k for k in routes if after[k] and before[k] and max(after[k].values()) > max(before[k].values())]
    if worse:                                         # the greedy pass lost somewhere: slice 1 was already as even
        jobs = dict(s1)
        lines = [f"route {', '.join(worse)}: the even pass would crowd it more; slice 1's classes kept"]
        after = before
    out = {pid: jobs[pid] for pid in legal}
    moved = [pid for pid in out if out[pid] != s1[pid]]
    head = [f"Assign evenly: {len(moved)} of {len(out)} people got another class so the classes spread. "
            f"Before: {spread_text(before)}. After: {spread_text(after)}."] + lines
    for pid in moved:
        head.append(f"{facts.pname(facts.by_pid[pid])}: {facts.jname(s1[pid])} -> {facts.jname(out[pid])}")
    return out, head


def make_plan_even(facts, seed: str, sw: dict | None = None, opts: dict | None = None):
    """(plan, lines): slice 1's plan, and with assign evenly on, slice 1 again with the even classes, so job_low,
    weapon exp, stats and carried weapons follow the new class. Guards are recomputed with the real facts.
    With the option off the plan is slice 1's own, unchanged."""
    plan = R.make_plan(facts, seed, sw)
    classes, lines = assign_evenly(facts, plan, seed, opts)
    if not classes or all(classes[e["pid"]] == e["job"] for e in plan["persons"] if e["pid"] in classes):
        return plan, lines
    even = R.make_plan(facts, seed, sw, classes=classes, carry=plan.get("guarantees"))
    even["guards"] = R.run_guards(facts, even)
    import guarantees as GU                       # round 75b: the guarantees backstop on the even plan too
    even["guards"]["guarantees: timing"] = GU.check(facts, even)
    for k, v in run_even_guards(facts, plan, even).items():
        even["guards"][f"misc: {k}"] = v
    return even, lines


def run_even_guards(facts, before: dict, after: dict) -> dict:
    out: dict[str, dict] = {}

    def g(name, bad):
        out[name] = {"ok": not bad, "detail": bad[:50]}

    routes = before.get("routes") or facts.route_members()
    b = {e["pid"]: e["job"] for e in before["persons"]}
    a = {e["pid"]: e["job"] for e in after["persons"]}
    kept = {e["pid"] for e in before["persons"] if e.get("kept")}
    g("story_fixed_people_unmoved", [pid for pid in kept if a.get(pid) != b.get(pid)])
    bad = []
    for pid, jid in a.items():
        if pid not in kept and jid not in facts.legal_classes(facts.by_pid[pid], after["switches"]):
            bad.append(f"{pid}: {jid} not legal")
    g("even_classes_legal", bad)
    cb, ca = route_counts(facts, b, routes), route_counts(facts, a, routes)
    g("no_route_more_crowded", [f"route {k}: {max(ca[k].values())} > {max(cb[k].values())}"
                                for k in routes if ca[k] and cb[k] and max(ca[k].values()) > max(cb[k].values())])
    bad = []
    for k, mem in routes.items():
        for role in ROLES:
            if _roles_ok(facts, b, mem, role) and not _roles_ok(facts, a, mem, role):
                bad.append(f"route {k}: lost its {role} user")
    g("route_roles_kept", bad)
    return out


# ------------------------------------------------------------------ writing the cells into the mod folder
def _read_csv(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


def job_csv_with_edits(facts, files: dict[str, bytes], edits: list[dict]) -> dict[str, bytes]:
    """files with this track's Job.mov cells: a 'mov' column added to tables/Job.csv (the promotions track may
    have made it already: its rows and columns are kept), or a new tables/Job.csv."""
    cells = {e["label"]: e["new"] for e in edits if e.get("table") == "Job"}
    if not cells:
        return files
    out = dict(files)
    rows = _read_csv(files["tables/Job.csv"]) if "tables/Job.csv" in files else [["index", "label"]]
    head = rows[0]
    if "mov" not in head:
        head = head + ["mov"]
        rows = [head] + [r + [""] for r in rows[1:]]
    li, mi = head.index("label"), head.index("mov")
    have = {r[li]: r for r in rows[1:]}
    for jid in cells:
        if jid not in have:
            j = facts.jobs[jid]
            r = [str(j.get(c, "")) for c in head]
            rows.append(r)
            have[jid] = r
    for jid, r in have.items():
        r[mi] = cells.get(jid, r[mi] or str(facts.jobs[jid]["mov"]))
    body = sorted(rows[1:], key=lambda r: ival(facts.jobs[r[li]]["index"]))
    out["tables/Job.csv"] = R._csv([head] + body)
    return out


def dispos_csv_with_edits(dispos: list[dict], files: dict[str, bytes], edits: list[dict]) -> dict[str, bytes]:
    """files with this track's item_N_flags cells added to tables/DisposUnit.csv (rows other tracks wrote keep
    their cells; a cell another track wrote is never overwritten, only the flag columns are added)."""
    cells: dict[tuple, dict] = {}
    for e in edits:
        if e.get("table") == "DisposUnit":
            cells.setdefault((e["file"], int(e["index"])), {})[e["column"]] = e["new"]
    if not cells:
        return files
    orig = {(d["file"], ival(d["index"])): d for d in dispos}
    rows = _read_csv(files["tables/DisposUnit.csv"]) if "tables/DisposUnit.csv" in files else [["file", "index", "label"]]
    head = list(rows[0])
    for s in ITEM_SLOTS:
        c = f"item_{s}_flags"
        if c not in head and any(c in v for v in cells.values()):
            head.append(c)
    have = {}
    for r in rows[1:]:
        r = r + [""] * (len(head) - len(r))
        k = (r[0], int(r[1]))
        for c in head[len(rows[0]):]:
            r[head.index(c)] = str(orig[k].get(c, ""))
        have[k] = r
    for k, v in cells.items():
        if k not in have:
            have[k] = [str(orig[k].get(c, "")) if c not in ("file", "index") else (k[0] if c == "file" else str(k[1]))
                       for c in head]
        for c, val in v.items():
            have[k][head.index(c)] = val
    out = dict(files)
    out["tables/DisposUnit.csv"] = R._csv([head] + [have[k] for k in sorted(have)])
    return out


# ------------------------------------------------------------------ command line (host only, writes nothing)
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="randomizer track misc: counts on the user's own tables (no writes)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--seed", required=True)
    m.add_argument("--enemy-drops", default="0")
    m.add_argument("--class-move", default="off", choices=MOVE_CHOICES)
    m.add_argument("--assign-evenly", default="off", choices=("on", "off"))
    a = ap.parse_args(argv)
    try:
        o = check_opts({"enemy_drops": a.enemy_drops, "class_move": a.class_move,
                        "assign_evenly": a.assign_evenly == "on"})
        import enemies as E
        import gamedata as GD
        t = E.load_tables()
        de, dl = plan_drops(t, a.seed, o)
        me, ml = plan_movement(t, a.seed, o)
        g = dict(run_drop_guards(t, de, o), **run_move_guards(t, me, o))
        facts = GD.load_facts()
        plan, el = make_plan_even(facts, a.seed, None, o)
        g.update({k: v for k, v in plan["guards"].items()})
    except R.RandoError as e:
        print(f"misc: {e}", file=sys.stderr)
        return 2
    for line in (dl[:1] + ml[:1] + el[:1]):
        print(line)
    bad = {k: v["detail"][:3] for k, v in g.items() if not v["ok"]}
    print("guards:", "all ok" if not bad else bad)
    return 0 if not bad else 2


if __name__ == "__main__":
    raise SystemExit(main())
