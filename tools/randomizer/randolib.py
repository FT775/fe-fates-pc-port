"""Fire Emblem Fates randomizer, slice 1 (F-041 #4-5): each playable person's class, growth rates and join
(personal base) stats, written as ordinary table edits (Person rows, and the item cells of that person's map
placements when a carried weapon no longer fits the new class).

Our own code. Public randomizers were read for facts only (which fields matter, which guards they keep); no code
was copied. Pure functions on plain rows (dicts of CSV cells, exactly as tools/tables/dump.py writes them), so the
tests can feed made-up tables. tools/randomizer/gamedata.py loads the real ones from the user's own RomFS.

Nothing here touches the hidden dice: the only random numbers are Python's own, seeded from the seed text and
the switches, one stream per person (so one person's draw never shifts another's).
"""
from __future__ import annotations

import hashlib
import json
import os
import random

STATS = ("hp", "str", "mag", "skl", "spd", "lck", "def", "res")
KINDS = ("sword", "lance", "axe", "dagger", "bow", "tome", "staff", "stone")
SLICE = 1
TOOL_VERSION = "rando-slice1-v1"
DEFAULT_SWITCHES = {"classes": True, "growths": True, "join_stats": True, "trees": "own",
                    "keep_royals": True, "children": False}
GROWTH_STEP = 5
RANKS = (1, 21, 51, 96, 161, 251)   # weapon rank thresholds E..S (WeaponLevel; the tier of a weapon)
GROWTH_CAP = 80        # one stat's personal growth after shuffling (class growth is added by the game)
GROWTH_HP_FLOOR = 10

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES_PATH = os.path.join(ROOT, "config", "randomizer", "rules.json")


class RandoError(Exception):
    """A problem the user can fix (bad seed, a switch that is not built yet); printed without a traceback."""


def load_rules(path: str = RULES_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------ small helpers
def flags(cell: str) -> set[str]:
    return {f for f in (cell or "").split("|") if f}


def ival(cell) -> int:
    return int(str(cell).strip() or 0)


def check_seed(seed: str) -> str:
    s = str(seed).strip()
    if not s or len(s) > 40 or not all(c.isalnum() or c in "-_" for c in s) or not s[0].isalnum():
        raise RandoError(f"seed {seed!r}: use 1-40 letters, digits, '-' or '_' (starting with a letter or digit)")
    return s


def switches_text(sw: dict) -> str:
    on = lambda b: "on" if b else "off"  # noqa: E731
    return (f"classes={on(sw['classes'])} growths={on(sw['growths'])} join-stats={on(sw['join_stats'])} "
            f"trees={sw['trees']} keep-royals={on(sw['keep_royals'])} children={on(sw['children'])}")


def rng_for(seed: str, sw: dict, *parts: str) -> random.Random:
    """One random stream per (seed, switches, purpose, person): SHA-256 of the text, so the same inputs give the
    same numbers on every machine and Python version (random.Random(int) is stable)."""
    key = "\x1f".join([TOOL_VERSION, seed, switches_text(sw)] + list(parts))
    return random.Random(int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big"))


# ------------------------------------------------------------------ the game's facts, from the rows
class Facts:
    """Read-only view of the tables a slice-1 plan needs. persons: Person rows of the main file (list, index
    order); jobs: Job rows; items: Item rows; subkinds: ItemSubKind rows; dispos: DisposUnit rows (all files);
    names: label -> English text (optional, spoiler log only)."""

    def __init__(self, persons, jobs, items, subkinds, dispos, rules, names=None, handover=None):
        self.rules = rules
        self.persons = list(persons)
        self.jobs = {j["label"]: j for j in jobs}
        self.job_list = sorted(jobs, key=lambda j: ival(j["index"]))
        self.items = {i["label"]: i for i in items}
        self.item_list = sorted(items, key=lambda i: ival(i["index"]))
        self.sub_kind = {ival(s["index"]): ival(s["kind"]) for s in subkinds}
        self.sub_origin = {ival(s["index"]): ival(s["origin"]) for s in subkinds}
        self.dispos = list(dispos)
        self.names = names or {}
        self.by_pid = {p["label"]: p for p in self.persons}
        # route-variant rows (GameData/Person/{A,B,C}_HANDOVER, PersonChapter layout with "file"): a placement that
        # names one creates the unit from that row, and Unit::Handover then switches it to the main row
        # (replace_index) but keeps the unit's class (docs/rando/RECRUIT.md section 2). Optional: [] = none known.
        self.handover = [dict(h) for h in (handover or [])]
        by_ix = {ival(p["index"]): p["label"] for p in self.persons}
        self.variant_of = {h["label"]: by_ix[ival(h.get("replace_index", 0))] for h in self.handover
                           if ival(h.get("replace_index", 0)) and ival(h.get("replace_index", 0)) in by_ix}
        self.variant_row = {h["label"]: h for h in self.handover if h["label"] in self.variant_of}

    # -- persons
    def name(self, label: str) -> str:
        return self.names.get(label) or label

    def pname(self, p: dict) -> str:
        n = self.names.get(p.get("mpid_name", ""))
        if not n and self.rules["keep_class_person_flags"][0] in flags(p["flags"]):
            n = "Corrin (avatar, " + ("female" if self.female(p) else "male") + ")"
        return n or p["label"]

    def jname(self, jid: str) -> str:
        j = self.jobs.get(jid)
        return (self.names.get(j.get("mjid_name", "")) if j else None) or jid

    def iname(self, iid: str) -> str:
        i = self.items.get(iid)
        return (self.names.get(i.get("miid_name", "")) if i else None) or iid

    def is_child(self, p: dict) -> bool:
        return str(p.get("child_id", "65535")).strip() not in ("65535", "")

    def in_scope(self, p: dict) -> bool:
        """A playable person of the player's army: not a child, not a bond (logbook) unit, not a capture-only
        generic, not downloadable, not enemy-only, not the empty row 0."""
        r = self.rules
        if ival(p["index"]) == 0 or p.get("belong") != r["player_army"]:
            return False
        if flags(p["flags"]) & set(r["scope_exclude_person_flags"]):
            return False
        return not self.is_child(p)

    def female(self, p_or_j: dict) -> bool:
        return self.rules["female_flag"] in flags(p_or_j["flags"])

    def promoted(self, j: dict) -> bool:
        return self.rules["promoted_job_flag"] in flags(j["flags"])

    def wexp_max(self, j: dict) -> list[int]:
        return [ival(j[f"max_weapon_exp.{k}"]) for k in KINDS]

    def kept_reason(self, p: dict, sw: dict) -> str | None:
        """Why this person's class never changes, or None."""
        r = self.rules
        pf = flags(p["flags"])
        j = self.jobs.get(p["job"])
        if pf & set(r["keep_class_person_flags"]):
            return "lord / dragonstone holder (story-fixed class)"
        if j and flags(j["flags"]) & set(r["keep_class_job_flags"]):
            return "the singer (story-fixed class)"
        if sw["keep_royals"] and pf & set(r["royal_weapon_person_flags"]):
            return "royal with a personal legendary weapon (keep-royals on)"
        if j is None:
            return "class not found"
        if self.excluded_job(p["job"]):
            return "starts in a special class (" + self.excluded_job(p["job"]) + ")"
        return None

    def excluded_job(self, jid: str) -> str | None:
        r = self.rules
        for pre in r["exclude_job_prefixes"]:
            if jid.startswith(pre):
                return r["exclude_job_reasons"].get(pre, "excluded")
        j = self.jobs[jid]
        if r["enemy_only_job_flag"] in flags(j["flags"]):
            return "enemy-only class"
        if r["dragon_job_category"] in flags(j["category"]):
            return "the avatar's own class line"
        if flags(j["flags"]) & set(r["keep_class_job_flags"]):
            return "the singer's class"
        return None

    def legal_classes(self, p: dict, sw: dict, promoted: bool | None = None) -> list[str]:
        """Every class this person may be given: same gender row, same tier as the class they start in (or the
        tier asked for), a normal player class, beasts stay beasts and nobody else becomes one, and with
        trees=own only the same side's classes (Hoshido 1 / Nohr 2, Job.origin) as their starting class."""
        r = self.rules
        own = self.jobs[p["job"]]
        tier = self.promoted(own) if promoted is None else promoted
        beast = r["beast_person_flag"] in flags(p["flags"])
        out = []
        for j in self.job_list:
            jid = j["label"]
            if self.excluded_job(jid):
                continue
            if self.female(j) != self.female(p) or self.promoted(j) != tier:
                continue
            if (r["beast_job_category"] in flags(j["category"])) != beast:
                continue
            if sw["trees"] == "own" and ival(own["origin"]) in (1, 2) and ival(j["origin"]) != ival(own["origin"]):
                continue
            if not any(self.wexp_max(j)):
                continue
            out.append(jid)
        return out

    # -- items
    def item_kind(self, iid: str) -> int | None:
        """ItemKind 0..7 for a weapon, stone or staff; None for an item (kind 8), an unknown or an empty slot."""
        it = self.items.get(iid)
        if not it:
            return None
        k = self.sub_kind.get(ival(it["weapon_kind"]))
        return None if k is None or k == self.rules["item_kind_none"] else k

    def item_rank(self, iid: str) -> int:
        return ival(self.items[iid]["weapon_rank"])

    def base_usable(self, p: dict, iid: str) -> bool:
        """True when the ORIGINAL person in the ORIGINAL class could use iid with their starting weapon exp (a
        placement may also list items for higher levels; only these must stay usable from the start)."""
        k = self.item_kind(iid)
        if k is None:
            return False
        own = self.wexp_max(self.jobs[p["job"]])
        return own[k] > 0 and self.item_rank(iid) <= max(ival(p[f"weapon_exp.{KINDS[k]}"]), 1)

    def class_can_hold(self, jid: str, p: dict, iid: str, wexp: list[int], need_exp: bool = True) -> str | None:
        """None when the person in class jid with weapon exp wexp can use iid (need_exp False: the class may use
        it at all, rank aside from the starting exp); else the reason in words."""
        k = self.item_kind(iid)
        if k is None:
            return None
        j = self.jobs[jid]
        mx = self.wexp_max(j)
        if mx[k] <= 0:
            return f"{self.jname(jid)} cannot use {KINDS[k]}"
        rank = self.item_rank(iid)
        if rank > mx[k]:
            return f"rank {rank} is above {self.jname(jid)}'s {KINDS[k]} limit {mx[k]}"
        if need_exp and rank > max(wexp[k], 1):
            return f"rank {rank} is above the weapon exp {wexp[k]}"
        itf = flags(self.items[iid]["flags"])
        for f, cat in self.rules["class_only_item_flags"].items():
            if f in itf and cat not in flags(j["category"]):
                return f"{self.iname(iid)} is for one class line only"
        for f, g in self.rules["gender_item_flags"].items():
            if f in itf and (g == "female") != self.female(p):
                return f"{self.iname(iid)} is for one gender only"
        return None

    def replacement_items(self, kind: int, rank: int, origin: int) -> list[str]:
        """Ordinary shop weapons of that kind and exact rank (tier): bought for a price, no personal / class /
        gender / enemy / chapter-only / precious flags. The same side's style first (katana for Hoshido...)."""
        refuse = set(self.rules["replacement_refuse_item_flags"])
        out = []
        for it in self.item_list:
            iid = it["label"]
            if self.item_kind(iid) != kind or self.item_rank(iid) != rank or ival(it["buy_price"]) <= 0:
                continue
            itf = flags(it["flags"])
            if itf & refuse or any("専用" in f for f in itf):
                continue
            if str(it.get("legal_player_weapon", "1")).strip() != "1":
                continue
            out.append(iid)
        same = [i for i in out if self.sub_origin.get(ival(self.items[i]["weapon_kind"])) == origin]
        return same or out

    # -- routes
    def placements(self, pid: str) -> list[dict]:
        return [d for d in self.dispos if d.get("pid") == pid]

    def variant_placements(self, pid: str) -> list[tuple[dict, dict]]:
        """(placement, route-variant row) for every placement that names a route-variant row of this main pid."""
        if not self.variant_of:
            return []
        return [(d, self.variant_row[d["pid"]]) for d in self.dispos if self.variant_of.get(d.get("pid", "")) == pid]

    def chapter_of(self, d: dict) -> str:
        return d["file"].replace("\\", "/").rsplit("/", 1)[-1].split(".", 1)[0]

    def route_members(self) -> dict[str, list[str]]:
        """Per route letter, the people (in scope or kept) placed on the player's side (team 0) in that route's
        chapters or the shared opening chapters, in order of their first placement."""
        shared = set(self.rules["shared_chapters"])
        out = {}
        for letter in self.rules["routes"]:
            seen = []
            for d in sorted(self.dispos, key=lambda d: (self.chapter_of(d)[1:4], self.chapter_of(d), ival(d["index"]))):
                if str(d.get("team")) != "0" or d.get("pid") not in self.by_pid:
                    continue
                ch = self.chapter_of(d)
                base = ch[:4]
                if base in shared or (ch[0] == letter and ch[1:4].isdigit() and base not in shared):
                    if d["pid"] not in seen:
                        seen.append(d["pid"])
            out[letter] = seen
        return out


# ------------------------------------------------------------------ the plan
def _distribute(rng: random.Random, total: int, n: int, floors: list[int], caps: list[int],
                weights: list[float], step: int = 1) -> list[int]:
    """total points (in steps) over n slots, each between its floor and cap, by weight; deterministic for a given
    rng state. Points that fit nowhere are dropped (reported by the caller through the sum)."""
    vals = list(floors)
    left = max(0, total - sum(floors))
    while left >= step:
        room = [i for i in range(n) if vals[i] + step <= caps[i]]
        if not room:
            break
        w = [weights[i] for i in room]
        i = rng.choices(room, weights=w)[0]
        vals[i] += step
        left -= step
    return vals


def remap_wexp(rng: random.Random, old: list[int], old_max: list[int], new_max: list[int]) -> list[int]:
    """The person's weapon exp moved onto the new class's weapon kinds: the old usable kinds' exp, largest
    first, onto the new kinds in a random order; kinds beyond that start at 0 (the game raises a usable kind to
    rank E at creation); every value cut to the new class's limit."""
    olds = sorted((old[k] for k in range(8) if old_max[k] > 0 and old[k] > 0), reverse=True)
    if not olds:
        olds = sorted((v for v in old if v > 0), reverse=True)
    kinds = [k for k in range(8) if new_max[k] > 0]
    rng.shuffle(kinds)
    out = [0] * 8
    for n, k in enumerate(kinds):
        out[k] = min(olds[n] if n < len(olds) else 0, new_max[k])
    return out


def make_plan(facts: Facts, seed: str, sw: dict | None = None, classes: dict | None = None,
              carry: dict | None = None) -> dict:
    """The whole slice-1 plan: {"seed", "switches", "persons": [...], "dispos": {...}, "guards": {...}}.
    Children must be off here (tracks.py routes the switch to the children track). classes: optional
    {pid: class} (misc "assign evenly"): that person's class draw and role pass see only that one class; job_low,
    weapon exp, stats and carried weapons then follow it as for any drawn class. None = slice 1 exactly.
    carry: optional, the earlier plan's "guarantees" block (round 75b; misc "assign evenly" re-plans with the classes
    slice 1's guarantee pass gave): a repair whose class came through is listed again and its healer still joins
    holding a staff."""
    seed = check_seed(seed)
    sw = dict(DEFAULT_SWITCHES, **(sw or {}))
    if sw["children"]:
        raise RandoError("children: not built in slice 1 (only off works)")
    if sw["trees"] not in ("own", "any"):
        raise RandoError("trees: own or any")
    persons = [p for p in facts.persons if facts.in_scope(p)]
    plan_p: dict[str, dict] = {}
    notes: list[str] = []
    fixed = dict(classes or {})

    def legal_of(p: dict) -> list[str]:
        if p["label"] in fixed:
            return [fixed[p["label"]]]
        return facts.legal_classes(p, sw)

    # 1. classes
    for p in persons:
        pid = p["label"]
        e = {"pid": pid, "index": ival(p["index"]), "name": facts.pname(p), "old_job": p["job"],
             "job": p["job"], "kept": facts.kept_reason(p, sw)}
        if sw["classes"] and not e["kept"]:
            legal = legal_of(p)
            if legal:
                e["job"] = rng_for(seed, sw, "class", pid).choice(legal)
            else:
                e["kept"] = "no legal class found"
        plan_p[pid] = e

    # 2. per-route role guards on the classes (staff user, door opener); dragon-vein users are a person flag
    members = facts.route_members()

    def role_ok(pid: str, role: str) -> bool:
        p = facts.by_pid[pid]
        jid = plan_p[pid]["job"] if pid in plan_p else p["job"]
        j = facts.jobs[jid]
        if role == "staff":
            return facts.wexp_max(j)[facts.rules["staff_kind"]] > 0
        if role == "door":
            lock = facts.rules["lock_skill"]
            own = [p.get(f"skill.{i}") for i in range(1, 6)] + [p.get("personal_skill.normal")]
            return lock in own or lock in [j.get(f"skill.{i}") for i in range(1, 5)]
        if role == "vein":
            return facts.rules["vein_person_flag"] in flags(p["flags"])
        raise ValueError(role)

    forced = []
    for letter, mem in members.items():
        for role in ("staff", "door"):
            if any(role_ok(pid, role) for pid in mem):
                continue
            # a changed person who had the role before, earliest first; else any changed person who can take it
            vanilla = [pid for pid in mem if pid in plan_p and plan_p[pid]["job"] != plan_p[pid]["old_job"]]
            done = False
            for pid in vanilla:
                p = facts.by_pid[pid]
                legal = [jid for jid in legal_of(p)
                         if role_ok_job(facts, p, jid, role)]
                if legal:
                    plan_p[pid]["job"] = rng_for(seed, sw, "class-" + role, pid).choice(legal)
                    forced.append(f"route {letter}: {plan_p[pid]['name']} given a {role} class")
                    done = True
                    break
            if not done:
                notes.append(f"route {letter}: no way found to keep a {role} user")

    # 2b. round 75b: the seed guarantees (docs/SEED_GUARANTEES_PLAN.md section 3): each needed role (door opener,
    #     healer, flier, vein) is in the army by the first chapter that needs it; one pool person per unmet need gets
    #     a class with the role from its own stream (guarantees.repair), so nobody else's draw moves
    import guarantees as GU
    g_block = GU.repair(facts, plan_p, seed, sw, members)
    forced += g_block.pop("forced")
    if carry:
        GU.carry_over(g_block, carry, plan_p)

    # 3. per person: job_low, weapon exp, bases, growths
    for p in persons:
        e = plan_p[p["label"]]
        pid = p["label"]
        oj, nj = facts.jobs[e["old_job"]], facts.jobs[e["job"]]
        changed = e["job"] != e["old_job"]
        e["job_low"] = p["job_low"]
        if changed:
            if facts.promoted(nj):
                lows = [jid for jid in facts.legal_classes(p, dict(sw, trees="any"), promoted=False)
                        if e["job"] in (facts.jobs[jid]["promotion.1"], facts.jobs[jid]["promotion.2"])]
                same = [jid for jid in lows if facts.jobs[jid]["origin"] == nj["origin"]]
                pick = same or lows
                if pick:
                    e["job_low"] = rng_for(seed, sw, "job_low", pid).choice(pick)
                else:
                    notes.append(f"{e['name']}: no base class promotes into {facts.jname(e['job'])}; reclass base kept")
            else:
                ups = [x for x in (nj["promotion.1"], nj["promotion.2"]) if x in facts.jobs and not facts.excluded_job(x)]
                if ups:
                    e["job_low"] = rng_for(seed, sw, "job_low", pid).choice(ups)
        old_w = [ival(p[f"weapon_exp.{k}"]) for k in KINDS]
        e["old_wexp"] = old_w
        e["wexp"] = (remap_wexp(rng_for(seed, sw, "wexp", pid), old_w, facts.wexp_max(oj), facts.wexp_max(nj))
                     if changed else list(old_w))
        e["old_base"] = [ival(p[f"base.{s}"]) for s in STATS]
        e["old_growth"] = [ival(p[f"growth.{s}"]) for s in STATS]
        caps = [ival(nj[f"max.{s}"]) + ival(p[f"limit_mod.{s}"]) - ival(nj[f"base.{s}"]) for s in STATS]
        e["base_caps"] = caps
        if sw["join_stats"]:
            r = rng_for(seed, sw, "bases", pid)
            w = [r.uniform(0.5, 1.5) for _ in STATS]
            w[0] *= 2.0
            floors = [max(0, -ival(nj[f"base.{s}"])) for s in STATS]
            if sum(e["old_base"]) < sum(floors):
                # a negative personal total (no row of the game has one; the character shuffle's "fit the spot's
                # level" can give one to a filler moved to an early spot): keep the negative bases instead of
                # raising them to 0, only so far that no stat of the new class drops below 0 (HP below 1)
                floors = [max(min(0, ob), (1 if s == "hp" else 0) - ival(nj[f"base.{s}"]))
                          for ob, s in zip(e["old_base"], STATS)]
            e["base"] = _distribute(r, sum(e["old_base"]), 8, floors, caps, w)
        else:
            e["base"] = [min(b, c) for b, c in zip(e["old_base"], caps)]
            if e["base"] != e["old_base"]:
                notes.append(f"{e['name']}: personal bases lowered to the new class's caps")
        if sw["growths"]:
            r = rng_for(seed, sw, "growths", pid)
            w = [r.uniform(0.3, 1.7) for _ in STATS]
            floors = [GROWTH_HP_FLOOR] + [0] * 7
            total = sum(e["old_growth"])
            g = _distribute(r, total - total % GROWTH_STEP, 8, floors, [GROWTH_CAP] * 8, w, GROWTH_STEP)
            g[0] += total % GROWTH_STEP
            e["growth"] = g
        else:
            e["growth"] = list(e["old_growth"])

    # 4. carried weapons that no longer fit: swap for an ordinary weapon of the same rank the class can use
    dispos_edits: dict[tuple, dict] = {}
    swaps: dict[str, list] = {}
    for p in persons:
        e = plan_p[p["label"]]
        if e["job"] == e["old_job"]:
            continue
        pid = p["label"]
        nj = facts.jobs[e["job"]]
        mx = facts.wexp_max(nj)
        origin = ival(nj["origin"])
        chosen: dict[str, str] = {}
        for d in facts.placements(pid):
            for s in range(1, 6):
                iid = d.get(f"item_{s}", "")
                k = facts.item_kind(iid)
                if k is None:
                    continue
                rank = facts.item_rank(iid)
                need = facts.base_usable(p, iid)
                if need and 0 < mx[k] and rank <= mx[k]:
                    e["wexp"][k] = max(e["wexp"][k], rank)    # usable at the start before: keep it so
                why = facts.class_can_hold(e["job"], p, iid, e["wexp"], need)
                if why is None:
                    continue
                if iid not in chosen:
                    usable = [kk for kk in range(8) if mx[kk] > 0 and kk != facts.rules["stone_kind"]]
                    r = rng_for(seed, sw, "item", pid, iid)
                    pick = None
                    ranks = sorted({rank} | {x for x in RANKS if x < rank}, reverse=True) + sorted(x for x in RANKS if x > rank)
                    for rk in ranks:
                        kinds = [kk for kk in usable if rk <= mx[kk]]
                        r.shuffle(kinds)
                        for kk in kinds:
                            cands = facts.replacement_items(kk, rk, origin)
                            if cands:
                                pick = r.choice(cands)
                                break
                        if pick:
                            break
                    if pick is None:
                        notes.append(f"{e['name']}: no replacement found for {facts.iname(iid)} ({why})")
                        chosen[iid] = iid
                        continue
                    chosen[iid] = pick
                    pk = facts.item_kind(pick)
                    if need:
                        e["wexp"][pk] = max(e["wexp"][pk], facts.item_rank(pick))
                    swaps.setdefault(pid, []).append({"old": iid, "new": pick, "why": why,
                                                      "same_rank": facts.item_rank(pick) == rank})
                new = chosen[iid]
                if new != iid:
                    key = (d["file"], ival(d["index"]))
                    dispos_edits.setdefault(key, {"label": d.get("label", "")})[f"item_{s}"] = new
        e["wexp"] = [min(v, m) for v, m in zip(e["wexp"], mx)]
        e["swaps"] = swaps.get(pid, [])

    # 4b. round 75b, the staff in hand (call 3): a healer the guarantee pass repaired joins holding a staff
    g_block["staff_in_hand"] = []
    for pid in g_block["staff_hand"]:
        e = plan_p[pid]
        p = facts.by_pid[pid]
        for h in GU.staff_in_hand(facts, e, p, dispos_edits):
            g_block["staff_in_hand"].append(dict(h, pid=pid, name=e["name"],
                                                 chapter=facts.chapter_of({"file": h["file"]})))
        e["wexp"] = [min(v, m) for v, m in zip(e["wexp"], facts.wexp_max(facts.jobs[e["job"]]))]

    # 5. route-variant joins (owner OK, F-046: docs/rando/RECRUIT_WIRE.md section 4). Their placements name a
    #    HANDOVER row and no class, so the unit was created in the route row's class and kept it after the handover:
    #    with a new class, write it into the placement's jid (a cell the in-game core lays), and swap carried weapons
    #    the unit cannot use with the route row's own weapon exp (that row is not edited). Own rng keys ("hv-item"),
    #    so no draw above moves; no route-variant row known (made-up tables) or Classes off = nothing here.
    for p in persons:
        e = plan_p[p["label"]]
        if e["job"] == e["old_job"]:
            continue
        joins = []
        for d, h in facts.variant_placements(p["label"]):
            want = _variant_class(facts, e, h)
            if not want or want == h.get("job"):
                continue
            key = (d["file"], ival(d["index"]))
            if (d.get("jid") or "") != want:
                dispos_edits.setdefault(key, {"label": d.get("label", "")})["jid"] = want
            wj = facts.jobs[want]
            wmx = facts.wexp_max(wj)
            vexp = _variant_wexp(facts, h, want)
            got = []
            for s in range(1, 6):
                iid = d.get(f"item_{s}", "")
                if facts.item_kind(iid) is None:
                    continue
                need = facts.base_usable(h, iid)
                why = facts.class_can_hold(want, h, iid, vexp, need)
                if why is None:
                    continue
                rank = facts.item_rank(iid)
                usable = [kk for kk in range(8) if wmx[kk] > 0 and kk != facts.rules["stone_kind"]]
                r = rng_for(seed, sw, "hv-item", d["pid"], d["file"], iid)
                pick = None
                for rk in sorted({rank} | {x for x in RANKS if x < rank}, reverse=True):
                    kinds = [kk for kk in usable if rk <= wmx[kk] and (not need or rk <= max(vexp[kk], 1))]
                    r.shuffle(kinds)
                    for kk in kinds:
                        cands = [c for c in facts.replacement_items(kk, rk, ival(wj["origin"]))
                                 if facts.class_can_hold(want, h, c, vexp, need) is None]
                        if cands:
                            pick = r.choice(cands)
                            break
                    if pick:
                        break
                if pick is None:
                    notes.append(f"{e['name']} ({d['pid']}, {facts.chapter_of(d)}): no replacement found for "
                                 f"{facts.iname(iid)} ({why})")
                    continue
                dispos_edits.setdefault(key, {"label": d.get("label", "")})[f"item_{s}"] = pick
                got.append({"slot": s, "old": iid, "new": pick, "why": why})
            joins.append({"pid": d["pid"], "file": d["file"], "index": ival(d["index"]), "jid": want, "swaps": got})
        if joins:
            e["route_joins"] = joins

    plan = {"tool": TOOL_VERSION, "slice": SLICE, "seed": seed, "switches": sw,
            "persons": [plan_p[p["label"]] for p in persons],
            "dispos": {f"{k[0]}#{k[1]}": v for k, v in sorted(dispos_edits.items())},
            "forced": forced, "notes": notes, "routes": members,
            "guarantees": g_block, "rando_version": GU.RANDO_VERSION}
    plan["guards"] = run_guards(facts, plan)
    g = GU.check(facts, plan)          # round 75b: the guarantees backstop on slice 1's own plan (tracks re-runs it)
    plan["guards"]["guarantees: timing"] = dict(g, detail=g["detail"] + ["checked after: slice 1"])
    return plan


def _variant_class(facts: Facts, e: dict, h: dict) -> str | None:
    """The class a route-variant join gets for a plan entry e: the new class when the route row is in the same tier
    as it (every row in the game today), else the plan's job_low when that one has the route row's tier; None =
    leave the placement as it is."""
    hj, nj = facts.jobs.get(h.get("job", "")), facts.jobs.get(e["job"])
    if hj is None or nj is None:
        return None
    if facts.promoted(hj) == facts.promoted(nj):
        return e["job"]
    lj = facts.jobs.get(e.get("job_low", ""))
    return e["job_low"] if lj is not None and facts.promoted(lj) == facts.promoted(hj) else None


def _variant_wexp(facts: Facts, h: dict, jid: str) -> list[int]:
    """The weapon exp a unit created from route row h in class jid starts with (the row's own, cut to the class)."""
    return [min(ival(h.get(f"weapon_exp.{k}", 0)), m) for k, m in zip(KINDS, facts.wexp_max(facts.jobs[jid]))]


def role_ok_job(facts: Facts, p: dict, jid: str, role: str) -> bool:
    j = facts.jobs[jid]
    if role == "staff":
        return facts.wexp_max(j)[facts.rules["staff_kind"]] > 0
    if role == "door":
        lock = facts.rules["lock_skill"]
        own = [p.get(f"skill.{i}") for i in range(1, 6)] + [p.get("personal_skill.normal")]
        return lock in own or lock in [j.get(f"skill.{i}") for i in range(1, 5)]
    return False


# ------------------------------------------------------------------ guards (re-checked from the plan alone)
def run_guards(facts: Facts, plan: dict) -> dict:
    """Every guard, recomputed from the plan and the original rows. {name: {"ok": bool, "detail": [...]}}"""
    sw = plan["switches"]
    out: dict[str, dict] = {}

    def g(name, bad, extra=None):
        out[name] = {"ok": not bad, "detail": bad[:50] + ([] if extra is None else extra)}

    pe = {e["pid"]: e for e in plan["persons"]}
    # legal class
    bad = []
    for e in plan["persons"]:
        p = facts.by_pid[e["pid"]]
        if e["job"] == e["old_job"]:
            continue
        if e["kept"]:
            bad.append(f"{e['name']}: class changed although kept ({e['kept']})")
        if e["job"] not in facts.legal_classes(p, sw):
            bad.append(f"{e['name']}: {e['job']} is not a legal class")
        if facts.female(facts.jobs[e["job"]]) != facts.female(p):
            bad.append(f"{e['name']}: gender row differs")
    g("legal_class", bad)
    # story-fixed people keep their class
    bad = [f"{e['name']}: {e['old_job']} -> {e['job']}" for e in plan["persons"]
           if facts.kept_reason(facts.by_pid[e["pid"]], sw) and e["job"] != e["old_job"]]
    g("story_classes_kept", bad)
    # children, new people, flags: nothing outside the scope is edited; no flag column is edited
    scope = {p["label"] for p in facts.persons if facts.in_scope(p)}
    bad = [e["pid"] for e in plan["persons"] if e["pid"] not in scope]
    bad += [p["label"] for p in facts.persons if facts.is_child(p) and p["label"] in pe]
    g("children_off_no_new_people", bad)
    # weapons usable
    bad = []
    for e in plan["persons"]:
        p = facts.by_pid[e["pid"]]
        if e["job"] == e["old_job"]:
            continue
        for d in facts.placements(e["pid"]):
            key = f"{d['file']}#{ival(d['index'])}"
            for s in range(1, 6):
                iid = plan["dispos"].get(key, {}).get(f"item_{s}", d.get(f"item_{s}", ""))
                need = facts.base_usable(p, d.get(f"item_{s}", ""))
                why = facts.class_can_hold(e["job"], p, iid, e["wexp"], need)
                if why:
                    bad.append(f"{e['name']} {facts.chapter_of(d)} slot {s}: {facts.iname(iid)}: {why}")
        # route-variant joins: the placement's class (jid, else the route row's) with the route row's weapon exp
        for d, h in facts.variant_placements(e["pid"]):
            key = f"{d['file']}#{ival(d['index'])}"
            jid = plan["dispos"].get(key, {}).get("jid") or d.get("jid") or h.get("job", "")
            if jid not in facts.jobs:
                continue
            if jid == h.get("job") == e["old_job"] and _variant_class(facts, e, h):
                bad.append(f"{e['name']} {facts.chapter_of(d)} ({d['pid']}): route-variant join keeps the old class")
                continue
            vexp = _variant_wexp(facts, h, jid)
            for s in range(1, 6):
                iid = plan["dispos"].get(key, {}).get(f"item_{s}", d.get(f"item_{s}", ""))
                need = facts.base_usable(h, d.get(f"item_{s}", ""))
                why = facts.class_can_hold(jid, h, iid, vexp, need)
                if why:
                    bad.append(f"{e['name']} {facts.chapter_of(d)} ({d['pid']}) slot {s}: {facts.iname(iid)}: {why}")
    g("weapons_usable", bad)
    # stats within the class caps; growths in steps of 5 and >= 0. With the growth track's bases mode on, the
    # base total may move by up to its variance (FE8 port meaning): its own bound guard ("growth: bounds") checks
    # that instead of the "total grew" line (tools/randomizer/tracks.py).
    bases_mode = ((plan.get("tracks") or {}).get("growth") or {}).get("opts", {}).get("bases", "slice1") != "slice1"
    bad = []
    for e in plan["persons"]:
        p = facts.by_pid[e["pid"]]
        j = facts.jobs[e["job"]]
        for n, s in enumerate(STATS):
            raw = e["base"][n] + ival(j[f"base.{s}"])
            cap = ival(j[f"max.{s}"]) + ival(p[f"limit_mod.{s}"])
            # below the floor only counts when the plan made it lower than the game's own data (round 58: a Seal
            # of Flames person, "Faceless", has luck -1 in the mod's own tables; nothing of ours caused it)
            oj = facts.jobs.get(e.get("old_job"), j)
            own = e.get("old_base", e["base"])[n] + ival(oj[f"base.{s}"])
            if raw > cap or (raw < (1 if s == "hp" else 0) and raw < own):
                bad.append(f"{e['name']} {s}: {raw} outside 0..{cap}")
            if e["growth"][n] < 0 or e["growth"][n] > 127 or (sw["growths"] and e["growth"][n] % 5 and n):
                bad.append(f"{e['name']} growth {s}: {e['growth'][n]}")
        # a negative personal total (only the character shuffle's "fit the spot's level" makes one) may grow up to
        # what the new class forces: no stat of the new class below 0 (HP below 1); make_plan's step 3 floors
        forced = sum(max(min(0, ob), (1 if s == "hp" else 0) - ival(j[f"base.{s}"]))
                     for ob, s in zip(e["old_base"], STATS))
        if sum(e["base"]) > max(sum(e["old_base"]), forced) and sw["join_stats"] and not bases_mode:
            bad.append(f"{e['name']}: personal base total grew")
        if any(v > m for v, m in zip(e["wexp"], facts.wexp_max(j))):
            bad.append(f"{e['name']}: weapon exp above the class limit")
    g("stats_within_caps", bad)
    # roles per route
    for role, label in (("staff", "staff_user_per_route"), ("door", "door_opener_per_route"),
                        ("vein", "vein_user_per_route")):
        bad, info = [], []
        for letter, mem in plan["routes"].items():
            who = []
            for pid in mem:
                p = facts.by_pid[pid]
                jid = pe[pid]["job"] if pid in pe else p["job"]
                if role == "vein":
                    if facts.rules["vein_person_flag"] in flags(p["flags"]):
                        who.append(pid)
                elif role_ok_job(facts, p, jid, role):
                    who.append(pid)
            names = [pe[x]["name"] if x in pe else facts.pname(facts.by_pid[x]) for x in who]
            info.append(f"{letter}: {len(who)} ({', '.join(names[:6])}{', ...' if len(names) > 6 else ''})")
            if not who:
                bad.append(f"route {letter}: nobody")
        g(label, bad, info)
    # only the allowed columns of Person and the item cells of DisposUnit
    variant_keys = {f"{d['file']}#{ival(d['index'])}" for d in facts.dispos if d.get("pid", "") in facts.variant_of}
    g("only_allowed_cells", [k for k, v in plan["dispos"].items()
                             if set(v) - {"label", *[f"item_{s}" for s in range(1, 6)]}
                             - ({"jid"} if k in variant_keys else set())])
    return out


# ------------------------------------------------------------------ output: a normal mod folder
PERSON_COLS = (["job", "job_low"] + [f"base.{s}" for s in STATS] + [f"growth.{s}" for s in STATS]
               + [f"weapon_exp.{k}" for k in KINDS])


def mod_name(seed: str) -> str:
    return "Rando-" + check_seed(seed)


def _csv(rows: list[list[str]]) -> bytes:
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def render(facts: Facts, plan: dict) -> dict[str, bytes]:
    """{relative path: bytes} of the mod folder: mod.json, tables/Person.csv, tables/DisposUnit.csv (when a
    weapon was swapped), spoiler.txt, plan.json. Same plan -> the same bytes."""
    files: dict[str, bytes] = {}
    name = mod_name(plan["seed"])
    meta = {"name": name, "description": f"Randomizer slice 1, seed {plan['seed']} ({switches_text(plan['switches'])}). "
            "For one randomized save only; see docs/RANDOMIZER.md.",
            "enabled": True, "order": 100, "override": False,
            "randomizer": {"tool": plan["tool"], "slice": SLICE, "seed": plan["seed"],
                           "switches": plan["switches"]}}
    files["mod.json"] = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    rows = [["index", "label"] + PERSON_COLS]
    for e in plan["persons"]:
        vals = [e["job"], e["job_low"]] + [str(v) for v in e["base"]] + [str(v) for v in e["growth"]] \
            + [str(v) for v in e["wexp"]]
        p = facts.by_pid[e["pid"]]
        if vals != [p[c] for c in PERSON_COLS]:
            rows.append([str(e["index"]), e["pid"]] + vals)
    files["tables/Person.csv"] = _csv(rows)
    if plan["dispos"]:
        # jid only for route-variant joins with a new class (make_plan step 5); without them the columns are as before
        cols = (["jid"] if any("jid" in ed for ed in plan["dispos"].values()) else []) + [f"item_{s}" for s in range(1, 6)]
        drows = [["file", "index", "label"] + cols]
        orig = {(d["file"], ival(d["index"])): d for d in facts.dispos}
        for key, ed in plan["dispos"].items():
            f, ix = key.rsplit("#", 1)
            d = orig[(f, int(ix))]
            drows.append([f, ix, d.get("label", "")] + [ed.get(c, d.get(c, "")) for c in cols])
        files["tables/DisposUnit.csv"] = _csv(drows)
    files["spoiler.txt"] = spoiler(facts, plan).encode("utf-8")
    files["plan.json"] = (json.dumps(plan, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    return files


def spoiler(facts: Facts, plan: dict) -> str:
    L = ["Fire Emblem Fates randomizer - spoiler log (slice 1: class, growths, join stats)",
         f"seed: {plan['seed']}", f"switches: {switches_text(plan['switches'])}", f"tool: {plan['tool']}", "",
         "Stats are hp str mag skl spd lck def res. 'bases' are the personal join stats the game adds to the",
         "class's own base stats. 'growths' are the personal growth rates (the class's growth is added by the game).",
         ""]
    for e in plan["persons"]:
        cls = (f"{facts.jname(e['old_job'])} -> {facts.jname(e['job'])}" if e["job"] != e["old_job"]
               else f"{facts.jname(e['job'])} (kept: {e['kept']})" if e["kept"] else f"{facts.jname(e['job'])} (same)")
        L.append(f"{e['name']} [{e['pid']}]")
        L.append(f"  class:    {cls}")
        if e["job_low"] and e["job"] != e["old_job"]:
            L.append(f"  class line base/next: {facts.jname(e['job_low'])}")
        L.append(f"  growths:  {' '.join(map(str, e['old_growth']))}  ->  {' '.join(map(str, e['growth']))}")
        L.append(f"  bases:    {' '.join(map(str, e['old_base']))}  ->  {' '.join(map(str, e['base']))}")
        if e["wexp"] != e["old_wexp"]:
            L.append(f"  weapon exp ({'/'.join(KINDS)}): {' '.join(map(str, e['old_wexp']))}  ->  "
                     f"{' '.join(map(str, e['wexp']))}")
        for s in e.get("swaps", []):
            L.append(f"  weapon swapped: {facts.iname(s['old'])} -> {facts.iname(s['new'])} ({s['why']}"
                     f"{'' if s['same_rank'] else '; another rank: no ordinary weapon of the same rank fits'})")
        for j in e.get("route_joins", []):
            L.append(f"  route-variant join {facts.chapter_of(j)} ({j['pid']}): joins as {facts.jname(j['jid'])}"
                     + "".join(f"; {facts.iname(w['old'])} -> {facts.iname(w['new'])}" for w in j["swaps"]))
    L += ["", "Guards:"]
    for k, v in plan["guards"].items():
        L.append(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
        for d in v["detail"][:12]:
            L.append(f"       {d}")
    if plan["forced"]:
        L += ["", "Classes re-drawn so a route keeps a role or a guarantee is met:"] + [f"  {x}" for x in plan["forced"]]
    if plan.get("guarantees") is not None:          # round 75b
        import guarantees as GU
        L += [""] + GU.spoiler_lines(facts, plan)
    if plan["notes"]:
        L += ["", "Notes:"] + [f"  {x}" for x in plan["notes"]]
    if plan.get("guarantees") is not None:
        L += ["", "Not checked by slice 1 (see docs/RANDOMIZER.md): items given by story scenes rather than map",
              "placements; personal skills and class skills (unchanged); Heart Seal (reclass) options (unchanged);",
              "capture-only and downloadable people; children. Which maps need a door opener, a healer, a flier or a",
              "vein: the Guarantees section above."]
    else:
        L += ["", "Not checked by slice 1 (see docs/RANDOMIZER.md): which maps need a vein, a door or a flier; items",
              "given by story scenes rather than map placements; personal skills and class skills (unchanged);",
              "Heart Seal (reclass) options (unchanged); capture-only and downloadable people; children."]
    return "\n".join(L) + "\n"


def write_mod(files: dict[str, bytes], out_dir: str) -> str:
    """Write the mod folder (refuses to write into an existing non-randomizer folder)."""
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        mj = os.path.join(out_dir, "mod.json")
        try:
            with open(mj, encoding="utf-8") as fh:
                if "randomizer" not in json.load(fh):
                    raise RandoError(f"{out_dir} holds a mod that is not a randomizer mod; not overwritten")
        except (OSError, ValueError):
            raise RandoError(f"{out_dir} exists and is not a randomizer mod folder; not overwritten") from None
        import shutil
        shutil.rmtree(out_dir)
    for rel, data in sorted(files.items()):
        path = os.path.join(out_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    return out_dir
