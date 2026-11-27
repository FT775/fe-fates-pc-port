#!/usr/bin/env python3
"""Randomizer track "nuzlocke" (F-046, round 55; docs/rando/NUZLOCKE.md): the rules a Nuzlocke run keeps on top of
Fates' own Classic mode, the run's rules file for the game core, and the graveyard / recruit log kept beside the
save. No table cell serves any of these rules, so this track NEVER edits a table, on or off.

    plan_nuzlocke(tables, rng, opts) -> (edits, spoiler_lines)      edits is always []

tables  a randolib.Facts (only Person / Job rows and the rules are read: who is never benched)
rng     the run seed text or a random.Random. Nuzlocke draws NOTHING from it: turning it on never moves another
        track's results, and the same options give the same rules whatever the seed
opts    DEFAULT_OPTS keys:
          nuzlocke  False | True     off = no edits, no lines, no rules file (old seeds stay byte-identical)
          recruits  "all" | "first"  first = only the first person who joins in each chapter may be fielded; the
                                     others join benched (the game's own "never sortie" unit bit) for the run

What Fates already does (Classic): a fallen unit is gone. What a Nuzlocke adds (FE8 port's rules, made to fit):
  1. Classic only. The New Game page refuses Casual and Phoenix with Nuzlocke on (check_mode), and the core keeps
     My Castle's difficulty menu from switching the run to Casual / Phoenix (a switch that happens anyway voids the
     run in the log: Ledger.on_mode_change).
  2. A death is final through any reset: written the moment it happens (Ledger.on_death); whenever a save, a battle
     save or a Zakuro state is loaded, everyone in the graveyard who is alive in it dies again (Ledger.on_load); a
     dead person who joins again (an older save) dies as they join (Ledger.on_join). A death that ends the game
     (Corrin, or a chapter's must-survive unit) is not written down: you go back as usual.
  3. Optional: first recruit per chapter (recruits="first"). A capture (prisoner scouted in My Castle) counts as
     the recruit of the chapter it was captured in. Story-fixed people are never benched (always_allowed).
  4. A readable death and recruit log beside the save (Ledger.text, `nuzlocke.py log FILE`).
Items 1-3 need hooks in the game core (a later engine round, owner OK then); the exact hooks are in
docs/rando/NUZLOCKE.md "What needs the game core". This module is the reference for what the core must decide:
the rules file it reads (make_rules), the graveyard file it writes (Ledger, same JSON), and every decision.

Our own code. The FE8 port (our sister project, port/reforged/reforged_rando_nuzlocke.c) gave the rules' shape;
no code from public Fates tools (none of them has a Nuzlocke).

    python tools/randomizer/nuzlocke.py rules [--recruits all|first] [--out FILE]   the run's rules (needs tables)
    python tools/randomizer/nuzlocke.py log FILE                                    print a graveyard file
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "nuzlocke"
TOOL = "rando-nuzlocke-v1"
LEDGER_VERSION = 1
DEFAULT_OPTS = {"nuzlocke": False, "recruits": "all"}
RECRUIT_MODES = ("all", "first")

# The game's own values the rules use (docs/rando/NUZLOCKE.md "Facts", read in the code):
MODE_PHOENIX, MODE_CASUAL, MODE_CLASSIC = 0, 1, 2      # GameUserData::GetMode 0x005096D0 (and ProcTitle+116)
MODE_NAMES = {MODE_PHOENIX: "Phoenix", MODE_CASUAL: "Casual", MODE_CLASSIC: "Classic"}
FORCE_PLAYER, FORCE_ENEMY, FORCE_OTHER, FORCE_RESERVE, FORCE_DEAD = 0, 1, 2, 3, 4   # Unit::Transfer's force index
UNIT_NEVER_SORTIE = 0x800                                # Unit+0x8 bit set by the script command UnitSetNeverSortie
JOIN_HOWS = ("story", "castle", "capture", "talk", "paralogue", "load", "other")
DEATH_CAUSES = ("battle", "event", "other")


# ------------------------------------------------------------------ options
def check_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS)
    for k in DEFAULT_OPTS:
        if opts and k in opts and opts[k] is not None:
            o[k] = opts[k]
    v = o["nuzlocke"]
    if isinstance(v, str):
        v = v.strip().lower()
        if v not in ("on", "off", "true", "false", "1", "0", "yes", "no"):
            raise R.RandoError("nuzlocke: on|off")
        v = v in ("on", "true", "1", "yes")
    o["nuzlocke"] = bool(v)
    o["recruits"] = str(o["recruits"]).strip().lower()
    if o["recruits"] not in RECRUIT_MODES:
        raise R.RandoError(f"nuzlocke recruits: {'|'.join(RECRUIT_MODES)}")
    return o


def opts_text(o: dict) -> str:
    return f"nuzlocke={'on' if o['nuzlocke'] else 'off'} recruits={o['recruits']}"


def check_mode(mode: int, opts: dict | None) -> str | None:
    """None when this game mode may start with these options, else the reason (for the New Game page, which knows
    the mode the player just picked: ProcTitle+116, Casual 1 / Classic 2 / Phoenix 0)."""
    o = check_opts(opts)
    if not o["nuzlocke"] or int(mode) == MODE_CLASSIC:
        return None
    return (f"Nuzlocke needs Classic: {MODE_NAMES.get(int(mode), str(mode))} brings fallen units back. "
            "Go back and pick Classic, or turn Nuzlocke off.")


# ------------------------------------------------------------------ who is never benched (from the tables)
def always_allowed(facts: R.Facts) -> list[dict]:
    """Player-army people the first-recruit rule never benches, and why: Corrin and the dragonstone/lord rows
    (rules.keep_class_person_flags) and the singer (a class with the sing command, rules.keep_class_job_flags).
    The story needs them on the field; their deaths follow the normal rules (Corrin's ends the game)."""
    r = facts.rules
    out = []
    for p in facts.persons:
        if R.ival(p["index"]) == 0 or p.get("belong") != r["player_army"]:
            continue
        pf = R.flags(p["flags"])
        j = facts.jobs.get(p["job"])
        why = None
        if r["keep_class_person_flags"][0] in pf:
            why = "Corrin (the avatar)"
        elif pf & set(r["keep_class_person_flags"]):
            why = "story-fixed (lord / dragonstone)"
        elif j and set(r["keep_class_job_flags"]) & R.flags(j["flags"]):
            why = "the singer"
        if why:
            out.append({"pid": p["label"], "name": facts.pname(p), "why": why})
    return out


def avatar_pids(facts: R.Facts) -> list[str]:
    r = facts.rules
    return [p["label"] for p in facts.persons
            if p.get("belong") == r["player_army"] and r["keep_class_person_flags"][0] in R.flags(p["flags"])]


def pid_key(label: str) -> str:
    """The key the game core gives a person (engine round E2, fates_nuzlocke.rs `label_key`): the label's bytes as the
    game holds them (cp932), printable ASCII kept and every other byte (and %, ", backslash) as %HH."""
    out = []
    for b in label.encode("cp932"):
        out.append(chr(b) if 0x21 <= b <= 0x7E and b not in (0x25, 0x22, 0x5C) else f"%{b:02X}")
    return "".join(out)


def key_label(key: str) -> str:
    """pid_key undone (for the readable log); a key that is not one comes back as it is."""
    if "%" not in key:
        return key
    try:
        raw, i = bytearray(), 0
        while i < len(key):
            if key[i] == "%":
                raw.append(int(key[i + 1:i + 3], 16))
                i += 3
            else:
                raw.append(ord(key[i]))
                i += 1
        return raw.decode("cp932")
    except (ValueError, UnicodeDecodeError):
        return key


def make_rules(facts: R.Facts, opts: dict | None) -> dict | None:
    """The run's rules file for the game core (rando/<title>/runs/<run>/nuzlocke.json in the in-game layout), or
    None when Nuzlocke is off (then no file is written at all)."""
    o = check_opts(opts)
    if not o["nuzlocke"]:
        return None
    return {
        "version": LEDGER_VERSION, "tool": TOOL, "nuzlocke": True, "recruits": o["recruits"],
        "mode_required": MODE_CLASSIC,
        "record_force": FORCE_DEAD,
        "bench_bit": UNIT_NEVER_SORTIE,
        "always_allowed": [a["pid"] for a in always_allowed(facts)],
        "game_over_not_recorded": avatar_pids(facts),
        # engine round E2: the same people as the core keys them (the labels' cp932 bytes, pid_key)
        "always_allowed_keys": [pid_key(a["pid"]) for a in always_allowed(facts)],
        "game_over_not_recorded_keys": [pid_key(p) for p in avatar_pids(facts)],
        # round 61: [key, display name] of every player-army person, so the core writes a death with a name
        "names": army_names(facts),
    }


def army_names(facts: R.Facts) -> list[list[str]]:
    """[pid_key, name] for every person of the player army (this game's tables, so a shuffled or mod game names
    its own people); the core looks a fallen person's name up here (fates_nuzlocke.rs `name_of`)."""
    r = facts.rules
    out, seen = [], set()
    for p in facts.persons:
        if R.ival(p["index"]) == 0 or p.get("belong") != r["player_army"] or not p.get("label"):
            continue
        k = pid_key(p["label"])
        if k not in seen:
            seen.add(k)
            out.append([k, facts.pname(p)])
    return out


# ------------------------------------------------------------------ the track's plan (spoiler lines only)
def plan_nuzlocke(tables: R.Facts, rng, opts: dict | None = None) -> tuple[list[dict], list[str]]:
    o = check_opts(opts)
    if not o["nuzlocke"]:
        return [], []
    _ = rng  # nothing is drawn: the rules do not depend on the seed
    lines = [f"Nuzlocke ({TOOL}): {opts_text(o)}",
             "  No table is changed. The rules are kept by the game core (docs/rando/NUZLOCKE.md):",
             "  - Classic only: Casual and Phoenix are refused at the New Game page and locked in My Castle.",
             "  - A death is final: written beside the save at once; a reset, an older save or a save state never",
             "    brings the unit back. A death that ends the game (Corrin, a must-survive unit) is not written."]
    if o["recruits"] == "first":
        lines += ["  - First recruit per chapter: only the first person who joins in a chapter may be fielded; the",
                  "    others join benched for the run. A captured prisoner counts as its chapter's recruit."]
        aa = always_allowed(tables)
        lines.append("  Never benched: " + (", ".join(f"{a['name']} ({a['why']})" for a in aa) or "nobody"))
    else:
        lines.append("  - Recruits: everyone who joins may be fielded.")
    return [], lines


# ------------------------------------------------------------------ the graveyard and recruit log (beside the save)
def ledger_path(data_dir: str, game_id: str, title: str = "0004000000179800") -> str:
    """Where the core keeps one Nuzlocke game's graveyard: <data>/rando/<title>/nuzlocke/<game id>.json, next to
    the slot files that name the run (the save itself is never touched)."""
    gid = str(game_id).strip().lower()
    if not gid or any(c not in "0123456789abcdef" for c in gid) or len(gid) > 32:
        raise R.RandoError("nuzlocke game id: 1-32 hex digits")
    return os.path.join(data_dir, "rando", title, "nuzlocke", gid + ".json")


def new_game_id(rng: random.Random | None = None) -> str:
    """A new game's id (16 hex digits). The core makes one when a Nuzlocke game starts, from the OS (never the
    game's own dice); a given Random is for tests."""
    if rng is not None:
        return format(rng.getrandbits(64), "016x")
    return os.urandom(8).hex()


class Ledger:
    """One Nuzlocke game's graveyard and recruit log. JSON, written atomically (temp file + rename) after every
    change, so a crash or a reset right after a death still finds it written. The core keeps the same file."""

    def __init__(self, path: str, data: dict):
        self.path = path
        self.d = data

    # -- files
    @classmethod
    def new_game(cls, path: str, game_id: str, run: str, rules: dict) -> "Ledger":
        if not rules or not rules.get("nuzlocke"):
            raise R.RandoError("Nuzlocke is off: no graveyard")
        led = cls(path, {"version": LEDGER_VERSION, "tool": TOOL, "game_id": str(game_id), "run": str(run),
                         "rules": rules, "started": _now(), "voided": None, "dead": [], "joined": [],
                         "first_recruit": {}, "events": []})
        led._event("new game", f"run {run}, recruits={rules.get('recruits')}")
        led.save()
        return led

    @classmethod
    def load(cls, path: str) -> "Ledger":
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        if d.get("version") != LEDGER_VERSION or d.get("tool") != TOOL:
            raise R.RandoError(f"{path}: not a {TOOL} graveyard (version {d.get('version')})")
        return cls(path, d)

    def save(self) -> None:
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".nuz-", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(self.d, fh, ensure_ascii=False, indent=1, sort_keys=True)
                fh.write("\n")
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    # -- queries
    @property
    def rules(self) -> dict:
        return self.d["rules"]

    def dead_pids(self) -> list[str]:
        return [e["pid"] for e in self.d["dead"]]

    def is_dead(self, pid: str) -> bool:
        return pid in self.dead_pids()

    def benched_pids(self) -> list[str]:
        return [e["pid"] for e in self.d["joined"] if not e["fielded"] and not self.is_dead(e["pid"])]

    def _event(self, what: str, detail: str) -> None:
        self.d["events"].append({"at": _now(), "what": what, "detail": detail})

    # -- decisions (what the core asks; every answer is also written down)
    def on_death(self, pid: str, chapter: str, turn: int = 0, *, ends_game: bool = False, player_unit: bool = True,
                 cause: str = "battle", name: str = "") -> bool:
        """A unit went to the dead force (Unit::Transfer(unit, 4, ..)). Written at once, unless: not a player
        unit (force 0/3 before), the death ends the game (Corrin, a must-survive unit: the attempt is over and is
        replayed), the run is voided, or the person is already in the graveyard. Returns True when written."""
        if not player_unit or ends_game or pid in self.rules.get("game_over_not_recorded", []):
            return False
        if self.d["voided"] or self.is_dead(pid):
            return False
        if cause not in DEATH_CAUSES:
            cause = "other"
        self.d["dead"].append({"pid": pid, "name": name, "chapter": chapter, "turn": int(turn), "cause": cause,
                               "at": _now()})
        self._event("death", f"{name or pid} in {chapter}, turn {turn} ({cause})")
        self.save()
        return True

    def on_join(self, pid: str, chapter: str, how: str = "story", *, forced: bool = False, name: str = "") -> str:
        """A person moved into the player's army (Unit::Transfer to force 0 or 3 from a join path). Returns what the
        core must do: "dead" (in the graveyard: send it to force 4 at once, an older save), "bench" (keep it in
        force 3 with the never-sortie bit) or "field" (nothing). forced = the chapter itself places the person on
        the map (a story deploy): fielded for that chapter, not counted as the chapter's recruit."""
        if self.is_dead(pid):
            self._event("dead again", f"{name or pid} joined again in {chapter} ({how}): in the graveyard")
            self.save()
            return "dead"
        known = next((e for e in self.d["joined"] if e["pid"] == pid), None)
        if known is not None:  # already decided (a load, a second join path): the first decision stands
            return "field" if (known["fielded"] or forced) else "bench"
        if how not in JOIN_HOWS:
            how = "other"
        r = self.rules
        if r.get("recruits") != "first" or pid in r.get("always_allowed", []):
            fielded, why = True, "allowed"
        elif forced:
            fielded, why = True, "placed by the story"
        elif chapter not in self.d["first_recruit"]:
            fielded, why = True, "first recruit of the chapter"
            self.d["first_recruit"][chapter] = pid
        else:
            fielded, why = False, f"benched: {self.d['first_recruit'][chapter]} was {chapter}'s first recruit"
        self.d["joined"].append({"pid": pid, "name": name, "chapter": chapter, "how": how, "fielded": fielded,
                                 "why": why, "at": _now()})
        self._event("join", f"{name or pid} in {chapter} ({how}): {why}")
        self.save()
        return "field" if fielded else "bench"

    def on_load(self, alive_pids: list[str], where: str = "save loaded") -> dict:
        """A save / battle save / Zakuro state was loaded. alive_pids: the people in forces 0 and 3 of the loaded
        game. Returns {"kill": [pids to send to force 4 again], "bench": [pids that must carry the never-sortie
        bit]}. Writes a line only when something is undone."""
        kill = [p for p in alive_pids if self.is_dead(p)]
        bench = [p for p in alive_pids if p in self.benched_pids()]
        if kill:
            self._event("dead again", f"{where}: " + ", ".join(kill))
            self.save()
        return {"kill": kill, "bench": bench}

    def on_mode_change(self, new_mode: int) -> bool:
        """My Castle's difficulty menu set a mode (GameUserData::SetMode). Classic: nothing. Anything else voids the
        run (written; the core is meant to grey those choices so this never happens). Returns True when voided."""
        if int(new_mode) == self.rules.get("mode_required", MODE_CLASSIC) or self.d["voided"]:
            return False
        self.d["voided"] = f"switched to {MODE_NAMES.get(int(new_mode), str(new_mode))}"
        self._event("voided", self.d["voided"])
        self.save()
        return True

    # -- the readable log
    def text(self) -> str:
        d = self.d
        L = [f"Nuzlocke game {d['game_id']} (run {d['run']}), started {d['started']}",
             f"Recruits: {d['rules'].get('recruits')}" + (f"   VOIDED: {d['voided']}" if d["voided"] else ""),
             "", f"Graveyard ({len(d['dead'])}):"]
        L += [f"  {e.get('name') or key_label(e['pid'])}: {e['chapter']}, turn {e['turn']} ({e['cause']})"
              for e in d["dead"]]
        L += ["", f"Joined ({len(d['joined'])}):"]
        L += [f"  {e.get('name') or e['pid']}: {e['chapter']} ({e['how']}) - {e['why']}"
              + ("  [dead]" if self.is_dead(e["pid"]) else "") for e in d["joined"]]
        return "\n".join(L) + "\n"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ command line
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("rules", help="print or write the run's Nuzlocke rules file (needs the game's tables)")
    a.add_argument("--recruits", default="all", choices=RECRUIT_MODES)
    a.add_argument("--out")
    b = sub.add_parser("log", help="print a graveyard file as text")
    b.add_argument("file")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.cmd == "log":
            sys.stdout.write(Ledger.load(args.file).text())
            return 0
        import gamedata as GD
        facts = GD.load_facts()
        rules = make_rules(facts, {"nuzlocke": True, "recruits": args.recruits})
        text = json.dumps(rules, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        else:
            sys.stdout.write(text)
        for line in plan_nuzlocke(facts, None, {"nuzlocke": True, "recruits": args.recruits})[1]:
            print(line, file=sys.stderr)
        return 0
    except R.RandoError as e:
        print(f"nuzlocke: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
