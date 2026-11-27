#!/usr/bin/env python3
"""Fire Emblem Fates randomizer, track "chests" (round 70 desk work, big goal 1; docs/rando/CHESTS.md).

What it plans: the item a chest, a village or a talk gift hands over. These are not table data in this game: each
chapter's event script (Scripts/**/<chapter>_Terrain.cmb for chests and villages, Scripts/**/<chapter>.cmb for
talks and story events) calls ev::ItemGain with the item's IID as a literal string. This module

  - reads those calls (a small READ-ONLY bytecode reader: it never writes a script, a text file or anything in the
    RomFS),
  - plans a new item for each changeable call (same band as the old item, like the castle rewards; no repeat inside
    one chapter; story and key items never change; deterministic per seed),
  - writes the plan.json "chests" list (plan["chests"]) and the chest list file chests.txt (engine_list) that the
    game core's hook reads (round 71, patch 0031, crates/zakuro-core/src/fates_rando_chests.rs; CHESTS.md section 3:
    the hook swaps the IID pointer at the entry of the game's ev::ItemGain handler, 0x003B0768).

OFF BY DEFAULT. Round 71 wires it into tracks.py (option "chests", rando.py --chests off|on, the page row "Chest and
village items"); with it off plan_chests returns nothing, add_to_plan leaves the plan untouched, no chests.txt is
written and the key stays out of mod.json, plan.json, the make flags and the page answer, so every seed fingerprint
and every run id stays the same.

The chest list file (chests.txt, in the run's mod folder; the core copies it into the run folder beside patch.txt):

    fates-rando-chests 1
    seed <seed>
    c <chapter> <original IID hex> <new IID hex> <new IID offset hex>
    end <number of c lines>

Labels are the bytes the game holds (cp932), in hex, so the file is plain ASCII. The offset is where the new IID's
own label text lies in GameData's string pool, from GameData's data start (the same base patch.txt's "g" label
offsets count from); the hook checks the bytes there before it points the handler at them. Only entries whose item
changes are listed. No file (or no c line) = the hook stays off for that run (the original word stays in memory).

    python tools/randomizer/chests.py list  [--game fates|seal] [--out build/r70/chests/calls_<game>.json]
    python tools/randomizer/chests.py counts [--game fates|seal]
    python tools/randomizer/chests.py kinds  [--game fates|seal]     (terrain under every chest / village tile event)
    python tools/randomizer/chests.py plan --seed S [--game ...] [--out build/r70/chests/plan_<seed>.json]

Facts only: chapter ids, script file names, call indexes and IID labels (the same kind of ids rules.json holds).
Seal of Flames scripts are read from the installed mod (over the base game's), nothing of them is committed.
Our own code; public tools were read for facts only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import randolib as R  # noqa: E402

TRACK = "chests"
TOOL_VERSION = "rando-chests-v1"
# "off" = nothing planned (default); "on" = chests, villages and talk gifts get a same-band item
DEFAULT_OPTS = {"chests": "off", "chest_kinds": "chest,village,talk"}

# ---------------------------------------------------------------- the script format (facts, read from the files)
CMB_MAGIC = b"cmb\0"
H_FUNCS, H_POOL = 0x1C, 0x20            # header: function table offset, string pool offset
F_CODE, F_TYPE, F_ARGC, F_ARGS = 4, 8, 9, 0x14   # function header: code start, event type, arg count, args offset
EV_TERRAIN, EV_TALK = 0x15, 0x17        # event types: a map tile event (chest, village, vein...), a talk
TERRAIN_KIND = {10: "chest", 1: "village"}   # a tile event's 5th argument [medium: by counts and context]
# operand bytes of each opcode (every function of the base game's 624 scripts and Seal of Flames' 249 walks to its
# end with this table; an unknown opcode stops the walk of that function and is counted)
OPLEN = {0x19: 1, 0x1A: 2, 0x1B: 4, 0x1C: 1, 0x1D: 2, 0x1F: 4, 0x47: 3, 0x07: 1, 0x46: 1, 0x01: 1, 0x02: 1,
         0x03: 1, 0x04: 1, 0x05: 1, 0x06: 1, 0x08: 1, 0x09: 1, 0x0A: 1, 0x0B: 1, 0x49: 2, 0x4A: 2, 0x4B: 2,
         0x4C: 2, 0x4D: 2}
for _op in (0x20, 0x21, 0x23, 0x48, 0x4E, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56):
    OPLEN[_op] = 0
for _op in range(0x26, 0x46):
    OPLEN.setdefault(_op, 0)
OP_RET = 0x54

GIVE_CALLS = ("ev::ItemGain", "ev::ItemGainSilent", "ev::ItemGainNoSound", "ev::ItemGainMessageOnly",
              "ev::ItemGainMessageOnlyNoSound")
GOLD_CALLS = ("ev::GoldGain", "ev::GoldGainSilent", "ev::GoldGain2")
OTHER_CALLS = ("ev::ItemGetRandom", "ev::ItemReplaceForYatonokami")
HOOKED_CALL = "ev::ItemGain"            # the one handler the engine hook covers (0x003B0768, CHESTS.md 3)
# round 71: the chest list the core's hook reads (fates_rando_chests.rs FILE / FORMAT)
LIST_FILE = "chests.txt"
LIST_FORMAT = 1
LIST_MAGIC = "fates-rando-chests"
MAX_LABEL = 63                          # the hook reads at most 64 bytes of a label (63 + its NUL)
# the terrain a tile event of each kind sits on (round 71 `kinds`: every Fates and Seal of Flames chest tile event is
# on a treasure chest tile, every village one on a village tile)
KIND_TERRAIN = {"chest": ("TID_宝箱", "TID_闇／宝箱"), "village": ("TID_村", "TID_村（足跡）")}

# story and key items a script hands over that never change (besides every item the items track will not place:
# ItemView.placeable, i.e. precious / chapter-only / divine / can't-remove / key / instant-gold / personal flags)
STORY_ITEMS = {
    "IID_夜刀神": "Yato (Corrin's sword) and its forms",
    "IID_夜刀神・空夜": "Yato form (Birthright)", "IID_夜刀神・白夜": "Yato final form (Birthright)",
    "IID_夜刀神・長夜": "Yato form (Conquest)", "IID_夜刀神・暗夜": "Yato final form (Conquest)",
    "IID_夜刀神・幻夜": "Yato form (Revelation)", "IID_夜刀神・終夜": "Yato final form (Revelation)",
    "IID_ガングレリ": "Ganglari (prologue story sword)",
    "IID_竜石": "Dragonstone (Corrin's, given in the prologue)",
    "IID_竜のブレス": "Draconic Rage (story gift)",
    "IID_ミステルトィン": "Missiletainn (a paralogue's story gift)",
    "IID_扉の鍵": "Door key (a map's key gift)", "IID_宝の鍵": "Chest key (a map's key gift)",
}


class ChestsError(R.RandoError):
    pass


def _cstr(d: bytes, o: int) -> str:
    e = d.find(b"\0", o)
    b = d[o:e if e >= 0 else len(d)]
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp932", "replace")


def read_cmb(d: bytes) -> list[dict]:
    """READ ONLY. The functions of one compiled event script: [{index, type, args (the event's own arguments, a
    tile event's x, y, w, h, kind...), calls: [{name, args (literal int/str, None = not a literal)}], walked (the
    walk reached the function's end)}]. A heuristic call reader, not a decompiler: the literal arguments it
    reports are the pushes right before the call."""
    if d[:4] != CMB_MAGIC:
        raise ChestsError("not a cmb script")
    pool = struct.unpack_from("<I", d, H_POOL)[0]
    tab = struct.unpack_from("<I", d, H_FUNCS)[0]
    starts = []
    o = tab
    while o + 4 <= len(d):
        v = struct.unpack_from("<I", d, o)[0]
        if v == 0:
            break
        starts.append(v)
        o += 4
    out = []
    for i, f in enumerate(starts):
        code = struct.unpack_from("<I", d, f + F_CODE)[0]
        end = starts[i + 1] if i + 1 < len(starts) else pool
        typ, argc = d[f + F_TYPE], d[f + F_ARGC]
        argo = struct.unpack_from("<I", d, f + F_ARGS)[0]
        hargs = list(struct.unpack_from(f"<{argc}I", d, argo)) if f < argo <= len(d) - 4 * argc else []
        calls, st, pc, walked = [], [], code, True
        while pc < end:
            op = d[pc]
            if op == 0 and d[pc - 1] == OP_RET:
                break
            n = OPLEN.get(op)
            if n is None:
                walked = False
                break
            a = d[pc + 1:pc + 1 + n]
            if op == 0x19:
                st.append(a[0])
            elif op == 0x1A:
                st.append(int.from_bytes(a, "big"))
            elif op == 0x1C:
                st.append(_cstr(d, pool + a[0]))
            elif op == 0x1D:
                st.append(_cstr(d, pool + int.from_bytes(a, "big")))
            elif op == 0x47:
                name = _cstr(d, pool + int.from_bytes(a[:2], "big"))
                k = a[2]
                args = st[len(st) - k:] if k else []
                args = [None] * (k - len(args)) + args
                del st[max(0, len(st) - k):]
                calls.append({"name": name, "args": args})
                st.append(None)
            elif op in (0x21, 0x4C, 0x4D):
                if st:
                    st.pop()
            elif op == 0x23:
                del st[-2:]
            elif 0x26 <= op <= 0x45:
                st[-2:] = [None]
            elif n:
                st.append(None)
            pc += 1 + n
        out.append({"index": i, "type": typ, "args": hargs, "calls": calls, "walked": walked})
    return out


# ---------------------------------------------------------------- the list of item-giving calls (read only)
def chapter_of(rel: str) -> str:
    return os.path.basename(rel).split(".")[0].split("_")[0][:4]


def script_files(dirs: list[str]) -> dict[str, str]:
    """{relative path under Scripts (with /): absolute path}; later dirs lay over earlier ones (a mod over the base
    game, the way the game's layered RomFS serves them)."""
    out: dict[str, str] = {}
    for top in dirs:
        s = os.path.join(top, "Scripts")
        for dp, dn, fs in os.walk(s):
            dn.sort()
            for fn in sorted(fs):
                if fn.endswith(".cmb"):
                    p = os.path.join(dp, fn)
                    out[os.path.relpath(p, s).replace(os.sep, "/")] = p
    return out


def classify(func: dict, call: str) -> str:
    if call in GOLD_CALLS:
        return "gold"
    if func["type"] == EV_TERRAIN and len(func["args"]) >= 5:
        return TERRAIN_KIND.get(func["args"][4], "tile")
    if func["type"] == EV_TALK:
        return "talk"
    return "event"


def calls_in(rel: str, data: bytes) -> tuple[list[dict], int]:
    """(the item-giving calls of one script, functions whose walk stopped early)."""
    out, bad, n = [], 0, 0
    for fn in read_cmb(data):
        bad += 0 if fn["walked"] else 1
        for c in fn["calls"]:
            nm = c["name"]
            if nm not in GIVE_CALLS + GOLD_CALLS + OTHER_CALLS:
                continue
            item = None
            if nm in GIVE_CALLS:
                v = c["args"][-1] if c["args"] else None
                item = v if isinstance(v, str) else "variable"
            elif nm in GOLD_CALLS:
                v = c["args"][1] if len(c["args"]) > 1 else None
                item = f"gold:{v}" if isinstance(v, int) else "gold:variable"
            elif nm == "ev::ItemReplaceForYatonokami":
                v = c["args"][-1] if c["args"] else None
                item = v if isinstance(v, str) else "variable"
            else:
                item = "variable"
            row = {"chapter": chapter_of(rel), "file": rel, "call": n, "func": fn["index"], "call_name": nm,
                   "kind": classify(fn, nm), "item": item}
            if fn["type"] == EV_TERRAIN and len(fn["args"]) >= 2:
                row["x"], row["y"] = fn["args"][0], fn["args"][1]
            out.append(row)
            n += 1
    return out, bad


def scan(dirs: list[str]) -> tuple[list[dict], dict]:
    """READ ONLY. Every item-giving call of every script under dirs (later dirs lay over earlier ones)."""
    rows, files, bad = [], 0, 0
    for rel, p in sorted(script_files(dirs).items()):
        with open(p, "rb") as fh:
            data = fh.read()
        r, b = calls_in(rel, data)
        rows += r
        bad += b
        files += 1
    return rows, {"files": files, "functions_not_walked": bad}


def game_dirs(game: str = "fates") -> list[str]:
    import sources as S
    g = S.check_game(game)
    return [S.BASE_ROMFS] if g == "fates" else [S.BASE_ROMFS, S.seal_romfs()]


def active_dirs() -> list[str]:
    """The RomFS view the tables are read from now (sources.activate): Fates' extracted RomFS, or the Seal of Flames
    layer (base + mod, its Scripts included), so a make reads the scripts of the same game as its tables."""
    import sources as S
    st = getattr(S, "_STATE", None) or {}
    return [st.get("romfs") or S.BASE_ROMFS]


# ---------------------------------------------------------------- scope and counts
def story_chapter(ch: str, rules: dict) -> bool:
    pat = (rules.get("scope") or {}).get("story_file") or r"^[ABCX]\d{3}$"
    return re.match(pat, ch) is not None


def route_of(ch: str, rules: dict) -> str:
    """"shared", a route letter of rules["routes"], "paralogue" (X), or "other"."""
    if ch in rules.get("shared_chapters", []):
        return "shared"
    if ch[:1] in rules.get("routes", {}):
        return ch[:1]
    return "paralogue" if ch[:1] == "X" else "other"


def counts(rows: list[dict], rules: dict) -> dict:
    """{route name: {kind: n}} over story chapters; a route counts the shared chapters too (as the player sees it);
    paralogues are listed on their own (several are route-only)."""
    out: dict[str, dict[str, int]] = {}
    story = [r for r in rows if story_chapter(r["chapter"], rules)]
    for letter, name in rules.get("routes", {}).items():
        c: dict[str, int] = {}
        for r in story:
            if route_of(r["chapter"], rules) in ("shared", letter):
                c[r["kind"]] = c.get(r["kind"], 0) + 1
        out[name] = dict(sorted(c.items()))
    for grp in ("paralogue", "other"):
        c = {}
        for r in story:
            if route_of(r["chapter"], rules) == grp:
                c[r["kind"]] = c.get(r["kind"], 0) + 1
        if c:
            out[grp] = dict(sorted(c.items()))
    return out


# ---------------------------------------------------------------- the plan
def sub_rng(seed: str, opts: dict | None = None) -> int:
    o = {k: (opts or {}).get(k, v) for k, v in DEFAULT_OPTS.items()}
    key = "\x1f".join([TOOL_VERSION, R.check_seed(seed), TRACK, json.dumps(o, sort_keys=True)])
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big")


def _stream(base: int, *parts) -> random.Random:
    key = "\x1f".join([str(base)] + [str(p) for p in parts])
    return random.Random(int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest(), "big"))


def hook_shared(rows: list[dict], iv, kinds: set[str], rules: dict) -> set[tuple[str, str]]:
    """(chapter, item) pairs that a KEPT ev::ItemGain call of that chapter also hands over (round 71). The hook knows
    only the chapter and the item it is handed, so such a slot would change the kept gift too: it is kept whole."""
    return {(r["chapter"], r["item"]) for r in rows
            if r["call_name"] == HOOKED_CALL and r["item"] != "variable" and _keep_base(r, iv, kinds, rules)}


def keep_reason(row: dict, iv, kinds: set[str], rules: dict, shared: set | None = None) -> str | None:
    """Why a call keeps its item (None = it may change). shared: hook_shared(...) of all the rows (None = not
    checked, the round-70 rule)."""
    why = _keep_base(row, iv, kinds, rules)
    if why is None and shared and (row["chapter"], row["item"]) in shared:
        return "a kept gift of this chapter is the same item (the hook could not tell them apart)"
    return why


def _keep_base(row: dict, iv, kinds: set[str], rules: dict) -> str | None:
    if not story_chapter(row["chapter"], rules):
        return "not a story chapter"
    if row["call_name"] != HOOKED_CALL:
        return "story handler (not ev::ItemGain)" if row["call_name"] in GIVE_CALLS else "not an item gift"
    if row["kind"] not in kinds:
        return f"{row['kind']} gifts are not changed"
    it = row["item"]
    if it == "variable":
        return "item chosen at run time"
    if it in STORY_ITEMS or any(it.startswith(s + "・") for s in STORY_ITEMS):
        return "story item"
    if not iv.placeable(it):
        return "story, key, gold or personal item"
    if iv.band(it) is None:
        return "no band (stone or seal)"
    return None


def plan_chests(facts: R.Facts, rows: list[dict], seed: str, opts: dict | None = None):
    """(entries, spoiler lines). entries: one per changeable (chapter, original item) slot, in file order:
    {"chapter", "kind", "orig", "new", "calls": [[file, call], ...], "x", "y" (tile events)}. Off (the default) ->
    ([], [])."""
    o = dict(DEFAULT_OPTS, **(opts or {}))
    if o["chests"] != "on":
        return [], []
    import items as I
    iv = I.ItemView(facts)
    kinds = {k.strip() for k in str(o["chest_kinds"]).split(",") if k.strip()}
    base = sub_rng(seed, o)
    pool = [it["label"] for it in facts.item_list if iv.placeable(it["label"]) and iv.band(it["label"]) is not None
            and it["label"] not in STORY_ITEMS]
    shared = hook_shared(rows, iv, kinds, facts.rules)
    slots: dict[tuple, dict] = {}
    for r in rows:
        if keep_reason(r, iv, kinds, facts.rules, shared):
            continue
        k = (r["chapter"], r["item"])
        s = slots.get(k)
        if s is None:
            s = slots[k] = {"chapter": r["chapter"], "kind": r["kind"], "orig": r["item"], "calls": []}
            if "x" in r:
                s["x"], s["y"] = r["x"], r["y"]
        s["calls"].append([r["file"], r["call"]])
    entries, lines = [], ["Chests, villages and talk gifts (same band, no repeat inside a chapter):"]
    used: dict[str, set] = {}
    for k in sorted(slots, key=lambda k: (k[0], slots[k]["calls"][0])):
        s = slots[k]
        b = iv.band(s["orig"])
        cands = [i for i in pool if iv.band(i) == b]
        u = used.setdefault(s["chapter"], set())
        fresh = [i for i in cands if i not in u] or cands
        fresh = [i for i in fresh if i != s["orig"]] or fresh       # another item when one fits
        new = _stream(base, "chest", s["chapter"], s["orig"]).choice(fresh)
        u.add(new)
        entries.append(dict(s, new=new))
        lines.append(f"  {s['chapter']} {s['kind']}: {facts.iname(s['orig'])} -> {facts.iname(new)}")
    return entries, lines


def check_chests(facts: R.Facts, rows: list[dict], entries: list[dict], opts: dict | None = None) -> dict:
    """Guards from the entries alone: {name: {"ok": bool, "bad": [...]}}."""
    import items as I
    o = dict(DEFAULT_OPTS, **(opts or {}))
    iv = I.ItemView(facts)
    kinds = {k.strip() for k in str(o["chest_kinds"]).split(",") if k.strip()}
    out = {}

    def g(name, bad):
        # "detail" is the randomizer's guard shape (plan["guards"], the spoiler); "bad" the round-70 name, kept
        out[f"chests: {name}"] = {"ok": not bad, "detail": bad[:20], "bad": bad[:20]}
    by_call = {(r["file"], r["call"]): r for r in rows}
    shared = hook_shared(rows, iv, kinds, facts.rules)
    bad = []
    for e in entries:
        for f, c in e["calls"]:
            r = by_call.get((f, c))
            if r is None or r["item"] != e["orig"] or r["chapter"] != e["chapter"]:
                bad.append(f"{f}#{c}: not the planned call")
            elif keep_reason(r, iv, kinds, facts.rules, shared):
                bad.append(f"{f}#{c}: a kept call was planned ({keep_reason(r, iv, kinds, facts.rules, shared)})")
    g("only_changeable_calls", bad)
    g("story_and_key_items_kept", [f"{e['chapter']}: {e['new']} placed" for e in entries
                                   if e["new"] in STORY_ITEMS or not iv.placeable(e["new"])])
    g("same_band", [f"{e['chapter']}: {e['orig']} -> {e['new']}" for e in entries
                    if iv.band(e["orig"]) != iv.band(e["new"])])
    seen: dict[str, list] = {}
    for e in entries:
        seen.setdefault(e["chapter"], []).append(e)
    rep = []
    for ch, es in seen.items():
        news = [e["new"] for e in es]
        for n in set(news):
            if news.count(n) > 1:
                band = iv.band(n)
                room = len({i for i in facts.items if iv.placeable(i) and iv.band(i) == band})
                need = sum(1 for e in es if iv.band(e["orig"]) == band)
                if room >= need:
                    rep.append(f"{ch}: {n} twice")
    g("no_repeat_in_chapter", rep)
    keys = [(e["chapter"], e["orig"]) for e in entries]
    g("one_entry_per_chapter_item", sorted({f"{c} {i}" for c, i in keys if keys.count((c, i)) > 1}))
    return out


def engine_table(entries: list[dict]) -> dict[str, dict[str, str]]:
    """What the hook reads: {chapter: {original IID: new IID}} (unchanged entries left out)."""
    out: dict[str, dict[str, str]] = {}
    for e in entries:
        if e["new"] != e["orig"]:
            out.setdefault(e["chapter"], {})[e["orig"]] = e["new"]
    return out


def add_to_plan(plan: dict, entries: list[dict]) -> dict:
    """plan["chests"] = the entries (only when there are any: an off track leaves the plan byte for byte the same)."""
    if entries:
        plan["chests"] = [{k: e[k] for k in ("chapter", "kind", "orig", "new", "calls", "x", "y") if k in e}
                          for e in entries]
    return plan


# ---------------------------------------------------------------- the chest list the core's hook reads (round 71)
def label_bytes(label: str) -> bytes:
    """A label as the game holds it (cp932, like every GameData label; the scripts hand the same bytes over)."""
    return label.encode("cp932")


def label_offsets(labels) -> dict[str, int]:
    """{label: offset of its text in GameData's string pool, from GameData's data start} for the ACTIVE game's
    GameData (sources.activate), through the in-memory patch's own pool reader (ingame._pool_index). A label that is
    not in the pool is left out (engine_list then refuses)."""
    import ingame as IG
    pool = IG._pool_index(IG._T().container(IG.GAMEDATA_REL))
    out = {}
    for lab in labels:
        b = label_bytes(lab)
        if b in pool:
            out[lab] = pool[b]
    return out


def engine_list(entries: list[dict], offsets: dict[str, int], seed: str) -> str:
    """The chest list file's text (module text above): one c line per entry whose item changes, in plan order.
    offsets: label_offsets(...) of at least every new item. Raises ChestsError when a new item has no offset, a
    label does not fit the hook (MAX_LABEL bytes) or a chapter is not 4 letters/digits."""
    lines = [f"{LIST_MAGIC} {LIST_FORMAT}", f"seed {R.check_seed(seed)}"]
    n = 0
    seen = set()
    for e in entries:
        if e["new"] == e["orig"]:
            continue
        ch = e["chapter"]
        if not re.fullmatch(r"[A-Z0-9]{4}", ch):
            raise ChestsError(f"chapter {ch!r} is not 4 capital letters or digits")
        o, nw = label_bytes(e["orig"]), label_bytes(e["new"])
        if not 0 < len(o) <= MAX_LABEL or not 0 < len(nw) <= MAX_LABEL:
            raise ChestsError(f"{ch}: {e['orig']} -> {e['new']}: a label is empty or longer than {MAX_LABEL} bytes")
        if e["new"] not in offsets:
            raise ChestsError(f"{ch}: {e['new']} is not in GameData's string pool (the hook could not point at it)")
        if (ch, o) in seen:
            raise ChestsError(f"{ch}: {e['orig']} is listed twice")
        seen.add((ch, o))
        lines.append(f"c {ch} {o.hex()} {nw.hex()} {offsets[e['new']]:x}")
        n += 1
    lines.append(f"end {n}")
    return "\n".join(lines) + "\n"


def parse_engine_list(text: str) -> dict:
    """The Python reading of the chest list (the same rules as fates_rando_chests.rs Table::parse; the tests keep
    them together): {"seed", "entries": [{"chapter", "orig" (bytes), "new" (bytes), "new_at"}]}."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines or lines[0] != f"{LIST_MAGIC} {LIST_FORMAT}":
        raise ChestsError("not a chest list (format 1)")
    seed, entries, end = None, [], None
    for ln in lines[1:]:
        parts = ln.split()
        if end is not None:
            raise ChestsError("a line after end")
        if parts[0] == "seed" and len(parts) == 2 and seed is None and not entries:
            seed = parts[1]
        elif parts[0] == "c" and len(parts) == 5:
            ch = parts[1]
            if not re.fullmatch(r"[A-Z0-9]{4}", ch):
                raise ChestsError(f"bad chapter {ch!r}")
            try:
                o, nw, at = bytes.fromhex(parts[2]), bytes.fromhex(parts[3]), int(parts[4], 16)
            except ValueError:
                raise ChestsError(f"bad c line {ln!r}") from None
            if not 0 < len(o) <= MAX_LABEL or not 0 < len(nw) <= MAX_LABEL or b"\0" in o + nw:
                raise ChestsError(f"bad label in {ln!r}")
            if any(x["chapter"] == ch and x["orig"] == o for x in entries):
                raise ChestsError(f"{ch}: an item listed twice")
            entries.append({"chapter": ch, "orig": o, "new": nw, "new_at": at})
        elif parts[0] == "end" and len(parts) == 2:
            end = int(parts[1])
            if end != len(entries):
                raise ChestsError(f"end says {end}, the list has {len(entries)}")
        else:
            raise ChestsError(f"bad line {ln!r}")
    if end is None:
        raise ChestsError("no end line (the file is not complete)")
    return {"seed": seed, "entries": entries}


# ---------------------------------------------------------------- the tile event kinds, checked on the maps (round 71)
def terrain_kinds(rows: list[dict]) -> dict[str, dict[str, int]]:
    """{kind: {terrain tid under the tile event: tile events}} for the chest and village tile events of rows, read
    from each chapter's own terrain file (GameData/Terrain/<chapter>.bin.lz) in the active RomFS view. Settles the
    [medium] kind numbers 10 = chest, 1 = village of round 70 from the maps (KIND_TERRAIN). Read only."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "maps"))
    import maplib as ML
    files = {ML.stem(f): f for f in ML.terrain_files()}
    terr: dict[str, object] = {}
    out: dict[str, dict[str, int]] = {}
    seen = set()
    for r in rows:
        if r["kind"] not in ("chest", "village") or "x" not in r:
            continue
        k = (r["chapter"], r["x"], r["y"], r["kind"])
        if k in seen:
            continue
        seen.add(k)
        c = out.setdefault(r["kind"], {})
        f = files.get(r["chapter"])
        if f is None:
            c["(no terrain file)"] = c.get("(no terrain file)", 0) + 1
            continue
        t = terr.get(f) or terr.setdefault(f, ML.Terrain(f))
        if not (0 <= r["x"] < t.width and 0 <= r["y"] < t.height):
            c["(off the map)"] = c.get("(off the map)", 0) + 1
            continue
        i = t.tile(r["x"], r["y"])
        tid = t.trows[i][t.thead.index("tid")] if i < len(t.trows) else "(no tile row)"
        c[tid] = c.get(tid, 0) + 1
    return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}


def kinds_ok(tk: dict[str, dict[str, int]]) -> list[str]:
    """The tile events that do not sit on their kind's terrain (KIND_TERRAIN): [] = kinds 10 and 1 confirmed."""
    return [f"{k}: {n} on {tid}" for k, c in tk.items() for tid, n in c.items() if tid not in KIND_TERRAIN.get(k, ())]


# ---------------------------------------------------------------- the robot's judge (pure)
def judge_gain(entries: list[dict], chapter: str, orig: str | None, gained: list[str],
               x: int | None = None, y: int | None = None) -> dict:
    """Was the item the game gave the one plan.json says? entries: plan["chests"] (may be empty: an off run must
    give the original); chapter/orig (or x, y of a tile event) name the chest or village the robot opened;
    gained: the IIDs that appeared in the unit's inventory or the convoy at that moment (rcheck.items_gained).
    -> {"ok", "want", "got", "why"}."""
    e = None
    if x is not None and y is not None:
        e = next((e for e in entries if e["chapter"] == chapter and e.get("x") == x and e.get("y") == y), None)
    if e is None and orig is not None:
        e = next((e for e in entries if e["chapter"] == chapter and e["orig"] == orig), None)
    if e is None and orig is None:
        return {"ok": False, "want": None, "got": list(gained), "why": "chest not named (no item, no tile)"}
    want = e["new"] if e else orig
    if len(gained) != 1:
        return {"ok": False, "want": want, "got": list(gained),
                "why": "nothing gained" if not gained else "more than one item gained"}
    ok = gained[0] == want
    why = "as planned" if ok and e else "kept item, as planned" if ok else (
        "the original item came (hook not active?)" if e and gained[0] == e["orig"] else "another item came")
    return {"ok": ok, "want": want, "got": gained[0], "why": why}


# ---------------------------------------------------------------- command line
def _out_path(p: str) -> str:
    p = os.path.abspath(p)
    if not p.startswith(os.path.join(ROOT, "build") + os.sep):
        raise ChestsError("outputs go under build/ only (game facts stay out of git)")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("list", "counts", "kinds", "plan"))
    ap.add_argument("--game", default="fates")
    ap.add_argument("--seed", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    try:
        import sources as S
        g = S.check_game(a.game)
        rules = S.load_rules(g)
        rows, info = scan(game_dirs(g))
        if a.cmd == "counts":
            print(json.dumps({"game": g, "info": info, "counts": counts(rows, rules)}, ensure_ascii=False, indent=1))
        elif a.cmd == "kinds":
            if g != "fates":
                S.activate(g)
            tk = terrain_kinds(rows)
            bad = kinds_ok(tk)
            print(json.dumps({"game": g, "terrain": tk, "not_on_their_terrain": bad}, ensure_ascii=False, indent=1))
            return 1 if bad else 0
        elif a.cmd == "list":
            data = json.dumps({"game": g, "info": info, "calls": rows}, ensure_ascii=False, indent=1)
            if a.out:
                with open(_out_path(a.out), "w", encoding="utf-8") as fh:
                    fh.write(data)
                print(f"{len(rows)} calls -> {a.out}")
            else:
                print(data)
        else:
            if g != "fates":
                S.activate(g)
            import gamedata as GD
            f = GD.load_facts(rules)
            e, lines = plan_chests(f, rows, a.seed, {"chests": "on"})
            gd = check_chests(f, rows, e, {"chests": "on"})
            res = {"game": g, "seed": a.seed, "chests": add_to_plan({}, e).get("chests", []), "guards": gd,
                   "list": engine_list(e, label_offsets({x["new"] for x in e}), a.seed or "s")}
            if a.out:
                with open(_out_path(a.out), "w", encoding="utf-8") as fh:
                    json.dump(res, fh, ensure_ascii=False, indent=1)
            print("\n".join(lines))
            print("guards:", "all green" if all(v["ok"] for v in gd.values()) else
                  [k for k, v in gd.items() if not v["ok"]])
    except (R.RandoError, OSError, Exception) as ex:  # noqa: BLE001  (SourceError and friends)
        print(f"chests: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
