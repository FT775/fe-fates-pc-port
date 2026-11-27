#!/usr/bin/env python3
"""Randomizer track "children" (owner 2026-11-20 "build the other missing parts too"; docs/rando/CHILDREN.md):
the 22 child units (the Person rows with a child_id: the two Kana rows and the 20 children who join in a
paralogue) get the same randomizing as the adults: class (slice 1's way), growths and join stats (slice 1's
switches, then the growth track's modes), personal skills and, if asked, class skills that follow the new class
(the skills track's modes). No other row, no new row, no flag.

    plan_children(tables, rng, opts) -> (edits, spoiler_lines)

tables  a randolib.Facts (the original rows)
rng     the run seed (text, as given to rando.py) or a random.Random; this track derives its OWN sub-seed from it
        and the track name, so no other track's draws move and the adults' slice-1 plan is never touched
opts    DEFAULT_OPTS keys (the names rando.py / tracks.py already use for the adults), plus optional
          "base_plan"       the adults' slice-1 plan: only read, to show the class each child would inherit from
                            its fixed parent in the spoiler log (the game reads the parent's Person row)
          "skill_rows"      the Skill rows (else read from the user's RomFS when a skill option is on)
          "taken_personal"  personal skills the adults hold after the skills track (random mode avoids them)

edits   Person cells   {"table": "Person", "index": 51, "label": "PID_..", "cell": "job", "old": .., "new": ..}
        DisposUnit     {"table": "DisposUnit", "file": .., "index": 40, "label": .., "column": "item_1",
                        "old": .., "new": ..}      (only a child's own placements; only item cells)

"children" off (the default) -> NO edits and no lines, so every existing seed stays byte-identical.

What a table edit can change and what it cannot (facts: docs/rando/CHILDREN.md section 2): the child's own
class at join (Person.job / job_low; the paralogue placements name no class), its personal growths (the game
averages them with one parent's at every level-up), its personal join stats, weapon exp, skills. It cannot pick
the class the child inherits from its parents for the Heart Seal: the game decides that when the child joins
(anonymous_namespace::GetInheritJobIndex reads the parent's Person row), nor the stat and skill terms the game
takes from the parents' live units at join (Unit::Inherit2, Unit::InheritEquipSkill).

Guards (tests/test_rando_children.py): legal classes (gender, tier, beasts stay beasts, the dragon Kana keeps
his/her class, no excluded class); a child who started as a healer keeps a staff class, a child who started
with a weapon keeps an attack class and holds a usable attack weapon in every one of its placements (paralogues
stay winnable: the child often fights alone or as an AI ally before it joins); every carried item usable; stats
within the class caps; the lock-opening skill never moved (door opener); personal skills of the personal family,
no two children the same; only children's rows and their placements' item cells.

Our own code; it reuses slice 1 (randolib), the growth track and the skills track. Public Fates randomizers
(GPL) were read for facts only.

    python tools/randomizer/children.py check [--seeds N] [option flags]   (host only: guards over N seeds)
    python tools/randomizer/children.py make --seed S [option flags] --out DIR   (slice 1 + this track)
"""
from __future__ import annotations

import copy
import hashlib
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "children"
TOOL = "rando-children-v1"
NONE_SKILL = "SEID_無し"
SKILL_CELLS = [f"skill.{i}" for i in range(1, 6)]
PERSONAL_CELLS = ("personal_skill.normal", "personal_skill.hard", "personal_skill.lunatic")
PERSON_CELLS = list(R.PERSON_COLS) + SKILL_CELLS + list(PERSONAL_CELLS)
# Job flags read by anonymous_namespace::IsInheritJobIndex 0x003C59F4 (labels from its literal pool)
INHERIT_BANNED = "SPID_継承禁止"            # never inherited (the singer's class)
SUPPORT_INHERIT_BANNED = "SPID_支援継承禁止"   # not inherited through a support pairing (Nohr Prince(ss), Wolfskin,
                                            # Kitsune, Villager)

DEFAULT_OPTS = {
    "children": False,                       # slice 1's switch name (rando.py --children); off = no edits
    # slice 1's switches, applied to the children
    "classes": True, "growths": True, "join_stats": True, "trees": "own",
    # the growth track's modes (tracks.py names)
    "growth_mode": "slice1", "growth_variance": 30, "growth_min": 5, "growth_max": 80, "adjust_hp": False,
    "bases_mode": "slice1", "base_variance": 5, "scale_to_level": True,
    # the skills track's modes (tracks.py names)
    "personal_skills": "keep", "skill_slots": "keep",
}
CHOICES = {"trees": ("own", "any"), "growth_mode": ("slice1", "redistribute", "delta", "full"),
           "bases_mode": ("slice1", "redistribute", "delta"), "personal_skills": ("keep", "shuffle", "random"),
           "skill_slots": ("keep", "class")}
BOOLS = ("children", "classes", "growths", "join_stats", "adjust_hp", "scale_to_level")
NUMBERS = {"growth_variance": (0, 100), "growth_min": (0, 100), "growth_max": (0, 125), "base_variance": (1, 10)}


# ------------------------------------------------------------------ options and the sub-seed
def check_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS)
    o.update({k: v for k, v in (opts or {}).items() if k in DEFAULT_OPTS and v is not None})
    for k, ch in CHOICES.items():
        o[k] = str(o[k]).strip().lower()
        if o[k] not in ch:
            raise R.RandoError(f"children {k.replace('_', '-')}: one of {', '.join(ch)}")
    for k in BOOLS:
        o[k] = bool(o[k])
    for k, (lo, hi) in NUMBERS.items():
        try:
            o[k] = int(str(o[k]).strip().rstrip("%"))
        except ValueError:
            raise R.RandoError(f"children {k.replace('_', '-')}: a whole number {lo}-{hi}") from None
        if not lo <= o[k] <= hi:
            raise R.RandoError(f"children {k.replace('_', '-')}: {o[k]} is outside {lo}-{hi}")
    return o


def opts_text(o: dict) -> str:
    out = []
    for k, v in o.items():
        if k != "children" and v != DEFAULT_OPTS[k]:
            out.append(f"{k.replace('_', '-')}={'on' if v is True else 'off' if v is False else v}")
    return " ".join(out) or "defaults"


def sub_seed(rng) -> str:
    """This track's own seed text (a valid slice-1 seed, 40 characters): from the run seed and the track name, or
    256 bits of a given Random. The slice-1 machinery below draws from it, so the adults' draws never move."""
    if isinstance(rng, random.Random):
        base = "random:" + format(rng.getrandbits(256), "064x")
    else:
        base = "seed:" + R.check_seed(str(rng))
    return "ch" + hashlib.sha256("\x1f".join([TOOL, base, TRACK]).encode("utf-8")).hexdigest()[:38]


def stream(key: str, purpose: str, who: str) -> random.Random:
    h = hashlib.sha256("\x1f".join([TOOL, key, purpose, who]).encode("utf-8")).digest()
    return random.Random(int.from_bytes(h, "big"))


def promo_ups(facts: R.Facts, job: str, job_promotions: dict | None = None) -> list[str]:
    """The promotions of a base class: the final ones when the promotions track passed them
    (opts["job_promotions"] = {class: [promotion cells]}), else the Job row's own."""
    if job_promotions is not None and job in job_promotions:
        cells = job_promotions[job]
    else:
        j = facts.jobs.get(job) or {}
        cells = [j.get("promotion.1"), j.get("promotion.2")]
    return [x for x in cells if x in facts.jobs and not facts.excluded_job(x)]


def fit_job_low(facts: R.Facts, p: dict, job: str, low: str, jp: dict, key: str) -> str:
    """job_low that fits the final promotions jp (the promotions track's Job edits): a base class keeps a job_low
    among its new promotions, a promoted class one of the base classes (own gender row) that now promote into it.
    The old value stays when it already fits or when nothing fits."""
    j = facts.jobs.get(job)
    if j is None:
        return low
    if not facts.promoted(j):
        ups = promo_ups(facts, job, jp)
        if not ups or low in ups:
            return low
        return stream(key, "job_low-promotions", p["label"]).choice(ups)
    bases = [b for b, cells in jp.items() if job in cells and b in facts.jobs and not facts.promoted(facts.jobs[b])
             and not facts.excluded_job(b) and facts.female(facts.jobs[b]) == facts.female(p)]
    if not bases or low in bases:
        return low
    same = [b for b in bases if facts.jobs[b]["origin"] == j["origin"]]
    return stream(key, "job_low-promotions", p["label"]).choice(same or bases)


# ------------------------------------------------------------------ the children's view of the facts
def attack_kinds(facts: R.Facts, jid: str) -> list[int]:
    """Weapon kinds of a class that can attack (everything but the staff)."""
    mx = facts.wexp_max(facts.jobs[jid])
    return [k for k in range(8) if mx[k] > 0 and k != facts.rules["staff_kind"]]


def has_staff(facts: R.Facts, jid: str) -> bool:
    return facts.wexp_max(facts.jobs[jid])[facts.rules["staff_kind"]] > 0


def role_need(facts: R.Facts, p: dict) -> str:
    """'healer' when the child starts in a class with a staff (it stays a staff user), else 'attack' when it
    starts in a class with a weapon (it keeps a class that can attack), else ''."""
    jid = p["job"]
    if jid not in facts.jobs:
        return ""
    if has_staff(facts, jid):
        return "healer"
    return "attack" if attack_kinds(facts, jid) else ""


def role_fits(facts: R.Facts, need: str, jid: str) -> bool:
    if need == "healer":
        return has_staff(facts, jid)
    if need == "attack":
        return bool(attack_kinds(facts, jid))
    return True


class ChildFacts(R.Facts):
    """The same rows; "in scope" means a child of the player's army (the slice-1 rules otherwise: not a bond,
    capture-only, downloadable or enemy-only row), and a child's legal classes also keep its role."""

    @classmethod
    def of(cls, facts: R.Facts) -> "ChildFacts":
        cf = copy.copy(facts)
        cf.__class__ = cls
        return cf

    def in_scope(self, p: dict) -> bool:
        r = self.rules
        if R.ival(p["index"]) == 0 or p.get("belong") != r["player_army"]:
            return False
        if R.flags(p["flags"]) & set(r["scope_exclude_person_flags"]):
            return False
        return self.is_child(p)

    def legal_classes(self, p: dict, sw: dict, promoted: bool | None = None) -> list[str]:
        out = R.Facts.legal_classes(self, p, sw, promoted)
        if not self.is_child(p) or promoted is not None:
            return out
        need = role_need(self, p)
        return [j for j in out if role_fits(self, need, j)]


def children(facts: R.Facts) -> list[dict]:
    cf = facts if isinstance(facts, ChildFacts) else ChildFacts.of(facts)
    return [p for p in facts.persons if cf.in_scope(p)]


def join_chapters(facts: R.Facts, pid: str) -> list[str]:
    """The chapters (Dispos files) that place this person, in name order."""
    return sorted({facts.chapter_of(d) for d in facts.placements(pid)})


# ------------------------------------------------------------------ the inherited class (as the game picks it)
def low_job(facts: R.Facts, p: dict, job: str | None = None, job_low: str | None = None) -> str:
    """Person::GetLowJobIndex 0x0053E198: the class, or job_low when the class is promoted."""
    j = job or p["job"]
    if j in facts.jobs and facts.promoted(facts.jobs[j]):
        return job_low or p["job_low"]
    return j


def is_inherit_job(facts: R.Facts, jid: str, child: dict, child_low: str, support: bool) -> str | None:
    """anonymous_namespace::IsInheritJobIndex 0x003C59F4 read as Python (the extra exclusion list argument is
    left out: it comes from the caller at join time). Returns the class the child would get (the other-gender
    twin when the genders differ), or None."""
    j = facts.jobs.get(jid)
    if not j or R.ival(j["index"]) == 0:
        return None
    if facts.female(j) != facts.female(child):
        jid = j.get("gender_pair", "")
        j = facts.jobs.get(jid)
        if not j or R.ival(j["index"]) == 0:
            return None
    if jid == child_low or facts.promoted(j):
        return None
    jf = R.flags(j["flags"])
    if INHERIT_BANNED in jf or (not support and SUPPORT_INHERIT_BANNED in jf):
        return None
    return jid


def inherited_class(facts: R.Facts, parent: dict, child: dict, child_low: str, support: bool = False,
                    parent_job: str | None = None, parent_low: str | None = None, depth: int = 0) -> str | None:
    """anonymous_namespace::GetInheritJobIndex 0x003C5C30 read as Python: the parent's base class, else the
    parent's first Heart Seal class (Person.reclass.1), else (when the parent itself has a fixed parent,
    Person.family_index) what that grandparent passes on, else the parallel class (Job.parallel_class) of the
    parent's base class, else that of its reclass.1."""
    pl = low_job(facts, parent, parent_job, parent_low)
    for cand in (pl, parent.get("reclass.1", "")):
        got = is_inherit_job(facts, cand, child, child_low, support)
        if got:
            return got
    fam = R.ival(parent.get("family_index", 0) or 0)
    if fam and depth < 3 and fam < len(facts.persons):
        gp = facts.persons[fam]
        got = inherited_class(facts, gp, parent, low_job(facts, parent, parent_job, parent_low), True,
                              depth=depth + 1)
        got = is_inherit_job(facts, got or "", child, child_low, support)
        if got:
            return got
    for base in (pl, parent.get("reclass.1", "")):
        b = facts.jobs.get(base)
        if b:
            got = is_inherit_job(facts, b.get("parallel_class", ""), child, child_low, support)
            if got:
                return got
    return None


# ------------------------------------------------------------------ the plan
def _attack_fixups(cf: ChildFacts, plan: dict, key: str) -> list[str]:
    """Slice 1's weapon swap may give a class with a staff and a weapon a staff in place of a sword. A child that
    held a usable attack weapon at the start keeps one: such a swap becomes an ordinary weapon of the same rank
    (or the nearest rank) of a kind the new class attacks with."""
    notes = []
    staff, stone = cf.rules["staff_kind"], cf.rules["stone_kind"]
    for e in plan["persons"]:
        if e["job"] == e["old_job"]:
            continue
        p = cf.by_pid[e["pid"]]
        nj = cf.jobs[e["job"]]
        mx = cf.wexp_max(nj)
        kinds = [k for k in range(8) if mx[k] > 0 and k not in (staff, stone)]
        if not kinds:
            continue
        for d in cf.placements(e["pid"]):
            key_d = f"{d['file']}#{R.ival(d['index'])}"
            ed = plan["dispos"].get(key_d, {})
            for s in range(1, 6):
                old = d.get(f"item_{s}", "")
                new = ed.get(f"item_{s}", old)
                ko, kn = cf.item_kind(old), cf.item_kind(new)
                if ko is None or ko == staff or kn != staff:
                    continue
                rank = cf.item_rank(old)
                r = stream(key, "attack-fix", e["pid"] + "\x1f" + old)
                pick = None
                for rk in sorted({rank} | {x for x in R.RANKS if x < rank}, reverse=True):
                    ks = [k for k in kinds if rk <= mx[k]]
                    r.shuffle(ks)
                    for k in ks:
                        c = cf.replacement_items(k, rk, R.ival(nj["origin"]))
                        if c:
                            pick = r.choice(c)
                            break
                    if pick:
                        break
                if pick is None:
                    notes.append(f"{e['name']}: no attack weapon found in place of {cf.iname(old)}")
                    continue
                plan["dispos"].setdefault(key_d, {"label": d.get("label", "")})[f"item_{s}"] = pick
                if cf.base_usable(p, old):
                    pk = cf.item_kind(pick)
                    e["wexp"][pk] = min(max(e["wexp"][pk], cf.item_rank(pick)), mx[pk])
                for sw_ in e.get("swaps", []):
                    if sw_["old"] == old:
                        sw_["new"], sw_["why"] = pick, sw_["why"] + "; an attack weapon kept"
    return notes


def _class_slots(sf, p: dict, nj: str, nl: str, key: str) -> tuple[list[str], list[str]]:
    """The skills track's "class" rule on one child: a slot skill the old class line teaches becomes the skill
    the new line teaches at the same place; the lock-opening skill never moves."""
    old = [p.get(c, NONE_SKILL) or NONE_SKILL for c in SKILL_CELLS]
    new = list(old)
    notes = []
    if nj == p["job"]:
        return new, notes
    nline = sf.line(nj, nl)
    r = stream(key, "slots-class", p["label"])
    tied = {i: sf.old_place(p, s) for i, s in enumerate(old) if s not in (NONE_SKILL, sf.lock)}
    tied = {i: k for i, k in tied.items() if k is not None}
    for i in tied:
        new[i] = NONE_SKILL
    late = []
    for i, k in sorted(tied.items()):
        want = nline[k]
        if want == NONE_SKILL or want in new or want in sf.banned_slot:
            late.append(i)
        else:
            new[i] = want
    for i in late:
        spare = [x for x in nline if x != NONE_SKILL and x not in new and x not in sf.banned_slot]
        new[i] = r.choice(spare or [x for x in sf.slot_pool if x not in new])
        notes.append(f"slot {i + 1}: {sf.name(old[i])} has no place in the new class line; got {sf.name(new[i])}")
    return new, notes


def plan_children(tables: R.Facts, rng, opts: dict | None = None) -> tuple[list[dict], list[str]]:
    facts = tables
    o = check_opts(opts)
    if not o["children"]:
        return [], []
    extra = opts or {}
    cf = ChildFacts.of(facts)
    seed = sub_seed(rng)
    sw = {"classes": o["classes"], "growths": o["growths"], "join_stats": o["join_stats"], "trees": o["trees"],
          "keep_royals": True, "children": False}
    plan = R.make_plan(cf, seed, sw)
    # the route-role lines of slice 1 speak about the adults (who are not in this plan); drop them
    plan["notes"] = [n for n in plan["notes"] if not n.startswith("route ")]
    plan["notes"] += _attack_fixups(cf, plan, seed)
    lines = [f"Children track ({TOOL}): {opts_text(o)}",
             "The class each child inherits from its parents (an extra Heart Seal class) is picked by the game when",
             "the child joins, from the parents' Person rows; the line 'inherits from <fixed parent>' shows what the",
             "game's rule gives with this seed's tables (the other parent is whoever the player paired)."]

    # growth track modes on top
    go = {"growths": o["growth_mode"], "growth_variance": o["growth_variance"], "growth_min": o["growth_min"],
          "growth_max": o["growth_max"], "adjust_hp": o["adjust_hp"], "bases": o["bases_mode"],
          "base_variance": o["base_variance"], "scale_to_level": o["scale_to_level"]}
    g_lines: list[str] = []
    if go["growths"] != "slice1" or go["bases"] != "slice1":
        import growth as G
        g_edits, g_lines = G.plan_growth(cf, seed, dict(go, base_plan=plan))
        plan = G.apply_edits(plan, g_edits, go)

    # skills
    new_skills: dict[str, dict[str, str]] = {}
    s_lines: list[str] = []
    if o["personal_skills"] != "keep" or o["skill_slots"] != "keep":
        import skills as S
        rows = extra.get("skill_rows") or getattr(facts, "skills", None) or S.load_skill_rows()
        sf = S.SkillFacts(facts, rows)
        kids = [facts.by_pid[e["pid"]] for e in plan["persons"]]
        movable = [p for p in kids if p.get("personal_skill.normal", NONE_SKILL) in sf.personal_family
                   and p.get("personal_skill.normal") not in S.KEEP_PERSONAL]
        if o["personal_skills"] == "shuffle":
            deck = [p["personal_skill.normal"] for p in movable]
            stream(seed, "personal-shuffle", "all").shuffle(deck)
            picks = dict(zip([p["label"] for p in movable], deck))
        elif o["personal_skills"] == "random":
            r = stream(seed, "personal-random", "all")
            taken = set(extra.get("taken_personal") or [])
            left = [s for s in sf.personal_pool if s not in taken]
            # round W1: with the adults' skills taken there may be fewer free skills than moving children. Then the
            # last children keep their own skill, and those skills leave the pool, so no child draws a skill another
            # child keeps (with enough skills this changes nothing)
            m = len(movable)
            while m > 0:
                keep = {p["personal_skill.normal"] for p in movable[m:]}
                if len([s for s in left if s not in keep]) >= m:
                    break
                m -= 1
            keep = {p["personal_skill.normal"] for p in movable[m:]}
            left = [s for s in left if s not in keep]
            picks = {}
            for p in movable[:m]:
                if not left:
                    break
                pick = r.choice(left)
                left.remove(pick)
                picks[p["label"]] = pick
        else:
            picks = {}
        for pid, s in picks.items():
            p = facts.by_pid[pid]
            for c in PERSONAL_CELLS:
                new_skills.setdefault(pid, {})[c] = s
            if s != p["personal_skill.normal"]:
                s_lines.append(f"{facts.pname(p)} [{pid}] personal skill: {sf.name(p['personal_skill.normal'])} -> "
                               f"{sf.name(s)}")
        if o["skill_slots"] == "class":
            for e in plan["persons"]:
                p = facts.by_pid[e["pid"]]
                new, notes = _class_slots(sf, p, e["job"], e["job_low"], seed)
                for i, c in enumerate(SKILL_CELLS):
                    new_skills.setdefault(e["pid"], {})[c] = new[i]
                old = [p.get(c, NONE_SKILL) or NONE_SKILL for c in SKILL_CELLS]
                if new != old:
                    s_lines.append(f"{facts.pname(p)} [{e['pid']}] skills: "
                                   f"{', '.join(sf.name(x) for x in old if x != NONE_SKILL)}  ->  "
                                   f"{', '.join(sf.name(x) for x in new if x != NONE_SKILL)}")
                    s_lines += [f"    ({n})" for n in notes]

    # edits: Person cells that differ from the original rows, then the placements' item cells
    edits: list[dict] = []
    bp = {e["pid"]: e for e in (extra.get("base_plan") or {}).get("persons", [])}
    jp = extra.get("job_promotions")
    for e in plan["persons"]:
        p = facts.by_pid[e["pid"]]
        if jp is not None:      # the promotions track is on: the child's job_low follows the new promotions
            e["job_low"] = fit_job_low(facts, p, e["job"], e["job_low"], jp, seed)
        vals = dict(zip(R.PERSON_COLS, [e["job"], e["job_low"]] + [str(v) for v in e["base"]]
                        + [str(v) for v in e["growth"]] + [str(v) for v in e["wexp"]]))
        vals.update(new_skills.get(e["pid"], {}))
        for c in PERSON_CELLS:
            if c in vals and vals[c] != p.get(c, ""):
                edits.append({"table": "Person", "index": R.ival(p["index"]), "label": e["pid"], "cell": c,
                              "old": p.get(c, ""), "new": vals[c]})
        # spoiler
        cls = (f"{facts.jname(e['old_job'])} -> {facts.jname(e['job'])}" if e["job"] != e["old_job"]
               else f"{facts.jname(e['job'])} (kept: {e['kept']})" if e["kept"] else f"{facts.jname(e['job'])} (same)")
        lines.append(f"{e['name']} [{e['pid']}] joins in {', '.join(join_chapters(facts, e['pid'])) or '-'}")
        lines.append(f"  class:    {cls}")
        if e["job"] != e["old_job"] and e["job_low"]:
            lines.append(f"  promotes (table's line): {facts.jname(e['job_low'])}")
        fam = R.ival(p.get("family_index", 0) or 0)
        if 0 < fam < len(facts.persons):
            par = facts.persons[fam]
            pe = bp.get(par["label"])
        if 0 < fam < len(facts.persons) and facts.rules["keep_class_person_flags"][0] in R.flags(par["flags"]):
            lines.append(f"  inherits from {facts.pname(par)} (fixed parent): the class the avatar's own choices give "
                         "(the game has a separate GetInheritJobIndexFromPlayer for this; not read yet)")
        elif 0 < fam < len(facts.persons):
            got = inherited_class(facts, par, p, low_job(facts, p, e["job"], e["job_low"]),
                                  parent_job=pe["job"] if pe else None, parent_low=pe["job_low"] if pe else None)
            lines.append(f"  inherits from {facts.pname(par)} (fixed parent): "
                         f"{facts.jname(got) if got else 'nothing (the rule finds no class)'}")
        lines.append(f"  growths:  {' '.join(map(str, e['old_growth']))}  ->  {' '.join(map(str, e['growth']))}"
                     "   (the game averages these with one parent's)")
        lines.append(f"  bases:    {' '.join(map(str, e['old_base']))}  ->  {' '.join(map(str, e['base']))}")
        for s in e.get("swaps", []):
            lines.append(f"  item swapped: {facts.iname(s['old'])} -> {facts.iname(s['new'])} ({s['why']})")
    orig = {(d["file"], R.ival(d["index"])): d for d in facts.dispos}
    for k, ed in sorted(plan["dispos"].items()):
        f, ix = k.rsplit("#", 1)
        d = orig[(f, int(ix))]
        for s in range(1, 6):
            c = f"item_{s}"
            if c in ed and ed[c] != d.get(c, ""):
                edits.append({"table": "DisposUnit", "file": f, "index": int(ix), "label": d.get("label", ""),
                              "column": c, "old": d.get(c, ""), "new": ed[c]})
    if g_lines:
        lines += ["", "Children: growth and bases modes (growth track rules)"] + g_lines[1:]
    if s_lines:
        lines += ["", "Children: skills (skills track rules)"] + s_lines
    if plan["notes"]:
        lines += ["", "Children: notes"] + [f"  {n}" for n in plan["notes"]]
    return edits, lines


# ------------------------------------------------------------------ guards (recomputed from the edits alone)
def rows_after(facts: R.Facts, edits: list[dict]) -> tuple[dict, dict]:
    """({pid: Person row with this track's cells}, {(file, index): placement row with its item cells})."""
    persons: dict[str, dict] = {}
    dispos: dict[tuple, dict] = {}
    orig = {(d["file"], R.ival(d["index"])): d for d in facts.dispos}
    for ed in edits:
        if ed["table"] == "Person":
            persons.setdefault(ed["label"], dict(facts.by_pid[ed["label"]]))[ed["cell"]] = ed["new"]
        else:
            k = (ed["file"], int(ed["index"]))
            dispos.setdefault(k, dict(orig[k]))[ed["column"]] = ed["new"]
    return persons, dispos


def run_guards(tables: R.Facts, edits: list[dict], opts: dict | None = None) -> dict:
    """{guard: {"ok": bool, "detail": [...]}}. With "children" off: every guard passes only when edits == []."""
    facts = tables
    o = check_opts(opts)
    cf = ChildFacts.of(facts)
    sw = {"classes": o["classes"], "growths": o["growths"], "join_stats": o["join_stats"], "trees": o["trees"],
          "keep_royals": True, "children": False}
    out: dict[str, dict] = {}

    def g(name, bad):
        out[name] = {"ok": not bad, "detail": bad[:50]}

    kids = {p["label"] for p in children(facts)}
    g("off_means_no_edits", [] if o["children"] or not edits else [f"{len(edits)} edits with children off"])
    persons, dispos = rows_after(facts, edits)
    orig = {(d["file"], R.ival(d["index"])): d for d in facts.dispos}
    # only children, only allowed cells
    bad = [f"{e['label']}: not a child in scope" for e in edits if e["table"] == "Person" and e["label"] not in kids]
    bad += [f"{e['file']}#{e['index']}: not a child's placement" for e in edits
            if e["table"] == "DisposUnit" and orig[(e["file"], int(e["index"]))].get("pid") not in kids]
    g("only_children", bad)
    bad = [f"{e['label']} {e['cell']}" for e in edits if e["table"] == "Person" and e["cell"] not in PERSON_CELLS]
    bad += [f"{e['file']}#{e['index']} {e['column']}" for e in edits
            if e["table"] == "DisposUnit" and e["column"] not in [f"item_{s}" for s in range(1, 6)]]
    bad += [f"{e['label']} {e['cell']}: unchanged cell written" for e in edits if e["old"] == e["new"]]
    g("only_allowed_cells", bad)

    def row(pid):
        return persons.get(pid) or facts.by_pid[pid]

    # classes
    bad_legal, bad_kept, bad_role, bad_line = [], [], [], []
    jp = (opts or {}).get("job_promotions")
    for pid in sorted(kids):
        p, n = facts.by_pid[pid], row(pid)
        if n["job"] == p["job"]:
            if n["job_low"] != p["job_low"] and not facts.promoted(facts.jobs[n["job"]]):
                ups = promo_ups(facts, n["job"], jp)
                if n["job_low"] not in ups:
                    bad_line.append(f"{pid}: job_low {n['job_low']} is not a promotion of {n['job']}")
            continue
        if cf.kept_reason(p, sw):
            bad_kept.append(f"{pid}: {p['job']} -> {n['job']} although kept ({cf.kept_reason(p, sw)})")
        if n["job"] not in R.Facts.legal_classes(cf, p, sw):
            bad_legal.append(f"{pid}: {n['job']} is not a legal class")
        if not role_fits(facts, role_need(facts, p), n["job"]):
            bad_role.append(f"{pid}: {role_need(facts, p)} child given {n['job']}")
        nj = facts.jobs[n["job"]]
        if not facts.promoted(nj):
            ups = promo_ups(facts, n["job"], jp)
            if ups and n["job_low"] not in ups:
                bad_line.append(f"{pid}: job_low {n['job_low']} is not a promotion of {n['job']}")
    g("legal_class", bad_legal)
    g("story_classes_kept", bad_kept)
    g("healer_and_attack_roles_kept", bad_role)
    g("promotion_line_legal", bad_line)
    # items usable; an attack weapon kept in every placement that had one usable at the start
    bad_use, bad_att = [], []
    staff = facts.rules["staff_kind"]
    for pid in sorted(kids):
        p, n = facts.by_pid[pid], row(pid)
        wexp = [R.ival(n[f"weapon_exp.{k}"]) for k in R.KINDS]
        mx = facts.wexp_max(facts.jobs[n["job"]])
        if any(v > m for v, m in zip(wexp, mx)):
            bad_use.append(f"{pid}: weapon exp above the class limit")
        for d in facts.placements(pid):
            nd = dispos.get((d["file"], R.ival(d["index"])), d)
            had_attack = keeps_attack = False
            for s in range(1, 6):
                old, new = d.get(f"item_{s}", ""), nd.get(f"item_{s}", "")
                need = facts.base_usable(p, old)
                if n["job"] != p["job"] or new != old:
                    why = facts.class_can_hold(n["job"], p, new, wexp, need)
                    if why:
                        bad_use.append(f"{pid} {facts.chapter_of(d)} slot {s}: {new}: {why}")
                ko, kn = facts.item_kind(old), facts.item_kind(new)
                if ko is not None and ko != staff and need:
                    had_attack = True
                if kn is not None and kn != staff and facts.class_can_hold(n["job"], p, new, wexp, True) is None:
                    keeps_attack = True
            if had_attack and not keeps_attack:
                bad_att.append(f"{pid} {facts.chapter_of(d)}: no usable attack weapon left")
    g("items_usable", bad_use)
    g("attack_weapon_at_join", bad_att)
    # stats
    bad = []
    for pid in sorted(kids):
        p, n = facts.by_pid[pid], row(pid)
        j = facts.jobs[n["job"]]
        for s in R.STATS:
            raw = R.ival(n[f"base.{s}"]) + R.ival(j[f"base.{s}"])
            cap = R.ival(j[f"max.{s}"]) + R.ival(p[f"limit_mod.{s}"])
            if raw > cap or raw < (1 if s == "hp" else 0):
                bad.append(f"{pid} {s}: {raw} outside 0..{cap}")
            gr = R.ival(n[f"growth.{s}"])
            if gr < 0 or gr > 127:
                bad.append(f"{pid} growth {s}: {gr}")
    g("stats_within_caps", bad)
    # door opener: a child that holds the lock skill keeps it in the same cell
    lock = facts.rules["lock_skill"]
    bad = []
    for pid in sorted(kids):
        p, n = facts.by_pid[pid], row(pid)
        for c in SKILL_CELLS + list(PERSONAL_CELLS):
            if p.get(c) == lock and n.get(c) != lock:     # gaining it from a new class line is allowed
                bad.append(f"{pid} {c}: the lock-opening skill moved")
    g("lock_skill_kept", bad)
    # personal skills: the three cells agree; no skill held by more children than before (the two Kana rows
    # share one: only one of them ever joins, by the avatar's gender)
    bad = []
    changed = {e["label"] for e in edits if e["table"] == "Person" and e["cell"] in PERSONAL_CELLS}
    if changed:
        from collections import Counter
        before = Counter(facts.by_pid[pid].get("personal_skill.normal") for pid in kids)
        after = Counter(row(pid).get("personal_skill.normal") for pid in kids)
        for pid in sorted(changed):
            if len({row(pid).get(c) for c in PERSONAL_CELLS}) != 1:
                bad.append(f"{pid}: the three personal-skill cells differ")
        for s, n in after.items():
            if s and s != NONE_SKILL and n > max(1, before.get(s, 0)):
                bad.append(f"{s}: held by {n} children")
    g("personal_skills_unique", bad)
    return out


def guards_ok(gd: dict) -> bool:
    return all(v["ok"] for v in gd.values())


# ------------------------------------------------------------------ files (for the integrate round)
def files_with_edits(facts: R.Facts, files: dict[str, bytes], edits: list[dict]) -> dict[str, bytes]:
    """A copy of a mod folder's files with this track's rows: the children's Person rows appended to
    tables/Person.csv (every column the file already has, plus any cell of this track it lacks) and the
    children's placement item cells added to tables/DisposUnit.csv. No edits -> the same dict, unchanged."""
    if not edits:
        return files
    import csv
    import io
    out = dict(files)
    pe: dict[str, dict] = {}
    for ed in edits:
        if ed["table"] == "Person":
            pe.setdefault(ed["label"], {})[ed["cell"]] = ed["new"]
    if pe:
        if "tables/Person.csv" in files:
            rdr = list(csv.reader(io.StringIO(files["tables/Person.csv"].decode("utf-8").lstrip("﻿"))))
            head, body = rdr[0], rdr[1:]
        else:
            head, body = ["index", "label"] + list(R.PERSON_COLS), []
        cols = [c for c in PERSON_CELLS if any(c in v for v in pe.values()) and c not in head]
        nhead = head + cols
        rows = []
        for r_ in body:
            p = facts.by_pid[r_[1]]
            if r_[1] in pe:
                raise R.RandoError(f"Person {r_[1]}: written by another track and the children track")
            rows.append(r_ + [p.get(c, "") for c in cols])
        for pid, cells in pe.items():
            p = facts.by_pid[pid]
            rows.append([p["index"], pid] + [cells.get(c, p.get(c, "")) for c in nhead[2:]])
        rows.sort(key=lambda r_: int(r_[0]))
        out["tables/Person.csv"] = R._csv([nhead] + rows)
    de: dict[tuple, dict] = {}
    for ed in edits:
        if ed["table"] == "DisposUnit":
            de.setdefault((ed["file"], int(ed["index"])), {})[ed["column"]] = ed["new"]
    if de:
        orig = {(d["file"], R.ival(d["index"])): d for d in facts.dispos}
        if "tables/DisposUnit.csv" in files:
            rdr = list(csv.reader(io.StringIO(files["tables/DisposUnit.csv"].decode("utf-8").lstrip("﻿"))))
            head, body = rdr[0], rdr[1:]
        else:
            head, body = ["file", "index", "label"] + [f"item_{s}" for s in range(1, 6)], []
        items = [f"item_{s}" for s in range(1, 6)]
        nhead = head + [c for c in items if c not in head]
        rows = []
        for r_ in body:
            k = (r_[0], int(r_[1]))
            if k in de:
                raise R.RandoError(f"DisposUnit {k}: written by another track and the children track")
            rows.append(r_ + [orig[k].get(c, "") for c in nhead[len(head):]])
        for k, cells in de.items():
            d = orig[k]
            rows.append([k[0], str(k[1]), d.get("label", "")] + [cells.get(c, d.get(c, "")) for c in nhead[3:]])
        rows.sort(key=lambda r_: (r_[0], int(r_[1])))
        out["tables/DisposUnit.csv"] = R._csv([nhead] + rows)
    return out


# ------------------------------------------------------------------ command line (host only)
def _add_opts(p) -> None:
    import rando
    onoff = rando.onoff
    p.add_argument("--classes", type=onoff, default=True)
    p.add_argument("--growths", type=onoff, default=True)
    p.add_argument("--join-stats", type=onoff, default=True)
    p.add_argument("--trees", choices=CHOICES["trees"], default="own")
    p.add_argument("--growth-mode", choices=CHOICES["growth_mode"], default="slice1")
    p.add_argument("--bases-mode", choices=CHOICES["bases_mode"], default="slice1")
    p.add_argument("--personal-skills", choices=CHOICES["personal_skills"], default="keep")
    p.add_argument("--skill-slots", choices=CHOICES["skill_slots"], default="keep")


def _opts_from(a) -> dict:
    return {"children": True, "classes": a.classes, "growths": a.growths, "join_stats": a.join_stats,
            "trees": a.trees, "growth_mode": a.growth_mode, "bases_mode": a.bases_mode,
            "personal_skills": a.personal_skills, "skill_slots": a.skill_slots}


def main(argv=None) -> int:
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="every guard over N seeds on the user's own tables (host only)")
    p.add_argument("--seeds", type=int, default=50)
    _add_opts(p)
    p = sub.add_parser("make", help="slice 1 + this track for one seed, as a mod folder under build/")
    p.add_argument("--seed", required=True)
    p.add_argument("--out", required=True)
    _add_opts(p)
    a = ap.parse_args(argv)
    import gamedata as GD
    try:
        facts = GD.load_facts()
        opts = _opts_from(a)
        if opts["personal_skills"] != "keep" or opts["skill_slots"] != "keep":
            import skills as S
            facts.skills = S.load_skill_rows()
        if a.cmd == "check":
            fails, total = 0, 0
            for i in range(a.seeds):
                seed = f"c{i}"
                edits, _ = plan_children(facts, seed, opts)
                total += len(edits)
                for k, v in run_guards(facts, edits, opts).items():
                    if not v["ok"]:
                        fails += 1
                        print(f"FAIL {seed} {k}: {v['detail'][:3]}")
            print(f"{a.seeds} seeds, {total} cells, {fails} guard failures")
            return 0 if not fails else 2
        out = os.path.abspath(a.out)
        if not os.path.normcase(out).startswith(os.path.normcase(os.path.join(ROOT, "build")) + os.sep):
            print("ERROR: --out must be below build/")
            return 1
        base = R.make_plan(facts, a.seed)
        edits, lines = plan_children(facts, a.seed, dict(opts, base_plan=base))
        files = files_with_edits(facts, R.render(facts, base), edits)
        files["spoiler.txt"] += ("\n" + "\n".join(lines) + "\n").encode("utf-8")
        folder = R.write_mod(files, os.path.join(out, R.mod_name(base["seed"])))
        gd = run_guards(facts, edits, opts)
        print(f"made {folder}; {len(edits)} cells from the children track")
        for k, v in gd.items():
            print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}" + ("" if v["ok"] else f"  {v['detail'][:3]}"))
        return 0 if guards_ok(gd) else 2
    except R.RandoError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
