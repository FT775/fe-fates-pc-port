#!/usr/bin/env python3
"""Per-game named guest addresses (config/readable/addresses.json) for the code-side tools.

    from gameaddr import addr, entry     # tools/readable on sys.path
    addr("guard")                        # int, or LookupError when the game has no value

    python tools/readable/gameaddr.py            list this game's entries
    python tools/readable/gameaddr.py --check    every address that names a symbol must be that
                                                 symbol in the extracted symbol map (exit 1 if not)
    python tools/readable/gameaddr.py --selftest

The entry used is config/game.json "key" (FE_GAME_KEY overrides it, for re-checking the
shared tools against another port).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "tools"))  # gamecfg (appended, never shadowing a same-named tool)
sys.path.insert(0, str(ROOT / "tools" / "readable"))
CONFIG = ROOT / "config" / "readable" / "addresses.json"


def game_key() -> str:
    if os.environ.get("FE_GAME_KEY"):
        return os.environ["FE_GAME_KEY"]
    from gamecfg import GAME
    return GAME.key


def table(key: str | None = None, path: Path = CONFIG) -> dict:
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    key = key or game_key()
    if key not in cfg:
        raise LookupError(f"{path.name} has no entry for game {key!r}")
    return {k: v for k, v in cfg[key].items() if not k.startswith("_")}


def entry(name: str, key: str | None = None, path: Path = CONFIG) -> dict:
    t = table(key, path)
    if name not in t:
        raise LookupError(f"{path.name}: game {key or game_key()!r} has no address {name!r}")
    return t[name]


def addr(name: str, key: str | None = None, path: Path = CONFIG) -> int:
    v = entry(name, key, path).get("address")
    if not v:
        raise LookupError(f"{path.name}: address {name!r} is a TODO for game {key or game_key()!r}")
    return int(v, 16)


def check(key: str | None = None, path: Path = CONFIG) -> list[str]:
    import symmap
    errs = []
    if not symmap.available():
        return ["symbol map not extracted: nothing checked"]
    names = symmap.by_addr()
    for n, e in table(key, path).items():
        if not e.get("address") or not e.get("symbol"):
            continue
        a = int(e["address"], 16)
        got = names.get(a)
        if got != e["symbol"]:
            errs.append(f"{n}: {e['address']} is {got!r} in the symbol map, config says {e['symbol']!r}")
        if e.get("isa") == "arm" and a & 3:
            errs.append(f"{n}: ARM address {e['address']} is not 4-aligned")
    return errs


def selftest() -> int:
    import tempfile
    fails = 0

    def ok(c, what):
        nonlocal fails
        fails += not c
        print(f"  {'ok  ' if c else 'FAIL'} {what}")

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.json"
        p.write_text(json.dumps({"_comment": "x", "g1": {"_comment": "y", "guard": {"address": "0x00100010"},
                                                          "todo": {"address": None}}}))
        ok(addr("guard", "g1", p) == 0x00100010, "address parsed")
        ok(list(table("g1", p)) == ["guard", "todo"], "_comment keys hidden")
        for what, fn in (("TODO raises", lambda: addr("todo", "g1", p)),
                         ("unknown name raises", lambda: addr("nope", "g1", p)),
                         ("unknown game raises", lambda: addr("guard", "g2", p))):
            try:
                fn()
                ok(False, what)
            except LookupError:
                ok(True, what)
    print(f"gameaddr selftest: {'OK' if not fails else f'{fails} failure(s)'}")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    if argv[:1] == ["--check"]:
        errs = check()
        for e in errs:
            print(e)
        n = sum(1 for e in table().values() if e.get("address") and e.get("symbol"))
        bad = [e for e in errs if not e.startswith("symbol map not extracted")]
        print(f"gameaddr check ({game_key()}): {n} named address(es), {len(bad)} problem(s)")
        return 1 if bad else 0
    for n, e in table().items():
        print(f"{n:16} {e.get('address') or 'TODO':12} {e.get('isa', ''):6} {e.get('symbol') or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
