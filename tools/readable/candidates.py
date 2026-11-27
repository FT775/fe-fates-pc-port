#!/usr/bin/env python3
"""Readable-layer worklist from the game's own symbol map (tools/readable/symmap.py).

    python tools/readable/candidates.py            write config/readable/candidates.csv
    python tools/readable/candidates.py --summary  counts per batch/system/kind only
    python tools/readable/candidates.py --selftest classification rules on made-up names

Each game function whose name places it in a game system becomes one row, grouped into
batches in the order the Awakening port wrote them (docs/READABLE.md section 7: data
getters, unit stats, battle, map, AI, events and progress, save data), then the systems
that Fates adds (castle, pair-up/dual, dragon veins, Live2D petting, amiibo). Library code
(nn::, nw::, std::, __rw::, live2d::, NEX/Pia, the RVCT runtime) is left out: it is either
HLE'd by the engine or byte-identical to known SDK code.

Columns (addresses, names and our own judgements only; no code, no data):
  address      function start (0x + 8 hex)
  name         suggested C name (symmap.c_name; snake_case renaming is the writer's job)
  symbol       the demangled name from the map
  batch        B1..B7 (Awakening order) or F1..F5 (Fates-only systems), X = later
  system       data | unit | item | skill | battle | map | ai | event | save | castle |
               dual | vein | live2d_game | amiibo | ui | other
  kind         getter (Get/Is/Has/Can..., const) | query (other const) | mutator |
               ctor | dtor | serialize | other
  words        size in 4-byte words (to the next function start; an upper bound)
  ref_analog   the reference port's readable function this one matched byte-for-byte
               (config/readable/xmap_reference.csv, confidence high/medium), if any
  priority     1 = do first (small const getters of core records and byte-matched
               analogs), 2 = normal, 3 = large or mutating
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "readable"))
import symmap  # noqa: E402

OUT = ROOT / "config" / "readable" / "candidates.csv"
XMAP = ROOT / "config" / "readable" / "xmap_reference.csv"
FIELDS = ["address", "name", "symbol", "batch", "system", "kind", "words", "ref_analog", "priority"]

LIBRARY_TOP = {"nn", "nw", "std", "__rw", "live2d", "pead", "mw", "MoLive", "mobiclip", "Pica", "ism",
               "virtual nn", "virtual nw", "prim", "__cxxabiv1", "sut"}
LIBRARY_NAME = re.compile(r"^(__|_[A-Z]|\.ARM|x\$|operator |__aeabi|__ARM|_fp|_dfix|_ll|"
                          r"(m|c|re|f)alloc|free|mem|str|wcs|printf|sprintf|vsn?printf)")

# (system, batch, regex on the qualified name). First match wins; order matters.
RULES: list[tuple[str, str, re.Pattern]] = [(s, b, re.compile(r)) for s, b, r in (
    ("battle", "B3", r"^(map::Battle(Calculator|Info)|BattleUtil|map::BattleSide|AIBattleSimulator|"
                     r"AIInterferenceSimulator)::"),
    ("battle", "B3", r"^Unit::\w*(Hit|Avoid|Avo|Crit|Critical|Dodge|Atk|Attack|Def|Damage|Power|Pow|Speed|Spd|"
                     r"Luck|Res|Mdf|Magic|Mag|Str|Skl|Tech|Weapon|Range|Exp)\w*$"),
    ("dual", "F2", r"(Dual|Double|PairUp|Pair)"),
    ("vein", "F3", r"(DragonVein|TrickDragon|DragonFocus|DragonAccess)"),
    ("castle", "F1", r"^(castle::|Castle\w*::|Proc(MyRoom|Dining|AcceShop|Jail|Museum|Lilith|MagicCardShop|"
                     r"Fortune|Spa)::|MyCastle|Visit)"),
    ("live2d_game", "F4", r"^(ProcLive2D|Live2D\w*|FaceInstance|ProcSkinship)::"),
    ("amiibo", "F5", r"^(Nfp|Amiibo\w*)::"),
    ("unit", "B2", r"^(Unit|unit::\w+|UnitPool|Transporter)::"),
    ("data", "B1", r"^(Person|Job|Chapter|Terrain\w*|Belong\w*|Dispos\w*|GameData\w*|data::\w+)::"),
    ("item", "B1", r"^(Item|ItemKind|unit::Item|ItemData\w*|Forge\w*|Shop\w*)::"),
    ("skill", "B1", r"^(EquipSkill|Skill\w*)::"),
    ("map", "B4", r"^(map::|Force::|FieldWorld|FieldArea|FieldData|HeightMap|spot::)"),
    ("ai", "B5", r"^(AI\w*|ai::\w+)::"),
    ("event", "B6", r"^(event::|FlagManager\w*|FlagNameManager|VariableManager|ChapterSequence|MainSequence|"
                    r"GameUserData|GameUserGlobalData|GameConfigData|GameProfile|cmvm::)"),
    ("event", "B6", r"^anonymous_namespace::\w+$"),   # script commands take cmvm::CmContext* (checked below)
    ("save", "B7", r"^(Backup|GameBackup|ExtSave|SaveData\w*)::"),
    ("ui", "X", r"(Menu|Window|Drawer|Viewer|Proc\w*|Sequence|Icon|Font|Help|Message)\w*::"),
)]
GETTER = re.compile(r"^(Get|Is|Has|Can|Calc|Find|Count|Num|Check|To|As)[A-Z0-9_]|^(Get|Is|Has|Can)$")
SERIAL = re.compile(r"^(Serialize|Deserialize|SerializePointer|DeserializePointer|Save|Load|Read|Write)")


def classify(sym: symmap.Sym) -> tuple[str, str] | None:
    """(system, batch) or None for library code."""
    q = sym.qualified
    if q.startswith("virtual "):
        q = q[len("virtual "):]
    top = symmap.split_scope(q)[0] if "::" in q else ""
    if top in LIBRARY_TOP or (not top and LIBRARY_NAME.match(q)):
        return None
    for system, batch, rx in RULES:
        if rx.search(q):
            if system == "event" and q.startswith("anonymous_namespace::") and "CmContext" not in sym.name:
                continue
            return system, batch
    return "other", "X"


def kind_of(sym: symmap.Sym) -> str:
    m = sym.method
    is_const = sym.name.rstrip().endswith(" const")
    cls_last = symmap.split_scope(sym.cls)[-1] if sym.cls else ""
    if m.startswith("~"):
        return "dtor"
    if cls_last and m == cls_last:
        return "ctor"
    if SERIAL.match(m):
        return "serialize"
    if GETTER.match(m) and (is_const or not sym.cls or m.startswith(("Is", "Has", "Can", "Get"))):
        return "getter"
    if is_const:
        return "query"
    if re.match(r"^(Set|Add|Sub|Reset|Clear|Update|Create|Delete|Remove|Change|Learn|Inherit|Copy|"
                r"Initialize|Finalize|Free)", m):
        return "mutator"
    return "other"


def priority(system: str, kind: str, words: int, analog: str) -> int:
    if analog:
        return 1
    if kind in ("getter", "query") and words <= 48 and system in ("data", "item", "skill", "unit", "battle"):
        return 1
    if kind in ("mutator", "ctor", "dtor", "serialize") or words > 200:
        return 3
    return 2


def read_analogs(path: Path = XMAP) -> dict[int, str]:
    out = {}
    if path.is_file():
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("confidence") in ("high", "medium") and r.get("address"):
                    out[int(r["address"], 16)] = r["ref_name"]
    return out


def build_rows(syms: list[symmap.Sym], spans: dict[int, int], analogs: dict[int, str]) -> list[dict]:
    rows, seen_names = [], Counter()
    for s in syms:
        if s.addr not in spans:          # Thumb or not a function start this generator knows
            continue
        c = classify(s)
        if c is None:
            continue
        system, batch = c
        k = kind_of(s)
        words = (spans[s.addr] - s.addr) // 4
        an = analogs.get(s.addr, "")
        name = symmap.c_name(s)
        seen_names[name] += 1
        rows.append({"address": f"0x{s.addr:08X}", "name": name, "symbol": s.name, "batch": batch,
                     "system": system, "kind": k, "words": words, "ref_analog": an,
                     "priority": priority(system, k, words, an)})
    for r in rows:                        # overloads share a qualified name: make C names unique
        if seen_names[r["name"]] > 1:
            r["name"] = f"{r['name']}_{r['address'][2:]}"
    rows.sort(key=lambda r: (r["batch"], r["system"], r["priority"], r["address"]))
    return rows


def selftest() -> int:
    fails = 0

    def check(c, what):
        nonlocal fails
        fails += not c
        print(f"  {'ok  ' if c else 'FAIL'} {what}")

    S = symmap.Sym
    cases = [
        (S(0x100, "Unit::GetHitImpl(const unit::Item*) const"), ("battle", "B3"), "getter"),
        (S(0x104, "Unit::GetItemEquipped(void)"), ("unit", "B2"), "getter"),
        (S(0x108, "Person::GetFromFid(const char*)"), ("data", "B1"), "getter"),
        (S(0x10C, "nn::fs::Open(const char*)"), None, None),
        (S(0x110, "map::BattleCalculator::Calculate(void)"), ("battle", "B3"), "other"),
        (S(0x114, "castle::MainSeq::Tick(void)"), ("castle", "F1"), "other"),
        (S(0x118, "GrowSequence::DualLevelUp(void)"), ("dual", "F2"), "other"),
        (S(0x11C, "anonymous_namespace::UnitCanDragonVein(cmvm::CmContext*,int)"), ("vein", "F3"), "other"),
        (S(0x120, "anonymous_namespace::TutorialIsEnable(cmvm::CmContext*)"), ("event", "B6"), "other"),
        (S(0x124, "anonymous_namespace::CalcTangent(int)"), ("other", "X"), "other"),
        (S(0x128, "Unit::Unit(void)"), ("unit", "B2"), "ctor"),
        (S(0x12C, "Unit::~Unit(void)"), ("unit", "B2"), "dtor"),
        (S(0x130, "Job::Deserialize(Stream*)"), ("data", "B1"), "serialize"),
        (S(0x134, "__aeabi_memcpy"), None, None),
        (S(0x138, "Force::IsAllied(Force::Type) const"), ("map", "B4"), "getter"),
        (S(0x13C, "UnitListMenu::Draw(void)"), ("ui", "X"), "other"),
    ]
    for s, want_c, want_k in cases:
        got = classify(s)
        check(got == want_c, f"{s.name}: {got}")
        if want_c:
            check(kind_of(s) == want_k, f"  kind {kind_of(s)}")
    spans = {0x100: 0x120, 0x104: 0x108}
    rows = build_rows([S(0x100, "Unit::GetHit(int) const"), S(0x104, "Unit::GetHit(void) const"),
                       S(0x108, "Unit::GetX(void) const")], spans, {0x104: "unit_hit"})
    check(len(rows) == 2, "symbols that are not known function starts are skipped")
    check(sorted(r["name"] for r in rows) == ["Unit__GetHit_00000100", "Unit__GetHit_00000104"], "overloads made unique")
    check(next(r for r in rows if r["address"] == "0x00000104")["priority"] == 1, "analog -> priority 1")
    print(f"candidates selftest: {'OK' if not fails else f'{fails} failure(s)'}")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    import xmap
    me = xmap.Image.load(ROOT)
    spans, _names = xmap.this_game_functions(me)
    rows = build_rows(symmap.load(), spans, read_analogs())
    by = Counter((r["batch"], r["system"]) for r in rows)
    kinds = Counter(r["kind"] for r in rows)
    pr = Counter(r["priority"] for r in rows)
    for (b, s), n in sorted(by.items()):
        print(f"  {b:3} {s:12} {n:6}")
    print(f"{len(rows)} candidates; kinds {dict(kinds)}; priority {dict(sorted(pr.items()))}")
    if not a.summary:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, FIELDS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
