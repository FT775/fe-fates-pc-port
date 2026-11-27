#!/usr/bin/env python3
"""Fire Emblem Fates randomizer: slice 1 (class, growth rates, join stats; F-041 #4-5), the four tracks of
round 49 (F-043: growth/base modes, skills, items/shops/rewards, enemy gear and classes) and the five modules wired
in round W1 (F-046 / F-047: children, promotions, stats, weapons, misc; docs/rando/WIRE_56.md) and round W2 (the
character shuffle, music, the Nuzlocke rules file). docs/RANDOMIZER.md.

    python tools/randomizer/rando.py make --seed S [--classes on|off] [--growths on|off] [--join-stats on|off]
                                      [--trees own|any] [--keep-royals on|off] [--children off|on]
                                      [track options, all off by default: see EPILOG / --help]
                                      [--out DIR] [--zakuro-dir DATA]
    python tools/randomizer/rando.py check DIR        re-run every guard on a made mod folder (exit 3: the folder was
                                                       made by another randomizer version, e.g. before round 75b)
    python tools/randomizer/rando.py schema           the in-game page's rows as JSON (F-044; tools/randomizer/ingame.py)
    make ... --patch-out FILE                          also write the in-memory patch the game's New Game page lays
                                                       (docs/RANDOMIZER_INGAME.md; nothing installed, GameData not
                                                       rebuilt on disk)

make writes one normal mod folder (mod.json, tables/Person.csv, tables/DisposUnit.csv when a weapon is
swapped, spoiler.txt, plan.json), the same kind tools/mods/mods.py builds and installs. Default folder:
build/rando/out/Rando-<seed>/. With --zakuro-dir DATA it also builds that one mod with the mods tool and
installs it into DATA/mods/<title>/ (a randomized save's own data folder, e.g. a play/randomizer/<seed>/data
profile); the work folders go next to DATA, never into the owner's mods/ or %APPDATA%.
Same seed and switches -> byte-identical files. With every track option at its default (off / keep / slice1 /
0) the files are exactly slice 1's, so old seeds give the same mod as before; a seed made with only the round-49
tracks on also gives the same files as before round W1 (the W1 options are stored only when not at their default).
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
import tracks as TR  # noqa: E402

DEFAULT_OUT = os.path.join(ROOT, "build", "rando", "out")


def onoff(v: str) -> bool:
    v = v.strip().lower()
    if v in ("on", "yes", "1", "true"):
        return True
    if v in ("off", "no", "0", "false"):
        return False
    raise argparse.ArgumentTypeError("on or off")


def _forbidden(path: str) -> str | None:
    """The owner's Zakuro folders are never written (%APPDATA%, %LOCALAPPDATA%, the repo's mods/)."""
    p = os.path.normcase(os.path.realpath(path))
    for env in ("APPDATA", "LOCALAPPDATA"):
        top = os.environ.get(env)
        if top and (p + os.sep).startswith(os.path.normcase(os.path.realpath(top)) + os.sep):
            return f"{path} is inside %{env}%"
    if (p + os.sep).startswith(os.path.normcase(os.path.realpath(os.path.join(ROOT, "mods"))) + os.sep):
        return f"{path} is inside the owner's mods/ folder"
    return None


def _activate(game: str | None, seal_romfs: str | None) -> str:
    """F-047: point every table read and the rules at this game (sources.activate). "fates" is the original state.
    No --game: the game already active stays (the in-game core's script activates Seal itself before make)."""
    import sources as S
    if game is None:
        if not seal_romfs:
            return S.current()
        game = "seal"
    if game == S.current() and not seal_romfs:
        return game
    try:
        S.activate(game, seal_romfs)
    except S.SourceError as e:
        raise R.RandoError(f"game {game}: {e}") from None
    return game


def _mark_game(plan: dict, files: dict, game: str):
    """A Seal of Flames run says so in plan.json (Fates runs keep their bytes: no "game" key)."""
    plan = dict(plan, game=game)
    p = json.loads(files["plan.json"].decode("utf-8"))
    p["game"] = game
    files = dict(files)
    files["plan.json"] = (json.dumps(p, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    return plan, files


def cmd_make(a) -> int:
    import gamedata as GD
    sw = {"classes": a.classes, "growths": a.growths, "join_stats": a.join_stats, "trees": a.trees,
          "keep_royals": a.keep_royals}
    topts = {k: getattr(a, k) for k in TR.DEFAULT_TOPTS}
    ropts = {k: getattr(a, k) for k in TR.RECRUIT_DEFAULTS}
    game = _activate(a.game, a.seal_romfs)
    if a.patch_out and ropts.get("recruit", "off") != "off" and ropts.get("recruit_look") == "full":
        # round 77 (F-062 open item): look = full is never laid for Seal of Flames outside the robot's test-only
        # switch, whatever asks; refused before anything is written (ingame.look_refusal, GREY_FOR's reason)
        import ingame as IG
        why = IG.look_refusal(game)
        if why:
            raise R.RandoError(f"in-memory patch refused: {why}")
    if game == "seal" and topts.get("children"):
        # round 62 (F-049, owner "seal children being out is fine"): Seal of Flames has no child in its reachable
        # chapters; the page greys the row there, and a make for Seal never turns the children on
        topts["children"] = False
        print("note: Children is off for Seal of Flames (no child in its chapters)")
    cdir = getattr(a, "cache", None) or os.environ.get("FEF_RANDO_CACHE")
    if cdir:
        import cache as CA
        CA.install(cdir, fast_patch=bool(a.patch_out) and not a.zakuro_dir, progress_lines=bool(getattr(a, "progress", False)))
    facts = GD.load_facts()
    plan, files = TR.make_all(facts, a.seed, sw, topts, ropts=ropts)
    recolour = getattr(a, "recolour", "on")
    colour_lines = _colours(facts, plan, files, game, ropts, recolour)
    if recolour != "on":
        plan, files = _mark_recolour(plan, files, recolour)
    if game != "fates":
        plan, files = _mark_game(plan, files, game)
    plan, files = _mark_version(plan, files)       # round 75b: rando_version + guarantees in plan.json and mod.json
    if not getattr(a, "spoiler", True):
        # round 62b (F-050): Spoiler log off writes no spoiler.txt; the plan, the mod files and the patch are the same
        files = {k: v for k, v in files.items() if not k.endswith("spoiler.txt")}
    name = R.mod_name(plan["seed"])
    if a.out:
        out_top = os.path.abspath(a.out)
    elif a.zakuro_dir:
        out_top = os.path.join(os.path.dirname(os.path.abspath(a.zakuro_dir)), "rando-work", "mods")
    else:
        out_top = DEFAULT_OUT
    for p in (out_top, a.zakuro_dir):
        why = p and _forbidden(p)
        if why:
            raise R.RandoError(f"refused: {why}")
    folder = R.write_mod(files, os.path.join(out_top, name))
    bad = [k for k, v in plan["guards"].items() if not v["ok"]]
    changed = sum(1 for e in plan["persons"] if e["job"] != e["old_job"])
    swaps = sum(len(e.get("swaps", [])) for e in plan["persons"])
    print(f"made {folder}")
    print(f"  seed {plan['seed']}; {switches_line(plan)}; {len(plan['persons'])} people, {changed} new classes, "
          f"{swaps} weapon swaps, {len(plan['dispos'])} map placements edited")
    if plan.get("tracks"):
        print(f"  options: {TR.topts_text(TR.check_topts(plan['topts']))}")
        if plan.get("ropts"):
            print(f"  character shuffle: {TR.ropts_text(plan['ropts'])}")
        for k, v in plan["tracks"].items():
            print(f"  track {k}: " + ", ".join(f"{a}={b}" for a, b in v.items() if a not in ("tool", "opts")))
    for k, v in plan["guards"].items():
        print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
    if bad:
        print("guards failed: the mod folder is written for inspection but NOT installed")
        return 2
    if a.patch_out:
        import ingame as IG
        why = _forbidden(a.patch_out)
        if why:
            raise R.RandoError(f"refused: {why}")
        o = TR.check_topts(plan.get("topts"))
        ro = TR.check_ropts(plan.get("ropts"))
        late = [k.replace("_", "-") for k in IG.PAGE_FIXED if k in TR.DEFAULT_TOPTS and o[k] != TR.DEFAULT_TOPTS[k]]
        # round 74 (A7): look = full passes only under the robot's test-only switch (ingame.full_look_allowed);
        # round 77: asked for this run's game (Seal of Flames: the switch only)
        full = ro["recruit"] != "off" and ro["recruit_look"] == "full" and IG.full_look_allowed(game)
        later = [k.replace("_", "-") for k in IG.PAGE_FIXED if k in TR.RECRUIT_DEFAULTS
                 and ro[k] != TR.RECRUIT_DEFAULTS[k] and not (k == "recruit_look" and full)]
        # engine round E2 (round 60): Nuzlocke is kept by the core; only "recruits first" stays out (Grok's pick)
        nz_first = bool(o["nuzlocke"]) and o["recruits"] != "all"
        if later or nz_first:
            raise R.RandoError("in-memory patch refused: " + ", ".join(later + (["recruits"] if nz_first else []))
                               + " cannot be laid by the in-game page yet (" + IG.LOOK_WAITS
                               + "; Nuzlocke's 'one recruit per chapter' is not offered: "
                               "the game cannot tell a story join from a recruit). "
                               "The mod folder is written; PLAY RANDOMIZED can use it.")
        if late:
            raise R.RandoError("in-memory patch refused: " + ", ".join(late) + " cannot be laid by the in-game page "
                               "yet (the stronger-weapons rank waits for its robot check). The mod folder is "
                               "written; PLAY RANDOMIZED can use it.")
        try:
            files = IG.rebuilt_files(out_top, os.path.join(os.path.dirname(out_top), "patch-work"))
            meta = {"switches": plan["switches"], "topts": plan.get("topts")}
            if plan.get("ropts"):
                meta["ropts"] = plan["ropts"]
            swaps = {e["spot"]: e["filler"] for e in plan.get("recruit_engine", []) if e["table"] == "FaceData"}
            fids = {e["fid"]: e["show"] for e in plan.get("recruit_engine", []) if e["table"] == "FaceData"}
            text, summ = IG.make_patch(files, plan["seed"], meta, person_ptrs=full,
                                       face_fids=fids if full else None)
            if colour_lines:
                text = _with_lines(text, colour_lines)
                summ["colour"] = sum(1 for ln in colour_lines if ln.startswith("v "))
        except IG.PatchError as e:
            raise R.RandoError(f"in-memory patch: {e}") from None
        dst = os.path.abspath(a.patch_out)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst + ".tmp", "w", encoding="ascii", newline="\n") as fh:
            fh.write(text)
        os.replace(dst + ".tmp", dst)
        print(f"patch {dst}: {summ['files']} files, {summ['v']} value cells, {summ['p']} label pointers")
        # round 74 (A5; docs/rando/FULL_BLOCK.md section 4): full.txt beside the patch only with look = full (no
        # file = the core never arms the names-and-voices trap); a stale one is removed for every other run
        full_dst = os.path.join(os.path.dirname(dst), "full.txt")
        if full:
            import recruit as RC
            ftext = RC.full_block(RC.load_tables(facts=facts), swaps, plan["seed"], game)
            with open(full_dst + ".tmp", "w", encoding="ascii", newline="\n") as fh:
                fh.write(ftext)
            os.replace(full_dst + ".tmp", full_dst)
            fb = RC.parse_full(ftext)
            print(f"full block {full_dst}: {len(fb['names'])} names, {len(fb['silence'])} voices silenced")
        elif os.path.exists(full_dst):
            os.remove(full_dst)
        # engine round E2: the Nuzlocke rules file beside the patch (the core keeps it with the run; no file = off)
        nz_dst = os.path.join(os.path.dirname(dst), "nuzlocke.json")
        if o["nuzlocke"]:
            import nuzlocke as NZ
            nz_rules = NZ.make_rules(facts, {"nuzlocke": True, "recruits": o["recruits"]})   # this game's tables
            with open(nz_dst + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(nz_rules, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
            os.replace(nz_dst + ".tmp", nz_dst)
            print(f"nuzlocke rules {nz_dst}")
        elif os.path.exists(nz_dst):
            os.remove(nz_dst)
    if a.zakuro_dir:
        sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
        import mods as M
        data = os.path.abspath(a.zakuro_dir)
        os.makedirs(data, exist_ok=True)
        ctx = M.Ctx(mods_dir=out_top, stage_dir=os.path.join(os.path.dirname(out_top), "stage"), zakuro_dir=data)
        others = [m.folder for m in M.load_mods(ctx) if m.folder != name and m.enabled]
        for m in M.load_mods(ctx):
            if m.folder != name and m.enabled:     # one randomizer mod per save: older ones in this folder off
                m.meta["enabled"] = False
                m.save()
        r = M.build(ctx)
        if M.print_build(ctx, r, True):
            print("install cancelled: the build failed; nothing in the data folder was touched")
            return 1
        for line in M.install(ctx):
            print(" ", line)
        print(f"installed into {ctx.title_dir()}" + (f" (switched off here: {', '.join(others)})" if others else ""))
    return 0


def _colours(facts, plan: dict, files: dict, game: str, ropts: dict, recolour: str = "on") -> list[str]:
    """Round 59 (docs/rando/COLOURS.md 5.1): with the shuffle on and the 'keep the face' look, each swapped spot wears
    the new person's hair colour (battle model hair cell + FaceData colour; the picture tint stays off after the
    round-59 review: it damaged dark-to-light portraits). Returns the patch lines (file asset/face + v); the guards go
    into plan["guards"] as "colour: ..." and the spoiler lines after the shuffle's. Round 71 (the page's Recolour
    row): recolour "on" = as before, "clear" = Easier to see (a clearer battle hair, colours.clear_hair), "off" = no
    recolour (no colour line, no colour guard; the spoiler says so)."""
    ro = TR.check_ropts(ropts)
    if ro["recruit"] == "off" or ro.get("recruit_look", "keep") != "keep":
        return []
    if recolour == "off":
        for k in list(files):
            if k.endswith("spoiler.txt"):
                files[k] = files[k] + (b"\nRecolour: off (the page's Recolour row): swapped spots keep the spot's "
                                       b"own hair.\n")
        return []
    import colours as CO
    import recruit as RC
    r_edits, _ = RC.plan_recruit(RC.load_tables(facts=facts), plan["seed"], ro)
    cplan = CO.plan_from(r_edits, facts, "keep")
    t = CO.load_tables(game, facts)
    co = {"pictures": "off"} if recolour == "on" else {"pictures": "off", "recolour": recolour}
    edits, lines = CO.plan_colours(t, cplan, co)
    for k, v in CO.run_guards(t, edits, cplan, co).items():
        plan["guards"][k if k.startswith("colour:") else f"colour: {k}"] = v
    for k in list(files):
        if k.endswith("spoiler.txt") and lines:
            files[k] = files[k] + ("\n" + "\n".join(lines) + "\n").encode("utf-8")
    return CO.patch_lines(edits)


def _mark_recolour(plan: dict, files: dict, recolour: str):
    """Round 71: a run made with the Recolour row away from its default says so in plan.json ("recolour"); at the
    default the plan keeps its bytes (no key)."""
    plan = dict(plan, recolour=recolour)
    p = json.loads(files["plan.json"].decode("utf-8"))
    p["recolour"] = recolour
    files = dict(files)
    files["plan.json"] = (json.dumps(p, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    return plan, files


def rando_version() -> int:
    """Round 75b: the randomizer's version (guarantees.RANDO_VERSION, read lazily through ingame.rando_version)."""
    import ingame as IG
    return IG.rando_version()


def folder_version(plan: dict) -> int:
    """The version a made folder's plan.json says it was made by: its "rando_version"; a plan with neither that key
    nor a "guarantees" block was made before round 75b (randomizer 1)."""
    v = plan.get("rando_version")
    if v is None:
        return 2 if "guarantees" in plan else 1
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def old_folder_sentence(made: int, now: int) -> str:
    """the plain sentence rando.py check prints for a folder made by another version (exit 3)"""
    when = " (before round 75b)" if made < 2 else ""
    return (f"made by randomizer {made}{when}; this tool makes randomizer {now}, so a remake would differ. "
            f"Saved games keep using the folder as it is; make a new game for the new rules.")


def _mark_version(plan: dict, files: dict):
    """Round 75b (docs/SEED_GUARANTEES_PLAN.md section 5 points 4 and 5): plan.json and mod.json's "randomizer" entry
    (the PLAY RANDOMIZED mod folder Rando-<seed>) carry "rando_version" and the plan's "guarantees" block. The code
    part's make (randolib / tracks) may already write them: a key that is there is left as it is, so this adds only
    what is missing and a file that has everything keeps its bytes."""
    now = rando_version()
    files = dict(files)
    p = json.loads(files["plan.json"].decode("utf-8"))
    if "rando_version" not in p:
        p["rando_version"] = now
        files["plan.json"] = (json.dumps(p, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    plan = dict(plan, rando_version=p["rando_version"])
    if "mod.json" in files:
        meta = json.loads(files["mod.json"].decode("utf-8"))
        entry = meta.get("randomizer")
        if isinstance(entry, dict):
            add = {"rando_version": p["rando_version"]}
            if "guarantees" in p:
                add["guarantees"] = p["guarantees"]
            missing = {k: v for k, v in add.items() if k not in entry}
            if missing:
                entry.update(missing)
                files["mod.json"] = (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return plan, files


def _made_by_make(folder: str) -> bool:
    """True when the folder's mod.json carries rando_version in its "randomizer" entry (rando.py make's
    _mark_version wrote it), so check marks the remade files the same way."""
    try:
        with open(os.path.join(folder, "mod.json"), encoding="utf-8") as fh:
            entry = json.load(fh).get("randomizer")
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(entry, dict) and "rando_version" in entry


def _with_lines(text: str, extra: list[str]) -> str:
    """the patch text with extra file/v lines before its end line (the count grows by the v lines)."""
    body, end = text.rstrip("\n").rsplit("\n", 1)
    n = int(end.split(" ")[1]) + sum(1 for ln in extra if ln.startswith(("v ", "tint ")))
    return body + "\n" + "\n".join(extra) + f"\nend {n}\n"


def switches_line(plan: dict) -> str:
    return R.switches_text(plan["switches"])


def cmd_check(a) -> int:
    import gamedata as GD
    folder = os.path.abspath(a.dir)
    with open(os.path.join(folder, "plan.json"), encoding="utf-8") as fh:
        plan = json.load(fh)
    # round 75b (docs/SEED_GUARANTEES_PLAN.md section 5 point 4): a folder made by another version of the randomizer
    # (before the seed guarantees: no rando_version, no guarantees block) is not remade: today's make would differ.
    # Exit 3, not a guard failure (1) and not a refused make (2). No frozen copy of the old maker is kept (call 10).
    made, now = folder_version(plan), rando_version()
    if made != now:
        print(f"{folder}: {old_folder_sentence(made, now)}")
        return 3
    game = _activate(a.game or plan.get("game", "fates"), a.seal_romfs)
    facts = GD.load_facts()
    again, files = TR.make_all(facts, plan["seed"], plan["switches"], plan.get("topts"), ropts=plan.get("ropts"))
    if game != "fates":
        again, files = _mark_game(again, files, game)
    if plan.get("recolour", "on") != "on":
        again, files = _mark_recolour(again, files, plan["recolour"])
    if _made_by_make(folder):    # made through rando.py make (a folder written by randolib alone keeps its bytes)
        again, files = _mark_version(again, files)
    def norm(rel: str, data: bytes):
        if rel == "mod.json":   # the mods tool's enable/disable switch is the user's, not the randomizer's
            m = json.loads(data.decode("utf-8"))
            m.pop("enabled", None)
            return m
        return data

    same = all(os.path.exists(os.path.join(folder, *rel.split("/"))) and
               norm(rel, open(os.path.join(folder, *rel.split("/")), "rb").read()) == norm(rel, data)
               for rel, data in files.items())
    guards = again["guards"]
    ok = same and all(v["ok"] for v in guards.values())
    print(f"{folder}: remade from seed {plan['seed']} -> {'byte-identical' if same else 'DIFFERENT'}")
    for k, v in guards.items():
        print(f"  {'PASS' if v['ok'] else 'FAIL'} {k}")
    return 0 if ok else 1


EPILOG = """make flags: --seed S  --classes on|off  --growths on|off  --join-stats on|off  --trees own|any
            --keep-royals on|off  --children off|on  --out DIR  --zakuro-dir DATA
            --game fates|seal  --seal-romfs DIR   (F-047: Seal of Flames' own tables, docs/rando/SEAL.md)
track options (default first; the defaults change nothing):
  Stats:   --growth-mode slice1|redistribute|delta|full  --growth-variance 30  --growth-min 5  --growth-max 80
           --adjust-hp off|on  --bases-mode slice1|redistribute|delta  --base-variance 5  --scale-to-level on|off
  Skills:  --personal-skills keep|shuffle|random  --skill-slots keep|class|random
  Items:   --starting-items off|on  --shops off|on  --shop-sides own|mixed  --rewards off|on
  Enemies: --enemy-weapons off|on  --enemy-classes off|on  --boss-classes off|on  --enemy-trees own|any
  Round W1 (docs/rando/WIRE_56.md section 1):
  Classes: --assign-evenly off|on  --promotions off|on  --promotion-sides any|own  --reclass keep|random
           --class-move off|small|wide
  Stats:   --class-growths off|delta  --class-growth-variance 10  --class-bases off|delta  --class-base-variance 2
           --enemy-growths off|flat|scaling  --enemy-buff 10  --enemy-levels 0  --boss-stats off|linear|ease
           --boss-max-boost 5  --boss-variance 0
  Weapons: --weapon-stats off|on  --weapon-traits 0  --wild-traits off|on  --enemy-upgrade 0  --upgrade-rank same|next
           (round 62: upgrade-rank is replaced by --difficulty; it is still taken and changes nothing)
  Round 62: --difficulty easy|normal|hard  (default normal) how far stronger enemy weapons go (easy +1 forge;
           normal the next tier of the same ladder, else +1 forge; hard the next tier and +1 forge, else +2) and the
           tougher-bosses boost (10% HP per step and +1 weapon might per step as the player sees it, made with forge
           levels by the game's own forge rule, round 63 docs/rando/BOSS_MIGHT.md; steps 1/2/3)
  Drops:   --enemy-drops 0 (0 = off, else 5-100 in steps of 5)
  Round W2 (docs/rando/WIRE_56.md section 1):
  Shuffle: --recruit off|route|any  --recruit-look keep|full  --recruit-class own|slot  --recruit-stats autolevel|slot
           --recolour on|clear|off   (round 71: the battle hair of a swapped spot, in-game patch only)
  Music:   --music off|maps|maps+battles
  Chests:  --chests off|on   (round 71: chests, villages and talk gifts; the in-game chest hook lays chests.txt)
  Nuzlocke: --nuzlocke off|on  --recruits all|first   (writes nuzlocke.json only; the game keeps the rules from
           engine round E2)"""


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make", help="write a randomized mod folder for one seed")
    p.add_argument("--seed", required=True)
    p.add_argument("--classes", type=onoff, default=True)
    p.add_argument("--growths", type=onoff, default=True)
    p.add_argument("--join-stats", dest="join_stats", type=onoff, default=True)
    p.add_argument("--trees", choices=("own", "any"), default="own")
    p.add_argument("--keep-royals", dest="keep_royals", type=onoff, default=True)
    D = TR.DEFAULT_TOPTS
    p.add_argument("--children", type=onoff, default=D["children"])
    p.add_argument("--growth-mode", choices=TR.CHOICES["growth_mode"], default=D["growth_mode"])
    p.add_argument("--growth-variance", type=int, default=D["growth_variance"])
    p.add_argument("--growth-min", type=int, default=D["growth_min"])
    p.add_argument("--growth-max", type=int, default=D["growth_max"])
    p.add_argument("--adjust-hp", type=onoff, default=D["adjust_hp"])
    p.add_argument("--bases-mode", choices=TR.CHOICES["bases_mode"], default=D["bases_mode"])
    p.add_argument("--base-variance", type=int, default=D["base_variance"])
    p.add_argument("--scale-to-level", type=onoff, default=D["scale_to_level"])
    p.add_argument("--personal-skills", choices=TR.CHOICES["personal_skills"], default=D["personal_skills"])
    p.add_argument("--skill-slots", choices=TR.CHOICES["skill_slots"], default=D["skill_slots"])
    p.add_argument("--starting-items", type=onoff, default=D["starting_items"])
    p.add_argument("--shops", type=onoff, default=D["shops"])
    p.add_argument("--shop-sides", choices=TR.CHOICES["shop_sides"], default=D["shop_sides"])
    p.add_argument("--rewards", type=onoff, default=D["rewards"])
    p.add_argument("--enemy-weapons", type=onoff, default=D["enemy_weapons"])
    p.add_argument("--enemy-classes", type=onoff, default=D["enemy_classes"])
    p.add_argument("--boss-classes", type=onoff, default=D["boss_classes"])
    p.add_argument("--enemy-trees", choices=TR.CHOICES["enemy_trees"], default=D["enemy_trees"])
    # round W1 (WIRE_56 section 1); tracks.check_topts checks the ranges
    for k in ("promotions", "promotion_sides", "reclass", "class_growths", "class_bases", "enemy_growths",
              "boss_stats", "weapon_stats", "upgrade_rank", "class_move"):
        p.add_argument("--" + k.replace("_", "-"), dest=k, choices=TR.CHOICES[k], default=D[k])
    for k in ("class_growth_variance", "class_base_variance", "enemy_buff", "enemy_levels", "boss_max_boost",
              "boss_variance", "weapon_traits", "enemy_upgrade", "enemy_drops"):
        p.add_argument("--" + k.replace("_", "-"), dest=k, type=int, default=D[k])
    for k in ("wild_traits", "assign_evenly"):
        p.add_argument("--" + k.replace("_", "-"), dest=k, type=onoff, default=D[k])
    # round W2: music, Nuzlocke (topts) and the character shuffle (ropts, its own dict)
    for k in ("music", "recruits", "difficulty"):
        p.add_argument("--" + k.replace("_", "-"), dest=k, choices=TR.CHOICES[k], default=D[k])
    p.add_argument("--nuzlocke", type=onoff, default=D["nuzlocke"])
    p.add_argument("--chests", type=onoff, default=D["chests"],
                   help="round 71: chests, villages and talk gifts give a same-band item (chests.txt in the mod folder; "
                        "only the in-game chest hook lays it; docs/rando/CHESTS.md)")
    for k, ch in TR.RECRUIT_CHOICES.items():
        p.add_argument("--" + k.replace("_", "-"), dest=k, choices=ch, default=TR.RECRUIT_DEFAULTS[k])
    p.add_argument("--recolour", choices=("on", "clear", "off"), default="on",
                   help="round 71: the shuffle's battle hair: on = the new person's colour (as before), clear = "
                        "easier to see, off = the spot's own hair (in-game patch only; docs/rando/COLOURS.md)")
    p.add_argument("--out", help=f"folder that receives Rando-<seed>/ (default {os.path.relpath(DEFAULT_OUT, ROOT)})")
    p.add_argument("--zakuro-dir", help="also build and install into this Zakuro data folder (a randomized save's own)")
    p.add_argument("--patch-out", help="also write the in-memory patch for the in-game New Game page (F-044)")
    p.add_argument("--game", choices=("fates", "seal"), default=None,
                   help="whose tables: the original game (default) or Seal of Flames (F-047, docs/rando/SEAL.md); "
                        "not given = the game already active (fates unless a caller activated another)")
    p.add_argument("--seal-romfs", help="the Seal of Flames mod's romfs folder (default: sources.py's own)")
    p.add_argument("--cache", help="keep parsed tables in this folder (tools/randomizer/cache.py; default "
                                   "FEF_RANDO_CACHE, none = no cache)")
    p.add_argument("--progress", action="store_true", help="print 'progress N stage' lines (the in-game page)")
    p.add_argument("--spoiler", type=onoff, default=True,
                   help="round 62b: off = no spoiler.txt is written (nothing else changes; the page's Spoiler log)")
    p = sub.add_parser("check", help="re-make a mod folder from its plan.json and re-run the guards")
    p.add_argument("dir")
    p.add_argument("--game", choices=("fates", "seal"), default=None, help="default: plan.json's game (else fates)")
    p.add_argument("--seal-romfs", help="the Seal of Flames mod's romfs folder (default: sources.py's own)")
    sub.add_parser("schema", help="print the in-game randomizer page's rows as JSON (F-044)")
    a = ap.parse_args(argv)
    if a.cmd == "schema":
        import ingame as IG
        print(json.dumps(IG.schema(), indent=1))
        return 0
    try:
        return cmd_make(a) if a.cmd == "make" else cmd_check(a)
    except R.RandoError as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
