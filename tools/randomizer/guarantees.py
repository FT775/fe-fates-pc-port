#!/usr/bin/env python3
"""Seed guarantees inside the randomizer (round 75b; docs/SEED_GUARANTEES_PLAN.md, which says 'round 79': read it
as round 75b). Each needed role joins at or before the first chapter that needs it:

    door    a door and chest opener (the lock-opening skill, the person's own or the class's)
    staff   a healer holding a staff (a class with a staff rank; a repaired healer's join placement carries a staff)
    flier   a flier (a class in the flying category) before the maps known to need one
    vein    a dragon-vein user (Corrin's person flag: always met, never repaired)

Always on, no page switch. The needs table is config/randomizer/guarantees.json for Fates (ids only) or the rules'
own "guarantees" block (Seal of Flames: sources.build_seal_rules writes it into seal_rules.json; a test may pass one).

    needs(rules)                          the table for the active game, in a fixed order (list of need dicts)
    applies(facts, need)                  (bool, why): a need counts only when someone of its army is in these
                                          tables and the original game meets it ("never stricter", call 1)
    met(facts, jobs, need, skills=None)   the army entries that cover the need with these classes ([] = unmet)
    repair(facts, people, seed, sw)       make_plan step 2b: one pool person (or the retainer slot) per unmet need
                                          gets a class with the role; returns the plan's "guarantees" block
    check(facts, plan, skill_edits=None)  the backstop (tracks.make_all's cross guard "guarantees: timing")

    python tools/randomizer/guarantees.py facts [--json OUT]   READ ONLY: re-derives the door and chest chapters from
           the scripts (tile event kinds 9 and 10) and, when round 72's break-check results are on disk, the army
           lists; exits 1 if guarantees.json disagrees, 2 on an error, 0 when all agree.

Our own code. Facts only from public tools (the ninja-village flier maps); no game values in this file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

ROUND = "75b"
RANDO_VERSION = 2          # the hidden page row rando_version (ingame.py) and plan.json's "rando_version"
BLOCK_VERSION = 1          # plan.json's "guarantees": {"version": 1, ...}
PATH = os.path.join(ROOT, "config", "randomizer", "guarantees.json")
ROLES = ("door", "staff", "flier", "vein")
ROLE_WORDS = {"door": "door / chest opener", "staff": "healer with a staff", "flier": "flier", "vein": "dragon vein"}
REPAIRABLE = ("door", "staff", "flier")
ROLE_ALIASES = {"opener": "door", "door_opener": "door", "healer": "staff", "staff_user": "staff"}   # Seal block words
MAX_PASSES = 3
FLIER_CAT = "JCID_飛行"
R72_JOBS = os.path.join(ROOT, "build", "r72", "check", "jobs")


class GuaranteeError(Exception):
    pass


# ------------------------------------------------------------------ the table
_CACHE: dict[str, tuple[float, dict]] = {}


def load_table(path: str = PATH) -> dict:
    """guarantees.json (read once per file change; callers must not edit the dict they get)."""
    mt = os.path.getmtime(path)
    got = _CACHE.get(path)
    if got is None or got[0] != mt:
        with open(path, encoding="utf-8") as fh:
            got = _CACHE[path] = (mt, json.load(fh))
    return got[1]


def table_for(rules: dict) -> dict | None:
    """The needs table of the game these rules describe: the rules' own "guarantees" block when they carry one (Seal of
    Flames, tests), else config/randomizer/guarantees.json for Fates; None = no table (a Seal rules file without the
    block: no needs)."""
    if "guarantees" in rules:
        return rules.get("guarantees") or None
    if rules.get("game", "fates") != "fates":
        return None
    return load_table()


def pos(ch: str) -> int:
    """A chapter's place in its story (A007 -> 7); 'every' (the vein) comes first."""
    if ch == "every":
        return 0
    digits = "".join(c for c in str(ch)[1:4] if c.isdigit())
    return int(digits) if digits else 999


def needs(rules: dict, table: dict | None = None) -> list[dict]:
    """[{story, story_name, role, by, why, confidence, army: [pid | [pid, ...]], ...}] ordered by (story position of
    the chapter, story letter, role): the same order every run. A story's value may be {"name", "needs": [...]} or
    the list itself."""
    t = table if table is not None else table_for(rules)
    if not t:
        return []
    out = []
    for letter, st in sorted((t.get("stories") or {}).items()):
        lst = st.get("needs", []) if isinstance(st, dict) else list(st)
        name = (st.get("name") if isinstance(st, dict) else None) or (rules.get("routes") or {}).get(letter, letter)
        for n in lst:
            role = ROLE_ALIASES.get(n.get("role"), n.get("role"))
            if role not in ROLES:
                raise GuaranteeError(f"guarantees: unknown role {n.get('role')!r} ({letter})")
            out.append(dict(n, role=role, story=letter, story_name=name,
                            army=[list(a) if isinstance(a, list) else a for a in n.get("army", [])]))
    out.sort(key=lambda n: (pos(n["by"]), n["story"], ROLES.index(n["role"])))
    return out


def members(entry) -> list[str]:
    return list(entry) if isinstance(entry, list) else [entry]


def where(n: dict) -> str:
    """'Birthright 7': Fates' A/B/C chapter ids carry the chapter number the game shows. Other ids (Seal of Flames'
    R001-R004 follow the shared chapters, so R002 is not the game's chapter 2) are printed as the id itself."""
    by = n["by"]
    if by == "every":
        return f"{n['story_name']} every chapter"
    if str(by)[:1] in ("A", "B", "C"):
        return f"{n['story_name']} {pos(by)}"
    return f"{n['story_name']} chapter id {by}"


def need_key(n: dict) -> str:
    return f"{n['story']}:{n['role']}:{n['by']}"


# ------------------------------------------------------------------ who covers a role
def _own_skills(p: dict, skills: dict | None = None) -> list[str]:
    s = (skills or {}).get(p["label"], {})
    return [s.get(f"skill.{i}", p.get(f"skill.{i}")) for i in range(1, 6)] + \
        [s.get("personal_skill.normal", p.get("personal_skill.normal"))]


def role_of(facts, p: dict, jid: str, role: str, skills: dict | None = None) -> bool:
    j = facts.jobs.get(jid)
    if j is None:
        return False
    r = facts.rules
    if role == "staff":
        return facts.wexp_max(j)[r["staff_kind"]] > 0
    if role == "door":
        lock = r["lock_skill"]
        return lock in _own_skills(p, skills) or lock in [j.get(f"skill.{i}") for i in range(1, 5)]
    if role == "flier":
        cat = (r.get("recruit") or {}).get("flier_job_category") or FLIER_CAT
        return cat in R.flags(j.get("category", ""))
    if role == "vein":
        return r["vein_person_flag"] in R.flags(p["flags"])
    raise ValueError(role)


def job_of(facts, jobs: dict, pid: str) -> str:
    return jobs.get(pid) or facts.by_pid[pid]["job"]


def covers(facts, jobs: dict, entry, role: str, skills: dict | None = None) -> bool:
    """One army entry covers a role: a person with it; a slot only if every one of its people in these tables has it."""
    ms = [pid for pid in members(entry) if pid in facts.by_pid]
    return bool(ms) and all(role_of(facts, facts.by_pid[pid], job_of(facts, jobs, pid), role, skills) for pid in ms)


def met(facts, jobs: dict, need: dict, skills: dict | None = None) -> list:
    """The army entries that cover the need with these classes ({pid: class}; others keep their row's class)."""
    return [e for e in need["army"] if covers(facts, jobs, e, need["role"], skills)]


def applies(facts, need: dict) -> tuple[bool, str]:
    """A need counts only when someone of its army is in these tables, and the ORIGINAL game meets it (never
    stricter than the original, call 1; facts.original_facts = the rows before the character shuffle)."""
    if not any(pid in facts.by_pid for e in need["army"] for pid in members(e)):
        return False, "nobody of its army is in these tables"
    orig = getattr(facts, "original_facts", None) or facts
    if not any(covers(orig, {}, e, need["role"]) for e in need["army"]):
        return False, "the original game does not meet it either (never stricter)"
    return True, ""


def held(facts, sw: dict | None = None) -> set[str]:
    """People a repair never touches in its first choice: rules.json's recruit_fixed / recruit_hold / recruit_castle
    (Gunter, Nyx, Shura, the castle joiners) and the four royals with a legendary weapon (whatever keep-royals says)."""
    rc = facts.rules.get("recruit") or {}
    out = set(rc.get("recruit_fixed", [])) | set(rc.get("recruit_hold", [])) | set(rc.get("recruit_castle", []))
    royal = set(facts.rules.get("royal_weapon_person_flags", []))
    out |= {p["label"] for p in facts.persons if R.flags(p["flags"]) & royal}
    return out


def last_resort(facts) -> set[str]:
    """Round 75b finding: with the character shuffle 'any', a beast can stand in the retainer slot, and then nobody in
    Revelation 7's first-choice pool can take a staff class (9 of 100 seeds). Only then, and only for people slice 1
    re-draws anyway, the shuffle's fixed people (rules.json recruit_fixed: Gunter) may be repaired. Never the held
    (Nyx, Shura), the castle joiners or the royals."""
    return set((facts.rules.get("recruit") or {}).get("recruit_fixed", []))


def join_order(facts, routes: dict | None = None) -> dict[str, int]:
    """Earliest joiner first: a person's place in the route member lists (first team-0 placement, randolib)."""
    routes = routes or facts.route_members()
    out: dict[str, int] = {}
    for mem in routes.values():
        for i, pid in enumerate(mem):
            out[pid] = min(out.get(pid, 10 ** 6), i)
    return out


def _family(facts, jid: str) -> str:
    import misc as M
    return M.family(jid, facts)


# ------------------------------------------------------------------ the repair pass (make_plan step 2b)
def repair(facts, people: dict, seed: str, sw: dict, routes: dict | None = None) -> dict:
    """people: make_plan's {pid: entry} after the class draw and the route pass (entry "job" is changed in place).
    Deterministic: needs in a fixed order, candidates in a fixed order, one stream per (role, chapter, person).
    Returns the plan's "guarantees" block; block["staff_hand"] = the repaired healers whose join placement must
    carry a staff (make_plan step 4b), block["forced"] = the spoiler lines."""
    ns = needs(facts.rules)
    block = {"version": BLOCK_VERSION, "round": ROUND, "rando_version": RANDO_VERSION, "needs": [], "skipped": [],
             "repairs": [], "notes": [], "staff_hand": [], "forced": []}
    live = []
    for n in ns:
        ok, why = applies(facts, n)
        if not ok:
            block["skipped"].append({"need": need_key(n), "why": why})
            continue
        if not any(pid in people for e in n["army"] for pid in members(e)) and n["role"] in REPAIRABLE:
            block["skipped"].append({"need": need_key(n), "why": "nobody of its army is in this plan"})
            continue
        live.append(n)
    if not live:
        return block
    jobs = {pid: e["job"] for pid, e in people.items()}
    hold = held(facts, sw)
    spare = last_resort(facts)
    order = join_order(facts, routes)

    def pool(pid: str, tier: int) -> bool:
        if pid not in people or people[pid].get("kept"):
            return False
        return pid not in hold or (tier == 2 and pid in spare)

    def entry_pool(entry, tier: int) -> bool:
        ms = [pid for pid in members(entry) if pid in facts.by_pid]
        return bool(ms) and all(pool(pid, tier) for pid in ms)

    def rank(e):
        return (0 if any(people[pid]["job"] != people[pid]["old_job"] for pid in members(e) if pid in people) else 1,
                min(order.get(pid, 10 ** 6) for pid in members(e)),
                min(R.ival(facts.by_pid[pid]["index"]) for pid in members(e) if pid in facts.by_pid))

    def all_met(j: dict, upto: int | None = None) -> list[int]:
        return [i for i, n in enumerate(live) if (upto is None or i < upto) and not met(facts, j, n)]

    repaired: dict[str, dict] = {}
    for attempt in range(MAX_PASSES):
        if not all_met(jobs):
            break
        for i, n in enumerate(live):
            if met(facts, jobs, n) or n["role"] not in REPAIRABLE:
                continue
            first = sorted((e for e in n["army"] if entry_pool(e, 1)), key=rank)
            cands = [(e, 1) for e in first] + [(e, 2) for e in sorted(
                (e for e in n["army"] if entry_pool(e, 2) and e not in first), key=rank)]
            # step 4: a repair never takes away the cover of an EARLIER need (a later one is re-checked below)
            before_ok = [k for k in range(i) if met(facts, jobs, live[k])]
            for e, tier in cands:
                ms = [pid for pid in members(e) if pid in facts.by_pid]
                army = {pid for a in n["army"] for pid in members(a) if pid in facts.by_pid} - set(ms)
                taken = {_family(facts, job_of(facts, jobs, q)) for q in army}
                trial = dict(jobs)
                picks = {}
                for pid in ms:
                    p = facts.by_pid[pid]
                    role_cls = [jid for jid in facts.legal_classes(p, sw) if role_of(facts, p, jid, n["role"])]
                    # only classes that keep every earlier need met (a flier who is an earlier need's only cover
                    # may become a healer only in a class that also flies)
                    role_cls = [jid for jid in role_cls
                                if all(met(facts, dict(trial, **{pid: jid}), live[k]) for k in before_ok)]
                    if not role_cls:
                        picks = None
                        break
                    # no repeated class (owner 2026-11-25 "Yes, add it"): first the role classes nobody else in that
                    # chapter's army has (class pairs count as one), else any role class
                    free = [jid for jid in role_cls if _family(facts, jid) not in taken]
                    parts = ["guarantee", n["role"], n["by"], pid] + (["attempt", str(attempt)] if attempt else [])
                    picks[pid] = R.rng_for(seed, sw, *parts).choice(free or role_cls)
                    picks[pid + "#free"] = bool(free)
                    trial[pid] = picks[pid]
                if not picks:
                    continue
                for pid in ms:
                    trial[pid] = picks[pid]
                if not met(facts, trial, n):
                    continue
                if any(not met(facts, trial, live[k]) for k in before_ok):
                    continue
                for pid in ms:
                    rec = repaired.setdefault(pid, {"pid": pid, "name": people[pid]["name"],
                                                    "from": jobs[pid], "needs": []})
                    rec["to"] = picks[pid]
                    rec["no_repeat"] = picks[pid + "#free"]
                    if tier == 2:
                        rec["last_resort"] = True
                    rec["needs"].append(need_key(n))
                    jobs[pid] = picks[pid]
                    people[pid]["job"] = picks[pid]
                    block["forced"].append(f"{where(n)}, {ROLE_WORDS[n['role']]}: {people[pid]['name']} given "
                                           f"{facts.jname(picks[pid])} (guarantee"
                                           f"{'' if picks[pid + '#free'] else '; every role class already in the army'}"
                                           f"{'; last resort: nobody else there could take it' if tier == 2 else ''})")
                    if n["role"] == "staff" and pid not in block["staff_hand"]:
                        block["staff_hand"].append(pid)
                break
    block["repairs"] = [repaired[k] for k in sorted(repaired, key=lambda x: R.ival(facts.by_pid[x]["index"]))]
    for n in live:
        cov = met(facts, jobs, n)
        if not cov:
            block["notes"].append(f"{where(n)}, {ROLE_WORDS[n['role']]}: no repair found in {MAX_PASSES} passes "
                                  f"(the backstop refuses this seed)")
        block["needs"].append({"need": need_key(n), "story": n["story"], "role": n["role"], "by": n["by"],
                               "ok": bool(cov), "covered_by": [members(e) for e in cov],
                               "repaired": [r["pid"] for r in block["repairs"] if need_key(n) in r["needs"]]})
    return block


def carry_over(block: dict, carry: dict, people: dict) -> dict:
    """make_plan(carry=...): the earlier plan's repairs whose class came through to this plan (misc "assign evenly"
    kept it) are listed again (marked "carried"), and their healers keep the staff in hand. Changes block."""
    have = {r["pid"] for r in block["repairs"]}
    for r in carry.get("repairs", []):
        pid = r["pid"]
        if pid in have or pid not in people or people[pid]["job"] != r.get("to"):
            continue
        block["repairs"].append(dict(r, carried=True))
        if pid in carry.get("staff_hand", []) and pid not in block["staff_hand"]:
            block["staff_hand"].append(pid)
    for n in block["needs"]:
        n["repaired"] = [r["pid"] for r in block["repairs"] if n["need"] in r.get("needs", [])]
    return block


# ------------------------------------------------------------------ the staff in hand (make_plan step 4b)
def join_placements(facts, pid: str, letters: list[str] | None = None) -> list[dict]:
    """The placement that creates the person on each story (the first team-0 placement in story order over the shared
    chapters and that story's own chapters); one placement may serve several stories."""
    shared = set(facts.rules.get("shared_chapters", []))
    routes = letters or list(facts.rules.get("routes", {}))
    out, seen = [], set()
    pl = [d for d in facts.placements(pid) if str(d.get("team")) == "0"]
    for letter in routes:
        best = None
        for d in pl:
            ch = facts.chapter_of(d)
            if ch[:4] in shared or (ch[:1] == letter and ch[1:4].isdigit()):
                k = (pos(ch), ch, R.ival(d["index"]))
                if best is None or k < best[0]:
                    best = (k, d)
        if best is not None:
            key = (best[1]["file"], R.ival(best[1]["index"]))
            if key not in seen:
                seen.add(key)
                out.append(best[1])
    return out


def cheapest_staff(facts, p: dict, jid: str) -> str | None:
    """The cheapest ordinary staff of the lowest rank the class can use (never a story item: replacement_items keeps
    only bought, unflagged weapons)."""
    r = facts.rules
    j = facts.jobs[jid]
    mx = facts.wexp_max(j)[r["staff_kind"]]
    for rk in R.RANKS:
        if rk > mx:
            break
        cands = [i for i in facts.replacement_items(r["staff_kind"], rk, R.ival(j["origin"]))
                 if facts.class_can_hold(jid, p, i, [0] * 8, need_exp=False) is None]
        if cands:
            return min(cands, key=lambda i: (R.ival(facts.items[i]["buy_price"]), R.ival(facts.items[i]["index"])))
    return None


def staff_in_hand(facts, e: dict, p: dict, dispos_edits: dict, letters: list[str] | None = None) -> list[dict]:
    """For one repaired healer: every join placement holds a staff the class can use; else the cheapest staff goes
    into the first empty item slot (or replaces the last carried weapon). Changes dispos_edits and e["wexp"] in place;
    returns [{"file", "index", "slot", "old", "new"}]."""
    staff = facts.rules["staff_kind"]
    got = []
    pick = None
    for d in join_placements(facts, e["pid"], letters):
        key = (d["file"], R.ival(d["index"]))
        ed = dispos_edits.get(key, {})
        items = [ed.get(f"item_{s}", d.get(f"item_{s}", "")) for s in range(1, 6)]
        if any(facts.item_kind(i) == staff and facts.class_can_hold(e["job"], p, i, e["wexp"], False) is None
               for i in items):
            continue
        pick = pick or cheapest_staff(facts, p, e["job"])
        if pick is None:
            return got
        empty = [s for s in range(5) if not items[s]]
        weap = [s for s in range(5) if facts.item_kind(items[s]) is not None]
        slot = empty[0] if empty else (weap[-1] if weap else None)
        if slot is None:
            continue
        dispos_edits.setdefault(key, {"label": d.get("label", "")})[f"item_{slot + 1}"] = pick
        e["wexp"][staff] = max(e["wexp"][staff], facts.item_rank(pick))
        got.append({"file": d["file"], "index": R.ival(d["index"]), "slot": slot + 1, "old": items[slot],
                    "new": pick})
    return got


# ------------------------------------------------------------------ the backstop (tracks.make_all)
def skills_from_edits(skill_edits: list[dict] | None) -> dict:
    out: dict[str, dict] = {}
    for e in skill_edits or []:
        if "file" in e or e.get("table", "Person") != "Person":
            continue
        out.setdefault(e["label"], {})[e["cell"]] = e["new"]
    return out


def check(facts, plan: dict, skill_edits: list[dict] | None = None) -> dict:
    """Every need again on the final classes (and the skills track's final skills): {"ok", "detail"}. A miss is our
    bug, never the seed's luck. Also checks that every repaired healer's join placement holds a staff. Writes the
    final covers into plan["guarantees"]["needs"] (the spoiler's Guarantees section reads them)."""
    jobs = {e["pid"]: e["job"] for e in plan["persons"]}
    skills = skills_from_edits(skill_edits)
    blk = plan.get("guarantees") or {}
    bad, info, final = [], [], []
    for n in needs(facts.rules):
        ok, why = applies(facts, n)
        if not ok:
            continue
        if not any(pid in jobs for e in n["army"] for pid in members(e)) and n["role"] in REPAIRABLE:
            continue
        cov = met(facts, jobs, n, skills)
        names = cover_names(facts, plan, [members(e) for e in cov])
        line = f"{where(n)}, {ROLE_WORDS[n['role']]}: {', '.join(names[:4]) or 'NOBODY'}"
        (info if cov else bad).append(line)
        final.append({"need": need_key(n), "story": n["story"], "role": n["role"], "by": n["by"], "ok": bool(cov),
                      "covered_by": [members(e) for e in cov],
                      "repaired": [r["pid"] for r in blk.get("repairs", []) if need_key(n) in r.get("needs", [])]})
    pe = {e["pid"]: e for e in plan["persons"]}
    staff = facts.rules["staff_kind"]
    for pid in blk.get("staff_hand", []):
        e = pe.get(pid)
        if e is None or not role_of(facts, facts.by_pid[pid], e["job"], "staff"):
            continue
        for d in join_placements(facts, pid):
            key = f"{d['file']}#{R.ival(d['index'])}"
            items = [plan["dispos"].get(key, {}).get(f"item_{s}", d.get(f"item_{s}", "")) for s in range(1, 6)]
            if not any(facts.item_kind(i) == staff for i in items):
                bad.append(f"{e['name']} ({facts.chapter_of(d)}): a repaired healer joins without a staff")
    if blk:
        blk["needs"] = final
    return {"ok": not bad, "detail": bad[:50] + info}


def cover_names(facts, plan: dict, cov: list[list[str]]) -> list[str]:
    """'Felicia (Maid) + Jakob (Butler)' per covering entry; the avatar rows (male and female, only one exists in a
    game) are one name, 'Corrin (the avatar)'."""
    avatar = (facts.rules.get("keep_class_person_flags") or [""])[0]
    out, seen_avatar = [], False
    for ms in cov:
        ms = [pid for pid in ms if pid in facts.by_pid]
        if ms and avatar and all(avatar in R.flags(facts.by_pid[pid]["flags"]) for pid in ms):
            if not seen_avatar:
                out.append("Corrin (the avatar)")
                seen_avatar = True
            continue
        out.append(" + ".join(_pname(facts, plan, pid) for pid in ms))
    return out


def _pname(facts, plan: dict, pid: str) -> str:
    e = next((x for x in plan["persons"] if x["pid"] == pid), None)
    name = e["name"] if e else facts.pname(facts.by_pid[pid])
    jid = e["job"] if e else facts.by_pid[pid]["job"]
    return f"{name} ({facts.jname(jid)})"


def spoiler_lines(facts, plan: dict) -> list[str]:
    """The spoiler's Guarantees section (randolib.spoiler): one line a need, the repairs, the paralogue doors."""
    blk = plan.get("guarantees")
    if not blk:
        return []
    by_key = {need_key(n): n for n in needs(facts.rules)}
    L = [f"Guarantees (round {blk.get('round', ROUND)}, always on; randomizer {plan.get('rando_version', RANDO_VERSION)}):"]
    for x in blk.get("needs", []):
        n = by_key.get(x["need"])
        if n is None:
            continue
        who = cover_names(facts, plan, x["covered_by"])
        L.append(f"  {where(n)}, {ROLE_WORDS[n['role']]}: {', '.join(who[:4]) or 'NOBODY'}"
                 + (f" (+{len(who) - 4} more)" if len(who) > 4 else ""))
    for r in blk.get("repairs", []):
        same = r["from"] == r["to"]        # a retainer-slot partner drawn back into the class they had
        L.append(f"  repaired: {r['name']} " + (f"keeps {facts.jname(r['to'])} (drawn again with the retainer slot)"
                                                if same else f"{facts.jname(r['from'])} -> {facts.jname(r['to'])}")
                 + ("" if r.get("no_repeat", True) else " (every role class was already in that army)")
                 + (" (last resort: nobody else in that army could take the role)" if r.get("last_resort") else ""))
    for h in blk.get("staff_in_hand", []):
        L.append(f"  staff in hand: {h['name']} joins ({h['chapter']}) holding {facts.iname(h['new'])}"
                 + (f" instead of {facts.iname(h['old'])}" if h.get("old") else ""))
    for s in blk.get("notes", []):
        L.append(f"  note: {s}")
    if not blk.get("needs"):
        L.append("  (no need applies to these tables)")
    t = table_for(facts.rules) or {}
    pd = (t.get("information") or {}).get("paralogue_doors") or {}
    if pd:
        L.append("  information only (optional paralogues with locked doors, not needs): "
                 + ", ".join(f"{k} {v} doors" for k, v in sorted(pd.items())))
    return L


# ------------------------------------------------------------------ facts (read only)
def tile_kinds(dirs: list[str] | None = None) -> dict[str, dict[int, int]]:
    """{chapter: {9: locked-door tile events, 10: chest tile events}} from the compiled scripts (chests.read_cmb)."""
    import chests as CH
    out: dict[str, dict[int, int]] = {}
    for rel, p in sorted(CH.script_files(dirs or CH.game_dirs("fates")).items()):
        with open(p, "rb") as fh:
            data = fh.read()
        for fn in CH.read_cmb(data):
            if fn["type"] == CH.EV_TERRAIN and len(fn["args"]) >= 5 and fn["args"][4] in (9, 10):
                c = out.setdefault(CH.chapter_of(rel), {})
                c[fn["args"][4]] = c.get(fn["args"][4], 0) + 1
    return out


def r72_army(rel: str, slot: list[str]) -> list | None:
    """A break-check job's army as guarantees.json writes it (the retainer as the slot, both Corrins), or None."""
    path = os.path.join(ROOT, *rel.split(" ")[0].split("/"))
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        r = json.load(fh)
    out: list = []
    for u in r.get("army") or []:
        pid = u["pid"]
        if pid.startswith("PID_プレイヤー"):
            for c in ("PID_プレイヤー男", "PID_プレイヤー女"):
                if c not in out:
                    out.append(c)
        elif pid in slot:
            if slot not in out:
                out.append(list(slot))
        else:
            out.append(pid)
    return out


def r72_jids(rel: str) -> dict[str, str]:
    path = os.path.join(ROOT, *rel.split(" ")[0].split("/"))
    with open(path, encoding="utf-8") as fh:
        return {u["pid"]: u["jid"] for u in json.load(fh).get("army") or []}


def facts_report(table: dict | None = None, rules: dict | None = None) -> dict:
    """The read-only cross-check of guarantees.json against the scripts and round 72's armies."""
    rules = rules or R.load_rules()
    table = table or load_table()
    ns = needs(rules, table)
    slot = table.get("retainer_slot") or []
    bad, ok, notes = [], [], []
    import gamedata as GD
    why = GD.available()
    tk = None
    facts = None
    if why:
        notes.append(f"scripts and tables not checked: {why}")
    else:
        tk = tile_kinds()
        facts = GD.load_facts(rules, names=False)
    shared = rules.get("shared_chapters", [])
    for letter, name in rules.get("routes", {}).items():
        story = [n for n in ns if n["story"] == letter]
        if tk is not None:
            chs = sorted({c for c in tk if c in shared or (c[:1] == letter and c[1:4].isdigit())}, key=pos)
            first_chest = next((c for c in chs if tk[c].get(10)), None)
            first_door = next((c for c in chs if tk[c].get(9)), None)
            ok.append(f"{name}: first chests {first_chest}, first locked doors {first_door} (script tile kinds 10/9)")
            dn = [n for n in story if n["role"] == "door"]
            if (first_chest or first_door) and not dn:
                bad.append(f"{name}: chests or doors but no door need")
            for n in dn:
                firsts = [c for c in (first_chest, first_door) if c]
                first = min(firsts, key=pos)
                if not tk.get(n["by"], {}).get(9) and not tk.get(n["by"], {}).get(10):
                    bad.append(f"{name} door need by {n['by']}: no chest or door tile event there")
                if pos(n["by"]) > pos(first):
                    # never stricter: every chest/door chapter before 'by' must have no opener in the original army
                    for c in chs:
                        if pos(c) >= pos(n["by"]) or not (tk[c].get(9) or tk[c].get(10)):
                            continue
                        job = os.path.join(R72_JOBS, f"{dict(A='bt', B='cq', C='rv').get(letter, '?')}-{c}-off",
                                           "result.json")
                        if not os.path.isfile(job):
                            notes.append(f"{name} {c}: no break-check army on disk (never-stricter step not checked)")
                            continue
                        rel = os.path.relpath(job, ROOT).replace(os.sep, "/")
                        jids = r72_jids(rel)
                        if facts and any(pid in facts.by_pid and role_of(facts, facts.by_pid[pid], j, "door")
                                         for pid, j in jids.items()):
                            bad.append(f"{name} door need by {n['by']}: the original army already has an opener in "
                                       f"{c} (the need should be {c})")
                        else:
                            ok.append(f"{name} {c}: chests/doors but no opener in the original army (never stricter)")
                if n["by"] in (first_chest, first_door) or pos(n["by"]) <= pos(first):
                    ok.append(f"{name} door need by {n['by']}: the first chest/door chapter")
            for n in story:
                if n["role"] == "flier" and not tk.get(n["by"], {}).get(9):
                    bad.append(f"{name} flier need by {n['by']}: no locked-door tile event there")
        for n in story:
            src = n.get("army_from")
            if not src:
                continue
            if n["by"] != "every" and f"-{n['by']}-off/" not in src:
                bad.append(f"{name} {n['role']} by {n['by']}: its army is read from another chapter ({src.split(' ')[0]})")
            got = r72_army(src, slot)
            if got is None:
                notes.append(f"{name} {n['role']} by {n['by']}: {src.split(' ')[0]} not on disk (army not checked)")
            elif n["role"] != "vein" and got != n["army"]:
                bad.append(f"{name} {n['role']} by {n['by']}: army differs from {src.split(' ')[0]}: "
                           f"json {n['army']} vs read {got}")
            else:
                ok.append(f"{name} {n['role']} by {n['by']}: army agrees with round 72's read")
            if got is not None and facts is not None:
                jids = r72_jids(src)      # the classes the robot read: the original game's

                def covered(e) -> bool:
                    there = [pid for pid in members(e) if pid in jids and pid in facts.by_pid]
                    return bool(there) and all(role_of(facts, facts.by_pid[pid], jids[pid], n["role"]) for pid in there)
                orig_ok = any(covered(e) for e in n["army"])
                (ok if orig_ok else bad).append(f"{name} {n['role']} by {n['by']}: the original army "
                                                f"{'meets' if orig_ok else 'does NOT meet'} it")
    if tk is not None:
        pd = (table.get("information") or {}).get("paralogue_doors") or {}
        real = {c: v[9] for c, v in tk.items() if c.startswith("X") and v.get(9)}
        if pd != real:
            bad.append(f"paralogue doors: json {pd} vs scripts {real}")
        else:
            ok.append(f"paralogue doors agree: {real}")
        total9 = sum(v.get(9, 0) for c, v in tk.items() if c[:1] in "ABCX" and c[1:4].isdigit())
        ok.append(f"kind-9 tile events in story and paralogue scripts: {total9}")
    # the Elise note (round 75b G1): she is not in the army before Conquest 7
    e6 = os.path.join(ROOT, "build", "r62", "rando", "check", "jobs", "cq-B006-bossprove", "result.json")
    if os.path.isfile(e6):
        with open(e6, encoding="utf-8") as fh:
            a6 = [u["pid"] for u in json.load(fh).get("army") or []]
        (ok if "PID_エリーゼ" not in a6 else bad).append(
            f"cq-ch6-clear army {a6}: Elise {'absent' if 'PID_エリーゼ' not in a6 else 'PRESENT'} before Conquest 7")
    return {"ok": not bad, "disagree": bad, "agree": ok, "not_checked": notes}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("facts", "needs"))
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "needs":
            print(json.dumps(needs(R.load_rules()), ensure_ascii=False, indent=1))
            return 0
        rep = facts_report()
    except (R.RandoError, GuaranteeError, OSError, ValueError, KeyError) as ex:
        print(f"guarantees: {ex}", file=sys.stderr)
        return 2
    text = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.json:
        p = os.path.abspath(a.json)
        if not p.startswith(os.path.join(ROOT, "build") + os.sep):
            print("guarantees: --json goes under build/ only", file=sys.stderr)
            return 2
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
