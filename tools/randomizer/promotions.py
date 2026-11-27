#!/usr/bin/env python3
"""Randomizer track "promotions" (round 55, owner 2026-11-20 "build the other missing parts too"; docs/rando/PROMOTIONS.md):
which promoted classes a base class reaches with a Master Seal, and (optional) each person's Heart Seal classes.

    plan_promotions(tables, rng, opts) -> (edits, spoiler_lines)

tables  a randolib.Facts (the original rows; gamedata.load_facts())
rng     the run seed (text, as given to rando.py) or a random.Random; this track derives its OWN sub-seed from it
        and the track name, then one stream per purpose, so no other track's draws are disturbed
opts    DEFAULT_OPTS keys, plus optional "base_plan": the slice-1 plan (randolib.make_plan). With it, the Heart Seal
        draw avoids each person's NEW class line, and Person.job_low follows the new promotions (see below)

edits   [{"table": "Job"|"Person", "index": 9, "label": "JID_...", "cell": "promotion.1", "old": "JID_..", "new": "JID_.."}]
        only cells whose value changes. Cells written:
          Job.promotion.1 / .2   of the base classes (Master Seal targets; Unit::ClassChange and
                                 ClassChangeEnumerator::AddSlideLow read Job+0x64, docs/TABLES.md)
          Person.reclass.1 / .2  of the playable people (Heart Seal classes; only slots that already hold a class)
          Person.job_low         of the playable people whose job_low no longer matches the new promotions (the
                                 game's own pattern: a base class names one of its promotions, a promoted class a
                                 base class that promotes into it; Person::GetLowJobIndex reads it for a promoted
                                 class). "old" is the value in base_plan when one is given (slice 1 writes it),
                                 else the original cell.

Options
    promotions  off | on        the Master Seal targets of every normal base class, drawn again
    choices     2               the game's menu shows the class's two promotion cells; the Job row has no third
                                cell (Job+0x68 "base_class" has no reader), so a FE8-style third choice needs a
                                game-code change (later engine round, owner OK then). "3" is refused with that reason
    reclass     keep | random   each playable person's Heart Seal classes drawn again
    sides       any | own       own: a Hoshido base class promotes only into Hoshido classes (Job.origin), Nohr
                                into Nohr; Heart Seal classes stay on the person's own side
Default opts are off / 2 / keep / any: NO edits, so a default run stays byte-identical.

Guards (each has a test in tests/test_rando_promotions.py; run_guards):
    every target is a normal promoted player class (no enemy-only, DLC, avatar, singer, Villager, beast class)
    of the same gender row; every base class keeps its number of promotions, two different ones; each target can
    use the base class's weapon kind at least as high as the base class can (so the unit's weapons and weapon exp
    stay usable: base classes have one weapon kind each); beast lines (Kitsune, Wolfskin) and the avatar's and
    singer's rows are untouched; promoted rows never get a promotion; every promoted class a playable person
    starts in stays reachable (and the draw tries to keep every promoted class reachable); Heart Seal classes are
    legal base classes of the person's gender, not their own line, no repeats, empty slots stay empty.

Our own code; public Fates randomizers (GPL) were read for facts only. The FE8 port's random promotions (three
choices) were the idea; nothing was copied.

    python tools/randomizer/promotions.py make --seed S [--reclass random] [--sides own] --out DIR
        slice 1 (default switches) + this track only, as one mod folder below build/ (mods-tool check)
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "promotions"
TOOL = "rando-promotions-v1"
DEFAULT_OPTS = {"promotions": "off", "choices": "2", "reclass": "keep", "sides": "any"}
PROMO_MODES = ("off", "on")
CHOICES = ("2",)
RECLASS_MODES = ("keep", "random")
SIDE_MODES = ("any", "own")
PROMO_CELLS = ("promotion.1", "promotion.2")
RECLASS_CELLS = ("reclass.1", "reclass.2")
THREE_WHY = ("a third promotion choice is not possible from the tables: the Job row holds exactly two promotion "
             "cells (Job+0x64), the next cell (Job+0x68) has no reader in the game code, and the Master Seal menu "
             "(ClassChangeEnumerator) lists only those two. It needs a game-code change (a later engine round, "
             "owner OK then)")
# The one special base class that the slice-1 rules exclude but whose promotion cells the game still uses (Mozu's
# Villager line promotes with a Master Seal). It is a promotion SOURCE here, never a Heart Seal or target class.
EXTRA_SOURCE_PREFIXES = ("JID_村人",)
ATTEMPTS = 64


def check_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS)
    for k in DEFAULT_OPTS:
        if opts and k in opts and opts[k] is not None:
            o[k] = str(opts[k]).strip().lower()
    if o["promotions"] in ("true", "1", "yes"):
        o["promotions"] = "on"
    if o["promotions"] in ("false", "0", "no"):
        o["promotions"] = "off"
    if o["promotions"] not in PROMO_MODES:
        raise R.RandoError(f"random promotions: {'|'.join(PROMO_MODES)}")
    if o["choices"] == "3":
        raise R.RandoError("promotion choices 3: " + THREE_WHY)
    if o["choices"] not in CHOICES:
        raise R.RandoError(f"promotion choices: {'|'.join(CHOICES)}")
    if o["reclass"] not in RECLASS_MODES:
        raise R.RandoError(f"Heart Seal classes: {'|'.join(RECLASS_MODES)}")
    if o["sides"] not in SIDE_MODES:
        raise R.RandoError(f"promotion sides: {'|'.join(SIDE_MODES)}")
    return o


def opts_text(o: dict) -> str:
    return f"promotions={o['promotions']} choices={o['choices']} reclass={o['reclass']} sides={o['sides']}"


def track_key(rng) -> str:
    """This track's sub-seed: from the run seed text and the track name (or 256 bits of a given Random)."""
    if isinstance(rng, random.Random):
        base = "random:" + format(rng.getrandbits(256), "064x")
    else:
        base = "seed:" + R.check_seed(str(rng))
    return hashlib.sha256("\x1f".join([TOOL, base, TRACK]).encode("utf-8")).hexdigest()


def stream(key: str, purpose: str, text: str, who: str) -> random.Random:
    h = hashlib.sha256("\x1f".join([key, purpose, text, who]).encode("utf-8")).digest()
    return random.Random(int.from_bytes(h, "big"))


# ------------------------------------------------------------------ class facts (read from the rows)
class PromoFacts:
    def __init__(self, facts: R.Facts):
        self.facts = facts
        f, r = facts, facts.rules
        self.none = f.job_list[0]["label"] if f.job_list else "JID_無し男"
        beast_cat = r["beast_job_category"]
        self.beast = {j["label"] for j in f.job_list if beast_cat in R.flags(j.get("category", ""))}

        def normal(jid):
            return jid in f.jobs and not f.excluded_job(jid) and jid not in self.beast and any(f.wexp_max(f.jobs[jid]))

        # promotion targets: normal promoted player classes
        self.targets = [j["label"] for j in f.job_list if f.promoted(j) and normal(j["label"])]
        # promotion sources: normal base classes that already have at least one promotion, plus the Villager line
        self.sources = []
        for j in f.job_list:
            jid = j["label"]
            if f.promoted(j) or jid in self.beast:
                continue
            if not (normal(jid) or jid.startswith(EXTRA_SOURCE_PREFIXES)):
                continue
            if self.filled(j):
                self.sources.append(jid)
        # Heart Seal classes: normal base classes (no Villager, no beast, no avatar / singer line)
        self.reclass_pool = [j["label"] for j in f.job_list if not f.promoted(j) and normal(j["label"])]

    def filled(self, j: dict) -> list[str]:
        return [j.get(c, self.none) for c in PROMO_CELLS if j.get(c, self.none) not in ("", self.none)]

    def kind(self, jid: str) -> list[int]:
        return [i for i, m in enumerate(self.facts.wexp_max(self.facts.jobs[jid])) if m > 0]

    def legal_target(self, src: str, tgt: str, sides: str) -> str | None:
        """None when tgt may be a promotion of base class src, else why not."""
        f = self.facts
        if tgt not in f.jobs:
            return "no such class"
        if tgt not in self.targets:
            return "not a normal promoted player class"
        s, t = f.jobs[src], f.jobs[tgt]
        if f.female(s) != f.female(t):
            return "other gender row"
        if sides == "own" and R.ival(s["origin"]) in (1, 2) and R.ival(t["origin"]) != R.ival(s["origin"]):
            return "other side"
        smax, tmax = f.wexp_max(s), f.wexp_max(t)
        if not any(smax[k] > 0 and tmax[k] >= smax[k] for k in range(len(smax))):
            return "cannot use the base class's weapon kind as high"
        return None

    def legal_targets(self, src: str, sides: str) -> list[str]:
        return [t for t in self.targets if self.legal_target(src, t, sides) is None]

    def lines(self) -> list[list[str]]:
        """Base classes grouped by gender pair (male row first): a line's rows get gender-paired targets, so
        e.g. male and female Cavaliers promote into the same classes."""
        f = self.facts
        out, seen = [], set()
        for jid in self.sources:
            if jid in seen:
                continue
            gp = f.jobs[jid].get("gender_pair", self.none)
            line = [jid]
            if (gp in self.sources and gp not in seen and gp != jid
                    and f.female(f.jobs[gp]) != f.female(f.jobs[jid])
                    and len(self.filled(f.jobs[gp])) == len(self.filled(f.jobs[jid]))):
                line.append(gp)
            line.sort(key=lambda x: f.female(f.jobs[x]))
            seen.update(line)
            out.append(line)
        return out

    def pair_of(self, tgt: str) -> str | None:
        gp = self.facts.jobs[tgt].get("gender_pair", self.none)
        return gp if gp in self.facts.jobs and gp != self.none else None


def own_base(facts: R.Facts, job: str, job_low: str) -> str:
    """The base class of a person's class line: the class itself when it is a base class, else job_low."""
    j = facts.jobs.get(job)
    if j and not facts.promoted(j):
        return job
    return job_low


def kept_row(facts: R.Facts, p: dict) -> str | None:
    """Rows whose Heart Seal classes are never edited: Corrin (the avatar, the player picks the talent) and the
    singer."""
    r = facts.rules
    if set(r["keep_class_person_flags"]) & R.flags(p["flags"]):
        return "Corrin / a dragonstone holder (talent and class are story-fixed)"
    j = facts.jobs.get(p["job"])
    if j and set(r["keep_class_job_flags"]) & R.flags(j["flags"]):
        return "the singer"
    return None


def _low_also(facts: R.Facts, opts: dict | None) -> list[dict]:
    """opts["low_also"]: extra Person labels (outside the slice-1 scope: the children when the children track is
    off) whose job_low follows the new promotions too. Their Heart Seal cells are never touched here (a child's
    reclass comes from its parents at join)."""
    out = []
    for pid in (opts or {}).get("low_also") or ():
        p = facts.by_pid.get(pid)
        if p is not None and not facts.in_scope(p):
            out.append(p)
    return out


# ------------------------------------------------------------------ the draw
def _draw_promotions(pf: PromoFacts, key: str, text: str, sides: str) -> tuple[dict[str, list[str]], list[str]]:
    """{base class: [targets]} for every source, and notes. Lines are drawn on the male row and mirrored by gender
    pair when the pair is legal for the female row; most-constrained-first so every target class stays reachable
    (up to ATTEMPTS tries)."""
    f = pf.facts
    lines = pf.lines()
    need = {tuple(line): len(pf.filled(f.jobs[line[0]])) for line in lines}

    def legal_line(line):
        out = []
        for t in pf.legal_targets(line[0], sides):
            if len(line) == 1:
                out.append(t)
                continue
            p = pf.pair_of(t)
            if p and pf.legal_target(line[1], p, sides) is None:
                out.append(t)
        return out

    legal = {tuple(line): legal_line(line) for line in lines}
    # a line whose mirrored list is too short is split (each row draws on its own)
    split = []
    for line in lines:
        if len(line) == 2 and len(legal[tuple(line)]) < need[tuple(line)]:
            del legal[tuple(line)]
            del need[tuple(line)]
            for x in line:
                split.append([x])
                legal[(x,)] = pf.legal_targets(x, sides)
                need[(x,)] = len(pf.filled(f.jobs[x]))
    lines = [ln for ln in lines if tuple(ln) in legal] + split
    notes: list[str] = []
    for ln in lines:
        if len(legal[tuple(ln)]) < need[tuple(ln)] and sides == "own":
            # too few classes on the line's own side: this line draws from both sides (said in the spoiler)
            legal[tuple(ln)] = [t for t in pf.legal_targets(ln[0], "any")
                                if len(ln) == 1 or (pf.pair_of(t) and pf.legal_target(ln[1], pf.pair_of(t), "any") is None)]
            notes.append(f"{f.jname(ln[0])}: too few classes on its own side; drawn from both sides")
        if len(legal[tuple(ln)]) < need[tuple(ln)]:
            raise R.RandoError(f"{f.jname(ln[0])}: only {len(legal[tuple(ln)])} legal promotion(s)")
    targets_m = sorted({t for ln in lines for t in legal[tuple(ln)]}, key=lambda t: R.ival(f.jobs[t]["index"]))
    result = None
    for attempt in range(ATTEMPTS):
        r = stream(key, "promotions", text, f"attempt{attempt}")
        assign = {tuple(ln): [] for ln in lines}
        order = list(targets_m)
        r.shuffle(order)
        order.sort(key=lambda t: sum(1 for ln in lines if t in legal[tuple(ln)]))
        ok = True
        for t in order:
            if any(t in a for a in assign.values()):
                continue
            # covered by a normal line (not the Villager line, which is never anyone's job_low)
            cands = [ln for ln in assign if len(assign[ln]) < need[ln] and t in legal[ln]
                     and not ln[0].startswith(EXTRA_SOURCE_PREFIXES)]
            if not cands:
                if not any(t in legal[ln] for ln in assign if not ln[0].startswith(EXTRA_SOURCE_PREFIXES)):
                    continue        # no normal line can reach it at all (e.g. sides=own): not a failure
                ok = False
                break
            assign[r.choice(cands)].append(t)
        if not ok:
            continue
        for ln in sorted(assign, key=lambda x: R.ival(f.jobs[x[0]]["index"])):
            while len(assign[ln]) < need[ln]:
                assign[ln].append(r.choice([t for t in legal[ln] if t not in assign[ln]]))
            r.shuffle(assign[ln])
        result = assign
        break
    if result is None:
        r = stream(key, "promotions", text, "fallback")
        result = {}
        for ln in lines:
            result[tuple(ln)] = r.sample(legal[tuple(ln)], need[tuple(ln)])
        notes.append(f"could not keep every promoted class reachable in {ATTEMPTS} tries; drawn freely")
    out: dict[str, list[str]] = {}
    for ln, ts in result.items():
        out[ln[0]] = list(ts)
        if len(ln) == 2:
            out[ln[1]] = [pf.pair_of(t) for t in ts]
    return out, notes


def _promotions_after(pf: PromoFacts, edits: list[dict]) -> dict[str, list[str]]:
    """{class: [promotion cells]} after this track's Job edits."""
    f = pf.facts
    after = {jid: [j.get(c, pf.none) for c in PROMO_CELLS] for jid, j in f.jobs.items()}
    for ed in edits:
        if ed["table"] == "Job" and ed["cell"] in PROMO_CELLS:
            after[ed["label"]][PROMO_CELLS.index(ed["cell"])] = ed["new"]
    return after


def plan_promotions(tables: R.Facts, rng, opts: dict | None = None) -> tuple[list[dict], list[str]]:
    facts = tables
    o = check_opts(opts)
    if o["promotions"] == "off" and o["reclass"] == "keep":
        return [], []
    pf = PromoFacts(facts)
    base_plan = (opts or {}).get("base_plan")
    bp = {e["pid"]: e for e in base_plan["persons"]} if base_plan else {}
    key = track_key(rng)
    text = opts_text(o)
    edits: list[dict] = []
    lines = [f"Promotions track ({TOOL}): {text}"]

    def add(table, row, cell, old, new):
        if new != old:
            edits.append({"table": table, "index": R.ival(row["index"]), "label": row["label"], "cell": cell,
                          "old": old, "new": new})

    # 1. Master Seal targets
    promo = {jid: [j.get(c, pf.none) for c in PROMO_CELLS] for jid, j in facts.jobs.items()}
    if o["promotions"] == "on":
        drawn, notes = _draw_promotions(pf, key, text, o["sides"])
        for jid in pf.sources:
            j = facts.jobs[jid]
            old = [j.get(c, pf.none) for c in PROMO_CELLS]
            new = list(old)
            k = 0
            for i, c in enumerate(PROMO_CELLS):
                if old[i] not in ("", pf.none):
                    new[i] = drawn[jid][k]
                    k += 1
            for i, c in enumerate(PROMO_CELLS):
                add("Job", j, c, old[i], new[i])
            promo[jid] = new
            lines.append(f"{facts.jname(jid)} [{jid}] promotes into: "
                         f"{', '.join(facts.jname(x) for x in old if x != pf.none)}  ->  "
                         f"{', '.join(facts.jname(x) for x in new if x != pf.none)}")
        lines += [f"    ({n})" for n in notes]

    # 2. job_low follows the new promotions (the game's own pattern); done before the Heart Seal draw so that
    #    draw avoids the person's final class line
    people = [p for p in facts.persons if facts.in_scope(p)]
    final_low: dict[str, str] = {}
    if o["promotions"] == "on":
        for p in people + _low_also(facts, opts):
            pid = p["label"]
            e = bp.get(pid)
            job, low = (e["job"], e.get("job_low", p["job_low"])) if e else (p["job"], p["job_low"])
            j = facts.jobs.get(job)
            if not j or kept_row(facts, p) or job in pf.beast:
                continue
            if facts.promoted(j):
                if job not in pf.targets:
                    continue
                # a normal base class (never the Villager line) of the person's gender that now promotes into it
                ok = [b for b in pf.sources if job in promo[b] and b in pf.reclass_pool
                      and facts.female(facts.jobs[b]) == facts.female(p)]
                if low in ok or not ok:
                    continue
                same = [b for b in ok if facts.jobs[b]["origin"] == j["origin"]]
                new = stream(key, "job_low", text, pid).choice(same or ok)
            else:
                if job not in pf.sources:
                    continue
                ups = [x for x in promo[job] if x != pf.none]
                if low in ups or not ups:
                    continue
                new = stream(key, "job_low", text, pid).choice(ups)
            add("Person", p, "job_low", low, new)
            final_low[pid] = new
            lines.append(f"{facts.pname(p)} [{pid}] class line base/next: {facts.jname(low)} -> {facts.jname(new)}"
                         " (follows the new promotions)")
    # 3. Heart Seal classes
    if o["reclass"] == "random":
        for p in people:
            if kept_row(facts, p):
                continue
            pid = p["label"]
            e = bp.get(pid)
            job, low = (e["job"], e.get("job_low", p["job_low"])) if e else (p["job"], p["job_low"])
            low = final_low.get(pid, low)
            mine = {own_base(facts, job, low), own_base(facts, p["job"], p["job_low"])}
            old = [p.get(c, pf.none) for c in RECLASS_CELLS]
            if not any(x not in ("", pf.none) for x in old):
                continue
            pj = facts.jobs[job]
            pool = [c for c in pf.reclass_pool if facts.female(facts.jobs[c]) == facts.female(p) and c not in mine]
            if o["sides"] == "own" and R.ival(pj["origin"]) in (1, 2):
                pool = [c for c in pool if R.ival(facts.jobs[c]["origin"]) == R.ival(pj["origin"])] or pool
            r = stream(key, "reclass", text, pid)
            new = list(old)
            drawn: list[str] = []
            for i, x in enumerate(old):
                if x in ("", pf.none):
                    continue
                left = [c for c in pool if c not in drawn]
                if not left:            # too few classes for this person: the slot keeps its class
                    lines.append(f"{facts.pname(p)} [{pid}]: no other legal Heart Seal class for slot {i + 1}; kept")
                    drawn.append(x)
                    continue
                new[i] = r.choice(left)
                drawn.append(new[i])
            for i, c in enumerate(RECLASS_CELLS):
                add("Person", p, c, old[i], new[i])
            if new != old:
                lines.append(f"{facts.pname(p)} [{pid}] Heart Seal classes: "
                             f"{', '.join(facts.jname(x) for x in old if x != pf.none)}  ->  "
                             f"{', '.join(facts.jname(x) for x in new if x != pf.none)}")

    if len(lines) == 1:
        lines.append("no promotion or Heart Seal class changed")
    return edits, lines


# ------------------------------------------------------------------ guards
def run_guards(tables: R.Facts, edits: list[dict], opts: dict | None = None) -> dict:
    """{guard: {"ok": bool, "detail": [...]}} over a list of this track's edits. opts: the same opts (sides, and
    base_plan for the job_low "old" values and the starting classes)."""
    facts = tables
    o = check_opts({k: v for k, v in (opts or {}).items() if k in DEFAULT_OPTS})
    pf = PromoFacts(facts)
    base_plan = (opts or {}).get("base_plan")
    bp = {e["pid"]: e for e in base_plan["persons"]} if base_plan else {}
    out = {}

    def g(name, bad):
        out[name] = {"ok": not bad, "detail": bad[:20]}

    bad_cells = []
    also = {p["label"] for p in _low_also(facts, opts)}
    persons_after = {p["label"]: dict(p) for p in facts.persons}
    for pid, e in bp.items():
        persons_after[pid]["job"] = e["job"]
        persons_after[pid]["job_low"] = e.get("job_low", persons_after[pid]["job_low"])
    for ed in edits:
        if ed["table"] == "Job":
            j = facts.jobs.get(ed["label"])
            if (j is None or ed["cell"] not in PROMO_CELLS or ed["label"] not in pf.sources
                    or R.ival(j["index"]) != ed["index"] or j.get(ed["cell"]) != ed["old"]):
                bad_cells.append(f"Job {ed['label']} {ed['cell']}")
        elif ed["table"] == "Person":
            p = facts.by_pid.get(ed["label"])
            scoped = facts.in_scope(p) if p is not None else False
            if (p is None or ed["cell"] not in RECLASS_CELLS + ("job_low",)
                    or not (scoped or (ed["label"] in also and ed["cell"] == "job_low"))
                    or R.ival(p["index"]) != ed["index"] or persons_after[ed["label"]].get(ed["cell"]) != ed["old"]):
                bad_cells.append(f"Person {ed['label']} {ed['cell']}")
                continue
            persons_after[ed["label"]][ed["cell"]] = ed["new"]
        else:
            bad_cells.append(f"{ed['table']} {ed.get('label')}")
    g("only base classes' promotion cells and the playable people's Heart Seal / job_low cells", bad_cells)

    after = _promotions_after(pf, edits)
    illegal, count, dup, untouched = [], [], [], []
    for jid, j in facts.jobs.items():
        old = [j.get(c, pf.none) for c in PROMO_CELLS]
        new = after[jid]
        if jid not in pf.sources:
            if new != old:
                untouched.append(f"{jid} ({'promoted' if facts.promoted(j) else 'special / beast / excluded'} row)")
            continue
        if [x != pf.none for x in old] != [x != pf.none for x in new]:
            count.append(jid)
        filled = [x for x in new if x != pf.none]
        if len(set(filled)) != len(filled):
            dup.append(jid)
        if not filled:
            count.append(f"{jid}: no promotion left")
        changed = new != old
        for x in filled:
            why = pf.legal_target(jid, x, "any")   # sides=own is a preference (a short line falls back)
            if why and changed:
                illegal.append(f"{jid} -> {x}: {why}")
    g("every promotion a normal promoted class of the same gender that keeps the weapon kind", illegal)
    g("every base class keeps its number of promotions (no dead ends)", count)
    g("no class offered twice in one Master Seal menu", dup)
    g("promoted, beast, avatar, singer and DLC rows untouched", untouched)

    reach_all = {x for jid in pf.sources for x in after[jid] if x != pf.none}
    starts, low_bad = [], []
    for p in facts.persons:
        if not (facts.in_scope(p) or p["label"] in also) or kept_row(facts, p):
            continue
        a = persons_after[p["label"]]
        j = facts.jobs.get(a["job"])
        if not j or a["job"] in pf.beast or a["job"] not in pf.targets + pf.sources:
            continue
        if facts.promoted(j) and a["job"] not in reach_all and p["label"] not in also:
            starts.append(f"{p['label']}: {a['job']} reached by no base class")
        if any(e["table"] == "Job" for e in edits):
            if facts.promoted(j):
                if a["job"] not in after.get(a["job_low"], []):
                    low_bad.append(f"{p['label']}: job_low {a['job_low']} does not promote into {a['job']}")
            elif a["job_low"] not in after[a["job"]]:
                low_bad.append(f"{p['label']}: job_low {a['job_low']} is not a promotion of {a['job']}")
    g("every promoted class a playable person starts in stays reachable", starts)
    g("job_low matches the promotions (the game's own pattern)", low_bad)

    rc_bad, rc_kept = [], []
    for p in facts.persons:
        if not facts.in_scope(p):
            continue
        a = persons_after[p["label"]]
        old = [p.get(c, pf.none) for c in RECLASS_CELLS]
        new = [a.get(c, pf.none) for c in RECLASS_CELLS]
        if new == old:
            continue
        if kept_row(facts, p):
            rc_kept.append(p["label"])
            continue
        if [x != pf.none for x in old] != [x != pf.none for x in new]:
            rc_bad.append(f"{p['label']}: filled slots changed")
        filled = [x for x in new if x != pf.none]
        if len(set(filled)) != len(filled):
            rc_bad.append(f"{p['label']}: same class twice")
        mine = own_base(facts, a["job"], a["job_low"])
        for x in filled:
            if x not in pf.reclass_pool:
                rc_bad.append(f"{p['label']}: {x} not a normal base class")
            elif facts.female(facts.jobs[x]) != facts.female(p):
                rc_bad.append(f"{p['label']}: {x} other gender row")
            elif x == mine:
                rc_bad.append(f"{p['label']}: {x} is their own class line")
    g("Heart Seal classes legal, own gender, not the own line, no repeats, empty stays empty", rc_bad)
    g("Corrin's and the singer's Heart Seal cells untouched", rc_kept)
    return out


# ------------------------------------------------------------------ output
def apply_edits(plan: dict, edits: list[dict], opts: dict | None = None) -> dict:
    """A copy of a slice-1 plan that records this track (plan["tracks"]["promotions"])."""
    if not edits:
        return plan
    out = copy.deepcopy(plan)
    o = check_opts({k: v for k, v in (opts or {}).items() if k in DEFAULT_OPTS})
    out.setdefault("tracks", {})[TRACK] = {"tool": TOOL, "opts": o, "edits": edits}
    return out


def files_with_edits(facts: R.Facts, s1files: dict[str, bytes], edits: list[dict]) -> dict[str, bytes]:
    """slice 1's files with this track's cells: tables/Job.csv (new) and the Person cells added as columns to
    slice 1's tables/Person.csv (a row slice 1 did not write gets its slice-1 columns from the original rows)."""
    files = dict(s1files)
    jobs: dict[str, dict] = {}
    for ed in edits:
        if ed["table"] == "Job":
            jobs.setdefault(ed["label"], {})[ed["cell"]] = ed["new"]
    if jobs:
        rows = [["index", "label"] + list(PROMO_CELLS)]
        for jid in sorted(jobs, key=lambda x: R.ival(facts.jobs[x]["index"])):
            j = facts.jobs[jid]
            rows.append([j["index"], jid] + [jobs[jid].get(c, j.get(c, "")) for c in PROMO_CELLS])
        files["tables/Job.csv"] = R._csv(rows)
    by: dict[str, dict] = {}
    for ed in edits:
        if ed["table"] == "Person":
            by.setdefault(ed["label"], {})[ed["cell"]] = ed["new"]
    if by:
        txt = files.get("tables/Person.csv", b"index,label\n").decode("utf-8").lstrip("﻿")
        rdr = list(csv.reader(io.StringIO(txt)))
        head, body = rdr[0], rdr[1:]
        extra = [c for c in RECLASS_CELLS if any(c in v for v in by.values())]
        nhead = head + extra
        jl = head.index("job_low") if "job_low" in head else None
        out_rows, seen = [], set()
        for row in body:
            pid = row[1]
            p = facts.by_pid[pid]
            seen.add(pid)
            row = list(row)
            if jl is not None and "job_low" in by.get(pid, {}):
                row[jl] = by[pid]["job_low"]
            out_rows.append(row + [by.get(pid, {}).get(c, p.get(c, "")) for c in extra])
        for p in facts.persons:
            pid = p["label"]
            if pid in by and pid not in seen:
                vals = [by[pid].get(c, p.get(c, "")) if c == "job_low" else p.get(c, "") for c in head[2:]]
                out_rows.append([p["index"], pid] + vals + [by[pid].get(c, p.get(c, "")) for c in extra])
        if jl is None and any("job_low" in v for v in by.values()):
            nhead.append("job_low")
            out_rows = [r + [by.get(r[1], {}).get("job_low", facts.by_pid[r[1]]["job_low"])] for r in out_rows]
        out_rows.sort(key=lambda r: int(r[0]))
        files["tables/Person.csv"] = R._csv([nhead] + out_rows)
    return files


def make_folder(seed: str, opts: dict, out_top: str, facts=None) -> tuple[str, dict, list[dict]]:
    """slice 1 (default switches) + this track only, as one mod folder (the integrate round does the real merge)."""
    import gamedata as GD
    facts = facts or GD.load_facts()
    plan = R.make_plan(facts, seed, {})
    o = dict(check_opts(opts), base_plan=plan)
    edits, lines = plan_promotions(facts, seed, o)
    guards = run_guards(facts, edits, o)
    files = files_with_edits(facts, R.render(facts, plan), edits)
    meta = json.loads(files["mod.json"].decode("utf-8"))
    meta["description"] += f" + promotions track ({opts_text(check_opts(opts))}); test folder."
    meta["randomizer"]["tracks"] = {TRACK: check_opts(opts)}
    files["mod.json"] = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    sp = lines + ["", "Promotions guards:"] + [f"  {'PASS' if v['ok'] else 'FAIL'} {k}" + ("" if v["ok"] else f" {v['detail']}")
                                               for k, v in guards.items()]
    files["spoiler.txt"] += ("\n" + "\n".join(sp) + "\n").encode("utf-8")
    files["promotions.json"] = (json.dumps({"tool": TOOL, "seed": seed, "opts": check_opts(opts), "edits": edits,
                                            "guards": guards}, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    folder = R.write_mod(files, os.path.join(out_top, R.mod_name(seed)))
    return folder, guards, edits


def _forbidden(path: str) -> str | None:
    p = os.path.normcase(os.path.realpath(path))
    for env in ("APPDATA", "LOCALAPPDATA"):
        top = os.environ.get(env)
        if top and (p + os.sep).startswith(os.path.normcase(os.path.realpath(top)) + os.sep):
            return f"{path} is inside %{env}%"
    if not (p + os.sep).startswith(os.path.normcase(os.path.realpath(os.path.join(ROOT, "build"))) + os.sep):
        return f"{path} is not below build/"
    return None


def main(argv: list[str] | None = None) -> int:
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make")
    p.add_argument("--seed", required=True)
    p.add_argument("--promotions", choices=PROMO_MODES, default="on")
    p.add_argument("--choices", default="2")
    p.add_argument("--reclass", choices=RECLASS_MODES, default="keep")
    p.add_argument("--sides", choices=SIDE_MODES, default="any")
    p.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        why = _forbidden(a.out)
        if why:
            raise R.RandoError(f"refused: {why}")
        opts = {"promotions": a.promotions, "choices": a.choices, "reclass": a.reclass, "sides": a.sides}
        folder, guards, edits = make_folder(a.seed, opts, os.path.abspath(a.out))
        print(f"made {folder}: {len(edits)} cells")
        for k, v in guards.items():
            print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
        return 0 if all(v["ok"] for v in guards.values()) else 2
    except R.RandoError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
