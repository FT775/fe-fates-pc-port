#!/usr/bin/env python3
"""Per-game constants from config/game.json. Import this instead of hard-coding title ids,
paths or names:

    from gamecfg import GAME          # (tools/ on sys.path)
    GAME.title_id, GAME.port.program_name, GAME.seg("text").vaddr
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
CONFIG = Path(os.environ.get("FE_GAME_CONFIG", REPO / "config" / "game.json"))


def _ns(obj):
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_ns(v) for v in obj]
    return obj


def load(path: Path = CONFIG) -> SimpleNamespace:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    g = _ns(raw)
    g.raw = raw
    g.title_id_int = int(raw["title_id"], 16)

    def seg(name: str) -> SimpleNamespace:
        s = raw["segments"][name]
        return SimpleNamespace(vaddr=int(s["vaddr"], 16), size=int(s["size"], 16),
                               end=int(s["vaddr"], 16) + int(s["size"], 16))

    g.seg = seg
    g.env = lambda name: f"{raw['port']['env_prefix']}_{name}"
    return g


GAME = load()

if __name__ == "__main__":
    print(json.dumps(GAME.raw, indent=2))
