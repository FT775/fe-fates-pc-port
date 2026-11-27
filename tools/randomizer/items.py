#!/usr/bin/env python3
"""Fire Emblem Fates randomizer, track "items" (F-043 #1, round 49; docs/rando/ITEMS.md).

What it changes (only cells of rows that already exist, table data only):
  - starting inventories: the item cells of the player's own map placements (DisposUnit item_1..5, team 0) of the
    people slice 1 randomizes; an ordinary bought weapon becomes another ordinary weapon the person's (new) class
    can use from the start, a healing staff another healing staff, a healing item / tonic / stat booster another of
    its own sort. Personal, legendary, story (precious, chapter-only, can't-remove), key and seal items stay.
  - shops: the four stock lists in the Item table (dawn / dusk armory, rod / staff shop; shop level 1-3). Within a
    shop, items of one "band" (same weapon type and rank; same staff rank and heal-or-not; same consumable sort)
    trade their stock pattern, so every shop level keeps the same number of goods of each band and prices stay
    the items' own. With shop sides "mixed" a shop may also take an item its partner shop (the other side's
    armory or item shop) sold. Vulnerary, the two rank-E healing staves (Heal, Bloom Festal) and every seal keep
    their own stock: every route keeps healing and Master / Heart Seals where it had them.
  - rewards: the castle's battle and visit achievement rewards (AchieveBonusBattle / AchieveBonusVisit .item)
    become another item of the same band. The route list and list 4 (downloadable class items, skill books) and
    the two trophy seals stay.

Not table data in this game, so not changed: chests, villages and other map gifts (they are in each chapter's
event script), enemy drops (the enemy track), the castle's random-gain and lottery pools (Item.pool_rank).

Entry point for the integrate step:  plan_items(facts, rng, opts) -> (edits, spoiler_lines)
  facts: randolib.Facts (the slice-1 view of the tables); rng: random.Random (use sub_rng(seed, "items")); opts:
  {"inventories": bool, "shops": bool, "shop_sides": "own"|"mixed", "rewards": bool,
   "slice1_plan": the slice-1 plan dict or None (then the original classes are used),
   "achieve": {"AchieveBonusBattle": rows, "AchieveBonusVisit": rows} (load_achieve()) or None}
  edits: [{"table", "file" (DisposUnit only), "index", "label", "cells": {column: value}}], values as the table CSV
  writes them. check_items(facts, edits, opts) re-checks every guard from the edits alone.

Our own code; public randomizers were read for facts only (Ignis has chests and villages as a separate switch).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "items"
TOOL_VERSION = "rando-items-v1"
DEFAULT_OPTS = {"inventories": True, "shops": True, "shop_sides": "own", "rewards": True}
SHOPS = ("dawn_stock", "dusk_stock", "rod_stock", "staff_stock")
LEVELS = ("lv1", "lv2", "lv3")
PARTNER = {"dawn_stock": "dusk_stock", "dusk_stock": "dawn_stock", "rod_stock": "staff_stock",
           "staff_stock": "rod_stock"}
SHOP_NAMES = {"dawn_stock": "Hoshido armory (dawn)", "dusk_stock": "Nohr armory (dusk)",
              "rod_stock": "Hoshido item shop (rod)", "staff_stock": "Nohr item shop (staff)"}
REWARD_TABLES = ("AchieveBonusBattle", "AchieveBonusVisit")
# Item flags (ISID_ ids, not game values). Story / key / unique items are never moved, replaced or newly placed.
KEEP_FLAGS = {"ISID_貴重品", "ISID_章限定", "ISID_神武器", "ISID_外せない", "ISID_敵専用", "ISID_扉鍵", "ISID_宝箱鍵",
              "ISID_即換金", "ISID_所持強化"}
HEAL_STAFF_FLAG = "ISID_回復杖"
DOOR_FLAG = "ISID_扉鍵"
SUB_HEAL, SUB_SEAL = 1, 11          # Item.item_subkind: healing items; seals (Master / Heart / ... Seal)
PINNED = ("IID_傷薬", "IID_ライブ", "IID_春祭")   # Vulnerary, Heal, Bloom Festal: their shop stock is never moved
LEVEL_FLAG_BITS = 0x1E              # DisposUnit item_N_flags bits 1-4: the item is given only at some levels


class ItemsError(R.RandoError):
    pass


def sub_rng(seed: str, track: str = TRACK, opts: dict | None = None) -> random.Random:
    """The track's own random stream: SHA-256 of (tool version, seed, track, this track's switches), so another
    track's switches or draws never move this track's results."""
    o = {k: (opts or {}).get(k, v) for k, v in DEFAULT_OPTS.items()}
    key = "\x1f".join([TOOL_VERSION, R.check_seed(seed), track, json.dumps(o, sort_keys=True)])
    return random.Random(int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big"))


def _stream(base: int, *parts) -> random.Random:
    key = "\x1f".join([str(base)] + [str(p) for p in parts])
    return random.Random(int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big"))


# ------------------------------------------------------------------ item facts
class ItemView:
    def __init__(self, facts: R.Facts):
        self.f = facts
        self.items = facts.items

    def flags(self, iid: str) -> set[str]:
        it = self.items.get(iid)
        return R.flags(it["flags"]) if it else set()

    def price(self, iid: str) -> int:
        return R.ival(self.items[iid].get("buy_price", 0)) if iid in self.items else 0

    def sub(self, iid: str) -> int:
        return R.ival(self.items[iid].get("item_subkind", 0)) if iid in self.items else 0

    def lpw(self, iid: str) -> int:
        return R.ival(self.items[iid].get("legal_player_weapon", 1)) if iid in self.items else 0

    def personal(self, iid: str) -> bool:
        return any("専用" in f for f in self.flags(iid))

    def placeable(self, iid: str) -> bool:
        """May appear in a new place: a real item of the player's game (not downloadable, enemy-only, money,
        key, story or trophy; Item.legal_player_weapon 1 or 2) and not a personal weapon."""
        if iid not in self.items or not iid or R.ival(self.items[iid]["index"]) == 0:
            return False
        if self.lpw(iid) not in (1, 2):
            return False
        return not (self.flags(iid) & KEEP_FLAGS) and not self.personal(iid)

    def heal_staff(self, iid: str) -> bool:
        return self.f.item_kind(iid) == self.f.rules["staff_kind"] and HEAL_STAFF_FLAG in self.flags(iid)

    def band(self, iid: str):
        """Items of one band may trade places: weapons by (type, rank), staves by (rank, heals), stones never,
        other items by their sort (item_subkind; seals never)."""
        k = self.f.item_kind(iid)
        if k is None:
            s = self.sub(iid)
            return None if s == SUB_SEAL else ("item", s)
        if k == self.f.rules["stone_kind"]:
            return None
        if k == self.f.rules["staff_kind"]:
            return ("staff", self.f.item_rank(iid), self.heal_staff(iid))
        return ("weapon", k, self.f.item_rank(iid))

    def stock(self, iid: str, shop: str) -> tuple[int, int, int]:
        it = self.items[iid]
        return tuple(R.ival(it.get(f"{shop}.{lv}", 0)) for lv in LEVELS)


# ------------------------------------------------------------------ the people's final classes (slice 1 aware)
def _final(facts: R.Facts, slice1: dict | None):
    """{pid: (job, wexp list)} after slice 1, and slice 1's DisposUnit item cells {key: {item_N: iid}}."""
    out = {}
    for p in facts.persons:
        if facts.in_scope(p):
            out[p["label"]] = (p["job"], [R.ival(p[f"weapon_exp.{k}"]) for k in R.KINDS])
    if slice1:
        for e in slice1["persons"]:
            out[e["pid"]] = (e["job"], list(e["wexp"]))
    return out, (slice1 or {}).get("dispos", {})


def dkey(d: dict) -> str:
    return f"{d['file']}#{R.ival(d['index'])}"


def base_items(d: dict, s1dispos: dict) -> list[str]:
    ed = s1dispos.get(dkey(d), {})
    return [ed.get(f"item_{s}", d.get(f"item_{s}", "")) for s in range(1, 6)]


def main_person(facts: R.Facts, pid: str) -> dict | None:
    """The main Person row of a placement's pid: itself, or, for a route-variant (HANDOVER) row such as
    PID_C_エリーゼ, the main row it hands over to (round 60: these joins were left out before)."""
    p = facts.by_pid.get(pid)
    if p is None:
        main = (getattr(facts, "variant_of", None) or {}).get(pid)
        p = facts.by_pid.get(main) if main else None
    return p


def placement_unit(facts: R.Facts, d: dict, final: dict, s1d: dict) -> tuple[dict, str, list[int], dict]:
    """(row the unit is created from, its class, its weapon exp, main person) for a placement in scope. A route-
    variant join is created from its HANDOVER row in that row's class (or the class slice 1 wrote into the
    placement's jid), with that row's weapon exp cut to the class (randolib make_plan step 5's rule)."""
    p = main_person(facts, d["pid"])
    if d["pid"] in facts.by_pid:
        job, wexp = final[d["pid"]]
        return p, job, wexp, p
    h = facts.variant_row[d["pid"]]
    job = s1d.get(dkey(d), {}).get("jid") or d.get("jid") or h["job"]
    return h, job, R._variant_wexp(facts, h, job), p


def inventory_scope(facts: R.Facts, slice1: dict | None) -> list[dict]:
    """The placements whose items this track may change: the player's side (team 0), people slice 1 randomizes
    (in scope), not the story-fixed ones (Corrin, Azura, royals with keep-royals, special classes). Round 60: a
    route-variant join (a placement naming a HANDOVER row, e.g. Revelation's PID_C_ rows) counts as its main
    person's placement."""
    sw = dict(R.DEFAULT_SWITCHES, **((slice1 or {}).get("switches") or {}))
    out = []
    for d in facts.dispos:
        p = main_person(facts, d.get("pid"))
        if p is None or str(d.get("team")) != "0" or not facts.in_scope(p) or facts.kept_reason(p, sw):
            continue
        if d.get("pid") not in facts.by_pid and d["pid"] not in (getattr(facts, "variant_row", None) or {}):
            continue
        out.append(d)
    return out


# ------------------------------------------------------------------ the plan
def plan_items(facts: R.Facts, rng: random.Random, opts: dict | None = None):
    o = dict(DEFAULT_OPTS, **(opts or {}))
    if o["shop_sides"] not in ("own", "mixed"):
        raise ItemsError("shop sides: own or mixed")
    base = rng.getrandbits(256)
    iv = ItemView(facts)
    edits: list[dict] = []
    lines = ["Items (track 'items'): " + ", ".join(
        f"{k.replace('_', ' ')}={'on' if o[k] is True else 'off' if o[k] is False else o[k]}"
        for k in ("inventories", "shops", "shop_sides", "rewards"))]
    if o["inventories"]:
        e, ln = _plan_inventories(facts, iv, base, o)
        edits += e
        lines += ln
    if o["shops"]:
        e, ln = _plan_shops(facts, iv, base, o)
        edits += e
        lines += ln
    if o["rewards"]:
        e, ln = _plan_rewards(facts, iv, base, o)
        edits += e
        lines += ln
    return edits, lines


def _inv_candidates(facts, iv, p, job, wexp, old):
    """Replacements for one carried item of person p in class job with weapon exp wexp; [] = keep it."""
    if not iv.placeable(old) or iv.price(old) <= 0:
        return []
    k = facts.item_kind(old)
    mx = facts.wexp_max(facts.jobs[job])
    out = []
    if k is None:
        s = iv.sub(old)
        if s == SUB_SEAL:
            return []
        cap = 2 * iv.price(old)
        for it in facts.item_list:
            i = it["label"]
            if facts.item_kind(i) is None and iv.sub(i) == s and iv.placeable(i) and 0 < iv.price(i) <= cap:
                out.append(i)
        return out
    if k == facts.rules["stone_kind"]:
        return []
    want_heal = iv.heal_staff(old)
    rank = facts.item_rank(old)
    # usable from the join with the person's own weapon exp: the new one must be too (any type the class uses);
    # else the old one is usable only through a later chapter's own person record (route joins at a higher
    # level): then only the same type and rank, so whatever made the old one usable makes the new one usable
    from_start = facts.class_can_hold(job, p, old, wexp, True) is None
    for it in facts.item_list:
        i = it["label"]
        kk = facts.item_kind(i)
        if kk is None or kk == facts.rules["stone_kind"] or not iv.placeable(i) or iv.price(i) <= 0:
            continue
        if (kk == facts.rules["staff_kind"]) != (k == facts.rules["staff_kind"]):
            continue
        if want_heal and not iv.heal_staff(i):
            continue
        if facts.item_rank(i) > rank or mx[kk] <= 0:
            continue
        if from_start:
            if facts.class_can_hold(job, p, i, wexp, True) is None:
                out.append(i)
        elif kk == k and facts.item_rank(i) == rank and facts.class_can_hold(job, p, i, wexp, False) is None:
            out.append(i)
    same = [i for i in out if facts.item_rank(i) == rank]
    return same or out


def _plan_inventories(facts, iv, base, o):
    final, s1d = _final(facts, o.get("slice1_plan"))
    chosen: dict[tuple, str] = {}
    edits, lines, changed = [], [], []
    for d in inventory_scope(facts, o.get("slice1_plan")):
        u, job, wexp, p = placement_unit(facts, d, final, s1d)
        cur = base_items(d, s1d)
        new = list(cur)
        for s in range(1, 6):
            old = cur[s - 1]
            if not old or R.ival(d.get(f"item_{s}_flags", 0)) & LEVEL_FLAG_BITS:
                continue
            key = (d["pid"], old)
            if key not in chosen:
                cands = _inv_candidates(facts, iv, u, job, wexp, old)
                pick = _stream(base, "inventory", d["pid"], old).choice(cands) if cands else old
                if d["pid"] not in facts.by_pid and p["label"] in final:
                    # a route-variant join: the main person's own pick for this item when it fits this join too
                    # ("same item in every chapter the person joins"), else a draw under the variant's label;
                    # the main rows' draws never move
                    mj, mw = final[p["label"]]
                    mc = _inv_candidates(facts, iv, p, mj, mw, old)
                    mpick = _stream(base, "inventory", p["label"], old).choice(mc) if mc else old
                    if mpick == old or mpick in cands:
                        pick = mpick
                chosen[key] = pick
                line = f"  {facts.pname(p)}: {facts.iname(old)} -> {facts.iname(chosen[key])}"
                if chosen[key] != old and line not in changed:
                    changed.append(line)
            new[s - 1] = chosen[key]
        if new != [d.get(f"item_{s}", "") for s in range(1, 6)]:
            edits.append({"table": "DisposUnit", "file": d["file"], "index": R.ival(d["index"]),
                          "label": d.get("label", ""), "cells": {f"item_{s}": new[s - 1] for s in range(1, 6)}})
    lines.append(f"Starting items: {len(changed)} changed (same item in every chapter the person joins):")
    lines += changed
    return edits, lines


def _shop_plan(facts, iv, base, o) -> dict[str, dict[str, tuple]]:
    """{shop: {iid: new (lv1, lv2, lv3)}} for every item whose stock in that shop changes or stays."""
    sold = {sh: [it["label"] for it in facts.item_list if any(iv.stock(it["label"], sh))] for sh in SHOPS}
    out: dict[str, dict[str, tuple]] = {}
    for sh in SHOPS:
        res = {}
        bands: dict[tuple, list[str]] = {}
        for i in sold[sh]:
            b = iv.band(i)
            if b is None or i in PINNED or not iv.placeable(i) or iv.price(i) <= 0:
                res[i] = iv.stock(i, sh)          # kept as it is
                continue
            bands.setdefault(b, []).append(i)
        for b in sorted(bands, key=repr):
            members = bands[b]
            pool = list(members)
            if o["shop_sides"] == "mixed":
                pool += [i for i in sold[PARTNER[sh]] if i not in pool and iv.band(i) == b and i not in PINNED
                         and iv.placeable(i) and iv.price(i) > 0 and i not in res]
            r = _stream(base, "shop", sh, repr(b))
            pool.sort(key=lambda i: R.ival(facts.items[i]["index"]))
            holders = r.sample(pool, len(members))
            pats = [iv.stock(i, sh) for i in members]
            r.shuffle(pats)
            for i in pool:
                res[i] = (0, 0, 0)
            for i, pat in zip(holders, pats):
                res[i] = pat
        out[sh] = res
    return out


def _plan_shops(facts, iv, base, o):
    plan = _shop_plan(facts, iv, base, o)
    rows: dict[str, dict] = {}
    lines = ["Shops (stock at shop level 1 / 2 / 3; 255 = no limit):"]
    for sh in SHOPS:
        gained, lost = [], []
        for i, pat in plan[sh].items():
            old = iv.stock(i, sh)
            if pat == old:
                continue
            rows.setdefault(i, {}).update({f"{sh}.{lv}": str(v) for lv, v in zip(LEVELS, pat)})
            (gained if any(pat) and not any(old) else lost if not any(pat) else gained).append(
                f"{facts.iname(i)} {'/'.join(map(str, old))}->{'/'.join(map(str, pat))}")
        lines.append(f"  {SHOP_NAMES[sh]}: " + ("; ".join(gained + lost) if gained or lost else "unchanged"))
    edits = [{"table": "Item", "index": R.ival(facts.items[i]["index"]), "label": i, "cells": c}
             for i, c in sorted(rows.items(), key=lambda kv: R.ival(facts.items[kv[0]]["index"]))]
    return edits, lines


def load_achieve() -> dict:
    import gamedata as GD
    return {t: GD._load(t) for t in REWARD_TABLES}


def _plan_rewards(facts, iv, base, o):
    ach = o.get("achieve")
    if not ach:
        return [], ["Castle achievement rewards: not loaded (unchanged)"]
    listed = {r["item"] for t in REWARD_TABLES for r in ach.get(t, [])}
    pool = [it["label"] for it in facts.item_list
            if iv.placeable(it["label"]) and (iv.price(it["label"]) > 0 or it["label"] in listed)]
    edits, lines = [], ["Castle achievement rewards (battles won / castle visits):"]
    for t in REWARD_TABLES:
        used = set()
        for r in ach.get(t, []):
            old = r["item"]
            b = iv.band(old) if iv.placeable(old) else None
            if b is None:
                used.add(old)
                continue
            cands = [i for i in pool if iv.band(i) == b]
            fresh = [i for i in cands if i not in used] or cands
            new = _stream(base, "reward", t, R.ival(r["index"])).choice(fresh)
            used.add(new)
            if new != old:
                edits.append({"table": t, "index": R.ival(r["index"]), "label": r.get("label", ""),
                              "cells": {"item": new}})
                lines.append(f"  {t[len('AchieveBonus'):].lower()} {r.get('requirement', '?')}: "
                             f"{facts.iname(old)} -> {facts.iname(new)}")
    return edits, lines


# ------------------------------------------------------------------ guards (from the edits alone)
def check_items(facts: R.Facts, edits: list[dict], opts: dict | None = None) -> dict:
    o = dict(DEFAULT_OPTS, **(opts or {}))
    iv = ItemView(facts)
    final, s1d = _final(facts, o.get("slice1_plan"))
    out = {}

    def g(name, bad, info=None):
        out[name] = {"ok": not bad, "detail": bad[:50] + (info or [])}

    dis = {f"{e['file']}#{e['index']}": e["cells"] for e in edits if e["table"] == "DisposUnit"}
    items_ed = {e["label"]: e["cells"] for e in edits if e["table"] == "Item"}
    scope = {dkey(d) for d in inventory_scope(facts, o.get("slice1_plan"))}
    # 1. only allowed cells and rows
    bad = []
    for e in edits:
        allowed = {"DisposUnit": {f"item_{s}" for s in range(1, 6)},
                   "Item": {f"{sh}.{lv}" for sh in SHOPS for lv in LEVELS},
                   "AchieveBonusBattle": {"item"}, "AchieveBonusVisit": {"item"}}.get(e["table"])
        if allowed is None or set(e["cells"]) - allowed:
            bad.append(f"{e['table']} {e.get('label')}: cells {sorted(e['cells'])}")
        if e["table"] == "DisposUnit" and f"{e['file']}#{e['index']}" not in scope:
            bad.append(f"{e['file']} #{e['index']}: not a placement this track may change")
    g("only_allowed_cells", bad)
    # 2. starting weapons usable; story / key / seal / personal items kept; no new non-placeable item
    bad = []
    for d in facts.dispos:
        k = dkey(d)
        if k not in dis:
            continue
        if k not in scope:
            continue   # reported by only_allowed_cells
        u, job, wexp, p = placement_unit(facts, d, final, s1d)
        cur = base_items(d, s1d)
        for s in range(1, 6):
            old, new = cur[s - 1], dis[k].get(f"item_{s}", cur[s - 1])
            if new == old:
                continue
            if not iv.placeable(old) or iv.sub(old) == SUB_SEAL and facts.item_kind(old) is None:
                bad.append(f"{facts.pname(p)} {facts.chapter_of(d)} slot {s}: {facts.iname(old)} must stay")
            if not iv.placeable(new) or iv.price(new) <= 0:
                bad.append(f"{facts.pname(p)} {facts.chapter_of(d)} slot {s}: {facts.iname(new)} may not be placed")
            if (facts.item_kind(old) is None) != (facts.item_kind(new) is None):
                bad.append(f"{facts.pname(p)} {facts.chapter_of(d)} slot {s}: weapon/item swapped across")
            if facts.item_kind(new) is not None:
                if facts.class_can_hold(job, u, old, wexp, True) is None:
                    why = facts.class_can_hold(job, u, new, wexp, True)
                elif facts.item_kind(new) != facts.item_kind(old) or facts.item_rank(new) != facts.item_rank(old):
                    why = "the old item was usable only by a later chapter's record: type and rank must stay"
                else:
                    why = facts.class_can_hold(job, u, new, wexp, False)
                if why:
                    bad.append(f"{facts.pname(p)} {facts.chapter_of(d)} slot {s}: {facts.iname(new)}: {why}")
            if iv.heal_staff(old) and not iv.heal_staff(new):
                bad.append(f"{facts.pname(p)} {facts.chapter_of(d)} slot {s}: a healing staff became {facts.iname(new)}")
    g("starting_items_usable_and_story_kept", bad)
    # 3. per route: someone on the player's side carries healing (heal staff they can use, or a healing item)
    #    and the door keys placed are all still there
    def carried(d):
        cur = base_items(d, s1d)
        ed = dis.get(dkey(d), {})
        return [ed.get(f"item_{s}", cur[s - 1]) for s in range(1, 6)]
    members = facts.route_members()
    shared = set(facts.rules["shared_chapters"])
    bad, info = [], []
    for letter in facts.rules["routes"]:
        heal_n, keys_before, keys_after = 0, 0, 0
        for d in facts.dispos:
            ch = facts.chapter_of(d)
            if str(d.get("team")) != "0" or not (ch[:4] in shared or ch[0] == letter):
                continue
            before, after = base_items(d, s1d), carried(d)
            keys_before += sum(1 for i in before if DOOR_FLAG in iv.flags(i))
            keys_after += sum(1 for i in after if DOOR_FLAG in iv.flags(i))
            pid = d.get("pid")
            job = final.get(pid, (facts.by_pid[pid]["job"] if pid in facts.by_pid else None, None))[0]
            for i in after:
                if iv.heal_staff(i) and job and facts.wexp_max(facts.jobs[job])[facts.rules["staff_kind"]] > 0:
                    heal_n += 1
                elif facts.item_kind(i) is None and iv.sub(i) == SUB_HEAL:
                    heal_n += 1
        info.append(f"{letter}: {heal_n} healing items carried; door keys {keys_before} -> {keys_after}; "
                    f"{len(members.get(letter, []))} people")
        if not heal_n:
            bad.append(f"route {letter}: nobody carries healing")
        if keys_after != keys_before:
            bad.append(f"route {letter}: door keys {keys_before} -> {keys_after}")
    g("healing_and_doors_per_route", bad, info)
    # 4. shops: same goods count per band and level; pinned items unchanged; nothing free; healing at level 1
    bad = []
    def stock(i, sh):
        c = items_ed.get(i, {})
        return tuple(R.ival(c.get(f"{sh}.{lv}", facts.items[i].get(f"{sh}.{lv}", 0))) for lv in LEVELS)
    for sh in SHOPS:
        cnt_old, cnt_new = {}, {}
        for it in facts.item_list:
            i = it["label"]
            old, new = iv.stock(i, sh), stock(i, sh)
            if new != old and (i in PINNED or iv.band(i) is None or not iv.placeable(i) or iv.price(i) <= 0):
                bad.append(f"{SHOP_NAMES[sh]}: {facts.iname(i)} must keep its stock")
            for n, lv in enumerate(LEVELS):
                if old[n]:
                    cnt_old[(repr(iv.band(i)), lv)] = cnt_old.get((repr(iv.band(i)), lv), 0) + 1
                if new[n]:
                    cnt_new[(repr(iv.band(i)), lv)] = cnt_new.get((repr(iv.band(i)), lv), 0) + 1
            if any(new) and iv.price(i) <= 0:
                bad.append(f"{SHOP_NAMES[sh]}: {facts.iname(i)} sold but has no price")
        if cnt_old != cnt_new:
            diff = sorted(set(cnt_old.items()) ^ set(cnt_new.items()))[:4]
            bad.append(f"{SHOP_NAMES[sh]}: goods per band/level changed {diff}")
        heal_old = [i for i in facts.items if iv.stock(i, sh)[0] and (iv.heal_staff(i) or (facts.item_kind(i) is None and iv.sub(i) == SUB_HEAL))]
        heal_new = [i for i in facts.items if stock(i, sh)[0] and (iv.heal_staff(i) or (facts.item_kind(i) is None and iv.sub(i) == SUB_HEAL))]
        if heal_old and not heal_new:
            bad.append(f"{SHOP_NAMES[sh]}: no healing at shop level 1 any more")
    g("shops_sane", bad)
    # 5. rewards: same band, placeable, trophies and downloadable lists untouched
    bad = []
    ach = o.get("achieve") or {}
    for e in edits:
        if e["table"] in REWARD_TABLES:
            row = {R.ival(r["index"]): r for r in ach.get(e["table"], [])}.get(e["index"])
            new = e["cells"]["item"]
            if row is None:
                bad.append(f"{e['table']} {e['index']}: no such row")
                continue
            if iv.band(row["item"]) != iv.band(new) or not iv.placeable(new) or not iv.placeable(row["item"]):
                bad.append(f"{e['table']} {e['index']}: {facts.iname(row['item'])} -> {facts.iname(new)}")
    g("rewards_same_band", bad)
    return out


# ------------------------------------------------------------------ output (for this track's own robot check)
def edits_to_files(facts: R.Facts, edits: list[dict], s1files: dict[str, bytes] | None = None) -> dict[str, bytes]:
    """CSV files for the edits, merged over slice 1's files (DisposUnit rows: this track's values win, the full
    five item cells are written)."""
    import csv
    import io
    files = dict(s1files or {})
    by_table: dict[str, list[dict]] = {}
    for e in edits:
        by_table.setdefault(e["table"], []).append(e)
    for t, es in sorted(by_table.items()):
        rel = f"tables/{t}.csv"
        if t == "DisposUnit":
            rows = {}
            if rel in files:
                rd = list(csv.reader(io.StringIO(files[rel].decode("utf-8").lstrip("﻿"))))
                for r in rd[1:]:
                    rows[(r[0], int(r[1]))] = r
            for e in es:
                rows[(e["file"], e["index"])] = [e["file"], str(e["index"]), e["label"]] + \
                    [e["cells"][f"item_{s}"] for s in range(1, 6)]
            out = [["file", "index", "label"] + [f"item_{s}" for s in range(1, 6)]] + [rows[k] for k in sorted(rows)]
        else:
            cols = sorted({c for e in es for c in e["cells"]})
            out = [["index", "label"] + cols]
            for e in sorted(es, key=lambda e: e["index"]):
                if t == "Item":
                    it = facts.items[e["label"]]
                    out.append([str(e["index"]), e["label"]] + [e["cells"].get(c, it.get(c, "")) for c in cols])
                else:
                    out.append([str(e["index"]), e["label"]] + [e["cells"].get(c, "") for c in cols])
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\n").writerows(out)
        files[rel] = ("﻿" + buf.getvalue()).encode("utf-8")
    return files


def cmd_make(a) -> int:
    """Slice 1 + this track only, as one mod folder (the integrate step does the real merge in rando.py)."""
    import gamedata as GD
    facts = GD.load_facts()
    s1 = R.make_plan(facts, a.seed, {})
    opts = {"inventories": a.inventories, "shops": a.shops, "shop_sides": a.shop_sides, "rewards": a.rewards}
    full = dict(opts, slice1_plan=s1, achieve=load_achieve())
    edits, lines = plan_items(facts, sub_rng(a.seed, TRACK, opts), full)
    guards = check_items(facts, edits, full)
    files = edits_to_files(facts, edits, R.render(facts, s1))
    meta = json.loads(files["mod.json"].decode("utf-8"))
    meta["description"] += f" Plus track 'items' ({TOOL_VERSION})."
    meta["randomizer"]["items"] = {"tool": TOOL_VERSION, "opts": opts}
    files["mod.json"] = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    gl = ["", "Items guards:"] + [f"  {'PASS' if v['ok'] else 'FAIL'} {k}" + "".join(f"\n       {d}" for d in v["detail"][:8])
                                  for k, v in guards.items()]
    files["spoiler.txt"] = files["spoiler.txt"] + ("\n" + "\n".join(lines + gl) + "\n").encode("utf-8")
    files["items_plan.json"] = (json.dumps({"tool": TOOL_VERSION, "seed": s1["seed"], "opts": opts, "edits": edits,
                                            "guards": guards}, indent=1, ensure_ascii=False, sort_keys=True)
                                + "\n").encode("utf-8")
    out = os.path.join(os.path.abspath(a.out), R.mod_name(a.seed))
    R.write_mod(files, out)
    n = {t: sum(1 for e in edits if e["table"] == t) for t in sorted({e["table"] for e in edits})}
    print(f"made {out}: {n}")
    for k, v in list(s1["guards"].items()) + list(guards.items()):
        print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
    return 0 if all(v["ok"] for v in list(s1["guards"].values()) + list(guards.values())) else 2


# ------------------------------------------------------------------ robot check (one job, own folder, read only)
ROBOT_TOP = os.path.join(ROOT, "build", "rando49", "items")
STOP = os.path.join(ROOT, "build", "STOP_ROUND")


def _offsets() -> dict:
    """Record-0 offsets of the tables read in memory, from the user's own GameData (same layout with the mod: the
    mod only changes cells)."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
    import mods as M
    reg = M.reg()
    out = {}
    for n in ("Person", "Item") + REWARD_TABLES:
        t = reg[n]
        c = M.T.container(t.files()[0])
        out[n] = (M.T.locate(t, c)[0], t.size)
    return out


def _expected(facts, mod_dir: str | None) -> dict:
    """Expected memory values: items' four stock lists, the reward lists' items, and the Chapter 2 (A002) player
    placements' items. mod_dir None = the original tables."""
    import csv
    import io
    van_items = {R.ival(it["index"]): it for it in facts.item_list}
    stock = {ix: [R.ival(it.get(f"{sh}.{lv}", 0)) for sh in SHOPS for lv in LEVELS] for ix, it in van_items.items()}
    ach = load_achieve()
    rewards = {t: {R.ival(r["index"]): R.ival(facts.items[r["item"]]["index"]) if r["item"] in facts.items else -1
                   for r in ach[t]} for t in REWARD_TABLES}
    disp = {}
    for d in facts.dispos:
        if facts.chapter_of(d) == "A002" and str(d.get("team")) == "0":
            disp[(d["file"], R.ival(d["index"]))] = (d["pid"], [d.get(f"item_{s}", "") for s in range(1, 6)])
    if mod_dir:
        def rows(t):
            p = os.path.join(mod_dir, "tables", f"{t}.csv")
            if not os.path.isfile(p):
                return [], []
            rd = list(csv.reader(io.StringIO(open(p, encoding="utf-8-sig").read())))
            return rd[0], rd[1:]
        h, rs = rows("Item")
        for r in rs:
            m = dict(zip(h, r))
            ix = int(m["index"])
            stock[ix] = [R.ival(m.get(f"{sh}.{lv}", van_items[ix].get(f"{sh}.{lv}", 0))) for sh in SHOPS for lv in LEVELS]
        for t in REWARD_TABLES:
            h, rs = rows(t)
            for r in rs:
                m = dict(zip(h, r))
                rewards[t][int(m["index"])] = R.ival(facts.items[m["item"]]["index"])
        h, rs = rows("DisposUnit")
        for r in rs:
            m = dict(zip(h, r))
            k = (m["file"], int(m["index"]))
            if k in disp:
                disp[k] = (disp[k][0], [m[f"item_{s}"] for s in range(1, 6)])
    ch2 = {}
    for (_f, _i), (pid, its) in sorted(disp.items()):
        ch2.setdefault(pid, [R.ival(facts.items[i]["index"]) if i in facts.items else 0 for i in its if i])
    return {"stock": stock, "rewards": rewards, "ch2": ch2}


def _read_tables(rd, s, person_rec0: int, offs: dict, facts, exp: dict) -> dict:
    """Compare the Item stock bytes (+0x4C..+0x57) of every item and the reward lists' item (+0x4) in memory."""
    import struct
    base = person_rec0 - offs["Person"][0]
    out = {"item_rec0": f"{base + offs['Item'][0]:08x}", "mismatches": [], "checked": 0}
    for ix, want in sorted(exp["stock"].items()):
        a = base + offs["Item"][0] + ix * offs["Item"][1]
        b = s.peek1(a, offs["Item"][1])
        lab = rd.cstr(struct.unpack_from("<I", b, 8)[0])
        num = struct.unpack_from("<H", b, 0x14)[0]
        got = list(b[0x4C:0x58])
        out["checked"] += 1
        if num != ix or got != want:
            out["mismatches"].append({"index": ix, "label": lab, "number": num, "mem": got, "want": want})
    for t in REWARD_TABLES:
        for ix, want in sorted(exp["rewards"][t].items()):
            b = s.peek1(base + offs[t][0] + ix * offs[t][1], offs[t][1])
            got = struct.unpack_from("<H", b, 4)[0]
            out["checked"] += 1
            if got != want:
                out["mismatches"].append({"table": t, "index": ix, "mem": got, "want": want})
    return out


def _unit_items(s, unit_addr: int) -> list[int]:
    import struct
    b = s.peek1(unit_addr + 0x108, 20)      # five unit::Item {u16 item number, u16 bits} (Unit::GetHasItemNum)
    return [struct.unpack_from("<H", b, 4 * n)[0] for n in range(5) if struct.unpack_from("<H", b, 4 * n)[0]]


def robot_run(name: str, zakdir: str | None, exp: dict, facts, offs: dict, plan_path: str | None) -> dict:
    """One headless server run (bt-ch1-clear, the recorded bt-ch2 presses up to frame 5117, reads at 4800, 5117
    and 5300; the same frames as round 47's ch2 run). Read only."""
    import json as _j
    import shutil
    import time
    sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
    import headless as hl
    import server as sv
    import robot_check as RC
    if os.path.exists(STOP):
        raise ItemsError("build/STOP_ROUND exists: not started")
    rin = _j.load(open(os.path.join(ROOT, "config", "harness", "routes.json"), encoding="utf-8"))["routes"]["bt-ch2"]["input"]
    inp = ",".join(x for x in rin.split(",") if x and int(x.split(":")[0]) <= 5117)
    pexp = RC.expected(plan_path or "vanilla", facts)
    orig = hl.lay_save

    def lay(zip_path, data_dir):
        names = orig(zip_path, data_dir)
        assert hl.below(os.path.abspath(data_dir), ROBOT_TOP), data_dir
        if zakdir and os.path.isdir(os.path.join(zakdir, "mods")):
            shutil.copytree(os.path.join(zakdir, "mods"), os.path.join(data_dir, "mods"), dirs_exist_ok=True)
        return names

    hl.lay_save = lay
    out = {"run": name, "save": "bt-ch1-clear", "route": "bt-ch2", "last_press": 5117, "reads": []}
    t0 = time.time()
    try:
        with sv.Server(f"items49-{name}", save="bt-ch1-clear", root=os.path.join(ROBOT_TOP, "server")) as s:
            out["pid"] = s.proc.pid
            out["mods_in_data"] = sorted(os.path.relpath(os.path.join(r, f), s.data_dir).replace("\\", "/")
                                         for r, _d, fs in os.walk(os.path.join(s.data_dir, "mods")) for f in fs)
            s.inputs_set(inp)
            rd = RC.Reader(s)
            shots = os.path.join(ROBOT_TOP, "shots", name)
            os.makedirs(shots, exist_ok=True)
            for f in (4800, 5117, 5300):
                s.step_to(f)
                s.shot(os.path.join(shots, f"f{f:06d}.png"), scale=1)
                e = {"frame": f}
                try:
                    us = rd.units()
                    e["units"] = [{k: u[k] for k in ("force", "pid", "jid", "level", "x", "y")} | {"items": _unit_items(s, int(u["unit"], 16))}
                                  for u in us]
                    if us:
                        pc = RC.compare_persons(rd, int(us[0]["person"], 16), pexp)
                        e["persons"] = {"checked": pc["checked"], "mismatches": pc["mismatches"]}
                        e["tables"] = _read_tables(rd, s, int(pc["record0"], 16), offs, facts, exp)
                        bad = []
                        seen = []
                        for u in e["units"]:
                            if u["force"] == 0 and u["pid"] in exp["ch2"] and not u["pid"].startswith("PID_プレイヤー"):  # Corrin: from the save
                                seen.append(u["pid"])
                                if u["items"] != exp["ch2"][u["pid"]]:
                                    bad.append({"pid": u["pid"], "mem": u["items"], "want": exp["ch2"][u["pid"]]})
                        e["ch2_units"] = {"seen": seen, "mismatches": bad}
                except Exception as ex:  # noqa: BLE001
                    e["error"] = repr(ex)
                out["reads"].append(e)
            out["digest"] = s.state_digest()
            out["frame"] = s.frame
    finally:
        hl.lay_save = orig
    out["seconds"] = round(time.time() - t0, 1)
    return out


def cmd_robot(a) -> int:
    """mod run -> uninstall -> off run, one job, one server at a time; results build/rando49/items/robot.json."""
    import subprocess
    import gamedata as GD
    facts = GD.load_facts(names=False)
    offs = _offsets()
    mod_dir = os.path.abspath(a.mod)
    zak = os.path.join(ROBOT_TOP, "zak")
    res = {"job": "items49", "mod": mod_dir, "offsets": {k: [hex(v[0]), v[1]] for k, v in offs.items()}, "runs": []}
    path = os.path.join(ROBOT_TOP, "robot.json")

    def save():
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, ensure_ascii=False)
    mt = [sys.executable, os.path.join(ROOT, "tools", "mods", "mods.py"), "--mods-dir", os.path.dirname(mod_dir),
          "--stage-dir", os.path.join(ROBOT_TOP, "stage"), "--zakuro-dir", zak]
    res["runs"].append(robot_run("mod", zak, _expected(facts, mod_dir), facts, offs, os.path.join(mod_dir, "plan.json")))
    save()
    for c in (["uninstall"], ["disable", os.path.basename(mod_dir)]):
        r = subprocess.run(mt + c, capture_output=True, text=True, encoding="utf-8", errors="replace")
        res.setdefault("uninstall", []).append({"cmd": c, "rc": r.returncode, "out": (r.stdout + r.stderr)[-1500:]})
    left = [os.path.join(r, f) for r, _d, fs in os.walk(os.path.join(zak, "mods")) for f in fs]
    res["files_left_after_uninstall"] = len(left)
    save()
    res["runs"].append(robot_run("off", zak, _expected(facts, None), facts, offs, None))
    save()
    for r in res["runs"]:
        print(r["run"], "frame", r.get("frame"), "memory", r.get("digest", {}).get("memory"), "mods", len(r.get("mods_in_data", [])),
              f"{r['seconds']} s")
        for e in r["reads"]:
            print("  read", e["frame"], "persons mism", len((e.get("persons") or {}).get("mismatches", [])),
                  "tables checked", (e.get("tables") or {}).get("checked"), "mism", len((e.get("tables") or {}).get("mismatches", [])),
                  "ch2 units", (e.get("ch2_units") or {}).get("seen"), "mism", len((e.get("ch2_units") or {}).get("mismatches", [])),
                  e.get("error", ""))
    print("files left after uninstall:", res["files_left_after_uninstall"])
    print("result:", path)
    return 0


def main(argv=None) -> int:
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make", help="slice 1 + items as one mod folder (robot check / inspection)")
    p.add_argument("--seed", required=True)
    p.add_argument("--inventories", type=_onoff, default=True)
    p.add_argument("--shops", type=_onoff, default=True)
    p.add_argument("--shop-sides", dest="shop_sides", choices=("own", "mixed"), default="own")
    p.add_argument("--rewards", type=_onoff, default=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("robot", help="this track's one robot check (mod installed under build/rando49/items/zak)")
    p.add_argument("--mod", required=True, help="the made mod folder (already installed with mods.py)")
    a = ap.parse_args(argv)
    try:
        return cmd_make(a) if a.cmd == "make" else cmd_robot(a)
    except R.RandoError as e:
        print(f"ERROR: {e}")
        return 1


def _onoff(v: str) -> bool:
    v = v.strip().lower()
    if v in ("on", "yes", "1", "true"):
        return True
    if v in ("off", "no", "0", "false"):
        return False
    raise ValueError("on or off")


if __name__ == "__main__":
    sys.exit(main())
