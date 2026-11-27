#!/usr/bin/env python3
"""Randomizer track "skills" (F-043 #1; docs/rando/SKILLS.md): personal skills and the skills already in the five
equipped-skill slots of the 49 playable people. No new skill rows, no new slots, no other table.

    plan_skills(tables, rng, opts) -> (edits, spoiler_lines)

tables  a randolib.Facts (the original rows) with the Skill rows in tables.skills, or opts["skill_rows"]
        (gamedata does not load the Skill table; load_skill_rows() below reads it through the same table tools)
rng     the run seed (text, as given to rando.py) or a random.Random; this track derives its OWN sub-seed from it
        and the track name, then one stream per (purpose, person), so no other track's draws are disturbed
opts    DEFAULT_OPTS keys, plus optional "base_plan": the slice-1 plan (randolib.make_plan); its new classes are
        what "class skills follow the new class" follows (without it the original classes are used)

edits   [{"table": "Person", "index": 4, "label": "PID_...", "cell": "skill.1", "old": "SEID_..", "new": "SEID_.."}]
        only cells whose value changes. Cells written: skill.1 .. skill.5 (only slots that already hold a skill)
        and personal_skill.normal / .hard / .lunatic (all three get the same new skill). skill_mask is never
        touched (it is 0x7FFF = every slot on every difficulty for all 49).

Modes (the FE8 port's randomizer has no skills; the shapes follow the public Fates tools' facts: shuffle the
personal skills, or give each one a random skill of the right family):
    personal  keep | shuffle (the movable people's personal skills are dealt out again among themselves)
                   | random (each movable person draws a personal-family skill, no two people the same)
    slots     keep | class (a slot skill that the person's old class line teaches becomes the skill the NEW
                     class line teaches at the same place: base class level 1 / 10, promoted class level 5 / 15)
                   | random (each filled slot draws from the skills normal player classes teach, no repeats)
Default opts are keep / keep: NO edits, so a default run stays byte-identical to slice 1. The page's suggested
values are personal=shuffle, slots=class.

Guards (each has a test in tests/test_rando_skills.py): only legal skill ids of the right family; the number and
place of filled slots unchanged; Corrin's and the singer's rows untouched; the lock-opening skill never moved
(slice 1's door-opener guard counts it); seven personal skills that the game's code or asset tables name by label
stay with their owners; same seed and opts -> the same edits.

Our own code; public Fates randomizers (GPL) were read for facts only.

    python tools/randomizer/skills.py make --seed S [--personal MODE] [--slots MODE] --out DIR
        slice 1 (default switches) + this track only, as one mod folder (robot checks)
    python tools/randomizer/skills.py robot ...   the track's one headless robot check (see robot_main)
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

TRACK = "skills"
TOOL = "rando-skills-v1"
NONE = "SEID_無し"
SLOTS = 5
PERSONAL_CELLS = ("personal_skill.normal", "personal_skill.hard", "personal_skill.lunatic")
DEFAULT_OPTS = {"personal": "keep", "slots": "keep"}
PERSONAL_MODES = ("keep", "shuffle", "random")
SLOT_MODES = ("keep", "class", "random")

# Skill.flags_2 bits (docs/TABLES.md "Skill"; Unit::CreateImpl skips a Person skill with bit 0 when unit_kind == 1,
# i.e. for every playable person): bit 0 = never given to a player unit (enemy-only rows and the personal family),
# bit 3 = the personal-skill family. Skill.kind 4 with no dictionary price = downloadable-class / DLC-only rows.
F2_NOT_PLAYER = 1
F2_PERSONAL = 8
KIND_DLC = 4
KIND_SONG = 1        # Inspiring Song: changes the singer's Sing command only

# Personal skills that stay with their owner, and why (labels, no game values). Found by searching the RomFS
# (every file, LZ unpacked) and the code for SEID_ labels: event scripts name only one skill (Self-Destruct, an
# enemy's, Scripts/B/B028.cmb); the asset table asset/ROM5.lz names three personal skills as model/effect
# conditions; the capture skills drive a command.
KEEP_PERSONAL = {
    "SEID_不思議な魅力": "Corrin's (the avatar's row is never edited)",
    "SEID_癒しの声": "the singer's (Azura's row is never edited)",
    "SEID_白夜の捕縛術": "Capture: the Hoshidan capture command (gives the person the Capture command)",
    "SEID_暗夜の拘束術": "Kidnap: the Nohrian capture command (gives the person the Capture command)",
    "SEID_炎の血": "named by the asset table asset/ROM5.lz as a model/effect condition (not traced)",
    "SEID_氷の血": "named by the asset table asset/ROM5.lz as a model/effect condition (not traced)",
    "SEID_風の血": "named by the asset table asset/ROM5.lz as a model/effect condition (not traced)",
}


def check_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS)
    for k in DEFAULT_OPTS:
        if opts and k in opts and opts[k] is not None:
            o[k] = str(opts[k]).strip().lower()
    if o["personal"] not in PERSONAL_MODES:
        raise R.RandoError(f"personal skills: {'|'.join(PERSONAL_MODES)}")
    if o["slots"] not in SLOT_MODES:
        raise R.RandoError(f"skill slots: {'|'.join(SLOT_MODES)}")
    return o


def opts_text(o: dict) -> str:
    return f"personal={o['personal']} slots={o['slots']}"


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


def load_skill_rows() -> list[dict]:
    """The Skill rows from the user's own RomFS (read only, through tools/mods like gamedata.py)."""
    import gamedata as GD
    why = GD.available()
    if why:
        raise R.RandoError(f"the game's tables are not available: {why}")
    return GD._load("Skill")


# ------------------------------------------------------------------ the skill facts the plan needs
class SkillFacts:
    """Families of skills, read from the rows (no hand-made list except KEEP_PERSONAL and the lock skill)."""

    def __init__(self, facts: R.Facts, skill_rows: list[dict]):
        self.facts = facts
        self.rows = {s["label"]: s for s in skill_rows}
        self.lock = facts.rules["lock_skill"]
        f2 = lambda s: R.ival(s.get("flags_2", 0))  # noqa: E731
        self.personal_family = {lab for lab, s in self.rows.items() if f2(s) & F2_PERSONAL and lab != NONE}
        self.enemy_only = {lab for lab, s in self.rows.items()
                           if f2(s) & F2_NOT_PLAYER and not f2(s) & F2_PERSONAL}
        self.dlc_only = {lab for lab, s in self.rows.items()
                         if R.ival(s.get("kind", 0)) == KIND_DLC and not f2(s) & F2_PERSONAL
                         and R.ival(s.get("price", 0)) == 0}
        self.song = {lab for lab, s in self.rows.items() if R.ival(s.get("kind", 0)) == KIND_SONG}
        # skills normal player classes teach (not excluded, not enemy-only classes: drops DLC classes, Corrin's
        # lines, the Songstress, Villager), minus anything enemy-only / DLC / personal / the song skill
        taught = []
        for j in facts.job_list:
            if facts.excluded_job(j["label"]):
                continue
            for i in range(1, 5):
                s = j.get(f"skill.{i}", NONE)
                if s and s != NONE and s not in taught:
                    taught.append(s)
        self.banned_slot = self.enemy_only | self.dlc_only | self.personal_family | self.song | {NONE}
        self.slot_pool = [s for s in taught if s in self.rows and s not in self.banned_slot and s != self.lock]
        # personal pool: the personal family as held by player-army people who are not downloadable / enemy-only
        # (children's are allowed: a row of the right family that the game gives a player unit)
        bad = {"SPID_ダウンロード", "SPID_敵専用"}
        held = []
        for p in facts.persons:
            s = p.get("personal_skill.normal", NONE)
            if (p.get("belong") == facts.rules["player_army"] and not (R.flags(p["flags"]) & bad)
                    and s in self.personal_family and s not in held):
                held.append(s)
        self.personal_pool = [s for s in held if s not in KEEP_PERSONAL]

    def name(self, lab: str) -> str:
        s = self.rows.get(lab)
        return (self.facts.names.get(s.get("mseid_name", "")) if s else None) or lab

    def line(self, jid: str, job_low: str) -> list[str]:
        """The class line's taught skills by place: [base lv1, base lv10, promoted lv5, promoted lv15]. For a base
        class the promoted half is empty (the class it will promote into is the player's choice)."""
        J = self.facts.jobs
        j = J.get(jid)
        if not j:
            return [NONE] * 4
        if self.facts.promoted(j):
            b = J.get(job_low)
            base = [b.get("skill.1", NONE), b.get("skill.2", NONE)] if b and not self.facts.promoted(b) else [NONE, NONE]
            return base + [j.get("skill.1", NONE), j.get("skill.2", NONE)]
        return [j.get("skill.1", NONE), j.get("skill.2", NONE), NONE, NONE]

    def old_place(self, p: dict, skill: str) -> int | None:
        """Where the person's ORIGINAL class line teaches this slot skill (0/1 base class, 2/3 promoted class),
        or None when it does not (then the slot is not tied to the class). For a promoted class the base half is
        looked up in Person.job_low first, then in every class that promotes into it (the table's job_low does
        not always name the class the person's skills came from: Gunter's do not match it)."""
        J = self.facts.jobs
        j = J.get(p["job"])
        if not j or skill in (NONE, ""):
            return None
        if not self.facts.promoted(j):
            for k in (1, 2):
                if j.get(f"skill.{k}") == skill:
                    return k - 1
            return None
        for k in (1, 2):
            if j.get(f"skill.{k}") == skill:
                return k + 1
        bases = [p.get("job_low")] + [b["label"] for b in self.facts.job_list
                                      if p["job"] in (b.get("promotion.1"), b.get("promotion.2"))]
        for bl in bases:
            b = J.get(bl)
            if b and not self.facts.promoted(b):
                for k in (1, 2):
                    if b.get(f"skill.{k}") == skill:
                        return k - 1
        return None


def kept_row(facts: R.Facts, p: dict) -> str | None:
    """Rows this track never edits: Corrin (the avatar) and the singer (a class with the sing/dance command)."""
    r = facts.rules
    if r["keep_class_person_flags"][0] in R.flags(p["flags"]):
        return "Corrin (the avatar)"
    j = facts.jobs.get(p["job"])
    if j and set(r["keep_class_job_flags"]) & R.flags(j["flags"]):
        return "the singer"
    return None


def _slots(p: dict) -> list[str]:
    return [p.get(f"skill.{i}", NONE) or NONE for i in range(1, SLOTS + 1)]


# ------------------------------------------------------------------ the plan
def plan_skills(tables: R.Facts, rng, opts: dict | None = None) -> tuple[list[dict], list[str]]:
    facts = tables
    o = check_opts(opts)
    if o["personal"] == "keep" and o["slots"] == "keep":
        return [], []
    rows = (opts or {}).get("skill_rows") or getattr(facts, "skills", None)
    if rows is None:
        rows = load_skill_rows()
    sf = SkillFacts(facts, rows)
    base_plan = (opts or {}).get("base_plan")
    bp = {e["pid"]: e for e in base_plan["persons"]} if base_plan else {}
    key = track_key(rng)
    text = opts_text(o)
    people = [p for p in facts.persons if facts.in_scope(p)]
    edits: list[dict] = []
    lines = [f"Skills track ({TOOL}): {text}"]

    def add(p, cell, old, new):
        if new != old:
            edits.append({"table": "Person", "index": R.ival(p["index"]), "label": p["label"], "cell": cell,
                          "old": old, "new": new})

    # 1. personal skills
    movable = [p for p in people if not kept_row(facts, p)
               and p.get("personal_skill.normal", NONE) not in KEEP_PERSONAL
               and p.get("personal_skill.normal", NONE) in sf.personal_family]
    new_personal: dict[str, str] = {}
    if o["personal"] == "shuffle":
        deck = [p["personal_skill.normal"] for p in movable]
        stream(key, "personal-shuffle", text, "all").shuffle(deck)
        new_personal = {p["label"]: s for p, s in zip(movable, deck)}
    elif o["personal"] == "random":
        r = stream(key, "personal-random", text, "all")
        left = list(sf.personal_pool)
        for p in movable:              # Person index order: one draw each, no two people the same
            pick = r.choice(left)
            left.remove(pick)
            new_personal[p["label"]] = pick
    for p in movable:
        new = new_personal.get(p["label"])
        if new is None:
            continue
        for c in PERSONAL_CELLS:
            add(p, c, p.get(c, NONE), new)
        old = p["personal_skill.normal"]
        if new != old:
            lines.append(f"{facts.pname(p)} [{p['label']}] personal skill: {sf.name(old)} -> {sf.name(new)}")

    # 2. slot skills
    slot_res: dict[str, tuple[list[str], list[str]]] = {}
    if o["slots"] != "keep":
        for p in people:
            if kept_row(facts, p):
                continue
            pid = p["label"]
            old = _slots(p)
            new = list(old)
            notes = []
            if o["slots"] == "class":
                e = bp.get(pid)
                nj, nl = (e["job"], e.get("job_low", p["job_low"])) if e else (p["job"], p["job_low"])
                if nj != p["job"]:
                    nline = sf.line(nj, nl)
                    r = stream(key, "slots-class", text, pid)
                    tied = {i: sf.old_place(p, s) for i, s in enumerate(old) if s not in (NONE, sf.lock)}
                    tied = {i: k for i, k in tied.items() if k is not None}
                    for i in tied:
                        new[i] = NONE
                    late = []
                    for i, k in sorted(tied.items()):        # first every slot whose new place has a skill
                        want = nline[k]
                        if want == NONE or want in new or want in sf.banned_slot:
                            late.append(i)
                        else:
                            new[i] = want
                    for i in late:
                        # the new line has nothing at that place (a base class's promoted half) or it repeats:
                        # another skill of the new line not yet held, else one from the class pool
                        spare = [x for x in nline if x != NONE and x not in new and x not in sf.banned_slot]
                        new[i] = r.choice(spare or [x for x in sf.slot_pool if x not in new])
                        notes.append(f"slot {i + 1}: {sf.name(old[i])} has no place in the new class line; "
                                     f"got {sf.name(new[i])}")
            else:  # random
                r = stream(key, "slots-random", text, pid)
                for i, s in enumerate(old):
                    if s == NONE or s == sf.lock:
                        continue
                    new[i] = NONE
                for i, s in enumerate(old):
                    if s == NONE or s == sf.lock:
                        continue
                    new[i] = r.choice([x for x in sf.slot_pool if x not in new])
            for i in range(SLOTS):
                add(p, f"skill.{i + 1}", old[i], new[i])
            slot_res[pid] = (old, new)
            if new != old:
                lines.append(f"{facts.pname(p)} [{pid}] skills: {', '.join(sf.name(x) for x in old if x != NONE)}"
                             f"  ->  {', '.join(sf.name(x) for x in new if x != NONE)}")
                lines += [f"    ({n})" for n in notes]

    # 3. route-variant (HANDOVER) rows (round 61, build/r60/screens/plans/SKILLS_VARIANTS.md): a route-variant join
    #    (Revelation's Elise, Arthur, Effie...) is created from its HANDOVER row and copies that row's slot skills,
    #    so the row follows its main person: the same old -> new map for the skills both rows hold, and for a skill
    #    only the route row holds the main rows' own rule (class: the class the join gets; random: a fresh draw)
    edits += _variant_edits(facts, sf, o, key, text, bp, new_personal, slot_res, lines)
    if len(lines) == 1:
        lines.append("no skill changed")
    return edits, lines


def variant_rows(facts: R.Facts) -> list[tuple[dict, dict]]:
    """(route-variant row, its main row) for every HANDOVER row of a person this track may edit, in file order."""
    out = []
    for h in getattr(facts, "handover", None) or []:
        main = (getattr(facts, "variant_of", None) or {}).get(h["label"])
        p = facts.by_pid.get(main) if main else None
        if p is None or not facts.in_scope(p) or kept_row(facts, p):
            continue
        out.append((h, p))
    return out


def join_class(facts: R.Facts, bp: dict, h: dict, p: dict) -> tuple[str, str]:
    """(class, job_low) a unit created from route row h gets: slice 1's make_plan step 5 rule (the new class in the
    route row's tier, else the plan's job_low), else the route row's own class."""
    e = bp.get(p["label"])
    if e and e["job"] != p["job"]:
        want = R._variant_class(facts, e, h)
        if want and want == e["job"]:
            return want, e.get("job_low", h.get("job_low", ""))
        if want:
            return want, h.get("job_low", "")
    return h["job"], h.get("job_low", "")


def _variant_edits(facts, sf, o, key, text, bp, new_personal, slot_res, lines) -> list[dict]:
    out: list[dict] = []
    for h, p in variant_rows(facts):
        hl, pid = h["label"], p["label"]
        cells = []
        # personal skill: the route row follows the main row when both held the same one
        newp = new_personal.get(pid)
        if newp is not None and newp != p.get("personal_skill.normal"):
            for c in PERSONAL_CELLS:
                if h.get(c, NONE) == p.get(c, NONE):
                    cells.append((c, h.get(c, NONE), newp))
        notes = []
        hold = _slots(h)
        hnew = list(hold)
        if o["slots"] != "keep" and pid in slot_res:
            old, new = slot_res[pid]
            m = {old[i]: new[i] for i in range(SLOTS) if old[i] not in (NONE, sf.lock) and new[i] != old[i]}
            own = [i for i, s in enumerate(hold) if s not in (NONE, sf.lock) and s not in old]
            for i, s in enumerate(hold):
                if s in m:
                    hnew[i] = m[s]
            redo = []
            if o["slots"] == "class":
                nj, nl = join_class(facts, bp, h, p)
                if nj != h["job"]:
                    nline = sf.line(nj, nl)
                    tied = {i: sf.old_place(h, hold[i]) for i in own}
                    tied = {i: k for i, k in tied.items() if k is not None}
                    for i in tied:
                        hnew[i] = NONE
                    for i, k in sorted(tied.items()):
                        want = nline[k]
                        if want == NONE or want in hnew or want in sf.banned_slot:
                            redo.append(i)
                        else:
                            hnew[i] = want
                    r = stream(key, "slots-class-variant", text, hl)
                    pool = lambda: [x for x in nline if x != NONE and x not in hnew and x not in sf.banned_slot] \
                        or [x for x in sf.slot_pool if x not in hnew]  # noqa: E731
                else:
                    r, pool = None, None
            else:  # random: the route row's own skills draw again
                r = stream(key, "slots-random-variant", text, hl)
                for i in own:
                    hnew[i] = NONE
                redo = list(own)
                pool = lambda: [x for x in sf.slot_pool if x not in hnew]  # noqa: E731
            # a kept own skill that the main map now also gives would repeat: that own slot draws again
            for i in own:
                if i not in redo and hnew[i] != NONE and hnew.count(hnew[i]) > 1:
                    if r is None:
                        r = stream(key, "slots-variant-repeat", text, hl)
                        pool = lambda: [x for x in sf.slot_pool if x not in hnew]  # noqa: E731
                    hnew[i] = NONE
                    redo.append(i)
            for i in sorted(redo):
                hnew[i] = r.choice(pool())
                notes.append(f"slot {i + 1}: {sf.name(hold[i])} (this route row only) -> {sf.name(hnew[i])}")
            for i in range(SLOTS):
                if hnew[i] != hold[i]:
                    cells.append((f"skill.{i + 1}", hold[i], hnew[i]))
        for c, a, b in cells:
            out.append({"table": "Person", "file": h["file"], "index": R.ival(h["index"]), "label": hl,
                        "cell": c, "old": a, "new": b, "main": pid})
        if cells:
            ch = h["file"].replace("\\", "/").rsplit("/", 1)[-1].split(".", 1)[0]
            bits = []
            if hnew != hold:
                bits.append(f"skills {', '.join(sf.name(x) for x in hold if x != NONE)}  ->  "
                            f"{', '.join(sf.name(x) for x in hnew if x != NONE)}")
            if any(c in PERSONAL_CELLS for c, _a, _b in cells):
                bits.append(f"personal skill -> {sf.name(newp)}")
            lines.append(f"  route row {ch} [{hl}] of {facts.pname(p)}: " + "; ".join(bits))
            lines += [f"    ({n})" for n in notes]
    return out


# ------------------------------------------------------------------ guards
def run_guards(tables: R.Facts, edits: list[dict], opts: dict | None = None) -> dict:
    """{guard: {"ok": bool, "detail": [...]}} over a list of this track's edits."""
    facts = tables
    rows = (opts or {}).get("skill_rows") or getattr(facts, "skills", None)
    sf = SkillFacts(facts, rows if rows is not None else load_skill_rows())
    out = {}

    def g(name, bad):
        out[name] = {"ok": not bad, "detail": bad[:20]}

    after = {p["label"]: dict(p) for p in facts.persons}
    bad_cells = []
    v_edits = [ed for ed in edits if "file" in ed]
    edits = [ed for ed in edits if "file" not in ed]
    for ed in edits:
        p = facts.by_pid.get(ed["label"])
        ok_cell = ed["cell"] in PERSONAL_CELLS or ed["cell"] in {f"skill.{i}" for i in range(1, SLOTS + 1)}
        if p is None or ed["table"] != "Person" or not ok_cell or not facts.in_scope(p) \
                or R.ival(p["index"]) != ed["index"] or p.get(ed["cell"]) != ed["old"]:
            bad_cells.append(f"{ed['label']} {ed['cell']}")
            continue
        after[ed["label"]][ed["cell"]] = ed["new"]
    g("only the 49 people's skill cells", bad_cells)
    illegal, fam, counts, kept, lock, keep_ps, rep = [], [], [], [], [], [], []
    for p in facts.persons:
        if not facts.in_scope(p):
            continue
        a, pid = after[p["label"]], p["label"]
        old, new = _slots(p), _slots(a)
        for c in PERSONAL_CELLS + tuple(f"skill.{i}" for i in range(1, SLOTS + 1)):
            if a.get(c, NONE) not in sf.rows:
                illegal.append(f"{pid} {c} {a.get(c)}")
        for i in range(SLOTS):
            if new[i] != old[i] and new[i] in sf.banned_slot:
                fam.append(f"{pid} skill.{i + 1} {new[i]} (enemy-only, DLC-only, personal or song skill)")
        if any(a.get(c) != p.get(c) for c in PERSONAL_CELLS):
            if any(a.get(c) not in sf.personal_family for c in PERSONAL_CELLS):
                fam.append(f"{pid} personal skill not of the personal family")
            if len({a.get(c) for c in PERSONAL_CELLS}) != 1:
                fam.append(f"{pid} personal skill differs between difficulties")
        if [s != NONE for s in old] != [s != NONE for s in new]:
            counts.append(pid)
        if kept_row(facts, p) and a != p:
            kept.append(f"{pid} ({kept_row(facts, p)})")
        if any(s == sf.lock and new[i] != sf.lock for i, s in enumerate(old)):
            lock.append(pid)
        if p.get("personal_skill.normal") in KEEP_PERSONAL and a.get("personal_skill.normal") != p.get("personal_skill.normal"):
            keep_ps.append(pid)
        if a.get("personal_skill.normal") in KEEP_PERSONAL and a.get("personal_skill.normal") != p.get("personal_skill.normal"):
            keep_ps.append(f"{pid} received a kept skill")
        filled = [s for s in new if s != NONE]
        if len(set(filled)) != len(filled):
            rep.append(pid)
    g("only legal skill ids", illegal)
    g("each cell keeps its family (slot: class-taught; personal: personal family)", fam)
    g("filled slots unchanged in number and place", counts)
    g("Corrin and the singer untouched", kept)
    g("lock-opening skill never taken away (door-opener guard)", lock)
    g("story/asset/command personal skills kept", keep_ps)
    g("no skill twice in one person's slots", rep)
    new_ps = [after[p["label"]]["personal_skill.normal"] for p in facts.persons if facts.in_scope(p)]
    old_ps = [p["personal_skill.normal"] for p in facts.persons if facts.in_scope(p)]
    dup = sorted({s for s in new_ps if new_ps.count(s) > 1 and old_ps.count(s) < new_ps.count(s)})
    g("no personal skill given to two people", dup)
    _variant_guards(facts, sf, after, v_edits, g)
    return out


def _variant_guards(facts: R.Facts, sf: SkillFacts, after: dict, v_edits: list[dict], g) -> None:
    """Round 61: the route-variant (HANDOVER) rows' cells. Same rules as the main rows, and every skill a route row
    shares with its main row becomes what the main row's skill became."""
    rows = {(h["file"], h["label"]): h for h in getattr(facts, "handover", None) or []}
    ok_rows = {(h["file"], h["label"]): p for h, p in variant_rows(facts)}
    hafter = {k: dict(h) for k, h in rows.items()}
    bad = []
    for ed in v_edits:
        k = (ed["file"], ed["label"])
        h = rows.get(k)
        ok_cell = ed["cell"] in PERSONAL_CELLS or ed["cell"] in {f"skill.{i}" for i in range(1, SLOTS + 1)}
        if h is None or k not in ok_rows or ed["table"] != "Person" or not ok_cell                 or R.ival(h["index"]) != ed["index"] or h.get(ed["cell"]) != ed["old"]                 or ok_rows[k]["label"] != ed.get("main"):
            bad.append(f"{ed['file']} {ed['label']} {ed['cell']}")
            continue
        hafter[k][ed["cell"]] = ed["new"]
    g("route-variant rows: only the skill cells of the 49 people's HANDOVER rows", bad)
    illegal, fam, counts, lock, rep, follow = [], [], [], [], [], []
    for k, p in ok_rows.items():
        h, a = rows[k], hafter[k]
        old, new = _slots(h), _slots(a)
        tag = f"{k[0].rsplit('/', 1)[-1]} {k[1]}"
        for c in PERSONAL_CELLS + tuple(f"skill.{i}" for i in range(1, SLOTS + 1)):
            if a.get(c, NONE) not in sf.rows:
                illegal.append(f"{tag} {c} {a.get(c)}")
        for i in range(SLOTS):
            if new[i] != old[i] and new[i] in sf.banned_slot:
                fam.append(f"{tag} skill.{i + 1} {new[i]}")
        if [s != NONE for s in old] != [s != NONE for s in new]:
            counts.append(tag)
        if any(s == sf.lock and new[i] != sf.lock for i, s in enumerate(old)):
            lock.append(tag)
        filled = [s for s in new if s != NONE]
        if len(set(filled)) != len(filled):
            rep.append(tag)
        pa = after[p["label"]]
        pm = {o: n for o, n in zip(_slots(p), _slots(pa)) if o != NONE}
        for i, s in enumerate(old):
            if s in pm and new[i] != pm[s]:
                follow.append(f"{tag} skill.{i + 1}: {s} -> {new[i]}, main row {p['label']} -> {pm[s]}")
        for c in PERSONAL_CELLS:
            if h.get(c) == p.get(c) and a.get(c) != pa.get(c):
                follow.append(f"{tag} {c}: {a.get(c)}, main row {pa.get(c)}")
    g("route-variant rows: only legal skill ids", illegal)
    g("route-variant rows: slot skills stay class-taught", fam)
    g("route-variant rows: filled slots unchanged in number and place", counts)
    g("route-variant rows: lock-opening skill never taken away", lock)
    g("route-variant rows: no skill twice in one row's slots", rep)
    g("route-variant rows follow their main row (shared skills and personal skill)", follow)


def apply_edits(plan: dict, edits: list[dict], opts: dict | None = None) -> dict:
    """A copy of a slice-1 plan that records this track (plan["tracks"]["skills"]); the edits themselves are
    written by person_csv_with_edits (randolib.render writes only slice 1's Person columns)."""
    if not edits:
        return plan
    out = copy.deepcopy(plan)
    out.setdefault("tracks", {})[TRACK] = {"tool": TOOL, "opts": check_opts(opts), "edits": edits}
    return out


def person_csv_with_edits(facts: R.Facts, csv_bytes: bytes, edits: list[dict]) -> bytes:
    """Slice 1's tables/Person.csv with this track's cells added (new columns; a row slice 1 did not write gets
    its slice-1 columns from the original rows, i.e. unchanged)."""
    import csv
    import io
    txt = csv_bytes.decode("utf-8").lstrip("﻿")
    rdr = list(csv.reader(io.StringIO(txt)))
    head, body = rdr[0], rdr[1:]
    cells = [f"skill.{i}" for i in range(1, SLOTS + 1)] + list(PERSONAL_CELLS)
    by = {}
    for ed in edits:
        if "file" not in ed:                  # route-variant rows go to tables/PersonChapter.csv (variant_cells)
            by.setdefault(ed["label"], {})[ed["cell"]] = ed["new"]
    if not by:
        return csv_bytes
    nhead = head + cells
    out_rows = []
    seen = set()
    for row in body:
        pid = row[1]
        p = facts.by_pid[pid]
        seen.add(pid)
        out_rows.append(row + [by.get(pid, {}).get(c, p.get(c, "")) for c in cells])
    for p in facts.persons:
        pid = p["label"]
        if pid in by and pid not in seen:
            out_rows.append([p["index"], pid] + [p.get(c, "") for c in head[2:]]
                            + [by[pid].get(c, p.get(c, "")) for c in cells])
    out_rows.sort(key=lambda r: int(r[0]))
    return R._csv([nhead] + out_rows)


def variant_cells(edits: list[dict]) -> dict[tuple, dict]:
    """The route-variant rows' cells {(file, index): {cell: new}} for tables/PersonChapter.csv."""
    out: dict[tuple, dict] = {}
    for ed in edits:
        if "file" in ed:
            out.setdefault((ed["file"], R.ival(ed["index"])), {})[ed["cell"]] = ed["new"]
    return out


# ------------------------------------------------------------------ CLI: slice 1 + this track only
def make_folder(seed: str, opts: dict, out_top: str, facts=None) -> tuple[str, dict, list[dict]]:
    import gamedata as GD
    facts = facts or GD.load_facts()
    facts.skills = load_skill_rows()
    plan = R.make_plan(facts, seed, {})
    o = dict(check_opts(opts), base_plan=plan)
    edits, lines = plan_skills(facts, seed, o)
    guards = run_guards(facts, edits)
    files = R.render(facts, plan)
    files["tables/Person.csv"] = person_csv_with_edits(facts, files["tables/Person.csv"], edits)
    vc = variant_cells(edits)
    if vc:
        import tracks as T
        files["tables/PersonChapter.csv"] = T._person_chapter_csv([], vc, None)
    meta = json.loads(files["mod.json"].decode("utf-8"))
    meta["description"] += f" + skills track ({opts_text(check_opts(opts))}); robot test folder."
    meta["randomizer"]["tracks"] = {TRACK: check_opts(opts)}
    files["mod.json"] = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    sp = lines + ["", "Skills guards:"] + [f"  {'PASS' if v['ok'] else 'FAIL'} {k}" + ("" if v["ok"] else f" {v['detail']}")
                                           for k, v in guards.items()]
    files["spoiler.txt"] += ("\n" + "\n".join(sp) + "\n").encode("utf-8")
    files["skills.json"] = (json.dumps({"tool": TOOL, "seed": seed, "opts": check_opts(opts), "edits": edits,
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
    p.add_argument("--personal", choices=PERSONAL_MODES, default="shuffle")
    p.add_argument("--slots", choices=SLOT_MODES, default="class")
    p.add_argument("--out", required=True)
    p = sub.add_parser("robot")
    p.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "robot":
            return robot_main(a.args)
        why = _forbidden(a.out)
        if why:
            raise R.RandoError(f"refused: {why}")
        folder, guards, edits = make_folder(a.seed, {"personal": a.personal, "slots": a.slots}, os.path.abspath(a.out))
        print(f"made {folder}: {len(edits)} skill cells")
        for k, v in guards.items():
            print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
        return 0 if all(v["ok"] for v in guards.values()) else 2
    except R.RandoError as e:
        print(f"ERROR: {e}")
        return 1


# ------------------------------------------------------------------ robot check (one headless job)
def robot_main(args: list[str]) -> int:
    """robot JOB MODFOLDER RUN:SAVE:ROUTE:LAST:READS:ZAKSUB:EXPECT ...
    ZAKSUB  a Zakuro data folder below build/rando49/skills/ whose mods/ is copied into the run's data folder
            (filled by tools/mods/mods.py install), or "none"; EXPECT  mod (MODFOLDER's plan.json + skills.json)
            or vanilla (the original tables). Runs go one after another in this one process.

    Like tools/randomizer/robot_check.py, but every server lives below build/rando49/skills/server/ and it also
    reads each Person row's five skill slots (+0x68) and personal skills (+0x74), and each unit's equipped
    skills (Unit +0xFE, s16[5]; docs/SKILLS.md). Reads only."""
    import struct
    import shutil
    import time
    sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
    import headless as hl
    import server as sv
    import robot_check as RC
    import gamedata as GD
    top = os.path.join(ROOT, "build", "rando49", "skills")
    if os.path.exists(os.path.join(ROOT, "build", "STOP_ROUND")):
        print("build/STOP_ROUND exists: not started")
        return 3
    job, mod = args[:2]
    facts = GD.load_facts(names=False)
    sk_ix = {s["label"]: R.ival(s["index"]) for s in load_skill_rows()}
    jix = {lab: R.ival(j["index"]) for lab, j in facts.jobs.items()}
    names = {}

    def exp_of(p, jobs):
        return {"job": jix[jobs[0]], "job_low": jix[jobs[1]],
                "skills": [sk_ix[p[f"skill.{i}"]] for i in range(1, SLOTS + 1)],
                "personal": [sk_ix[p[c]] for c in PERSONAL_CELLS]}

    exps = {"vanilla": {}, "mod": {}}
    for p in facts.persons:
        if facts.in_scope(p):
            names[R.ival(p["index"])] = p["label"]
            exps["vanilla"][R.ival(p["index"])] = exp_of(p, (p["job"], p["job_low"]))
    plan = json.load(open(os.path.join(mod, "plan.json"), encoding="utf-8"))
    skj = json.load(open(os.path.join(mod, "skills.json"), encoding="utf-8"))
    rows = {p["label"]: dict(p) for p in facts.persons}
    for ed in skj["edits"]:
        if "file" not in ed:
            rows[ed["label"]][ed["cell"]] = ed["new"]
    for e in plan["persons"]:
        exps["mod"][e["index"]] = exp_of(rows[e["pid"]], (e["job"], e["job_low"]))
    res = {"job": job, "mod": mod, "runs": []}
    os.makedirs(os.path.join(top, "robot"), exist_ok=True)
    path = os.path.join(top, "robot", f"{job}.json")
    for spec in args[2:]:
        if os.path.exists(os.path.join(ROOT, "build", "STOP_ROUND")):
            res["stopped"] = "build/STOP_ROUND appeared"
            break
        name, save, route, last, reads, zsub, expect = spec.split(":")[:7]
        zakdir = "none" if zsub == "none" else os.path.join(top, zsub)
        exp = exps[expect]
        reads = [int(x) for x in reads.split("/") if x]
        rin = json.load(open(os.path.join(ROOT, "config", "harness", "routes.json"), encoding="utf-8"))["routes"][route]["input"]
        inp = ",".join(x for x in rin.split(",") if x and int(x.split(":")[0]) <= int(last))
        orig = hl.lay_save

        def lay(zip_path, data_dir):
            names = orig(zip_path, data_dir)
            assert hl.below(os.path.abspath(data_dir), top), data_dir
            if zakdir != "none" and os.path.isdir(os.path.join(zakdir, "mods")):
                shutil.copytree(os.path.join(zakdir, "mods"), os.path.join(data_dir, "mods"), dirs_exist_ok=True)
            return names

        hl.lay_save = lay
        run = {"run": name, "save": save, "route": route, "last_press": int(last), "reads": [], "zakdir": zsub,
               "expect": expect}
        t0 = time.time()
        try:
            with sv.Server(f"{job}-{name}", save=save, root=os.path.join(top, "server")) as s:
                run["mods_in_data"] = sorted(os.path.relpath(os.path.join(r, f), s.data_dir).replace("\\", "/")
                                             for r, _d, fs in os.walk(os.path.join(s.data_dir, "mods")) for f in fs)
                s.inputs_set(inp)
                rd = RC.Reader(s)
                shots = os.path.join(top, "robot", "shots", f"{job}-{name}")
                os.makedirs(shots, exist_ok=True)
                for f in sorted(set(reads)):
                    s.step_to(f)
                    s.shot(os.path.join(shots, f"f{f:06d}.png"), scale=1)
                    entry = {"frame": f}
                    try:
                        us = rd.units()
                        for u in us:
                            ub = s.peek1(int(u["unit"], 16), 0x110)
                            u["equip_skills"] = list(struct.unpack_from("<5h", ub, 0xFE))
                        entry["units"] = us
                        if us:
                            p0 = rd.person(int(us[0]["person"], 16))
                            rec0 = int(us[0]["person"], 16) - p0["index"] * RC.PREC
                            bad, rowsout = [], []
                            for ix, w in sorted(exp.items()):
                                b = s.peek1(rec0 + ix * RC.PREC, RC.PREC)
                                got = {"job": struct.unpack_from("<H", b, 0x2C)[0],
                                       "job_low": struct.unpack_from("<H", b, 0x2E)[0],
                                       "skills": list(struct.unpack_from("<5h", b, 0x68)),
                                       "personal": list(struct.unpack_from("<3h", b, 0x74))}
                                diff = [k for k in w if got[k] != w[k]]
                                if struct.unpack_from("<H", b, 0x24)[0] != ix:
                                    diff.append("index")
                                rowsout.append({"index": ix, "pid": names[ix], "diff": diff, "mem": got})
                                if diff:
                                    bad.append(f"{names[ix]}: {', '.join(diff)}")
                            entry["persons"] = {"record0": f"{rec0:08x}", "checked": len(rowsout),
                                                "mismatches": bad, "rows": rowsout}
                            ub_bad = []
                            for u in us:
                                if u["force"] != 0:
                                    continue
                                ix = u["pid_number"]
                                # the game keeps a unit's equipped skills sorted by skill number (seen in the
                                # unmodded run: Gunter's row has Elbow Room, Shelter; his unit Shelter, Elbow Room)
                                if ix in exp and sorted(u["equip_skills"]) != sorted(exp[ix]["skills"]):
                                    ub_bad.append(f"{u['pid']}: unit {u['equip_skills']} vs row {exp[ix]['skills']}")
                            entry["unit_skill_mismatches"] = ub_bad
                    except Exception as e:  # noqa: BLE001
                        entry["error"] = repr(e)
                    run["reads"].append(entry)
                run["digest"] = s.state_digest()
                run["frame"] = s.frame
        finally:
            hl.lay_save = orig
        run["seconds"] = round(time.time() - t0, 1)
        res["runs"].append(run)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, ensure_ascii=False)
    for r in res["runs"]:
        print(r["run"], "frame", r.get("frame"), "memory", r.get("digest", {}).get("memory", "")[:16],
              "mods", len(r.get("mods_in_data", [])), "seconds", r.get("seconds"))
        for e in r["reads"]:
            pc = e.get("persons") or {}
            print("  read", e["frame"], "units", len(e.get("units", [])), "persons", pc.get("checked"),
                  "mismatches", len(pc.get("mismatches", [])), "unit-skill mismatches",
                  len(e.get("unit_skill_mismatches", [])), e.get("error", ""))
    print("result:", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
