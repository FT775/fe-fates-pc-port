"""Randomized games for PLAY (F-041 #4): each randomized game is its own PROFILE.

    PLAY RANDOMIZED.bat                      (what the owner double-clicks; a small menu)
    python tools/play/rando.py               the same menu
    python tools/play/rando.py new [--seed S] [--classes on|off] [--growths on|off] [--join-stats on|off]
                                   [track OPTIONS below, e.g. --growth-mode full --enemy-classes on]
    python tools/play/rando.py continue [SEED]
    python tools/play/rando.py list
    OPTIONS (new only; defaults first, the defaults change nothing):
            --growth-mode slice1|redistribute|delta|full --growth-variance 30 --growth-min 5 --growth-max 80
            --adjust-hp off|on --bases-mode slice1|redistribute|delta --base-variance 5 --scale-to-level on|off
            --personal-skills keep|shuffle|random --skill-slots keep|class|random
            --starting-items off|on --shops off|on --shop-sides own|mixed --rewards off|on
            --enemy-weapons off|on --enemy-classes off|on --boss-classes off|on --enemy-trees own|any
            round W1: --assign-evenly off|on --promotions off|on --promotion-sides any|own --reclass keep|random
            --children off|on --class-growths off|delta --class-growth-variance 10 --class-bases off|delta
            --class-base-variance 2 --class-move off|small|wide --weapon-stats off|on --weapon-traits 0
            --wild-traits off|on --enemy-upgrade 0 --upgrade-rank same|next --enemy-growths off|flat|scaling
            --enemy-buff 10 --enemy-levels 0 --boss-stats off|linear|ease --boss-max-boost 5 --boss-variance 0
            --enemy-drops 0 (steps of 5)
            round W2: --recruit off|route|any --recruit-look keep|full --recruit-class own|slot
            --recruit-stats autolevel|slot --music off|maps|maps+battles
            --nuzlocke off|on (round 61: the profile keeps a Nuzlocke run of its own; at the New Game page leave
            Randomizer off, Nuzlocke starts by itself and Classic is locked) --recruits all (first: not offered)
    python tools/play/rando.py --check       only PLAY's checks (ROM in roms/, program, .cia files): makes no
                                             profile, writes nothing under play/randomizer, starts nothing
    common: --dry-run (check and print, start nothing), --no-start (make the profile, do not start),
            --anyway (start even when a check says stop, as PLAY.bat --anyway)

Why a profile: Zakuro reads ONE mods folder per data folder. A randomizer mod "for that save only" must
therefore live in a data folder of its own, with its own saves and its own mods. That is a profile:

    play/randomizer/<seed>/
        profile.json      seed, switches, when made, how the mod was made (randomizer or stub)
        randomizer.log    what the randomizer printed
        mod/Rando-<seed>/ the randomizer's own mod folder (spreadsheets, plan.json, spoiler.txt), when its CLI takes --out
        stage/            the mods tool's work folder (the randomizer's --zakuro-dir install)
        data/             the profile's Zakuro data folder (--data and ZAKURO_DATA point here)
            user/         this profile's saves only (the game makes them on the first start)
            mods/<TITLE>/ the randomizer's mod, and nothing else
            cheats/       empty (never filled by this tool)
        backups/          zips of this profile's save before each start (the last 10)

The normal PLAY.bat is not changed and never sees a profile. A profile never reads or writes the normal
save place (%APPDATA%\\zakuro or play\\data), the owner's mods/ workspace, or %LOCALAPPDATA%. Zakuro's own
settings (window size, picture, keys) stay the owner's: Zakuro keeps them in %APPDATA%\\zakuro\\settings.toml
whatever --data says, exactly as for normal play; this tool never writes that file.

Deleting play/randomizer/<seed>/ deletes that randomized game (its saves too). The original game and the
normal save are untouched either way.

The randomizer itself (tools/randomizer, written by another helper) is called through its command line
only. If it is not there yet, the profile gets a STUB mod folder (no changed files: the original game) and
profile.json says "stub": the game then plays unrandomized, and this tool says so every time.
Python 3 standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import play  # noqa: E402  (the PLAY launcher: same checks, same program, same ROM; not changed by this file)

REPO = play.REPO
TITLE_HEX = play.TITLE_HEX
RANDO_DIR = play.PLAY_DIR / "randomizer"
RANDOMIZER_DIR = Path(os.environ.get(play.ENV("RANDOMIZER_DIR")) or (REPO / "tools" / "randomizer"))
SEED_RX = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
SWITCHES = ("classes", "growths", "join_stats")          # slice 1 (F-041 #5); children is an option (round W1)
SWITCH_LABELS = {"classes": "Classes", "growths": "Growths", "join_stats": "Join stats"}
# The randomizer's track options (round 49, F-043; tools/randomizer/tracks.py DEFAULT_TOPTS). key -> (menu label,
# choices / "onoff" / (lo, hi), default). Every default changes nothing; an option is passed on only when it is not
# the default (flag --growth-mode for growth_mode, and so on), and only if the randomizer's --help names the flag.
OPTIONS = {
    # round W2: the character shuffle (docs/rando/RECRUIT.md; tools/randomizer/recruit.py). The randomizer keeps
    # these four in their own dict ("ropts"); the flags are the same kind as every other option's.
    "recruit": ("Who joins where (character shuffle: route = within the route, any = any route)", ("off", "route", "any"), "off"),
    "recruit_look": ("  Shuffled people look like (keep = the spot's person; full = themselves: own name, model, voice;"
                     " portraits and names in dialogue come with later engine rounds)", ("keep", "full"), "keep"),
    "recruit_class": ("  Shuffled people's class (own = their own, slot = the spot's)", ("own", "slot"), "own"),
    "recruit_stats": ("  Shuffled people's level and stats (autolevel = fit the spot's level, slot = the spot's)",
                      ("autolevel", "slot"), "autolevel"),
    # Classes (round W1: assign evenly, docs/rando/MISC.md)
    "assign_evenly": ("Spread classes evenly (fewer repeats)", "onoff", False),
    # Stats
    "growth_mode": ("Growths mode (slice1 = the Growths switch above)", ("slice1", "redistribute", "delta", "full"), "slice1"),
    "growth_variance": ("  Growth variance %", (0, 100), 30),
    "growth_min": ("  Growth min %", (0, 100), 5),
    "growth_max": ("  Growth max %", (0, 125), 80),
    "adjust_hp": ("  Adjust HP growths", "onoff", False),
    "bases_mode": ("Bases mode (slice1 = the Join stats switch above)", ("slice1", "redistribute", "delta"), "slice1"),
    "base_variance": ("  Base variance", (1, 10), 5),
    "scale_to_level": ("  Scale base variance to join level", "onoff", True),
    "personal_skills": ("Personal skills (shuffle = swap the skills between characters)", ("keep", "shuffle", "random"), "keep"),
    "skill_slots": ("Skill slots", ("keep", "class", "random"), "keep"),
    # round W1: promotions (docs/rando/PROMOTIONS.md), children (docs/rando/CHILDREN.md)
    "promotions": ("Random promotions (Master Seal choices)", ("off", "on"), "off"),
    "promotion_sides": ("  Promotions stay on own side (own) or any side", ("any", "own"), "any"),
    "reclass": ("Heart Seal classes", ("keep", "random"), "keep"),
    "children": ("Children (class, growths, one skill; parents stay)", "onoff", False),
    # round W1: stats (docs/rando/STATS.md) and class movement (docs/rando/MISC.md)
    "class_growths": ("Class growth rates (delta = changed a little)", ("off", "delta"), "off"),
    "class_growth_variance": ("  How much (in 5s)", (0, 50), 10),
    "class_bases": ("Class base stats (delta = changed a little)", ("off", "delta"), "off"),
    "class_base_variance": ("  How much", (1, 5), 2),
    "class_move": ("Class movement (small = 1, wide = 2; mostly farther, no enemy gets stuck)", ("off", "small", "wide"), "off"),
    # Items
    "starting_items": ("Starting items", "onoff", False),
    "shops": ("Shops", "onoff", False),
    "shop_sides": ("  Shop sides (own = own side, mixed = both sides)", ("own", "mixed"), "own"),
    "rewards": ("Castle rewards", "onoff", False),
    # round W1: weapons (docs/rando/WEAPONS.md)
    "weapon_stats": ("Weapon stats (might, hit, crit, avoid, staff uses)", ("off", "on"), "off"),
    "weapon_traits": ("Weapon special powers (chance per weapon %)", (0, 100), 0),
    "wild_traits": ("  Wild powers too (brave, double counter, heal)", "onoff", False),
    # Enemies
    "enemy_classes": ("Enemy classes", "onoff", False),
    "boss_classes": ("Boss classes (same rank of class; Garon, Anankos and bosses whose scenes are not proven keep theirs)", "onoff", False),
    "enemy_trees": ("  Enemy class trees (own side / any)", ("own", "any"), "own"),
    "enemy_weapons": ("Enemy weapons (shuffled, same kind)", "onoff", False),
    "enemy_upgrade": ("Stronger enemy weapons (chance %)", (0, 100), 0),
    "upgrade_rank": ("  Stronger weapons may be one rank higher (replaced by Difficulty since round 62)", ("same", "next"), "same"),
    "enemy_growths": ("Enemies grow faster (flat, or scaling = more for high growths)", ("off", "flat", "scaling"), "off"),
    "enemy_buff": ("  Extra growth %", (0, 100), 10),
    "enemy_levels": ("Enemy levels up", (0, 5), 0),
    "boss_stats": ("Tougher bosses (linear = steady, ease = more later in the story)", ("off", "linear", "ease"), "off"),
    "boss_max_boost": ("  Most extra points per stat", (1, 20), 5),
    "boss_variance": ("  Random spread", (0, 5), 0),
    "enemy_drops": ("Enemies drop items (chance per enemy %, steps of 5)", (0, 100), 0),
    # round 62 (F-049): the randomizer's difficulty, for stronger enemy weapons and tougher bosses
    "difficulty": ("Difficulty (stronger enemy weapons and tougher bosses: easy, normal, hard)", ("easy", "normal", "hard"), "normal"),
    # round W2: music (docs/rando/MUSIC.md) and Nuzlocke (docs/rando/NUZLOCKE.md)
    "music": ("Music (map themes; maps+battles = boss and named-unit battle themes too)", ("off", "maps", "maps+battles"), "off"),
    "nuzlocke": ("Nuzlocke: the fallen stay fallen, Classic only", "onoff", False),
    "recruits": ("  Only the first new ally per chapter (with Nuzlocke)", ("all", "first"), "all"),
}
# options this page shows but cannot start yet: key -> why (they stay at their default; a non-default value stops)
NOT_YET = {"recruits": "'only the first new ally per chapter' is not offered: the game cannot tell a story join from a "
                       "recruit (docs/collab/NUZLOCKE_E2_GROK.md)"}
# round 61: the run a profile with Nuzlocke on keeps in its own data folder (fates_rando_session.rs PROFILE_NUZLOCKE):
# a patch of no cells and the rules file; the game core lays it when the New Game page answers "Randomizer off"
PROFILE_NUZLOCKE = "profile-nuzlocke"
EMPTY_PATCH = "fates-rando-patch 1\nseed profile\noptions {}\ngamedata-sha256 -\nend 0\n"


def write_profile_nuzlocke(data_dir: Path) -> Path:
    """The profile's Nuzlocke run: <data>/rando/<title>/runs/profile-nuzlocke/{patch.txt, nuzlocke.json}. The rules come
    from tools/randomizer/nuzlocke.py rules (started hidden); only files under the profile are written."""
    run = data_dir / "rando" / TITLE_HEX / "runs" / PROFILE_NUZLOCKE
    run.mkdir(parents=True, exist_ok=True)
    rules = run / "nuzlocke.json"
    tool = REPO / "tools" / "randomizer" / "nuzlocke.py"
    flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
    r = subprocess.run([sys.executable, str(tool), "rules", "--out", str(rules)], capture_output=True, text=True,
                       creationflags=flags, timeout=300)
    if r.returncode != 0 or not rules.is_file():
        raise Stop("Nuzlocke: the rules file could not be made:\n" + (r.stdout + r.stderr)[-2000:])
    (run / "patch.txt").write_text(EMPTY_PATCH, encoding="ascii", newline="\n")
    return run
# numbers that must be a whole step (0 = off)
STEPS = {"enemy_drops": 5}
# "Everything on" in the menu: the suggested values from each track's write-up (docs/rando/*.md, WIRE_56 section 1)
SUGGESTED = {"growth_mode": "redistribute", "bases_mode": "redistribute", "personal_skills": "shuffle",
             "skill_slots": "class", "starting_items": True, "shops": True, "rewards": True, "enemy_weapons": True,
             "enemy_classes": True, "boss_classes": True,
             "assign_evenly": True, "promotions": "on", "reclass": "random", "children": True,
             "class_growths": "delta", "class_bases": "delta", "class_move": "small", "weapon_stats": "on",
             "weapon_traits": 25, "enemy_upgrade": 25, "enemy_growths": "flat", "boss_stats": "linear",
             "enemy_drops": 10,
             "recruit": "route", "music": "maps+battles"}
KEEP_BACKUPS = 10
Stop = play.Stop


# ---------------------------------------------------------------------------------------
# places and guards


def profile_dir(seed: str) -> Path:
    check_seed(seed)
    return RANDO_DIR / seed


def check_seed(seed: str) -> str:
    if not isinstance(seed, str) or not SEED_RX.fullmatch(seed):
        raise Stop(f"Seed {seed!r}: use 1 to 32 letters, digits, - or _ (it becomes a folder name).")
    return seed


def make_seed() -> str:
    """A fresh seed: 10 characters, easy to read out and send (no 0/O or 1/I/L)."""
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    while True:
        seed = "".join(secrets.choice(alphabet) for _ in range(10))
        if not (RANDO_DIR / seed).exists():
            return seed


def normal_data_dirs(config: dict) -> list[Path]:
    """The owner's normal save places. A profile must never be one of them or inside one."""
    out = [play.portable_data_dir(config)]
    try:
        out.append(play.appdata_data_dir())
    except Stop:
        pass
    return out


def guard_profile(path: Path, config: dict) -> Path:
    """path is a profile folder below play/randomizer/ and not inside a normal save place (fails closed)."""
    path = path.resolve()
    top = RANDO_DIR.resolve()
    if not play.within(path, top) or path == top:
        raise Stop(f"{path}: not a profile folder below {top}")
    for normal in normal_data_dirs(config):
        n = normal.resolve()
        if path == n or play.within(path, n) or play.within(n, path):
            raise Stop(f"{path}: overlaps the normal save place {n}; refusing.")
    return path


def read_profile(folder: Path) -> dict | None:
    try:
        data = json.loads((folder / "profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("seed") == folder.name else None


def list_profiles() -> list[dict]:
    if not RANDO_DIR.is_dir():
        return []
    out = []
    for folder in sorted(RANDO_DIR.iterdir()):
        if folder.is_dir() and SEED_RX.fullmatch(folder.name):
            prof = read_profile(folder)
            if prof is not None:
                prof["_dir"] = folder
                prof["_has_save"] = play.save_exists(folder / "data")
                out.append(prof)
    return out


def default_options() -> dict:
    return {k: v[2] for k, v in OPTIONS.items()}


def option_text(value) -> str:
    return "on" if value is True else "off" if value is False else str(value)


def check_option(key: str, value):
    """value (text or a Python value) -> the option's value; Stop when it is not allowed."""
    _label, kind, default = OPTIONS[key]
    flag = "--" + key.replace("_", "-")
    if key in NOT_YET:
        if kind == "onoff":
            v = value if isinstance(value, bool) else on_off(str(value), flag)
        else:
            v = str(value).strip().lower()
        if v != default:
            raise Stop(f"{flag}: not yet. {NOT_YET[key]}.")
        return v
    if kind == "onoff":
        return value if isinstance(value, bool) else on_off(str(value), flag)
    if isinstance(kind[0], int):
        try:
            n = int(str(value).strip().rstrip("%"))
        except ValueError:
            raise Stop(f"{flag} needs a whole number {kind[0]}-{kind[1]}.") from None
        if not kind[0] <= n <= kind[1]:
            raise Stop(f"{flag}: {n} is outside {kind[0]}-{kind[1]}.")
        if n % STEPS.get(key, 1):
            raise Stop(f"{flag}: {n} is not a step of {STEPS[key]} (0 = off).")
        return n
    v = str(value).strip().lower()
    if v not in kind:
        raise Stop(f"{flag} needs one of: {', '.join(kind)}.")
    return v


def changed_options(options: dict | None) -> dict:
    return {k: v for k, v in (options or {}).items() if k in OPTIONS and v != OPTIONS[k][2]}


def describe(prof: dict) -> str:
    on = [SWITCH_LABELS[k] for k in SWITCHES if prof.get("switches", {}).get(k)]
    on += [f"{k.replace('_', '-')}={option_text(v)}" for k, v in changed_options(prof.get("options")).items()]
    made = prof.get("created", "?")[:16].replace("T", " ")
    how = "STUB (not randomized)" if prof.get("mod", {}).get("stub") else "randomized"
    save = "has a save" if prof.get("_has_save") else "no save yet"
    return f"{prof['seed']:<12} {', '.join(on) or 'nothing on':<32} {how:<22} {save:<12} made {made}"


# ---------------------------------------------------------------------------------------
# the randomizer, through its command line only


def find_randomizer() -> Path | None:
    for name in ("randomizer.py", "rando.py", "cli.py", "__main__.py"):
        p = RANDOMIZER_DIR / name
        if p.is_file():
            return p
    return None


def randomizer_help(cli: Path) -> str:
    try:
        proc = subprocess.run([sys.executable, str(cli), "--help"], capture_output=True, text=True, timeout=60,
                              cwd=str(REPO))
    except (OSError, subprocess.SubprocessError):
        return ""
    return (proc.stdout or "") + (proc.stderr or "")


def randomizer_command(cli: Path, help_text: str, seed: str, switches: dict, data_dir: Path,
                       options: dict | None = None) -> list[str] | None:
    """The command for the randomizer's CLI, from the flags its --help names. None if it has no flag for
    the seed or no flag that puts the mod into a given Zakuro data folder / mods folder (then: stub)."""
    def has(flag: str) -> bool:
        return re.search(r"(?<![\w-])" + re.escape(flag) + r"(?![\w-])", help_text) is not None

    if not has("--seed"):
        return None
    cmd = [sys.executable, str(cli)]
    # a subcommand, if its help shows one (generate / make / build), first
    for sub in ("generate", "make", "build", "new"):
        if re.search(r"\{[^}]*\b" + sub + r"\b[^}]*\}", help_text):
            cmd.append(sub)
            break
    cmd += ["--seed", seed]
    for key in SWITCHES:
        flag = "--" + key.replace("_", "-")
        if has(flag):
            cmd += [flag, "on" if switches[key] else "off"]
        elif has("--no-" + flag[2:]) and not switches[key]:
            cmd.append("--no-" + flag[2:])
    for key, value in changed_options(options).items():
        flag = "--" + key.replace("_", "-")
        if not has(flag):
            raise Stop(f"The randomizer here has no {flag} option (it is older than this page). "
                       "Leave that option at its default, or update tools/randomizer.")
        cmd += [flag, option_text(value)]
    mods = data_dir / "mods" / TITLE_HEX
    if has("--zakuro-dir"):
        cmd += ["--zakuro-dir", str(data_dir)]
        if has("--out"):   # the mod's own folder (spreadsheets, plan, spoiler) stays with the profile
            cmd += ["--out", str(data_dir.parent / "mod")]
    elif has("--data-dir"):
        cmd += ["--data-dir", str(data_dir)]
    elif has("--mods-out"):
        cmd += ["--mods-out", str(mods)]
    elif has("--out"):
        cmd += ["--out", str(mods)]
    else:
        return None
    return cmd


def write_stub(data_dir: Path, why: str) -> dict:
    mods = data_dir / "mods" / TITLE_HEX
    mods.mkdir(parents=True, exist_ok=True)
    (mods / "RANDOMIZER-STUB.txt").write_text(
        "This profile's mod folder is a stub: the randomizer was not available when it was made.\n"
        f"Why: {why}\nNo game file is changed here, so this profile plays the original game.\n", encoding="utf-8")
    return {"stub": True, "why": why}


def run_randomizer(folder: Path, seed: str, switches: dict, dry_run: bool, options: dict | None = None) -> dict:
    data_dir = folder / "data"
    cli = find_randomizer()
    if cli is None:
        why = f"no randomizer command line in {RANDOMIZER_DIR}"
        return {"stub": True, "why": why} if dry_run else write_stub(data_dir, why)
    help_text = randomizer_help(cli)
    cmd = randomizer_command(cli, help_text, seed, switches, data_dir, options)
    if cmd is None:
        why = f"{cli.relative_to(REPO)} --help names no --seed or no output-folder flag this page knows"
        return {"stub": True, "why": why} if dry_run else write_stub(data_dir, why)
    if dry_run:
        print("[dry run] would run: " + subprocess.list2cmdline(cmd))
        return {"stub": False, "command": cmd}
    env = os.environ.copy()
    env.pop("ZAKURO_DATA", None)
    print("Making the randomized mod (seed " + seed + ") ...")
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO), env=env, timeout=1800)
    (folder / "randomizer.log").write_text(
        "$ " + subprocess.list2cmdline(cmd) + "\n" + (proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
    if proc.returncode != 0:
        raise Stop(f"The randomizer stopped (exit {proc.returncode}). Its words are in\n  {folder / 'randomizer.log'}\n"
                   "  Nothing was started. Delete that profile folder and try again, or try another seed.")
    return {"stub": False, "command": [str(c) for c in cmd], "exit": 0}


# ---------------------------------------------------------------------------------------
# start a profile


def profile_command(config: dict, exe: Path, data_dir: Path, extra: list[str]) -> list[str]:
    """PLAY's command with the profile's data folder: never the normal --data (portable or not)."""
    cmd = [str(exe), str(Path(config["rom"])), "--data", str(data_dir)]
    scale = config.get("scale")
    if scale not in (None, "", 0):
        cmd += ["--scale", str(int(scale))]
    args = [str(a) for a in config.get("zakuro_args") or []]
    # a --data in the owner's own zakuro_args would point back at the normal save: drop it
    i = 0
    while i < len(args):
        if args[i] == "--data":
            i += 2
            continue
        cmd.append(args[i])
        i += 1
    return cmd + extra


def profile_env(data_dir: Path, base: dict | None = None) -> dict:
    """The program's environment with the profile's data folder. base: a portable folder's whole environment
    (play.portable_folder_env, round 77, as the Seal edition's installer uses it), else the normal one."""
    src = os.environ if base is None else base
    env = {k: v for k, v in src.items() if k.upper() != "ZAKURO_DATA"}
    env["ZAKURO_DATA"] = str(data_dir)
    return env


def backup_profile(folder: Path, extdata_id: int | None) -> str | None:
    data_dir = folder / "data"
    if not play.save_exists(data_dir):
        return None
    dest = folder / "backups" / f"auto-{play.timestamp()}.zip"
    play.zip_save(data_dir, extdata_id, dest)
    for old in sorted((folder / "backups").glob("auto-*.zip"))[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)
    return f"Backed up this profile's save to {dest.relative_to(play.PLAY_DIR.parent) if play.within(dest, play.PLAY_DIR.parent) else dest}."


def start_profile(folder: Path, opts: dict, extra: list[str]) -> int:
    config, _created = play.load_config()
    folder = guard_profile(folder, config)
    data_dir = folder / "data"
    prof = read_profile(folder)
    if prof is None:
        raise Stop(f"{folder}: no readable profile.json; not a randomized game made by this page.")
    state = play.load_state()
    notes: list[str] = []
    blockers: list[str] = []
    exe, standalone = play.find_program(config)
    rom_info = play.check_rom(config, state, opts.get("rehash", False), notes)
    if rom_info.get("hash_mismatch"):
        blockers.append("The ROM's SHA-256 is not the known clean dump's (PLAY.bat --check says more).")
    play.check_recompiled(config, exe, data_dir, notes, blockers, standalone)
    cia_stops, _ = play.classify_cias(Path(config["rom"]))
    if cia_stops:
        blockers.append("These .cia files lie beside the ROM: " + ", ".join(cia_stops) + " (see PLAY.bat --check).")
    if play.zakuro_running():
        blockers.append(f"Zakuro or {play.STANDALONE_NAME} is already running. Close it first.")
    cmd = profile_command(config, exe, data_dir, extra)
    for n in notes:
        print(n)
    if prof.get("mod", {}).get("stub"):
        print("NOTE: this profile's mod is a STUB (" + prof["mod"].get("why", "") + "):\n"
              "  the game plays the ORIGINAL tables. Make a new randomized game once the randomizer is there.")
    if blockers and not opts.get("anyway"):
        for b in blockers:
            print("\nSTOP: " + b)
        return 1
    if opts.get("dry_run"):
        print(f"[dry run] would run, data folder {data_dir}:")
        print("  cd /d " + subprocess.list2cmdline([str(exe.parent)]))
        print("  set ZAKURO_DATA=" + str(data_dir))
        print("  " + subprocess.list2cmdline(cmd))
        return 0
    try:
        message = backup_profile(folder, rom_info.get("extdata_id"))
    except OSError as error:
        message = f"Warning: the profile backup failed ({error}); starting anyway."
    if message:
        print(message)
    data_dir.mkdir(parents=True, exist_ok=True)
    portable = play.portable_folder_env(config)   # round 77: a portable folder's places, else the normal ones
    play.make_portable_dirs(portable)
    play.launch(cmd, exe.parent, env=profile_env(data_dir, portable))
    prof["last_started"] = _dt.datetime.now().isoformat(timespec="seconds")
    play.write_json(folder / "profile.json", {k: v for k, v in prof.items() if not k.startswith("_")})
    print(f"Started randomized game {prof['seed']} ({'standalone program' if standalone else 'Zakuro'}).")
    print(f"Its saves: {data_dir / 'user'}   (your normal save is not used)")
    print("In the game: start a New Game on an empty file. Esc opens the menu, F11 switches full screen.")
    return 0


# ---------------------------------------------------------------------------------------
# new / continue / list


def new_profile(seed: str | None, switches: dict, opts: dict, extra: list[str], options: dict | None = None) -> int:
    config, _created = play.load_config()
    seed = check_seed(seed) if seed else make_seed()
    folder = profile_dir(seed)
    guard_profile(folder, config)
    if folder.exists():
        raise Stop(f"A randomized game with seed {seed} already exists:\n  {folder}\n"
                   "  Use \"Continue randomized game\" for it, or pick another seed.")
    options = dict(default_options(), **(options or {}))
    if not any(switches.values()) and not changed_options(options):
        print("Note: every switch is off, so the game is the original one with its own save place.")
    print(f"New randomized game: seed {seed}; " +
          ", ".join(f"{SWITCH_LABELS[k]} {'on' if switches[k] else 'off'}" for k in SWITCHES) +
          f"; children {'on' if options.get('children') else 'off'}.")
    if changed_options(options):
        print("  Options: " + ", ".join(f"{k.replace('_', '-')} {option_text(v)}"
                                         for k, v in changed_options(options).items()))
    if opts.get("dry_run"):
        print(f"[dry run] would make {folder}\\data (user, mods\\{TITLE_HEX}, cheats)")
        run_randomizer(folder, seed, switches, dry_run=True, options=options)
        return 0
    tmp = RANDO_DIR / f".{seed}.making"
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        for sub in ("data/user", f"data/mods/{TITLE_HEX}", "data/cheats", "backups"):
            (tmp / sub).mkdir(parents=True, exist_ok=True)
        mod = run_randomizer(tmp, seed, switches, dry_run=False, options=options)
        if options.get("nuzlocke"):   # round 61: the game core keeps the rules (Classic locked, the fallen stay fallen)
            write_profile_nuzlocke(tmp / "data")
            mod["nuzlocke"] = PROFILE_NUZLOCKE
        if "command" in mod:   # the paths it was given were the temporary folder's; record the final ones
            mod["command"] = [c.replace(str(tmp), str(folder)) for c in mod["command"]]
        prof = {"seed": seed, "switches": {k: bool(switches[k]) for k in SWITCHES},
                "children": bool(options.get("children")),
                "options": options,
                "created": _dt.datetime.now().isoformat(timespec="seconds"), "mod": mod,
                "made_by": "tools/play/rando.py", "about": "F-041 #4: a randomized game, its own saves and mods."}
        play.write_json(tmp / "profile.json", prof)
        os.replace(tmp, folder)
        log = folder / "randomizer.log"
        if log.is_file():   # the randomizer was given the temporary folder's name; the log says the final one
            log.write_text(log.read_text(encoding="utf-8").replace(str(tmp), str(folder)), encoding="utf-8")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    print(f"Made {folder}")
    if mod.get("stub"):
        print("NOTE: the randomizer is not there yet, so this profile's mod is a STUB (original tables).")
    if mod.get("nuzlocke"):
        print("Nuzlocke is on: at the New Game page leave Randomizer OFF (this game is already randomized). The game "
              "starts a Nuzlocke game by itself: Classic is locked and a fallen unit stays fallen after a reset.")
    if opts.get("no_start"):
        return 0
    return start_profile(folder, opts, extra)


def continue_profile(seed: str | None, opts: dict, extra: list[str]) -> int:
    profiles = list_profiles()
    if not profiles:
        raise Stop("There is no randomized game yet. Choose \"New randomized game\" first.")
    if seed is None:
        seed = pick(profiles)
        if seed is None:
            return 0
    folder = profile_dir(seed)
    if read_profile(folder) is None:
        raise Stop(f"No randomized game with seed {seed}. Existing: " + ", ".join(p["seed"] for p in profiles))
    return start_profile(folder, opts, extra)


def cmd_list() -> int:
    profiles = list_profiles()
    if not profiles:
        print(f"No randomized games yet (they live in {RANDO_DIR}).")
        return 0
    print(f"Randomized games in {RANDO_DIR}:")
    for prof in profiles:
        print("  " + describe(prof))
    return 0


# ---------------------------------------------------------------------------------------
# the menu


def ask(prompt: str, default: str = "") -> str:
    try:
        value = input(prompt).strip()
    except EOFError:
        value = ""
    return value or default


def ask_on(label: str, default: bool) -> bool:
    while True:
        v = ask(f"  {label} ({'Y/n' if default else 'y/N'}): ").lower()
        if not v:
            return default
        if v in ("y", "yes", "on", "1"):
            return True
        if v in ("n", "no", "off", "0"):
            return False


def pick(profiles: list[dict]) -> str | None:
    print("Randomized games:")
    for i, prof in enumerate(profiles, 1):
        print(f"  {i}. " + describe(prof))
    while True:
        v = ask("Number or seed to continue (Enter = back): ")
        if not v:
            return None
        if v.isdigit() and 1 <= int(v) <= len(profiles):
            return profiles[int(v) - 1]["seed"]
        for prof in profiles:
            if prof["seed"].lower() == v.lower():
                return prof["seed"]
        print("  Not in the list.")


def menu(opts: dict, extra: list[str]) -> int:
    print("Fire Emblem Fates - randomized games (your normal save and mods are not used here)")
    print("  1. New randomized game")
    print("  2. Continue randomized game")
    print("  3. List randomized games")
    print("  Enter: quit")
    choice = ask("Choice: ")
    if choice == "1":
        seed = ask("Seed (Enter = make one): ") or None
        if seed:
            check_seed(seed)
        print("Switches (children are under More options):")
        switches = {k: ask_on(SWITCH_LABELS[k], True) for k in SWITCHES}
        options = ask_options()
        return new_profile(seed, switches, opts, extra, options)
    if choice == "2":
        return continue_profile(None, opts, extra)
    if choice == "3":
        return cmd_list()
    return 0


def ask_options() -> dict:
    """The track options. Enter keeps them all at their defaults (nothing more changes)."""
    print("More options (character shuffle, classes, growth and base modes, skills, promotions, children, class "
          "stats, items and shops, weapons, enemies, music):")
    print("  Enter = none (defaults), a = everything on (suggested values), c = choose each one")
    v = ask("  Choice: ").lower()
    options = default_options()
    if v in ("a", "all"):
        options.update(SUGGESTED)
        return options
    if v not in ("c", "choose"):
        return options
    for key, (label, kind, default) in OPTIONS.items():
        if key in NOT_YET:
            print(f"  {label.strip()}: not yet ({NOT_YET[key].split(';')[0]})")
            continue
        if kind == "onoff":
            options[key] = ask_on(label.strip(), default)
            continue
        shown = f"{kind[0]}-{kind[1]}" if isinstance(kind[0], int) else "/".join(kind)
        while True:
            raw = ask(f"  {label.strip()} [{shown}] (Enter = {option_text(default)}): ", str(default))
            try:
                options[key] = check_option(key, raw)
                break
            except Stop as why:
                print(f"    {why}")
    return options


def on_off(value: str, flag: str) -> bool:
    v = value.lower()
    if v in ("on", "yes", "1", "true"):
        return True
    if v in ("off", "no", "0", "false"):
        return False
    raise Stop(f"{flag} needs on or off.")


def parse_args(argv: list[str]) -> tuple[str | None, dict, list[str]]:
    extra: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    opts: dict = {"dry_run": False, "no_start": False, "anyway": False, "rehash": False, "check": False, "seed": None,
                  "switches": {k: True for k in SWITCHES}, "options": default_options(), "positional": []}
    action = None
    it = iter(argv)
    for arg in it:
        if arg in ("-h", "--help", "/?"):
            print(__doc__)
            sys.exit(0)
        key = arg.lstrip("-").replace("-", "_").lower()
        if arg.startswith("--") and key in ("dry_run", "no_start", "anyway", "rehash", "check"):
            opts[key] = True
        elif arg == "--seed":
            opts["seed"] = next(it, None) or ""
            check_seed(opts["seed"])
        elif arg.startswith("--") and key in SWITCHES:
            value = next(it, None)
            if value is None:
                raise Stop(f"{arg} needs on or off.")
            opts["switches"][key] = on_off(value, arg)
        elif arg.startswith("--") and key in OPTIONS:
            value = next(it, None)
            if value is None:
                raise Stop(f"{arg} needs a value.")
            opts["options"][key] = check_option(key, value)
        elif not arg.startswith("-") and action is None and arg.lower() in ("new", "continue", "list", "menu"):
            action = arg.lower()
        elif not arg.startswith("-"):
            opts["positional"].append(arg)
        else:
            raise Stop(f"Unknown option {arg!r} (rando.py --help lists them).")
    if action != "new" and (opts["seed"] is not None):
        raise Stop("--seed belongs to new (continue takes the seed as a plain word).")
    return action, opts, extra


def check_only(opts: dict) -> int:
    """--check: the ROM (roms/ first, tools/paths.py), the program and the .cia files, as a randomized start would
    check them. Makes no profile and starts nothing."""
    config, _created = play.load_config()
    state = play.load_state()
    notes: list[str] = []
    blockers: list[str] = []
    exe, _standalone = play.find_program(config)
    rom_info = play.check_rom(config, state, opts.get("rehash", False), notes)
    if rom_info.get("hash_mismatch"):
        blockers.append("The ROM's SHA-256 is not the known clean dump's (PLAY.bat --check says more).")
    cia_stops, _ = play.classify_cias(Path(config["rom"]))
    if cia_stops:
        blockers.append("These .cia files lie beside the ROM: " + ", ".join(cia_stops) + " (see PLAY.bat --check).")
    for n in notes:
        print(n)
    print(f"ROM:     {config['rom']}")
    print(f"Program: {exe}")
    print(f"Profiles: {RANDO_DIR}")
    for b in blockers:
        print("STOP: " + b)
    print("Check: " + ("a randomized game would start." if not blockers else "would NOT start (see STOP lines)."))
    return 1 if blockers else 0


def main(argv: list[str]) -> int:
    action, opts, extra = parse_args(argv)
    if opts.get("check"):
        return check_only(opts)
    if action in (None, "menu"):
        return menu(opts, extra)
    if action == "list":
        return cmd_list()
    if action == "new":
        return new_profile(opts["seed"], opts["switches"], opts, extra, opts["options"])
    seed = opts["positional"][0] if opts["positional"] else None
    return continue_profile(check_seed(seed) if seed else None, opts, extra)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Stop as stop:
        print(f"\nSTOP: {stop}")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(1)
