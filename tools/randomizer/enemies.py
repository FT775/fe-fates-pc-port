#!/usr/bin/env python3
"""Fire Emblem Fates randomizer, track "enemies" (F-043 #1, round 49; docs/rando/ENEMIES.md).

Enemy and boss weapons (gear) and, as options, enemy and boss classes, from the map placement tables
(DisposUnit). Our own code. Public randomizers were read for facts only (their known breaks); no code copied.

    python tools/randomizer/enemies.py make --seed S [--gear on|off] [--enemy-classes on|off]
                                       [--boss-classes on|off] [--trees own|any] [--out DIR]
    python tools/randomizer/enemies.py scripted          list the units this track never changes, and why
    python tools/randomizer/enemies.py robot ...         one headless robot check (see robot_main)

The interface for the integrate step:

    plan_enemies(tables, rng, opts) -> (edits, spoiler_lines)

tables  EnemyTables (load_tables() for the real game; the tests build small made-up ones)
rng     random.Random; use track_rng(seed, opts) so this track's draws never depend on another track's
opts    DEFAULT_OPTS keys
edits   [{"table": "DisposUnit", "file", "index", "label", "column", "old", "new"}], in a fixed order
        (columns: only "jid" and "item_1".."item_5")

What it keeps (each one is a guard, re-checked by run_guards from the edits alone):
- enemy counts, positions, levels, AI, flags, difficulty bits, forge ranks, drops' slots: no other column is
  written; no row is added; items that are not weapons (gold, keys, vulneraries, seals) are never touched;
- only enemy units (team 1) of the Enemy* and Reinforce* groups of story chapters (A, B, C, X; not the E
  encounter variants); reinforcement timing is not a DisposUnit cell and is never written;
- story-scripted units are never changed (named people and story versions of them, units the chapter's
  script names, units of Event groups); bosses the script names keep their class but may get new gear;
- the four chapters where public randomizers broke (Conquest 9, Conquest 16, Revelation 8, Revelation 13):
  nothing at all is changed;
- a new class: same gender, same tier, same side (trees own), fliers stay fliers, beasts beasts; monsters,
  dragons, enemy-only, downloadable and special classes never change and are never given; the same
  village-breaking flag; can use the unit's kind of weapon role (staff users stay staff users);
- the "no stuck enemies" rule (the FE8 port's, adapted): over the chapter's own terrain grid, the new class
  must reach at least 3/4 as many tiles in 3 turns as the original class, and enter the tile the unit stands
  on at most as dearly; units off the map at start, or with no terrain file, keep their class;
- weapons: never above the rank the unit carried (generic enemies have no stored weapon exp: the game gives
  them what their level allows, so the original rank is the safe ceiling); bosses keep the same kind and
  rank (they have stored weapon exp), so every boss keeps a weapon it can use; personal, legendary,
  enemy-only, chapter-only and precious weapons stay where they are.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "enemies"
TOOL_VERSION = "rando-enemies-v1"
DEFAULT_OPTS = {"gear": True, "enemy_classes": False, "boss_classes": False, "trees": "own"}
GUARDED = {"B009": "Conquest 9 (Nyx talk)", "B016": "Conquest 16 (spare prompt)",
           "C008": "Revelation 8 (Hayato)", "C013": "Revelation 13 (obstacles)"}
STORY_FILE = re.compile(r"^[ABCX]\d{3}$")
GROUP_OK = re.compile(r"^(Enemy|Reinforce)")
REACH_TURNS = 3
REACH_RATIO = 0.75
ITEM_SLOTS = range(1, 6)
NO_CLASS_PERSON_FLAGS = ("SPID_専用地形コスト", "SPID_移動禁止")   # private terrain costs; never moves
VILLAGE_FLAG = "SPID_村破壊"
FLIER_CAT = "JCID_飛行"
EMPTY_PID = "PID_無し"
GENERIC_MAIN_PREFIXES = ("PID_魔物", "PID_捕獲")    # main-table generics share their name ids with enemies
DEFAULT_OUT = os.path.join(ROOT, "build", "rando", "out")


def flags(cell) -> set:
    return R.flags(cell)


def ival(cell) -> int:
    return R.ival(cell)


def opts_text(o: dict) -> str:
    on = lambda b: "on" if b else "off"  # noqa: E731
    return (f"gear={on(o['gear'])} enemy-classes={on(o['enemy_classes'])} boss-classes={on(o['boss_classes'])} "
            f"trees={o['trees']}")


def track_rng(seed: str, opts: dict | None = None) -> random.Random:
    """This track's own random stream from the run seed: SHA-256 of (version, track name, seed, options). Round 61:
    the boss-classes switch is written as off in the key, so turning boss classes on changes the bosses only (every
    other draw is per unit, unit_rng, and stays the same: a same-seed pair shows the boss class as the only change).
    Runs with boss classes off keep the very same key as before."""
    o = dict(DEFAULT_OPTS, **(opts or {}))
    key = "\x1f".join([TOOL_VERSION, TRACK, R.check_seed(seed), opts_text(dict(o, boss_classes=False))])
    return random.Random(int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big"))


def chapter_of(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1].split(".", 1)[0]


# ------------------------------------------------------------------ the tables
class EnemyTables:
    """Read-only view of what this track needs. All arguments are lists of CSV-cell dicts (tools/tables
    dump.py shape); scripts: {chapter (4 chars): set of PIDs the chapter's event scripts name}."""

    def __init__(self, persons, person_chapter, jobs, items, subkinds, dispos, factions, terrain_tiles,
                 terrain_grids, terrain_cost, scripts, rules=None, names=None):
        self.rules = rules or R.load_rules()
        self.f = R.Facts(persons, jobs, items, subkinds, [], self.rules, names)
        self.main_pids = {p["label"] for p in persons}
        mp: dict[str, set] = {}
        for p in persons:
            mp.setdefault(p.get("mpid_name", ""), set()).add(p["label"])
        self.named_mpids = {m for m, pids in mp.items()
                            if m and not all(x.startswith(GENERIC_MAIN_PREFIXES) for x in pids)}
        self.pc = {}
        for r in person_chapter:
            self.pc.setdefault(r["label"], r)
        self.dispos = sorted(dispos, key=lambda d: (d["file"], ival(d["index"])))
        self.group = {}
        for g in factions:
            fu = str(g.get("first_unit", ""))
            if not fu.startswith("#"):
                continue
            s = int(fu[1:])
            for i in range(s, s + ival(g["unit_count"])):
                self.group[(g["file"], i)] = g["group"]
        self.tiles = {}
        for t in terrain_tiles:
            self.tiles.setdefault(chapter_of(t["file"]), {})[ival(t["index"])] = ival(t["move_cost_column"])
        self.grids = {chapter_of(g["file"]): g for g in terrain_grids}
        self.cost = {ival(c["index"]): [ival(c[f"cost.{i}"]) for i in range(16)] for c in terrain_cost}
        self.scripts = {k: set(v) for k, v in (scripts or {}).items()}
        self._reach_cache: dict = {}
        # scope rules (F-047): from the rules' "scope" block when it has them, else the original game's
        scope = self.rules.get("scope") or {}
        self.story_file = re.compile(scope["story_file"]) if scope.get("story_file") else STORY_FILE
        self.guarded = dict(scope["guarded"]) if scope.get("guarded") is not None else dict(GUARDED)
        # round 62 (F-049): story bosses may change class too. The rules name the bosses that never do (Garon,
        # Anankos, a possessed royal, ...; ids only) and the script-named bosses a robot run took past their
        # chapter's scenes with a new class (only those change). No list = no story boss changes (Seal of
        # Flames until its own rules carry one).
        bc = self.rules.get("boss_classes") or {}
        self.boss_never = dict(bc.get("never") or {})
        self.boss_proven = set(bc.get("proven_bosses") or [])

    # -- people and classes
    def jobs(self):
        return self.f.jobs

    def unit_job(self, d: dict) -> str | None:
        if d.get("jid"):
            return d["jid"]
        p = self.pc.get(d["pid"]) or self.f.by_pid.get(d["pid"])
        return p["job"] if p else None

    def is_boss(self, d: dict) -> bool:
        p = self.pc.get(d["pid"])
        return "ボス" in d["pid"] or bool(p and str(p.get("unit_kind")) == "2")

    def kept_job(self, jid: str) -> str | None:
        """Why a class is never changed and never given (None = an ordinary class). The answer depends only on the
        tables, so it is worked out once per class (speed, docs/rando/SPEED.md)."""
        try:
            memo = self._kept_memo
        except AttributeError:
            memo = self._kept_memo = {}
        if jid not in memo:
            memo[jid] = self._kept_job(jid)
        return memo[jid]

    def _kept_job(self, jid: str) -> str | None:
        j = self.f.jobs.get(jid)
        if j is None:
            return "class not found"
        why = self.f.excluded_job(jid)
        if why:
            return why
        if ival(j["origin"]) not in (1, 2):
            return "no side (downloadable or special)"
        if not any(self.f.wexp_max(j)):
            return "no weapons"
        return None

    def attack_kinds(self, j: dict) -> list[int]:
        mx = self.f.wexp_max(j)
        return [k for k in range(8) if mx[k] > 0 and k not in (self.rules["staff_kind"], self.rules["stone_kind"])]

    # -- scope: why a unit is left alone (None = in scope)
    def out_of_scope(self, d: dict) -> str | None:
        ch = chapter_of(d["file"])
        if not self.story_file.match(ch):
            return "not a story chapter file"
        if str(d.get("team")) != "1":
            return "not an enemy"
        if not d.get("pid") or d["pid"] == EMPTY_PID:
            return "no person"
        return None

    def scripted(self, d: dict) -> str | None:
        """Why this enemy unit is story-scripted (never changed), or None. Bosses named by the script are
        reported by boss_in_script, not here."""
        ch = chapter_of(d["file"])
        g = self.group.get((d["file"], ival(d["index"])), "")
        if ch[:4] in self.guarded:
            return "guarded chapter: " + self.guarded[ch[:4]]
        if d["pid"] in self.main_pids:
            return "named person (main cast)"
        p = self.pc.get(d["pid"])
        if p is None:
            return "person not found in the chapter's people"
        if p.get("mpid_name") in self.named_mpids:
            return "story version of a named person"
        if not GROUP_OK.match(g):
            return f"group {g or '?'} (event or support)"
        if d["pid"] in self.scripts.get(ch[:4], set()) and not self.is_boss(d):
            return "named by the chapter's script"
        return None

    def boss_in_script(self, d: dict) -> bool:
        return self.is_boss(d) and d["pid"] in self.scripts.get(chapter_of(d["file"])[:4], set())

    def script_names_classes(self, d: dict) -> bool:
        """The chapter's event scripts name a class (a JID): a scene there may check or show a class."""
        return any(x.startswith("JID_") for x in self.scripts.get(chapter_of(d["file"])[:4], set()))

    def boss_class_block(self, d: dict) -> str | None:
        """Round 62: why this boss keeps its class with Boss classes on (None = it may change, tier-matched).
        Every boss may change, story bosses included, except: guarded chapters; the rules' never-change list
        (Garon, Anankos and his parts, a possessed royal, the singer when a scene needs the song); classes that
        are never changed (enemy-only forms such as dragons and the Faceless, no side); units that never move or
        have their own terrain; event groups; and a boss the chapter's script names, unless that chapter's scenes
        check no class and a robot run went past them with the new class (rules boss_classes.proven_bosses)."""
        if not self.is_boss(d):
            return "not a boss"
        ch = chapter_of(d["file"])[:4]
        if ch in self.guarded:
            return "guarded chapter: " + self.guarded[ch]
        if d["pid"] in self.boss_never:
            return self.boss_never[d["pid"]]
        old = self.unit_job(d)
        if old is None or old not in self.f.jobs:
            return "class not found"
        why = self.kept_job(old)
        if why:
            return f"its class is never changed ({why})"
        p = self.pc.get(d["pid"]) or {}
        if flags(p.get("flags", "")) & set(NO_CLASS_PERSON_FLAGS):
            return "never moves or has its own terrain costs"
        g = self.group.get((d["file"], ival(d["index"])), "")
        if not GROUP_OK.match(g):
            return f"group {g or '?'} (event or support)"
        story = (d["pid"] in self.main_pids or p.get("mpid_name") in self.named_mpids
                 or d["pid"] in self.scripts.get(ch, set()))
        if story and self.script_names_classes(d):
            return "the chapter's script names classes (a scene may check the class)"
        if story and d["pid"] not in self.boss_proven:
            return "named by the story: kept until a robot run goes past its scenes with a new class"
        return None

    # -- terrain
    def _tile_cols(self, k: str) -> dict | None:
        """{(x, y): move cost column} of every playable tile of chapter k (None: no grid), made once per chapter
        (speed, docs/rando/SPEED.md: the grid's hex text used to be parsed again for every tile looked at)."""
        try:
            return self._tcols[k]
        except AttributeError:
            self._tcols = {}
        except KeyError:
            pass
        g = self.grids.get(k)
        if g is None:
            self._tcols[k] = None
            return None
        tiles = bytes.fromhex(g["tiles"])
        tmap = self.tiles.get(k, {})
        cols = {}
        for y in range(ival(g["play_y_min"]), ival(g["play_y_end"])):
            for x in range(ival(g["play_x_min"]), ival(g["play_x_end"])):
                cols[(x, y)] = tmap.get(tiles[x | (y << 5)])
        self._tcols[k] = cols
        return cols

    def tile_col(self, ch: str, x: int, y: int) -> int | None:
        cols = self._tile_cols(ch[:4])
        if cols is None:
            return None
        return cols.get((x, y))

    def step_cost(self, jid: str, col: int | None) -> int:
        if col is None:
            return -1
        try:
            row = self._job_cost[jid]
        except AttributeError:
            self._job_cost = {}
            row = self._job_cost[jid] = self.cost.get(ival(self.f.jobs[jid]["move_cost_class"]))
        except KeyError:
            row = self._job_cost[jid] = self.cost.get(ival(self.f.jobs[jid]["move_cost_class"]))
        if row is None or col >= len(row):
            return -1
        return row[col]

    def reach(self, ch: str, x: int, y: int, jid: str) -> int:
        """Tiles a unit of class jid can reach from (x, y) in REACH_TURNS turns over the map's terrain (other
        units ignored), the start tile included."""
        key = (ch[:4], x, y, jid)
        if key in self._reach_cache:
            return self._reach_cache[key]
        j = self.f.jobs[jid]
        n = self.reach_tiles(ch, x, y, ival(j["move_cost_class"]), ival(j["mov"]))
        self._reach_cache[key] = n
        return n

    def _cost_map(self, k: str, mcc: int) -> dict:
        """{(x, y): step cost} of every tile of chapter k a unit of move cost class mcc can enter (once per pair)."""
        try:
            maps = self._cost_maps
        except AttributeError:
            maps = self._cost_maps = {}
        got = maps.get((k, mcc))
        if got is None:
            row = self.cost.get(mcc)
            got = {}
            if row is not None:
                for pos, col in (self._tile_cols(k) or {}).items():
                    if col is not None and col < len(row) and row[col] >= 0:
                        got[pos] = row[col]
            maps[(k, mcc)] = got
        return got

    def reach_tiles(self, ch: str, x: int, y: int, mcc: int, mov: int) -> int:
        """Tiles reachable from (x, y) within mov * REACH_TURNS move points with move cost class mcc, the start tile
        included (other units ignored). One answer per (chapter, tile, mcc, mov), shared by this track's no-stuck
        rule and misc.py's (speed, docs/rando/SPEED.md; the same tiles as the old search, which looked every
        neighbour up again through the grid's hex text)."""
        key = (ch[:4], x, y, mcc, mov)
        try:
            memo = self._reach_memo
        except AttributeError:
            memo = self._reach_memo = {}
        if key in memo:
            return memo[key]
        cost = self._cost_map(ch[:4], mcc)
        budget = mov * REACH_TURNS
        best = {(x, y): 0}
        q = [(0, x, y)]
        pop, push, get = heapq.heappop, heapq.heappush, cost.get
        while q:
            c, cx, cy = pop(q)
            if c > best[(cx, cy)]:
                continue
            for nb in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                sc = get(nb)
                if sc is None:
                    continue
                nc = c + sc
                if nc <= budget and nc < best.get(nb, 1 << 30):
                    best[nb] = nc
                    push(q, (nc, nb[0], nb[1]))
        memo[key] = len(best)
        return len(best)

    def terrain_ok(self, d: dict, old: str, new: str) -> str | None:
        """None when class new passes the no-stuck rule where d stands; else why not."""
        ch = chapter_of(d["file"])
        x, y = ival(d["pos.x"]), ival(d["pos.y"])
        col = self.tile_col(ch, x, y)
        if col is None:
            return "no terrain known for the unit's tile"
        co, cn = self.step_cost(old, col), self.step_cost(new, col)
        if cn < 0:
            return "cannot stand on its tile"
        if co >= 0 and cn > co:
            return f"its tile costs {cn} instead of {co}"
        ro, rn = self.reach(ch, x, y, old), self.reach(ch, x, y, new)
        if rn < REACH_RATIO * ro:
            return f"reaches {rn} tiles in {REACH_TURNS} turns instead of {ro}"
        return None

    # -- items
    def special_item(self, iid: str) -> bool:
        it = self.f.items.get(iid)
        if it is None:
            return True
        itf = flags(it["flags"])
        return bool(itf & set(self.rules["replacement_refuse_item_flags"])) or any("専用" in x for x in itf)

    def weapon_slots(self, d: dict) -> list[tuple[int, str, int, int]]:
        """(slot, item, kind, rank) of every weapon, staff or stone the unit carries."""
        out = []
        for s in ITEM_SLOTS:
            iid = d.get(f"item_{s}", "")
            k = self.f.item_kind(iid)
            if k is not None:
                out.append((s, iid, k, self.f.item_rank(iid)))
        return out

    def can_hold(self, jid: str, female: bool, iid: str) -> bool:
        """Whether a unit of class jid (female or not) can use item iid; once per (class, sex, item): the answer
        depends only on the tables (speed, docs/rando/SPEED.md)."""
        try:
            memo = self._hold_memo
        except AttributeError:
            memo = self._hold_memo = {}
        key = (jid, female, iid)
        got = memo.get(key)
        if got is None:
            got = memo[key] = self._can_hold(jid, female, iid)
        return got

    def _can_hold(self, jid: str, female: bool, iid: str) -> bool:
        k = self.f.item_kind(iid)
        if k is None:
            return True
        j = self.f.jobs[jid]
        if self.f.wexp_max(j)[k] < max(self.f.item_rank(iid), 1):
            return False
        fake = {"flags": "SPID_女性" if female else ""}
        return self.f.class_can_hold(jid, fake, iid, [255] * 8, need_exp=False) is None


# ------------------------------------------------------------------ class candidates
def class_candidates(t: EnemyTables, d: dict, old: str, trees: str, boss: bool) -> list[str]:
    """Every class the unit may be given (before the terrain rule), in Job index order. The answer depends only on
    the tables, the class, the options and the unit's items, so it is worked out once per such set (speed,
    docs/rando/SPEED.md)."""
    try:
        memo = t._cand_memo
    except AttributeError:
        memo = t._cand_memo = {}
    key = (old, trees, bool(boss), tuple(d.get(f"item_{s}", "") for s in ITEM_SLOTS))
    got = memo.get(key)
    if got is None:
        got = memo[key] = _class_candidates(t, d, old, trees, boss)
    return list(got)


def _class_candidates(t: EnemyTables, d: dict, old: str, trees: str, boss: bool) -> list[str]:
    oj = t.f.jobs[old]
    fem, tier = t.f.female(oj), t.f.promoted(oj)
    ocat, oflag = flags(oj["category"]), flags(oj["flags"])
    beast = t.rules["beast_job_category"]
    weapons = t.weapon_slots(d)
    staff_k, stone_k = t.rules["staff_kind"], t.rules["stone_kind"]
    out = []
    for j in t.f.job_list:
        jid = j["label"]
        if jid == old or t.kept_job(jid):
            continue
        cat, jf = flags(j["category"]), flags(j["flags"])
        if t.f.female(j) != fem or t.f.promoted(j) != tier:
            continue
        if (FLIER_CAT in cat) != (FLIER_CAT in ocat) or (beast in cat) != (beast in ocat):
            continue
        if (VILLAGE_FLAG in jf) != (VILLAGE_FLAG in oflag):
            continue
        if trees == "own" and ival(j["origin"]) != ival(oj["origin"]):
            continue
        if bool(t.attack_kinds(j)) != bool(t.attack_kinds(oj)):
            continue
        mx = t.f.wexp_max(j)
        ok = True
        for _s, iid, k, rank in weapons:
            if not t.can_hold(old, fem, iid):
                continue                                # carried but not usable (a drop): left as it is
            if t.special_item(iid) or k == stone_k or boss:
                ok = t.can_hold(jid, fem, iid)          # kept as it is: the class must use it
            elif k == staff_k:
                ok = mx[staff_k] >= rank
            else:
                ok = any(mx[kk] >= rank for kk in t.attack_kinds(j))
            if not ok:
                break
        if ok:
            out.append(jid)
    return out


# ------------------------------------------------------------------ the plan
def unit_rng(base: int, purpose: str, d: dict) -> random.Random:
    key = f"{base}\x1f{TRACK}\x1f{purpose}\x1f{d['file']}#{ival(d['index'])}"
    return random.Random(int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big"))


def pick_weapon(t: EnemyTables, r: random.Random, jid: str, female: bool, iid: str, kind: int, rank: int,
                boss: bool) -> str:
    """A new weapon for one slot: an ordinary weapon of the same rank (or the next lower one) of a kind the class
    can use; bosses: the same kind and rank. The old weapon when nothing fits or it is special."""
    if t.special_item(iid):
        return iid
    j = t.f.jobs[jid]
    mx = t.f.wexp_max(j)
    origin = ival(j["origin"])
    if boss:
        kinds = [kind]
    elif kind == t.rules["staff_kind"]:
        kinds = [kind]
    elif kind == t.rules["stone_kind"]:
        return iid
    else:
        kinds = t.attack_kinds(j)
    ranks = [rank] + sorted((x for x in R.RANKS if x < rank), reverse=True)
    if boss:
        ranks = [rank]
    for rk in ranks:
        ks = [k for k in kinds if mx[k] >= max(rk, 1)]
        r.shuffle(ks)
        for k in ks:
            cands = [c for c in t.f.replacement_items(k, rk, origin) if t.can_hold(jid, female, c)]
            if cands:
                return r.choice(cands)
    return iid


def plan_enemies(tables: EnemyTables, rng: random.Random, opts: dict | None = None):
    """(edits, spoiler_lines) for this track. See the module text for every rule."""
    t = tables
    o = dict(DEFAULT_OPTS, **(opts or {}))
    if o["trees"] not in ("own", "any"):
        raise R.RandoError("trees: own or any")
    base = rng.getrandbits(128)
    edits: list[dict] = []
    spoil: list[str] = []
    counts = {"units": 0, "classes": 0, "weapons": 0, "kept_terrain": 0, "scripted": 0}
    for d in t.dispos:
        if t.out_of_scope(d):
            continue
        why = t.scripted(d)
        story_boss = bool(why) and o["boss_classes"] and t.is_boss(d) and t.boss_class_block(d) is None
        if why:
            counts["scripted"] += 1
            if not story_boss:
                continue
        else:
            counts["units"] += 1
        boss = t.is_boss(d)
        old = t.unit_job(d)
        if old is None or old not in t.f.jobs:
            continue
        new = old
        p = t.pc.get(d["pid"]) or {}
        want = o["boss_classes"] if boss else o["enemy_classes"]
        note = ""
        if boss and want:
            ok = t.boss_class_block(d) is None
        else:
            ok = want and not t.boss_in_script(d) and not t.kept_job(old) \
                and not (flags(p.get("flags", "")) & set(NO_CLASS_PERSON_FLAGS))
        if ok:
            cands = class_candidates(t, d, old, "own" if boss else o["trees"], boss)   # bosses: own side
            r = unit_rng(base, "class", d)
            r.shuffle(cands)
            for c in cands:
                if t.terrain_ok(d, old, c) is None:
                    new = c
                    break
            if new == old and cands:
                counts["kept_terrain"] += 1
                note = " (class kept: no class passed the terrain rule here)"
        fem = t.f.female(t.f.jobs[old])
        row_edits = []
        if new != old:
            row_edits.append(("jid", d.get("jid", ""), new))
        if (o["gear"] or new != old) and not story_boss:
            r = unit_rng(base, "gear", d)
            for s, iid, k, rank in t.weapon_slots(d):
                if not t.can_hold(old, fem, iid):
                    continue                        # the original class cannot use it either: a drop, kept
                if not o["gear"] and t.can_hold(new, fem, iid):
                    continue                        # gear off: only weapons the new class cannot use
                ni = pick_weapon(t, r, new, fem, iid, k, rank, boss)
                if ni != iid:
                    row_edits.append((f"item_{s}", iid, ni))
        if not row_edits:
            continue
        ch = chapter_of(d["file"])
        bits = []
        for col, a, b in row_edits:
            edits.append({"table": "DisposUnit", "file": d["file"], "index": ival(d["index"]),
                          "label": d.get("label", ""), "column": col, "old": a, "new": b})
            if col == "jid":
                counts["classes"] += 1
                bits.append(f"class {t.f.jname(old)} -> {t.f.jname(b)}")
            else:
                counts["weapons"] += 1
                bits.append(f"{t.f.iname(a)} -> {t.f.iname(b)}")
        spoil.append(f"{ch} unit {ival(d['index'])} ({'story boss ' if story_boss else 'boss ' if boss else ''}"
                     f"{t.f.name(p.get('mpid_name', '')) if p else d['pid']}"
                     f" at {d['pos.x']},{d['pos.y']}): " + "; ".join(bits) + note)
    head = [f"Enemies ({opts_text(o)}): {counts['units']} enemy units in scope, {counts['scripted']} story-scripted "
            f"or guarded left alone; {counts['classes']} new classes, {counts['weapons']} weapons changed, "
            f"{counts['kept_terrain']} kept their class because no class passed the terrain rule."]
    return edits, head + spoil


# ------------------------------------------------------------------ guards (from the edits alone)
def run_guards(t: EnemyTables, edits: list[dict], opts: dict | None = None) -> dict:
    o = dict(DEFAULT_OPTS, **(opts or {}))
    by = {(d["file"], ival(d["index"])): d for d in t.dispos}
    rows: dict[tuple, dict] = {}
    out: dict[str, dict] = {}

    def g(name, bad):
        out[name] = {"ok": not bad, "detail": bad[:50]}

    bad = []
    for e in edits:
        key = (e["file"], e["index"])
        d = by.get(key)
        if e["table"] != "DisposUnit" or d is None:
            bad.append(f"{key}: not a DisposUnit row")
            continue
        if e["column"] not in ("jid",) + tuple(f"item_{s}" for s in ITEM_SLOTS):
            bad.append(f"{key}: column {e['column']}")
        if str(d.get(e["column"], "")) != str(e["old"]):
            bad.append(f"{key}: old value differs")
        rows.setdefault(key, dict(d))[e["column"]] = e["new"]
    g("only_jid_and_item_cells", bad)
    bad = []
    for k in rows:
        why = t.out_of_scope(by[k]) or t.scripted(by[k])
        if not why:
            continue
        cols = {e["column"] for e in edits if (e["file"], e["index"]) == k}
        if (not t.out_of_scope(by[k]) and o["boss_classes"] and t.is_boss(by[k]) and cols == {"jid"}
                and t.boss_class_block(by[k]) is None):
            continue                        # round 62: a story boss's class (only), where the rules allow it
        bad.append(f"{k}: {why}")
    g("only_unscripted_enemies", bad)
    g("guarded_chapters_unchanged", [f"{k}" for k in rows if chapter_of(k[0])[:4] in t.guarded])
    bad = []
    for k, nd in rows.items():
        d = by[k]
        old, new = t.unit_job(d), (nd.get("jid") or t.unit_job(d))
        boss = t.is_boss(d)
        fem = t.f.female(t.f.jobs[old])
        if new != old:
            if boss and t.boss_class_block(d):
                bad.append(f"{k}: class of a boss that must keep it changed ({t.boss_class_block(d)})")
            elif not boss and t.boss_in_script(d):
                bad.append(f"{k}: class of a unit named by the script changed")
            if not (o["boss_classes"] if boss else o["enemy_classes"]):
                bad.append(f"{k}: class changed with the option off")
            if boss and (t.f.promoted(t.f.jobs[new]) != t.f.promoted(t.f.jobs[old])
                         or ival(t.f.jobs[new]["origin"]) != ival(t.f.jobs[old]["origin"])
                         or t.f.female(t.f.jobs[new]) != t.f.female(t.f.jobs[old])):
                bad.append(f"{k}: boss class {old} -> {new} is not the same tier, side and gender")
            if new not in class_candidates(t, d, old, "own" if boss else o["trees"], boss):
                bad.append(f"{k}: {new} is not a legal class here")
            why = t.terrain_ok(d, old, new)
            if why:
                bad.append(f"{k}: terrain rule: {why}")
        for s in ITEM_SLOTS:
            a, b = d.get(f"item_{s}", ""), nd.get(f"item_{s}", "")
            if a == b:
                if t.f.item_kind(a) is not None and t.can_hold(old, fem, a) and not t.can_hold(new, fem, a):
                    bad.append(f"{k} slot {s}: kept {a} cannot be used by {new}")
                continue
            ka, kb = t.f.item_kind(a), t.f.item_kind(b)
            if ka is None or kb is None:
                bad.append(f"{k} slot {s}: a non-weapon slot changed")
                continue
            if not t.can_hold(old, fem, a):
                bad.append(f"{k} slot {s}: a weapon the unit could not use (a drop) was replaced")
            if t.special_item(a):
                bad.append(f"{k} slot {s}: a special weapon was replaced")
            if not t.can_hold(new, fem, b):
                bad.append(f"{k} slot {s}: {b} cannot be used by {new}")
            if t.f.item_rank(b) > t.f.item_rank(a):
                bad.append(f"{k} slot {s}: rank went up")
            if (ka == t.rules["staff_kind"]) != (kb == t.rules["staff_kind"]):
                bad.append(f"{k} slot {s}: staff and weapon swapped")
            if boss and (ka != kb or t.f.item_rank(a) != t.f.item_rank(b)):
                bad.append(f"{k} slot {s}: a boss weapon changed kind or rank")
    g("legal_class_weapons_terrain", bad)
    bad = []
    for k, nd in rows.items():
        d = by[k]
        if not t.is_boss(d):
            continue
        new = nd.get("jid") or t.unit_job(d)
        fem = t.f.female(t.f.jobs[t.unit_job(d)])
        had = [i for _s, i, _k, _r in t.weapon_slots(d)]
        has = [nd.get(f"item_{s}", "") for s in ITEM_SLOTS if t.f.item_kind(nd.get(f"item_{s}", "")) is not None]
        if had and not any(t.can_hold(new, fem, i) for i in has):
            bad.append(f"{k}: boss has no usable weapon")
    g("bosses_keep_a_usable_weapon", bad)
    return out


# ------------------------------------------------------------------ loading the real game (read only)
def script_pids(romfs: str) -> dict[str, set]:
    """{chapter: PIDs (and, round 62, JIDs: a class a scene may check) named in that chapter's event scripts
    (Scripts/**/<chapter>*.cmb)}."""
    out: dict[str, set] = {}
    top = os.path.join(romfs, "Scripts")
    for dp, _dn, fs in os.walk(top):
        for fn in fs:
            if not fn.endswith(".cmb"):
                continue
            with open(os.path.join(dp, fn), "rb") as fh:
                data = fh.read()
            s = out.setdefault(fn[:4], set())
            for m in re.finditer(rb"(?:PID|JID)_[^\x00]{1,60}", data):     # round 62: classes too
                try:
                    s.add(m.group().decode("cp932"))
                except UnicodeDecodeError:
                    pass
    return out


def load_tables(names: bool = True) -> EnemyTables:
    import gamedata as GD
    why = GD.available()
    if why:
        raise R.RandoError(f"the game's tables are not available: {why}")
    nm = {}
    if names:
        try:
            M = GD.M
            van = M.TX.archive(M.NAME_ARCHIVE, M.ROMFS)
            for lab, _v, a in van.entries:
                if not a:
                    nm[lab.decode("cp932", "replace")] = van.text_of[lab]
        except Exception:  # noqa: BLE001
            nm = {}
    L = GD._load
    return EnemyTables(L("Person", only_first=True), L("PersonChapter"), L("Job"), L("Item"), L("ItemSubKind"),
                       L("DisposUnit"), L("DisposFaction"), L("TerrainTile"), L("TerrainGrid"), L("TerrainCost"),
                       script_pids(GD.M.ROMFS), R.load_rules(), nm)


def scripted_list(t: EnemyTables) -> list[tuple[str, int, str, str]]:
    """(chapter, unit index, pid, reason) of every enemy unit of a story chapter this track leaves alone,
    plus bosses named by the script (gear only)."""
    out = []
    for d in t.dispos:
        if t.out_of_scope(d):
            continue
        why = t.scripted(d)
        if why:
            out.append((chapter_of(d["file"]), ival(d["index"]), d["pid"], why))
        elif t.boss_in_script(d):
            out.append((chapter_of(d["file"]), ival(d["index"]), d["pid"], "boss named by the script: gear only"))
    return out


# ------------------------------------------------------------------ output: a mod folder
def render(t: EnemyTables, seed: str, o: dict, edits: list[dict], spoil: list[str], guards: dict) -> dict:
    import csv
    import io
    cols = ["jid"] + [f"item_{s}" for s in ITEM_SLOTS]
    by = {(d["file"], ival(d["index"])): d for d in t.dispos}
    rows: dict[tuple, dict] = {}
    for e in edits:
        rows.setdefault((e["file"], e["index"]), {})[e["column"]] = e["new"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["file", "index", "label"] + cols)
    for k in sorted(rows):
        d = by[k]
        w.writerow([k[0], str(k[1]), d.get("label", "")] + [rows[k].get(c, d.get(c, "")) for c in cols])
    name = R.mod_name(seed) + "-enemies"
    meta = {"name": name, "description": f"Randomizer track enemies, seed {seed} ({opts_text(o)}). "
            "For one randomized save only; see docs/rando/ENEMIES.md.", "enabled": True, "order": 110,
            "override": False, "randomizer": {"tool": TOOL_VERSION, "track": TRACK, "seed": seed, "options": o}}
    plan = {"tool": TOOL_VERSION, "track": TRACK, "seed": seed, "options": o, "edits": edits,
            "guards": guards}
    sp = ["Fire Emblem Fates randomizer - spoiler log, track enemies", f"seed: {seed}", f"options: {opts_text(o)}",
          ""] + spoil + ["", "Guards:"]
    for k, v in guards.items():
        sp.append(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
        sp += [f"       {x}" for x in v["detail"][:12]]
    files = {"mod.json": (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
             "spoiler-enemies.txt": ("\n".join(sp) + "\n").encode("utf-8"),
             "plan-enemies.json": (json.dumps(plan, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")}
    if rows:
        files["tables/DisposUnit.csv"] = ("﻿" + buf.getvalue()).encode("utf-8")
    return files


def cmd_make(a) -> int:
    o = {"gear": a.gear, "enemy_classes": a.enemy_classes, "boss_classes": a.boss_classes, "trees": a.trees}
    seed = R.check_seed(a.seed)
    t = load_tables()
    edits, spoil = plan_enemies(t, track_rng(seed, o), o)
    guards = run_guards(t, edits, o)
    files = render(t, seed, o, edits, spoil, guards)
    out_top = os.path.abspath(a.out or DEFAULT_OUT)
    for env in ("APPDATA", "LOCALAPPDATA"):
        top = os.environ.get(env)
        if top and os.path.normcase(out_top + os.sep).startswith(os.path.normcase(os.path.realpath(top)) + os.sep):
            raise R.RandoError(f"refused: {out_top} is inside %{env}%")
    if os.path.normcase(out_top + os.sep).startswith(os.path.normcase(os.path.join(ROOT, "mods")) + os.sep):
        raise R.RandoError("refused: the owner's mods/ folder")
    folder = R.write_mod(files, os.path.join(out_top, R.mod_name(seed) + "-enemies"))
    print(f"made {folder}")
    print(" ", spoil[0])
    for k, v in guards.items():
        print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
    return 0 if all(v["ok"] for v in guards.values()) else 2


def cmd_scripted(a) -> int:
    t = load_tables(names=False)
    rows = scripted_list(t)
    by: dict[str, int] = {}
    for ch, ix, pid, why in rows:
        key = re.sub(r"[0-9]+", "NN", why.split(":")[0])
        by[key] = by.get(key, 0) + 1
        if a.all or ch[:4] in t.guarded:
            print(f"{ch} {ix:3d} {pid}  {why}")
    for k, v in sorted(by.items()):
        print(f"{v:5d}  {k}")
    return 0


# ------------------------------------------------------------------ robot check (one headless job)
def robot_main(argv: list[str]) -> int:
    """robot SEED MODS_DIR ZAKDIR RUN:SAVE:ROUTE:LAST:READ ...  -> build/rando49/enemies/robot.json

    Reads (never writes) the enemy units on the map from the robot's own test game with the mod folder of
    ZAKDIR (built and installed by the caller): class, items and weapon exp of every force-1 unit, matched to
    DisposUnit rows by person and position, against the expected cells (the plan's edits on the original).
    STOP_ROUND is checked before every game start."""
    import struct
    sys.path.insert(0, os.path.join(ROOT, "tools", "harness"))
    import shutil
    import time
    import headless as hl
    import server as sv
    import robot_check as RC
    seed, mods_dir, zakdir = argv[:3]
    top = os.path.join(ROOT, "build", "rando49", "enemies")
    t = load_tables(names=False)
    plan = None
    pj = os.path.join(mods_dir, R.mod_name(seed) + "-enemies", "plan-enemies.json")
    if os.path.exists(pj):
        with open(pj, encoding="utf-8") as fh:
            plan = json.load(fh)
    want: dict[tuple, dict] = {}
    for e in (plan or {}).get("edits", []) if zakdir != "none" else []:
        want.setdefault((e["file"], e["index"]), {})[e["column"]] = e["new"]
    jix = {lab: ival(j["index"]) for lab, j in t.f.jobs.items()}
    iix = {ival(i["index"]): lab for lab, i in t.f.items.items()}
    res = {"seed": seed, "zakdir": zakdir, "runs": []}
    out_path = os.path.join(top, "robot.json" if zakdir != "none" else "robot-none.json")
    for spec in argv[3:]:
        if os.path.exists(os.path.join(ROOT, "build", "STOP_ROUND")):
            res["stopped"] = "build/STOP_ROUND exists"
            break
        name, save, route, last, reads = spec.split(":")[:5]
        reads = [int(x) for x in reads.split("/") if x]
        chapter = name.split("-")[-1]
        rin = json.load(open(os.path.join(ROOT, "config", "harness", "routes.json"), encoding="utf-8"))["routes"][route]["input"]
        inp = ",".join(x for x in rin.split(",") if x and int(x.split(":")[0]) <= int(last))
        orig = hl.lay_save

        def lay(zip_path, data_dir, _z=zakdir):
            names_ = orig(zip_path, data_dir)
            assert hl.below(os.path.abspath(data_dir), top), data_dir
            if _z != "none" and os.path.isdir(os.path.join(_z, "mods")):
                shutil.copytree(os.path.join(_z, "mods"), os.path.join(data_dir, "mods"), dirs_exist_ok=True)
            return names_

        hl.lay_save = lay
        run = {"run": name, "chapter": chapter, "reads": []}
        t0 = time.time()
        try:
            with sv.Server(f"e49-{name}", save=save, root=os.path.join(top, "server")) as s:
                run["mods_in_data"] = sorted(os.path.relpath(os.path.join(r, f), s.data_dir).replace("\\", "/")
                                             for r, _d, fs in os.walk(os.path.join(s.data_dir, "mods")) for f in fs)
                s.inputs_set(inp)
                rd = RC.Reader(s)
                for f in sorted(set(reads)):
                    s.step_to(f)
                    os.makedirs(os.path.join(top, "shots"), exist_ok=True)
                    s.shot(os.path.join(top, "shots", f"{name}-f{f:06d}.png"), scale=1)
                    entry = {"frame": f, "units": [], "mismatches": [], "matched": 0}
                    us = rd.units(forces=(1,))
                    rows = [d for d in t.dispos if chapter_of(d["file"]) == chapter and str(d["team"]) == "1"]
                    for u in us:
                        ub = s.peek1(int(u["unit"], 16), 0x120)
                        items = [struct.unpack_from("<HH", ub, 0x108 + 4 * i) for i in range(5)]
                        u["items"] = [iix.get(a, str(a)) if a else "" for a, _b in items]
                        u["equipped"] = [bool(b & 0x4000) for _a, b in items]
                        u["wexp"] = list(ub[0xE8:0xF0])
                        cand = [d for d in rows if d["pid"] == u["pid"] and ival(d["pos.x"]) == u["x"]
                                and ival(d["pos.y"]) == u["y"] and ival(d["flags"]) & 0x100]
                        if len(cand) != 1:
                            u["match"] = f"{len(cand)} rows"
                            entry["units"].append(u)
                            continue
                        d = cand[0]
                        exp = dict(d, **want.get((d["file"], ival(d["index"])), {}))
                        ej = exp.get("jid") or t.unit_job(d)
                        # slots whose Normal forge byte is negative are not given on Normal (Unit::SetDisposItem)
                        eitems = [exp.get(f"item_{i}", "") if ival(d.get(f"item_{i}_forge.normal", 0) or 0) >= 0 else ""
                                  for i in ITEM_SLOTS]
                        u["match"] = f"{d['file']}#{d['index']}"
                        u["changed"] = (d["file"], ival(d["index"])) in want
                        u["expect"] = {"jid": ej, "items": eitems}
                        diff = []
                        if u["job"] != jix.get(ej):
                            diff.append(f"class {u['jid']} != {ej}")
                        if [x for x in u["items"] if x] != [x for x in eitems if x]:
                            diff.append(f"items {u['items']} != {eitems}")
                        # can the unit use the weapons it holds? (CanItemEquip with its own rank)
                        jrow = t.f.jobs.get(u["jid"])
                        unusable = []
                        for iid in u["items"]:
                            k = t.f.item_kind(iid) if iid else None
                            if k is None or jrow is None:
                                continue
                            reach = min(u["wexp"][k], t.f.wexp_max(jrow)[k])
                            if reach < t.f.item_rank(iid) and not t.special_item(iid):
                                unusable.append(iid)
                        u["unusable"] = unusable
                        if unusable:
                            diff.append(f"cannot use {unusable}")
                        entry["matched"] += 1
                        if diff:
                            entry["mismatches"].append(f"{u['match']} {u['pid']}: " + "; ".join(diff))
                        entry["units"].append(u)
                    run["reads"].append(entry)
                run["digest"] = s.state_digest()
        finally:
            hl.lay_save = orig
        run["seconds"] = round(time.time() - t0, 1)
        res["runs"].append(run)
        os.makedirs(top, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, ensure_ascii=False, default=str)
    for r in res["runs"]:
        for e in r["reads"]:
            ch = sum(1 for u in e["units"] if u.get("changed"))
            print(r["run"], "frame", e["frame"], "enemy units", len(e["units"]), "matched", e["matched"],
                  "changed", ch, "mismatches", len(e["mismatches"]))
            for m in e["mismatches"][:20]:
                print("   ", m)
        print("  digest", r.get("digest", {}).get("memory", "")[:16], "mods", len(r.get("mods_in_data", [])))
    print("result:", out_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "robot":
        return robot_main(argv[1:])
    import rando
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make")
    p.add_argument("--seed", required=True)
    p.add_argument("--gear", type=rando.onoff, default=True)
    p.add_argument("--enemy-classes", dest="enemy_classes", type=rando.onoff, default=False)
    p.add_argument("--boss-classes", dest="boss_classes", type=rando.onoff, default=False)
    p.add_argument("--trees", choices=("own", "any"), default="own")
    p.add_argument("--out")
    p = sub.add_parser("scripted")
    p.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    try:
        return cmd_make(a) if a.cmd == "make" else cmd_scripted(a)
    except R.RandoError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
