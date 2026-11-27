#!/usr/bin/env python3
"""Randomizer track "recruit": the character shuffle, who joins where (F-046; design docs/RANDOMIZER_RECRUIT.md,
this round's page docs/rando/RECRUIT.md, wiring docs/rando/RECRUIT_WIRE.md).

Way A of the design: every join spot keeps its person id (PID_), so every scene, talk, transfer, exit and support
still finds its spot. Only what the spot's Person row (and its route-variant HANDOVER rows) holds changes: the
spot plays as the filler. Nothing in Scripts/, no map tile, no castle_join record is ever edited.

    plan_recruit(tables, rng, opts) -> (edits, spoiler_lines)
    run_guards(tables, edits, opts) -> {name: {"ok": bool, "detail": [...]}}
    shuffled_facts(facts, edits)    -> randolib.Facts (a copy with the main Person rows and the Dispos cells edited)

tables  a RecruitTables: the slice-1 Facts (main Person rows, Job, Item, DisposUnit), the HANDOVER route-variant
        Person rows, and the recruit rules. load_tables() reads the user's own RomFS; a Seal of Flames (or any other
        story) tables object passes its own rows and rules (F-047): the pools, routes, join chapters and story
        people are worked out from the rows and the rules, not from names written in this file.
rng     the run seed (text) or a random.Random; this track derives its OWN sub-seed (sha256 of tool, seed, "recruit"),
        then one stream per purpose and pool or spot, so no other track's draws move.
opts    {"recruit": "off"|"route"|"any", "recruit_look": "keep"|"full", "recruit_class": "own"|"slot",
         "recruit_stats": "autolevel"|"slot"}; recruit "off" (the default) = NO edits and no lines.

edits   (fixed order, only cells whose value changes)
        {"table": "Person", "file": "GameData/GameData.bin.lz" | "GameData/Person/C_HANDOVER.bin.lz", "index": n,
         "label": "PID_..", "cell": "job", "old": .., "new": .., "spot": "PID_<main>", "filler": "PID_<main>",
         "laid_by": "core" | "person_hook"}
        {"table": "DisposUnit", "file": "GameData/Dispos/C/C009.bin.lz", "index": n, "label": "PID_C_..",
         "column": "jid" | "item_1".."item_5", "old": .., "new": .., "spot": .., "filler": .., "laid_by": "core"}
        full look only (round 74, docs/rando/FULL_BLOCK.md; reachable only through the robot's test-only switch):
        {"table": "Person", "file": "GameData/Person/<chapter>.bin.lz", ..., "cell": "aid"|"mpid_name"|"mpid_help",
         "laid_by": "person_hook", "look": "full", "copy": True}   (the chapter copies of the spot's person)
        {"table": "FaceData", "fid": "FID_<spot>", "show": "FID_<filler>", "spot": .., "filler": .., "laid_by": "engine"}
        {"table": "Message", "mpid": "MPID_<spot>", "show": "MPID_<filler>", "spot": .., "filler": .., "laid_by": "engine"}
        (ingame.make_patch turns the FaceData records into the patch's "file face" cells; full_block() gives the
        run's full.txt: names per text language, voice keys to silence, full_off_chapters)

laid_by: "core" = the in-game randomizer core lays it today (GameData at New Game, GameData/Dispos/**, round 51);
"person_hook" = needs the per-file hook extended to GameData/Person/** (an engine build, plan round 3);
"engine" = needs the face/asset/message hooks (plan rounds 4-6).

Host reads behind the cells (this round, read only, asm/text; docs/rando/RECRUIT.md section 2):
- Unit::Handover (0x003D82F4) is called only from Unit::CreateImpl2 (0x003D4490) when the placed row's
  replace_index (+0x28) is not 0. It replaces the unit's Person pointer (unit+0x9C) with the MAIN row
  (Person::Get(replace_index)), shifts the unit's stored stats by (route row bases - main row bases) so the totals
  do not jump, then merges the set-aside unit of the main person (force 5) by taking the higher level, stats,
  weapon exp and skills. So: the route-variant row decides the join class (the unit is created from it, or from
  the placement's jid), level and stats; the main row decides everything after the join (growths, personal skill,
  name, face, model). The unit's class is never re-read from the main row.
- Map head: UnitIcon::SetIcon(const Job*, const Person*) (0x004F5104) builds unit/Head/%s from Person+0x10 (the
  AID_, skipping "AID_"), the body from the Job's JID_. So P5 needs nothing beyond P3 (aid).
- FaceDataManager::Initialize is called from MainSequence ProcSequence::InitializeB, and AssetTable::Load from
  ContentsManager::LoadGlobal / AssetTable::LoadROM from BattleGlobal::Initialize: loaded once at boot, before
  New Game. Full identity P1/P3 by file therefore needs a resident patch at New Game (engine build).
- Message fetch: Mess::Get(const char*) (0x003D1CEC), about 1,590 call sites; Mess::GetNoReplace (0x003D16CC)
  is the variant without argument replacement. One hook at Mess::Get covers P4.

    python tools/randomizer/recruit.py plan  --seed S [--recruit route] [--recruit-look keep] [--recruit-class own]
                                             [--recruit-stats autolevel] [--json build/<dir>/recruit.json]
    python tools/randomizer/recruit.py check [--seeds 50] [option flags]     (guards over N seeds; host only)

Public Fates randomizers (Ignis, Paragon by thane98, lashoun's upgraded-fefates-randomizer, the 2016 GBAtemp
randomizer) are GPL: their list of known breaks was used as facts only; no code was read into this module.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "recruit"
TOOL = "rando-recruit-v1"
MAIN_FILE = "GameData/GameData.bin.lz"
HANDOVER_FILES = ("GameData/Person/A_HANDOVER.bin.lz", "GameData/Person/B_HANDOVER.bin.lz",
                  "GameData/Person/C_HANDOVER.bin.lz")
CREDIT = ("Known breaks (Conquest 9, Conquest 16, Revelation 8, Revelation 13, ninja maps needing a flier) from the "
          "public Fates randomizers: Ignis and Paragon (thane98), lashoun's upgraded-fefates-randomizer, the 2016 "
          "GBAtemp randomizer. Facts only, no code.")

DEFAULT_OPTS = {"recruit": "off", "recruit_look": "keep", "recruit_class": "own", "recruit_stats": "autolevel"}
CHOICES = {"recruit": ("off", "route", "any"), "recruit_look": ("keep", "full"),
           "recruit_class": ("own", "slot"), "recruit_stats": ("autolevel", "slot")}

# The recruit rules. rules.json is not this track's file: the wiring round copies this block into
# config/randomizer/rules.json under "recruit" (docs/rando/RECRUIT_WIRE.md); until then these defaults are used and
# a "recruit" block in the passed rules overrides them key by key. Labels only, no game values.
DEFAULT_RULES = {
    # story people who never move, besides the avatar (keep_class_person_flags) and every dragon-vein holder
    # (vein_person_flag: the eight royals and Azura). Gunter: his leaves and returns span chapters.
    "recruit_fixed": ["PID_ギュンター"],
    # held in their own spot until their chapter passes the robot (Nyx: Conquest 9 talk; Shura: Conquest 16)
    "recruit_hold": ["PID_ニュクス", "PID_アシュラ"],
    # people who join through the castle (castle/castle_join.bin.lz records 2-5); they form a pool of their own.
    # The servants (records 0-1) also have chapter joins, so they are ordinary spots.
    "recruit_castle": ["PID_イザナ", "PID_フウガ", "PID_ユキムラ", "PID_フローラ"],
    # the flier rule (R6): a flier must have joined on route <letter> before chapter <chapter> (the ninja-village
    # doors of Birthright 10 and Revelation 11, the same map)
    "recruit_flier_before": {"A": "A010", "C": "C011"},
    "flier_job_category": "JCID_飛行",
    # cells that follow the filler (keep the face); full identity adds recruit_full_cells
    "recruit_keep_cells": (["job", "job_low", "reclass.1", "reclass.2"]
                           + [f"base.{s}" for s in R.STATS] + [f"growth.{s}" for s in R.STATS]
                           + [f"limit_mod.{s}" for s in R.STATS] + [f"weapon_exp.{k}" for k in R.KINDS]
                           + [f"skill.{i}" for i in range(1, 6)] + ["skill_mask", "personal_skill.normal",
                                                                    "personal_skill.hard", "personal_skill.lunatic",
                                                                    "flags"]),
    "recruit_full_cells": ["aid", "mpid_name", "mpid_help", "body_type", "voice"],
    # round 74 (A5): chapters where the names-and-voices pass leaves the text alone (FULL_SWAP_PLAN section 3;
    # round 75 fills it, rules.json recruit.full_off_chapters)
    "full_off_chapters": [],
}
# round 74 (A1): the cells of a chapter copy of a swapped person (a GameData/Person/<chapter> row with another PID_
# but the person's FID_) that follow the filler with look = full, each only where the copy shows the spot's own
# value; a "recruit_copy_cells" key in the passed rules overrides it
COPY_CELLS = ("aid", "mpid_name", "mpid_help")
# round 74 (A2, R9 b): the face file every face package needs, because a missing expression shows it
# (docs/rando/FULL_SWAP_PLAN.md 1.1, round 73b check); a label, as the game's code names it; a
# "face_normal_expression" key in the passed rules overrides it
FACE_NORMAL = "通常"
FACE_KINDS = ("ST", "BU")
FULL_FORMAT = 1
# Grok, round-74 consult (docs/collab/ROUND74_NAMES_GROK.md): replace only the plain display name; no extra pairs
NAMES_GAP = ("Dialogue uses each person's main name only; nicknames and older names may still name the person "
             "of the spot.")
CLASS_CELLS = ("job", "job_low", "reclass.1", "reclass.2")
MAX_ATTEMPTS = 60


# ------------------------------------------------------------------ the tables object
class RecruitTables:
    """facts: a randolib.Facts (the main Person rows etc.); handover: the route-variant Person rows, each a dict with
    a "file" key (as the table codec gives them); rules: the facts' rules with DEFAULT_RULES under them."""

    def __init__(self, facts: R.Facts, handover: list[dict], rules: dict | None = None, copies=None, faces=None,
                 packages=None, scenes=None, names=None):
        """Round 74 (look = full only; each a value or a zero-argument function called once when first needed, so
        a keep-the-face run reads none of them): copies = the chapter Person rows (GameData/Person/<chapter>, not
        the HANDOVER files) with "file"; faces = FaceData records (portrait.load_facedata form: fsid, key,
        package, ...); packages = function package name -> set of its member names without ".bch.lz" (None = no
        such package); scenes = {speaker label: {expression: first place}} from the message text; names =
        {text language: {MPID_: display name}}. None = not given (made-up tables): no copies, R9 (a)(b) not
        checked, no names."""
        self._src = {"copies": copies, "faces": faces, "scenes": scenes, "names": names}
        self._packages = packages
        self.facts = facts
        self.handover = [dict(h) for h in handover]
        r = dict(DEFAULT_RULES)
        r.update((facts.rules.get("recruit") or {}))
        r.update(rules or {})
        self.rules = r
        self.by_index = {R.ival(p["index"]): p for p in facts.persons}
        self.variants: dict[str, list[dict]] = {}
        for h in self.handover:
            main = self.by_index.get(R.ival(h["replace_index"]))
            if main is not None and R.ival(h["replace_index"]):
                self.variants.setdefault(main["label"], []).append(h)
        self.variant_of = {h["label"]: m for m, hs in self.variants.items() for h in hs}
        self._cache: dict = {}

    def cached(self, name, fn):
        if name not in self._cache:
            self._cache[name] = fn()
        return self._cache[name]

    def given(self, name: str):
        """A round-74 input (see __init__): the value, the function's result (once), or None."""
        def build():
            v = self._src.get(name)
            return v() if callable(v) else v
        return self.cached(("given", name), build)

    def chapter_copies(self, spot_pid: str) -> list[dict]:
        """The chapter copies of a main person: rows of the chapter Person files (not HANDOVER) with another
        label but the person's FID_."""
        def build():
            fid_of = {p["fid"]: p["label"] for p in self.facts.persons if p.get("fid")}
            out: dict[str, list[dict]] = {}
            for r in self.given("copies") or []:
                main = fid_of.get(r.get("fid") or "")
                if main and r.get("label") != main and not r["file"].endswith("_HANDOVER.bin.lz"):
                    out.setdefault(main, []).append(r)
            for v in out.values():
                v.sort(key=lambda r: (r["file"], R.ival(r["index"])))
            return out
        return self.cached("copies", build).get(spot_pid, [])

    def face(self, fid: str, kind: str) -> dict | None:
        """FaceData record FSID_<kind>_<short> for FID_<short>, or None (also when no FaceData was given)."""
        faces = self.given("faces")
        if faces is None or not fid or "_" not in fid:
            return None
        by = self.cached("faces_by", lambda: {r["fsid"]: r for r in faces})
        return by.get(f"FSID_{kind}_{fid.split('_', 1)[1]}")

    def package_files(self, pkg: str) -> set | None:
        if self._packages is None or not pkg:
            return None
        return self.cached(("pkg", pkg), lambda: self._packages(pkg))

    def spot_placements(self, spot: str) -> list[dict]:
        def build():
            out: dict[str, list[dict]] = {}
            for d in self.facts.dispos:
                sp = self.spot_of(d.get("pid", ""))
                if sp:
                    out.setdefault(sp, []).append(d)
            return out
        return self.cached("placements", build).get(spot, [])

    def replacements(self, kind: int, rank: int, origin: int) -> list[str]:
        return self.cached(("repl", kind, rank, origin), lambda: self.facts.replacement_items(kind, rank, origin))

    def carried(self, beast: bool, kind: int) -> list[str]:
        """Fallback weapons when no shop weapon fits (beaststones are precious, not sold): the weapons of that kind
        the game itself hands to people whose starting class is (or is not) a beast class, lowest rank first."""
        def build():
            f = self.facts
            cat = f.rules["beast_job_category"]
            out: dict[tuple, set] = {}
            for d in f.dispos:
                p = f.by_pid.get(d.get("pid", ""))
                if not p or not f.in_scope(p) or p["job"] not in f.jobs:
                    continue
                b = cat in R.flags(f.jobs[p["job"]]["category"])
                for s in range(1, 6):
                    iid = d.get(f"item_{s}", "")
                    k = f.item_kind(iid)
                    if k is not None:
                        out.setdefault((b, k), set()).add(iid)
            return {key: sorted(v, key=lambda i: (f.item_rank(i), i)) for key, v in out.items()}
        return self.cached("carried", build).get((beast, kind), [])

    def original_dispos(self, file: str, index: int) -> dict:
        return self.cached("dkey", lambda: {(d["file"], R.ival(d["index"])): d for d in self.facts.dispos})[(file, index)]

    def spot_of(self, pid: str) -> str | None:
        """The main PID a placed id stands for (itself, or the main row of a HANDOVER row)."""
        if pid in self.variant_of:
            return self.variant_of[pid]
        return pid if pid in self.facts.by_pid else None


def load_tables(rules: dict | None = None, facts: R.Facts | None = None) -> RecruitTables:
    """The user's own RomFS through the existing table tools (read only). facts: already loaded slice-1 facts
    (rando.py's), else they are loaded here; only the HANDOVER rows are read in addition."""
    import gamedata as G
    sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
    import mods as M
    facts = facts if facts is not None else G.load_facts()
    full = full_loaders()
    if getattr(facts, "handover", None):          # gamedata.load_facts already read them (slice 1's route-join fix)
        return RecruitTables(facts, facts.handover, rules, **full)
    t = M.reg()["Person"]
    cd = M.codec("Person")
    head = cd.columns()
    rows = []
    for rel in HANDOVER_FILES:
        try:
            c = M.T.container(rel)
        except Exception:  # noqa: BLE001  (a story without route variants simply has none)
            continue
        start, count = M.T.locate(t, c)
        labels = M.T.record_labels(t, c, start, count)
        for i in range(count):
            row = dict(zip(head, cd.decode(c, i, start + i * t.size, labels[i])))
            row["file"] = rel
            rows.append(row)
    return RecruitTables(facts, rows, rules, **full)


def full_loaders() -> dict:
    """Round 74: the full look's inputs from the user's own files of the ACTIVE game (sources.activate points
    mods.ROMFS at Seal of Flames' layer), read only and only when a full-look plan first asks (keep-the-face runs
    read none). Nothing read here is written anywhere but the run's own folder (spoiler, full.txt)."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "mods"))
    sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
    import mods as M

    def roots():
        """the active game's file roots, first wins: the table layer, then (Seal of Flames) the mod's own romfs
        over the base game's, as the game sees them (the recolour's colours._romfs_roots does the same)."""
        import sources as SRC
        out = [M.ROMFS]
        if SRC.current() != "fates":
            out += [SRC.seal_romfs(), SRC.BASE_ROMFS]
        return out

    def find(*parts):
        for r in roots():
            p = os.path.join(r, *parts)
            if os.path.isfile(p):
                return p
        return None

    def copies():
        import gamedata as G
        return [r for r in G._load("PersonChapter") if not r["file"].endswith("_HANDOVER.bin.lz")]

    def faces():
        import portrait
        p = find("face", "FaceData.bin.lz")
        return portrait.load_facedata(p) if p else []

    def packages(pkg):
        import arc
        import isbin
        p = find("face", "face", pkg + ".arc")
        if not p:
            return None
        d, _ = isbin.load_maybe_lz(p)
        return {m["name"].decode("cp932", "replace")[:-len(".bch.lz")] for m in arc.parse(d)
                if m["name"].endswith(b".bch.lz")}

    def langs():
        return sorted({os.path.basename(d)[1:] for r in roots() for d in glob.glob(os.path.join(r, "m", "@*"))
                       if os.path.isfile(os.path.join(d, "GameData.bin.lz"))})

    def names():
        import isbin
        import msg
        out = {}
        for lang in langs():
            d, _ = isbin.load_maybe_lz(find("m", f"@{lang}", "GameData.bin.lz"))
            _n, ents, _b = msg.parse(d)
            out[lang] = {lab.decode("cp932", "replace"): txt for lab, txt, alias in ents if not alias}
        return out

    def scenes():
        import isbin
        ls = langs()
        if not ls:
            return {}
        lang = "E" if "E" in ls else ls[0]
        rels: dict[str, str] = {}
        for r in roots():
            top = os.path.join(r, "m", f"@{lang}")
            for p in glob.glob(os.path.join(top, "**", "*.bin.lz"), recursive=True):
                rels.setdefault(os.path.relpath(p, top).replace(os.sep, "/")[:-len(".bin.lz")], p)
        return scene_faces((rel, isbin.load_maybe_lz(rels[rel])[0]) for rel in sorted(rels))

    return {"copies": copies, "faces": faces, "packages": packages, "scenes": scenes, "names": names}


def scene_faces(archives) -> dict[str, dict[str, str]]:
    """{speaker label: {expression: first place}} from (archive name, archive bytes) pairs: in a talk text, `$Ws<x>|`
    sets the speaker and `$E<expression>,..|` asks the speaker's face for that expression (docs/rando/
    FULL_SWAP_PLAN.md 1.1). Places are "<archive> <message label>", first in archive order."""
    import re
    sys.path.insert(0, os.path.join(ROOT, "tools", "assets"))
    import msg
    rx = re.compile(r"\$(Ws|E)([^|$]*)\|")
    out: dict[str, dict[str, str]] = {}
    for name, data in archives:
        try:
            _n, ents, _b = msg.parse(data)
        except Exception:  # noqa: BLE001  (not a message archive)
            continue
        for lab, txt, alias in ents:
            if alias or "$E" not in txt:
                continue
            who = None
            for m in rx.finditer(txt):
                if m.group(1) == "Ws":
                    who = m.group(2)
                elif who:
                    ex = m.group(2).split(",")[0]
                    if ex:
                        out.setdefault(who, {}).setdefault(ex, f"{name} {lab.decode('cp932', 'replace')}")
    return out


# ------------------------------------------------------------------ options and the sub-seed
def check_opts(opts: dict | None) -> dict:
    o = dict(DEFAULT_OPTS)
    o.update({k: v for k, v in (opts or {}).items() if k in DEFAULT_OPTS and v is not None})
    for k, ch in CHOICES.items():
        o[k] = str(o[k]).strip().lower()
        if o[k] == "keep_face":
            o[k] = "keep"
        if o[k] not in ch:
            raise R.RandoError(f"{k.replace('_', '-')}: one of {', '.join(ch)}")
    return o


def opts_text(o: dict) -> str:
    return " ".join(f"{k.replace('_', '-')}={v}" for k, v in o.items())


def sub_seed(rng) -> str:
    if isinstance(rng, random.Random):
        base = "random:" + format(rng.getrandbits(256), "064x")
    else:
        base = "seed:" + R.check_seed(str(rng))
    return hashlib.sha256("\x1f".join([TOOL, base, TRACK]).encode("utf-8")).hexdigest()


def stream(key: str, *parts: str) -> random.Random:
    h = hashlib.sha256("\x1f".join([TOOL, key, *parts]).encode("utf-8")).digest()
    return random.Random(int.from_bytes(h, "big"))


# ------------------------------------------------------------------ routes, spots and pools (from the rows)
def chapter_num(ch: str) -> int:
    return int(ch[1:4]) if len(ch) >= 4 and ch[1:4].isdigit() else -1


def route_chapter(t: RecruitTables, ch: str) -> str | None:
    """The route letter of a route chapter file (A/B/C + three digits, not a shared opening chapter), else None."""
    r = t.facts.rules
    if ch[:1] in r["routes"] and ch[1:4].isdigit() and ch[:4] not in set(r["shared_chapters"]):
        return ch[0]
    return None


def spot_joins(t: RecruitTables) -> dict[str, dict[str, int]]:
    """{main PID: {route letter: first chapter number}} from every placement of the main id or its route rows in a
    route chapter (any team: talk and mid-map recruits start on team 1 or 2)."""
    return t.cached("joins", lambda: _spot_joins(t))


def _spot_joins(t: RecruitTables) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for d in t.facts.dispos:
        spot = t.spot_of(d.get("pid", ""))
        if not spot:
            continue
        ch = t.facts.chapter_of(d)
        letter = route_chapter(t, ch)
        if not letter:
            continue
        cur = out.setdefault(spot, {})
        n = chapter_num(ch)
        if letter not in cur or n < cur[letter]:
            cur[letter] = n
    return out


def fixed_reason(t: RecruitTables, p: dict) -> str | None:
    """Why a person never moves (and is no filler), or None for a pool member."""
    f, r = t.facts, t.rules
    pf = R.flags(p["flags"])
    if f.is_child(p):
        return "child (children stay out)"
    if not f.in_scope(p):
        return "out of scope (download, bond, capture-only, enemy-only)"
    if pf & set(f.rules["keep_class_person_flags"]):
        return "lord (the avatar)"
    if f.rules["vein_person_flag"] in pf:
        return "royal / story person (dragon vein)"
    if p["label"] in r["recruit_fixed"]:
        return "story person (fixed)"
    if p["label"] in r["recruit_hold"]:
        return "held until their chapter passes the robot"
    if p["job"] not in f.jobs or f.excluded_job(p["job"]):
        return "special class (out of the pool)"
    return None


def pools(t: RecruitTables, mode: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    return t.cached(("pools", mode), lambda: _pools(t, mode))


def _pools(t: RecruitTables, mode: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    """({pool key: [main PIDs in index order]}, {PID: why fixed}) for mode "route" or "any". A pool is one route
    group (the set of routes the spot exists on) and one sex; "any" merges every chapter-join group per sex; the
    castle joins are always a pool of their own."""
    f = t.facts
    joins = spot_joins(t)
    castle = set(t.rules["recruit_castle"])
    out: dict[str, list[str]] = {}
    fixed: dict[str, str] = {}
    for p in sorted(f.persons, key=lambda p: R.ival(p["index"])):
        pid = p["label"]
        why = fixed_reason(t, p)
        if why:
            if f.in_scope(p) or f.is_child(p):
                fixed[pid] = why
            continue
        sex = "F" if f.female(p) else "M"
        if pid in castle:
            group = "castle"
        elif joins.get(pid):
            group = "any" if mode == "any" else "".join(sorted(joins[pid]))
        else:
            fixed[pid] = "no join on any route (out of the pool)"
            continue
        out.setdefault(f"{group}/{sex}", []).append(pid)
    return out, fixed


def permute(members: list[str], r: random.Random) -> dict[str, str]:
    """{spot: filler}, a permutation of members (a pool of one stays put)."""
    fill = list(members)
    r.shuffle(fill)
    return dict(zip(members, fill))


# ------------------------------------------------------------------ what a filler brings into a spot
def tier_class(t: RecruitTables, filler: dict, spot_promoted: bool) -> tuple[str, str, str | None]:
    """(job, job_low, note): the filler's own class line at the spot's tier. job_low is the paired class of the
    line (the promotion for a base class, the base for a promoted one), so a tier change swaps the two."""
    f = t.facts
    job, low = filler["job"], filler["job_low"]
    if f.promoted(f.jobs[job]) == spot_promoted:
        return job, low, None
    if low in f.jobs and not f.excluded_job(low) and f.promoted(f.jobs[low]) == spot_promoted:
        return low, job, None
    return job, low, "no class of the right tier in the filler's line; own class kept"


def eff_level(t: RecruitTables, level, jid: str) -> int:
    return R.ival(level) + (20 if t.facts.promoted(t.facts.jobs[jid]) else 0)


def autolevel(t: RecruitTables, filler: dict, job: str, target_eff: int) -> list[int]:
    """The filler's personal bases moved from its own level to target_eff (levels counted +20 when promoted) with
    the filler's personal growth plus the new class's growth (expected value, rounded), within the new class's
    floors and caps. Same class and same level gives the filler's own bases back."""
    f = t.facts
    nj = f.jobs[job]
    d = target_eff - eff_level(t, filler["level"], filler["job"])
    out = []
    for s in R.STATS:
        v = R.ival(filler[f"base.{s}"]) + round((R.ival(filler[f"growth.{s}"]) + R.ival(nj[f"growth.{s}"])) * d / 100)
        out.append(v)
    return clamp_bases(t, out, job, filler)


def clamp_bases(t: RecruitTables, bases: list[int], job: str, limits_from: dict) -> list[int]:
    nj = t.facts.jobs[job]
    out = []
    for s, v in zip(R.STATS, bases):
        cb = R.ival(nj[f"base.{s}"])
        cap = R.ival(nj[f"max.{s}"]) + R.ival(limits_from[f"limit_mod.{s}"]) - cb
        floor = (1 if s == "hp" else 0) - cb
        out.append(max(floor, min(cap, v)))
    return out


def set_beast(t: RecruitTables, spot_flags: str, beast: bool) -> str:
    flag = t.facts.rules["beast_person_flag"]
    parts = [x for x in str(spot_flags).split("|") if x and x != flag]
    if beast:
        parts.append(flag)
    return "|".join(parts)


def new_row(t: RecruitTables, row: dict, spot: dict, filler: dict, o: dict) -> dict[str, str]:
    """The values the spot's row (main or route-variant) takes for this filler: {cell: new}."""
    f = t.facts
    spot_prom = f.promoted(f.jobs[spot["job"]])
    vals: dict[str, str] = {}
    if o["recruit_class"] == "own":
        job, low, _ = tier_class(t, filler, spot_prom)
        vals.update({"job": job, "job_low": low, "reclass.1": filler["reclass.1"], "reclass.2": filler["reclass.2"]})
        wsrc = filler
    else:
        job = row["job"]
        vals.update({c: row[c] for c in CLASS_CELLS})
        wsrc = row
    mx = f.wexp_max(f.jobs[job])
    for n, k in enumerate(R.KINDS):
        vals[f"weapon_exp.{k}"] = str(min(R.ival(wsrc[f"weapon_exp.{k}"]), mx[n]) if mx[n] > 0 else 0)
    target = eff_level(t, row["level"], row["job"])
    if o["recruit_stats"] == "autolevel":
        bases = autolevel(t, filler, job, target)
    else:
        bases = clamp_bases(t, [R.ival(row[f"base.{s}"]) for s in R.STATS], job, filler)
    for s, v in zip(R.STATS, bases):
        vals[f"base.{s}"] = str(v)
    for s in R.STATS:
        vals[f"growth.{s}"] = filler[f"growth.{s}"]
        vals[f"limit_mod.{s}"] = filler[f"limit_mod.{s}"]
    for c in [f"skill.{i}" for i in range(1, 6)] + ["skill_mask", "personal_skill.normal", "personal_skill.hard",
                                                     "personal_skill.lunatic"]:
        vals[c] = filler[c]
    if o["recruit_class"] == "own":
        vals["flags"] = set_beast(t, row["flags"], f.rules["beast_person_flag"] in R.flags(filler["flags"]))
    else:
        vals["flags"] = row["flags"]
    if o["recruit_look"] == "full":
        for c in t.rules["recruit_full_cells"]:
            if c in filler:
                vals[c] = filler[c]
    return vals


# ------------------------------------------------------------------ carried weapons
def fix_items(t: RecruitTables, d: dict, spot: dict, person_vals: dict, key: str) -> dict[str, str]:
    """{column: new item} for the carried weapons of placement d that the new class cannot use: an ordinary
    weapon of a kind the new class uses, at the old rank or the highest the new weapon exp allows."""
    f = t.facts
    job = person_vals["job"]
    nj = f.jobs[job]
    mx = f.wexp_max(nj)
    wexp = [R.ival(person_vals[f"weapon_exp.{k}"]) for k in R.KINDS]
    probe = dict(spot, flags=person_vals["flags"])
    staff = f.rules["staff_kind"]
    out = {}
    for s in range(1, 6):
        iid = d.get(f"item_{s}", "")
        k = f.item_kind(iid)
        if k is None:
            continue
        need = f.base_usable(spot, iid)
        if not f.class_can_hold(job, probe, iid, wexp, need):
            continue
        if k == staff and mx[staff] > 0:
            kinds = [staff]
        else:
            att = [n for n in range(8) if mx[n] > 0 and n != staff]
            att.sort(key=lambda n: (-wexp[n], n))
            kinds = att or ([staff] if mx[staff] > 0 else [])
        old_rank = f.item_rank(iid)
        pick = None
        for kind in kinds:
            ranks = [r for r in R.RANKS if r <= min(old_rank, max(wexp[kind], 1), mx[kind])]
            for rank in sorted(ranks, reverse=True):
                cands = [c for c in t.replacements(kind, rank, R.ival(nj["origin"]))
                         if not f.class_can_hold(job, probe, c, wexp, True)]
                if cands:
                    pick = stream(key, "item", d["file"], str(d["index"]), str(s)).choice(cands)
                    break
            if pick:
                break
        if not pick:
            beast = f.rules["beast_job_category"] in R.flags(nj["category"])
            for kind in kinds:
                cands = [c for c in t.carried(beast, kind) if not f.class_can_hold(job, probe, c, wexp, True)]
                if cands:
                    pick = cands[0]
                    break
        if pick:
            out[f"item_{s}"] = pick
    return out


# ------------------------------------------------------------------ the plan
def plan_recruit(tables: RecruitTables, rng, opts: dict | None = None) -> tuple[list[dict], list[str]]:
    o = check_opts(opts)
    if o["recruit"] == "off":
        return [], []
    key = sub_seed(rng)
    t = tables
    pl, fixed = pools(t, o["recruit"])
    mapping: dict[str, str] = {}
    edits: list[dict] = []
    for attempt in range(MAX_ATTEMPTS):
        mapping = {}
        for pk in sorted(pl):
            mapping.update(permute(pl[pk], stream(key, "pool", pk, str(attempt))))
        edits = build_edits(t, mapping, o, key)
        g = run_guards(t, edits, o)
        if all(v["ok"] for v in g.values()):
            break
    return edits, spoiler(t, mapping, fixed, o, key, attempt)


def build_edits(t: RecruitTables, mapping: dict[str, str], o: dict, key: str) -> list[dict]:
    f = t.facts
    edits: list[dict] = []
    cells = list(t.rules["recruit_keep_cells"]) + (list(t.rules["recruit_full_cells"]) if o["recruit_look"] == "full" else [])
    for spot_pid in sorted(mapping, key=lambda x: R.ival(f.by_pid[x]["index"])):
        filler_pid = mapping[spot_pid]
        if filler_pid == spot_pid:
            continue
        spot, filler = f.by_pid[spot_pid], f.by_pid[filler_pid]
        rows = [(MAIN_FILE, spot, "core")] + [(h["file"], h, "person_hook") for h in t.variants.get(spot_pid, [])]
        row_vals = {}
        for file, row, laid in rows:
            vals = new_row(t, row, spot, filler, o)
            row_vals[row["label"]] = vals
            for c in cells:
                if c in vals and c in row and str(vals[c]) != str(row[c]):
                    edits.append({"table": "Person", "file": file, "index": R.ival(row["index"]), "label": row["label"],
                                  "cell": c, "old": row[c], "new": str(vals[c]), "spot": spot_pid,
                                  "filler": filler_pid, "laid_by": laid,
                                  "look": "full" if c in t.rules["recruit_full_cells"] else "keep"})
        # placements: route-variant placements name no class (empty jid) and take it from their own row, which the
        # core cannot lay yet, so the class goes into the placement's jid (the core lays Dispos); carried weapons
        # that no longer fit are swapped on every placement of the spot
        for d in t.spot_placements(spot_pid):
            pid = d.get("pid", "")
            vals = row_vals.get(pid) or row_vals[spot_pid]
            base = {"table": "DisposUnit", "file": d["file"], "index": R.ival(d["index"]), "label": pid,
                    "spot": spot_pid, "filler": filler_pid, "laid_by": "core"}
            if pid != spot_pid:
                hrow = next(h for h in t.variants[spot_pid] if h["label"] == pid)
                want = vals["job"] if vals["job"] != hrow["job"] else ""
                if (d.get("jid") or "") != want and want:
                    edits.append(dict(base, column="jid", old=d.get("jid", ""), new=want))
            for col, new in fix_items(t, d, spot, vals, key).items():
                edits.append(dict(base, column=col, old=d.get(col, ""), new=new))
        if o["recruit_look"] == "full":
            # round 74 (A1): the chapter copies of the spot's person show the filler's model and menu name too
            edits += copy_edits(t.chapter_copies(spot_pid), spot, filler,
                                t.rules.get("recruit_copy_cells", COPY_CELLS), spot_pid, filler_pid)
            edits.append({"table": "FaceData", "fid": spot["fid"], "show": filler["fid"], "spot": spot_pid,
                          "filler": filler_pid, "laid_by": "engine"})
            edits.append({"table": "Message", "mpid": spot["mpid_name"], "show": filler["mpid_name"],
                          "spot": spot_pid, "filler": filler_pid, "laid_by": "engine"})
    return edits


def copy_edits(copies: list[dict], spot: dict, filler: dict, cells, spot_pid: str, filler_pid: str) -> list[dict]:
    """Round 74 (A1, look = full): Person cells of the chapter copies of the spot's person. A cell changes only where
    the copy shows the spot's own value (a copy with a help text of its own keeps it), to the filler's value; laid
    by the core's person-file path (patch 0034: label pointers in person files, laid after the game stores the
    file)."""
    out = []
    for r in copies:
        for c in cells:
            old, mine, new = r.get(c), spot.get(c), filler.get(c)
            if old and old == mine and new is not None and str(new) != str(old):
                out.append({"table": "Person", "file": r["file"], "index": R.ival(r["index"]), "label": r["label"],
                            "cell": c, "old": old, "new": str(new), "spot": spot_pid, "filler": filler_pid,
                            "laid_by": "person_hook", "look": "full", "copy": True})
    return out


def mapping_of(edits: list[dict]) -> dict[str, str]:
    return {e["spot"]: e["filler"] for e in edits if "spot" in e}


# ------------------------------------------------------------------ the shuffled view for slice 1 and the tracks
def shuffled_facts(facts: R.Facts, edits: list[dict]) -> R.Facts:
    """A copy of facts with the main-file Person cells and the DisposUnit cells of the edits applied (route-variant
    rows are not part of Facts). No edits -> the same object back (Recruitment off changes nothing, R8)."""
    if not edits:
        return facts
    persons = [dict(p) for p in facts.persons]
    by = {p["label"]: p for p in persons}
    dispos = [dict(d) for d in facts.dispos]
    dkey = {(d["file"], R.ival(d["index"])): d for d in dispos}
    for e in edits:
        if e["table"] == "Person" and e["file"] == MAIN_FILE and e["label"] in by:
            by[e["label"]][e["cell"]] = e["new"]
        elif e["table"] == "DisposUnit" and (e["file"], e["index"]) in dkey:
            dkey[(e["file"], e["index"])][e["column"]] = e["new"]
    handover = [dict(h) for h in getattr(facts, "handover", [])]
    hkey = {(h["file"], h["label"]): h for h in handover}
    for e in edits:
        if e["table"] == "Person" and (e["file"], e["label"]) in hkey:
            hkey[(e["file"], e["label"])][e["cell"]] = e["new"]
    jobs = list(facts.jobs.values())
    items = list(facts.items.values())
    subkinds = [{"index": str(k), "kind": str(v), "origin": str(facts.sub_origin.get(k, 0))}
                for k, v in facts.sub_kind.items()]
    return R.Facts(persons, jobs, items, subkinds, dispos, facts.rules, facts.names, handover=handover)


# ------------------------------------------------------------------ guards
def _after(t: RecruitTables, edits: list[dict]):
    """(rows after the edits by (file, label), placements after the edits by (file, index))."""
    rows = {(MAIN_FILE, p["label"]): dict(p) for p in t.facts.persons}
    rows.update({(h["file"], h["label"]): dict(h) for h in t.handover})
    disp = {(d["file"], R.ival(d["index"])): dict(d) for sp in t.facts.by_pid for d in t.spot_placements(sp)}
    for e in edits:
        if e["table"] == "Person" and not e.get("copy"):
            rows[(e["file"], e["label"])][e["cell"]] = e["new"]
        elif e["table"] == "DisposUnit":
            disp[(e["file"], e["index"])][e["column"]] = e["new"]
    return rows, disp


def run_guards(tables: RecruitTables, edits: list[dict], opts: dict | None = None) -> dict:
    o = check_opts(opts)
    t, f = tables, tables.facts
    out: dict[str, dict] = {}

    def g(name, bad, info=None):
        out[name] = {"ok": not bad, "detail": list(bad)[:50] + (info or [])}

    if o["recruit"] == "off":
        g("R8_off_no_edits", [f"{len(edits)} edits with Recruitment off"] if edits else [])
        return out
    pl, fixed = pools(t, o["recruit"])
    mp = mapping_of(edits)
    full_map = {pid: mp.get(pid, pid) for members in pl.values() for pid in members}
    # R1 permutation of each pool
    bad = []
    for pk, members in pl.items():
        got = sorted(full_map[m] for m in members)
        if got != sorted(members):
            bad.append(f"pool {pk}: fillers {got} are not the members {sorted(members)}")
    for s, fl in mp.items():
        if not any(s in m and fl in m for m in pl.values()):
            bad.append(f"{s} <- {fl}: not in the same pool")
    g("R1_permutation", bad)
    # R2 fixed, held and out-of-pool people map to themselves and their rows are untouched
    bad = [f"{e.get('label', e.get('fid'))}: edited although fixed ({fixed[e['spot']]})"
           for e in edits if e.get("spot") in fixed]
    bad += [f"{fl} used as a filler although fixed" for fl in mp.values() if fl in fixed]
    g("R2_fixed_stay", bad)
    # R3 every route-variant row and placement of a spot carries the same filler as its main row
    bad = []
    for e in edits:
        if e.get("copy"):           # round 74: a chapter copy belongs to the spot whose FID_ it shows
            copies = {(r["file"], R.ival(r["index"])) for r in t.chapter_copies(e["spot"])}
            if (e["file"], e["index"]) not in copies or mp.get(e["spot"]) != e["filler"] \
                    or e["old"] != f.by_pid[e["spot"]].get(e["cell"]):
                bad.append(f"{e['label']} ({e['file']}): not a chapter copy of {e['spot']} filled by {e['filler']}")
        elif e["table"] in ("Person", "DisposUnit"):
            sp = t.spot_of(e["label"])
            if sp != e["spot"] or mp.get(sp) != e["filler"]:
                bad.append(f"{e['label']} ({e['file']}): filler {e['filler']} but its spot {sp} has {mp.get(sp)}")
    rows, disp = _after(t, edits)
    for spot_pid, hs in t.variants.items():
        main_job = rows[(MAIN_FILE, spot_pid)]["job"]
        hrows = {h["label"]: rows[(h["file"], h["label"])] for h in hs}
        # every placement of a route row joins in the main row's class (placement jid, else the row's own class),
        # and both placements of one route row in one chapter (Revelation 9's Hayato) agree
        per: dict[tuple, set] = {}
        for d in disp.values():
            if d["pid"] in hrows:
                job = d.get("jid") or hrows[d["pid"]]["job"]
                per.setdefault((d["file"], d["pid"]), set()).add(job)
                if job != main_job:
                    bad.append(f"{d['pid']} {t.facts.chapter_of(d)}: joins as {job}, main row has {main_job}")
        for k, v in per.items():
            if len(v) > 1:
                bad.append(f"{k[1]} in {k[0]}: placements disagree ({sorted(v)})")
    g("R3_route_rows_same_filler", bad)
    # R4 same sex
    bad = [f"{s} <- {fl}" for s, fl in mp.items() if f.female(f.by_pid[s]) != f.female(f.by_pid[fl])]
    g("R4_same_sex", bad)
    # R5 staff user, door opener and vein user per route, on the shuffled rows
    joins = spot_joins(t)
    shared_members = []
    for d in t.facts.dispos:
        ch = f.chapter_of(d)
        if ch[:4] in set(f.rules["shared_chapters"]) and str(d.get("team")) == "0" and d.get("pid") in f.by_pid:
            if d["pid"] not in shared_members:
                shared_members.append(d["pid"])
    for role, name in (("staff", "R5_staff_user_per_route"), ("door", "R5_door_opener_per_route"),
                       ("vein", "R5_vein_user_per_route")):
        bad, info = [], []
        for letter in f.rules["routes"]:
            members = [p for p, js in joins.items() if letter in js] + [p for p in shared_members if p not in joins]
            who = []
            for pid in members:
                row = rows[(MAIN_FILE, pid)]
                if not f.in_scope(row) and not (R.flags(row["flags"]) & set(f.rules["keep_class_person_flags"])):
                    continue
                if role == "vein":
                    ok = f.rules["vein_person_flag"] in R.flags(row["flags"])
                else:
                    ok = row["job"] in f.jobs and R.role_ok_job(f, row, row["job"], role)
                if ok:
                    who.append(pid)
            info.append(f"{letter}: {len(who)}")
            if not who:
                bad.append(f"route {letter}: no {role} user")
        g(name, bad, info)
    # R6 a flier before the ninja-village doors
    cat = t.rules["flier_job_category"]
    bad, info = [], []
    for letter, before in t.rules["recruit_flier_before"].items():
        cut = chapter_num(before)
        who = []
        for pid, js in joins.items():
            if letter in js and js[letter] < cut:
                row = rows[(MAIN_FILE, pid)]
                jobs = {row["job"]} | {d["jid"] for d in disp.values()
                                       if d.get("jid") and t.spot_of(d["pid"]) == pid and f.chapter_of(d)[:1] == letter}
                if any(cat in R.flags(f.jobs[j]["category"]) for j in jobs if j in f.jobs):
                    who.append(pid)
        info.append(f"{letter} before {before}: {len(who)}")
        if not who:
            bad.append(f"route {letter}: no flier before {before}")
    g("R6_flier_before_ninja_doors", bad, info)
    # R7 only the allowed tables and cells
    allowed = set(t.rules["recruit_keep_cells"]) | (set(t.rules["recruit_full_cells"]) if o["recruit_look"] == "full" else set())
    files = {MAIN_FILE, *HANDOVER_FILES, *(h["file"] for h in t.handover)}
    bad = []
    for e in edits:
        if e["table"] == "Person" and e.get("copy"):
            copy_cells = t.rules.get("recruit_copy_cells", COPY_CELLS)
            if o["recruit_look"] != "full" or e["cell"] not in copy_cells or \
                    not e["file"].startswith("GameData/Person/") or e["file"].endswith("_HANDOVER.bin.lz"):
                bad.append(f"chapter copy {e['label']} {e['file']} {e['cell']}")
        elif e["table"] == "Person":
            if e["cell"] not in allowed or e["file"] not in files:
                bad.append(f"Person {e['label']} {e['file']} {e['cell']}")
            if e["cell"] == "flags":
                diff = R.flags(e["old"]) ^ R.flags(e["new"])
                if diff - {f.rules["beast_person_flag"]}:
                    bad.append(f"{e['label']}: flags other than the beast flag changed ({sorted(diff)})")
        elif e["table"] == "DisposUnit":
            if e["column"] not in ("jid", *[f"item_{s}" for s in range(1, 6)]) or not e["file"].startswith("GameData/Dispos/"):
                bad.append(f"Dispos {e['file']} {e['column']}")
        elif e["table"] in ("FaceData", "Message"):
            if o["recruit_look"] != "full":
                bad.append(f"{e['table']} record with keep the face")
        else:
            bad.append(f"table {e['table']}")
    g("R7_only_allowed_cells", bad)
    # R8 holds trivially when on (the off case is above)
    # R9 full identity: the filler has a face id (the missing-expression check needs the face files: plan round 5)
    if o["recruit_look"] == "full":
        bad, info = r9_faces(t, mp)
        g("R9_full_face_exists", bad, info)
    # weapons: every carried weapon usable by the new class at the new weapon exp
    bad = []
    for d in disp.values():
        spot = t.spot_of(d.get("pid", ""))
        if spot not in mp:
            continue
        row = rows[(MAIN_FILE, spot)]
        vrow = rows.get(next(((h["file"], h["label"]) for h in t.variants.get(spot, []) if h["label"] == d["pid"]),
                             (MAIN_FILE, spot)))
        job = d.get("jid") or vrow["job"]
        wexp = [R.ival(vrow[f"weapon_exp.{k}"]) for k in R.KINDS]
        orig = f.by_pid[spot]
        for s in range(1, 6):
            iid = d.get(f"item_{s}", "")
            src = t.original_dispos(d["file"], R.ival(d["index"]))
            why = f.class_can_hold(job, dict(orig, flags=row["flags"]), iid, wexp, f.base_usable(orig, src.get(f"item_{s}", "")))
            if why:
                bad.append(f"{d['pid']} {f.chapter_of(d)} slot {s}: {iid}: {why}")
    g("weapons_usable", bad)
    return out


# ------------------------------------------------------------------ round 74: R9 and the full block (A2, A5)
def _swaps(mp: dict) -> list[tuple[str, str]]:
    return sorted((s, fl) for s, fl in mp.items() if s != fl)


def r9_faces(t: RecruitTables, mp: dict) -> tuple[list[str], list[str]]:
    """R9 (a)(b) (docs/rando/FULL_SWAP_PLAN.md 1.2 with the round-73b check): for every swapped spot A -> B, B has a
    face id and a FaceData record of each kind A has, and each of those records' face package holds the normal
    face (a missing expression shows it). A spot with no record of its own (a generic face) has nothing to fill
    and is only counted. (bad, info). Made-up tables without FaceData: only the face id."""
    f = t.facts
    normal = t.rules.get("face_normal_expression", FACE_NORMAL)
    bad, info = [], []
    no_own = 0
    have_faces = t.given("faces") is not None
    for s, fl in _swaps(mp):
        a, b = f.by_pid[s], f.by_pid[fl]
        if not b.get("fid"):
            bad.append(f"{fl} has no face id")
            continue
        if not have_faces:
            continue
        kinds = [k for k in FACE_KINDS if t.face(a.get("fid", ""), k)]
        if not kinds:       # a generic face (Seal of Flames' class-named recruits): no record of A's to fill
            no_own += 1
            continue
        for k in kinds:
            rb = t.face(b["fid"], k)
            if rb is None:
                bad.append(f"{fl}: no FSID_{k} face record (filling {s})")
                continue
            files = t.package_files(rb.get("package") or "")
            if files is None:
                bad.append(f"{fl}: face package {rb.get('package')!r} not found (filling {s})")
            elif normal not in files:
                bad.append(f"{fl}: face package {rb.get('package')!r} has no normal face (filling {s})")
    if not have_faces:
        info.append("FaceData not given (made-up tables): R9 (a)(b) not checked")
    else:
        miss = missing_faces(t, mp)
        if no_own:
            info.append(f"R9: {no_own} swapped spots have no face record of their own (generic faces): their "
                        "portraits stay as the game draws them")
        info.append(f"R9 (c): {sum(1 for m in miss if m[2])} swapped spots ask for "
                    f"{sum(len(m[2]) for m in miss)} faces their new person lacks (those show the normal face)")
    return bad, info


def missing_faces(t: RecruitTables, mp: dict) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """R9 (c), for the spoiler only: [(A, B, [(expression, first place)])] for every swapped spot: the expressions
    A's scenes ask A's face for (`$Ws<A>|` ... `$E<expression>,|`) that A's own face packages have and one of B's
    lacks; the game shows B's normal face there."""
    f = t.facts
    scenes = t.given("scenes") or {}
    out = []
    for s, fl in _swaps(mp):
        a, b = f.by_pid[s], f.by_pid[fl]
        fa = a.get("fid", "")
        short = fa.split("_", 1)[1] if "_" in fa else ""
        asked = scenes.get(short, {})
        a_has, b_sets = set(), []
        for k in FACE_KINDS:
            ra, rb = t.face(fa, k), t.face(b.get("fid", ""), k)
            if ra is not None:
                a_has |= t.package_files(ra.get("package") or "") or set()
            if rb is not None:
                b_sets.append(t.package_files(rb.get("package") or "") or set())
        miss = sorted((ex, place) for ex, place in asked.items()
                      if ex in a_has and b_sets and any(ex not in bs for bs in b_sets))
        out.append((s, fl, miss))
    return out


def full_text(seed: str, game: str, pairs: list[tuple[str, str]], names: dict, keys: list[str],
              off_chapters: list[str]) -> str:
    """The full block (docs/rando/FULL_BLOCK.md section 4) from plain inputs: pairs [(A's MPID_, B's MPID_)],
    names {language: {MPID_: display name}}, keys = the voice keys to silence, off_chapters = full_off_chapters.
    One `n` line per language and pair (old != new; an old name that would get two new ones is left out), one `s`
    line per key, one `off` line per chapter; sorted so one seed gives one file."""
    n_lines = []
    for lang in sorted(names):
        nm = names[lang]
        got: dict[bytes, set] = {}
        for a, b in pairs:
            old, new = nm.get(a), nm.get(b)
            if old and new and old != new:
                got.setdefault(old.encode("utf-16-le", "surrogatepass"), set()).add(
                    new.encode("utf-16-le", "surrogatepass"))
        for old, news in got.items():
            if len(news) == 1:
                n_lines.append((lang, old, news.pop()))
    n_lines.sort(key=lambda x: (-len(x[1]), x[1], x[0], x[2]))
    s_lines = sorted({k.encode("ascii") for k in keys if k})
    off = sorted(set(off_chapters))
    lines = [f"fates-rando-full {FULL_FORMAT}", f"seed {seed}", f"game {game}"]
    lines += [f"n {lang} {old.hex()} {new.hex()}" for lang, old, new in n_lines]
    lines += [f"s {k.hex()}" for k in s_lines]
    lines += [f"off {c}" for c in off]
    lines.append(f"end {len(n_lines) + len(s_lines) + len(off)}")
    return "\n".join(lines) + "\n"


def full_block(t: RecruitTables, mp: dict, seed: str, game: str = "fates") -> str:
    """The run's full.txt for the swaps mp {spot PID_: filler PID_} (look = full only; the caller writes nothing
    for keep-the-face runs): A's display name -> B's per text language from both main rows' MPID_, A's voice key
    from A's FaceData records (+0x08), full_off_chapters from the rules."""
    f = t.facts
    pairs, keys = [], []
    for s, fl in _swaps(mp):
        a, b = f.by_pid[s], f.by_pid[fl]
        pairs.append((a.get("mpid_name", ""), b.get("mpid_name", "")))
        for k in FACE_KINDS:
            r = t.face(a.get("fid", ""), k)
            if r is not None and r.get("key"):
                keys.append(r["key"])
    return full_text(seed, game, pairs, t.given("names") or {}, keys, list(t.rules.get("full_off_chapters") or []))


def parse_full(text: str) -> dict:
    """The reference reader of full.txt (tests; the core's own parser is in fates_rando_names.rs)."""
    ln = text.splitlines()
    if not ln or ln[0] != f"fates-rando-full {FULL_FORMAT}":
        raise ValueError("not a fates-rando-full file of this format")
    out = {"seed": None, "game": None, "names": [], "silence": [], "off": []}
    count = 0
    for line in ln[1:]:
        w = line.split(" ")
        if w[0] in ("seed", "game"):
            out[w[0]] = w[1]
        elif w[0] == "n":
            out["names"].append((w[1], bytes.fromhex(w[2]).decode("utf-16-le"), bytes.fromhex(w[3]).decode("utf-16-le")))
            count += 1
        elif w[0] == "s":
            out["silence"].append(bytes.fromhex(w[1]).decode("ascii"))
            count += 1
        elif w[0] == "off":
            out["off"].append(w[1])
            count += 1
        elif w[0] == "end":
            if int(w[1]) != count:
                raise ValueError("entry count does not match")
            out["count"] = count
        else:
            raise ValueError(f"unknown line {w[0]!r}")
    if "count" not in out:
        raise ValueError("no end line")
    return out


# ------------------------------------------------------------------ spoiler lines
def spoiler(t: RecruitTables, mapping: dict, fixed: dict, o: dict, key: str, attempt: int) -> list[str]:
    f = t.facts
    look = "keep the face" if o["recruit_look"] == "keep" else "full identity (faces, menu names, models; dialogue names by the message hook)"
    L = ["Character shuffle (who joins where)",
         f"  options: {opts_text(o)}; look: {look}; sub-seed {key[:16]}; draw {attempt + 1}",
         "  Each spot keeps its place in the story and its scenes; the person in it plays as the filler.",
         ""]
    pl, _ = pools(t, o["recruit"])
    for pk in sorted(pl):
        L.append(f"  pool {pk}:")
        for s in pl[pk]:
            fl = mapping.get(s, s)
            L.append(f"    {f.pname(f.by_pid[s])} spot -> {f.pname(f.by_pid[fl])}" + ("" if fl != s else " (stays)"))
    L.append("  fixed:")
    for pid, why in fixed.items():
        L.append(f"    {f.pname(f.by_pid[pid])}: {why}")
    if o["recruit_look"] == "full":
        L.append("  full swap (round 74, robot test only):")
        L.append("    " + NAMES_GAP)
        if t.given("faces") is not None:
            L.append("    scene faces the new person lacks (the game shows their normal face there):")
            n = 0
            for s, fl, miss in missing_faces(t, mapping):
                if miss:
                    n += 1
                    L.append(f"      {f.pname(f.by_pid[fl])} in {f.pname(f.by_pid[s])}'s spot: {len(miss)}: "
                             + "; ".join(f"{ex} (first {place})" for ex, place in miss))
            if not n:
                L.append("      none")
    L.append("  " + CREDIT)
    return L


# ------------------------------------------------------------------ CLI (tests and the owner; rando.py is wired later)
def all_option_sets() -> list[dict]:
    out = []
    for rec in ("route", "any"):
        for look in ("keep", "full"):
            for cls in ("own", "slot"):
                for st in ("autolevel", "slot"):
                    out.append({"recruit": rec, "recruit_look": look, "recruit_class": cls, "recruit_stats": st})
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "check"):
        p = sub.add_parser(name)
        p.add_argument("--recruit", choices=CHOICES["recruit"], default="route" if name == "plan" else None)
        p.add_argument("--recruit-look", choices=CHOICES["recruit_look"], default=None)
        p.add_argument("--recruit-class", choices=CHOICES["recruit_class"], default=None)
        p.add_argument("--recruit-stats", choices=CHOICES["recruit_stats"], default=None)
        if name == "plan":
            p.add_argument("--seed", required=True)
            p.add_argument("--json", help="write the edits as JSON (a path under build/)")
        else:
            p.add_argument("--seeds", type=int, default=50)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    t = load_tables()
    given = {k: getattr(a, k) for k in DEFAULT_OPTS if getattr(a, k) is not None}
    if a.cmd == "plan":
        o = check_opts(given)
        edits, lines = plan_recruit(t, a.seed, o)
        print("\n".join(lines))
        g = run_guards(t, edits, o)
        for k, v in g.items():
            print(f"{'ok  ' if v['ok'] else 'FAIL'} {k}" + ("" if v["ok"] else ": " + "; ".join(v["detail"][:5])))
        laid = {}
        for e in edits:
            laid[e["laid_by"]] = laid.get(e["laid_by"], 0) + 1
        print(f"{len(edits)} edits: " + ", ".join(f"{k} {v}" for k, v in sorted(laid.items())))
        if a.json:
            path = os.path.abspath(a.json)
            if not path.startswith(os.path.join(ROOT, "build") + os.sep):
                raise SystemExit("--json must be a path under build/ (game values never go into git)")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"opts": o, "edits": edits, "spoiler": lines}, fh, ensure_ascii=False, indent=1)
            print("wrote", path)
        return 0 if all(v["ok"] for v in g.values()) else 1
    sets = [check_opts(dict(s, **given)) for s in all_option_sets()] if not given.get("recruit") else [check_opts(given)]
    fails = 0
    for o in sets:
        bad = 0
        for i in range(a.seeds):
            edits, _ = plan_recruit(t, f"chk{i}", o)
            g = run_guards(t, edits, o)
            nb = [k for k, v in g.items() if not v["ok"]]
            if nb:
                bad += 1
                print(f"  seed chk{i} {opts_text(o)}: {nb}")
        print(f"{'ok  ' if not bad else 'FAIL'} {opts_text(o)}: {a.seeds - bad}/{a.seeds} seeds pass every guard")
        fails += bad
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
