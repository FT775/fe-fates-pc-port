#!/usr/bin/env python3
"""Randomizer track "stats" (round 56, owner 2026-11-20 "build the other missing parts too"; docs/rando/STATS.md):
class growths and class bases with variance, enemy growths and enemy levels, and boss stats. The FE8 port's rows
'Class growths', 'Class bases', 'Enemy growths' + 'Enemy buff', 'Boss stats' + 'Boss max boost', in Fates terms.

    plan_stats(tables, rng, opts) -> (edits, spoiler_lines)

tables  a StatsTables (load_tables() for the user's own game; the tests build small made-up ones). Every fact the
        track needs comes from it: the Job rows, the resident Person rows, the per-chapter Person rows
        (PersonChapter), the placements (DisposUnit), which rows are bosses and where a chapter sits in its story.
        Nothing about one particular game (Fates' three routes, Seal of Flames) is hard-coded: a different story
        passes its own rows, its own chapter_order and, if its bosses are not named the Fates way, its own boss list
        (F-047)
rng     the run seed (text, as given to rando.py) or a random.Random; this track derives its OWN sub-seed from it
        and the track name, then one stream per (purpose, row), so no other track's draws move
opts    DEFAULT_OPTS keys

edits   [{"table": "Job", "index": 9, "label": "JID_..", "cell": "growth.str", "old": "15", "new": "20"},
         {"table": "PersonChapter", "file": "GameData/Person/A/A010.bin.lz", "index": 3, "label": "PID_..",
          "cell": "base.def", "old": "4", "new": "7"}, ...]
        only cells whose value changes, in a fixed order. Cells written:
          Job.growth.*         class growths: the game adds them to a player character's personal growth
                               (Unit::GetGrow when Person.unit_kind == 1)
          Job.base.*           class bases: added to every unit's personal base in that class (Unit::Get*Impl)
          Job.enemy_growth.*   the growths every other unit levels with (unit_kind != 1: enemies, other armies,
                               and the automatic level gains of generic units, Unit::CaclulateAutoGrowCapability)
          PersonChapter.level  generic enemies' level (unit_kind 0: the automatic gains count level - 1)
          PersonChapter.base.* boss stats
Default opts are all off: NO edits, so a default run stays byte-identical.

Options (all "off" / 0 by default)
    class_growths   off | delta       each class growth moves up or down by up to class_growth_variance (steps of
                                      5), kept within 0..class_growth_max; a male/female pair of one class gets the
                                      same draw
    class_bases     off | delta       each class base moves by up to class_base_variance, kept within 0..the class
                                      maximum; HP class bases never go down (no unit can reach 0 HP through this)
    enemy_growths   off | flat | scaling   flat adds enemy_buff to every enemy growth, scaling adds enemy_buff % of
                                      it (the FE8 port's Enemy growths + Enemy buff); rounded to steps of 5, at most 125
    enemy_levels    0..5              generic enemies (unit_kind 0 rows used only by enemy units) gain this many
                                      levels, up to level 20, and a promoted one never crosses level 10 -> 11 (the
                                      placement item flags give some items only at promoted level <= 10 or >= 11)
    boss_stats      off | linear | ease   bosses gain stats, more the later their chapter is in its story (the FE8
                                      port's formula); boss_max_boost (1..20, 5) is the most one stat gains
    boss_variance   0..5              each boss stat also moves by up to this many points either way

Guards (run_guards; each has a test in tests/test_rando_stats.py): only the cells above are written; every value
fits its cell; growths are multiples of 5; class growths within 0..max and within the variance; class bases within
0..class maximum and within the variance, HP never lower; enemy growths exactly the FE8 formula; enemy levels only
on generic enemy rows, never above 20, never across promoted level 10/11, never more than enemy_levels; boss stats
only on boss rows of people who never join the army, each stat moved by at most boss_max_boost up and boss_variance
down, never below 0 (HP 1) or above the class maximum + the person's limit modifier, and each stat's gain at most
the story-position buff of the boss's chapter + boss_variance (boss_gain_follows_story); off = no edits.

Our own code. The formulas follow our own FE8 port (port/reforged/reforged_rando.c ApplyEnemyGrowth,
reforged_rando_classes.c BossBuffAmount; a sister project). Public Fates randomizers (GPL) were not used.

    python tools/randomizer/stats.py make --seed S [--class-growths delta] [--class-growth-variance 10]
        [--class-bases delta] [--class-base-variance 2] [--enemy-growths flat|scaling] [--enemy-buff 10]
        [--enemy-levels N] [--boss-stats linear|ease] [--boss-max-boost 5] [--boss-variance N] --out DIR
        this track alone as one mod folder below build/ (tables/Job.csv, tables/PersonChapter.csv)
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "stats"
TOOL = "rando-stats-v1"
STEP = 5
GROWTH_TOP = 125               # Job growth cells are signed bytes; the randomizer keeps every growth <= 125
LEVEL_TOP = 20                 # a generic enemy's level never goes above this
PROMOTED_GATE = 10             # DisposUnit item flags bit 3 / bit 4: promoted level <= 10 / >= 11
BOSS_TAG = "ボス"              # Fates names its generic boss rows PID_<chapter>_ボス (the tables can pass others)
CLASS_MODES = ("off", "delta")
ENEMY_MODES = ("off", "flat", "scaling")
BOSS_MODES = ("off", "linear", "ease")
DEFAULT_OPTS = {"class_growths": "off", "class_growth_variance": 10, "class_growth_max": 60,
                "class_bases": "off", "class_base_variance": 2,
                "enemy_growths": "off", "enemy_buff": 10, "enemy_levels": 0,
                "boss_stats": "off", "boss_max_boost": 5, "boss_variance": 0, "difficulty": "normal"}
# round 62 (F-049, Grok's plan docs/collab/OWNER_PICKS_R61_GROK.md): tougher bosses also get 10% more HP per
# difficulty step (Easy 1, Normal 2, Hard 3; the weapon part, +1 shown might per step, is a forge in weapons.py by the game's own forge rule; round 63, docs/rando/BOSS_MIGHT.md),
# and boss rows of people who join the army on another route get that same boost (chapter row only) on the routes
# the rules name (rules.json "army_boss_boost_routes"; Fates: Conquest)
DIFFICULTY_STEP = {"easy": 1, "normal": 2, "hard": 3}
HP_BOOST_PCT = 10
NUMBERS = {"class_growth_variance": (0, 50), "class_growth_max": (0, GROWTH_TOP), "class_base_variance": (1, 5),
           "enemy_buff": (0, 100), "enemy_levels": (0, 5), "boss_max_boost": (1, 20), "boss_variance": (0, 5)}
CHAPTER = re.compile(r"^([A-Z])(\d{3})")


def ival(cell) -> int:
    return R.ival(cell)


def chapter_of(path: str) -> str:
    """'GameData/Person/A/A010.bin.lz' -> 'A010' (the chapter key; placements A010E share it)."""
    base = path.replace("\\", "/").rsplit("/", 1)[-1].split(".", 1)[0]
    return base[:4]


# ------------------------------------------------------------------ the tables object (F-047)
class StatsTables:
    """Read-only view of what this track needs. persons: resident Person rows; person_chapter: PersonChapter rows
    (with "file"); jobs: Job rows; dispos: DisposUnit rows (with "file"); rules: config/randomizer/rules.json.
    chapter_order: optional {chapter key: story fraction 0..1}; by default A/B/C + 3 digits is number / the largest
    number of that letter, anything else 0.5. boss_pids: optional set of PersonChapter labels that are bosses
    (default: label contains ボス, or unit_kind 2 placed only on the enemy team)."""

    def __init__(self, persons, person_chapter, jobs, dispos, rules=None, names=None, chapter_order=None,
                 boss_pids=None):
        self.rules = rules or R.load_rules()
        self.names = names or {}
        self.persons = list(persons)
        self.pc = sorted(person_chapter, key=lambda r: (r["file"], ival(r["index"])))
        self.job_list = sorted(jobs, key=lambda j: ival(j["index"]))
        self.jobs = {j["label"]: j for j in self.job_list}
        self.dispos = list(dispos)
        # people who are, or become, part of the player's army: their chapter versions are never boss-buffed
        self.army_mpids = {p.get("mpid_name", "") for p in self.persons
                           if p.get("belong") == self.rules["player_army"] and p.get("mpid_name")}
        # which teams place each (chapter, pid)
        self.teams: dict[tuple[str, str], set] = {}
        for d in self.dispos:
            self.teams.setdefault((chapter_of(d["file"]), d["pid"]), set()).add(str(d.get("team", "")))
        # the largest chapter number of each route letter (the default story position)
        last: dict[str, int] = {}
        for r in self.pc:
            m = CHAPTER.match(chapter_of(r["file"]))
            if m and m.group(1) in "ABC":
                last[m.group(1)] = max(last.get(m.group(1), 0), int(m.group(2)))
        self.last = last
        self.chapter_order = dict(chapter_order or {})
        self.boss_pids = set(boss_pids) if boss_pids is not None else None

    def jname(self, jid: str) -> str:
        j = self.jobs.get(jid)
        return (self.names.get(j.get("mjid_name", "")) if j else None) or jid

    def pname(self, r: dict) -> str:
        return self.names.get(r.get("mpid_name", "")) or r["label"]

    def class_ok(self, j: dict) -> bool:
        """Ordinary classes only: not the empty row, not excluded (downloadable, special, story forms)."""
        return ival(j["index"]) != 0 and not self._excluded(j["label"])

    def _excluded(self, jid: str) -> bool:
        return any(jid.startswith(p) for p in self.rules["exclude_job_prefixes"])

    def promoted(self, j: dict) -> bool:
        return self.rules["promoted_job_flag"] in R.flags(j.get("flags", ""))

    def pair_key(self, j: dict) -> str:
        """The male/female pair of one class share a draw: the smaller label of the two."""
        g = j.get("gender_pair", "")
        if g and g in self.jobs and self.jobs[g].get("gender_pair") == j["label"]:
            return min(g, j["label"])
        return j["label"]

    def story_fraction(self, path: str) -> float:
        ch = chapter_of(path)
        if ch in self.chapter_order:
            return float(self.chapter_order[ch])
        m = CHAPTER.match(ch)
        if m and m.group(1) in self.last and self.last[m.group(1)] > 0:
            return min(1.0, int(m.group(2)) / self.last[m.group(1)])
        return 0.5

    def placed_teams(self, r: dict) -> set:
        return self.teams.get((chapter_of(r["file"]), r["label"]), set())

    def is_generic_enemy(self, r: dict) -> bool:
        """unit_kind 0 (automatic level gains) and placed in its chapter by the enemy team only."""
        return str(r.get("unit_kind")) == "0" and self.placed_teams(r) == {"1"}

    def is_boss(self, r: dict) -> bool:
        """A boss row of a person who never joins the army."""
        if r.get("mpid_name", "") in self.army_mpids:
            return False
        if self.boss_pids is not None:
            return r["label"] in self.boss_pids
        if BOSS_TAG in r["label"]:
            return True
        return str(r.get("unit_kind")) == "2" and self.placed_teams(r) == {"1"}

    def unit_job(self, r: dict) -> dict | None:
        return self.jobs.get(r.get("job", ""))

    def is_army_boss(self, r: dict) -> bool:
        """Round 62: a boss row (a boss label or unit_kind 2, placed in its chapter by the enemy team only) of a
        person who joins the army on another route, in a chapter of a route the rules name (Fates: Conquest's
        chapter-only bosses). Only that chapter row is boosted; the person who joins elsewhere is not changed."""
        routes = self.rules.get("army_boss_boost_routes") or {}
        if not routes or r.get("mpid_name", "") not in self.army_mpids:
            return False
        if chapter_of(r["file"])[:1] not in routes:
            return False
        return (BOSS_TAG in r["label"] or str(r.get("unit_kind")) == "2") and self.placed_teams(r) == {"1"}


def load_tables(names: bool = True) -> StatsTables:
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
        except Exception:  # noqa: BLE001  (names only make the spoiler log nicer)
            nm = {}
    L = GD._load
    rules = R.load_rules()
    # F-047: a game with its own chapters (Seal of Flames) gives their story positions; Fates has none (default)
    return StatsTables(L("Person", only_first=True), L("PersonChapter"), L("Job"), L("DisposUnit"), rules, nm,
                       chapter_order=rules.get("chapter_order"))


# ------------------------------------------------------------------ options and random streams
def check_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS)
    o.update({k: v for k, v in (opts or {}).items() if k in DEFAULT_OPTS})
    for k, modes in (("class_growths", CLASS_MODES), ("class_bases", CLASS_MODES), ("enemy_growths", ENEMY_MODES),
                     ("boss_stats", BOSS_MODES)):
        if o[k] is False or o[k] is None:
            o[k] = "off"
        if o[k] not in modes:
            raise R.RandoError(f"{k}: one of {', '.join(modes)}")
    for k, (lo, hi) in NUMBERS.items():
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
    o["difficulty"] = str(o["difficulty"]).strip().lower()
    if o["difficulty"] not in DIFFICULTY_STEP:
        raise R.RandoError("difficulty: one of easy, normal, hard")
    return o


def is_off(o: dict) -> bool:
    return (o["class_growths"] == "off" and o["class_bases"] == "off" and o["enemy_growths"] == "off"
            and o["enemy_levels"] == 0 and o["boss_stats"] == "off" and o["boss_variance"] == 0)


def opts_text(o: dict) -> str:
    t = []
    if o["class_growths"] != "off":
        t.append(f"class-growths={o['class_growths']} variance={o['class_growth_variance']} max={o['class_growth_max']}")
    if o["class_bases"] != "off":
        t.append(f"class-bases={o['class_bases']} variance={o['class_base_variance']}")
    if o["enemy_growths"] != "off":
        t.append(f"enemy-growths={o['enemy_growths']} buff={o['enemy_buff']}")
    if o["enemy_levels"]:
        t.append(f"enemy-levels=+{o['enemy_levels']}")
    if o["boss_stats"] != "off" or o["boss_variance"]:
        t.append(f"boss-stats={o['boss_stats']} max-boost={o['boss_max_boost']} variance={o['boss_variance']}"
                 + (f" difficulty={o['difficulty']}" if o["boss_stats"] != "off" else ""))
    return " ".join(t) or "off"


def track_key(rng) -> str:
    if isinstance(rng, random.Random):
        base = "random:" + format(rng.getrandbits(256), "064x")
    else:
        base = "seed:" + R.check_seed(str(rng))
    return hashlib.sha256("\x1f".join([TOOL, base, TRACK]).encode("utf-8")).hexdigest()


def stream(key: str, purpose: str, text: str, row: str) -> random.Random:
    h = hashlib.sha256("\x1f".join([key, purpose, text, row]).encode("utf-8")).digest()
    return random.Random(int.from_bytes(h, "big"))


# ------------------------------------------------------------------ the pieces (pure functions, re-used by the guards)
def growth_bounds(o: dict, orig: int) -> tuple[int, int]:
    """Class growth bounds: 0..max in steps of 5, never cutting a number the game already has."""
    hi = max(o["class_growth_max"] // STEP * STEP, orig)
    return 0 if orig >= 0 else orig, hi


def class_growth_delta(r: random.Random, v: list[int], o: dict) -> list[int]:
    out, steps = [], o["class_growth_variance"] // STEP
    for g in v:
        lo, hi = growth_bounds(o, g)
        g5 = min(max(int(round(g / STEP)) * STEP, lo), hi) if g % STEP else g
        m = STEP * r.randint(0, steps)
        n = g5 + m if r.randrange(2) == 0 else g5 - m
        out.append(min(max(n, lo), hi))
    return out


def base_bounds(j: dict, s: str) -> tuple[int, int]:
    orig = ival(j[f"base.{s}"])
    hi = max(orig, ival(j[f"max.{s}"]))
    return (orig if s == "hp" else min(0, orig)), hi


def class_base_delta(r: random.Random, j: dict, var: int) -> list[int]:
    out = []
    for s in R.STATS:
        b = ival(j[f"base.{s}"])
        lo, hi = base_bounds(j, s)
        m = r.randint(0, var)
        n = b + m if r.randrange(2) == 0 else b - m
        out.append(min(max(n, lo), hi))
    return out


def enemy_growth_new(v: int, mode: str, buff: int) -> int:
    """FE8 ApplyEnemyGrowth: flat adds buff, scaling adds buff % (negative growths untouched); then steps of 5
    (rounded half up) and at most 125, never below the original."""
    if v < 0 or mode == "off" or buff == 0:
        return v
    n = v + buff if mode == "flat" else v * (100 + buff) / 100
    n = int(n / STEP + 0.5) * STEP
    return max(v, min(n, GROWTH_TOP))


def enemy_level_new(level: int, add: int, promoted: bool) -> int:
    if add <= 0 or level <= 0:
        return level
    n = min(level + add, max(level, LEVEL_TOP))
    if promoted and level <= PROMOTED_GATE:
        n = min(n, PROMOTED_GATE)
    return max(n, level)


def boss_buff_amount(mode: str, amt: int, frac: float) -> int:
    """FE8 BossBuffAmount with the story position as a fraction 0..1: linear = ceil(amt * f), ease = ceil(amt *
    f^2 / (f^2 + (1-f)^2)); never above amt; 0 at the story's start."""
    if mode == "off" or amt <= 0 or frac <= 0:
        return 0
    f = min(frac, 1.0)
    x = amt * f if mode == "linear" else amt * f * f / (f * f + (1 - f) * (1 - f))
    return min(amt, int(-(-round(x * 1000) // 1000)))


def boss_limits(t: StatsTables, r: dict, s: str) -> tuple[int, int] | None:
    """(lowest, highest) personal base so that personal + class base stays within 0 (HP 1) and the class maximum
    + the person's limit modifier (the cap the game applies). None when the class is not known."""
    j = t.unit_job(r)
    if j is None:
        return None
    jb = ival(j[f"base.{s}"])
    lo = (1 if s == "hp" else 0) - jb
    hi = ival(j[f"max.{s}"]) + ival(r.get(f"limit_mod.{s}", 0)) - jb
    return lo, hi




def hp_boost(t: StatsTables, r: dict, step: int) -> int:
    """10% of the boss's HP (personal + class base) per difficulty step, rounded up."""
    j = t.unit_job(r)
    if j is None or step <= 0:
        return 0
    hp = ival(r["base.hp"]) + ival(j["base.hp"])
    return max(0, -(-(HP_BOOST_PCT * step * hp) // 100))


def boost_rows(t: StatsTables, opts: dict | None) -> set:
    """(chapter, PersonChapter label) of every row the tougher-bosses boost reaches (bosses who never join, and
    the army bosses of the rules' routes); weapons.py forges their weapons. Empty with boss stats off."""
    o = check_opts(opts)
    if o["boss_stats"] == "off":
        return set()
    return {(chapter_of(r["file"]), r["label"]) for r in t.pc if t.is_boss(r) or t.is_army_boss(r)}


def with_hp(t: StatsTables, r: dict, vals: list[int], bonus: int) -> list[int]:
    """vals with the HP boost added (never past the cap; an HP already at or above it stays)."""
    out = list(vals)
    if bonus:
        lim = boss_limits(t, r, "hp")
        n = out[0] + bonus
        if lim:
            n = min(n, max(out[0], lim[1]))
        out[0] = n
    return out


def boss_new(t: StatsTables, r: dict, buff: int, var: int, top: int, rng: random.Random) -> list[int]:
    """buff (+ up to var either way) per stat, at most top up and var down, within boss_limits."""
    out = []
    for s in R.STATS:
        b = ival(r[f"base.{s}"])
        d = buff + (rng.randint(-var, var) if var else 0)
        d = min(max(-var, d), top)
        lim = boss_limits(t, r, s)
        n = b + d
        if lim:
            lo, hi = lim
            if d > 0:
                n = min(n, max(b, hi))          # never raised past the cap (a stat at or above it stays)
            elif d < 0:
                n = max(n, min(b, lo))          # never lowered below 0 / HP 1
        out.append(n)
    return out


# ------------------------------------------------------------------ the plan
def plan_stats(tables: StatsTables, rng, opts: dict | None = None) -> tuple[list[dict], list[str]]:
    t = tables
    o = check_opts(opts)
    if is_off(o):
        return [], []
    key = track_key(rng)
    text = opts_text(o)
    edits: list[dict] = []
    lines = [f"Stats track ({TOOL}): {text}"]

    def job_edit(j, cell, old, new):
        if old != new:
            edits.append({"table": "Job", "index": ival(j["index"]), "label": j["label"], "cell": cell,
                          "old": str(old), "new": str(new)})

    for j in t.job_list:
        if not t.class_ok(j):
            continue
        name = f"{t.jname(j['label'])} [{j['label']}]"
        if o["class_growths"] != "off":
            orig = [ival(j[f"growth.{s}"]) for s in R.STATS]
            new = class_growth_delta(stream(key, "class_growths", text, t.pair_key(j)), orig, o)
            for n, s in enumerate(R.STATS):
                job_edit(j, f"growth.{s}", orig[n], new[n])
            if new != orig:
                lines.append(f"{name} class growths: {' '.join(map(str, orig))}  ->  {' '.join(map(str, new))}")
        if o["class_bases"] != "off":
            orig = [ival(j[f"base.{s}"]) for s in R.STATS]
            new = class_base_delta(stream(key, "class_bases", text, t.pair_key(j)), j, o["class_base_variance"])
            for n, s in enumerate(R.STATS):
                job_edit(j, f"base.{s}", orig[n], new[n])
            if new != orig:
                lines.append(f"{name} class bases: {' '.join(map(str, orig))}  ->  {' '.join(map(str, new))}")
        if o["enemy_growths"] != "off":
            orig = [ival(j[f"enemy_growth.{s}"]) for s in R.STATS]
            new = [enemy_growth_new(v, o["enemy_growths"], o["enemy_buff"]) for v in orig]
            for n, s in enumerate(R.STATS):
                job_edit(j, f"enemy_growth.{s}", orig[n], new[n])
            if new != orig:
                lines.append(f"{name} enemy growths: {' '.join(map(str, orig))}  ->  {' '.join(map(str, new))}")

    def pc_edit(r, cell, old, new):
        if old != new:
            edits.append({"table": "PersonChapter", "file": r["file"], "index": ival(r["index"]), "label": r["label"],
                          "cell": cell, "old": str(old), "new": str(new)})

    raised = 0
    for r in t.pc:
        if o["enemy_levels"] and t.is_generic_enemy(r):
            j = t.unit_job(r)
            if j is not None and t.class_ok(j):
                old = ival(r["level"])
                new = enemy_level_new(old, o["enemy_levels"], t.promoted(j))
                pc_edit(r, "level", old, new)
                raised += new != old
        step = DIFFICULTY_STEP[o["difficulty"]] if o["boss_stats"] != "off" else 0
        if (o["boss_stats"] != "off" or o["boss_variance"]) and t.is_boss(r):
            frac = t.story_fraction(r["file"])
            buff = boss_buff_amount(o["boss_stats"], o["boss_max_boost"], frac)
            orig = [ival(r[f"base.{s}"]) for s in R.STATS]
            new = boss_new(t, r, buff, o["boss_variance"], o["boss_max_boost"], stream(key, "boss", text, f"{r['file']}#{r['index']}"))
            hb = hp_boost(t, r, step)
            new = with_hp(t, r, new, hb)
            hp_note = f", HP +{hb} ({o['difficulty']})" if hb else ""
            for n, s in enumerate(R.STATS):
                pc_edit(r, f"base.{s}", orig[n], new[n])
            if new != orig:
                lines.append(f"{chapter_of(r['file'])} boss {t.pname(r)} [{r['label']}] (story {frac:.2f}, buff {buff}"
                             f"{hp_note}): "
                             f"{' '.join(map(str, orig))}  ->  {' '.join(map(str, new))}")
        elif step and t.is_army_boss(r):
            orig = [ival(r[f"base.{s}"]) for s in R.STATS]
            hb = hp_boost(t, r, step)
            new = with_hp(t, r, orig, hb)
            pc_edit(r, "base.hp", orig[0], new[0])
            if new != orig:
                lines.append(f"{chapter_of(r['file'])} boss {t.pname(r)} [{r['label']}] (joins on another route: this "
                             f"chapter row only; HP +{hb}, {o['difficulty']}): HP {orig[0]} -> {new[0]}")
    if o["enemy_levels"]:
        lines.append(f"Generic enemy rows raised by up to {o['enemy_levels']} levels: {raised}")
    return edits, lines


# ------------------------------------------------------------------ guards (recomputed from the edits alone)
WRITABLE = {"Job": re.compile(r"^(growth|base|enemy_growth)\.(hp|str|mag|skl|spd|lck|def|res)$"),
            "PersonChapter": re.compile(r"^(level|base\.(hp|str|mag|skl|spd|lck|def|res))$")}


def run_guards(tables: StatsTables, edits: list[dict], opts: dict | None = None) -> dict:
    t = tables
    o = check_opts(opts)
    G = {k: [] for k in ("only_stat_cells", "cells_fit", "class_growths_bounded", "class_bases_bounded",
                         "enemy_growths_formula", "enemy_levels_bounded", "boss_stats_bounded", "boss_gain_follows_story",
                         "off_means_no_edits")}
    if is_off(o) and edits:
        G["off_means_no_edits"].append(f"{len(edits)} edits with every option off")
    pcs = {(r["file"], ival(r["index"])): r for r in t.pc}
    seen = set()
    boss_delta: dict[tuple, dict] = {}
    for e in edits:
        k = (e["table"], e.get("file", ""), e["index"], e["cell"])
        if k in seen:
            G["only_stat_cells"].append(f"{k}: written twice")
        seen.add(k)
        pat = WRITABLE.get(e["table"])
        if not pat or not pat.match(e["cell"]):
            G["only_stat_cells"].append(f"{e['table']}.{e['cell']} is not a stats cell")
            continue
        new, old = ival(e["new"]), ival(e["old"])
        if e["table"] == "Job":
            j = t.jobs.get(e["label"])
            if j is None or ival(j["index"]) != e["index"] or not t.class_ok(j):
                G["only_stat_cells"].append(f"{e['label']}: not an ordinary class row")
                continue
            kind, s = e["cell"].split(".")
            if str(old) != str(ival(j[e["cell"]])):
                G["only_stat_cells"].append(f"{e['label']}.{e['cell']}: old {old} is not the original {j[e['cell']]}")
            if not -128 <= new <= 127:
                G["cells_fit"].append(f"{e['label']}.{e['cell']} = {new}")
            if kind == "growth":
                lo, hi = growth_bounds(o, old)
                v = o["class_growth_variance"]
                if o["class_growths"] == "off" or new % STEP or not lo <= new <= hi or abs(new - old) > v + (0 if old % STEP == 0 else STEP - 1):
                    G["class_growths_bounded"].append(f"{e['label']}.{e['cell']}: {old} -> {new}")
            elif kind == "base":
                lo, hi = base_bounds(j, s)
                if o["class_bases"] == "off" or not lo <= new <= hi or abs(new - old) > o["class_base_variance"] \
                        or (s == "hp" and new < old):
                    G["class_bases_bounded"].append(f"{e['label']}.{e['cell']}: {old} -> {new}")
            else:
                if new != enemy_growth_new(old, o["enemy_growths"], o["enemy_buff"]) or new % STEP and new != old:
                    G["enemy_growths_formula"].append(f"{e['label']}.{e['cell']}: {old} -> {new}")
        else:
            r = pcs.get((e.get("file", ""), e["index"]))
            if r is None or r["label"] != e["label"]:
                G["only_stat_cells"].append(f"{e.get('file')}#{e['index']}: no such PersonChapter row")
                continue
            if str(old) != str(ival(r[e["cell"]])):
                G["only_stat_cells"].append(f"{e['label']}.{e['cell']}: old {old} is not the original")
            if e["cell"] == "level":
                j = t.unit_job(r)
                ok = (o["enemy_levels"] > 0 and t.is_generic_enemy(r) and j is not None and t.class_ok(j)
                      and old < new <= max(old, LEVEL_TOP) and new - old <= o["enemy_levels"]
                      and not (t.promoted(j) and old <= PROMOTED_GATE < new))
                if not ok or not 0 <= new <= 255:
                    G["enemy_levels_bounded"].append(f"{e['label']} level {old} -> {new}")
            else:
                s = e["cell"].split(".")[1]
                if not -128 <= new <= 127:
                    G["cells_fit"].append(f"{e['label']}.{e['cell']} = {new}")
                step = DIFFICULTY_STEP[o["difficulty"]] if o["boss_stats"] != "off" else 0
                hb = hp_boost(t, r, step) if s == "hp" else 0
                d = new - old
                if step and t.is_army_boss(r) and not t.is_boss(r):
                    lim = boss_limits(t, r, "hp")
                    want = with_hp(t, r, [old], hp_boost(t, r, step))[0] if lim else old + hp_boost(t, r, step)
                    if s != "hp" or new != want:
                        G["boss_stats_bounded"].append(f"{e['label']}.{s}: {old} -> {new} (an army boss row: HP +{hp_boost(t, r, step)} only)")
                    continue
                if (o["boss_stats"] == "off" and not o["boss_variance"]) or not t.is_boss(r):
                    G["boss_stats_bounded"].append(f"{e['label']}: not a boss row (or boss stats off)")
                    continue
                if d > o["boss_max_boost"] + hb or d < -o["boss_variance"]:
                    G["boss_stats_bounded"].append(f"{e['label']}.{s}: moved {d}")
                lim = boss_limits(t, r, s)
                if lim:
                    lo, hi = lim
                    if (new > old and new > max(old, hi)) or (d < 0 and new < min(old, lo)):
                        G["boss_stats_bounded"].append(f"{e['label']}.{s}: {old} -> {new} outside {lo}..{hi}")
                # the story buff alone (the HP boost taken off; a capped HP may have gained less than both)
                boss_delta.setdefault((r["file"], ival(r["index"])), {})[s] = d - hb if d - hb >= 0 else (d if d < 0 else 0)
    # W1 (WIRE_56 2c): the old "HP+Def+Res at most 3 x max boost" line could never fail (each stat is capped
    # already). This one is independent: each stat's gain is at most the story-position buff of the boss's own
    # chapter (recomputed here from the chapter, not taken from the plan) plus the variance.
    for k, dd in boss_delta.items():
        r = pcs[k]
        cap = boss_buff_amount(o["boss_stats"], o["boss_max_boost"], t.story_fraction(r["file"])) + o["boss_variance"]
        over = [f"{s} +{d}" for s, d in dd.items() if d > cap]
        if over:
            G["boss_gain_follows_story"].append(f"{k}: {', '.join(over)} above {cap} for its story position")
    return {k: {"ok": not v, "detail": v[:20]} for k, v in G.items()}


# ------------------------------------------------------------------ mod files (this track alone; the wiring merges)
def edits_to_files(t: StatsTables, edits: list[dict]) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    jobs: dict[str, dict] = {}
    for e in edits:
        if e["table"] == "Job":
            jobs.setdefault(e["label"], {})[e["cell"]] = e["new"]
    if jobs:
        cols = sorted({c for v in jobs.values() for c in v},
                      key=lambda c: (("base", "growth", "enemy_growth").index(c.split(".")[0]), R.STATS.index(c.split(".")[1])))
        rows = [["index", "label"] + cols]
        for jid in sorted(jobs, key=lambda x: ival(t.jobs[x]["index"])):
            j = t.jobs[jid]
            rows.append([str(ival(j["index"])), jid] + [jobs[jid].get(c, str(ival(j[c]))) for c in cols])
        files["tables/Job.csv"] = R._csv(rows)
    pcs: dict[tuple, dict] = {}
    for e in edits:
        if e["table"] == "PersonChapter":
            pcs.setdefault((e["file"], e["index"], e["label"]), {})[e["cell"]] = e["new"]
    if pcs:
        order = ["level"] + [f"base.{s}" for s in R.STATS]
        cols = [c for c in order if any(c in v for v in pcs.values())]
        by = {(r["file"], ival(r["index"])): r for r in t.pc}
        rows = [["file", "index", "label"] + cols]
        for k in sorted(pcs):
            r = by[(k[0], k[1])]
            rows.append([k[0], str(k[1]), k[2]] + [pcs[k].get(c, str(ival(r[c]))) for c in cols])
        files["tables/PersonChapter.csv"] = R._csv(rows)
    return files


def render(t: StatsTables, seed: str, o: dict, edits: list[dict], spoil: list[str], guards: dict) -> dict[str, bytes]:
    files = edits_to_files(t, edits)
    meta = {"name": R.mod_name(seed) + "-stats", "description": f"Randomizer track stats, seed {seed} "
            f"({opts_text(o)}). For one randomized save only; see docs/rando/STATS.md.", "enabled": True,
            "order": 140, "override": False, "randomizer": {"tool": TOOL, "track": TRACK, "seed": seed, "options": o}}
    sp = ["Fire Emblem Fates randomizer - spoiler log, track stats", f"seed: {seed}", f"options: {opts_text(o)}", ""] \
        + spoil + ["", "Guards:"]
    for k, v in guards.items():
        sp.append(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
        sp += [f"       {x}" for x in v["detail"][:12]]
    files["mod.json"] = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    files["spoiler-stats.txt"] = ("\n".join(sp) + "\n").encode("utf-8")
    files["plan-stats.json"] = (json.dumps({"tool": TOOL, "track": TRACK, "seed": seed, "options": o, "edits": edits,
                                            "guards": guards}, indent=1, ensure_ascii=False, sort_keys=True)
                                + "\n").encode("utf-8")
    return files


def make_folder(seed: str, opts: dict, out_top: str, tables: StatsTables | None = None) -> tuple[str, dict, list]:
    t = tables or load_tables()
    o = check_opts(opts)
    edits, lines = plan_stats(t, seed, o)
    guards = run_guards(t, edits, o)
    files = render(t, seed, o, edits, lines, guards)
    folder = R.write_mod(files, os.path.join(out_top, R.mod_name(seed) + "-stats"))
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
    p = sub.add_parser("make", help="this track alone as one mod folder below build/ (host only)")
    p.add_argument("--seed", required=True)
    p.add_argument("--class-growths", choices=CLASS_MODES, default="off")
    p.add_argument("--class-growth-variance", type=int, default=DEFAULT_OPTS["class_growth_variance"])
    p.add_argument("--class-growth-max", type=int, default=DEFAULT_OPTS["class_growth_max"])
    p.add_argument("--class-bases", choices=CLASS_MODES, default="off")
    p.add_argument("--class-base-variance", type=int, default=DEFAULT_OPTS["class_base_variance"])
    p.add_argument("--enemy-growths", choices=ENEMY_MODES, default="off")
    p.add_argument("--enemy-buff", type=int, default=DEFAULT_OPTS["enemy_buff"])
    p.add_argument("--enemy-levels", type=int, default=0)
    p.add_argument("--boss-stats", choices=BOSS_MODES, default="off")
    p.add_argument("--boss-max-boost", type=int, default=DEFAULT_OPTS["boss_max_boost"])
    p.add_argument("--boss-variance", type=int, default=0)
    p.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    opts = {k: getattr(a, k) for k in DEFAULT_OPTS}
    try:
        why = _forbidden(a.out)
        if why:
            raise R.RandoError(f"refused: {why}")
        folder, guards, edits = make_folder(a.seed, opts, os.path.abspath(a.out))
    except R.RandoError as e:
        print(f"ERROR: {e}")
        return 1
    print(f"made {folder}: {len(edits)} cells")
    for k, v in guards.items():
        print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}" + ("" if v["ok"] else f"  {v['detail'][:3]}"))
    return 0 if all(v["ok"] for v in guards.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
