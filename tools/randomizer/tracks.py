"""The randomizer's four extra tracks put together with slice 1 (round 49, F-043; docs/RANDOMIZER.md section 7).

    make_all(facts, seed, switches, topts) -> (plan, files)

facts     randolib.Facts (gamedata.load_facts())
switches  slice 1's switches (randolib.DEFAULT_SWITCHES keys)
topts     the track options (DEFAULT_TOPTS keys, the names rando.py's flags use); every default is "off", so with
          the defaults nothing below runs and the files are slice 1's, byte for byte

Order: slice 1's plan -> growth (growth/base modes, written into the plan's persons) -> skills (Person skill
cells) -> items (team-0 placements' item cells, Item shop stock, castle rewards) -> enemies (team-1 placements'
class and item cells). Each track takes its own sub-seed from the run seed and its own name (and options), so
one track's switches never move another track's results. Rows touched by two tracks: a team-0 placement can get
slice 1's weapon swap and then the items track's new items (the items track starts from slice 1's values, its
cells win); team-0 and team-1 rows never overlap, so items and enemies never meet.

Guards: slice 1's (re-run after the growth track), plus each track's own, all in plan["guards"] with the track
name in front ("growth: bounds", "items: ...", "skills: ...", "enemies: ..."). With a bases mode on, slice 1's
"personal base total grew" line gives way to the growth track's own bound (randolib.run_guards reads
plan["tracks"]["growth"]).

Round W1 (F-046 / F-047, docs/rando/WIRE_56.md section 2) adds five more modules, each with its own sub-seed and
its own options (all off by default, so old seeds stay byte for byte the same; a module whose options are off is
not even imported): children, promotions (Master Seal / Heart Seal classes), stats (class growths and bases, enemy
growths and levels, boss stats), weapons (weapon stats and traits, stronger enemy weapons) and misc (enemy drops,
class movement, assign classes evenly). The order, by WIRE_56 section 2: slice 1 -> misc assign evenly (slice 1
again with the even classes) -> growth -> promotions (Job part; job_low follows) -> skills -> children (with the
final promotions) -> items -> enemies -> stats -> misc enemy drops (on the final enemy items) -> weapons (drops
left alone) -> misc class movement (on the final enemy classes) -> the cross guards ("cross: ...":
job_low_fits_final_promotions, no_stuck_final, weapons_usable_final, one_writer_per_cell). Shared tables are
merged by column (Job: promotions / stats / misc; Item: items / weapons; DisposUnit: slice 1 / items / enemies /
weapons / misc drop flags, then the children's rows). Music, Nuzlocke and the character shuffle are not wired
here yet (W2 and the engine rounds); the in-game page shows them grey.

Round 75b (docs/SEED_GUARANTEES_PLAN.md, written as 'round 79'): slice 1's make_plan repairs the seed guarantees
(guarantees.repair: a door opener, a healer holding a staff, a flier and the vein user by the first chapter that needs
them); the cross guard "guarantees: timing" (guarantees.check) runs after slice 1, the even spread, promotions,
skills, children and on the final rows; the spoiler gets a "Guarantees" section; plan.json carries the "guarantees"
block and "rando_version" 2. With the shuffle on, "never stricter than the original" is judged on the rows before the
shuffle (facts.original_facts).
Our own code.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402
import guarantees as GU  # noqa: E402

# rando.py's names (FE8-port style where the FE8 port has the row) -> default. "off"/"keep"/"slice1" = unchanged.
DEFAULT_TOPTS = {
    # Stats (growth track; FE8 port: Growths, Growth variance, Growth min, Growth max, Adjust HP growths, Bases,
    # Base variance). "slice1" = slice 1's own growths/join-stats switches decide.
    "growth_mode": "slice1", "growth_variance": 30, "growth_min": 5, "growth_max": 80, "adjust_hp": False,
    "bases_mode": "slice1", "base_variance": 5, "scale_to_level": True,
    # Skills (skills track; the FE8 port's randomizer has no skills)
    "personal_skills": "keep", "skill_slots": "keep",
    # Items (items track; FE8 port: Shops, Rewards; plus starting items)
    "starting_items": False, "shops": False, "shop_sides": "own", "rewards": False,
    # Enemies (enemies track; FE8 port: Enemy classes, Boss classes, "Better enemy weapons" as on/off)
    "enemy_weapons": False, "enemy_classes": False, "boss_classes": False, "enemy_trees": "own",
    # round W1 (WIRE_56 section 1): children, promotions, stats, weapons, misc
    "children": False,
    "promotions": "off", "promotion_sides": "any", "reclass": "keep",
    "class_growths": "off", "class_growth_variance": 10, "class_bases": "off", "class_base_variance": 2,
    "enemy_growths": "off", "enemy_buff": 10, "enemy_levels": 0,
    "boss_stats": "off", "boss_max_boost": 5, "boss_variance": 0,
    "weapon_stats": "off", "weapon_traits": 0, "wild_traits": False, "enemy_upgrade": 0, "upgrade_rank": "same",
    "enemy_drops": 0, "class_move": "off", "assign_evenly": False,
    # round W2 (WIRE_56 section 1): music (map / battle themes), Nuzlocke (rules file only until engine round E2)
    "music": "off", "nuzlocke": False, "recruits": "all",
    # round 62 (F-049): the randomizer's difficulty: how far "stronger enemy weapons" go (one step on the ladder;
    # weapons.py) and the tougher-bosses boost (10% HP and +1 shown weapon might per step; stats.py / weapons.py)
    "difficulty": "normal",
    # round 71 (A1, docs/rando/CHESTS.md): chests, villages and talk gifts (chests track); laid by the game core's chest
    # hook (patch 0031) from the run's chests.txt; PLAY RANDOMIZED mod folders cannot change a chest
    "chests": False,
}
# the keys added in round W1: kept out of mod.json / plan.json while at their default, so a seed made with only
# the round-49 tracks on gives the same files byte for byte as before the wiring
W1_KEYS = ("children", "promotions", "promotion_sides", "reclass", "class_growths", "class_growth_variance",
           "class_bases", "class_base_variance", "enemy_growths", "enemy_buff", "enemy_levels", "boss_stats",
           "boss_max_boost", "boss_variance", "weapon_stats", "weapon_traits", "wild_traits", "enemy_upgrade",
           "upgrade_rank", "enemy_drops", "class_move", "assign_evenly")
# the keys added in round W2: the same rule (stored only when not at their default)
W2_KEYS = ("music", "nuzlocke", "recruits")
R62_KEYS = ("difficulty",)
# round 71: the same rule (kept out of mod.json / plan.json, the make flags and the page answer while off)
R71_KEYS = ("chests",)
# options only the in-game page offers (PLAY RANDOMIZED's mod folders cannot lay them): not in tools/play/rando.py
INGAME_ONLY = ("chests",)
LATE_KEYS = W1_KEYS + W2_KEYS + R62_KEYS + R71_KEYS
# the character shuffle's options (recruit.DEFAULT_OPTS / CHOICES, copied so recruit.py is never imported while the
# shuffle is off, R8). A separate dict, "ropts", never part of topts: mod.json / plan.json carry it only when on.
RECRUIT_DEFAULTS = {"recruit": "off", "recruit_look": "keep", "recruit_class": "own", "recruit_stats": "autolevel"}
RECRUIT_CHOICES = {"recruit": ("off", "route", "any"), "recruit_look": ("keep", "full"),
                   "recruit_class": ("own", "slot"), "recruit_stats": ("autolevel", "slot")}
CHOICES = {"growth_mode": ("slice1", "redistribute", "delta", "full"), "bases_mode": ("slice1", "redistribute", "delta"),
           "personal_skills": ("keep", "shuffle", "random"), "skill_slots": ("keep", "class", "random"),
           "shop_sides": ("own", "mixed"), "enemy_trees": ("own", "any"),
           "promotions": ("off", "on"), "promotion_sides": ("any", "own"), "reclass": ("keep", "random"),
           "class_growths": ("off", "delta"), "class_bases": ("off", "delta"),
           "enemy_growths": ("off", "flat", "scaling"), "boss_stats": ("off", "linear", "ease"),
           "weapon_stats": ("off", "on"), "upgrade_rank": ("same", "next"), "class_move": ("off", "small", "wide"),
           "music": ("off", "maps", "maps+battles"), "recruits": ("all", "first"),
           "difficulty": ("easy", "normal", "hard")}
BOOLS = ("adjust_hp", "scale_to_level", "starting_items", "shops", "rewards", "enemy_weapons", "enemy_classes",
         "boss_classes", "children", "wild_traits", "assign_evenly", "nuzlocke", "chests")
NUMBERS = {"growth_variance": (0, 100), "growth_min": (0, 100), "growth_max": (0, 125), "base_variance": (1, 10),
           "class_growth_variance": (0, 50), "class_base_variance": (1, 5), "enemy_buff": (0, 100),
           "enemy_levels": (0, 5), "boss_max_boost": (1, 20), "boss_variance": (0, 5), "weapon_traits": (0, 100),
           "enemy_upgrade": (0, 100), "enemy_drops": (0, 100)}


def check_topts(topts: dict | None) -> dict:
    o = dict(DEFAULT_TOPTS)
    for k, v in (topts or {}).items():
        if k not in DEFAULT_TOPTS:
            raise R.RandoError(f"unknown randomizer option {k!r}")
        o[k] = v
    for k, ch in CHOICES.items():
        o[k] = str(o[k]).strip().lower()
        if o[k] not in ch:
            raise R.RandoError(f"{k.replace('_', '-')}: one of {', '.join(ch)}")
    for k in BOOLS:
        o[k] = bool(o[k])
    for k, (lo, hi) in NUMBERS.items():
        try:
            o[k] = int(str(o[k]).strip().rstrip("%"))
        except ValueError:
            raise R.RandoError(f"{k.replace('_', '-')}: a whole number {lo}-{hi}") from None
        if not lo <= o[k] <= hi:
            raise R.RandoError(f"{k.replace('_', '-')}: {o[k]} is outside {lo}-{hi}")
    if o["enemy_drops"] % 5:
        raise R.RandoError(f"enemy-drops: {o['enemy_drops']} is not a step of 5 (0 = off, 5-100)")
    return o


def stored_topts(o: dict) -> dict:
    """The options as mod.json / plan.json keep them: the round-W1 keys only when they are not at their default."""
    return {k: v for k, v in o.items() if k not in LATE_KEYS or v != DEFAULT_TOPTS[k]}


def check_ropts(ropts: dict | None) -> dict:
    """The character shuffle's options (RECRUIT_DEFAULTS keys; None / {} = off)."""
    o = dict(RECRUIT_DEFAULTS)
    for k, v in (ropts or {}).items():
        if k not in RECRUIT_DEFAULTS:
            raise R.RandoError(f"unknown character shuffle option {k!r}")
        if v is not None:
            o[k] = v
    for k, ch in RECRUIT_CHOICES.items():
        o[k] = str(o[k]).strip().lower()
        if o[k] == "keep_face":
            o[k] = "keep"
        if o[k] not in ch:
            raise R.RandoError(f"{k.replace('_', '-')}: one of {', '.join(ch)}")
    return o


def ropts_text(o: dict) -> str:
    return " ".join(f"{k.replace('_', '-')}={v}" for k, v in o.items())


def growth_opts(o: dict) -> dict:
    return {"growths": o["growth_mode"], "growth_variance": o["growth_variance"], "growth_min": o["growth_min"],
            "growth_max": o["growth_max"], "adjust_hp": o["adjust_hp"], "bases": o["bases_mode"],
            "base_variance": o["base_variance"], "scale_to_level": o["scale_to_level"]}


def skills_opts(o: dict) -> dict:
    return {"personal": o["personal_skills"], "slots": o["skill_slots"]}


def items_opts(o: dict) -> dict:
    return {"inventories": o["starting_items"], "shops": o["shops"], "shop_sides": o["shop_sides"],
            "rewards": o["rewards"]}


def enemies_opts(o: dict) -> dict:
    return {"gear": o["enemy_weapons"], "enemy_classes": o["enemy_classes"], "boss_classes": o["boss_classes"],
            "trees": o["enemy_trees"]}


CHILD_SLOTS = {"keep": "keep", "class": "class", "random": "class"}   # the children track knows keep|class only


def children_opts(sw: dict, o: dict) -> dict:
    s = dict(R.DEFAULT_SWITCHES, **(sw or {}))
    return {"children": o["children"], "classes": s["classes"], "growths": s["growths"],
            "join_stats": s["join_stats"], "trees": s["trees"],
            "growth_mode": o["growth_mode"], "growth_variance": o["growth_variance"], "growth_min": o["growth_min"],
            "growth_max": o["growth_max"], "adjust_hp": o["adjust_hp"], "bases_mode": o["bases_mode"],
            "base_variance": o["base_variance"], "scale_to_level": o["scale_to_level"],
            "personal_skills": o["personal_skills"], "skill_slots": CHILD_SLOTS[o["skill_slots"]]}


def promotions_opts(o: dict) -> dict:
    return {"promotions": o["promotions"], "choices": "2", "reclass": o["reclass"], "sides": o["promotion_sides"]}


STATS_KEYS = ("class_growths", "class_growth_variance", "class_bases", "class_base_variance", "enemy_growths",
              "enemy_buff", "enemy_levels", "boss_stats", "boss_max_boost", "boss_variance")


def stats_opts(o: dict) -> dict:
    out = {k: o[k] for k in STATS_KEYS}
    if o["boss_stats"] != "off":            # round 62: the tougher-bosses boost scales with the difficulty
        out["difficulty"] = o["difficulty"]
    return out


def weapons_opts(o: dict) -> dict:
    out = {"stats": o["weapon_stats"] == "on", "traits": o["weapon_traits"], "wild_traits": o["wild_traits"],
           "enemy_upgrade": o["enemy_upgrade"], "upgrade_rank": o["upgrade_rank"]}
    if o["enemy_upgrade"] or o["boss_stats"] != "off":     # round 62: the ladder and the boss forge
        out["difficulty"] = o["difficulty"]
    if o["boss_stats"] != "off":
        out["boss_forge"] = DIFFICULTY_STEP[o["difficulty"]]
    return out


DIFFICULTY_STEP = {"easy": 1, "normal": 2, "hard": 3}


def misc_opts(o: dict) -> dict:
    return {"enemy_drops": o["enemy_drops"], "class_move": o["class_move"], "assign_evenly": o["assign_evenly"]}


def music_opts(o: dict) -> dict:
    return {"music": o["music"]}


def nuzlocke_opts(o: dict) -> dict:
    return {"nuzlocke": o["nuzlocke"], "recruits": o["recruits"]}


def chests_opts(o: dict) -> dict:
    return {"chests": "on" if o["chests"] else "off"}


def active(o: dict) -> dict[str, bool]:
    return {"growth": o["growth_mode"] != "slice1" or o["bases_mode"] != "slice1",
            "skills": o["personal_skills"] != "keep" or o["skill_slots"] != "keep",
            "items": o["starting_items"] or o["shops"] or o["rewards"],
            "enemies": o["enemy_weapons"] or o["enemy_classes"] or o["boss_classes"],
            "children": o["children"],
            "promotions": o["promotions"] != "off" or o["reclass"] != "keep",
            "stats": (o["class_growths"] != "off" or o["class_bases"] != "off" or o["enemy_growths"] != "off"
                      or o["enemy_levels"] > 0 or o["boss_stats"] != "off" or o["boss_variance"] > 0),
            "weapons": (o["weapon_stats"] == "on" or o["weapon_traits"] > 0 or o["enemy_upgrade"] > 0
                        or o["boss_stats"] != "off"),
            "misc": o["enemy_drops"] > 0 or o["class_move"] != "off" or o["assign_evenly"],
            "music": o["music"] != "off",
            "nuzlocke": o["nuzlocke"],
            "chests": o["chests"]}


def topts_text(o: dict) -> str:
    """The non-default options only ("" with every default)."""
    out = []
    for k, v in o.items():
        if v != DEFAULT_TOPTS[k]:
            out.append(f"{k.replace('_', '-')}={'on' if v is True else 'off' if v is False else v}")
    return " ".join(out)


def _section(title: str, lines: list[str]) -> list[str]:
    return ["", "=" * 8 + f" {title} " + "=" * 8] + list(lines)


def make_all(facts: R.Facts, seed: str, switches: dict | None = None, topts: dict | None = None,
             enemy_tables=None, skill_rows=None, achieve=None, stats_tables=None, ropts: dict | None = None,
             music_tables=None, recruit_tables=None, chest_rows=None,
             chest_offsets=None) -> tuple[dict, dict[str, bytes]]:
    o = check_topts(topts)
    ro = check_ropts(ropts)
    r_on = ro["recruit"] != "off"
    on = active(o)
    sw = dict(switches or {})
    if sw.pop("children", False):           # the old switch name: the children track, never slice 1 (WIRE_56 s.1)
        o["children"] = True
        on = active(o)
    sections: list[tuple[str, list[str]]] = []
    track_guards: dict[str, dict] = {}
    writes: list[tuple] = []        # (module, table, row key, column, old, new) for the cross guard one_writer_per_cell

    # step 1, the character shuffle (WIRE_56 section 2): every later step plans on the shuffled army. Off = recruit.py
    # is not even imported and facts stay the same object (R8).
    r_edits: list[dict] = []
    rt = None
    if r_on:
        import recruit as RC
        rt = recruit_tables if recruit_tables is not None else RC.load_tables(facts=facts)
        r_edits, r_lines = RC.plan_recruit(rt, seed, ro)
        for k, v in RC.run_guards(rt, r_edits, ro).items():
            track_guards[f"recruit: {k}"] = v
        for e in r_edits:
            if e["table"] == "Person" and e["file"] == RC.MAIN_FILE:
                writes.append(("recruit", "Person", e["label"], e["cell"], e["old"], e["new"]))
            elif e["table"] == "Person":
                writes.append(("recruit", "PersonChapter", (e["file"], R.ival(e["index"])), e["cell"], e["old"],
                               e["new"]))
            elif e["table"] == "DisposUnit":
                writes.append(("recruit", "DisposUnit", (e["file"], R.ival(e["index"])), e["column"], e["old"],
                               e["new"]))
        hook = sum(1 for e in r_edits if e.get("laid_by") == "person_hook")
        eng = [e for e in r_edits if e.get("laid_by") == "engine"]
        r_lines = list(r_lines) + [
            "",
            f"Cells: {sum(1 for e in r_edits if e.get('laid_by') == 'core')} in GameData and the chapter placements, "
            f"{hook} in the route-variant rows (GameData/Person/*_HANDOVER, written as tables/PersonChapter.csv), "
            f"{len(eng)} portrait / name records (plan.json only; the 'keep the face' look does not lay them).",
            "PLAY RANDOMIZED (this mod folder) and the in-game New Game page (round 59, 'keep the face' look) lay "
            "every table cell above, the route-variant rows included."]
        if ro["recruit_look"] == "full":
            # round 75 (b): the records above are laid now (FaceData cells and full.txt), not "for later engine
            # rounds". Only the full swap's line changes; the keep-the-face text stays byte-identical (fingerprints).
            # round 75b: the keep-the-face phrase is fixed too (every fingerprint is re-recorded in round 75b)
            r_lines[-2] = r_lines[-2].replace("(plan.json only; the 'keep the face' look does not lay them)",
                                              "(laid by the full swap below)")
            r_lines.append("Full swap (round 74, robot test only): names, models, portraits (FaceData cells) and the "
                           "names inside dialogue (full.txt, the core's Mess::Get trap) follow the person; a silenced "
                           "spot's voice lines are dropped.")
        sections.append(("Character shuffle (who joins where)", r_lines))
        orig_facts = facts
        facts = RC.shuffled_facts(facts, r_edits)
        if facts is not orig_facts:
            facts.original_facts = orig_facts   # round 75b: "never stricter" is judged on the original rows

    plan = R.make_plan(facts, seed, sw)
    if not any(on.values()) and not r_on:
        files = R.render(facts, plan)               # slice 1 exactly (byte-identical default) ...
        return _with_floor(facts, sw, o, plan, files)   # ... plus round 62's growth floor when growths are random
    # round 75b: the guarantees backstop ("guarantees: timing"): make_plan ran it on slice 1's plan (the default
    # above keeps that one); here it runs again after the even spread, promotions, skills, children and on the final
    # rows (g_checks, _g_guard)
    g_checks = [("slice 1", GU.check(facts, plan))]

    import copy
    plan = copy.deepcopy(plan)
    seed = plan["seed"]
    plan["tracks"] = {}

    # misc "assign evenly": slice 1 again with the even classes, before every track that reads the classes
    mo = misc_opts(o)
    if on["misc"] and mo["assign_evenly"]:
        import misc as M
        before = plan
        classes, ev_lines = M.assign_evenly(facts, plan, seed, mo)
        if classes and any(classes[e["pid"]] != e["job"] for e in plan["persons"] if e["pid"] in classes):
            plan = copy.deepcopy(R.make_plan(facts, seed, sw, classes=classes, carry=before.get("guarantees")))
            plan["tracks"] = {}
        for k, v in M.run_even_guards(facts, before, plan).items():
            track_guards[f"misc: {k}"] = v
        sections.append(("Classes spread evenly (misc track)", ev_lines))
        g_checks.append(("even spread", GU.check(facts, plan)))     # ... after the even spread ...

    # growth: written into the plan's persons, so slice 1's renderer writes it
    if on["growth"]:
        import growth as G
        go = growth_opts(o)
        g_edits, g_lines = G.plan_growth(facts, seed, dict(go, base_plan=plan))
        plan = G.apply_edits(plan, g_edits, go)
        plan.setdefault("tracks", {})["growth"] = {"tool": G.TOOL, "opts": G.check_opts(go), "cells": len(g_edits)}
        bad = G.check_bounds(facts, plan, go)
        track_guards["growth: bounds"] = {"ok": not bad, "detail": bad[:50]}
        sections.append(("Growths and bases (growth track)", g_lines))
    # slice 1's guards again, on the plan as it is now (growth may have changed bases/growths)
    plan["guards"] = R.run_guards(facts, plan)
    for e in plan["persons"]:
        p = facts.by_pid[e["pid"]]
        for c, v in (("job", e["job"]), ("job_low", e["job_low"])):
            if v != p[c]:
                writes.append(("slice1", "Person", e["pid"], c, p[c], v))
    for key, ed in plan["dispos"].items():
        f_, ix = key.rsplit("#", 1)
        for c, v in ed.items():
            if c != "label":
                writes.append(("slice1", "DisposUnit", (f_, int(ix)), c, None, v))

    # promotions, Job part (Master Seal targets; job_low follows; Heart Seal classes)
    p_edits: list[dict] = []
    promo_after = None
    kids = None
    if on["promotions"]:
        import children as C
        import promotions as P
        po = promotions_opts(o)
        kids = [p["label"] for p in C.children(facts)]
        p_full = dict(po, base_plan=plan, low_also=[] if o["children"] else kids)
        p_edits, p_lines = P.plan_promotions(facts, seed, p_full)
        for k, v in P.run_guards(facts, p_edits, p_full).items():
            track_guards[f"promotions: {k}"] = v
        promo_after = P._promotions_after(P.PromoFacts(facts), p_edits)
        plan = P.apply_edits(plan, p_edits, po)
        plan["tracks"][P.TRACK] = {"tool": P.TOOL, "opts": P.check_opts(po), "cells": len(p_edits)}
        lows = {e["label"]: e["new"] for e in p_edits if e["table"] == "Person" and e["cell"] == "job_low"}
        for e in plan["persons"]:                   # slice 1's renderer and the skills track see the new job_low
            if e["pid"] in lows:
                e["job_low"] = lows[e["pid"]]
        for e in p_edits:
            writes.append(("promotions", e["table"], e["label"], e["cell"], e["old"], e["new"]))
        sections.append(("Promotions and Heart Seal classes (promotions track)", p_lines))
        g_checks.append(("promotions", GU.check(facts, plan)))      # ... after promotions ...

    s_edits: list[dict] = []
    rows = skill_rows
    if on["skills"]:
        import skills as S
        so = skills_opts(o)
        rows = skill_rows if skill_rows is not None else S.load_skill_rows()
        s_edits, s_lines = S.plan_skills(facts, seed, dict(so, base_plan=plan, skill_rows=rows))
        for k, v in S.run_guards(facts, s_edits, dict(so, skill_rows=rows)).items():
            track_guards[f"skills: {k}"] = v
        plan["tracks"]["skills"] = {"tool": S.TOOL, "opts": S.check_opts(so), "cells": len(s_edits)}
        for e in s_edits:
            if "file" in e:     # round 61: a route-variant (HANDOVER) row, laid as tables/PersonChapter.csv
                writes.append(("skills", "PersonChapter", (e["file"], R.ival(e["index"])), e["cell"], e.get("old"),
                               e["new"]))
            else:
                writes.append(("skills", "Person", e["label"], e["cell"], e.get("old"), e["new"]))
        sections.append(("Skills (skills track)", s_lines))
        g_checks.append(("skills", GU.check(facts, plan, s_edits)))  # ... after skills (the final skill cells) ...

    # children (class, growths, one skill; the parents stay), with the final promotions
    c_edits: list[dict] = []
    if on["children"]:
        import children as C
        co = children_opts(sw, o)
        if co["personal_skills"] != "keep" or co["skill_slots"] != "keep":
            if rows is None:
                import skills as S
                rows = S.load_skill_rows()
        taken = set()
        if co["personal_skills"] == "random":
            new_personal = {e["label"]: e["new"] for e in s_edits
                            if e["cell"] == "personal_skill.normal" and "file" not in e}
            for p in facts.persons:
                if facts.in_scope(p):
                    taken.add(new_personal.get(p["label"], p.get("personal_skill.normal", "")))
        c_full = dict(co, base_plan=plan, skill_rows=rows, taken_personal=sorted(taken))
        if promo_after is not None:
            c_full["job_promotions"] = promo_after
        c_edits, c_lines = C.plan_children(facts, seed, c_full)
        for k, v in C.run_guards(facts, c_edits, c_full).items():
            track_guards[f"children: {k}"] = v
        plan["tracks"]["children"] = {"tool": C.TOOL, "opts": C.check_opts(co), "cells": len(c_edits)}
        if o["skill_slots"] == "random":
            c_lines = c_lines + ["(skill slots 'random' is 'class' for the children: the track gives a child its "
                                 "class line's skills)"]
        for e in c_edits:
            key = e["label"] if e["table"] == "Person" else (e["file"], e["index"])
            writes.append(("children", e["table"], key, e.get("cell") or e.get("column"), e["old"], e["new"]))
        sections.append(("Children (children track)", c_lines))
        g_checks.append(("children", GU.check(facts, plan, s_edits)))   # ... after children (never counted) ...

    i_edits: list[dict] = []
    if on["items"]:
        import items as I
        io_ = items_opts(o)
        full = dict(io_, slice1_plan=plan, achieve=achieve if achieve is not None else I.load_achieve())
        i_edits, i_lines = I.plan_items(facts, I.sub_rng(seed, I.TRACK, io_), full)
        for k, v in I.check_items(facts, i_edits, full).items():
            track_guards[f"items: {k}"] = v
        plan["tracks"]["items"] = {"tool": I.TOOL_VERSION, "opts": io_,
                                   "rows": {t: sum(1 for e in i_edits if e["table"] == t)
                                            for t in sorted({e["table"] for e in i_edits})}}
        for e in i_edits:
            key = (e["file"], e["index"]) if e["table"] == "DisposUnit" else e["label"]
            for c, v in e["cells"].items():
                writes.append(("items", e["table"], key, c, None, v))
        sections.append(("Items, shops and castle rewards (items track)", i_lines))

    need_et = on["enemies"] or (on["weapons"] and (o["enemy_upgrade"] > 0 or o["boss_stats"] != "off")) or (
        on["misc"] and (o["enemy_drops"] > 0 or o["class_move"] != "off"))
    t = None
    if need_et:
        import enemies as E
        t = enemy_tables if enemy_tables is not None else E.load_tables()

    e_edits: list[dict] = []
    if on["enemies"]:
        import enemies as E
        eo = enemies_opts(o)
        e_edits, e_lines = E.plan_enemies(t, E.track_rng(seed, eo), eo)
        for k, v in E.run_guards(t, e_edits, eo).items():
            track_guards[f"enemies: {k}"] = v
        plan["tracks"]["enemies"] = {"tool": E.TOOL_VERSION, "opts": dict(E.DEFAULT_OPTS, **eo),
                                     "cells": len(e_edits)}
        for e in e_edits:
            writes.append(("enemies", "DisposUnit", (e["file"], e["index"]), e["column"], e["old"], e["new"]))
        sections.append(("Enemies (enemies track)", e_lines))

    # stats: Job growth / base / enemy growth cells and PersonChapter level / boss bases
    st_edits: list[dict] = []
    st_files: dict[str, bytes] = {}
    if on["stats"]:
        import stats as ST
        sto = stats_opts(o)
        stt = stats_tables if stats_tables is not None else ST.load_tables()
        st_edits, st_lines = ST.plan_stats(stt, seed, sto)
        for k, v in ST.run_guards(stt, st_edits, sto).items():
            track_guards[f"stats: {k}"] = v
        plan["tracks"]["stats"] = {"tool": ST.TOOL, "opts": ST.check_opts(sto), "cells": len(st_edits)}
        st_files = ST.edits_to_files(stt, st_edits)
        for e in st_edits:
            key = e["label"] if e["table"] == "Job" else (e["file"], e["index"])
            writes.append(("stats", e["table"], key, e["cell"], e["old"], e["new"]))
        sections.append(("Class and enemy stats (stats track)", st_lines))

    # the enemy tables as the enemies track left them (final classes and items), for drops and movement
    t1 = _tables_with_edits(t, e_edits) if t is not None else None
    m_drop: list[dict] = []
    m_move: list[dict] = []
    misc_lines: list[str] = []
    if on["misc"] and mo["enemy_drops"]:
        import misc as M
        m_drop, d_lines = M.plan_drops(t1, seed, mo)
        for k, v in M.run_drop_guards(t1, m_drop, mo).items():
            track_guards[f"misc: {k}"] = v
        for e in m_drop:
            writes.append(("misc", "DisposUnit", (e["file"], e["index"]), e["column"], e["old"], e["new"]))
        misc_lines += d_lines

    # weapons: on the original rows plus the drop marks (a marked slot is never upgraded), after the enemies chain
    w_edits: list[dict] = []
    if on["weapons"]:
        import weapons as W
        wo = weapons_opts(o)
        tw = _tables_with_edits(t, m_drop) if t is not None else facts
        w_full = dict(wo, enemies_edits=e_edits)
        if wo.get("boss_forge"):            # round 62: tougher bosses' weapons (the stats track's boss rows)
            import stats as ST
            w_full["boss_rows"] = ST.boost_rows(stt, sto)
            w_full["refine"] = W.load_refine()
        w_edits, w_lines = W.plan_weapons(tw, W.sub_rng(seed, wo), w_full)
        for k, v in W.check_weapons(tw, w_edits, w_full).items():
            track_guards[f"weapons: {k}"] = v
        plan["tracks"]["weapons"] = {"tool": W.TOOL_VERSION, "opts": W.norm_opts(wo), "cells": len(w_edits)}
        for e in w_edits:
            if e["table"] == "Item":
                for c, v in e["cells"].items():
                    writes.append(("weapons", "Item", e["label"], c, None, v))
            else:
                writes.append(("weapons", "DisposUnit", (e["file"], e["index"]), e["column"], e["old"], e["new"]))
        sections.append(("Weapons (weapons track)", w_lines))

    if on["misc"] and mo["class_move"] != "off":
        import misc as M
        m_move, mv_lines = M.plan_movement(t1, seed, mo)
        for k, v in M.run_move_guards(t1, m_move, mo).items():
            track_guards[f"misc: {k}"] = v
        for e in m_move:
            writes.append(("misc", "Job", e["label"], e["column"], e["old"], e["new"]))
        misc_lines += mv_lines
    if on["misc"]:
        import misc as M
        plan["tracks"]["misc"] = {"tool": M.TOOL, "opts": M.check_opts(mo), "cells": len(m_drop) + len(m_move)}
        if misc_lines:
            sections.append(("Enemy drops and class movement (misc track)", misc_lines))

    # music (map and battle themes): romfs/map/config files and PersonChapter / Person combat_music cells
    mu_edits: list[dict] = []
    mu_files: dict[str, bytes] = {}
    if on["music"]:
        import music as MU
        mt = music_tables if music_tables is not None else MU.load_tables()
        muo = music_opts(o)
        mu_edits, mu_lines = MU.plan_music(mt, seed, muo)
        for k, v in MU.run_guards(mt, mu_edits, muo).items():
            track_guards[f"music: {k}"] = v
        plan["tracks"]["music"] = {"tool": MU.TOOL, "opts": MU.check_opts(muo), "cells": len(mu_edits)}
        mu_files = MU.edits_to_files(mt, mu_edits)
        for e in mu_edits:
            if e["table"] == "MapConfig":
                writes.append(("music", "MapConfig", e["file"], e["cell"], e["old"], e["new"]))
            elif e["table"] == "PersonChapter":
                writes.append(("music", "PersonChapter", (e["file"], R.ival(e["index"])), e["cell"], e["old"],
                               e["new"]))
            else:
                writes.append(("music", "Person", e["label"], e["cell"], e["old"], e["new"]))
        sections.append(("Music (music track)", mu_lines))

    # Nuzlocke: no table edits ever; with it on, the rules file nuzlocke.json for the game core (engine round E2)
    nz_rules = None
    if on["nuzlocke"]:
        import nuzlocke as NZ
        nzo = nuzlocke_opts(o)
        _none, nz_lines = NZ.plan_nuzlocke(facts, seed, nzo)
        nz_rules = NZ.make_rules(facts, nzo)
        plan["tracks"]["nuzlocke"] = {"tool": NZ.TOOL, "opts": NZ.check_opts(nzo), "cells": 0}
        sections.append(("Nuzlocke (rules file nuzlocke.json; the game core keeps them from engine round E2)",
                         nz_lines))

    # chests, villages and talk gifts (round 71): no table cell at all; plan.json's "chests" list and the chest list
    # file chests.txt that the game core's hook reads (patch 0031). Off = chests.py is not even imported.
    ch_entries: list[dict] = []
    if on["chests"]:
        import chests as CH
        cho = chests_opts(o)
        ch_rows = chest_rows if chest_rows is not None else CH.scan(CH.active_dirs())[0]
        ch_entries, ch_lines = CH.plan_chests(facts, ch_rows, seed, cho)
        track_guards.update(CH.check_chests(facts, ch_rows, ch_entries, cho))     # keys already "chests: ..."
        plan["tracks"]["chests"] = {"tool": CH.TOOL_VERSION, "opts": dict(CH.DEFAULT_OPTS, **cho),
                                    "cells": len(ch_entries)}
        sections.append(("Chests, villages and talk gifts (chests track; the game core's chest hook gives them)",
                         ch_lines))

    # cross guards on the final edits of every module (WIRE_56 section 2a); only with a round-W1 / W2 module or the shuffle on, so the
    # plan and spoiler of a seed with only the round-49 tracks stay byte for byte as before
    w1_on = any(on[k] for k in ("children", "promotions", "stats", "weapons", "misc", "music")) or r_on
    for k, v in (cross_guards if w1_on else _no_cross)(facts, plan, o, writes, t, e_edits, w_edits, m_move, p_edits, c_edits, promo_after,
                             kids).items():
        track_guards[f"cross: {k}"] = v

    if r_on:
        import recruit as RC
        plan["tracks"] = dict({"recruit": {"tool": RC.TOOL, "opts": ro,
                                           "cells": sum(1 for e in r_edits if e.get("laid_by") in ("core", "person_hook"))}},
                              **plan["tracks"])
        plan["ropts"] = ro
        eng = [e for e in r_edits if e.get("laid_by") == "engine"]
        if eng:
            plan["recruit_engine"] = eng
    g_checks.append(("final", GU.check(facts, plan, s_edits)))    # ... and on the final rows
    track_guards["guarantees: timing"] = _g_guard(g_checks)
    plan["topts"] = stored_topts(o)
    plan["guards"].update(track_guards)
    if ch_entries:
        import chests as CH
        CH.add_to_plan(plan, ch_entries)
    files = R.render(facts, plan)
    if ch_entries:
        offs = chest_offsets if chest_offsets is not None else CH.label_offsets({e["new"] for e in ch_entries})
        try:
            files[CH.LIST_FILE] = CH.engine_list(ch_entries, offs, seed).encode("ascii")
        except CH.ChestsError as ex:
            raise R.RandoError(f"chests: {ex}") from None

    # Person: the skill cells (new columns on slice 1's rows), the children's rows, the promotions' cells
    if s_edits:
        import skills as S
        files["tables/Person.csv"] = S.person_csv_with_edits(facts, files["tables/Person.csv"], s_edits)
    # DisposUnit: slice 1's item cells, then the items track's (team 0), the enemies track's (team 1), the weapons
    # track's upgrades (after the enemies track) and the misc drop flags; then the children's rows
    if i_edits or e_edits or w_edits or m_drop:
        files["tables/DisposUnit.csv"] = _dispos_csv(facts, plan, i_edits, e_edits,
                                                     [e for e in w_edits if e["table"] == "DisposUnit"], m_drop)
    if c_edits:
        import children as C
        files = C.files_with_edits(facts, files, c_edits)
    if p_edits:
        import promotions as P
        files = P.files_with_edits(facts, files, [e for e in p_edits if e["table"] == "Person"])
    # Job: promotions' promotion cells, stats' growth / base / enemy growth cells, misc's Move; one row per class
    job_cells = [(e["label"], e["cell"], e["new"]) for e in p_edits if e["table"] == "Job"]
    job_cells += [(e["label"], e["cell"], e["new"]) for e in st_edits if e["table"] == "Job"]
    job_cells += [(e["label"], e["column"], e["new"]) for e in m_move]
    if job_cells:
        files["tables/Job.csv"] = _job_csv(facts, job_cells)
    # PersonChapter (GameData/Person/**): stats' level / boss bases, music's combat_music, the shuffle's route-variant
    # (HANDOVER) rows; one module alone keeps its own CSV byte for byte, several are merged by row and column
    pc_parts = []
    if "tables/PersonChapter.csv" in st_files:
        pc_parts.append(("stats", st_files["tables/PersonChapter.csv"]))
    if "tables/PersonChapter.csv" in mu_files:
        pc_parts.append(("music", mu_files["tables/PersonChapter.csv"]))
    r_pc: dict[tuple, dict] = {}
    for e in r_edits:
        if e["table"] == "Person" and e.get("laid_by") == "person_hook":
            r_pc.setdefault((e["file"], R.ival(e["index"])), {})[e["cell"]] = e["new"]
    if s_edits:                     # round 61: the skills track's route-variant rows (after the shuffle's: they win)
        import skills as S
        for k, cs in S.variant_cells(s_edits).items():
            r_pc.setdefault(k, {}).update(cs)
    if len(pc_parts) == 1 and not r_pc:
        files["tables/PersonChapter.csv"] = pc_parts[0][1]
    elif pc_parts or r_pc:
        files["tables/PersonChapter.csv"] = _person_chapter_csv(pc_parts, r_pc, rt)
    # music: whole romfs/map/config files, and a resident Person row's combat_music if one changes
    for rel, data in mu_files.items():
        if rel.startswith("romfs/"):
            files[rel] = data
    mu_person = {}
    for e in mu_edits:
        if e["table"] == "Person":
            mu_person.setdefault(e["label"], {})[e["cell"]] = e["new"]
    if mu_person:
        files["tables/Person.csv"] = _overlay_person(facts, files.get("tables/Person.csv"), mu_person, csv_wins=False)
    # the shuffle's own cells that no later step wrote: every later step planned on the shuffled facts, so a cell
    # already in the CSV holds the later value (it wins); the others get the shuffle's value
    if r_on:
        rp: dict[str, dict] = {}
        rd: dict[tuple, dict] = {}
        for e in r_edits:
            if e["table"] == "Person" and e.get("laid_by") == "core":
                rp.setdefault(e["label"], {})[e["cell"]] = e["new"]
            elif e["table"] == "DisposUnit":
                rd.setdefault((e["file"], R.ival(e["index"])), {})[e["column"]] = e["new"]
        if rp:
            files["tables/Person.csv"] = _overlay_person(facts, files.get("tables/Person.csv"), rp, csv_wins=True)
        if rd:
            files["tables/DisposUnit.csv"] = _overlay_dispos(facts, files.get("tables/DisposUnit.csv"), rd)
    if nz_rules is not None:
        files["nuzlocke.json"] = (json.dumps(nz_rules, indent=1, ensure_ascii=False, sort_keys=True)
                                  + "\n").encode("utf-8")
    # Item / AchieveBonusBattle / AchieveBonusVisit (items), Item (weapons): merged by item and column
    other = [e for e in i_edits if e["table"] != "DisposUnit"]
    w_items = [e for e in w_edits if e["table"] == "Item"]
    if w_items:
        other = _merge_item_edits(other, w_items)
    if other:
        import items as I
        files = I.edits_to_files(facts, other, files)

    meta = json.loads(files["mod.json"].decode("utf-8"))
    meta["description"] = meta["description"].replace(
        "Randomizer slice 1,", "Randomizer (slice 1 + tracks: " + ", ".join(k for k, v in on.items() if v) + "),")
    meta["randomizer"]["topts"] = stored_topts(o)
    meta["randomizer"]["tracks"] = {k: plan["tracks"][k]["tool"] for k in plan["tracks"]}
    if r_on:
        meta["randomizer"]["ropts"] = ro
        meta["description"] = meta["description"].replace("(slice 1 + tracks: ", "(slice 1 + tracks: recruit, ", 1)
    files["mod.json"] = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    extra = [f"options: {topts_text(o)}"] + ([f"character shuffle: {ropts_text(ro)}"] if r_on else [])
    for title, lines in sections:
        extra += _section(title, lines)
    sp = files["spoiler.txt"].decode("utf-8")
    files["spoiler.txt"] = (sp + "\n".join(extra) + "\n").encode("utf-8")
    return _with_floor(facts, sw, o, plan, files)


def _g_guard(checks: list[tuple[str, dict]]) -> dict:
    """Round 75b: the backstop cross guard "guarantees: timing" from guarantees.check after every class- or
    skill-changing step: the last check's lines, plus every earlier step that missed a need (named)."""
    last = checks[-1][1]
    bad = [f"after {stage}: {d}" for stage, c in checks[:-1] if not c["ok"]
           for d in c["detail"] if "NOBODY" in d or "without a staff" in d]
    ok = last["ok"] and not bad
    return {"ok": ok, "detail": bad[:20] + last["detail"] + [f"checked after: {', '.join(s for s, _ in checks)}"]}


def _with_floor(facts: R.Facts, sw: dict, o: dict, plan: dict, files: dict) -> tuple[dict, dict]:
    """Round 62 (F-049): the growth floor, the very last step (growth.apply_floor): every total growth of the army
    and the children in 20..100 when growths are randomized. Its guard and cells go into plan.json, its lines and
    the final growth table at the end of the spoiler."""
    import growth as G
    if not G.floor_on(sw, o):
        return plan, files
    import copy
    plan = copy.deepcopy(plan)
    files, lines = G.apply_floor(facts, files, plan)
    sp = files["spoiler.txt"].decode("utf-8")
    files["spoiler.txt"] = (sp + "\n".join(_section("Growth floor (round 62)", lines)) + "\n").encode("utf-8")
    return plan, files


def _tables_with_edits(t, edits: list[dict]):
    """A shallow copy of an EnemyTables whose placement rows carry these DisposUnit cell edits (the original rows
    are never changed). No edits -> t itself."""
    if not edits:
        return t
    import copy
    by: dict[tuple, dict] = {}
    for e in edits:
        k = (e["file"], R.ival(e["index"]))
        by.setdefault(k, {})[e["column"]] = e["new"]
    t2 = copy.copy(t)
    t2.dispos = [dict(d, **by[(d["file"], R.ival(d["index"]))]) if (d["file"], R.ival(d["index"])) in by else d
                 for d in t.dispos]
    t2._reach_cache = {}
    return t2


def _merge_item_edits(a: list[dict], b: list[dict]) -> list[dict]:
    """Item edits of two tracks merged by item (one row each; the columns never overlap: items writes shop stock,
    weapons the weapon stats; a clash is reported by the cross guard and the later track's value is kept)."""
    out: dict[tuple, dict] = {}
    for e in a + b:
        k = (e["table"], e["label"])
        if k in out:
            out[k] = dict(out[k], cells=dict(out[k]["cells"], **e["cells"]))
        else:
            out[k] = dict(e, cells=dict(e["cells"]))
    return list(out.values())


JOB_COL_ORDER = (["promotion.1", "promotion.2"] + [f"base.{s}" for s in R.STATS] + [f"growth.{s}" for s in R.STATS]
                 + [f"enemy_growth.{s}" for s in R.STATS] + ["mov"])


def _job_csv(facts: R.Facts, cells: list[tuple]) -> bytes:
    """tables/Job.csv with every module's Job cells: one row per class, the columns any module wrote (a row's
    other columns keep the original value)."""
    by: dict[str, dict] = {}
    for jid, col, v in cells:
        by.setdefault(jid, {})[col] = v
    used = {c for v in by.values() for c in v}
    cols = [c for c in JOB_COL_ORDER if c in used] + sorted(used - set(JOB_COL_ORDER))
    out = [["index", "label"] + cols]
    for jid in sorted(by, key=lambda x: R.ival(facts.jobs[x]["index"])):
        j = facts.jobs[jid]
        out.append([str(R.ival(j["index"])), jid] + [str(by[jid].get(c, j.get(c, ""))) for c in cols])
    return R._csv(out)


def _dispos_csv(facts: R.Facts, plan: dict, i_edits: list[dict], e_edits: list[dict],
                w_edits: list[dict] | None = None, m_drop: list[dict] | None = None) -> bytes:
    orig = {(d["file"], R.ival(d["index"])): d for d in facts.dispos}
    rows: dict[tuple, dict] = {}
    for key, ed in plan["dispos"].items():
        f, ix = key.rsplit("#", 1)
        rows.setdefault((f, int(ix)), {}).update({k: v for k, v in ed.items() if k != "label"})
    for e in i_edits:
        if e["table"] == "DisposUnit":
            rows.setdefault((e["file"], e["index"]), {}).update(e["cells"])
    for e in list(e_edits) + list(w_edits or []):     # enemies, then weapons on top (its "old" = the enemies' new)
        k = (e["file"], e["index"])
        cur = rows.get(k, {}).get(e["column"], orig[k].get(e["column"], "") if k in orig else "")
        if k in rows and e["column"] in rows[k] and rows[k][e["column"]] != e["old"]:
            raise R.RandoError(f"DisposUnit {k}: {e['column']} written by two tracks")
        if str(cur) != str(e["old"]):
            raise R.RandoError(f"DisposUnit {k}: {e['column']} old value {e['old']!r} is not {cur!r}")
        rows.setdefault(k, {})[e["column"]] = e["new"]
    flag_cols = []
    for e in m_drop or []:
        k = (e["file"], e["index"])
        if e["column"] in rows.get(k, {}):
            raise R.RandoError(f"DisposUnit {k}: {e['column']} written by two tracks")
        rows.setdefault(k, {})[e["column"]] = e["new"]
        if e["column"] not in flag_cols:
            flag_cols.append(e["column"])
    cols = (["jid"] if any("jid" in v for v in rows.values()) else []) + [f"item_{s}" for s in range(1, 6)]
    cols += sorted(flag_cols)
    # round 62: the weapons track's forge cells (one step stronger, tougher bosses); only when one is written
    used = {c for v in rows.values() for c in v}
    cols += [f"item_{s}_forge.{x}" for s in range(1, 6) for x in ("normal", "hard", "lunatic")
             if f"item_{s}_forge.{x}" in used]
    out = [["file", "index", "label"] + cols]
    for k in sorted(rows):
        d = orig[k]
        out.append([k[0], str(k[1]), d.get("label", "")] + [rows[k].get(c, d.get(c, "")) for c in cols])
    return R._csv(out)


# ------------------------------------------------------------------ CSV overlays (round W2)
BOM = chr(0xFEFF)


def _read_csv(data: bytes | None) -> tuple[list[str] | None, list[list[str]]]:
    if not data:
        return None, []
    import csv
    import io
    rows = list(csv.reader(io.StringIO(data.decode("utf-8").lstrip(BOM))))
    return (rows[0], rows[1:]) if rows else (None, [])


def _overlay(data: bytes | None, ids: list[str], key_of, cells: dict, base_of, csv_wins: bool, sort_key) -> bytes:
    """A table CSV (or none) with more cells: cells {row key: {column: value}}; base_of(key) -> the full row the
    unwritten cells come from (the CSV's ID columns included). csv_wins: a cell the CSV already writes keeps the
    CSV's value; else the new value replaces it."""
    head, body = _read_csv(data)
    head = list(head or ids)
    rows = {key_of(r): dict(zip(head, r)) for r in body}
    extra: list[str] = []
    for cs in cells.values():
        for c in cs:
            if c not in head and c not in extra:
                extra.append(c)
    for k, cs in cells.items():
        if k not in rows:
            b = base_of(k)
            rows[k] = {c: str(b.get(c, "")) for c in head}
            rows[k].update(cs)
            continue
        for c, v in cs.items():
            if c in extra or not csv_wins:
                rows[k][c] = v
    nhead = head + extra
    out = [nhead]
    for k in sorted(rows, key=sort_key):
        b = None
        row = []
        for c in nhead:
            if c not in rows[k]:
                b = b if b is not None else base_of(k)
                rows[k][c] = str(b.get(c, ""))
            row.append(rows[k][c])
        out.append(row)
    return R._csv(out)


def _overlay_person(facts: R.Facts, data: bytes | None, cells: dict, csv_wins: bool) -> bytes:
    return _overlay(data, ["index", "label"], lambda r: r[1], cells, lambda k: facts.by_pid[k], csv_wins,
                    lambda k: R.ival(facts.by_pid[k]["index"]))


def _overlay_dispos(facts: R.Facts, data: bytes | None, cells: dict) -> bytes:
    by = {(d["file"], R.ival(d["index"])): d for d in facts.dispos}
    return _overlay(data, ["file", "index", "label"], lambda r: (r[0], int(r[1])), cells, lambda k: by[k], True,
                    lambda k: k)


def _person_chapter_csv(parts: list[tuple[str, bytes]], r_pc: dict, rt) -> bytes:
    """Several modules' PersonChapter cells in one CSV (row = (file, index)); the unwritten cells from the
    original rows (the shuffle's own route-variant rows, else the game's PersonChapter rows, read once)."""
    orig: dict[tuple, dict] = {}
    if rt is not None:
        orig.update({(h["file"], R.ival(h["index"])): h for h in rt.handover})
    loaded = []

    def base_of(k):
        if k not in orig and not loaded:
            import gamedata as GD
            loaded.append(1)
            for r in GD._load("PersonChapter"):
                orig.setdefault((r["file"], R.ival(r["index"])), r)
        return orig[k]

    data = None
    cells: dict[tuple, dict] = {}
    for _name, b in parts:
        head, body = _read_csv(b)
        if data is None:
            data = b
            continue
        for r in body:
            cells.setdefault((r[0], int(r[1])), {}).update({c: v for c, v in zip(head[3:], r[3:])})
    for k, cs in r_pc.items():
        cells.setdefault(k, {}).update(cs)
    return _overlay(data, ["file", "index", "label"], lambda r: (r[0], int(r[1])), cells, base_of, False,
                    lambda k: k)


# ------------------------------------------------------------------ cross guards (WIRE_56 section 2a)
def _no_cross(*_a) -> dict:
    return {}



CHAINS = {("slice1", "items", "DisposUnit"), ("enemies", "weapons", "DisposUnit"),
          ("slice1", "promotions", "Person")}


def cross_guards(facts: R.Facts, plan: dict, o: dict, writes: list[tuple], t, e_edits: list[dict],
                 w_edits: list[dict], m_move: list[dict], p_edits: list[dict], c_edits: list[dict],
                 promo_after: dict | None, kids: list[str] | None) -> dict:
    out: dict[str, dict] = {}

    def g(name, bad, info=None):
        out[name] = {"ok": not bad, "detail": bad[:50] + list(info or [])}

    # 1. job_low_fits_final_promotions: every army Person row (children included) whose class line the promotions
    #    track redrew has a job_low among the final promotions of its final class
    bad, n = [], 0
    if promo_after is not None and any(e["table"] == "Job" for e in p_edits):
        import children as C
        import promotions as P
        pf = P.PromoFacts(facts)
        final = {p["label"]: {"job": p["job"], "job_low": p["job_low"]} for p in facts.persons}
        for e in plan["persons"]:
            final[e["pid"]].update(job=e["job"], job_low=e["job_low"])
        for e in p_edits:
            if e["table"] == "Person" and e["cell"] == "job_low":
                final[e["label"]]["job_low"] = e["new"]
        for e in c_edits:
            if e["table"] == "Person" and e["cell"] in ("job", "job_low"):
                final[e["label"]][e["cell"]] = e["new"]
        army = [p for p in facts.persons if facts.in_scope(p)] + C.children(facts)
        for p in army:
            a = final[p["label"]]
            j = facts.jobs.get(a["job"])
            if (not j or not a["job_low"] or a["job_low"] == pf.none or P.kept_row(facts, p) or a["job"] in pf.beast
                    or a["job"] not in pf.targets + pf.sources):
                continue
            n += 1
            if facts.promoted(j):
                if a["job"] not in promo_after.get(a["job_low"], []):
                    bad.append(f"{p['label']}: job_low {a['job_low']} does not promote into {a['job']}")
            elif a["job_low"] not in promo_after.get(a["job"], []):
                bad.append(f"{p['label']}: job_low {a['job_low']} is not a promotion of {a['job']}")
        g("job_low_fits_final_promotions", bad, [f"{n} army rows checked"])
    else:
        g("job_low_fits_final_promotions", [], ["promotions off: the Job rows' promotions are the original ones"])

    # 2. no_stuck_final: every enemy whose class or Move changed still reaches 3/4 of its old tiles in 3 turns
    bad, n = [], 0
    if t is not None and (e_edits or m_move):
        import misc as M
        new_mov = {e["label"]: R.ival(e["new"]) for e in m_move}
        jid_new = {(e["file"], R.ival(e["index"])): e["new"] for e in e_edits if e["column"] == "jid"}
        cache: dict = {}
        for d in t.dispos:
            if str(d.get("team")) not in ("1", "2") or not d.get("pid"):
                continue
            k = (d["file"], R.ival(d["index"]))
            oj = t.unit_job(d)
            nj = jid_new.get(k, oj)
            if not oj or oj not in facts.jobs or nj not in facts.jobs:
                continue
            if nj == oj and nj not in new_mov:
                continue
            ch = M._chapter(d)
            x, y = R.ival(d.get("pos.x", -1)), R.ival(d.get("pos.y", -1))
            if t.tile_col(ch, x, y) is None:
                continue
            J0, J1 = t.f.jobs[oj], t.f.jobs[nj]
            r0 = M._reach(t, ch, x, y, R.ival(J0["move_cost_class"]), R.ival(J0["mov"]), cache)
            r1 = M._reach(t, ch, x, y, R.ival(J1["move_cost_class"]), new_mov.get(nj, R.ival(J1["mov"])), cache)
            n += 1
            if new_mov.get(nj, R.ival(J1["mov"])) < R.ival(J1["mov"]) or nj != oj:
                if r1 < M.REACH_RATIO * r0:
                    bad.append(f"{d['file']}#{k[1]} ({oj} -> {nj}): reaches {r1} tiles instead of {r0}")
        g("no_stuck_final", bad, [f"{n} enemy units with a new class or Move checked"])
    else:
        g("no_stuck_final", [], ["no enemy class or Move changed"])

    # 3. weapons_usable_final: every weapon a track put into an enemy's hands (or kept through a class change) is
    #    usable by its final class
    bad, n = [], 0
    if t is not None and (e_edits or [e for e in w_edits if e["table"] == "DisposUnit"]):
        rows: dict[tuple, dict] = {}
        by = {(d["file"], R.ival(d["index"])): d for d in t.dispos}
        touched: dict[tuple, set] = {}
        for e in list(e_edits) + [e for e in w_edits if e["table"] == "DisposUnit"]:
            k = (e["file"], R.ival(e["index"]))
            rows.setdefault(k, dict(by[k]))[e["column"]] = e["new"]
            touched.setdefault(k, set()).add(e["column"])
        for k, row in rows.items():
            d = by[k]
            oj = t.unit_job(d)
            nj = row.get("jid") or oj
            if not oj or oj not in facts.jobs or nj not in facts.jobs:
                continue
            fem = facts.female(facts.jobs[oj])
            for s in range(1, 6):
                c = f"item_{s}"
                iid = row.get(c, "")
                if not iid or facts.item_kind(iid) is None:
                    continue
                if c not in touched[k] and not ("jid" in touched[k] and t.can_hold(oj, fem, d.get(c, ""))):
                    continue
                if R.ival(d.get(f"item_{s}_flags", 0)) & 1 and c not in touched[k]:
                    continue                    # a drop the unit never used: the enemies track keeps it as it was
                n += 1
                if not t.can_hold(nj, fem, iid):
                    bad.append(f"{k[0]}#{k[1]} slot {s}: {iid} not usable by {nj}")
        g("weapons_usable_final", bad, [f"{n} enemy weapons checked"])
    else:
        g("weapons_usable_final", [], ["no enemy class or weapon changed"])

    # 4. one_writer_per_cell: no cell written by two modules with different values, except the listed chains
    bad = []
    last: dict[tuple, tuple] = {}
    for mod, table, key, col, old, new in writes:
        if isinstance(key, tuple) and len(key) == 2:        # (file, index): one spelling of the index for every module
            key = (key[0], R.ival(key[1]))
        k = (table, key, col)
        if k in last:
            pmod, pnew = last[k]
            if pmod != mod and str(pnew) != str(new):
                if (pmod, mod, table) not in CHAINS and pmod != "recruit":
                    bad.append(f"{table} {key} {col}: {pmod}={pnew} and {mod}={new}")
                elif old is not None and str(old) != str(pnew):
                    bad.append(f"{table} {key} {col}: {mod} starts from {old}, not {pmod}'s {pnew}")
        last[k] = (mod, new)
    g("one_writer_per_cell", bad, [f"{len(writes)} cell writes, {len(last)} cells"])
    return out


def guards_ok(plan: dict) -> bool:
    return all(v["ok"] for v in plan["guards"].values())
