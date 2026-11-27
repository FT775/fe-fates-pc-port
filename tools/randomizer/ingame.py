"""The randomizer inside the game's New Game flow (F-044 addendum; docs/RANDOMIZER_INGAME.md).

Two things for the engine side (Zakuro's `fates_rando`, patch 0007):

  schema()           the page's rows (key, label, kind, default, "Everything on" value), built from the SAME lists
                     PLAY RANDOMIZED uses (tools/play/rando.py SWITCHES / OPTIONS / SUGGESTED / SEED_RX) plus the two
                     make switches PLAY RANDOMIZED does not ask (--trees, --keep-royals), in the order of
                     docs/rando/R62B_PAGE.md (PAGE). Rows the core cannot lay yet are grey ("fixed",
                     at their default, the reason in the label): PAGE_FIXED (options whose files are not GameData or
                     chapter placements, or that wait for a robot check); of those, PAGE_NOFLAG (the character
                     shuffle, music, Nuzlocke: PLAY RANDOMIZED options since round W2) also carry no flag, so the
                     page's command line is the same as before.
  make_patch(files)  the in-memory patch for one made mod: for every file the mods tool rebuilds (GameData.bin.lz and
                     the chapter Dispos files) every cell that differs from the original, with the ORIGINAL value (the
                     engine checks it before it writes anything) and the new one. Plain cells are bytes; pointer cells
                     (a Dispos unit's class or item label, any string a table points to) are given as the old and the
                     new label text plus where that label text lives in the resident GameData (or in the file's own
                     string pool), because a pointer in memory is "where the file was loaded + its offset".

Patch file (text, one line per entry, parsed by zakuro-core/src/fates_rando.rs; no JSON needed in the engine):

    fates-rando-patch 1
    seed <seed>
    options <one JSON line, for people; the engine does not read it>
    gamedata-sha256 <sha256 of the original decompressed GameData.bin>
    file gamedata GameData/GameData.bin.lz
    v <offset hex> <original bytes hex> <new bytes hex>
    p <offset hex> <original label hex or -> <new label hex or -> <g|s|-> <new label offset hex or ->
      <original pointer's file value hex or -> (revert writes data start + that value back)
    file dispos GameData/Dispos/A/A005.bin.lz
    ...
    end <number of v and p lines>

Offsets are from the start of the file's data region (the IS .bin header excluded), the same base the file's own
pointers count from, so memory address = data start in memory + offset. `g` = the label lives in GameData's string
pool (offset from GameData's data start), `s` = in this file's own pool. `-` = a null pointer.
Python 3 standard library plus the repo's table tools (read only).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
sys.path.insert(0, os.path.join(ROOT, "tools", "play"))

FORMAT = 1
GAMEDATA_REL = "GameData/GameData.bin.lz"
DISPOS_PREFIX = "GameData/Dispos/"
PERSON_PREFIX = "GameData/Person/"      # engine round E1: chapter person files and the route-variant rows
MAPCONFIG_PREFIX = "map/config/"        # engine round E1: the map settings files (map themes), stored plain


NUL = bytes(1)


class PatchError(Exception):
    pass


# ------------------------------------------------------------------------------------------------ schema


def play_randomized():
    """tools/play/rando.py (PLAY RANDOMIZED), loaded by path: its name clashes with tools/randomizer/rando.py."""
    if "fef_play_rando" not in sys.modules:
        import importlib.util
        spec = importlib.util.spec_from_file_location("fef_play_rando", os.path.join(ROOT, "tools", "play", "rando.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["fef_play_rando"] = mod
        spec.loader.exec_module(mod)
    return sys.modules["fef_play_rando"]


# The page's row order, sections, labels and help: PAGE below (round 62b). ARG_ORDER is the round-62 page order
# (docs/rando/WIRE_56.md section 3): make_args passes the flags in this order, so the command is the same as before.
ARG_ORDER = ("randomizer", "seed", "recruit", "recruit_look", "recruit_class", "recruit_stats",
             "classes", "trees", "keep_royals", "assign_evenly",
             "growths", "growth_mode", "growth_variance", "growth_min", "growth_max", "adjust_hp",
             "join_stats", "bases_mode", "base_variance", "scale_to_level", "personal_skills", "skill_slots",
             "promotions", "promotion_sides", "reclass", "children",
             "class_growths", "class_growth_variance", "class_bases", "class_base_variance", "class_move",
             "starting_items", "shops", "shop_sides", "rewards", "weapon_stats", "weapon_traits", "wild_traits",
             "enemy_classes", "boss_classes", "enemy_trees", "enemy_weapons", "enemy_upgrade", "upgrade_rank",
             "enemy_growths", "enemy_buff", "enemy_levels", "boss_stats", "boss_max_boost", "boss_variance",
             "enemy_drops", "difficulty", "music", "nuzlocke", "recruits")
# Options PLAY RANDOMIZED has but the page cannot offer yet: key -> the reason shown in the label (grey, default).
# Engine round E1 (round 59): the core lays GameData/Person/** (chapter person files, the route-variant rows) and
# map/config/*.bin (map themes) too, so enemy levels, tougher bosses, the character shuffle ("keep the face") and
# music are live on the page. Still grey: the full identity look and the stronger-weapons rank (its robot check).
# Nuzlocke is live since engine round E2 (round 60; round 61 gate fix, see below).
# The full identity look (round 74 built it; robot test only through A7's switch below): round 75 ran the four
# trouble chapters (docs/rando/FULL_SWAP_PLAN.md section 3, F-060). Rule 5: Revelation 13 (turns 6-32) and
# Conquest 9 (the OP4 scene and turns 11-28) were not reached, so they were not proven and the row stayed fixed.
# Round 76 (F-062, THE PAGE rule of F-060): Revelation 13 (turns 6-32) and Conquest 9 (OP4 and turns 11-28) PASS, with
# Revelation 8 and Conquest 16 PASS from round 75, so the row is OFFERED on the Fire Emblem Fates page with both
# choices ("Keep the face" stays the default and stays out of "Randomize everything"). No chapter is on
# recruit.full_off_chapters (no rule-2 break was found). Seal of Flames keeps the row grey at "Keep the face"
# (GREY_FOR below): round 76's Seal leg found the scene name plates keep the old Seal name above the new face (a FAIL,
# not fixed: the randomizer was frozen that round). LOOK_WAITS is that reason (rando.py's refusal text names it too).
ENGINE_E1 = "PLAY RANDOMIZED only until the next engine round"
LOOK_WAITS = "Full swap waits on Seal of Flames: name plates in scenes keep the old name"
LOOK_OFFERED = True     # round 76: the owner's page offers "Full swap" (Fates; Seal grey through GREY_FOR)
PAGE_FIXED = {
    "upgrade_rank": "replaced by Difficulty",
}
# Round W2: the shuffle, music and Nuzlocke are PLAY RANDOMIZED options now (rando.py takes their flags), but the
# page cannot lay them yet: grey, at their default, and WITHOUT a flag, so the page's command stays exactly as
# before (rando.py's default for each is "off"). Their own page labels say when they come.
# Engine round E2 (round 60): the core keeps Nuzlocke (graveyard beside the save, the fallen kept fallen after any
# reset, Classic locked), so its row is live and carries its flag. "Recruits: first" stays grey at "all", without a
# flag, on Grok's pick (docs/collab/NUZLOCKE_E2_GROK.md): the game cannot tell a story join from a recruit.
RECRUITS_GREY = "one per chapter is off: a story ally cannot be told from a recruit"
PAGE_FIXED.update({"recruits": RECRUITS_GREY})     # round 76: recruit_look left PAGE_FIXED (offered, F-062)
PAGE_NOFLAG = ("recruits",)


# round 62 (F-049) greyed the Children row for Seal of Flames; round 62b (F-049 addendum, owner: "no worries on the
# seal children, just remove the option existing instead of greying it out"): the row does not exist on the Seal page.
# row key -> {game: reason}; the page leaves the row out for that game and answers it at its default, and rando.py make
# --game seal never turns the children on whatever the page sends. The page still reads the old grey_for field.
HIDE_FOR = {"children": {"seal": "no child in Seal of Flames"}}
# round 76 (F-062): the full swap's look row is grey on the Seal page only (its scene name plates FAIL); Fates offers it.
GREY_FOR: dict = {"recruit_look": {"seal": LOOK_WAITS}}

# ------------------------------------------------------------------------------- round 62b: the page cleanup (F-050)
# Grok's page (docs/collab/RANDO_OPTIONS_GROK.md) with the owner's corrections: rows under section headers, a short
# label and ONE plain sentence of help on every visible row; leftover rows off the page with their old keys still
# answered (a hidden row keeps its default or the restored old answer), so every old answer gives the same text,
# the same run id and the same laid game. Page-only rows (page_only) are never in the answer: Spoiler log and the
# two switches that drive a hidden row (drives: the switch shows on when that row is not at its "off" value).
SECTIONS = ("Basics", "Characters", "Classes", "Growths and stats", "Items and shops", "Enemies and bosses", "Extras")
# key -> (section, label, help). The page order is this order; rows not here (hidden ones) go after, never shown.
PAGE = {
    "randomizer": ("Basics", "Randomizer", "On uses the settings below; Off plays the original game."),
    "seed": ("Basics", "Seed", "The same seed and the same settings make the same game; leave it empty for a new one."),
    "difficulty": ("Basics", "Difficulty", "How much stronger enemy weapons and tougher bosses get: Easy is +1 forge, "
                   "Normal the next weapon tier, Hard the next tier +1; bosses gain 10% HP and +1 might per step."),
    "spoiler_log": ("Basics", "Spoiler log", "On keeps a list of what changed next to the run; Off keeps no list "
                    "(the game itself is the same)."),
    "recruit": ("Characters", "Who joins where", "Off: nobody moves; Within this story: people swap join spots in "
                "this story; Any story: from any story (join levels can be odd)."),
    "recruit_look": ("Characters", "How they look", "Full swap: a moved person comes as themselves (name, face, battle "
                     "look), but movies and My Room keep the old person while castle join scenes show the new one."),
    "recruit_class": ("Characters", "Their class", "Their own: a moved person keeps their class; The spot's: they take "
                      "the class of the spot."),
    "recruit_stats": ("Characters", "Their stats", "Fit the spot: levelled to that chapter; The spot's: they take "
                      "that spot's level and stats."),
    "recolour": ("Characters", "Recolour", "A moved person's battle hair: their own colour, a clearer one that is "
                 "easier to see, or Off (the spot's own hair)."),
    "keep_royals": ("Characters", "Royals keep class", "On: Corrin, Azura and the royal a chapter is named for keep "
                    "their class."),
    "personal_skills": ("Characters", "Personal skills", "Keep, swap the personal skills between people, or give "
                        "each a random one they can have."),
    "skill_slots": ("Characters", "Skill slots", "Keep the learned skills, take ones from the new class, or random "
                    "ones."),
    "children": ("Characters", "Children", "On: a child's class, growths and one skill change; the parents stay."),
    "classes": ("Classes", "Classes", "On: people can start in another class they are allowed to be."),
    "trees": ("Classes", "Class trees", "Own side keeps a Hoshidan in Hoshidan classes (and Nohrians in Nohrian "
              "ones); Any side mixes them."),
    "assign_evenly": ("Classes", "Spread classes", "On: fewer people share the same class."),
    "promotions": ("Classes", "Promotion choices", "On: the two Master Seal choices are shuffled within the same "
                   "rank."),
    "promotion_sides": ("Classes", "Promotion side", "Any side: a shuffled promotion can be any side's class; Own "
                        "side: it stays on the person's side."),
    "reclass": ("Classes", "Heart Seal classes", "Keep, or a random class that seal can already offer."),
    "growths": ("Growths and stats", "Growths", "On: growth percents change (each total stays 20-100); Select on "
                "the stat page shows them."),
    "growth_mode": ("Growths and stats", "How growths change", "Shuffle keeps each total; Share a new total moves the "
                    "total and shares it out; Nudge moves each growth; Roll gives new ones."),
    "growth_variance": ("Growths and stats", "How far growths move", "How many percent a growth (or a total) can "
                        "move; every total still ends between 20 and 100."),
    "adjust_hp": ("Growths and stats", "HP grows more", "On: HP gets a larger share of the growths."),
    "join_stats": ("Growths and stats", "Join stats", "On: the stats someone joins with can change."),
    "bases_mode": ("Growths and stats", "How join stats change", "Shuffle keeps the total; Share a new total moves "
                   "it and shares it out; Nudge moves each stat."),
    "base_variance": ("Growths and stats", "How far stats move", "How many points the join stats can move."),
    "scale_to_level": ("Growths and stats", "Fit the chapter", "On: a later join moves more, in step with their "
                       "level."),
    "class_growths": ("Growths and stats", "Class growths", "Move a little: each class growth moves by the step "
                      "below; a growth of 0 stays 0."),
    "class_growth_variance": ("Growths and stats", "Class growth step", "How far a class growth moves, in steps of "
                              "5."),
    "class_bases": ("Growths and stats", "Class bases", "Move a little: each class base stat moves by the step "
                    "below."),
    "class_base_variance": ("Growths and stats", "Class base step", "How many points a class base stat moves."),
    "class_move": ("Growths and stats", "Class movement", "1 or 2 farther: some classes move farther; nobody moves "
                   "less, so enemies can still reach you."),
    "starting_items": ("Items and shops", "Starting items", "On: what someone joins holding can change, to things "
                       "they can use."),
    "shops": ("Items and shops", "Shops", "On: what the shops sell can change."),
    "shop_sides": ("Items and shops", "Shop sides", "Own side sells your side's goods; Both sides mixes them."),
    "rewards": ("Items and shops", "Castle rewards", "On: a castle prize can be another item."),
    "chests": ("Items and shops", "Chest and village items", "On: chests, villages and talk gifts give another item "
               "about as strong; story and key items stay."),
    "weapon_stats": ("Items and shops", "Weapon stats", "On: might, hit, crit, avoid and staff uses move a little; "
                     "prices stay."),
    "weapon_traits": ("Items and shops", "Special powers", "The percent chance a weapon gains one special power; 0 "
                      "is off."),
    "wild_traits": ("Items and shops", "Wild powers", "On: brave, counter blow and heal can be rolled too; these "
                    "are strong."),
    "enemy_classes": ("Enemies and bosses", "Enemy classes", "On: a generic enemy can be another class using the "
                      "same kind of weapon."),
    "boss_classes": ("Enemies and bosses", "Boss classes", "On: every boss, story bosses too, can get another class "
                     "of the same rank; Garon, Anankos and a few story bosses keep theirs (on Seal of Flames, most "
                     "story bosses do)."),
    "enemy_trees": ("Enemies and bosses", "Enemy trees", "Own side keeps enemies in their side's classes; Any side "
                    "mixes them."),
    "enemy_weapons": ("Enemies and bosses", "Enemy weapons", "On: an enemy's weapon is swapped for another of the "
                      "same kind."),
    "stronger_weapons": ("Enemies and bosses", "Stronger enemy weapons", "On: some enemy weapons go one step up; "
                         "how far comes from Difficulty."),
    "enemy_growths": ("Enemies and bosses", "Enemies grow faster", "Flat adds the same to every enemy growth; More "
                      "for fast growers adds more where a class already grows fast."),
    "enemy_buff": ("Enemies and bosses", "Extra enemy growth", "The percent added; used only when the row above is "
                   "on."),
    "enemy_levels": ("Enemies and bosses", "Enemy levels", "How many extra levels enemies get."),
    "tougher_bosses": ("Enemies and bosses", "Tougher bosses", "On: bosses gain HP and might, more with Difficulty "
                       "(10% HP and +1 might per step)."),
    "enemy_drops": ("Enemies and bosses", "Enemy drops", "The percent chance an enemy carries a drop, in steps of "
                    "5."),
    "music": ("Extras", "Music", "Map themes, or maps and battle themes, are shuffled; story scenes and sung songs "
              "stay."),
    "nuzlocke": ("Extras", "Nuzlocke", "On: a fallen unit stays fallen even after a reset; Classic is locked, a lost "
                 "chapter can be restarted; keep your first healer and lock opener alive."),
    "recruits": ("Extras", "Who counts", "All who join count for Nuzlocke."),
}
# choice values shown in plain words (the answer keeps the value itself; "slice1" never shows on the page)
CHOICE_LABELS = {
    "difficulty": {"easy": "Easy", "normal": "Normal", "hard": "Hard"},
    "recruit": {"off": "Off", "route": "Within this story", "any": "Any story"},
    "recruit_look": {"keep": "Keep the face", "full": "Full swap"},
    "recruit_class": {"own": "Their own", "slot": "The spot's"},
    "recruit_stats": {"autolevel": "Fit the spot", "slot": "The spot's"},
    "recolour": {"on": "Their own colour", "clear": "Easier to see", "off": "Off"},
    "personal_skills": {"keep": "Keep", "shuffle": "Swap between people", "random": "Random"},
    "skill_slots": {"keep": "Keep", "class": "From the class", "random": "Random"},
    "trees": {"own": "Own side", "any": "Any side"},
    "enemy_trees": {"own": "Own side", "any": "Any side"},
    "promotion_sides": {"any": "Any side", "own": "Own side"},
    "reclass": {"keep": "Keep", "random": "Random"},
    "growth_mode": {"slice1": "Shuffle (same total)", "redistribute": "Share a new total", "delta": "Nudge each",
                    "full": "Roll new ones"},
    "bases_mode": {"slice1": "Shuffle (same total)", "redistribute": "Share a new total", "delta": "Nudge each"},
    "class_growths": {"off": "Off", "delta": "Move a little"},
    "class_bases": {"off": "Off", "delta": "Move a little"},
    "class_move": {"off": "Off", "small": "1 farther", "wide": "2 farther"},
    "shop_sides": {"own": "Own side", "mixed": "Both sides"},
    "enemy_growths": {"off": "Off", "flat": "Flat", "scaling": "More for fast growers"},
    "music": {"off": "Off", "maps": "Map themes", "maps+battles": "Maps and battles"},
    "recruits": {"all": "All who join", "first": "First per chapter"},
}
# two-choice rows drawn as an Off/On switch (the answer keeps "off"/"on")
SWITCH_CHOICES = ("promotions", "weapon_stats")
# leftover rows: never shown, still answered (the old keys keep old seeds the same)
HIDDEN = ("growth_min", "growth_max", "upgrade_rank", "enemy_upgrade", "boss_stats", "boss_max_boost", "boss_variance")
# page-only switches over a hidden row: on = that row at its round-62 "Everything on" value (the same answers give the
# same game); an old answer that already has a value other than "off" keeps it (the switch shows on)
DRIVES = {"stronger_weapons": {"key": "enemy_upgrade", "off": 0, "on": 25},
          "tougher_bosses": {"key": "boss_stats", "off": "off", "on": "linear"}}
# "Randomize everything" (the page's button, row "all"): the safe rows only. Never Nuzlocke, children, the full
# identity swap or a row hidden for the game; the seed is kept.
NOT_IN_EVERYTHING = ("children", "nuzlocke", "recruit_look", "recruits")
PAGE_REASONS = {"recruits": "First per chapter: a story ally cannot be told from a recruit"}   # round 76: no look reason
# round 71: rows that are left out of the page's answer while they are at their default ("omit_default"), so a row
# added after round 62b never changes an old answer's text, run id or make flags. The page's answer, the run id
# (fates_rando_session::run_id_for) and make_args all skip such a row at its default; the Rust page twin
# (rando_page.rs answers_with_seed) must skip it the same way.
# Recolour (round 71, A6; F-047 recolour scope, docs/rando/COLOURS.md section 8): its own row, on whenever the
# shuffle is on in the keep-the-face look, as before; "clear" = Easier to see (colours.clear_hair, battle hair only);
# "off" = the spot's own hair. Not a PLAY RANDOMIZED option (that page lays mod folders; the recolour is laid by the
# in-game patch only). "Randomize everything" keeps it at its default (Grok, round-71 consult: old seeds never change).
RECOLOUR_ROW = {"key": "recolour", "label": "Recolour", "kind": "choice", "choices": ["on", "clear", "off"],
                "default": "on", "all": "on", "flag": "--recolour", "omit_default": True}
# Chest and village items (round 71, A1; docs/rando/CHESTS.md): the chests track (tools/randomizer/chests.py) plans a
# same-band item for every chest, village and talk gift; the game core's chest hook (patch 0031,
# fates_rando_chests.rs) swaps it in memory when the game hands it over. Off by default and left out of the answer
# while off (omit_default), so every old answer keeps its text, run id and make flags. Not a PLAY RANDOMIZED option
# (a mod folder cannot change a chest: only the in-game hook can). "Randomize everything" keeps it off until the
# robot's chest proof (round 71 P1) has passed and the owner said ok (F-037); turning it on there would change the
# everything-on seed fingerprints.
CHESTS_ROW = {"key": "chests", "label": "Chest and village items", "kind": "onoff", "default": False, "all": False,
              "flag": "--chests", "omit_default": True}

# Round 75b (seed guarantees, docs/SEED_GUARANTEES_PLAN.md section 5; the plan says "round 79"): the hidden one-choice
# row rando_version. Its only choice is the randomizer's version (guarantees.RANDO_VERSION, "2" since round 75b: the
# guarantee repair can change a seed's tables). Fixed and hidden: never drawn, not in "Randomize everything" (a fixed
# row stays at its default there), no command-line flag (make_args skips it, so the make command is the same), but
# ALWAYS answered (no omit_default): every answer text gains "rando_version":"2", so every run id changes and a new
# game never re-uses a run folder made before the guarantees (the core re-uses runs/<run id>/ when its patch.txt is
# there). A restored old answer (last.json, Esc "Next New Game") gets the current value, because a fixed row keeps its
# default (page_restore here, RandoForm::set in the Rust page). A share code carries it at width 0 (one choice), but
# the row changes the code's layout, so a code made before round 75b is refused as "made by another version of the
# randomizer". Old saves are untouched: a save names its own run folder, which is still there. The next version
# that changes seeds sets the only choice to "3" (guarantees.RANDO_VERSION).
VERSION_KEY = "rando_version"
RANDO_VERSION_FALLBACK = 2      # used only while guarantees.py (the code part's module) is not there


def rando_version() -> int:
    """The randomizer's version: guarantees.RANDO_VERSION, read lazily (2 when that module is not there yet)."""
    try:
        import guarantees as G
    except ImportError:
        return RANDO_VERSION_FALLBACK
    return int(getattr(G, "RANDO_VERSION", RANDO_VERSION_FALLBACK))


def version_row() -> dict:
    v = str(rando_version())
    return {"key": VERSION_KEY, "label": "Randomizer version", "kind": "choice", "choices": [v], "default": v,
            "all": v, "fixed": True, "hidden": True}

# Round 74 (A7; docs/rando/FULL_BLOCK.md section 5): the robot's test-only switch for look = full. Round 74's
# owner page kept "How they look" fixed (call 1); since round 76 it offers the row on Fates (grey on Seal), and the
# switch still works as before (on Seal too: it lifts the Seal grey for the robot only). The robot's runner writes
# <job data>/rando/test-switches.json ({"format": 1, "recruit_look": "full"}) and starts the game with
# FEF_RANDO_TEST_DATA=<job data>. Honoured only when the folder it names, resolved, lies inside <repo>/build/ and
# the file is JSON with format 1; anything else = no switch, silently (a broken file is logged to stderr). The
# owner's data folder is under %APPDATA%, so it never qualifies. Without the switch schema() is byte-identical.
TEST_ENV = "FEF_RANDO_TEST_DATA"
TEST_SWITCH_FILE = ("rando", "test-switches.json")
FULL_TEST_LABELS = {"keep": "Keep the face", "full": "Full swap (robot test)"}


def test_switches() -> dict:
    """The robot's test-only switches ({} when there are none or they do not qualify)."""
    d = os.environ.get(TEST_ENV)
    if not d:
        return {}
    real = os.path.normcase(os.path.realpath(d))
    build = os.path.normcase(os.path.realpath(os.path.join(ROOT, "build")))
    if not (real + os.sep).startswith(build + os.sep):
        return {}
    path = os.path.join(real, *TEST_SWITCH_FILE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            sw = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"note: {path} ignored ({e})", file=sys.stderr)
        return {}
    if not isinstance(sw, dict) or sw.get("format") != 1:
        print(f"note: {path} ignored (not format 1)", file=sys.stderr)
        return {}
    return sw


def full_look_allowed(game: str | None = None) -> bool:
    """True when look = full may be laid for this game (schema(), make_args and rando.py --patch-out all ask here):
    since round 76 the owner's page offers it (LOOK_OFFERED), and the robot's test-only switch still turns it on as
    in round 74. Round 77 (F-062 open item): a game on GREY_FOR["recruit_look"] (Seal of Flames) never gets it except
    under the robot's test-only switch, whatever the answer or a direct rando.py --patch-out call asks. None = the
    question as before round 77 (Fire Emblem Fates)."""
    if test_switches().get("recruit_look") == "full":
        return True
    if game is not None and game in GREY_FOR.get("recruit_look", {}):
        return False
    return LOOK_OFFERED


class LookRefused(ValueError):
    """make_args: an answer asks for look = full for a game that cannot have it (look_refusal says why)."""


def look_refusal(game: str | None) -> str | None:
    """None when look = full may be laid for this game; else the one plain sentence every caller refuses it with,
    built on GREY_FOR's reason (the Seal page's grey row shows the same reason)."""
    if full_look_allowed(game):
        return None
    reason = GREY_FOR.get("recruit_look", {}).get(game) or LOOK_WAITS
    return f"{reason}, so this run is refused (pick Keep the face)."


def _active_game() -> str:
    """The game the tables point at (tools/randomizer/sources.py; the in-game core's script activates Seal before it
    calls make_args). "fates" only when the sources module is not there at all (then no Seal table can be active);
    any other fault stops the make (round 77 review: never let a Seal full swap through on a read error)."""
    try:
        import sources as SRC
    except ImportError:
        return "fates"
    return SRC.current()


# Round 74 (A6, track page; docs/rando/FULL_BLOCK.md section 6, docs/ROUND74_PLAN.md calls 2 and 3, Grok's proposal
# docs/collab/ROUND74_PRESETS_GROK.md): the page's two preset buttons in Basics. A press puts every row at its default
# (page-only switches too), then these values through the page's own set rule (fixed and game-hidden rows keep their
# rule), keeps the seed box and writes the help line. Presets are buttons, not rows: never in the answer or the run
# id. Light = Randomizer on, every other row at its default; Wild = Light + enemy classes, enemy weapons, music on the
# maps, people swap join spots within the story. Both: chest and village items off, Recolour at its default ("Their
# own colour"), Nuzlocke off, the face kept ("How they look" at its default, Keep the face).
PRESETS = (
    {"name": "light", "label": "Light",
     "help": "Different classes and growths. Enemies, chests, and the face stay.",
     "values": {"randomizer": True}},
    {"name": "wild", "label": "Wild",
     "help": "Light, plus enemy classes and weapons, music, and who joins. Face stays.",
     "values": {"randomizer": True, "enemy_classes": True, "enemy_weapons": True, "music": "maps",
                "recruit": "route"}},
)


def presets() -> list[dict]:
    """The schema's "presets" list (a fresh copy)."""
    return [dict(p, values=dict(p["values"])) for p in PRESETS]


def schema() -> dict:
    """The page's rows. One list, one place: PLAY RANDOMIZED's own lists (tools/play/rando.py); round 62b adds the
    page's sections, labels, help, hidden rows and page-only switches (docs/rando/R62B_PAGE.md)."""
    PR = play_randomized()
    rows = [{"key": "randomizer", "label": "Randomizer", "kind": "onoff", "default": False, "all": True},
            {"key": "seed", "label": "Seed", "kind": "seed", "default": "", "pattern": PR.SEED_RX.pattern}]
    for k in PR.SWITCHES:
        rows.append({"key": k, "label": PR.SWITCH_LABELS[k], "kind": "onoff", "default": True, "all": True,
                     "flag": "--" + k.replace("_", "-")})
    rows.append({"key": "trees", "label": "Class trees", "kind": "choice", "choices": ["own", "any"],
                 "default": "own", "all": "own", "flag": "--trees"})
    rows.append({"key": "keep_royals", "label": "Royals keep class", "kind": "onoff", "default": True,
                 "all": True, "flag": "--keep-royals"})
    for k, (label, kind, default) in PR.OPTIONS.items():
        row = {"key": k, "label": label.strip(), "default": default,
               "all": PR.SUGGESTED.get(k, default), "flag": "--" + k.replace("_", "-")}
        if kind == "onoff":
            row["kind"] = "onoff"
        elif isinstance(kind[0], int):
            row.update(kind="number", min=kind[0], max=kind[1])
        else:
            row.update(kind="choice", choices=list(kind))
        if k in PAGE_FIXED:
            row.update(fixed=True, all=default)
            if k in PAGE_NOFLAG:
                del row["flag"]
        rows.append(row)
    rows.append(dict(RECOLOUR_ROW, choices=list(RECOLOUR_ROW["choices"])))
    rows.append(dict(CHESTS_ROW))
    rows.append(version_row())          # round 75b: hidden, fixed, always answered (see VERSION_KEY)
    rows.append({"key": "spoiler_log", "label": "Spoiler log", "kind": "onoff", "default": True, "all": True,
                 "page_only": True})
    for k, d in DRIVES.items():
        rows.append({"key": k, "label": k, "kind": "onoff", "default": False, "all": True, "page_only": True,
                     "drives": dict(d)})
    for row in rows:
        k = row["key"]
        if k in PAGE:
            row["section"], row["label"], row["help"] = PAGE[k]
            if k in PAGE_REASONS:
                row["label"] = f"{row['label']} ({PAGE_REASONS[k]})"
        if k in CHOICE_LABELS:
            row["choice_labels"] = dict(CHOICE_LABELS[k])
        if k in SWITCH_CHOICES:
            row["switch"] = True
        if k in HIDDEN:
            row["hidden"] = True
        if k in NOT_IN_EVERYTHING:
            row["all"] = row["default"]
        if k in HIDE_FOR:
            row["hide_for"] = dict(HIDE_FOR[k])
        if k in GREY_FOR:
            row["grey_for"] = dict(GREY_FOR[k])
    for k, d in DRIVES.items():          # a hidden driven row: default = the switch's off, "all" = its on
        driven = next(r for r in rows if r["key"] == d["key"])
        assert driven["all"] == d["on"] and driven["default"] == d["off"] and driven.get("hidden"), (k, driven)
    look = next(r for r in rows if r["key"] == "recruit_look")
    if test_switches().get("recruit_look") == "full":   # round 74 A7: the robot's own data folder only
        look.pop("fixed", None)
        look.update(label=PAGE["recruit_look"][1], choices=["keep", "full"], choice_labels=dict(FULL_TEST_LABELS),
                    default="keep", all="keep")
    # round 77: a game keeps the grey look row exactly when full_look_allowed(game) says no (Seal of Flames outside
    # the robot's test-only switch; round 76: under the switch the robot may still test the full swap on Seal)
    grey = {g: why for g, why in (look.get("grey_for") or {}).items() if not full_look_allowed(g)}
    if grey:
        look["grey_for"] = grey
    else:
        look.pop("grey_for", None)
    rank = {k: i for i, k in enumerate(PAGE)}
    rows = [r for _i, r in sorted(enumerate(rows), key=lambda ir: (rank.get(ir[1]["key"], len(rank)), ir[0]))]
    return {"format": FORMAT, "rows": rows, "presets": presets()}   # round 74: presets (the page ignores unknown keys)


def page_answers(rows: list[dict], values: dict, game: str | None = None) -> dict:
    """The answer the page gives at Start game for these form values (round 62b; the Rust page's
    RandoForm::answers_with_seed, kept the same by tests on both sides): Randomizer off = {"randomizer": False};
    on = every row that is not page-only, a fixed row or a row hidden for the game at its default, every other row
    (hidden ones too) at its value (or default)."""
    if not values.get("randomizer"):
        return {"randomizer": False}
    out = {}
    for r in rows:
        if r.get("page_only"):
            continue
        hid = game is not None and (game in (r.get("hide_for") or {}) or game in (r.get("grey_for") or {}))
        v = r["default"] if r.get("fixed") or hid else values.get(r["key"], r["default"])
        if r.get("omit_default") and v == r["default"]:      # round 71: a late row at its default is not answered
            continue
        out[r["key"]] = v
    return out


def page_restore(rows: list[dict], last: dict, game: str | None = None) -> dict:
    """Form values from a saved answer or last.json laid over the defaults, as the Rust page's restore does: a value
    that does not fit its row (or a fixed / game-hidden row) stays at the default; page-only switches follow."""
    vals = {r["key"]: r["default"] for r in rows if not r.get("drives")}
    for r in rows:
        k = r["key"]
        if k not in last or r.get("drives") or r.get("fixed"):
            continue
        if game is not None and (game in (r.get("hide_for") or {}) or game in (r.get("grey_for") or {})):
            continue
        v = last[k]
        kind = r["kind"]
        ok = (kind == "onoff" and isinstance(v, bool)) or (kind == "seed" and isinstance(v, str)) or \
             (kind == "choice" and v in r["choices"]) or \
             (kind == "number" and isinstance(v, int) and not isinstance(v, bool) and r["min"] <= v <= r["max"])
        if ok:
            vals[k] = v
    return vals


def page_everything(rows: list[dict], values: dict, game: str | None = None) -> tuple[dict, list[str]]:
    """'Randomize everything': every row at its "all" value (fixed and game-hidden rows at their default), Randomizer
    on, the seed kept. Returns (values, labels of the visible rows it changed)."""
    out = dict(values)
    for r in rows:
        if r["key"] == "seed" or r.get("drives"):
            continue
        hid = game is not None and (game in (r.get("hide_for") or {}) or game in (r.get("grey_for") or {}))
        out[r["key"]] = r["default"] if r.get("fixed") or hid else r.get("all", r["default"])
    out["randomizer"] = True
    turned = [r["label"] for r in rows if not r.get("hidden") and r["key"] != "seed"
              and page_value(rows, out, r) != page_value(rows, values, r)
              and not (game is not None and game in (r.get("hide_for") or {}))]
    return out, turned


def page_preset(rows: list[dict], values: dict, name: str, game: str | None = None) -> dict:
    """Round 74: a preset button's press, as the Rust page does it (RandoPage preset press): every row at its
    default, then the preset's values where they fit (fixed and game-hidden rows keep their default), the seed box
    kept as it was."""
    p = next(p for p in PRESETS if p["name"] == name)
    out = page_restore(rows, dict(p["values"]), game)
    out["seed"] = values.get("seed", "")
    return out


def page_value(rows: list[dict], values: dict, row: dict):
    """A row's value on the page: a driving switch shows on when its row is not at its off value."""
    d = row.get("drives")
    if d:
        return values.get(d["key"], d["off"]) != d["off"]
    return values.get(row["key"], row["default"])


def answer_text(answer: dict) -> str:
    """The page's answer as the frontend writes it (serde_json, no preserve_order: keys sorted, compact)."""
    return json.dumps(answer, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def run_id(answer: dict, game: str | None = None) -> str:
    """fates_rando_session::run_id_for: <seed>-<8 hex FNV-1a of the answer text>, Seal with "game" put first."""
    text = answer_text(answer)
    if game and "game" not in answer:
        rest = text[1:]
        text = '{"game": "' + game + '"' + ("" if rest.startswith("}") else ", ") + rest
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{answer['seed']}-{h:08x}"


def make_args(answer: dict, game: str | None = None) -> list[str]:
    """A page answer ({"seed": .., key: value}) -> `rando.py make` flags (defaults are passed too: explicit).
    game: the game the make is for (None = the game the tables point at: the in-game core activates Seal first).
    Round 77: an answer with the shuffle on and look = full for a game that cannot have it (Seal of Flames, outside
    the robot's test-only switch) raises LookRefused with look_refusal's sentence; Fates flags are unchanged."""
    PR = play_randomized()
    rank = {k: i for i, k in enumerate(ARG_ORDER)}
    rows = {r["key"]: r for r in sorted(schema()["rows"], key=lambda r: rank.get(r["key"], len(rank)))}
    look, rec = rows.get("recruit_look"), rows.get("recruit")
    if (look and rec and not look.get("fixed") and answer.get("recruit_look", look["default"]) == "full"
            and answer.get("recruit", rec["default"]) != "off"):
        why = look_refusal(game or _active_game())
        if why:
            raise LookRefused(why)
    out = ["--seed", str(answer["seed"])]
    for k, r in rows.items():
        if "flag" not in r:
            continue
        v = answer.get(k, r["default"])
        if r.get("fixed"):
            v = r["default"]
        if r.get("omit_default") and v == r["default"]:      # round 71: the flags stay as before at the default
            continue
        step = getattr(PR, "STEPS", {}).get(k)
        if step and r["kind"] == "number" and not r.get("fixed"):    # the page has no step: round to the nearest
            v = max(r["min"], min(r["max"], int(round(int(v) / step)) * step))
        if r["kind"] == "onoff":
            v = "on" if v else "off"
        out += [r["flag"], str(v)]
    return out


# ------------------------------------------------------------------------------------------------ the patch


def _T():
    import mods as M
    if M.T is None:
        raise PatchError(f"the table tools are not available: {M.tables_status()}")
    return M.T


def _pool_index(c) -> dict[bytes, int]:
    """label text -> its offset from the data start, for every string that starts in c's string pool."""
    out: dict[bytes, int] = {}
    tab = c.b.strtab
    i = 0
    while i < len(tab):
        e = tab.find(b"\0", i)
        if e < 0:
            break
        out.setdefault(tab[i:e], c.se + i)
        i = e + 1
    return out


def _string(c, ptr: int) -> bytes | None:
    s = c.string_at(ptr)
    if s is None:
        raise PatchError(f"{c.rel}: pointer {ptr:#x} does not point at a string")
    return s


def file_entries(rel: str, new_raw: bytes, gd_pool: dict[bytes, int], person_ptrs: bool = False,
                 orig=None) -> list[tuple]:
    """('v', off, old, new) and ('p', off, old_label|None, new_label|None, where, label_off|None, old_value|None) for one file.

    person_ptrs (round 74, A3; docs/rando/FULL_BLOCK.md section 2): False = the code path of every run before round
    74 (a label change in a chapter person file is a rename in place or refused). True (only for a run whose look is
    "full") = a label change in a GameData/Person/** file becomes a 'p' cell, the place picked as for GameData (g
    first, then s; a label in neither pool keeps the rename in place); the core then lays that file in memory after
    the game stores it. map/config/*.bin keeps refusing 'p' cells either way. orig: the original container (tests
    pass a made-up one; default the user's own file)."""
    T = _T()
    o = orig if orig is not None else T.container(rel)
    n = T.Container(rel, new_raw)
    if len(o.data) != len(n.data):
        raise PatchError(f"{rel}: the rebuilt data region has another size ({len(o.data)} -> {len(n.data)}); "
                         "an in-memory patch can only change cells in place")
    own_pool = _pool_index(o)
    renames: dict[int, list[tuple]] = {}
    in_read_only = rel.startswith(MAPCONFIG_PREFIX) or (rel.startswith(PERSON_PREFIX) and not person_ptrs)
    ptr_slots = o.relset | n.relset
    out: list[tuple] = []
    covered = {s + k for s in ptr_slots for k in range(4)}
    run_start = None
    for i in range(len(o.data) + 1):
        differs = i < len(o.data) and i not in covered and o.data[i] != n.data[i]
        if differs and run_start is None:
            run_start = i
        if not differs and run_start is not None:
            out.append(("v", run_start, bytes(o.data[run_start:i]), bytes(n.data[run_start:i])))
            run_start = None
    for slot in sorted(ptr_slots):
        if slot & 3:
            raise PatchError(f"{rel}: pointer slot {slot:#x} is not 4-aligned")
        if slot in o.relset and slot in n.relset and o.u32(slot) < o.se and n.u32(slot) < n.se:
            if o.u32(slot) == n.u32(slot):      # a pointer into the data region itself: the region does not move
                continue
            raise PatchError(f"{rel}: data pointer at {slot:#x} changes ({o.u32(slot):#x} -> {n.u32(slot):#x})")
        for c in (o, n):
            if slot in c.relset and c.u32(slot) < c.se:
                raise PatchError(f"{rel}: slot {slot:#x} switches between a data pointer and a label")
        old = _string(o, o.u32(slot)) if slot in o.relset else None
        new = _string(n, n.u32(slot)) if slot in n.relset else None
        if slot not in o.relset and o.u32(slot) != 0:
            raise PatchError(f"{rel}: slot {slot:#x} becomes a pointer but held {o.u32(slot):#x}, not null")
        if slot not in n.relset and n.u32(slot) != 0:
            raise PatchError(f"{rel}: slot {slot:#x} stops being a pointer but is not null")
        if old == new:
            continue
        old_off = o.u32(slot) if old is not None else None
        if in_read_only:
            # engine round E1: chapter person files and map settings take no label pointers (they are laid only in
            # the game's read); a label change is the new text written over the old one in this file's pool
            if old is None or new is None or old_off is None or old_off < o.se:
                raise PatchError(f"{rel}: slot {slot:#x} changes {old!r} -> {new!r}; only a label renamed in place "
                                 "can be laid in this file")
            renames.setdefault(old_off, []).append((slot, old, new))
            continue
        if new is None:
            out.append(("p", slot, old, None, "-", None, old_off))
        elif new in gd_pool:
            out.append(("p", slot, old, new, "g", gd_pool[new], old_off))
        elif new in own_pool:
            out.append(("p", slot, old, new, "s", own_pool[new], old_off))
        elif old is not None and old_off is not None and old_off >= o.se:
            renames.setdefault(old_off, []).append((slot, old, new))
        else:
            raise PatchError(f"{rel}: label {new!r} is in neither GameData's nor the file's own string pool")
    out.extend(_renames_in_place(o, renames))
    out.sort(key=lambda e: e[1])
    return out


def _renames_in_place(o, renames: dict[int, list[tuple]]) -> list[tuple]:
    """Engine round E1 (music, docs/collab/E1_MUSIC_GROK.md): a label that is in no pool the game has in memory is
    written over the old label's own bytes in this file's string pool (a plain 'v' cell from the pool start, the
    new text NUL-padded to the old length), the pointer itself unchanged. Only when the new text is no longer than
    the old one and nothing else in the file shows the old text: every pointer to it changes to the same new label
    and no exported name uses those bytes. Anything else is refused: the patch is never half made."""
    out = []
    tab = o.b.strtab
    for ptr, cells in sorted(renames.items()):
        old = cells[0][1]
        news = {c[2] for c in cells}
        if len(news) != 1:
            raise PatchError(f"{o.rel}: label {old!r} would become {sorted(news)!r} at once")
        new = news.pop()
        if len(new) > len(old):
            raise PatchError(f"{o.rel}: label {new!r} is longer than {old!r} and in no pool in memory")
        lo, hi = ptr, ptr + len(old) + 1
        mine = {c[0] for c in cells}
        for r in o.relset:
            if r not in mine and lo <= o.u32(r) < hi:
                raise PatchError(f"{o.rel}: label {old!r} is also shown by the pointer at {r:#x}")
        for _off, _name, no in o.b.labels:
            if lo <= o.se + no < hi:
                raise PatchError(f"{o.rel}: label {old!r} shares its bytes with an exported name")
        po = ptr - o.se
        if tab[po:po + len(old) + 1] != old + NUL:
            raise PatchError(f"{o.rel}: label {old!r} is not where its pointer says")
        out.append(("v", ptr, old + NUL, new + NUL * (len(old) + 1 - len(new))))
    return out


# ------------------------------------------------------------------------------- round 74: FaceData cells (A1, P1)
# docs/rando/FULL_BLOCK.md section 3. One "file face face/FaceData.bin.lz <records>" section: for every swapped spot
# A -> B and each of A's records (FSID_ST_<A>, FSID_BU_<A>), every field that differs from B's record of the same
# kind. Offsets from the file's data start (record i at 4 + i * 0x48). +0x00 (the FSID the game finds the record by)
# and +0x08 (the voice key: the silence list in full.txt handles voices) are never written. Labels come from
# FaceData's own pool only ('s': B's record already points at them).
FACE_REL = "face/FaceData.bin.lz"
FACE_REC = 0x48
FACE_PTRS = (0x04, 0x0C, 0x10, 0x14, 0x18, 0x20, 0x24)     # name plate, package, body, hair, accessory, 2 expressions
FACE_COLOUR = 0x1C
FACE_LAYOUT = (0x28, 0x48)
FACE_KINDS = ("ST", "BU")


def _face_container():
    """The active game's FaceData as the game sees it: the table root, else (Seal of Flames: the table layer has no
    face folder) the mod's own romfs over the base game's, as colours.load_faces reads it."""
    T = _T()
    if os.path.isfile(os.path.join(T.ROMFS, *FACE_REL.split("/"))):
        return T.container(FACE_REL)
    import sources as SRC
    for root in ([SRC.seal_romfs()] if SRC.current() != "fates" else []) + [SRC.BASE_ROMFS]:
        p = os.path.join(root, *FACE_REL.split("/"))
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                return T.Container(FACE_REL, fh.read())
    raise PatchError(f"{FACE_REL} not found")


def face_records(c) -> list[dict]:
    """The FaceData records of container c: index, off, fsid and key (label bytes or None) and, per pointer field,
    (label bytes or None, the pointer's file value or None)."""
    count = c.u32(0)
    if 4 + count * FACE_REC != len(c.data):
        raise PatchError(f"{c.rel}: {count} records of {FACE_REC:#x} bytes do not fill {len(c.data):#x}")

    def ptr(o):
        if o not in c.relset:
            if c.u32(o):
                raise PatchError(f"{c.rel}: {o:#x} holds {c.u32(o):#x} without a relocation")
            return None, None
        return _string(c, c.u32(o)), c.u32(o)

    out = []
    for i in range(count):
        o = 4 + i * FACE_REC
        rec = {"index": i, "off": o, "fsid": ptr(o)[0], "key": ptr(o + 8)[0],
               "ptr": {f: ptr(o + f) for f in FACE_PTRS}}
        out.append(rec)
    return out


def face_pairs(records: list[dict], fids: dict[str, str]) -> list[tuple[int, int]]:
    """[(A's record index, B's record index)] for {FID_<A>: FID_<B>} (B is not A), each of A's kinds matched to B's
    record of the same kind; a kind B lacks is left out (recruit.py's R9 refuses such a seed before this)."""
    by = {r["fsid"]: r["index"] for r in records if r["fsid"]}
    out = []
    for a, b in sorted(fids.items()):
        if a == b or not a or not b:
            continue
        for kind in FACE_KINDS:
            ka = f"FSID_{kind}_{a.split('_', 1)[1]}".encode("cp932")
            kb = f"FSID_{kind}_{b.split('_', 1)[1]}".encode("cp932")
            if ka in by and kb in by:
                out.append((by[ka], by[kb]))
    return out


def face_entries(c, pairs: list[tuple[int, int]]) -> list[tuple]:
    """file_entries-style cells for FaceData container c and record pairs (A's index, B's index): B's values from
    the ORIGINAL file into A's record (a permutation is laid in one pass: A -> B and B -> C never chain)."""
    recs = face_records(c)
    out: list[tuple] = []
    seen: set[int] = set()
    for ia, ib in pairs:
        if ia == ib:
            continue
        if ia in seen:
            raise PatchError(f"{c.rel}: record {ia} is filled twice")
        seen.add(ia)
        a, b = recs[ia], recs[ib]
        for f in FACE_PTRS:
            (old, oval), (new, nval) = a["ptr"][f], b["ptr"][f]
            if old == new:
                continue
            if new is not None and nval < c.se:
                raise PatchError(f"{c.rel}: record {ib} +{f:#x} does not point into the file's own pool")
            out.append(("p", a["off"] + f, old, new, "s" if new is not None else "-", nval, oval))
        o, p = a["off"] + FACE_COLOUR, b["off"] + FACE_COLOUR
        if c.data[o:o + 4] != c.data[p:p + 4]:
            out.append(("v", o, bytes(c.data[o:o + 4]), bytes(c.data[p:p + 4])))
        lo, hi = FACE_LAYOUT
        diff = [k for k in range(lo, hi) if c.data[a["off"] + k] != c.data[b["off"] + k]]
        if diff:
            s, e = a["off"] + diff[0], a["off"] + diff[-1] + 1
            t = b["off"] + diff[0]
            out.append(("v", s, bytes(c.data[s:e]), bytes(c.data[t:t + e - s])))
    out.sort(key=lambda e: e[1])
    return out


def _entry_line(e: tuple) -> str:
    if e[0] == "v":
        return f"v {e[1]:x} {e[2].hex()} {e[3].hex()}"
    hx = (lambda b: "-" if b is None else b.hex())
    ox = (lambda v: "-" if v is None else format(v, "x"))
    return f"p {e[1]:x} {hx(e[2])} {hx(e[3])} {e[4]} {ox(e[5])} {ox(e[6])}"


def make_patch(files: dict[str, bytes], seed: str, options: dict, person_ptrs: bool = False,
               face_fids: dict[str, str] | None = None, face_container=None) -> tuple[str, dict]:
    """files: rel -> rebuilt stored bytes (mods.compute(...).files). Returns (patch text, summary).
    Round 74 (look = full only; every other run passes the defaults and gets today's text): person_ptrs lets the
    chapter person files carry label-pointer cells (file_entries); face_fids {FID_<spot>: FID_<filler>} adds the one
    'file face' section (face_container: a made-up FaceData for tests, default the user's own)."""
    T = _T()
    gd = T.container(GAMEDATA_REL)
    gd_pool = _pool_index(gd)
    lines = [f"fates-rando-patch {FORMAT}", f"seed {seed}",
             "options " + json.dumps(options, sort_keys=True, separators=(",", ":")),
             f"gamedata-sha256 {hashlib.sha256(gd.dec).hexdigest()}"]
    count, summary = 0, {"files": 0, "v": 0, "p": 0}
    for rel in sorted(files):
        if rel == GAMEDATA_REL:
            kind = "gamedata"
        elif rel.startswith(DISPOS_PREFIX):
            kind = "dispos"
        elif rel.startswith(PERSON_PREFIX):
            kind = "person"
        elif rel.startswith(MAPCONFIG_PREFIX):
            kind = "mapconfig"
        else:
            raise PatchError(f"{rel}: this file cannot be changed in memory (only GameData, chapter placements, "
                             "chapter person files and map settings)")
        ents = file_entries(rel, files[rel], gd_pool, person_ptrs=person_ptrs)
        if not ents:
            continue
        lines.append(f"file {kind} {rel}")
        summary["files"] += 1
        for e in ents:
            lines.append(_entry_line(e))
            summary[e[0]] += 1
            count += 1
    if face_fids:
        fc = face_container if face_container is not None else _face_container()
        ents = face_entries(fc, face_pairs(face_records(fc), face_fids))
        if ents:
            lines.append(f"file face {FACE_REL} {fc.u32(0)}")
            summary["files"] += 1
            summary["face"] = len(ents)
            for e in ents:
                lines.append(_entry_line(e))
                summary[e[0]] += 1
                count += 1
    lines.append(f"end {count}")
    return "\n".join(lines) + "\n", summary


def rebuilt_files(mods_dir: str, work_dir: str) -> dict[str, bytes]:
    """The mods tool's rebuilt files for the mods in mods_dir (nothing installed, nothing staged)."""
    import mods as M
    ctx = M.Ctx(mods_dir=mods_dir, stage_dir=os.path.join(work_dir, "stage"),
                zakuro_dir=os.path.join(work_dir, "unused-data"), quiet=True)
    r = M.compute(ctx)
    if r.errors:
        raise PatchError("the mods tool refused the mod: " + "; ".join(r.errors[:5]))
    if r.text_merged:
        raise PatchError("the mod has text changes; those cannot be laid in memory")
    files = dict(r.files)
    for rel, a in sorted(r.assets.items()):
        # engine round E1: the music track's map settings files (whole files rebuilt from the game's own bytes)
        # become cell patches; any other whole-file change cannot be laid by the core
        if not (rel.startswith(MAPCONFIG_PREFIX) and rel.lower().endswith(".bin")):
            raise PatchError(f"the mod replaces {rel} as a whole file; that cannot be laid in memory")
        with open(a[0], "rb") as fh:
            files[rel] = fh.read()
    return files


# ------------------------------------------------------------------------------------------------ reference apply
# The same algorithm fates_rando.rs runs on guest memory, on a Python "memory image" (used by the tests).


def parse_patch(text: str) -> dict:
    lines = text.splitlines()
    if not lines or lines[0] != f"fates-rando-patch {FORMAT}":
        raise PatchError("not a fates-rando-patch file of this format")
    out = {"files": [], "seed": None}
    cur = None
    count = 0
    for ln in lines[1:]:
        w = ln.split(" ")
        if w[0] == "seed":
            out["seed"] = w[1]
        elif w[0] == "file":
            cur = {"kind": w[1], "rel": w[2], "v": [], "p": []}
            out["files"].append(cur)
        elif w[0] == "v":
            cur["v"].append((int(w[1], 16), bytes.fromhex(w[2]), bytes.fromhex(w[3])))
            count += 1
        elif w[0] == "p":
            un = (lambda s: None if s == "-" else bytes.fromhex(s))
            ui = (lambda s: None if s == "-" else int(s, 16))
            cur["p"].append((int(w[1], 16), un(w[2]), un(w[3]), w[4], ui(w[5]), ui(w[6])))
            count += 1
        elif w[0] == "end":
            if int(w[1]) != count:
                raise PatchError("entry count does not match")
            out["count"] = count
    if "count" not in out:
        raise PatchError("no end line")
    return out


def memory_image(c, base: int) -> bytearray:
    """The file as the game holds it from its data start (data, relocation and label lists, string pool):
    every relocated pointer = base + its file value."""
    import struct
    img = bytearray(c.data) + bytes(c.se - len(c.data)) + bytes(c.b.strtab)
    for r in c.b.relocs:
        struct.pack_into("<I", img, r, (base + c.u32(r)) & 0xFFFFFFFF)
    return img


def read_cstr(images: dict[int, bytes], addr: int) -> bytes | None:
    for base, buf in images.items():
        if base <= addr < base + len(buf):
            o = addr - base
            e = buf.find(b"\0", o)
            return None if e < 0 else bytes(buf[o:e])
    return None


def apply_image(f: dict, img: bytearray, base: int, images: dict[int, bytes], gd_base: int,
                revert: bool = False) -> list[str]:
    """Guard every entry, then write all of them (or none). Returns the problems (empty = applied)."""
    import struct
    bad = []
    for off, old, new in f["v"]:
        want = new if revert else old
        if bytes(img[off:off + len(old)]) != want:
            bad.append(f"v {off:#x}")
    for off, old, new, where, loff, ooff in f["p"]:
        cur = struct.unpack_from("<I", img, off)[0]
        want = new if revert else old
        got = None if cur == 0 else read_cstr(images, cur)
        if (want is None and cur != 0) or (want is not None and got != want):
            bad.append(f"p {off:#x}")
    if bad:
        return bad
    for off, old, new in f["v"]:
        img[off:off + len(old)] = old if revert else new
    for off, old, new, where, loff, ooff in f["p"]:
        if revert:   # the original pointer: into the file's own data/pool, at its file value
            val = 0 if old is None else (base + ooff)
        else:
            val = 0 if new is None else (gd_base if where == "g" else base) + loff
        struct.pack_into("<I", img, off, val)
    return []
